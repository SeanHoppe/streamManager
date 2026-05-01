"""SQLite WAL event bus — persists governance decisions for offline inspection.

Usage::

    bus = EventBus("/tmp/gov.db")
    bus.emit(msg, decision)
    bus.close()

Monitor with ``tools/monitor.py``.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from stream_manager.governance import GovDecision
from stream_manager.messages import Message

_SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              REAL    NOT NULL,
    msg_id          TEXT,
    role            TEXT,
    snippet         TEXT,
    action          TEXT    NOT NULL,
    original_action TEXT,
    confidence      REAL,
    source          TEXT,
    mode            TEXT,
    matched_hash    TEXT,
    reasoning       TEXT
);
CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions (ts);
"""


class EventBus:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def emit(self, msg: Message, decision: GovDecision) -> None:
        snippet = (msg.content or "")[:120].replace("\n", " ")
        self._conn.execute(
            """INSERT INTO decisions
               (ts, msg_id, role, snippet, action, original_action,
                confidence, source, mode, matched_hash, reasoning)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                time.time(),
                msg.id,
                msg.role,
                snippet,
                decision.action,
                decision.original_action or None,
                decision.confidence,
                decision.source,
                decision.mode.name,
                decision.matched_hash or None,
                decision.reasoning,
            ),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> EventBus:
        return self

    def __exit__(self, *_) -> None:
        self.close()
