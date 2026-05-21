# v2.7 P1 — Seed v2.6-G step (2) timeout-tighten: `TIMEOUT_SECONDS = 25.0` → `30.0`

> Minted ahead-of-fire 2026-05-21 (mirrors v2.4 PR #182 + v2.5.1
> PR #188 + v2.6 PR #195 + PR #197 precedent — work-phase prompt minted
> in a PM PR separate from the P0 cycle-frame PR).
>
> Cycle type **FEATURE** (recorded at P0 PR #200 `4902cca` per
> `docs/v2.7-task-plan.md` §"Operator decisions recorded at P0 fire"
> #1). Soft LOC ≤ 1500 / BLOCK at 1.5× = 2250 vs cycle-tip
> (`4902cca440b33c14fddd9357116923ae5fe1fa4b`).
>
> **Single work phase this cycle.** Per `docs/v2.7-task-plan.md` §"P1/P2
> fire-order": v2.7 = P0 (frame) + P1 (this) + P2 (ship-gate). Seed
> v2.6-C Path-D P5 defers to v2.8 (5th-consecutive); Seed v2.6-G step
> (3) env-split CARRIES independently to v2.8+ (J2 audit default given
> cap = 30 s; prod-vs-eval divergence only +5 s does not justify
> env-split ops complexity).
>
> **First FROZEN-surface lever ever wired in any v1.x/v2.x cycle.**
> The J2-audit framing treats `src/stream_manager/cli_governance.py:49`
> `TIMEOUT_SECONDS` as ADR-18-aware: the symbol's existence and
> semantics remain FROZEN under Rule 1; the value is the lever the
> audit was specifically designed to inform. Lever ledger BUMP **2 →
> 3** (production-bucket canonical) at v2.7 P1 merge.
>
> Comparison anchor: `docs/v2.7-next-steps.md` §"Fire-order" row 2 +
> §"Seed v2.6-G". Compare-back row marker `[ ] Seed v2.6-G P1 — FIRE
> (v2.7 P1 PR #___)` updated on merge.

## Branch + base

- Base: `main` after v2.7 P0 (PR #200 `4902cca`) + v2.7 SHA backfill
  (this PR's predecessor, post-merge) + this prompt-mint PR merged.
- PR target: `main`.
- Branch: `feat/v2.7-p1-cli-timeout-tighten`.
- ABORT if v2.7 P0 not merged at HEAD or HEAD has drifted from v2.7
  P0 base lineage.

## Pre-flight

```
git fetch origin
git log --oneline origin/main -10
```

Expected top-of-main lineage includes `4902cca` (v2.7 P0) reachable.
If divergent, STOP.

Memory pre-flight at P1 — light re-verify (P0 already stamped 6
load-bearing memories FRESH in `docs/v2.7-task-plan.md` §"Memory pre-
flight stamp"). Re-confirm at P1 PR body:

- `project_v26_cycle_close.md` — Sonnet n=192 p99 = 25.048 s (J2
  audit primary input); cap = 30 s headroom = +4.952 s above measured
  Sonnet p99.
- `feedback_cli_over_sdk.md` — `claude -p` subprocess path unchanged;
  the constant edit binds the production-path timeout for live CLI
  invocations.
- `feedback_alignment_eval_stability_window.md` — n=6 mandate
  unchanged; v2.7 P2 entry condition prior_sonnet = 0.9412 ≥ 0.85
  → default `--runs 3` applies unless escape-hatches fire.
- `feedback_certportal_dev_firewall.md` + `feedback_no_self_monitor.md`
  — unchanged scope; no certPortal coupling added.

Stale memories: update in a separate pre-P1 PR or at top of P1 PR
per Amendment B precedent.

## Context

Per `docs/seed-v2.6-g-step2-timeout-tighten-audit.md` §"Recommendation"
the measurement-protocol three-step plan landed step (1) at v2.6 P1
(PR #196 `7220b33` — wall-clock instrumentation in
`tools/alignment_eval.py`, ledger BUMP 1 → 2). Step (2) cap-tighten
is now evidence-ready:

| Source                                                                   | Sonnet n   | p50      | p95      | p99      | max      |
|--------------------------------------------------------------------------|------------|----------|----------|----------|----------|
| `reports/alignment-eval-20260520T205842Z.{md,json}` (v2.6 P2 full corpus) | 192        | 16.140 s | 25.039 s | 25.048 s | 25.063 s |
| `reports/seed-v2.5-a/alignment-eval-20260520T172054Z.{md,json}` (row-10) | 6          | 22.891 s | 24.613 s | 24.960 s | 25.047 s |

Current cap `TIMEOUT_SECONDS = 25.0` sits 48 ms *below* measured
Sonnet p99 — approximately 1 in 100 escalation calls exits via the
timeout-degrade path. The J2 audit recommends **primary cap = 30 s**
(operator-confirmed at v2.7 P0): clears Sonnet n=192 p99 with ~5 s
(~20%) headroom; closes Seed v2.6-A-T mechanically (5.04 s margin
above row-10 single-row p99 24.960 s — well above 2 s close
threshold); substantial false-timeout-NONE reduction expected; eval-
runtime worst-case +16 min absorbable; production-path worst-case
user wait moves 25 s → 30 s only on the rare tail (`degrade_count
= 0` across all post-v2.4 soaks).

Seed v2.6-G step (3) env-split CARRIES independently to v2.8+ per
v2.7 P0 §"Operator decisions" #5. Step (3) is NOT in this phase's
scope.

Seed v2.6-A n=12 re-measure of `frog7-wirecli-module-10` fires at
v2.7 P2 ship-gate (S6.5) under the new 30 s cap per
`docs/seed-v2.6-a-row10-remeasure-protocol.md`; row-10 verdict
disposition (golden-update vs DIP-watch vs verdict-diversity vs
timeout-escalate) is recorded at v2.7 P2 S6.5, NOT this PR.

## ⚠️ CRITICAL: Do-not-touch guard

ADR-18 surface-freeze applies. P1 MUST touch ONLY:

- `src/stream_manager/cli_governance.py:49` — single value edit
  `TIMEOUT_SECONDS = 25.0` → `TIMEOUT_SECONDS = 30.0`. Symbol name,
  type, module location, downstream consumers (lines 257, 322, 350)
  UNCHANGED. The `log.warning(..., %.1fs, TIMEOUT_SECONDS)` format on
  line 350 auto-rewrites to "30.0s" via the existing format spec —
  no message-string edit.
- `src/stream_manager/latency_budgets.py:11-15` — comment cite of
  the source value (`TIMEOUT_SECONDS (25.0)` → `TIMEOUT_SECONDS
  (30.0)`) + recomputed constant
  `BRIDGE_FALLBACK_LATENCY_BUDGET_MS = 35_000` → `45_000`
  (`math.ceil(30.0 * 1.4 / 5.0) * 5_000 = 45_000`). The constant is
  derived from the cap per the file's docstring; updating the
  source value without re-deriving the budget would FAIL
  `tests/test_latency_budgets_invariant.py`.
- `tests/test_cli_governance.py:95` — `assert kwargs["timeout"] ==
  25.0` → `30.0`. The literal is the contract-level assertion that
  `CliGovernor` passes the FROZEN cap to `subprocess.run`; updating
  to the new value preserves the assertion's intent (cap forwarded
  verbatim).
- `tests/test_alignment_eval_timing.py:52-54` —
  `test_timeout_count_threshold` data + comment. Make the test cap-
  agnostic by importing `cli_governance.TIMEOUT_SECONDS` and
  parameterising the values; see §"Scope" deliverable 3 below.
- `docs/v2.7-task-plan.md` §"PHASE P1" — append ledger row noting
  actual LOC delta on merge.

NO edits to other `src/` modules, `model_router.py`, FROZEN bus
envelope schema, `_ALLOW_PHASE_ORDER`, `_L2_L3_TRIGGER` corpus,
`_last_phase_timings_ms` keys, governance HITL surfaces, or any
other tooling. NO deletions; NO renames. **Specifically do NOT
touch:**

- `src/stream_manager/wirecli.py:64` `DEFAULT_TIMEOUT_SECONDS = 25.0`
  — separate symbol bound to the wirecli adapter, NOT the governance
  CLI cap; scope-creep risk. The J2 audit targets `cli_governance.
  TIMEOUT_SECONDS` exclusively.
- `src/stream_manager/cli_pool.py:61` `RESPONSE_TIMEOUT_S = 25.0`
  — internal pool-worker response timeout, NOT the governance CLI
  cap. Scope-creep risk.
- `src/stream_manager/learn_categorizer.py:70` `TIMEOUT_SECONDS =
  30.0` — already at 30 s; learn-mode categoriser is a separate
  subsystem on a separate cap. Coincidence, not coupling.

Pre-flight grep:

```
# Via project Grep tool (ripgrep):
pattern: 'TIMEOUT_SECONDS|25\.0'
path: src/ tests/ tools/ dashboard/
```

Before P1 edits: hits in `src/stream_manager/cli_governance.py:49,257,322,350`,
`src/stream_manager/latency_budgets.py:12,13`,
`src/stream_manager/wirecli.py:64,114`,
`src/stream_manager/cli_pool.py:61`,
`src/stream_manager/learn_categorizer.py:70,199,293`,
`tests/test_cli_governance.py:95`,
`tests/test_alignment_eval_timing.py:53,54`,
`tests/test_api_timeout_invariant.py:14,64`,
`tests/test_latency_budgets_invariant.py:7,12`.

After P1 edits: the `cli_governance.py` 25.0 literal at line 49 is
replaced by 30.0; the `latency_budgets.py` comment + constant track
the new value; `test_cli_governance.py:95` reads 30.0; the
`test_alignment_eval_timing.py:52-54` block is cap-agnostic
(`TIMEOUT_SECONDS` imported). All other hits unchanged (wirecli,
cli_pool, learn_categorizer, test_api_timeout_invariant,
test_latency_budgets_invariant — the latter two import
`TIMEOUT_SECONDS` and follow the constant automatically).

## Scope

### Deliverables

1. **`cli_governance.py:49` constant value edit.**

   ```python
   # before
   TIMEOUT_SECONDS = 25.0

   # after
   TIMEOUT_SECONDS = 30.0
   ```

   No surrounding-line touch. No type annotation, no docstring on the
   constant, no comment line added — the J2 audit
   (`docs/seed-v2.6-g-step2-timeout-tighten-audit.md`) is the
   provenance record; embedding rationale in the source as a comment
   duplicates the audit and rots independently.

2. **`latency_budgets.py:11-15` comment + constant re-derivation.**

   ```python
   # before
   # Bridge forward latency must stay below this even when the CLI
   # governance API times out. Value = cli_governance.TIMEOUT_SECONDS
   # (25.0) * 1.4 rounded up to the nearest 5_000 ms, giving headroom
   # for the timeout + fallback path + downstream forward step.
   BRIDGE_FALLBACK_LATENCY_BUDGET_MS = 35_000

   # after
   # Bridge forward latency must stay below this even when the CLI
   # governance API times out. Value = cli_governance.TIMEOUT_SECONDS
   # (30.0) * 1.4 rounded up to the nearest 5_000 ms, giving headroom
   # for the timeout + fallback path + downstream forward step.
   BRIDGE_FALLBACK_LATENCY_BUDGET_MS = 45_000
   ```

   Re-derivation: `math.ceil(30.0 * 1.4 / 5.0) * 5_000 = ceil(8.4) *
   5_000 = 9 * 5_000 = 45_000`. The drift-guard
   `tests/test_latency_budgets_invariant.py` recomputes the same
   formula at test-time and asserts equality — it auto-validates the
   new constant.

3. **`tests/test_alignment_eval_timing.py:52-54` cap-agnostic.**

   ```python
   # before
   def test_timeout_count_threshold():
       # TIMEOUT_SECONDS=25.0 -> threshold >=24.5; 24.6 + 25.0 hit.
       assert _timeout_count([1.0, 24.0, 24.6, 25.0]) == 2
       assert _timeout_count([]) == 0

   # after
   def test_timeout_count_threshold():
       # threshold = TIMEOUT_SECONDS - 0.5 (subprocess teardown slack).
       from stream_manager.cli_governance import TIMEOUT_SECONDS as _CAP
       assert _timeout_count(
           [1.0, _CAP - 1.0, _CAP - 0.4, _CAP]) == 2
       assert _timeout_count([]) == 0
   ```

   Cap-agnostic shape pins the test to the helper's *contract*
   (threshold = cap − 0.5) rather than a hardcoded numeric, which
   re-creates the v2.6 P1 mint-time rationale that the threshold
   should not be hard-coded. Future cap changes (e.g. v2.8 tightening
   back toward 28 s) no longer require a test-data edit.

4. **`tests/test_cli_governance.py:95` literal update.**

   ```python
   # before
   assert kwargs["timeout"] == 25.0

   # after
   assert kwargs["timeout"] == 30.0
   ```

   The assertion is contract-level: `CliGovernor` forwards the
   FROZEN cap verbatim to `subprocess.run(..., timeout=...)`.
   Cap-agnostic (`from stream_manager.cli_governance import
   TIMEOUT_SECONDS as _CAP; assert kwargs["timeout"] == _CAP`) is
   acceptable if the operator prefers; the literal update is the
   default per v2.6 P2 ship-gate stance ("assertion is the
   contract-level wire — pinning to the live constant blurs which
   side of the seam is under test"). Literal default per this
   prompt.

5. **`docs/v2.7-task-plan.md` §"PHASE P1" ledger row.**

   Append `LANDED PR #___, +N LOC src / +M LOC tests / +K LOC docs`
   on merge. Recorded in the merge commit by the operator (or this
   prompt's final stamp at fire).

### LOC budget

Expected production-bucket delta (`src/` + `tests/`):

| File                                              | Lines     | Bucket   |
|---------------------------------------------------|-----------|----------|
| `src/stream_manager/cli_governance.py`            | +1 / −1   | src      |
| `src/stream_manager/latency_budgets.py`           | +2 / −2   | src      |
| `tests/test_cli_governance.py`                    | +1 / −1   | tests    |
| `tests/test_alignment_eval_timing.py`             | +4 / −3   | tests    |

**Net production-bucket add: ~8 LOC.** Well under the J2-audit
estimate of ≤ 20 LOC `src/` change cited in `docs/v2.7-task-plan.md`
§P1 scope, and well under the v2.6 P1 ~80 LOC instrumentation
phase. **Strict cap: ≤ 50 LOC production-bucket net add.** If draft
exceeds 50 LOC, the change has expanded beyond a single-value
lever-wire and the operator must justify the overshoot in the P1 PR
body OR split into P1a.

Soft ≤ 1500 cycle LOC binding from `docs/v2.7-task-plan.md`
§"Operator decisions" #1 means P1 + P2 combined must stay under
1500; P2 is docs-only ship-gate so headroom is ample. BLOCK at 2250
only matters if P1 wildly overshoots.

## DOD

### Step (2) mandatory

- [ ] `src/stream_manager/cli_governance.py:49` reads
      `TIMEOUT_SECONDS = 30.0` (line position unchanged).
- [ ] `src/stream_manager/latency_budgets.py` comment cites the new
      source value (`30.0`) and constant
      `BRIDGE_FALLBACK_LATENCY_BUDGET_MS = 45_000`.
- [ ] `tests/test_cli_governance.py:95` reads `30.0` literal.
- [ ] `tests/test_alignment_eval_timing.py:test_timeout_count_threshold`
      imports `TIMEOUT_SECONDS` and uses cap-relative data.
- [ ] `pytest tests/test_cli_governance.py
      tests/test_alignment_eval_timing.py
      tests/test_api_timeout_invariant.py
      tests/test_latency_budgets_invariant.py` green.
- [ ] Full pytest suite green (no other test exercises the constant
      value; any unexpected failure surfaces a hidden coupling and
      blocks merge).
- [ ] No FROZEN-surface touch beyond the single value edit at
      `cli_governance.py:49`. `governance.py`, `model_router.py`,
      `message_bus.py`, bus envelope schema, `_ALLOW_PHASE_ORDER`,
      `_L2_L3_TRIGGER` corpus — all untouched.
- [ ] No `wirecli.py` / `cli_pool.py` / `learn_categorizer.py` touch
      (scope-creep guards from §"Do-not-touch").
- [ ] `docs/v2.7-task-plan.md` §"PHASE P1" ledger row appended with
      final LOC delta + PR #.

### Cycle-discipline

- [ ] LOC budget: production-bucket net add ≤ 50 strict cap
      (expected ~8 LOC).
- [ ] Cycle-tip LOC measurement at merge:
      ```
      git diff 4902cca440b33c14fddd9357116923ae5fe1fa4b..HEAD --stat -- src tests tools dashboard
      ```
      Append result in P1 PR body.
- [ ] Predecessor-tag narrative diff `c3a964c..HEAD` recorded
      alongside (does NOT gate; cycle-impact context only).
- [ ] WIRED_LEVER_LEDGER posture: P1 wires +1 production
      (Seed v2.6-G step (2) `TIMEOUT_SECONDS` cap-tighten in
      `src/`; **first FROZEN-surface lever ever wired in any
      v1.x/v2.x cycle**). Target end posture entering P2: **3
      production / 0 soak** (v2.3 Seed 6 JsonlTailWorker wire + v2.6
      Seed v2.5-G step (1) wire unchanged + this Seed v2.6-G step
      (2) wire NEW).
- [ ] Cross-PR seam review: value-edit is single-writer
      (`cli_governance.py`) → multi-reader (consumers at lines 257,
      322, 350 in same module + `latency_budgets.py` derived
      constant + import-time consumers in tests). No new bus
      envelope, no new HITL trigger, no new dashboard surface. Seam
      check trivial.
- [ ] Sub-cycle close-out diff guard per
      `feedback_subagent_stale_mental_model.md`:
      ```
      git --no-pager diff origin/main..HEAD -- \
        src/stream_manager/cli_governance.py \
        src/stream_manager/latency_budgets.py \
        tests/test_cli_governance.py \
        tests/test_alignment_eval_timing.py
      ```
      Confirm only the four files listed are touched + each diff is
      the surgical hunk described in §"Scope" deliverables 1–4.
- [ ] Single PR against `main` (`feat(v2.7-p1):` conventional
      commits prefix).
- [ ] Alignment-eval `--report-only` exit 0 + `--ci-gate` exit 0
      against existing golden set (smoke; no regression; existing
      pass semantics unchanged. Re-fire under new cap is the v2.7
      P2 ship-gate's job, not this PR's).

### ADR-18 surface-classification

- [ ] PR body documents the J2-audit framing: the value-change at
      `cli_governance.py:49` is ADR-18-aware. The FROZEN
      classification covers the symbol's existence and semantics;
      the value is the lever the J2 audit was specifically designed
      to inform. No new amendment required per v2.7 P0 §"Operator
      decisions" #4 + skeleton §"ADR-18 reference block".
- [ ] PR body cites: J2 audit
      (`docs/seed-v2.6-g-step2-timeout-tighten-audit.md`),
      v2.6 P1 instrumentation evidence
      (`reports/alignment-eval-20260520T205842Z.json`,
      Sonnet n=192 p99 = 25.048 s), and Seed v2.6-A-T close-out
      path (5.04 s margin above row-10 single-row p99 24.960 s;
      mechanical close-vote at v2.7 P2 S6.6).

### Memory + docs

- [ ] No new memory minted at P1 (P0 pre-flight stamps 6 FRESH;
      P1 may surface new findings; recordable at P2 ship-gate
      close memory `project_v27_cycle_close.md`).
- [ ] No new FR row in `REQUIREMENTS.md` (timeout-cap value is
      internal infrastructure tuning; not a product surface
      contract).
- [ ] `docs/v2.7-next-steps.md` §"Fire-order" row 2 marker
      `[ ] phase-1-cli-timeout-tighten.md ... FIRE at v2.7 P1` →
      `✅ LANDED PR #___ (`<merge-SHA>`)` on merge. §"Seed v2.6-G"
      compare-back row marker also updated.

## Cross-refs

- `docs/seed-v2.6-g-step2-timeout-tighten-audit.md` — J2 evidence
  audit (this cycle); cap = 30 s primary recommendation source;
  structural template for the operator-decision block already
  resolved at v2.7 P0.
- `docs/seed-v2.4-g-cli-timeout-audit.md` — predecessor J2 (v2.5
  P0); recommended band 30–45 s + measurement-protocol stance.
- `docs/seed-v2.5-a-row10-diagnosis.md` §"Latency boundary analysis"
  — Seed v2.6-A-T close-criterion source (new cap ≥ row-10 p99 +
  2 s; row-10 p99 = 24.960 s → close threshold ≥ 26.960 s; 30 s
  cap clears with 5.04 s margin).
- `docs/seed-v2.6-a-row10-remeasure-protocol.md` — J3 protocol;
  row-10 n=12 re-measure fires at v2.7 P2 S6.5 under the new cap
  landed by this PR.
- `docs/v2.7-task-plan.md` §"PHASE P1" — ledger destination + LOC
  budget anchor.
- `docs/v2.7-next-steps.md` §"Seed v2.6-G" — compare-back marker.
- `src/stream_manager/cli_governance.py:49` — value-edit site;
  FROZEN under ADR-18 Rule 1 (symbol existence + semantics); value
  is the lever the J2 audit was designed to inform.
- `src/stream_manager/cli_governance.py:257,322,350` — downstream
  consumers (`worker.send(..., timeout=TIMEOUT_SECONDS)`,
  `subprocess.run(..., timeout=TIMEOUT_SECONDS)`, degrade-on-
  timeout warning `log.warning("cli governance timeout (>%.1fs);
  degrading", TIMEOUT_SECONDS)`). All auto-follow the constant
  edit; the warning-message format spec auto-rewrites the rendered
  literal "25.0s" → "30.0s".
- `src/stream_manager/latency_budgets.py` — derived constant +
  drift-guard source.
- `tests/test_latency_budgets_invariant.py` — re-derives the
  formula at test-time; validates the new pair (30.0, 45_000).
- `tests/test_api_timeout_invariant.py` — imports `TIMEOUT_SECONDS`;
  auto-follows the constant. No edit required.
- `tools/alignment_eval.py` — per-run timing surface from v2.6 P1
  (PR #196 `7220b33`); `_timeout_count` helper reads
  `cli_governance.TIMEOUT_SECONDS` via the import-order spec
  enforced at v2.6 P1 §6. Auto-follows the new cap; no edit
  required this PR.
- ADR-18 Rule 1 (surface freeze) — `TIMEOUT_SECONDS` symbol's
  existence + type + downstream consumers unchanged; only the
  numeric value is re-classified per the J2-audit framing.
- ADR-18 Rule 3 (consolidation gate) — not in force this cycle
  (feature classification per P0 PR #200).
- ADR-18 Amendment A (3-bucket measurement) — `src/` constant edit
  qualifies as production-bucket lever-wire on its own.
- ADR-18 Amendment C (cycle-tip anchor) —
  `4902cca440b33c14fddd9357116923ae5fe1fa4b` binds P1 LOC
  measurement.
- ADR-18 Amendment B (memory pre-flight) — P0 stamped; P1 light
  re-verify above.
- `feedback_cli_over_sdk.md` — live `claude -p` subprocess path
  unchanged; the new cap binds the same path at the new value.
- `feedback_alignment_eval_stability_window.md` — n=6 mandate
  unchanged; the new cap is expected to reduce unstable_sonnet
  rows substantially (J2 audit §"Boundary analysis").
- `feedback_cassette_must_cover_new_envelopes.md` — N/A this PR
  (no new bus envelope).
- Precedent ahead-of-fire prompt mints: v2.4 PR #182 (P2 mint);
  v2.5.1 PR #188 (P1 corrective mint); v2.6 PR #195 (P1
  instrumentation mint); v2.6 PR #197 (P2 mint).
- v2.7 P0 PR #200 (`4902cca`).
- v2.6 P1 commit `7220b33` (PR #196) — step (1) wall-clock
  instrumentation source PR; lever ledger BUMP 1 → 2; this PR
  closes step (2) and bumps 2 → 3.

Report back when P1 PR opens with:

1. PR URL.
2. Diff stat against cycle-tip:
   `git diff 4902cca440b33c14fddd9357116923ae5fe1fa4b..HEAD --stat -- src tests tools dashboard`.
3. Predecessor-tag narrative diff stat
   `git diff c3a964c..HEAD --stat -- src tests tools dashboard`
   (cycle-impact context only; does NOT gate).
4. Sub-cycle close-out diff guard output (must be additive on the
   four files listed in §"Cycle-discipline" sub-cycle guard,
   nothing else).
5. `pytest tests/test_cli_governance.py
   tests/test_alignment_eval_timing.py
   tests/test_api_timeout_invariant.py
   tests/test_latency_budgets_invariant.py` green output paste.
6. Full pytest suite green (paste tail of `pytest -q` output).
7. ADR-18 surface-classification note in PR body (J2-audit framing
   citation; cite v2.7 P0 §"Operator decisions" #4 + this prompt
   §"ADR-18 surface-classification" DoD).
8. J2 audit + v2.6 P1 instrumentation evidence + Seed v2.6-A-T
   close-out-path citations in PR body (per §"ADR-18 surface-
   classification" DoD).
9. WIRED_LEVER_LEDGER posture confirmation: entering 2 production
   / 0 soak; this PR wires +1 production (Seed v2.6-G step (2)
   `TIMEOUT_SECONDS` cap); target end-P1 posture **3 production
   / 0 soak** (first FROZEN-surface lever ever wired).
10. Confirmation that Seed v2.6-G step (3) env-split was NOT
    bundled in this PR (operator pick at v2.7 P0 §"Operator
    decisions" #5 = CARRY independently to v2.8+).
