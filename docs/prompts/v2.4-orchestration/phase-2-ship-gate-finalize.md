# v2.4 P2 — ship-gate finalize + ADR-5 v2.4 baseline (conditional) + CHANGELOG + tag

> Minted 2026-05-19 as part of v2.4 P1 fire. Format mirrors v2.3 P2
> prompt with Amendment C cycle-tip anchor + dual-anchor reporting +
> Seed v2.4-H lever-ledger scope binding folded into P2 PR body +
> Sonnet-DIP follow-up watch (post-FREEZE) + p95 / L4 / LM watch.
>
> Cycle type **CONSOLIDATION** (recorded at P0 PR #179 per
> `docs/v2.4-task-plan.md` §"Operator decisions recorded at P0 fire"
> #1). Net production LOC ≤ 0 vs cycle-tip per Amendment C.
>
> Comparison anchor: `docs/v2.4-next-steps.md` §"Compare-back
> protocol". Each S-step that closes a seed MUST mark its row in
> `v2.4-next-steps.md`.

## Branch + base

- Base: `main` after v2.4 P0 (PR #179 `b35e982`) + v2.4 P1
  (PR #181 `69e2116`, Sonnet-DIP report — FREEZE) merged.
- PR target: `main`.
- Branch: `ship/v2.4-shipgate-finalize`.
- ABORT if P0 or P1 not merged at HEAD.

## Pre-flight (Amendment B — memory pre-flight)

```
git fetch origin
git log --oneline origin/main -10
```

Expected: HEAD = `69e2116` (PR #181) on top of `b35e982` (PR #179)
on top of v2.3.0 lineage. If divergent, STOP.

Verify memories per `phase-0-cycle-frame.md` §Pre-flight; re-check
freshness (P0 already updated `project_v10_rl_track.md` +
`project_v10_p4_hold_lifted.md` at PR #179; verify no further drift).
Add to pre-flight at P2:

- `project_v23_cycle_close.md` — predecessor close memory.
- `project_v10_p5_gate_deadlock.md` — Amendment D landed P0; status
  flip to `AMENDMENT-LANDED (docs side)` if not already done.

If any memory stale, update IN A SEPARATE PRE-P2 PR or at top of P2
PR (per Amendment B precedent). Stamp goes in P2 PR body.

## Context

v2.4 ship-gate validates the **consolidation** classification:

- **Consolidation cycle:** net production LOC ≤ **0** vs cycle-tip
  (`b35e9824881a7251800fc35eb956157561527e47`, P0 merge SHA).
  `WIRED_LEVER_LEDGER_COUNT` HOLD (no wire/rip this cycle; entering
  posture = 1 production / 0 soak per `docs/v2.4-task-plan.md` §2).

In addition:

- API-timeout invariant holds (canary line PASS).
- Sonnet pass-rate: v2.3 ship-gate landed 0.8182 (DIP). P1 Seed v2.4-D
  recommended **FREEZE-on-content** (PR #181); v2.4 P2 re-measures —
  ≥ 0.80 floor must hold (FR-OG-7 binding). Trajectory recorded.
- Haiku pass-rate: v2.3 = 0.9412 (RECOVERED off floor; Seed 2
  CLOSED). v2.4 P2 confirms ≥ 0.85 floor.
- p95 latency: v2.3 = 10.584 s (Seed 1 PARTIAL RECOVERY; closure
  threshold ≤ 8.2 s). v2.4 P2 = Seed v2.4-E re-measure.
- L4 + LM p95: v2.3 small-n watch (Seed v2.4-F). v2.4 P2 re-measure
  at larger n if available.

ADR-18 surface freeze stays in force. Amendment D + E landed P0.

## References (load before starting)

- `docs/v2.4-task-plan.md` §PHASE P2 — scope sketch (minted at P0).
- `docs/v2.4-next-steps.md` — comparison anchor. Walk row-by-row at
  S10 (compare-back) → record outcome in S11 (close memory).
- `docs/prompts/v2.3-orchestration/phase-2-ship-gate-finalize.md` —
  immediate predecessor; format template.
- `docs/adr/ADR-5-latency-budget.md` — append §"v2.4 ship-gate
  baseline" if soak fires; else record skip rationale in P2 PR body.
- `docs/adr/ADR-17-soak-tiers.md` + `docs/soak-trigger-matrix.md` —
  Tier-3 invocation.
- `docs/adr/ADR-18-mvp-surface-freeze.md` §Amendments A / B / C /
  D / E.
- `reports/soak-20260517T193220Z.md` — v2.3 ship-gate baseline.
- `reports/alignment-eval-20260517T205353Z.md` — v2.3 baseline (DIP).
- `reports/sonnet-dip-v23-v24.md` — P1 FREEZE recommendation.
- `tools/soak_driver.py` — `--ppp-auto-probe` inherited; verify
  `WIRED_LEVER_LEDGER: dict = {}` (soak-scope ledger) still empty.
- Memory: `project_v23_cycle_close.md`,
  `project_v10_p5_gate_deadlock.md`,
  `feedback_subagent_long_task_abandonment.md`,
  `feedback_monitoring_live_sessions.md`,
  `feedback_soak_cli_pool_flag.md`.

## ⚠️ CRITICAL: Do-not-touch guard

P2 touches **only**:

- `docs/adr/ADR-5-latency-budget.md` — append v2.4 baseline (or
  skip with rationale recorded in P2 PR body if consolidation
  cycle + LOC delta ≈ 0 + no latency lever wired, per
  `phase-0-cycle-frame.md` §"ADR-5 freshness").
- `docs/v2.4-task-plan.md` — append §"P2 close-out (this PR)".
- `docs/v2.4-backlog.md` (mint if not present) — append §"Carry-
  forwards from v2.4" with rows for unresolved seeds (v2.4-I..N
  promotion-criterion-bound carries + any NEW v2.4 ship-gate
  seeds).
- `docs/v2.4-next-steps.md` — **row-by-row mark-up only**; do NOT
  rewrite seeds. Append §"v2.4 P2 ship-gate close-out" with the
  comparison-pass result and §"NEW v2.4 ship-gate seeds (carry-
  forward to v2.5)" if any.
- `docs/v2.3-backlog.md` — annotate any resolved carry-forwards
  with `RESOLVED v2.4 PR #___` markers. **No edits to existing
  emoji** — per frozen-emoji rule.
- `CHANGELOG.md` — append `## [2.4.0]` section.
- Memory: write `project_v24_cycle_close.md` + add to `MEMORY.md`.

**No code edits expected at P2.** P0 PR #179 (docs + Amendment D/E
+ #111 close) and P1 PR #181 (report-only Sonnet-DIP) shipped the
cycle surface; P2 is verification + narrative.

## Scope

### S1 — Wipe soak state

```powershell
Remove-Item -Force .bridge/soak-driver/*, .bridge/cli-pool.pids, reports/soak-*.md -ErrorAction SilentlyContinue
```

(Preserve historical reports in git; only wipe working-directory
artifacts. The `reports/soak-*.md` files already committed remain
intact in git history.)

### S2 — Fire Tier-3 soak

Per ADR-17 Tier-3 + `feedback_subagent_long_task_abandonment.md`,
launch from main thread with `run_in_background` + `ScheduleWakeup`.
**NEVER from a subagent** per memory.

```powershell
$env:BRIDGE_API_GOV = "1"
$env:BRIDGE_RL_LOGGER_ENABLED = "1"       # v10 P4 corpus continued piggyback (per docs/v2.4-task-plan.md)
$env:BRIDGE_CYCLE_TIP_SHA = "b35e9824881a7251800fc35eb956157561527e47"  # v2.4 P0 merge — Amendment C anchor
$env:BRIDGE_PREDECESSOR_TAG_SHA = "b00473dd68fe1d9faed6feb6397370ca542602a0"  # v2.3.0
$env:BRIDGE_CYCLE_TYPE = "consolidation"

python tools/soak_driver.py `
  --cli-pool-size 2 `
  --ppp-auto-probe `
  --total-seconds 1800 `
  --interval-seconds 20
```

`--cli-pool-size 2` is REQUIRED per `feedback_soak_cli_pool_flag.md`
(default 0 silently reproduces v1.0 cold-start regression).

Monitor template: `feedback_monitoring_live_sessions.md`. Expected
duration ~30 min. Schedule wake-up at 35 min for completion check.

### S3 — Verify invariant-degrade canary

Soak summary closing block MUST contain
`[soak] invariant-degrade canary: PASS`. FAIL = ship blocked.

Also verify Seed 4 dual-anchor block renders in soak report:
- `cycle-tip (b35e982..HEAD): +X / -Y / +Z [PASS|BLOCK]`
- `predecessor-tag (b00473d..HEAD): +X / -Y / +Z [narrative]`

Cycle-tip line MUST show **net ≤ 0** for consolidation PASS.

### S4 — Alignment-eval

```
python tools/alignment_eval.py --ci-gate
```

Exit 0 required. Compare against v2.3 ship-gate baselines:

- **Sonnet** at v2.3 = 0.8182 (DIP; P1 FREEZE recommendation).
  v2.4 disposition:
  - ≥ 0.90 → RECOVERED; record FREEZE-validated; close Seed v2.4-D
    follow-up watch.
  - 0.85 – 0.90 → STABILIZED; FREEZE recommendation holds; record
    as v2.5 informational watch.
  - 0.80 – 0.85 → STILL DIPPED; FREEZE recommendation holds but
    re-open Seed v2.4-D investigation as v2.5 seed (consider FIRE-fix
    promotion).
  - < 0.80 → BLOCK ship; FR-OG-7 floor BREACH; root-cause before
    tag.
- **Haiku** at v2.3 = 0.9412 (RECOVERED). v2.4 disposition:
  - ≥ 0.85 → STABLE; no action.
  - 0.80 – 0.85 → BREACH; FR-OG-7 floor regression. BLOCK ship
    OR mint floor amendment.
  - < 0.80 → BLOCK ship; root-cause.

Record four-cycle trajectory `v2.1 → v2.2 → v2.3 → v2.4` for both
models in P2 PR body. Matches Sonnet-DIP investigation §Step 4
pattern (`task-sonnet-dip-investigation.md`) which pulls v2.1
majority for trajectory continuity.

### S5 — LOC delta verification (Amendment C cycle-tip anchor)

**Per ADR-18 Amendment C, the binding gate anchor is the cycle-tip
(P0-merge SHA `b35e982`), NOT the predecessor tag.** Run BOTH for the
dual-anchor narrative:

```
# Binding (Amendment C) — consolidation gate:
git diff b35e9824881a7251800fc35eb956157561527e47..HEAD --stat -- src tests tools dashboard

# Narrative (Amendment A) vs predecessor tag v2.3.0:
git diff b00473d..HEAD --stat -- src tests tools dashboard
```

Gate verdict from cycle-tip (production bucket: `src/` + `tests/` +
`tools/` + `dashboard/`):

- **Consolidation: net ≤ 0 = PASS; > 0 = BLOCK.**
- Docs bucket advisory under Amendment A — not gating.

If gate BLOCK, demand deletion reconciliation pre-tag.

Cross-check: Seed 4 dual-anchor block in soak summary report should
match this manual computation byte-for-byte. Mismatch = report bug.

### S6 — Seed v2.4-H lever-ledger scope binding (P2 PR body)

Per `docs/v2.4-next-steps.md` fire-order row 7 footnote + Seed
v2.4-H disposition, the P2 PR body MUST record the lever-ledger
scope-binding decision verbatim. Options:

- **(a) Production scope is canonical.** Close-memory
  `WIRED_LEVER_LEDGER_COUNT` field = production count (= 1 at
  v2.4 close, unchanged from v2.3 Seed 6 JsonlTailWorker wire).
  Soak-scope ledger remains an internal soak-driver artefact only.
- **(b) Soak scope is canonical.** Close-memory field = soak count
  (= 0). Production-scope wiring is informational; close-memory
  uses soak `WIRED_LEVER_LEDGER: dict = {}` len.

**Recommendation: (a) production scope.** Rationale: feature-cycle
classification under Amendment A asks "is a lever wired in shipped
code?" not "is a lever exercised by soak driver?". Soak-scope
ledger stays internal to soak harness narrative.

Decision recorded verbatim in P2 PR body. P2 PR body alone is
binding — no ADR-18 amendment required for (a) or (b). If operator
wishes to elevate scope split into ADR-18 §Amendments (e.g. dual-
field future evolution), mint as a SEPARATE follow-up PR in v2.5
(not in P2 ship-gate PR, per Do-not-touch guard).

### S7 — ADR-5 v2.4 baseline append (conditional)

Per `phase-0-cycle-frame.md` §"ADR-5 freshness":

- **IF** consolidation cycle with LOC delta ≈ 0 AND no latency lever
  wired → **MAY skip** the v2.4 ADR-5 baseline append. Record skip
  rationale in P2 PR body.
- **ELSE** (any latency-relevant delta surfaced) → append §"v2.4
  ship-gate baseline" mirroring v2.3 format:
  - Source soak report path.
  - Per-band p50/p95 (ALLOW, L2, L3, L4, LM).
  - **Delta vs v2.3 ship-gate** (Seed v2.4-E p95 watch + Seed
    v2.4-F L4/LM watch).
    - If overall p95 ≤ 8.2 s → Seed v2.4-E CLOSES; record.
    - If overall p95 > 10.584 s + 0.5 s → 🟡 REGRESSION;
      promote Seed v2.4-E to 🔴 v2.5 seed.
    - If L4 + LM hold or recover at larger n → Seed v2.4-F
      WATCH continues OR closes per pattern.
  - Lever ledger row (HOLD at 1 production / 0 soak per S6
    decision; cite scope-binding decision).
  - Alignment-eval gate verdict + per-model rates.
  - v10 P4 corpus piggyback delta (post-soak episode count).
  - Caveats.

**Default for v2.4 (consolidation, LOC ≈ 0, no latency lever
wired): SKIP the append with rationale.** Operator overrides at
P2 fire if soak surfaces latency-relevant data.

### S8 — CHANGELOG entry

Append `## [2.4.0]` per Keep-a-Changelog format. Cover:

- **Added** — none expected (consolidation cycle).
- **Changed** — ADR-18 Amendment D (v10 P5 gate split) + Amendment E
  (Rule 5 cycle-handoff exemption) minted at P0; staging file
  `docs/adr/ADR-18-amendment-d-draft.md` deleted.
- **Closed** — Issue #111 (v10 P4 trainer DOD; PR #176); Issue #177
  (closed by Amendment D landing).
- **Removed** — deletions vs **cycle-tip** (Amendment C binding;
  if any). Predecessor-tag delta listed in narrative footnote only.
- **Deferred / carry-forward** — explicit list of v2.4-next-steps
  seeds NOT closed this cycle: Seed v2.4-C (Path-D P5; v2.5),
  Seed v2.4-G (CLI-timeout audit; v2.5), Seeds v2.4-I..N (promotion-
  criterion / demand-bound exempts), plus any NEW v2.4 ship-gate
  seeds.

### S9 — Tag v2.4.0

After PR review approve + merge to main:

```
git tag -a v2.4.0 -m "v2.4.0 consolidation cycle — Amendment D (v10 P5 gate split) + Amendment E (Rule 5 exemption) + #111 close + Sonnet-DIP FREEZE" <merge-SHA>
git push origin v2.4.0
```

### S10 — Compare-back pass against `docs/v2.4-next-steps.md`

**This is the comparison anchor checkpoint** — the goal-directive
binding step. Walk row-by-row through `docs/v2.4-next-steps.md`
§Seeds (v2.4-A..N) + §"P0 frame":

For each row:
- Mark `[x]` and append `LANDED PR #N (<merge-SHA>)` (closed this
  cycle), OR
- Mark `[ ] DEFERRED v2.5 — <one-line rationale>`, OR
- Mark `[ ] DROPPED — <one-line rationale>` (e.g. promotion
  criterion not met, demand absent).

Expected state going into S10 (per task-plan / next-steps as of
P1 close):

| Seed | Expected disposition |
|------|----------------------|
| v2.4-A (🔴 Amendment D)   | LANDED P0 PR #179 |
| v2.4-B (🟡 #111 close)    | LANDED P0 PR #179 |
| v2.4-C (🟡 Path-D P5)     | DEFERRED v2.5 (consolidation cycle) |
| v2.4-D (🟡 Sonnet-DIP)    | LANDED P1 PR #181 (FREEZE) |
| v2.4-E (🟢 p95 watch)     | re-measure at S4/S7 |
| v2.4-F (🟡 L4/LM watch)   | re-measure at S4/S7 |
| v2.4-G (🟡 CLI timeout)   | DEFERRED v2.5 (consolidation cycle) |
| v2.4-H (🟡 lever scope)   | LANDED P2 (this PR) per S6 |
| v2.4-I..N (🟢/🟡 carries) | promotion-criterion / demand-bound — carry to v2.5 |

Append §"v2.4 P2 ship-gate close-out" section at the end of
`docs/v2.4-next-steps.md` with the row-by-row outcome table. Fill
the TBD table at L315 of `docs/v2.4-next-steps.md`.

### S11 — Mint close memory

Write `memory/project_v24_cycle_close.md` per template
(`project_v23_cycle_close.md`). Cover:

- Tag SHA + PR list (chronological: #178, #179, #180, #181, this PR).
- Cycle type = CONSOLIDATION + LOC delta (cycle-tip binding,
  predecessor-tag narrative).
- Lever ledger status (delta vs entering posture; cite S6 scope
  binding).
- v2.4-next-steps comparison-pass outcome (S10 summary).
- Sonnet-DIP follow-up result (FREEZE validated / re-open / closed).
- Haiku floor result.
- p95 watch result (Seed v2.4-E closure or carry-forward).
- L4/LM watch result (Seed v2.4-F closure or carry-forward).
- v10 P4 corpus delta (post-soak episode count).
- Amendment D + E landing recorded.
- Carry-forwards into v2.5 (Seed v2.4-C, v2.4-G, v2.4-I..N, NEW
  ship-gate seeds).

Add index entry to `MEMORY.md`.

### S12 — Lifetime cleanup

If any v2.4 prompt file in `docs/prompts/v2.4-orchestration/` has a
lifetime clause, retire per clause. Default: prompts persist as
historical record (matches v2.0 / v2.1 / v2.2 / v2.3 pattern).

### S13 — Mint-new-phase rule

If S2–S5 surfaces any must-fix item, mint a v2.4.1 patch-cycle
prompt (v1.3 / v1.6 / v1.8 corrective-cycle precedent). Default:
no follow-up; ship clean.

## DoD

- [ ] Tier-3 soak PASS verdict.
- [ ] Invariant-degrade canary PASS.
- [ ] Alignment-eval `--ci-gate` exit 0; both Sonnet + Haiku
      dispositions recorded (with three-cycle trajectory).
- [ ] LOC delta verified at **cycle-tip anchor** (Amendment C);
      consolidation gate net ≤ 0 = PASS.
- [ ] Seed 4 dual-anchor block in soak summary verified byte-
      identical with manual computation.
- [ ] Seed v2.4-H lever-ledger scope binding decision recorded
      verbatim in P2 PR body (S6).
- [ ] ADR-5 v2.4 baseline appended OR skip rationale recorded.
- [ ] CHANGELOG `## [2.4.0]` appended.
- [ ] `v2.4.0` tag pushed.
- [ ] `project_v24_cycle_close.md` memory + MEMORY.md index.
- [ ] **`docs/v2.4-next-steps.md` row-by-row pass complete** (the
      goal-directive binding step) + §"v2.4 P2 ship-gate close-out"
      table populated.
- [ ] Single PR `ship(v2.4):` against `main`.

Report back when v2.4.0 tag is pushed with: tag SHA, soak report
path, alignment dispositions (Sonnet + Haiku with three-cycle
trajectory), final cycle-tip LOC delta, predecessor-tag narrative
LOC delta, v10 P4 episode count delta, Seed v2.4-H scope-binding
choice, and the row-by-row outcome from `docs/v2.4-next-steps.md`.
