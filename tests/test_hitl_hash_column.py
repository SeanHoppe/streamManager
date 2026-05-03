"""Task L (v1.1): hitl_pending.matched_hash dedicated column.

Reference: docs/v1.1-task-plan.md (Task L block).

Replaces the v1.0 Task F string-encoding hack where the pattern hash
travelled inside `proposed_action="flag_cross_session:<hash>"`. After
this migration the hash lives in `hitl_pending.matched_hash` and the
proposed_action is simply "flag".

Coverage:
1. matched_hash column present after MessageBus init
2. queue_hitl(matched_hash=...) round-trips through get_hitl_pending_row
   and get_pending_hitl
3. dispatch_resolution reads from matched_hash column on a fresh
   (post-Task L) row
4. Backfill: a DB seeded with legacy
   `proposed_action="flag_cross_session:<hash>"` rows is migrated
   on next MessageBus init — matched_hash populated, proposed_action
   normalised to "flag"
5. Backfill is idempotent — running migration twice doesn't
   re-corrupt already-migrated rows
6. Legacy fallback: dispatch_resolution still resolves correctly when
   matched_hash is empty AND proposed_action carries the legacy prefix
   (covers untouched DBs in the wild)
"""

from __future__ import annotations

import sqlite3

from stream_manager.hitl import dispatch_resolution
from stream_manager.message_bus import MessageBus, Message


# ── helpers ──────────────────────────────────────────────────────────


def _open_session_and_anchor(bus: MessageBus, session_id: str) -> str:
    """Open a session and publish an anchor message; return its id."""
    bus.open_session(session_id)
    anchor = Message.new(
        session_id=session_id,
        type="cross_session_promotion",
        direction="internal",
        content="placeholder",
    )
    bus.publish(anchor)
    return anchor.id


# ── 1. column present ────────────────────────────────────────────────


def test_matched_hash_column_present(tmp_path):
    bus = MessageBus(str(tmp_path / "gov.db"))
    cols = {
        row[1]
        for row in bus._conn.execute("PRAGMA table_info(hitl_pending)").fetchall()
    }
    assert "matched_hash" in cols
    bus.close()


# ── 2. queue_hitl round-trips matched_hash ──────────────────────────


def test_queue_hitl_persists_matched_hash(tmp_path):
    bus = MessageBus(str(tmp_path / "gov.db"))
    msg_id = _open_session_and_anchor(bus, "s-A")

    pending_id = bus.queue_hitl(
        message_id=msg_id,
        proposed_action="flag",
        proposed_confidence=0.9,
        trigger_reason="cross_session_flag",
        matched_hash="deadbeef",
    )

    row = bus.get_hitl_pending_row(pending_id)
    assert row is not None
    assert row["matched_hash"] == "deadbeef"
    assert row["proposed_action"] == "flag"

    pending = bus.get_pending_hitl("s-A")
    assert pending and pending[0]["matched_hash"] == "deadbeef"
    bus.close()


def test_queue_hitl_default_matched_hash_is_empty(tmp_path):
    """Non-cross-session callers omit matched_hash — it must default to ''."""
    bus = MessageBus(str(tmp_path / "gov.db"))
    msg_id = _open_session_and_anchor(bus, "s-A")

    pending_id = bus.queue_hitl(
        message_id=msg_id,
        proposed_action="approve",
        proposed_confidence=0.5,
        trigger_reason="low_confidence",
    )
    row = bus.get_hitl_pending_row(pending_id)
    assert row is not None
    assert row["matched_hash"] == ""
    bus.close()


# ── 3. dispatch_resolution reads from new column ────────────────────


def test_dispatch_resolution_uses_matched_hash_column(tmp_path):
    bus = MessageBus(str(tmp_path / "gov.db"))
    msg_id = _open_session_and_anchor(bus, "s-A")
    target = "abc123"

    # Seed pattern row so flag_pattern_cross_session has something to flip.
    bus.upsert_pattern(
        hash=target,
        level=3,
        occurrences=10,
        success_rate=0.9,
        last_seen=1.0,
        payload="npm run build",
    )
    pending_id = bus.queue_hitl(
        message_id=msg_id,
        proposed_action="flag",
        proposed_confidence=0.9,
        trigger_reason="cross_session_flag",
        matched_hash=target,
    )

    bus.resolve_hitl(pending_id, "approved")

    row = bus.get_pattern(target)
    assert row is not None
    assert row["cross_session"] == 1
    bus.close()


# ── 4. backfill on legacy rows ──────────────────────────────────────


def _seed_legacy_row(db_path, session_id: str, target_hash: str) -> int:
    """Open a raw sqlite connection, create the v1.0 schema (no
    matched_hash column), and insert one legacy row. Returns its id.
    Mimics a DB authored before Task L shipped.
    """
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # v1.0 schema for the two tables we need (no matched_hash column).
    conn.executescript(
        """
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
        """
    )
    msg_id = "anchor-legacy"
    conn.execute(
        "INSERT INTO messages (id, session_id, sequence, type, direction, "
        "content, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (msg_id, session_id, 1, "cross_session_promotion", "internal",
         "placeholder", 0.0),
    )
    cur = conn.execute(
        "INSERT INTO hitl_pending (message_id, proposed_action, "
        "proposed_confidence, trigger_reason, queued_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (msg_id, f"flag_cross_session:{target_hash}", 0.9,
         "cross_session_flag", "1970-01-01T00:00:00+00:00"),
    )
    pending_id = int(cur.lastrowid or 0)
    conn.close()
    return pending_id


def test_backfill_migrates_legacy_rows(tmp_path):
    db = tmp_path / "gov.db"
    target = "legacyhash"
    pending_id = _seed_legacy_row(db, "s-A", target)

    # Open via MessageBus — _init_schema runs the additive migration +
    # backfill.
    bus = MessageBus(str(db))
    row = bus.get_hitl_pending_row(pending_id)
    assert row is not None
    assert row["matched_hash"] == target
    assert row["proposed_action"] == "flag"
    bus.close()


def test_backfill_is_idempotent(tmp_path):
    """Re-opening an already-migrated DB must not corrupt rows."""
    db = tmp_path / "gov.db"
    target = "legacyhash"
    pending_id = _seed_legacy_row(db, "s-A", target)

    bus1 = MessageBus(str(db))
    row1 = bus1.get_hitl_pending_row(pending_id)
    bus1.close()

    bus2 = MessageBus(str(db))
    row2 = bus2.get_hitl_pending_row(pending_id)
    bus2.close()

    assert row1 == row2
    assert row2["matched_hash"] == target
    assert row2["proposed_action"] == "flag"


def test_backfill_skips_already_migrated_rows(tmp_path):
    """If a row already has a non-empty matched_hash, leave it alone
    (backfill must not touch it even if the proposed_action somehow still
    looks legacy).
    """
    bus = MessageBus(str(tmp_path / "gov.db"))
    msg_id = _open_session_and_anchor(bus, "s-A")
    pending_id = bus.queue_hitl(
        message_id=msg_id,
        proposed_action="flag",
        proposed_confidence=0.9,
        trigger_reason="cross_session_flag",
        matched_hash="real",
    )
    # Force a sentinel value in proposed_action that LIKE 'flag_cross_session:%'
    # would match — backfill must skip because matched_hash is already set.
    bus._conn.execute(
        "UPDATE hitl_pending SET proposed_action='flag_cross_session:fake' "
        "WHERE id=?",
        (pending_id,),
    )
    bus.close()

    # Re-open — backfill runs again, but should NOT overwrite matched_hash.
    bus2 = MessageBus(str(tmp_path / "gov.db"))
    row = bus2.get_hitl_pending_row(pending_id)
    assert row is not None
    assert row["matched_hash"] == "real"  # unchanged
    bus2.close()


# ── 5. legacy fallback in dispatch_resolution ───────────────────────


def test_dispatch_resolution_legacy_fallback(tmp_path, monkeypatch):
    """If matched_hash is empty but proposed_action still carries the
    v1.0 prefix, dispatch_resolution must extract the hash and flip
    the cross_session flag. Belt-and-suspenders for DBs that, for
    whatever reason, slipped past the backfill step.
    """
    bus = MessageBus(str(tmp_path / "gov.db"))
    msg_id = _open_session_and_anchor(bus, "s-A")
    target = "fallback_hash"
    bus.upsert_pattern(
        hash=target,
        level=3,
        occurrences=10,
        success_rate=0.9,
        last_seen=1.0,
        payload="npm run build",
    )
    # Manually craft a row that looks pre-Task-L (no matched_hash) so we
    # exercise the fallback branch.
    bus._conn.execute(
        "INSERT INTO hitl_pending (message_id, proposed_action, "
        "proposed_confidence, trigger_reason, queued_at, matched_hash) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (msg_id, f"flag_cross_session:{target}", 0.9,
         "cross_session_flag", "1970-01-01T00:00:00+00:00", ""),
    )
    pending_id = int(
        bus._conn.execute(
            "SELECT id FROM hitl_pending ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
    )

    # Direct call to the dispatcher (bypasses resolve_hitl's UPDATE
    # so we keep the empty matched_hash on read).
    dispatch_resolution(bus, pending_id, "approved")

    row = bus.get_pattern(target)
    assert row is not None
    assert row["cross_session"] == 1
    bus.close()
