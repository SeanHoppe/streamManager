You are implementing **Task D — Long-poll consumer path removal** from the streamManager v1.2 ship cycle.

This is a removal task. The long-poll path was deprecated in v1.1 Task K when the SSE consumer (`_run_sse`, `_consume_sse_stream`) shipped as the new default. v1.2 removes the legacy long-poll code path.

## Branch + base
- Base your work on `ship/v1.2-scope` (NOT main, NOT ship/v1.1-scope).
- Open PR targeting `ship/v1.2-scope`.
- If `ship/v1.2-scope` does not yet exist, ABORT and tell the user to cut it from `main`.

## Predecessor precondition

Task A (Soak cassette + replay tiers) must have shipped to `ship/v1.2-scope` before this task starts, so soak coverage doesn't depend on a transport that's mid-removal. Verify:

```
git log origin/ship/v1.2-scope --oneline | grep -i 'task.*a\|cassette\|soak'
```

…shows a recent merge. If not, STOP and tell the user Task A needs to land first.

## ⚠️ CRITICAL: Do-not-touch guard (REDUCED for this task)

v1.1.0 was tagged on 2026-05-03 and contains shipped work you MUST NOT revert — EXCEPT for the long-poll consumer path which this task removes.

For THIS task, the long-poll fallback inside `desktop_command_consumer.py` SHOULD be removed; everything else stays. Specifically:

- ✅ KEEP: `transport` kwarg on `DesktopCommandConsumer` (Task K). It just loses the `"longpoll"` value as a valid choice; `"sse"` becomes the only/default value.
- ✅ KEEP: `_run_sse`, `_consume_sse_stream` (Task K — SSE path is the survivor).
- ✅ KEEP: `/api/commands/stream` SSE endpoint in `dashboard/server.py` (Task K).
- ❌ REMOVE: any `_run_longpoll`, `_consume_longpoll_stream`, or equivalent long-poll method on the consumer.
- ❌ REMOVE: any `/api/commands/poll` (or equivalently named) long-poll endpoint on `dashboard/server.py` if one exists.
- ❌ REMOVE: any config flag, env var, or CLI switch that selected long-poll.

Reduced do-not-touch table for this task:

| From task | File | Symbols/sections |
|-----------|------|------------------|
| I | `src/stream_manager/governance.py` | `_install_lazy_hydrator`, `GovernanceEngine.hydrated` field |
| I | `tools/perf_probe.py` | entire file (durable artifact) |
| J | `src/stream_manager/cli_pool.py` | `CliPool`, `CliWorker`, PID file `.bridge/cli-pool.pids` |
| J | `src/stream_manager/governance.py` | `GovernanceEngine.cli_pool` field |
| J | `dashboard/server.py` | cli_pool lifecycle (boot init, shutdown) |
| K | `src/stream_manager/desktop_command_consumer.py` | `transport` kwarg (kept; long-poll value removed), `_run_sse`, `_consume_sse_stream` |
| K | `dashboard/server.py` | `/api/commands/stream` SSE endpoint |
| L | `src/stream_manager/message_bus.py` | `hitl_pending.matched_hash` column + idempotent backfill |
| L | `src/stream_manager/hitl.py` | `dispatch_resolution` reads `matched_hash` w/ legacy split-on-colon fallback |
| M | `src/stream_manager/governance.py` | `EngineRegistry.start_refresh/stop_refresh/refresh_all/refresh_status`, `last_refresh_ts`, `_refresh_timer` |
| M | `dashboard/server.py` | refresh start/stop hooks, `/api/registry/active` payload |
| N | `src/stream_manager/wirecli.py` | entire module — `WireProtocolError`, `WireSchemaVersionError`, `WireTransportError` |
| N | `src/stream_manager/cli_client.py` | `transport` kwarg, `cli_transport()` resolver |

Before editing any of `governance.py`, `dashboard/server.py`, `message_bus.py`, `hitl.py`, `desktop_command_consumer.py`, `cli_client.py`, `wirecli.py`, run:

```
grep -nE 'cli_pool|_install_lazy_hydrator|matched_hash|_run_sse|start_refresh|stop_refresh|WireProtocolError' src/stream_manager/governance.py src/stream_manager/message_bus.py src/stream_manager/hitl.py src/stream_manager/desktop_command_consumer.py dashboard/server.py src/stream_manager/cli_client.py src/stream_manager/wirecli.py
```

…and confirm the symbols exist. If any are missing OTHER than long-poll-specific symbols, STOP and report — do not proceed. Likely silent-revert trap.

## Task brief

Remove the deprecated long-poll consumer path from `desktop_command_consumer.py` and its server-side endpoint, leaving SSE as the only transport.

- Identify all long-poll code: search for `longpoll`, `long_poll`, `poll_commands`, `_run_longpoll`, `_consume_longpoll_stream` across the repo.
- Remove the consumer-side long-poll method(s) entirely. Keep the `transport` kwarg shape but reduce its accepted values to `"sse"` only (and reject `"longpoll"` with a clear error message pointing to the v1.1 deprecation note in CHANGELOG).
- Remove the server-side long-poll endpoint if it exists.
- Remove any documentation or env-var hints that referenced long-poll as a fallback.
- Update CHANGELOG / release notes for v1.2 with a "Removed: long-poll command transport (deprecated in v1.1)" line.

## DOD

- [ ] No reference to `longpoll` / `long_poll` remains in `src/`, `dashboard/`, or `tools/` (verify with grep).
- [ ] `transport="sse"` continues to work; `transport="longpoll"` raises a clear deprecation/removal error.
- [ ] All tests touching the long-poll path are either removed (if they were testing the removed code only) or updated to assert the removal error.
- [ ] CHANGELOG entry added.
- [ ] No changes to any do-not-touch symbol in the reduced table above.
- [ ] `pytest -q` passes end-to-end.

## Final verification before opening PR

```
git --no-pager diff origin/ship/v1.2-scope..HEAD --stat
```

Diff stat MUST show only the files you intentionally added/modified/deleted for this task. Expected files:
- `src/stream_manager/desktop_command_consumer.py` (modified — long-poll removed)
- `dashboard/server.py` (modified — long-poll endpoint removed if present)
- `tests/*` (modified — long-poll tests removed/updated)
- `CHANGELOG.md` or equivalent (modified)
- documentation (modified)

If the diff stat shows ANY change to symbols in the reduced do-not-touch table above (other than the long-poll-specific removal scope), STOP, report which files, do not open PR. Likely silent-revert.

Run `pytest -q` end-to-end. Paste tail in PR body.

Report back when PR is open with: PR URL, diff stat, pytest tail.
