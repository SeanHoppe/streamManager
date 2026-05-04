You are implementing **Phase P2 — v1.6 ship-gate + ADR-5 v1.6 baseline + driver localization** from the streamManager v1.6 cycle.

## Branch + base

- Base: `main` with P1 (`feat/v1.6-cli-residue-timings`) merged.
- PR target: `main`.
- Branch: `ship/v1.6-shipgate-finalize` (or operator's choice).
- If P1 is not merged, ABORT — P2 ship-gate depends on the v1.6 CLI residue instrumentation landing first.

## ⚠️ CRITICAL: Do-not-touch guard

P2 is **finalize only** — soak run, report, ADR-5 re-baseline, CHANGELOG, tag. Do not modify engine code, soak driver report logic, or any v1.0–v1.5 protected symbols. Per memory `feedback_subagent_stale_mental_model.md`, diff PR head vs `main` on `src/` and `tools/` and confirm zero hunks before merging.

```
git --no-pager diff origin/main..HEAD -- src tools
```

Expect empty output (or trivial whitespace only). Any code hunks: STOP — finalize PR has accidentally absorbed P1 follow-up work.

Per memory `feedback_no_self_monitor.md`: do NOT run governance over the SM's own JSONL/bus during the ship-gate. Use the standard `tools/soak_driver.py --cli-pool-size 2` cassette path.

Per memory `feedback_soak_cli_pool_flag.md`: **always** pass `--cli-pool-size 2` to `tools/soak_driver.py`. Default 0 silently reproduces the v1.0 cold-start regression and invalidates the ship-gate.

Per memory `feedback_subagent_long_task_abandonment.md`: the 32-min soak MUST run from the main session via `run_in_background` + `ScheduleWakeup` polling. NEVER launch the soak from a subagent — subagents abandon long-running Bash tasks (>5 min) and the ship-gate report will not land.

## Task brief

Finalize v1.6. Four deliverables.

### 1. Ship-gate soak

Run a Tier-3 soak per ADR-17 with the v1.6 CLI residue instrumentation enabled:

```
python tools/soak_driver.py --cli-pool-size 2 [other v1.5 ship-gate flags from reports/soak-20260504T201714Z.md]
```

Match the v1.5 ship-gate parameter set exactly (32-min wall-clock, ALLOW n=50, L2/L3 n=5, L4 n=5, LM n=10) so the v1.6 numbers diff cleanly against the v1.5 baseline.

Launch the soak with `run_in_background=true` from the main session. Use `ScheduleWakeup` to poll for completion (~32 min wall-clock). Do NOT delegate this run to a subagent.

Report file: `reports/soak-<UTC-timestamp>Z.md`. Verify the report contains ALL THREE blocks:
- `### ALLOW publish-path phase breakout (v1.4)` (back-compat, unchanged columns)
- `### ALLOW _evaluate_inner sub-phase breakout (v1.5)` (back-compat, unchanged columns)
- `### ALLOW _evaluate_inner CLI residue breakout (v1.6)` (new, five rows: `cli_setup_ms`, `cli_dispatch_ms`, `cli_pool_acquire_ms`, `cli_pool_send_ms`, `cli_parse_ms`)

If any block is missing, the soak driver did not pick up P1 instrumentation — STOP and audit P1 merge before proceeding.

### 2. ADR-5 v1.6 baseline

Append a new section `## v1.6 ship-gate baseline` to `docs/adr/ADR-5-latency-budget.md` mirroring the v1.5 baseline section's structure:

- Soak source-of-truth report path
- Driver invocation line
- Measured table (overall p50 / p95 / max + per-band p50/p95)
- New `### ALLOW _evaluate_inner CLI residue breakout (v1.6)` table reproduced from the report with the diagnosing finding paragraph
- Budget table (carry forward v1.5 budget unchanged unless the residue finding localizes the driver AND budget revision is justified)
- §"Caveats" — see deliverable 3

Update the ADR header `Status:` line to add `re-baselined v1.6 (<date>, see §"v1.6 ship-gate baseline")`.

Do NOT alter any prior baseline section. Append-only.

### 3. Driver-localization finding (data-driven)

Document in v1.6 §"Caveats". Read the residue block first; report what the data says; do NOT predict.

Identify which of the five v1.6 keys carries the largest share of `cli_dispatch_ms` p95:

- **If `cli_pool_send_ms` p95 ≈ `cli_dispatch_ms` p95** (e.g. send accounts for ≥90% of dispatch): tail localized to the **model round-trip** itself (claude CLI subprocess wall-clock waiting on the API). v1.7 lever = Haiku fastpath / model latency, NOT pool sizing. Open a `🟡` v1.7 backlog item: "🟡 v1.7: Haiku fastpath for ALLOW escalation — drive `cli_pool_send_ms` down via model selection".

- **If `cli_pool_acquire_ms` p95 nontrivial (>200 ms)**: pool starvation — workers are not free when `_maybe_cli_evaluate` calls `acquire()`. v1.7 lever = pool size or queue policy. Open a `🟡` v1.7 backlog item: "🟡 v1.7: CLI pool sizing / queue-policy investigation — `cli_pool_acquire_ms` p95 = <X> ms at `--cli-pool-size 2`".

- **If `cli_setup_ms` p95 nontrivial (>50 ms)**: lazy `CliGovernor()` construction or `_system_prompt()` cache build hot. Less likely (one-time costs). Open a `🟢` v1.7 follow-up: "🟢 v1.7: warm `CliGovernor` construction at engine init".

- **If `cli_parse_ms` p95 nontrivial (>50 ms)**: JSON parse hot. Very unlikely. Open a `🟢` v1.7 follow-up.

- **If the residue is STILL un-localized** (none of the five new keys explains the dispatch tail — i.e. `cli_dispatch_ms` >> sum of nested keys): record as a falsification of the v1.6 P1 hypothesis. Open a `🔴` v1.7 P1 item: "🔴 v1.7 P1: extend instrumentation into `CliWorker.send` stdout drain loop — v1.6 residue keys explain <X>% of `cli_dispatch_ms`". Do NOT tighten the ALLOW p95 budget.

Cite specific numbers (p95 in ms) from the residue table. The §"Caveats" entry must be reproducible from the report alone.

### 4. LM (categorize) p95 trend re-check

v1.5 closed the v1.4 LM watch item at 15.39 s. Re-confirm in v1.6 §"Caveats":

- ≤ 18 s: state the trend remains retreated; no v1.7 follow-up needed.
- > 18 s: state the trend re-emerged; open a v1.7 backlog item titled "🟡 LM (categorize) p95 sustained-elevation re-investigation" referencing v1.3.1, v1.4, v1.5, v1.6 measurements.

Do NOT speculate on cause — categorizer p95 is dominated by upstream Sonnet queueing and our local sample is n=10. Report the number, classify against the threshold, ship.

### 5. CHANGELOG + tag

- Append a `## [1.6.0] - <date>` section to `CHANGELOG.md` covering: v1.6 CLI residue instrumentation, ADR-5 v1.6 baseline, driver-localization finding (which sub-phase dominates `cli_dispatch_ms`), v1.7 backlog items opened, LM trend disposition.
- After PR merges to `main`, tag `v1.6.0` on the merge commit.

## Cross-PR seam audit

Per memory `feedback_cross_pr_seam_review.md`: before merging this PR, audit the writer↔reader seam between P1 (engine emits new timing keys + `CliGovernor.evaluate` `sub_timings` kwarg) and P2 (soak report consumes them) against the v1.6 task plan component table. Specifically verify:

- Engine writes ALL five v1.6 keys on every ALLOW evaluation (CLI branch: real values; non-CLI branches: `0.0`)
- `_ALLOW_PHASE_ORDER` lists ALL five v1.6 keys in canonical code-path order
- The new `### ALLOW _evaluate_inner CLI residue breakout (v1.6)` block reads the same `engine._last_phase_timings_ms` source as the v1.4 + v1.5 blocks
- The soak report file emitted by the ship-gate run contains all three blocks
- On the residue block, the precheck-hit subset rows render `0.0` for all five new keys (this is correct — instrumented behavior, not missing data); note this in §"Caveats" if the precheck-hit ratio is unusual

Per memory `feedback_subagent_escape_hatches.md`: if any subagent return uses "deferred to a follow-up" phrasing, demand authorization or in-PR landing before accepting.

## DOD

- [ ] `reports/soak-<UTC-timestamp>Z.md` produced with `--cli-pool-size 2`, ALL THREE phase-breakout blocks present (v1.4 + v1.5 + v1.6)
- [ ] `docs/adr/ADR-5-latency-budget.md` appended with `## v1.6 ship-gate baseline` section + §"Caveats" + header `Status:` line updated
- [ ] Driver-localization finding recorded in §"Caveats" with specific p95 numbers; v1.7 backlog item opened per the localization branch (or a `🔴` v1.7 P1 item if residue is still un-localized)
- [ ] LM p95 trend re-check disposition recorded in §"Caveats"; v1.7 backlog item opened if and only if LM p95 > 18 s
- [ ] `CHANGELOG.md` `## [1.6.0]` section appended
- [ ] No code touched (`git --no-pager diff origin/main..HEAD -- src tools` empty)
- [ ] `pytest -q` passes (sanity — should be unchanged from P1 merge)
- [ ] PR merged to `main`
- [ ] `git tag v1.6.0 <merge-sha>` applied; tag pushed

## Final verification before opening PR

```
git --no-pager diff origin/main..HEAD --stat
```

Expected files:
- `reports/soak-<UTC-timestamp>Z.md` (new)
- `docs/adr/ADR-5-latency-budget.md` (modified — append-only)
- `CHANGELOG.md` (modified — append-only)
- `docs/v1.7-backlog.md` (modified — append-only, ONLY if a v1.7 item is opened by the localization branch or the LM trend branch; otherwise unchanged)

If diff shows any change under `src/` or `tools/`, STOP — finalize PR has scope creep. Open a separate hotfix PR if a real defect was found.

Report back: PR URL, diff stat, ship-gate p95 numbers (overall + ALLOW + LM), CLI residue breakout finding (which sub-phase dominates `cli_dispatch_ms` p95), v1.7 backlog items opened, LM trend disposition, tag SHA.
