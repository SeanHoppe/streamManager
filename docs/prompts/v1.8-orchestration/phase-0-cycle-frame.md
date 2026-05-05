You are implementing **Phase P0 — Cycle frame** for the streamManager v1.8 cycle.

## Branch + base

- Base: `main` (v1.7.0 tagged at `b7e61044`).
- PR target: `main`.
- Branch: `docs/v1.8-cycle-frame` (or operator's choice).
- If `main` is unexpectedly behind v1.7.0, ABORT and tell the user.

## Do-not-touch guard

P0 is **docs only**. Verify before commit:

```
git --no-pager diff origin/main..HEAD --stat -- src tests tools dashboard
```

Expected: empty. Any code hunk → STOP.

Do NOT edit `docs/v1.8-backlog.md` (frozen-emoji convention; disposition lives in v1.7 ADR-5 / CHANGELOG / this task plan).

## Task brief

Author the v1.8 cycle frame artifacts. Mirror the v1.7 P0 layout (`docs/prompts/v1.7-orchestration/phase-0-cycle-frame.md`).

### Deliverables

1. **`docs/v1.8-task-plan.md`** — phase ledger covering P0 / P1 / P2 with the do-not-touch list extended to include v1.7 protected symbols (RoutingDecision.fallback_model_id, CliGovernor.evaluate fallback_model_id kwarg, governance_fallback_routed + governance_envelope_missing_confidence envelopes, cli_dispatch_fallback_ms timing key, FALLBACK_CONFIDENCE_DEFAULT/_ENV constants, alignment_eval harness + golden set).

2. **`docs/v1.9-backlog.md`** — empty seed (no items at P0 frame), convention block only. Carry-forward stubs for CLI pool sizing >2 + PPP audit harness (still un-promoted from v1.8).

3. **`docs/prompts/v1.8-orchestration/phase-{0,1,2}-*.md`** — three orchestration prompts:
   - `phase-0-cycle-frame.md` (THIS file)
   - `phase-1-content-detection-wiring.md`
   - `phase-2-ship-gate-finalize.md`

4. Confirm `docs/v1.8-backlog.md` already exists (seeded at v1.7 P3) and contains the content-detection wiring item + the two carry-forwards. Do NOT mutate.

### Format invariant

Each phase block in the task plan stands alone — copy-pasteable verbatim into a fresh Claude Code session via the matching action prompt. References to memory files use absolute names (no scrollback assumed).

## DOD

- [ ] `docs/v1.8-task-plan.md` created with P0 / P1 / P2 phase blocks + extended do-not-touch list
- [ ] `docs/v1.9-backlog.md` created (empty seed, convention block, carry-forward stubs)
- [ ] `docs/prompts/v1.8-orchestration/phase-{0,1,2}-*.md` created (3 files)
- [ ] `docs/v1.8-backlog.md` UNCHANGED (frozen-emoji rule)
- [ ] PR scope is docs-only — `git --no-pager diff origin/main..HEAD --stat -- src tests tools dashboard` empty
- [ ] Single PR against `main`

## Mint-new-phase rule

P0 is mechanical; no mints expected. If `docs/v1.8-backlog.md` is missing the content-detection wiring item or the carry-forwards (i.e. v1.7 P3 did not seed correctly), STOP and patch v1.7 retrospectively before opening v1.8 P0.

Report back when PR is open with: PR URL, diff stat, file list.
