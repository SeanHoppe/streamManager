You are implementing **Phase P4 — v2.1 ship-gate + ADR-5 v2.1 baseline + CHANGELOG + tag** for the streamManager v2.1 cycle (PPP audit harness). v2.1 P1 (PR #138) shipped Layer 1 stream disambiguation, P1a (PR #141) drained P1 follow-ups, P2 (PR #143) shipped Layer 2 canary echo, P3 (PR #145) shipped Layer 3 negative-control + self-monitor hard guard, and P3a (PR #147) drained the P3 caveman-review (R-decoy-idem 🔴 + R-decoy-bus-sig + R-decoy-test-gap + R-loc-amend) and recorded the retroactive ADR-18 Rule 4 LOC amendment for the P3 overage. With all three layers + their drain sub-phases merged, P4 closes the cycle: Tier 3 soak with PPP auto-probe default-on, alignment-eval gate, ADR-5 baseline append, CHANGELOG v2.1.0 entry, v2.1.0 tag, and cycle-close memory mint.

## Branch + base

- Base: `main` (after v2.1 P1, P1a, P2, P3, P3a all merged — confirm at start).
- PR target: `main`.
- Branch: `ship/v2.1-shipgate-finalize` (or operator's choice).
- If P1 / P1a / P2 / P3 / P3a not merged, ABORT.

## Pre-flight (run first, before any S-step)

```
git fetch origin
git log --oneline origin/main -10
```

Expected top-of-main commits (most recent first):
- `b064dd4` fix(ppp): v2.1 P3a — drain PR #145 caveman-review + ADR-18 Rule 4 LOC amendment (#147)
- `0fe3282` docs(v2.1 P3a): mint pre-merge tightening prompt for PR #147 (#148)
- `cc4ce8c` docs(v2.1 P3a): mint P3 review-drain scope + phase prompt (#146)
- `0f19b9c` feat(ppp): v2.1 P3 — PPP Layer 3 negative-control + self-monitor hard guard (M1–M6) (#145)
- `b5c4f4c` docs(v2.1 P3): mint Layer 3 negative-control + self-monitor hard guard phase prompt (#144)
- `4b755f6` feat(ppp): v2.1 P2 — PPP Layer 2 canary echo (M1–M6) (#143)
- `863175e` feat(ppp): v2.1 P1a — drain P1 follow-ups (R14 + R16 + R-cassette-idx + R-conftest) (#141)
- `531714c` feat(ppp): v2.1 P1 PPP Layer 1 stream disambiguation (#138)

If the head set diverges, STOP and reconcile before opening the ship branch.

## Context

v2.1 ship-gate validates the feature cycle's two guarantees:

1. **PPP audit harness ships end-to-end** — Layer 1 (stream disambiguation, FR-PPP-1..7) + Layer 2 (canary echo, FR-PPP-8..11) + Layer 3 (negative-control + self-monitor hard guard, FR-PPP-12..14) all wire through `/api/sm-probe`, `/api/sm-decoy/register`, the cassette pump, and the dashboard panel. Tier 3 soak with `--ppp-auto-probe` fires at least one probe end-to-end during the gate.
2. **PPP did not regress alignment or latency** — alignment-eval `--ci-gate` exit 0; Tier 3 soak verdict PASS; ADR-5 budgets respected. PPP envelopes are sparse (probe cadence ≥ 30 min during soak; canary observer is passive read-after-`_is_sm_originated`-filter; decoy detector is no-op until a registered path is parsed). None of the three layers add hot-path work to the governance request path.

ADR-18 surface freeze stays in force. v2.1 cycle is **feature, no LOC cap** per `docs/v2.1-task-plan.md` §"LOC budget". The retroactive Rule 4 amendment landed in P3a (`docs/v2.1-p3-scope.md` §LOC tracker) covers the P3 overage; P4 records no new amendments. `WIRED_LEVER_LEDGER` remains empty (PPP envelope pairs are additive, not levers) — DORMANT-N gate stays inert.

## References (load before starting)

- `docs/v2.1-task-plan.md` §"PHASE P4 — v2.1 ship-gate" — scope sketch the P3 close-out promised to elaborate
- `docs/v2.1-p1-scope.md` / `docs/v2.1-p2-scope.md` / `docs/v2.1-p3-scope.md` / `docs/v2.1-p3a-scope.md` — per-phase scope docs (read for FR coverage when writing the CHANGELOG entry)
- `docs/v1.7-backlog.md` §"🟢 PPP audit harness — Provenance Probe Protocol" — original seed; P4 closes via tail-of-entry graduation note (NOT an emoji edit; frozen-emoji convention from `docs/v1.3-backlog.md`)
- `docs/v2.1-backlog.md` — 6 seeds at hard cap; P4 closes PPP seed and decides whether to seed v2.2 from any P4-surfaced findings
- `docs/adr/ADR-18-mvp-surface-freeze.md` §"Cycle-discipline rules" + §"Decommissioned" + §"WIRED_LEVER_LEDGER_COUNT: 0" HTML comment
- `docs/adr/ADR-5-latency-budget.md` — append §"v2.1 ship-gate baseline" section
- `docs/adr/ADR-17-soak-tier-amendment.md` + `docs/soak-trigger-matrix.md` — Tier 3 invocation
- `docs/prompts/v2.0-orchestration/phase-4-ship-gate-finalize.md` — immediate predecessor; format reference for S1–S12 structure
- `reports/soak-20260507T174051Z.md` — v2.0 ship-gate baseline (compare against)
- `tools/soak_driver.py` §`WIRED_LEVER_LEDGER` (line ~474) + §`_format_lever_ledger` + §`--ppp-auto-probe` flag — auto-probe cadence already implemented at P1; P4 flips default
- `tools/alignment_eval.py` — `--ci-gate` invocation unchanged
- `REQUIREMENTS.md` §FR-PPP-1..14 — all 14 PPP requirements ship-gate'd by this phase
- Memory: `project_v20_cycle_close.md` (template for the v2.1 close-out memory), `feedback_subagent_long_task_abandonment.md` (soak launch discipline), `feedback_monitoring_live_sessions.md` (soak monitor template), `feedback_subagent_stale_mental_model.md` (sub-cycle close-out diff guard), `feedback_cross_pr_seam_review.md`, `feedback_cassette_must_cover_new_envelopes.md`, `feedback_parallel_undisclosed_deviations.md`, `project_v21_cycle_frame.md` (cycle-open frame; P4 writes the close)

## ⚠️ CRITICAL: Do-not-touch guard

ADR-18 surface freeze still in force at P4. P4 touches **only**:

- `tools/soak_driver.py` — flip `--ppp-auto-probe` default OFF → ON. Additive default change per FR-PPP-1 ("MAY emit one on unattended soak ... default OFF" → "default ON at v2.1 ship-gate"). Update the flag's help text accordingly. **No other behavioural changes**; no envelope-schema edits; no FROZEN-symbol edits; no `_last_phase_timings_ms` key edits.
- `docs/adr/ADR-5-latency-budget.md` — append v2.1 ship-gate baseline section (additive at file tail).
- `docs/v2.1-task-plan.md` — append §"P4 close-out (this PR)" subsection noting actual outcomes; do NOT rewrite earlier sections.
- `docs/v1.7-backlog.md` — append graduation note under the existing 🟢 PPP audit harness entry (tail-of-entry; emoji stays 🟢 per frozen-emoji rule).
- `docs/v2.1-backlog.md` — append §"Carry-forwards from v2.1" subsection and §"P4 close-out disposition" subsection ONLY IF the JsonlTailWorker.start() decision lands as "record dormancy + seed v2.2" (see S8). No edits to existing 6 seeds.
- `CHANGELOG.md` — append `## [2.1.0]` section.
- `REQUIREMENTS.md` — NO edits expected at P4 (FR-PPP-1..14 already landed across P1/P2/P3; P4 does not add new FRs).
- `docs/adr/ADR-18-mvp-surface-freeze.md` — NO edits expected at P4 (the P3 Rule 4 amendment is already recorded in `docs/v2.1-p3-scope.md` §LOC tracker per the P3a R-loc-amend resolution). `WIRED_LEVER_LEDGER_COUNT: 0` HTML comment stays at 0.
- `tests/test_dormant_ledger_consistency.py` — should still pass unchanged (ledger empty, count comment 0).

**FROZEN seams reminder:** all v1.1–v2.0 envelope types, all `desktop_command` allowlist kinds, all WAL tables that pre-date v2.1, all `_last_phase_timings_ms` keys, `CliPool.__init__` signature defaults, `cli_governance` contract — unchanged.

**Pre-flight grep guard** (run BEFORE editing the soak driver default):

```
grep -nE 'ppp-auto-probe|ppp_auto_probe|PPP_AUTO_PROBE' tools/ src/ docs/ tests/
```

Hit set should show the flag wired across `tools/soak_driver.py` (definition + read site) plus any FR-PPP-1 reference in `REQUIREMENTS.md`. P4 changes the default value in ONE place (the argparse default) plus its help-text string; the consumer site is unchanged.

## Scope

### S1 — Wipe soak state

Per `docs/prompts/v1.6-shipgate/S1-wipe-soak-state.md` pattern (carried forward through v1.7 → v1.8 → v1.9 → v2.0). Clean `.bridge/` and `reports/soak-*` working state on the ship branch's worktree so the Tier 3 run lands in a clean tree.

```
rm -rf .bridge/                       # PowerShell: Remove-Item -Recurse -Force .bridge
# (do not delete the reports/ directory — git tracks prior soaks)
```

### S2 — Flip `--ppp-auto-probe` default to ON

Edit `tools/soak_driver.py` argparse: change `--ppp-auto-probe` default from `False` to `True`. Update the help string to reflect the v2.1 ship-gate default flip. Keep the corresponding `--no-ppp-auto-probe` (or equivalent disable form) available so legacy CI / Tier 1.5 smokes can opt out if needed. If the existing flag is a simple `action="store_true"` (no built-in disable form), add a paired `--no-ppp-auto-probe` `action="store_false"` with the same `dest` and document the pair in the help text.

Net LOC delta: ≤ 5. This is a default flip plus help-text update plus optional `--no-` mirror flag, nothing more.

After the edit, run a quick `pytest tests/test_soak_driver*.py` (or whichever test module covers the soak-driver argparse surface) to confirm no test was pinning the default to `False`. If any test relied on the OFF default, update it to assert the new ON default (these are P4-legitimate test edits because they record the ship-gate default flip — not P1/P2/P3 feature edits).

### S3 — Run Tier 3 ship-gate soak

Launch from the **main thread** (per `feedback_subagent_long_task_abandonment.md` — never from a subagent), via `run_in_background` + `ScheduleWakeup`, and monitor with the template from `feedback_monitoring_live_sessions.md` (PASS / FAIL / panic / PID-exit / 0-byte file is OK):

```
python tools/soak_driver.py --cli-pool-size 2
```

(`--ppp-auto-probe` is now the default; do NOT pass it explicitly — the absence of the flag exercises the flipped default. Do NOT pass `--worker-recycle-every-n` — v2.0 P1 falsified that lever.)

Wall-clock: ~32 min. Auto-probe cadence: 30 min ⇒ at least one PPP probe fires during the gate. Confirm in the soak report that an `audit.probe` envelope was emitted and acked (or expired) at least once.

**Soak-launch checklist** (per `feedback_soak_cli_pool_flag.md`):
- [ ] `--cli-pool-size 2` passed (default 0 silently reproduces v1.0 cold-start regression)
- [ ] `--worker-recycle-every-n` NOT passed (lever ripped in v2.0 P3)
- [ ] `--ppp-auto-probe` NOT passed (default-on; ride the new default)
- [ ] Launched via `run_in_background` from main thread
- [ ] `ScheduleWakeup` armed for ~35 min from launch

### S4 — Pull soak report

Verify `reports/soak-<UTC-timestamp>.md` written. Extract:

- Overall p95 (compare against v2.0 ship `reports/soak-20260507T174051Z.md`)
- ALLOW p95
- L2/L3 p95
- L4 alignment p95
- LM p95
- `cli_pool_send_ms` p95 (v1.7 lever surface, still the dominant latency driver per `project_v17_cycle_close.md`)
- Lever ledger subsection — must read `Lever ledger: 0 wired levers — DORMANT-N gate inert` (the v2.0 P4 codification format; unchanged at v2.1)
- PPP probe activity: at least one `audit.probe` emit + ack (or canary-timeout) appearing in the soak summary or in the bus envelope counts

If `Lever ledger` line is missing or shows a non-zero count, ABORT — either the soak driver regressed or someone re-wired a lever silently. Investigate before proceeding.

### S5 — Compute LOC delta vs v2.0.0

```
git --no-pager diff 401ae47..HEAD --stat -- src tests tools dashboard | tail -1
```

v2.1 is a **feature cycle, no hard cap** per `docs/v2.1-task-plan.md` §"LOC budget". Record the exact net add in the PR description and in the cycle-close memory; do not gate on the number. Expected order of magnitude: ~+1500..+3000 LOC (sum of P1 ~700 + P1a ~150 + P2 ~400 + P3 ~1071 + P3a ~88 + P4 ~5 — actuals will diverge from the per-phase soft caps; the P3 line exceeded its 300-soft-cap by ~770 LOC and earned the retroactive ADR-18 Rule 4 amendment recorded at P3a R-loc-amend, so v2.1 cycle LOC is materially higher than the task-plan §"Total v2.1 ~750–1400 LOC" estimate).

**Operator anchor (write into the PR description and memory):** v1.9 cycle ~+2800 LOC; v2.0 cycle −1031 LOC; v2.1 cycle [actual]. Frames the precedent for future feature-cycle LOC ceilings (the §"Feature-cycle LOC ceiling — POLICY GAP" cross-cutting risk from `docs/v2.1-task-plan.md`).

If the delta against v2.0.0 is anomalously low (< +500) or anomalously high (> +4000), audit before merging — neither bound is hard, but both are far enough from the cycle's known shape that they warrant a manual check.

### S6 — Run alignment-eval `--ci-gate`

```
python tools/alignment_eval.py --ci-gate
```

Exit 0 required. Sonnet ≥ 0.95, Haiku ≥ 0.85, 0 FR-OG-7 regressions, 0 Haiku regressions vs Sonnet (the v1.9 / v2.0 gate floor; unchanged at v2.1).

PPP envelopes are advisory and not on the governance hot path — alignment should not move. If alignment regresses non-trivially (e.g. sonnet < 0.95 or any FR-OG-7 regression), STOP. Investigate which PPP layer changed corpus-evaluation behaviour — most likely culprit is unintentional logging or envelope-fanout in a band whose alignment fixture replays bus envelopes.

### S7 — Update ADR-5

Append §"v2.1 ship-gate baseline" section to `docs/adr/ADR-5-latency-budget.md`. Mirror the v2.0 section format. Include:

- Source: `reports/soak-<timestamp>.md`
- Date
- Ship SHA (will be the merge commit of THIS PR; record after merge)
- Driver: `--cli-pool-size 2`, `--ppp-auto-probe` default-on (no explicit flag)
- Per-band p95, RSS drift, alignment-eval results
- PPP cadence note: ≥ 1 `audit.probe` fired during 32-min Tier 3 soak; sparse-cadence reasoning preserves p95 (the 30-min auto-probe cadence is 1-2 events per soak, well below the per-band n=60 floor that drives p95)
- LOC delta vs v2.0.0
- Caveats (any per-band tail violations at small n; LM trend movement; any PPP envelope-count anomalies)

### S8 — Decide JsonlTailWorker.start() disposition

**Background (from `docs/v2.1-p3-scope.md` §R4):** the P3 decoy hook is exercised today via direct calls in tests (matching the P2 `_process_line` test pattern). `JsonlTailWorker.start()` itself is dormant in production — no `src/` or `dashboard/` call site invokes it; only `tests/` instantiate the class. The P3 scope made this disclosure and deferred the disposition to P4: either wire the worker into the production startup sequence, or record the dormancy explicitly and seed v2.2 with the wiring task.

**Decision criteria (operator-facing):**

- **Option A — Wire `JsonlTailWorker.start()` in production now.** Suitable if: there is a clear, low-risk call site (dashboard FastAPI startup hook, or `streamManager`'s entry point), the start parameters (`session_id`, `project_slug`) have an unambiguous resolution path at startup time, and the LOC cost is small (< 30 LOC). Production wiring extends P4 from a docs-only ship-gate to a code-bearing ship-gate; bring the wiring's call site under cassette/soak coverage to confirm the canary timeout sweep and decoy detector fire in the production loop, not just in tests. **If picked, document the wiring in the PR body's `## Disclosed non-additive seam hunk` block** (the worker thread becoming live in production is a non-additive runtime-shape change even though the API surface is unchanged).

- **Option B — Record dormancy + seed v2.2.** Suitable if: the start-call site has unresolved dependencies (e.g. `SM_OWN_SESSION_ID` env-var wiring at startup is operator-managed today and would need a startup-time resolution path), the wiring would push v2.1 cycle LOC beyond a comfortable feature-cycle ceiling, or the operator wants the cycle to close on the docs-only ship-gate pattern that v2.0 P4 established. **If picked**, append a 🟢 entry to `docs/v2.2-backlog.md` (or `docs/v2.1-backlog.md` §"Carry-forwards from v2.1" — operator's call which file holds it; the §"Carry-forwards" subsection is the closer match because v2.1 itself is the cycle that left it dormant), and reference the dormancy in `project_v21_cycle_close.md`.

**Default disposition (apply if operator does not direct otherwise at P4 kickoff):** **Option B**. Rationale: v2.1 already shipped a load-bearing feature surface across three layers + two drain sub-phases; closing P4 on a docs-only ship-gate matches the v2.0 P4 pattern and avoids dragging a startup-wiring decision into the ship branch. The cassette already exercises the decoy path via direct calls per `feedback_cassette_must_cover_new_envelopes.md` so the FR-PPP-13/14 surface is not regression-blind.

**Record the decision** in the PR body (which option, why) and in `project_v21_cycle_close.md`. If Option B, add the seed to `docs/v2.1-backlog.md` §"Carry-forwards from v2.1" with concrete pointers (call-site candidates inside `dashboard/server.py` startup or `streamManager` entry, `SM_OWN_SESSION_ID` resolution path, expected LOC).

### S9 — Update CHANGELOG.md

Append `## [2.1.0] — <date>` section. Format mirrors v2.0.0 entry. Highlights:

- PPP audit harness shipped end-to-end (FR-PPP-1..14): Layer 1 (stream disambiguation, signed assertions, HITL panel row variant); Layer 2 (canary echo, 10-s timeout sweep, Layer-1 re-fire); Layer 3 (decoy registration + hallucination detector + self-monitor hard guard)
- `audit.probe` / `audit.probe_ack` / `audit.canary_emit` / `audit.canary_observed` / `audit.probe_failure` / `audit.hallucination_detected` envelopes added (additive; FROZEN-seam-compatible)
- WAL tables added: `provenance_assertions` (Layer 1), `provenance_decoys` (Layer 3)
- `audit_probe` `desktop_command` kind + `audit_probe` HITL trigger reason
- `--ppp-auto-probe` default flipped ON at v2.1 ship-gate
- `session_watcher.build_audit_probe_candidates` `sm_brain_id` graduated to mandatory (P3 self-monitor hard guard; P1a defense-in-depth preview elevated)
- P3a retroactive ADR-18 Rule 4 amendment (P3 LOC overage 1071 vs 700 cap; recorded at `docs/v2.1-p3-scope.md` §LOC tracker per the P1 → P1a precedent)
- P3a pre-merge tightening of caveman-review findings on PR #147 (R-decoy-idem 🔴 + R-decoy-bus-sig + R-decoy-test-gap + 3 ❓/🔵 defensive-code drain commits)
- Net LOC delta cycle-wide (cite figure from S5)
- `WIRED_LEVER_LEDGER` remains empty; DORMANT-N gate stays inert

### S10 — Open ship PR

Conventional commit prefix: `chore(release):` or `ship(v2.1):` per the operator's repo convention (v2.0 used `chore(release):` per the v2.0.0 tag commit). PR title: `ship(v2.1): v2.1.0 — PPP audit harness ship-gate`.

PR body must include:
- Soak verdict + report path
- Alignment-eval verdict (sonnet / haiku / FR-OG-7)
- LOC delta vs v2.0.0
- PPP probe fire count during soak
- Lever ledger state (empty; inert)
- JsonlTailWorker disposition (Option A or B; rationale)
- v2.2 backlog seed list (if any)
- Cross-PR seam review note (per `feedback_cross_pr_seam_review.md`): all PPP writer↔reader pairs from P1/P2/P3 audited against the design tables in `docs/v2.1-p1-scope.md` / `docs/v2.1-p2-scope.md` / `docs/v2.1-p3-scope.md` before merge

### S11 — Merge + tag

Squash-merge ship PR. v2.1.0 tag on the merge commit:

```
git tag -a v2.1.0 <merge-sha> -m "v2.1.0 — PPP audit harness"
git push origin v2.1.0
```

Verify the tag pushes cleanly (no force; tag does not exist on remote yet).

### S12 — Memory mint

Mint `project_v21_cycle_close.md` (and update `MEMORY.md` index) per the existing `project_v20_cycle_close.md` template. Include:

- Ship SHA + v2.1.0 tag SHA
- ADR-18 status: surface freeze + Rule 4 amendment recorded at P3a (no new amendments at P4)
- P1/P1a/P2/P3/P3a layer-by-layer summary + FR coverage
- Cycle LOC delta (cite figure)
- Lever ledger final state (still 0; DORMANT-N gate still inert)
- JsonlTailWorker disposition (Option A wired / Option B dormant + v2.2 seeded)
- PPP audit harness 🟢 seed graduation note path (v1.7-backlog tail-of-entry note)
- Cross-cutting risk closures (from `docs/v2.1-task-plan.md` §"Cross-cutting risks"): #1 stale-memory recurrence (mitigated at P0), #2 cassette coverage drift (held; cassette extended same-cycle in P1/P2/P3), #3 self-monitor leak (closed at P3 mandatory kwarg graduation), #4 sub-phase escape hatch (held; P1→P1a + P3→P3a both followed cycle-frame amendment path), #5 probe transport coupling (resolved at P1 kickoff; record which path: HTTP or direct-bus), #6 P3 candidate-discovery surface (closed at P3 hard-guard scope), #7 feature-cycle LOC ceiling (POLICY GAP carries forward to v2.2 as an ADR-18 amendment seed)
- v2.2 backlog handoff (seed list if any)

Update `MEMORY.md` index with the new memory line.

### S13 — Close 🟢 PPP audit harness seed in v1.7 backlog

Append a tail-of-entry graduation note under the 🟢 PPP audit harness entry in `docs/v1.7-backlog.md`:

```
**v2.1.0 graduation note (<UTC-date>):** PPP audit harness shipped
end-to-end across v2.1 P1/P1a/P2/P3/P3a at tag v2.1.0 (SHA `<merge-sha>`).
Layer 1 (PR #138, #141), Layer 2 (PR #143), Layer 3 (PR #145, #147).
FR-PPP-1..14 in REQUIREMENTS.md. Seed graduates; emoji stays 🟢 per
frozen-emoji convention (`docs/v1.3-backlog.md`).
```

### S14 — Seed v2.2 backlog (only if v2.1 surfaced new findings)

If S8 picked Option B, the JsonlTailWorker dormancy gets seeded into `docs/v2.1-backlog.md` §"Carry-forwards from v2.1" (NOT a fresh file). If P4 surfaces other new findings (PPP envelope-count anomaly in soak, an alignment-eval observation worth tracking, a feature-cycle-LOC-ceiling ADR amendment candidate), file each as a 🟢 seed in `docs/v2.1-backlog.md` §"Carry-forwards from v2.1" subsection. Respect ADR-18 Rule 5 backlog hard cap — v2.1-backlog is already at 6 seeds; the carry-forward subsection is allowed because it tracks cycle-handoff items, not fresh backlog growth.

A `docs/v2.2-backlog.md` mint is **not** P4's responsibility. The next cycle's P0 mints its own backlog file when it opens (matches the v2.0 P4 → v2.1 P0 pattern where `docs/v2.1-backlog.md` minted at v2.0 P4 §S8 but `docs/v2.2-backlog.md` waits for v2.2 P0).

## Total LOC delta (P4-only)

Estimate: ≤ 10 net add in `src tests tools dashboard` (the `--ppp-auto-probe` default flip + optional paired `--no-` flag + any test-default updates). Docs deltas are unbounded but additive (ADR-5 section, CHANGELOG entry, v1.7-backlog graduation note, task-plan close-out subsection, cycle-close memory file). Cycle-wide LOC delta (S5) is the operator-anchor figure.

## DOD

- [ ] Pre-flight log shows all expected v2.1 PR merges on `main` (P1, P1a, P2, P3, P3a)
- [ ] `tools/soak_driver.py` `--ppp-auto-probe` default flipped to ON; help text updated; optional `--no-ppp-auto-probe` mirror flag added if not already present
- [ ] Tier 3 soak verdict PASS (`--cli-pool-size 2`, `--ppp-auto-probe` default-on)
- [ ] Soak report shows `Lever ledger: 0 wired levers — DORMANT-N gate inert`
- [ ] Soak report shows ≥ 1 `audit.probe` envelope fired during the 32-min run
- [ ] Soak report has no PPP-related regression (no envelope-fanout exception, no canary-sweep crash, no decoy-detector exception)
- [ ] Alignment-eval `--ci-gate` exit 0; sonnet ≥ 0.95, haiku ≥ 0.85, 0 FR-OG-7 regressions, 0 Haiku regressions vs Sonnet
- [ ] LOC delta vs `401ae47` computed and recorded (no hard ceiling; record exact figure)
- [ ] ADR-5 v2.1 baseline section appended (additive at file tail)
- [ ] CHANGELOG.md v2.1.0 entry written
- [ ] `docs/v2.1-task-plan.md` §"P4 close-out (this PR)" subsection appended
- [ ] JsonlTailWorker.start() disposition decided + recorded (Option A or B); seed in `docs/v2.1-backlog.md` §"Carry-forwards from v2.1" if Option B
- [ ] 🟢 PPP audit harness seed graduation note appended at `docs/v1.7-backlog.md`
- [ ] `WIRED_LEVER_LEDGER_COUNT: 0` HTML comment in ADR-18 unchanged; `tests/test_dormant_ledger_consistency.py` passes unchanged
- [ ] Memory mint: `project_v21_cycle_close.md` created + `MEMORY.md` index line added
- [ ] v2.1.0 tag on a `main` commit; ship PR merged
- [ ] PR body cross-references the JsonlTailWorker disposition + lever ledger state + cross-cutting risk closures
- [ ] FROZEN-seam diff guard: only the disclosed seams are touched; sub-cycle close-out diff PR head vs `main` confirms no surprise additions per `feedback_subagent_stale_mental_model.md`
- [ ] NO new FR-PPP entries in REQUIREMENTS.md (all 14 landed across P1/P2/P3)
- [ ] NO ADR-18 amendment in this PR

## Mint-new-phase rule

If Tier 3 soak fails verdict for reasons attributable to v2.1 P1/P1a/P2/P3/P3a changes, do NOT mint a P5 fix-forward phase — phase budget at cap (ADR-18 Rule 4). Open `ship/v2.1-shipgate-fixups` as a sub-cycle under the existing ship-gate frame (S9a pattern from v1.6 / v1.8 / v2.0). Same authority as S1–S14, not a numbered phase mint.

If the soak surfaces a 🔴 PPP regression (envelope-fanout exception, canary-sweep crash, decoy-detector exception, alignment-eval regression directly attributable to a PPP layer), the fixup sub-cycle drains it. If the regression is structural (e.g. a Layer-2 race that wasn't covered by P2 cassette), treat as a v2.2 P0 candidate, not a v2.1 fixup — v2.1 ships with the regression documented as a 🟡 seed and the v2.2 cycle decides whether to revisit. **Do NOT** silently extend v2.1 with a fifth work phase; that breaks the ADR-18 Rule 4 phase cap and would require a cycle-frame amendment (which is heavier than minting v2.2).

If alignment-eval `--ci-gate` regresses but the regression is attributable to corpus drift (not PPP), record the regression in the PR body and proceed with ship — v2.1 cycle is feature, not consolidation; alignment-gate floor is the v1.9/v2.0 anchor and a corpus-drift dip below the floor warrants a separate alignment-recovery cycle (v2.1.1 patch or v2.2 P0), not a v2.1 ship abort.

If during S12 memory mint a sixth memory gap surfaces (e.g. PPP-specific debugging insight worth surfacing), mint a new memory file rather than overloading `project_v21_cycle_close.md` (single-topic-per-memory convention per `anthropic-skills:consolidate-memory`).

If `WIRED_LEVER_LEDGER` ends up non-empty at P4 (someone silently wired a v2.1 lever), STOP and surface — v2.1 had no lever introduction declared at P0 (PPP is additive, not a DORMANT-N candidate per `docs/v2.1-task-plan.md` §"DORMANT-N gate stays inert this cycle"). Either the ledger drifted or a lever was silently introduced; both require investigation before ship.

## Report back

When ship PR is merged and v2.1.0 is tagged, report:

- PR URL + merge SHA
- v2.1.0 tag SHA
- Soak report path
- Alignment-eval report path
- LOC delta vs `401ae47`
- Lever ledger final state (expected: count = 0)
- JsonlTailWorker disposition (A wired / B dormant + seed)
- v2.1-backlog §"Carry-forwards from v2.1" subsection state (seed list if any)
- Cycle-close memory file path

## After this phase

v2.1 cycle is **closed**. v2.2 P0 opens when the operator picks the next cycle's primary lever. Backlog handoff: 6 seeds in `docs/v2.1-backlog.md` (PPP audit harness graduates out via v1.7-backlog tail-of-entry note; `--total-events` flag drift, 🟡 corpus-framing parity, 🟢 CI gate Tier 1.5 trigger matrix, 🟢 Tier 4 large-n soak, 🟢 CLI pool sizing >2 carry forward) plus any P4-seeded carry-forwards.

The §"Feature-cycle LOC ceiling — POLICY GAP" cross-cutting risk from `docs/v2.1-task-plan.md` deserves consideration at v2.2 P0 as an ADR-18 amendment candidate — v2.1 sets a precedent for feature-cycle LOC magnitudes that the consolidation-cycle Rule 3 cap (≤ 0) does not anchor.
