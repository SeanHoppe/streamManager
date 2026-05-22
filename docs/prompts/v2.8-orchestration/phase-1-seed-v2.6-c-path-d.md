# v2.8 P1 — Seed v2.6-C Path-D synthetic-fixture P5 implementation

> Minted ahead-of-fire 2026-05-22 (mirrors v2.4 PR #182 + v2.5.1
> PR #188 + v2.6 PR #195 + v2.7 PR #202 PM-mint cadence — work-phase
> prompt minted in a PM PR separate from the P0 cycle-frame PR).
>
> Cycle type **FEATURE / Convergence** (Q-A recorded at v2.8 P0 PR #211
> `70e23e5` per `docs/v2.8-task-plan.md` §"Cycle posture entering v2.8"
> + `docs/v2.8-next-steps.md` §"P0 frame — operator-bound decisions"
> Q-A `[x]`). Bundle order Q-B option 1: this is P1 (Path-D first).
> Soft LOC ≤ 1500 / BLOCK at 1.5× = 2250 vs cycle-tip `70e23e5`.
>
> **Three work phases this cycle** per `docs/v2.8-task-plan.md`
> §"Phases (recommended bundle order)": P1 (this) + P2 (step (3)
> env-split + Seed v2.7-A-CLIP corpus re-measure) + P3 (ship-gate).
>
> **6th-consecutive defer averted.** Seed v2.6-C deferred 6 cycles
> (v2.4 + v2.5 + v2.5.1 + v2.6 + v2.7 + v2.7.1; per `docs/v2.7.1-
> backlog.md` L28 "6th-consecutive deferral"). v2.8 Convergence-cycle
> Q-A FEATURE pick promotes this seed to FIRE; closes head-of-chain
> per `docs/v10-mvp-status.md` §"Held-chain map" (unblocks #112 →
> #131 → #124 + #125 in sequence).
>
> **v10 P5 prompt is authoritative.** Implementation surface mirrors
> `docs/prompts/v10-orchestration/phase-5-shadow-stop-conditions.md`
> verbatim; this v2.8 P1 prompt is the cycle-scoped framing wrapper +
> Amendment D v10.1-mode entry-gate disambiguation header. NO scope
> drift vs v10 P5 prompt without explicit operator override.
>
> Comparison anchor: `docs/v2.8-next-steps.md` §"Fire-order" row 1 +
> §"Seed v2.6-C". Compare-back row marker `[ ] FIRE FIRST — Path-D
> synthetic-fixture P5; ~+600 LOC ... PR #___ (<merge-SHA>)` updated
> on merge.

## Branch + base

- Base: `main` after v2.8 P0 PR #211 (`70e23e5`) + v2.8 P0 backfill
  PR #212 (`1f17cbc`) + this P1-prep PR merged.
- PR target: `main`.
- Branch: `feat/v2.8-p1-path-d`.
- ABORT if v2.8 P0 + backfill + this P1-prep PR not at HEAD lineage;
  ABORT if HEAD has drifted from v2.8 P0 base.

## Pre-flight

```
git fetch origin
git log --oneline origin/main -10
```

Expected top-of-main lineage includes `1f17cbc` (v2.8 P0 backfill) +
`70e23e5` (v2.8 P0 frame) reachable. If divergent, STOP.

Memory pre-flight at P1 — light re-verify (P0 already stamped 7
load-bearing memories FRESH in v2.8 P0 PR #211 + `docs/v2.8-task-
plan.md` §"Cycle posture entering v2.8"). Re-confirm at P1 PR body:

- `project_v271_cycle_close.md` — cycle-close ground truth; carry-
  forward seed list (Seed v2.6-C disposition).
- `feedback_no_self_monitor.md` §"Polarity flip" — Q-D monitor target
  binding from P0; v2.8 phase fires inherit env-var mandate.
- `feedback_certportal_dev_firewall.md` — dev-session firewall
  unchanged; runtime monitoring of certPortal sessions (Q-D binding)
  != dev-session licence to read certPortal repo.
- `feedback_subagent_long_task_abandonment.md` — P1 implementation
  does NOT spawn long-running tasks from subagents; any soak
  validation runs from main thread.
- `feedback_soak_cli_pool_flag.md` — `--cli-pool-size 2` mandate
  binds at any P1 verification soak (synthetic-fixture P5 does NOT
  require Tier-3 soak; v10 P4 piggyback resumes at P3 ship-gate).

Stale memories: update in a separate pre-P1 PR or at top of P1 PR
per Amendment B precedent.

## Context

Per `docs/v10-mvp-status.md` §"Implementation-side gate: Seed v2.6-C
(Path-D synthetic-fixture P5, ~600 LOC, deferred v2.7 — 4th
consecutive deferral)" + `docs/v2.8-task-plan.md` §"P1 — Seed v2.6-C
Path-D synthetic-fixture P5":

Path-D is the **synthetic-fixture** flavour of v10 P5 — the canonical
v10 P5 prompt (`docs/prompts/v10-orchestration/phase-5-shadow-stop-
conditions.md`) covers two operating modes. Under v10.1-mode
deterministic-policy operation (the active mode through v10.3
writeback unlock), there is no off-baseline candidate to run a live
A/B shadow against. Path-D resolves this by validating the
implementation end-to-end against **synthetic fixtures** (test corpus,
not live shadow) — proving infrastructure works without requiring
v10.3 stochastic-propensity rollouts.

**ADR-18 Amendment D v10.1-mode entry gate** (minted at v2.4 P0
PR #179 `b35e982`):

| Mode | Active when | Gate condition |
|---|---|---|
| **v10.1-mode** | v10.x stages 0-2 (deterministic production policy) | baseline arm `_total >= 200` AND `posterior_ci_width(baseline_arm) <= 0.10`; P5 runs as infrastructure validation (baseline-vs-baseline) |
| **v10.3-mode** | v10.3 stochastic propensity writeback active | original gate: non-baseline `best_arm` clears `_total >= 200 AND best_arm_posterior_ci() <= 0.10`; ship criteria checker may exit 0 (ALL PASS) |

v2.8 P1 fires under **v10.1-mode**. Synthetic-fixture run = baseline-
vs-baseline ghost-path execution against the alignment-golden corpus.
Infrastructure validates end-to-end; ship-criteria checker exit code
is informational (NOT a v10.3 writeback green-light at this stage).

Corpus posture at P1 fire (per `project_v271_cycle_close.md`
§"v10 P4 corpus piggyback (Run 9)"): cumulative live episodes = 777
(3.89× over the 200-row v10 P4 gate). v10.1-mode baseline arm
`_total >= 200` satisfied with margin.

## Scope (adapted from v10 P5 prompt — `docs/prompts/v10-orchestration/phase-5-shadow-stop-conditions.md`)

### Adaptation rationale

v2.8 P1 §"Scope" mirrors the v10 P5 prompt deliverables with two
v2.8-cycle adaptations:

1. **+2 CLI test files** (`tests/test_rl_cli_shadow.py` + `tests/
   test_rl_cli_check_criteria.py`). v10 P5 prompt DoD L134 only
   floors `test_rl_{shadow,stop_conditions}.py`. v2.8 P1 lands CLI
   modules `rl/cli/shadow.py` + `rl/cli/check_criteria.py` (per
   v10 P5 prompt §"Deliverables 3" + "Deliverables 4"); per
   ADR-18 §"New module classification rule" each new module needs
   matching test coverage at birth. CLI tests target argparse +
   exit-code surface, not subprocess behaviour.
2. **DoD substitutes `pytest` for "real Tier 3 soak"** per
   Amendment D v10.1-mode synthetic-fixture mode (see §Context
   L84-89 + §"Departure footnote" in §"DoD" below).

Touch list (~+600 LOC `rl/` + tests):

- **`rl/shadow.py`** (new) — `ShadowRecorder` class; ghost-path
  candidate exec; opens dedicated `rl_shadow.db` (WAL, separate
  writer); `on_governance_decision(envelope)` bus callback;
  non-invasion invariant (≤ 50 ms p95; production NEVER waits on
  shadow; drop + emit `rl_shadow_dropped` envelope on budget
  breach).
- **`rl/stop_conditions.py`** (new) — `ShipCriteria` dataclass
  (frozen thresholds; pre-registered values not configurable);
  `evaluate_criteria(shadow_db, manifest_dir, baseline)
  -> CriteriaReport`; 6 pre-registered criteria per v10 P5 prompt
  §"Ship criteria — pre-registered" table.
- **`rl/cli/shadow.py`** (new) — `python -m rl.cli.shadow --proposal
  rl_proposals/<UTC>Z.json --soak-tier 3 [--soak-args "..."]`;
  spawns `tools/soak_driver.py --cli-pool-size 2 --shadow-recorder
  rl_shadow.db --shadow-proposal <path>`. **OPEN at P0 in v10 P5
  prompt L92**: if `tools/soak_driver.py` is FROZEN under
  ADR-18, fall back to sidecar JSONL-tail post-run write. Resolve
  at v2.8 P1 fire-PR open: re-verify soak_driver classification
  against ADR-18 §"Initial classification" + amendments — current
  classification = EVOLVING for v10.0-v10.2 per
  `docs/v10-task-plan.md` L38, so in-process `--shadow-recorder`
  flag-add is admissible. v2.8 P1 PR records the re-verification
  outcome in PR body.
- **`rl/cli/check_criteria.py`** (new) — `python -m rl.cli.check_
  criteria --shadow-db rl_shadow.db --manifests rl_proposals/`;
  exit 0 = ALL PASS (informational only under v10.1-mode; NOT a
  writeback green-light).
- **`tests/test_rl_shadow.py`** (new) — synthetic-fixture
  ghost-path test against alignment-golden corpus subset; verifies
  schema integrity, non-invasion invariant, `agree` boolean
  semantics, ground-truth-when-available handling.
- **`tests/test_rl_stop_conditions.py`** (new) — verifies all 6
  criteria evaluated correctly on synthesised shadow_db + manifest
  fixtures; verifies pre-registered thresholds are frozen (assert
  on dataclass `frozen=True`).
- **`tests/test_rl_cli_shadow.py`** (new) — CLI argparse + subprocess
  spawn surface (mock soak_driver call); verifies `--shadow-recorder`
  flag passthrough + soak_run_id derivation.
- **`tests/test_rl_cli_check_criteria.py`** (new) — CLI argparse +
  report generation; verifies exit code 0 / 1 semantics.
- **`docs/v10-rl-design.md`** APPEND only — new §"v10 ship criteria
  — pre-registered" subsection with the 6 thresholds verbatim from
  v10 P5 prompt §"Ship criteria" table.
- **`docs/adr/ADR-5-latency-budget.md`** APPEND only — new §"v10
  shadow overhead" subsection citing the ≤ 50 ms p95 non-invasion
  budget; recorded as advisory baseline pending Tier-3 shadow
  reading at v10.3 promotion (NOT v2.8 P1).
- **NO edits to gov code**. Shadow path is non-invasive by
  construction. Pre-flight grep verifies FROZEN symbols still
  present:

  ```
  grep -nE 'governance_decision|RoutingDecision|requires_alignment' src/stream_manager/governance.py src/stream_manager/cli_governance.py
  ```

  No diff in any v2.8 P1 PR against `src/stream_manager/governance.py`
  + `src/stream_manager/cli_governance.py` allowed.

## Shadow-only invariant (v10 P5 prompt L119-125 carryover)

P5 changes NO production behaviour. Adapted to v10.1-mode
synthetic-fixture mode:

- **Production decision flow byte-identical pre/post shadow** —
  golden-corpus replay verdicts MUST match between
  `--shadow-recorder=<db>` enabled and disabled runs. Pre-merge
  sanity-check: `tools/alignment_eval.py --runs 1 --report-only`
  output JSON byte-equal between shadow-on and shadow-off.
- **`cli_dispatch_ms` p95 unchanged** vs v10 P4 baseline in
  fixture-replay timing (since no Tier-3 soak fires at v2.8 P1
  under Amendment D substitution, the comparator is the v10 P4
  episode-logging p95 from `reports/seed-v2.5-g/` baseline rather
  than a live soak).
- **All v1.7–v2.0 + v10 P1–P4 tests green** per v10 P5 prompt
  DoD L141.
- **Non-invasion invariant `on_governance_decision` ≤ 50 ms p95**
  asserted in `tests/test_rl_shadow.py::test_shadow_does_not_
  block_bus` (v10 P5 prompt L102 verbatim test name).

Any deviation = STOP fire + surface to operator (production
correctness blocking).

## ADR-18 surface-classification

Per `docs/v10-task-plan.md` §"P5 — shadow + ship criteria (v10.2)"
+ ADR-18 §"Initial classification":

- `rl/shadow.py`, `rl/stop_conditions.py`, `rl/cli/shadow.py`,
  `rl/cli/check_criteria.py` — **NEW modules**; classification at
  birth = EVOLVING (not FROZEN until first ship-gate consolidation
  per ADR-18 §"New module classification rule"). Path-D synthetic-
  fixture lands under EVOLVING; v10.x freeze-lift cycle (issue #131)
  will re-classify post-#112 close.
- `rl_shadow.db` schema — NEW; EVOLVING until v10.3 writeback opens.
- `tools/soak_driver.py` — current classification = EVOLVING for
  v10.0-v10.2 per `docs/v10-task-plan.md` L38; the `--shadow-
  recorder` CLI flag-add stays within EVOLVING surface. v2.8 P1
  PR body MUST re-verify this classification against
  ADR-18 amendments before flag-add lands. If reclassified to
  FROZEN since v10-task-plan.md last update, fall back to sidecar
  JSONL-tail strategy per v10 P5 prompt L92.

## WIRED_LEVER_LEDGER posture

- Entering P1: **3 production / 0 soak** (per
  `docs/v2.7.1-task-plan.md` close-out + v2.8 P0 frame
  §"Cycle-discipline carries").
- Exiting P1: **HOLD 3 / 0**. Path-D touches `rl/` surface which is
  EVOLVING-not-FROZEN; new-module landings do NOT count as
  lever-wires (lever-wire = FROZEN-surface classification widening
  per ADR-18 amendment record).
- v2.8 P2 step (3) env-split WILL bump ledger 3 → 4 (FROZEN
  `cli_governance.py:49` widening to cover `BRIDGE_CLI_TIMEOUT_EVAL`
  env override); that's P2 scope, not P1.

## LOC envelope

- P1 cycle-tip LOC delta vs `70e23e5`: target **~+600 LOC**
  production-bucket (`rl/` + `tests/`); BLOCK at +900 LOC strict
  scope cap (1.5× target; matches `docs/v10-task-plan.md` L144
  P5 budget ≤ 600 net add). Soft target ≤ 1500 / BLOCK 2250
  cycle-wide envelope absorbs P1 + P2 (~50) + P3 (0 prod) with
  substantial headroom.
- Re-run at P1 fire:

  ```
  git diff 70e23e5..HEAD --stat -- src tests tools dashboard rl
  ```

  Expected at P1 close: `rl/` ~+600 / `tests/` substantial /
  `src/`, `tools/`, `dashboard/` = 0.

## Q-D monitor target carryover (binds P1 if any verification soak fires)

Per v2.8 P0 §"Monitor target" §"Operator action for v2.8 P1
fire-PR (pre-launch checklist)": IF P1 fire-PR runs the dashboard
process OR launches a Tier-3 soak (which it generally does NOT for
synthetic-fixture P5 — fixtures are offline), env-var mandate
applies before launch:

- 0. Restart dashboard process so FastAPI startup re-reads env.
- 1. Enumerate operator-local SM project dir names (encoded form).
- 2. Export `BRIDGE_SM_PROJECT_SLUGS=<encoded SM dir set ∪
     short-form alias `streamManager`>`.
- 3. Export `BRIDGE_PROJECT_SLUG=C--Users-SeanHoppe-VS-certPortal`
     (encoded dir name).
- 4. Export `BRIDGE_SM_SELF_SESSION_ID=<current session id>`.
- 5. Verify dashboard log emits `jsonl_tail: started (...
     slug=C--Users-SeanHoppe-VS-certPortal ...)`.
- 6. Abort + surface to operator if certPortal slug dir absent
     (NEVER bootstrap via certPortal repo read; firewall holds).

**Path-D synthetic-fixture P5 implementation in this PR does NOT
require dashboard runtime OR Tier-3 soak.** Synthetic-fixture =
offline ghost-path execution against alignment-golden corpus
subset (test fixture). Q-D env mandate is documented here for
completeness; phase-fire-PR body cites "N/A — fixture-driven, no
dashboard/soak runtime" when the binding does not actually
fire at P1.

## Do-not-touch guard

Scope locked to the 4 new modules + 4 new test files + 2 doc
appends listed in §"Scope". Explicit scope-creep guards:

- `src/stream_manager/governance.py` — NO diff allowed (FROZEN
  per ADR-18 Rule 1).
- `src/stream_manager/cli_governance.py` — NO diff allowed
  (FROZEN per Rule 1; only v2.8 P2 step (3) env-split is sanctioned
  to touch this file in v2.8 cycle).
- `rl/episode_logger.py` — NO diff allowed (out-of-scope; v10 P5
  shadow path is non-invasive by construction — shadow records to
  separate `rl_shadow.db`, never touches the live `rl_episodes.db`
  ingest surface. Classification verify at fire: ADR-18
  §"Initial classification" lists `rl/` as EXPERIMENTAL at v10 P1
  birth; promotion to EVOLVING / FROZEN tracked in amendment record.
  Either way, this PR does NOT diff the file).
- `tools/soak_driver.py` — `--shadow-recorder` flag-add ONLY,
  ≤ 30 LOC. NO other changes (parser surface stays minimal).
- `docs/v10-rl-design.md` — APPEND only (new section); NO edits
  to existing sections.
- `docs/adr/ADR-5-latency-budget.md` — APPEND only (new
  subsection); NO edits to existing budgets.

Any cross-file refactor or "I noticed this nearby" cleanup STOPS
fire and surfaces to operator. Land cleanups in a separate PR
post-v2.8.

## DoD (P1 fire-PR)

### Departure footnote (Amendment D v10.1-mode substitution)

v10 P5 prompt DoD L138 requires "Sample shadow report attached
to PR, from a real Tier 3 soak with the latest P4 proposal". v2.8
P1 substitutes synthetic-fixture pytest validation per Amendment D
v10.1-mode entry gate (deterministic production policy; no off-
baseline candidate to A/B). Real Tier-3 shadow report DEFERS to
v10.3 writeback cutover. Sample CRITERIA report at P1 close MAY
attach (expected outcome at v10.1-mode first run: FAIL on
"insufficient shadow runs" per v10 P5 prompt L139).

### Checkpoints

- [ ] v10.1-mode synthetic-fixture substitution invoked per
      §Context + §"Departure footnote" above (NOT a v10.3
      writeback green-light).
- [ ] Branch `feat/v2.8-p1-path-d` opened from `main` after v2.8
      P0 + backfill + this prep PR merged.
- [ ] Touch list matches §"Scope" exactly (4 new code modules +
      4 new test files + 2 doc appends + soak_driver flag-add).
- [ ] Pre-flight FROZEN-symbol grep PASS (no diff in
      governance.py / cli_governance.py / rl/episode_logger.py).
- [ ] soak_driver ADR-18 classification re-verified in PR body
      (EVOLVING confirmation OR sidecar JSONL-tail fallback
      documented).
- [ ] `pytest tests/test_rl_shadow.py tests/test_rl_stop_conditions.py
      tests/test_rl_cli_shadow.py tests/test_rl_cli_check_criteria.py
      -v` green.
- [ ] Full suite `pytest -q` green (no regressions).
- [ ] LOC delta `git diff 70e23e5..HEAD --stat -- src tests tools
      dashboard rl` within target (~+600 / BLOCK +900 P1-strict).
- [ ] Cumulative cycle-tip delta within Convergence envelope
      (cycle-wide soft ≤ 1500 / BLOCK 2250).
- [ ] WIRED_LEVER_LEDGER posture HOLD 3 / 0 at P1 merge confirmed
      in PR body.
- [ ] `docs/v10-rl-design.md` §"v10 ship criteria —
      pre-registered" appended with 6 thresholds verbatim from v10
      P5 prompt.
- [ ] `docs/adr/ADR-5-latency-budget.md` §"v10 shadow overhead"
      appended.
- [ ] PR body cites synthetic-fixture mode + v10.1-mode entry gate
      semantics (NOT a v10.3 writeback green-light).
- [ ] Memory pre-flight stamp recorded in PR body (5 memories
      re-verified per §"Pre-flight").
- [ ] Compare-back marker `[ ] FIRE FIRST — Path-D synthetic-
      fixture P5 ...` in `docs/v2.8-next-steps.md` §"Fire-order"
      row 1 → `[x] LANDED PR #___ (<merge-SHA>)` on merge.

## Cross-refs

- `docs/prompts/v10-orchestration/phase-5-shadow-stop-conditions.md`
  — authoritative implementation surface (verbatim source for
  §"Scope").
- `docs/v10-task-plan.md` §"P5 — shadow + ship criteria (v10.2)"
  — touch list + LOC budget + EVOLVING classification anchor.
- `docs/v10-mvp-status.md` §"Implementation-side gate: Seed v2.6-C"
  + §"Held-chain map" — head-of-chain rationale; downstream
  unblock sequence (#112 → #131 → #124 + #125).
- `docs/v2.7.1-backlog.md` §"Carry-forwards from v2.7.1" item 1
  — Seed v2.6-C carry-forward; PROMOTED candidate ground truth.
- `docs/v2.8-task-plan.md` + `docs/v2.8-next-steps.md` — cycle
  ledger + row-by-row fire-order disposition.
- `docs/prompts/v2.8-orchestration/phase-0-cycle-frame.md` §"LOC
  envelope" + §"Cycle-discipline carries" + §"Monitor target" —
  P0 cycle frame.
- `docs/adr/ADR-18-mvp-surface-freeze.md` §"Amendments" 2026-05-18
  v2.4 P0 Amendment D — v10 P5 entry-gate split (v10.1-mode vs
  v10.3-mode).
- `docs/adr/ADR-18-mvp-surface-freeze.md` Amendment A (3-bucket
  LOC) — feature-cycle classification rationale for ~600 LOC
  Path-D landing.
- v2.7 P1-prep PR #202 (`5afd5da`) — most recent P1-prep PM-mint
  precedent (single-doc prompt landing).
- v2.4 P0 PR #179 (`b35e982`) — Amendment D origin + #177 close.
