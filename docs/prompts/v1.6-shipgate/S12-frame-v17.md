# S12 — Frame v1.7 cycle (separate session)

**Goal:** Open v1.7 cycle frame in a NEW session, driven by v1.6 driver
finding. Mirrors v1.6 P0 docs-only PR pattern.

## Context

Out-of-scope for today's v1.6 ship session. Listed here for completeness so
the checklist captures full closure-of-loop. Session boundary is intentional:
keeps v1.6 ship session focused, lets v1.7 cycle frame start with a clean
context window.

## Steps (for the next session, NOT this one)

1. Read `docs/v1.7-backlog.md` (S8 output) + ADR-5 v1.6 baseline (S6 output).
2. Mint `docs/prompts/v1.7-orchestration/phase-{0,1,2}-*.md` per v1.6 template.
3. Create `docs/v1.7-task-plan.md` w/ phases driven by S4 lever.
4. Open P0 docs-only PR.

## Acceptance (this phase, this session)

- Marker only. Ack flips to `[x]` when v1.7 P0 PR opens in a future session.

## On-done ack

`- [x] PR #<m> v1.7 P0 **S12 — Frame v1.7 cycle** (next-session handoff)`

## Mint-new check

- Not for today's session. v1.7 cycle generates its own checklist.
