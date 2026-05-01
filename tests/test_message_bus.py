from __future__ import annotations

import threading
import uuid

import pytest

from stream_manager.message_bus import Message, MessageBus, WalReader, list_sessions
from stream_manager.governance import GovernanceEngine
from stream_manager.messages import Message as GovMessage
from stream_manager.project_context import ProjectContextSnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bus(tmp_path) -> MessageBus:
    return MessageBus(str(tmp_path / "test.db"))


def _gov_msg(content: str) -> GovMessage:
    import time
    return GovMessage(id=str(uuid.uuid4()), role="user", content=content, timestamp=time.time())


# ---------------------------------------------------------------------------
# MessageBus — basic
# ---------------------------------------------------------------------------

def test_publish_increments_sequence(tmp_path):
    bus = _bus(tmp_path)
    for i in range(5):
        seq = bus.publish(Message.new("s1", "chat", "inbound", f"msg {i}"))
        assert seq == i + 1
    bus.close()


def test_publish_stats(tmp_path):
    bus = _bus(tmp_path)
    bus.publish(Message.new("s1", "chat", "inbound", "hi"))
    s = bus.stats()
    assert s["messages"] == 1
    assert s["decisions"] == 0
    bus.close()


def test_record_decision(tmp_path):
    bus = _bus(tmp_path)
    msg = Message.new("s1", "chat", "inbound", "hi")
    bus.publish(msg)
    dec_id = bus.record_decision(msg.id, "ALLOW", 0.9, "graph match", "abc123")
    assert dec_id
    assert bus.stats()["decisions"] == 1
    bus.close()


def test_session_open_and_close(tmp_path):
    db = str(tmp_path / "test.db")
    bus = MessageBus(db)
    bus.open_session("s1", project_slug="myproj", pid=99)

    sessions = list_sessions(db)
    assert len(sessions) == 1
    assert sessions[0]["project_slug"] == "myproj"
    assert sessions[0]["pid"] == 99
    assert sessions[0]["ended_at"] is None

    bus.close_session("s1")
    sessions = list_sessions(db)
    assert sessions[0]["ended_at"] is not None
    bus.close()


def test_open_session_idempotent(tmp_path):
    db = str(tmp_path / "test.db")
    bus = MessageBus(db)
    bus.open_session("s1")
    bus.open_session("s1")  # INSERT OR IGNORE — must not raise
    assert len(list_sessions(db)) == 1
    bus.close()


def test_subscriber_called_on_publish(tmp_path):
    bus = _bus(tmp_path)
    received: list[Message] = []
    bus.subscribe(received.append)
    bus.publish(Message.new("s1", "chat", "inbound", "hello"))
    assert len(received) == 1
    assert received[0].content == "hello"
    bus.close()


def test_subscriber_failure_does_not_crash_bus(tmp_path):
    bus = _bus(tmp_path)

    def bad_sub(_msg):
        raise RuntimeError("boom")

    bus.subscribe(bad_sub)
    bus.publish(Message.new("s1", "chat", "inbound", "hello"))  # must not raise
    assert bus.stats()["messages"] == 1
    bus.close()


def test_sequences_per_session_independent(tmp_path):
    bus = _bus(tmp_path)
    bus.publish(Message.new("s1", "chat", "inbound", "a"))
    bus.publish(Message.new("s1", "chat", "inbound", "b"))
    seq = bus.publish(Message.new("s2", "chat", "inbound", "x"))
    assert seq == 1  # s2 starts its own sequence
    bus.close()


# ---------------------------------------------------------------------------
# MessageBus — concurrency
# ---------------------------------------------------------------------------

def test_concurrent_publish_no_errors(tmp_path):
    bus = _bus(tmp_path)
    errors: list[Exception] = []

    def writer(session_id: str, n: int) -> None:
        try:
            for i in range(n):
                bus.publish(Message.new(session_id, "chat", "inbound", f"msg {i}"))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(f"sess{i}", 20)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert bus.stats()["messages"] == 100
    bus.close()


# ---------------------------------------------------------------------------
# WalReader
# ---------------------------------------------------------------------------

def _drain(reader: WalReader, n: int) -> list[dict]:
    rows: list[dict] = []
    for row in reader:
        rows.append(row)
        if len(rows) == n:
            break
    return rows


def test_wal_reader_reads_published_rows(tmp_path):
    db = str(tmp_path / "test.db")
    bus = MessageBus(db)
    bus.open_session("s1")
    for i in range(3):
        bus.publish(Message.new("s1", "chat", "inbound", f"msg {i}"))
    bus.close()

    reader = WalReader(db, "s1", poll_ms=10)
    rows = _drain(reader, 3)
    reader.close()

    assert len(rows) == 3
    assert rows[0]["sequence"] == 1
    assert rows[2]["sequence"] == 3
    assert rows[1]["content"] == "msg 1"


def test_wal_reader_session_isolation(tmp_path):
    db = str(tmp_path / "test.db")
    bus = MessageBus(db)
    bus.open_session("s1")
    bus.open_session("s2")
    bus.publish(Message.new("s1", "chat", "inbound", "from-s1"))
    bus.publish(Message.new("s2", "chat", "inbound", "from-s2"))
    bus.close()

    reader = WalReader(db, "s1", poll_ms=10)
    rows = _drain(reader, 1)
    reader.close()

    assert rows[0]["content"] == "from-s1"


def test_wal_reader_returns_only_new_rows(tmp_path):
    db = str(tmp_path / "test.db")
    bus = MessageBus(db)
    bus.open_session("s1")
    bus.publish(Message.new("s1", "chat", "inbound", "first"))
    bus.close()

    reader = WalReader(db, "s1", poll_ms=10)
    _drain(reader, 1)  # consume the first row

    # Publish another message after reader is positioned past seq=1
    bus2 = MessageBus(db)
    bus2.publish(Message.new("s1", "chat", "inbound", "second"))
    bus2.close()

    rows = _drain(reader, 1)
    reader.close()

    assert rows[0]["content"] == "second"
    assert rows[0]["sequence"] == 2


# ---------------------------------------------------------------------------
# Bus + GovernanceEngine integration
# ---------------------------------------------------------------------------

def test_governance_evaluate_publishes_message_and_decision(tmp_path):
    db = str(tmp_path / "test.db")
    bus = MessageBus(db)
    session_id = "test-session"
    bus.open_session(session_id)

    engine = GovernanceEngine(
        project_context=ProjectContextSnapshot(repo_path="/tmp"),
        bus=bus,
        session_id=session_id,
    )
    engine.evaluate(_gov_msg("hello"))
    engine.evaluate(_gov_msg("world"))

    s = bus.stats()
    assert s["messages"] == 2
    assert s["decisions"] == 2
    bus.close_session(session_id)
    bus.close()


def test_governance_evaluate_without_bus_does_not_crash(tmp_path):
    engine = GovernanceEngine(
        project_context=ProjectContextSnapshot(repo_path="/tmp"),
    )
    decision = engine.evaluate(_gov_msg("hello"))
    assert decision.action  # any action is valid


def test_governance_decisions_readable_via_wal_reader(tmp_path):
    import sqlite3

    db = str(tmp_path / "test.db")
    bus = MessageBus(db)
    session_id = "int-session"
    bus.open_session(session_id)

    engine = GovernanceEngine(
        project_context=ProjectContextSnapshot(repo_path="/tmp"),
        bus=bus,
        session_id=session_id,
    )
    engine.evaluate(_gov_msg("test content"))

    reader = WalReader(db, session_id, poll_ms=10)
    rows = _drain(reader, 1)
    reader.close()

    msg_id = rows[0]["id"]
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    dec = conn.execute(
        "SELECT action, confidence FROM decisions WHERE message_id=?", (msg_id,)
    ).fetchone()
    conn.close()

    assert dec is not None
    assert dec["action"] in {"ALLOW", "SUGGEST", "GUIDE", "INTERVENE", "BLOCK"}
    bus.close()
