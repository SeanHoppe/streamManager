# #111 — v10 P4: Bandit trainer (Thompson + CMDP + promotion gate)

**Status:** HELD (Q4 hold).
**Bucket:** v10 chain (head). No move til #111 unholds.
**GH:** https://github.com/SeanHoppe/streamManager/issues/111

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
