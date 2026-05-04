"""CLI subprocess wrapper with background-job event emission.

Wraps the locally-installed ``claude`` CLI as well as ad-hoc generic
subprocesses (test runs, builds, lints, etc.) and emits ``background_job``
lifecycle events into the WAL message bus so the dashboard's frame C
(Background Jobs — FR-UI-1) can render them in real time.

Event shape (consumed by ``dashboard/static/index.html``):

    {
        "event_type": "background_job",   # set by dashboard; type on bus row
        "timestamp": <unix seconds>,
        "metadata": {
            "pid": "<pid as string>",
            "name": "<command + first arg>",
            "status": "running" | "exited" | "failed",
            "exitCode": <int|null>,
            "lastLine": "<trimmed stdout/stderr line, ≤ 200 chars>",
        },
    }

Frequency:
  • One ``running`` event at process start.
  • A ``running`` event with updated ``lastLine`` per stdout/stderr line,
    debounced to at most one emission per 250 ms per pid.
  • One ``exited`` (rc==0) or ``failed`` (rc!=0) event at process exit
    (status transitions bypass the throttle).

The wrapper publishes events through any object exposing a
``publish(Message)`` method (matches ``stream_manager.message_bus.MessageBus``);
tests can substitute a fake bus.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Literal, Protocol

from stream_manager.message_bus import Message

log = logging.getLogger(__name__)

THROTTLE_SECONDS = 0.25
LAST_LINE_MAX_CHARS = 200
EVENT_TYPE = "background_job"

# Task N (v1.1): structured-RPC transport selector. ``"wirecli"``
# routes through stream_manager.wirecli with typed exceptions on parse
# failure. v1.2 (Task E) removed the legacy ``"json"`` value; WireCLI
# is now the only accepted transport and the default. Passing
# ``"json"`` raises ValueError with a CHANGELOG / ADR-15 migration
# hint. See docs/adr/ADR-15-wirecli-transport.md.

# Single-value Literal: kept as a contract surface for future transports; do not collapse to `str`.
Transport = Literal["wirecli"]
DEFAULT_TRANSPORT: Transport = "wirecli"
_VALID_TRANSPORTS: frozenset[str] = frozenset({"wirecli"})

# Migration hint surfaced when a caller still passes the v1.2-removed
# ``"json"`` value. Module-level constant so tests + downstream tools
# (e.g. tools/wirecli_soak_compare.py) can match against it without
# duplicating wording. Mirrors the _LONGPOLL_REMOVED_MSG pattern from
# Task D (PR #44, src/stream_manager/desktop_command_consumer.py).
_JSON_REMOVED_MSG = (
    "cli transport 'json' was removed in v1.2 (deprecated in v1.1, "
    "ADR-15). Use transport='wirecli' (now the default) or unset "
    "BRIDGE_CLI_TRANSPORT. See CHANGELOG.md [Unreleased] Removed "
    "and docs/adr/ADR-15-wirecli-transport.md for migration."
)


def cli_transport(transport: str | None = None) -> Transport:
    """Resolve and validate the CLI transport selector.

    Precedence: explicit arg > ``BRIDGE_CLI_TRANSPORT`` env > default.
    Unknown values raise ``ValueError`` — silent fallback would mask
    typos that matter for soak comparisons.

    v1.2 (Task E) removed ``"json"``; passing it raises ``ValueError``
    with a migration hint pointing at CHANGELOG and ADR-15.
    """
    import os

    chosen = transport or os.environ.get("BRIDGE_CLI_TRANSPORT") or DEFAULT_TRANSPORT
    if chosen == "json":
        raise ValueError(_JSON_REMOVED_MSG)
    if chosen not in _VALID_TRANSPORTS:
        raise ValueError(
            f"unknown cli transport {chosen!r}; "
            f"expected one of {sorted(_VALID_TRANSPORTS)}"
        )
    return chosen  # type: ignore[return-value]


class _BusLike(Protocol):
    def publish(self, msg: Message) -> int: ...


def _job_name(cmd: list[str]) -> str:
    if not cmd:
        return ""
    if len(cmd) == 1:
        return cmd[0]
    return f"{cmd[0]} {cmd[1]}"


def _trim_line(line: str) -> str:
    s = line.rstrip("\r\n")
    if len(s) > LAST_LINE_MAX_CHARS:
        s = s[:LAST_LINE_MAX_CHARS]
    return s


def _emit(
    bus: _BusLike,
    session_id: str,
    *,
    pid: str,
    name: str,
    status: str,
    exit_code: int | None,
    last_line: str,
) -> None:
    metadata: dict[str, object] = {
        "pid": pid,
        "name": name,
        "status": status,
        "exitCode": exit_code,
        "lastLine": last_line,
    }
    msg = Message.new(
        session_id=session_id,
        type=EVENT_TYPE,
        direction="internal",
        content="",
        metadata=metadata,
    )
    try:
        bus.publish(msg)
    except Exception:
        # NFR-R6 parity: never let bus failure crash the wrapped subprocess.
        log.exception("cli_client: failed to publish background_job event")


@dataclass
class JobHandle:
    """Handle for a tracked subprocess. ``wait()`` blocks until exit."""

    pid: int
    name: str
    proc: subprocess.Popen
    _threads: list[threading.Thread]
    _done: threading.Event

    def wait(self, timeout: float | None = None) -> int:
        rc = self.proc.wait(timeout=timeout)
        for t in self._threads:
            t.join(timeout=timeout)
        self._done.wait(timeout=timeout)
        return rc

    def is_running(self) -> bool:
        return self.proc.poll() is None


def track_subprocess(
    cmd: list[str],
    bus: _BusLike,
    session_id: str,
    *,
    popen_factory=subprocess.Popen,
) -> JobHandle:
    """Spawn ``cmd`` as a tracked subprocess and emit lifecycle events.

    Returns immediately with a ``JobHandle``; reader threads stream
    stdout/stderr until the process exits, throttling ``running`` updates
    to one per ``THROTTLE_SECONDS`` per pid.

    ``popen_factory`` is injectable for tests.
    """
    name = _job_name(cmd)
    proc = popen_factory(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    pid_str = str(proc.pid)

    # Initial running event (bypasses throttle).
    _emit(
        bus,
        session_id,
        pid=pid_str,
        name=name,
        status="running",
        exit_code=None,
        last_line="",
    )

    state = {
        "last_emit": 0.0,
        "last_line": "",
        "lock": threading.Lock(),
    }
    done = threading.Event()

    def _reader() -> None:
        assert proc.stdout is not None
        try:
            for raw in proc.stdout:
                line = _trim_line(raw)
                if not line:
                    continue
                now = time.time()
                with state["lock"]:
                    state["last_line"] = line
                    if now - state["last_emit"] >= THROTTLE_SECONDS:
                        state["last_emit"] = now
                        emit_now = True
                    else:
                        emit_now = False
                if emit_now:
                    _emit(
                        bus,
                        session_id,
                        pid=pid_str,
                        name=name,
                        status="running",
                        exit_code=None,
                        last_line=line,
                    )
        except Exception:
            log.exception("cli_client: reader thread error for pid=%s", pid_str)

    def _waiter() -> None:
        try:
            rc = proc.wait()
            reader_t.join()
            with state["lock"]:
                last_line = state["last_line"]
            status = "exited" if rc == 0 else "failed"
            _emit(
                bus,
                session_id,
                pid=pid_str,
                name=name,
                status=status,
                exit_code=int(rc),
                last_line=last_line,
            )
        finally:
            done.set()

    reader_t = threading.Thread(
        target=_reader, name=f"cli_client-reader-{pid_str}", daemon=True
    )
    waiter_t = threading.Thread(
        target=_waiter, name=f"cli_client-waiter-{pid_str}", daemon=True
    )
    reader_t.start()
    waiter_t.start()

    return JobHandle(
        pid=proc.pid,
        name=name,
        proc=proc,
        _threads=[reader_t, waiter_t],
        _done=done,
    )


def wrap_claude(
    extra_args: list[str],
    bus: _BusLike,
    session_id: str,
) -> JobHandle:
    """Wrap a ``claude --no-browser`` subprocess (FR-CC-1) with tracking.

    Existing claude-wrapping behaviour is preserved; the new tracking is
    additive so claude itself shows up in frame C alongside ad-hoc jobs.
    """
    cmd = ["claude", "--no-browser", *extra_args]
    return track_subprocess(cmd, bus, session_id)


def _main(argv: list[str] | None = None) -> int:
    import argparse
    import os
    import sys

    from stream_manager.message_bus import MessageBus

    parser = argparse.ArgumentParser(
        prog="python -m stream_manager.cli_client",
        description="Track a subprocess and emit background_job events to gov.db.",
    )
    parser.add_argument("--session", default="dev", help="session id (default: dev)")
    parser.add_argument(
        "--db",
        default=os.environ.get("GOV_DB", ".claude/gov.db"),
        help="path to gov.db (default: $GOV_DB or .claude/gov.db)",
    )
    parser.add_argument(
        "cmd",
        nargs=argparse.REMAINDER,
        help="command to run, prefix with -- (e.g. -- pytest tests/)",
    )
    args = parser.parse_args(argv)

    cmd = list(args.cmd or [])
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        parser.error("specify a command after --, e.g. -- pytest tests/")

    bus = MessageBus(args.db)
    log.info("cli_client: tracking %r session=%s db=%s", cmd, args.session, args.db)
    handle = track_subprocess(cmd, bus, args.session)
    return handle.wait()


if __name__ == "__main__":
    import sys as _sys

    _sys.exit(_main())
