You are implementing **Phase P0a — Seed reconcile (doc-only fixes)** for the streamManager v10 RL companion track.

## Branch + base

- Base: PR #106 head (`claude/awesome-perlman-abde9c`) OR `main` if #106 already merged.
- PR target: same as #106's target (`main`); if #106 still open, push directly to its branch as a follow-up commit.
- Branch (if minting fresh): `docs/v10-seed-reconcile`.
- Predecessor: PR #106 (D3 seed) review findings — encoded inline below.

## ⚠️ CRITICAL: Do-not-touch guard

P0a is **docs only**. Verify before commit:

```
git --no-pager diff origin/main..HEAD --stat -- src tests tools dashboard
```

Expected: empty. Any code hunk → STOP.

ADR-18 surface-freeze applies. P0a edits ONLY:

- `docs/prompts/v10-orchestration/phase-0-formal-design.md`
- `docs/prompts/v10-orchestration/phase-1-episode-logging.md`
- `docs/prompts/v10-orchestration/phase-2-corpus-augmentation.md`
- `docs/prompts/v10-orchestration/phase-3-ope-harness.md`
- `docs/prompts/v10-orchestration/phase-4-bandit-trainer.md`
- `docs/prompts/v10-orchestration/phase-5-shadow-stop-conditions.md`
- `docs/v10-rl-design-review.md`

NO code, no tests, no tools/, no FROZEN-symbol grep against source needed (P0a does not introduce new source-symbol claims).

## Task brief

PR #106 review surfaced 22 findings; 16 are concrete, identifiable, and reconcilable via in-place doc edits. P0a applies all 16. Open items requiring design judgement (ε-shaped prior precise formula, cross-process bus IPC strategy) are flagged in P0a but resolved in P0 formal-design.

### Pre-flight verifications (already performed; encoded as facts)

These were verified against `main` at `a7d0666` + #106 head. Re-verify only if the branch base shifts.

| Symbol / claim | Status on main | Source |
|---|---|---|
| `BRIDGE_L4_FALLBACK_CONFIDENCE` env var | EXISTS (v1.7 P2 introduced; v1.9 P1 still references) | `docs/prompts/v1.7-orchestration/phase-2-haiku-fastpath-router.md:54` |
| `FR_OG_7` (caps + underscore) Python symbol | DOES NOT EXIST | `grep -nrE 'FR_OG_7' src/` returns empty |
| Canonical FR-OG-7 Python tokens | `og7`, `fr_og7`, `_check_fr_og7`, `og7_check`, `_OG7_UNCONFIGURED_EMITTED`, `fr_og7_regression`, `fr_og7_sweep`, `fr_og7_aar` | `src/stream_manager/governance.py`, `src/stream_manager/project_context.py` |
| `_DESTRUCTIVE_PATTERNS` symbol on main | DOES NOT EXIST in `src/` (referenced in v1.8/v1.9 prompts as load-bearing, but not present in current `main`) | `grep -nrE '_DESTRUCTIVE_PATTERNS' src/` returns empty |
| Conventional-commit prefix `rl:` | NO precedent | `git log --oneline -50` shows `ship:`/`feat(...):`/`docs(...):`/`fix:` only |

### Fix list (16 items)

#### A. Cross-doc canonicalisation

**A1. Action space.** Single canonical list = **9 bins** at L4 threshold ∈ `{0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90}` (closed interval [0.50, 0.90], step 0.05). Drop 0.95 (degenerate near-noop arm). Update:

- `phase-0-formal-design.md` L46: replace bracket list `{0.50, 0.55, …, 0.95}` with the 9-element list above. Drop the parenthetical "(the seed says 9 — count the open interval)".
- `phase-4-bandit-trainer.md` L65: already correct; verify no drift.

**A2. Prior shape.** P0 says "ε-neighbourhood-shaped warm start"; P4 implements flat `Beta(10,10)` for non-baseline arms. Reconcile to a **mild ε-tilt**:

| Arm distance from baseline | Prior |
|---|---|
| 0 (baseline arm) | `Beta(14, 6)` (mean 0.70) |
| ±1 step | `Beta(11, 9)` (mean ~0.55) |
| ±2 or more | `Beta(10, 10)` (uniform) |

`α₀ + β₀ = 20` invariant holds for all arms. Update:

- `phase-0-formal-design.md` L58: replace "ε-neighbourhood-shaped warm start per seed D6" with the explicit table above; cite seed D6 as the source of the ε-tilt principle.
- `phase-4-bandit-trainer.md` L66: replace flat `Beta(10,10)` with the table above. Add test `test_epsilon_tilted_prior` asserting initial mean by distance.

**A3. Conventional-commit prefix.** Repo precedent uses `feat(...)`/`ship:`/`docs(...)`/`fix:`. The phase prompts insist `rl:`. Change all DOD lines to:

> Conventional commit prefix `feat(rl):` (or `docs(rl):` for docs-only phases like P0)

Update DOD in `phase-0` L81, `phase-1` L132, `phase-2` L118, `phase-3` L129, `phase-4` L135, `phase-5` L142. Replace `rl:` → `feat(rl):` (or `docs(rl):` for P0).

#### B. phase-0-formal-design.md

**B1.** L76 DOD says "all 8 sections" but the deliverable bullets list 12 (Status, Goal, Non-goals, State-feature, Action, Reward, Constraints, Posterior, Cadence, Phase-ledger, Stop-conditions, v10.3-amendment). Change `all 8 sections` → `all 12 sections`.

**B2.** L66 says "P1–P5 already minted in design-review pass — verify they exist; if any missing, STOP and ask for re-mint". Since P0+P1–P5 co-land in #106 (the seed PR), this verification is redundant in P0 itself but useful as a sanity check. Keep, but reword to:

> P1–P5 prompts MUST already exist on `main` (landed via #106). If absent, P0 is being run before #106 merge — STOP and merge #106 first.

**B3.** L10 instructs cherry-pick from `4be19ad`. That commit lives on a non-pushed branch (`claude/v10-rl-design-seed`). Add a pre-flight check immediately above L10:

```
git cat-file -e 4be19ad 2>/dev/null || { echo "STOP: 4be19ad not reachable. Operator must push claude/v10-rl-design-seed branch first."; exit 1; }
```

#### C. phase-1-episode-logging.md

**C1.** L83 instructs `_DESTRUCTIVE_PATTERNS` parity test, but the symbol does NOT exist in `src/` on `main`. Replace L83's last sentence:

> Regex helpers re-use `_DESTRUCTIVE_PATTERNS` indirectly via a small adapter (do NOT import the symbol directly — re-declare equivalent patterns in `rl/state_features.py` and add a unit test that asserts pattern-set parity at least on the P1a probe corpus).

with:

> Regex helpers are defined locally in `rl/state_features.py` (canonical destructive-content patterns; v10-owned). NO import from FROZEN modules. The pattern parity test (L99 below) compares ONLY against the v1.9 P1a probe corpus outcome distribution (≥ 90 % BLOCK on the wrapped corpus); there is no cross-module symbol parity to assert.

L99 `test_destructive_pattern_parity` description: change to "agrees with the v1.9 P1a probe corpus outcome distribution (≥ 90 % match on wrapped + bare prompts)".

**C2.** L92 says "single process + file lock on `rl_episodes.db.lock`" + "WAL mode required". SQLite WAL already serialises writers; file lock adds no safety, only deadlock risk. Drop file lock:

> Writer is a SINGLE process. WAL mode required. Multiple SM instances are NOT supported in v10.0; SQLite WAL provides single-writer multi-reader semantics. (If multi-instance SM lands later, revisit with explicit IPC, not file locks.)

**C3.** L89: `fr_og_7_pass` defaults to `1` for live (non-alignment) rows. Replace L89's last clause with NULL-semantics:

> read `requires_alignment` outcome to determine `fr_og_7_pass`: `1` only on golden-replay episodes where verdict matches golden expected; `0` only on confirmed regression; `NULL` on live and cassette episodes (no ground-truth signal). Trainer downstream MUST treat `fr_og_7_pass IS NULL` as "no signal", not as "pass".

Update schema at L60: `fr_og_7_pass INTEGER` (drop `NOT NULL` constraint). Add test `test_logger_fr_og_7_pass_null_on_live` to L96 deliverable list.

#### D. phase-2-corpus-augmentation.md

**D1.** L29 pre-flight grep uses `FR_OG_7`. That token does not exist on `main`. Replace with canonical Python tokens:

```
grep -nE 'BRIDGE_L4_FALLBACK|requires_alignment|_check_fr_og7|og7_check' src/stream_manager
```

(Drop `_DESTRUCTIVE_PATTERNS` from this grep — the symbol is not on main; v10 owns its own pattern set per C1 above.)

**D2.** L57 sets golden adapter `hitl_override = 1 always`. This conflates "expected verdict" with "HITL-confirmed signal". Replace with:

> Recorded verdict is the golden expected verdict. `hitl_override = NULL` (golden is a labelled-expected signal, NOT a HITL signal; mixing the two inflates HITL agreement downstream). Ground truth is carried via the `verdict` column itself + `source='golden'` discriminator.

Update test `test_golden_episode_hitl_override_set` to `test_golden_hitl_override_is_null`.

**D3.** L52 hardcodes "~96–100 % BLOCK on this corpus per v1.9 P1a outcome". Replace numeric range with citation:

> Recorded verdict is the Haiku probe verdict (high-quality minority signal; outcome distribution per `reports/p1a-corpus-haiku-verdicts-<UTC>.md`).

Test `test_probe_corpus_block_dominant` (L83): keep `≥ 90 %` threshold; cite the same report path in the docstring so the threshold's provenance is traceable.

#### E. phase-3-ope-harness.md

**E1.** L78 introduces two thresholds (`cassette p95 ≤ 10 %`, `action-dist ≤ 20 %`) not in formal design. Add note immediately after L78:

> **Provenance**: these two thresholds are P3-local heuristics, NOT pre-registered ship criteria. They MUST be promoted into `docs/v10-rl-design.md` §"v10 ship criteria" by P0 before P3 merge OR demoted to "advisory" with explicit acknowledgement in the validation report.

Add a checkbox to P0 DOD: `[ ] Cassette p95 + action-dist thresholds adopted from P3 OR explicitly marked advisory`.

**E2.** L52 IPS undefined-off-support handling: clarify by replacing "Handle off-support gracefully: clip propensity weights to [0.01, 100] and emit warning." with:

> Handle off-support gracefully: clip propensity weights to `[0.01, 100]` and emit `rl_ips_clipped` warning envelope. NOTE: at v10.0 production policy is deterministic so live episodes have `propensity = 1.0`; off-support arises only when `target_policy(state) ≠ production_action`. Off-support fraction MUST be reported in the validation report.

#### F. phase-4-bandit-trainer.md

**F1.** L130 DOD says "ZERO `subprocess` / `claude` / `anthropic` imports" — but trainer calls `rl.validate.validate` which (P3 stage 3) shells `tools/soak_driver.py` via subprocess. Reword:

> Trainer module (`rl/bandit.py`, `rl/constraints.py`, `rl/manifest.py`, `rl/cli/train.py`) imports ZERO `subprocess` / `anthropic` directly. Subprocess invocation is permitted ONLY via `rl.validate.validate(...)` at P3 stage 3 (cassette replay). Test `test_trainer_no_direct_subprocess_imports` asserts AST-level absence of `subprocess` / `anthropic` imports in the four trainer files.

**F2.** L93 exit codes invert unix convention. Replace with:

| Exit | Meaning |
|---|---|
| 0 | Trainer ran cleanly; baseline retained (no feasible candidate beats baseline). Default success. |
| 10 | Trainer found a feasible candidate that beats baseline AND posterior CI ≤ 0.10 → proposal manifest ready for P5 shadow. |
| 1 | Trainer error (DB read fail, manifest write fail, etc.). |

Update DOD test name to `test_exit_codes_0_no_lift_10_promote_1_error`.

#### G. phase-5-shadow-stop-conditions.md

**G1.** L91 says "Subscribes to [soak subprocess's] bus using existing subscriber surfaces". The bus is in-process; cross-process subscription does not exist. Replace L89-93 with:

> 3. **`rl/cli/shadow.py`** — CLI: `python -m rl.cli.shadow --proposal rl_proposals/<UTC>Z.json --soak-tier 3 [--soak-args "..."]`:
>    - Spawns `tools/soak_driver.py --cli-pool-size 2 --shadow-recorder rl_shadow.db [--shadow-proposal <path>]` as a subprocess.
>    - The `--shadow-recorder` flag is a NEW soak_driver CLI surface (added in P5 OR a P5 predecessor sub-phase IF soak_driver is FROZEN). The soak driver, running in-process with the bus, invokes `rl.shadow.ShadowRecorder.on_governance_decision` for each envelope.
>    - **Open question for P0**: if `tools/soak_driver.py` is on the FROZEN list (per ADR-18), P5 cannot add a CLI flag. In that case shadow recording must use a sidecar JSONL-tail strategy (read soak's bus log file as it appends), with the recorder written to `rl_shadow.db` post-run, NOT live. Resolve this in P0 formal design before P5 merge.
>    - On soak completion: writes `reports/v10-shadow-<UTC>Z.md` summarising agreement rate, candidate-vs-production reward, FR-OG-7 row outcomes, HITL agreement.

Add P0 DOD checkbox: `[ ] Shadow recording strategy resolved: in-process subscriber via soak_driver flag (if soak_driver editable) OR sidecar JSONL-tail (if FROZEN)`.

**G2.** L77 "≤ 50 ms p95" — add ADR-5 reference:

> **Non-invasion invariant**: `on_governance_decision` MUST be wall-clock-bounded (≤ 50 ms p95; budget cited from ADR-5 §"v10 shadow overhead", to be added when P5 lands) and MUST NOT block the bus.

#### H. docs/v10-rl-design-review.md

**H1.** L177 arithmetic: `0.25·(1.96/0.05)^2 = 384.16` → ceil = 385 → `9·385 = 3465`. Doc says 3456. Replace with 3465.

**H2.** L67-68 wording misstates CMDP. Replace:

> seed D5 already does this for FR-OG-7 (constraint-violating episodes are rejected from the training set, not penalised).

with:

> seed D5 already does this for FR-OG-7 (constraint-violating CANDIDATES are rejected from the action set BEFORE Thompson sampling, not penalised in the reward; constraint-violating EPISODES remain in the log for observability).

### Non-goals

P0a does NOT:

- Mint the formal design doc itself (P0 owns that).
- Touch `rl/` source (no `rl/` exists yet at P0a; P1 mints it).
- Change any FROZEN-surface symbol.
- Change ship criteria thresholds in the table at `phase-5-shadow-stop-conditions.md` L40-46 (those are pre-registered; P0a only fixes adjacent prose).

## DOD

- [ ] All 7 listed doc files edited per fix list A–H
- [ ] `git --no-pager diff origin/main..HEAD --stat -- src tests tools dashboard` empty
- [ ] Action-space list canonicalised to 9 bins {0.50..0.90} across P0 + P4 (verifiable: `grep -E '0\.95' docs/prompts/v10-orchestration/phase-{0,4}-*.md` returns NO action-space-context match)
- [ ] Conventional-commit prefix changed from `rl:` to `feat(rl):`/`docs(rl):` in all 6 DOD blocks
- [ ] `FR_OG_7` removed from P2 grep; replaced with canonical `og7`/`fr_og7` tokens
- [ ] `_DESTRUCTIVE_PATTERNS` parity language removed from P1 + P2; replaced with v10-owned local pattern set
- [ ] `hitl_override = 1 always` for golden replaced with `NULL` semantics in P2; corresponding test renamed
- [ ] `fr_og_7_pass` schema in P1 changed to nullable; trainer-side semantics added
- [ ] P5 shadow-recorder cross-process IPC strategy flagged as P0 open question
- [ ] design-review arithmetic corrected (3456 → 3465)
- [ ] design-review CMDP wording aligned with P4 implementation
- [ ] Single PR (or single follow-up commit on #106's branch) against `main`
- [ ] Conventional commit prefix `docs(rl):`

## Mint-new-phase rule

P0a is a doc reconcile pass; no new phases are minted. If the operator discovers new identifiable issues during the pass, append them to this prompt's fix list and note in PR description.

Report back when commit/PR is open with: PR URL (if new) OR commit SHA (if added to #106 branch), diff stat, file list, table mapping each fix item (A1..H2) to the resulting line range.
