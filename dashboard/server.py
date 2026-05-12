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
import secrets
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
# v10 P4 B': rl.bus_subscriber close-fn captured by _get_bus() so the
# WAL handle on rl_episodes.db releases on dashboard shutdown. Stays
# None when BRIDGE_RL_LOGGER_ENABLED is unset (attach() returns the
# module-level _noop_close, which we also accept). Set once per process
# alongside _bus.
_rl_logger_close = None  # type: ignore[var-annotated]
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
# Task B: per-session governance engine registry. Lazily constructed; the
# dashboard process itself does not run engines today, but the registry
# is exposed via /api/registry/active so operators (and future SM
# components) can see which session_ids have hot engines in this process.
_engine_registry = None  # type: ignore[var-annotated]
# Task J / v1.1: warm-pool of long-lived `claude` workers, shared across
# every CliGovernor / engine constructed in this dashboard process. Built
# lazily by `_get_cli_pool()`; size controlled by SM_CLI_POOL_SIZE (default
# 2). Disabled entirely when SM_CLI_POOL_SIZE=0 or when the `claude` CLI is
# not on PATH (the spawn-per-call legacy path remains the fallback).
_cli_pool = None  # type: ignore[var-annotated]
_cli_pool_init_lock: object = None  # populated lazily inside _get_cli_pool


def _get_bus():
    """Return a lazily-initialized shared MessageBus instance."""
    global _bus, _rl_logger_close
    if _bus is None:
        try:
            from stream_manager.message_bus import MessageBus
            _bus = MessageBus(str(DB_PATH))
            # v10 P4 B': opt-in subscribe rl_episodes.db to live
            # governance_decision envelopes. No-op when
            # BRIDGE_RL_LOGGER_ENABLED unset (ADR-5 §"v10 logging
            # overhead" zero-cost default). The dashboard is the
            # canonical long-lived attach point; the per-hook process
            # also attaches via tools/hook_evaluate.py. The close-fn is
            # captured into module scope so _shutdown_cli_pool_event
            # can release the WAL handle on graceful shutdown.
            try:
                from rl.bus_subscriber import attach as _rl_attach
                _rl_db = os.environ.get("BRIDGE_RL_EPISODES_DB", "rl_episodes.db")
                _rl_logger_close = _rl_attach(_bus, _rl_db)
            except Exception:
                log.exception("rl bus_subscriber attach failed; dashboard continues")
                _rl_logger_close = None
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


def _get_engine_registry():
    """Return a lazily-initialized per-session GovernanceEngine registry.

    The dashboard process does not run engines itself, but the registry
    is the canonical place for any future in-process consumer to obtain
    per-session engines, and `/api/registry/active` exposes it for
    operator visibility. Returns None on import/load failure.
    """
    global _engine_registry
    if _engine_registry is None:
        try:
            from stream_manager.governance import EngineRegistry
            from stream_manager.project_context import load as load_project
            _engine_registry = EngineRegistry(
                bus=_get_bus(),
                project_context=load_project(ROOT),
                agent_registry=_get_registry(),
                cli_pool=_get_cli_pool(),
            )
        except Exception:
            _engine_registry = None
    return _engine_registry


def _get_cli_pool():
    """Return a lazily-initialized warm-pool of `claude` CLI workers.

    Task J / v1.1. Returns None when:
      * SM_CLI_POOL_SIZE=0 (operator opt-out)
      * `claude` CLI is not on PATH (legacy spawn-per-call path still works
        when BRIDGE_API_GOV is set; the pool would just fail at spawn)
      * cli_pool import / spawn fails (degrade silently — governance still
        runs via the per-call path)
    """
    global _cli_pool
    if _cli_pool is not None:
        return _cli_pool
    try:
        size_raw = os.environ.get("SM_CLI_POOL_SIZE", "2")
        size = int(size_raw)
    except ValueError:
        size = 2
    if size <= 0:
        return None
    try:
        from stream_manager.cli_pool import CliPool, cli_on_path, reap_stale_workers
    except Exception:
        log.exception("cli_pool: import failed; pool disabled")
        return None
    if not cli_on_path():
        log.info("cli_pool: `claude` CLI not on PATH; pool disabled")
        return None
    try:
        # Reap any stale workers from a prior crashed run before opening
        # a fresh pool. Idempotent and safe on a clean boot.
        reaped = reap_stale_workers(root=ROOT)
        if reaped:
            log.warning("cli_pool: reaped %d stale worker(s) at startup", reaped)
        _cli_pool = CliPool(size=size, pid_root=ROOT)
        # warmup() spawns up front; if the model rejects the args we want
        # to know now rather than on first governance call.
        _cli_pool.warmup()
        log.info("cli_pool: warmup complete (size=%d)", size)
    except Exception:
        log.exception("cli_pool: warmup failed; pool disabled")
        _cli_pool = None
    return _cli_pool


def _shutdown_cli_pool() -> None:
    """Kill every worker. Idempotent; safe to call from atexit + signal."""
    global _cli_pool
    if _cli_pool is None:
        return
    try:
        _cli_pool.shutdown()
    except Exception:
        log.exception("cli_pool: shutdown raised; ignoring")
    _cli_pool = None


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


# ── Task J / v1.1: CLI warm-pool lifecycle ──────────────────────────────
# Pool is built at FastAPI startup (so the cold-start cost is paid before
# the first governance call hits) and torn down on shutdown + atexit +
# SIGTERM/SIGINT. Multi-layered shutdown protects against operator-issued
# Ctrl-C, parent-process kill, and clean uvicorn stop.

@app.on_event("startup")
async def _startup_cli_pool() -> None:
    # Best-effort. Failure to warm the pool must never prevent the
    # dashboard from starting; the per-call CLI path remains as fallback.
    try:
        _get_cli_pool()
    except Exception:
        log.exception("cli_pool: startup warmup raised; continuing")
    # Task M (v1.1): wire EngineRegistry.start_refresh() so cross-session
    # pattern flips made via the operator UI propagate to hot engines on
    # the chained 60s tick. Best-effort: a missing registry must not
    # block startup.
    try:
        reg = _get_engine_registry()
        if reg is not None:
            reg.start_refresh()
    except Exception:
        log.exception("registry: start_refresh raised; continuing")
    # v1.9 P2: external session watcher. Read-only observation of
    # `~/.claude/sessions/` and bg-task tokens. Daemon thread; idempotent.
    # Best-effort — failure must never block dashboard startup.
    try:
        from stream_manager.session_watcher import start_session_watcher
        bus = _get_bus()
        if bus is not None:
            start_session_watcher(bus)
    except Exception:
        log.exception("session_watcher: startup raised; continuing")


@app.on_event("shutdown")
async def _shutdown_cli_pool_event() -> None:
    # Task M (v1.1): stop the EngineRegistry refresh timer first so the
    # daemon Timer is joined deterministically before the pool tears down.
    try:
        reg = _get_engine_registry()
        if reg is not None:
            reg.stop_refresh()
    except Exception:
        log.exception("registry: stop_refresh raised; continuing")
    # v1.9 P2: stop the session watcher (daemon thread; 1s join).
    try:
        from stream_manager.session_watcher import stop_session_watcher
        stop_session_watcher()
    except Exception:
        log.exception("session_watcher: shutdown raised; continuing")
    # v10 P4 B': release rl.bus_subscriber's EpisodeLogger WAL handle on
    # rl_episodes.db. Idempotent no-op when env was unset (_rl_logger_close
    # stays None). Run before _shutdown_cli_pool() so any final
    # governance_decision envelopes from in-flight cli_pool workers can
    # land in rl_episodes.db before its conn closes.
    global _rl_logger_close
    if _rl_logger_close is not None:
        try:
            _rl_logger_close()
        except Exception:
            log.exception("rl bus_subscriber close failed; continuing")
        _rl_logger_close = None
    _shutdown_cli_pool()


def _install_pool_signal_handlers() -> None:
    import atexit
    import signal

    atexit.register(_shutdown_cli_pool)

    def _handler(signum, frame):  # pragma: no cover - signal path
        _shutdown_cli_pool()
        # Re-raise default behaviour: exit non-zero on terminal signals.
        # We avoid sys.exit so uvicorn's own signal handling can finish
        # tearing down the loop.

    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            existing = signal.getsignal(sig)
            def _chained(signum, frame, _existing=existing):  # pragma: no cover
                try:
                    _shutdown_cli_pool()
                finally:
                    if callable(_existing) and _existing not in (signal.SIG_DFL, signal.SIG_IGN):
                        _existing(signum, frame)
            signal.signal(sig, _chained)
        except (ValueError, OSError):
            # ValueError: signal only works in main thread (uvicorn worker).
            # OSError: signal not supported on this platform.
            pass


_install_pool_signal_handlers()

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
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    # Task C: inject SM_OWN_SESSION_ID meta tag so the Mirror frame can
    # filter the SM's own session_id client-side as a defence-in-depth
    # layer (the SSE handler already strips these rows server-side).
    sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
    if sm_own:
        # Escape HTML special chars in the env value.
        sm_own_safe = (
            sm_own.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;")
        )
        meta = f'<meta name="sm-own-session-id" content="{sm_own_safe}">'
        html = html.replace("</head>", f"  {meta}\n</head>", 1)
    return html


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


@app.get("/api/registry/active")
async def api_registry_active():
    """Return the list of session_ids with a hot in-process engine.

    Task B: surfaces the per-session engine registry for operator
    visibility. The dashboard process today does not host engines, so
    on a fresh boot this list is empty; future in-process engine hosts
    (soak driver, SM daemon) will populate it.
    """
    reg = _get_engine_registry()
    if reg is None:
        return {
            "active_session_ids": [],
            "count": 0,
            "refresh_active": False,
            "last_refresh_ts": None,
        }
    ids = reg.active_session_ids()
    status = reg.refresh_status()
    return {
        "active_session_ids": ids,
        "count": len(ids),
        "refresh_active": status["refresh_active"],
        "last_refresh_ts": status["last_refresh_ts"],
    }


@app.get("/api/lifecycle/jobs")
async def api_lifecycle_jobs(session_id: str | None = None, limit: int = 100):
    """Active BG jobs + spawned subagents (Task C / v1.2 lifecycle bridge).

    Read-only view over WAL ``messages`` rows authored by
    ``stream_manager.lifecycle_bridge``. Returns rows whose latest
    envelope is a ``*_start`` (no matching ``*_end`` / ``*_done``
    observed yet), newest-start first.

    If a ``session_id`` query param is provided, scope to that session
    (pairs with the Task B session selector). Otherwise return all open
    jobs/agents across sessions.
    """
    try:
        from stream_manager.lifecycle_bridge import list_active_jobs
        rows = list_active_jobs(
            db_path=str(DB_PATH),
            session_id=session_id,
            limit=min(int(limit or 100), 500),
        )
        return {"jobs": rows, "count": len(rows)}
    except Exception:  # pragma: no cover - defensive
        # Detail goes to the server log, not the response body, so we
        # don't leak internal paths / SQL fragments / stack hints to any
        # caller of the dashboard.
        log.exception("lifecycle/jobs: query failed")
        return JSONResponse(
            {"error": "internal error", "jobs": [], "count": 0},
            status_code=500,
        )


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


# ── v1.9 P2: external session watcher dashboard endpoints ───────────


@app.get("/api/sessions/external")
async def api_external_sessions():
    """Snapshot of external claude -p sessions discovered by the watcher.

    Read-only mirror of ``SessionWatcher.list_active_sessions``. Empty
    list when the watcher is not running (no error — the dashboard panel
    just renders empty).
    """
    try:
        from stream_manager.session_watcher import get_session_watcher
        watcher = get_session_watcher()
        if watcher is None:
            return {"sessions": [], "count": 0}
        sessions = watcher.list_active_sessions()
        return {"sessions": sessions, "count": len(sessions)}
    except Exception:
        log.exception("session_watcher: external sessions endpoint failed")
        return JSONResponse(
            {"sessions": [], "count": 0, "error": "internal error"},
            status_code=500,
        )


@app.get("/api/sessions/bg-tasks")
async def api_bg_tasks():
    """Snapshot of pending background-task tokens tracked by the watcher.

    Read-only mirror of ``SessionWatcher.list_pending_bg_tasks``. Empty
    list when the watcher is not running.
    """
    try:
        from stream_manager.session_watcher import get_session_watcher
        watcher = get_session_watcher()
        if watcher is None:
            return {"tasks": [], "count": 0}
        tasks = watcher.list_pending_bg_tasks()
        return {"tasks": tasks, "count": len(tasks)}
    except Exception:
        log.exception("session_watcher: bg tasks endpoint failed")
        return JSONResponse(
            {"tasks": [], "count": 0, "error": "internal error"},
            status_code=500,
        )


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


def _decode_bias_hint(raw: object) -> dict | None:
    """Decode the JSON-encoded ``hitl_pending.bias_hint`` column for
    dashboard consumption.

    The writer side (`stream_manager.hitl._encode_bias_hint`) stores a
    minimal Learn Mode advisory shape: category, confidence,
    ladder_step_suggestion, pattern_id, last_reinforced_ts. The column
    is the empty string when no hint was attached at queueing time.

    Returns None for empty / malformed payloads so the client can omit
    the advisory block entirely (v1.3 C10).
    """
    if not raw or not isinstance(raw, str):
        return None
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    category = payload.get("category")
    if not category:
        return None
    out: dict[str, object] = {"category": str(category)}
    if "confidence" in payload:
        try:
            out["confidence"] = float(payload["confidence"])
        except Exception:
            pass
    if "ladder_step_suggestion" in payload:
        try:
            out["ladder_step_suggestion"] = int(payload["ladder_step_suggestion"])
        except Exception:
            pass
    if "pattern_id" in payload:
        try:
            out["pattern_id"] = int(payload["pattern_id"])
        except Exception:
            pass
    if "last_reinforced_ts" in payload:
        try:
            out["last_reinforced_ts"] = float(payload["last_reinforced_ts"])
        except Exception:
            pass
    return out


@app.get("/api/hitl/pending")
async def api_hitl_pending(session_id: str | None = None):
    """Return unresolved hitl_pending rows. If session_id is omitted,
    return unresolved rows across all sessions.

    v1.3 C10: the ``bias_hint`` column (JSON-encoded Learn Mode
    advisory, written by ``HitlQueue.route``) is projected and decoded
    server-side so the dashboard can pre-fill the operator prompt with
    the suggested category. Rows without a hint surface ``bias_hint:
    None``.
    """
    try:
        conn = _open()
        if not _has_table(conn, "hitl_pending"):
            conn.close()
            return []
        if session_id:
            rows = conn.execute(
                "SELECT hp.id, hp.message_id, hp.proposed_action, "
                "hp.proposed_confidence, hp.trigger_reason, hp.queued_at, "
                "hp.bias_hint, m.session_id, m.content "
                "FROM hitl_pending hp JOIN messages m ON hp.message_id=m.id "
                "WHERE hp.resolved_at IS NULL AND m.session_id=? "
                "ORDER BY hp.id ASC",
                (session_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT hp.id, hp.message_id, hp.proposed_action, "
                "hp.proposed_confidence, hp.trigger_reason, hp.queued_at, "
                "hp.bias_hint, m.session_id, m.content "
                "FROM hitl_pending hp JOIN messages m ON hp.message_id=m.id "
                "WHERE hp.resolved_at IS NULL ORDER BY hp.id ASC"
            ).fetchall()
        conn.close()
        out: list[dict] = []
        for r in rows:
            d = dict(r)
            d["bias_hint"] = _decode_bias_hint(d.get("bias_hint"))
            out.append(d)
        return out
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
    # Task F: dispatch resolution side-effects (cross_session flag).
    try:
        bus = _get_bus()
        if bus is not None:
            from stream_manager.hitl import dispatch_resolution
            dispatch_resolution(bus, pending_id, resolution)
    except Exception:
        log.exception("api_hitl_resolve: dispatch failed")
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


# ── v2.1 P1 (FR-PPP) — Provenance Probe Protocol endpoints ───────────


@app.get("/api/sm-probe")
async def api_sm_probe(session_id: str, force: int = 0):
    """Emit `audit.probe` for ``session_id`` (FR-PPP-1).

    ``force=1`` required (operator-initiated; prevents accidental
    storms). 503 branch (issue #128 §A2) fires on
    ``delivered_count == 0`` from ``emit_audit_probe`` and resolves the
    queued HITL row ``no_subscriber``. Branching on the return value
    avoids the TOCTOU race vs ``envelope_subscriber_count`` pre-check.
    """
    if force != 1:
        raise HTTPException(
            status_code=400, detail="force=1 required (operator-initiated)"
        )
    _reject_sm_own(session_id)

    bus = _get_bus()
    if bus is None:
        raise HTTPException(status_code=500, detail="bus unavailable")

    from stream_manager.session_watcher import get_session_watcher
    watcher = get_session_watcher()
    if watcher is None:
        raise HTTPException(status_code=503, detail="session watcher inactive")
    # v2.1 P3 hard guard: sm_brain_id is mandatory; missing env var ⇒
    # raise at the endpoint with HTTP 500 (the watcher would also raise,
    # but the endpoint-side check produces the more-specific error body).
    sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
    if not sm_own:
        raise HTTPException(
            status_code=500,
            detail="SM_OWN_SESSION_ID required for audit probe",
        )
    candidates = watcher.build_audit_probe_candidates(sm_brain_id=sm_own)
    if not candidates:
        raise HTTPException(status_code=400, detail="no candidate streams")

    reg = _get_engine_registry()
    if reg is None:
        raise HTTPException(status_code=500, detail="engine registry unavailable")
    try:
        engine = reg.get_or_create(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        probe_id, hitl_id, delivered = engine.emit_audit_probe(candidates)
    except Exception as exc:
        log.exception("api_sm_probe: emit_audit_probe failed")
        raise HTTPException(status_code=500, detail=str(exc))

    if delivered == 0:
        try:
            bus.resolve_hitl(hitl_id, "no_subscriber")
        except Exception:
            log.exception("api_sm_probe: resolve_hitl(no_subscriber) failed")
        return JSONResponse(
            status_code=503,
            content={
                "error": "no envelope subscribers",
                "probe_id": probe_id,
                "hitl_id": hitl_id,
                "delivered": 0,
            },
        )

    return {
        "probe_id": probe_id,
        "hitl_id": hitl_id,
        "delivered": delivered,
        "candidate_count": len(candidates),
    }


@app.post("/api/sm-probe/ack")
async def api_sm_probe_ack(request: Request):
    """Operator ack for an audit_probe HITL row (FR-PPP-1).

    Body: {probe_id, hitl_id, session_id, selected_jsonl_path|null,
    ttl_seconds?}. ``selected_jsonl_path is None`` = "none of the
    above"; row still lands in ``provenance_assertions`` with
    ``jsonl_path=NULL`` for P2 negative-control. HMAC seam reuses
    ``desktop_commands.sign`` (issue #128 §A1).
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json body")
    probe_id = body.get("probe_id")
    hitl_id = body.get("hitl_id")
    session_id = body.get("session_id")
    selected = body.get("selected_jsonl_path")
    # v2.1 P1a (R14): brain_id + prompt_hash flow from the selected
    # candidate row in the probe envelope (browser passes them through).
    # Both null when operator picks "none of the above".
    brain_id = body.get("brain_id")
    prompt_hash = body.get("prompt_hash")
    ttl_seconds = int(body.get("ttl_seconds") or 1800)
    if not isinstance(probe_id, str) or not probe_id:
        raise HTTPException(status_code=400, detail="probe_id required")
    if not isinstance(hitl_id, int):
        raise HTTPException(status_code=400, detail="hitl_id must be int")
    if not isinstance(session_id, str) or not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    if selected is not None and not isinstance(selected, str):
        raise HTTPException(status_code=400, detail="selected_jsonl_path must be string or null")
    if brain_id is not None and not isinstance(brain_id, str):
        raise HTTPException(status_code=400, detail="brain_id must be string or null")
    if prompt_hash is not None and not isinstance(prompt_hash, str):
        raise HTTPException(status_code=400, detail="prompt_hash must be string or null")
    # FR-PPP-2: empty-string == "none of the above"; coerce to None so
    # provenance_assertions.jsonl_path stores SQL NULL, not "".
    selected = selected or None
    # Same coercion for brain_id + prompt_hash so the WAL row stores
    # NULL (not empty string) when the operator picked "none".
    brain_id = brain_id or None
    prompt_hash = prompt_hash or None

    bus = _get_bus()
    if bus is None:
        raise HTTPException(status_code=500, detail="bus unavailable")

    from stream_manager import desktop_commands as _dc
    from stream_manager.message_bus import AuditProbeAckEnvelope
    signed_at = time.time()
    expires_at = signed_at + ttl_seconds
    # v2.1 P1a (R14): sig_v=2 binds brain_id + prompt_hash into the sig
    # so a P2 canary-echo verifier can detect candidate-row tampering.
    # Pre-P1a v1 rows still validate under the v1 schema (see
    # `AuditProbeAckEnvelope.signing_payload` sig_v branch).
    ack = AuditProbeAckEnvelope(
        probe_id=probe_id, selected_jsonl_path=selected,
        signed_at=signed_at, expires_at=expires_at, hmac_sig="",
        brain_id=brain_id, prompt_hash=prompt_hash, sig_v=2,
    )
    hmac_sig = _dc.sign(ack.signing_payload())
    ack.hmac_sig = hmac_sig

    written = bus.write_provenance_assertion(
        probe_id=probe_id,
        session_id=session_id,
        jsonl_path=selected,
        brain_id=brain_id,
        prompt_hash=prompt_hash,
        signed_at=signed_at,
        expires_at=expires_at,
        hmac_sig=hmac_sig,
    )
    if not written:
        raise HTTPException(status_code=409, detail="probe_id replay")

    try:
        resolution = "approved" if selected else "overridden:none"
        bus.resolve_hitl(hitl_id, resolution)
    except Exception:
        log.exception("api_sm_probe_ack: resolve_hitl failed")

    try:
        bus.write_envelope("audit.probe_ack", ack.to_dict())
    except Exception:
        log.exception("api_sm_probe_ack: write_envelope failed")

    # v2.1 P2: auto-emit Layer-2 canary on ack-success path. Skipped on
    # "none of the above" (`selected is None`) since there is no JSONL
    # to bind. Failures are swallowed — ack success MUST NOT be rolled
    # back by canary emit failure (the assertion row is already on
    # disk; canary is best-effort).
    canary_nonce: str | None = None
    canary_timeout_s: int | None = None
    canary_delivered: int | None = None
    if selected:
        try:
            reg = _get_engine_registry()
            if reg is not None:
                engine = reg.get_or_create(session_id)
                canary_nonce, _env, canary_delivered = (
                    engine.emit_audit_canary(
                        probe_id=probe_id,
                        jsonl_path=selected,
                    )
                )
                canary_timeout_s = 10
                # Register on the per-process JsonlTailWorker so the
                # observer can match the nonce in the user's claimed
                # JSONL. Without this call the canary envelope fires
                # but the registry stays empty → every canary times out
                # → wired-but-dormant lifecycle.
                from stream_manager import jsonl_tail as _jt
                worker = _jt.get_active_worker()
                if worker is not None and canary_nonce is not None:
                    worker.register_canary(
                        probe_id=probe_id,
                        nonce=canary_nonce,
                        target_jsonl_path=selected,
                        timeout_s=float(canary_timeout_s),
                    )
                else:
                    # Surface DORMANT-observer state rather than silently
                    # accepting a timeout-bound canary. The envelope still
                    # fired (SSE subscribers see it), but the observer is
                    # not running so this canary WILL time out.
                    log.warning(
                        "api_sm_probe_ack: canary emitted but no active "
                        "tail worker; observer dormant (probe_id=%s)",
                        probe_id,
                    )
                if canary_delivered == 0:
                    log.warning(
                        "api_sm_probe_ack: canary delivered=0 (no SSE "
                        "subscribers) for probe_id=%s",
                        probe_id,
                    )
        except Exception:
            log.exception("api_sm_probe_ack: emit_audit_canary failed")

    return {
        "ok": True,
        "probe_id": probe_id,
        "written": True,
        "sig_v": 2,
        "canary_nonce": canary_nonce,
        "canary_timeout_s": canary_timeout_s,
        "canary_delivered": canary_delivered,
    }


# v2.1 P2 (FR-PPP) — explicit canary emit (operator-triggered or
# cassette/test deterministic path). The auto-emit hook on
# /api/sm-probe/ack already fires the canary on the UX happy path; this
# endpoint exists for re-emit + cassette determinism.
@app.post("/api/sm-canary/emit")
async def api_sm_canary_emit(request: Request):
    """Emit `audit.canary_emit` for an existing provenance assertion.

    Body: ``{probe_id, timeout_s?}``. Looks up the assertion row to
    recover ``session_id`` + ``jsonl_path``; rejects when the assertion
    is unknown / expired / has ``jsonl_path IS NULL`` (operator picked
    "none of the above" — nothing to bind).
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json body")
    probe_id = body.get("probe_id")
    timeout_s = int(body.get("timeout_s") or 10)
    if not isinstance(probe_id, str) or not probe_id:
        raise HTTPException(status_code=400, detail="probe_id required")

    bus = _get_bus()
    if bus is None:
        raise HTTPException(status_code=500, detail="bus unavailable")

    # Look up the assertion row. P2 reads via direct WAL query — the
    # bus exposes `get_active_provenance_assertion(session_id)` but the
    # caller of this endpoint knows only `probe_id`, not `session_id`.
    try:
        row = bus._conn.execute(  # noqa: SLF001 — read-only WAL probe
            "SELECT session_id, jsonl_path, expires_at "
            "FROM provenance_assertions WHERE probe_id=?",
            (probe_id,),
        ).fetchone()
    except Exception as exc:
        log.exception("api_sm_canary_emit: WAL lookup failed")
        raise HTTPException(status_code=500, detail=str(exc))
    if row is None:
        raise HTTPException(status_code=404, detail="probe_id unknown")
    session_id, jsonl_path, expires_at = row[0], row[1], float(row[2])
    if not jsonl_path:
        raise HTTPException(
            status_code=400,
            detail="assertion has no jsonl_path (none-of-the-above)",
        )
    if expires_at <= time.time():
        raise HTTPException(status_code=410, detail="assertion expired")

    reg = _get_engine_registry()
    if reg is None:
        raise HTTPException(status_code=500, detail="engine registry unavailable")
    try:
        engine = reg.get_or_create(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        nonce, _env, delivered = engine.emit_audit_canary(
            probe_id=probe_id,
            jsonl_path=jsonl_path,
            timeout_s=timeout_s,
        )
    except Exception as exc:
        log.exception("api_sm_canary_emit: emit_audit_canary failed")
        raise HTTPException(status_code=500, detail=str(exc))

    if delivered == 0:
        return JSONResponse(
            status_code=503,
            content={
                "error": "no envelope subscribers",
                "probe_id": probe_id,
                "delivered": 0,
            },
        )

    # Register on the per-process JsonlTailWorker (peer to the
    # auto-emit hook on /api/sm-probe/ack). When no worker is active
    # the observer is dormant and this canary will time out; surface
    # that as a `observer_dormant` flag in the response so the cassette
    # / soak driver can distinguish "wired" from "wired + observed".
    from stream_manager import jsonl_tail as _jt
    worker = _jt.get_active_worker()
    observer_dormant = False
    if worker is not None:
        worker.register_canary(
            probe_id=probe_id,
            nonce=nonce,
            target_jsonl_path=jsonl_path,
            timeout_s=float(timeout_s),
        )
    else:
        observer_dormant = True
        log.warning(
            "api_sm_canary_emit: no active tail worker; observer "
            "dormant (probe_id=%s)",
            probe_id,
        )

    return {
        "probe_id": probe_id,
        "nonce": nonce,
        "timeout_s": timeout_s,
        "delivered": delivered,
        "observer_dormant": observer_dormant,
    }


# v2.1 P3 (FR-PPP) — Layer 3 negative-control decoy registration.
# Operator-triggered (or auto-fired at SM boot) registration of a
# synthetic JSONL path that is never written. Subsequent parser reports
# on this path fire `audit.hallucination_detected` via the M4 hook in
# `jsonl_tail._check_decoy_hallucination`. The path SHAPE convention
# (sentinel slug + fresh uuid) matches the phase-3 prompt §1.
@app.post("/api/sm-decoy/register")
async def api_sm_decoy_register(request: Request):
    """Register a synthetic decoy JSONL path. Returns the registration
    row metadata (probe_id, jsonl_path, hmac_sig) per FR-PPP-12.

    Body: optional `{jsonl_path}`. When omitted, the endpoint generates
    a fresh path under `~/.claude/projects/sm-decoy-control/<uuid>.jsonl`
    per the phase-3 prompt §1 path-shape convention. Re-register on the
    same path is idempotent at the WAL UNIQUE-constraint level (returns
    `first_write=false` in the response body).
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    jsonl_path = body.get("jsonl_path") if isinstance(body, dict) else None
    if not jsonl_path:
        # Generate a fresh decoy path under the sentinel slug.
        decoy_uuid = secrets.token_hex(16)
        jsonl_path = str(
            Path.home() / ".claude" / "projects"
            / "sm-decoy-control" / f"{decoy_uuid}.jsonl"
        )
    if not isinstance(jsonl_path, str) or not jsonl_path:
        raise HTTPException(
            status_code=400, detail="jsonl_path must be a non-empty string"
        )

    bus = _get_bus()
    if bus is None:
        raise HTTPException(status_code=500, detail="bus unavailable")
    reg = _get_engine_registry()
    if reg is None:
        raise HTTPException(
            status_code=500, detail="engine registry unavailable"
        )
    # Pick any engine — register_decoy_stream is bus-scoped, not session-
    # scoped (the decoy is a process-wide synthetic path). Reuse a known
    # session id if present; fall back to a sentinel session id.
    sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip() or "sm-decoy"
    try:
        engine = reg.get_or_create(sm_own)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        probe_id, registration, first_write = engine.register_decoy_stream(
            jsonl_path=jsonl_path,
        )
    except Exception as exc:
        log.exception("api_sm_decoy_register: register_decoy_stream failed")
        raise HTTPException(status_code=500, detail=str(exc))
    return {
        "probe_id": probe_id,
        "jsonl_path": registration["jsonl_path"],
        "registered_at": registration["registered_at"],
        "hmac_sig": registration["hmac_sig"],
        "first_write": first_write,
    }


# ── Task F: cross-session pattern endpoints ──────────────────────────


@app.get("/api/patterns/cross_session")
async def api_patterns_cross_session():
    """Return all patterns currently flagged cross_session=1."""
    try:
        conn = _open()
        if not _has_table(conn, "patterns"):
            conn.close()
            return []
        cols = {
            row[1] for row in conn.execute("PRAGMA table_info(patterns)").fetchall()
        }
        if "cross_session" not in cols:
            conn.close()
            return []
        rows = conn.execute(
            "SELECT hash, level, occurrences, success_rate, last_seen, payload "
            "FROM patterns WHERE cross_session=1 ORDER BY last_seen DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/patterns/{hash}/demote")
async def api_patterns_demote(hash: str):
    """Set patterns.cross_session=0 for the given hash. 404 if not found."""
    try:
        bus = _get_bus()
        if bus is None:
            raise HTTPException(status_code=503, detail="bus unavailable")
        existed = bus.unflag_pattern_cross_session(hash)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if not existed:
        raise HTTPException(status_code=404, detail="pattern not found")
    return {"hash": hash, "cross_session": 0}


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


# ── v1.4: Learn Mode runtime toggle (slide button) ───────────────────
#
# Dashboard surface for flipping the Learn Mode categorizer worker
# on/off at runtime without bouncing the host. Persists to
# ``learn_categorizer_state(key='runtime_enabled')`` via the bus
# helper so the toggle survives a restart. The worker reads the flag
# at the top of every ``tick()`` (default poll interval 5 s), so
# round-trip toggle latency is bounded by that interval.
#
# Boot-time gate (``SM_LEARN_MODE`` env var) is unchanged — a fresh
# host process still requires explicit opt-in before the worker
# spawns. The runtime toggle only flips the active state of an
# already-running worker.

@app.get("/api/learn-mode/state")
async def api_learn_mode_state():
    """Return the runtime + boot-time Learn Mode enable flags.

    ``runtime_enabled``: persisted to the bus; the value the worker
    consults on each tick.

    ``env_enabled``: the boot-time ``SM_LEARN_MODE`` env-var read.
    Surfaced so the dashboard can warn the operator that the worker
    will not auto-start on host restart unless the env var is also
    set.
    """
    from stream_manager.learn_categorizer import (  # noqa: WPS433
        get_runtime_enabled,
        is_enabled as _env_enabled,
    )
    bus = _get_bus()
    if bus is None:
        # No bus wired (e.g. a unit-test client without WAL init);
        # fall back to env-only and report runtime as None.
        return {
            "runtime_enabled": None,
            "env_enabled": _env_enabled(),
            "bus_available": False,
        }
    try:
        runtime = bool(get_runtime_enabled(bus))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {
        "runtime_enabled": runtime,
        "env_enabled": _env_enabled(),
        "bus_available": True,
    }


@app.post("/api/learn-mode/state")
async def api_learn_mode_state_update(request: Request):
    """Flip the runtime Learn Mode enable flag.

    Body: ``{"enabled": true|false}``. Returns the same shape as the
    GET endpoint after the write.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json body")
    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(
            status_code=400, detail="enabled must be a JSON boolean"
        )
    from stream_manager.learn_categorizer import (  # noqa: WPS433
        get_runtime_enabled,
        is_enabled as _env_enabled,
        set_runtime_enabled,
    )
    bus = _get_bus()
    if bus is None:
        raise HTTPException(
            status_code=503,
            detail="bus not initialized; cannot persist runtime toggle",
        )
    try:
        set_runtime_enabled(bus, enabled)
        runtime = bool(get_runtime_enabled(bus))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {
        "runtime_enabled": runtime,
        "env_enabled": _env_enabled(),
        "bus_available": True,
        "ok": True,
    }


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
        # FR-OG-7 loud-degrade: pass bus so absent `.sm-context.yaml`
        # emits a one-shot `og7_unconfigured` event the dashboard can
        # surface as a banner.
        ctx = load_sm_context(
            project_root,
            bus=_get_bus(),
            session_id=os.environ.get("SM_OWN_SESSION_ID", "sm-system"),
        )
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


# ── FR-UI-9: per-session settings persistence ─────────────────────────
#
# Settings are stored as a single JSON blob in `sessions.settings`. The
# blob avoids per-column migration churn as new FR-UI-9 controls land.
# The endpoint validates each known field's value range, merges into
# the persisted blob, and emits `session_settings_updated` so the
# event-log can render the change and other tabs/clients can sync.

_SETTINGS_FIELD_VALIDATORS: dict[str, object] = {}


def _validate_session_settings_payload(
    payload: dict[str, object]
) -> dict[str, object]:
    """Return the cleaned subset of `payload` that may be persisted.

    Raises HTTPException(400) on any invalid value. Unknown keys are
    silently dropped so the server stays the source of truth on schema.
    """
    out: dict[str, object] = {}

    if "sync_timeout_sec" in payload:
        try:
            v = float(payload["sync_timeout_sec"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="sync_timeout_sec must be a number")
        if v < 10.0 or v > 600.0:
            raise HTTPException(
                status_code=400,
                detail="sync_timeout_sec out of range (10-600)",
            )
        out["sync_timeout_sec"] = v

    if "activity_window_sec" in payload:
        try:
            v = float(payload["activity_window_sec"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="activity_window_sec must be a number")
        if v < 1.0 or v > 600.0:
            raise HTTPException(
                status_code=400,
                detail="activity_window_sec out of range (1-600)",
            )
        out["activity_window_sec"] = v

    if "confidence_floor" in payload:
        try:
            v = float(payload["confidence_floor"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="confidence_floor must be a number")
        if v < 0.0 or v > 1.0:
            raise HTTPException(
                status_code=400,
                detail="confidence_floor out of range (0.0-1.0)",
            )
        out["confidence_floor"] = v

    if "audible_cue" in payload:
        if not isinstance(payload["audible_cue"], bool):
            raise HTTPException(status_code=400, detail="audible_cue must be bool")
        out["audible_cue"] = payload["audible_cue"]

    if "motion" in payload:
        m = payload["motion"]
        if m not in ("system", "reduce", "allow"):
            raise HTTPException(
                status_code=400,
                detail="motion must be one of: system, reduce, allow",
            )
        out["motion"] = m

    if "hitl_mode" in payload:
        if payload["hitl_mode"] not in ("sync", "async"):
            raise HTTPException(
                status_code=400,
                detail="hitl_mode must be one of: sync, async",
            )
        out["hitl_mode"] = payload["hitl_mode"]

    if "pause_detection_enabled" in payload:
        if not isinstance(payload["pause_detection_enabled"], bool):
            raise HTTPException(
                status_code=400,
                detail="pause_detection_enabled must be bool",
            )
        out["pause_detection_enabled"] = payload["pause_detection_enabled"]

    return out


@app.get("/api/sessions/{session_id}/settings")
async def api_session_settings_get(session_id: str):
    """Return the persisted FR-UI-9 settings blob for a session."""
    bus = _get_bus()
    if bus is None:
        raise HTTPException(status_code=500, detail="bus unavailable")
    try:
        settings = bus.get_session_settings(session_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {
        "session_id": session_id,
        "settings": settings,
    }


@app.post("/api/sessions/{session_id}/settings")
async def api_session_settings_post(session_id: str, request: Request):
    """Persist a partial FR-UI-9 settings update for a session.

    Validates each known field, merges into the existing JSON blob, and
    emits a `session_settings_updated` bus event carrying the FULL merged
    settings (not just the patch) so other connected clients can sync.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json body")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")

    cleaned = _validate_session_settings_payload(body)
    if not cleaned:
        raise HTTPException(status_code=400, detail="no recognised settings keys in body")

    bus = _get_bus()
    if bus is None:
        raise HTTPException(status_code=500, detail="bus unavailable")

    # Ensure the session row exists so the UPDATE finds something to write.
    try:
        bus.open_session(session_id)
    except Exception:
        # If open_session fails the session may already exist; the
        # subsequent set_session_settings will surface the real error.
        pass

    try:
        bus.set_session_settings(session_id, cleaned)
        merged = bus.get_session_settings(session_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Emit bus event so audit replay and other clients see the update.
    try:
        from stream_manager.message_bus import Message
        bus.publish(
            Message.new(
                session_id=session_id,
                type="session_settings_updated",
                direction="internal",
                content=f"settings updated: {','.join(sorted(cleaned.keys()))}",
                metadata={"settings": merged, "patch": cleaned},
            )
        )
    except Exception:
        log.exception("session_settings_updated publish failed")

    return {
        "ok": True,
        "session_id": session_id,
        "settings": merged,
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


_MIRROR_TYPE_ALLOWLIST: frozenset[str] = frozenset({
    "tool_call", "tool_result", "tool_use", "tool_use_result",
})


def _parse_types_param(raw: str | None) -> list[str]:
    """Parse a ``?types=tool_call,tool_result`` query param into a clean list.

    Strips whitespace, drops empties, intersects against an allowlist so
    callers cannot use the param to widen the stream beyond mirror-relevant
    types (defence-in-depth — the SQL query already binds parameters).
    """
    if not raw:
        return []
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return [p for p in parts if p in _MIRROR_TYPE_ALLOWLIST]


# ── Task D: desktop_command outbound control plane ───────────────────

_DESKTOP_COMMAND_TTL_SECONDS = 30.0


def _reject_sm_own(session_id: str) -> None:
    """Raise HTTP 400 if session_id matches SM_OWN_SESSION_ID."""
    sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
    if sm_own and session_id == sm_own:
        raise HTTPException(
            status_code=400,
            detail="session_id matches SM_OWN_SESSION_ID",
        )


@app.post("/api/commands")
async def api_commands_emit(request: Request):
    """Emit a desktop_command targeted at a governed session.

    Body: ``{session_id, kind, args}``. Inserts a signed row into the
    ``desktop_commands`` WAL table with ``status='pending'`` and returns
    ``{id, status: "pending"}``.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json body")
    session_id = body.get("session_id")
    kind = body.get("kind")
    args = body.get("args", {})
    if not isinstance(session_id, str) or not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    if not isinstance(kind, str) or not kind:
        raise HTTPException(status_code=400, detail="kind required")
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise HTTPException(status_code=400, detail="args must be an object")
    _reject_sm_own(session_id)

    bus = _get_bus()
    if bus is None:
        raise HTTPException(status_code=500, detail="bus unavailable")
    try:
        from stream_manager.desktop_commands import emit_command
        cmd_id = emit_command(bus, session_id, kind, args)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"id": cmd_id, "status": "pending"}


# Note: the legacy ``GET /api/commands/pending`` long-poll endpoint was
# removed in v1.2 (Task D). SSE — ``GET /api/commands/stream`` below —
# is now the sole transport for the desktop_command control plane.
# See CHANGELOG.md and ADR-14 for the migration record.

_VALID_ACK_STATUS = {"ok", "rejected"}

# Task K (v1.1): SSE tail-poll cadence for /api/commands/stream. The SSE
# endpoint replays current pending rows on connect, then polls the
# desktop_commands table at this interval to push new pending rows. 200ms
# matches the v1.1 sub-second-delivery target while staying low enough that
# the SQLite read pressure is negligible (one indexed SELECT per session).
_DESKTOP_COMMAND_STREAM_TAIL_INTERVAL = 0.2


def _serialize_command_row(r: sqlite3.Row) -> dict[str, object]:
    """Shared row → JSON shape used by /pending and /stream.

    Mirrors the body in ``api_commands_pending`` so consumers can flip
    transports without parsing differences.
    """
    try:
        args = json.loads(r["args_json"]) if r["args_json"] else {}
    except (TypeError, ValueError):
        args = {}
    payload = {
        "id": r["id"],
        "session_id": r["session_id"],
        "kind": r["kind"],
        "args": args,
        "sent_at": float(r["sent_at"]),
    }
    return {
        "id": r["id"],
        "session_id": r["session_id"],
        "kind": r["kind"],
        "args": args,
        "sent_at": float(r["sent_at"]),
        "status": r["status"],
        "signature": r["signature"],
        "payload": payload,
    }


@app.get("/api/commands/stream")
async def api_commands_stream(request: Request, session_id: str):
    """SSE stream of pending desktop_commands for a session.

    Sole desktop_command transport as of v1.2 (Task D removed the
    legacy ``GET /api/commands/pending`` long-poll endpoint).

    On connect: replay current ``status='pending'`` rows oldest-first.
    Then tail-poll the ``desktop_commands`` table every
    ``_DESKTOP_COMMAND_STREAM_TAIL_INTERVAL`` seconds and emit any new
    pending rows whose rowid is strictly greater than the running cursor.

    Server-side filters (defence-in-depth):
      - session_id match required
      - SM_OWN_SESSION_ID rows rejected up-front (HTTP 400)
      - rows older than ``_DESKTOP_COMMAND_TTL_SECONDS`` are flipped to
        ``expired`` in the same connection and are NOT emitted.

    Frame shape: the JSON object emitted on each ``data:`` line is
    produced by ``_serialize_command_row`` (id, session_id, kind, args,
    sent_at, status, signature, payload). Consumers parse one frame at a
    time; the post-parse code path was kept transport-agnostic in v1.1
    so v1.2's removal of the long-poll endpoint required no consumer-
    side reshape.
    """
    if not isinstance(session_id, str) or not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    _reject_sm_own(session_id)

    sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()

    async def generate():
        try:
            conn = sqlite3.connect(
                str(DB_PATH), check_same_thread=False, isolation_level=None
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            return

        try:
            if not _has_table(conn, "desktop_commands"):
                # No table yet; emit a comment frame so the client sees
                # the connection is alive, then loop on a slow heartbeat.
                yield ": no desktop_commands table\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    await asyncio.sleep(1.0)
                    yield ": keepalive\n\n"
                return

            last_rowid = 0  # cursor: only emit rows with rowid > last_rowid

            # Replay phase: expire stale rows then send current pending
            # rows oldest-first. Tracks last_rowid so the tail loop never
            # double-emits replayed rows.
            try:
                cutoff = time.time() - _DESKTOP_COMMAND_TTL_SECONDS
                conn.execute(
                    "UPDATE desktop_commands SET status='expired' "
                    "WHERE session_id=? AND status='pending' AND sent_at < ?",
                    (session_id, cutoff),
                )
                # SM_OWN_SESSION_ID rows must never reach a consumer even
                # if they somehow landed in the table; the WHERE clause
                # excludes them server-side.
                params: list[object] = [session_id]
                where_extra = ""
                if sm_own:
                    where_extra = " AND session_id != ?"
                    params.append(sm_own)
                replay_sql = (
                    "SELECT rowid AS rid, id, session_id, kind, args_json, "
                    "signature, sent_at, status FROM desktop_commands "
                    "WHERE session_id=? AND status='pending'"
                    + where_extra
                    + " ORDER BY sent_at ASC, rowid ASC"
                )
                rows = conn.execute(replay_sql, tuple(params)).fetchall()
                for r in rows:
                    rid = int(r["rid"])
                    if rid > last_rowid:
                        last_rowid = rid
                    payload = _serialize_command_row(r)
                    yield f"data: {json.dumps(payload)}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"

            # Tail phase: poll for newly-inserted pending rows. We use the
            # rowid cursor (monotonic, no clock skew) rather than sent_at
            # so producer clock drift can't hide rows.
            tail_params_template: list[object] = [session_id]
            tail_where_extra = ""
            if sm_own:
                tail_where_extra = " AND session_id != ?"
                tail_params_template.append(sm_own)
            tail_sql = (
                "SELECT rowid AS rid, id, session_id, kind, args_json, "
                "signature, sent_at, status FROM desktop_commands "
                "WHERE rowid > ? AND session_id=? AND status='pending'"
                + tail_where_extra
                + " ORDER BY rowid ASC"
            )

            heartbeat_every = 15.0  # seconds
            last_heartbeat = time.time()

            while True:
                if await request.is_disconnected():
                    break
                # Expire stale rows on each tick so the producer side
                # observes consistent TTL behaviour with /pending.
                try:
                    cutoff = time.time() - _DESKTOP_COMMAND_TTL_SECONDS
                    conn.execute(
                        "UPDATE desktop_commands SET status='expired' "
                        "WHERE session_id=? AND status='pending' AND sent_at < ?",
                        (session_id, cutoff),
                    )
                    rows = conn.execute(
                        tail_sql, (last_rowid, *tail_params_template),
                    ).fetchall()
                    for r in rows:
                        rid = int(r["rid"])
                        if rid > last_rowid:
                            last_rowid = rid
                        payload = _serialize_command_row(r)
                        yield f"data: {json.dumps(payload)}\n\n"
                except Exception:
                    # Defensive: keep the connection alive on transient
                    # SQLite errors; the next tick will retry.
                    pass

                now = time.time()
                if now - last_heartbeat >= heartbeat_every:
                    yield ": keepalive\n\n"
                    last_heartbeat = now

                await asyncio.sleep(_DESKTOP_COMMAND_STREAM_TAIL_INTERVAL)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )


@app.post("/api/commands/{cmd_id}/ack")
async def api_commands_ack(cmd_id: str, request: Request):
    """ACK a pending desktop_command.

    Body: ``{status: "ok"|"rejected", error?: str}``. Updates the row's
    ``status``, ``acked_at``, and (optional) ``error``. Returns the new
    state of the row.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json body")
    status = body.get("status")
    error = body.get("error")
    if not isinstance(status, str) or status not in _VALID_ACK_STATUS:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of {sorted(_VALID_ACK_STATUS)}",
        )
    if error is not None and not isinstance(error, str):
        raise HTTPException(status_code=400, detail="error must be string or null")

    try:
        conn = _open_rw()
        if not _has_table(conn, "desktop_commands"):
            conn.close()
            raise HTTPException(status_code=404, detail="command not found")
        row = conn.execute(
            "SELECT session_id FROM desktop_commands WHERE id=?",
            (cmd_id,),
        ).fetchone()
        if row is None:
            conn.close()
            raise HTTPException(status_code=404, detail="command not found")
        # Defence-in-depth: ensure the row's session_id is not the SM
        # owner's. (emit_command rejects this on insert, but check on ack
        # too in case env changed mid-flight.)
        sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
        if sm_own and str(row["session_id"]) == sm_own:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail="session_id matches SM_OWN_SESSION_ID",
            )
        conn.execute(
            "UPDATE desktop_commands SET status=?, acked_at=?, error=? "
            "WHERE id=?",
            (status, time.time(), error, cmd_id),
        )
        conn.close()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"id": cmd_id, "status": status, "error": error}


@app.get("/events")
async def sse_events(
    request: Request,
    session_id: str | None = None,
    types: str | None = None,
):
    """SSE stream: one JSON event per new decision row, 500ms poll.

    FR-UI-8: emits ``id: d{drid}:m{mrid}`` on every event so the browser
    resumes from the last seen cursor via ``Last-Event-ID`` after reconnect.

    Task C (Session Mirror): optional ``?session_id=<id>&types=tool_call,tool_result``
    narrows the messages branch to a single session and a fixed type allowlist.
    The decisions branch is suppressed when either filter is supplied so the
    Mirror panel sees only tool-call/result rows for the selected session.
    Rows whose ``session_id`` matches ``SM_OWN_SESSION_ID`` are filtered
    server-side regardless of params (no-self-monitor enforcement).
    """

    resume_drid, resume_mrid = _parse_last_event_id(
        request.headers.get("last-event-id")
    )

    mirror_session = (session_id or "").strip() or None
    mirror_types = _parse_types_param(types)
    is_mirror = mirror_session is not None or bool(mirror_types)
    sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()

    async def generate():
        try:
            conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            return

        # FR-PPP-1: per-connection envelope subscriber. The bus invokes
        # _env_cb from a worker thread; thread-safe-trampoline into the
        # asyncio loop pushes (event_type, payload) onto the per-conn
        # queue. The generator drains the queue each tick. unsubscribe
        # in `finally` is the only thing preventing a callback leak (the
        # callback closure pins the queue + request scope).
        loop = asyncio.get_running_loop()
        # v2.1 P1a (R16): cap raised 256 → 512 to absorb LM-pump bursts
        # observed during cassette record (45-row Learn Mode dialogue
        # arrives in <50 ms when soak driver pumps locally). Drops are
        # still possible under sustained backpressure but now logged
        # (was silent pre-P1a).
        env_q: asyncio.Queue = asyncio.Queue(maxsize=512)
        env_drop_count = [0]
        bus = _get_bus()

        def _safe_put(item: tuple[str, dict]) -> None:
            try:
                env_q.put_nowait(item)
            except asyncio.QueueFull:
                env_drop_count[0] += 1
                if env_drop_count[0] == 1 or env_drop_count[0] % 50 == 0:
                    log.warning(
                        "/events: env_q full, dropped envelope "
                        "(type=%s, drop_total=%d, qsize=%d/%d)",
                        item[0], env_drop_count[0],
                        env_q.qsize(), env_q.maxsize,
                    )

        def _env_cb(env_type: str, payload: dict) -> None:
            try:
                loop.call_soon_threadsafe(_safe_put, (env_type, payload))
            except RuntimeError:
                pass

        if bus is not None:
            try:
                bus.subscribe_envelope(_env_cb)
            except Exception:
                log.exception("/events: subscribe_envelope failed")

        if resume_drid is not None and resume_mrid is not None:
            # Resume path: skip seed, replay strictly newer rows from cursor.
            last_rid = resume_drid
            last_msg_rid = resume_mrid
        else:
            # Fresh connect: seed last 25 decisions (oldest→newest) and snap
            # the messages cursor to current max so we don't ship history.
            # Mirror-mode (session_id or types filter) suppresses the
            # decisions seed — Mirror only renders message rows.
            if is_mirror:
                last_rid = 0
            else:
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

        # Build the messages-branch SQL once. Filters apply per request:
        # - Mirror session_id pin
        # - Mirror types allowlist
        # - Always exclude SM_OWN_SESSION_ID (no-self-monitor)
        msg_filters: list[str] = ["rowid > ?"]
        msg_params_template: list = []
        if is_mirror:
            # In mirror mode we DO want inbound rows (tool_call rows are
            # written with direction='inbound' from the hook). Skip the
            # default "direction != 'inbound'" gate.
            pass
        else:
            msg_filters.append("direction != 'inbound'")
        if mirror_session is not None:
            msg_filters.append("session_id = ?")
            msg_params_template.append(mirror_session)
        if mirror_types:
            placeholders = ",".join(["?"] * len(mirror_types))
            msg_filters.append(f"type IN ({placeholders})")
            msg_params_template.extend(mirror_types)
        if sm_own:
            msg_filters.append("session_id != ?")
            msg_params_template.append(sm_own)
        msg_sql = (
            "SELECT rowid AS rid, id, session_id, type, content, "
            "metadata, timestamp, direction FROM messages "
            f"WHERE {' AND '.join(msg_filters)} "
            "ORDER BY rowid ASC"
        )

        try:
            while True:
                if await request.is_disconnected():
                    break
                # Mirror mode suppresses the decisions tail — only messages flow.
                if not is_mirror:
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
                        msg_sql, (last_msg_rid, *msg_params_template),
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
                # FR-PPP-1: drain envelope queue. Use a named SSE event
                # so the browser binds via `addEventListener('audit.probe', ...)`
                # rather than the default `message` handler.
                while True:
                    try:
                        env_type, env_payload = env_q.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    yield (
                        f"event: {env_type}\n"
                        f"data: {json.dumps(env_payload)}\n\n"
                    )
                await asyncio.sleep(0.5)
        finally:
            if bus is not None:
                try:
                    bus.unsubscribe_envelope(_env_cb)
                except Exception:
                    log.exception("/events: unsubscribe_envelope failed")
            try:
                conn.close()
            except Exception:
                pass

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":       "keep-alive",
        },
    )
