from __future__ import annotations

from pathlib import Path

from stream_manager.message_bus import Message, MessageBus


def _make_msg(session_id: str, content: str = "hello") -> Message:
    return Message.new(session_id, "user", "desktop_to_cli", content)


def test_publish_assigns_monotonic_sequence(tmp_path: Path) -> None:
    bus = MessageBus(str(tmp_path / "bus.db"))
    try:
        s1 = bus.publish(_make_msg("sess-A"))
        s2 = bus.publish(_make_msg("sess-A"))
        s3 = bus.publish(_make_msg("sess-A"))
        assert (s1, s2, s3) == (1, 2, 3)
    finally:
        bus.close()


def test_sequence_per_session_is_independent(tmp_path: Path) -> None:
    bus = MessageBus(str(tmp_path / "bus.db"))
    try:
        a1 = bus.publish(_make_msg("A"))
        b1 = bus.publish(_make_msg("B"))
        a2 = bus.publish(_make_msg("A"))
        assert (a1, b1, a2) == (1, 1, 2)
    finally:
        bus.close()


def test_subscriber_failure_does_not_crash_publish(tmp_path: Path) -> None:
    bus = MessageBus(str(tmp_path / "bus.db"))
    try:
        bus.subscribe(lambda _m: (_ for _ in ()).throw(RuntimeError("boom")))
        seq = bus.publish(_make_msg("X"))
        assert seq == 1
        assert bus.stats()["messages"] == 1
    finally:
        bus.close()


def test_record_decision_writes_row(tmp_path: Path) -> None:
    bus = MessageBus(str(tmp_path / "bus.db"))
    try:
        msg = _make_msg("Y")
        bus.publish(msg)
        bus.record_decision(msg.id, "ALLOW", 0.0, "noop")
        assert bus.stats() == {"messages": 1, "decisions": 1}
    finally:
        bus.close()


def test_wal_mode_is_enabled(tmp_path: Path) -> None:
    bus = MessageBus(str(tmp_path / "bus.db"))
    try:
        cur = bus._conn.execute("PRAGMA journal_mode")
        mode = cur.fetchone()[0]
        assert mode.lower() == "wal"
    finally:
        bus.close()
