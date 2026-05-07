"""Unit tests for SessionWatcher (v1.9 P2).

Covers UC-01 acceptance criteria:

* AC-1 (external session registry): ``test_registers_external_session``,
  ``test_emits_exited_on_dead_pid``, ``test_self_monitor_guard_own_cwd``,
  ``test_self_monitor_guard_sm_entrypoint``, ``test_no_duplicate_registration``,
  ``test_missing_fields_skipped``.
* AC-3 (bg task token tracking): ``test_bg_task_ready_on_size_transition``,
  ``test_bg_task_no_emit_while_zero``.

The watcher is exercised in single-tick mode (``poll_once`` /
``poll_bg_tasks_once``) so no background thread is spawned during the
test run. Bus publishes are captured via a stub bus that records every
``Message`` published.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from stream_manager.message_bus import Message
from stream_manager.session_watcher import (
    BG_TASK_POLL_ENV,
    ENVELOPE_BG_READY,
    ENVELOPE_EXITED,
    ENVELOPE_REGISTERED,
    SESSION_WATCHER_POLL_ENV,
    SessionWatcher,
)


# ── Test doubles ───────────────────────────────────────────────────────


@dataclass
class _StubBus:
    """Captures every Message handed to ``publish``."""

    published: list[Message] = field(default_factory=list)

    def publish(self, msg: Message) -> int:
        self.published.append(msg)
        return len(self.published)

    def types(self) -> list[str]:
        return [m.type for m in self.published]

    def metadata_for(self, envelope_type: str) -> list[dict]:
        return [m.metadata for m in self.published if m.type == envelope_type]


class _PidController:
    """Deterministic ``pid_alive`` substitute. Tests flip pids alive/dead."""

    def __init__(self) -> None:
        self.alive: set[int] = set()

    def __call__(self, pid: int) -> bool:
        return pid in self.alive


# ── Helpers ────────────────────────────────────────────────────────────


def _write_session_file(
    sessions_dir: Path,
    *,
    pid: int,
    session_id: str,
    cwd: str,
    entrypoint: str = "claude --model claude-opus-4-7 -p",
    extra: dict | None = None,
) -> Path:
    sessions_dir.mkdir(parents=True, exist_ok=True)
    payload: dict = {
        "pid": pid,
        "sessionId": session_id,
        "cwd": cwd,
        "entrypoint": entrypoint,
    }
    if extra:
        payload.update(extra)
    path = sessions_dir / f"{pid}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _make_watcher(
    *,
    bus: _StubBus,
    sessions_dir: Path,
    pid_alive: _PidController,
    sm_cwd: str = "/nowhere/streamManager-sm",
) -> SessionWatcher:
    return SessionWatcher(
        bus=bus,
        sessions_dir=sessions_dir,
        sm_cwd=sm_cwd,
        sm_session_id="session_watcher",
        poll_interval_s=0.01,
        bg_poll_interval_s=0.01,
        pid_alive=pid_alive,
    )


# ── Tests ──────────────────────────────────────────────────────────────


def test_registers_external_session(tmp_path: Path) -> None:
    """AC-1: a live external session emits external_session_registered."""
    sessions_dir = tmp_path / "sessions"
    bus = _StubBus()
    pid_alive = _PidController()
    pid_alive.alive.add(4242)
    watcher = _make_watcher(
        bus=bus, sessions_dir=sessions_dir, pid_alive=pid_alive
    )
    _write_session_file(
        sessions_dir,
        pid=4242,
        session_id="sess-A",
        cwd="/tmp/extern-project",
        entrypoint="claude -p something",
    )

    watcher.poll_once()

    types = bus.types()
    assert types.count(ENVELOPE_REGISTERED) == 1, types
    meta = bus.metadata_for(ENVELOPE_REGISTERED)[0]
    assert meta["sessionId"] == "sess-A"
    assert meta["pid"] == 4242
    assert meta["cwd"] == "/tmp/extern-project"
    assert meta["entrypoint"] == "claude -p something"
    assert "registered_at" in meta and meta["registered_at"]

    snapshot = watcher.list_active_sessions()
    assert len(snapshot) == 1
    assert snapshot[0]["sessionId"] == "sess-A"
    assert snapshot[0]["state"] == "active"


def test_emits_exited_on_dead_pid(tmp_path: Path) -> None:
    """AC-1: a previously-active session emits external_session_exited."""
    sessions_dir = tmp_path / "sessions"
    bus = _StubBus()
    pid_alive = _PidController()
    pid_alive.alive.add(5555)
    watcher = _make_watcher(
        bus=bus, sessions_dir=sessions_dir, pid_alive=pid_alive
    )
    _write_session_file(
        sessions_dir, pid=5555, session_id="sess-B", cwd="/tmp/proj-b"
    )
    watcher.poll_once()
    assert ENVELOPE_REGISTERED in bus.types()

    # PID dies; next poll must emit exit.
    pid_alive.alive.discard(5555)
    watcher.poll_once()

    types = bus.types()
    assert types.count(ENVELOPE_EXITED) == 1, types
    meta = bus.metadata_for(ENVELOPE_EXITED)[0]
    assert meta["sessionId"] == "sess-B"
    assert meta["pid"] == 5555
    assert meta["exit_time"]

    snapshot = watcher.list_active_sessions()
    assert len(snapshot) == 1
    assert snapshot[0]["state"] == "exited"


def test_self_monitor_guard_own_cwd(tmp_path: Path) -> None:
    """A session whose cwd is SM's cwd is silently skipped."""
    sessions_dir = tmp_path / "sessions"
    bus = _StubBus()
    pid_alive = _PidController()
    pid_alive.alive.add(7777)
    sm_cwd = str(tmp_path / "sm-here")
    Path(sm_cwd).mkdir()
    watcher = _make_watcher(
        bus=bus, sessions_dir=sessions_dir, pid_alive=pid_alive, sm_cwd=sm_cwd
    )
    _write_session_file(
        sessions_dir,
        pid=7777,
        session_id="sess-self",
        cwd=sm_cwd,  # same as SM's cwd
        entrypoint="claude -p arbitrary",
    )

    watcher.poll_once()

    assert bus.types() == []
    assert watcher.list_active_sessions() == []


def test_self_monitor_guard_sm_entrypoint(tmp_path: Path) -> None:
    """An SM-identifying entrypoint is silently skipped."""
    sessions_dir = tmp_path / "sessions"
    bus = _StubBus()
    pid_alive = _PidController()
    pid_alive.alive.add(8888)
    watcher = _make_watcher(
        bus=bus,
        sessions_dir=sessions_dir,
        pid_alive=pid_alive,
        sm_cwd=str(tmp_path / "elsewhere"),
    )
    _write_session_file(
        sessions_dir,
        pid=8888,
        session_id="sess-sm-ep",
        cwd="/tmp/external-cwd",
        entrypoint="python -m stream_manager --service",
    )

    watcher.poll_once()

    assert bus.types() == []
    assert watcher.list_active_sessions() == []


def test_no_duplicate_registration(tmp_path: Path) -> None:
    """A live session polled twice emits external_session_registered once."""
    sessions_dir = tmp_path / "sessions"
    bus = _StubBus()
    pid_alive = _PidController()
    pid_alive.alive.add(1111)
    watcher = _make_watcher(
        bus=bus, sessions_dir=sessions_dir, pid_alive=pid_alive
    )
    _write_session_file(
        sessions_dir, pid=1111, session_id="sess-stable", cwd="/tmp/stable"
    )

    watcher.poll_once()
    watcher.poll_once()
    watcher.poll_once()

    assert bus.types().count(ENVELOPE_REGISTERED) == 1
    assert ENVELOPE_EXITED not in bus.types()


def test_re_register_updates_pid_and_metadata(tmp_path: Path) -> None:
    """PR #102 review fix: re-registration after exit refreshes pid/cwd/entrypoint.

    Without the fix, a re-appearing sessionId retains the dead PID's
    SessionRecord, so the next liveness sweep probes the dead pid and
    emits a spurious external_session_exited envelope.
    """
    sessions_dir = tmp_path / "sessions"
    bus = _StubBus()
    pid_alive = _PidController()
    pid_alive.alive.add(3001)
    watcher = _make_watcher(
        bus=bus, sessions_dir=sessions_dir, pid_alive=pid_alive
    )

    # 1) Register with pid=3001.
    _write_session_file(
        sessions_dir,
        pid=3001,
        session_id="sess-recur",
        cwd="/tmp/old-cwd",
        entrypoint="claude -p old",
    )
    watcher.poll_once()
    assert bus.types().count(ENVELOPE_REGISTERED) == 1

    # 2) PID dies; sweep emits exited.
    pid_alive.alive.discard(3001)
    watcher.poll_once()
    assert bus.types().count(ENVELOPE_EXITED) == 1

    # 3) Same sessionId reappears with NEW pid + new cwd/entrypoint.
    pid_alive.alive.add(3002)
    _write_session_file(
        sessions_dir,
        pid=3002,
        session_id="sess-recur",
        cwd="/tmp/new-cwd",
        entrypoint="claude -p new",
    )
    watcher.poll_once()

    # Re-registration emits ENVELOPE_REGISTERED with NEW metadata.
    registered_meta = bus.metadata_for(ENVELOPE_REGISTERED)
    assert len(registered_meta) == 2
    assert registered_meta[-1]["pid"] == 3002
    assert registered_meta[-1]["cwd"] == "/tmp/new-cwd"
    assert registered_meta[-1]["entrypoint"] == "claude -p new"

    # SessionRecord reflects the live process.
    snapshot = watcher.list_active_sessions()
    assert len(snapshot) == 1
    assert snapshot[0]["pid"] == 3002
    assert snapshot[0]["state"] == "active"

    # 4) One more poll: liveness sweep checks NEW pid (alive). No spurious
    # exited emission on the old pid.
    watcher.poll_once()
    assert bus.types().count(ENVELOPE_EXITED) == 1  # still 1 — no spurious second exit


def test_missing_fields_skipped(tmp_path: Path) -> None:
    """Session JSON missing required fields → no envelope, no exception."""
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    bus = _StubBus()
    pid_alive = _PidController()
    pid_alive.alive.add(2222)
    watcher = _make_watcher(
        bus=bus, sessions_dir=sessions_dir, pid_alive=pid_alive
    )

    # Missing pid.
    (sessions_dir / "missing-pid.json").write_text(
        json.dumps(
            {
                "sessionId": "x",
                "cwd": "/tmp/x",
                "entrypoint": "claude -p y",
            }
        ),
        encoding="utf-8",
    )
    # Missing sessionId.
    (sessions_dir / "missing-sid.json").write_text(
        json.dumps(
            {"pid": 2222, "cwd": "/tmp/y", "entrypoint": "claude -p z"}
        ),
        encoding="utf-8",
    )
    # Garbage JSON.
    (sessions_dir / "garbage.json").write_text("{ not json", encoding="utf-8")

    watcher.poll_once()

    assert bus.types() == []
    assert watcher.list_active_sessions() == []


def _write_jsonl(
    projects_root: Path,
    cwd: str,
    session_id: str,
    records: list[dict],
) -> Path:
    """Write a session JSONL file in the canonical UC-01 layout."""
    slug = cwd.replace("\\", "-").replace("/", "-").strip("-")
    target = projects_root / slug / f"{session_id}.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
    return target


def test_bg_task_ready_on_size_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-3: a tracked bg-task output file going 0 → non-zero emits ready."""
    # Redirect ~/.claude into tmp_path so _derive_jsonl_path resolves
    # against test-controlled state.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    fake_home = tmp_path
    sessions_dir = fake_home / ".claude" / "sessions"
    bus = _StubBus()
    pid_alive = _PidController()
    pid_alive.alive.add(3333)
    watcher = SessionWatcher(
        bus=bus,
        sessions_dir=sessions_dir,
        sm_cwd=str(tmp_path / "sm-cwd"),
        sm_session_id="session_watcher",
        poll_interval_s=0.01,
        bg_poll_interval_s=0.01,
        pid_alive=pid_alive,
    )

    # Register one external session.
    cwd = "/tmp/uc01-ext"
    _write_session_file(
        sessions_dir, pid=3333, session_id="sess-bg", cwd=cwd
    )
    watcher.poll_once()
    assert ENVELOPE_REGISTERED in bus.types()

    # Stage a session JSONL with a backgroundTaskId AND an explicit
    # outputPath so the test does not rely on $TEMP layout.
    output_file = tmp_path / "task-output.txt"
    output_file.write_text("", encoding="utf-8")  # 0 bytes
    _write_jsonl(
        fake_home / ".claude" / "projects",
        cwd=cwd,
        session_id="sess-bg",
        records=[
            {
                "type": "tool_use",
                "name": "Bash",
                "input": {
                    "backgroundTaskId": "tok-XYZ",
                    "outputPath": str(output_file),
                },
            }
        ],
    )

    # First bg poll: token discovered, file is 0 bytes → no envelope.
    watcher.poll_bg_tasks_once()
    assert ENVELOPE_BG_READY not in bus.types()
    pending = watcher.list_pending_bg_tasks()
    assert len(pending) == 1
    assert pending[0]["taskId"] == "tok-XYZ"
    assert pending[0]["output_path"] == str(output_file)

    # Output file becomes non-zero.
    output_file.write_text("done\n", encoding="utf-8")

    # Next bg poll: size transition fires the envelope, token removed.
    watcher.poll_bg_tasks_once()
    assert bus.types().count(ENVELOPE_BG_READY) == 1
    meta = bus.metadata_for(ENVELOPE_BG_READY)[0]
    assert meta["taskId"] == "tok-XYZ"
    assert meta["output_path"] == str(output_file)
    assert meta["originating_session"] == "sess-bg"
    assert meta["start_time"]
    assert meta["ready_at"]

    # Token has been emitted; pending list now empty.
    assert watcher.list_pending_bg_tasks() == []


def test_bg_task_no_emit_while_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-3 negative: 0-byte output across two polls emits nothing.

    Memory: feedback_monitoring_live_sessions — 0 bytes does not mean
    the bg task has completed; output is populated only on chain exit.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    fake_home = tmp_path
    sessions_dir = fake_home / ".claude" / "sessions"
    bus = _StubBus()
    pid_alive = _PidController()
    pid_alive.alive.add(6666)
    watcher = SessionWatcher(
        bus=bus,
        sessions_dir=sessions_dir,
        sm_cwd=str(tmp_path / "sm-cwd"),
        sm_session_id="session_watcher",
        poll_interval_s=0.01,
        bg_poll_interval_s=0.01,
        pid_alive=pid_alive,
    )

    cwd = "/tmp/uc01-zero"
    _write_session_file(
        sessions_dir, pid=6666, session_id="sess-zero", cwd=cwd
    )
    watcher.poll_once()

    output_file = tmp_path / "still-zero.txt"
    output_file.write_text("", encoding="utf-8")
    _write_jsonl(
        fake_home / ".claude" / "projects",
        cwd=cwd,
        session_id="sess-zero",
        records=[
            {
                "backgroundTaskId": "tok-Q",
                "outputPath": str(output_file),
            }
        ],
    )

    # Poll twice; file remains 0 bytes throughout.
    watcher.poll_bg_tasks_once()
    watcher.poll_bg_tasks_once()

    assert ENVELOPE_BG_READY not in bus.types()
    pending = watcher.list_pending_bg_tasks()
    assert len(pending) == 1
    assert pending[0]["taskId"] == "tok-Q"
    assert pending[0]["last_size_bytes"] == 0


# ── Sanity: env vars are honoured for poll-interval overrides ────────


def test_env_poll_interval_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The poll-interval env knobs override the defaults at construction."""
    monkeypatch.setenv(SESSION_WATCHER_POLL_ENV, "1.5")
    monkeypatch.setenv(BG_TASK_POLL_ENV, "12.0")
    bus = _StubBus()
    watcher = SessionWatcher(
        bus=bus,
        sessions_dir=tmp_path / "sessions",
        sm_cwd=str(tmp_path / "sm"),
    )
    assert watcher._poll_interval_s == pytest.approx(1.5)
    assert watcher._bg_poll_interval_s == pytest.approx(12.0)
