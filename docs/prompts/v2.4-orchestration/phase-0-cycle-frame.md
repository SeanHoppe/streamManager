# v2.4 P0 — Cycle frame

> Minted 2026-05-18 as part of v2.4-pm-mint PR. Cycle type **TBD by
> operator at fire time**. Default lean: **consolidation** (v2.3 was
> feature, LOC +461; alternation hygiene). Operator may override to
> **feature** if v10 deadlock-resolution scope (issue #177 Amendment D
> + Path-D synthetic-fixture P5) is sequenced into this cycle.
>
> Comparison anchor: `docs/v2.4-next-steps.md` §"P0 frame — operator-
> bound decisions" (to be drafted in same P0 PR — companion to this
> frame, mirroring `docs/v2.3-next-steps.md` pattern).

## Branch + base

- Base: `main` after v2.3.0 (commit `b00473d`, PR #175).
- Branch: `feat/v2.4-p0-cycle-frame` (feature) or
  `chore/v2.4-p0-cycle-frame` (consolidation) — pick at branch open.
- PR target: `main`.

## Pre-flight (ADR-18 Rule 6 — memory pre-flight per Amendment B)

Verify each load-bearing memory against current repo state before
opening P0 PR. If any cited memory is stale, update it BEFORE
opening P0 PR. Record verification stamp in P0 PR body.

Memories to verify (v2.4 P0):

- `project_v23_cycle_close.md` — v2.3 close-out facts; ship SHA
  `b00473d`, PR `#175`, cycle-tip +461 LOC.
- `project_v10_p5_gate_deadlock.md` — v10 P5 entry-gate deadlock;
  issue #177 filed 2026-05-18; blocks #112.
- `project_v10_rl_track.md` + `project_v10_p4_hold_lifted.md` — RL
  track status (P4 merged cf7d003 PR #176; gate semantics surfaced).
- `feedback_soak_cli_pool_flag.md` — `--cli-pool-size 2` still required.
- `feedback_no_self_monitor.md` — polarity-flip rule unchanged.
- `MEMORY.md` index entries for any of the above.

## Operator decisions to record at P0 fire

1. **Cycle type.** Feature (≥ 1 lever wired; soft LOC ≤ 1500 per
   Amendment A; BLOCK at 1.5× = 2250) vs consolidation (net LOC ≤ 0
   vs P0-merge tip per Amendment C). Default lean: **consolidation**
   — alternation hygiene (v2.3 was feature, +461 LOC).

   **Override case**: if Amendment D scope (docs-only) + Path-D P5
   synthetic-fixture implementation (~600 LOC) sequenced together,
   choose feature. Note: Amendment D alone fits consolidation cycle.

2. **`WIRED_LEVER_LEDGER_COUNT` posture.** Currently 1 (JsonlTailWorker
   production wiring landed v2.3 P1 Seed 6, `76b137d`). Feature cycle
   classification requires ≥ 1 new lever wired OR retains existing
   wired-lever count without rip.

   **Standing candidates** (if feature):
   - Path-D P5 shadow harness implementation (synthetic-fixture
     mode per issue #177 disposition). LOC ~600 (rl/shadow.py +
     rl/stop_conditions.py + 2 CLIs + 2 test files + design append).
     Wire status: harness lives behind P5 phase prompt, fires at v10.3.
   - `BRIDGE_L4_FALLBACK_CONFIDENCE` wiring per #124 (still blocked
     by ADR-18 surface freeze; lifting requires its own amendment).

3. **ADR-18 Amendment D — v10 gate split.** Per issue #177 disposition
   recommendation, mint Amendment D restructuring v10 P5 entry gate:
   - v10.1-mode: P5 fires when baseline arm n ≥ 200 effective updates
     AND baseline arm CI ≤ 0.10 → infrastructure-validation shadow run.
   - v10.3-mode: original gate (non-baseline arm clears both) → real
     promotion. Lands when v10.3 stochastic propensities ship.
   - Scope: v10 EXPERIMENTAL track per ADR-18 row table L71. No FROZEN
     surface touched.
   - Decision: draft Amendment D text in P0 PR body OR defer to
     dedicated PR within v2.4 cycle? Default: draft in P0 PR body
     (matches Amendments A/B/C pattern).

4. **ADR-18 Rule 5 backlog cap.** Verify open-backlog count at P0
   fire. If above prior cycle's cap, operator must:
   - Accept another cap-bump (record in `docs/v2.4-task-plan.md`),
     OR
   - Mint Rule 5 amendment documenting cycle-handoff exemption.

5. **v10 freeze-lift overlap.** Per ADR-18 Rule 1 + #131 trigger
   cond 2, v10.x cycle cannot mint while v2.x is in P0–P3. State
   whether v2.4 is short (≤ 4 phases) to free v10.x slot — but note
   v10.x is now additionally gated on #177 resolution + #112 close,
   so freeze-lift overlap is secondary.

6. **Issue #111 close**. P4 trainer DOD met (cf7d003) but gate
   semantics under #177 amendment. Decision: close #111 at P0 (DOD
   verification complete) OR hold until Amendment D lands? Default:
   close at P0 with body comment linking #177 as gate-semantics
   follow-up.

## Carry-forwards from v2.3 (re-triage at P0 fire)

Disposition for each seed at P0 fire (default in parens, operator
may override):

1. 🟡 Seed v2.3-A — Sonnet-DIP investigation (0.9474 → 0.8182 at v2.3
   ship-gate). WATCH default; FIRE if root-cause hypothesis ready.
2. 🟡 Seed v2.3-B — Overall p95 partial-recovery watch (+4.54s vs
   v2.2; v2.3 Seed-1 partial recovery 12.238 → 10.584s). WATCH;
   re-measure at P2.
3. 🔴 Seed v2.4-A (NEW) — v10 P5 deadlock #177 disposition.
   - Default: FIRE Amendment D (docs-only, P0/P1 scope).
   - Parallel: FIRE Path-D P5 synthetic-fixture implementation (if
     feature cycle).
4. 🟡 Seed v2.4-B (NEW) — #111 close housekeeping.
5. 🟢 Open seeds — Promotion-criterion-bound seeds from v2.3 backlog
   (re-evaluate at P0; default carry forward).

## Paired ADR-18 §"Amendments" entries (planned at P0)

- **Amendment D** (default FIRE per decision #3): v10 P5 gate split
  into v10.1-mode vs v10.3-mode. Draft text lives in P0 PR body.
  Cross-ref issue #177.

## ADR-5 freshness

`ADR-5-latency-budget.md` has §"v2.3 ship-gate baseline" current after
v2.3 close. v2.4 P2 will append §"v2.4 ship-gate baseline" (or skip
if consolidation cycle with LOC delta ≈ 0 and no latency lever wired).
No P0 ADR-5 work.

## DoD

- [ ] Branch opened from `main` at `b00473d` or later.
- [ ] Memory pre-flight stamp in PR body (Amendment B; self-applies).
- [ ] `docs/v2.4-next-steps.md` drafted alongside this frame (mirror
      `docs/v2.3-next-steps.md` pattern).
- [ ] All 6 P0-frame operator decisions recorded in
      `docs/v2.4-task-plan.md` (mint at P0).
- [ ] `docs/v2.4-next-steps.md` §"P0 frame" checklist fully ticked
      with cross-link to P0 PR commit.
- [ ] If cycle = feature: explicit lever-wire commitment recorded
      (Path-D P5 synthetic-fixture if Amendment D scoped together).
- [ ] If cycle = consolidation: deletion-offset survey ≥ 0 LOC net.
- [ ] Amendment D draft text in P0 PR body (default) OR deferred-PR
      pointer (override).
- [ ] Cross-link to ADR-18 Amendment C cycle-tip anchor (must cite
      `<v2.4 P0-merge SHA>..HEAD` template in `docs/v2.4-task-plan.md`).

## Refs

- `docs/v2.4-next-steps.md` (draft alongside; comparison anchor).
- `docs/v2.3-backlog.md` §"Carry-forwards from v2.3" (if drafted at
  v2.3 close).
- `docs/adr/ADR-18-mvp-surface-freeze.md` Amendments A / B / C.
- `project_v23_cycle_close.md`.
- `project_v10_p5_gate_deadlock.md`.
- Issue #177 — v10 P5 entry-gate deadlock disposition.
- Issue #112 — v10 P5 phase (blocked on #177).
- Issue #111 — v10 P4 (PR #176 merged; close at P0 default).
- Issue #131 — v10.x cycle frame (blocked on #112).
