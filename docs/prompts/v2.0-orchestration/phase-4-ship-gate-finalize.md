You are implementing **Phase P4 — v2.0 ship-gate + ADR-5 v2.0 baseline + LOC delta gate** for the streamManager v2.0 cycle.

## Branch + base

- Base: `main` (after v2.0 P1 + P2 + P3 are all merged).
- PR target: `main`.
- Branch: `ship/v2.0-shipgate-finalize` (or operator's choice).
- If P1 / P2 / P3 not merged, ABORT.

## Context

v2.0 ship-gate validates the consolidation cycle's three guarantees:

1. **LOC-delta target met** — net add ≤ 0 (deletion-positive) per
   ADR-18 Rule 3. Compute against the v1.9.0 ship SHA `a7d0666`.
2. **Lever rips did not regress alignment or latency** — alignment-
   eval `--ci-gate` exit 0; Tier 3 soak verdict PASS; ADR-5 budget
   respected.
3. **DORMANT-N rule has codified WARN/BLOCK signal in the soak
   summary** — additive output; no behavioural change to soak driver.

## References

- `docs/adr/ADR-18-mvp-surface-freeze.md` Rule 2 (DORMANT-N) + Rule 3
  (LOC budget) + Rule 5 (backlog hard cap)
- `docs/adr/ADR-5-latency-budget.md` — append v2.0 ship-gate baseline
  section
- `tools/soak_driver.py` — Tier 3 invocation unchanged; post-soak
  summary extends additively with DORMANT-N read
- `tools/alignment_eval.py` — `--ci-gate` invocation unchanged
- `reports/soak-20260507T084933Z.md` — v1.9 baseline (compare against)
- `reports/v2-p1-cli-pool-ab-<timestamp>.md` — P1 outcome
- `reports/v2-p3-rip-<timestamp>.md` (if P3 minted one) — P3 outcome
- v1.6/v1.7/v1.8/v1.9 ship-gate prompt directories — format reference
  for shipgate sub-tasks (S1-S12 pattern from
  `docs/prompts/v1.6-shipgate/`)

## Do-not-touch guard

Tier 3 soak invocation, alignment-eval gate, ADR-5 baseline format
UNCHANGED. ADR-18 amendments only via explicit decision (no silent
edits). DORMANT-N codification is additive output in soak summary; do
NOT change the post-soak summary's existing fields or ordering — only
append.

## Scope

### S1 — Wipe soak state
Per `docs/prompts/v1.6-shipgate/S1-wipe-soak-state.md` pattern.
Clean `.bridge/`, `reports/soak-*` working state.

### S2 — Run Tier 3 ship-gate soak
`python tools/soak_driver.py --cli-pool-size 2 [--worker-recycle-every-n <N>]`
where `<N>` is the recommended cadence from P1 (Branch A — fallback
revived); omit the flag entirely under Branch B (fallback ripped) or
if P1 produced no clear winner. `CliPool.__init__` default stays
`None` either way — no FROZEN signature default flip per ADR-18
Rule 1. Wall-clock ~32 min. Launch via `run_in_background` +
`ScheduleWakeup` from main thread (per
`feedback_subagent_long_task_abandonment.md`). Use Monitor template
from `feedback_monitoring_live_sessions.md` for PASS / FAIL / panic /
PID-exit detection.

### S3 — Pull soak report
Verify `reports/soak-<UTC-timestamp>.md` written. Read overall p95,
ALLOW p95, L2/L3 p95, L4 alignment p95, LM p95, `cli_pool_send_ms`
p95, fallback fire rate (Branch A only — Branch B has no fallback
key).

### S4 — Compute LOC delta
```
git --no-pager diff a7d0666..HEAD --stat -- src tests tools dashboard | tail -1
```
Target: ≤ 0 net add (deletion-positive). Record exact number in
PR description.

If positive: ABORT ship. Either land an ADR-18 amendment justifying
the delta in this same PR, OR open v2.1 as a forced consolidation
cycle (carry the v2.0 work in as the prior baseline; v2.1 must be
deletion-positive).

### S5 — Codify DORMANT-N WARN/BLOCK in soak driver
Extend `tools/soak_driver.py` post-soak summary output:
- After existing summary fields, emit a new "Lever ledger" subsection.
- Hard-code a `WIRED_LEVER_LEDGER` dict in `tools/soak_driver.py`
  that mirrors ADR-18's current wired levers (after P3 rips). Each
  entry: `{lever_name: (fire_rate_metric_key, dormant_n_count_at_cycle_start)}`.
- For each entry: cross-reference the soak's measured fire rate for
  that metric key. Emit:
  - DORMANT-1 → INFO line (counter started)
  - DORMANT-2 → WARN line
  - DORMANT-3 → BLOCK line (and exit non-zero AFTER all summary
    output complete)
- **Empty-ledger case (Branch B):** if `WIRED_LEVER_LEDGER` is empty
  (P3 ripped both levers), still emit
  `Lever ledger: 0 wired levers — DORMANT-N gate inert`. This
  preserves a regression signal: future re-introduction of any
  lever bumps `WIRED_LEVER_LEDGER` and the summary line changes
  shape, alerting reviewers.

**Test (drift-detection between dict and ADR-18):** add
`tests/test_dormant_ledger_consistency.py`. Test reads
`docs/adr/ADR-18-mvp-surface-freeze.md`, regex-matches
`WIRED_LEVER_LEDGER_COUNT:\s*(\d+)`, asserts equality with
`len(WIRED_LEVER_LEDGER)` imported from `tools/soak_driver`.
Single-line parse, no full-markdown parser. Failure message points
at both files: "ADR-18 says N wired levers; soak_driver dict has M.
Update both in the same PR (ADR-18 HTML comment + dict)."

After v2.0 P3 rips, the wired-lever count is either 1 (Branch A —
fallback retained) or 0 (Branch B — both ripped). Both the dict and
the ADR-18 HTML comment must reflect P3's chosen branch; P3 PR
updates both same-commit.

### S6 — Update ADR-5
Append §"v2.0 ship-gate baseline" section. Include:
- Source: `reports/soak-<timestamp>.md`
- Date
- Ship SHA
- Driver: `--cli-pool-size 2` (+ `worker_recycle_every_n` value if
  promoted by P1)
- Per-band p95, RSS drift, alignment-eval results
- Lever-effect ledger update: P3 rip outcomes, P1 revival outcome (if
  Branch A)
- LOC delta vs v1.9.0
- Caveats (any per-band tail violations at small n; LM trend
  movement)

### S7 — Update CHANGELOG.md
Add `## [2.0.0] — <date>` section. Format mirrors v1.9.0 entry.
Highlights:
- ADR-18 minted (cycle-discipline rules)
- v2.0 P1 cli_pool A/B outcome
- ADR-17 amendment (Tier 1.5 + trigger matrix)
- v2.0 P3 rips (lever-cleanup)
- Net LOC delta achieved

### S8 — Seed v2.1 backlog
Create `docs/v2.1-backlog.md`. Stubs:
- Carry-forwards from v2.0 (any 🟡 items not graduated; expected zero
  if v2.0 cycle disposed cleanly)
- 🟢 PPP audit harness (still blocked on sync-comms v1.0 HITL panel)
- 🟢 CI gate enforcement of Tier 1.5 trigger matrix (if matrix proves
  stable in v2.0)
- 🟢 Tier 4 large-n smoke soak (tail-variance triage candidate from
  v1.9 ship-gate)
- Any new items from P1 / P3 escape-hatches

### S9 — Open ship PR

### S10 — Merge + tag
v2.0.0 tag on the merge commit.

### S11 — Update memory
Mint `project_v20_cycle_close.md` per the existing
`project_v19_cycle_close.md` template. Include:
- Ship SHA + tag
- ADR-18 minted
- Lever rips (which, why)
- LOC delta
- Cycle-discipline rules now in force for v2.1+

### S12 — Frame v2.1
(Optional — operator may defer.) Mint
`docs/prompts/v2.1-orchestration/phase-0-cycle-frame.md` stub
inheriting ADR-18 rules.

## DOD

- [ ] Tier 3 soak verdict PASS
- [ ] Alignment-eval `--ci-gate` exit 0; sonnet ≥ 0.95, haiku ≥ 0.85,
      0 FR-OG-7 regressions, 0 haiku regressions vs sonnet
- [ ] LOC delta ≤ 0 OR explicit ADR-18 amendment in same PR
- [ ] ADR-5 v2.0 baseline section appended
- [ ] DORMANT-N gate codified in `tools/soak_driver.py` post-soak
      summary; test asserts dict matches ADR-18 wired-lever count
- [ ] CHANGELOG.md v2.0.0 entry written
- [ ] Memory mint: `project_v20_cycle_close.md`
- [ ] v2.0.0 tag on a `main` commit; ship PR merged
- [ ] `docs/v2.1-backlog.md` created
- [ ] (Optional) v2.1 P0 stub minted

## Mint-new-phase rule

If Tier 3 soak fails verdict for reasons attributable to v2.0 P1 or
P3 changes, do NOT mint a P5 fix-forward phase — phase budget is at
cap. Open `ship/v2.0-shipgate-fixups` as a sub-cycle (S9a pattern from
v1.6 / v1.8) under the existing ship-gate frame; same authority as
S1-S12, not a numbered phase mint.

If LOC delta is +N where N > 0 and the work is genuinely irreducible,
land an ADR-18 amendment "v2.0 LOC budget exception" in the same PR
explaining the irreducibility. This is allowed by ADR-18 Rule 3
(amendment path). Do NOT silently merge over budget.

If during S11 memory mint a sixth memory gap surfaces (e.g. P1's
worker-recycle finding has unexpected long-tail implications), mint a
new memory file rather than overloading `project_v20_cycle_close.md`
— each memory file should remain single-topic per the
`anthropic-skills:consolidate-memory` convention.

Report back when ship PR is merged and v2.0.0 is tagged with: PR URL,
tag SHA, soak report path, alignment-eval report path, LOC delta,
P3 branch chosen, lever-ledger final state, v2.1 backlog path.
