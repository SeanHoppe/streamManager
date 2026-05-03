You are implementing **Task M4 — ADR-5 v1.2 re-baseline** from `docs/v1.2-soak-finalize.md`.

## Master plan
Read `docs/v1.2-soak-finalize.md` first. M4 updates `docs/adr/ADR-5-latency-budget.md` with v1.2 ship-gate numbers from the M3 report. Cross-references M3 report path. Bumps `REQUIREMENTS.md` spec version pin if needed.

## Predecessor gate
- M3 PASS + merged. Confirm `reports/soak-<m3-ts>.md` exists on `main` with all gates green.
- If M3 not green: STOP, report to user.

## Branch + base
- Base: `main` (post-M3).
- PR title: `docs(adr-5): re-baseline latency budget for v1.2`.

## ⚠️ CRITICAL
M4 is **documentation only**. NO code edits. NO test edits.

ADR-17 §"Cassette is a *relative* signal" mandates: only Tier 3 (ship-gate) numbers feed ADR-5. Do NOT ingest M1/M2 replay numbers into the budget.

## Task brief

### Steps

1. Read current `docs/adr/ADR-5-latency-budget.md`. Locate §"v1.1 ship-gate re-baseline" — mirror its structure for the new v1.2 section.

2. Read M3 report `reports/soak-<m3-ts>.md`. Extract:
   - Overall p50, p95, max, mean
   - Per-trigger split: ALLOW p50/p95, L2/L3 p50/p95, L4 alignment p50/p95
   - Runtime, total events, total emitted
   - RSS drift, FD drift
   - Verdict: PASS

3. Append new section to `docs/adr/ADR-5-latency-budget.md`:
   ```
   ## v1.2 ship-gate baseline

   - **Source**: `reports/soak-<m3-ts>.md`
   - **Date**: <date from M3 report>
   - **Runtime**: <runtime>
   - **Driver**: `tools/soak_driver.py --cli-pool-size 2` (Tier 3)
   - **Events**: <emitted>/<received>

   ### Latency targets (overall)
   - p50: <m3 p50>
   - p95: <m3 p95>
   - max: <m3 max>

   ### Per-trigger split
   - ALLOW: p50=<...>, p95=<...>
   - L2/L3 escalation: p50=<...>, p95=<...>
   - L4 alignment: p50=<...>, p95=<...>

   ### Delta vs v1.1 ship-gate (`reports/soak-20260503T101758Z.md`)
   - <regression / improvement / parity per band>
   - <commentary on Task C/D/E impact if any>

   ### Status
   ACCEPTED as v1.2 budget. v1.3 latency work measures against this section.
   ```

4. Update ADR-5 status header (top of doc) to append:
   ```
   - 2026-MM-DD: v1.2 ship-gate re-baseline accepted (see §"v1.2 ship-gate baseline")
   ```

5. `REQUIREMENTS.md`: check whether v1.2 added or modified any FR-OG-* entries (Task B added session picker FR-OG-X; Task C added lifecycle pane). If yes:
   - Bump spec version pin at top of REQUIREMENTS.md
   - Confirm new FR-OG entries are present and numbered
   - If absent (drift): file separate fix PR, do not bundle here

6. Commit (single PR):
   - `docs/adr/ADR-5-latency-budget.md`
   - `REQUIREMENTS.md` (only if version pin bumped)
   Commit msg:
   ```
   docs(adr-5): re-baseline latency budget for v1.2

   Captures v1.2 ship-gate soak numbers from reports/soak-<m3-ts>.md
   per ADR-17 (only Tier 3 feeds ADR-5). Adds delta vs v1.1 baseline.
   <REQUIREMENTS.md spec version pin bumped to vX.Y if applicable>
   ```

## Do NOT
- Modify code or tests.
- Reference M1/M2 replay numbers in ADR-5 (relative signal only).
- Re-run M3 in this PR.

## DOD
- ADR-5 §"v1.2 ship-gate baseline" merged to `main`
- REQUIREMENTS.md version pin reflects v1.2 if applicable
- Single-PR, doc-only diff
- M5 prompt unblocked
