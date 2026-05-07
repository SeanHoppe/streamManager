"""Warm-pool of long-lived ``claude`` CLI subprocesses.

v1.1 / Task J. Spawn-per-call governance escalation pays the full Node-runtime
+ auth cold-start on every L2/L3/L4 call, which dominates the v1.0 p50 budget
(see ADR-5 latency budget rationale). This module reuses a small pool of
already-warm ``claude`` subprocesses across calls. Each worker accepts one
prompt at a time over stdin (stream-json input), reads one JSON envelope
back over stdout, and is then returned to the pool.

Design notes:

  * Transport: ``claude -p --input-format stream-json --output-format
    stream-json --include-partial-messages=false --no-session-persistence
    --tools "" --model <id>``. The process stays alive between turns; we
    write one JSONL user-message per request and read until we see the
    matching ``result`` envelope on stdout.

  * Recycle policy: after ``CALLS_PER_RECYCLE`` successful calls (default
    50) OR on ANY decode error / non-JSON output, the worker is killed
    and respawned. This bounds in-process state accumulation in the CLI
    runtime (memory, accumulated context, etc.).

  * Health probe at acquire(): write a one-byte JSONL keep-alive and
    expect a non-empty response within ``HEALTH_TIMEOUT_S`` seconds.
    Probe failure → kill + respawn before returning the worker.

  * PID tracking: each spawned worker's PID is appended to
    ``.bridge/cli-pool.pids``. ``reap_stale_workers()`` is called by
    long-lived consumers at boot to terminate any leftover ``claude``
    processes from a prior crashed run before opening a new pool.

  * Windows: SIGTERM does not exist; ``Process.terminate()`` (which sends
    CTRL_BREAK_EVENT / TerminateProcess on win32) is used everywhere.

This module deliberately does NOT import psutil at module top — the
import is delayed to ``reap_stale_workers`` so unit tests on a no-psutil
host can still exercise the pool primitives via the injected spawner.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

log = logging.getLogger(__name__)

CLI_BIN = "claude"
DEFAULT_MODEL = "claude-haiku-4-5"
CALLS_PER_RECYCLE = 50
HEALTH_TIMEOUT_S = 2.0
RESPONSE_TIMEOUT_S = 25.0
SHUTDOWN_TIMEOUT_S = 5.0
PID_FILE_RELATIVE = ".bridge/cli-pool.pids"


SpawnFn = Callable[[list[str]], subprocess.Popen]


def _default_spawn(cmd: list[str]) -> subprocess.Popen:
    """Default Popen factory: stdin/stdout pipes, line-buffered text mode."""
    creationflags = 0
    if os.name == "nt":
        # CREATE_NEW_PROCESS_GROUP allows the parent to send signals
        # without affecting itself; useful for clean termination.
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    return subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )


def _build_cmd(model: str, system_prompt: str | None) -> list[str]:
    cmd = [
        CLI_BIN, "-p",
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        # claude requires --verbose alongside --output-format=stream-json;
        # without it the process exits immediately with an error.
        "--verbose",
        "--model", model,
        "--no-session-persistence",
        "--tools", "",
    ]
    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])
    return cmd


def _pid_file_path(root: Path | None = None) -> Path:
    base = root if root is not None else Path.cwd()
    return base / PID_FILE_RELATIVE


def _append_pid(pid: int, root: Path | None = None) -> None:
    p = _pid_file_path(root)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(f"{pid}\n")
    except OSError:
        log.exception("cli_pool: failed to append pid to %s", p)


def _read_pid_file(root: Path | None = None) -> list[int]:
    p = _pid_file_path(root)
    if not p.exists():
        return []
    pids: list[int] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                pids.append(int(line))
            except ValueError:
                continue
    except OSError:
        log.exception("cli_pool: failed to read pid file %s", p)
    return pids


def _clear_pid_file(root: Path | None = None) -> None:
    p = _pid_file_path(root)
    try:
        if p.exists():
            p.unlink()
    except OSError:
        log.exception("cli_pool: failed to clear pid file %s", p)


def reap_stale_workers(root: Path | None = None) -> int:
    """Kill any PIDs recorded in the pid-file whose command-line still looks
    like a ``claude`` process. Returns the count of processes killed.

    Safe to call when psutil is unavailable — degrades to a best-effort
    ``Popen`` -free SIGTERM via os.kill on POSIX, no-op on Windows.
    """
    pids = _read_pid_file(root)
    if not pids:
        _clear_pid_file(root)
        return 0
    killed = 0
    try:
        import psutil  # type: ignore
    except ImportError:
        psutil = None  # type: ignore[assignment]
    for pid in pids:
        if psutil is not None:
            try:
                proc = psutil.Process(pid)
                name = (proc.name() or "").lower()
                if "claude" in name or "node" in name:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2.0)
                    except psutil.TimeoutExpired:
                        proc.kill()
                    killed += 1
            except psutil.NoSuchProcess:
                continue
            except Exception:
                log.exception("cli_pool: reaper failed for pid=%d", pid)
        else:
            # Best-effort POSIX kill; on Windows w/o psutil we skip.
            if os.name != "nt":
                try:
                    os.kill(pid, 15)  # SIGTERM
                    killed += 1
                except ProcessLookupError:
                    continue
                except Exception:
                    log.exception("cli_pool: os.kill failed for pid=%d", pid)
    _clear_pid_file(root)
    return killed


@dataclass
class CliWorker:
    """A long-lived ``claude`` subprocess that serves one prompt at a time."""

    model: str
    system_prompt: str | None = None
    _proc: subprocess.Popen | None = None
    _calls: int = 0
    _spawn_fn: SpawnFn = field(default=_default_spawn)
    _pid_root: Path | None = None
    _stdout_q: "queue.Queue[str]" = field(default_factory=queue.Queue)
    _reader_thread: threading.Thread | None = None
    _alive: bool = False

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc is not None else None

    @property
    def calls(self) -> int:
        return self._calls

    def is_alive(self) -> bool:
        return self._alive and self._proc is not None and self._proc.poll() is None

    def spawn(self) -> None:
        """Start the underlying ``claude`` process and reader thread."""
        if self._proc is not None:
            return
        cmd = _build_cmd(self.model, self.system_prompt)
        log.debug("cli_pool: spawning worker cmd=%r", cmd)
        self._proc = self._spawn_fn(cmd)
        self._alive = True
        self._calls = 0
        if self._proc.pid:
            _append_pid(self._proc.pid, self._pid_root)
        self._stdout_q = queue.Queue()
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name=f"cli-pool-reader-{self._proc.pid}",
            daemon=True,
        )
        self._reader_thread.start()

    def _reader_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            for line in proc.stdout:
                line = line.rstrip("\r\n")
                if not line:
                    continue
                self._stdout_q.put(line)
        except Exception:
            log.exception("cli_pool: reader loop crashed for pid=%s", self.pid)
        finally:
            # Sentinel so any pending recv unblocks.
            self._stdout_q.put("")

    def send(self, user_text: str, *, timeout: float = RESPONSE_TIMEOUT_S) -> str:
        """Send one user message and return the raw stdout JSON envelope.

        Implements the ``stream-json`` ↔ ``stream-json`` protocol:
          * write a single JSONL line with role=user
          * read JSONL lines from stdout until the ``result`` envelope is
            seen, then return that envelope's full JSON line
          * raise ``RuntimeError`` on any decode error so the pool can
            recycle the worker (per the recycle-on-decode-error contract)
        """
        if not self.is_alive():
            raise RuntimeError("worker is not alive")
        proc = self._proc
        assert proc is not None and proc.stdin is not None

        msg = {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": user_text}],
            },
            "session_id": str(uuid.uuid4()),
            "parent_tool_use_id": None,
        }
        try:
            proc.stdin.write(json.dumps(msg) + "\n")
            proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            self._alive = False
            raise RuntimeError(f"stdin write failed: {e}") from e

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("response timeout")
            try:
                line = self._stdout_q.get(timeout=remaining)
            except queue.Empty:
                raise RuntimeError("response timeout") from None
            if not line:
                # Sentinel — process exited.
                self._alive = False
                raise RuntimeError("worker process exited mid-response")
            try:
                envelope = json.loads(line)
            except json.JSONDecodeError as e:
                # Per spec: any decode error → caller should recycle the worker.
                raise RuntimeError(f"decode error: {e}; line={line[:200]!r}") from e
            if not isinstance(envelope, dict):
                continue
            if envelope.get("type") == "result":
                self._calls += 1
                return line
            # Other event types (system, assistant partial, etc.) — keep reading.

    def health_probe(self, *, timeout: float = HEALTH_TIMEOUT_S) -> bool:
        """Best-effort liveness check. Returns True if the underlying process
        still has its pipe open; False otherwise. We deliberately do NOT
        send a user-turn here because that would consume real model tokens
        on every acquire(); a process-poll is sufficient given the recycle
        policy already protects against accumulated state.
        """
        if not self.is_alive():
            return False
        # Drain any leftover stdout fragments from a previous turn so the
        # next send() starts clean.
        drained = 0
        while drained < 100:
            try:
                self._stdout_q.get_nowait()
                drained += 1
            except queue.Empty:
                break
        return self.is_alive()

    def kill(self) -> None:
        """Terminate the underlying process. Idempotent."""
        self._alive = False
        proc = self._proc
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=SHUTDOWN_TIMEOUT_S)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    try:
                        proc.wait(timeout=1.0)
                    except subprocess.TimeoutExpired:
                        pass
        finally:
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                try:
                    if stream is not None:
                        stream.close()
                except Exception:
                    pass
            self._proc = None


class CliPool:
    """Bounded pool of long-lived ``claude`` workers.

    Acquire/release pattern (preferred — context-manager):

        pool = CliPool(size=2)
        with pool.acquire() as worker:
            envelope = worker.send("...prompt...")

    The pool guarantees:
      * at most ``size`` warm workers exist concurrently
      * a worker is recycled (killed + respawned) after ``CALLS_PER_RECYCLE``
        successful calls or on any RuntimeError raised by ``worker.send``
      * ``shutdown()`` kills every worker, clears the pid file, and is
        idempotent
    """

    def __init__(
        self,
        size: int = 2,
        model: str | None = None,
        *,
        system_prompt: str | None = None,
        spawn_fn: SpawnFn | None = None,
        pid_root: Path | None = None,
        calls_per_recycle: int = CALLS_PER_RECYCLE,
        worker_recycle_every_n: int | None = None,
    ) -> None:
        # ``worker_recycle_every_n`` (v2.0 P1): when set, overrides
        # ``calls_per_recycle`` with a smaller per-worker call budget so
        # the pool tests the warm-process-bias hypothesis (per-turn
        # isolation A/B). Default ``None`` preserves byte-identical v1.9
        # behaviour. ``CliWorker.send`` signature is unchanged; the
        # recycle decision lives at release time in ``_release``.
        if size < 1:
            raise ValueError("size must be >= 1")
        if worker_recycle_every_n is not None and worker_recycle_every_n < 1:
            raise ValueError("worker_recycle_every_n must be >= 1 when set")
        self._size = size
        self._model = model or DEFAULT_MODEL
        self._system_prompt = system_prompt
        self._spawn_fn: SpawnFn = spawn_fn or _default_spawn
        self._pid_root = pid_root
        self._calls_per_recycle = (
            worker_recycle_every_n
            if worker_recycle_every_n is not None
            else calls_per_recycle
        )
        self._worker_recycle_every_n = worker_recycle_every_n
        self._available: "queue.Queue[CliWorker]" = queue.Queue()
        self._all: list[CliWorker] = []
        self._lock = threading.Lock()
        self._shut = False
        # Pre-spawn lazily — the first acquire() pays the cold-start cost
        # on the calling thread, but subsequent acquires reuse the worker.
        # Long-lived consumers (dashboard, soak driver) call ``warmup()``
        # at boot so the first governance call is already fast.

    @property
    def size(self) -> int:
        return self._size

    def warmup(self) -> None:
        """Pre-spawn ``size`` workers up front. Called by long-lived consumers."""
        with self._lock:
            if self._shut:
                raise RuntimeError("pool is shut down")
            while len(self._all) < self._size:
                w = self._make_worker()
                self._all.append(w)
                self._available.put(w)

    def _make_worker(self) -> CliWorker:
        w = CliWorker(
            model=self._model,
            system_prompt=self._system_prompt,
            _spawn_fn=self._spawn_fn,
            _pid_root=self._pid_root,
        )
        w.spawn()
        return w

    def _replace_worker(self, dead: CliWorker) -> CliWorker:
        """Kill ``dead`` and substitute a fresh worker in the all-list."""
        try:
            dead.kill()
        except Exception:
            log.exception("cli_pool: kill failed during replace")
        with self._lock:
            try:
                idx = self._all.index(dead)
            except ValueError:
                idx = -1
            fresh = self._make_worker()
            if idx >= 0:
                self._all[idx] = fresh
            else:
                self._all.append(fresh)
            return fresh

    class _Handle:
        """Context-manager wrapper around a checked-out worker."""

        def __init__(self, pool: "CliPool", worker: CliWorker) -> None:
            self._pool = pool
            self._worker = worker
            self._failed = False

        def __enter__(self) -> CliWorker:
            return self._worker

        def __exit__(self, exc_type, exc, tb) -> None:
            # Any exception inside the with-block is treated as a worker
            # failure — recycle it before returning to the pool.
            self._failed = exc_type is not None
            self._pool._release(self._worker, failed=self._failed)
            # Do not suppress exceptions.
            return None

    def acquire(self, *, timeout: float | None = None) -> "CliPool._Handle":
        """Check out a worker. Blocks up to ``timeout`` seconds, then raises
        ``queue.Empty`` if no worker is available.
        """
        if self._shut:
            raise RuntimeError("pool is shut down")
        # Lazy first-fill: if no worker has been spawned yet, spawn one on
        # demand so callers that skipped ``warmup()`` still work.
        with self._lock:
            if not self._all:
                w = self._make_worker()
                self._all.append(w)
                self._available.put(w)
        worker = self._available.get(timeout=timeout)
        # Health probe: if the process died while idle, recycle.
        if not worker.health_probe():
            worker = self._replace_worker(worker)
        return CliPool._Handle(self, worker)

    def release(self, worker: CliWorker) -> None:
        """Public release — back-compat for non-context-manager use.

        Prefer the ``with pool.acquire() as w:`` form; release() is provided
        for callers that cannot use ``with`` (e.g. async paths that hold the
        worker across awaits).
        """
        self._release(worker, failed=False)

    def _release(self, worker: CliWorker, *, failed: bool) -> None:
        if self._shut:
            # Don't re-pool into a shutdown pool — just kill.
            try:
                worker.kill()
            except Exception:
                pass
            return
        if failed or not worker.is_alive() or worker.calls >= self._calls_per_recycle:
            worker = self._replace_worker(worker)
        self._available.put(worker)

    def shutdown(self) -> None:
        """Kill every worker. Idempotent. Clears the pid file."""
        with self._lock:
            if self._shut:
                return
            self._shut = True
            workers = list(self._all)
            self._all.clear()
        for w in workers:
            try:
                w.kill()
            except Exception:
                log.exception("cli_pool: shutdown kill failed")
        # Drain the available queue so any blocked acquire() doesn't hand
        # out stale workers.
        try:
            while True:
                self._available.get_nowait()
        except queue.Empty:
            pass
        _clear_pid_file(self._pid_root)


def cli_on_path() -> bool:
    """Mirror of soak_driver._check_cli_on_path; used by tests to skip."""
    return shutil.which(CLI_BIN) is not None or shutil.which(f"{CLI_BIN}.exe") is not None


__all__ = [
    "CALLS_PER_RECYCLE",
    "CliPool",
    "CliWorker",
    "DEFAULT_MODEL",
    "HEALTH_TIMEOUT_S",
    "PID_FILE_RELATIVE",
    "RESPONSE_TIMEOUT_S",
    "cli_on_path",
    "reap_stale_workers",
]
