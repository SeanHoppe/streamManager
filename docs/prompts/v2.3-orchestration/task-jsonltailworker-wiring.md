# Task — JsonlTailWorker.start() production wiring (🟡 Seed 6, 3rd-cycle deferred)

> Minted 2026-05-17 as part of v2.3-pm-mint PR. Comparison anchor:
> `docs/v2.3-next-steps.md` §"Seed 6 — 🟡 JsonlTailWorker.start()
> production wiring".
>
> **CONDITIONAL.** Fires P1 ONLY IF v2.3 cycle type = feature.
> Consolidation cycle defers to v2.4 — but third consecutive deferral
> triggers escalation per `docs/v2.3-next-steps.md`.

## Why

`src/stream_manager/jsonl_tail.py:86 JsonlTailWorker` is built,
tested (5 test files construct it), but **never started in
production code**. `grep -rn "JsonlTailWorker(" src/ tools/` returns
zero matches outside tests; `grep -rn "set_active_worker" src/`
shows only the setter definition, no caller.

Three other startup peers (CLI pool, EngineRegistry, session_watcher)
ARE wired at `dashboard/server.py:241 @app.on_event("startup")`.
JsonlTailWorker should be peer #4.

Standing as a deferred-three-cycles item is itself a smell —
dead-at-runtime code accumulates surface without runtime exercise.
ADR-18 surface freeze + Rule 6 memory pre-flight argue for either
wiring or removing.

## Cycle-type gate

- **v2.3 = feature**: FIRE this task. Counts toward
  `WIRED_LEVER_LEDGER_COUNT` increment 0 → 1 (satisfies feature
  classification per ADR-18).
- **v2.3 = consolidation**: DEFER this task to v2.4. P0 PR body
  MUST cite the third-deferral escalation note: "JsonlTailWorker
  deferred v2.1 → v2.2 → v2.3. v2.4 P0 MUST either wire or
  document removal." If v2.4 also defers, v2.5 P0 cycle frame
  treats it as dead code and proposes removal PR.

## Deliverable (when fired)

### 1. Wire at dashboard startup

`dashboard/server.py` `_startup_cli_pool` (or rename event handler
to `_startup_dashboard`):

```python
# v2.3 P1: JsonlTailWorker production wiring (Seed 6, deferred v2.1 →
# v2.2). Daemon thread; idempotent; failure must not block dashboard.
try:
    from stream_manager.jsonl_tail import (
        JsonlTailWorker, set_active_worker,
    )
    from stream_manager.agent_registry import AgentRegistry
    bus = _get_bus()
    if bus is not None:
        projects_dir = Path(
            os.environ.get(
                "BRIDGE_PROJECTS_DIR",
                str(Path.home() / ".claude" / "projects"),
            )
        )
        registry = AgentRegistry()  # or _get_agent_registry() if helper exists
        worker = JsonlTailWorker(
            projects_dir=projects_dir,
            registry=registry,
            bus=bus,
            governance=_get_governance_engine(),  # required per v2.1 P2 canary
        )
        session_id = os.environ.get("SM_OWN_SESSION_ID", "")
        project_slug = os.environ.get("BRIDGE_PROJECT_SLUG", "default")
        worker.start(session_id=session_id, project_slug=project_slug)
        set_active_worker(worker)
except Exception:
    log.exception("jsonl_tail: startup raised; continuing")
```

### 2. Shutdown hook

`_shutdown_cli_pool_event`:

```python
try:
    from stream_manager.jsonl_tail import get_active_worker, set_active_worker
    w = get_active_worker()
    if w is not None:
        w.stop()  # confirm method name; may be _stop_event.set()
        set_active_worker(None)
except Exception:
    log.exception("jsonl_tail: shutdown raised; continuing")
```

Verify `JsonlTailWorker` has a public `stop()` method; if only
`_stop_event` exists, mint `stop()` as a 3-line public wrapper.

### 3. Env contract documentation

`docs/learn-mode-design.md` or equivalent:

- `BRIDGE_PROJECTS_DIR` — overrides default `~/.claude/projects/`.
- `SM_OWN_SESSION_ID` — SM's own Claude Code session id to filter
  per `feedback_no_self_monitor.md` polarity-flip rule.
- `BRIDGE_PROJECT_SLUG` — project slug for bus.open_session
  registration.

### 4. SM-self-filter cross-check

Per CLAUDE.md §"Session-source exception rule (polarity-flip)" + 
`feedback_no_self_monitor.md`, the worker MUST filter out SM's own
session JSONL. Verify `jsonl_tail._is_sm_originated` consults
`SM_OWN_SESSION_ID` AND the project-slug exclusion list
(`STREAM_MANAGER_PROJECT_SLUGS`). Add a startup-time log line:

```
[startup] jsonl_tail: SM-self filter active (own_session=<id>, excl_slugs=<list>)
```

If the filter is misconfigured at runtime, this turns into the loud
failure path Per CLAUDE.md ("default-exclude makes leakage the loud
failure path").

## Tests

`tests/test_dashboard_startup_jsonl_tail.py` (NEW, ~ 40 LOC):

- Fixture: `TestClient(app)` lifecycle.
- Assert `get_active_worker()` returns a non-None instance after
  startup.
- Assert worker thread is alive.
- Assert shutdown stops the worker (post-context-manager exit).

## Cycle-discipline (Amendment A — feature cycle assumption)

- Production (`src/`): 0 LOC (uses existing `JsonlTailWorker`).
- Dashboard (`dashboard/`): ~ 25 LOC additive in `server.py`.
  **Counts as production for Amendment A bucket.**
- Test (`tests/`): ~ 40 LOC. Advisory.
- Docs: ~ 15 LOC env-contract block in `learn-mode-design.md`.

Net: ~ 40 LOC production-bucket; well under feature soft target
1500.

Lever ledger increment: **0 → 1** (first wired lever since v1.7
cycle close).

## DoD

- [ ] Wired at `dashboard/server.py` startup + shutdown.
- [ ] Env contract documented.
- [ ] SM-self filter startup log line emits at boot (manual smoke
      test: `uvicorn dashboard.server:app` + check log).
- [ ] `tests/test_dashboard_startup_jsonl_tail.py` PASSES.
- [ ] Local Tier-3 soak with `tools/soak_driver.py` confirms the
      worker actually receives JSONL lines from a parallel Claude
      Code session (smoke test, not formal soak).
- [ ] `WIRED_LEVER_LEDGER_COUNT` incremented in `docs/v2.3-task-
      plan.md` from 0 to 1 (with cross-link to this PR).
- [ ] `docs/v2.3-next-steps.md` Seed 6 row updated:
      `[x] Seed 6 — wired PR #___`.
- [ ] `docs/v2.1-backlog.md` + `docs/v2.2-backlog.md` carry-forward
      entries annotated `RESOLVED v2.3 PR #___`.

## Refs

- `src/stream_manager/jsonl_tail.py:86 JsonlTailWorker`,
  L128 `.start()`.
- `dashboard/server.py:241 _startup_cli_pool`.
- `feedback_no_self_monitor.md` §"Polarity flip".
- `CLAUDE.md` §"Session-source exception rule".
- `docs/v2.1-backlog.md` §"Carry-forwards from v2.1" #1.
- `docs/v2.2-backlog.md` §"Carry-forwards from v2.1 (dispositions at
  v2.2 P0)" #1.
