# ADR-18 Amendment D — DRAFT (not yet landed)

> **Status: DRAFT.** Lands in `docs/adr/ADR-18-mvp-surface-freeze.md`
> §"Amendments" at v2.4 P0 PR open. This file is a staging document
> for review; the canonical home is the ADR-18 §"Amendments" section.
> Delete this file once the amendment lands in ADR-18.
>
> **Authority:** Issue #177 — v10 P5 entry-gate deadlock under v10.1
> deterministic policy. Filed 2026-05-18.
>
> **Precedent format:** Amendments A / B / C (ADR-18 §"Amendments"
> L342–L513). Body text follows the same structure: **Problem.**,
> **Amendment.**, **Reason.**, **Self-application.**, **Acceptance**.

---

## 2026-05-18 — v2.4 P0 Amendment D: v10 P5 entry-gate split (v10.1-mode vs v10.3-mode) (closes #177)

**Problem.** The v10 P5 phase prompt
(`docs/prompts/v10-orchestration/phase-5-shadow-stop-conditions.md`
L8) ABORTs if no manifest with `is_ready_for_shadow() == True`
exists. `is_ready_for_shadow()` is defined in `rl/bandit.py` L99-101
as `(self._total >= PROMOTION_N_FLOOR
AND self.best_arm_posterior_ci() <= PROMOTION_CI_CAP)`, where
`PROMOTION_N_FLOOR = 200` and `PROMOTION_CI_CAP = 0.10`
(`rl/bandit.py` L23-24). Under v10.1's deterministic production policy
(threshold fixed at baseline_thr=0.70), the trainer's offline-replay
loop in `rl/cli/train.py` L120-123 only conjugate-updates the
baseline arm — off-baseline arms receive zero on-support data and
their posterior CI stays at the warm-start floor (~0.43 for
`Beta(10,10)`). The 0.10 CI cap is therefore unreachable on any
non-baseline arm regardless of episode count. Even if the baseline
arm itself clears both conditions, the train CLI's exit-10 (PROMOTE)
path requires `best_arm != baseline_arm` (`train.py:221`), so the P5
entry signal remains unreachable.

This creates a chicken-and-egg deadlock: P5 entry requires off-arm
CI shrinkage → off-arm CI requires on-support updates → on-support
updates require stochastic propensities → stochastic propensities
arrive with v10.3 writeback → v10.3 writeback requires P5 ALL PASS.
v10 RL track is pre-DORMANT deadlocked at the P5 entry, with no
designed escape path. Live train evidence (2026-05-18,
`rl_proposals/v10p4-live-20260518.json`): n_actual=79/200,
best_arm_ci_width_95=0.119/0.10, ready=False.

**Amendment.** Split the v10 P5 entry gate into two modes:

| Mode | Active when | Gate condition | P5 outcome |
|---|---|---|---|
| **v10.1-mode** | v10.x track stages 0-2 (deterministic production policy) | baseline arm `_total >= 200` effective updates AND `posterior_ci_width(baseline_arm) <= 0.10` | P5 shadow harness fires as **infrastructure validation**: candidate = baseline (sanity), recorder writes a baseline-vs-baseline shadow run, harness exercises end-to-end without claiming promotion |
| **v10.3-mode** | v10.3 stochastic propensity writeback active | original gate: non-baseline `best_arm` clears `_total >= 200 AND best_arm_posterior_ci() <= 0.10` | P5 shadow run measures real candidate-vs-production divergence; ship-criteria checker may exit 0 (ALL PASS) and open v10.3 writeback gate |

`rl/bandit.py` adds a sibling method `is_ready_for_shadow_v10_1()`
returning the v10.1-mode condition. `is_ready_for_shadow()` retains
its current semantics (v10.3-mode). P5 phase prompt re-minted at
v2.4 P0 with a header section disambiguating which mode is being
exercised in the current cycle.

The `proposals.promotion_gate` JSON envelope grows two additive
keys: `ready_v10_1` (v10.1-mode bool) and `mode` (string literal
`"v10.1"` or `"v10.3"` indicating which mode is active per the
caller's `BRIDGE_RL_MODE` env or CLI flag). The existing `ready`
key (v10.3-mode) is preserved verbatim — additive extension per
ADR-18 Rule 1 §"Metadata-only extensions to FROZEN bus envelope
schemas".

The v10.1-mode shadow harness MUST record its mode in
`shadow_episodes.soak_run_id` (string suffix `--mode=v10.1`) so
post-hoc analysis can distinguish infrastructure-validation runs
from real-data shadow runs. v10.3 ship-criteria checker
(`rl.cli.check_criteria`) ignores rows with `--mode=v10.1` suffix
when computing the 6 pre-registered ship criteria — those rows are
infrastructure-only and cannot count toward writeback promotion.

**Scope.** v10 EXPERIMENTAL track per ADR-18 row table L71. No
FROZEN surface touched. `bandit.py`, `train.py`, `manifest.py`,
phase-5 prompt — all are v10-track files in the EXPERIMENTAL
classification.

**Reason.** The v10 design doc §10 specifies 6 pre-registered ship
criteria with the implicit assumption that stochastic propensities
are available when criteria are evaluated. v10.1's deterministic
policy violates that assumption silently — the gate compiles, runs,
and returns False forever. Amendment D acknowledges the assumption
gap explicitly and provides a documented v10.1-mode escape that:

1. Lets the P5 shadow harness ship and be exercised end-to-end
   without waiting on v10.3.
2. Reserves the original (v10.3-mode) ship criteria verbatim,
   preserving the pre-registration discipline of §10.
3. Surfaces the mode boundary in the data (via `soak_run_id`
   suffix) so v10.3 writeback promotion cannot be accidentally
   triggered by infrastructure-validation runs.

Without Amendment D, the v10 track either (a) stalls indefinitely
at P5 entry, (b) tempts ad-hoc threshold relaxation (p-hacking
against pre-registration), or (c) blocks until v10.3 stochastic
writeback ships first — but v10.3 requires P5 ALL PASS, which
loops to (a). Amendment D is the minimum-surface break of the
loop that preserves all other invariants.

**Self-application.** This amendment self-applies at v2.4 P0 — the
P0 PR carries the amendment text body, and Path-D synthetic-
fixture P5 implementation (Seed v2.4-C) fires under v10.1-mode IF
v2.4 = feature cycle.

**Acceptance (#177).**

- [ ] Amendment text in `docs/adr/ADR-18-mvp-surface-freeze.md`
      §"Amendments" (this entry, copied verbatim from this draft
      and re-located).
- [ ] `docs/adr/ADR-18-amendment-d-draft.md` (this staging file)
      deleted in the same PR that relocates the amendment text
      into ADR-18 §"Amendments" — staging artefact must not
      outlive the relocation, or it rots into a stale duplicate.
- [ ] Verify `shadow_episodes` schema exposes the `soak_run_id`
      column (currently designed in `phase-5-shadow-stop-
      conditions.md` L71 as `soak_run_id TEXT NOT NULL`) BEFORE
      Path-D synthetic-fixture P5 implementation fires. If the
      schema lands without that column, Amendment D's
      `--mode=v10.1` suffix mechanism has no carrier.
- [ ] `rl/bandit.py` adds `is_ready_for_shadow_v10_1()` method;
      `is_ready_for_shadow()` semantics unchanged.
- [ ] `rl/cli/train.py` `promotion_gate` envelope adds
      `ready_v10_1` + `mode` keys; existing `ready` preserved.
- [ ] Phase-5 prompt re-minted with mode-disambiguation header
      OR new `phase-1-shadow-synthetic.md` prompt minted for v2.4
      (operator decides at P0).
- [ ] Path-D shadow harness records `soak_run_id` with
      `--mode=v10.1` suffix for v10.1-mode runs.
- [ ] `rl.cli.check_criteria` ignores `--mode=v10.1` rows when
      computing ship criteria.
- [ ] Issue #177 closed with link to landing PR.
- [ ] `project_v10_p5_gate_deadlock.md` memory updated to record
      Amendment D as the resolution (status moves from OPEN to
      RESOLVED).
- [ ] `docs/v10-rl-design.md` §10 footnote appended cross-
      referencing Amendment D (one-line additive doc edit).

---

## Implementation notes (not part of amendment body — staging only)

### Why a sibling method, not a flag

Adding `is_ready_for_shadow_v10_1()` as a sibling method preserves
the existing `is_ready_for_shadow()` semantics byte-identical.
Alternative: a `mode` kwarg on the original method. Rejected because
ADR-18 Rule 1 prefers additive surfaces over modified surfaces for
FROZEN-adjacent code, and bandit.py is borderline (v10 track is
EXPERIMENTAL but the bandit module is internally stable).

### Why mode in `soak_run_id` not a separate column

`shadow_episodes` schema is FROZEN at v10 P5 design L57-75. Adding
a `mode` column is a non-additive schema change. Embedding mode in
the existing `soak_run_id` string (which is opaque to consumers
except for grouping) is additive at the schema level. Filter
predicates in `check_criteria` parse the suffix.

### Why infrastructure-validation runs are non-promoting

v10.1-mode P5 runs candidate==baseline, so by construction
`agree=1` for every shadow row and reward divergence ≈ 0. Allowing
these runs to count toward §10's "Shadow reward improvement ≥ 0.02
over 3 consecutive shadows" would automatically fail the criterion
on every infrastructure run — which is a false negative on the
underlying production policy, not the candidate. Ignoring v10.1-
mode rows entirely is cleaner than special-casing the criterion.

### Open questions deferred to v10.3 phase prompt

- Should v10.3 retroactively re-evaluate v10.1-mode shadow runs as
  baseline-stability data? (Deferred — re-evaluate at v10.3 design.)
- Does Amendment D's `mode` field bind for v10.2 if v10.2 ever
  ships separately from v10.3? (Deferred — no v10.2 currently
  planned as a separate phase.)
