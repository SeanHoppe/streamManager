You are implementing **Phase P2 — Tier 1.5 smoke soak codification + trigger matrix** for the streamManager v2.0 cycle.

## Branch + base

- Base: `main` (after v2.0 P0 is merged).
- PR target: `main`.
- Branch: `docs/v2-p2-tier-15-codify` (or operator's choice).
- Independent of P1 — may land in parallel.

## Context

ADR-17 codifies three soak tiers (1: replay / 2: cassette record /
3: ship-gate). Gap: a fast-soak variant between Tier 1 (0 quota) and
Tier 3 (32 min wall-clock) is missing. Plan-agent flagged this in v1.9
as the cheapest reduction in soak-cost / regression-coverage gap.

v2.0 P2 codifies the variant + the PR-touch-path → tier mapping.
Docs-only.

## References

- `docs/v2.0-backlog.md` §"🟡 Tier 1.5 smoke soak — codification +
  trigger matrix" — proposed shape
- `docs/adr/ADR-17-soak-tiers.md` — additive amendment only
- `docs/adr/ADR-18-mvp-surface-freeze.md` Rule 1 (ADR-17 is FROZEN —
  additive only)
- `tools/soak_driver.py` — already supports `--total-events` +
  `--total-seconds` + `--cli-pool-size`; Tier 1.5 is a parameter set,
  not a new flag

## Do-not-touch guard

P2 is **docs only**. Verify before commit:

```
git --no-pager diff origin/main..HEAD --stat -- src tests tools dashboard
```

Expected: empty. Any code hunk → STOP.

ADR-17 Tier 1 / 2 / 3 sections UNCHANGED. ADR-5 baseline source-of-truth
UNCHANGED. `tools/soak_driver.py` flag set UNCHANGED.

## Scope

1. **Amend `docs/adr/ADR-17-soak-tiers.md`**: add §"Tier 1.5 — smoke
   soak (per-PR; pool-warmup gate)" section. Required content:
   - Invocation:
     `python tools/soak_driver.py --cli-pool-size 2 --total-events 6 --total-seconds 120`
   - Wall-clock: ~90s
   - Token cost: ~6 Haiku calls
   - Gate semantics: BINARY — pool warmed AND clean shutdown. NOT a
     latency gate. NOT a source-of-truth for ADR-5 numbers.
   - Position relative to existing tiers: between Tier 1 (replay) and
     Tier 3 (ship-gate). Optional gate for PRs that touch hot paths.
   - Token-reduction estimate at typical-cycle scale (vs running
     Tier 3 on every gate).
2. **Create `docs/soak-trigger-matrix.md`** — new doc. Required
   sections:
   - PR-touch path → required tier table:
     - Pure docs / `docs/**` only → no soak
     - Pure tests / `tests/**` only → Tier 1 (replay)
     - `tools/**` only → Tier 1 (replay)
     - `src/stream_manager/cli_pool.py` → Tier 1.5 required
     - `src/stream_manager/cli_governance.py` → Tier 1.5 required
     - `src/stream_manager/governance.py` → Tier 1.5 required
     - `src/stream_manager/model_router.py` → Tier 1.5 required
     - Ship-gate PR (release tag cut) → Tier 3 + alignment-eval
       `--ci-gate`
   - Operator obligations: matrix is currently advisory; CI gate
     enforcement lands as v2.1 backlog item if matrix proves stable.
3. **Do NOT** add a CI gate that runs Tier 1.5 automatically. v2.0
   P2 codifies the matrix; enforcement is operator-driven this cycle.
4. **Cassette compatibility**: confirm in the ADR-17 amendment that
   Tier 1.5 invocation does NOT require `cassette_record.py` envelope
   coverage updates (per `feedback_cassette_must_cover_new_envelopes.md`)
   because Tier 1.5 hits real `claude -p` (just at smaller scale),
   not replay.

## DOD

- [ ] ADR-17 amended with Tier 1.5 section (additive — Tier 1 / 2 / 3
      sections unchanged)
- [ ] `docs/soak-trigger-matrix.md` created
- [ ] Token-reduction estimate recorded in ADR-17 amendment
- [ ] PR scope is docs-only — `git --no-pager diff origin/main..HEAD --stat -- src tests tools dashboard` empty
- [ ] PR LOC delta ≤ 0 net add in `src/` + `tools/` (zero by
      construction)
- [ ] Single PR against `main`

## Mint-new-phase rule

If during drafting a Tier 4 (large-n smoke for tail-variance triage,
flagged in v1.9 ship-gate as a v2.0 backlog candidate) seems
necessary, do NOT mint it here — codify Tier 1.5 only and seed
Tier 4 as a v2.1 backlog stub. Phase budget is at cap.

If the trigger matrix as written would BLOCK an existing in-flight PR
on `main` because that PR did not run Tier 1.5, mark the PR exempt
in the matrix doc (with explicit comment) — the matrix is forward-
looking and not a retroactive gate.

Report back when PR is open with: PR URL, diff stat (should be docs-
only), token-reduction estimate, and any matrix-coverage edge cases
flagged.
