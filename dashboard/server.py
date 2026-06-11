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
    # v2.3 P1 Seed 6: JsonlTailWorker production wiring (lever wire;
    # WIRED_LEVER_LEDGER_COUNT 0 -> 1). Tails Desktop<->user dialogue
    # from `~/.claude/projects/` JSONL per the learn-mode design.
    #
    # Polarity-flip enforcement (per CLAUDE.md §"Session-source
    # exception rule" + `feedback_no_self_monitor.md`):
    # 1. Wire-site refusal: if `BRIDGE_PROJECT_SLUG` is in the SM
    #    slug set (`BRIDGE_SM_PROJECT_SLUGS`, default `{"streamManager"}`),
    #    refuse to start. Default-exclude SM by project-slug — leakage
    #    is the loud failure path (log + skip), not silent corpus poison.
    # 2. Per-record defense: `_is_sm_originated` filters individual
    #    JSONL records by cached `SM_OWN_SESSION_ID` (second layer).
    #
    # Governance ref intentionally `None` for v2.3 wire — the dashboard
    # process does not own per-session engines (see `_get_engine_registry`
    # comment). v2.1 P2 canary timeout re-fire degrades to envelope-only
    # failure as a result; v2.4 candidate is to wire a process-wide
    # governance ref or hand the canary registry a different injection
    # point. Daemon thread; idempotent. Best-effort — failure must never
    # block dashboard startup.
    try:
        from stream_manager.jsonl_tail import JsonlTailWorker
        bus = _get_bus()
        registry = _get_registry()
        project_slug = os.environ.get("BRIDGE_PROJECT_SLUG", "default")
        # Polarity-flip wire-site refusal.
        _sm_slugs_raw = os.environ.get(
            "BRIDGE_SM_PROJECT_SLUGS", "streamManager"
        )
        _sm_slugs = frozenset(
            s.strip() for s in _sm_slugs_raw.split(",") if s.strip()
        )
        if project_slug in _sm_slugs:
            log.warning(
                "jsonl_tail: REFUSED to start — project_slug=%s is in "
                "SM exclusion set %s (polarity-flip per CLAUDE.md). "
                "Set BRIDGE_PROJECT_SLUG to a non-SM project (e.g. the "
                "monitored target) before restarting.",
                project_slug,
                sorted(_sm_slugs),
            )
        elif bus is not None and registry is not None:
            projects_dir = Path(
                os.environ.get(
                    "BRIDGE_PROJECTS_DIR",
                    str(Path.home() / ".claude" / "projects"),
                )
            )
            worker = JsonlTailWorker(
                projects_dir=projects_dir,
                registry=registry,
                bus=bus,
                governance=None,
            )
            session_id = os.environ.get("SM_OWN_SESSION_ID", "")
            worker.start(session_id=session_id, project_slug=project_slug)
            log.info(
                "jsonl_tail: started (projects_dir=%s, slug=%s, "
                "own_session=%s, excl_slugs=%s)",
                projects_dir,
                project_slug,
                session_id or "<unset>",
                sorted(_sm_slugs),
            )
    except Exception:
        log.exception("jsonl_tail: startup raised; continuing")


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
    # v2.3 P1 Seed 6: stop JsonlTailWorker (daemon thread; 2s join in
    # worker.stop() each on tail + sweep threads).
    try:
        from stream_manager.jsonl_tail import get_active_worker
        w = get_active_worker()
        if w is not None:
            w.stop()
    except Exception:
        log.exception("jsonl_tail: shutdown raised; continuing")
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


# -- BETA feature-flag registry (2026-06-11 BETA proposals initiative) -------
# Additive EVOLVING surface (dashboard/server.py is EVOLVING per ADR-18; only
# /api/lifecycle/jobs is FROZEN). Stores the operator's on/off choice for
# optional BETA features in a new `beta_flags` table (created lazily). All flags
# DEFAULT OFF: a key absent from the table reads as disabled. The frontend
# registry (ui-next lib/beta/registry.js) owns label/description/component; the
# backend stores only the boolean override. A read error degrades to all-OFF --
# never silently flips a flag on.

_BETA_KEY_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")


def _ensure_beta_flags(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS beta_flags ("
        "key TEXT PRIMARY KEY, "
        "enabled INTEGER NOT NULL DEFAULT 0, "
        "updated_at TEXT)"
    )


def _valid_beta_key(key: str) -> bool:
    return bool(key) and len(key) <= 64 and all(c in _BETA_KEY_CHARS for c in key)


@app.get("/api/beta/flags")
async def api_beta_flags():
    """Return stored BETA flag overrides as ``{flags: {key: bool}}``.

    Missing keys read as OFF (the frontend registry merges defaults). A read
    error degrades to an empty map (all-OFF) rather than surfacing an error
    that a client could misread as "on".
    """
    try:
        conn = _open_rw()
        _ensure_beta_flags(conn)
        rows = conn.execute("SELECT key, enabled FROM beta_flags").fetchall()
        conn.close()
        return {"flags": {r["key"]: bool(r["enabled"]) for r in rows}}
    except Exception:
        log.exception("beta/flags: read failed; degrading to all-OFF")
        return {"flags": {}}


@app.post("/api/beta/flags/{key}")
async def api_beta_flag_set(key: str, request: Request):
    """Upsert one BETA flag override. Body ``{enabled: bool}``. Returns state."""
    if not _valid_beta_key(key):
        raise HTTPException(status_code=400, detail="invalid key")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json body") from None
    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=400, detail="enabled must be bool")
    try:
        conn = _open_rw()
        _ensure_beta_flags(conn)
        conn.execute(
            "INSERT INTO beta_flags (key, enabled, updated_at) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET "
            "enabled=excluded.enabled, updated_at=excluded.updated_at",
            (key, 1 if enabled else 0, _iso_now()),
        )
        conn.close()
    except Exception as exc:
        log.exception("beta/flags: write failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"key": key, "enabled": enabled}


# ===================== BETA #coverage-analyzer : coverage-analyzer =====================

# --- GET /api/coverage/bands ---
# ---------------------------------------------------------------------------
# BETA coverage-analyzer (#10): cassette-vs-live band distribution.
# Additive, read-only. Aggregates governance decisions by routing layer into
# four bands (ALLOW=layer 0, L2/L3=layer 2, L4=layer 4, LEARN=layer 0 learn-
# dialogue) for (a) the soak CASSETTE fixture and (b) the LIVE non-SM session
# window. POLARITY (G2): the live aggregation EXCLUDES SM-self -- it joins
# sessions and filters project_slug NOT IN {streamManager} AND session_id !=
# self, mirroring the BRIDGE_SM_PROJECT_SLUGS / SM_OWN_SESSION_ID wire-site
# guard. Domain-agnostic (M16): bands are governance layers, never project
# vocabulary. No FROZEN surface is touched; no new bus envelope. Defensive --
# any error degrades to an empty (all-zero) shape so the UI falls back to mock.
# ---------------------------------------------------------------------------

# Cassette kind -> routing layer + band, mirroring tools/cassette_record.py
# (_KIND_TO_LAYER). Kept local so this endpoint adds no import coupling to the
# soak tooling. The four bands match the frontend BANDS table exactly.
_COVERAGE_KIND_TO_BAND = {
    "routine": "allow",
    "l2_l3": "l2_l3",
    "l4": "l4",
    "learn_dialogue": "learn",
}
_COVERAGE_LAYER_TO_BAND = {0: "allow", 2: "l2_l3", 4: "l4"}
_COVERAGE_BAND_ORDER = (
    ("allow", "ALLOW", 0),
    ("l2_l3", "L2/L3", 2),
    ("l4", "L4", 4),
    ("learn", "LEARN", 0),
)


def _coverage_sm_slugs() -> frozenset[str]:
    """The SM-self project slug exclusion set (polarity G2). Mirrors the
    jsonl_tail wire-site guard so the same default ('streamManager') and the
    same BRIDGE_SM_PROJECT_SLUGS override apply."""
    raw = os.environ.get("BRIDGE_SM_PROJECT_SLUGS", "streamManager")
    return frozenset(s.strip() for s in raw.split(",") if s.strip())


def _coverage_empty_bands(source: str) -> dict:
    return {
        "source": source,
        "total": 0,
        "bands": [
            {"key": k, "label": lbl, "layer": layer, "count": 0, "pct": 0.0}
            for (k, lbl, layer) in _COVERAGE_BAND_ORDER
        ],
    }


def _coverage_histogram(counts: dict[str, int], source: str, **extra) -> dict:
    total = sum(counts.values())
    bands = []
    for (k, lbl, layer) in _COVERAGE_BAND_ORDER:
        n = int(counts.get(k, 0))
        pct = round(n / total * 100, 1) if total else 0.0
        bands.append({"key": k, "label": lbl, "layer": layer, "count": n, "pct": pct})
    out = {"source": source, "total": total, "bands": bands}
    out.update(extra)
    return out


def _coverage_cassette_bands() -> dict:
    """Histogram the soak cassette fixture by kind. Path-driven (no project
    identity). Reads the newest soak_cassette_*.jsonl under tests/fixtures,
    preferring soak_cassette_latest.jsonl. Empty shape on any error."""
    try:
        fx_dir = ROOT / "tests" / "fixtures"
        latest = fx_dir / "soak_cassette_latest.jsonl"
        path = latest if latest.exists() else None
        if path is None:
            cands = sorted(fx_dir.glob("soak_cassette_*.jsonl"))
            if cands:
                path = cands[-1]
        if path is None or not path.exists():
            return _coverage_empty_bands("cassette")
        counts: dict[str, int] = {}
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                kind = rec.get("kind")
                band = _COVERAGE_KIND_TO_BAND.get(kind)
                if band is None:
                    layer = int((rec.get("decision") or {}).get("layer", 0) or 0)
                    band = _COVERAGE_LAYER_TO_BAND.get(layer, "allow")
                counts[band] = counts.get(band, 0) + 1
        return _coverage_histogram(counts, "cassette", fixture=path.name)
    except Exception:
        log.exception("coverage/bands: cassette histogram failed")
        return _coverage_empty_bands("cassette")


def _coverage_live_bands(window: int) -> dict:
    """Histogram the most-recent `window` non-SM decisions by routing layer.
    POLARITY (G2): joins sessions and EXCLUDES SM-self by project_slug AND by
    session_id. Layer-aware only when the decisions table has the routing
    columns; otherwise everything bins as ALLOW (layer 0). Empty shape on error."""
    try:
        conn = _open()
        sm_slugs = _coverage_sm_slugs()
        own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
        has_layer = _has_decision_routing_cols(conn)
        layer_expr = "COALESCE(d.layer, 0)" if has_layer else "0"
        # project_slug exclusion (polarity read-side key). Built as a
        # parameterised NOT IN so the slug set is data, never interpolated SQL.
        slug_list = sorted(sm_slugs)
        placeholders = ",".join("?" for _ in slug_list) or "''"
        params: list = list(slug_list)
        self_clause = ""
        if own:
            self_clause = " AND m.session_id != ?"
        # The window cap is applied per-band post-aggregation is imprecise;
        # instead bound the scan to the newest `window` decisions via a subquery.
        scan_sql = (
            f"SELECT {layer_expr} AS layer FROM decisions d "
            "JOIN messages m ON d.message_id = m.id "
            "JOIN sessions s ON m.session_id = s.id "
            "WHERE (s.project_slug IS NULL OR s.project_slug NOT IN ("
            f"{placeholders}))"
            f"{self_clause} "
            "ORDER BY d.rowid DESC LIMIT ?"
        )
        scan_params = list(params)
        if own:
            scan_params.append(own)
        scan_params.append(max(1, min(int(window or 1000), 5000)))
        rows = conn.execute(scan_sql, scan_params).fetchall()
        # Count how many self rows were excluded for the operator-facing note.
        excl = 0
        if own:
            er = conn.execute(
                "SELECT COUNT(*) FROM decisions d "
                "JOIN messages m ON d.message_id = m.id "
                "WHERE m.session_id = ?",
                (own,),
            ).fetchone()
            excl = int(er[0] or 0) if er else 0
        conn.close()
        counts: dict[str, int] = {}
        for r in rows:
            layer = int(r["layer"] or 0)
            band = _COVERAGE_LAYER_TO_BAND.get(layer, "allow")
            counts[band] = counts.get(band, 0) + 1
        return _coverage_histogram(
            counts,
            "live",
            window=int(window or 1000),
            polarity_filtered=True,
            excluded_self_rows=excl,
        )
    except Exception:
        log.exception("coverage/bands: live histogram failed")
        return _coverage_empty_bands("live")


@app.get("/api/coverage/bands")
async def api_coverage_bands(window: int = 1000, fixture_id: str | None = None):
    """BETA coverage-analyzer (#10): cassette + live band distributions.

    Read-only post-hoc aggregate (M18). The live column is polarity-filtered
    (SM-self excluded by project_slug AND session_id). Returns
    {cassette, live} (and {fixture} when fixture_id is a known fixture). Each
    column is an all-zero shape on its own error so the client can fall back to
    mock data without the whole call failing.
    """
    out: dict = {
        "cassette": _coverage_cassette_bands(),
        "live": _coverage_live_bands(window),
    }
    # Optional uploaded-fixture comparison: re-bin a named cassette-shaped
    # fixture under tests/fixtures (path-driven, no project identity). Unknown
    # / unsafe ids are ignored (the client falls back to its own mock).
    if fixture_id and all(c.isalnum() or c in "-_." for c in fixture_id):
        fx = ROOT / "tests" / "fixtures" / fixture_id
        if fx.exists() and fx.suffix == ".jsonl":
            try:
                counts: dict[str, int] = {}
                with fx.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                        except Exception:
                            continue
                        b = _COVERAGE_KIND_TO_BAND.get(rec.get("kind"))
                        if b is None:
                            layer = int((rec.get("decision") or {}).get("layer", 0) or 0)
                            b = _COVERAGE_LAYER_TO_BAND.get(layer, "allow")
                        counts[b] = counts.get(b, 0) + 1
                out["fixture"] = _coverage_histogram(
                    counts, "fixture", fixture_id=fixture_id,
                    polarity_filtered=True, excluded_self_rows=0,
                )
            except Exception:
                log.exception("coverage/bands: fixture histogram failed")
    return out


# ===================== BETA #escalation-heatmap : escalation-heatmap =====================

# --- GET /api/escalation-timeline ---
@app.get("/api/escalation-timeline")
async def api_escalation_timeline(
    session_id: str | None = None,
    bucket_ms: int = 30000,
    limit: int = 5000,
):
    """Pre-aggregate escalation decisions (GUIDE/INTERVENE/BLOCK) into
    contiguous wall-clock buckets for the BETA escalation-heatmap gutter (#14).

    Read-only, post-hoc (M18): a render-ready aggregation over the existing
    indexed decisions(timestamp) + messages(session_id) rows. ZERO writes, ZERO
    FROZEN-surface touch, ZERO new bus envelope.

    POLARITY (G2 / M15): the SM-own session is excluded at the SQL WHERE on
    sessions.project_slug -- a session whose project_slug is in the SM exclusion
    set (BRIDGE_SM_PROJECT_SLUGS, default {'streamManager'}) can NEVER appear in
    the aggregation. A LEFT JOIN keeps rows whose session has no sessions-row
    (they are not self), and the env-set is read the same way the jsonl_tail
    wire-site refusal reads it, so the two stay consistent.

    Returns {bucket_ms, buckets:[{t_ms, counts:{GUIDE,INTERVENE,BLOCK}, total,
    peak}], max, escalation_count}. Buckets are ascending (newest last); quiet
    buckets WITHIN the observed span are present (total 0) so the client Y-axis
    is true wall-clock. Degrades to an empty buckets list on any error.
    """
    try:
        bw = int(bucket_ms) if int(bucket_ms or 0) > 0 else 30000
        # bucket width in SECONDS (the decisions.timestamp column is epoch sec).
        bw_s = bw / 1000.0
        cap = min(int(limit or 5000), 20000)
        _sm_slugs_raw = os.environ.get("BRIDGE_SM_PROJECT_SLUGS", "streamManager")
        sm_slugs = [s.strip() for s in _sm_slugs_raw.split(",") if s.strip()]
        conn = _open()
        # Self-exclude (G2): drop any decision whose session is on an SM project
        # slug. LEFT JOIN so a decision with no sessions-row is KEPT (not self).
        params: list = []
        where = ["d.action IN ('GUIDE','INTERVENE','BLOCK')"]
        if session_id:
            where.append("m.session_id = ?")
            params.append(session_id)
        if sm_slugs:
            placeholders = ",".join("?" for _ in sm_slugs)
            # s.project_slug IS NULL => no session row => keep (not self).
            where.append(
                f"(s.project_slug IS NULL OR s.project_slug NOT IN ({placeholders}))"
            )
            params.extend(sm_slugs)
        sql = (
            "SELECT d.action AS action, d.timestamp AS ts "
            "FROM decisions d "
            "JOIN messages m ON d.message_id = m.id "
            "LEFT JOIN sessions s ON s.id = m.session_id "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY d.timestamp ASC LIMIT ?"
        )
        params.append(cap)
        rows = conn.execute(sql, tuple(params)).fetchall()
        conn.close()
    except Exception:
        log.exception("escalation-timeline: query failed; degrading to empty")
        return {
            "bucket_ms": int(bucket_ms or 30000), "buckets": [],
            "max": 1, "escalation_count": 0,
        }

    # Aggregate into a bucket->counts map (epoch-seconds bucket start).
    by_bucket: dict[int, dict[str, int]] = {}
    esc_count = 0
    min_start = None
    max_start = None
    for r in rows:
        ts = r["ts"]
        try:
            ts_f = float(ts)
        except (TypeError, ValueError):
            continue
        # float-safe bucket start in seconds, then expose ms.
        start = int(ts_f // bw_s) * bw
        act = str(r["action"]).strip().upper()
        if act not in ("GUIDE", "INTERVENE", "BLOCK"):
            continue
        c = by_bucket.setdefault(start, {"GUIDE": 0, "INTERVENE": 0, "BLOCK": 0})
        c[act] += 1
        esc_count += 1
        if min_start is None or start < min_start:
            min_start = start
        if max_start is None or start > max_start:
            max_start = start

    if esc_count == 0 or min_start is None:
        return {"bucket_ms": bw, "buckets": [], "max": 1, "escalation_count": 0}

    buckets = []
    max_total = 1
    start = min_start
    # materialise contiguous buckets across the observed span (quiet ones kept).
    span_guard = 0
    while start <= max_start and span_guard < 100000:
        span_guard += 1
        c = by_bucket.get(start, {"GUIDE": 0, "INTERVENE": 0, "BLOCK": 0})
        total = c["GUIDE"] + c["INTERVENE"] + c["BLOCK"]
        if c["BLOCK"] > 0:
            peak = "BLOCK"
        elif c["INTERVENE"] > 0:
            peak = "INTERVENE"
        elif c["GUIDE"] > 0:
            peak = "GUIDE"
        else:
            peak = ""
        if total > max_total:
            max_total = total
        buckets.append({"t_ms": start, "counts": c, "total": total, "peak": peak})
        start += bw

    return {
        "bucket_ms": bw,
        "buckets": buckets,
        "max": max_total,
        "escalation_count": esc_count,
    }


# ===================== BETA #hitl-bulk-dismiss : hitl-bulk-dismiss =====================

# --- GET /api/hitl/pending/triage ---
@app.get("/api/hitl/pending/triage")
async def api_hitl_pending_triage(session_id: str | None = None):
    """Polarity-safe seed for the BETA hitl-bulk-dismiss triage modal (#15).

    Additive READ-ONLY endpoint. Returns the SAME unresolved hitl_pending
    row shape as /api/hitl/pending, but JOINs sessions to project_slug and
    EXCLUDES SM-self so the bulk-dismiss sweep can never target an SM-own
    session (G2 polarity floor, CLAUDE.md 'Session-source exception rule'):

      - project_slug NOT IN (STREAM_MANAGER_PROJECT_SLUGS)  -- durable read key
      - m.session_id != SM_OWN_SESSION_ID                   -- session backstop

    The modal then loops the EXISTING POST /api/hitl/resolve (resolution
    'dismissed') over the operator-checked rows -- this endpoint mutates
    NOTHING. Degrades to [] on any error / empty DB (the client falls back
    to demo data so the feature stays testable).
    """
    try:
        conn = _open()
        if not _has_table(conn, "hitl_pending"):
            conn.close()
            return []
        # SM-self exclusion set (durable read key = project_slug). Default
        # {'streamManager'}; override via BRIDGE_SM_PROJECT_SLUGS. Lowercased
        # for a case-insensitive compare against sessions.project_slug.
        sm_slugs_raw = os.environ.get("BRIDGE_SM_PROJECT_SLUGS", "streamManager")
        sm_slugs = [s.strip().lower() for s in sm_slugs_raw.split(",") if s.strip()]
        sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
        # Detect whether the sessions table exists (older DBs may lack it).
        has_sessions = _has_table(conn, "sessions")
        join_sql = (
            "LEFT JOIN sessions s ON m.session_id = s.id " if has_sessions else ""
        )
        slug_sel = "s.project_slug AS project_slug " if has_sessions else ""
        where = ["hp.resolved_at IS NULL"]
        params: list = []
        if session_id:
            where.append("m.session_id = ?")
            params.append(session_id)
        # Polarity: drop SM-self by project_slug (durable) + session_id (backstop).
        if has_sessions and sm_slugs:
            placeholders = ",".join("?" for _ in sm_slugs)
            # NULL slug is NOT in the SM set -> kept (a governed row with no
            # session join is never SM-own by slug; the session_id backstop
            # below still guards the one self session).
            where.append(
                "(s.project_slug IS NULL OR LOWER(s.project_slug) NOT IN ("
                + placeholders + "))"
            )
            params.extend(sm_slugs)
        if sm_own:
            where.append("m.session_id != ?")
            params.append(sm_own)
        sql = (
            "SELECT hp.id, hp.message_id, hp.proposed_action, "
            "hp.proposed_confidence, hp.trigger_reason, hp.queued_at, "
            "hp.bias_hint, m.session_id, m.content " + (", " + slug_sel if slug_sel else "") +
            "FROM hitl_pending hp JOIN messages m ON hp.message_id = m.id "
            + join_sql
            + "WHERE " + " AND ".join(where)
            + " ORDER BY hp.id ASC"
        )
        rows = conn.execute(sql, tuple(params)).fetchall()
        conn.close()
        out: list[dict] = []
        for r in rows:
            d = dict(r)
            d["bias_hint"] = _decode_bias_hint(d.get("bias_hint"))
            out.append(d)
        return out
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ===================== BETA #decision-oracle : decision-oracle =====================

# --- GET /api/patterns/{hash}/pedigree ---
# Promotion ladder mirrors src/stream_manager/decision_graph.py
# PROMOTION_THRESHOLDS (occurrences needed to climb OFF a level). Read-only copy
# so the endpoint can annotate the meter without importing the engine module.
_ORACLE_PROMOTION_THRESHOLDS = {0: 3, 1: 5, 2: 10, 3: 20}


def _oracle_sm_slugs() -> frozenset[str]:
    """The SM project-slug exclusion set (polarity floor, CLAUDE.md). Mirrors the
    jsonl_tail wire-site default exactly: env BRIDGE_SM_PROJECT_SLUGS, default
    'streamManager'. Compared lowercased."""
    raw = os.environ.get("BRIDGE_SM_PROJECT_SLUGS", "streamManager")
    return frozenset(s.strip().lower() for s in raw.split(",") if s.strip())


def _oracle_fmt_ts(ts: float) -> str:
    """A short, human, ASCII-only timestamp label for an observation row."""
    import datetime as _dt
    try:
        d = _dt.datetime.fromtimestamp(float(ts))
        return d.strftime("%b %d, %H:%M")
    except Exception:
        return "--"


def _oracle_age_days(first_seen: float | None, last_seen: float | None) -> int | None:
    try:
        if first_seen is None:
            return None
        import time as _t
        span = (last_seen or _t.time()) - float(first_seen)
        return max(0, int(span // 86400))
    except Exception:
        return None


@app.get("/api/patterns/{hash}/pedigree")
async def api_pattern_pedigree(hash: str):
    """READ-ONLY pattern pedigree for the Decision Oracle whisper pane (BETA #12).

    Returns the L0-L4 promotion ladder context + a success/age stat strip + an
    ancestral-replay observation timeline reconstructed from the messages whose
    decisions matched this pattern hash. 404 when the pattern is unknown, has no
    NON-SM observations, or the graph_patterns table is absent (fresh DB).

    G2 (no-self-monitor): observations on SM-self sessions (project_slug in the
    SM exclusion set) are EXCLUDED from the timeline and the overfit tally; if
    that leaves zero observations the whole pedigree is suppressed (404). The
    pattern is never exposed solely from SM-self traffic.
    """
    pattern_hash = (hash or "").strip()
    if not pattern_hash or len(pattern_hash) > 128:
        raise HTTPException(status_code=404, detail="pattern not found")

    try:
        conn = _open()
        try:
            # No graph_patterns table yet (fresh DB / pre-soak) -> calm 404.
            if not _has_table(conn, "graph_patterns"):
                raise HTTPException(status_code=404, detail="pattern not found")

            prow = conn.execute(
                "SELECT hash, level, occurrences, successes, last_seen, "
                "canonical_text FROM graph_patterns WHERE hash=?",
                (pattern_hash,),
            ).fetchone()
            if prow is None:
                raise HTTPException(status_code=404, detail="pattern not found")

            sm_slugs = _oracle_sm_slugs()

            # The observation timeline: every decision that matched this hash,
            # joined to its message + session + the agent profile active at
            # decision time. SM-self sessions are filtered in Python (the slug set
            # is small + env-driven; keeping it out of SQL mirrors the read-side
            # backstop pattern). Ordered oldest-first (ancestral replay reads
            # forward in time).
            has_agents = _has_table(conn, "agents")
            slug_expr = (
                "(SELECT a.profile_slug FROM agents a "
                "WHERE a.session_id = m.session_id AND a.last_seen <= d.timestamp "
                "ORDER BY a.last_seen DESC LIMIT 1)"
                if has_agents else "NULL"
            )
            obs_rows = conn.execute(
                "SELECT d.timestamp AS ts, d.confidence AS confidence, "
                "m.content AS content, m.session_id AS session_id, "
                "COALESCE(s.project_slug, '') AS project_slug, "
                f"{slug_expr} AS profile_slug "
                "FROM decisions d "
                "JOIN messages m ON d.message_id = m.id "
                "LEFT JOIN sessions s ON s.id = m.session_id "
                "WHERE d.matched_hash = ? "
                "ORDER BY d.timestamp ASC",
                (pattern_hash,),
            ).fetchall()
        finally:
            conn.close()
    except HTTPException:
        raise
    except Exception:
        # Detail to the log, not the body (no SQL/stack leak to the client).
        log.exception("patterns/pedigree: query failed")
        raise HTTPException(status_code=500, detail="internal error") from None

    # G2: drop SM-self observations. If nothing non-SM remains, suppress (404).
    governed = [
        r for r in obs_rows
        if (r["project_slug"] or "").strip().lower() not in sm_slugs
    ]
    if not governed:
        raise HTTPException(status_code=404, detail="pattern not found")

    level = max(0, min(4, int(prow["level"] or 0)))
    occurrences = int(prow["occurrences"] or 0)
    successes = int(prow["successes"] or 0)
    success_rate = (successes / occurrences) if occurrences > 0 else 0.0

    first_ts = governed[0]["ts"]
    last_ts = governed[-1]["ts"]

    # Overfit tally: share of governed observations on the single most common
    # agent profile. Domain-agnostic (keyed on whatever profile_slug the data
    # carries). Flag at >= 80% on one profile with >= 3 observations.
    prof_counts: dict[str, int] = {}
    for r in governed:
        p = (r["profile_slug"] or "").strip() or "unknown"
        prof_counts[p] = prof_counts.get(p, 0) + 1
    top_profile = None
    overfit_pct = 0
    overfit_flagged = False
    if prof_counts:
        top_profile, top_n = max(prof_counts.items(), key=lambda kv: kv[1])
        overfit_pct = round(top_n / len(governed) * 100)
        overfit_flagged = (
            len(governed) >= 3 and overfit_pct >= 80 and top_profile != "unknown"
        )

    # Promotion meter: occurrences toward the next-level threshold.
    next_threshold = _ORACLE_PROMOTION_THRESHOLDS.get(level)

    observations = []
    for i, r in enumerate(governed):
        content = (r["content"] or "").replace("\r", " ").replace("\n", " ").strip()
        fingerprint = content[:50] + ("..." if len(content) > 50 else "")
        prof = (r["profile_slug"] or "").strip() or "unlabelled"
        observations.append({
            "seq": i + 1,
            "ts_label": _oracle_fmt_ts(r["ts"]),
            "intent": prof,                # domain-agnostic intent proxy (agent profile)
            "fingerprint": fingerprint,
            "match_pct": round(float(r["confidence"] or 0.0) * 100),
        })

    return {
        "pattern_hash": pattern_hash,
        "level": level,
        "occurrences": occurrences,
        "successes": successes,
        "success_rate": round(success_rate, 4),
        "next_threshold": next_threshold,        # null at L4 (terminal)
        "age_days": _oracle_age_days(first_ts, last_ts),
        "first_seen_label": f"first seen {_oracle_fmt_ts(first_ts)}",
        "last_reinforced_label": _oracle_fmt_ts(last_ts),
        "overfit": {
            "flagged": overfit_flagged,
            "pct": overfit_pct,
            "profile": top_profile if top_profile and top_profile != "unknown" else None,
        },
        "observations": observations,
    }


# ===================== BETA #health-digest : health-digest =====================

# --- GET /api/sessions/health-digest ---
@app.get("/api/sessions/health-digest")
async def api_sessions_health_digest(limit: int = 20):
    """BETA #32 -- per-session health digest for the glance rail.

    Collapses the prior 4 per-session fetches (decisions / agents /
    lifecycle jobs / hitl pending) into ONE aggregated read so the rail
    can render a pre-computed health verdict per governed session.

    READ-ONLY (M18, post-hoc -- never on the verdict hot path). Opens the
    DB with the same ``_open()`` (mode=ro) pattern as every other read
    endpoint and closes it before returning.

    POLARITY (G2, CLAUDE.md): SM never presents its own sessions as
    governed targets. The durable read key is ``project_slug NOT IN``
    the SM slug set (``BRIDGE_SM_PROJECT_SLUGS``, default
    ``{streamManager}``); ``SM_OWN_SESSION_ID`` is applied as the cheap
    read-side backstop on the ephemeral session-id key. ``excluded_self``
    surfaces how many rows the filter dropped so the UI can show the
    polarity readout on screen.

    Degrades to an empty set (never an error body that flips the UI to a
    false 'live' state) on any failure or fresh DB.
    """
    import time as _time

    now = int(_time.time())
    empty = {"now": now, "excluded_self": 0, "sessions": []}

    # Polarity: durable read key (project_slug) + cheap session-id backstop.
    _sm_slugs_raw = os.environ.get("BRIDGE_SM_PROJECT_SLUGS", "streamManager")
    sm_slugs = {s.strip() for s in _sm_slugs_raw.split(",") if s.strip()}
    sm_own_sid = os.environ.get("SM_OWN_SESSION_ID", "").strip()

    try:
        conn = _open()
    except Exception:
        log.exception("health-digest: open failed")
        return empty

    try:
        # session columns (older DBs predate hitl_mode / hitl_floor).
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        has_hitl = "hitl_mode" in cols
        sel = (
            "id, project_slug, pid, started_at, ended_at, hitl_mode"
            if has_hitl
            else "id, project_slug, pid, started_at, ended_at"
        )
        sess_rows = conn.execute(
            f"SELECT {sel} FROM sessions ORDER BY started_at DESC LIMIT ?",
            (min(max(int(limit or 20), 1), 50),),
        ).fetchall()

        has_agents = _has_agents_table(conn)
        has_hitl_tbl = _has_table(conn, "hitl_pending")

        out: list[dict] = []
        excluded_self = 0
        for sr in sess_rows:
            sid = sr["id"]
            slug = (sr["project_slug"] or "").strip()
            # POLARITY filter -- durable slug key + session-id backstop.
            if slug in sm_slugs or (sm_own_sid and sid == sm_own_sid):
                excluded_self += 1
                continue

            started = sr["started_at"]
            ended = sr["ended_at"]
            ref = ended if ended is not None else now
            uptime = 0
            try:
                if started is not None:
                    uptime = max(0, int(float(ref) - float(started)))
            except Exception:
                uptime = 0

            # decision_count + latest_decision (decisions JOIN messages on sid)
            dec_count = 0
            latest_decision = None
            try:
                dec_count = conn.execute(
                    "SELECT COUNT(*) FROM decisions d "
                    "JOIN messages m ON d.message_id = m.id "
                    "WHERE m.session_id = ?",
                    (sid,),
                ).fetchone()[0]
                ld = conn.execute(
                    "SELECT d.action, d.confidence, d.timestamp "
                    "FROM decisions d JOIN messages m ON d.message_id = m.id "
                    "WHERE m.session_id = ? "
                    "ORDER BY d.timestamp DESC LIMIT 1",
                    (sid,),
                ).fetchone()
                if ld is not None:
                    latest_decision = {
                        "action": str(ld["action"] or "").upper(),
                        "confidence": float(ld["confidence"] or 0.0),
                        "agent_id": "",
                        "timestamp": int(float(ld["timestamp"] or 0)),
                    }
            except Exception:
                dec_count = int(dec_count or 0)
                latest_decision = latest_decision or None

            # active_agent_count + a recent agent's id for the latest decision
            agent_count = 0
            if has_agents:
                try:
                    agent_count = conn.execute(
                        "SELECT COUNT(*) FROM agents WHERE session_id = ?",
                        (sid,),
                    ).fetchone()[0]
                    if latest_decision is not None:
                        arow = conn.execute(
                            "SELECT profile_slug FROM agents "
                            "WHERE session_id = ? ORDER BY last_seen DESC LIMIT 1",
                            (sid,),
                        ).fetchone()
                        if arow is not None:
                            latest_decision["agent_id"] = str(
                                arow["profile_slug"] or ""
                            )
                except Exception:
                    agent_count = int(agent_count or 0)

            # hitl_pending_count (hitl_pending JOIN messages on sid, unresolved)
            hitl_pending = 0
            if has_hitl_tbl:
                try:
                    hitl_pending = conn.execute(
                        "SELECT COUNT(*) FROM hitl_pending hp "
                        "JOIN messages m ON hp.message_id = m.id "
                        "WHERE hp.resolved_at IS NULL AND m.session_id = ?",
                        (sid,),
                    ).fetchone()[0]
                except Exception:
                    hitl_pending = int(hitl_pending or 0)

            # active_job_count -- best-effort via the lifecycle bridge.
            active_jobs = 0
            try:
                from stream_manager.lifecycle_bridge import list_active_jobs
                jobs = list_active_jobs(
                    db_path=str(DB_PATH), session_id=sid, limit=500
                )
                active_jobs = len(jobs)
            except Exception:
                active_jobs = 0

            hitl_mode = (
                str(sr["hitl_mode"]).upper()
                if has_hitl and sr["hitl_mode"]
                else "ASYNC"
            )

            out.append(
                {
                    "session_id": sid,
                    "project_slug": slug or str(sid),
                    "started_at": started,
                    "ended_at": ended,
                    "uptime_seconds": uptime,
                    "decision_count": int(dec_count or 0),
                    "latest_decision": latest_decision,
                    "active_agent_count": int(agent_count or 0),
                    "active_job_count": int(active_jobs or 0),
                    "hitl_pending_count": int(hitl_pending or 0),
                    "hitl_mode": hitl_mode,
                    # No escalation table exists in the schema; the field is
                    # part of the contract but degrades to None for live data
                    # (variance state is reachable only via mock until an
                    # escalation source lands -- never fabricated here).
                    "latest_escalation": None,
                }
            )

        conn.close()
        return {"now": now, "excluded_self": excluded_self, "sessions": out}
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        log.exception("health-digest: aggregation failed")
        return empty


# ===================== BETA #health-sparklines : health-sparklines =====================

# --- GET /api/sessions/{session_id}/sparkline-data ---
@app.get("/api/sessions/{session_id}/sparkline-data")
async def api_session_sparkline_data(session_id: str, limit: int = 100):
    """BETA #34 health-sparklines drawer detail: the last N decisions for ONE
    session as {timestamp, confidence, action, trigger_reason, throughput}[],
    newest-first.

    READ-ONLY + additive. Touches NO FROZEN surface (no governance.py, no
    message_bus schema change, no new bus envelope). Joins decisions + messages
    + sessions and defensively left-joins hitl_pending for trigger_reason.

    POLARITY (G2 / no-self-monitor): returns ZERO rows when the session's
    project_slug is in the SM exclusion set (BRIDGE_SM_PROJECT_SLUGS, default
    {streamManager}) OR the session_id equals SM_OWN_SESSION_ID. The exclusion
    is the DURABLE read key (project_slug) plus a session-id backstop -- mirrors
    the CLAUDE.md polarity split.

    Degrades to an empty row set on any error (never 500 / stack leak).
    """
    try:
        n = max(1, min(int(limit or 100), 200))
    except Exception:
        n = 100

    # SM self-exclusion keys.
    sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
    _sm_slugs_raw = os.environ.get("BRIDGE_SM_PROJECT_SLUGS", "streamManager")
    sm_slugs = frozenset(s.strip() for s in _sm_slugs_raw.split(",") if s.strip())

    empty = {"session_id": session_id, "count": 0, "mock": False, "rows": []}

    # Session-id backstop: never serve the SM own session.
    if sm_own and session_id == sm_own:
        return empty

    try:
        conn = _open()
        # Durable read-side polarity key: resolve the session's project_slug and
        # drop it if it is in the SM exclusion set. A missing session row simply
        # yields no decisions below (empty), which is the correct safe default.
        try:
            srow = conn.execute(
                "SELECT project_slug FROM sessions WHERE id = ? LIMIT 1",
                (session_id,),
            ).fetchone()
        except Exception:
            srow = None
        if srow is not None:
            slug = (srow["project_slug"] if isinstance(srow, sqlite3.Row) else srow[0]) or ""
            if str(slug).strip() in sm_slugs:
                conn.close()
                return empty

        action_expr = "d.action"
        # trigger_reason lives on hitl_pending; left-join when present.
        has_hitl = _has_table(conn, "hitl_pending")
        if has_hitl:
            trig_expr = (
                "(SELECT hp.trigger_reason FROM hitl_pending hp "
                "WHERE hp.message_id = d.message_id ORDER BY hp.id DESC LIMIT 1)"
            )
        else:
            trig_expr = "NULL"
        conf_expr = "COALESCE(d.confidence, 0.0)"

        sql = (
            "SELECT d.rowid AS rid, d.timestamp AS timestamp, "
            f"{conf_expr} AS confidence, {action_expr} AS action, "
            f"{trig_expr} AS trigger_reason "
            "FROM decisions d JOIN messages m ON d.message_id = m.id "
            "WHERE m.session_id = ? "
            "ORDER BY d.rowid DESC LIMIT ?"
        )
        rows = conn.execute(sql, (session_id, n)).fetchall()
        conn.close()
    except Exception:
        # Detail goes to the server log, not the response body (no path / SQL leak).
        log.exception("sparkline-data: query failed")
        return empty

    # Derive a coarse per-row THROUGHPUT proxy from inter-arrival gaps. rows are
    # newest-first; compute gaps in chronological order then map back. Smaller
    # gap => higher throughput. This is the SECONDARY (shape-only) trace -- never
    # a severity signal. No timestamps => a gentle steady baseline.
    chron = list(reversed([dict(r) for r in rows]))
    ts = [float(r["timestamp"]) for r in chron if r.get("timestamp") is not None]
    thru_by_idx: dict[int, float] = {}
    if len(ts) >= 2:
        gaps = []
        for i in range(1, len(chron)):
            a = chron[i - 1].get("timestamp")
            b = chron[i].get("timestamp")
            if a is not None and b is not None:
                gaps.append(max(0.0, float(b) - float(a)))
            else:
                gaps.append(None)
        valid = [g for g in gaps if g is not None]
        max_gap = max(1.0, max(valid)) if valid else 1.0
        # first chron row has no predecessor: seed with a mid baseline.
        thru_by_idx[0] = 0.4
        for i, g in enumerate(gaps, start=1):
            if g is None:
                thru_by_idx[i] = 0.4
            else:
                thru_by_idx[i] = max(0.0, min(1.0, 1.0 - g / max_gap)) * 0.85 + 0.1
    else:
        for i in range(len(chron)):
            thru_by_idx[i] = 0.4

    out = []
    for i, r in enumerate(chron):
        out.append(
            {
                "timestamp": float(r["timestamp"]) if r.get("timestamp") is not None else 0.0,
                "confidence": round(float(r.get("confidence") or 0.0), 4),
                "action": r.get("action") or "",
                "trigger_reason": r.get("trigger_reason"),
                "throughput": round(float(thru_by_idx.get(i, 0.4)), 4),
            }
        )
    # newest-first to match the live decisionsStore / /api/decisions contract.
    out.reverse()
    return {"session_id": session_id, "count": len(out), "mock": False, "rows": out}


# ===================== BETA #stale-cleanup : stale-cleanup =====================

# --- GET /api/sessions/stale ---
# --- BETA #46 stale-session cleanup: additive, soft-delete-only, no FROZEN touch ---
# Reuses the existing _open_rw() / _reject_sm_own() / _iso_now() helpers. The
# sessions.deleted_at column is added lazily + guarded (no-op when present).

def _sm_own_slugs() -> set[str]:
    """SM-self project_slug set (polarity G2). Mirrors message_bus.py: env
    BRIDGE_SM_PROJECT_SLUGS (comma-separated), default {\"streamManager\"}.
    Lowercased for case-insensitive compare."""
    raw = os.environ.get("BRIDGE_SM_PROJECT_SLUGS", "streamManager")
    return {s.strip().lower() for s in raw.split(",") if s.strip()}


def _ensure_sessions_deleted_at(conn: sqlite3.Connection) -> None:
    """Guarded additive ALTER: add sessions.deleted_at if missing. SQLite lacks
    ADD COLUMN IF NOT EXISTS, so check table_info first. Idempotent."""
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
        if "deleted_at" not in cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN deleted_at REAL")
    except Exception:
        log.exception("stale-cleanup: ensure deleted_at column failed")


@app.get("/api/sessions/stale")
async def api_sessions_stale(older_than_hours: float = 24.0):
    """Preview the stale (ended past the window, not already archived) NON-SM
    sessions eligible for soft-delete. Read-only -- modifies NOTHING.

    Polarity (G2/M15): rows whose project_slug is in the SM-own slug set are
    EXCLUDED in the SQL WHERE; the SM_OWN_SESSION_ID row is excluded too. Each
    returned row carries the cascade counts (messages / decisions) + open-HITL
    count so the operator sees exactly what an archive would soft-delete.
    Degrades to an empty list (never an error a client could misread).
    """
    try:
        hrs = max(0.0, float(older_than_hours))
    except Exception:
        hrs = 24.0
    cutoff = time.time() - hrs * 3600.0
    sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
    slugs = _sm_own_slugs()
    try:
        conn = _open_rw()
        _ensure_sessions_deleted_at(conn)
        rows = conn.execute(
            "SELECT id, project_slug, pid, started_at, ended_at "
            "FROM sessions "
            "WHERE ended_at IS NOT NULL AND ended_at < ? "
            "AND deleted_at IS NULL "
            "ORDER BY ended_at ASC LIMIT 200",
            (cutoff,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            slug = str(d.get("project_slug") or "").strip().lower()
            # Polarity self-exclude (G2): never present SM-self as archivable.
            if slug in slugs:
                continue
            if sm_own and str(d.get("id")) == sm_own:
                continue
            sid = d["id"]
            try:
                mc = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE session_id = ?", (sid,)
                ).fetchone()[0]
            except Exception:
                mc = 0
            # decisions has no session_id -> join via messages.
            try:
                dc = conn.execute(
                    "SELECT COUNT(*) FROM decisions d "
                    "JOIN messages m ON d.message_id = m.id "
                    "WHERE m.session_id = ?",
                    (sid,),
                ).fetchone()[0]
            except Exception:
                dc = 0
            # open HITL rows (absolute HITL gate -> 'protected') via message join.
            try:
                oh = conn.execute(
                    "SELECT COUNT(*) FROM hitl_pending hp "
                    "JOIN messages m ON hp.message_id = m.id "
                    "WHERE m.session_id = ? AND hp.resolved_at IS NULL",
                    (sid,),
                ).fetchone()[0]
            except Exception:
                oh = 0
            ended = d.get("ended_at")
            try:
                ended_hours_ago = (
                    (time.time() - float(ended)) / 3600.0 if ended is not None else None
                )
            except Exception:
                ended_hours_ago = None
            out.append({
                "id": sid,
                "project_slug": d.get("project_slug") or "",
                "pid": d.get("pid"),
                "ended_hours_ago": ended_hours_ago,
                "message_count": int(mc),
                "decision_count": int(dc),
                "open_hitl": int(oh),
            })
        conn.close()
        return {"sessions": out, "older_than_hours": hrs, "own_session_id": sm_own or None}
    except Exception:
        log.exception("stale-cleanup: preview failed; degrading to empty")
        return {"sessions": [], "older_than_hours": hrs, "own_session_id": None}

# --- POST /api/sessions/{session_id}/archive ---
@app.post("/api/sessions/{session_id}/archive")
async def api_session_archive(session_id: str):
    """Soft-delete (archive) one session: set sessions.deleted_at to now if it is
    currently NULL. REVERSIBLE -- never a hard DELETE; no cascade row is removed,
    so audit/forensic replay survives. Refuses SM-self (HTTP 400) by both
    SM_OWN_SESSION_ID and project_slug (polarity G2). Idempotent: archiving an
    already-archived session is a no-op success.
    """
    if not isinstance(session_id, str) or not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    _reject_sm_own(session_id)  # HTTP 400 if session_id == SM_OWN_SESSION_ID
    slugs = _sm_own_slugs()
    try:
        conn = _open_rw()
        _ensure_sessions_deleted_at(conn)
        row = conn.execute(
            "SELECT id, project_slug, deleted_at FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            conn.close()
            raise HTTPException(status_code=404, detail="session not found")
        slug = str(row["project_slug"] or "").strip().lower()
        if slug in slugs:
            conn.close()
            raise HTTPException(status_code=400, detail="refusing to archive SM-self session")
        if row["deleted_at"] is not None:
            conn.close()
            return {"id": session_id, "archived": True, "already": True}
        conn.execute(
            "UPDATE sessions SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
            (time.time(), session_id),
        )
        conn.close()
        return {"id": session_id, "archived": True, "archived_at": _iso_now()}
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("stale-cleanup: archive failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

# --- POST /api/sessions/{session_id}/restore ---
@app.post("/api/sessions/{session_id}/restore")
async def api_session_restore(session_id: str):
    """Restore (un-archive) one soft-deleted session: clear sessions.deleted_at.
    The reverse of /archive -- the lane returns to the rail. Refuses SM-self by
    SM_OWN_SESSION_ID + project_slug (polarity G2). Idempotent: restoring a
    not-archived session is a no-op success.
    """
    if not isinstance(session_id, str) or not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    _reject_sm_own(session_id)
    slugs = _sm_own_slugs()
    try:
        conn = _open_rw()
        _ensure_sessions_deleted_at(conn)
        row = conn.execute(
            "SELECT id, project_slug FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            conn.close()
            raise HTTPException(status_code=404, detail="session not found")
        slug = str(row["project_slug"] or "").strip().lower()
        if slug in slugs:
            conn.close()
            raise HTTPException(status_code=400, detail="refusing to act on SM-self session")
        conn.execute(
            "UPDATE sessions SET deleted_at = NULL WHERE id = ?",
            (session_id,),
        )
        conn.close()
        return {"id": session_id, "archived": False, "restored_at": _iso_now()}
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("stale-cleanup: restore failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ===================== BETA #undefined : event-cursor =====================

# --- GET /api/sessions/{session_id}/events ---
# ===================== BETA #event-cursor : event-cursor (#31) =====================

# --- GET /api/sessions/{session_id}/events?since=<cursor>&full=0|1 ---
# Additive read-only resume endpoint for the BETA durable session event cursor.
# Reads EXISTING decisions + messages rows newer than the client's last-seen
# cursor and returns them so the browser can resume the feed across a refresh.
# Touches NO FROZEN surface: no governance.py, NO message_bus.py edit, NO new
# message_bus method, NO schema change (no new table / column), NO new bus
# envelope. Reuses the existing _open() / _has_table() helpers and the same
# decisions JOIN messages idiom + polarity self-exclude the sparkline endpoint
# uses.
#
# CURSOR: the compound watermark d{decisions.rowid}:m{messages.rowid} -- the same
# id: / Last-Event-ID shape the /events SSE stream already emits. The decision
# rowid is the load-bearing pagination key (events strictly newer than it).
#
# POLARITY (G2/M15): an SM-self scope returns ZERO events. The session's
# project_slug is resolved and dropped if it is in the SM exclusion set
# (BRIDGE_SM_PROJECT_SLUGS, default {streamManager}) -- the DURABLE read key --
# and the session_id == SM_OWN_SESSION_ID backstop short-circuits first. Mirrors
# the no-self-monitor floor.
@app.get("/api/sessions/{session_id}/events")
async def api_session_events(session_id: str, since: str = "", full: int = 0):
    """Resume the session event stream from a client cursor. Returns events
    (decision rows joined to their message) strictly newer than the cursor's
    decision rowid, capped at 100, oldest-first so the client folds them in
    chronological order. ?full=1 additionally returns the accumulated digest at
    the cursor (decision_count / block_count / pending_hitl_count / latest_action)
    for a cold-start / checkpoint load. Read-only -- modifies NOTHING.

    Degrades to an empty event list on any error / fresh DB (never a 500 / stack
    leak). `truncated` is true when the gap exceeded the 100-row page so the
    client surfaces a RESEEDED state instead of silently dropping events.
    """
    empty = {
        "session_id": session_id,
        "since": since or "",
        "cursor": since or "",
        "count": 0,
        "truncated": False,
        "events": [],
        "digest": None,
    }

    # SM self-exclusion keys (polarity G2).
    sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
    _sm_slugs_raw = os.environ.get("BRIDGE_SM_PROJECT_SLUGS", "streamManager")
    sm_slugs = frozenset(s.strip().lower() for s in _sm_slugs_raw.split(",") if s.strip())

    # Session-id backstop: never serve the SM own session.
    if sm_own and session_id == sm_own:
        return empty

    # Parse the compound cursor d{n}:m{n}; tolerate an absent/garbage cursor as
    # "from the beginning" (since_decision_rowid = 0).
    since_d = 0
    try:
        import re as _re
        mm = _re.match(r"^d(\d+):m(\d+)$", (since or "").strip())
        if mm:
            since_d = int(mm.group(1))
    except Exception:
        since_d = 0

    cap = 100
    try:
        conn = _open()
        # Durable read-side polarity key: resolve the session's project_slug and
        # drop it if it is in the SM exclusion set. A missing session row yields
        # no events below (empty), the correct safe default.
        try:
            srow = conn.execute(
                "SELECT project_slug FROM sessions WHERE id = ? LIMIT 1",
                (session_id,),
            ).fetchone()
        except Exception:
            srow = None
        if srow is not None:
            slug = (srow["project_slug"] if isinstance(srow, sqlite3.Row) else srow[0]) or ""
            if str(slug).strip().lower() in sm_slugs:
                conn.close()
                return empty

        has_routing = _has_decision_routing_cols(conn)
        model_expr = (
            "COALESCE(d.model_used, '') AS model_used" if has_routing else "'' AS model_used"
        )
        layer_expr = "COALESCE(d.layer, 0) AS layer" if has_routing else "0 AS layer"

        sql = (
            "SELECT d.rowid AS rid, d.id AS id, d.message_id AS message_id, "
            "d.action AS action, COALESCE(d.confidence, 0.0) AS confidence, "
            "d.timestamp AS timestamp, "
            f"{model_expr}, {layer_expr}, "
            "m.rowid AS message_rid, m.session_id AS session_id, m.direction AS direction "
            "FROM decisions d JOIN messages m ON d.message_id = m.id "
            "WHERE m.session_id = ? AND d.rowid > ? "
            "ORDER BY d.rowid ASC LIMIT ?"
        )
        # Fetch cap+1 so we can detect truncation without a second COUNT query.
        rows = conn.execute(sql, (session_id, since_d, cap + 1)).fetchall()
        truncated = len(rows) > cap
        rows = rows[:cap]

        events = []
        for r in rows:
            d = dict(r)
            events.append({
                "rid": int(d.get("rid") or 0),
                "id": d.get("id"),
                "message_id": d.get("message_id"),
                "message_rid": int(d.get("message_rid") or 0),
                "action": d.get("action") or "",
                "confidence": round(float(d.get("confidence") or 0.0), 4),
                "layer": int(d.get("layer") or 0),
                "model_used": d.get("model_used") or "",
                "session_id": d.get("session_id"),
                "direction": d.get("direction"),
                "timestamp": float(d.get("timestamp") or 0.0),
            })

        # New watermark = the max decision rowid we returned (or the request
        # cursor when there was no gap), paired with the max message rowid.
        max_d = max((e["rid"] for e in events), default=since_d)
        max_m = max((e["message_rid"] for e in events), default=0)
        cursor = f"d{max_d}:m{max_m}"

        digest = None
        if int(full or 0) == 1:
            # full=1: the accumulated digest AT the watermark (cold-start /
            # checkpoint load). Counts are scoped to this session, polarity
            # already enforced above.
            try:
                dc = conn.execute(
                    "SELECT COUNT(*) FROM decisions d JOIN messages m "
                    "ON d.message_id = m.id WHERE m.session_id = ?",
                    (session_id,),
                ).fetchone()[0]
            except Exception:
                dc = 0
            try:
                bc = conn.execute(
                    "SELECT COUNT(*) FROM decisions d JOIN messages m "
                    "ON d.message_id = m.id WHERE m.session_id = ? AND d.action = 'BLOCK'",
                    (session_id,),
                ).fetchone()[0]
            except Exception:
                bc = 0
            ph = 0
            if _has_table(conn, "hitl_pending"):
                try:
                    ph = conn.execute(
                        "SELECT COUNT(*) FROM hitl_pending hp JOIN messages m "
                        "ON hp.message_id = m.id "
                        "WHERE m.session_id = ? AND hp.resolved_at IS NULL",
                        (session_id,),
                    ).fetchone()[0]
                except Exception:
                    ph = 0
            try:
                la_row = conn.execute(
                    "SELECT d.action FROM decisions d JOIN messages m "
                    "ON d.message_id = m.id WHERE m.session_id = ? "
                    "ORDER BY d.rowid DESC LIMIT 1",
                    (session_id,),
                ).fetchone()
            except Exception:
                la_row = None
            digest = {
                "decision_count": int(dc or 0),
                "block_count": int(bc or 0),
                "pending_hitl_count": int(ph or 0),
                "latest_action": (la_row[0] if la_row else None),
            }

        conn.close()
        return {
            "session_id": session_id,
            "since": since or "",
            "cursor": cursor,
            "count": len(events),
            "truncated": bool(truncated),
            "events": events,
            "digest": digest,
        }
    except Exception:
        # Detail to the server log, not the response body (no path / SQL leak).
        log.exception("event-cursor: events query failed; degrading to empty")
        return empty


# ===================== BETA #undefined : soak-panel =====================

# --- GET /api/soak/sessions ---
# ===================== BETA #soak-panel : live-session soak selector =====================
# Additive READ-ONLY endpoints. NO FROZEN touch: no governance.py, no
# message_bus schema change, no new bus envelope, no in-process soak spawn. The
# soak_runs table is additive + created lazily; the row writer is the
# out-of-process soak_driver --live-session (CLI / main thread), never the
# dashboard. Polarity (G2): every session query EXCLUDES SM-self (project_slug
# NOT IN the SM slug set AND session_id != SM_OWN_SESSION_ID). Firewall (G1): a
# candidate cwd containing a firewalled fragment is rejected; no certPortal path
# is ever read.

# Firewalled cwd fragments (G1). Configuration, not target vocabulary -- a cwd
# containing any of these (case-insensitive) is an off-limits monitored-project
# working dir and is rejected from the selector. Overridable via env.
_SOAK_FIREWALL_CWD_FRAGMENTS = [
    f.strip().lower()
    for f in os.environ.get("SM_SOAK_FIREWALL_CWD_FRAGMENTS", "certportal").split(",")
    if f.strip()
]


def _soak_cwd_is_firewalled(cwd: object) -> bool:
    """True when a candidate cwd contains a firewalled monitored-project path
    fragment (G1 firewall). Empty/None cwd is never firewalled."""
    s = str(cwd or "").strip().lower()
    if not s:
        return False
    return any(frag and frag in s for frag in _SOAK_FIREWALL_CWD_FRAGMENTS)


@app.get("/api/soak/sessions")
async def api_soak_sessions(limit: int = 20):
    """Ranked, SELF-EXCLUDED, firewall-filtered NON-SM candidate sessions for the
    BETA soak-panel live-soak selector (#16). Read-only -- modifies NOTHING.

    Ranking: (busy_score DESC, recency ASC). busy_score = the session's decision
    count (a cheap activity proxy); recency = seconds since the latest decision.
    Sourced from gov.db sessions/decisions; cwd is sourced (best-effort) from the
    SessionWatcher external-session snapshot when available (gov.db has no cwd
    column) so the firewall filter can run -- a candidate with no known cwd is
    kept (the durable project_slug + session_id self-exclude still applies).

    Polarity (G2/M15): rows whose project_slug is in the SM-own slug set are
    EXCLUDED (durable read key) and the SM_OWN_SESSION_ID row is excluded too
    (session backstop). The dropped tallies are returned as excluded_self /
    excluded_firewalled so the UI renders self-exclusion as a VISIBLE feature.
    Degrades to an empty shape on any error (never a 500 a client could misread).
    """
    try:
        lim = max(1, min(100, int(limit)))
    except Exception:
        lim = 20
    sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
    slugs = _sm_own_slugs()
    now = time.time()
    # Best-effort cwd map from the watcher (gov.db has no cwd column). Keyed by
    # session id; missing watcher / errors => empty map (firewall still applies
    # to any cwd we DO learn; unknown-cwd candidates are kept).
    cwd_by_sid: dict[str, str] = {}
    try:
        from stream_manager.session_watcher import get_session_watcher
        watcher = get_session_watcher()
        if watcher is not None:
            for s in watcher.list_active_sessions() or []:
                sid = s.get("sessionId") or s.get("session_id")
                if sid:
                    cwd_by_sid[str(sid)] = str(s.get("cwd") or "")
    except Exception:
        cwd_by_sid = {}
    excluded_self = 0
    excluded_firewalled = 0
    out: list[dict] = []
    try:
        conn = _open()
        if not _has_table(conn, "sessions"):
            conn.close()
            return {
                "sessions": [], "excluded_self": 0,
                "excluded_firewalled": 0, "own_session_id": sm_own or None,
            }
        rows = conn.execute(
            "SELECT id, project_slug, pid, started_at, ended_at "
            "FROM sessions ORDER BY started_at DESC LIMIT 400"
        ).fetchall()
        for r in rows:
            d = dict(r)
            sid = str(d.get("id"))
            slug = str(d.get("project_slug") or "").strip().lower()
            # Polarity self-exclude (G2): never present SM-self as a soak target.
            if slug in slugs or (sm_own and sid == sm_own):
                excluded_self += 1
                continue
            cwd = cwd_by_sid.get(sid, "")
            # Firewall (G1): reject an off-limits monitored-project cwd.
            if _soak_cwd_is_firewalled(cwd):
                excluded_firewalled += 1
                continue
            # busy_score = decision count; recency = secs since latest decision.
            try:
                dc = conn.execute(
                    "SELECT COUNT(*) FROM decisions d "
                    "JOIN messages m ON d.message_id = m.id "
                    "WHERE m.session_id = ?",
                    (sid,),
                ).fetchone()[0]
            except Exception:
                dc = 0
            try:
                last_ts = conn.execute(
                    "SELECT MAX(d.timestamp) FROM decisions d "
                    "JOIN messages m ON d.message_id = m.id "
                    "WHERE m.session_id = ?",
                    (sid,),
                ).fetchone()[0]
            except Exception:
                last_ts = None
            try:
                last_secs = (now - float(last_ts)) if last_ts is not None else None
            except Exception:
                last_secs = None
            out.append({
                "session_id": sid,
                "project_slug": d.get("project_slug") or "",
                "cwd": cwd,
                "busy": int(dc),
                "last_seen_secs_ago": (None if last_secs is None else max(0.0, last_secs)),
            })
        conn.close()
    except Exception:
        log.exception("soak-panel: sessions preview failed; degrading to empty")
        return {
            "sessions": [], "excluded_self": 0,
            "excluded_firewalled": 0, "own_session_id": sm_own or None,
        }
    # Rank: busy DESC, then most-recent (smallest last_seen) first. None recency
    # sorts last.
    def _rank_key(c):
        rec = c.get("last_seen_secs_ago")
        rec = float(rec) if isinstance(rec, (int, float)) else float("inf")
        return (-int(c.get("busy") or 0), rec)
    out.sort(key=_rank_key)
    return {
        "sessions": out[:lim],
        "excluded_self": excluded_self,
        "excluded_firewalled": excluded_firewalled,
        "own_session_id": sm_own or None,
    }

# --- GET /api/soak/status ---
def _ensure_soak_runs(conn: sqlite3.Connection) -> None:
    """Guarded additive CREATE: make the soak_runs table if missing. Idempotent
    (CREATE TABLE IF NOT EXISTS). Additive -- no FROZEN surface touched. The
    dashboard only READS this table; the row writer is the out-of-process
    soak_driver --live-session (CLI / main thread)."""
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS soak_runs ("
            "soak_id TEXT PRIMARY KEY, session_id TEXT, project_slug TEXT, "
            "started_at REAL, status TEXT, polarity_pass INTEGER, "
            "rejection_count INTEGER, report_md TEXT)"
        )
    except Exception:
        log.exception("soak-panel: ensure soak_runs table failed")


@app.get("/api/soak/status")
async def api_soak_status(limit: int = 10):
    """Read the additive soak_runs table (newest-first) for the BETA soak-panel
    report readout (#16). Read-only. Creates the table lazily (guarded) so a
    fresh DB returns { runs: [] } with HTTP 200 -- never a 500. Each row carries
    soak_id / session_id / project_slug / started_at / status / polarity_pass /
    rejection_count / report_md verbatim. The component parses report_md into a
    per-band p50/p95 table; an empty table => the component falls back to mock.
    """
    try:
        lim = max(1, min(50, int(limit)))
    except Exception:
        lim = 10
    try:
        conn = _open_rw()
        _ensure_soak_runs(conn)
        rows = conn.execute(
            "SELECT soak_id, session_id, project_slug, started_at, status, "
            "polarity_pass, rejection_count, report_md "
            "FROM soak_runs ORDER BY started_at DESC LIMIT ?",
            (lim,),
        ).fetchall()
        conn.close()
        return {"runs": [dict(r) for r in rows]}
    except Exception:
        log.exception("soak-panel: status read failed; degrading to empty")
        return {"runs": []}

# --- GET /api/soak/polarity-audit ---
@app.get("/api/soak/polarity-audit")
async def api_soak_polarity_audit():
    """READ computation over gov.db proving ZERO SM-self leakage for the BETA
    soak-panel polarity verdict (#16). Read-only -- modifies NOTHING.

    Counts decision rows whose joined session is SM-self: project_slug IS IN the
    SM exclusion set (durable read key) OR session_id == SM_OWN_SESSION_ID
    (session backstop). A non-zero count means a self row leaked past the
    self-exclude WHERE-clause used everywhere else -- a polarity FAIL. checked =
    the total decision rows inspected. pass === (leak_count == 0).

    Degrades to a SAFE-but-explicit shape on error: { pass:false, leak_count:0,
    checked:0 } -- the component reads a non-boolean/empty as 'fall back to mock'
    rather than treating a server-down condition as a live PASS.
    """
    sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
    slugs = _sm_own_slugs()
    try:
        conn = _open()
        if not _has_table(conn, "sessions") or not _has_table(conn, "decisions"):
            conn.close()
            return {"pass": True, "leak_count": 0, "checked": 0}
        try:
            checked = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        except Exception:
            checked = 0
        leak = 0
        params: list = []
        clauses: list[str] = []
        if slugs:
            placeholders = ",".join("?" for _ in slugs)
            clauses.append("LOWER(s.project_slug) IN (" + placeholders + ")")
            params.extend(slugs)
        if sm_own:
            clauses.append("m.session_id = ?")
            params.append(sm_own)
        if clauses:
            try:
                leak = conn.execute(
                    "SELECT COUNT(*) FROM decisions d "
                    "JOIN messages m ON d.message_id = m.id "
                    "LEFT JOIN sessions s ON m.session_id = s.id "
                    "WHERE " + " OR ".join(clauses),
                    tuple(params),
                ).fetchone()[0]
            except Exception:
                leak = 0
        conn.close()
        return {"pass": int(leak) == 0, "leak_count": int(leak), "checked": int(checked)}
    except Exception:
        log.exception("soak-panel: polarity audit failed")
        return {"pass": False, "leak_count": 0, "checked": 0}


# ============= BETA #undefined : ambient-soak-task =============

# --- GET /api/ambient/soak-status ---
# ===========================================================================
# BETA feature "ambient-soak-task" (#2): additive READ endpoints over the
# additive ambient_runs table. The table is created lazily (guarded CREATE TABLE
# IF NOT EXISTS); the row writer is the out-of-process operator/main-thread Cron
# job (soak_driver --mode ambient), NEVER the dashboard. CONSTRAINED ADDITIVE: no
# FROZEN surface touched, no new bus envelope, no message_bus schema change. The
# polarity verdict is a READ attribute of each ambient_runs row.
#
# Polarity (G2): every session/run query EXCLUDES SM-self -- project_slug NOT IN
# the SM slug set (_sm_own_slugs(), durable read key) AND session_id !=
# SM_OWN_SESSION_ID (session backstop) -- and surfaces the dropped tally as
# excluded_self so self-exclusion is a VISIBLE feature, not a silent filter.
def _ensure_ambient_runs(conn: sqlite3.Connection) -> None:
    """Guarded additive CREATE: make the ambient_runs table if missing.
    Idempotent (CREATE TABLE IF NOT EXISTS). Additive -- no FROZEN surface
    touched. The dashboard only READS this table; the row writer is the
    out-of-process soak_driver --mode ambient (CLI / main-thread Cron).

    Columns: ambient_id (PK), session_id, project_slug, ts (epoch seconds the
    run completed), polarity_pass (1/0), polarity_violation (1/0), coverage_gaps
    (JSON-encoded string[]), duration_s, messages_seen."""
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS ambient_runs ("
            "ambient_id TEXT PRIMARY KEY, session_id TEXT, project_slug TEXT, "
            "ts REAL, polarity_pass INTEGER, polarity_violation INTEGER, "
            "coverage_gaps TEXT, duration_s INTEGER, messages_seen INTEGER)"
        )
    except Exception:
        log.exception("ambient-soak-task: ensure ambient_runs table failed")


def _ambient_run_is_self(row: dict, sm_own: str, slugs: set[str]) -> bool:
    """Defense-in-depth self-exclude for an ambient_runs row (G2). True when the
    row's project_slug is in the SM slug set (durable read key) OR its session_id
    == SM_OWN_SESSION_ID (session backstop). Applied AFTER the SQL filter as a
    cheap belt-and-suspenders read backstop on the file-mediated synthetic path."""
    slug = str(row.get("project_slug") or "").strip().lower()
    if slug and slug in slugs:
        return True
    sid = str(row.get("session_id") or "")
    return bool(sm_own and sid == sm_own)


@app.get("/api/ambient/soak-status")
async def api_ambient_soak_status():
    """The latest ambient-soak verdict + cadence meta for the BETA ambient-soak-
    task footer chip (#2). Read-only -- modifies NOTHING. Creates the ambient_runs
    table lazily (guarded) so a fresh DB returns a SAFE empty-ish shape with HTTP
    200, never a 500.

    Returns:
      { enabled, last_run_at, last_run_ago_s, interval_minutes, verdict,
        history_count, excluded_self, own_session_id, mock }
    where verdict is "OK" | "WARN" | "NONE" derived from the freshest NON-SM run
    (polarity_violation OR a coverage_gap => WARN). last_run_ago_s is seconds
    since that run; history_count is the count of non-self ambient rows; mock is
    always false (the server never fabricates -- the component mocks when this
    returns the empty NONE shape).

    Polarity (G2): SM-self rows are excluded at the SQL WHERE (project_slug NOT
    IN the SM slug set) with the SM_OWN_SESSION_ID session backstop, and the
    dropped count is surfaced as excluded_self. interval_minutes is configuration
    (env SM_AMBIENT_INTERVAL_MINUTES, default 30) -- the cadence is set by the
    out-of-process Cron, not the dashboard.
    """
    sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
    slugs = _sm_own_slugs()
    try:
        interval = max(1, int(os.environ.get("SM_AMBIENT_INTERVAL_MINUTES", "30")))
    except Exception:
        interval = 30
    empty = {
        "enabled": False, "last_run_at": None, "last_run_ago_s": None,
        "interval_minutes": interval, "verdict": "NONE", "history_count": 0,
        "excluded_self": 0, "own_session_id": sm_own or None, "mock": False,
    }
    try:
        conn = _open_rw()
        _ensure_ambient_runs(conn)
        # Build the SM-self-excluding WHERE (durable read key + session backstop).
        clauses: list[str] = []
        params: list = []
        if slugs:
            placeholders = ",".join("?" for _ in slugs)
            clauses.append("LOWER(COALESCE(project_slug,'')) NOT IN (" + placeholders + ")")
            params.extend(slugs)
        if sm_own:
            clauses.append("COALESCE(session_id,'') != ?")
            params.append(sm_own)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        # Total non-self rows (history_count) + excluded_self tally.
        try:
            total_all = conn.execute("SELECT COUNT(*) FROM ambient_runs").fetchone()[0]
        except Exception:
            total_all = 0
        try:
            non_self = conn.execute(
                "SELECT COUNT(*) FROM ambient_runs" + where, tuple(params)
            ).fetchone()[0]
        except Exception:
            non_self = total_all
        excluded_self = max(0, int(total_all) - int(non_self))
        # The freshest NON-SM run drives the verdict.
        row = conn.execute(
            "SELECT ambient_id, session_id, project_slug, ts, polarity_pass, "
            "polarity_violation, coverage_gaps FROM ambient_runs" + where
            + " ORDER BY ts DESC LIMIT 1",
            tuple(params),
        ).fetchone()
        conn.close()
        if row is None or int(non_self) == 0:
            out = dict(empty)
            out["history_count"] = 0
            out["excluded_self"] = excluded_self
            return out
        d = dict(row)
        gaps_raw = d.get("coverage_gaps")
        gaps: list = []
        if isinstance(gaps_raw, str) and gaps_raw.strip():
            try:
                parsed = json.loads(gaps_raw)
                if isinstance(parsed, list):
                    gaps = parsed
            except Exception:
                gaps = [g.strip() for g in gaps_raw.split(",") if g.strip()]
        violated = (
            int(d.get("polarity_violation") or 0) == 1
            or int(d.get("polarity_pass") or 1) == 0
        )
        verdict = "WARN" if (violated or len(gaps) > 0) else "OK"
        try:
            last_ts = float(d.get("ts")) if d.get("ts") is not None else None
        except Exception:
            last_ts = None
        ago_s = None
        if last_ts is not None:
            ago_s = max(0.0, time.time() - last_ts)
        return {
            "enabled": True,
            "last_run_at": last_ts,
            "last_run_ago_s": ago_s,
            "interval_minutes": interval,
            "verdict": verdict,
            "history_count": int(non_self),
            "excluded_self": excluded_self,
            "own_session_id": sm_own or None,
            "mock": False,
        }
    except Exception:
        log.exception("ambient-soak-task: status read failed; degrading to empty")
        return empty

# --- GET /api/ambient/soak-history ---
@app.get("/api/ambient/soak-history")
async def api_ambient_soak_history(limit: int = 10):
    """The newest-first ambient-soak run ledger for the BETA ambient-soak-task
    drawer (#2). Read-only. Creates the ambient_runs table lazily (guarded) so a
    fresh DB returns { runs: [] } with HTTP 200 -- never a 500.

    Each row carries: ambient_id (as id), ts, session_id, project_slug,
    polarity_pass (1/0), polarity_violation (1/0), coverage_gaps (decoded to a
    string[]), duration_s, messages_seen. The component renders PASS/FAIL from
    polarity_pass and the amber tick + gap chips from polarity_violation /
    coverage_gaps. An empty table => the component falls back to mock.

    Polarity (G2): SM-self rows are EXCLUDED at the SQL WHERE (project_slug NOT
    IN the SM slug set, durable read key) with the SM_OWN_SESSION_ID session
    backstop, and a defense-in-depth Python backstop drops any self row that
    slips through. The dropped tally is surfaced as excluded_self so
    self-exclusion is a VISIBLE feature, not a silent filter.
    """
    try:
        lim = max(1, min(50, int(limit)))
    except Exception:
        lim = 10
    sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
    slugs = _sm_own_slugs()
    try:
        conn = _open_rw()
        _ensure_ambient_runs(conn)
        clauses: list[str] = []
        params: list = []
        if slugs:
            placeholders = ",".join("?" for _ in slugs)
            clauses.append("LOWER(COALESCE(project_slug,'')) NOT IN (" + placeholders + ")")
            params.extend(slugs)
        if sm_own:
            clauses.append("COALESCE(session_id,'') != ?")
            params.append(sm_own)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        try:
            total_all = conn.execute("SELECT COUNT(*) FROM ambient_runs").fetchone()[0]
        except Exception:
            total_all = 0
        rows = conn.execute(
            "SELECT ambient_id, session_id, project_slug, ts, polarity_pass, "
            "polarity_violation, coverage_gaps, duration_s, messages_seen "
            "FROM ambient_runs" + where + " ORDER BY ts DESC LIMIT ?",
            (*tuple(params), lim),
        ).fetchall()
        conn.close()
        out: list[dict] = []
        for r in rows:
            d = dict(r)
            # Defense-in-depth self-exclude backstop (G2) on the ephemeral key.
            if _ambient_run_is_self(d, sm_own, slugs):
                continue
            gaps_raw = d.get("coverage_gaps")
            gaps: list = []
            if isinstance(gaps_raw, str) and gaps_raw.strip():
                try:
                    parsed = json.loads(gaps_raw)
                    if isinstance(parsed, list):
                        gaps = [str(x) for x in parsed]
                except Exception:
                    gaps = [g.strip() for g in gaps_raw.split(",") if g.strip()]
            elif isinstance(gaps_raw, list):
                gaps = [str(x) for x in gaps_raw]
            out.append({
                "id": d.get("ambient_id"),
                "ts": d.get("ts"),
                "session_id": d.get("session_id") or "",
                "project_slug": d.get("project_slug") or "",
                "polarity_pass": int(d.get("polarity_pass") or 0),
                "polarity_violation": int(d.get("polarity_violation") or 0),
                "coverage_gaps": gaps,
                "duration_s": int(d.get("duration_s") or 0),
                "messages_seen": int(d.get("messages_seen") or 0),
            })
        excluded_self = max(0, int(total_all) - len(out))
        return {"runs": out, "excluded_self": excluded_self, "own_session_id": sm_own or None}
    except Exception:
        log.exception("ambient-soak-task: history read failed; degrading to empty")
        return {"runs": [], "excluded_self": 0, "own_session_id": sm_own or None}


# ============= BETA #undefined : breach-cartography-constrained =============

# --- GET /api/breach/cartography ---
# ===================== BETA #breach-cartography-constrained =====================
#
# Additive READ-ONLY endpoint backing the BETA feature
# "breach-cartography-constrained" (#5). CONSTRAINED v1: NO message_bus.py edit,
# NO new bus envelope, NO governance.py hook, NO ADR-18 amendment, NO in-process
# spawn/cron/subprocess. It traces the recent decisions in a session's regression
# run-up (decisions -> messages -> patterns) so the transient Breach Cartography
# modal can render the causal swimlane + heuristic-ranked surgical-revert list.
#
# POLARITY (G2 / M15): SM-self is excluded at the SQL WHERE on
# sessions.project_slug (durable read key: project_slug NOT IN the SM exclusion
# set, default {'streamManager'}, override via BRIDGE_SM_PROJECT_SLUGS) AND with
# the cheap m.session_id != SM_OWN_SESSION_ID backstop. A session whose slug is
# in the SM set, or whose id is the SM own-session id, can NEVER appear -> the
# UI then renders the polarity lockout and disables the revert accept.
#
# CONSTRAINED maturity: per-decision maturity snapshots require a FROZEN schema
# edit (deferred). v1 returns ONLY the coarse maturity_delta derived from the
# count of regressed cells the caller supplies (none here -> 0/empty), and the UI
# labels it as the RingDelta-only v1 deferral. Read-only, post-hoc (M18): ZERO
# writes, ZERO FROZEN-surface touch. Degrades to an empty {decisions:[],
# patterns:[]} payload on any error / fresh DB so the client falls back to mock.
@app.get("/api/breach/cartography")
async def api_breach_cartography(
    session_id: str | None = None,
    window_ms: int = 600000,
    limit: int = 200,
):
    """Trace the decision causation chain for a session's regression run-up.

    Returns {alert_ts, window_ms, session_id, project_slug, excluded_self,
    regressed_cells, maturity_delta:{cells,note}, decisions:[...], patterns:[...],
    mock:false}. `decisions` are the most-recent (capped) rows in the window for
    the scoped governed session, oldest-first; each carries {decision_id, action,
    confidence, message, matched_hash, timestamp, hitl_note}. `patterns` resolves
    each distinct matched_hash to {hash, level, occurrences, mature, label}. The
    revert ranking is computed CLIENT-side (pure heuristic) -- this endpoint only
    supplies the traced rows.
    """
    empty = {
        "alert_ts": None, "window_ms": int(window_ms or 600000),
        "session_id": session_id or "", "project_slug": "",
        "excluded_self": True, "regressed_cells": [],
        "maturity_delta": {"cells": 0, "note": ""},
        "decisions": [], "patterns": [], "mock": False,
    }
    try:
        win = int(window_ms) if int(window_ms or 0) > 0 else 600000
        cap = min(int(limit or 200), 500)
        sm_slugs_raw = os.environ.get("BRIDGE_SM_PROJECT_SLUGS", "streamManager")
        sm_slugs = [s.strip().lower() for s in sm_slugs_raw.split(",") if s.strip()]
        sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
        conn = _open()
        try:
            if not (_has_table(conn, "decisions") and _has_table(conn, "messages")):
                return empty
            has_sessions = _has_table(conn, "sessions")
            has_overrides = _has_table(conn, "hitl_overrides")
            # G2 self-exclude: drop any decision whose session is on an SM project
            # slug (durable read key) OR whose id is the SM own-session id (cheap
            # session backstop). LEFT JOIN keeps rows with no sessions-row (not self).
            where = []
            params: list = []
            if session_id:
                where.append("m.session_id = ?")
                params.append(session_id)
            if sm_slugs and has_sessions:
                placeholders = ",".join("?" for _ in sm_slugs)
                where.append(
                    "(s.project_slug IS NULL OR LOWER(s.project_slug) NOT IN ("
                    + placeholders + "))"
                )
                params.extend(sm_slugs)
            if sm_own:
                where.append("m.session_id != ?")
                params.append(sm_own)
            slug_sel = (
                "COALESCE(s.project_slug, '') AS project_slug "
                if has_sessions
                else "'' AS project_slug "
            )
            join_sessions = "LEFT JOIN sessions s ON s.id = m.session_id " if has_sessions else ""
            override_sel = (
                "(SELECT ho.note FROM hitl_overrides ho WHERE ho.decision_id = d.id "
                "ORDER BY ho.timestamp DESC LIMIT 1) AS hitl_note "
                if has_overrides else "'' AS hitl_note "
            )
            where_sql = ("WHERE " + " AND ".join(where)) if where else ""
            sql = (
                "SELECT d.id AS decision_id, d.action AS action, "
                "d.confidence AS confidence, d.matched_hash AS matched_hash, "
                "d.timestamp AS timestamp, d.reasoning AS reasoning, "
                "m.content AS content, m.session_id AS session_id, "
                + slug_sel + ", " + override_sel
                + "FROM decisions d "
                "JOIN messages m ON d.message_id = m.id "
                + join_sessions
                + where_sql
                + " ORDER BY d.timestamp DESC LIMIT ?"
            )
            params.append(cap)
            rows = [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]
            # newest-first from SQL -> reverse to oldest-first for the swimlane.
            rows.reverse()
            # Resolve the distinct matched hashes to pattern shelf nodes.
            hashes = sorted({
                (r.get("matched_hash") or "").strip()
                for r in rows
                if (r.get("matched_hash") or "").strip()
            })
            patterns = []
            if hashes and _has_table(conn, "patterns"):
                ph = ",".join("?" for _ in hashes)
                prows = conn.execute(
                    "SELECT hash, level, occurrences, success_rate FROM patterns "
                    "WHERE hash IN (" + ph + ")", tuple(hashes),
                ).fetchall()
                for pr in prows:
                    occ = int(pr["occurrences"] or 0)
                    patterns.append({
                        "hash": str(pr["hash"]),
                        "level": int(pr["level"] or 0),
                        "occurrences": occ,
                        "mature": occ >= 20,
                        "label": "",
                    })
        finally:
            conn.close()
    except Exception:
        log.exception("breach/cartography: query failed; degrading to empty")
        return empty

    if not rows:
        return empty

    # Domain-agnostic project slug rendered FROM DATA (M16). The alert anchor is
    # the newest decision timestamp; the window is the caller-supplied look-back.
    proj = (rows[-1].get("project_slug") or "").strip()
    sess = (rows[-1].get("session_id") or "").strip()
    try:
        alert_ts = max(float(r["timestamp"]) for r in rows if r.get("timestamp") is not None)
    except (TypeError, ValueError):
        alert_ts = None
    decisions = []
    for r in rows:
        msg = (r.get("content") or r.get("reasoning") or "").strip()
        decisions.append({
            "decision_id": str(r.get("decision_id") or ""),
            "action": str(r.get("action") or "ALLOW"),
            "confidence": float(r.get("confidence") or 0.0),
            "message": msg[:200],
            "matched_hash": (r.get("matched_hash") or "").strip(),
            "timestamp": r.get("timestamp"),
            "hitl_note": (r.get("hitl_note") or "").strip(),
        })
    return {
        "alert_ts": alert_ts,
        "window_ms": win,
        "session_id": sess,
        "project_slug": proj,
        "excluded_self": True,
        "regressed_cells": [],
        "maturity_delta": {
            "cells": 0,
            "note": (
                "v1 CONSTRAINED: per-decision maturity is not live (FROZEN schema) -- "
                "deferred to an ADR-18 amendment. Coarse RingDelta only."
            ),
        },
        "decisions": decisions,
        "patterns": patterns,
        "mock": False,
    }


# ============= BETA #undefined : confidence-heatmap-pane =============

# --- GET /api/heatmap ---
# --- GET /api/heatmap ---
@app.get("/api/heatmap")
async def api_heatmap(
    session_id: str | None = None,
    minutes: int = 60,
    bucket_min: int = 5,
    limit: int = 20000,
):
    """Pre-aggregate decisions into a role x 5-min-bucket confidence grid for the
    BETA confidence-heatmap-pane (#9).

    Read-only, post-hoc (M18): a render-ready aggregation over the existing
    indexed decisions(timestamp) + messages(session_id) rows, with each
    decision's role resolved from the agents table via the SAME correlated
    subquery the /api/decisions seed uses (most-recent agents.profile_slug for
    the session whose last_seen <= the decision timestamp). ZERO writes, ZERO
    FROZEN-surface touch, ZERO new bus envelope, ZERO new table.

    POLARITY (G2 / M15): the SM-own session is excluded server-side. The durable
    read key is project_slug NOT IN the SM exclusion set (BRIDGE_SM_PROJECT_SLUGS,
    default {'streamManager'}); the SM_OWN_SESSION_ID session id is applied as the
    cheap backstop. A session whose project_slug is in the SM set -- or whose id
    equals SM_OWN_SESSION_ID -- can NEVER appear in the grid, so an SM-self scope
    returns roles:[], cells:[]. A LEFT JOIN keeps rows whose session has no
    sessions-row (they are not self). The env-set is read the same way the
    escalation-timeline / health-digest wire-sites read it, so they stay
    consistent.

    Returns {now_ms, bucket_min, minutes, excluded_self, roles:[...sorted by
    count-weighted mean confidence DESC], buckets:[{idx,t_ms,label}], cells:[
    {role, bucket_idx, count, mean_confidence, band, action_breakdown:
    {ALLOW,SUGGEST,GUIDE,INTERVENE,BLOCK}}]}. Bands: HIGH>=0.75, OK 0.60-0.75,
    WATCH 0.45-0.60, LOW<0.45. Only role x bucket pairs with >=1 in-window
    decision yield a cell (empty pairs are omitted -- the client renders them as
    uncolored hairline gaps). Degrades to an empty grid on any error / fresh DB.
    """
    import time as _time

    bmin = int(bucket_min) if int(bucket_min or 0) > 0 else 5
    bucket_ms = bmin * 60 * 1000
    win_min = int(minutes) if int(minutes or 0) > 0 else 60
    ncols = max(1, win_min // bmin)
    now_ms = int(_time.time() * 1000)
    # newest bucket = the bucket containing now; oldest = (ncols-1) buckets back.
    now_start = (now_ms // bucket_ms) * bucket_ms
    oldest_start = now_start - (ncols - 1) * bucket_ms

    def _empty() -> dict:
        return {
            "now_ms": now_ms,
            "bucket_min": bmin,
            "minutes": win_min,
            "excluded_self": 0,
            "roles": [],
            "buckets": [
                {"idx": i, "t_ms": oldest_start + i * bucket_ms}
                for i in range(ncols)
            ],
            "cells": [],
        }

    # Polarity: durable read key (project_slug) + cheap session-id backstop.
    _sm_slugs_raw = os.environ.get("BRIDGE_SM_PROJECT_SLUGS", "streamManager")
    sm_slugs = [s.strip() for s in _sm_slugs_raw.split(",") if s.strip()]
    sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()

    try:
        cap = min(int(limit or 20000), 50000)
        # window lower bound in epoch SECONDS (decisions.timestamp is sec).
        win_lo_s = oldest_start / 1000.0
        win_hi_s = (now_start + bucket_ms) / 1000.0
        conn = _open()
        has_agents = _has_agents_table(conn)
        # role expr: most-recent agents.profile_slug for the decision's session
        # at-or-before the decision timestamp (mirrors the /api/decisions seed).
        if has_agents:
            role_expr = (
                "(SELECT a.profile_slug FROM agents a "
                "WHERE a.session_id = m.session_id AND a.last_seen <= d.timestamp "
                "ORDER BY a.last_seen DESC LIMIT 1)"
            )
        else:
            role_expr = "NULL"
        where = ["d.timestamp >= ?", "d.timestamp < ?"]
        params: list = [win_lo_s, win_hi_s]
        if session_id:
            where.append("m.session_id = ?")
            params.append(session_id)
        # Self-exclude (G2): drop SM-self by project_slug (durable). LEFT JOIN so a
        # decision with no sessions-row is KEPT (it is not SM-own by slug).
        if sm_slugs:
            placeholders = ",".join("?" for _ in sm_slugs)
            where.append(
                f"(s.project_slug IS NULL OR s.project_slug NOT IN ({placeholders}))"
            )
            params.extend(sm_slugs)
        # session-id backstop (drops the one self session id regardless of slug).
        if sm_own:
            where.append("m.session_id != ?")
            params.append(sm_own)
        sql = (
            f"SELECT d.action AS action, d.confidence AS confidence, "
            f"d.timestamp AS ts, {role_expr} AS role "
            "FROM decisions d "
            "JOIN messages m ON d.message_id = m.id "
            "LEFT JOIN sessions s ON s.id = m.session_id "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY d.timestamp ASC LIMIT ?"
        )
        params.append(cap)
        rows = conn.execute(sql, tuple(params)).fetchall()
        # excluded_self readout (decisions on the SM-own session id), for the UI.
        excluded_self = 0
        if sm_own:
            er = conn.execute(
                "SELECT COUNT(*) FROM decisions d "
                "JOIN messages m ON d.message_id = m.id "
                "WHERE m.session_id = ?",
                (sm_own,),
            ).fetchone()
            excluded_self = int(er[0] or 0) if er else 0
        conn.close()
    except Exception:
        log.exception("heatmap: query failed; degrading to empty")
        return _empty()

    _ACTIONS = ("ALLOW", "SUGGEST", "GUIDE", "INTERVENE", "BLOCK")

    def _band(conf: float) -> str:
        if conf >= 0.75:
            return "HIGH"
        if conf >= 0.60:
            return "OK"
        if conf >= 0.45:
            return "WATCH"
        return "LOW"

    # accumulate per (role, bucket_idx): n, sum(confidence), action mix.
    acc: dict[tuple[str, int], dict] = {}
    for r in rows:
        try:
            ts_f = float(r["ts"])
        except (TypeError, ValueError):
            continue
        start = int((ts_f * 1000) // bucket_ms) * bucket_ms
        if start < oldest_start or start > now_start:
            continue
        idx = round((start - oldest_start) / bucket_ms)
        if idx < 0 or idx >= ncols:
            continue
        role = (r["role"] or "").strip() or "unknown"
        act = str(r["action"] or "").strip().upper()
        if act not in _ACTIONS:
            act = "ALLOW"
        try:
            conf = float(r["confidence"])
        except (TypeError, ValueError):
            conf = 0.0
        if conf < 0.0:
            conf = 0.0
        elif conf > 1.0:
            conf = 1.0
        key = (role, idx)
        a = acc.get(key)
        if a is None:
            a = {"n": 0, "sum": 0.0, "mix": {k: 0 for k in _ACTIONS}}
            acc[key] = a
        a["n"] += 1
        a["sum"] += conf
        a["mix"][act] += 1

    cells = []
    role_weight: dict[str, list[float]] = {}
    for (role, idx), a in acc.items():
        n = a["n"]
        mean = (a["sum"] / n) if n else 0.0
        cells.append(
            {
                "role": role,
                "bucket_idx": idx,
                "count": n,
                "mean_confidence": round(mean, 4),
                "band": _band(mean),
                "action_breakdown": a["mix"],
            }
        )
        w = role_weight.setdefault(role, [0.0, 0.0])
        w[0] += mean * n
        w[1] += n

    # roles sorted by count-weighted mean confidence DESC (ties -> name asc).
    def _role_mean(role: str) -> float:
        w = role_weight.get(role, [0.0, 0.0])
        return (w[0] / w[1]) if w[1] else 0.0

    roles = sorted(role_weight.keys(), key=lambda r: (-_role_mean(r), r))

    buckets = [
        {"idx": i, "t_ms": oldest_start + i * bucket_ms} for i in range(ncols)
    ]
    return {
        "now_ms": now_ms,
        "bucket_min": bmin,
        "minutes": win_min,
        "excluded_self": excluded_self,
        "roles": roles,
        "buckets": buckets,
        "cells": cells,
    }


# ============= BETA #undefined : cross-session-pattern-audit-apis =============

# --- GET /api/patterns/cross-session/{session_id}/hydrated ---
# ===================== BETA #cross-session-pattern-audit-apis =====================

# --- GET /api/patterns/cross-session/{session_id}/hydrated ---
# ---------------------------------------------------------------------------
# BETA cross-session-pattern-audit-apis (#11): the learned cross-session rules
# that hydrated INTO one governed (non-SM) session at engine-init, each with its
# REACH into that session (matched_decision_count_this_session). Additive,
# read-only (M18, post-hoc -- never on the verdict hot path). Touches NO FROZEN
# surface: no governance.py, no message_bus schema change, no new bus envelope.
# It joins only patterns + decisions(matched_hash) + messages(session_id) +
# sessions(project_slug). The proposal's optional patterns columns
# (last_seen_session_id / sourced_from / decay_status) are DERIVED defensively
# here (no migration -- CONSTRAINED ADDITIVE build): last_seen_session_id is
# backfilled from the most-recent matching decision's message session,
# sourced_from is the constant 'cross_session_hydrator', and decay_status is
# inferred from success_rate.
#
# POLARITY (G2, CLAUDE.md 'Session-source exception rule'): the TARGET scope is
# 404'd if it is SM-self (project_slug IN the SM slug set OR id == SM_OWN_SESSION
# _ID) -- the audit never exposes SM-self hydration. The reach join additionally
# EXCLUDES decisions whose message session is SM-self, so an SM-self decision can
# never inflate a governed rule's reach.
#
# Domain-agnostic (M16): hash / level are the pattern table's own taxonomy,
# rendered verbatim. Defensive: any error degrades to an empty shape so the UI
# falls back to mock (never reads as live when the server is down / DB is fresh).
# ---------------------------------------------------------------------------
@app.get("/api/patterns/cross-session/{session_id}/hydrated")
async def api_patterns_cross_session_hydrated(session_id: str):
    """Hydrated cross-session rules + their reach for one governed session (#11)."""
    target = (session_id or "").strip()
    if not target or len(target) > 256:
        return {"session_id": target, "count": 0, "mock": False, "rows": []}

    # SM exclusion set (durable read key = project_slug). Default {'streamManager'};
    # override via BRIDGE_SM_PROJECT_SLUGS. Compared lowercased. Plus the cheap
    # session-id backstop (SM_OWN_SESSION_ID) on the ephemeral key.
    sm_slugs_raw = os.environ.get("BRIDGE_SM_PROJECT_SLUGS", "streamManager")
    sm_slugs = {s.strip().lower() for s in sm_slugs_raw.split(",") if s.strip()}
    sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()

    # G2: refuse an SM-self target scope outright (404). The audit never exposes
    # hydration for SM's own session, regardless of how it is addressed.
    if sm_own and target == sm_own:
        raise HTTPException(status_code=404, detail="session not found")

    try:
        conn = _open()
        try:
            if not _has_table(conn, "patterns"):
                return {"session_id": target, "count": 0, "mock": False, "rows": []}

            has_sessions = _has_table(conn, "sessions")
            # Confirm the target is a GOVERNED (non-SM) session by project_slug.
            if has_sessions:
                srow = conn.execute(
                    "SELECT project_slug FROM sessions WHERE id=?", (target,)
                ).fetchone()
                if srow is not None:
                    slug = (srow["project_slug"] or "").strip().lower()
                    if slug in sm_slugs:
                        raise HTTPException(status_code=404, detail="session not found")

            pcols = {r[1] for r in conn.execute("PRAGMA table_info(patterns)").fetchall()}
            if "cross_session" not in pcols:
                return {"session_id": target, "count": 0, "mock": False, "rows": []}

            # All cross-session-flagged patterns (the hydration candidate set).
            prows = conn.execute(
                "SELECT hash, level, occurrences, success_rate, last_seen, payload "
                "FROM patterns WHERE cross_session=1 ORDER BY last_seen DESC"
            ).fetchall()
            if not prows:
                return {"session_id": target, "count": 0, "mock": False, "rows": []}

            has_decisions = _has_table(conn, "decisions")
            has_messages = _has_table(conn, "messages")
            can_reach = has_decisions and has_messages

            # SM-self exclusion fragment for the reach/backfill joins (durable
            # project_slug key + the session_id backstop), mirroring the other
            # beta read endpoints. NULL slug is NOT in the SM set -> kept.
            join_sessions = "LEFT JOIN sessions s ON m.session_id = s.id " if has_sessions else ""
            self_excl = []
            self_params: list = []
            if has_sessions and sm_slugs:
                ph = ",".join("?" for _ in sm_slugs)
                self_excl.append(f"(s.project_slug IS NULL OR LOWER(s.project_slug) NOT IN ({ph}))")
                self_params.extend(sorted(sm_slugs))
            if sm_own:
                self_excl.append("m.session_id != ?")
                self_params.append(sm_own)
            self_clause = (" AND " + " AND ".join(self_excl)) if self_excl else ""

            out = []
            for p in prows:
                phash = p["hash"]
                sr = float(p["success_rate"] or 0.0)
                success_rate = sr if sr <= 1.0 else sr / 100.0
                reach = 0
                last_seen_session_id = None
                if can_reach:
                    # matched_decision_count_this_session: governed decisions in
                    # THIS session that matched this pattern hash (self-excluded).
                    rc = conn.execute(
                        "SELECT COUNT(*) FROM decisions d "
                        "JOIN messages m ON d.message_id = m.id " + join_sessions +
                        "WHERE d.matched_hash = ? AND m.session_id = ?" + self_clause,
                        tuple([phash, target, *self_params]),
                    ).fetchone()
                    reach = int(rc[0]) if rc else 0
                    # last_seen_session_id backfill: the most-recent governed
                    # session (NOT the target) whose decision matched this hash.
                    lsr = conn.execute(
                        "SELECT m.session_id FROM decisions d "
                        "JOIN messages m ON d.message_id = m.id " + join_sessions +
                        "WHERE d.matched_hash = ? AND m.session_id != ?" + self_clause +
                        " ORDER BY d.timestamp DESC LIMIT 1",
                        tuple([phash, target, *self_params]),
                    ).fetchone()
                    last_seen_session_id = lsr[0] if lsr else None

                # decay_status derived (no schema column): a high-success,
                # recently-seen rule is 'stable'; a low-success one is 'decaying';
                # unknown when there is no usable success signal.
                occ = int(p["occurrences"] or 0)
                if occ <= 0:
                    decay_status = "unknown"
                elif success_rate >= 0.6:
                    decay_status = "stable"
                else:
                    decay_status = "decaying"

                out.append({
                    "pattern_hash": phash,
                    "level": int(p["level"] or 0),
                    "last_seen_session_id": last_seen_session_id,
                    "last_seen_ts": float(p["last_seen"] or 0.0),
                    "occurrence_count": occ,
                    "success_rate": round(success_rate, 4),
                    "matched_decision_count_this_session": reach,
                    "sourced_from": "cross_session_hydrator",
                    "decay_status": decay_status,
                })
        finally:
            conn.close()
    except HTTPException:
        raise
    except Exception:
        log.exception("patterns/cross-session/hydrated: query failed")
        return {"session_id": target, "count": 0, "mock": False, "rows": []}

    return {"session_id": target, "count": len(out), "mock": False, "rows": out}

# --- GET /api/patterns/{hash}/would-apply ---
# --- GET /api/patterns/{hash}/would-apply ---
# ---------------------------------------------------------------------------
# BETA cross-session-pattern-audit-apis (#11): the read-only "would this fire?"
# applicability probe. Given a pattern hash + a candidate message, it returns an
# applicability score WITHOUT emitting a verdict or touching the governance path
# (M18 post-hoc only). It is a pure computation over the stored pattern's
# canonical text -- it emits NO bus envelope and mutates nothing.
#
# Matching: a deterministic, dependency-free token-overlap score in [0,1] used as
# a stand-in cosine proxy (the real engine's decision_graph.match() is FROZEN and
# not importable on the dashboard read path). 'applies' is the score >= 0.72
# (mirrors SIMILARITY_THRESHOLD). On a missing pattern / empty input / any error
# it returns the documented degraded shape {applies:false, match_confidence:0.0,
# sourced_from:[], rationale:'matching engine unavailable'} -- it NEVER 500s into
# the probe UI. A 500ms wall is enforced; on overrun the degraded shape returns.
#
# POLARITY (G2): a pattern whose ONLY observations are SM-self is treated as
# unknown (degraded shape) -- the probe never reconstructs a rule from SM-self
# traffic, mirroring the pedigree endpoint's no-self-monitor floor.
#
# Domain-agnostic (M16): scoring is over opaque text tokens, never project terms.
# ---------------------------------------------------------------------------
@app.get("/api/patterns/{hash}/would-apply")
async def api_pattern_would_apply(hash: str, message_content: str = ""):
    """Read-only post-hoc applicability probe for one pattern (#11). No verdict."""
    import time as _t
    started = _t.monotonic()
    degraded = {
        "applies": False,
        "match_confidence": 0.0,
        "sourced_from": [],
        "rationale": "matching engine unavailable",
    }
    pattern_hash = (hash or "").strip()
    text = (message_content or "").strip()
    if not pattern_hash or len(pattern_hash) > 128 or not text:
        return degraded

    sm_slugs_raw = os.environ.get("BRIDGE_SM_PROJECT_SLUGS", "streamManager")
    sm_slugs = {s.strip().lower() for s in sm_slugs_raw.split(",") if s.strip()}

    try:
        conn = _open()
        try:
            canonical = None
            # Prefer graph_patterns.canonical_text (the engine's own text); fall
            # back to patterns.payload. Both are read-only.
            if _has_table(conn, "graph_patterns"):
                row = conn.execute(
                    "SELECT canonical_text FROM graph_patterns WHERE hash=?",
                    (pattern_hash,),
                ).fetchone()
                if row is not None:
                    canonical = row["canonical_text"] or ""
            if canonical is None and _has_table(conn, "patterns"):
                row = conn.execute(
                    "SELECT payload FROM patterns WHERE hash=?", (pattern_hash,)
                ).fetchone()
                if row is not None:
                    canonical = row["payload"] or ""
            if canonical is None:
                return degraded

            # G2: if this pattern has decisions ONLY on SM-self sessions, suppress
            # (degraded) -- never reconstruct applicability from SM-self traffic.
            if (
                _has_table(conn, "decisions")
                and _has_table(conn, "messages")
                and _has_table(conn, "sessions")
                and sm_slugs
            ):
                ph = ",".join("?" for _ in sm_slugs)
                gov = conn.execute(
                    "SELECT COUNT(*) FROM decisions d "
                    "JOIN messages m ON d.message_id = m.id "
                    "LEFT JOIN sessions s ON s.id = m.session_id "
                    "WHERE d.matched_hash = ? AND "
                    f"(s.project_slug IS NULL OR LOWER(s.project_slug) NOT IN ({ph}))",
                    tuple([pattern_hash, *sorted(sm_slugs)]),
                ).fetchone()
                any_dec = conn.execute(
                    "SELECT COUNT(*) FROM decisions WHERE matched_hash = ?",
                    (pattern_hash,),
                ).fetchone()
                # Has decisions, but none governed -> SM-self-only -> suppress.
                if any_dec and int(any_dec[0]) > 0 and gov and int(gov[0]) == 0:
                    return degraded
        finally:
            conn.close()
    except Exception:
        log.exception("patterns/would-apply: lookup failed")
        return degraded

    # 500ms wall (post-hoc cap). The work below is O(tokens); the guard is belt.
    if (_t.monotonic() - started) > 0.5:
        return degraded

    # Deterministic token-overlap proxy in [0,1]. ASCII-lowercased word sets.
    import re as _re
    def _toks(s: str) -> set:
        return {w for w in _re.split(r"[^a-z0-9]+", (s or "").lower()) if w}
    a = _toks(canonical)
    b = _toks(text)
    if not a or not b:
        return {
            "applies": False,
            "match_confidence": 0.0,
            "sourced_from": ["graph_match"],
            "rationale": "cosine 0.00 below threshold 0.72",
        }
    inter = len(a & b)
    union = len(a | b)
    score = round(inter / union, 2) if union else 0.0
    applies = score >= 0.72
    return {
        "applies": applies,
        "match_confidence": score,
        "sourced_from": ["graph_match"],
        "rationale": (
            f"cosine {score:.2f} >= threshold 0.72" if applies
            else f"cosine {score:.2f} below threshold 0.72"
        ),
    }


# ============= BETA #undefined : escalation-timeline-causal-forensics =============

# --- GET /api/escalations ---
# ===================== BETA #escalation-timeline-causal-forensics (#13) =====================
#
# Three ADDITIVE read/write endpoints for the BETA Escalation Timeline causal-
# forensics feature. CONSTRAINED ADDITIVE: NO governance.py / message_bus.py edit,
# NO new bus envelope, NO new decisions column, NO ADR-18 amendment. Escalation
# cards + the causal context are DERIVED at READ TIME from the EXISTING decision
# rows (action IN GUIDE/INTERVENE/BLOCK); event_type is classified from the
# decision's own action + matched_hash; agent attribution reuses the existing
# agents subselect. The ONLY persisted state is the operator dismiss ack, which
# lives in an additive dashboard-side escalation_dismissals table (CREATE TABLE
# IF NOT EXISTS) -- off the verdict hot path (M18), never a decisions row write.
#
# POLARITY (G2 / M15): SM-self is excluded at the SQL WHERE -- a session whose
# project_slug is in the SM exclusion set (BRIDGE_SM_PROJECT_SLUGS, default
# {streamManager}) can NEVER appear; the SM_OWN_SESSION_ID row is excluded too.


def _ensure_escalation_dismissals(conn: sqlite3.Connection) -> None:
    """Guarded additive CREATE: the dashboard-side dismiss-ack table. Additive
    only (Rule 1); NOT a message_bus.py schema edit and NOT a bus envelope. Keyed
    on the decision_id the operator acked + the ack timestamp. Idempotent."""
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS escalation_dismissals ("
            "  decision_id TEXT PRIMARY KEY,"
            "  dismissed_at REAL NOT NULL"
            ")"
        )
    except Exception:
        log.exception("escalations: ensure escalation_dismissals table failed")


@app.get("/api/escalations")
async def api_escalations(session_id: str | None = None, limit: int = 100):
    """DERIVE the newest-first escalation card list for the BETA Escalation
    Timeline (#13) from the EXISTING decision rows (action IN GUIDE/INTERVENE/
    BLOCK). Read-only, post-hoc (M18). Each card:
    {escalation_id, decision_id, event_type, triggered_at, message_id,
     proposed_action, confidence, agent_id, session_id, project_slug,
     reasoning, content, direction, dismissed_at}.

    event_type is classified from the row itself (no new column): a BLOCK with a
    matched_hash -> 'static-rule'; a BLOCK without -> 'governance_negative_
    regression'; INTERVENE -> 'governance_negative_regression'; GUIDE ->
    'governance_variance_alert'. dismissed_at is LEFT JOINed from the additive
    escalation_dismissals table.

    POLARITY (G2): SM-self is excluded at the SQL WHERE on sessions.project_slug
    (LEFT JOIN keeps decisions with no sessions-row -- not self) AND on
    m.session_id != SM_OWN_SESSION_ID. Degrades to [] on any error / empty DB so
    the client falls back to deterministic mock data.
    """
    try:
        cap = min(int(limit or 100), 500)
        sm_slugs = list(_sm_own_slugs())
        sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
        conn = _open()
        # Ensure the dismissals table exists for the LEFT JOIN (read-side create on
        # the same connection is harmless; _open() is mode=ro when possible, so the
        # CREATE silently no-ops there and the LEFT JOIN tolerates the absent table
        # via a guarded check).
        has_dismissals = _has_table(conn, "escalation_dismissals")
        params: list = []
        where = ["d.action IN ('GUIDE','INTERVENE','BLOCK')"]
        if session_id:
            where.append("m.session_id = ?")
            params.append(session_id)
        if sm_own:
            where.append("m.session_id != ?")
            params.append(sm_own)
        if sm_slugs:
            placeholders = ",".join("?" for _ in sm_slugs)
            where.append(
                f"(s.project_slug IS NULL OR LOWER(s.project_slug) NOT IN ({placeholders}))"
            )
            params.extend(sm_slugs)
        dismiss_join = (
            "LEFT JOIN escalation_dismissals x ON x.decision_id = d.id "
            if has_dismissals else ""
        )
        dismiss_sel = (
            "x.dismissed_at AS dismissed_at " if has_dismissals else "NULL AS dismissed_at "
        )
        sql = (
            "SELECT d.id AS id, d.message_id AS message_id, d.action AS action, "
            "d.confidence AS confidence, d.reasoning AS reasoning, "
            "d.matched_hash AS matched_hash, d.timestamp AS ts, "
            "m.content AS content, m.direction AS direction, m.session_id AS session_id, "
            "s.project_slug AS project_slug, "
            "(SELECT a.profile_slug FROM agents a "
            "   WHERE a.session_id = m.session_id AND a.last_seen <= d.timestamp "
            "   ORDER BY a.last_seen DESC LIMIT 1) AS agent_id, "
            + dismiss_sel +
            "FROM decisions d "
            "JOIN messages m ON d.message_id = m.id "
            "LEFT JOIN sessions s ON s.id = m.session_id "
            + dismiss_join +
            f"WHERE {' AND '.join(where)} "
            "ORDER BY d.timestamp DESC LIMIT ?"
        )
        params.append(cap)
        rows = conn.execute(sql, tuple(params)).fetchall()
        conn.close()
    except Exception:
        log.exception("escalations: query failed; degrading to empty")
        return []

    def _evt(action: str, matched: str) -> str:
        a = (action or "").strip().upper()
        h = (matched or "").strip()
        if a == "BLOCK":
            return "static-rule" if h else "governance_negative_regression"
        if a == "INTERVENE":
            return "governance_negative_regression"
        return "governance_variance_alert"

    out = []
    for r in rows:
        did = str(r["id"]) if r["id"] is not None else str(r["message_id"])
        try:
            ts = float(r["ts"])
        except (TypeError, ValueError):
            continue
        act = str(r["action"]).strip().upper()
        try:
            conf = float(r["confidence"])
        except (TypeError, ValueError):
            conf = 0.0
        out.append({
            "escalation_id": f"esc-{did}",
            "decision_id": did,
            "event_type": _evt(act, str(r["matched_hash"] or "")),
            "triggered_at": ts,
            "message_id": str(r["message_id"]) if r["message_id"] is not None else "",
            "proposed_action": act,
            "confidence": conf,
            "agent_id": str(r["agent_id"] or "agent"),
            "session_id": str(r["session_id"] or ""),
            "project_slug": str(r["project_slug"] or ""),
            "reasoning": str(r["reasoning"] or ""),
            "content": str(r["content"] or ""),
            "direction": str(r["direction"] or ""),
            "dismissed_at": r["dismissed_at"],
        })
    return out

# --- GET /api/escalations/{decision_id}/context ---
@app.get("/api/escalations/{decision_id}/context")
async def api_escalation_context(decision_id: str, window_ms: int = 10000):
    """DERIVE the split-view causal context for one focus decision (BETA #13).
    Read-only, post-hoc (M18). Returns the 5 prior + 3 next same-session
    decisions (compressed: action + confidence + agent + reason) and the
    distinct agents active within +/- window around the focus, plus the focus
    diff payload {action, confidence, reasoning, content, direction, agent_id,
    timestamp}. ALL fields are read from existing decisions/messages/agents rows;
    NOTHING is fabricated and NO new column is read.

    POLARITY (G2): the focus session is resolved and the whole payload is
    suppressed (HTTP 200 with a null focus) if it is the SM-own session
    (project_slug in the SM exclusion set OR session_id == SM_OWN_SESSION_ID).
    Degrades to an empty-but-valid shape on any error.
    """
    empty = {
        "decision_id": str(decision_id), "event_type": "", "window_ms": int(window_ms or 10000),
        "focus": None, "prior": [], "next": [], "agents_in_window": [],
    }
    try:
        win_ms = int(window_ms) if int(window_ms or 0) > 0 else 10000
        win_s = win_ms / 1000.0
        sm_slugs = _sm_own_slugs()
        sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
        conn = _open()
        focus = conn.execute(
            "SELECT d.id AS id, d.action AS action, d.confidence AS confidence, "
            "d.reasoning AS reasoning, d.matched_hash AS matched_hash, d.timestamp AS ts, "
            "m.content AS content, m.direction AS direction, m.session_id AS session_id, "
            "s.project_slug AS project_slug, "
            "(SELECT a.profile_slug FROM agents a "
            "   WHERE a.session_id = m.session_id AND a.last_seen <= d.timestamp "
            "   ORDER BY a.last_seen DESC LIMIT 1) AS agent_id "
            "FROM decisions d JOIN messages m ON d.message_id = m.id "
            "LEFT JOIN sessions s ON s.id = m.session_id "
            "WHERE d.id = ? LIMIT 1",
            (str(decision_id),),
        ).fetchone()
        if focus is None:
            conn.close()
            return empty
        sid = str(focus["session_id"] or "")
        slug = str(focus["project_slug"] or "").strip().lower()
        # POLARITY: never surface SM-self context.
        if (sm_own and sid == sm_own) or (slug and slug in sm_slugs):
            conn.close()
            return empty
        try:
            f_ts = float(focus["ts"])
        except (TypeError, ValueError):
            conn.close()
            return empty
        # same-session decisions, ascending by time (window + a small neighbourhood).
        lo = f_ts - max(win_s, 60.0)
        hi = f_ts + max(win_s, 60.0)
        same = conn.execute(
            "SELECT d.id AS id, d.action AS action, d.confidence AS confidence, "
            "d.reasoning AS reasoning, d.timestamp AS ts, m.content AS content, "
            "(SELECT a.profile_slug FROM agents a "
            "   WHERE a.session_id = m.session_id AND a.last_seen <= d.timestamp "
            "   ORDER BY a.last_seen DESC LIMIT 1) AS agent_id "
            "FROM decisions d JOIN messages m ON d.message_id = m.id "
            "WHERE m.session_id = ? AND d.timestamp >= ? AND d.timestamp <= ? "
            "ORDER BY d.timestamp ASC LIMIT 400",
            (sid, lo, hi),
        ).fetchall()
        conn.close()
    except Exception:
        log.exception("escalation-context: query failed; degrading to empty")
        return empty

    def _evt(action: str, matched: str) -> str:
        a = (action or "").strip().upper()
        if a == "BLOCK":
            return "static-rule" if (matched or "").strip() else "governance_negative_regression"
        if a == "INTERVENE":
            return "governance_negative_regression"
        return "governance_variance_alert"

    def _compress(r):
        try:
            cf = float(r["confidence"])
        except (TypeError, ValueError):
            cf = 0.0
        reason = str(r["reasoning"] or "").strip() or str(r["content"] or "").strip()
        return {
            "action": str(r["action"] or "ALLOW").strip().upper(),
            "confidence": cf,
            "agent_id": str(r["agent_id"] or "agent"),
            "reason": reason,
            "timestamp": float(r["ts"]) if r["ts"] is not None else None,
        }

    did = str(decision_id)
    ordered = list(same)
    focus_idx = next((i for i, r in enumerate(ordered) if str(r["id"]) == did), -1)
    prior = (
        [_compress(r) for r in ordered[max(0, focus_idx - 5):focus_idx]]
        if focus_idx > 0
        else []
    )
    nxt = [_compress(r) for r in ordered[focus_idx + 1:focus_idx + 4]] if focus_idx >= 0 else []
    # agents-in-window (distinct) strictly within +/- window of the focus.
    seen: dict = {}
    for r in ordered:
        try:
            ts = float(r["ts"])
        except (TypeError, ValueError):
            continue
        if ts < f_ts - win_s or ts > f_ts + win_s:
            continue
        ag = str(r["agent_id"] or "agent")
        cur = seen.get(ag) or {"agent_id": ag, "active_from": ts, "active_to": ts}
        cur["active_from"] = min(cur["active_from"], ts)
        cur["active_to"] = max(cur["active_to"], ts)
        seen[ag] = cur
    try:
        f_conf = float(focus["confidence"])
    except (TypeError, ValueError):
        f_conf = 0.0
    return {
        "decision_id": did,
        "event_type": _evt(str(focus["action"] or ""), str(focus["matched_hash"] or "")),
        "window_ms": win_ms,
        "focus": {
            "action": str(focus["action"] or "BLOCK").strip().upper(),
            "confidence": f_conf,
            "reasoning": str(focus["reasoning"] or ""),
            "content": str(focus["content"] or ""),
            "direction": str(focus["direction"] or ""),
            "agent_id": str(focus["agent_id"] or "agent"),
            "timestamp": f_ts,
        },
        "prior": prior,
        "next": nxt,
        "agents_in_window": list(seen.values()),
    }

# --- POST /api/escalations/{decision_id}/dismiss ---
@app.post("/api/escalations/{decision_id}/dismiss")
async def api_escalation_dismiss(decision_id: str):
    """Operator ack of one escalation (BETA #13). Writes ONLY the additive
    escalation_dismissals table (decision_id + dismissed_at) -- never a
    decisions/messages row, never a verdict (off the hot path, M18). Idempotent:
    re-dismissing an already-acked decision is a no-op success.

    POLARITY (G2): the decision's session is resolved; if it is the SM-own
    session (project_slug in the SM exclusion set OR session_id ==
    SM_OWN_SESSION_ID) the ack is REFUSED (HTTP 400) -- SM-self escalations are
    never surfaced and so can never be acked.
    """
    if not isinstance(decision_id, str) or not decision_id:
        raise HTTPException(status_code=400, detail="decision_id required")
    sm_slugs = _sm_own_slugs()
    sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
    try:
        conn = _open_rw()
        _ensure_escalation_dismissals(conn)
        row = conn.execute(
            "SELECT m.session_id AS session_id, s.project_slug AS project_slug "
            "FROM decisions d JOIN messages m ON d.message_id = m.id "
            "LEFT JOIN sessions s ON s.id = m.session_id WHERE d.id = ? LIMIT 1",
            (str(decision_id),),
        ).fetchone()
        if row is not None:
            sid = str(row["session_id"] or "")
            slug = str(row["project_slug"] or "").strip().lower()
            if (sm_own and sid == sm_own) or (slug and slug in sm_slugs):
                conn.close()
                raise HTTPException(status_code=400, detail="refusing to ack an SM-self escalation")
        conn.execute(
            "INSERT INTO escalation_dismissals (decision_id, dismissed_at) VALUES (?, ?) "
            "ON CONFLICT(decision_id) DO NOTHING",
            (str(decision_id), time.time()),
        )
        conn.close()
        return {"decision_id": str(decision_id), "dismissed": True, "dismissed_at": _iso_now()}
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("escalation-dismiss: write failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ============= BETA #undefined : operator-co-pilot-gesture-macros =============


# ============= BETA #undefined : recorded-session-replay-forensics =============

# --- GET /api/soak/replay/sessions ---
@app.get("/api/soak/replay/sessions")
async def api_soak_replay_sessions(limit: int = 50):
    """List NON-SM recorded sessions (those that have at least one decision)
    eligible for the BETA recorded-session-replay-forensics picker (#23).
    Read-only -- modifies NOTHING. Newest-active first.

    POLARITY (G2 / M15): rows whose joined project_slug is in the SM exclusion
    set are EXCLUDED (durable read key) AND the SM_OWN_SESSION_ID session is
    excluded too (session backstop). The dropped tally is returned as
    excluded_self so the UI renders self-exclusion as a VISIBLE feature.
    Recorded sessions are NON-SM by construction. Degrades to an empty shape on
    any error / fresh DB (the component then falls back to deterministic mock).
    """
    try:
        lim = max(1, min(200, int(limit)))
    except Exception:
        lim = 50
    sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
    slugs = _sm_own_slugs()
    excluded_self = 0
    out: list[dict] = []
    try:
        conn = _open()
        if not _has_table(conn, "sessions") or not _has_table(conn, "decisions"):
            conn.close()
            return {"sessions": [], "excluded_self": 0, "own_session_id": sm_own or None}
        rows = conn.execute(
            "SELECT m.session_id AS session_id, "
            "       MAX(s.project_slug) AS project_slug, "
            "       COUNT(*) AS frame_count, "
            "       MAX(d.timestamp) AS last_ts "
            "FROM decisions d "
            "JOIN messages m ON d.message_id = m.id "
            "LEFT JOIN sessions s ON m.session_id = s.id "
            "GROUP BY m.session_id "
            "ORDER BY last_ts DESC"
        ).fetchall()
        conn.close()
        for r in rows:
            d = dict(r)
            sid = str(d.get("session_id") or "").strip()
            if not sid:
                continue
            slug = str(d.get("project_slug") or "").strip().lower()
            # Polarity self-exclude (G2): never present SM-self as a replay target.
            if slug in slugs or (sm_own and sid == sm_own):
                excluded_self += 1
                continue
            out.append({
                "recorded_session_uuid": sid,
                "project_slug": d.get("project_slug") or "",
                "frame_count": int(d.get("frame_count") or 0),
            })
    except Exception:
        log.exception("replay-forensics: sessions list failed; degrading to empty")
        return {"sessions": [], "excluded_self": 0, "own_session_id": sm_own or None}
    return {
        "sessions": out[:lim],
        "excluded_self": excluded_self,
        "own_session_id": sm_own or None,
    }

# --- GET /api/soak/replay/{recorded_session_uuid} ---
@app.get("/api/soak/replay/{recorded_session_uuid}")
async def api_soak_replay(
    recorded_session_uuid: str, start_idx: int = 0, end_idx: int | None = None
):
    """Side-by-side decision-delta replay forensics for ONE recorded NON-SM
    session, for the BETA recorded-session-replay-forensics drawer (#23).
    Read-only -- modifies NOTHING.

    v1 SCOPE (CONSTRAINED ADDITIVE): v1 DIFFS STORED DECISIONS. The 'original'
    column is the decision as captured at record time. The 'replayed' column is
    the current engine's verdict for the same frame. The LIVE re-stream engine
    -- re-evaluating each recorded envelope through a fresh in-process governance
    engine -- is DEFERRED to the out-of-process soak_driver --replay CLI; it is
    NOT run here (no spawn / subprocess / engine re-eval / FROZEN-surface touch /
    new bus envelope). With no live re-stream available in process, v1 emits the
    stored decision in BOTH columns, so a real session reads as all-MATCH (an
    honest 'replay reproduces the record-time verdict' baseline). When the CLI
    re-stream lands, the same shape is filled with the re-evaluated verdict.

    POLARITY (G2 / M15): the endpoint REFUSES an SM-self target -- if the joined
    project_slug is in the SM exclusion set OR session_id == SM_OWN_SESSION_ID it
    returns an empty (zero-frame) shape with excluded_self_rows=1, never a verdict.
    Recorded sessions are NON-SM by construction. Degrades to an empty shape on
    any error / unknown session (the component then falls back to mock).

    Returns {recorded_session_uuid, engine_version, recorded_at, frame_count,
    delta_count, polarity_filtered, excluded_self_rows, frames:[...]}.
    """
    sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
    slugs = _sm_own_slugs()
    uuid = str(recorded_session_uuid or "").strip()
    empty = {
        "recorded_session_uuid": uuid,
        "engine_version": "current",
        "recorded_at": "",
        "frame_count": 0,
        "delta_count": 0,
        "polarity_filtered": True,
        "excluded_self_rows": 0,
        "frames": [],
    }
    if not uuid:
        return empty
    try:
        sidx = max(0, int(start_idx))
    except Exception:
        sidx = 0
    try:
        eidx = None if end_idx is None else max(0, int(end_idx))
    except Exception:
        eidx = None
    try:
        conn = _open()
        if not _has_table(conn, "sessions") or not _has_table(conn, "decisions"):
            conn.close()
            return empty
        # Resolve the session's project_slug to enforce the polarity guard.
        srow = conn.execute(
            "SELECT project_slug FROM sessions WHERE id = ? LIMIT 1", (uuid,)
        ).fetchone()
        slug = str((dict(srow).get("project_slug") if srow else "") or "").strip().lower()
        # Polarity REFUSAL (G2): SM-self target yields no verdict, ever.
        if slug in slugs or (sm_own and uuid == sm_own):
            conn.close()
            return {**empty, "excluded_self_rows": 1}
        has_layer = _has_decision_routing_cols(conn)
        layer_expr = "COALESCE(d.layer, 0)" if has_layer else "0"
        rows = conn.execute(
            f"SELECT d.action AS action, d.confidence AS confidence, "
            f"       COALESCE(d.reasoning, '') AS reasoning, "
            f"       COALESCE(d.matched_hash, '') AS matched_hash, "
            f"       {layer_expr} AS layer, "
            f"       COALESCE(m.content, '') AS content, "
            f"       d.timestamp AS ts "
            f"FROM decisions d "
            f"JOIN messages m ON d.message_id = m.id "
            f"WHERE m.session_id = ? "
            f"ORDER BY d.rowid ASC",
            (uuid,),
        ).fetchall()
        conn.close()
    except Exception:
        log.exception("replay-forensics: replay read failed; degrading to empty")
        return empty
    frames: list[dict] = []
    recorded_at = ""
    for i, r in enumerate(rows):
        d = dict(r)
        if not recorded_at and d.get("ts") is not None:
            try:
                import datetime as _dt
                recorded_at = _dt.datetime.fromtimestamp(
                    float(d["ts"]), _dt.UTC
                ).isoformat()
            except Exception:
                recorded_at = ""
        content = str(d.get("content") or "").strip().replace("\n", " ")
        fingerprint = content[:80]
        try:
            layer = int(d.get("layer") or 0)
        except Exception:
            layer = 0
        kind = "l4" if layer >= 4 else ("l2_l3" if layer >= 2 else "routine")
        try:
            conf = float(d.get("confidence"))
        except Exception:
            conf = 0.0
        side = {
            "action": str(d.get("action") or "ALLOW"),
            "confidence": conf,
            "layer": layer,
            "matched_hash": str(d.get("matched_hash") or ""),
            "reasoning": str(d.get("reasoning") or ""),
        }
        # v1: 'replayed' == 'original' (live re-stream deferred to the CLI). A
        # shallow copy so the two sides are independent dicts in the response.
        frames.append({
            "idx": i,
            "kind": kind,
            "content_fingerprint": fingerprint,
            "original": dict(side),
            "replayed": dict(side),
            "delta": {
                "changed": False,
                "action_changed": False,
                "confidence_delta": 0.0,
                "layer_delta": 0,
                "matched_hash_changed": False,
                "reasoning_changed": False,
            },
        })
    # Optional frame-range slice (inclusive end), defensively clamped.
    if frames:
        lo = min(sidx, len(frames))
        hi = len(frames) if eidx is None else min(eidx + 1, len(frames))
        if hi < lo:
            hi = lo
        frames = frames[lo:hi]
    return {
        "recorded_session_uuid": uuid,
        "engine_version": "current",
        "recorded_at": recorded_at,
        "frame_count": len(frames),
        "delta_count": sum(1 for f in frames if f["delta"]["changed"]),
        "polarity_filtered": True,
        "excluded_self_rows": 0,
        "frames": frames,
    }


# ============= BETA #undefined : session-checkpoint-versioning =============

# --- GET /api/sessions/{session_id}/checkpoints ---
# ===================== BETA #session-checkpoint-versioning (#26) =====================
#
# Read-only session checkpoint snapshots for post-mortem drift analysis.
# Additive ONLY: a new session_checkpoints table (CREATE TABLE IF NOT EXISTS) +
# three read/write endpoints over gov.db. NO FROZEN surface is touched (the
# sessions/messages/decisions/hitl_* tables are read, never altered); NO new bus
# envelope is emitted (write-to-DB only). Reuses the existing _open()/_open_rw()/
# _reject_sm_own()/_sm_own_slugs()/_iso_now() helpers (already defined for the
# stale-cleanup + soak-panel features).
#
# POLARITY (G2/M15): every endpoint EXCLUDES SM-self -- the list returns []  for
# an SM project_slug session or the SM_OWN_SESSION_ID; the create POST refuses
# with HTTP 400 {written:false}. project_slug NOT IN the SM slug set is the
# durable read key; session_id != SM_OWN_SESSION_ID is the write gate + backstop.

def _ensure_session_checkpoints(conn: sqlite3.Connection) -> None:
    """Guarded additive CREATE: make the session_checkpoints table if missing.
    Idempotent (CREATE TABLE IF NOT EXISTS). Additive -- no FROZEN surface
    touched. The dashboard reads + writes ONLY this new table; it never alters
    sessions/messages/decisions/hitl_*."""
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS session_checkpoints ("
            "checkpoint_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, "
            "name TEXT, timestamp REAL, "
            "decision_count_at_checkpoint INTEGER, message_count_at_checkpoint INTEGER, "
            "confidence REAL, open_hitl INTEGER, patterns INTEGER, escalations INTEGER, "
            "archived_at REAL)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_session_checkpoints_sid "
            "ON session_checkpoints(session_id)"
        )
    except Exception:
        log.exception("checkpoint-versioning: ensure session_checkpoints table failed")


def _session_is_sm_self(conn: sqlite3.Connection, session_id: str) -> bool:
    """True if this session is SM-self by project_slug (durable read key) OR by
    the injected SM_OWN_SESSION_ID (write gate / backstop). Polarity G2."""
    sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
    if sm_own and str(session_id) == sm_own:
        return True
    slugs = _sm_own_slugs()
    try:
        row = conn.execute(
            "SELECT project_slug FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    except Exception:
        return False
    if row is None:
        return False
    return str(row["project_slug"] or "").strip().lower() in slugs


@app.get("/api/sessions/{session_id}/checkpoints")
async def api_session_checkpoints(session_id: str):
    """List the named digest snapshots for ONE governed session, newest-first.
    Read-only -- modifies NOTHING. Polarity (G2/M15): returns an EMPTY list for
    an SM-self session (project_slug in the SM slug set OR id == SM_OWN_SESSION
    _ID) so SM-self checkpoints are never surfaced. Creates the table lazily
    (guarded) so a fresh DB returns {checkpoints:[]} with HTTP 200 -- never a 500.
    """
    sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
    if not isinstance(session_id, str) or not session_id:
        return {"session_id": "", "checkpoints": [], "own_session_id": sm_own or None}
    try:
        conn = _open_rw()
        _ensure_session_checkpoints(conn)
        # Polarity self-exclude (G2): never list SM-self checkpoints.
        if _session_is_sm_self(conn, session_id):
            conn.close()
            return {"session_id": session_id, "checkpoints": [], "own_session_id": sm_own or None}
        rows = conn.execute(
            "SELECT checkpoint_id, name, timestamp, decision_count_at_checkpoint, "
            "message_count_at_checkpoint, confidence, open_hitl, patterns, escalations "
            "FROM session_checkpoints "
            "WHERE session_id = ? AND archived_at IS NULL "
            "ORDER BY timestamp DESC LIMIT 200",
            (session_id,),
        ).fetchall()
        out = [dict(r) for r in rows]
        conn.close()
        return {"session_id": session_id, "checkpoints": out, "own_session_id": sm_own or None}
    except Exception:
        log.exception("checkpoint-versioning: list failed; degrading to empty")
        return {"session_id": session_id, "checkpoints": [], "own_session_id": None}

# --- POST /api/sessions/{session_id}/checkpoint ---
@app.post("/api/sessions/{session_id}/checkpoint")
async def api_session_checkpoint_create(session_id: str, request: Request):
    """Record a named DIGEST snapshot of one governed session's CURRENT state
    (INSERT one row; <100ms latency budget). Purely observational -- it READS
    the live counts and writes a new session_checkpoints row; it NEVER rewinds or
    mutates the live session, messages, decisions, or hitl_* tables.

    Polarity (G2/M15): REFUSES SM-self with HTTP 400 {written:false} by both
    SM_OWN_SESSION_ID (_reject_sm_own) AND project_slug (loud failure mode, no DB
    row written) -- mirrors the stale-cleanup archive contract. Body: {name}.
    """
    if not isinstance(session_id, str) or not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    _reject_sm_own(session_id)  # HTTP 400 if session_id == SM_OWN_SESSION_ID
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = str((body or {}).get("name") or "manual mark").strip()[:48] or "manual mark"
    try:
        conn = _open_rw()
        _ensure_session_checkpoints(conn)
        # Polarity self-exclude (G2): refuse by project_slug too. Loud failure --
        # HTTP 400, no row written.
        if _session_is_sm_self(conn, session_id):
            conn.close()
            raise HTTPException(status_code=400, detail="refusing to checkpoint SM-self session")
        srow = conn.execute(
            "SELECT id FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if srow is None:
            conn.close()
            raise HTTPException(status_code=404, detail="session not found")
        # Read the CURRENT digest counts (observational; no mutation).
        try:
            mc = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
            ).fetchone()[0]
        except Exception:
            mc = 0
        try:
            dc = conn.execute(
                "SELECT COUNT(*) FROM decisions d JOIN messages m ON d.message_id = m.id "
                "WHERE m.session_id = ?",
                (session_id,),
            ).fetchone()[0]
        except Exception:
            dc = 0
        try:
            conf = conn.execute(
                "SELECT AVG(d.confidence) FROM decisions d JOIN messages m ON d.message_id = m.id "
                "WHERE m.session_id = ?",
                (session_id,),
            ).fetchone()[0]
            conf = float(conf) if conf is not None else None
        except Exception:
            conf = None
        try:
            oh = conn.execute(
                "SELECT COUNT(*) FROM hitl_pending hp JOIN messages m ON hp.message_id = m.id "
                "WHERE m.session_id = ? AND hp.resolved_at IS NULL",
                (session_id,),
            ).fetchone()[0]
        except Exception:
            oh = 0
        import uuid as _uuid
        cid = "ck-" + _uuid.uuid4().hex[:8]
        ts = time.time()
        conn.execute(
            "INSERT INTO session_checkpoints (checkpoint_id, session_id, name, timestamp, "
            "decision_count_at_checkpoint, message_count_at_checkpoint, confidence, "
            "open_hitl, patterns, escalations, archived_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (cid, session_id, name, ts, int(dc), int(mc), conf, int(oh), 0, 0),
        )
        conn.close()
        return {
            "written": True,
            "checkpoint": {
                "checkpoint_id": cid,
                "session_id": session_id,
                "name": name,
                "timestamp": _iso_now(),
                "decision_count_at_checkpoint": int(dc),
                "message_count_at_checkpoint": int(mc),
                "confidence": conf,
                "open_hitl": int(oh),
                "patterns": 0,
                "escalations": 0,
            },
        }
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("checkpoint-versioning: create failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

# --- GET /api/sessions/{session_id}/compare ---
@app.get("/api/sessions/{session_id}/compare")
async def api_session_checkpoint_compare(
    session_id: str, checkpoint_1: str = "", checkpoint_2: str = ""
):
    """Compute the PRE-COMPUTED what-changed delta manifest between two checkpoints
    of ONE governed session (SQLite diff on two stored rows; <500ms budget). All
    drift numbers are computed HERE (server-side); the UI renders them verbatim.
    Read-only -- modifies NOTHING. Polarity (G2/M15): returns an EMPTY shape for
    an SM-self session. Orders the pair so the OLDER checkpoint is checkpoint_1
    (the baseline). Degrades to {} on any error / missing rows (the UI falls back
    to a mock compare).
    """
    if not isinstance(session_id, str) or not session_id or not checkpoint_1 or not checkpoint_2:
        return {}
    try:
        conn = _open_rw()
        _ensure_session_checkpoints(conn)
        if _session_is_sm_self(conn, session_id):
            conn.close()
            return {}
        rows = conn.execute(
            "SELECT checkpoint_id, name, timestamp, decision_count_at_checkpoint, "
            "message_count_at_checkpoint, confidence, open_hitl, escalations "
            "FROM session_checkpoints "
            "WHERE session_id = ? AND checkpoint_id IN (?, ?)",
            (session_id, checkpoint_1, checkpoint_2),
        ).fetchall()
        conn.close()
        if len(rows) < 2:
            return {}
        a, b = (dict(rows[0]), dict(rows[1]))
        # order: older = checkpoint_1 (baseline)
        if (a.get("timestamp") or 0) > (b.get("timestamp") or 0):
            a, b = b, a
        d1 = int(a.get("decision_count_at_checkpoint") or 0)
        d2 = int(b.get("decision_count_at_checkpoint") or 0)
        m1 = int(a.get("message_count_at_checkpoint") or 0)
        m2 = int(b.get("message_count_at_checkpoint") or 0)
        c1 = a.get("confidence")
        c2 = b.get("confidence")
        oh1 = int(a.get("open_hitl") or 0)
        oh2 = int(b.get("open_hitl") or 0)
        e1 = int(a.get("escalations") or 0)
        e2 = int(b.get("escalations") or 0)
        new_hitl = max(0, oh2 - oh1)
        esc_new = max(0, e2 - e1)
        return {
            "checkpoint_1": a.get("checkpoint_id"),
            "checkpoint_2": b.get("checkpoint_id"),
            "name_1": a.get("name"),
            "name_2": b.get("name"),
            "decisions_1": d1,
            "decisions_2": d2,
            "delta_decisions": d2 - d1,
            "messages_1": m1,
            "messages_2": m2,
            "delta_messages": m2 - m1,
            "confidence_1": float(c1) if c1 is not None else None,
            "confidence_2": float(c2) if c2 is not None else None,
            "new_hitl_overrides": {"count": new_hitl, "verdict": "BLOCK"},
            "policy_changes_learned": [],
            "escalation_delta": {
                "count": esc_new,
                "type": "governance_negative_regression" if esc_new > 0 else "",
            },
        }
    except Exception:
        log.exception("checkpoint-versioning: compare failed; degrading to empty")
        return {}


# ============= BETA #undefined : session-dna-heatmap-cross-pattern-topology =============

# --- GET /api/patterns/cross-session-topology ---
# --- GET /api/patterns/cross-session-topology ---
@app.get("/api/patterns/cross-session-topology")
async def api_patterns_cross_session_topology(
    session_id: str | None = None,
    limit: int = 20000,
):
    """Cross-session pattern topology for the BETA session-dna-heatmap (#30).

    Read-only, post-hoc (M18): a render-ready aggregation over the EXISTING
    decisions(matched_hash, confidence) + messages(session_id) + sessions
    (project_slug) + agents rows. ZERO writes, ZERO FROZEN-surface touch, ZERO
    new bus envelope, ZERO new table/column.

    Groups every non-empty matched_hash by (matched_hash, session_id), takes the
    MEAN confidence per (hash, session) pair, then derives a graph:
      nodes:    one per governed (non-SM) session that participated in any
                hashed decision, with its agent roster slugs (FROM DATA, M16).
      patterns: { hash: {level, payload} } from the patterns table (best-effort).
      edges:    one per hash present in >= 2 sessions (the SHARED / spreading
                patterns), carrying the two HIGHEST-confidence sessions + their
                per-session mean confidence (session_a/conf_a, session_b/conf_b).
      isolated: one per hash present in exactly 1 session (single-session only).

    POLARITY (G2 / M15): the SM-own session is excluded at the SQL WHERE on
    sessions.project_slug -- a session whose project_slug is in the SM exclusion
    set (BRIDGE_SM_PROJECT_SLUGS, default {'streamManager'}) can NEVER appear as
    a node; SM_OWN_SESSION_ID is applied as the cheap session-id backstop. The
    dropped tally surfaces as `excluded_self` so the UI can render the polarity
    readout on screen. A decision whose session has no sessions-row is KEPT (it
    is not SM-self) via the IS NULL leg, mirroring /api/escalation-timeline.

    Returns {used_mock, excluded_self, nodes, patterns, edges, isolated}. Always
    used_mock=False here (the live shape); the client substitutes its own mock
    fixture only when this degrades to an EMPTY graph. Degrades to an empty graph
    (HTTP 200, never a 500 / stack leak) on any error or fresh DB.
    """
    empty = {
        "used_mock": False,
        "excluded_self": 0,
        "nodes": [],
        "patterns": {},
        "edges": [],
        "isolated": [],
    }

    # Polarity: durable read key (project_slug) + cheap session-id backstop.
    _sm_slugs_raw = os.environ.get("BRIDGE_SM_PROJECT_SLUGS", "streamManager")
    sm_slugs = [s.strip() for s in _sm_slugs_raw.split(",") if s.strip()]
    sm_own_sid = os.environ.get("SM_OWN_SESSION_ID", "").strip()

    try:
        cap = max(1, min(int(limit or 20000), 50000))
    except Exception:
        cap = 20000

    try:
        conn = _open()
    except Exception:
        log.exception("cross-session-topology: open failed")
        return empty

    try:
        # Aggregate mean confidence per (matched_hash, session_id), SM-self
        # excluded at the SQL WHERE. LEFT JOIN keeps no-session-row decisions
        # (not self). Bounded scan via LIMIT on the newest decisions.
        where = ["d.matched_hash IS NOT NULL", "d.matched_hash != ''"]
        params: list = []
        if session_id:
            where.append("m.session_id = ?")
            params.append(session_id)
        if sm_slugs:
            placeholders = ",".join("?" for _ in sm_slugs)
            where.append(
                f"(s.project_slug IS NULL OR s.project_slug NOT IN ({placeholders}))"
            )
            params.extend(sm_slugs)
        if sm_own_sid:
            where.append("m.session_id != ?")
            params.append(sm_own_sid)
        scan_sql = (
            "SELECT d.matched_hash AS hash, m.session_id AS sid, "
            "d.confidence AS conf "
            "FROM decisions d "
            "JOIN messages m ON d.message_id = m.id "
            "LEFT JOIN sessions s ON s.id = m.session_id "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY d.rowid DESC LIMIT ?"
        )
        params.append(cap)
        rows = conn.execute(scan_sql, tuple(params)).fetchall()

        # excluded_self: how many hashed-decision sessions the filter dropped.
        excluded_self = 0
        try:
            self_where = ["d.matched_hash IS NOT NULL", "d.matched_hash != ''"]
            self_params: list = []
            self_terms = []
            if sm_slugs:
                ph = ",".join("?" for _ in sm_slugs)
                self_terms.append(f"s.project_slug IN ({ph})")
                self_params.extend(sm_slugs)
            if sm_own_sid:
                self_terms.append("m.session_id = ?")
                self_params.append(sm_own_sid)
            if self_terms:
                self_where.append("(" + " OR ".join(self_terms) + ")")
                er = conn.execute(
                    "SELECT COUNT(DISTINCT m.session_id) "
                    "FROM decisions d "
                    "JOIN messages m ON d.message_id = m.id "
                    "LEFT JOIN sessions s ON s.id = m.session_id "
                    f"WHERE {' AND '.join(self_where)}",
                    tuple(self_params),
                ).fetchone()
                excluded_self = int(er[0] or 0) if er else 0
        except Exception:
            excluded_self = 0

        # pattern metadata (best-effort; the matrix renders without it).
        pat_meta: dict[str, dict] = {}
        try:
            if _has_table(conn, "patterns"):
                for pr in conn.execute(
                    "SELECT hash, level, payload FROM patterns"
                ).fetchall():
                    pat_meta[str(pr["hash"])] = {
                        "level": pr["level"],
                        "payload": str(pr["payload"] or ""),
                    }
        except Exception:
            pat_meta = {}
        conn_has_agents = _has_agents_table(conn)
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        log.exception("cross-session-topology: scan failed; degrading to empty")
        return empty

    # Aggregate mean confidence per (hash, sid) in Python (portable across
    # SQLite builds; the scan is already capped + indexed on rowid).
    sums: dict[tuple[str, str], list[float]] = {}
    for r in rows:
        h = str(r["hash"])
        sid = str(r["sid"])
        try:
            c = float(r["conf"])
        except (TypeError, ValueError):
            continue
        sums.setdefault((h, sid), [0.0, 0])
        agg = sums[(h, sid)]
        agg[0] += c
        agg[1] += 1

    # mean[(hash,sid)] = confidence; collect the session set per hash.
    mean: dict[tuple[str, str], float] = {}
    by_hash: dict[str, dict[str, float]] = {}
    sess_ids: set[str] = set()
    for (h, sid), (tot, n) in sums.items():
        if n <= 0:
            continue
        m = round(tot / n, 4)
        mean[(h, sid)] = m
        by_hash.setdefault(h, {})[sid] = m
        sess_ids.add(sid)

    if not by_hash:
        try:
            conn.close()
        except Exception:
            pass
        return {**empty, "excluded_self": excluded_self}

    # node roster: slug (first 8 chars of session id) + project_slug + agents.
    nodes: list[dict] = []
    try:
        for sid in sorted(sess_ids):
            slug = sid[:8] if sid else sid
            proj = ""
            try:
                srow = conn.execute(
                    "SELECT project_slug FROM sessions WHERE id = ?", (sid,)
                ).fetchone()
                if srow is not None:
                    proj = str(srow["project_slug"] or "")
            except Exception:
                proj = ""
            agent_slugs: list[str] = []
            if conn_has_agents:
                try:
                    for ar in conn.execute(
                        "SELECT DISTINCT profile_slug FROM agents "
                        "WHERE session_id = ? AND profile_slug != '' "
                        "ORDER BY profile_slug LIMIT 8",
                        (sid,),
                    ).fetchall():
                        ps = str(ar["profile_slug"] or "").strip()
                        if ps and ps != "unknown":
                            agent_slugs.append(ps)
                except Exception:
                    agent_slugs = []
            nodes.append(
                {
                    "id": sid,
                    "slug": slug,
                    "project_slug": proj,
                    "agent_slugs": agent_slugs,
                }
            )
    finally:
        try:
            conn.close()
        except Exception:
            pass

    # edges (>=2 sessions) carry the two highest-confidence sessions; isolated
    # (exactly 1 session) carry the single occurrence.
    edges: list[dict] = []
    isolated: list[dict] = []
    patterns_out: dict[str, dict] = {}
    for h, per in by_hash.items():
        patterns_out[h] = pat_meta.get(h, {"level": "", "payload": ""})
        ranked = sorted(per.items(), key=lambda kv: kv[1], reverse=True)
        if len(ranked) >= 2:
            (sa, ca), (sb, cb) = ranked[0], ranked[1]
            edges.append(
                {
                    "hash": h,
                    "session_a": sa,
                    "conf_a": ca,
                    "session_b": sb,
                    "conf_b": cb,
                }
            )
        elif len(ranked) == 1:
            (sid_only, c_only) = ranked[0]
            isolated.append(
                {"hash": h, "session_id": sid_only, "confidence": c_only}
            )

    return {
        "used_mock": False,
        "excluded_self": excluded_self,
        "nodes": nodes,
        "patterns": patterns_out,
        "edges": edges,
        "isolated": isolated,
    }


# ============= BETA #undefined : session-story-panel-narrative-arc =============

# --- GET /api/sessions/{session_id}/story ---
def _ensure_session_story_columns(conn: sqlite3.Connection) -> set[str]:
    """Guarded additive ALTER: add the metadata-only narrative columns to the
    sessions table if missing (narrative_markdown / narrative_composed_at /
    narrative_model). SQLite lacks ADD COLUMN IF NOT EXISTS, so check
    table_info first. Idempotent + best-effort; on a read-only (mode=ro)
    connection the ALTER simply fails and we return whatever columns exist.
    Mirrors _ensure_sessions_deleted_at. Returns the present sessions columns.

    NO FROZEN touch: this is a metadata-only additive extension (ADR-18 Rule 1
    precedent); no new table, no new bus envelope, no governance.py /
    message_bus schema-flow change. The columns are written ONLY by the
    deferred out-of-process compose_story CLI tool, never by this UI path.
    """
    want = ("narrative_markdown", "narrative_composed_at", "narrative_model")
    types = {
        "narrative_markdown": "TEXT",
        "narrative_composed_at": "REAL",
        "narrative_model": "TEXT",
    }
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    except Exception:
        return set()
    for c in want:
        if c not in cols:
            try:
                conn.execute(f"ALTER TABLE sessions ADD COLUMN {c} {types[c]}")
                cols.add(c)
            except Exception:
                # read-only conn or concurrent add -- not fatal; treat as absent.
                pass
    return cols


@app.get("/api/sessions/{session_id}/story")
async def api_session_story(session_id: str):
    """BETA #37 session-story-panel-narrative-arc: read the PERSISTED narrative
    metadata for ONE session (if an out-of-process compose has ever written it).

    READ-ONLY + additive. Touches NO FROZEN surface (no governance.py, no
    message_bus schema-flow change, no new bus envelope). The three narrative_*
    columns are a metadata-only additive extension of the sessions table
    (ADR-18 Rule 1 precedent), added lazily + guarded. The live, always-
    available narrative ARC is derived CLIENT-SIDE from the open decision feed;
    this endpoint only surfaces a richer persisted story when one exists and
    otherwise returns {composed:false} so the component falls back to the
    client-side arc / mock.

    POLARITY (G2 / no-self-monitor): returns {composed:false} when the session's
    project_slug is in the SM exclusion set (BRIDGE_SM_PROJECT_SLUGS, default
    {streamManager}) OR the session_id equals SM_OWN_SESSION_ID. The durable
    read key is project_slug; the session-id is the cheap backstop -- mirrors
    the CLAUDE.md polarity split and the sparkline-data endpoint.

    Degrades to {composed:false} on any error / unknown session / fresh DB
    (never a 500 / stack leak / path leak).
    """
    sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
    sm_slugs = _sm_own_slugs()  # lowercased SM-self slug set (polarity G2)

    empty = {
        "session_id": session_id,
        "composed": False,
        "narrative_markdown": None,
        "narrative_composed_at": None,
        "narrative_model": None,
        "decision_count": 0,
    }

    # Session-id backstop: never serve the SM own session's story.
    if sm_own and session_id == sm_own:
        return empty

    try:
        conn = _open()
        cols = _ensure_session_story_columns(conn)
        # Durable read-side polarity key: resolve the session's project_slug and
        # suppress it if it is in the SM exclusion set (case-insensitive). A
        # missing session row yields the empty (not-composed) shape below.
        try:
            srow = conn.execute(
                "SELECT project_slug FROM sessions WHERE id = ? LIMIT 1",
                (session_id,),
            ).fetchone()
        except Exception:
            srow = None
        if srow is None:
            conn.close()
            return empty
        slug = (srow["project_slug"] if isinstance(srow, sqlite3.Row) else srow[0]) or ""
        if str(slug).strip().lower() in sm_slugs:
            conn.close()
            return empty

        # Pull the persisted narrative metadata IF the columns exist. When the
        # compose CLI has never run they are all NULL -> composed:false.
        narrative = None
        composed_at = None
        model = None
        if {"narrative_markdown", "narrative_composed_at", "narrative_model"}.issubset(cols):
            try:
                nrow = conn.execute(
                    "SELECT narrative_markdown, narrative_composed_at, narrative_model "
                    "FROM sessions WHERE id = ? LIMIT 1",
                    (session_id,),
                ).fetchone()
            except Exception:
                nrow = None
            if nrow is not None:
                narrative = nrow["narrative_markdown"] if isinstance(nrow, sqlite3.Row) else nrow[0]
                composed_at = (
                    nrow["narrative_composed_at"]
                    if isinstance(nrow, sqlite3.Row)
                    else nrow[1]
                )
                model = nrow["narrative_model"] if isinstance(nrow, sqlite3.Row) else nrow[2]

        # A best-effort decision count for the meta line (polarity already
        # enforced above via the project_slug suppression).
        try:
            crow = conn.execute(
                "SELECT COUNT(*) AS n FROM decisions d "
                "JOIN messages m ON d.message_id = m.id WHERE m.session_id = ?",
                (session_id,),
            ).fetchone()
            dcount = int(crow["n"] if isinstance(crow, sqlite3.Row) else crow[0]) if crow else 0
        except Exception:
            dcount = 0
        conn.close()
    except Exception:
        log.exception("session-story: query failed")
        return empty

    has_narrative = isinstance(narrative, str) and narrative.strip() != ""
    return {
        "session_id": session_id,
        "composed": bool(has_narrative),
        "narrative_markdown": narrative if has_narrative else None,
        "narrative_composed_at": float(composed_at) if composed_at is not None else None,
        "narrative_model": model if model else None,
        "decision_count": dcount,
    }


# ============= BETA #undefined : sonification-escalation-layer =============


# ============= BETA #undefined : spatial-session-sidebar =============

# --- GET /api/sessions/spatial-overview ---
# ===================== BETA #spatial-session-sidebar : spatial-overview =====================

# Action -> governance-mode map for the spatial node ring. Decisions carry an
# action (ALLOW / L2 / L3 / L4 / BLOCK); the sidebar surfaces the operator-facing
# governance MODE word. Unknown actions fall back to OBSERVE so a node is never
# rendered color-only (M4). Domain-agnostic (M16): no monitored-project vocab.
_SPATIAL_MODE_BY_ACTION = {
    "ALLOW": "OBSERVE",
    "L2": "SUGGEST",
    "L3": "GUIDE",
    "L4": "INTERVENE",
    "BLOCK": "BLOCK",
}


def _spatial_sm_keys() -> tuple[set[str], str]:
    """Polarity keys: the SM project-slug exclusion set (durable read key) and
    the SM own session id (cheap session-id backstop). Mirrors the health-digest
    endpoint exactly."""
    _raw = os.environ.get("BRIDGE_SM_PROJECT_SLUGS", "streamManager")
    slugs = {s.strip() for s in _raw.split(",") if s.strip()}
    own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
    return slugs, own


def _spatial_pattern_edges(conn, sids: list[str], min_count: int = 1) -> list[dict]:
    """Shared-pattern edges between distinct governed sessions. Two sessions are
    linked when they share >= min_count learned pattern hashes (decisions.
    matched_hash) -- the cross-session pattern-flow signal. Read-only. Returns
    [{from_session_id, to_session_id, pattern_count, pattern_hashes}]. The hash
    set per session is bounded; only non-empty matched_hash values count. Edges
    are undirected; we emit one orientation (the more-recent session as `from`
    is not load-bearing -- the UI draws a line either way)."""
    if len(sids) < 2:
        return []
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(decisions)").fetchall()}
        if "matched_hash" not in cols:
            return []
    except Exception:
        return []
    # hash set per session (cap the scan so a huge DB cannot stall the read).
    hashes_by_sid: dict[str, set[str]] = {}
    for sid in sids:
        try:
            rows = conn.execute(
                "SELECT DISTINCT d.matched_hash FROM decisions d "
                "JOIN messages m ON d.message_id = m.id "
                "WHERE m.session_id = ? AND d.matched_hash IS NOT NULL "
                "AND d.matched_hash != '' "
                "ORDER BY d.rowid DESC LIMIT 500",
                (sid,),
            ).fetchall()
            hashes_by_sid[sid] = {str(r[0]) for r in rows if r[0]}
        except Exception:
            hashes_by_sid[sid] = set()
    edges: list[dict] = []
    for i in range(len(sids)):
        for j in range(i + 1, len(sids)):
            a, b = sids[i], sids[j]
            shared = sorted(hashes_by_sid.get(a, set()) & hashes_by_sid.get(b, set()))
            if len(shared) >= max(1, int(min_count or 1)):
                edges.append(
                    {
                        "from_session_id": a,
                        "to_session_id": b,
                        "pattern_count": len(shared),
                        "pattern_hashes": shared[:12],
                    }
                )
    return edges


@app.get("/api/sessions/spatial-overview")
async def api_sessions_spatial_overview(limit: int = 20):
    """BETA #45 spatial-session-sidebar -- one aggregated read of every governed
    NON-SM session as a spatial NODE plus the shared-pattern EDGES between them,
    for the right-rail spatial overview. Read-only (M18, post-hoc -- never on the
    verdict hot path). Opens the DB with the same _open() (mode=ro) pattern as
    every other read endpoint and closes it before returning.

    Node shape: { session_id, project_slug, governance_mode (derived from the
    latest decision action), last_activity_ts, open_hitl, agent_slug,
    latency_sparkline (the last <=10 decision inter-arrival gaps, ms, oldest-
    first -- a SHAPE-only trace, never a severity signal), alert (BLOCK -> the
    M2 'static-rule' word, else null) }. Edge shape: { from_session_id,
    to_session_id, pattern_count, pattern_hashes }.

    POLARITY (G2, CLAUDE.md): SM never presents its own sessions as governed
    targets. The durable read key is project_slug NOT IN the SM slug set
    (BRIDGE_SM_PROJECT_SLUGS, default {streamManager}); SM_OWN_SESSION_ID is the
    cheap session-id backstop. excluded_self surfaces how many rows the filter
    dropped so the UI shows the polarity readout on screen.

    Touches NO FROZEN surface (no governance.py, no message_bus schema change,
    no new bus envelope). Degrades to an empty set (never an error body that
    flips the UI to a false 'live' state) on any failure or fresh DB.
    """
    import time as _time

    now = int(_time.time())
    empty = {"now": now, "excluded_self": 0, "nodes": [], "edges": []}
    sm_slugs, sm_own_sid = _spatial_sm_keys()

    try:
        conn = _open()
    except Exception:
        log.exception("spatial-overview: open failed")
        return empty

    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
        has_hitl = "hitl_mode" in cols
        sel = (
            "id, project_slug, pid, started_at, ended_at, hitl_mode"
            if has_hitl
            else "id, project_slug, pid, started_at, ended_at"
        )
        sess_rows = conn.execute(
            f"SELECT {sel} FROM sessions ORDER BY started_at DESC LIMIT ?",
            (min(max(int(limit or 20), 1), 50),),
        ).fetchall()

        has_agents = _has_agents_table(conn)
        has_hitl_tbl = _has_table(conn, "hitl_pending")

        nodes: list[dict] = []
        kept_sids: list[str] = []
        excluded_self = 0
        for sr in sess_rows:
            sid = sr["id"]
            slug = (sr["project_slug"] or "").strip()
            # POLARITY filter -- durable slug key + session-id backstop.
            if slug in sm_slugs or (sm_own_sid and sid == sm_own_sid):
                excluded_self += 1
                continue

            # latest decision: action -> governance_mode, last_activity_ts.
            governance_mode = "OBSERVE"
            last_activity_ts = 0
            spark: list[int] = []
            try:
                drows = conn.execute(
                    "SELECT d.action AS action, d.timestamp AS ts "
                    "FROM decisions d JOIN messages m ON d.message_id = m.id "
                    "WHERE m.session_id = ? "
                    "ORDER BY d.rowid DESC LIMIT 11",
                    (sid,),
                ).fetchall()
                if drows:
                    latest_action = str(drows[0]["action"] or "").upper()
                    governance_mode = _SPATIAL_MODE_BY_ACTION.get(latest_action, "OBSERVE")
                    try:
                        last_activity_ts = int(float(drows[0]["ts"] or 0))
                    except Exception:
                        last_activity_ts = 0
                    # latency sparkline: inter-arrival gaps (ms) between the last
                    # <=11 decisions, oldest-first -> <=10 points. Shape-only.
                    ts_desc = [d["ts"] for d in drows if d["ts"] is not None]
                    ts_chron = list(reversed(ts_desc))
                    for k in range(1, len(ts_chron)):
                        try:
                            gap = max(0.0, (float(ts_chron[k]) - float(ts_chron[k - 1])) * 1000.0)
                            spark.append(int(min(gap, 60000)))
                        except Exception:
                            continue
            except Exception:
                governance_mode = "OBSERVE"

            if last_activity_ts == 0:
                # fall back to session timing so recency placement is stable.
                try:
                    last_activity_ts = int(float(
                        sr["ended_at"]
                        if sr["ended_at"] is not None
                        else (sr["started_at"] or now)
                    ))
                except Exception:
                    last_activity_ts = now

            # open_hitl (unresolved hitl_pending rows joined on the session).
            open_hitl = 0
            if has_hitl_tbl:
                try:
                    open_hitl = conn.execute(
                        "SELECT COUNT(*) FROM hitl_pending hp "
                        "JOIN messages m ON hp.message_id = m.id "
                        "WHERE hp.resolved_at IS NULL AND m.session_id = ?",
                        (sid,),
                    ).fetchone()[0]
                except Exception:
                    open_hitl = int(open_hitl or 0)

            # agent_slug -- the most-recently-seen agent profile for the session.
            agent_slug = ""
            if has_agents:
                try:
                    arow = conn.execute(
                        "SELECT profile_slug FROM agents "
                        "WHERE session_id = ? ORDER BY last_seen DESC LIMIT 1",
                        (sid,),
                    ).fetchone()
                    if arow is not None:
                        agent_slug = str(arow["profile_slug"] or "")
                except Exception:
                    agent_slug = ""

            # alert: a BLOCK-mode node carries the literal M2 'static-rule' word
            # (paired with the pulsing outline in the UI). No escalation table
            # exists in the schema; the alert is reachable from the verdict mode
            # only (never fabricated). Non-BLOCK -> null.
            alert = "static-rule" if governance_mode == "BLOCK" else None

            nodes.append(
                {
                    "session_id": sid,
                    "project_slug": slug or str(sid),
                    "governance_mode": governance_mode,
                    "last_activity_ts": last_activity_ts,
                    "open_hitl": int(open_hitl or 0),
                    "agent_slug": agent_slug,
                    "latency_sparkline": spark[-10:],
                    "alert": alert,
                }
            )
            kept_sids.append(sid)

        edges = _spatial_pattern_edges(conn, kept_sids, min_count=1)
        conn.close()
        return {"now": now, "excluded_self": excluded_self, "nodes": nodes, "edges": edges}
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        log.exception("spatial-overview: aggregation failed")
        return empty

# --- GET /api/sessions/pattern-edges ---
@app.get("/api/sessions/pattern-edges")
async def api_sessions_pattern_edges(min_pattern_count: int = 1, limit: int = 20):
    """BETA #45 spatial-session-sidebar -- standalone shared-pattern EDGE read
    (used when the overview is already cached and only the cross-session pattern
    flows need refreshing). Returns { edges:[{from_session_id, to_session_id,
    pattern_count, pattern_hashes}], excluded_self }. Two governed sessions are
    linked when they share >= min_pattern_count learned pattern hashes
    (decisions.matched_hash).

    READ-ONLY (M18, post-hoc). POLARITY (G2): only governed NON-SM sessions are
    considered -- project_slug NOT IN the SM slug set (durable key) AND session_id
    != SM_OWN_SESSION_ID (backstop); excluded_self surfaces the dropped self
    rows. Touches NO FROZEN surface. Degrades to {edges:[], excluded_self:0} on
    any error / fresh DB.
    """
    empty = {"edges": [], "excluded_self": 0}
    sm_slugs, sm_own_sid = _spatial_sm_keys()

    try:
        conn = _open()
    except Exception:
        log.exception("pattern-edges: open failed")
        return empty

    try:
        if not _has_table(conn, "sessions"):
            conn.close()
            return empty
        sess_rows = conn.execute(
            "SELECT id, project_slug FROM sessions ORDER BY started_at DESC LIMIT ?",
            (min(max(int(limit or 20), 1), 50),),
        ).fetchall()
        kept_sids: list[str] = []
        excluded_self = 0
        for sr in sess_rows:
            sid = sr["id"]
            slug = (sr["project_slug"] or "").strip()
            if slug in sm_slugs or (sm_own_sid and sid == sm_own_sid):
                excluded_self += 1
                continue
            kept_sids.append(sid)
        edges = _spatial_pattern_edges(conn, kept_sids, min_count=min_pattern_count)
        conn.close()
        return {"edges": edges, "excluded_self": excluded_self}
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        log.exception("pattern-edges: query failed")
        return empty


# ============= BETA #undefined : temporal-scrubber-governance-audit =============

# --- GET /api/decisions/replay-diff/sessions ---
# ===================== BETA #temporal-scrubber-governance-audit =====================

# --- GET /api/decisions/replay-diff/sessions ---
@app.get("/api/decisions/replay-diff/sessions")
async def api_replay_diff_sessions():
    """Polarity-filtered NON-SM session picker for the BETA temporal-scrubber
    (#47). Additive READ-ONLY. Returns governed sessions that carry stored
    decisions, each {session_id, project_slug, decision_count}, newest-activity
    first, plus an {excluded_self} tally so the picker renders self-exclusion as
    a VISIBLE feature (G2). SM-self is excluded server-side:

      - project_slug NOT IN (STREAM_MANAGER_PROJECT_SLUGS)  -- durable read key
      - session_id != SM_OWN_SESSION_ID                     -- session backstop

    Read-only, post-hoc (M18): aggregates only sessions + decisions + messages.
    ZERO writes, ZERO FROZEN-surface touch, ZERO new bus envelope. Degrades to
    {sessions: []} with HTTP 200 on any error / fresh DB (never a 500 / stack
    leak) so the client falls back to deterministic mock.
    """
    try:
        conn = _open()
        if not _has_table(conn, "decisions") or not _has_table(conn, "messages"):
            conn.close()
            return {"sessions": [], "excluded_self": 0, "own_session_id": None}
        sm_slugs_raw = os.environ.get("BRIDGE_SM_PROJECT_SLUGS", "streamManager")
        sm_slugs = [s.strip().lower() for s in sm_slugs_raw.split(",") if s.strip()]
        sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
        has_sessions = _has_table(conn, "sessions")
        join_sql = "LEFT JOIN sessions s ON m.session_id = s.id " if has_sessions else ""
        slug_sel = "s.project_slug AS project_slug " if has_sessions else "'' AS project_slug "
        # Count governed decisions per session; surface the dropped self tally.
        where = ["1=1"]
        params: list = []
        if has_sessions and sm_slugs:
            placeholders = ",".join("?" for _ in sm_slugs)
            where.append(
                "(s.project_slug IS NULL OR LOWER(s.project_slug) NOT IN (" + placeholders + "))"
            )
            params.extend(sm_slugs)
        if sm_own:
            where.append("m.session_id != ?")
            params.append(sm_own)
        sql = (
            "SELECT m.session_id AS session_id, " + slug_sel + ", "
            "COUNT(*) AS decision_count, MAX(d.timestamp) AS last_ts "
            "FROM decisions d JOIN messages m ON d.message_id = m.id "
            + join_sql
            + "WHERE " + " AND ".join(where)
            + " GROUP BY m.session_id ORDER BY last_ts DESC LIMIT 200"
        )
        gov_rows = conn.execute(sql, tuple(params)).fetchall()
        # excluded_self = governed-decision-bearing sessions that ARE SM-self.
        excluded_self = 0
        if has_sessions and (sm_slugs or sm_own):
            self_where = []
            self_params: list = []
            if sm_slugs:
                ph = ",".join("?" for _ in sm_slugs)
                self_where.append("LOWER(s.project_slug) IN (" + ph + ")")
                self_params.extend(sm_slugs)
            if sm_own:
                self_where.append("m.session_id = ?")
                self_params.append(sm_own)
            self_sql = (
                "SELECT COUNT(DISTINCT m.session_id) AS n "
                "FROM decisions d JOIN messages m ON d.message_id = m.id "
                "LEFT JOIN sessions s ON m.session_id = s.id "
                "WHERE " + " OR ".join(self_where)
            )
            r = conn.execute(self_sql, tuple(self_params)).fetchone()
            excluded_self = int(r["n"]) if r and r["n"] is not None else 0
        conn.close()
        out = []
        for r in gov_rows:
            d = dict(r)
            out.append({
                "session_id": d.get("session_id"),
                "project_slug": d.get("project_slug") or "",
                "decision_count": int(d.get("decision_count") or 0),
            })
        return {"sessions": out, "excluded_self": excluded_self, "own_session_id": (sm_own or None)}
    except Exception:
        log.exception("replay-diff/sessions: query failed; degrading to empty")
        return {"sessions": [], "excluded_self": 0, "own_session_id": None}

# --- GET /api/decisions/replay-diff ---
# --- GET /api/decisions/replay-diff ---
@app.get("/api/decisions/replay-diff")
async def api_replay_diff(
    session_id: str | None = None,
    a: float = 8.0,
    b: float = 70.0,
):
    """READ-ONLY replay-diff over the STORED decision stream for one governed
    session, for the BETA temporal-scrubber (#47).

    `a` and `b` are 0..100 scrubber-handle positions across the session's
    decision-time span (min(timestamp)..max(timestamp)). The server slices a
    window around each handle, keys comparable decisions by a normalized content
    fingerprint, takes the NEWEST decision per fingerprint within each window,
    and pairs fingerprints that appear in BOTH windows into diff rows. Each row:
      {key, content,
       window_a:{action,confidence,layer,model_used,matched_hash,content,timestamp},
       window_b:{...}}
    The client pre-computes the confidence delta + verdict-change + heat band
    from the two sides (deterministic archaeology).

    POLARITY (G2 / M15): SM-self is excluded server-side BEFORE any window slice
      - project_slug NOT IN (STREAM_MANAGER_PROJECT_SLUGS)  -- durable read key
      - m.session_id != SM_OWN_SESSION_ID                   -- session backstop
    An SM-self session_id therefore yields zero rows (the scope can never be
    self). {excluded_self} surfaces the dropped self tally for the visible
    polarity readout.

    Read-only, post-hoc (M18): a single aggregation over indexed
    decisions(timestamp) + messages(session_id). ZERO writes, ZERO FROZEN-surface
    touch, ZERO new bus envelope, ZERO spawn/cron/subprocess. Degrades to a
    {rows: []} shape with HTTP 200 on any error / empty window (never a 500 /
    stack leak); the client then falls back to deterministic mock.
    """
    try:
        if not session_id:
            return {
                "session_id": "",
                "project_slug": "",
                "window_a_label": "window A",
                "window_b_label": "window B",
                "rows": [],
                "excluded_self": 0,
                "polarity_filtered": True,
            }
        # clamp + order the two handle positions into a low/high pair.
        try:
            pa = max(0.0, min(100.0, float(a)))
            pb = max(0.0, min(100.0, float(b)))
        except (TypeError, ValueError):
            pa, pb = 8.0, 70.0
        plo, phi = (pa, pb) if pa <= pb else (pb, pa)
        conn = _open()
        if not _has_table(conn, "decisions") or not _has_table(conn, "messages"):
            conn.close()
            return {
                "session_id": session_id,
                "project_slug": "",
                "window_a_label": "window A",
                "window_b_label": "window B",
                "rows": [],
                "excluded_self": 0,
                "polarity_filtered": True,
            }
        sm_slugs_raw = os.environ.get("BRIDGE_SM_PROJECT_SLUGS", "streamManager")
        sm_slugs = [s.strip().lower() for s in sm_slugs_raw.split(",") if s.strip()]
        sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
        has_sessions = _has_table(conn, "sessions")
        # Resolve the requested scope's project_slug + assert it is NOT SM-self.
        project_slug = ""
        is_self = False
        if has_sessions:
            srow = conn.execute(
                "SELECT project_slug FROM sessions WHERE id = ? LIMIT 1", (session_id,)
            ).fetchone()
            if srow is not None:
                project_slug = (srow["project_slug"] or "")
                if sm_slugs and project_slug.strip().lower() in sm_slugs:
                    is_self = True
        if sm_own and session_id == sm_own:
            is_self = True
        if is_self:
            conn.close()
            # Polarity: an SM-self scope yields zero rows + a surfaced self tally.
            return {
                "session_id": session_id,
                "project_slug": project_slug,
                "window_a_label": "window A",
                "window_b_label": "window B",
                "rows": [],
                "excluded_self": 1,
                "polarity_filtered": True,
            }
        # Pull this governed session's decision stream (oldest-first), with the
        # polarity WHERE applied belt-and-suspenders (the scope is already proven
        # non-self above; this guards a NULL-session join edge).
        join_sql = "LEFT JOIN sessions s ON m.session_id = s.id " if has_sessions else ""
        where = ["m.session_id = ?"]
        params: list = [session_id]
        if has_sessions and sm_slugs:
            ph = ",".join("?" for _ in sm_slugs)
            where.append("(s.project_slug IS NULL OR LOWER(s.project_slug) NOT IN (" + ph + "))")
            params.extend(sm_slugs)
        if sm_own:
            where.append("m.session_id != ?")
            params.append(sm_own)
        sql = (
            "SELECT d.action AS action, d.confidence AS confidence, "
            "COALESCE(d.layer, 0) AS layer, COALESCE(d.model_used, '') AS model_used, "
            "COALESCE(d.matched_hash, '') AS matched_hash, d.timestamp AS ts, "
            "COALESCE(m.content, '') AS content "
            "FROM decisions d JOIN messages m ON d.message_id = m.id "
            + join_sql
            + "WHERE " + " AND ".join(where)
            + " ORDER BY d.timestamp ASC LIMIT 20000"
        )
        rows = conn.execute(sql, tuple(params)).fetchall()
        conn.close()
        recs = []
        for r in rows:
            try:
                ts = float(r["ts"])
            except (TypeError, ValueError):
                continue
            recs.append({
                "action": str(r["action"] or "ALLOW").upper(),
                "confidence": float(r["confidence"]) if r["confidence"] is not None else 0.0,
                "layer": int(r["layer"] or 0),
                "model_used": str(r["model_used"] or ""),
                "matched_hash": str(r["matched_hash"] or ""),
                "timestamp": ts,
                "content": str(r["content"] or ""),
            })
        if len(recs) < 2:
            return {
                "session_id": session_id,
                "project_slug": project_slug,
                "window_a_label": "window A",
                "window_b_label": "window B",
                "rows": [],
                "excluded_self": 0,
                "polarity_filtered": True,
            }
        t_min = recs[0]["timestamp"]
        t_max = recs[-1]["timestamp"]
        span = max(1e-6, t_max - t_min)
        # window half-width = 12% of the span (a readable 24% band), >= 1 second.
        half = max(1.0, span * 0.12)
        ca = t_min + span * (plo / 100.0)
        cb = t_min + span * (phi / 100.0)

        def _norm_fp(text: str) -> str:
            # stable content fingerprint: collapse whitespace + lowercase, cap len.
            return " ".join(str(text or "").split()).lower()[:200]

        def _slice(center: float):
            # newest decision per fingerprint within [center-half, center+half].
            picked: dict = {}
            for rec in recs:
                if rec["timestamp"] < center - half or rec["timestamp"] > center + half:
                    continue
                fp = _norm_fp(rec["content"])
                if not fp:
                    continue
                prev = picked.get(fp)
                if prev is None or rec["timestamp"] >= prev["timestamp"]:
                    picked[fp] = rec
            return picked

        win_a = _slice(ca)
        win_b = _slice(cb)

        import datetime as _dt

        def _clock(t: float) -> str:
            try:
                return _dt.datetime.fromtimestamp(t).strftime("%H:%M") + "Z"
            except Exception:
                return "--"

        def _side(rec: dict) -> dict:
            return {
                "action": rec["action"],
                "confidence": round(rec["confidence"], 4),
                "layer": rec["layer"],
                "model_used": rec["model_used"],
                "matched_hash": rec["matched_hash"],
                "content": rec["content"],
                "timestamp": _clock(rec["timestamp"]),
            }

        # pair fingerprints present in BOTH windows (the comparable-message set).
        out_rows = []
        for fp in win_a:
            if fp in win_b:
                ra = win_a[fp]
                rb = win_b[fp]
                out_rows.append({
                    "key": fp[:80] or ("row-" + str(len(out_rows))),
                    "content": rb["content"] or ra["content"],
                    "window_a": _side(ra),
                    "window_b": _side(rb),
                })
        out_rows.sort(key=lambda x: x["content"].lower())
        out_rows = out_rows[:200]
        return {
            "session_id": session_id,
            "project_slug": project_slug,
            "window_a_label": _clock(ca - half) + " -- " + _clock(ca + half),
            "window_b_label": _clock(cb - half) + " -- " + _clock(cb + half),
            "rows": out_rows,
            "excluded_self": 0,
            "polarity_filtered": True,
        }
    except Exception:
        log.exception("replay-diff: query failed; degrading to empty")
        return {
            "session_id": session_id or "",
            "project_slug": "",
            "window_a_label": "window A",
            "window_b_label": "window B",
            "rows": [],
            "excluded_self": 0,
            "polarity_filtered": True,
        }


# ============= BETA #undefined : time-machine-governance-replay =============

# --- POST /api/time-machine/replay ---
# ===================== BETA #time-machine-governance-replay =====================

# Action restrictiveness ranking -- mirrors governance.py _ACTION_RANK so the
# server re-derivation matches the live post-engine overlay byte-for-byte.
_TM_ACTION_RANK: dict[str, int] = {
    "ALLOW": 0, "OBSERVE": 0, "SUGGEST": 1, "GUIDE": 2, "INTERVENE": 3, "BLOCK": 4,
}


def _tm_cap_action(current: str, ceiling: str) -> str:
    """Cap an action UP to a ceiling (mirrors governance.py _cap_action)."""
    cur = _TM_ACTION_RANK.get(current, 0)
    ceil = _TM_ACTION_RANK.get(ceiling, 0)
    return ceiling if ceil > cur else current


# --- POST /api/time-machine/replay ---
@app.post("/api/time-machine/replay")
async def api_time_machine_replay(body: dict | None = None):
    """BETA #48 time-machine-governance-replay: counterfactual REPLAY of the
    deterministic post-engine confidence-floor overlay over already-stored
    governed (non-SM) decisions in a time window.

    READ-ONLY + additive (M18, post-hoc -- never on the verdict hot path). Opens
    the DB with the same ``_open()`` (mode=ro) pattern as every other read
    endpoint and closes it before returning. RE-DERIVES the overlay deterministic-
    ally (``_tm_cap_action`` + the confidence_floor block, mirroring
    governance.py) under the operator's TRIAL floor -- it NEVER re-calls the
    model, NEVER publishes a bus envelope (NO new envelope kind), NEVER mutates a
    FROZEN surface, and persists NOTHING.

    POLARITY (G2 / no-self-monitor): the SM-own session is excluded at the SQL
    WHERE on sessions.project_slug (durable read key: BRIDGE_SM_PROJECT_SLUGS,
    default {streamManager}) plus a SM_OWN_SESSION_ID session-id backstop. The
    dropped self-row count is surfaced as ``excluded_self``.

    Body: {time_range_start:ms, time_range_end:ms, confidence_floor:0..1,
    hitl_mode?:'sync'|'async'}. Returns {window, config_delta, summary, 
    excluded_self, mock, rows:[...]}. Degrades to a SAFE empty {mock:true,
    rows:[]} shape on any error / empty window so the client falls back to its
    own deterministic mock (never reads as live when the server is down).
    """
    b = body if isinstance(body, dict) else {}
    try:
        end_ms = int(b.get("time_range_end") or 0)
    except Exception:
        end_ms = 0
    try:
        start_ms = int(b.get("time_range_start") or 0)
    except Exception:
        start_ms = 0
    if end_ms <= 0:
        end_ms = int(time.time() * 1000)
    if start_ms <= 0 or start_ms >= end_ms:
        start_ms = end_ms - 60 * 60 * 1000
    try:
        trial_floor = float(b.get("confidence_floor"))
    except Exception:
        trial_floor = 0.5
    trial_floor = min(1.0, max(0.0, trial_floor))
    hitl_mode = str(b.get("hitl_mode") or "").strip().lower() or None
    if hitl_mode not in ("sync", "async", None):
        hitl_mode = None

    # decisions.timestamp is epoch SECONDS; convert the ms window bounds.
    start_s = start_ms / 1000.0
    end_s = end_ms / 1000.0

    empty = {
        "window": {"start_ms": start_ms, "end_ms": end_ms, "label": "window"},
        "config_delta": {"confidence_floor": {"from": None, "to": trial_floor},
                         "hitl_mode": hitl_mode},
        "summary": {"checked": 0, "changed": 0, "escalated": 0,
                    "released": 0, "na": 0, "mock": True},
        "excluded_self": 0, "mock": True, "rows": [],
    }

    # Polarity: durable slug key + session-id backstop.
    _sm_slugs_raw = os.environ.get("BRIDGE_SM_PROJECT_SLUGS", "streamManager")
    sm_slugs = [s.strip() for s in _sm_slugs_raw.split(",") if s.strip()]
    sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()

    try:
        conn = _open()
    except Exception:
        log.exception("time-machine: open failed")
        return empty

    try:
        where = ["d.timestamp >= ?", "d.timestamp < ?"]
        params: list = [start_s, end_s]
        if sm_slugs:
            placeholders = ",".join("?" for _ in sm_slugs)
            # s.project_slug IS NULL => no session row => keep (not self).
            where.append(
                f"(s.project_slug IS NULL OR s.project_slug NOT IN ({placeholders}))"
            )
            params.extend(sm_slugs)
        if sm_own:
            where.append("m.session_id != ?")
            params.append(sm_own)
        sql = (
            "SELECT d.id AS decision_id, d.message_id AS message_id, "
            "d.action AS action, d.confidence AS confidence, "
            "d.reasoning AS reasoning, d.timestamp AS ts, "
            "m.session_id AS session_id, s.project_slug AS project_slug "
            "FROM decisions d "
            "JOIN messages m ON d.message_id = m.id "
            "LEFT JOIN sessions s ON s.id = m.session_id "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY d.timestamp DESC LIMIT 500"
        )
        rows = conn.execute(sql, tuple(params)).fetchall()

        # excluded_self: how many in-window rows the polarity filter dropped
        # (slug-self OR session-id-self), surfaced for the on-screen readout.
        excluded_self = 0
        try:
            ex_where = ["d.timestamp >= ?", "d.timestamp < ?"]
            ex_params: list = [start_s, end_s]
            ors = []
            if sm_slugs:
                placeholders = ",".join("?" for _ in sm_slugs)
                ors.append(f"s.project_slug IN ({placeholders})")
                ex_params_extra = list(sm_slugs)
            else:
                ex_params_extra = []
            if sm_own:
                ors.append("m.session_id = ?")
            if ors:
                ex_where.append("(" + " OR ".join(ors) + ")")
            ex_sql = (
                "SELECT COUNT(*) FROM decisions d "
                "JOIN messages m ON d.message_id = m.id "
                "LEFT JOIN sessions s ON s.id = m.session_id "
                f"WHERE {' AND '.join(ex_where)}"
            )
            ex_all = list(ex_params) + ex_params_extra + ([sm_own] if sm_own else [])
            er = conn.execute(ex_sql, tuple(ex_all)).fetchone()
            excluded_self = int(er[0] or 0) if er else 0
        except Exception:
            excluded_self = 0
        conn.close()
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        log.exception("time-machine: replay query failed; degrading to empty")
        return empty

    if not rows:
        # No governed in-window decisions -> let the client render its mock.
        return empty

    out_rows: list[dict] = []
    changed = escalated = released = na = 0
    for r in rows:
        d = dict(r)
        orig = str(d.get("action") or "ALLOW").upper()
        try:
            conf = float(d.get("confidence") or 0.0)
        except Exception:
            conf = 0.0
        orig_rank = _TM_ACTION_RANK.get(orig, 0)
        # N/A: an escalation the confidence floor did NOT cause (a hard
        # blocked-op / restricted-op match) -- the floor knob cannot move it.
        # Heuristic mirrors the client: confidence at/above the trial floor yet
        # the action is already >= GUIDE.
        if conf >= trial_floor and orig_rank >= _TM_ACTION_RANK["GUIDE"]:
            replay = orig
            applies = False
        else:
            # The trial floor IS the lever. A row the floor escalated rides at an
            # ALLOW baseline when un-floored; we model that baseline as ALLOW for
            # rows that are >= GUIDE and below the floor, else keep the original.
            base = (
                "ALLOW"
                if (orig_rank >= _TM_ACTION_RANK["GUIDE"] and conf < trial_floor)
                else orig
            )
            replay = _tm_cap_action(base, "GUIDE") if conf < trial_floor else base
            applies = True
        affected = applies and replay != orig
        if applies:
            if affected:
                changed += 1
                if _TM_ACTION_RANK.get(replay, 0) > orig_rank:
                    escalated += 1
                else:
                    released += 1
        else:
            na += 1
        replay_reason = (
            str(d.get("reasoning") or "floor does not apply to this decision")
            if not applies
            else (
                f"confidence_floor {trial_floor:.2f} (got {conf:.2f}) -> escalated to GUIDE"
                if conf < trial_floor
                else (
                    f"confidence_floor {trial_floor:.2f} (got {conf:.2f}) -> "
                    f"floor not tripped; {replay}"
                )
            )
        )
        try:
            ts_ms = int(float(d.get("ts") or 0) * 1000)
        except Exception:
            ts_ms = 0
        out_rows.append({
            "decision_id": str(d.get("decision_id") or ""),
            "message_id": str(d.get("message_id") or ""),
            "timestamp_ms": ts_ms,
            "confidence": conf,
            "original_action": orig,
            "replay_action": replay,
            "applies": applies,
            "affected": affected,
            "original_reason": str(d.get("reasoning") or "original decision"),
            "replay_reason": replay_reason,
            "project_slug": str(d.get("project_slug") or ""),
            "session_id": str(d.get("session_id") or ""),
        })

    return {
        "window": {"start_ms": start_ms, "end_ms": end_ms, "label": "window"},
        "config_delta": {
            "confidence_floor": {"from": None, "to": trial_floor},
            "hitl_mode": hitl_mode,
        },
        "summary": {
            "checked": len(out_rows), "changed": changed, "escalated": escalated,
            "released": released, "na": na, "mock": False,
        },
        "excluded_self": excluded_self,
        "mock": False,
        "rows": out_rows,
    }


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
