You are implementing **Phase P5e — Tests + decay** from the streamManager v1.3 cycle (Learn Mode sub-cycle).

## Branch + base

- Base: `ship/v1.3-learn-mode`.
- PR target: `ship/v1.3-learn-mode`.
- Branch: `feat/v1.3-learn-decay-tests` off `ship/v1.3-learn-mode` (or operator's choice).
- If `ship/v1.3-learn-mode` does not exist, ABORT — P5a must ship first.

After P5e merges, `ship/v1.3-learn-mode` is ready to merge to `main` — that becomes the final P5 close-out PR.

## Dependencies

- P5a: `docs/learn-mode-design.md` — source of truth for decay ladder spec (30/60/90/120 day step demote + reinforcement reset + contradiction snap-demote).
- P5b: dialogue ingest.
- P5c: `learn_patterns` table + categorizer.
- P5d: advisory bias hookup.
- `docs/v1.3-testing.md` §"Method 2 — Expectation Beacon" — categorizer expected-output coverage.
- `docs/v1.3-testing.md` §"Method 3 — Adversarial Drift Probe" — false-positive promotion + decay/contradiction coverage.

## ⚠️ CRITICAL: Do-not-touch guard

Decay logic is internal to `learn_categorizer.py`. No governance hot-path edits. Same protected symbols as P5c/P5d.

| From task | File | Symbols/sections |
|-----------|------|------------------|
| I (v1.1) | `src/stream_manager/governance.py` | `_install_lazy_hydrator`, `GovernanceEngine.hydrated` |
| J (v1.1) | `src/stream_manager/cli_pool.py` | `CliPool`, `CliWorker` |
| M (v1.1) | `src/stream_manager/governance.py` | `EngineRegistry.start_refresh/stop_refresh/refresh_all/refresh_status` |
| (cross-cutting) | `INTENT.md` | §"Safety priorities" — ALWAYS preserved by adversarial probe gating |

Pre-flight grep:

```
grep -nE 'CliPool|_install_lazy_hydrator|start_refresh|learn_patterns|bias_for' src/stream_manager/cli_pool.py src/stream_manager/governance.py src/stream_manager/learn_categorizer.py
```

If any symbol missing or `learn_patterns` / `bias_for` not present (P5c/P5d not merged), STOP and report.

## Task brief

### Steps

1. Implement decay ladder in `src/stream_manager/learn_categorizer.py`:
   - Time-based step demote at 30/60/90/120 day age thresholds.
   - Reinforcement reset on each matching prompt (`last_reinforced_ts` updated).
   - Contradiction snap-demote when a `user_reply` contradicts the predicted category (`contradicted_count` increments; `ladder_step` snaps down per design threshold).

2. Background decay sweep — runs on a schedule (daily) OR on each categorizer worker tick. Updates `ladder_step`, `last_reinforced_ts`, `contradicted_count`.

3. Beacon fixtures (Method 2 — Expectation Beacon) under `tests/beacons/learn_mode_categorizer.jsonl`:
   - Canned dialogue → expected category prediction.
   - Operator runs `tools/scenario_runner.py --beacons tests/beacons/learn_mode_categorizer.jsonl` to drive the beacons.
   - If `tools/scenario_runner.py` does not yet exist (P1 has not landed it as a side artifact), stub the minimal driver here OR document the dependency in the PR body.

4. Probe table (Method 3 — Adversarial Drift Probe) under `tests/probes/learn_mode_drift.csv`:
   - Rows of `{prompt, true_category, distractor_categories}`.
   - Driver asserts zero false promotions + contradiction snap-demote fires at design threshold.

5. Standard unit tests for decay math: synthesize patterns at various ages and reinforcement counts; assert correct ladder step.

## DOD

- [ ] Decay/reinforcement/contradiction logic shipped in `learn_categorizer.py`
- [ ] Beacon fixtures committed under `tests/beacons/`
- [ ] Probe table committed under `tests/probes/`
- [ ] Standard unit tests for decay math pass
- [ ] `pytest -q` passes end-to-end
- [ ] No protected-symbol drift
- [ ] Single PR against `ship/v1.3-learn-mode`
- [ ] After merge, note in PR body that `ship/v1.3-learn-mode` is now ready to merge to `main`

## Final verification before opening PR

```
git --no-pager diff origin/ship/v1.3-learn-mode..HEAD --stat
```

Expected files:
- `src/stream_manager/learn_categorizer.py` (modified — decay logic)
- `tests/test_learn_categorizer_decay.py` (new — unit tests)
- `tests/beacons/learn_mode_categorizer.jsonl` (new)
- `tests/probes/learn_mode_drift.csv` (new)
- (optional) `tools/scenario_runner.py` (new stub if not yet present)

If diff shows reshape of existing ladder logic in `governance.py` or any change to `_install_lazy_hydrator` / `cli_pool` / `EngineRegistry.refresh_*`, STOP and report.

Run `pytest -q` end-to-end. Paste tail in PR body.

Report back: PR URL, diff stat, pytest tail, plus a note that `ship/v1.3-learn-mode` is ready to merge to `main`.
