# v2.2 P0 — Cycle frame (consolidation-leaning) + paired ADR-18 §"Amendments"

> Minted 2026-05-16 by PM pass. Cycle type **TBD by operator at fire time** —
> feature vs consolidation choice belongs to the operator. This prompt
> drafts both arms; the unused arm is dropped at P0 PR open.

## Branch + base

- Base: `main` after v2.1.0 (tag `8303f38`, PR #150) + v10 P4 corpus-fill
  PRs #155 / #156 already merged.
- Branch: `feat/v2.2-p0-cycle-frame` (feature) or
  `chore/v2.2-p0-cycle-frame` (consolidation) — pick at branch open.
- PR target: `main`.

## Pre-flight (ADR-18 Rule 6 — memory pre-flight; itself the thing being
codified at #133)

Before opening branch, verify every load-bearing memory cited below
against current repo state (grep / file existence / status doc cross-
check). If any cited memory is stale, update it BEFORE opening P0 PR.
Record verification stamp in the P0 PR body.

Memories to verify:

- `project_v21_cycle_close.md` — v2.1 close-out facts.
- `project_v10_rl_track.md` + `project_v10_p4_hold_lifted.md` — RL track
  status (P4 hold-lift, corpus-fill state).
- `feedback_cassette_must_cover_new_envelopes.md` — for #132 disposition.
- `MEMORY.md` index entries for any of the above.

## Operator decisions to record at P0 fire

1. **Cycle type.** Feature (≥1 lever wired) vs consolidation (LOC ≤ 0,
   no new levers). Default lean: **consolidation** — v2.1 was feature
   cycle (+3874 LOC). ADR-18 cycle alternation hygiene argues for
   consolidation slot.
2. **Lever ledger posture.** `WIRED_LEVER_LEDGER_COUNT` = 0 entering
   v2.2. State whether v2.2 keeps the ledger inert or wires a probe-side
   lever (e.g. the alignment-dip remediation path if it surfaces a real
   regression).
3. **v10 freeze-lift overlap.** Per #131 trigger cond 2, v10.x cycle
   cannot mint while v2.x is in P0–P3. Record whether v2.2 is short
   (4 phases) to free the v10.x slot for #112-close + #131 mint.

## Paired ADR-18 §"Amendments" entries (must land at P0)

### Amendment A — Rule 3 extension: feature-cycle LOC soft target (closes #130)

Draft language (verbatim — adjust thresholds against v2.1 actual at
final draft):

> **Rule 3 extension (Amendment v2.2 P0).** Consolidation cycles
> retain net LOC ≤ 0. Feature cycles target ≤ 1500 LOC by default;
> exceeding requires operator override recorded in cycle-frame doc.
> Threshold PROVISIONAL through v2.3 P0 — re-calibrate at ≥ 4
> feature-cycle data points (recompute via p75 or median + stddev).
> Net-LOC measurement scope = 3 buckets: production (`src/`), test
> (`tests/`), docs (`docs/` + `*.md`). Production is load-bearing;
> test + docs advisory. Cycle-start commit = prior cycle's release-
> tag SHA (e.g. v2.1.0 = `8303f38`). Ship-gate diff:
> `git diff <prior-tag>...HEAD --stat`. BLOCK threshold = 1.5× soft
> target (2250 LOC), NOT 2× (2× retro-permits v1.9).

Acceptance (#130):

- [ ] Amendment text in `docs/adr/ADR-18-mvp-surface-freeze.md`
      §"Amendments".
- [ ] §C1–C5 fold-ins per issue body.
- [ ] §C2 per-phase sub-question explicitly DROPPED (defer post-v2.3).
- [ ] `tools/soak_driver.py` post-soak LOC delta summary updated
      against new threshold (additive output only).

### Amendment B — Rule 6 (NEW): memory pre-flight at cycle frame (closes #133)

Draft language (verbatim):

> **Rule 6. Memory pre-flight at cycle frame.** Cycle-frame P0
> verifies every load-bearing project memory against ground-truth
> code state. Stale memories updated in the same P0 PR before cycle
> proceeds. Reason: v2.1 P0 surfaced 5-day-stale
> `project_sync_comms.md` that misled lever selection; cost ~1
> cycle-frame round-trip.

Acceptance (#133):

- [ ] Amendment text in `docs/adr/ADR-18-mvp-surface-freeze.md`
      §"Amendments".
- [ ] Cycle-frame prompt template (this file) carries DOD line
      enforcing the pre-flight.
- [ ] First applied: this very PR (self-applies).

## Carry-forwards from v2.1 backlog (re-triage)

Per `docs/v2.1-backlog.md` §"Carry-forwards from v2.1" — 4 items.
Decide disposition for each:

1. **🟢 `JsonlTailWorker.start()` production wiring** — ~30 LOC
   non-additive runtime-shape change. Disposition options: fold
   into v2.2 P1 (if v2.2 is feature) or defer to v2.3 (if v2.2 is
   consolidation).
2. **🟢 Soak-summary probe-emit counter** — ~5 LOC additive.
   Trivial; can land at P0 or fold into any sub-phase drain.
3. **🟡 Sonnet 0.95 → 0.8636 alignment dip** — see paired prompt
   `task-alignment-dip-row-audit.md`. P0 disposition: promote
   audit-task to v2.2 P1 OR fold into v2.2 P0 as observability-only
   instrumentation.
4. **🟢 Feature-cycle LOC ceiling** — closed by Amendment A above.

## v2.2 backlog seed (single seed)

`docs/v2.2-backlog.md` carries 1 seed: 🟡 remote-CLI monitoring.
ADR-18 Rule 5 backlog hard cap. If v2.2 surfaces > 1 new backlog
item, MUST close or graduate ≥ 1 of the carry-forwards.

## DOD (P0 only)

- [ ] Memory pre-flight stamp in PR body (Rule 6 self-application).
- [ ] Cycle type decision recorded (feature vs consolidation).
- [ ] ADR-18 Amendment A text added (#130 → CLOSE on merge).
- [ ] ADR-18 Amendment B text added (#133 → CLOSE on merge).
- [ ] `docs/v2.2-task-plan.md` written with P1–P4 scope + LOC ledger
      under chosen cycle-type rule.
- [ ] Phase prompts P1/P2/P3/P4 stubbed under
      `docs/prompts/v2.2-orchestration/`.
- [ ] Memory `project_v22_cycle_frame.md` written.
- [ ] Stale GH issues closed in same PR or paired hygiene PR:
      #128 (DECIDED 2026-05-08, P1 shipped at PR #138), #129 (P3
      shipped at PR #145 — task moot).
- [ ] `docs/jobs/MASTER.md` row for #111 corrected (HELD → READY
      corpus-gated; mirror `docs/v10-mvp-status.md` §2).
- [ ] Single PR `feat(v2.2):` or `chore(v2.2):` against `main`.

## Cross-references

- ADR-18: `docs/adr/ADR-18-mvp-surface-freeze.md`.
- Prior cycle close: `CHANGELOG.md` §"[2.1.0]", tag `8303f38`.
- v2.1 backlog: `docs/v2.1-backlog.md`.
- v2.2 backlog: `docs/v2.2-backlog.md`.
- Companion v10 status: `docs/v10-mvp-status.md`.

Report back when P0 PR is open with: PR URL, cycle-type decision,
both ADR-18 amendments diff, list of GH issues closed.
