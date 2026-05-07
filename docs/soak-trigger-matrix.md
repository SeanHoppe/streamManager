# Soak trigger matrix

**Status:** Advisory (v2.0 P2). Operator-driven; not CI-enforced.
**Related:** [`docs/adr/ADR-17-soak-tiers.md`](adr/ADR-17-soak-tiers.md) §"v2.0 Tier 1.5 amendment", [`docs/adr/ADR-18-mvp-surface-freeze.md`](adr/ADR-18-mvp-surface-freeze.md) Rule 1 (FROZEN surfaces)

This doc maps PR-touch paths to the soak tier required before merge.
The matrix is **forward-looking from the v2.0 P2 merge SHA**; PRs
opened before P2 lands are exempt by timing (see "Exemptions"
below).

CI gate enforcement is **not** in scope for v2.0. Operators are
expected to read this matrix at PR-open time and run the required
tier locally (or on a soak host) before requesting review on
PRs that touch hot paths.

## Matrix

| PR-touch path | Required tier | Rationale |
|---|---|---|
| `docs/**` only | none | docs cannot regress runtime |
| `tests/**` only | Tier 1 (replay) | catch cassette/test-fixture drift |
| `tools/**` only (excl. `tools/soak_driver.py`) | Tier 1 (replay) | tooling rarely on hot path |
| `tools/soak_driver.py` | Tier 1.5 (smoke) | driver itself is the soak harness; smoke verifies it still warms a pool |
| `src/stream_manager/cli_pool.py` | **Tier 1.5 (smoke)** | pool warmup + send-loop is FROZEN per ADR-18 Rule 1; any change must verify pool still warms |
| `src/stream_manager/cli_governance.py` | **Tier 1.5 (smoke)** | fallback retry path; smoke verifies retry plumbing didn't break the happy path |
| `src/stream_manager/governance.py` | **Tier 1.5 (smoke)** | `_evaluate_inner_core` content-detection helpers; smoke verifies the engine.evaluate loop completes |
| `src/stream_manager/model_router.py` | **Tier 1.5 (smoke)** | `RoutingDecision` field set + band priority FROZEN per ADR-18; smoke verifies routing still selects a band |
| Any other `src/stream_manager/**` | Tier 1.5 recommended | err on the side of running smoke for new src changes; cheap (~6 calls, ~90 s) |
| Ship-gate PR (release tag cut) | **Tier 3 (ship-gate)** + alignment-eval `--ci-gate` | ADR-5 baseline source-of-truth; only Tier 3 numbers feed the budget |

## Required tier definitions

See [`docs/adr/ADR-17-soak-tiers.md`](adr/ADR-17-soak-tiers.md).
Quick reference:

- **Tier 1**: `python tools/soak_driver.py --cli-replay <cassette.jsonl>` — 0 quota.
- **Tier 1.5**: `python tools/soak_driver.py --cli-pool-size 2 --total-events 6 --total-seconds 120` — ~6 real calls, ~90 s wall-clock. Binary gate (pool warmed + clean shutdown). NOT a latency gate; NOT an alignment gate.
- **Tier 3**: `python tools/soak_driver.py --cli-pool-size 2` — full ship-gate, ~32 min, ~60 calls. Source-of-truth for ADR-5.

## Operator obligations

For every PR that touches a row marked **Tier 1.5** above:

1. Run the Tier 1.5 invocation locally (or on a soak host) against
   the PR branch tip.
2. Confirm: driver exit 0, `cli_pool_send_ms` p95 is finite, no
   panics in the soak summary tail.
3. Cite the run in the PR description (timestamp + outcome line is
   enough; no need to attach the full report).

For every PR that cuts a release tag (i.e. ship-gate PRs):

1. Run Tier 3 (`--cli-pool-size 2`, default `--total-events`).
2. Run alignment-eval `--ci-gate` (sonnet ≥ 0.95, haiku ≥ 0.85,
   0 FR-OG-7 regressions, 0 haiku regressions vs sonnet).
3. Both pass before tagging.

## Exemptions

A PR is exempt from a Tier 1.5 obligation in this matrix if:

1. The PR was opened before the v2.0 P2 commit landed (matrix is
   forward-looking).
2. The PR is itself the canonical first invocation of a row in this
   matrix — currently `feat/v2-p1-cli-pool-ab` (v2.0 P1) — in which
   case the PR cites this exemption in its description and the
   operator runs Tier 1.5 retroactively as a sanity check, not as a
   gate.
3. The PR is a hotfix for a production-blocking regression and the
   operator explicitly accepts the matrix-skip risk in writing in
   the PR description. (This row exists for completeness; v2.0 has
   no production deployment yet, so this exemption is unused at
   cycle-frame time.)

## Token-cost summary at typical-cycle scale

Assuming 5 hot-path PRs per cycle:

| Strategy | Calls / cycle | Notes |
|---|---|---|
| Tier 3 on every hot-path PR | ~300 | infeasible — 5 × 32 min wall-clock = ~2.7 h soak time per cycle |
| Tier 1.5 on every hot-path PR (this matrix) | ~30 | ~5 × 90 s = ~7.5 min total |
| No gate (status quo pre-v2.0) | 0 | regressions caught only at ship-gate; one merge earlier when broken |

Tier 1.5 trades ~30 calls / cycle for one-merge-earlier regression
detection on FROZEN surfaces.

## v2.1 candidates

Tracked here for v2.1 backlog seeding (per ADR-18 Rule 5
backlog-cap discipline):

- Promote this matrix to a CI gate (GitHub Actions check that runs
  Tier 1.5 on PR-open when touched paths intersect the
  Tier-1.5-required rows). Block on matrix proving stable in v2.0
  with no false positives.
- Add Tier 4 (large-n smoke for tail-variance triage, e.g.
  `--total-events 240 --total-seconds 480`) — flagged in v1.9
  ship-gate report. Not minted in v2.0 per ADR-18 Rule 4 phase
  budget cap.
