# S8 — Seed v1.7 backlog (data-driven)

**Goal:** Convert v1.6 driver finding (S4) + LM watch decision (S5) into
concrete v1.7 backlog items in `docs/v1.7-backlog.md`.

## Context

`docs/v1.7-backlog.md` was seeded empty in P0. v1.7 lever choice was
explicitly deferred to v1.6 attribution data. S4 supplies the lever; this
phase writes it down.

## Steps

1. Read `docs/v1.7-backlog.md` (currently mostly an empty seed).
2. Append items, each with:
   - Title.
   - **Why:** line tying to v1.6 finding (cite SHA + ADR-5 §).
   - **How to apply:** scope hint (single-PR vs multi-phase).
3. Likely items based on S4 outcome:
   - Primary lever (Haiku fastpath / pool sizing / parse path / dispatch
     decomp — whichever S4 selected).
   - Secondary item: sub-phase further-decomp if S4a was minted.
   - LM follow-up if S5 left watch open.
4. Optional: P0 cycle-frame seed item (mirrors v1.6 P0 pattern).

## Acceptance

- `docs/v1.7-backlog.md` has at least one concrete primary-lever item.
- Each item cites v1.6 evidence (numbers + SHA reference).

## On-done ack

`- [x] docs/v1.7-backlog.md **S8 — Seed v1.7 backlog** (<n> items added)`

## Mint-new check

- If S4 finding inconclusive (no clear single lever), mint `S8a-v17-prep-investigation.md`
  (additional probe before v1.7 cycle frame).
