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
    resolution TEXT,
    matched_hash TEXT NOT NULL DEFAULT '',
    bias_hint TEXT NOT NULL DEFAULT ''
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

CREATE TABLE IF NOT EXISTS desktop_commands (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    args_json TEXT NOT NULL DEFAULT '{}',
    signature TEXT NOT NULL,
    sent_at REAL NOT NULL,
    acked_at REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_dc_pending ON desktop_commands(session_id, status);

-- v2.1 P1 (FR-PPP): Provenance Probe Protocol assertions. Operator's
-- signed answer to "which JSONL stream is currently being driven?"
-- (`audit.probe_ack` payload). Additive — no FROZEN tables modified.
-- `probe_id UNIQUE` provides replay protection: a second ack for the
-- same probe_id is a constraint violation; server returns HTTP 409.
-- jsonl_path NULL = operator picked "none" (no candidate matches).
-- Active-row resolution: the "current" assertion for a session is the
-- row with the largest signed_at whose expires_at > NOW(). Multiple
-- non-expired rows MAY coexist; readers MUST take the latest.
CREATE TABLE IF NOT EXISTS provenance_assertions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    probe_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL,
    jsonl_path TEXT,
    brain_id TEXT,
    prompt_hash TEXT,
    signed_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    hmac_sig TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_provenance_session_active
    ON provenance_assertions (session_id, signed_at DESC);

-- v1.3 P5c: Learn Mode categorizer output. One row per categorized
-- desktop_prompt/user_reply pair. Additive — does not modify any
-- existing table. The verdict hot path never writes here; this is
-- populated exclusively by the out-of-band categorizer worker.
--
-- Append-only by design; P5e (decay/reinforcement) is responsible for
-- consolidation. Multiple rows per prompt_hash are expected within and
-- across process lifetimes — do NOT add UNIQUE(prompt_hash) here.
CREATE TABLE IF NOT EXISTS learn_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_hash TEXT NOT NULL,
    category TEXT NOT NULL,
    confidence REAL NOT NULL,
    ladder_step INTEGER NOT NULL DEFAULT 0,
    last_reinforced_ts REAL NOT NULL,
    contradicted_count INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_learn_patterns_hash ON learn_patterns(prompt_hash);

-- v1.3 P5c (Fix A): Durable ledger for the LearnCategorizerWorker.
-- Persists `last_id_seen` across worker restarts so we don't re-
-- categorize historical pairs. Generic key/value to allow future
-- worker state without further schema churn.
CREATE TABLE IF NOT EXISTS learn_categorizer_state (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- v1.3 P5e: Canonical (UPSERT) projection of `learn_patterns`.
-- Additive migration — leaves the append-only `learn_patterns` audit
-- log untouched. Consolidation/decay pass merges per-prompt_hash rows
-- into a single canonical record here. Decay sweeps update
-- `ladder_step` / `last_reinforced_ts` / `contradicted_count` here;
-- no rewrites of the underlying audit log are required.
--
-- Design notes:
--   * UNIQUE(prompt_hash) is the whole point of this table.
--   * Append-only `learn_patterns` remains the source of truth for
--     "what categorizations did we ever observe"; this table answers
--     "what is the current canonical bias for prompt_hash X".
--   * Bias readers (P5d `bias_for`) are NOT modified by P5e; they
--     continue to read `learn_patterns` directly. P5e ships the
--     decay/consolidate primitives only — wiring `bias_for` to the
--     canonical projection is deferred to a follow-up if/when the
--     append-only ordering proves insufficient.
CREATE TABLE IF NOT EXISTS learn_patterns_canonical (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_hash TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    confidence REAL NOT NULL,
    ladder_step INTEGER NOT NULL DEFAULT 0,
    last_reinforced_ts REAL NOT NULL,
    contradicted_count INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_learn_patterns_canon_hash
    ON learn_patterns_canonical(prompt_hash);
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


# v2.1 P1 (FR-PPP) — Provenance Probe Protocol envelope payloads.
# Additive type definitions; not routed through `publish` (which writes
# to the messages table). PPP envelopes ride the existing ADR-14 SSE
# transport via the bus subscriber list and the dashboard SSE stream.
#
# `frozen=True` on `AuditProbeCandidate` defends against the
# sign-then-mutate footgun: HMAC sig is computed over the canonical-
# encoded candidate list at envelope-build time; if the list members
# were mutable, a caller could mutate `slug` / `jsonl_path` after sign
# and the delivered envelope dict would diverge from the signed one
# (verifier-side mismatch).
@dataclass(frozen=True)
class AuditProbeCandidate:
    slug: str
    jsonl_path: str
    brain_id: str
    last_event_ts: float
    prompt_hash: str

    def to_dict(self) -> dict[str, object]:
        return {
            "slug": self.slug,
            "jsonl_path": self.jsonl_path,
            "brain_id": self.brain_id,
            "last_event_ts": float(self.last_event_ts),
            "prompt_hash": self.prompt_hash,
        }


# `AuditProbeEnvelope` is intentionally NOT `frozen=True`. The HMAC sig
# is stamped onto the dataclass after construction (see
# `governance.emit_audit_probe`: build → sign sans hmac_sig → assign
# hmac_sig). Inner `AuditProbeCandidate` is frozen, which is what the
# sign-then-mutate guard hinges on; mutating the outer envelope fields
# post-sign would invalidate the sig and is caller-side discipline.
@dataclass
class AuditProbeEnvelope:
    probe_id: str
    candidate_streams: list[AuditProbeCandidate]
    ttl_seconds: int
    issued_at: float
    hmac_sig: str

    def to_dict(self) -> dict[str, object]:
        return {
            "probe_id": self.probe_id,
            "candidate_streams": [c.to_dict() for c in self.candidate_streams],
            "ttl_seconds": int(self.ttl_seconds),
            "issued_at": float(self.issued_at),
            "hmac_sig": self.hmac_sig,
        }

    def signing_payload(self) -> dict[str, object]:
        out = self.to_dict()
        out.pop("hmac_sig", None)
        return out


@dataclass
class AuditProbeAckEnvelope:
    probe_id: str
    selected_jsonl_path: str | None
    signed_at: float
    expires_at: float
    hmac_sig: str
    # v2.1 P1a (R14): sig schema versioning. v1 = {probe_id,
    # selected_jsonl_path, signed_at, expires_at}. v2 adds brain_id +
    # prompt_hash (FR-PPP-2 enrichment for P2 canary echo). Defaults
    # keep P1-era call sites compiling under v1.
    brain_id: str | None = None
    prompt_hash: str | None = None
    sig_v: int = 1

    def to_dict(self) -> dict[str, object]:
        return {
            "probe_id": self.probe_id,
            "selected_jsonl_path": self.selected_jsonl_path,
            "signed_at": float(self.signed_at),
            "expires_at": float(self.expires_at),
            "hmac_sig": self.hmac_sig,
            "brain_id": self.brain_id,
            "prompt_hash": self.prompt_hash,
            "sig_v": int(self.sig_v),
        }

    def signing_payload(self) -> dict[str, object]:
        """Return the dict that gets HMAC-signed. Schema depends on sig_v.

        sig_v == 1: legacy P1 shape — `{probe_id, selected_jsonl_path,
        signed_at, expires_at}`. Used for pre-P1a rows.

        sig_v >= 2: P1a-enriched shape — includes `brain_id`,
        `prompt_hash`, and `sig_v` itself so a v1 sig can never collide
        with a v2 sig over the same probe.
        """
        out = self.to_dict()
        out.pop("hmac_sig", None)
        if int(self.sig_v) <= 1:
            out.pop("brain_id", None)
            out.pop("prompt_hash", None)
            out.pop("sig_v", None)
        return out


# v2.1 P2 (FR-PPP) — Layer 2 canary echo envelopes. Server-stamped sigs
# at emit / observe / failure time inside the JsonlTailWorker and
# governance emitters; browser never holds the secret per FR-PPP-2.
# Canary sigs are sig_v=1 (intrinsic to envelope; no schema versioning
# needed yet — schema-versioning rationale is reserved for the ack path
# where sig_v=2 added brain_id/prompt_hash in P1a). NOT `frozen=True`:
# `hmac_sig` is stamped after construction by the canonical-payload
# build → sign-sans-sig → re-stamp pattern that AuditProbeEnvelope uses.
@dataclass
class AuditCanaryEmitEnvelope:
    probe_id: str
    jsonl_path: str
    nonce: str
    issued_at: float
    timeout_s: int
    hmac_sig: str

    def to_dict(self) -> dict[str, object]:
        return {
            "probe_id": self.probe_id,
            "jsonl_path": self.jsonl_path,
            "nonce": self.nonce,
            "issued_at": float(self.issued_at),
            "timeout_s": int(self.timeout_s),
            "hmac_sig": self.hmac_sig,
        }

    def signing_payload(self) -> dict[str, object]:
        out = self.to_dict()
        out.pop("hmac_sig", None)
        return out


@dataclass
class AuditCanaryObservedEnvelope:
    probe_id: str
    nonce: str
    observed_at: float
    jsonl_path: str
    hmac_sig: str

    def to_dict(self) -> dict[str, object]:
        return {
            "probe_id": self.probe_id,
            "nonce": self.nonce,
            "observed_at": float(self.observed_at),
            "jsonl_path": self.jsonl_path,
            "hmac_sig": self.hmac_sig,
        }

    def signing_payload(self) -> dict[str, object]:
        out = self.to_dict()
        out.pop("hmac_sig", None)
        return out


@dataclass
class AuditProbeFailureEnvelope:
    probe_id: str
    reason: str
    failed_at: float
    hmac_sig: str

    def to_dict(self) -> dict[str, object]:
        return {
            "probe_id": self.probe_id,
            "reason": self.reason,
            "failed_at": float(self.failed_at),
            "hmac_sig": self.hmac_sig,
        }

    def signing_payload(self) -> dict[str, object]:
        out = self.to_dict()
        out.pop("hmac_sig", None)
        return out


EnvelopeSubscriberCallback = Callable[[str, dict[str, object]], None]


class MessageBus:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._subscribers: list[SubscriberCallback] = []
        self._envelope_subscribers: list[EnvelopeSubscriberCallback] = []
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

            # FR-UI-9 — additive migration for sessions.settings: a JSON
            # blob holding the FR-UI-9 user-preference snapshot for this
            # session (sync timeout, audible cue, activity window, motion
            # override, etc). JSON blob avoids a column per setting.
            if "settings" not in cols:
                with contextlib.suppress(sqlite3.OperationalError):
                    self._conn.execute(
                        "ALTER TABLE sessions ADD COLUMN settings TEXT NOT NULL DEFAULT '{}'"
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

            # Task F — additive migration for patterns table: cross_session
            # flag (HITL-gated). Operator-approved cross-session patterns are
            # hydrated into other engines at L1 advisory. See OQ5/OQ6/OQ8.
            with contextlib.suppress(sqlite3.OperationalError):
                self._conn.execute(
                    "ALTER TABLE patterns ADD COLUMN cross_session INTEGER NOT NULL DEFAULT 0"
                )

            # Task L (v1.1) — additive migration for hitl_pending: dedicated
            # matched_hash column replacing the Task F string-encoded
            # `flag_cross_session:<hash>` proposed_action hack. Idempotent:
            # ALTER raises OperationalError on re-run.
            with contextlib.suppress(sqlite3.OperationalError):
                self._conn.execute(
                    "ALTER TABLE hitl_pending ADD COLUMN matched_hash TEXT NOT NULL DEFAULT ''"
                )

            # v1.3 P5d (Fix B / review) — additive migration for hitl_pending:
            # JSON-encoded ``bias_hint`` carries the Learn Mode advisory
            # bias so the dashboard can pre-fill the prompt with the
            # suggested action. Empty string when no bias matched. The
            # verdict is never mutated; the operator still confirms.
            with contextlib.suppress(sqlite3.OperationalError):
                self._conn.execute(
                    "ALTER TABLE hitl_pending ADD COLUMN bias_hint TEXT NOT NULL DEFAULT ''"
                )

            # v2.1 P2 (FR-PPP) — Layer 2 canary echo columns on
            # `provenance_assertions`. Additive ALTER; idempotent via
            # `PRAGMA table_info` guard (peer to the hitl_pending /
            # decisions migrations above). Existing P1 rows get
            # `canary_nonce=NULL, canary_confirmed_at=NULL` —
            # semantically "P1 row, no canary attempted yet".
            prov_cols = {
                row[1]
                for row in self._conn.execute(
                    "PRAGMA table_info(provenance_assertions)"
                ).fetchall()
            }
            if "canary_nonce" not in prov_cols:
                with contextlib.suppress(sqlite3.OperationalError):
                    self._conn.execute(
                        "ALTER TABLE provenance_assertions "
                        "ADD COLUMN canary_nonce TEXT"
                    )
            if "canary_confirmed_at" not in prov_cols:
                with contextlib.suppress(sqlite3.OperationalError):
                    self._conn.execute(
                        "ALTER TABLE provenance_assertions "
                        "ADD COLUMN canary_confirmed_at REAL"
                    )

            # One-time backfill: rows authored before Task L encoded the
            # pattern hash inside proposed_action as `flag_cross_session:<h>`.
            # Migrate them to (matched_hash=<h>, proposed_action='flag').
            # Skip rows already migrated (matched_hash != '') so re-runs are
            # safe.
            with contextlib.suppress(sqlite3.OperationalError):
                self._conn.execute(
                    "UPDATE hitl_pending "
                    "SET matched_hash = substr(proposed_action, "
                    "length('flag_cross_session:') + 1), "
                    "proposed_action = 'flag' "
                    "WHERE proposed_action LIKE 'flag_cross_session:%' "
                    "AND (matched_hash IS NULL OR matched_hash = '')"
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
        matched_hash: str = "",
        bias_hint: str = "",
    ) -> int:
        """Queue a decision for human approval. Returns hitl_pending.id.

        Task L: matched_hash carries the pattern hash for cross_session_flag
        rows so the dispatcher does not need to parse it out of
        proposed_action. Default '' for non-cross-session callers.

        v1.3 P5d (Fix B): ``bias_hint`` is a JSON-encoded
        ``BiasHint`` payload (or '' when no bias matched). The dashboard
        reads this column to pre-fill the HITL prompt with the suggested
        action. Verdict is never mutated; the operator still confirms.
        """
        queued_at = _dt.datetime.now(_dt.UTC).isoformat()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO hitl_pending (message_id, proposed_action, "
                "proposed_confidence, trigger_reason, queued_at, "
                "matched_hash, bias_hint) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    message_id,
                    proposed_action,
                    float(proposed_confidence),
                    trigger_reason,
                    queued_at,
                    matched_hash,
                    bias_hint,
                ),
            )
            pending_id = int(cur.lastrowid or 0)
        return pending_id

    def resolve_hitl(self, pending_id: int, resolution: str) -> None:
        """Mark a pending HITL row as resolved + dispatch any side effects."""
        resolved_at = _dt.datetime.now(_dt.UTC).isoformat()
        with self._lock:
            self._conn.execute(
                "UPDATE hitl_pending SET resolved_at=?, resolution=? "
                "WHERE id=? AND resolved_at IS NULL",
                (resolved_at, resolution, pending_id),
            )
        # Side-effect dispatcher (Task F): cross_session_flag rows that the
        # operator approves promote the underlying pattern to a hydrated
        # cross-session advisory in other engines. Lazy import avoids a
        # cycle with stream_manager.hitl.
        try:
            from stream_manager.hitl import dispatch_resolution
            dispatch_resolution(self, pending_id, resolution)
        except Exception:
            log.exception("resolve_hitl: dispatch_resolution failed")

    def get_pending_hitl(self, session_id: str) -> list[dict[str, object]]:
        """Return unresolved hitl_pending rows for a session, oldest first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT hp.id, hp.message_id, hp.proposed_action, "
                "hp.proposed_confidence, hp.trigger_reason, hp.queued_at, "
                "hp.resolved_at, hp.resolution, hp.matched_hash, "
                "hp.bias_hint "
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
                    "matched_hash": r[8] or "",
                    "bias_hint": r[9] or "",
                }
            )
        return out

    def get_hitl_pending_row(self, pending_id: int) -> dict[str, object] | None:
        """Look up a single hitl_pending row by id (for poll loops)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT id, message_id, proposed_action, proposed_confidence, "
                "trigger_reason, queued_at, resolved_at, resolution, "
                "matched_hash, bias_hint "
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
            "matched_hash": row[8] or "",
            "bias_hint": row[9] or "",
        }

    # ── v2.1 P1 (FR-PPP) — Provenance Probe Protocol ─────────────────

    def subscribe_envelope(self, callback: EnvelopeSubscriberCallback) -> None:
        """Register an envelope subscriber.

        Envelope subscribers receive (envelope_type, payload) tuples for
        non-message bus events such as `audit.probe` / `audit.probe_ack`
        (FR-PPP). They do NOT receive ordinary `Message` publishes — those
        go through `subscribe`. Per ADR-14, the dashboard's SSE stream
        bridges these envelopes to connected browsers.
        """
        self._envelope_subscribers.append(callback)

    def envelope_subscriber_count(self) -> int:
        """Return the number of registered envelope subscribers.

        Telemetry only. The `/api/sm-probe?force=1` 503 branch MUST NOT
        pre-check this counter — TOCTOU. The handler branches on the
        return value of `write_envelope` instead.
        """
        return len(self._envelope_subscribers)

    def unsubscribe_envelope(self, callback: EnvelopeSubscriberCallback) -> None:
        """Remove a previously-registered envelope subscriber.

        Idempotent. The dashboard SSE handler registers one envelope
        subscriber per browser connection and must call this in a
        ``try/finally`` on disconnect — without it, browser disconnects
        leak callbacks that hold references to the per-connection
        ``asyncio.Queue`` and the FastAPI request scope.
        """
        try:
            self._envelope_subscribers.remove(callback)
        except ValueError:
            pass

    def write_envelope(
        self, envelope_type: str, payload: dict[str, object]
    ) -> int:
        """Fan an envelope out to all registered envelope subscribers.

        Returns the number of subscribers that received the envelope.
        Subscriber failures are logged but do NOT crash the bus (NFR-R6
        invariant from `publish`). Used by the soak driver's
        `--ppp-auto-probe` direct-bus writer (issue #128 Option B) and by
        the dashboard `/api/sm-probe` HTTP handler — two writers, one
        bus, dashboard SSE consumes from the bus.
        """
        delivered = 0
        for sub in list(self._envelope_subscribers):
            try:
                sub(envelope_type, payload)
                delivered += 1
            except Exception:
                log.exception(
                    "envelope subscriber callback failed (%s)", envelope_type
                )
        return delivered

    def write_provenance_assertion(
        self,
        probe_id: str,
        session_id: str,
        jsonl_path: str | None,
        brain_id: str | None,
        prompt_hash: str | None,
        signed_at: float,
        expires_at: float,
        hmac_sig: str,
    ) -> bool:
        """Write a single provenance_assertions row. Returns False on
        replay (probe_id UNIQUE conflict); True on first write.

        Replay protection is atomic at the SQLite UNIQUE constraint
        level. The bus runs in autocommit mode (`isolation_level=None`,
        L222), so each INSERT commits immediately and the
        ``ON CONFLICT(probe_id) DO NOTHING`` clause guarantees no
        duplicate row writes regardless of caller-side concurrency. The
        caller (dashboard `/api/sm-probe/ack` POST handler) translates
        False to HTTP 409.
        """
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO provenance_assertions ("
                "probe_id, session_id, jsonl_path, brain_id, prompt_hash, "
                "signed_at, expires_at, hmac_sig) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(probe_id) DO NOTHING",
                (
                    probe_id,
                    session_id,
                    jsonl_path,
                    brain_id,
                    prompt_hash,
                    float(signed_at),
                    float(expires_at),
                    hmac_sig,
                ),
            )
            return (cur.rowcount or 0) > 0

    def get_active_provenance_assertion(
        self, session_id: str, now: float | None = None
    ) -> dict[str, object] | None:
        """Return the current (latest non-expired) assertion for a session.

        Multiple non-expired rows MAY coexist (e.g. operator answered then
        revised); readers MUST take the latest by `signed_at`. The
        `idx_provenance_session_active` index supports this query.
        """
        ts = float(now) if now is not None else time.time()
        with self._lock:
            row = self._conn.execute(
                "SELECT id, probe_id, session_id, jsonl_path, brain_id, "
                "prompt_hash, signed_at, expires_at, hmac_sig "
                "FROM provenance_assertions "
                "WHERE session_id=? AND expires_at > ? "
                "ORDER BY signed_at DESC LIMIT 1",
                (session_id, ts),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": int(row[0]),
            "probe_id": row[1],
            "session_id": row[2],
            "jsonl_path": row[3],
            "brain_id": row[4],
            "prompt_hash": row[5],
            "signed_at": float(row[6]),
            "expires_at": float(row[7]),
            "hmac_sig": row[8],
        }

    def mark_canary_confirmed(
        self,
        probe_id: str,
        nonce: str,
        confirmed_at: float,
    ) -> bool:
        """v2.1 P2 — record a Layer-2 canary echo on the assertion row.

        Single-write-wins via WHERE canary_confirmed_at IS NULL: a
        second observe of the same nonce (operator re-typed) does NOT
        re-stamp the row. Returns True on first write, False on no-op.
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE provenance_assertions "
                "SET canary_nonce=?, canary_confirmed_at=? "
                "WHERE probe_id=? AND canary_confirmed_at IS NULL",
                (nonce, float(confirmed_at), probe_id),
            )
            return (cur.rowcount or 0) > 0

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

    def get_session_settings(self, session_id: str) -> dict[str, object]:
        """Return the FR-UI-9 settings blob for a session.

        Returns an empty dict when the row is missing or the blob is
        unparsable. Callers MUST be tolerant of missing keys — the schema
        evolves additively.
        """
        with self._lock:
            try:
                row = self._conn.execute(
                    "SELECT settings FROM sessions WHERE id=?",
                    (session_id,),
                ).fetchone()
            except sqlite3.OperationalError:
                return {}
        if row is None or row[0] is None:
            return {}
        raw = str(row[0])
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except (TypeError, ValueError):
            pass
        return {}

    def set_session_settings(
        self, session_id: str, settings: dict[str, object]
    ) -> None:
        """Persist the FR-UI-9 settings blob for a session.

        Merges into any existing blob so callers may patch a subset of
        keys. Unknown keys are stored verbatim — server-side validation
        is done by the dashboard endpoint.
        """
        if not isinstance(settings, dict):
            raise TypeError("settings must be a dict")
        with self._lock:
            try:
                row = self._conn.execute(
                    "SELECT settings FROM sessions WHERE id=?",
                    (session_id,),
                ).fetchone()
            except sqlite3.OperationalError:
                row = None
            current: dict[str, object] = {}
            if row is not None and row[0]:
                try:
                    parsed = json.loads(str(row[0]))
                    if isinstance(parsed, dict):
                        current = parsed
                except (TypeError, ValueError):
                    current = {}
            merged = {**current, **settings}
            blob = json.dumps(merged, separators=(",", ":"))
            self._conn.execute(
                "UPDATE sessions SET settings=? WHERE id=?",
                (blob, session_id),
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

    # ── Task F: cross-session patterns (HITL-gated) ───────────────────

    def upsert_pattern(
        self,
        hash: str,
        level: int,
        occurrences: int,
        success_rate: float,
        last_seen: float,
        payload: str = "",
    ) -> None:
        """Insert or update a row in patterns. Preserves cross_session flag."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO patterns (hash, level, occurrences, success_rate, "
                "last_seen, payload) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(hash) DO UPDATE SET level=excluded.level, "
                "occurrences=excluded.occurrences, "
                "success_rate=excluded.success_rate, "
                "last_seen=excluded.last_seen, "
                "payload=excluded.payload",
                (
                    hash,
                    int(level),
                    int(occurrences),
                    float(success_rate),
                    float(last_seen),
                    payload,
                ),
            )

    def flag_pattern_cross_session(self, hash: str) -> bool:
        """Set patterns.cross_session=1 for the given hash. Returns True if a
        row was updated. Caller is responsible for ensuring the hash exists
        (via upsert_pattern) before flagging.
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE patterns SET cross_session=1 WHERE hash=?",
                (hash,),
            )
            return (cur.rowcount or 0) > 0

    def unflag_pattern_cross_session(self, hash: str) -> bool:
        """Set patterns.cross_session=0 for the given hash. Returns True if a
        row was updated.
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE patterns SET cross_session=0 WHERE hash=?",
                (hash,),
            )
            return (cur.rowcount or 0) > 0

    def get_cross_session_patterns(self) -> list[dict[str, object]]:
        """Return all patterns with cross_session=1, newest first by last_seen."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT hash, level, occurrences, success_rate, last_seen, "
                "payload FROM patterns WHERE cross_session=1 "
                "ORDER BY last_seen DESC"
            ).fetchall()
        return [
            {
                "hash": str(r[0]),
                "level": int(r[1]),
                "occurrences": int(r[2]),
                "success_rate": float(r[3]),
                "last_seen": float(r[4]),
                "payload": str(r[5]) if r[5] is not None else "",
            }
            for r in rows
        ]

    def get_pattern(self, hash: str) -> dict[str, object] | None:
        """Return a single patterns row by hash, or None."""
        with self._lock:
            row = self._conn.execute(
                "SELECT hash, level, occurrences, success_rate, last_seen, "
                "payload, cross_session FROM patterns WHERE hash=?",
                (hash,),
            ).fetchone()
        if row is None:
            return None
        return {
            "hash": str(row[0]),
            "level": int(row[1]),
            "occurrences": int(row[2]),
            "success_rate": float(row[3]),
            "last_seen": float(row[4]),
            "payload": str(row[5]) if row[5] is not None else "",
            "cross_session": int(row[6]),
        }

    def get_hitl_pending_for_hash(self, matched_hash: str) -> list[dict[str, object]]:
        """Return hitl_pending rows for the given pattern hash.

        Task L: queries the dedicated hitl_pending.matched_hash column.
        For backward compat with rows authored under the v1.0 hack
        (proposed_action='flag_cross_session:<hash>') we also union those
        in — the migration backfill handles already-migrated DBs but a
        caller hitting an un-initialized legacy DB still gets correct
        results.
        """
        if not matched_hash:
            return []
        legacy_prefix = f"flag_cross_session:{matched_hash}"
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, message_id, proposed_action, proposed_confidence, "
                "trigger_reason, queued_at, resolved_at, resolution, "
                "matched_hash "
                "FROM hitl_pending "
                "WHERE matched_hash=? OR proposed_action=? "
                "ORDER BY id ASC",
                (matched_hash, legacy_prefix),
            ).fetchall()
        return [
            {
                "id": int(r[0]),
                "message_id": r[1],
                "proposed_action": r[2],
                "proposed_confidence": float(r[3]),
                "trigger_reason": r[4],
                "queued_at": r[5],
                "resolved_at": r[6],
                "resolution": r[7],
                "matched_hash": r[8] or "",
            }
            for r in rows
        ]

    def fetch_rows(
        self,
        query: str,
        params: tuple = (),
    ) -> list[tuple]:
        """TEST/INTROSPECTION ONLY — do not call from hot paths.

        Holds the bus lock across ``fetchall()``; long queries will block
        all writers. Run a SELECT (or WITH/CTE) under the bus lock and
        return ``fetchall()`` as a list of tuples. This exists so callers
        do not have to reach into ``self._conn`` directly. The helper is
        intentionally narrow: no row factory, no DDL, no commit semantics
        — pass the query and bound parameters and consume the rows.

        Guarded read-only: queries that do not start with SELECT or WITH
        raise ``ValueError``.

        Added in v1.3 to migrate tests off ``bus._conn.execute(...)``.
        """
        stripped = query.lstrip().lower()
        if not (stripped.startswith("select") or stripped.startswith("with")):
            first_word = stripped.split(None, 1)[0] if stripped else ""
            raise ValueError(
                f"fetch_rows is read-only; expected SELECT/WITH, got: {first_word}"
            )
        with self._lock:
            return list(self._conn.execute(query, params).fetchall())

    def execute_write(
        self,
        query: str,
        params: tuple = (),
    ) -> None:
        """Symmetric write companion to ``fetch_rows``.

        Holds the bus lock and runs a non-SELECT statement, matching the
        codebase's "small write under bus lock" idiom. Connections are
        opened with ``isolation_level=None`` (autocommit) so no explicit
        commit is required.

        Guarded write-only: queries whose first keyword is ``select`` or
        ``with`` raise ``ValueError``. Use ``fetch_rows`` for those.

        Added in v1.3 P5c so callers (e.g. ``LearnCategorizerWorker``)
        do not have to reach into ``self._conn`` / ``self._lock``.
        """
        stripped = query.lstrip().lower()
        first_word = stripped.split(None, 1)[0] if stripped else ""
        if first_word in ("select", "with"):
            raise ValueError(
                f"execute_write is for non-SELECT statements; got: {first_word}"
            )
        with self._lock:
            self._conn.execute(query, params)

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
