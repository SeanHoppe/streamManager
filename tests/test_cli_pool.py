"""Unit tests for CliPool / CliWorker (Task J / v1.1).

Tests use an injected `spawn_fn` to avoid spawning the real `claude` CLI.
The fake implements just enough of the stream-json protocol to round-trip
one user-message → result envelope. Tests that exercise the real binary
are guarded by ``cli_on_path`` and skipped on no-CLI hosts (mirrors the
existing pattern in tools/soak_driver.py).
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import threading
import time
from pathlib import Path

import pytest

from stream_manager import cli_pool
from stream_manager.cli_pool import (
    CliPool,
    CliWorker,
    cli_on_path,
    reap_stale_workers,
)


# ── Fakes ────────────────────────────────────────────────────────────────

class _FakeStdin:
    def __init__(self, parent: "_FakeProc") -> None:
        self._parent = parent
        self._buf: list[str] = []
        self.closed = False

    def write(self, s: str) -> int:
        if self.closed:
            raise BrokenPipeError("stdin closed")
        self._buf.append(s)
        # Each newline-terminated line triggers one response on stdout.
        if s.endswith("\n"):
            self._parent._on_user_message("".join(self._buf))
            self._buf = []
        return len(s)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class _FakeStdout:
    """Iterable line stream backed by a thread-safe queue of pending lines."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._lines: list[str] = []
        self._closed = False

    def push(self, line: str) -> None:
        with self._cond:
            self._lines.append(line)
            self._cond.notify_all()

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    def __iter__(self):
        return self

    def __next__(self) -> str:
        with self._cond:
            while not self._lines and not self._closed:
                self._cond.wait()
            if self._lines:
                return self._lines.pop(0)
            raise StopIteration


class _FakeProc:
    """Minimal Popen stand-in implementing the stream-json round-trip."""

    _id_counter = 0

    def __init__(
        self,
        *,
        result_action: str = "ALLOW",
        decode_corrupt: bool = False,
        die_on_first_message: bool = False,
    ) -> None:
        _FakeProc._id_counter += 1
        # Use a synthetic large pid so reap_stale_workers tests are
        # cross-platform (psutil.Process(pid) for nonexistent pids raises).
        self.pid = 90000 + _FakeProc._id_counter
        self.stdin = _FakeStdin(self)
        self.stdout = _FakeStdout()
        self.stderr = io.StringIO()
        self._returncode: int | None = None
        self._result_action = result_action
        self._decode_corrupt = decode_corrupt
        self._die_on_first_message = die_on_first_message
        self.calls = 0

    # Popen-shaped API
    def poll(self) -> int | None:
        return self._returncode

    def wait(self, timeout: float | None = None) -> int:
        if self._returncode is None:
            self._returncode = 0
        return self._returncode

    def terminate(self) -> None:
        if self._returncode is None:
            self._returncode = -15
        self.stdout.close()

    def kill(self) -> None:
        if self._returncode is None:
            self._returncode = -9
        self.stdout.close()

    # Wire protocol
    def _on_user_message(self, line: str) -> None:
        self.calls += 1
        if self._die_on_first_message and self.calls == 1:
            self._returncode = 1
            self.stdout.close()
            return
        if self._decode_corrupt:
            self.stdout.push("not json at all\n")
            return
        # Push a couple of intermediate events first, then the result envelope.
        self.stdout.push(json.dumps({"type": "system", "subtype": "info"}) + "\n")
        envelope = {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": json.dumps(
                {
                    "action": self._result_action,
                    "confidence": 0.9,
                    "reasoning": "fake",
                }
            ),
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "total_cost_usd": 0.0001,
        }
        self.stdout.push(json.dumps(envelope) + "\n")


def _make_spawn(**kwargs):
    """Return a spawn_fn that produces _FakeProc instances and tracks them."""
    spawned: list[_FakeProc] = []

    def _spawn(cmd):
        p = _FakeProc(**kwargs)
        spawned.append(p)
        return p

    _spawn.spawned = spawned  # type: ignore[attr-defined]
    return _spawn


# ── Tests ────────────────────────────────────────────────────────────────

def test_acquire_release_round_trip(tmp_path: Path) -> None:
    spawn = _make_spawn()
    pool = CliPool(size=2, spawn_fn=spawn, pid_root=tmp_path)
    pool.warmup()
    try:
        assert len(spawn.spawned) == 2  # type: ignore[attr-defined]

        with pool.acquire() as w:
            stdout = w.send("hello")
        env = json.loads(stdout)
        assert env["type"] == "result"
        assert json.loads(env["result"])["action"] == "ALLOW"
    finally:
        pool.shutdown()


def test_acquire_ordering_round_robin(tmp_path: Path) -> None:
    spawn = _make_spawn()
    pool = CliPool(size=2, spawn_fn=spawn, pid_root=tmp_path)
    pool.warmup()
    try:
        seen: set[int] = set()
        for _ in range(4):
            with pool.acquire() as w:
                seen.add(w.pid or 0)
                w.send("ping")
        # Both workers should have served at least one call.
        assert len(seen) == 2
    finally:
        pool.shutdown()


def test_recycle_after_n_calls(tmp_path: Path) -> None:
    spawn = _make_spawn()
    pool = CliPool(size=1, spawn_fn=spawn, pid_root=tmp_path, calls_per_recycle=3)
    pool.warmup()
    try:
        first_pid = pool._all[0].pid  # noqa: SLF001 - test only
        for _ in range(3):
            with pool.acquire() as w:
                w.send("x")
        # On release after the 3rd call, the worker hits the recycle threshold
        # and is replaced. The next acquire should yield a fresh pid.
        with pool.acquire() as w:
            assert w.pid != first_pid
        # Three workers spawned: the original + the post-recycle replacement
        # made at release time. Acquiring after did NOT spawn another (the
        # replacement was already in the queue).
        assert len(spawn.spawned) == 2  # type: ignore[attr-defined]
    finally:
        pool.shutdown()


def test_recycle_on_decode_error(tmp_path: Path) -> None:
    spawn = _make_spawn(decode_corrupt=True)
    pool = CliPool(size=1, spawn_fn=spawn, pid_root=tmp_path)
    pool.warmup()
    try:
        # First acquire: send raises on decode error (caller treats this as
        # a worker fault — the context-manager release recycles).
        with pytest.raises(RuntimeError):
            with pool.acquire() as w:
                w.send("x")
        # Second acquire: a fresh worker has been substituted.
        assert len(spawn.spawned) == 2  # type: ignore[attr-defined]
    finally:
        pool.shutdown()


def test_health_probe_replaces_dead_worker(tmp_path: Path) -> None:
    spawn = _make_spawn()
    pool = CliPool(size=1, spawn_fn=spawn, pid_root=tmp_path)
    pool.warmup()
    try:
        # Simulate the worker dying while sitting idle.
        worker = pool._all[0]  # noqa: SLF001
        worker._proc._returncode = 0  # noqa: SLF001
        worker._alive = False  # noqa: SLF001

        with pool.acquire() as w:
            assert w.pid != worker.pid
            w.send("x")
        assert len(spawn.spawned) == 2  # type: ignore[attr-defined]
    finally:
        pool.shutdown()


def test_shutdown_kills_all_workers(tmp_path: Path) -> None:
    spawn = _make_spawn()
    pool = CliPool(size=3, spawn_fn=spawn, pid_root=tmp_path)
    pool.warmup()
    procs = list(spawn.spawned)  # type: ignore[attr-defined]
    pool.shutdown()
    assert all(p.poll() is not None for p in procs)
    # Idempotent
    pool.shutdown()
    # PID file cleared on shutdown.
    assert not (tmp_path / cli_pool.PID_FILE_RELATIVE).exists()


def test_shutdown_blocks_new_acquire(tmp_path: Path) -> None:
    spawn = _make_spawn()
    pool = CliPool(size=1, spawn_fn=spawn, pid_root=tmp_path)
    pool.warmup()
    pool.shutdown()
    with pytest.raises(RuntimeError):
        pool.acquire()


def test_pid_file_appended_per_spawn(tmp_path: Path) -> None:
    spawn = _make_spawn()
    pool = CliPool(size=2, spawn_fn=spawn, pid_root=tmp_path)
    pool.warmup()
    try:
        pid_file = tmp_path / cli_pool.PID_FILE_RELATIVE
        assert pid_file.exists()
        pids = [int(line) for line in pid_file.read_text().splitlines() if line.strip()]
        assert len(pids) == 2
        assert set(pids) == {w.pid for w in pool._all}  # noqa: SLF001
    finally:
        pool.shutdown()


def test_reap_stale_workers_no_psutil(tmp_path: Path, monkeypatch) -> None:
    # Seed a pid file with a definitely-not-running pid.
    pid_file = tmp_path / cli_pool.PID_FILE_RELATIVE
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text("999999\n", encoding="utf-8")

    # Force the no-psutil path: the function imports psutil lazily, so we
    # patch sys.modules to mask it during the call.
    import sys
    saved = sys.modules.get("psutil")
    sys.modules["psutil"] = None  # type: ignore[assignment]
    try:
        # Should not raise even when psutil is missing.
        reap_stale_workers(root=tmp_path)
    finally:
        if saved is not None:
            sys.modules["psutil"] = saved
        else:
            sys.modules.pop("psutil", None)
    # Pid file cleared even if no kill was possible.
    assert not pid_file.exists()


def test_release_after_failure_recycles(tmp_path: Path) -> None:
    spawn = _make_spawn()
    pool = CliPool(size=1, spawn_fn=spawn, pid_root=tmp_path)
    pool.warmup()
    try:
        first_pid = pool._all[0].pid  # noqa: SLF001
        try:
            with pool.acquire() as w:
                # Force an exception inside the with-block. The handle's
                # __exit__ should mark the worker as failed and recycle.
                raise ValueError("boom")
        except ValueError:
            pass
        with pool.acquire() as w:
            assert w.pid != first_pid
    finally:
        pool.shutdown()


def test_size_validation() -> None:
    with pytest.raises(ValueError):
        CliPool(size=0)


# ── v2.0 P1: worker_recycle_every_n A/B kwarg ──────────────────────────

def test_worker_recycle_every_n_none_is_status_quo(tmp_path: Path) -> None:
    """Default ``None`` preserves byte-identical v1.9 behaviour: the pool's
    ``_calls_per_recycle`` falls back to module-level CALLS_PER_RECYCLE.
    """
    spawn = _make_spawn()
    pool = CliPool(size=1, spawn_fn=spawn, pid_root=tmp_path)
    pool.warmup()
    try:
        assert pool._calls_per_recycle == cli_pool.CALLS_PER_RECYCLE  # noqa: SLF001
        assert pool._worker_recycle_every_n is None  # noqa: SLF001
        first_pid = pool._all[0].pid  # noqa: SLF001
        # 5 sends should not trigger recycle (CALLS_PER_RECYCLE = 50).
        for _ in range(5):
            with pool.acquire() as w:
                w.send("x")
        with pool.acquire() as w:
            assert w.pid == first_pid  # same worker reused
        assert len(spawn.spawned) == 1  # type: ignore[attr-defined]
    finally:
        pool.shutdown()


@pytest.mark.parametrize("n", [1, 5])
def test_worker_recycle_every_n_respawns_after_n_sends(tmp_path: Path, n: int) -> None:
    """When ``worker_recycle_every_n`` is set to N, the pool recycles each
    worker after exactly N successful sends (matching the existing
    calls-per-recycle contract).
    """
    spawn = _make_spawn()
    pool = CliPool(
        size=1, spawn_fn=spawn, pid_root=tmp_path, worker_recycle_every_n=n
    )
    pool.warmup()
    try:
        assert pool._calls_per_recycle == n  # noqa: SLF001
        assert pool._worker_recycle_every_n == n  # noqa: SLF001
        first_pid = pool._all[0].pid  # noqa: SLF001
        # Send N times: at release after the Nth call, the worker hits the
        # recycle threshold and is replaced.
        for _ in range(n):
            with pool.acquire() as w:
                w.send("x")
        with pool.acquire() as w:
            assert w.pid != first_pid  # fresh worker
        # Two workers spawned: original + post-recycle replacement.
        assert len(spawn.spawned) == 2  # type: ignore[attr-defined]
    finally:
        pool.shutdown()


def test_worker_recycle_every_n_validates_positive() -> None:
    with pytest.raises(ValueError):
        CliPool(size=1, worker_recycle_every_n=0)
    with pytest.raises(ValueError):
        CliPool(size=1, worker_recycle_every_n=-1)


# ── Real-CLI smoke (skipped when claude is not on PATH) ─────────────────

requires_cli = pytest.mark.skipif(
    not cli_on_path(),
    reason="`claude` CLI not on PATH; pool real-spawn smoke skipped",
)


def test_cli_governor_uses_pool_when_provided(tmp_path: Path, monkeypatch) -> None:
    """End-to-end: CliGovernor wired with a pool routes through it."""
    from stream_manager.cli_governance import CliGovernor
    from stream_manager.project_context import ProjectContextSnapshot

    monkeypatch.setenv("BRIDGE_API_GOV", "1")

    spawn = _make_spawn(result_action="SUGGEST")
    pool = CliPool(size=1, spawn_fn=spawn, pid_root=tmp_path)
    pool.warmup()
    try:
        snap = ProjectContextSnapshot(repo_path="/x", intent_text="test")

        # Sentinel runner that fails the test if it gets called — the pool
        # path must NOT fall through to subprocess.run.
        def _no_runner(*args, **kwargs):
            raise AssertionError("subprocess.run should not be called when pool is set")

        gov = CliGovernor(snap, runner=_no_runner, pool=pool)
        decision = gov.evaluate("ship the feature to prod")
        assert decision is not None
        assert decision.action == "SUGGEST"
        assert decision.confidence == pytest.approx(0.9)
    finally:
        pool.shutdown()


@requires_cli
def test_real_cli_spawn_and_kill(tmp_path: Path) -> None:
    """Sanity: a real `claude` worker spawns, accepts kill(), and exits."""
    pool = CliPool(size=1, pid_root=tmp_path)
    pool.warmup()
    try:
        worker = pool._all[0]  # noqa: SLF001
        assert worker.is_alive()
        assert worker.pid is not None
    finally:
        pool.shutdown()
