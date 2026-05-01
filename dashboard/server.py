"""FastAPI + SSE governance dashboard server.

Reads from the WAL bus (gov.db) using the schema from message_bus.py:
    messages(id, session_id, sequence, type, direction, content,
             context, metadata, timestamp)
    decisions(id, message_id, action, confidence, reasoning,
              matched_hash, timestamp)
    sessions(id, project_slug, pid, started_at, ended_at)

Usage:
    pip install -r dashboard/requirements.txt
    uvicorn dashboard.server:app --port 8765 --reload

    # custom DB path:
    GOV_DB=.claude/gov.db uvicorn dashboard.server:app --port 8765
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("GOV_DB", str(ROOT / ".claude" / "gov.db")))
STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="StreamManager Governance Dashboard")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_SEED_SQL = """
    SELECT d.rowid AS rid, d.action, d.confidence, d.reasoning,
           d.matched_hash, d.timestamp,
           m.content, m.direction, m.session_id,
           (SELECT a.profile_slug FROM agents a
              WHERE a.session_id = m.session_id AND a.last_seen <= d.timestamp
              ORDER BY a.last_seen DESC LIMIT 1) AS profile_slug,
           (SELECT a.attribution_plugin FROM agents a
              WHERE a.session_id = m.session_id AND a.last_seen <= d.timestamp
              ORDER BY a.last_seen DESC LIMIT 1) AS attribution_plugin
    FROM decisions d
    JOIN messages m ON d.message_id = m.id
    ORDER BY d.rowid DESC LIMIT ?
"""

_TAIL_SQL = """
    SELECT d.rowid AS rid, d.action, d.confidence, d.reasoning,
           d.matched_hash, d.timestamp,
           m.content, m.direction, m.session_id,
           (SELECT a.profile_slug FROM agents a
              WHERE a.session_id = m.session_id AND a.last_seen <= d.timestamp
              ORDER BY a.last_seen DESC LIMIT 1) AS profile_slug,
           (SELECT a.attribution_plugin FROM agents a
              WHERE a.session_id = m.session_id AND a.last_seen <= d.timestamp
              ORDER BY a.last_seen DESC LIMIT 1) AS attribution_plugin
    FROM decisions d
    JOIN messages m ON d.message_id = m.id
    WHERE d.rowid > ?
    ORDER BY d.rowid ASC
"""

_STATS_SQL = """
    SELECT
        COUNT(*)                                              AS total,
        COUNT(DISTINCT m.session_id)                         AS sessions,
        SUM(CASE WHEN d.matched_hash != '' THEN 1 ELSE 0 END) AS graph_hits,
        AVG(d.confidence)                                    AS avg_conf
    FROM decisions d
    JOIN messages m ON d.message_id = m.id
"""

_ACTIONS_SQL = "SELECT action, COUNT(*) AS n FROM decisions GROUP BY action"
_ACTIVE_SQL  = "SELECT COUNT(*) FROM sessions WHERE ended_at IS NULL"


def _open(readonly: bool = True) -> sqlite3.Connection:
    uri = f"file:{DB_PATH}{'?mode=ro' if readonly else ''}".replace("\\", "/")
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)
    except sqlite3.OperationalError:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _has_agents_table(conn: sqlite3.Connection) -> bool:
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agents'"
        ).fetchone()
        return row is not None
    except Exception:
        return False


_SEED_SQL_NO_AGENTS = """
    SELECT d.rowid AS rid, d.action, d.confidence, d.reasoning,
           d.matched_hash, d.timestamp,
           m.content, m.direction, m.session_id,
           NULL AS profile_slug, NULL AS attribution_plugin
    FROM decisions d
    JOIN messages m ON d.message_id = m.id
    ORDER BY d.rowid DESC LIMIT ?
"""

_TAIL_SQL_NO_AGENTS = """
    SELECT d.rowid AS rid, d.action, d.confidence, d.reasoning,
           d.matched_hash, d.timestamp,
           m.content, m.direction, m.session_id,
           NULL AS profile_slug, NULL AS attribution_plugin
    FROM decisions d
    JOIN messages m ON d.message_id = m.id
    WHERE d.rowid > ?
    ORDER BY d.rowid ASC
"""


def _seed_sql(conn: sqlite3.Connection) -> str:
    return _SEED_SQL if _has_agents_table(conn) else _SEED_SQL_NO_AGENTS


def _tail_sql(conn: sqlite3.Connection) -> str:
    return _TAIL_SQL if _has_agents_table(conn) else _TAIL_SQL_NO_AGENTS


@app.get("/", response_class=HTMLResponse)
async def root():
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/stats")
async def api_stats():
    try:
        conn = _open()
        tot   = conn.execute(_STATS_SQL).fetchone()
        acts  = conn.execute(_ACTIONS_SQL).fetchall()
        active = conn.execute(_ACTIVE_SQL).fetchone()[0]
        conn.close()
    except Exception as exc:
        return {"error": str(exc), "total_decisions": 0}

    total = int(tot["total"] or 0)
    graph = int(tot["graph_hits"] or 0)
    return {
        "total_decisions": total,
        "sessions":        int(tot["sessions"] or 0),
        "active_sessions": int(active or 0),
        "graph_pct":       round(graph / total * 100, 1) if total else 0.0,
        "avg_confidence":  round(float(tot["avg_conf"] or 0), 3),
        "actions":         {r["action"]: int(r["n"]) for r in acts},
    }


@app.get("/api/decisions")
async def api_decisions(limit: int = 50):
    """Seed: last N decisions newest-first (for page load before SSE connects)."""
    try:
        conn = _open()
        rows = conn.execute(_seed_sql(conn), (min(limit, 200),)).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


@app.get("/api/agents")
async def api_agents(session_id: str | None = None, limit: int = 50):
    """Active agents per session — newest last_seen first.

    If session_id is provided, scope to that session. Otherwise return up
    to `limit` rows across all sessions.
    """
    try:
        conn = _open()
        if session_id:
            rows = conn.execute(
                "SELECT session_id, attribution_plugin, attribution_skill, "
                "is_sidechain, profile_slug, first_seen, last_seen "
                "FROM agents WHERE session_id=? "
                "ORDER BY last_seen DESC LIMIT ?",
                (session_id, min(limit, 200)),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT session_id, attribution_plugin, attribution_skill, "
                "is_sidechain, profile_slug, first_seen, last_seen "
                "FROM agents ORDER BY last_seen DESC LIMIT ?",
                (min(limit, 200),),
            ).fetchall()
        conn.close()
        out = []
        for r in rows:
            d = dict(r)
            d["is_sidechain"] = bool(d.get("is_sidechain"))
            out.append(d)
        return out
    except Exception:
        return []


@app.get("/api/sessions")
async def api_sessions(limit: int = 10):
    """Recent sessions, newest first."""
    try:
        conn = _open()
        rows = conn.execute(
            "SELECT id, project_slug, pid, started_at, ended_at "
            "FROM sessions ORDER BY started_at DESC LIMIT ?",
            (min(limit, 50),),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


# ── FR-HITL §4.9 dashboard endpoints ─────────────────────────────────


def _open_rw() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        return row is not None
    except Exception:
        return False


@app.get("/api/hitl/pending")
async def api_hitl_pending(session_id: str | None = None):
    """Return unresolved hitl_pending rows. If session_id is omitted,
    return unresolved rows across all sessions."""
    try:
        conn = _open()
        if not _has_table(conn, "hitl_pending"):
            conn.close()
            return []
        if session_id:
            rows = conn.execute(
                "SELECT hp.id, hp.message_id, hp.proposed_action, "
                "hp.proposed_confidence, hp.trigger_reason, hp.queued_at, "
                "m.session_id, m.content "
                "FROM hitl_pending hp JOIN messages m ON hp.message_id=m.id "
                "WHERE hp.resolved_at IS NULL AND m.session_id=? "
                "ORDER BY hp.id ASC",
                (session_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT hp.id, hp.message_id, hp.proposed_action, "
                "hp.proposed_confidence, hp.trigger_reason, hp.queued_at, "
                "m.session_id, m.content "
                "FROM hitl_pending hp JOIN messages m ON hp.message_id=m.id "
                "WHERE hp.resolved_at IS NULL ORDER BY hp.id ASC"
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


_VALID_RESOLUTIONS = {
    "approved",
    "dismissed",
    "overridden:ALLOW",
    "overridden:GUIDE",
    "overridden:SUGGEST",
    "overridden:INTERVENE",
    "overridden:BLOCK",
}


@app.post("/api/hitl/resolve")
async def api_hitl_resolve(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json body")
    pending_id = body.get("pending_id")
    resolution = body.get("resolution")
    if not isinstance(pending_id, int):
        raise HTTPException(status_code=400, detail="pending_id must be int")
    if not isinstance(resolution, str) or resolution not in _VALID_RESOLUTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"resolution must be one of {sorted(_VALID_RESOLUTIONS)}",
        )
    try:
        conn = _open_rw()
        conn.execute(
            "UPDATE hitl_pending SET resolved_at=?, resolution=? "
            "WHERE id=? AND resolved_at IS NULL",
            (
                _iso_now(),
                resolution,
                pending_id,
            ),
        )
        conn.close()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"ok": True, "pending_id": pending_id, "resolution": resolution}


@app.post("/api/hitl/annotate")
async def api_hitl_annotate(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json body")
    decision_id = body.get("decision_id")
    override_action = body.get("override_action")
    note = body.get("note")
    if not isinstance(decision_id, str) or not decision_id:
        raise HTTPException(status_code=400, detail="decision_id required")
    if not isinstance(override_action, str) or not override_action:
        raise HTTPException(status_code=400, detail="override_action required")
    if note is not None and not isinstance(note, str):
        raise HTTPException(status_code=400, detail="note must be string or null")
    try:
        conn = _open_rw()
        d = conn.execute(
            "SELECT action, matched_hash FROM decisions WHERE id=?",
            (decision_id,),
        ).fetchone()
        if d is None:
            conn.close()
            raise HTTPException(status_code=404, detail="decision not found")
        original_action = str(d["action"])
        truncated_note: str | None = None
        if note:
            parts = note.split()
            truncated_note = " ".join(parts[:50])
        conn.execute(
            "INSERT INTO hitl_overrides (decision_id, original_action, "
            "override_action, note, mode, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (
                decision_id,
                original_action,
                override_action,
                truncated_note,
                "async",
                _iso_now(),
            ),
        )
        conn.close()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"ok": True, "decision_id": decision_id, "override_action": override_action}


_DEFAULT_TIMEOUT_S = 60.0


@app.get("/api/hitl/settings")
async def api_hitl_settings(session_id: str | None = None):
    if not session_id:
        return {
            "hitl_mode": "async",
            "hitl_floor": 0.60,
            "timeout_seconds": _DEFAULT_TIMEOUT_S,
        }
    try:
        conn = _open()
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        if "hitl_mode" not in cols or "hitl_floor" not in cols:
            conn.close()
            return {
                "hitl_mode": "async",
                "hitl_floor": 0.60,
                "timeout_seconds": _DEFAULT_TIMEOUT_S,
            }
        row = conn.execute(
            "SELECT hitl_mode, hitl_floor FROM sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        conn.close()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if row is None:
        return {
            "hitl_mode": "async",
            "hitl_floor": 0.60,
            "timeout_seconds": _DEFAULT_TIMEOUT_S,
        }
    return {
        "hitl_mode": str(row["hitl_mode"]) if row["hitl_mode"] else "async",
        "hitl_floor": float(row["hitl_floor"]) if row["hitl_floor"] is not None else 0.60,
        "timeout_seconds": _DEFAULT_TIMEOUT_S,
    }


@app.post("/api/hitl/settings")
async def api_hitl_settings_update(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json body")
    session_id = body.get("session_id")
    hitl_mode = body.get("hitl_mode")
    hitl_floor = body.get("hitl_floor")
    if not isinstance(session_id, str) or not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    if hitl_mode not in ("sync", "async"):
        raise HTTPException(status_code=400, detail="hitl_mode must be 'sync' or 'async'")
    try:
        floor_f = float(hitl_floor)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="hitl_floor must be a number")
    if floor_f < 0.0 or floor_f > 1.0:
        raise HTTPException(status_code=400, detail="hitl_floor must be in [0.0, 1.0]")
    try:
        conn = _open_rw()
        conn.execute(
            "UPDATE sessions SET hitl_mode=?, hitl_floor=? WHERE id=?",
            (hitl_mode, floor_f, session_id),
        )
        conn.close()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"ok": True, "session_id": session_id, "hitl_mode": hitl_mode, "hitl_floor": floor_f}


def _iso_now() -> str:
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


_HITL_EVENT_TYPES = ("hitl_sync_queued", "hitl_async_flagged", "hitl_timeout")


@app.get("/events")
async def sse_events(request: Request):
    """SSE stream: one JSON event per new decision row, 500ms poll."""

    async def generate():
        try:
            conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            return

        # Seed with last 25 decisions (oldest→newest so client prepends correctly)
        try:
            seed = conn.execute(_seed_sql(conn), (25,)).fetchall()
            last_rid = seed[0]["rid"] if seed else 0
            for row in reversed(seed):
                yield f"data: {json.dumps(dict(row))}\n\n"
        except Exception:
            last_rid = 0

        # Track last messages.rowid we've seen for HITL bus events.
        try:
            last_msg_rid = conn.execute(
                "SELECT COALESCE(MAX(rowid), 0) FROM messages"
            ).fetchone()[0]
        except Exception:
            last_msg_rid = 0

        while True:
            if await request.is_disconnected():
                break
            try:
                rows = conn.execute(_tail_sql(conn), (last_rid,)).fetchall()
                for row in rows:
                    last_rid = row["rid"]
                    yield f"data: {json.dumps(dict(row))}\n\n"
            except Exception:
                pass
            # FR-HITL §4.9: forward hitl_sync_queued and hitl_async_flagged
            # bus events as SSE messages so the dashboard can update the
            # HITL Queue panel in real time.
            try:
                placeholders = ",".join("?" for _ in _HITL_EVENT_TYPES)
                hitl_rows = conn.execute(
                    f"SELECT rowid AS rid, id, session_id, type, content, "
                    f"metadata, timestamp FROM messages "
                    f"WHERE rowid > ? AND type IN ({placeholders}) "
                    f"ORDER BY rowid ASC",
                    (last_msg_rid, *_HITL_EVENT_TYPES),
                ).fetchall()
                for hr in hitl_rows:
                    last_msg_rid = hr["rid"]
                    payload = dict(hr)
                    payload["event_type"] = payload.pop("type")
                    yield f"data: {json.dumps(payload)}\n\n"
            except Exception:
                pass
            await asyncio.sleep(0.5)

        conn.close()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":       "keep-alive",
        },
    )
