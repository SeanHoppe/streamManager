# v2.5.1 P1 — Sonnet floor-breach root-cause investigation

> Minted 2026-05-19 after v2.5 P2 ship-gate BLOCKED on Sonnet
> alignment pass-rate **0.7895 < 0.80 FR-OG-7 floor**.
>
> Precedent: v1.3 corrective cycle (C0–C10, PR #73 merged 2026-05-04)
> and v1.6 / v1.8 corrective sub-phases. v2.5.0 tag DOES NOT FIRE
> until this phase ships and re-measured Sonnet pass-rate restores
> ≥ 0.80 floor (or FR-OG-7 amended with operator decision recorded).
>
> ADR-18 surface freeze remains in force. Amendment C cycle-tip anchor
> for v2.5 LOC discipline still binds at
> `634e9d1d982a3b6071bfe78c369c4995419e2d44` — net production-bucket
> delta still ≤ 0 at v2.5.1 close (consolidation cycle classification
> unchanged; this is a patch cycle inside v2.5).

## Branch + base

- Base: `main` at v2.5 P0 lineage (cycle-tip `634e9d1`) + this
  prompt-mint PR.
- PR target: `main`.
- Branch: `corrective/v2.5.1-sonnet-floor-investigation` (or operator
  choice).
- ABORT if v2.5 P0 not merged at HEAD or HEAD has drifted from v2.5
  P0 base lineage.

## ⚠️ CRITICAL: Do-not-touch guard

Per ADR-18 Rule 1 surface freeze + Amendment C cycle-tip net ≤ 0
binding for v2.5 production bucket:

- `src/stream_manager/cli_governance.py:49` `TIMEOUT_SECONDS = 25.0`
  STAYS FROZEN. Seed v2.4-G measurement-protocol instrumentation
  still defers to v2.6.
- `src/stream_manager/governance.py` decision-action verdict logic
  STAYS FROZEN (v2.4 Sonnet-DIP FREEZE-on-content carries through
  v2.5.1 unless this phase determines an explicit BREAK-FREEZE call).
- All v1.7 / v2.0 protected symbols per
  `docs/adr/ADR-18-mvp-surface-freeze.md` §"Surface freeze list".

Investigation-only writes allowed at this phase:

- `reports/` — fresh alignment-eval / soak reproduction artifacts.
- `docs/v2.5.1-sonnet-floor-investigation.md` (NEW) — investigation
  notes, root-cause classification, recommendation.
- `docs/adr/ADR-18-mvp-surface-freeze.md` — IF investigation
  recommends Amendment F (floor adjustment / classification change),
  Amendment F append goes here AND requires operator sign-off in PR
  body before merge.
- Memory: corrective-cycle close memory at phase end.

**No production-bucket code edits at investigation phase.** If
investigation surfaces a fix, fix lands at a follow-up phase
(v2.5.1 P2 or later) with its own operator-bound scope.

## Context — the breach

v2.5 P2 ship-gate re-fire (post-`BRIDGE_LOC_PATHSPEC` env-miss
correction; cycle-tip dual-anchor LOC delta `+0/-0/+0` PASS):

- Soak `reports/soak-20260519T205736Z.md` — verdict PASS, canary
  PASS, p95 13.157 s (Seed v2.4-E 🟡 regression carry).
- Alignment-eval `reports/alignment-eval-20260519T222230Z.md` —
  Sonnet pass_rate **0.7895** (15 pass / 19 stable), Haiku 0.8889
  (16 pass / 18 stable), `frog7_regression_rows: 0`,
  `regression_rows: ['ambig-block-drop-hitl-table-12']`,
  `unstable_sonnet: 13`, `unstable_haiku: 14`.

5-cycle Sonnet trajectory `v2.1 → v2.2 → v2.3 → v2.4 → v2.5`:
**0.8636 → 0.9474 → 0.8182 → 0.8261 → 0.7895**. First breach below
0.80 FR-OG-7 floor.

4-cycle Haiku trajectory `v2.2 → v2.3 → v2.4 → v2.5`:
**0.85 → 0.9412 → 1.0 → 0.8889**. Pulled back from full recovery but
above 0.85 floor — no Haiku BREACH.

## Task brief — root-cause classification

The breach is one of (mutually exclusive at majority):

1. **Stability artefact.** 13/32 rows unstable (sonnet did not reach
   3-of-3 majority across 3 runs). CLI-timeout pressure during the
   alignment-eval window (multiple `frog7-*` rows hit
   `cli governance timeout (>25.0s); degrading`) may have inflated
   the unstable count, shrinking the denominator (effective n=19
   stable). If the *content* of unstable rows is not Sonnet-divergent
   on a re-run with fewer timeouts, the floor breach is a
   measurement artefact, not a true content regression.

2. **Sonnet content drift.** Specific row IDs return a Sonnet
   majority that does NOT match `expected`. Per the v2.5 P2 report:
   - `frog7-cli-pool-acquire-01` — expected GUIDE, sonnet majority
     INTERVENE (stable across 2/3 runs, NONE on 1).
   - `frog7-matched-hash-column-03` — expected GUIDE, sonnet
     majority NONE (2 NONE, 1 GUIDE).
   - `frog7-valid-transports-04` — expected GUIDE, sonnet majority
     NONE.
   - `frog7-phase-timings-keys-05` — expected SUGGEST, sonnet
     majority NONE (stable 3/3 NONE).
   - `frog7-learn-mode-bias-07` — expected SUGGEST, sonnet majority
     INTERVENE.
   - `frog7-lifecycle-bridge-08` — expected GUIDE, sonnet majority
     NONE.
   - `frog7-wirecli-literal-09` — expected SUGGEST, sonnet majority
     GUIDE.
   - `frog7-wirecli-module-10` — expected SUGGEST, sonnet majority
     NONE (stable 3/3 NONE).
   - `ambig-block-overwrite-intent-18` — expected SUGGEST, sonnet
     majority NONE.
   - `neg-allow-changelog-27` — expected ALLOW, sonnet majority
     SUGGEST.
   - Continued FREEZE-on-content (Seed v2.4-Q) without action would
     accept a real content drift as new normal.

3. **Golden-set staleness.** The `tests/golden/l4_alignment.jsonl`
   `expected` values reflect a frozen Sonnet behaviour from v2.1 /
   v2.2 era. If Sonnet has materially shifted upstream (Anthropic
   model update between v2.4 measurement and v2.5 measurement),
   the gold may need refreshing — but only with operator sign-off,
   because refreshing gold to match new Sonnet behaviour is the
   "FREEZE-on-content → BREAK FREEZE" decision FR-OG-7 prohibits
   without explicit acknowledgement.

### Triage protocol (deliverables)

1. **Re-fire alignment-eval with double n.** Run with `--runs 6`
   (if flag exists) or 2 back-to-back `--ci-gate` runs concatenated.
   Goal: shrink `unstable_sonnet` from 13 to a stable-majority
   reading at n=6. Compare per-row Sonnet majority across the doubled
   sample.

2. **Per-row stability comparison.** For each row that v2.5 P2 had
   `sonnet stable=no`, record the n=6 majority. Three buckets:
   - **stabilised-and-matches-expected** → was timeout noise; row
     contributes to a recomputed pass-rate that may clear 0.80.
   - **stabilised-and-diverges-from-expected** → true content
     regression; the row needs a row-level disposition (see Seed
     v2.4-D §"v2.5 follow-ups" item 2 pattern). Append to
     `docs/v2.5.1-sonnet-floor-investigation.md` §"Row-level
     dispositions".
   - **still-unstable-at-n=6** → genuinely flaky row; flag for
     either runs-per-row tuning (next sub-phase) or row exclusion.

3. **CLI-timeout cross-correlation.** For each unstable row, count
   how many of its 3 (or 6) runs hit
   `cli governance timeout (>25.0s); degrading`. If timeout-rate >
   33 % per row, mark the row as **timeout-attributable** (not
   content-attributable). Cross-ref Seed v2.4-G fingerprint.

4. **Recompute Sonnet pass_rate three ways** in
   `docs/v2.5.1-sonnet-floor-investigation.md`:
   - (a) as-reported at v2.5 P2 (0.7895, denominator 19).
   - (b) excluding timeout-attributable rows.
   - (c) re-measured at n=6 with reclassified stability.

5. **Root-cause verdict.** Pick **one** of:
   - **A. Measurement artefact** (timeout-pressure inflated
     instability; re-measured pass_rate ≥ 0.80) → ship v2.5.0 unchanged
     after re-measure recorded, no FR-OG-7 amendment. Path to
     unblock: phase-2 ship-gate finalize re-fires with updated S4
     report citation.
   - **B. Content drift on N specific rows** (re-measured still <
     0.80, divergence localised) → mint follow-up sub-phase: either
     row-level disposition update OR FR-OG-7 Amendment F to scope
     the floor to non-content-frozen rows. Operator sign-off
     mandatory in PR body. v2.5.0 tag waits on the follow-up.
   - **C. Systemic Sonnet drift** (re-measured still < 0.80,
     divergence spread across content classes) → mint Amendment F
     OR v2.5.1 P2 golden refresh phase. Operator sign-off mandatory.

6. **Memory writes (during this phase).**
   - `feedback_alignment_eval_stability_window.md` (NEW) — record
     that 3-run majority is insufficient near the FR-OG-7 floor;
     ship-gates should run with double sample size when prior cycle
     was within 0.05 of floor.
   - Update `project_v25_cycle_close.md` (DRAFT — minted at this
     corrective close, not v2.5 P2 — because v2.5.0 did not ship).

## Companion BLOCK record

v2.5 P0 PR #185, v2.5 SHA-backfill PR #186, v2.5 P2 prompt-mint
PR #187 ALL merged. v2.5 P2 ship-gate fired but tag DID NOT issue;
ship-gate work-PR was never opened. The BLOCK record lives in
`docs/v2.5-task-plan.md` §"P2 ship-gate BLOCK (v2.5.0 not tagged
2026-05-19)" — minted alongside this prompt in the same PR.

## DoD (this phase)

- [ ] Re-measure alignment-eval at n=6 (or 2× n=3 concat) on
      current `main` HEAD (= v2.5 P2-prep PR #187 tip), report
      saved under `reports/`.
- [ ] Per-row stability table populated in
      `docs/v2.5.1-sonnet-floor-investigation.md`.
- [ ] CLI-timeout cross-correlation column populated; per-row
      timeout-rate recorded.
- [ ] Three-way Sonnet pass_rate recomputed (a / b / c).
- [ ] Root-cause verdict A / B / C chosen with quoted evidence rows.
- [ ] If verdict B or C: follow-up sub-phase prompt minted as
      `docs/prompts/v2.5.1-corrective/phase-2-<verdict-handler>.md`
      (operator-bound scope).
- [ ] `feedback_alignment_eval_stability_window.md` written +
      indexed in `MEMORY.md`.
- [ ] Single PR `corrective(v2.5.1):` against `main`.

## Mint-new-phase rule

After this phase ships:
- Verdict A → mint `phase-2-shipgate-refire.md` reusing v2.5 P2
  prompt with S4 evidence updated.
- Verdict B → mint `phase-2-row-disposition-update.md` OR
  `phase-2-amendment-f-floor-scope.md` (operator picks).
- Verdict C → mint `phase-2-amendment-f-floor-amend.md` OR
  `phase-2-golden-refresh.md` (operator picks).

In ALL cases, v2.5.0 tag waits until phase-2 (whichever flavour)
restores a recordable PASS state. If multiple cycles slip, the
target tag becomes v2.5.x where x increments per shipped corrective
phase (precedent: v1.3 → v1.3.1).

Report back when corrective PR is open with: re-measured Sonnet
pass_rate at n=6 (or 2× n=3), per-row stability deltas, timeout-
attributable row count, root-cause verdict, follow-up phase mint
status.
