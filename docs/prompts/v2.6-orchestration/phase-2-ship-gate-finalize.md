# v2.6 P2 — ship-gate finalize + Seed v2.5-A diagnosis + ADR-5 v2.6 baseline (conditional) + CHANGELOG + tag

> Minted ahead-of-fire 2026-05-20 (mirrors v2.4 PR #182 + v2.5.1
> PR #188 + v2.5 PR #187 precedent — P2 prompt minted in a PM/PR
> separate from the P1 work-phase PR).
>
> Cycle type **FEATURE** (recorded at P0 PR #193 per
> `docs/v2.6-task-plan.md` §"Operator decisions recorded at P0 fire"
> #1). Production LOC soft target ≤ **1500** vs cycle-tip
> (`084137dfc8823ae5eac84755581fc0aeed6342db`); BLOCK at 1.5× =
> 2250.
>
> **One work phase this cycle.** v2.6 = P0 frame (PR #193) + P1
> instrumentation (PR #196) + P2 ship-gate (this prompt). Seed v2.5-C
> Path-D P5 deferred to v2.7 (3rd consecutive). Seed v2.5-G step (2)
> timeout-tighten + step (3) env-split both deferred to v2.7+.
>
> Comparison anchor: `docs/v2.6-next-steps.md` §"Compare-back
> protocol". Each S-step that closes a seed MUST mark its row in
> `docs/v2.6-next-steps.md`.

## Branch + base

- Base: `main` after v2.6 P0 (PR #193 `084137d`) + v2.6 SHA backfill
  (PR #194) + P1 instrumentation (PR #196 `7220b33`) + this prompt-
  mint PR merged.
- PR target: `main`.
- Branch: `feat/v2.6-p2-shipgate-finalize`.
- ABORT if v2.6 P1 not merged at HEAD or HEAD has drifted from v2.6
  P1 lineage.

## Pre-flight (Amendment B — memory pre-flight)

```
git fetch origin
git log --oneline origin/main -10
```

Expected: HEAD reachable from cycle-tip merge SHA
`084137dfc8823ae5eac84755581fc0aeed6342db` + P1 merge SHA `7220b33`.
If divergent, STOP.

Memory pre-flight at P2 — light re-verify (P0 already stamped 6
load-bearing memories FRESH 2026-05-20 in `docs/v2.6-task-plan.md`
§"Memory pre-flight stamp"). Add to P2 pre-flight:

- `project_v25_cycle_close.md` — predecessor close memory. Verify
  FRESH (minted 2026-05-20 at v2.5.1 P2 close).
- `feedback_alignment_eval_stability_window.md` — verify n=6 mandate
  trigger thresholds unchanged.
- `feedback_soak_cli_pool_flag.md` — `--cli-pool-size 2` invocation
  pattern unchanged.
- `feedback_glob_narrowing_no_op.md` — S1 wipe pattern matches
  PR #184 closing form.
- `feedback_cli_over_sdk.md` — Seed v2.5-A diagnosis uses real
  `claude -p` subprocess; the instrumented runner from P1 measures
  that path.

If any memory stale, update IN A SEPARATE PRE-P2 PR or at top of P2
PR (per Amendment B precedent). Stamp goes in P2 PR body.

## Context

v2.6 ship-gate validates the **feature** classification:

- **Feature cycle:** production LOC soft target ≤ **1500** vs cycle-
  tip (`084137d`); BLOCK at 1.5× = 2250. `WIRED_LEVER_LEDGER_COUNT`
  entering = **2 production / 0 soak** (v2.3 Seed 6 JsonlTailWorker
  wire unchanged + v2.6 P1 Seed v2.5-G step (1) wire NEW per PR
  #196). HOLD posture this P2 (no further wire/rip).

In addition:

- API-timeout invariant holds (canary line PASS).
- Sonnet pass-rate: v2.5.1 P2 = 0.9375 (RECOVERED at n=6 re-measure
  after v2.5 P2 BLOCK n=3 0.7895). v2.6 P2 re-measure — Sonnet
  trajectory now 6 cycles long. ≥ 0.80 FR-OG-7 floor must hold.
- Haiku pass-rate: v2.5.1 P2 = 1.0 (fully recovered). v2.6 P2
  confirms ≥ 0.85 floor holds.
- p95 latency: v2.5.1 P2 = 9.656 s (Seed v2.4-E; Δ −0.862 s vs v2.4
  P2 10.518 s; Δ −3.501 s vs v2.5 P2 first-soak 13.157 s outlier).
  v2.6 P2 = Seed v2.4-E re-measure; closure threshold ≤ 8.2 s.
- L4 + LM p95: v2.5.1 P2 L4 = 21.64 s (n=4; Δ +6.28 s vs v2.4 P2
  15.36 s — flagged regression at small n); LM = 25.26 s (n=10;
  Δ +11.66 s vs v2.4 P2 13.60 s — flagged regression at small n).
  v2.6 P2 re-measure (Seed v2.4-F verdict: 🔴 promote vs sample-
  variance dismissal).
- Seed v2.5-G CLI-timeout: step (1) instrumentation WIRED at v2.6
  P1 (PR #196). v2.6 P2 measures eval p99 from instrumented runner.
- **Seed v2.5-A diagnosis** (new at v2.6 P2): row `frog7-wirecli-
  module-10` re-measured with instrumented runner; verdict =
  content-drift OR timeout-attributable (see §S6.5).

ADR-18 surface freeze stays in force. Amendments A–E in place; no
new amendment minted this cycle.

## References (load before starting)

- `docs/v2.6-task-plan.md` §PHASE P2 — scope sketch (minted at P0).
- `docs/v2.6-next-steps.md` — comparison anchor. Walk row-by-row at
  S10 (compare-back) → record outcome in S11 (close memory).
- `docs/prompts/v2.5-orchestration/phase-2-ship-gate-finalize.md` —
  immediate predecessor; format template.
- `docs/prompts/v2.5.1-corrective/phase-2-shipgate-refire.md` —
  predecessor refire; n=6 escape-hatch pattern.
- `docs/adr/ADR-5-latency-budget.md` — append §"v2.6 ship-gate
  baseline" if soak fires; else record skip rationale in P2 PR body.
- `docs/adr/ADR-17-soak-tiers.md` + `docs/soak-trigger-matrix.md` —
  Tier-3 invocation.
- `docs/adr/ADR-18-mvp-surface-freeze.md` §Amendments A / B / C /
  D / E.
- `docs/seed-v2.4-g-cli-timeout-audit.md` — J2 evidence audit.
- `docs/v2.5.1-sonnet-floor-investigation.md` — Seed v2.5-A row-10
  origin (6/6 timeout at v2.5.1 P1 n=6 re-measure).
- `docs/v2.5-backlog.md` — v2.5.1 carry-forward backlog (ground
  truth at v2.5.1 P2 close).
- `reports/soak-20260520T*.md` — v2.5.1 ship-gate baseline (latest).
- `reports/alignment-eval-20260520T092222Z.md` — v2.5.1 n=6 re-
  measure (Sonnet 0.9375 RECOVERED; Haiku 1.0).
- `reports/seed-v2.5-a/row10-fixture.jsonl` (this PR's S6.5
  instrumented re-measure fixture).
- `tools/alignment_eval.py` — P1-instrumented runner (PR #196).
- `tools/soak_driver.py` — `--ppp-auto-probe` inherited; verify
  `WIRED_LEVER_LEDGER: dict = {}` (soak-scope ledger) still empty.
- Memory: `project_v25_cycle_close.md`,
  `feedback_alignment_eval_stability_window.md`,
  `feedback_subagent_long_task_abandonment.md`,
  `feedback_monitoring_live_sessions.md`,
  `feedback_soak_cli_pool_flag.md`,
  `feedback_glob_narrowing_no_op.md`,
  `feedback_cli_over_sdk.md`.

## ⚠️ CRITICAL: Do-not-touch guard

P2 touches **only**:

- `docs/adr/ADR-5-latency-budget.md` — append v2.6 baseline (or
  skip with rationale recorded in P2 PR body if feature cycle but
  no latency lever wired; Seed v2.5-G step (1) is tooling-only so
  latency surface unchanged — operator decides at fire per `phase-
  0-cycle-frame.md` §"ADR-5 freshness").
- `docs/v2.6-task-plan.md` — append §"P2 close-out (this PR)".
- `docs/v2.6-backlog.md` (MINT in this PR) — append §"Carry-
  forwards from v2.6" with rows for unresolved seeds (Seed v2.5-A
  CLOSED IF row-10 verdict resolves, else CARRY; Seed v2.5-C
  CARRY; Seed v2.4-E disposition; Seed v2.4-F disposition; Seed
  v2.5-G step (2)/(3) CARRY; v2.4-I..N exempt carries; plus any
  NEW v2.6 ship-gate seeds; renaming carries to v2.6-C, v2.6-G as
  needed).
- `docs/v2.6-next-steps.md` — **row-by-row mark-up only**; do NOT
  rewrite seeds. Append §"v2.6 P2 ship-gate close-out" with the
  comparison-pass result and §"NEW v2.6 ship-gate seeds (carry-
  forward to v2.7)" if any.
- `docs/v2.5-backlog.md` — annotate any resolved carry-forwards
  with `RESOLVED v2.6 PR #___` markers. **No edits to existing
  emoji** — per frozen-emoji rule.
- `docs/seed-v2.5-a-row10-diagnosis.md` (MINT or finalise; the
  S6.5 verdict doc — see §S6.5).
- `reports/seed-v2.5-a/row10-fixture.jsonl` — single-row golden
  fixture for the S6.5 re-measure (already committed in this PR).
- `reports/seed-v2.5-a/alignment-eval-*.{md,json}` — re-measure
  output produced by S6.5 invocation.
- `CHANGELOG.md` — append `## [2.6.0]` section.
- Memory: write `project_v26_cycle_close.md` + add to `MEMORY.md`.

**No `src/` code edits expected at P2.** P1 PR #196 shipped the
production-bucket scope (`tools/alignment_eval.py` + tests). P2 is
verification + diagnosis + narrative.

## Scope

### S1 — Wipe soak state

```powershell
Remove-Item -Force .bridge/soak-driver/*, .bridge/cli-pool.pids -ErrorAction SilentlyContinue
git clean -df reports/
```

(Per Seed v2.4-P PR #184 fix: soak driver writes
`reports/soak-{iso_ts}.md` — no `tmp-` prefix — so any tracked-
baseline-safe wipe must filter by git-tracked status, not filename
glob. `git clean -df` removes ONLY untracked under `reports/`;
tracked baseline reports stay intact. Cross-ref
`feedback_glob_narrowing_no_op.md`. The `reports/seed-v2.5-a/`
subdir is tracked once this PR commits the fixture + diagnosis;
`git clean -df` leaves it intact.)

### S1.1 — Post-wipe assertion

```powershell
$drift = git status --short --untracked-files=no reports/
if ($drift) {
  Write-Error "S1 wipe left tracked reports/ in drift state:`n$drift"
  exit 1
}
```

Must return clean before S2.

### S2 — Fire Tier-3 soak

Per ADR-17 Tier-3 + `feedback_subagent_long_task_abandonment.md`,
launch from main thread with `run_in_background` + `ScheduleWakeup`.
**NEVER from a subagent** per memory.

```powershell
$env:BRIDGE_API_GOV = "1"
$env:BRIDGE_RL_LOGGER_ENABLED = "1"
$env:BRIDGE_CYCLE_TIP_SHA = "084137dfc8823ae5eac84755581fc0aeed6342db"
$env:BRIDGE_PREDECESSOR_TAG_SHA = "c1e9070"
$env:BRIDGE_CYCLE_TYPE = "feature"
$env:BRIDGE_LOC_PATHSPEC = "src/,tests/,tools/,dashboard/"

python tools/soak_driver.py `
  --cli-pool-size 2 `
  --ppp-auto-probe `
  --total-seconds 1800 `
  --interval-seconds 20
```

`--cli-pool-size 2` is REQUIRED per `feedback_soak_cli_pool_flag.md`.

Monitor template: `feedback_monitoring_live_sessions.md`. Expected
duration ~30 min. Schedule wake-up at 35 min for completion check.

### S3 — Verify invariant-degrade canary

Soak summary closing block MUST contain
`[soak] invariant-degrade canary: PASS`. FAIL = ship blocked.

Verify Seed 4 dual-anchor block in soak report:
- `cycle-tip (084137d..HEAD): +X / -Y / +Z [PASS|BLOCK]`
- `predecessor-tag (c1e9070..HEAD): +X / -Y / +Z [narrative]`

Cycle-tip line MUST show **net ≤ 1500 LOC** for feature PASS;
BLOCK at 2250.

### S4 — Alignment-eval

Default `--runs 3` per `feedback_alignment_eval_stability_window.md`:
prior cycle v2.5.1 P2 Sonnet `pass_rate=0.9375` is ≥ 0.05 above the
0.80 FR-OG-7 floor (gap = 0.1375), so the n=6 mandate does NOT
trigger by trajectory.

```
python tools/alignment_eval.py --ci-gate
```

Exit 0 required.

**Escape-hatch: n=6 trigger conditions** (per skeleton §"Alignment-
eval n=6 stability rule" + `feedback_alignment_eval_stability_window.md`):

- If first-pass `summary.unstable_sonnet` ≥ 12 of 32 (≥ 37.5%) →
  re-run `--runs 6`.
- If any row-level Sonnet `timeout_count / runs` ≥ 0.50 at n=3 →
  re-run `--runs 6` (the v2.5.1 P1 row-10 trigger pattern).
- If unanimous-S+D (stable-and-diverges) rows ≥ 2 at n=3 → re-run
  `--runs 6`.

Record disposition per band:

- **Sonnet**:
  - ≥ 0.90 → PASS (continued RECOVERED state).
  - 0.85 – 0.90 → PASS but DIP-watch row open in v2.6 backlog.
  - 0.80 – 0.85 → PASS with row-level disposition + DIP watch.
  - < 0.80 → BLOCK ship; FR-OG-7 floor BREACH; mint v2.6.1
    corrective per S13.
- **Haiku**:
  - ≥ 0.85 → STABLE.
  - 0.80 – 0.85 → BREACH; BLOCK ship OR mint floor amendment.
  - < 0.80 → BLOCK ship.

Record **6-cycle Sonnet trajectory** `v2.1 → v2.2 → v2.3 → v2.4 →
v2.5.1 → v2.6` (0.8636 → 0.9474 → 0.8182 → 0.8261 → 0.9375 → ___)
and **5-cycle Haiku trajectory** (0.85 → 0.9412 → 1.0 → 1.0 →
1.0 → ___) in P2 PR body.

Capture wall-clock distributions from new P1 instrumentation:
- `summary.sonnet_duration_s_{p50,p95,p99,max,n}`.
- `summary.haiku_duration_s_{p50,p95,p99,max,n}`.

Record per-model p99 in P2 PR body — this is the measured-eval
p99 input that step (2) timeout-tighten requires at v2.7+ (Seed
v2.5-G step (2) deferral source).

### S5 — LOC delta verification (Amendment C cycle-tip anchor)

**Per ADR-18 Amendment C, the binding gate anchor is the cycle-tip
(P0-merge SHA `084137d`), NOT the predecessor tag.** Run BOTH:

```
# Binding (Amendment C) — feature gate:
git diff 084137dfc8823ae5eac84755581fc0aeed6342db..HEAD --stat -- src tests tools dashboard

# Narrative (Amendment A) vs predecessor tag v2.5.1:
git diff c1e9070..HEAD --stat -- src tests tools dashboard
```

Gate verdict from cycle-tip (production bucket: `src/` + `tests/` +
`tools/` + `dashboard/`):

- **Feature: net ≤ 1500 LOC soft = PASS; net > 2250 = BLOCK.**
- Docs bucket advisory under Amendment A — not gating.

Expected at P2 entering: ~147 LOC (P1 PR #196 ledger; tools +147
net / tests +84). P2 adds zero production-bucket delta beyond
docs / reports fixtures + diagnosis. Final cycle-tip net should
read ~147 production LOC.

Cross-check: Seed 4 dual-anchor block in soak summary should match
this manual computation byte-for-byte. Mismatch = report bug.

### S6 — Lever-ledger bump verification (P2 PR body)

Per `docs/v2.6-task-plan.md` §"Operator decisions" #2, lever ledger
posture:

- Entering P2 = **2 production / 0 soak** (v2.3 Seed 6
  JsonlTailWorker wire unchanged + Seed v2.5-G step (1)
  instrumentation wired at v2.6 P1 PR #196).
- Exiting P2 = **2 production / 0 soak** (HOLD; no further
  wire/rip).

P2 PR body records the BUMP + HOLD verdict:

- Production count = 2 (v2.3 Seed 6 + v2.6 P1 Seed v2.5-G step (1)).
- Soak-scope ledger `WIRED_LEVER_LEDGER: dict = {}` in
  `tools/soak_driver.py` remains empty (internal artefact).
- Production-scope canonical binding (Seed v2.4-H) unchanged.

### S6.5 — Seed v2.5-A diagnosis verdict (the headline P2 close-out)

**This is the cycle's named seed-resolution checkpoint.** v2.5.1 P1
established the row `frog7-wirecli-module-10` 6/6 Sonnet timeout
fingerprint. v2.6 P2 closes the diagnosis with the P1-instrumented
runner.

#### Procedure

1. Fixture: `reports/seed-v2.5-a/row10-fixture.jsonl` (single row,
   committed in this PR).

2. Invocation (apples-to-apples with v2.5.1 P1 n=6 evidence;
   Sonnet-only via `--candidate-only-control`):

   ```
   python -m tools.alignment_eval \
     --golden reports/seed-v2.5-a/row10-fixture.jsonl \
     --runs 6 \
     --candidate-only-control \
     --report-only \
     --reports-dir reports/seed-v2.5-a
   ```

3. Read sidecar JSON `reports/seed-v2.5-a/alignment-eval-*.json`:
   - `rows.frog7-wirecli-module-10.sonnet_runs` — verdict per run.
   - `rows.frog7-wirecli-module-10.sonnet_durations_s` — wall-
     clock per run (P1 instrumentation).
   - `rows.frog7-wirecli-module-10.sonnet_timeout_count` — count
     of runs at ≥ TIMEOUT_SECONDS − 0.5 = 24.5 s (P1 instrumentation).
   - `rows.frog7-wirecli-module-10.sonnet_majority` /
     `sonnet_stable`.

#### Verdict matrix

| sonnet_timeout_count / 6 | sonnet_majority | verdict |
|---|---|---|
| 6 (100%) | NONE (unanimous degrade) | **TIMEOUT-ATTRIBUTABLE** — row is measurement-blind; no Sonnet content judgement extractable; carries Seed v2.5-A as 🟡 watch + names Seed v2.6-A "wirecli-module timeout opacity (n=12 cumulative)"; close-out path = Seed v2.5-G step (2) timeout-tighten at v2.7+ |
| 3–5 (50–83%) | mixed or NONE | **TIMEOUT-DOMINATED** — partial degradation; record per-run breakdown; carries Seed v2.5-A with disposition narrative (mixed-state evidence) |
| 1–2 (17–33%) | non-NONE stable or unstable | **PARTIAL TIMEOUT, MOSTLY CONTENT** — record non-NONE majority + non-timeout runs as the actual Sonnet content reading; if majority matches `expected_verdict=SUGGEST` → CLOSE Seed v2.5-A (content judgement clean); else → carries as content-drift seed |
| 0 (0%) | any | **CONTENT-DRIFT (NO TIMEOUT)** — pure content judgement; if `sonnet_majority == "SUGGEST"` and `sonnet_stable == true` → CLOSE Seed v2.5-A (v2.5.1 P1 finding was a transient infrastructure artefact); if majority ≠ SUGGEST OR unstable → CARRY as content-drift seed |

**Row 3 vs row 4 stability asymmetry — rationale.** Row 3 (1–2
timeouts) accepts unstable+majority-SUGGEST as a clean close
because timeout-induced NONE returns already explain the
instability — the non-NONE runs are the actual content signal.
Row 4 (0 timeouts) requires `sonnet_stable=true` for close
because there is no timeout to absorb instability; an unstable
0-timeout reading is pure content-judgement variance and must
carry as a drift seed.

#### Verdict doc

Mint `docs/seed-v2.5-a-row10-diagnosis.md` with:

- Inputs: fixture path, invocation, P1 instrumentation lineage.
- Per-run table: run index | verdict | duration_s | timeout?
- v2.5.1 P1 vs v2.6 P2 comparison table (n=6 each):
  - `sonnet_timeout_count` delta.
  - `sonnet_majority` delta.
  - Mean / p50 / p95 wall-clock delta.
- Verdict (one of 4 matrix outcomes above).
- Disposition (CLOSE or CARRY with disposition string).
- Cross-ref to Seed v2.5-G step (2) timeout-tighten lever (carries
  into v2.7+ regardless of verdict — diagnostic outcome here informs
  but does not gate step (2)).

#### Compare-back hook

Mark `[ ] Seed v2.5-A` row in `docs/v2.6-next-steps.md` per S10
walk; fill the bracketed verdict (`___`).

### S7 — ADR-5 v2.6 baseline append (conditional)

Per `phase-0-cycle-frame.md` §"ADR-5 freshness" + v2.4 P2 §S7
default:

- **IF** feature cycle AND **no latency surface change** (Seed
  v2.5-G step (1) is tooling-only in `tools/alignment_eval.py`; no
  changes to `cli_governance.py` or pool / worker code paths) AND
  no latency lever wired → **MAY skip** the v2.6 ADR-5 baseline
  append. Record skip rationale in P2 PR body.
- **ELSE** (any latency-relevant delta surfaced) → append §"v2.6
  ship-gate baseline" mirroring v2.5 format (or v2.4 if v2.5
  skipped):
  - Source soak report path.
  - Per-band p50/p95 (ALLOW, L2, L3, L4, LM).
  - **Delta vs v2.5.1 ship-gate** (Seed v2.4-E p95 + Seed v2.4-F
    L4/LM watches):
    - If overall p95 ≤ 8.2 s → Seed v2.4-E CLOSES.
    - If overall p95 > v2.5.1's 9.656 s + 0.5 s → 🟡 REGRESSION;
      promote Seed v2.4-E.
    - If L4 + LM hold ≤ v2.4-P2 band (L4 ≤ 17 s, LM ≤ 15 s) →
      Seed v2.4-F downgrade-toward-close.
    - If L4 + LM hold elevated → promote Seed v2.4-F 🔴.
  - Lever ledger row (HOLD at 2 production / 0 soak per S6).
  - Alignment-eval gate verdict + per-model rates + **NEW: eval
    wall-clock distributions p50/p95/p99 per model** (P1
    instrumentation).
  - v10 P4 corpus piggyback delta.
  - Caveats.

**Default for v2.6 (feature cycle but tooling-only lever, no
latency surface change): SKIP the append with rationale.** Operator
overrides at P2 fire if soak surfaces latency-relevant data.

### S8 — CHANGELOG entry

Append `## [2.6.0]` per Keep-a-Changelog format. Cover:

- **Added** — Seed v2.5-G step (1): per-run wall-clock
  instrumentation in `tools/alignment_eval.py` (PR #196). New JSON
  sidecar / MD sections for p50/p95/p99/max/n per model; per-row
  `sonnet_durations_s` + `sonnet_timeout_count` + Haiku peers.
- **Changed** — `evaluate_row` return shape `list[str]` →
  `tuple[list[str], list[float]]` (internal helper; no CLI surface
  change).
- **Closed** — Seed v2.5-A diagnosis verdict (per §S6.5 verdict
  matrix outcome).
- **Removed** — deletions vs cycle-tip (Amendment C binding; if
  any). Predecessor-tag delta listed in narrative footnote only.
- **Deferred / carry-forward** — Seed v2.5-G step (2) timeout-
  tighten (v2.7+ pending measured eval p99 from S4); Seed v2.5-G
  step (3) env-split (v2.7+); Seed v2.5-C Path-D P5 (v2.7;
  becomes Seed v2.6-C); Seeds v2.4-I..N (promotion-criterion /
  demand-bound exempts); Seed v2.4-E + Seed v2.4-F per S7 disposition;
  Seed v2.5-A IF carry-forward per S6.5 verdict; **Seed v2.6-A**
  (row-10 Sonnet content drift vs golden expected_verdict, IF
  S6.5 verdict is CONTENT-DRIFT / PARTIAL-TIMEOUT-MOSTLY-CONTENT);
  **Seed v2.6-A-T** (row-10 timeout-boundary watch, IF S6.5
  surfaces any timeout count and Seed v2.5-G step (2) has not
  yet landed).

### S9 — Tag v2.6.0

After PR review approve + merge to main:

```
git tag -a v2.6.0 -m "v2.6.0 feature cycle — Seed v2.5-G step (1) CLI-timeout instrumentation + Seed v2.5-A diagnosis verdict (___)" <merge-SHA>
git push origin v2.6.0
```

Fill the `___` placeholder with the §S6.5 verdict string.

### S10 — Compare-back pass against `docs/v2.6-next-steps.md`

**This is the comparison anchor checkpoint** — the goal-directive
binding step. Walk row-by-row through `docs/v2.6-next-steps.md`
§Seeds + §"Fire-order" + §"P0 frame":

For each row:
- Mark `[x]` and append `LANDED PR #N (<merge-SHA>)`, OR
- Mark `[ ] DEFERRED v2.7 — <one-line rationale>`, OR
- Mark `[ ] DROPPED — <one-line rationale>`.

Expected state going into S10 (per task-plan / next-steps as of
P1 close):

| Seed | Expected disposition |
|------|----------------------|
| v2.5-A (🟡 row-10 100% timeout) | RESOLVED per §S6.5 verdict matrix (CLOSE or CARRY w/ disposition) |
| v2.5-C (🟡 Path-D P5)            | DEFERRED v2.7 (3rd consecutive) — renames Seed v2.6-C |
| v2.4-E (🟢 p95 watch)            | re-measure at S4/S7 (closure ≤ 8.2 s; downgrade ≤ 10 s) |
| v2.4-F (🟡 L4/LM watch)          | re-measure at S4/S7 verdict (downgrade / hold 🟡 / promote 🔴) |
| v2.5-G (🔴 CLI timeout)          | step (1) LANDED PR #196; steps (2)+(3) DEFERRED v2.7+; renames Seed v2.6-G IF step (2) carries |
| v2.4-I..N (🟢/🟡 carries)        | promotion-criterion / demand-bound — carry to v2.7 |

Append §"v2.6 P2 ship-gate close-out" outcome at the end of
`docs/v2.6-next-steps.md` with the row-by-row outcome.

### S11 — Mint close memory

Write `memory/project_v26_cycle_close.md` per template
(`project_v25_cycle_close.md`). Cover:

- Tag SHA + PR list (chronological: #191, #192, #193, #194, #195,
  #196, this prompt-mint PR, this ship-gate PR).
- Cycle type = FEATURE + LOC delta (cycle-tip binding,
  predecessor-tag narrative; expected ~147 production LOC).
- Lever ledger status (BUMP 1 → 2 at P1 PR #196; HOLD at P2;
  exiting posture = 2 production / 0 soak; cite Seed v2.4-H
  production-scope-canonical binding).
- v2.6-next-steps comparison-pass outcome (S10 summary).
- **Seed v2.5-A diagnosis verdict** (the headline cycle outcome).
- Sonnet pass-rate (6-cycle trajectory).
- Haiku floor result (5-cycle trajectory).
- Wall-clock distributions p50/p95/p99 per model (NEW P1
  instrumentation surface).
- p95 watch result (Seed v2.4-E closure or carry-forward).
- L4/LM watch result (Seed v2.4-F closure or carry-forward).
- Seed v2.5-G step (2) deferral rationale + measured eval p99
  input now in hand.
- v10 P4 corpus delta (post-soak episode count).
- Carry-forwards into v2.7 (Seed v2.5-A IF carry, Seed v2.6-C,
  Seed v2.6-G step (2)/(3), v2.4-I..N exempts, Seed v2.4-E + v2.4-F
  dispositions, NEW ship-gate seeds).

Add index entry to `MEMORY.md`.

### S12 — Lifetime cleanup

Default: prompts persist as historical record (matches v2.0–v2.5
pattern).

### S13 — Mint-new-phase rule

If S2–S6.5 surfaces any must-fix item, mint a v2.6.1 patch-cycle
prompt (v1.3/v1.6/v1.8/v2.5.1 corrective-cycle precedent). Default:
no follow-up; ship clean.

If Seed v2.5-A verdict is TIMEOUT-ATTRIBUTABLE 100%/100% (same as
v2.5.1 P1) → no v2.6.1 corrective required; this is the expected
outcome that promotes Seed v2.5-G step (2) priority at v2.7 P0.

## DoD

- [ ] Tier-3 soak PASS verdict.
- [ ] Invariant-degrade canary PASS.
- [ ] Alignment-eval `--ci-gate` exit 0; both Sonnet + Haiku
      dispositions recorded (6-cycle Sonnet + 5-cycle Haiku
      trajectories).
- [ ] LOC delta verified at **cycle-tip anchor** (Amendment C);
      feature gate net ≤ 1500 soft = PASS (expected ~147
      production LOC).
- [ ] Seed 4 dual-anchor block in soak summary verified byte-
      identical with manual computation.
- [ ] Lever-ledger BUMP 1 → 2 confirmed at P1 (PR #196); P2 HOLD
      recorded verbatim in P2 PR body (S6).
- [ ] **Seed v2.5-A diagnosis verdict** rendered per §S6.5
      matrix; `docs/seed-v2.5-a-row10-diagnosis.md` minted.
- [ ] **Wall-clock p50/p95/p99 per model** recorded in P2 PR body
      (new P1 instrumentation surface).
- [ ] ADR-5 v2.6 baseline appended OR skip rationale recorded.
- [ ] CHANGELOG `## [2.6.0]` appended.
- [ ] `v2.6.0` tag pushed.
- [ ] `project_v26_cycle_close.md` memory + MEMORY.md index.
- [ ] **`docs/v2.6-next-steps.md` row-by-row pass complete** + §"v2.6
      P2 ship-gate close-out" table populated.
- [ ] `docs/v2.6-backlog.md` minted with carry-forwards.
- [ ] Single PR `ship(v2.6):` against `main`.

Report back when v2.6.0 tag is pushed with: tag SHA, soak report
path, alignment dispositions (Sonnet + Haiku with trajectories),
final cycle-tip LOC delta, predecessor-tag narrative LOC delta,
v10 P4 episode count delta, **Seed v2.5-A verdict**, Seed v2.5-G
step (2) p99 input value, Seed v2.4-E + v2.4-F verdicts, and the
row-by-row outcome from `docs/v2.6-next-steps.md`.
