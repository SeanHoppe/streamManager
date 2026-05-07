You are implementing **Phase P0 — Formal v10 design doc** for the streamManager v10 RL companion track.

## Branch + base

- Base: `main` AT OR AFTER v2.0 ship tag. If v2.0 has not shipped, ABORT and tell the user (per seed D3).
- PR target: `main`.
- Branch: `docs/v10-formal-design` (or operator's choice).
- Predecessor docs (read first; never inline):
  - `docs/v10-rl-companion-discussion.md` — discussion artefact.
  - `docs/v10-rl-design-seed.md` — D1–D7 resolutions (cherry-pick from `4be19ad` if not on `main`).
  - Pre-flight reachability check before cherry-pick:
    ```
    git cat-file -e 4be19ad 2>/dev/null || { echo "STOP: 4be19ad not reachable. Operator must push claude/v10-rl-design-seed branch first."; exit 1; }
    ```
  - `docs/v10-rl-design-review.md` — best-practices review + 5-issue treatment table.

## ⚠️ CRITICAL: Do-not-touch guard

P0 is **docs only**. Verify before commit:

```
git --no-pager diff origin/main..HEAD --stat -- src tests tools dashboard
```

Expected: empty. Any code hunk → STOP.

ADR-18 surface-freeze applies. RL track NEVER modifies any FROZEN symbol or file (full list: `docs/adr/ADR-18-mvp-surface-freeze.md` §"Initial classification"). v10 reads gov state, writes only to `rl_episodes.db` + `rl_proposals/*.json`.

## Task brief

Promote the seed (`docs/v10-rl-design-seed.md`) plus the design review (`docs/v10-rl-design-review.md`) into a single formal design doc. Resolve the five remaining open items listed at the end of the review.

### Deliverables

1. **`docs/v10-rl-design.md`** — formal design. Sections (in order):

   - **Status**: Accepted (v10 P0). Date. Supersedes: seed + review.
   - **Goal**: close the streamManager governance loop with a deterministic-Python contextual bandit over the L4 confidence threshold, off-policy trained on logged Tier 3 + cassette + golden + probe episodes, gated by a 5-stage validation gauntlet, with three hard constraints (FR-OG-7, HITL-agreement floor, alignment-eval pass-rate floor).
   - **Non-goals**: parameterising more than the L4 threshold in v10.1; LLM tokens in the training loop; modifying any FROZEN gov surface; auto-writeback before v10.3.
   - **State-feature schema** — concrete numerical vector. Required columns:
     - `latency_ms_last5_p95: float`
     - `content_length: int`
     - `regex_destructive_match: int` (0/1)
     - `regex_alignment_match: int` (0/1)
     - `time_of_day_bucket: int` (0–23)
     - `session_history_action_share: float[5]` (rolling share of last 5 actions over ALLOW/SUGGEST/INTERVENE/BLOCK/AMBIGUOUS)
     - `routing_band: int` (L1–L4)
     - `trigger_factor: int` (output of `classify_trigger_factor`)
     - `learn_mode_bias_hint: float` (current `bias_consult` advisory output)
   - **Action space** (v10.1): L4 confidence threshold ∈ {0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90}. 9 bins (closed interval [0.50, 0.90], step 0.05). 0.95 dropped as degenerate near-noop arm.
   - **Reward formula**:
     ```
     reward_stage_A = 1 if HITL_agreement(action) else 0
     reward_stage_B = reward_stage_A − λ₁ · z(latency_p95) − λ₂ · budget_violation_count
     ```
     Stage A used at v10.1 launch; stage B activates only after λ₁/λ₂ calibration completes per phase 4.
   - **Hard constraints (CMDP)** — candidate is INFEASIBLE and dropped from the action set if ANY:
     1. FR-OG-7 violation count > 0 on golden replay.
     2. HITL agreement < baseline − 2 % on logged subset.
     3. Alignment-eval pass rate < baseline pass rate.
     Constraint violations are NOT encoded as reward penalties.
   - **Posterior family**: Beta-Bernoulli per arm (binned discrete action space). Prior: Beta(α₀, β₀) per arm; `α₀ + β₀ = 20` invariant (moderately informative). Mild ε-tilt around the production-baseline arm per seed D6 (ε-neighbourhood principle):

     | Arm distance from baseline | Prior |
     |---|---|
     | 0 (baseline arm) | `Beta(14, 6)` (mean 0.70) |
     | ±1 step | `Beta(11, 9)` (mean ~0.55) |
     | ±2 or more | `Beta(10, 10)` (uniform) |
   - **Cadence** (per seed D7): on-demand → weekly post-stability. Weekly slot pre-registered (e.g. Sunday 02:00 local).
   - **Phase ledger** P0 → P5 (this file → phases 1–5; mirror v1.x phase-block format).
   - **Stop conditions table** — copy from `docs/v10-rl-design-review.md` §"Issue #4". Pre-registered.
   - **v10.3 writeback ADR-18 amendment text** — drafted but NOT enacted in v10 P0. Lands when v10.3 promotes.

2. **`docs/v10-task-plan.md`** — phase ledger covering P0–P5 with do-not-touch list. Mirror `docs/v2.0-task-plan.md` format.

3. **`docs/prompts/v10-orchestration/phase-{0,1,2,3,4,5}-*.md`** — 6 orchestration prompts (this file is P0). P1–P5 prompts MUST already exist on `main` (landed via #106). If absent, P0 is being run before #106 merge — STOP and merge #106 first.

4. **No `rl/` subdirectory yet.** P0 is docs only. Code lands in P1.

### Format invariant

Each phase block in the task plan stands alone — copy-pasteable verbatim into a fresh Claude Code session via the matching action prompt. References to memory files use absolute names (no scrollback assumed).

## DOD

- [ ] `docs/v10-rl-design.md` created with all 12 sections above
- [ ] `docs/v10-task-plan.md` created with P0–P5 phase blocks + do-not-touch list (ADR-18 FROZEN list as-is)
- [ ] `docs/prompts/v10-orchestration/phase-{0..5}-*.md` exist (6 files); P1–P5 reviewed for currency against design doc
- [ ] Cassette p95 + action-dist thresholds adopted from P3 OR explicitly marked advisory
- [ ] Shadow recording strategy resolved: in-process subscriber via soak_driver flag (if soak_driver editable) OR sidecar JSONL-tail (if FROZEN)
- [ ] PR scope is docs-only — `git --no-pager diff origin/main..HEAD --stat -- src tests tools dashboard` empty
- [ ] Single PR against `main`
- [ ] Conventional commit prefix `docs(rl):` (so v10 commits filter cleanly per seed D1: `git log --grep="(rl)"`)

## Mint-new-phase rule

P0 is mechanical; no mints expected unless P1–P5 prompts are missing or contradict the formal design doc. If they contradict, ALIGN the prompt to the design doc and note in the PR description.

Report back when PR is open with: PR URL, diff stat, file list.
