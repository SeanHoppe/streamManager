# v2.6 P1 — Seed v2.5-G step (1) instrumentation: per-run wall-clock in alignment-eval row runner

> Minted ahead-of-fire 2026-05-20 (mirrors v2.4 PR #182 + v2.5.1
> PR #188 precedent — work-phase prompt minted in a PM PR separate
> from the P0 cycle-frame PR).
>
> Cycle type **FEATURE** (recorded at P0 PR #193 per
> `docs/v2.6-task-plan.md` §"Operator decisions recorded at P0 fire"
> #1). Soft LOC ≤ 1500 / BLOCK at 1.5× = 2250 vs cycle-tip
> (`084137dfc8823ae5eac84755581fc0aeed6342db`).
>
> **Single work phase this cycle.** Per `docs/v2.6-task-plan.md` §"P1/P2
> fire-order": v2.6 = P0 (frame) + P1 (this) + P2 (ship-gate). Seed
> v2.5-C Path-D P5 deferred to v2.7 (3rd consecutive); Seed v2.5-G
> step (2) timeout-tighten defers to v2.7+; step (3) env-split is
> operator-elective at this mint (see §"Optional step (3) env-split"
> below).
>
> Comparison anchor: `docs/v2.6-next-steps.md` §"Fire-order" row 2 +
> §"Seed v2.5-G". Compare-back row marker `[ ] Seed v2.5-G P1 — FIRE
> (v2.6 P1 PR #___)` updated on merge.

## Branch + base

- Base: `main` after v2.6 P0 (PR #193 `084137d`) + v2.6 SHA backfill
  (PR #194, post-merge) + this prompt-mint PR merged.
- PR target: `main`.
- Branch: `feat/v2.6-p1-cli-timeout-instrumentation`.
- ABORT if v2.6 P0 not merged at HEAD or HEAD has drifted from v2.6
  P0 base lineage.

## Pre-flight

```
git fetch origin
git log --oneline origin/main -10
```

Expected top-of-main lineage includes `084137d` (v2.6 P0) reachable.
If divergent, STOP.

Memory pre-flight at P1 — light re-verify (P0 already stamped 6
load-bearing memories FRESH in `docs/v2.6-task-plan.md` §"Memory pre-
flight stamp"). Re-confirm at P1 PR body:

- `feedback_cli_over_sdk.md` — alignment-eval uses real `claude -p`
  subprocess; instrumentation MUST measure that path, not a mock.
- `feedback_alignment_eval_stability_window.md` — n=6 mandate
  trigger conditions; instrumentation MUST cover both n=3 and n=6
  runs without code change.
- `feedback_certportal_dev_firewall.md` + `feedback_no_self_monitor.md`
  — unchanged scope; no certPortal coupling added.

Stale memories: update in a separate pre-P1 PR or at top of P1 PR
per Amendment B precedent.

## Context

Per `docs/seed-v2.4-g-cli-timeout-audit.md` §"Recommendation" the
measurement-protocol stance is:

1. **Instrument first, change second.** Add per-run wall-clock timing
   to the alignment-eval row runner so the next eval reports p50 /
   p95 / p99 per row per model, not just majority verdicts.
2. **Then tighten timeout to a measured band** (DEFERS v2.7+).
3. **Re-frame `TIMEOUT_SECONDS` as configurable, not constant**
   (operator-elective at this P1 mint — see §"Optional step (3)
   env-split" below).

v2.5.1 P1 n=6 re-measure recorded row `frog7-wirecli-module-10` 6/6
Sonnet runs `cli governance timeout (>25.0s); degrading` (100% rate).
This is the strongest single-row evidence yet for the measurement-
protocol stance; closing the eval-path per-run timing gap is the
prerequisite for any `TIMEOUT_SECONDS` point-estimate change at v2.7+.

v2.6 P1 closes only the step (1) gap. The instrumented row runner
re-measures row 10 at v2.6 P2 ship-gate; verdict = content-drift OR
timeout-attributable. That resolves Seed v2.5-A diagnosis in
lockstep at v2.6 P2.

## ⚠️ CRITICAL: Do-not-touch guard

ADR-18 surface-freeze applies. P1 step (1) (mandatory) MUST touch
ONLY:

- `tools/alignment_eval.py` — add per-run wall-clock timing in
  `evaluate_row` + extend `render_report` MD section + extend JSON
  sidecar payload. Existing CLI surface (`--report-only` / `--ci-gate`
  / `--runs` / `--control-model` / `--candidate-model` /
  `--candidate-only-control`) UNCHANGED. Existing report columns +
  summary keys UNCHANGED (new keys additive only).
- `tests/test_alignment_eval_timing.py` (new) — unit test for the
  timing helper + JSON sidecar shape; does NOT exercise the live
  CLI (no `BRIDGE_API_GOV=1` in this test; per-row timing helper is
  pure-Python + monkeypatched governor).
- `docs/v2.6-task-plan.md` §"PHASE P1" — append ledger row noting
  actual LOC delta on merge.

If operator elects step (3) env-split same phase (see §"Optional
step (3) env-split" below), additionally touch:

- `src/stream_manager/cli_governance.py:49` — split single
  `TIMEOUT_SECONDS = 25.0` constant into env-readable resolver that
  reads `BRIDGE_CLI_TIMEOUT_EVAL` (when `BRIDGE_API_GOV` set AND
  alignment-eval marker present) OR `BRIDGE_CLI_TIMEOUT` (otherwise),
  defaulting to **25.0** in both branches. Default-25.0 invariant
  preserves Rule 1 surface-freeze semantics (constant value
  unchanged at default); env override is additive opt-in.
- `tests/test_cli_governance_timeout_env.py` (new) — unit test for
  env-resolver default-25.0 path + override paths.

NO edits to other `src/` modules, `model_router.py`, FROZEN bus
envelope schema, `_ALLOW_PHASE_ORDER`, `_L2_L3_TRIGGER` corpus,
`_last_phase_timings_ms` keys, governance HITL surfaces, or any
other tooling. NO deletions; NO renames.

Pre-flight grep:

```
# Via project Grep tool (ripgrep):
pattern: 'evaluate_row|sonnet_durations|haiku_durations|BRIDGE_CLI_TIMEOUT'
path: src/ tests/ tools/ dashboard/
```

Before P1 edits: hits in `tools/alignment_eval.py:98` (`evaluate_row`
signature) only. After P1 edits (step 1 mandatory only): hits in
`tools/alignment_eval.py` + `tests/test_alignment_eval_timing.py`
and nowhere else. After P1 edits (step 1 + step 3 elective):
additional hits in `src/stream_manager/cli_governance.py` +
`tests/test_cli_governance_timeout_env.py`.

## Scope — step (1) instrumentation (MANDATORY)

### Deliverables

1. **`evaluate_row` per-run wall-clock capture.**

   `tools/alignment_eval.py:98`. Wrap each
   `governor.evaluate(...)` call in `time.monotonic()` deltas (NOT
   wall-clock `time.time()` — eval may straddle clock adjustments
   on the laptop runtime; `monotonic` is the correct choice for
   subprocess wall-clock). Return shape changes:

   ```python
   # before
   def evaluate_row(governor, prompt, model_id, runs) -> list[str]:
       out: list[str] = []
       for _ in range(runs):
           decision = governor.evaluate(content=prompt, model_id=model_id)
           out.append(decision.action if decision is not None else "NONE")
       return out

   # after
   def evaluate_row(governor, prompt, model_id, runs) -> tuple[list[str], list[float]]:
       actions: list[str] = []
       durations_s: list[float] = []
       for _ in range(runs):
           t0 = time.monotonic()
           decision = governor.evaluate(content=prompt, model_id=model_id)
           durations_s.append(round(time.monotonic() - t0, 3))
           actions.append(decision.action if decision is not None else "NONE")
       return actions, durations_s
   ```

   Call sites updated correspondingly (single use in `main()`).

2. **Per-row per-model duration aggregation.**

   In `main()` after each row evaluated, store `durations_s` lists
   on the `results[row_id]` dict alongside existing run-action
   lists. New keys (additive — do NOT rename existing keys):

   ```python
   results[row["id"]] = {
       "sonnet_runs": sonnet_runs,                # existing
       "sonnet_majority": sm,                     # existing
       "sonnet_stable": ss,                       # existing
       "sonnet_durations_s": sonnet_durations_s,  # NEW
       "haiku_runs": haiku_runs,                  # existing
       "haiku_majority": hm,                      # existing
       "haiku_stable": hs,                        # existing
       "haiku_durations_s": haiku_durations_s,    # NEW
       "agree": ...,                              # existing
   }
   ```

3. **Aggregate distribution in `__summary__`.**

   Add p50 / p95 / p99 aggregates over the **flattened** per-model
   duration lists (all rows × all runs) so each eval reports a
   single distribution per model. Helper:

   ```python
   def _percentile(values: list[float], p: float) -> float:
       """Linear-interpolated percentile. Empty list → 0.0."""
       if not values:
           return 0.0
       s = sorted(values)
       k = (len(s) - 1) * p
       lo = int(k)
       hi = min(lo + 1, len(s) - 1)
       return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 3)
   ```

   New `__summary__` keys (additive):

   ```python
   "sonnet_duration_s_p50": _percentile(all_sonnet_durations, 0.50),
   "sonnet_duration_s_p95": _percentile(all_sonnet_durations, 0.95),
   "sonnet_duration_s_p99": _percentile(all_sonnet_durations, 0.99),
   "sonnet_duration_s_max": max(all_sonnet_durations) if all_sonnet_durations else 0.0,
   "sonnet_duration_s_n": len(all_sonnet_durations),
   "haiku_duration_s_p50": ...,
   "haiku_duration_s_p95": ...,
   "haiku_duration_s_p99": ...,
   "haiku_duration_s_max": ...,
   "haiku_duration_s_n": ...,
   ```

   When `--candidate-only-control` is set, haiku duration list is
   empty; aggregates default to 0.0 / n=0 (handler in `_percentile`).

4. **MD report — new §"Per-model wall-clock distribution" section.**

   Appended **after** existing §"Summary" block, **before** existing
   §"Regressing rows" block. Format:

   ```
   ## Per-model wall-clock distribution

   | Model  | n  | p50    | p95    | p99    | max    |
   |--------|----|--------|--------|--------|--------|
   | sonnet | 96 | 4.123s | ...    | ...    | ...    |
   | haiku  | 96 | ...    | ...    | ...    | ...    |
   ```

   When `--candidate-only-control` is set, haiku row reads
   `n=0; (skipped)`.

5. **JSON sidecar — per-row durations + summary percentiles.**

   Both already covered by additive key inclusion in §3 + §2. The
   sidecar `rows` payload now carries `sonnet_durations_s` +
   `haiku_durations_s`; the `summary` payload carries the 10 new
   percentile keys. No structural change to top-level shape.

6. **Per-row timeout-attribution column (NEW).**

   The Seed v2.5-A close-out depends on identifying which `NONE`
   verdicts were timeout-degrade events vs other failure modes. The
   v2.5.1 P1 investigation surfaced this gap directly. Add per-row
   per-model `timeout_count` derived from
   `sum(1 for d in durations_s if d >= TIMEOUT_SECONDS - 0.5)` — a
   conservative timeout-attribution proxy (TIMEOUT_SECONDS is 25.0
   today; the -0.5 s threshold accounts for subprocess teardown
   latency). New keys:

   ```python
   "sonnet_timeout_count": _timeout_count(sonnet_durations_s),
   "haiku_timeout_count": _timeout_count(haiku_durations_s),
   ```

   Threshold sourced from `cli_governance.TIMEOUT_SECONDS` import
   (do NOT hard-code 25.0 in `alignment_eval.py`; that would create
   a silent skew if step (3) env-split lands same phase).

7. **Tests — `tests/test_alignment_eval_timing.py` (new).**

   - `test_evaluate_row_returns_actions_and_durations_lists` —
     monkeypatch `governor.evaluate` to return a sentinel decision
     after a short sleep; assert return tuple shape + len-equality.
   - `test_evaluate_row_handles_none_decision` — monkeypatch to
     return `None`; assert action recorded as `"NONE"` and a
     duration is still captured.
   - `test_percentile_helper_known_distribution` — feed
     `[1.0, 2.0, 3.0, 4.0, 5.0]`; assert p50=3.0, p95=4.8, p99=4.96
     (linear-interp).
   - `test_percentile_empty_list_returns_zero` — `_percentile([],
     0.95) == 0.0`.
   - `test_timeout_count_threshold` — durations
     `[1.0, 24.0, 24.6, 25.0]` with `TIMEOUT_SECONDS=25.0` (threshold
     `>=24.5`); count = 2 (24.6 + 25.0).
   - `test_render_report_includes_wall_clock_section` — feed
     synthetic results dict containing duration lists + summary
     percentile keys; assert MD output contains `## Per-model
     wall-clock distribution` and a sonnet row.

   Tests are **pure unit** — no `BRIDGE_API_GOV` set, no live CLI
   invocation. Per `feedback_cli_over_sdk.md`: the live-CLI behaviour
   is what the harness exercises in production; the unit tests
   exercise the helper logic in isolation. Live behaviour is
   validated implicitly at v2.6 P2 ship-gate when the harness fires
   against the real CLI.

8. **`docs/v2.6-task-plan.md` §"PHASE P1" ledger row.**

   Append `LANDED PR #___, +N LOC tooling / +M LOC tests / docs
   delta 0` on merge. Recorded in the merge commit by the operator
   (or this prompt's final stamp at fire).

### LOC budget

P1 step (1) net add **target ~30 LOC tooling** (per J2 audit
recommendation §"Recommendation" line 219-222) + **~50 LOC tests** =
**~80 LOC total** production-bucket addition.

**Strict cap: ≤ 150 LOC production-bucket net add** (tooling +
tests). If draft exceeds the strict cap, split the test surface to
a P1a sub-phase OR re-scope per ADR-18 Rule 4 (work-phase cap ≤ 3
already at 1 — adding P1a is allowed).

Soft ≤ 1500 cycle LOC binding from `docs/v2.6-task-plan.md`
§"Operator decisions" #1 means P1 + P2 combined must stay under
1500; P2 is docs-only ship-gate so headroom is ample. BLOCK at
2250 only matters if P1 wildly overshoots.

## Optional step (3) env-split (OPERATOR-ELECTIVE AT THIS MINT)

Per `docs/v2.6-task-plan.md` §"Operator decisions" #4:

> Step (3) env-split MAY land same phase as step (1) OR defer to
> v2.7+; operator decides at P1 mint.

**Default disposition (no operator override at this mint): DEFER
step (3) to v2.7+.** Rationale: step (1) instrumentation alone
qualifies as lever-wire under Amendment A 3-bucket production
measurement (~30 LOC `tools/`); bundling step (3) adds
`src/stream_manager/cli_governance.py:49` touch which, while
preserving the default-25.0 invariant, expands the FROZEN-surface
diff and the P1 review burden without measured eval p99 data yet
in hand to justify the urgency.

**If operator elects step (3) FIRE same phase at this mint:**

Append the operator pick + rationale here:

```
- [ ] FIRE step (3) env-split same phase as step (1).
      Operator pick recorded: ___________________ (signature line)
      Rationale: ___________________
```

If selected, the `cli_governance.py:49` deliverable + the
`tests/test_cli_governance_timeout_env.py` test surface from §"Do-
not-touch guard" above become MANDATORY at P1 fire.

`cli_governance.py:49` env-resolver shape:

```python
# before
TIMEOUT_SECONDS = 25.0

# after
def _resolve_timeout_seconds() -> float:
    """Read env override; default 25.0 (invariant per ADR-18 Rule 1)."""
    raw = os.environ.get("BRIDGE_CLI_TIMEOUT_EVAL") if os.environ.get(
        "BRIDGE_ALIGNMENT_EVAL") == "1" else os.environ.get("BRIDGE_CLI_TIMEOUT")
    if raw is None:
        return 25.0
    try:
        v = float(raw)
        if v <= 0:
            return 25.0
        return v
    except ValueError:
        return 25.0

TIMEOUT_SECONDS = _resolve_timeout_seconds()
```

`BRIDGE_ALIGNMENT_EVAL=1` is exported by `tools/alignment_eval.py`
at startup peer to the existing `os.environ["BRIDGE_API_GOV"] = "1"`
line. Both invariants:

- No env vars set → `TIMEOUT_SECONDS = 25.0` (unchanged from
  pre-split).
- `BRIDGE_CLI_TIMEOUT_EVAL=30.0` + `BRIDGE_ALIGNMENT_EVAL=1` →
  eval timeout = 30.0 s.
- `BRIDGE_CLI_TIMEOUT=20.0` (no eval marker) → production timeout =
  20.0 s. Eval path is unaffected (still resolves via
  `BRIDGE_CLI_TIMEOUT_EVAL` branch which would be unset → 25.0).
- Invalid value → fallback 25.0 (do NOT raise; production stays
  safe).

Test surface:

- `test_default_timeout_when_env_unset` — both env vars unset →
  25.0.
- `test_eval_path_reads_eval_override` — `BRIDGE_ALIGNMENT_EVAL=1`
  + `BRIDGE_CLI_TIMEOUT_EVAL=30.0` → 30.0.
- `test_prod_path_reads_prod_override` —
  `BRIDGE_CLI_TIMEOUT=20.0` (no eval marker) → 20.0.
- `test_eval_path_ignores_prod_override_when_eval_marker_set` —
  `BRIDGE_ALIGNMENT_EVAL=1` + `BRIDGE_CLI_TIMEOUT=20.0` (no eval
  override) → 25.0 (default; eval branch wins precedence).
- `test_invalid_env_falls_back_to_25` — `BRIDGE_CLI_TIMEOUT=abc`
  → 25.0.
- `test_negative_or_zero_env_falls_back_to_25` — `=0` / `=-1` →
  25.0.

Step (3) adds ~25 LOC `src/` + ~50 LOC tests = ~75 LOC additional
production-bucket; bundled P1 total ≈ 155 LOC. Still under strict
150 cap **only if** test surface is compact — operator should
verify final diff before merge.

**If step (3) deferred (default):** no `src/` touch this PR. The
prompt persists as the v2.7+ template for step (3) impl when
measured eval p99 data lands at v2.6 P2 ship-gate.

## DOD

### Step (1) mandatory

- [ ] `evaluate_row` returns `tuple[list[str], list[float]]` and
      captures `time.monotonic` deltas per run.
- [ ] `results[row_id]` carries `sonnet_durations_s` +
      `haiku_durations_s` additive lists.
- [ ] `__summary__` carries 10 new percentile / max / n keys
      (sonnet × 5 + haiku × 5).
- [ ] `results[row_id]` carries per-row `sonnet_timeout_count` +
      `haiku_timeout_count` derived from `cli_governance.TIMEOUT_SECONDS`
      (NOT hard-coded 25.0).
- [ ] `_percentile` + `_timeout_count` helpers added with unit
      tests.
- [ ] MD report carries §"Per-model wall-clock distribution"
      section in the documented position (after Summary, before
      Regressing rows).
- [ ] JSON sidecar `rows` payload carries per-row duration lists;
      `summary` payload carries new aggregates.
- [ ] `tests/test_alignment_eval_timing.py` added; full pytest
      suite green.
- [ ] No `--report-only` / `--ci-gate` CLI behaviour changed
      (gate logic untouched; only enriched output).
- [ ] No FROZEN-surface touch (step (1) only).
- [ ] `docs/v2.6-task-plan.md` §"PHASE P1" ledger row appended
      with final LOC delta.

### Step (3) elective (only if operator FIRE same-phase)

- [ ] `_resolve_timeout_seconds` resolver added at
      `src/stream_manager/cli_governance.py`; default-25.0
      invariant preserved.
- [ ] `tools/alignment_eval.py` exports
      `os.environ["BRIDGE_ALIGNMENT_EVAL"] = "1"` peer to
      existing `BRIDGE_API_GOV`.
- [ ] `tests/test_cli_governance_timeout_env.py` added; 6 unit
      tests pass.
- [ ] Default-no-env path returns 25.0 verified at runtime under
      `BRIDGE_API_GOV=1` (manual smoke OR test that imports
      module and reads `TIMEOUT_SECONDS`).
- [ ] ADR-18 surface-freeze annotation appended in P1 PR body:
      explicit operator-authorized step (3) bundle (cite v2.6 P0
      §"Operator decisions" #4 + this prompt §"Optional step (3)
      env-split" operator pick line).

### Cycle-discipline

- [ ] LOC budget: production-bucket net add ≤ 150 strict cap
      (step (1) only ≈ 80; step (1) + step (3) ≈ 155 — flag for
      operator review if step (3) bundled).
- [ ] Cycle-tip LOC measurement at merge:
      ```
      git diff 084137dfc8823ae5eac84755581fc0aeed6342db..HEAD --stat -- src tests tools dashboard
      ```
      Append result in P1 PR body.
- [ ] Predecessor-tag narrative diff `c1e9070..HEAD` recorded
      alongside (does NOT gate; cycle-impact context only).
- [ ] WIRED_LEVER_LEDGER posture: P1 wires +1 production
      (Seed v2.5-G step (1) instrumentation in `tools/`). Target
      end posture entering P2: **2 production / 0 soak** (Seed 6
      JsonlTailWorker wire + Seed v2.5-G step (1) wire NEW).
- [ ] Cross-PR seam review: instrumentation is single-writer
      (alignment_eval) → single-reader (MD/JSON report consumers).
      No new bus envelope, no new HITL trigger, no new dashboard
      surface. Seam check trivial.
- [ ] Sub-cycle close-out diff guard per
      `feedback_subagent_stale_mental_model.md`:
      ```
      git --no-pager diff origin/main..HEAD -- \
        tools/alignment_eval.py \
        src/stream_manager/cli_governance.py
      ```
      Confirm only additive hunks on `alignment_eval.py` (step
      (1) mandatory) + only env-resolver hunks on
      `cli_governance.py` (step (3) elective if FIRE).
- [ ] Single PR against `main` (`feat(eval):` or
      `feat(v2.6-p1):` conventional commits prefix).
- [ ] Alignment-eval `--report-only` exit 0 + `--ci-gate` exit 0
      against existing golden set (no regression; existing pass
      semantics unchanged).

### Memory + docs

- [ ] No new memory minted at P1 (P0 pre-flight stamps 6 FRESH;
      P1 may surface new findings; recordable at P2 ship-gate
      close memory).
- [ ] No new FR row in `REQUIREMENTS.md` (instrumentation is an
      internal eval-tooling enrichment; not a product surface
      contract).
- [ ] `docs/v2.6-next-steps.md` §"Fire-order" row 2 marker
      `[ ] Seed v2.5-G P1` updated to `✅ LANDED PR #___` on
      merge.

## Cross-refs

- `docs/seed-v2.4-g-cli-timeout-audit.md` §"Recommendation" — J2
  evidence audit; measurement-protocol three-step plan; primary
  spec for P1 step (1) shape.
- `docs/v2.5.1-sonnet-floor-investigation.md` §"n=6 re-measure
  summary" — row `frog7-wirecli-module-10` 6/6 timeout evidence;
  Seed v2.5-A namesake row; closed at v2.6 P2 ship-gate by the
  instrumented runner.
- `docs/v2.6-task-plan.md` §"PHASE P1" — ledger destination + LOC
  budget anchor.
- `docs/v2.6-next-steps.md` §"Seed v2.5-G" — compare-back marker.
- `src/stream_manager/cli_governance.py:49` — `TIMEOUT_SECONDS =
  25.0` (FROZEN constant value; env-resolver split at step (3)
  elective preserves default-25.0 invariant).
- `src/stream_manager/cli_governance.py:347-368` — degrade-on-
  timeout branch; line 350 `cli governance timeout (>%.1fs);
  degrading` warning — the empirical fingerprint Seed v2.5-A
  hinges on.
- `tools/alignment_eval.py:98` — `evaluate_row` modification site.
- ADR-18 Rule 1 (surface freeze) — `TIMEOUT_SECONDS` default
  value invariant preserved at step (3) elective.
- ADR-18 Rule 3 (consolidation gate) — not in force this cycle
  (feature classification per P0 PR #193).
- ADR-18 Amendment A (3-bucket measurement) — `tools/` instrumentation
  qualifies as production bucket; lever-wire under bucket binding.
- ADR-18 Amendment C (cycle-tip anchor) — `084137dfc8823ae5eac84755581fc0aeed6342db`
  binds P1 LOC measurement.
- ADR-18 Amendment B (memory pre-flight) — P0 stamped; P1 light
  re-verify above.
- `feedback_cli_over_sdk.md` — instrumentation MUST measure live
  `claude -p` subprocess path; unit tests use monkeypatch only.
- `feedback_alignment_eval_stability_window.md` — n=6 mandate
  triggers; instrumentation covers both n=3 and n=6 without code
  change.
- `feedback_cassette_must_cover_new_envelopes.md` — N/A this PR
  (no new bus envelope).
- Precedent ahead-of-fire prompt mints: v2.4 PR #182 (P2 mint),
  v2.5.1 PR #188 (P1 corrective mint).
- v2.6 P0 PR #193 (`084137d`).
- v2.6 P0 SHA backfill PR #194.

Report back when P1 PR opens with:

1. PR URL.
2. Diff stat against cycle-tip:
   `git diff 084137dfc8823ae5eac84755581fc0aeed6342db..HEAD --stat -- src tests tools dashboard`.
3. Step (3) disposition (DEFER default OR FIRE same-phase).
4. Sample MD §"Per-model wall-clock distribution" rendering against
   a synthetic results dict (paste in PR body).
5. Sample JSON sidecar `rows` payload fragment showing per-row
   `sonnet_durations_s` + `haiku_durations_s` keys.
6. Sample `__summary__` payload fragment showing the 10 new keys.
7. Sub-cycle close-out diff guard output (must be additive on
   `tools/alignment_eval.py` step (1) and either empty OR
   env-resolver-only on `cli_governance.py` step (3) elective).
8. `pytest tests/test_alignment_eval_timing.py` green (+
   `tests/test_cli_governance_timeout_env.py` if step (3) bundled).
9. WIRED_LEVER_LEDGER posture confirmation (entering 1 / target
   end-P1 2 production).
