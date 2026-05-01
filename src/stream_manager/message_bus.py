from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    type TEXT NOT NULL,
    direction TEXT NOT NULL,
    content TEXT NOT NULL,
    context TEXT NOT NULL DEFAULT '{}',
    metadata TEXT NOT NULL DEFAULT '{}',
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session_seq ON messages(session_id, sequence);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL,
    action TEXT NOT NULL,
    confidence REAL NOT NULL,
    reasoning TEXT NOT NULL,
    matched_hash TEXT NOT NULL DEFAULT '',
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decisions_message ON decisions(message_id);

CREATE TABLE IF NOT EXISTS patterns (
    hash TEXT PRIMARY KEY,
    level INTEGER NOT NULL,
    occurrences INTEGER NOT NULL,
    success_rate REAL NOT NULL,
    last_seen REAL NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    project_slug TEXT NOT NULL DEFAULT '',
    pid INTEGER,
    started_at REAL NOT NULL,
    ended_at REAL
);

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    attribution_plugin TEXT NOT NULL DEFAULT '',
    attribution_skill TEXT NOT NULL DEFAULT '',
    is_sidechain INTEGER NOT NULL DEFAULT 0,
    profile_slug TEXT NOT NULL DEFAULT 'unknown',
    first_seen REAL NOT NULL,
    last_seen REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agents_session ON agents(session_id);
"""


@dataclass
class Message:
    id: str
    session_id: str
    sequence: int
    type: str
    direction: str
    content: str
    timestamp: float
    context: dict[str, object] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)

    @classmethod
    def new(
        cls,
        session_id: str,
        type: str,
        direction: str,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> Message:
        return cls(
            id=str(uuid.uuid4()),
            session_id=session_id,
            sequence=-1,
            type=type,
            direction=direction,
            content=content,
            timestamp=time.time(),
            metadata=metadata or {},
        )


SubscriberCallback = Callable[[Message], None]


class MessageBus:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._subscribers: list[SubscriberCallback] = []
        self._conn = self._connect()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            isolation_level=None,
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)

    def open_session(
        self,
        session_id: str,
        project_slug: str = "",
        pid: int | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO sessions (id, project_slug, pid, started_at) VALUES (?, ?, ?, ?)",
                (session_id, project_slug, pid, time.time()),
            )

    def close_session(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET ended_at=? WHERE id=? AND ended_at IS NULL",
                (time.time(), session_id),
            )

    def publish(self, msg: Message) -> int:
        with self._lock:
            cur = self._conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) FROM messages WHERE session_id=?",
                (msg.session_id,),
            )
            row = cur.fetchone()
            msg.sequence = (row[0] or 0) + 1
            self._conn.execute(
                "INSERT INTO messages (id, session_id, sequence, type, direction, "
                "content, context, metadata, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    msg.id,
                    msg.session_id,
                    msg.sequence,
                    msg.type,
                    msg.direction,
                    msg.content,
                    json.dumps(msg.context),
                    json.dumps(msg.metadata),
                    msg.timestamp,
                ),
            )
        for sub in list(self._subscribers):
            try:
                sub(msg)
            except Exception:
                # NFR-R6: subscriber failures must not crash the bus.
                log.exception("subscriber callback failed")
        return msg.sequence

    def subscribe(self, callback: SubscriberCallback) -> None:
        self._subscribers.append(callback)

    def record_decision(
        self,
        message_id: str,
        action: str,
        confidence: float,
        reasoning: str,
        matched_hash: str = "",
    ) -> str:
        decision_id = str(uuid.uuid4())
        with self._lock:
            self._conn.execute(
                "INSERT INTO decisions (id, message_id, action, confidence, "
                "reasoning, matched_hash, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (decision_id, message_id, action, confidence, reasoning, matched_hash, time.time()),
            )
        return decision_id

    def upsert_agent(
        self,
        session_id: str,
        attribution_plugin: str,
        attribution_skill: str,
        is_sidechain: bool,
        profile_slug: str,
    ) -> None:
        """Insert or update the agent identity row for (session_id, attribution_plugin).

        One row per (session_id, attribution_plugin) pair: subsequent calls
        with the same plugin update last_seen and profile_slug; first_seen
        is preserved.
        """
        now = time.time()
        sidechain_int = 1 if is_sidechain else 0
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, first_seen FROM agents "
                "WHERE session_id=? AND attribution_plugin=?",
                (session_id, attribution_plugin),
            )
            row = cur.fetchone()
            if row is None:
                agent_id = str(uuid.uuid4())
                self._conn.execute(
                    "INSERT INTO agents (id, session_id, attribution_plugin, "
                    "attribution_skill, is_sidechain, profile_slug, "
                    "first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        agent_id,
                        session_id,
                        attribution_plugin,
                        attribution_skill,
                        sidechain_int,
                        profile_slug,
                        now,
                        now,
                    ),
                )
            else:
                self._conn.execute(
                    "UPDATE agents SET attribution_skill=?, is_sidechain=?, "
                    "profile_slug=?, last_seen=? WHERE id=?",
                    (
                        attribution_skill,
                        sidechain_int,
                        profile_slug,
                        now,
                        row[0],
                    ),
                )

    def stats(self) -> dict[str, int]:
        with self._lock:
            mrow = self._conn.execute("SELECT COUNT(*) FROM messages").fetchone()
            drow = self._conn.execute("SELECT COUNT(*) FROM decisions").fetchone()
        return {"messages": int(mrow[0]), "decisions": int(drow[0])}

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class WalReader:
    """Cross-process polling reader. Yields new message rows as they arrive."""

    def __init__(self, db_path: str, session_id: str, poll_ms: int = 100) -> None:
        self._db_path = str(db_path)
        self._session_id = session_id
        self._poll = poll_ms / 1000
        self._last_seq = 0
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            self._conn = conn
        return self._conn

    def __iter__(self):
        conn = self._get_conn()
        while True:
            rows = conn.execute(
                "SELECT id, session_id, sequence, type, direction, content, "
                "context, metadata, timestamp FROM messages "
                "WHERE session_id=? AND sequence>? ORDER BY sequence",
                (self._session_id, self._last_seq),
            ).fetchall()
            for row in rows:
                self._last_seq = row["sequence"]
                yield dict(row)
            if not rows:
                time.sleep(self._poll)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


def list_sessions(db_path: str) -> list[dict]:
    """Return all sessions from a WAL bus DB, newest first."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, project_slug, pid, started_at, ended_at "
            "FROM sessions ORDER BY started_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
