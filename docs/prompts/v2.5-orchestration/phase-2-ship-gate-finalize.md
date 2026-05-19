# v2.5 P2 — ship-gate finalize + ADR-5 v2.5 baseline (conditional) + CHANGELOG + tag

> Minted ahead-of-fire 2026-05-19 (mirrors v2.4 PR #182 precedent —
> P2 prompt minted in a PM PR separate from the P0 cycle-frame PR).
> Format mirrors v2.4 P2 prompt with Amendment C cycle-tip anchor +
> dual-anchor reporting + Sonnet-DIP FREEZE-on-content re-measure
> watch (Seed v2.4-Q) + Seed v2.4-E p95 watch + Seed v2.4-F L4/LM
> watch + Seed v2.4-G promotion confirm (impl defers v2.6).
>
> Cycle type **CONSOLIDATION** (recorded at P0 PR #185 per
> `docs/v2.5-task-plan.md` §"Operator decisions recorded at P0 fire"
> #1). Net production LOC ≤ 0 vs cycle-tip per Amendment C.
>
> **Zero work phases this cycle.** v2.5 = docs-frame at P0 + docs-
> ship-gate at P2; no v2.5 P1. Seed v2.4-G measurement-protocol
> instrumentation (~30 LOC) and Seed v2.4-C Path-D P5 (~600 LOC)
> both DEFER to v2.6.
>
> Comparison anchor: `docs/v2.5-next-steps.md` §"Compare-back
> protocol". Each S-step that closes a seed MUST mark its row in
> `v2.5-next-steps.md`.

## Branch + base

- Base: `main` after v2.5 P0 (PR #185 `634e9d1`) + v2.5 SHA backfill
  (PR #186, post-merge) + this prompt-mint PR merged.
- PR target: `main`.
- Branch: `ship/v2.5-shipgate-finalize`.
- ABORT if P0 not merged at HEAD or HEAD has drifted from v2.5 P0
  base lineage.

## Pre-flight (Amendment B — memory pre-flight)

```
git fetch origin
git log --oneline origin/main -10
```

Expected: HEAD = post-v2.5-P0 lineage with cycle-tip merge SHA
`634e9d1d982a3b6071bfe78c369c4995419e2d44` reachable. If divergent,
STOP.

Memory pre-flight at P2 — light re-verify (P0 already stamped all 5
load-bearing memories FRESH 2026-05-19 in `docs/v2.5-task-plan.md`
§"Memory pre-flight stamp"). Add to P2 pre-flight:

- `project_v24_cycle_close.md` — predecessor close memory. Verify
  FRESH (minted 2026-05-19 at v2.4 P2 ship-gate; should match
  current `main` lineage).
- `feedback_glob_narrowing_no_op.md` — verify S1 wipe pattern still
  matches PR #184 closing form.
- `feedback_cycle_tolerance_masks_bugs.md` — verify both-tolerance
  test discipline language unchanged.

If any memory stale, update IN A SEPARATE PRE-P2 PR or at top of P2
PR (per Amendment B precedent). Stamp goes in P2 PR body.

## Context

v2.5 ship-gate validates the **consolidation** classification:

- **Consolidation cycle:** net production LOC ≤ **0** vs cycle-tip
  (`634e9d1d982a3b6071bfe78c369c4995419e2d44`, v2.5 P0 merge SHA).
  `WIRED_LEVER_LEDGER_COUNT` HOLD (no wire/rip this cycle; entering
  posture = 1 production / 0 soak per `docs/v2.5-task-plan.md` §2;
  Seed v2.4-H production-scope-canonical binding remains in force).

In addition:

- API-timeout invariant holds (canary line PASS).
- Sonnet pass-rate: v2.4 ship-gate landed 0.8261 (STILL DIPPED;
  FREEZE-on-content per v2.4 P1 PR #181 recommendation). v2.5 P2
  re-measures — Seed v2.4-Q 5th-cycle watch fires. ≥ 0.80 floor
  must hold (FR-OG-7 binding). 5-cycle trajectory recorded.
- Haiku pass-rate: v2.4 = 1.0 (fully recovered). v2.5 P2 confirms
  ≥ 0.85 floor holds.
- p95 latency: v2.4 = 10.518 s (Seed v2.4-E; Δ −0.07 s vs v2.3).
  v2.5 P2 = Seed v2.4-E re-measure; closure threshold ≤ 8.2 s.
- L4 + LM p95: v2.4 P2 L4 = 15.36 s (n=4), LM = 13.60 s (n=10);
  Seed v2.4-F small-n watch. v2.5 P2 re-measure.
- Seed v2.4-G CLI-timeout: PROMOTED 🟡 → 🔴 at v2.5 P0;
  instrumentation defers v2.6. P2 re-confirms promotion stance +
  defers implementation (no FROZEN-surface touches).

ADR-18 surface freeze stays in force. Amendments A–E in place; no
new amendment minted this cycle.

## References (load before starting)

- `docs/v2.5-task-plan.md` §PHASE P2 — scope sketch (minted at P0).
- `docs/v2.5-next-steps.md` — comparison anchor. Walk row-by-row at
  S10 (compare-back) → record outcome in S11 (close memory).
- `docs/prompts/v2.4-orchestration/phase-2-ship-gate-finalize.md` —
  immediate predecessor; format template.
- `docs/adr/ADR-5-latency-budget.md` — append §"v2.5 ship-gate
  baseline" if soak fires; else record skip rationale in P2 PR body.
- `docs/adr/ADR-17-soak-tiers.md` + `docs/soak-trigger-matrix.md` —
  Tier-3 invocation.
- `docs/adr/ADR-18-mvp-surface-freeze.md` §Amendments A / B / C /
  D / E.
- `docs/seed-v2.4-g-cli-timeout-audit.md` — J2 evidence audit for
  Seed v2.4-G promotion. Cited at S6.5.
- `reports/soak-20260519T*.md` — v2.4 ship-gate baseline (latest).
- `reports/alignment-eval-20260519T101249Z.md` — v2.4 baseline
  (Sonnet 0.8261 DIP; Haiku 1.0).
- `reports/sonnet-dip-v23-v24.md` — v2.4 P1 FREEZE recommendation.
- `tools/soak_driver.py` — `--ppp-auto-probe` inherited; verify
  `WIRED_LEVER_LEDGER: dict = {}` (soak-scope ledger) still empty.
- Memory: `project_v24_cycle_close.md`,
  `project_v10_p5_gate_deadlock.md`,
  `feedback_subagent_long_task_abandonment.md`,
  `feedback_monitoring_live_sessions.md`,
  `feedback_soak_cli_pool_flag.md`,
  `feedback_glob_narrowing_no_op.md`,
  `feedback_cycle_tolerance_masks_bugs.md`.

## ⚠️ CRITICAL: Do-not-touch guard

P2 touches **only**:

- `docs/adr/ADR-5-latency-budget.md` — append v2.5 baseline (or
  skip with rationale recorded in P2 PR body if consolidation
  cycle + LOC delta ≈ 0 + no latency lever wired, per
  `phase-0-cycle-frame.md` §"ADR-5 freshness" and matching v2.4 P2
  §S7 default).
- `docs/v2.5-task-plan.md` — append §"P2 close-out (this PR)".
- `docs/v2.5-backlog.md` (MINT in this PR) — append §"Carry-
  forwards from v2.5" with rows for unresolved seeds (v2.4-C, v2.4-
  G, v2.4-I..N exempt carries, v2.4-Q if FREEZE renews, plus any
  NEW v2.5 ship-gate seeds; renaming carries to v2.5-C, v2.5-G as
  needed).
- `docs/v2.5-next-steps.md` — **row-by-row mark-up only**; do NOT
  rewrite seeds. Append §"v2.5 P2 ship-gate close-out" with the
  comparison-pass result and §"NEW v2.5 ship-gate seeds (carry-
  forward to v2.6)" if any. Fill the TBD table at L319.
- `docs/v2.4-backlog.md` — annotate any resolved carry-forwards
  with `RESOLVED v2.5 PR #___` markers. **No edits to existing
  emoji** — per frozen-emoji rule.
- `CHANGELOG.md` — append `## [2.5.0]` section.
- Memory: write `project_v25_cycle_close.md` + add to `MEMORY.md`.

**No code edits expected at P2.** P0 PR #185 (docs + Seed v2.4-G
promotion record + v2.4-backlog reconciliation) shipped the cycle
surface; v2.5 has zero work phases. P2 is verification + narrative.

## Scope

### S1 — Wipe soak state

```powershell
Remove-Item -Force .bridge/soak-driver/*, .bridge/cli-pool.pids -ErrorAction SilentlyContinue
git clean -df reports/
```

(Per Seed v2.4-P PR #184 fix: the soak driver writes
`reports/soak-{iso_ts}.md` — no `tmp-` prefix — so any tracked-
baseline-safe wipe must filter by git-tracked status, not by filename
glob. `git clean -df` removes ONLY untracked files under `reports/`
by construction; tracked baseline reports stay intact. Cross-ref
`feedback_glob_narrowing_no_op.md`.)

### S1.1 — Post-wipe assertion

```powershell
$drift = git status --short --untracked-files=no reports/
if ($drift) {
  Write-Error "S1 wipe left tracked reports/ in drift state:`n$drift"
  exit 1
}
```

(Asserts S1 did not touch any tracked file under `reports/`. The
`--untracked-files=no` flag filters out stray untracked files —
e.g. scratch cassettes — that would otherwise false-fire BLOCK
before S2. Must return clean before S2 fires.)

### S2 — Fire Tier-3 soak

Per ADR-17 Tier-3 + `feedback_subagent_long_task_abandonment.md`,
launch from main thread with `run_in_background` + `ScheduleWakeup`.
**NEVER from a subagent** per memory.

```powershell
$env:BRIDGE_API_GOV = "1"
$env:BRIDGE_RL_LOGGER_ENABLED = "1"       # v10 P4 corpus continued piggyback (Run 5+)
$env:BRIDGE_CYCLE_TIP_SHA = "634e9d1d982a3b6071bfe78c369c4995419e2d44"  # v2.5 P0 merge — Amendment C anchor
$env:BRIDGE_PREDECESSOR_TAG_SHA = "08eb71d"  # v2.4.0 (narrative only)
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
- `cycle-tip (634e9d1..HEAD): +X / -Y / +Z [PASS|BLOCK]`
- `predecessor-tag (08eb71d..HEAD): +X / -Y / +Z [narrative]`

Cycle-tip line MUST show **net ≤ 0** for consolidation PASS.

### S4 — Alignment-eval

```
python tools/alignment_eval.py --ci-gate
```

Exit 0 required. Compare against v2.4 ship-gate baselines:

- **Sonnet** at v2.4 = 0.8261 (STILL DIPPED; FREEZE-on-content per
  v2.4 P1 PR #181). v2.5 P2 = Seed v2.4-Q 5th-cycle watch:
  - ≥ 0.90 → RECOVERED; FREEZE-on-content validated as transient;
    close Seed v2.4-Q at v2.5 P2; record validation.
  - 0.85 – 0.90 → STABILIZED above DIP band; FREEZE holds; record
    as v2.6 informational watch.
  - 0.80 – 0.85 → STILL DIPPED 5th cycle; mint row-level disposition
    per Seed v2.4-D §"v2.5 follow-ups" item 2 (row-16
    `ambig-block-reset-tag-16` INTERVENE → BLOCK golden update OR
    REQUIREMENTS amendment to accept BLOCK). Carry as Seed v2.5-Q.
  - < 0.80 → BLOCK ship; FR-OG-7 floor BREACH; root-cause before
    tag.
- **Haiku** at v2.4 = 1.0 (fully recovered). v2.5 disposition:
  - ≥ 0.85 → STABLE; no action.
  - 0.80 – 0.85 → BREACH; FR-OG-7 floor regression. BLOCK ship
    OR mint floor amendment.
  - < 0.80 → BLOCK ship; root-cause.

Record **5-cycle Sonnet trajectory** `v2.1 → v2.2 → v2.3 → v2.4 →
v2.5` (0.8636 → 0.9474 → 0.8182 → 0.8261 → ___) and 4-cycle Haiku
trajectory (1.0 → 0.85 → 0.9412 → 1.0 → ___) in P2 PR body.

### S5 — LOC delta verification (Amendment C cycle-tip anchor)

**Per ADR-18 Amendment C, the binding gate anchor is the cycle-tip
(P0-merge SHA `634e9d1`), NOT the predecessor tag.** Run BOTH for
the dual-anchor narrative:

```
# Binding (Amendment C) — consolidation gate:
git diff 634e9d1d982a3b6071bfe78c369c4995419e2d44..HEAD --stat -- src tests tools dashboard

# Narrative (Amendment A) vs predecessor tag v2.4.0:
git diff 08eb71d..HEAD --stat -- src tests tools dashboard
```

Gate verdict from cycle-tip (production bucket: `src/` + `tests/` +
`tools/` + `dashboard/`):

- **Consolidation: net ≤ 0 = PASS; > 0 = BLOCK.**
- Docs bucket advisory under Amendment A — not gating.

If gate BLOCK, demand deletion reconciliation pre-tag.

Cross-check: Seed 4 dual-anchor block in soak summary report should
match this manual computation byte-for-byte. Mismatch = report bug
(cross-ref Seed v2.4-O closure pattern).

### S6 — Lever-ledger HOLD verification (P2 PR body)

Per `docs/v2.5-task-plan.md` §"Operator decisions" #2, lever ledger
posture entering v2.5 = 1 production / 0 soak. **No wire/rip this
cycle.** P2 PR body records the HOLD verdict:

- Production-scope canonical (Seed v2.4-H binding from v2.4 P2;
  unchanged this cycle).
- Production count = 1 (v2.3 Seed 6 JsonlTailWorker wire).
- Soak-scope ledger `WIRED_LEVER_LEDGER: dict = {}` in
  `tools/soak_driver.py` remains empty (internal artefact).

No ADR-18 amendment required. Decision recorded verbatim in P2 PR
body alongside cycle-tip LOC delta.

### S6.5 — Seed v2.4-G promotion re-confirm

Per `docs/v2.5-task-plan.md` §"Operator decisions" #4 and J2 audit
`docs/seed-v2.4-g-cli-timeout-audit.md`:

- Seed v2.4-G PROMOTED 🟡 → 🔴 at v2.5 P0 (PR #185); measurement-
  protocol stance recorded.
- Implementation (~30 LOC tooling for per-run wall-clock
  instrumentation) DEFERS to v2.6 per consolidation gate (production-
  bucket net ≤ 0 binding).
- `src/stream_manager/cli_governance.py:49` `TIMEOUT_SECONDS = 25.0`
  STAYS FROZEN through v2.5.

P2 PR body re-confirms:

- Promotion stance unchanged.
- v2.5 P2 deferral to v2.6 P0/P1 confirmed.
- Seed v2.4-G renames to **Seed v2.5-G** in `docs/v2.5-backlog.md`
  (minted this PR).

Cross-check at S4: if alignment-eval surfaces ≥ 1 new sonnet NONE
row attributable to CLI-timeout pattern (frog7 fingerprint), record
in P2 PR body as fresh v2.5 evidence row but do NOT promote further
(Seed v2.4-G already 🔴).

### S7 — ADR-5 v2.5 baseline append (conditional)

Per `phase-0-cycle-frame.md` §"ADR-5 freshness" + v2.4 P2 §S7
default:

- **IF** consolidation cycle with LOC delta ≈ 0 AND no latency lever
  wired → **MAY skip** the v2.5 ADR-5 baseline append. Record skip
  rationale in P2 PR body.
- **ELSE** (any latency-relevant delta surfaced) → append §"v2.5
  ship-gate baseline" mirroring v2.4 format:
  - Source soak report path.
  - Per-band p50/p95 (ALLOW, L2, L3, L4, LM).
  - **Delta vs v2.4 ship-gate** (Seed v2.4-E p95 watch + Seed
    v2.4-F L4/LM watch).
    - If overall p95 ≤ 8.2 s → Seed v2.4-E CLOSES; record.
    - If overall p95 > 10.518 s + 0.5 s → 🟡 REGRESSION;
      promote Seed v2.4-E to 🔴 v2.6 seed.
    - If L4 + LM hold or recover at larger n → Seed v2.4-F
      WATCH continues OR closes per pattern.
  - Lever ledger row (HOLD at 1 production / 0 soak per S6
    decision; cite Seed v2.4-H production-scope-canonical binding).
  - Alignment-eval gate verdict + per-model rates (5-cycle Sonnet
    trajectory).
  - v10 P4 corpus piggyback delta (post-soak episode count).
  - Caveats.

**Default for v2.5 (consolidation, LOC ≈ 0, no latency lever wired):
SKIP the append with rationale.** Operator overrides at P2 fire if
soak surfaces latency-relevant data.

### S8 — CHANGELOG entry

Append `## [2.5.0]` per Keep-a-Changelog format. Cover:

- **Added** — none expected (consolidation cycle, zero work phases).
- **Changed** — Seed v2.4-G promoted 🟡 → 🔴 at P0 with measurement-
  protocol stance (instrumentation defers v2.6); v2.4-backlog
  reconciled (Seed v2.4-O RESOLVED PR #184; cap-counted reading
  7 → 5).
- **Closed** — none new this cycle (#111, #177 closed in v2.4).
- **Removed** — deletions vs **cycle-tip** (Amendment C binding;
  if any). Predecessor-tag delta listed in narrative footnote only.
- **Deferred / carry-forward** — explicit list of v2.5-next-steps
  seeds NOT closed this cycle: Seed v2.4-C (Path-D P5; v2.6),
  Seed v2.4-G (CLI-timeout impl; v2.6), Seeds v2.4-I..N (promotion-
  criterion / demand-bound exempts), plus Seed v2.4-Q disposition
  (per S4 verdict), plus any NEW v2.5 ship-gate seeds.

### S9 — Tag v2.5.0

After PR review approve + merge to main:

```
git tag -a v2.5.0 -m "v2.5.0 consolidation cycle — Seed v2.4-G promotion + v2.4-backlog reconciliation + Sonnet-DIP Seed v2.4-Q watch" <merge-SHA>
git push origin v2.5.0
```

### S10 — Compare-back pass against `docs/v2.5-next-steps.md`

**This is the comparison anchor checkpoint** — the goal-directive
binding step. Walk row-by-row through `docs/v2.5-next-steps.md`
§Seeds (v2.4-C, E, F, G, Q, I..N) + §"P0 frame":

For each row:
- Mark `[x]` and append `LANDED PR #N (<merge-SHA>)` (closed this
  cycle), OR
- Mark `[ ] DEFERRED v2.6 — <one-line rationale>`, OR
- Mark `[ ] DROPPED — <one-line rationale>` (e.g. promotion
  criterion not met, demand absent).

Expected state going into S10 (per task-plan / next-steps as of
P0 close):

| Seed | Expected disposition |
|------|----------------------|
| v2.4-C (🟡 Path-D P5)     | DEFERRED v2.6 (consolidation cycle) — renames Seed v2.5-C |
| v2.4-E (🟢 p95 watch)     | re-measure at S4/S7 |
| v2.4-F (🟡 L4/LM watch)   | re-measure at S4/S7 |
| v2.4-G (🔴 CLI timeout)   | promotion recorded P0 PR #185; impl DEFERRED v2.6 — renames Seed v2.5-G |
| v2.4-Q (🟡 Sonnet DIP)    | 5th-cycle watch — re-measure at S4; disposition per band |
| v2.4-I..N (🟢/🟡 carries) | promotion-criterion / demand-bound — carry to v2.6 |

Append §"v2.5 P2 ship-gate close-out" outcome at the end of
`docs/v2.5-next-steps.md` (fill the TBD table at L319) with the
row-by-row outcome.

### S11 — Mint close memory

Write `memory/project_v25_cycle_close.md` per template
(`project_v24_cycle_close.md`). Cover:

- Tag SHA + PR list (chronological: #185, #186, this prompt-mint PR,
  this ship-gate PR).
- Cycle type = CONSOLIDATION + LOC delta (cycle-tip binding,
  predecessor-tag narrative).
- Lever ledger status (HOLD at 1 production / 0 soak vs entering
  posture; cite S6 production-scope-canonical binding).
- v2.5-next-steps comparison-pass outcome (S10 summary).
- Sonnet-DIP Seed v2.4-Q 5th-cycle verdict (close / row-16 mint /
  FREEZE renew / BLOCK).
- Haiku floor result.
- p95 watch result (Seed v2.4-E closure or carry-forward).
- L4/LM watch result (Seed v2.4-F closure or carry-forward).
- Seed v2.4-G promotion re-confirm + v2.6 deferral.
- v10 P4 corpus delta (post-soak episode count; Run 5+).
- Carry-forwards into v2.6 (Seed v2.4-C → v2.5-C, v2.4-G → v2.5-G,
  v2.4-I..N exempts, v2.4-Q disposition, NEW ship-gate seeds).

Add index entry to `MEMORY.md`.

### S12 — Lifetime cleanup

If any v2.5 prompt file in `docs/prompts/v2.5-orchestration/` has a
lifetime clause, retire per clause. Default: prompts persist as
historical record (matches v2.0–v2.4 pattern).

### S13 — Mint-new-phase rule

If S2–S5 surfaces any must-fix item, mint a v2.5.1 patch-cycle
prompt (v1.3 / v1.6 / v1.8 corrective-cycle precedent). Default:
no follow-up; ship clean.

## DoD

- [ ] Tier-3 soak PASS verdict.
- [ ] Invariant-degrade canary PASS.
- [ ] Alignment-eval `--ci-gate` exit 0; both Sonnet + Haiku
      dispositions recorded (with 5-cycle Sonnet trajectory and
      4-cycle Haiku trajectory).
- [ ] LOC delta verified at **cycle-tip anchor** (Amendment C);
      consolidation gate net ≤ 0 = PASS.
- [ ] Seed 4 dual-anchor block in soak summary verified byte-
      identical with manual computation.
- [ ] Lever-ledger HOLD verdict recorded verbatim in P2 PR body
      (S6) with production-scope-canonical citation.
- [ ] Seed v2.4-G promotion re-confirm + v2.6 deferral recorded
      in P2 PR body (S6.5).
- [ ] ADR-5 v2.5 baseline appended OR skip rationale recorded.
- [ ] CHANGELOG `## [2.5.0]` appended.
- [ ] `v2.5.0` tag pushed.
- [ ] `project_v25_cycle_close.md` memory + MEMORY.md index.
- [ ] **`docs/v2.5-next-steps.md` row-by-row pass complete** (the
      goal-directive binding step) + §"v2.5 P2 ship-gate close-out"
      table populated.
- [ ] `docs/v2.5-backlog.md` minted with carry-forwards (Seed
      v2.5-C, v2.5-G, v2.4-I..N exempts, v2.4-Q disposition, NEW
      ship-gate seeds).
- [ ] Single PR `ship(v2.5):` against `main`.

Report back when v2.5.0 tag is pushed with: tag SHA, soak report
path, alignment dispositions (Sonnet + Haiku with trajectories),
final cycle-tip LOC delta, predecessor-tag narrative LOC delta,
v10 P4 episode count delta, Seed v2.4-Q 5th-cycle verdict, Seed
v2.4-G promotion re-confirm, and the row-by-row outcome from
`docs/v2.5-next-steps.md`.
