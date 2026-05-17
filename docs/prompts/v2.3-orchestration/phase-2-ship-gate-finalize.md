# v2.3 P2 — ship-gate finalize + ADR-5 v2.3 baseline + CHANGELOG + tag

> Minted 2026-05-17 as part of v2.3-pm-mint PR. Format mirrors v2.2 P2
> prompt with Amendment C cycle-tip anchor baked into S5 + dual-anchor
> reporting + p95 regression watch + Haiku floor watch.
>
> Comparison anchor: `docs/v2.3-next-steps.md` §"Compare-back
> protocol". Each S-step that closes a seed MUST mark its row in
> `v2.3-next-steps.md`.

## Branch + base

- Base: `main` after v2.3 P0 + all v2.3 P1 PRs merged.
- PR target: `main`.
- Branch: `ship/v2.3-shipgate-finalize`.
- ABORT if P0 or any required P1 not merged.

## Pre-flight (Amendment B — memory pre-flight)

```
git fetch origin
git log --oneline origin/main -10
```

Expected: P0 merge + N x P1 merges at HEAD. If divergent, STOP.

Verify memories per `phase-0-cycle-frame.md` §Pre-flight; re-check
freshness (some may have been touched by P1 work).

## Context

v2.3 ship-gate validates the cycle's classification:

- **Feature cycle:** net LOC ≤ 1500 (soft) / < 2250 (BLOCK at 1.5×)
  vs **cycle-tip** (P0-merge SHA). `WIRED_LEVER_LEDGER_COUNT` ≥ 1.
- **Consolidation cycle:** net LOC ≤ 0 vs cycle-tip.
  `WIRED_LEVER_LEDGER_COUNT` unchanged.

In **both** classifications:

- API-timeout invariant holds (canary line PASS).
- p95 latency does not regress further beyond the v2.2 ceiling
  (+4.54 s = 🟡 watch, not 🔴 block). If +1570 ms `cli_pool_send_ms`
  holds AGAIN, recompute v1.7 budget framing in ADR-5.
- Haiku alignment pass rate ≥ 0.85 floor; 1 row flip below triggers
  BREACH.

ADR-18 surface freeze stays in force.

## References (load before starting)

- `docs/v2.3-task-plan.md` §PHASE P2 — scope sketch (minted at P0).
- `docs/prompts/v2.2-orchestration/phase-2-ship-gate-finalize.md` —
  immediate predecessor; format template.
- `docs/adr/ADR-5-latency-budget.md` — append §"v2.3 ship-gate
  baseline".
- `docs/adr/ADR-17-soak-tiers.md` + `docs/soak-trigger-matrix.md` —
  Tier-3 invocation.
- `reports/soak-20260517T142726Z.md` — v2.2 ship-gate baseline.
- `tools/soak_driver.py` — `--ppp-auto-probe` inherited; verify
  Seed 4 dual-anchor block landed (cycle-tip + predecessor-tag).
- `docs/v2.3-next-steps.md` — comparison anchor. Walk row-by-row at
  S9 close memory.
- Memory: `project_v22_cycle_close.md` (template +
  predecessor-cycle facts), `feedback_subagent_long_task_
  abandonment.md`, `feedback_monitoring_live_sessions.md`,
  `feedback_soak_cli_pool_flag.md`.

## ⚠️ CRITICAL: Do-not-touch guard

P2 touches **only**:

- `docs/adr/ADR-5-latency-budget.md` — append v2.3 baseline.
- `docs/v2.3-task-plan.md` — append §"P2 close-out (this PR)".
- `docs/v2.3-backlog.md` (mint if not present) — append §"Carry-
  forwards from v2.3" with rows for unresolved seeds.
- `docs/v2.3-next-steps.md` — **row-by-row mark-up only**; do NOT
  rewrite seeds. Append §"v2.3 P2 ship-gate close-out" with the
  comparison-pass result.
- `docs/v2.2-backlog.md` — annotate resolved carry-forwards with
  `RESOLVED v2.3 PR #___` markers. **No edits to existing emoji** —
  per frozen-emoji rule.
- `CHANGELOG.md` — append `## [2.3.0]` section.
- Memory: write `project_v23_cycle_close.md` + add to `MEMORY.md`.
- If ADR-18 Rule 5 amendment was minted at P0: cross-link only;
  amendment text is P0 territory.

**No code edits expected at P2.** P1 PRs shipped all code surface;
P2 is verification + narrative.

## Scope

### S1 — Wipe soak state

```powershell
Remove-Item -Force .bridge/soak-driver/*, .bridge/cli-pool.pids, reports/soak-*.md -ErrorAction SilentlyContinue
```

(Preserve historical reports in git; only wipe working-directory
artifacts.)

### S2 — Fire Tier-3 soak

Per ADR-17 Tier-3 + `feedback_subagent_long_task_abandonment.md`,
launch from main thread with `run_in_background` + `ScheduleWakeup`:

```powershell
$env:BRIDGE_API_GOV = "1"
$env:BRIDGE_RL_LOGGER_ENABLED = "1"       # v10 P4 corpus piggyback
$env:BRIDGE_CYCLE_TIP_SHA = "<P0-merge-SHA>"      # Seed 4 dual-anchor
$env:BRIDGE_PREDECESSOR_TAG_SHA = "3235144"       # v2.2.0
$env:BRIDGE_CYCLE_TYPE = "feature"        # OR "consolidation"
# If Seed 3 NOT yet landed: $env:PYTHONPATH = "."

python tools/soak_driver.py `
  --cli-pool-size 2 `
  --ppp-auto-probe `
  --total-seconds 1800 `
  --interval-seconds 20
```

Monitor template: `feedback_monitoring_live_sessions.md`. Expected
duration ~30 min. Schedule wake-up at 35 min for completion check.

### S3 — Verify invariant-degrade canary

Soak summary closing block MUST contain
`[soak] invariant-degrade canary: PASS`. FAIL = ship blocked.

### S4 — Alignment-eval

```
python tools/alignment_eval.py --ci-gate
```

Exit 0 required. Compare against v2.2 ship-gate baselines:

- **Sonnet** at v2.2 = 0.9474 (recovered). v2.3 disposition:
  - ≥ 0.90 → STABLE; record `docs/v2.3-next-steps.md` reflection.
  - 0.80 – 0.90 → DIP; mint v2.3-backlog seed (similar to v2.1 dip).
  - < 0.80 → BLOCK ship; root-cause.
- **Haiku** at v2.2 = 0.85 (at floor exact). v2.3 disposition:
  - ≥ 0.85 → STABLE; **close Seed 2 watch**.
  - 0.80 – 0.85 → BREACH; FR-OG-7 floor regression. BLOCK ship
    OR mint floor amendment.
  - < 0.80 → BLOCK ship; root-cause.

### S5 — LOC delta verification (Amendment C cycle-tip anchor)

**Per ADR-18 Amendment C, the binding gate anchor is the cycle-tip
(P0-merge SHA), NOT the predecessor tag.** Run BOTH for the dual-
anchor narrative (matches Seed 4 soak-summary block):

```
# Binding (Amendment C):
git diff <P0-merge-SHA>...HEAD --stat -- src tests tools dashboard

# Narrative (Amendment A):
git diff 3235144...HEAD --stat -- src tests tools dashboard
```

Gate verdict from cycle-tip:
- Consolidation: net ≤ 0 = PASS; > 0 = BLOCK.
- Feature: net ≤ 1500 = PASS; 1500–2249 = PASS w/ override note;
  ≥ 2250 = BLOCK (1.5× hard).

If gate BLOCK, demand deletion reconciliation pre-tag.

Cross-check: Seed 4 dual-anchor block in soak summary report should
match this manual computation byte-for-byte. Mismatch = report bug.

### S6 — ADR-5 v2.3 baseline append

Append §"v2.3 ship-gate baseline" to `docs/adr/ADR-5-latency-
budget.md`. Format mirrors v2.2 baseline. Include:

- Source soak report path.
- Per-band p50/p95 (ALLOW, L2, L3, L4, LM).
- **Delta vs v2.2 ship-gate** (the 🟡 p95 watch — Seed 1).
  - If overall p95 ≤ v2.1 floor + 0.5 s → Seed 1 CLOSES; record
    in ADR-5 caveats.
  - If `cli_pool_send_ms` p95 ≥ v2.2 value + 0 ms (i.e. holds) →
    promote to 🔴; recompute v1.7 budget framing.
  - If `cli_pool_send_ms` p95 < v2.2 value − 500 ms (recovers) →
    Seed 1 CLOSES; record run-to-run variance hypothesis confirmed.
- Lever ledger row (0 → N depending on cycle type).
- Alignment-eval gate verdict + per-model rates.
- v10 P4 piggyback delta (if Seed 5 fired Path A): episode-count
  before/after.
- Caveats.

### S7 — CHANGELOG entry

Append `## [2.3.0]` per Keep-a-Changelog format. Cover:

- **Added** — list per landed P1 PRs.
- **Changed** — Amendments minted (Rule 5 if applicable);
  configuration changes.
- **Removed** — deletions (if consolidation cycle).
- **Deferred / carry-forward** — explicit list of v2.3-next-steps
  seeds NOT closed this cycle.

### S8 — Tag v2.3.0

After PR review approve + merge to main:

```
git tag -a v2.3.0 -m "v2.3.0 <cycle-type> cycle — <one-line summary>" <merge-SHA>
git push origin v2.3.0
```

### S9 — Compare-back pass against `docs/v2.3-next-steps.md`

**This is the comparison anchor checkpoint** — the goal-directive
binding step. Walk row-by-row through `docs/v2.3-next-steps.md`
§Seeds (1-12) + §"P0 frame":

For each row:
- Mark `[x] LANDED PR #N` (closed this cycle), OR
- Mark `[ ] DEFERRED v2.4 — <one-line rationale>`, OR
- Mark `[ ] DROPPED — <one-line rationale>` (e.g. promotion
  criterion not met, demand absent).

Append a §"v2.3 P2 ship-gate close-out" section at the end of
`docs/v2.3-next-steps.md` with the row-by-row outcome table.

### S10 — Mint close memory

Write `memory/project_v23_cycle_close.md` per template
(`project_v22_cycle_close.md`). Cover:

- Tag SHA + PR list (chronological).
- Cycle type + LOC delta (cycle-tip binding, predecessor-tag
  narrative).
- Lever ledger status (delta vs entering posture).
- v2.3-next-steps comparison-pass outcome (S9 summary).
- p95 watch result (Seed 1 closure or carry-forward).
- Haiku floor result (Seed 2 closure or breach).
- v10 P4 corpus-fill result (Seed 5 episode count post-cycle).
- Carry-forwards into v2.4.

Add index entry to `MEMORY.md`.

### S11 — Lifetime cleanup

If any v2.3 prompt file in `docs/prompts/v2.3-orchestration/` has a
lifetime clause, retire per clause. Default: prompts persist as
historical record (matches v2.0 / v2.1 / v2.2 pattern).

### S12 — Mint-new-phase rule

If S2–S5 surfaces any must-fix item, mint a v2.3.1 patch-cycle
prompt (v1.3 / v1.6 / v1.8 corrective-cycle precedent). Default:
no follow-up; ship clean.

## DoD

- [ ] Tier-3 soak PASS verdict.
- [ ] Invariant-degrade canary PASS.
- [ ] Alignment-eval `--ci-gate` exit 0; both Sonnet + Haiku
      dispositions recorded.
- [ ] LOC delta verified at **cycle-tip anchor** (Amendment C).
- [ ] Seed 4 dual-anchor block in soak summary verified.
- [ ] ADR-5 v2.3 baseline appended.
- [ ] CHANGELOG `## [2.3.0]` appended.
- [ ] `v2.3.0` tag pushed.
- [ ] `project_v23_cycle_close.md` memory + MEMORY.md index.
- [ ] **`docs/v2.3-next-steps.md` row-by-row pass complete** (the
      goal-directive binding step).
- [ ] Single PR `ship(v2.3):` against `main`.

Report back when v2.3.0 tag is pushed with: tag SHA, soak report
path, alignment dispositions (Sonnet + Haiku), final cycle-tip LOC
delta, predecessor-tag narrative LOC delta, v10 P4 episode count
delta, and the row-by-row outcome from `docs/v2.3-next-steps.md`.
