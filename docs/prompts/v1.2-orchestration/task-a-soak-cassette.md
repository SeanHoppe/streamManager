You are implementing **Task A — Soak cassette + replay tiers** from the streamManager v1.2 ship cycle.

## Branch + base
- Base your work on `ship/v1.2-scope` (NOT main, NOT ship/v1.1-scope).
- Open PR targeting `ship/v1.2-scope`.
- If `ship/v1.2-scope` does not yet exist, ABORT and tell the user to cut it from `main`.

This task is the FIRST task of v1.2 and has no in-cycle predecessor. Tasks B, D, E in v1.2 depend on this shipping first.

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

Cut quota cost of routine soaks and remove upstream rate-limit variance from latency numbers.

Pain point: 30-min ship-gate soak burns 60 real `claude -p` calls; CI cannot run it; rate-limit jitter corrupts p95.

Implement a three-tier soak model:

- **replay tier** (free, every CI run / dev) — add a `--cli-replay <cassette.jsonl>` flag on `tools/soak_driver.py`. In replay mode, the driver does NOT spawn a real `claude` subprocess; instead it sleeps `recorded_latency_ms` per envelope then emits the canned JSON envelope from the cassette file. This tier tests pool/bus/governance plumbing only — no model calls, no PATH dependency on `claude`.
- **record-cassette tier** (weekly refresh, Haiku) — new `tools/cassette_record.py` runs a real soak with `claude -p --model claude-haiku-4-5-20251001` and writes `tests/fixtures/soak_cassette_<YYYY-MM-DD>.jsonl`. Each line is a JSON envelope with `recorded_latency_ms` plus the original CLI response payload. Cheap baseline refresh; catches model-side envelope drift.
- **ship-gate soak tier** (minor version cut, default model) — current `tools/soak_driver.py --cli-pool-size 2` path. Source of truth for ADR-5 absolute latency numbers. No code change beyond making sure the new flag does not interfere with the existing path.

Documentation:
- Write `docs/adr/ADR-17-soak-tiers.md` documenting the three-tier model. Warn explicitly that cassette p95 is a *relative* regression signal, not an absolute target.
- Update `docs/adr/ADR-5-*.md` with a cross-reference: only ship-gate soak feeds the absolute latency budget.

## DOD

- [ ] `tools/soak_driver.py --cli-replay <path>` runs end-to-end without a `claude` binary on PATH (verify by running with `PATH= ` or a temporarily renamed binary).
- [ ] `tools/cassette_record.py` writes a re-runnable artifact under `tests/fixtures/soak_cassette_*.jsonl`.
- [ ] At least one cassette artifact committed (a small ~5-envelope sample is fine for the first PR — full weekly cassette can land separately).
- [ ] `tests/test_soak_replay.py` exercises the replay path (spin up driver in replay mode against the sample cassette, assert envelopes flow through bus, assert no `claude` subprocess was spawned).
- [ ] `docs/adr/ADR-17-soak-tiers.md` merged with the three-tier description and the cassette-is-relative-only warning.
- [ ] ADR-5 cross-reference added.
- [ ] No changes to any v1.1.0 do-not-touch symbol.
- [ ] `pytest -q` passes end-to-end.

## Final verification before opening PR

```
git --no-pager diff origin/ship/v1.2-scope..HEAD --stat
```

Diff stat MUST show only the files you intentionally added/modified for this task. Expected files:
- `tools/soak_driver.py` (modified — new flag)
- `tools/cassette_record.py` (new)
- `tests/test_soak_replay.py` (new)
- `tests/fixtures/soak_cassette_*.jsonl` (new sample)
- `docs/adr/ADR-17-soak-tiers.md` (new)
- `docs/adr/ADR-5-*.md` (modified — cross-reference)

If the diff stat shows ANY change to symbols in the do-not-touch table above, STOP, report which files, do not open PR. Likely silent-revert.

Run `pytest -q` end-to-end. Paste tail in PR body.

Report back when PR is open with: PR URL, diff stat, pytest tail.
