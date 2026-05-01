from __future__ import annotations

import contextlib
import datetime as _dt
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

CREATE TABLE IF NOT EXISTS hitl_pending (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL REFERENCES messages(id),
    proposed_action TEXT NOT NULL,
    proposed_confidence REAL NOT NULL,
    trigger_reason TEXT NOT NULL,
    queued_at TEXT NOT NULL,
    resolved_at TEXT,
    resolution TEXT
);
CREATE INDEX IF NOT EXISTS idx_hitl_pending_unresolved ON hitl_pending(resolved_at);

CREATE TABLE IF NOT EXISTS hitl_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id TEXT NOT NULL REFERENCES decisions(id),
    original_action TEXT NOT NULL,
    override_action TEXT NOT NULL,
    note TEXT,
    mode TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hitl_overrides_decision ON hitl_overrides(decision_id);
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
            # Additive migration for sessions table: add hitl_mode + hitl_floor
            # if absent. Older DBs created before Phase 2 will not have these
            # columns; CREATE TABLE IF NOT EXISTS does not add them.
            cols = {
                row[1]
                for row in self._conn.execute("PRAGMA table_info(sessions)").fetchall()
            }
            if "hitl_mode" not in cols:
                self._conn.execute(
                    "ALTER TABLE sessions ADD COLUMN hitl_mode TEXT NOT NULL DEFAULT 'async'"
                )
            if "hitl_floor" not in cols:
                self._conn.execute(
                    "ALTER TABLE sessions ADD COLUMN hitl_floor REAL NOT NULL DEFAULT 0.60"
                )

            # Phase 4 / NFR-M3 — additive migration for decisions table:
            # add model_used + layer if absent. Older DBs created before
            # Phase 4 will not have these columns. SQLite's ALTER TABLE
            # ADD COLUMN is the supported migration path.
            for col, definition in (
                ("model_used", "TEXT NOT NULL DEFAULT ''"),
                ("layer", "INTEGER NOT NULL DEFAULT 0"),
            ):
                # try/except sqlite3.OperationalError (idiomatic via
                # contextlib.suppress): the column already exists on
                # already-migrated DBs.
                with contextlib.suppress(sqlite3.OperationalError):
                    self._conn.execute(
                        f"ALTER TABLE decisions ADD COLUMN {col} {definition}"
                    )

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
        model_used: str = "",
        layer: int = 0,
    ) -> str:
        decision_id = str(uuid.uuid4())
        with self._lock:
            self._conn.execute(
                "INSERT INTO decisions (id, message_id, action, confidence, "
                "reasoning, matched_hash, timestamp, model_used, layer) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    decision_id,
                    message_id,
                    action,
                    confidence,
                    reasoning,
                    matched_hash,
                    time.time(),
                    model_used,
                    int(layer),
                ),
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

    # ── FR-HITL §4.9 ─────────────────────────────────────────────────

    def queue_hitl(
        self,
        message_id: str,
        proposed_action: str,
        proposed_confidence: float,
        trigger_reason: str,
    ) -> int:
        """Queue a decision for human approval. Returns hitl_pending.id."""
        queued_at = _dt.datetime.now(_dt.UTC).isoformat()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO hitl_pending (message_id, proposed_action, "
                "proposed_confidence, trigger_reason, queued_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    message_id,
                    proposed_action,
                    float(proposed_confidence),
                    trigger_reason,
                    queued_at,
                ),
            )
            pending_id = int(cur.lastrowid or 0)
        return pending_id

    def resolve_hitl(self, pending_id: int, resolution: str) -> None:
        """Mark a pending HITL row as resolved."""
        resolved_at = _dt.datetime.now(_dt.UTC).isoformat()
        with self._lock:
            self._conn.execute(
                "UPDATE hitl_pending SET resolved_at=?, resolution=? "
                "WHERE id=? AND resolved_at IS NULL",
                (resolved_at, resolution, pending_id),
            )

    def get_pending_hitl(self, session_id: str) -> list[dict[str, object]]:
        """Return unresolved hitl_pending rows for a session, oldest first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT hp.id, hp.message_id, hp.proposed_action, "
                "hp.proposed_confidence, hp.trigger_reason, hp.queued_at, "
                "hp.resolved_at, hp.resolution "
                "FROM hitl_pending hp "
                "JOIN messages m ON hp.message_id = m.id "
                "WHERE m.session_id=? AND hp.resolved_at IS NULL "
                "ORDER BY hp.id ASC",
                (session_id,),
            ).fetchall()
        out: list[dict[str, object]] = []
        for r in rows:
            out.append(
                {
                    "id": int(r[0]),
                    "message_id": r[1],
                    "proposed_action": r[2],
                    "proposed_confidence": float(r[3]),
                    "trigger_reason": r[4],
                    "queued_at": r[5],
                    "resolved_at": r[6],
                    "resolution": r[7],
                }
            )
        return out

    def get_hitl_pending_row(self, pending_id: int) -> dict[str, object] | None:
        """Look up a single hitl_pending row by id (for poll loops)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT id, message_id, proposed_action, proposed_confidence, "
                "trigger_reason, queued_at, resolved_at, resolution "
                "FROM hitl_pending WHERE id=?",
                (pending_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": int(row[0]),
            "message_id": row[1],
            "proposed_action": row[2],
            "proposed_confidence": float(row[3]),
            "trigger_reason": row[4],
            "queued_at": row[5],
            "resolved_at": row[6],
            "resolution": row[7],
        }

    def annotate_decision(
        self,
        decision_id: str,
        original_action: str,
        override_action: str,
        note: str | None,
        mode: str,
    ) -> None:
        """Insert an override row into hitl_overrides."""
        ts = _dt.datetime.now(_dt.UTC).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO hitl_overrides (decision_id, original_action, "
                "override_action, note, mode, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (decision_id, original_action, override_action, note, mode, ts),
            )

    def get_overrides_for_hash(
        self, matched_hash: str, limit: int = 5
    ) -> list[dict[str, object]]:
        """Return up to `limit` most recent overrides linked to decisions
        whose matched_hash equals the given value.
        """
        if not matched_hash:
            return []
        with self._lock:
            rows = self._conn.execute(
                "SELECT ho.id, ho.decision_id, ho.original_action, "
                "ho.override_action, ho.note, ho.mode, ho.timestamp "
                "FROM hitl_overrides ho "
                "JOIN decisions d ON ho.decision_id = d.id "
                "WHERE d.matched_hash=? "
                "ORDER BY ho.id DESC LIMIT ?",
                (matched_hash, int(limit)),
            ).fetchall()
        return [
            {
                "id": int(r[0]),
                "decision_id": r[1],
                "original_action": r[2],
                "override_action": r[3],
                "note": r[4],
                "mode": r[5],
                "timestamp": r[6],
            }
            for r in rows
        ]

    def get_hitl_mode(self, session_id: str) -> tuple[str, float]:
        """Return (hitl_mode, hitl_floor) for a session.

        Falls back to ("async", 0.60) if the session row is missing.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT hitl_mode, hitl_floor FROM sessions WHERE id=?",
                (session_id,),
            ).fetchone()
        if row is None:
            return ("async", 0.60)
        mode = str(row[0]) if row[0] is not None else "async"
        floor = float(row[1]) if row[1] is not None else 0.60
        return (mode, floor)

    def set_hitl_mode(self, session_id: str, mode: str, floor: float) -> None:
        """Update hitl_mode and hitl_floor for a session."""
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET hitl_mode=?, hitl_floor=? WHERE id=?",
                (mode, float(floor), session_id),
            )

    def get_decision_by_id(self, decision_id: str) -> dict[str, object] | None:
        """Return a single decision row by id."""
        with self._lock:
            row = self._conn.execute(
                "SELECT id, message_id, action, confidence, reasoning, "
                "matched_hash, timestamp FROM decisions WHERE id=?",
                (decision_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "message_id": row[1],
            "action": row[2],
            "confidence": float(row[3]),
            "reasoning": row[4],
            "matched_hash": row[5],
            "timestamp": float(row[6]),
        }

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
