"""Tests for cli_client.track_subprocess background_job emission (FR-UI-1 frame C)."""

from __future__ import annotations

import sys
import threading
import time

import pytest

from stream_manager.cli_client import (
    LAST_LINE_MAX_CHARS,
    THROTTLE_SECONDS,
    track_subprocess,
)
from stream_manager.message_bus import Message


class _FakeBus:
    def __init__(self) -> None:
        self.events: list[Message] = []
        self._lock = threading.Lock()
        self._seq = 0

    def publish(self, msg: Message) -> int:
        with self._lock:
            self._seq += 1
            msg.sequence = self._seq
            self.events.append(msg)
            return self._seq


def _job_events(bus: _FakeBus) -> list[dict]:
    return [
        {**e.metadata, "type": e.type, "direction": e.direction}
        for e in bus.events
    ]


def _wait_until(predicate, timeout: float = 5.0, interval: float = 0.05) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def test_short_subprocess_emits_running_then_exited():
    bus = _FakeBus()
    cmd = [sys.executable, "-c", "print('hello world')"]
    handle = track_subprocess(cmd, bus, session_id="s-test")
    rc = handle.wait(timeout=10)

    assert rc == 0
    assert _wait_until(lambda: any(e.metadata.get("status") == "exited" for e in bus.events))

    statuses = [e.metadata["status"] for e in bus.events]
    assert statuses[0] == "running"
    assert statuses[-1] == "exited"

    first = bus.events[0]
    assert first.type == "background_job"
    assert first.direction == "internal"
    assert first.metadata["pid"] == str(handle.pid)
    assert first.metadata["name"].startswith(sys.executable)
    assert first.metadata["exitCode"] is None
    assert first.metadata["lastLine"] == ""

    last = bus.events[-1]
    assert last.metadata["exitCode"] == 0
    assert "hello world" in last.metadata["lastLine"]


def test_failing_subprocess_emits_failed_with_exit_code():
    bus = _FakeBus()
    cmd = [sys.executable, "-c", "import sys; sys.exit(7)"]
    handle = track_subprocess(cmd, bus, session_id="s-fail")
    rc = handle.wait(timeout=10)

    assert rc == 7
    assert _wait_until(lambda: any(e.metadata.get("status") == "failed" for e in bus.events))

    last = bus.events[-1]
    assert last.metadata["status"] == "failed"
    assert last.metadata["exitCode"] == 7


def test_high_frequency_lines_are_throttled():
    bus = _FakeBus()
    # Print 50 lines back-to-back; with THROTTLE_SECONDS=0.25 the runtime
    # is well under one window so we expect far fewer than 50 running
    # events with non-empty lastLine. The terminal exited event always
    # bypasses the throttle.
    code = (
        "import sys\n"
        "for i in range(50):\n"
        "    sys.stdout.write(f'line {i}\\n')\n"
        "    sys.stdout.flush()\n"
    )
    cmd = [sys.executable, "-c", code]
    handle = track_subprocess(cmd, bus, session_id="s-throttle")
    rc = handle.wait(timeout=10)
    assert rc == 0
    assert _wait_until(lambda: any(e.metadata.get("status") == "exited" for e in bus.events))

    running_with_line = [
        e for e in bus.events
        if e.metadata.get("status") == "running" and e.metadata.get("lastLine")
    ]
    # At most ~5 running-with-line events expected (50 lines / 10ms ≈ 0.5s
    # → ~2 throttle windows → ≤ ~3 in steady state, plus generous slack
    # for slow CI). Definitely far less than 50.
    assert len(running_with_line) < 25, (
        f"throttle leaked: {len(running_with_line)} running events with lastLine"
    )

    # Final event has the most recent line and a clean exit.
    last = bus.events[-1]
    assert last.metadata["status"] == "exited"
    assert last.metadata["exitCode"] == 0
    assert "line" in last.metadata["lastLine"]


def test_lastline_is_trimmed_to_200_chars():
    bus = _FakeBus()
    code = "print('x' * 500)"
    cmd = [sys.executable, "-c", code]
    handle = track_subprocess(cmd, bus, session_id="s-trim")
    handle.wait(timeout=10)
    assert _wait_until(lambda: any(e.metadata.get("status") == "exited" for e in bus.events))

    last = bus.events[-1]
    assert len(last.metadata["lastLine"]) <= LAST_LINE_MAX_CHARS


def test_throttle_constant_is_250ms():
    # Frame C consumer expects this exact debounce window.
    assert THROTTLE_SECONDS == 0.25
