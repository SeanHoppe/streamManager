You are implementing **Task B — Session selector (CLI + UI)** from the streamManager v1.2 ship cycle.

## Branch + base
- Base your work on `ship/v1.2-scope` (NOT main, NOT ship/v1.1-scope).
- Open PR targeting `ship/v1.2-scope`.
- If `ship/v1.2-scope` does not yet exist, ABORT and tell the user to cut it from `main`.

## Predecessor precondition

Task A (Soak cassette + replay tiers) must have shipped to `ship/v1.2-scope` before this task starts. Verify:

```
git log origin/ship/v1.2-scope --oneline | grep -i 'task.*a\|cassette\|soak'
```

…shows a recent merge. If not, STOP and tell the user Task A needs to land first.

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

All symbols above must be preserved by this task. This task READS from `EngineRegistry.refresh_status` and `/api/registry/active` (Task M output) — do not modify those, only consume them.

Before editing any of `governance.py`, `dashboard/server.py`, `message_bus.py`, `hitl.py`, `desktop_command_consumer.py`, `cli_client.py`, `wirecli.py`, run:

```
grep -nE 'cli_pool|_install_lazy_hydrator|matched_hash|_run_sse|start_refresh|stop_refresh|WireProtocolError' src/stream_manager/governance.py src/stream_manager/message_bus.py src/stream_manager/hitl.py src/stream_manager/desktop_command_consumer.py dashboard/server.py src/stream_manager/cli_client.py src/stream_manager/wirecli.py
```

…and confirm the symbols exist. If any are missing, STOP and report — do not proceed. Likely silent-revert trap.

## Task brief

End-user discoverability of which SM session/job is being monitored. Pain point: dashboard surfaces governance state but doesn't expose a session picker, and there is no `sm` CLI for listing/tailing sessions.

Scope:

- **CLI** (new module `tools/sm_cli.py` wrapping `MessageBus` queries):
  - `sm sessions list` — print rows from `gov.db` `sessions` table joined with last message ts and active flag from `EngineRegistry.refresh_status`. Columns: `session_id`, `started_at`, `last_msg_ts`, `active`.
  - `sm sessions tail <id>` — stream that session's bus envelopes to stdout (similar shape to existing dashboard `/events` SSE, but stdout JSONL).
  - Wire up via console_scripts entry point in `pyproject.toml` so `sm sessions list` works after `pip install -e .`.
- **Dashboard**: session picker dropdown in header, sourced from `/api/registry/active` (already shipped in Task M). Selecting a session filters all panes (decisions, HITL queue, latency, command stream) by `session_id`. The `/events` SSE already carries `session_id` per envelope, so the filter is client-side — do NOT change the server payload.
- **Default selection**: most recently active session at page load. Include a "show all" pseudo-id (e.g. `__all__`) that disables the filter and matches the pre-task behavior.

## DOD

- [ ] `sm sessions list` exits 0 with at least the active session listed (verify in a manual run after starting the dashboard).
- [ ] `sm sessions tail <id>` streams envelopes for that session and exits cleanly on Ctrl-C.
- [ ] Dashboard header has a session picker dropdown that switches all four panes (decisions, HITL queue, latency, command stream).
- [ ] "Show all" option restores pre-task behavior.
- [ ] Existing tests stay green.
- [ ] New `tests/test_sm_cli.py` covers `list` and `tail` against a seeded message bus fixture.
- [ ] No changes to v1.1.0 do-not-touch symbols. `/api/registry/active` payload shape preserved.
- [ ] `pytest -q` passes end-to-end.

## Final verification before opening PR

```
git --no-pager diff origin/ship/v1.2-scope..HEAD --stat
```

Diff stat MUST show only the files you intentionally added/modified for this task. Expected files:
- `tools/sm_cli.py` (new)
- `tests/test_sm_cli.py` (new)
- `pyproject.toml` (modified — console_scripts entry)
- `dashboard/server.py` (minimal — only if a static asset route needs adding; do NOT touch the symbols in the do-not-touch table)
- `dashboard/static/*.html|js|css` (modified — header picker + client-side filter)

If the diff stat shows ANY change to symbols in the do-not-touch table above, STOP, report which files, do not open PR. Likely silent-revert.

Run `pytest -q` end-to-end. Paste tail in PR body.

Report back when PR is open with: PR URL, diff stat, pytest tail.
