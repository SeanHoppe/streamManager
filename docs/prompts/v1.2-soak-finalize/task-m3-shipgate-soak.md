You are implementing **Task M3 — Tier 3 ship-gate soak** from `docs/v1.2-soak-finalize.md`.

## Master plan
Read `docs/v1.2-soak-finalize.md` first. M3 is the **sole source of truth** for ADR-5 absolute latency numbers. 30-min soak, default model, real CLI subprocess pool, ~60 real `claude -p` calls.

## Predecessor gate
- M1 PASS + merged
- M2 PASS + merged
- Confirm `tests/fixtures/soak_cassette_latest.jsonl` points at the M2-refreshed cassette
- If either upstream gate not green: STOP, report to user

## Branch + base
- Base: `main` (post-M1, post-M2).
- PR title: `chore(v1.2): ship-gate soak baseline for ADR-5 re-bind`.

## ⚠️ CRITICAL

**Mandatory flag** (memory: `feedback_soak_cli_pool_flag.md`):
```
--cli-pool-size 2
```
Default `--cli-pool-size 0` reproduces v1.0 cold-start regression. Without this flag the run is invalid.

M3 is **measurement only**. No production code edits. See do-not-touch table in `docs/v1.2-soak-finalize.md` §"CRITICAL".

## Pre-flight

1. **Subagent stale-mental-model defense** (memory: `feedback_subagent_stale_mental_model.md`):
   ```
   git diff v1.2.0..HEAD -- src/stream_manager/cli_pool.py src/stream_manager/governance.py src/stream_manager/wirecli.py src/stream_manager/desktop_command_consumer.py src/stream_manager/cli_client.py src/stream_manager/message_bus.py src/stream_manager/hitl.py
   ```
   Confirm no protected-symbol drift since v1.2.0 tag. If drift: STOP and report.

2. `claude` CLI on PATH and authenticated:
   ```
   claude --version
   ```

3. Environment:
   - `BRIDGE_API_GOV=1`
   - Quota for ~60 default-model calls
   - No competing soak running (single-writer SQLite gov.db)

4. Disk: ~50 MB headroom for `tmp/soak_*` artifacts.

## Task brief

### Steps

1. Run ship-gate soak:
   ```
   python tools/soak_driver.py --cli-pool-size 2
   ```
   Runtime: ~30 min. Driver writes `reports/soak-<UTC-ts>.md`.

2. Acceptance gates — ALL must pass:
   - **Overall: PASS**
   - 100% events via SSE
   - RSS drift < 50 MB
   - No uncaught exceptions in dashboard server log
   - **ALLOW p95**: within ADR-5 §"v1.1 ship-gate re-baseline" envelope (~6s pool-bound floor)
   - **L2/L3 trigger p95**: within ADR-5 v1.1 envelope (~6s)
   - **L4 alignment p95**: ≤ 13.5s
   - **NEW v1.2 expectation**: lifecycle bridge events visible in dashboard log; no orphan start/end keys remain in `LifecycleBridge._seen` at shutdown
   - Cross-check report against v1.1 baseline `reports/soak-20260503T101758Z.md` for parity / regression / improvement classification

3. **If any gate FAILS:**
   - **Latency miss** (p95 over budget): propose either (a) ADR-5 re-baseline with explicit justification (option B precedent from v1.1 cycle), or (b) revert offending v1.2 task. Do NOT silently widen budget. Document choice in PR body.
   - **Plumbing FAIL** (RSS drift, exceptions, SSE gap, lifecycle orphans): file fix PR against `main`, do NOT merge M3 report. Re-run M3 after fix lands.

4. **If all gates PASS:**
   - Commit only the new `reports/soak-<ts>.md`. Commit msg:
     ```
     chore(v1.2): ship-gate soak baseline for ADR-5 re-bind

     30-min Tier 3 soak, default model, --cli-pool-size 2.
     Source of truth for v1.2 ADR-5 latency budget per ADR-17.
     All acceptance gates green: see report.
     ```
   - PR body summarizes p50/p95/max for ALLOW, L2/L3, L4. Includes delta vs v1.1 baseline.

## Do NOT
- Edit production code.
- Run with default `--cli-pool-size 0` — invalid run.
- Update ADR-5 in this PR (M4 owns it).
- Bundle cassette refresh (M2 already shipped).

## DOD
- `reports/soak-<m3-ts>.md` PASS, all gates green
- Report merged to `main`
- M4 prompt unblocked with M3 report path as input
