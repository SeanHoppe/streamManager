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
import logging
import os
import sqlite3
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("GOV_DB", str(ROOT / ".claude" / "gov.db")))
STATIC = Path(__file__).resolve().parent / "static"

# ── FR-HITL §4.9: shared HitlQueue + MessageBus instances ───────────────
# Module-level singletons wired lazily on first access. The dashboard
# server is read-mostly against gov.db, but HITL settings/resolutions need
# the same MessageBus instance so notes/feedback land in WAL the same way
# the governance engine writes them.
_bus = None  # type: ignore[var-annotated]
_hitl_queue = None  # type: HitlQueue | None
_hitl_runtime_settings: dict[str, object] = {
    "timeout_seconds": 60.0,
    "pause_detection_enabled": True,
}

# ── Phase 6 §1 + follow-up: Per-agent governance mode override ─────────
# Storage moved to AgentRegistry so the engine and dashboard share the
# same source of truth. Override applies to profile.default_action only
# (safety floor preserved — blocked_ops still fire).
_VALID_OVERRIDE_MODES = {"OBSERVE", "SUGGEST", "GUIDE", "INTERVENE", "BLOCK"}
_registry = None  # type: ignore[var-annotated]


def _get_bus():
    """Return a lazily-initialized shared MessageBus instance."""
    global _bus
    if _bus is None:
        try:
            from stream_manager.message_bus import MessageBus
            _bus = MessageBus(str(DB_PATH))
        except Exception:
            _bus = None
    return _bus


def _get_registry():
    """Return a lazily-initialized shared AgentRegistry singleton.

    The registry holds per-agent mode overrides for the dashboard
    process. The governance engine running in-process can be wired to
    the same instance by having the engine accept a pre-built registry.
    Returns None on import/load failure (override storage will degrade
    gracefully — POST returns 422 in that case).
    """
    global _registry
    if _registry is None:
        try:
            from stream_manager.agent_registry import AgentRegistry
            profiles_path = (
                ROOT / "src" / "stream_manager" / "agent_profiles.yaml"
            )
            _registry = AgentRegistry(profiles_path=profiles_path)
        except Exception:
            _registry = None
    return _registry


def _get_hitl_queue():
    """Return a lazily-initialized shared HitlQueue instance."""
    global _hitl_queue
    if _hitl_queue is None:
        bus = _get_bus()
        if bus is None:
            return None
        try:
            from stream_manager.hitl import HitlQueue
            _hitl_queue = HitlQueue(
                bus=bus,
                timeout_seconds=float(_hitl_runtime_settings["timeout_seconds"]),
            )
        except Exception:
            _hitl_queue = None
    return _hitl_queue


app = FastAPI(title="StreamManager Governance Dashboard")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_SEED_SQL = """
    SELECT d.rowid AS rid, d.id AS id, d.message_id AS message_id,
           d.action, d.confidence, d.reasoning,
           d.matched_hash, d.timestamp,
           COALESCE(d.model_used, '') AS model_used,
           COALESCE(d.layer, 0)       AS layer,
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
    SELECT d.rowid AS rid, d.id AS id, d.message_id AS message_id,
           d.action, d.confidence, d.reasoning,
           d.matched_hash, d.timestamp,
           COALESCE(d.model_used, '') AS model_used,
           COALESCE(d.layer, 0)       AS layer,
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


def _has_decision_routing_cols(conn: sqlite3.Connection) -> bool:
    """Phase 4: detect whether the decisions table has model_used + layer."""
    try:
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(decisions)").fetchall()
        }
        return "model_used" in cols and "layer" in cols
    except Exception:
        return False


_SEED_SQL_NO_AGENTS = """
    SELECT d.rowid AS rid, d.id AS id, d.message_id AS message_id,
           d.action, d.confidence, d.reasoning,
           d.matched_hash, d.timestamp,
           COALESCE(d.model_used, '') AS model_used,
           COALESCE(d.layer, 0)       AS layer,
           m.content, m.direction, m.session_id,
           NULL AS profile_slug, NULL AS attribution_plugin
    FROM decisions d
    JOIN messages m ON d.message_id = m.id
    ORDER BY d.rowid DESC LIMIT ?
"""

_TAIL_SQL_NO_AGENTS = """
    SELECT d.rowid AS rid, d.id AS id, d.message_id AS message_id,
           d.action, d.confidence, d.reasoning,
           d.matched_hash, d.timestamp,
           COALESCE(d.model_used, '') AS model_used,
           COALESCE(d.layer, 0)       AS layer,
           m.content, m.direction, m.session_id,
           NULL AS profile_slug, NULL AS attribution_plugin
    FROM decisions d
    JOIN messages m ON d.message_id = m.id
    WHERE d.rowid > ?
    ORDER BY d.rowid ASC
"""


def _seed_sql(conn: sqlite3.Connection) -> str:
    sql = _SEED_SQL if _has_agents_table(conn) else _SEED_SQL_NO_AGENTS
    if not _has_decision_routing_cols(conn):
        sql = sql.replace(
            "COALESCE(d.model_used, '') AS model_used,",
            "'' AS model_used,",
        ).replace(
            "COALESCE(d.layer, 0)       AS layer,",
            "0  AS layer,",
        )
    return sql


def _tail_sql(conn: sqlite3.Connection) -> str:
    sql = _TAIL_SQL if _has_agents_table(conn) else _TAIL_SQL_NO_AGENTS
    if not _has_decision_routing_cols(conn):
        sql = sql.replace(
            "COALESCE(d.model_used, '') AS model_used,",
            "'' AS model_used,",
        ).replace(
            "COALESCE(d.layer, 0)       AS layer,",
            "0  AS layer,",
        )
    return sql


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
async def api_decisions(limit: int = 50, session_id: str | None = None):
    """Seed: last N decisions newest-first (for page load before SSE connects).

    Phase 6 §5: optional ?session_id= filter for the session selector.
    """
    try:
        conn = _open()
        base = _seed_sql(conn)
        if session_id:
            # Inject WHERE clause before ORDER BY
            sql = base.replace(
                "JOIN messages m ON d.message_id = m.id",
                "JOIN messages m ON d.message_id = m.id WHERE m.session_id = ?",
            )
            rows = conn.execute(sql, (session_id, min(limit, 200))).fetchall()
        else:
            rows = conn.execute(base, (min(limit, 200),)).fetchall()
        conn.close()
        out = []
        for r in rows:
            d = dict(r)
            # Phase 6 §7: alias profile_slug -> agent_profile_slug
            d["agent_profile_slug"] = d.get("profile_slug")
            out.append(d)
        return out
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


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
        registry = _get_registry()
        for r in rows:
            d = dict(r)
            d["is_sidechain"] = bool(d.get("is_sidechain"))
            # Phase 6 §1: surface active per-agent mode override (if any)
            sess = d.get("session_id")
            slug = d.get("profile_slug")
            override = None
            if sess and slug and registry is not None:
                override = registry.get_mode_override(str(sess), str(slug))
            d["mode_override"] = override
            out.append(d)
        return out
    except Exception:
        return []


@app.get("/api/sessions")
async def api_sessions(limit: int = 10):
    """Recent sessions, newest first.

    Phase 6 §7: include hitl_mode + hitl_floor when those columns exist
    (older DBs created before HITL settings landed will return None).
    """
    try:
        conn = _open()
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        has_hitl = "hitl_mode" in cols and "hitl_floor" in cols
        if has_hitl:
            rows = conn.execute(
                "SELECT id, project_slug, pid, started_at, ended_at, "
                "hitl_mode, hitl_floor "
                "FROM sessions ORDER BY started_at DESC LIMIT ?",
                (min(limit, 50),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, project_slug, pid, started_at, ended_at "
                "FROM sessions ORDER BY started_at DESC LIMIT ?",
                (min(limit, 50),),
            ).fetchall()
        conn.close()
        out = []
        for r in rows:
            d = dict(r)
            if not has_hitl:
                d["hitl_mode"] = None
                d["hitl_floor"] = None
            out.append(d)
        return out
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


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


def _runtime_settings_payload(extra: dict[str, object] | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "timeout_seconds": float(_hitl_runtime_settings.get("timeout_seconds", _DEFAULT_TIMEOUT_S)),
        "pause_detection_enabled": bool(_hitl_runtime_settings.get("pause_detection_enabled", True)),
    }
    if extra:
        payload.update(extra)
    return payload


def _latest_active_session_id(conn: sqlite3.Connection) -> str | None:
    try:
        row = conn.execute(
            "SELECT id FROM sessions WHERE ended_at IS NULL "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT id FROM sessions ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        return str(row["id"]) if row else None
    except Exception:
        return None


@app.get("/api/hitl/settings")
async def api_hitl_settings(session_id: str | None = None):
    default = {
        "hitl_mode": "async",
        "hitl_floor": 0.60,
    }
    try:
        conn = _open()
        if not session_id:
            session_id = _latest_active_session_id(conn)
        if not session_id:
            conn.close()
            return _runtime_settings_payload(default)
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        if "hitl_mode" not in cols or "hitl_floor" not in cols:
            conn.close()
            out = dict(default)
            out["session_id"] = session_id
            return _runtime_settings_payload(out)
        row = conn.execute(
            "SELECT hitl_mode, hitl_floor FROM sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        conn.close()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if row is None:
        out = dict(default)
        out["session_id"] = session_id
        return _runtime_settings_payload(out)
    return _runtime_settings_payload({
        "session_id": session_id,
        "hitl_mode": str(row["hitl_mode"]) if row["hitl_mode"] else "async",
        "hitl_floor": float(row["hitl_floor"]) if row["hitl_floor"] is not None else 0.60,
    })


@app.post("/api/hitl/settings")
async def api_hitl_settings_update(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json body")
    session_id = body.get("session_id")
    hitl_mode = body.get("hitl_mode")
    hitl_floor = body.get("hitl_floor")
    timeout_seconds = body.get("timeout_seconds")
    pause_detection_enabled = body.get("pause_detection_enabled")

    # Resolve session implicitly if not provided — settings panel doesn't
    # always know the active session id, especially before any decisions
    # have been recorded.
    if not isinstance(session_id, str) or not session_id:
        try:
            conn = _open()
            session_id = _latest_active_session_id(conn)
            conn.close()
        except Exception:
            session_id = None

    # Update runtime-only settings (in-memory; no WAL persistence required).
    if timeout_seconds is not None:
        try:
            t = float(timeout_seconds)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="timeout_seconds must be a number")
        if t < 1.0 or t > 3600.0:
            raise HTTPException(status_code=400, detail="timeout_seconds out of range")
        _hitl_runtime_settings["timeout_seconds"] = t
        # Propagate to the live HitlQueue if one is wired.
        try:
            hq = _get_hitl_queue()
            if hq is not None:
                hq.timeout_seconds = t
        except Exception:
            pass

    if pause_detection_enabled is not None:
        if not isinstance(pause_detection_enabled, bool):
            raise HTTPException(status_code=400, detail="pause_detection_enabled must be bool")
        _hitl_runtime_settings["pause_detection_enabled"] = pause_detection_enabled

    # Update session-scoped HITL mode + floor only when a session is in scope.
    if hitl_mode is not None or hitl_floor is not None:
        if hitl_mode is not None and hitl_mode not in ("sync", "async"):
            raise HTTPException(status_code=400, detail="hitl_mode must be 'sync' or 'async'")
        floor_f: float | None = None
        if hitl_floor is not None:
            try:
                floor_f = float(hitl_floor)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="hitl_floor must be a number")
            if floor_f < 0.0 or floor_f > 1.0:
                raise HTTPException(status_code=400, detail="hitl_floor must be in [0.0, 1.0]")
        if session_id:
            # Read current values to preserve unspecified fields.
            try:
                conn = _open_rw()
                cur = conn.execute(
                    "SELECT hitl_mode, hitl_floor FROM sessions WHERE id=?",
                    (session_id,),
                ).fetchone()
                cur_mode = (str(cur["hitl_mode"]) if cur and cur["hitl_mode"] else "async")
                cur_floor = (float(cur["hitl_floor"]) if cur and cur["hitl_floor"] is not None else 0.60)
                new_mode = hitl_mode if hitl_mode is not None else cur_mode
                new_floor = floor_f if floor_f is not None else cur_floor
                # Prefer the bus-level setter when available so we share
                # the same write path as the governance engine.
                bus = _get_bus()
                if bus is not None:
                    try:
                        bus.set_hitl_mode(session_id, new_mode, new_floor)
                    except Exception:
                        conn.execute(
                            "UPDATE sessions SET hitl_mode=?, hitl_floor=? WHERE id=?",
                            (new_mode, new_floor, session_id),
                        )
                else:
                    conn.execute(
                        "UPDATE sessions SET hitl_mode=?, hitl_floor=? WHERE id=?",
                        (new_mode, new_floor, session_id),
                    )
                conn.close()
            except Exception as exc:
                raise HTTPException(status_code=500, detail=str(exc))

    return {
        "ok": True,
        "session_id": session_id,
        "hitl_mode": hitl_mode,
        "hitl_floor": hitl_floor,
        "timeout_seconds": _hitl_runtime_settings["timeout_seconds"],
        "pause_detection_enabled": _hitl_runtime_settings["pause_detection_enabled"],
    }


def _iso_now() -> str:
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


# ── FR-OG-7 (Phase 5): /api/maturity endpoint ─────────────────────────
#
# A separate, lazily-initialized MaturityReader is held at module scope
# so the dashboard can poll without coupling to the running governance
# engine. Activation is gated on the presence of ``.sm-context.yaml``
# AND a valid ``maturity.artifact_path`` in the governed project root.
# Resolution order for the project root:
#   1. ``SM_PROJECT_ROOT`` env var (explicit override)
#   2. fallback: SM repo root (i.e. ROOT) — yields ``active=False`` in
#      practice because SM itself doesn't ship `.sm-context.yaml`.

_maturity_reader = None  # type: ignore[var-annotated]
_maturity_resolved = False
_maturity_last_sweep_ts: float | None = None


def _get_maturity_reader():
    """Resolve and cache the MaturityReader. Returns None when FR-OG-7
    is dormant for this dashboard (no `.sm-context.yaml` or no artifact).
    """
    global _maturity_reader, _maturity_resolved
    if _maturity_resolved:
        return _maturity_reader
    _maturity_resolved = True
    try:
        from stream_manager.maturity_reader import MaturityReader
        from stream_manager.project_context import (
            get_maturity_artifact_path,
            load_sm_context,
        )

        project_root_env = os.environ.get("SM_PROJECT_ROOT")
        project_root = Path(project_root_env) if project_root_env else ROOT
        ctx = load_sm_context(project_root)
        if ctx is None:
            _maturity_reader = None
            return None
        artifact = get_maturity_artifact_path(ctx, project_root)
        if artifact is None:
            _maturity_reader = None
            return None
        _maturity_reader = MaturityReader(artifact)
    except Exception:
        _maturity_reader = None
    return _maturity_reader


@app.get("/api/maturity")
async def api_maturity():
    """FR-OG-7 ring snapshot for the dashboard panel.

    Returns ``active=False`` when no MaturityReader is wired (gate
    condition); the dashboard hides the ring panel in that case.
    """
    reader = _get_maturity_reader()
    if reader is None:
        return {
            "active": False,
            "percent": 0.0,
            "at_threshold": 0,
            "total": 0,
            "last_delta": None,
            "regressed_cells": [],
            "promoted_cells": [],
            "snapshot_age_seconds": 0.0,
            "last_sweep_timestamp": None,
        }

    delta = None
    try:
        delta = reader.refresh()
    except Exception:
        delta = None

    snap = reader.current_snapshot
    if snap is None:
        # Force a non-debounced read to seed the panel on first hit.
        snap = reader.read()

    # Look up the most recent fr_og7_sweep bus event for the timestamp
    # badge. We reach into the WAL bus directly so this endpoint stays
    # decoupled from any in-process engine instance.
    last_sweep_ts: float | None = None
    try:
        conn = _open()
        row = conn.execute(
            "SELECT timestamp FROM messages WHERE type='fr_og7_sweep' "
            "ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        if row is None:
            # Older code paths emit nothing for fr_og7_sweep — the
            # ALLOW decision itself sources to fr_og7_sweep, so fall
            # back to the latest decision row with that source.
            row = conn.execute(
                "SELECT timestamp FROM decisions WHERE reasoning LIKE "
                "'FR-OG-7: sweep JOB pattern recognized%' "
                "ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
        if row is not None:
            last_sweep_ts = float(row[0])
        conn.close()
    except Exception:
        last_sweep_ts = None

    if snap is None:
        return {
            "active": True,
            "percent": 0.0,
            "at_threshold": 0,
            "total": 0,
            "last_delta": None,
            "regressed_cells": [],
            "promoted_cells": [],
            "snapshot_age_seconds": 0.0,
            "last_sweep_timestamp": last_sweep_ts,
        }

    return {
        "active": True,
        "percent": round(snap.percent, 1),
        "at_threshold": snap.at_threshold,
        "total": snap.total,
        "last_delta": (round(delta.delta, 2) if delta is not None else None),
        "regressed_cells": (delta.regressed_cells if delta is not None else []),
        "promoted_cells": (delta.promoted_cells if delta is not None else []),
        "snapshot_age_seconds": max(0.0, time.time() - snap.timestamp),
        "last_sweep_timestamp": last_sweep_ts,
    }


# ── Phase 6 §1: per-agent mode override endpoint ───────────────────────


@app.post("/api/agents/{agent_id}/override-mode")
async def api_agent_override_mode(agent_id: str, request: Request):
    """Set or clear a per-agent governance mode override.

    Body: ``{"mode": "OBSERVE"|"SUGGEST"|"GUIDE"|"INTERVENE"|"BLOCK"|null,
             "session_id": "..."}``.

    If ``mode`` is null, the override is removed (revert to profile
    default). The map is in-memory (session_id -> agent_id -> mode);
    no WAL persistence in Phase 6.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json body"}, status_code=400)
    mode = body.get("mode")
    session_id = body.get("session_id")
    # Resolve session implicitly when not provided.
    if not isinstance(session_id, str) or not session_id:
        try:
            conn = _open()
            session_id = _latest_active_session_id(conn)
            conn.close()
        except Exception:
            session_id = None
    if not session_id:
        return JSONResponse(
            {"error": "no active session to override"}, status_code=422
        )
    registry = _get_registry()
    if registry is None:
        return JSONResponse(
            {"error": "registry unavailable"}, status_code=503
        )
    # Validation lives in the registry (raises ValueError); surface as 422.
    try:
        registry.set_mode_override(session_id, agent_id, mode)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    return {
        "ok": True,
        "session_id": session_id,
        "agent_id": agent_id,
        "mode": mode,
    }


# ── FR-UI-5: ranked decision-suggestion candidates ────────────────────


def _resolve_sm_context_path() -> Path | None:
    """Resolve the .sm-context.yaml (or .toml) path for weights loading.

    Resolution order:
      1. SM_CONTEXT_PATH env var (explicit override)
      2. SM_PROJECT_ROOT/.sm-context.yaml
      3. SM_PROJECT_ROOT/.sm-context.toml
      4. None (load_weights returns defaults)
    """
    explicit = os.environ.get("SM_CONTEXT_PATH")
    if explicit:
        p = Path(explicit)
        return p if p.exists() else None
    project_root_env = os.environ.get("SM_PROJECT_ROOT")
    project_root = Path(project_root_env) if project_root_env else ROOT
    yaml_p = project_root / ".sm-context.yaml"
    if yaml_p.exists():
        return yaml_p
    toml_p = project_root / ".sm-context.toml"
    if toml_p.exists():
        return toml_p
    return None


@app.get("/api/decisions/{decision_id}/suggestions")
async def api_decision_suggestions(decision_id: str):
    """FR-UI-5: ranked candidate actions for a single decision.

    Returns a JSON array sorted by descending blended score. At least one
    candidate is always present (engine-proposal fallback). Hard-fails to
    HTTP 500 with the validation message when `.sm-context.yaml` weights
    are malformed (per FR-UI-5 contract — no silent default).
    """
    try:
        from stream_manager.decision_suggestions import (
            load_weights,
            rank_candidates,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"import failed: {exc}")

    # Hard-fail validation surfaces here.
    try:
        weights = load_weights(_resolve_sm_context_path())
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"weights load failed: {exc}")

    try:
        conn = _open()
        row = conn.execute(
            "SELECT d.id, d.action, d.confidence, d.matched_hash, "
            "m.content FROM decisions d "
            "JOIN messages m ON d.message_id = m.id WHERE d.id=?",
            (decision_id,),
        ).fetchone()
        if row is None:
            conn.close()
            raise HTTPException(status_code=404, detail="decision not found")
        decision = dict(row)
        project_root_env = os.environ.get("SM_PROJECT_ROOT")
        project_root = Path(project_root_env) if project_root_env else None
        candidates = rank_candidates(
            decision, conn, weights, project_root=project_root
        )
        conn.close()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return [c.to_json() for c in candidates]


# ── FR-HITL: persist hitl_mode promotion + emit bus event ─────────────


@app.post("/api/hitl/mode")
async def api_hitl_mode(request: Request):
    """Persist a HITL mode flip and emit a `hitl_mode_promoted` bus event.

    Body: ``{"session_id": "...", "mode": "off|sync|async",
              "reason": "take_action|user_toggle"}``.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json body")
    session_id = body.get("session_id")
    mode = body.get("mode")
    reason = body.get("reason") or "user_toggle"
    if not isinstance(mode, str) or mode not in ("off", "sync", "async"):
        raise HTTPException(
            status_code=400, detail="mode must be 'off', 'sync', or 'async'"
        )
    if not isinstance(reason, str) or reason not in (
        "take_action", "user_toggle",
    ):
        raise HTTPException(
            status_code=400,
            detail="reason must be 'take_action' or 'user_toggle'",
        )
    if not isinstance(session_id, str) or not session_id:
        try:
            conn = _open()
            session_id = _latest_active_session_id(conn)
            conn.close()
        except Exception:
            session_id = None
    if not session_id:
        raise HTTPException(
            status_code=422, detail="no active session to promote"
        )

    # Read current mode + floor so we can preserve the floor and report the
    # transition in the bus event.
    old_mode: str = "async"
    floor: float = 0.60
    try:
        conn = _open()
        cols = {
            r[1]
            for r in conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        if "hitl_mode" in cols and "hitl_floor" in cols:
            row = conn.execute(
                "SELECT hitl_mode, hitl_floor FROM sessions WHERE id=?",
                (session_id,),
            ).fetchone()
            if row is not None:
                old_mode = (
                    str(row["hitl_mode"]) if row["hitl_mode"] else "async"
                )
                floor = (
                    float(row["hitl_floor"])
                    if row["hitl_floor"] is not None
                    else 0.60
                )
        conn.close()
    except Exception:
        pass

    # Persist via the bus when available; fall back to direct UPDATE.
    bus = _get_bus()
    persisted = False
    if bus is not None:
        try:
            # The bus layer only models sync/async at the schema level;
            # 'off' is allowed via fall-through update so older callers
            # don't break.
            if mode in ("sync", "async"):
                bus.set_hitl_mode(session_id, mode, floor)
                persisted = True
        except Exception:
            log.exception("set_hitl_mode failed; falling back to UPDATE")
    if not persisted:
        try:
            conn = _open_rw()
            conn.execute(
                "UPDATE sessions SET hitl_mode=? WHERE id=?",
                (mode, session_id),
            )
            conn.close()
            persisted = True
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    # Emit bus event so audit replay surfaces the transition.
    if bus is not None:
        try:
            from stream_manager.message_bus import Message
            bus.publish(
                Message.new(
                    session_id=session_id,
                    type="hitl_mode_promoted",
                    direction="internal",
                    content=(
                        f"HITL mode {old_mode} -> {mode} ({reason})"
                    ),
                    metadata={
                        "old_mode": old_mode,
                        "new_mode": mode,
                        "reason": reason,
                    },
                )
            )
        except Exception:
            log.exception("hitl_mode_promoted publish failed")

    return {
        "ok": True,
        "session_id": session_id,
        "old_mode": old_mode,
        "new_mode": mode,
        "reason": reason,
    }


# ── Phase 6 §2: NDJSON decisions export ────────────────────────────────


@app.get("/api/decisions/export")
async def api_decisions_export(session_id: str | None = None):
    """Stream decisions as NDJSON (Content-Type application/x-ndjson).

    Each line is one decision JSON record with fields:
    decision_id, session_id, timestamp, action, confidence, reasoning,
    matched_hash, model_used, layer, agent_profile_slug, trigger_reason.
    """
    try:
        conn = _open()
        has_agents = _has_agents_table(conn)
        has_routing = _has_decision_routing_cols(conn)

        model_expr = "COALESCE(d.model_used, '')" if has_routing else "''"
        layer_expr = "COALESCE(d.layer, 0)" if has_routing else "0"
        if has_agents:
            slug_expr = (
                "(SELECT a.profile_slug FROM agents a "
                "WHERE a.session_id = m.session_id AND a.last_seen <= d.timestamp "
                "ORDER BY a.last_seen DESC LIMIT 1)"
            )
        else:
            slug_expr = "NULL"
        # trigger_reason is on hitl_pending; left-join when the table exists.
        has_hitl = _has_table(conn, "hitl_pending")
        if has_hitl:
            trig_expr = (
                "(SELECT hp.trigger_reason FROM hitl_pending hp "
                "WHERE hp.message_id = d.message_id ORDER BY hp.id DESC LIMIT 1)"
            )
        else:
            trig_expr = "NULL"

        sql = (
            "SELECT d.id AS decision_id, m.session_id AS session_id, "
            "d.timestamp AS timestamp, d.action AS action, "
            "d.confidence AS confidence, d.reasoning AS reasoning, "
            "d.matched_hash AS matched_hash, "
            f"{model_expr} AS model_used, "
            f"{layer_expr} AS layer, "
            f"{slug_expr} AS agent_profile_slug, "
            f"{trig_expr} AS trigger_reason "
            "FROM decisions d JOIN messages m ON d.message_id = m.id "
        )
        params: tuple = ()
        if session_id:
            sql += "WHERE m.session_id = ? "
            params = (session_id,)
        sql += "ORDER BY d.rowid ASC"
        rows = conn.execute(sql, params).fetchall()
        conn.close()
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

    def gen():
        for r in rows:
            yield json.dumps(dict(r), separators=(",", ":")) + "\n"

    import datetime as _dt
    fname = f"sm-decisions-{_dt.datetime.now(_dt.timezone.utc).date().isoformat()}.jsonl"
    return StreamingResponse(
        gen(),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "Cache-Control": "no-cache",
        },
    )


# ── Phase 6 §3/§7: SSE forwards ALL bus event types ────────────────────
# NB: previously filtered to hitl_* + decisions; broaden so the dashboard
# event-log panel can render the full bus stream.
_HITL_EVENT_TYPES = ("hitl_sync_queued", "hitl_async_flagged", "hitl_timeout")


def _parse_last_event_id(raw: str | None) -> tuple[int | None, int | None]:
    """Parse compound SSE Last-Event-ID of form ``d{drid}:m{mrid}``.

    Returns (decisions_rid, messages_rid) or (None, None) if absent/malformed.
    On fresh connect (no header) the caller seeds 25 recent decisions; on
    resume both cursors are honoured and the seed is skipped (FR-UI-8).
    """
    if not raw:
        return None, None
    try:
        d_part, m_part = raw.split(":", 1)
        if not (d_part.startswith("d") and m_part.startswith("m")):
            return None, None
        return int(d_part[1:]), int(m_part[1:])
    except Exception:
        return None, None


@app.get("/events")
async def sse_events(request: Request):
    """SSE stream: one JSON event per new decision row, 500ms poll.

    FR-UI-8: emits ``id: d{drid}:m{mrid}`` on every event so the browser
    resumes from the last seen cursor via ``Last-Event-ID`` after reconnect.
    """

    resume_drid, resume_mrid = _parse_last_event_id(
        request.headers.get("last-event-id")
    )

    async def generate():
        try:
            conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            return

        if resume_drid is not None and resume_mrid is not None:
            # Resume path: skip seed, replay strictly newer rows from cursor.
            last_rid = resume_drid
            last_msg_rid = resume_mrid
        else:
            # Fresh connect: seed last 25 decisions (oldest→newest) and snap
            # the messages cursor to current max so we don't ship history.
            try:
                seed = conn.execute(_seed_sql(conn), (25,)).fetchall()
                last_rid = seed[0]["rid"] if seed else 0
                for row in reversed(seed):
                    payload = dict(row)
                    last_rid_seed = payload["rid"]
                    yield (
                        f"id: d{last_rid_seed}:m0\n"
                        f"data: {json.dumps(payload)}\n\n"
                    )
            except Exception:
                last_rid = 0
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
                    yield (
                        f"id: d{last_rid}:m{last_msg_rid}\n"
                        f"data: {json.dumps(dict(row))}\n\n"
                    )
            except Exception:
                pass
            # Phase 6 §3/§7: forward ALL bus event types (not just HITL)
            # so the dashboard event-log panel can render the full
            # stream. Bus events use direction='internal' (user content
            # uses 'inbound'); skip inbound rows so we don't duplicate
            # the decisions feed and don't ship raw user input.
            try:
                msg_rows = conn.execute(
                    "SELECT rowid AS rid, id, session_id, type, content, "
                    "metadata, timestamp, direction FROM messages "
                    "WHERE rowid > ? AND direction != 'inbound' "
                    "ORDER BY rowid ASC",
                    (last_msg_rid,),
                ).fetchall()
                for hr in msg_rows:
                    last_msg_rid = hr["rid"]
                    payload = dict(hr)
                    payload["event_type"] = payload.pop("type")
                    yield (
                        f"id: d{last_rid}:m{last_msg_rid}\n"
                        f"data: {json.dumps(payload)}\n\n"
                    )
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
