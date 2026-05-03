You are implementing **Task E — json CLI transport removal** from the streamManager v1.2 ship cycle.

This is a removal task. The `json` CLI transport was deprecated in v1.1 Task N when WireCLI shipped as `transport="wirecli"`. v1.2 makes WireCLI the only transport and removes the json path.

## Branch + base
- Base your work on `ship/v1.2-scope` (NOT main, NOT ship/v1.1-scope).
- Open PR targeting `ship/v1.2-scope`.
- If `ship/v1.2-scope` does not yet exist, ABORT and tell the user to cut it from `main`.

## Predecessor precondition

Task A (Soak cassette + replay tiers) must have shipped to `ship/v1.2-scope` before this task starts — soak fixtures must already be on a transport-agnostic recording shape so the cassette doesn't lock in `json` envelopes. Verify:

```
git log origin/ship/v1.2-scope --oneline | grep -i 'task.*a\|cassette\|soak'
```

…shows a recent merge. If not, STOP and tell the user Task A needs to land first.

Additionally, before removal, confirm that v1.1 left `transport="wirecli"` in a runnable state and that all callers in the v1.2 tree default to or explicitly select WireCLI. Search:

```
grep -rnE 'transport\s*=\s*"json"|cli_transport\(.*json' src/ tools/ dashboard/ tests/
```

…if any production caller still uses `"json"` explicitly, fix those FIRST in this task before removing the transport.

## ⚠️ CRITICAL: Do-not-touch guard (REDUCED for this task)

v1.1.0 was tagged on 2026-05-03 and contains shipped work you MUST NOT revert — EXCEPT for the json transport implementation which this task removes.

For THIS task, the json transport branch inside `cli_client.py` and any json-only helper in `cli_transport()` SHOULD be removed; everything else stays. Specifically:

- ✅ KEEP: `transport` kwarg on `cli_client` (Task N). It just loses `"json"` as a valid value; `"wirecli"` becomes the only/default value.
- ✅ KEEP: `cli_transport()` resolver (Task N). It now resolves only to WireCLI.
- ✅ KEEP: the entire `wirecli.py` module — `WireProtocolError`, `WireSchemaVersionError`, `WireTransportError` (Task N).
- ❌ REMOVE: any json-specific transport class/function (e.g. `JsonCliTransport`, `_run_json`, etc.) inside `cli_client.py` or sibling modules.
- ❌ REMOVE: any `transport="json"` config flag, env var, or CLI switch.

Reduced do-not-touch table for this task:

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
| N | `src/stream_manager/cli_client.py` | `transport` kwarg (kept; `"json"` value removed), `cli_transport()` resolver (kept; resolves only to WireCLI) |

Before editing any of `governance.py`, `dashboard/server.py`, `message_bus.py`, `hitl.py`, `desktop_command_consumer.py`, `cli_client.py`, `wirecli.py`, run:

```
grep -nE 'cli_pool|_install_lazy_hydrator|matched_hash|_run_sse|start_refresh|stop_refresh|WireProtocolError' src/stream_manager/governance.py src/stream_manager/message_bus.py src/stream_manager/hitl.py src/stream_manager/desktop_command_consumer.py dashboard/server.py src/stream_manager/cli_client.py src/stream_manager/wirecli.py
```

…and confirm the symbols exist. If any are missing OTHER than json-transport-specific symbols, STOP and report — do not proceed. Likely silent-revert trap.

## Task brief

Remove the deprecated json CLI transport from `cli_client.py`, leaving WireCLI as the only transport.

- Identify all json-transport code: search for `transport="json"`, `JsonCliTransport`, `_run_json` (or whatever the v1.1 internal name is) across the repo.
- Remove the json transport branch from `cli_client.py`. Keep the `transport` kwarg shape but reduce its accepted values to `"wirecli"` only (and reject `"json"` with a clear error message pointing to the v1.1 deprecation note in CHANGELOG and ADR-N coverage).
- Update `cli_transport()` to resolve only to WireCLI; if it had a default-of-`"json"`, change to default `"wirecli"`.
- Update CHANGELOG / release notes for v1.2 with a "Removed: json CLI transport (deprecated in v1.1)" line.

## DOD

- [ ] No reference to `transport="json"` or json-transport implementation remains in `src/`, `dashboard/`, or `tools/` (verify with grep).
- [ ] `transport="wirecli"` continues to work; `transport="json"` raises a clear deprecation/removal error.
- [ ] WireCLI is the unconditional default (no env var or config required to opt in).
- [ ] All tests touching the json transport path are either removed or updated to assert the removal error.
- [ ] CHANGELOG entry added.
- [ ] No changes to any do-not-touch symbol in the reduced table above. The wirecli.py module is untouched.
- [ ] `pytest -q` passes end-to-end.

## Final verification before opening PR

```
git --no-pager diff origin/ship/v1.2-scope..HEAD --stat
```

Diff stat MUST show only the files you intentionally added/modified/deleted for this task. Expected files:
- `src/stream_manager/cli_client.py` (modified — json branch removed; default flips to wirecli)
- `tests/*` (modified — json tests removed/updated)
- `CHANGELOG.md` or equivalent (modified)
- documentation (modified)

If the diff stat shows ANY change to symbols in the reduced do-not-touch table above (other than the json-transport-specific removal scope), STOP, report which files, do not open PR. Likely silent-revert.

Run `pytest -q` end-to-end. Paste tail in PR body.

Report back when PR is open with: PR URL, diff stat, pytest tail.
