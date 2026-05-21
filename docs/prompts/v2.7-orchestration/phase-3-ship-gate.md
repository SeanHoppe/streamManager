# v2.7 P3 — ship-gate finalize + v2.7.0 tag

> **STUB minted post-P1-merge 2026-05-21** (operator-authorised chain
> at v2.7 P1 merge). v2.7 P1 landed at `28a89c4` (PR #203). Full fold
> post-P2 verdict per goal cadence: the n=12 Seed v2.6-A re-measure
> outcome at v2.7 P2 dictates this prompt's `--runs` flag, the Seed
> v2.6-A disposition recording shape, and the Seed v2.6-A-T close-vote
> margin.
>
> **What this stub locks now:**
>
> 1. Cycle-tip anchor `4902cca440b33c14fddd9357116923ae5fe1fa4b`
>    (Amendment C — backfilled at P0 PR #201; verified at P1 merge).
> 2. Procedure skeleton (S1–S13) — mirror of v2.6 P2 ship-gate
>    (`docs/prompts/v2.6-orchestration/phase-2-ship-gate-finalize.md`)
>    minus the embedded Seed v2.5-A diagnosis blocks (those now live
>    in v2.7 P2 = the standalone re-measure phase).
> 3. Alignment-eval stability-window pre-binding per
>    `feedback_alignment_eval_stability_window.md` (3 escape-hatches):
>    - **Hatch (1) — within-band rule.** FR-OG-7 floor = **0.80**.
>      Prior cycle v2.6 P2 Sonnet `pass_rate = 0.9412` is `0.1412`
>      above floor — OUTSIDE 0.05 band. Hatch (1) does NOT fire.
>    - **Hatch (3) — unstable-count rule.** v2.6 P2
>      `unstable_sonnet = 15` of `total = 32` → **47% > 25%
>      threshold**. Hatch (3) **FIRES**: P3 MUST run `--runs 6` (or
>      2× back-to-back `--runs 3` concatenated) regardless of
>      headline `pass_rate`.
>    - **Hatch (4) — row-level timeout exclusion.** Per-row
>      `sonnet_timeout_count > 33 %` rows excluded from gate
>      denominator. Apply at P3 fire-PR per row inspection of
>      v2.7 P2 alignment-eval output.
>    - **Conclusion:** `--runs 6` mandatory at P3 (escape-hatch 3
>      bound). v2.7 P2 n=12 verdict may further escalate (see
>      §"P2 → P3 verdict-bridge" table).
> 4. Seed v2.4-E + Seed v2.4-F close-vote anchors carried from v2.6.
> 5. Memory pre-flight: 6 load-bearing memories carried from P0; light
>    re-verify at P3 fire — no full pre-flight at this stub PR.
>
> **What stays TBD pending P2 verdict (folded at P3 fire-PR):**
>
> - `--runs` final value (3 / 6 / 12 — driven by P2 disposition).
> - Seed v2.6-A disposition cite (golden update / DIP hold / new seed
>   / carry — verbatim P2 LANDED row).
> - Seed v2.6-A-T close-vote cite (close or carry; margin value).
> - Final cycle-discipline LOC tally (P1 + P2 cumulative cycle-tip
>   delta; ADR-18 Amendment A 3-bucket breakdown).
> - WIRED_LEVER_LEDGER final count (3 production / 0 soak expected
>   unchanged from P1 entry).
> - ADR-5 baseline append disposition (operator pick at fire — default
>   APPEND for a latency-surface lever like Seed v2.6-G step (2)).
>
> Cycle type **FEATURE** (recorded at P0 PR #200 `4902cca`). Soft LOC
> ≤ 1500 / BLOCK 2250 vs cycle-tip (`4902cca440b33c14fddd9357116923a
> e5fe1fa4b`). P1 + P2 cumulative cycle-tip delta entering P3:
> production-bucket +8 / −6 LOC (P1) + 0–2 LOC (P2 conditional);
> well under 1500 soft target.

## Branch + base

- Base: `main` after v2.7 P1 (PR #203 `28a89c4`) + v2.7 P2 (PR #___
  `<P2-merge-SHA>`) merged.
- PR target: `main`.
- Branch: `ship/v2.7-p3-ship-gate`.
- ABORT if either v2.7 P1 (`28a89c4`) or v2.7 P2 not merged at
  HEAD lineage (`git log --oneline origin/main -10` must include
  both).

## Pre-flight

```
git fetch origin
git log --oneline origin/main -10
```

Expected top-of-main lineage includes `28a89c4` (v2.7 P1 merge of
#203) and the v2.7 P2 merge SHA. If divergent, STOP.

Memory pre-flight at P3 — light re-verify only (Amendment B P0 pre-
flight covers 6 load-bearing memories; this ship-gate phase adds no
new memory-loading risk):

- `project_v26_cycle_close.md` — v2.6 ship reference; the v2.7 cycle
  closes by appending a sibling memory `project_v27_cycle_close.md`.
- `feedback_cli_over_sdk.md` — `claude -p` subprocess path unchanged.
- `feedback_soak_cli_pool_flag.md` — `--cli-pool-size 2` mandatory
  for S2 Tier-3 soak.
- `feedback_glob_narrowing_no_op.md` — S1 wipe uses `git clean -df
  reports/` (not glob narrowing).
- `feedback_alignment_eval_stability_window.md` — `--runs` decision
  (see §"P2 → P3 verdict-bridge").
- `feedback_certportal_dev_firewall.md` + `feedback_no_self_monitor.
  md` — unchanged scope; no certPortal coupling, no self-monitor
  surface added.

## Context

P3 is the v2.7 ship-gate. Procedure mirrors v2.6 P2 ship-gate
(`docs/prompts/v2.6-orchestration/phase-2-ship-gate-finalize.md`)
with the row-10 re-measure surgery REMOVED — that landed at v2.7 P2
as its own work-phase. v2.7's P3 is therefore a thinner, more
focused ship-gate: soak + alignment-eval + invariants + tag.

## P2 → P3 verdict-bridge (folded at P3 fire-PR)

The v2.7 P2 n=12 re-measure verdict drives three P3 parameters:

**Baseline `--runs 6` is already bound at P3 via stability-window
escape-hatch (3) — unstable_sonnet 15/32 = 47% > 25%** (see header
§3 above). The P2 verdict can only ESCALATE further (to `--runs 12`
or full re-fire), never down-shift from 6.

| P2 verdict                          | `--runs` (S4 alignment-eval) | Seed v2.6-A status at P3       | Seed v2.6-A-T status at P3    |
|-------------------------------------|------------------------------|---------------------------------|--------------------------------|
| STABLE-CONTENT-DRIFT (≥ 9/12 INTERVENE) | `--runs 6` (baseline; golden re-baselined at P2 expected to restore stability — re-evaluate unstable_sonnet at P3 alignment-eval output) | CLOSED RESOLVED (golden updated at P2) | CLOSED iff p99 ≥ 2 s under cap (expected) |
| STILL-UNSTABLE (6–8/12 INTERVENE)   | `--runs 6` (baseline; row-10 instability persists — consider per-row exclusion via hatch (4) if its timeout-count > 33 %) | CARRIES to v2.8 (DIP-watch hold)| CLOSED iff p99 ≥ 2 s under cap (expected) |
| VERDICT-DIVERSITY (< 6/12 INTERVENE) | `--runs 6` (baseline; new verdict landscape — Sonnet pass-rate floor at risk; consider `--runs 12` if P2 timing budget allows) | SPAWNS Seed v2.7-A-N at backlog | CLOSED iff p99 ≥ 2 s under cap (expected) |
| STILL-100%-TIMEOUT-ESCALATE (≥ 6/12 NONE) | `--runs 6` baseline + Seed v2.6-G step (3) env-split FOLLOW-UP escalation v2.8 | CARRIES to v2.8 pending v2.6-A-T resolution | CARRIES — re-fire after step (3) lands |

Default expectation at this stub mint: STABLE-CONTENT-DRIFT or
STILL-UNSTABLE most likely (n=6 baseline = 4/6 INTERVENE; new 30 s
cap removes the 1/6 NONE noise floor); STILL-100%-TIMEOUT-ESCALATE
unlikely (5.04 s headroom above row-10 single-row n=6 p99 24.960 s).

## ⚠️ CRITICAL: Do-not-touch guard

ADR-18 surface-freeze applies. P3 MUST touch ONLY:

- **CHANGELOG.md** — append v2.7.0 ship entry.
- **`docs/v2.7-task-plan.md` §"P3 close-out"** — fill the operator-
  decision blocks.
- **`docs/v2.7-next-steps.md`** §"Fire-order" row 5 + compare-back
  rows — flip `[ ]` → `[x] ✅ LANDED`.
- **`docs/v2.7-backlog.md`** (NEW; carry-forwards to v2.8).
- **`docs/adr/ADR-5-latency-budgets.md`** — operator decides
  APPEND vs hold; default APPEND for latency-surface lever
  (Seed v2.6-G step (2)).
- **Memory mint:** `~/.claude/projects/.../memory/project_v27_cycle_
  close.md` + MEMORY.md index entry.

NO edits to `src/`, `tests/` (other than golden if v2.7 P2 didn't
land its conditional golden flip and STABLE-CONTENT-DRIFT was the
verdict — but that's a P2 scope obligation, not P3's), `tools/`,
`dashboard/`, FROZEN bus envelope schema, governance HITL surfaces.
NO deletions; NO renames.

**Specifically do NOT touch:**

- `src/stream_manager/cli_governance.py:49` — `TIMEOUT_SECONDS =
  30.0` from P1; do NOT revert or further adjust.
- `src/stream_manager/latency_budgets.py` — `BRIDGE_FALLBACK_
  LATENCY_BUDGET_MS = 45_000` from P1; do NOT revert.
- `tests/golden/l4_alignment.jsonl:10` — if updated, the update
  landed at P2; do NOT re-edit.

## Scope (S1–S13)

Procedure mirrors v2.6 P2 ship-gate skeleton; row-10 re-measure
blocks REMOVED (handled at v2.7 P2):

### S1 — wipe reports

```
git clean -df reports/
```

Per `feedback_glob_narrowing_no_op.md`: tracked-status filter, not
filename pattern guess. **S1.1 assertion:** `git status -s reports/`
empty after clean.

### S2 — Tier-3 soak (cycle-tip anchor binding)

```
# Canonical S2 env block (per P0 skeleton §"Canonical S2 env block")
$env:BRIDGE_API_GOV = "1"
$env:BRIDGE_RL_LOGGER_ENABLED = "1"
$env:BRIDGE_LOC_PATHSPEC = "src/,tests/,tools/,dashboard/"

python -m tools.soak_driver --tier 3 --cli-pool-size 2 \
  --duration-minutes <TBD; default per v2.6 P2 = 60>
```

`--cli-pool-size 2` MANDATORY per `feedback_soak_cli_pool_flag.md`.
Soak runs with new `TIMEOUT_SECONDS = 30.0` (production path under
elevated cap; expect `degrade_count = 0` unchanged from v2.4–v2.6
baseline).

### S3 — invariant + dual-anchor

```
python -m tools.invariant_check --anchor cycle-tip
python -m tools.cycle_loc_dual_anchor \
  --cycle-tip 4902cca440b33c14fddd9357116923ae5fe1fa4b \
  --predecessor-tag c3a964c
```

Cycle-tip is the gating LOC anchor (Amendment C); predecessor-tag
narrative diff `c3a964c..HEAD` is reported alongside but does not
gate (Amendment C §"Bucket-scoped narrative").

### S4 — alignment-eval

`--runs` flag per `feedback_alignment_eval_stability_window.md` and
the §"P2 → P3 verdict-bridge" table above. **At this stub mint, the
P2 verdict is not yet known; the P3 fire-PR sets the final flag.**

```
python -m tools.alignment_eval --runs <P2-verdict-driven; see bridge> \
  --ci-gate
```

If `--ci-gate` exit ≠ 0 → BLOCK; fold corrective sub-phase per
v2.5.1 precedent (PR #188).

### S4.5 — (REMOVED; was Seed v2.6-A re-measure at v2.6 P2)

Re-measure landed at v2.7 P2 (PR #___ `<P2-merge-SHA>`). P3 does NOT
re-fire the row-10 single-row.

### S5 — LOC delta verify (Amendment C cycle-tip)

```
git diff 4902cca440b33c14fddd9357116923ae5fe1fa4b..HEAD --stat -- src tests tools dashboard
```

Cumulative cycle delta entering P3: production-bucket +8 / −6 LOC
(P1) + 0–2 LOC (P2 conditional). P3 adds 0 LOC production-bucket.
Total expected: +8 / −6 LOC production, well under soft ≤ 1500
target.

Predecessor-tag narrative diff `c3a964c..HEAD` reported alongside
(does NOT gate; cycle-impact context only).

### S6 — lever-ledger confirm

WIRED_LEVER_LEDGER posture: **3 production / 0 soak** unchanged.
P1 bumped 2 → 3 (Seed v2.6-G step (2) `TIMEOUT_SECONDS` cap); P2
added no production lever (re-measure is measurement, not wire);
P3 adds no production lever (ship-gate is closure, not wire).

| Cycle | Wire                                                            | Bucket    |
|-------|-----------------------------------------------------------------|-----------|
| v2.3  | Seed 6 — JsonlTailWorker production wiring                      | src       |
| v2.6  | Seed v2.5-G step (1) — alignment-eval wall-clock instrumentation | tools/src |
| v2.7  | Seed v2.6-G step (2) — `TIMEOUT_SECONDS` cap                    | src       |

### S6.5 / S6.6 — (REMOVED; absorbed into v2.7 P2)

Seed v2.6-A disposition + Seed v2.6-A-T close-vote landed at v2.7
P2. P3 records the verdicts in `project_v27_cycle_close.md` only.

### S7 — ADR-5 baseline append

Operator decides at P3 fire: APPEND new baseline row with `TIMEOUT_
SECONDS = 30.0` measurement, or hold. Default APPEND (latency-surface
lever; ADR-5 cadence prefers append over re-baseline).

### S8 — CHANGELOG append

Append v2.7.0 entry to `CHANGELOG.md`:

- Feature: `cli_governance.TIMEOUT_SECONDS` 25.0 → 30.0 (first
  FROZEN-surface lever ever wired; J2-audit-aware).
- Calibration (conditional): golden row 10 `expected_verdict`
  SUGGEST → INTERVENE (v2.7 P2 STABLE-CONTENT-DRIFT outcome only).
- Closed seeds: Seed v2.6-A-T (timeout-boundary watch), Seed v2.6-A
  (if STABLE-CONTENT-DRIFT; otherwise carries v2.8).
- Carry-forwards: see `docs/v2.7-backlog.md`.

### S9 — tag v2.7.0

```
git tag -a v2.7.0 -m "v2.7.0 — feature cycle (Seed v2.6-G step (2) timeout-tighten)"
git push origin v2.7.0
```

### S10 — compare-back

Walk `docs/v2.7-next-steps.md` row-by-row. Every `[ ]` should now
read `[x] ✅ LANDED PR #__ (`<SHA>`)`. Any leftover `[ ]` BLOCKS
ship; fold disposition into §"P3 close-out" or carry to v2.8.

### S11 — close memory

Mint `~/.claude/projects/C--Users-SeanHoppe-vs-streamManager/memory/
project_v27_cycle_close.md`:

- v2.7.0 ship SHA + date.
- P1 verdict: Seed v2.6-G step (2) wired (first FROZEN-surface).
- P2 verdict: Seed v2.6-A disposition (filled from P2 LANDED row).
- Seed v2.6-A-T close-vote outcome.
- Alignment-eval Sonnet pass-rate post-cap (track vs 0.9412 v2.6
  baseline).
- Soak p95 / Haiku floor / regression rows.
- v10 P4 corpus delta (if BRIDGE_RL_LOGGER_ENABLED=1).
- Cycle-tip LOC delta + WIRED_LEVER_LEDGER final.
- Carry-forwards to v2.8.

Update MEMORY.md index with one-line hook entry.

### S12 — lifetime

Default: v2.7 prompts persist as historical record (mirror v2.6
lifetime decision).

### S13 — mint v2.8 P0 frame ahead-of-fire

Per PM-mint precedent (PR #178 / PR #191 / PR #199), mint:

- `docs/prompts/v2.8-orchestration/phase-0-cycle-frame.md` skeleton.
- `docs/v2.8-task-plan.md` skeleton.
- `docs/v2.8-next-steps.md` skeleton with carry-forwards from
  `docs/v2.7-backlog.md`.

Operator chooses cycle-type default-lean (feature vs consolidation)
at P0 fire.

### Close-vote rows

- **Seed v2.4-E (overall p95):** close ≤ 8.2 s; carry ≤ 10 s (3rd
  consecutive); regression-flag > 10.156 s.
- **Seed v2.4-F (L4 half):** close ≤ 17 s; carry ≤ 22 s (reduced
  concern); promote 🔴 if ≥ 22 s.
- **v10 P4 corpus piggyback (Run 8):** if `BRIDGE_RL_LOGGER_ENABLED=1`,
  record Δ episodes; ≥ 60 → CLEARED, < 60 → CARRY.

## DOD

### Step (P3) mandatory

- [ ] S1 wipe + S1.1 assertion clean.
- [ ] S2 Tier-3 soak completed; `degrade_count = 0`; canonical env
      block exported.
- [ ] S3 invariant check exit 0; dual-anchor LOC matrix produced.
- [ ] S4 alignment-eval `--runs <P2-verdict-driven>` `--ci-gate`
      exit 0.
- [ ] S5 cycle-tip LOC verified ≤ 1500 (soft); production-bucket
      breakdown documented.
- [ ] S6 WIRED_LEVER_LEDGER posture verified **3 production / 0
      soak**.
- [ ] S7 ADR-5 baseline disposition recorded (APPEND vs hold).
- [ ] S8 CHANGELOG v2.7.0 entry appended.
- [ ] S9 tag v2.7.0 created + pushed.
- [ ] S10 compare-back walk complete; no leftover `[ ]`.
- [ ] S11 `project_v27_cycle_close.md` minted + MEMORY.md index
      entry added.
- [ ] S12 lifetime decision recorded.
- [ ] S13 v2.8 P0 skeleton minted.
- [ ] Close-vote rows recorded (Seed v2.4-E, v2.4-F, v10 P4
      piggyback).

### Cycle-discipline

- [ ] LOC budget: production-bucket cumulative cycle-tip delta
      documented; inside soft ≤ 1500 / BLOCK 2250.
- [ ] WIRED_LEVER_LEDGER unchanged at P3 (P3 is closure, not wire).
- [ ] Sub-cycle close-out diff guard per
      `feedback_subagent_stale_mental_model.md`: confirm P3 touched
      only the documented surface (CHANGELOG + docs + ADR-5 +
      memory).
- [ ] Single PR against `main` (`ship(v2.7):` conventional commits
      prefix).
- [ ] No re-fire of P1 or P2 edits (cap stays 30.0; golden row
      stays at the value set by P2).

### ADR-18 surface-classification

- [ ] PR body documents: P3 fires no new lever wire. P1's FROZEN-
      surface lever (Seed v2.6-G step (2)) ships **as part of**
      v2.7.0 — the J2-audit framing already documented at P1 fire
      (PR #203) is cited verbatim in `project_v27_cycle_close.md`.
- [ ] PR body cites: P1 PR #203 (`28a89c4`), P2 PR #___
      (`<P2-merge-SHA>`), J2 audit
      (`docs/seed-v2.6-g-step2-timeout-tighten-audit.md`).

### Memory + docs

- [ ] `project_v27_cycle_close.md` minted with all verdict cites
      filled.
- [ ] MEMORY.md index updated.
- [ ] No new FR row in `REQUIREMENTS.md` (P3 is ship, not contract
      delta).

## Cross-refs

- `docs/prompts/v2.6-orchestration/phase-2-ship-gate-finalize.md` —
  full v2.6 P2 procedure template (S1–S13 source; row-10 re-measure
  surgery REMOVED in v2.7 P3 because it lives at v2.7 P2).
- `docs/prompts/v2.7-orchestration/phase-0-cycle-frame.md` — P0
  skeleton; canonical S2 env block source.
- `docs/prompts/v2.7-orchestration/phase-1-cli-timeout-tighten.md` —
  P1 prompt (PR #202 `5afd5da` mint; PR #203 `28a89c4` fire).
- `docs/prompts/v2.7-orchestration/phase-2-seed-v2.6-a-row10-
  remeasure.md` — P2 prompt (PR #204 `232f22c` mint; fire PR
  TBD).
- `docs/v2.7-task-plan.md` §"PHASE P3" — ledger destination.
- `docs/v2.7-next-steps.md` §"Fire-order" row 5 + close-vote rows —
  compare-back markers.
- `docs/seed-v2.6-g-step2-timeout-tighten-audit.md` — J2 evidence
  audit; cap = 30 s primary recommendation.
- `docs/seed-v2.6-a-row10-remeasure-protocol.md` — J3 protocol
  (consumed by v2.7 P2).
- `feedback_alignment_eval_stability_window.md` — n=6 escape-hatch
  rule (P3 §"P2 → P3 verdict-bridge" lookup).
- `feedback_soak_cli_pool_flag.md` — `--cli-pool-size 2` mandatory.
- `feedback_glob_narrowing_no_op.md` — S1 wipe pattern.
- `feedback_subagent_stale_mental_model.md` — sub-cycle close-out
  diff guard.
- ADR-18 Rule 1 (surface freeze) — P3 touches no FROZEN surface.
- ADR-18 Amendment A (3-bucket) — P3 docs-bucket only.
- ADR-18 Amendment C (cycle-tip anchor) —
  `4902cca440b33c14fddd9357116923ae5fe1fa4b` binds P3 LOC
  measurement.
- Precedent ship PRs: v2.5 PR #__ ; v2.6 PR #198 (`c3a964c`).

## Stub → final fold task list (at P3 fire-PR open)

When opening the P3 fire-PR, the operator (or this prompt's
finalisation step) replaces the TBD blocks listed in the header
with verbatim values pulled from v2.7 P2 LANDED:

1. P2 merge SHA → fill `<P2-merge-SHA>` placeholder (3 sites).
2. P2 disposition verdict → §"P2 → P3 verdict-bridge" table
   row-pin + §S11 close-memory bullet.
3. P2 Seed v2.6-A-T close-vote → §S11 close-memory bullet.
4. `--runs` final value → §S4 invocation block.
5. P1 + P2 cumulative cycle-tip LOC tally → §S5 expectation block.
6. Final WIRED_LEVER_LEDGER count → §S6 confirmation block (still
   3 / 0 expected).
7. ADR-5 baseline append disposition → §S7 (APPEND / hold).

This stub does NOT autonomously fire. It is the structure-and-
parameter holder; the P3 fire-PR fold turns it into an executable
script.

Report back when P3 fire-PR opens with:

1. PR URL.
2. Final-fold delta (this stub → fire-PR final form; the 7 TBD
   slots filled).
3. v2.7.0 tag SHA + push confirmation.
4. `project_v27_cycle_close.md` paste.
5. Full cycle-discipline LOC matrix + WIRED_LEVER_LEDGER posture.
