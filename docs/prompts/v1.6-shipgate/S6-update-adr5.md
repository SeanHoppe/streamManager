# S6 — Update ADR-5 (latency budget) w/ v1.6 baseline

**Goal:** Append `## v1.6 ship-gate baseline` section + replace v1.5 "residue
unidentified" caveat w/ v1.6 attribution.

## Context

ADR-5 = `docs/adr/ADR-5-latency-budget.md`. v1.5 added baseline section that
ended w/ §"Caveats" noting residue location unknown. S4 produced the
attribution sentence.

## Steps

1. Read `docs/adr/ADR-5-latency-budget.md` — locate v1.5 baseline section + caveat.
2. Append new section `## v1.6 ship-gate baseline` after v1.5 section:
   - Date, ship SHA (filled in S10).
   - `evaluate_inner` p95 + 5 residue rows p95.
   - Driver finding sentence from S4.
   - Pool config (`--cli-pool-size 2`).
3. In §"Caveats" — strike-through OR replace the v1.5 "residue unidentified"
   line w/ pointer to v1.6 attribution.
4. Cross-link ADR-5 → CHANGELOG `## [1.6.0]` entry (S7).

## Acceptance

- New v1.6 baseline section reads coherently w/ v1.4 + v1.5 sections (style match).
- Caveat updated, no stale "unidentified" claim remains.
- Numbers match S3 captures + S4 finding.

## On-done ack

`- [x] docs/adr/ADR-5-latency-budget.md **S6 — Update ADR-5** (driver: <component>)`

## Mint-new check

- If S4 mint'd S4a/S4b, factor multi-driver finding into ADR text BEFORE this
  phase closes (don't ship single-driver attribution if data says otherwise).
