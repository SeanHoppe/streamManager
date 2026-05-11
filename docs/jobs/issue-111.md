# #111 — v10 P4: Bandit trainer (Thompson + CMDP + promotion gate)

**Status:** READY (Q4 hold lifted 2026-05-11 by operator).
**Bucket:** v10 chain (head). Unblocks #112 → #131 → #124/#125.
**GH:** https://github.com/SeanHoppe/streamManager/issues/111

## Pre-build gates (verify before phase-4 prompt fires)

- ✅ P3 OPE harness CLI present at `rl/cli/validate.py` (imports `rl.validate.validate`).
- ⚠ `rl_episodes.db` is EMPTY locally (0 rows; no `episodes` table). P4 phase-4 prompt § "Branch + base" ABORTS if < 200 live episodes. **Operator must run ≥1 Tier-3 soak to populate corpus BEFORE invoking `phase-4-bandit-trainer.md`.** Alt: if pre-existing remote DB available, copy in.
- ✅ ADR-18 surface freeze posture compatible: P4 touches new `rl/{bandit,constraints,manifest}.py` + `rl/cli/train.py` only; no FROZEN gov edit.

## Summary

Phase prompt: `docs/prompts/v10-orchestration/phase-4-bandit-trainer.md`.
Predecessor: P3 merged (✅ at fa4a55f).

## Scope

- Thompson sampler over P0 action space.
- CMDP safety filter (formal-design constraints).
- Posterior-CI promotion gate.
- Proposal manifest output → consumed by P5 shadow.

## Exit

- Trainer emits ≥ 1 candidate manifest with `is_ready_for_shadow() == True`.
- All P3 gauntlet stages PASS before manifest emit.

## Hold reason

Q4 hold per operator. Unhold gates entire v10 chain (#112 → #131 → #124 + #125).

## Refs

- Seed PR #106.
- P3 PR #123.
- `docs/v10-rl-design.md`.
- Memory `project_v10_rl_track.md`.
