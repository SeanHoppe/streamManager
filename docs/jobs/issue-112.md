# #112 — v10 P5: Shadow A/B + pre-registered ship criteria

**Status:** BLOCKED on #111 (Q4 hold).
**Bucket:** v10 chain.
**GH:** https://github.com/SeanHoppe/streamManager/issues/112

## Summary

Phase prompt: `docs/prompts/v10-orchestration/phase-5-shadow-stop-conditions.md`.
Predecessor: P4 merged + ≥ 1 manifest with `is_ready_for_shadow() == True`.

## Scope

- `rl/shadow.py` — ghost-path candidate exec alongside production decision.
- `rl/cli/shadow.py` — `python -m rl.cli.shadow --proposal <json> --soak-tier 3`.
- `rl/stop_conditions.py` — 6 pre-registered v10 ship criteria.
- Tests + ADR append (additive only) to `docs/v10-rl-design.md`.

NON-INVASIVE: shadow subscribes to bus, runs candidate in-process, writes `rl_shadow.db`. Never
affects production decision flow.

## Exit

- Shadow run on Tier-3 soak produces (production, candidate, state, ground-truth) tuples.
- All 6 ship criteria evaluated; ship/no-ship verdict reproducible.
- v10 cycle close pending criteria PASS.

## Refs

- Seed PR #106.
- #111 (predecessor).
- `docs/v10-rl-design.md`.
