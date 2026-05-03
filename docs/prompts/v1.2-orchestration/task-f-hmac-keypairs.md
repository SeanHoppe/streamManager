You are implementing **Task F — Per-instance HMAC keypairs default** from the streamManager v1.2 ship cycle.

## ⚠️ P3 conditional — only run this task if its trigger fires

This task is P3 conditional, mirroring how v1.1 Tasks O and P were gated.

**ONLY run this task if Task O ran during v1.1** (i.e. v1.1 actually shipped a per-instance HMAC bootstrap path that needs to become default in v1.2). Verify before starting:

```
git log v1.1.0 --oneline | grep -iE 'task.*o|hmac|keypair'
grep -rn 'per_instance_hmac\|hmac_keypair\|HMAC_KEYPAIR' src/ tools/ docs/adr/
```

If neither query returns hits, Task O did NOT run in v1.1 → STOP, do not implement this task. Tell the user the trigger has not fired and recommend deferring to a later cycle.

If Task O did run, proceed.

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

Make per-instance HMAC keypairs the default for desktop_command signing, replacing the shared/static key path that v1.1 Task O introduced as opt-in.

Scope:
- Flip the bootstrap default: when SM starts and no keypair exists for this instance, generate one (using the helper Task O shipped) and persist under `.bridge/hmac-keypair.{json,pem}` (or whatever filename Task O chose). Do NOT regenerate on every boot — generate-if-missing only.
- Update verifiers in `desktop_command_consumer.py` (and any sibling) to look up the per-instance public key by `instance_id` from the envelope. The shared/static key remains accepted for one minor cycle as a fallback (to give existing deployments a window) — log a deprecation warning whenever the static key verifies a message.
- Update CHANGELOG with: "Default-on per-instance HMAC keypairs. Static-key fallback retained for one minor; will be removed in v1.3."
- Update ADR (whichever ADR Task O wrote, e.g. `ADR-15-desktop-command-hmac.md`) to reflect the new default.

## DOD

- [ ] Fresh clone + first boot generates a keypair under `.bridge/`.
- [ ] Repeat boot reuses the existing keypair (no regeneration).
- [ ] Envelopes signed by per-instance key verify successfully end-to-end.
- [ ] Envelopes signed by the legacy static key still verify but emit a deprecation warning.
- [ ] `tests/test_hmac_keypair_default.py` (new) covers generate-if-missing, reuse, and the deprecation-path warning.
- [ ] CHANGELOG and ADR updated.
- [ ] No changes to v1.1.0 do-not-touch symbols.
- [ ] `pytest -q` passes end-to-end.

## Final verification before opening PR

```
git --no-pager diff origin/ship/v1.2-scope..HEAD --stat
```

Diff stat MUST show only the files you intentionally added/modified for this task. Expected files:
- whichever module Task O introduced for HMAC bootstrap (modified — default flipped)
- `src/stream_manager/desktop_command_consumer.py` (modified — verifier lookup by instance_id; do NOT touch `transport`, `_run_sse`, or `_consume_sse_stream`)
- `tests/test_hmac_keypair_default.py` (new)
- `CHANGELOG.md` (modified)
- `docs/adr/ADR-*-desktop-command-hmac.md` (modified)

If the diff stat shows ANY change to symbols in the do-not-touch table above, STOP, report which files, do not open PR. Likely silent-revert.

Run `pytest -q` end-to-end. Paste tail in PR body.

Report back when PR is open with: PR URL, diff stat, pytest tail.
