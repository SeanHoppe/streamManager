You are implementing **Phase P0 — Cycle frame** for the streamManager v1.9 cycle.

## Branch + base

- Base: `main` (v1.8.0 tagged).
- PR target: `main`.
- Branch: `docs/v1.9-cycle-frame` (or operator's choice).
- If `main` is unexpectedly behind v1.8.0, ABORT and tell the user.

## Do-not-touch guard

P0 is **docs only**. Verify before commit:

```
git --no-pager diff origin/main..HEAD --stat -- src tests tools dashboard
```

Expected: empty. Any code hunk → STOP.

Do NOT edit `docs/v1.9-backlog.md` (frozen-emoji convention; disposition lives in v1.8 ADR-5 / CHANGELOG / this task plan).

## Task brief

Author the v1.9 cycle frame artifacts. Mirror the v1.8 P0 layout (`docs/prompts/v1.8-orchestration/phase-0-cycle-frame.md`).

### Deliverables

1. **`docs/v1.9-task-plan.md`** — phase ledger covering P0 / P1 / P2 / P3 / P4 with the do-not-touch list extended to include v1.8 protected symbols:
   - `governance._evaluate_inner_core` content-detection helpers (`_looks_ambiguous_block`, `is_ambiguous_block` / `is_hitl_synthesis` computation + `route()` kwargs)
   - `tests/test_governance_content_detection.py` (40 scenarios — extend only)
   - `tools/soak_driver.py` `_L2_L3_TRIGGER` list (8+ items — extend only)

2. **`docs/v2.0-backlog.md`** — seed file with two carry-forward stubs (CLI pool sizing >2, PPP audit harness) and convention block only.

3. **`docs/prompts/v1.9-orchestration/phase-{0,1,2,3,4}-*.md`** — five orchestration prompts:
   - `phase-0-cycle-frame.md` (THIS file)
   - `phase-1-verdict-based-fallback.md`
   - `phase-2-session-watcher.md`
   - `phase-3-learn-mode-sources.md`
   - `phase-4-ship-gate-finalize.md`

4. Confirm `docs/v1.9-backlog.md` already exists and contains:
   - 🟡 Haiku fastpath confidence floor
   - 🟡 External session registry
   - 🟡 Learn Mode JSONL expansion
   - 🟢 CLI pool sizing >2 (carry-forward)
   - 🟢 PPP audit harness (carry-forward)
   - 🟢 Background task token registry
   Do NOT mutate it.

### Format invariant

Each phase block in the task plan stands alone — copy-pasteable verbatim into a fresh Claude Code session via the matching action prompt. References to memory files use absolute names (no scrollback assumed).

## DOD

- [ ] `docs/v1.9-task-plan.md` created with P0 / P1 / P2 / P3 / P4 phase blocks + extended do-not-touch list
- [ ] `docs/v2.0-backlog.md` created (carry-forward stubs, convention block)
- [ ] `docs/prompts/v1.9-orchestration/phase-{0,1,2,3,4}-*.md` created (5 files)
- [ ] `docs/v1.9-backlog.md` UNCHANGED (frozen-emoji rule)
- [ ] PR scope is docs-only — `git --no-pager diff origin/main..HEAD --stat -- src tests tools dashboard` empty
- [ ] Single PR against `main`

## Mint-new-phase rule

P0 is mechanical; no mints expected. If `docs/v1.9-backlog.md` is missing any of the six expected seed items (i.e. v1.8 P2 did not seed correctly), STOP and patch v1.8 retrospectively before opening v1.9 P0.

Report back when PR is open with: PR URL, diff stat, file list.
