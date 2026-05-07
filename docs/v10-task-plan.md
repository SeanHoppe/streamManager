# v10 task plan — RL companion track

**Cycle theme: closed-loop RL.** v10.0–v10.2 add deterministic-Python contextual bandit over the L4 confidence threshold, off-policy trained, validation-gated. v10.3 (writeback) is a separate ADR-18 amendment, NOT covered by this plan.

**Companion docs:**
- `docs/v10-rl-design.md` — formal design (P0 deliverable; 12 sections + draft v10.3 amendment).
- `docs/v10-rl-design-seed.md` — D1–D7 resolutions (cherry-picked from `4be19ad`).
- `docs/v10-rl-design-review.md` — 5-issue treatment table (P0a-reconciled).
- `docs/adr/ADR-18-mvp-surface-freeze.md` — surface freeze; FROZEN list governs every v10 phase.
- `docs/adr/ADR-5-latency-budget.md` — appended in P1 (§"v10 logging overhead") and P5 (§"v10 shadow overhead").
- `docs/adr/ADR-17-soak-tiers.md` — soak tiers; v10 P5 shadow runs Tier 3.

**Reference docs (always available, never inlined):**
- `REQUIREMENTS.md` — current spec.
- `reports/soak-20260507T084933Z.md` — v1.9 ship-gate baseline (carries forward as v2.0 baseline).
- `reports/p1a-corpus-haiku-verdicts-<UTC>.md` — Haiku probe corpus (P2 source).
- `tests/fixtures/soak_cassette_*.jsonl` — cassette source (P2 + P3).
- `tools/alignment_eval.py` — golden corpus, n=32 (P2 + P3).
- `tools/soak_driver.py` — soak driver; P3 reads via env-injected threshold; P5 may extend with `--shadow-recorder` flag if EVOLVING.
- Memory: `project_v10_rl_track.md`, `project_v20_cycle_close.md`, `feedback_no_self_monitor.md`, `feedback_subagent_long_task_abandonment.md`, `feedback_cassette_must_cover_new_envelopes.md`, `feedback_cross_pr_seam_review.md`.

**Format:** mirrors `docs/v2.0-task-plan.md` — each phase block is self-contained; hand verbatim to a fresh Claude Code session via the matching prompt under `docs/prompts/v10-orchestration/`.

**Predecessor baseline:** v2.0.0 ship at `401ae47` (per `project_v20_cycle_close.md`; ADR-5 baseline at `7b7dc64` re-baselined post-cycle-close). v10 P1 logging overhead measured against this baseline.

---

## Do-not-touch list (ADR-18 FROZEN as-is)

v10 NEVER modifies any FROZEN symbol. The full list is in `docs/adr/ADR-18-mvp-surface-freeze.md` §"Initial classification". Quick-reference subset relevant to v10:

- `src/stream_manager/governance.py` (all)
- `src/stream_manager/cli_governance.py` (all)
- `src/stream_manager/model_router.py` (all)
- `src/stream_manager/cli_pool.py` (all)
- `src/stream_manager/learn_mode.py` (all)
- `tools/alignment_eval.py` (all — golden corpus is read-only for v10)
- `tools/soak_driver.py` — EVOLVING for v10.0–v10.2 (the v2.0 P1 `worker_recycle_every_n` kwarg pass-through landed without amendment); v10 P5 may extend with `--shadow-recorder` only after re-verifying classification at phase start.
- `tests/fixtures/soak_cassette_*.jsonl` — frozen format (ADR-17 Tier 2).
- `dashboard/` (all).

v10 reads gov state, writes only to `rl_episodes.db` + `rl_shadow.db` + `rl_proposals/*.json`.

---

## Phase blocks

### Phase P0 — formal design (this PR's first commit)

**Prompt**: `docs/prompts/v10-orchestration/phase-0-formal-design.md`.

**Deliverables**:
- `docs/v10-rl-design.md` — formal design with all 12 sections.
- `docs/v10-task-plan.md` — this file.
- `docs/v10-rl-design-seed.md` — cherry-picked from `4be19ad`.

**Gate**: v2.0 ship tag exists (verified: `v2.0.0` at `401ae47` per `git tag -l`).

**Done when**: `docs/v10-rl-design.md` exists, P1–P5 prompts on `main` align with design doc, single PR open against `main` with `docs(rl):` prefix.

---

### Phase P0a — seed reconcile (this PR's second commit)

**Prompt**: `docs/prompts/v10-orchestration/phase-0a-seed-reconcile.md`.

**Scope**: 16 in-place doc edits across `phase-{0,1,2,3,4,5}-*.md` + `v10-rl-design-review.md`. NO code, NO new files. See P0a prompt §"Fix list" for the canonical A1–H2 list.

**Gate**: #106 (D3 seed) merged.

**Done when**: all 16 fixes applied; action-space canonicalised to 9 bins {0.50..0.90}; commit prefix `docs(rl):` / `feat(rl):` across all 6 phase prompts; `_DESTRUCTIVE_PATTERNS` parity removed; `fr_og_7_pass` schema nullable; design-review arithmetic 3456 → 3465.

---

### Phase P1 — episode logging (this PR's third commit)

**Prompt**: `docs/prompts/v10-orchestration/phase-1-episode-logging.md`.

**Touch list**:
- `rl/__init__.py` — package marker, `__all__ = []`.
- `rl/schema.sql` — `episodes` table DDL, WAL pragma.
- `rl/state_features.py` — pure `extract(state, *, now_utc) -> dict`.
- `rl/episode_logger.py` — single-writer subscriber + CLI ingest.
- `tests/test_rl_state_features.py` + `tests/test_rl_episode_logger.py`.
- `docs/adr/ADR-5-latency-budget.md` — append §"v10 logging overhead".

**Gate (per phase prompt)**: P0 merged. In this bundle PR: P0 + P0a precede P1 commit.

**LOC budget**: ≤ 500 net add (excl. tests + schema.sql).

**Done when**:
- `rl/` package created with 4 files.
- 2 test files pass.
- ADR-5 §"v10 logging overhead" appended (overhead measurement may be deferred to a post-merge soak; this bundle PR carries placeholder text + the budget definition).
- `cli_dispatch_ms` p95 unchanged ± 5 % vs v2.0 baseline (verified post-merge in a Tier 3 soak; if regression, hot-path offload required before merge).
- Self-monitor guard active (`BRIDGE_SM_SELF_SESSION_ID` env var refusal, `feedback_no_self_monitor.md`).

---

### Phase P2 — corpus augmentation (separate future PR)

**Prompt**: `docs/prompts/v10-orchestration/phase-2-corpus-augmentation.md`.

**Touch list**: `rl/corpus_augment.py`, `rl/sources/{__init__,cassette,probe,golden,review}.py`, `tests/test_rl_corpus_augment.py`, `tests/test_rl_sources_*.py`.

**Gate**: P1 merged AND `rl_episodes.db` has ≥ 60 live episodes (real-distribution baseline before synthetic injection).

**LOC budget**: ≤ 500 net add.

---

### Phase P3 — OPE harness (5-stage gauntlet)

**Prompt**: `docs/prompts/v10-orchestration/phase-3-ope-harness.md`.

**Touch list**: `rl/ope.py`, `rl/validate.py`, `rl/cli/validate.py`, `tests/test_rl_ope.py`, `tests/test_rl_validate.py`.

**Gate**: P2 merged.

**LOC budget**: ≤ 600 net add.

---

### Phase P4 — bandit trainer (v10.1)

**Prompt**: `docs/prompts/v10-orchestration/phase-4-bandit-trainer.md`.

**Touch list**: `rl/bandit.py`, `rl/constraints.py`, `rl/manifest.py`, `rl/cli/train.py`, tests.

**Gate**: P3 merged AND `rl_episodes.db` has ≥ 200 live episodes.

**LOC budget**: ≤ 700 net add.

---

### Phase P5 — shadow + ship criteria (v10.2)

**Prompt**: `docs/prompts/v10-orchestration/phase-5-shadow-stop-conditions.md`.

**Touch list**: `rl/shadow.py`, `rl/stop_conditions.py`, `rl/cli/shadow.py`, `rl/cli/check_criteria.py`, tests, `docs/v10-rl-design.md` append (§"v10 ship criteria — pre-registered").

**Gate**: P4 merged AND ≥ 1 P4 trainer run produced a manifest with `is_ready_for_shadow() == True`.

**LOC budget**: ≤ 600 net add.

**Strategy**: re-verify `tools/soak_driver.py` ADR-18 classification at phase start. If EVOLVING → in-process subscriber via `--shadow-recorder` flag. If FROZEN → sidecar JSONL-tail.

---

## v10.3 — writeback (NOT in this plan)

v10.3 lifts `bias_consult` (or the L4 threshold itself) from advisory/proposal-only to write authority. Requires:

1. SEPARATE ADR-18 amendment (draft text in `docs/v10-rl-design.md` §11).
2. Its own phase prompt (`docs/prompts/v10-orchestration/phase-6-writeback.md`, NOT yet minted).
3. `evaluate_criteria` returns ALL PASS for ≥ 1 cycle without manual override.

v10.3 is gated on a successful v10.2 cycle. Do NOT pre-mint.

---

## Bundle PR scope (this PR only)

This PR bundles P0 + P0a + P1 into a single PR (3 commits) since each unblocks the next mechanically and the operator opted for bundle-over-split. Subsequent phases (P2–P5) open their own PRs per their phase prompts' single-PR rule.

Commits in order:
1. `docs(rl): P0a — reconcile seed (16 fixes A1–H2)`
2. `docs(rl): P0 — formal design + task plan + seed cherry-pick`
3. `feat(rl): P1 — episode logging + state features + ADR-5 append`

Diff stat target:
- P0a: 7 files edited (6 phase prompts + design-review).
- P0: 2 new docs + 1 cherry-picked seed.
- P1: 4 new code files + 2 new test files + 1 doc append.

PR-level DOD:
- [ ] P0a 16 fixes applied (verifiable via line-by-line cross-check against P0a prompt §"Fix list").
- [ ] P0 12 sections present in `docs/v10-rl-design.md`.
- [ ] P1 LOC budget ≤ 500 net add (excl. tests + schema.sql).
- [ ] FROZEN-symbol grep clean (no edits inside FROZEN files; verifiable via `git diff origin/main..HEAD --stat -- src/stream_manager tools/soak_driver.py tools/alignment_eval.py dashboard/`).
- [ ] Single PR against `main`.
- [ ] Bundle commit log: 3 commits with `docs(rl):` / `docs(rl):` / `feat(rl):` prefixes.
