You are implementing **Phase P1 — Soak driver + recorder hardening** from the streamManager v1.3 cycle.

## Branch + base

- Base: `main` (v1.2.0 tagged at `69965aa`; v1.2 close-out cycle finalized at `7b7dc64`).
- PR target: `main`.
- Branch: `fix/v1.3-driver-recorder-hardening` (or operator's choice).
- If `main` is unexpectedly behind v1.2 close-out, ABORT and tell the user.

## ⚠️ CRITICAL: Do-not-touch guard

The following symbols are load-bearing. Verify they exist on your branch before any edit, and do not modify them:

| From task | File | Symbols/sections |
|-----------|------|------------------|
| J (v1.1) | `src/stream_manager/cli_pool.py` | `CliPool`, `CliWorker`, `.bridge/cli-pool.pids` |
| I (v1.1) | `src/stream_manager/governance.py` | `_install_lazy_hydrator`, `GovernanceEngine.hydrated` |
| K (v1.1) | `src/stream_manager/desktop_command_consumer.py` | `_run_sse`, `_consume_sse_stream`, `transport` kwarg |
| K (v1.1) | `dashboard/server.py` | `/api/commands/stream` SSE endpoint |
| L (v1.1) | `src/stream_manager/message_bus.py` | `hitl_pending.matched_hash` column |
| M (v1.1) | `src/stream_manager/governance.py` | `EngineRegistry.start_refresh/stop_refresh/refresh_all/refresh_status` |
| N (v1.1) | `src/stream_manager/wirecli.py` | entire module |
| A (v1.2) | `tools/soak_driver.py` | `--cli-replay` flag (extend, never remove) |
| A (v1.2) | `src/stream_manager/cli_replay_pool.py` | `ReplayPool` / `ReplayWorker` (read-only for P1) |
| C (v1.2) | `src/stream_manager/lifecycle_bridge.py` | `LifecycleBridge` outer surface (read `_seen` only — no method/field renames) |
| D (v1.2) | `src/stream_manager/desktop_command_consumer.py` | `_VALID_TRANSPORTS = frozenset({"sse"})` |
| E (v1.2) | `src/stream_manager/cli_client.py` | `Transport = Literal["wirecli"]`, `_JSON_REMOVED_MSG` |

Pre-flight grep:

```
grep -nE 'CliPool|_install_lazy_hydrator|_run_sse|matched_hash|--cli-replay|LifecycleBridge|_VALID_TRANSPORTS|Literal\["wirecli"\]' src/stream_manager/cli_pool.py src/stream_manager/governance.py src/stream_manager/desktop_command_consumer.py src/stream_manager/lifecycle_bridge.py src/stream_manager/cli_replay_pool.py src/stream_manager/cli_client.py tools/soak_driver.py tools/cassette_record.py
```

If any symbol missing, STOP and report — likely silent-revert trap.

## Task brief

Three carry-overs from v1.2 close-out (M2/PR #49 and M3/PR #50) — see `docs/v1.3-backlog.md` §"From v1.2 close-out cycle":

1. **Cassette recorder filename collision.** `tools/cassette_record.py` derives the output filename from `_dt.date.today().isoformat()` only — same-day re-record overwrites the prior cassette. Add a UTC HHMMSS timestamp suffix, OR a `--no-clobber` guard that aborts with non-zero exit when the target path exists. Pick the timestamp suffix unless the operator explicitly opts in via `--allow-overwrite`.

2. **Driver does not split per-band p95.** `tools/soak_driver.py` aggregates ALLOW (n=50), L2/L3 (n=5), L4 (n=5) into a single overall p95. Emit per-band p50/p95 in a new "per-band" table block matching the ADR-5 §"v1.2 ship-gate baseline" format. Keep the overall line for back-compat.

3. **Driver does not dump `LifecycleBridge._seen` final state.** Add an end-of-run `### Lifecycle bridge final state` heading to the soak report. Positively assert "no orphan start keys" / "no orphan end keys" with counts. Read from the existing `LifecycleBridge` instance — do not modify the bridge surface.

New tests:
- `tests/test_cassette_record_filename.py` — assert no-clobber and timestamp-suffix paths.
- `tests/test_soak_driver_per_band_split.py` — synthesize cassette covering all three bands; assert per-band rows.
- `tests/test_soak_driver_lifecycle_dump.py` — synthesize bridge state with one orphan; assert report flags it.

## DOD

- [ ] `tools/cassette_record.py` no-clobber + timestamp-suffix logic shipped
- [ ] `tools/soak_driver.py` per-band p50/p95 table in report
- [ ] `tools/soak_driver.py` `LifecycleBridge._seen` final-state dump in report
- [ ] Three new tests pass; existing soak-replay tests stay green
- [ ] `pytest -q` passes end-to-end
- [ ] `git --no-pager diff main..HEAD --stat` shows only intentionally added/modified files
- [ ] No protected-symbol drift

## Final verification before opening PR

```
git --no-pager diff origin/main..HEAD --stat
```

Expected files:
- `tools/cassette_record.py` (modified)
- `tools/soak_driver.py` (modified)
- `tests/test_cassette_record_filename.py` (new)
- `tests/test_soak_driver_per_band_split.py` (new)
- `tests/test_soak_driver_lifecycle_dump.py` (new)

If diff shows any change to symbols in the do-not-touch table, STOP and report — likely silent-revert.

Run `pytest -q` end-to-end. Paste tail in PR body.

Report back: PR URL, diff stat, pytest tail.
