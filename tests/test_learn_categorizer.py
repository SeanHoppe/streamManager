"""Tests for v1.3 P5c — Learn Mode Sonnet categorizer worker.

Asserts:

  1. The worker pulls paired ``desktop_prompt`` + ``user_reply`` rows
     from the bus and writes one ``learn_patterns`` row per pair.
  2. The CLI subprocess invocation matches the existing
     ``cli_governance`` pattern (``claude -p``, ``--model``,
     ``--output-format json``, ``--no-session-persistence``,
     ``--tools ""``).
  3. The worker DOES NOT block the verdict hot path. Even when the
     mocked Sonnet runner sleeps for several seconds (simulating real
     L4 latency), a synchronous governance verdict completes well
     within the ADR-5 budget.
  4. Each row carries the expected ``prompt_hash``, ``category``,
     ``confidence``, ``last_reinforced_ts``, and ``created_at`` fields.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from stream_manager import message_bus as _msg_bus
from stream_manager.learn_categorizer import (
    DEFAULT_MODEL,
    LearnCategorizerWorker,
    categorize_pair,
    prompt_hash,
)


# ── helpers ─────────────────────────────────────────────────────────


@dataclass
class _CompletedProcess:
    returncode: int
    stdout: str
    stderr: str = ""


def _envelope(category: str, confidence: float, reasoning: str = "") -> str:
    inner = {
        "category": category,
        "confidence": confidence,
        "reasoning": reasoning,
    }
    envelope = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": json.dumps(inner),
    }
    return json.dumps(envelope)


class _RecordingRunner:
    """subprocess.run stand-in. Records calls; optionally sleeps."""

    def __init__(
        self,
        category: str = "approve",
        confidence: float = 0.85,
        sleep_s: float = 0.0,
        returncode: int = 0,
    ) -> None:
        self.category = category
        self.confidence = confidence
        self.sleep_s = sleep_s
        self.returncode = returncode
        self.calls: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def __call__(self, cmd, **kwargs):
        with self._lock:
            self.calls.append({"cmd": cmd, "kwargs": kwargs})
        if self.sleep_s:
            time.sleep(self.sleep_s)
        return _CompletedProcess(
            returncode=self.returncode,
            stdout=_envelope(self.category, self.confidence),
        )


@pytest.fixture
def bus(tmp_path: Path) -> _msg_bus.MessageBus:
    return _msg_bus.MessageBus(str(tmp_path / "bus.db"))


def _publish_pair(
    bus: _msg_bus.MessageBus,
    *,
    session_id: str = "S1",
    prompt_text: str = "Want me to ship the v1.3 PR?",
    reply_text: str = "yes please, ship it",
) -> tuple[str, str]:
    """Publish a desktop_prompt + user_reply pair, returning (prompt_id, reply_id)."""
    prompt_msg = _msg_bus.Message.new(
        session_id=session_id,
        type="desktop_prompt",
        direction="inbound",
        content=prompt_text,
        metadata={"uuid": "a-uuid-1"},
    )
    bus.publish(prompt_msg)
    reply_msg = _msg_bus.Message.new(
        session_id=session_id,
        type="user_reply",
        direction="inbound",
        content=reply_text,
        metadata={"uuid": "u-uuid-1", "pair_id": prompt_msg.id},
    )
    bus.publish(reply_msg)
    return prompt_msg.id, reply_msg.id


def _read_learn_patterns(bus: _msg_bus.MessageBus) -> list[dict[str, Any]]:
    rows = bus.fetch_rows(
        "SELECT id, prompt_hash, category, confidence, ladder_step, "
        "last_reinforced_ts, contradicted_count, created_at "
        "FROM learn_patterns ORDER BY id ASC"
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": int(r[0]),
                "prompt_hash": str(r[1]),
                "category": str(r[2]),
                "confidence": float(r[3]),
                "ladder_step": int(r[4]),
                "last_reinforced_ts": float(r[5]),
                "contradicted_count": int(r[6]),
                "created_at": float(r[7]),
            }
        )
    return out


# ── tests ───────────────────────────────────────────────────────────


def test_learn_patterns_table_created(bus: _msg_bus.MessageBus) -> None:
    """The learn_patterns table + index must be created by MessageBus init."""
    rows = bus.fetch_rows(
        "SELECT name FROM sqlite_master "
        "WHERE type IN ('table','index') "
        "AND name IN ('learn_patterns','idx_learn_patterns_hash') "
        "ORDER BY name"
    )
    names = [r[0] for r in rows]
    assert "learn_patterns" in names
    assert "idx_learn_patterns_hash" in names


def test_prompt_hash_is_stable_and_normalized() -> None:
    h1 = prompt_hash("Want me to ship the v1.3 PR?")
    h2 = prompt_hash("  WANT me to SHIP the v1.3   PR?  ")
    assert h1 == h2
    assert len(h1) == 16


def test_categorize_pair_invokes_cli_with_expected_flags() -> None:
    runner = _RecordingRunner(category="approve", confidence=0.9)
    out = categorize_pair(
        "Want me to ship?",
        "yes please",
        runner=runner,
    )
    assert out is not None
    assert out.category == "approve"
    assert out.confidence == pytest.approx(0.9)
    assert len(runner.calls) == 1
    cmd = runner.calls[0]["cmd"]
    # Mirror cli_governance flag set.
    assert cmd[0] == "claude"
    assert "-p" in cmd
    assert "--model" in cmd
    assert DEFAULT_MODEL in cmd
    assert "--output-format" in cmd
    assert "json" in cmd
    assert "--no-session-persistence" in cmd
    assert "--tools" in cmd


def test_worker_writes_one_row_per_pair(bus: _msg_bus.MessageBus) -> None:
    """tick() must drain all new pairs and write one learn_patterns row each."""
    p1, _ = _publish_pair(
        bus,
        prompt_text="Want me to ship the v1.3 PR?",
        reply_text="yes please, ship it",
    )
    _publish_pair(
        bus,
        session_id="S2",
        prompt_text="Should I rebase first?",
        reply_text="no, fast-forward is fine",
    )
    runner = _RecordingRunner(category="approve", confidence=0.78)
    worker = LearnCategorizerWorker(bus, runner=runner)
    n = worker.tick()
    assert n == 2

    patterns = _read_learn_patterns(bus)
    assert len(patterns) == 2
    # Each row carries the expected schema fields.
    for row in patterns:
        assert row["category"] == "approve"
        assert row["confidence"] == pytest.approx(0.78)
        assert row["ladder_step"] == 0
        assert row["contradicted_count"] == 0
        assert row["last_reinforced_ts"] > 0
        assert row["created_at"] > 0
        assert len(row["prompt_hash"]) == 16

    # First row's hash matches the canonical hash of its prompt.
    assert patterns[0]["prompt_hash"] == prompt_hash("Want me to ship the v1.3 PR?")
    assert patterns[1]["prompt_hash"] == prompt_hash("Should I rebase first?")


def test_worker_is_idempotent_across_ticks(bus: _msg_bus.MessageBus) -> None:
    """A second tick() with no new pairs must not re-categorize."""
    _publish_pair(bus)
    runner = _RecordingRunner()
    worker = LearnCategorizerWorker(bus, runner=runner)

    assert worker.tick() == 1
    assert worker.tick() == 0
    assert len(_read_learn_patterns(bus)) == 1
    assert len(runner.calls) == 1


def test_worker_records_unknown_on_runner_failure(bus: _msg_bus.MessageBus) -> None:
    """Categorizer failure (non-zero exit) records a low-confidence unknown row."""
    _publish_pair(bus)
    runner = _RecordingRunner(returncode=1)  # CLI failure
    worker = LearnCategorizerWorker(bus, runner=runner)
    worker.tick()
    rows = _read_learn_patterns(bus)
    assert len(rows) == 1
    assert rows[0]["category"] == "unknown"
    assert rows[0]["confidence"] == 0.0


def test_worker_does_not_block_verdict_hot_path(
    bus: _msg_bus.MessageBus,
) -> None:
    """The categorizer worker MUST run out-of-band.

    Simulate real Sonnet latency (~2s) inside the worker's mocked CLI
    runner. A synchronous "verdict-like" call running on the main
    thread MUST return well within the ADR-5 budget — i.e. the
    categorizer thread does not hold any lock or resource that would
    block the hot path.

    This is the load-bearing P5c invariant: ``categorize_pair`` is a
    fresh subprocess, not a ``CliPool`` borrow, and the worker runs on
    its own daemon thread.
    """
    _publish_pair(bus)

    # 2s of simulated Sonnet latency in the worker.
    runner = _RecordingRunner(category="approve", confidence=0.7, sleep_s=2.0)
    worker = LearnCategorizerWorker(
        bus,
        runner=runner,
        poll_interval_s=0.05,
    )

    # Start the worker; it spawns a daemon thread and immediately enters
    # the simulated Sonnet round-trip.
    worker.start()

    # Give the worker thread a beat to enter the runner.
    time.sleep(0.1)

    # Now exercise the hot path: a publish() + fetch round-trip on the
    # bus while the categorizer is mid-flight. This stands in for a
    # verdict path call (which itself just publishes governance_call
    # events and reads from the bus). If the categorizer were holding a
    # lock or borrowing the verdict pool, this would hang or be slow.
    hot_start = time.monotonic()
    msg = _msg_bus.Message.new(
        session_id="hot-path-session",
        type="user_message",
        direction="inbound",
        content="ls",
    )
    bus.publish(msg)
    # Read it back to round-trip the lock.
    rows = bus.fetch_rows(
        "SELECT id FROM messages WHERE session_id=?",
        ("hot-path-session",),
    )
    hot_elapsed = time.monotonic() - hot_start

    assert len(rows) == 1
    # ADR-5 budget is p95 ≤ 15s; out-of-band-ness is satisfied if the
    # hot path returns in well under 1s while the categorizer is
    # mid-flight on its 2s sleep.
    assert hot_elapsed < 1.0, (
        f"hot path blocked by categorizer: {hot_elapsed:.3f}s "
        f"(should be << 1s while worker is in 2s mock-Sonnet sleep)"
    )

    # Let the worker finish its in-flight pair and shut down cleanly.
    worker.stop(join_timeout=5.0)

    # Worker did eventually run categorize and write a row.
    rows = _read_learn_patterns(bus)
    assert len(rows) == 1
    assert rows[0]["category"] == "approve"


def test_worker_start_stop_idempotent(bus: _msg_bus.MessageBus) -> None:
    runner = _RecordingRunner()
    worker = LearnCategorizerWorker(bus, runner=runner, poll_interval_s=0.05)
    worker.start()
    worker.start()  # second start is a no-op
    assert worker.running is True
    worker.stop()
    worker.stop()  # second stop is a no-op
    assert worker.running is False
