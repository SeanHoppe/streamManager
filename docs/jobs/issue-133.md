# #133 — Cycle-frame memory pre-flight: ADR-18 Rule 6 + DOD checklist

**Status:** OPEN — mint at v2.2 P0 (paired with #130).
**Bucket:** v2.2 P0.
**GH:** https://github.com/SeanHoppe/streamManager/issues/133

## Summary

v2.1 P0 caught `project_sync_comms.md` 5+ days stale; sync-comms v1.0 already SHIPPED but memory
described pre-ship state. Lever proposal retracted, P1 re-pivoted to PPP. Cost: ~1 cycle-frame
round-trip. Survivable but repeatable. No guard today.

## Proposal

**1. DOD checklist line — every cycle-frame prompt:**

> - [ ] Memory pre-flight: every project memory cited in proposed cycle scope verified
>   against current code state (grep for cited files / symbols / commits) within last 24 h.
>   Stale memories updated or marked SHIPPED before P0 PR opens.

**2. ADR-18 §"Cycle-discipline rules" Rule 6:**

> **Rule 6. Memory pre-flight at cycle frame.** Cycle-frame P0 verifies every load-bearing
> project memory against ground-truth code state. Stale memories updated in same P0 PR before
> cycle proceeds. Reason: v2.1 P0 surfaced 5-day-stale `project_sync_comms.md` that misled lever
> selection.

## Acceptance

- [ ] Cycle-frame prompt template carries DOD line.
- [ ] ADR-18 §"Amendments" entry with Rule 6 language.
- [ ] First applied: v2.2 P0.
- [ ] No backfill required — retroactive note in `project_sync_comms.md` + `MEMORY.md` index sufficient for v2.1.

## Timing

Pair with #130 at v2.2 P0 — both ADR-18 §"Amendments" entries, shared reviewer attention.

## Refs

- v2.1 P0 incident: `docs/prompts/v2.1-orchestration/phase-0-cycle-frame.md` §"Pivot rationale" item 2.
- `project_sync_comms.md` (now SHIPPED v1.0–v1.2).
- `MEMORY.md`.
- Companion: #130.
- ADR-18.
- Memory-system guidance (memories decay; verify before relying).
