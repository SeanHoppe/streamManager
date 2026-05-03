You are implementing **Task C — Claude Code lifecycle bridge** from the streamManager v1.2 ship cycle.

## Branch + base
- Base your work on `ship/v1.2-scope` (NOT main, NOT ship/v1.1-scope).
- Open PR targeting `ship/v1.2-scope`.
- If `ship/v1.2-scope` does not yet exist, ABORT and tell the user to cut it from `main`.

## ⚠️ CRITICAL: Do-not-touch guard

v1.1.0 was tagged on 2026-05-03 and contains shipped work you MUST NOT revert. The following symbols are load-bearing — verify they exist on your branch before any edit, and do not modify them:

| From task | File | Symbols/sections |
|-----------|------|------------------|
| I | `src/stream_manager/governance.py` | `_install_lazy_hydrator`, `GovernanceEngine.hydrated` field |
| I | `tools/perf_probe.py` | entire file (durable artifact) |
| J | `src/stream_manager/cli_pool.py` | `CliPool`, `CliWorker`, PID file `.bridge/cli-pool.pids` |
| J | `src/stream_manager/governance.py` | `GovernanceEngine.cli_pool` field |
| J | `dashboard/server.py` | cli_pool lifecycle (boot init, shutdown) |
| K | `src/stream_manager/desktop_command_consumer.py` | `transport` kwarg, `_run_sse`, `_consume_sse_stream` |
| K | `dashboard/server.py` | `/api/commands/stream` SSE endpoint |
| L | `src/stream_manager/message_bus.py` | `hitl_pending.matched_hash` column + idempotent backfill |
| L | `src/stream_manager/hitl.py` | `dispatch_resolution` reads `matched_hash` w/ legacy split-on-colon fallback |
| M | `src/stream_manager/governance.py` | `EngineRegistry.start_refresh/stop_refresh/refresh_all/refresh_status`, `last_refresh_ts`, `_refresh_timer` |
| M | `dashboard/server.py` | refresh start/stop hooks, `/api/registry/active` payload |
| N | `src/stream_manager/wirecli.py` | entire module — `WireProtocolError`, `WireSchemaVersionError`, `WireTransportError` |
| N | `src/stream_manager/cli_client.py` | `transport` kwarg, `cli_transport()` resolver |

All symbols above must be preserved by this task.

Before editing any of `governance.py`, `dashboard/server.py`, `message_bus.py`, `hitl.py`, `desktop_command_consumer.py`, `cli_client.py`, `wirecli.py`, run:

```
grep -nE 'cli_pool|_install_lazy_hydrator|matched_hash|_run_sse|start_refresh|stop_refresh|WireProtocolError' src/stream_manager/governance.py src/stream_manager/message_bus.py src/stream_manager/hitl.py src/stream_manager/desktop_command_consumer.py dashboard/server.py src/stream_manager/cli_client.py src/stream_manager/wirecli.py
```

…and confirm the symbols exist. If any are missing, STOP and report — do not proceed. Likely silent-revert trap.

## Task brief

Surface Claude Code background jobs (`BG <id>`) and `Agent(...)` subagent spawns into SM's bus so the dashboard can show them.

Pain point: SM today only sees conversation/decision events; Claude Code's internal process management (background bash jobs, spawned agents) is invisible. When the user runs a background soak or spawns a subagent, the SM dashboard shows nothing — the operator can't tell which job is being governed.

Scope:

- **Hook surface in Claude Code**: needs `BackgroundJobStart` / `BackgroundJobEnd` and `AgentSpawn` / `AgentComplete` events. If existing `UserPromptSubmit` / `TaskOutput` hooks don't carry these, file an upstream feature request OR poll Claude Code's task output directory as a shim (`%LOCALAPPDATA%\claude\...\tasks\<id>.output`). Document which path was taken in the PR body.
- **New module** `src/stream_manager/lifecycle_bridge.py`: subscribes to the hook stream and emits typed envelopes into MessageBus with `event_type` in `{bg_job_start, bg_job_end, agent_spawn, agent_done}`.
- **Governance opt-in**: bg jobs and agents do NOT auto-route to L4 alignment. Default ALLOW with a `track_only` decision unless the operator wires a policy. This avoids quota burn from the bridge itself.
- **Dashboard panel**: "Active jobs / agents" pane listing live BG job IDs + agent IDs + start ts + status. Pairs with the v1.2 session selector (Task B) — if Task B has shipped, selecting a session filters the panel; if not, panel shows all.

## DOD

- [ ] Spawning a background bash via Claude Code shows up in the dashboard within 2s; completion event closes the row.
- [ ] Spawning an `Agent(...)` subagent shows up in the dashboard within 2s; completion event closes the row.
- [ ] No governance decision is spent on `track_only` events (verify by checking decision count before/after a bg job).
- [ ] `tests/test_lifecycle_bridge.py` covers the round-trip: simulated hook in → envelope on bus out → dashboard payload contains the row.
- [ ] PR body documents whether hook surface was extended or shim path was taken.
- [ ] No changes to v1.1.0 do-not-touch symbols.
- [ ] `pytest -q` passes end-to-end.

Estimate: ~1–2 sessions (plus 0–1 session of upstream work if Claude Code hook surface needs an extension).

## Final verification before opening PR

```
git --no-pager diff origin/ship/v1.2-scope..HEAD --stat
```

Diff stat MUST show only the files you intentionally added/modified for this task. Expected files:
- `src/stream_manager/lifecycle_bridge.py` (new)
- `tests/test_lifecycle_bridge.py` (new)
- `dashboard/server.py` (minimal — only if a new read-only endpoint is needed; do NOT touch symbols in do-not-touch table)
- `dashboard/static/*` (modified — new pane)
- possibly `src/stream_manager/governance.py` ONLY if a `track_only` decision type needs registering — if so, add it as a new field/branch, do NOT modify `_install_lazy_hydrator`, `cli_pool`, `EngineRegistry.start_refresh/stop_refresh/refresh_all/refresh_status`, or `last_refresh_ts`.

If the diff stat shows ANY change to symbols in the do-not-touch table above, STOP, report which files, do not open PR. Likely silent-revert.

Run `pytest -q` end-to-end. Paste tail in PR body.

Report back when PR is open with: PR URL, diff stat, pytest tail.
