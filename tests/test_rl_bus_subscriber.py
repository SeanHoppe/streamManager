"""v10 P4 B' — tests for rl.bus_subscriber.

Covers the live-bus → ``rl_episodes.db`` adapter wired through
``MessageBus.subscribe_decision``. Defensive postures (silent skip on
self-monitor refusal, idempotent on duplicate, no-crash on DB fault)
are required by ADR-5 §"v10 logging overhead" + NFR-R6.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

import pytest

from rl import bus_subscriber
from stream_manager.message_bus import Message, MessageBus


def _open_bus(tmp_path: Path) -> MessageBus:
    return MessageBus(str(tmp_path / "gov.db"))


def _seed_session(
    bus: MessageBus,
    *,
    session_id: str = "sess-target",
    project_slug: str = "certPortal",
) -> str:
    """Open a session + publish one tool message; return message id."""
    bus.open_session(session_id, project_slug=project_slug, pid=os.getpid())
    msg = Message.new(
        session_id=session_id,
        type="tool",
        direction="inbound",
        content="ship",
    )
    bus.publish(msg)
    return msg.id


def test_subscriber_disabled_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """env unset → attach() is a no-op; no rl DB created."""
    monkeypatch.delenv("BRIDGE_RL_LOGGER_ENABLED", raising=False)
    bus = _open_bus(tmp_path)
    rl_db = tmp_path / "rl_episodes.db"
    close_fn = bus_subscriber.attach(bus, rl_db)
    assert bus.decision_subscriber_count() == 0
    assert not rl_db.exists()
    # Closing the no-op is also safe.
    close_fn()
    bus.close()


def test_subscriber_receives_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """env=1 → subscribe + record_decision → 1 row in rl DB."""
    monkeypatch.setenv("BRIDGE_RL_LOGGER_ENABLED", "1")
    bus = _open_bus(tmp_path)
    rl_db = tmp_path / "rl_episodes.db"
    close_fn = bus_subscriber.attach(bus, rl_db)

    assert bus.decision_subscriber_count() == 1
    msg_id = _seed_session(bus)
    bus.record_decision(
        message_id=msg_id,
        action="ALLOW",
        confidence=0.9,
        reasoning="happy path",
    )
    close_fn()
    bus.close()

    conn = sqlite3.connect(str(rl_db))
    count = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
    verdict = conn.execute("SELECT verdict FROM episodes").fetchone()[0]
    src = conn.execute("SELECT source FROM episodes").fetchone()[0]
    assert count == 1
    assert verdict == "ALLOW"
    assert src == "live"


def test_subscriber_skips_sm_slug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Session opened with project_slug=streamManager → polarity-filter
    drops; 0 rows in rl DB even though record_decision was called."""
    monkeypatch.setenv("BRIDGE_RL_LOGGER_ENABLED", "1")
    bus = _open_bus(tmp_path)
    rl_db = tmp_path / "rl_episodes.db"
    close_fn = bus_subscriber.attach(bus, rl_db)

    msg_id = _seed_session(bus, project_slug="streamManager")
    bus.record_decision(
        message_id=msg_id,
        action="ALLOW",
        confidence=0.9,
        reasoning="sm-self",
    )
    close_fn()
    bus.close()

    conn = sqlite3.connect(str(rl_db))
    count = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
    assert count == 0


def test_subscriber_skips_self_session_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BRIDGE_SM_SELF_SESSION_ID match → polarity-filter drops."""
    monkeypatch.setenv("BRIDGE_RL_LOGGER_ENABLED", "1")
    monkeypatch.setenv("BRIDGE_SM_SELF_SESSION_ID", "sm-self-1")
    bus = _open_bus(tmp_path)
    rl_db = tmp_path / "rl_episodes.db"
    close_fn = bus_subscriber.attach(bus, rl_db)

    msg_id = _seed_session(bus, session_id="sm-self-1", project_slug="other")
    bus.record_decision(
        message_id=msg_id,
        action="ALLOW",
        confidence=0.9,
        reasoning="sm-self via id",
    )
    close_fn()
    bus.close()

    conn = sqlite3.connect(str(rl_db))
    count = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
    assert count == 0


def test_subscriber_idempotent_on_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same (session_id, decision_id) twice = 1 row; second is silent
    sqlite3.IntegrityError swallowed by adapter. We simulate dup by
    re-firing the envelope through subscribe_decision directly."""
    monkeypatch.setenv("BRIDGE_RL_LOGGER_ENABLED", "1")
    bus = _open_bus(tmp_path)
    rl_db = tmp_path / "rl_episodes.db"

    # Capture the envelope produced by record_decision so we can replay.
    captured: list[dict] = []
    bus.subscribe_decision(captured.append)
    close_fn = bus_subscriber.attach(bus, rl_db)

    msg_id = _seed_session(bus)
    bus.record_decision(
        message_id=msg_id,
        action="ALLOW",
        confidence=0.9,
        reasoning="first",
    )
    assert len(captured) == 1
    # Re-fire the captured envelope through the rl subscriber callback
    # (last subscriber in the list is the rl adapter).
    rl_callback = bus._decision_subscribers[-1]  # noqa: SLF001 — test access
    rl_callback(captured[0])  # second insertion attempt → silent skip

    close_fn()
    bus.close()

    conn = sqlite3.connect(str(rl_db))
    count = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
    assert count == 1


def test_subscriber_survives_logger_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If record_decision raises an unexpected exception, the adapter
    logs + swallows; bus.record_decision still returns normally."""
    monkeypatch.setenv("BRIDGE_RL_LOGGER_ENABLED", "1")
    bus = _open_bus(tmp_path)
    rl_db = tmp_path / "rl_episodes.db"
    close_fn = bus_subscriber.attach(bus, rl_db)

    # Sabotage the rl callback so record_decision blows up.
    rl_callback = bus._decision_subscribers[-1]  # noqa: SLF001

    def _raising(_env: dict) -> None:
        raise RuntimeError("synthetic DB fault")

    # Replace last subscriber with the sabotaged one.
    bus._decision_subscribers[-1] = _raising  # noqa: SLF001

    msg_id = _seed_session(bus)
    with caplog.at_level(logging.ERROR):
        # bus.record_decision wraps subscriber failures (NFR-R6).
        decision_id = bus.record_decision(
            message_id=msg_id,
            action="ALLOW",
            confidence=0.9,
            reasoning="forced fault",
        )
    assert isinstance(decision_id, str)
    assert any(
        "decision subscriber callback failed" in r.message for r in caplog.records
    )

    # Restore + close cleanly.
    bus._decision_subscribers[-1] = rl_callback  # noqa: SLF001
    close_fn()
    bus.close()


def test_subscriber_latency_ms_zero_in_b_prime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B' documented limitation: envelope carries latency_ms=0.0 because
    _last_phase_timings_ms is populated AFTER record_decision returns.
    Test pins this so the follow-up PR (kwarg-extension) breaks loudly."""
    monkeypatch.setenv("BRIDGE_RL_LOGGER_ENABLED", "1")
    bus = _open_bus(tmp_path)
    rl_db = tmp_path / "rl_episodes.db"
    close_fn = bus_subscriber.attach(bus, rl_db)

    msg_id = _seed_session(bus)
    bus.record_decision(
        message_id=msg_id,
        action="ALLOW",
        confidence=0.9,
        reasoning="latency check",
    )
    close_fn()
    bus.close()

    conn = sqlite3.connect(str(rl_db))
    latency = conn.execute("SELECT latency_ms FROM episodes").fetchone()[0]
    assert latency == 0.0


def test_subscriber_close_unsubscribes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """close_fn() removes the subscriber; subsequent record_decision
    fans to zero subscribers (envelope build skipped)."""
    monkeypatch.setenv("BRIDGE_RL_LOGGER_ENABLED", "1")
    bus = _open_bus(tmp_path)
    rl_db = tmp_path / "rl_episodes.db"
    close_fn = bus_subscriber.attach(bus, rl_db)
    assert bus.decision_subscriber_count() == 1
    close_fn()
    assert bus.decision_subscriber_count() == 0
    bus.close()
