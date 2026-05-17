# v2.3 P0 — Cycle frame

> Minted 2026-05-17 as part of v2.3-pm-mint PR. Cycle type **TBD by
> operator at fire time**. Default lean: **feature** (v2.2 was
> consolidation; alternation hygiene).
>
> Comparison anchor: `docs/v2.3-next-steps.md` §"P0 frame — operator-
> bound decisions". Every decision below must be recorded against
> that checklist when P0 PR opens.

## Branch + base

- Base: `main` after v2.2.0 (tag `3235144`, PR #169).
- Branch: `feat/v2.3-p0-cycle-frame` (feature) or
  `chore/v2.3-p0-cycle-frame` (consolidation) — pick at branch open.
- PR target: `main`.

## Pre-flight (ADR-18 Rule 6 — memory pre-flight per Amendment B)

Verify each load-bearing memory against current repo state before
opening P0 PR. If any cited memory is stale, update it BEFORE
opening P0 PR. Record verification stamp in P0 PR body.

Memories to verify (v2.3 P0):

- `project_v22_cycle_close.md` — v2.2 close-out facts; ship SHA
  `3235144`, PR `#169`.
- `project_v10_rl_track.md` + `project_v10_p4_hold_lifted.md` — RL
  track status (60/200 live episodes post-v2.2 piggyback).
- `feedback_soak_cli_pool_flag.md` — `--cli-pool-size 2` still
  required at every Tier-3 soak.
- `feedback_no_self_monitor.md` — polarity-flip; SM excludes itself.
- `MEMORY.md` index entries for any of the above.

Cross-check `docs/v2.3-next-steps.md` §"P0 frame" checklist row
"Memory pre-flight (Amendment B)" — same set.

## Operator decisions to record at P0 fire (compare against `docs/v2.3-next-steps.md` §"P0 frame")

1. **Cycle type.** Feature (≥ 1 lever wired; soft LOC ≤ 1500 per
   Amendment A; BLOCK at 1.5× = 2250) vs consolidation (net LOC ≤ 0
   vs P0-merge tip per Amendment C). Default lean: **feature** —
   alternation hygiene (v2.2 was consolidation; LOC −6).
2. **`WIRED_LEVER_LEDGER_COUNT` posture.** Currently 0 (3rd
   consecutive cycle inert: v2.0 P3 ripped levers; v2.1 wired none;
   v2.2 wired none). Feature cycle classification requires ≥ 1 lever
   wired. **Standing candidate:** `JsonlTailWorker.start()` production
   wiring (~30 LOC, deferred v2.1 → v2.2). See
   `task-jsonltailworker-wiring.md`.
3. **ADR-18 Rule 5 backlog cap decision.** Backlog enters v2.3 at
   **11 open items** (per `docs/v2.3-next-steps.md` §Seeds). Per
   `docs/v2.2-backlog.md` §"ADR-18 Rule 5 — backlog hard cap"
   closing paragraph, operator must either:
   - Accept another cap-bump (record in `docs/v2.3-task-plan.md`
     §"Cycle-discipline guardrails"), OR
   - Mint a Rule 5 amendment to ADR-18 documenting the cycle-
     handoff exemption pattern verbatim.
4. **v10 freeze-lift overlap.** Per ADR-18 Rule 1 + #131 trigger
   cond 2, v10.x cycle cannot mint while v2.x is in P0–P3. State
   whether v2.3 is short (≤ 4 phases) to free the v10.x slot.

## Carry-forwards from v2.2 (re-triage, per `docs/v2.3-next-steps.md`)

Disposition for each seed at P0 fire (default in parens, operator
may override):

1. 🟡 Seed 1 — Overall p95 regression watch (WATCH; re-measure at P2).
2. 🟡 Seed 2 — Haiku floor watch (WATCH; re-measure at P2).
3. 🔴 Seed 3 — Soak-driver PYTHONPATH fix (FIRE P1).
4. 🟡 Seed 4 — Soak-summary dual-anchor (FIRE P1 hardening).
5. 🔴 Seed 5 — v10 P4 corpus-fill (FIRE BG, Path A re-soak default).
6. 🟡 Seed 6 — JsonlTailWorker wiring (FIRE P1 IF feature; DEFER ELSE).
7–11. 🟢 Seeds 7–11 — INTENT graduated (NOT FIRED; promotion-criterion-
       bound).
12. 🟡 Seed 12 — Remote-CLI monitoring (NOT FIRED; demand-bound).

## Paired ADR-18 §"Amendments" entries (only if minted at P0)

None planned. v2.3 P0 default = no new amendments. If operator
chooses Rule 5 amendment route (decision #3 above), draft language
in same PR body.

## ADR-5 freshness

`ADR-5-latency-budget.md` has §"v2.2 ship-gate baseline" current.
v2.3 P2 will append §"v2.3 ship-gate baseline". No P0 ADR-5 work.

## DoD

- [ ] Branch opened from `main` at `3235144` or later.
- [ ] Memory pre-flight stamp in PR body (Amendment B; self-applies).
- [ ] All 5 P0-frame operator decisions recorded in
      `docs/v2.3-task-plan.md` (mint at P0).
- [ ] `docs/v2.3-next-steps.md` §"P0 frame" checklist fully ticked
      with cross-link to P0 PR commit.
- [ ] If cycle = feature: explicit lever-wire commitment recorded.
- [ ] If cycle = consolidation: deletion-offset survey ≥ 0 LOC net.
- [ ] Cross-link to ADR-18 Amendment C cycle-tip anchor (must cite
      `<v2.3 P0-merge SHA>..HEAD` template in `docs/v2.3-task-plan.md`).

## Refs

- `docs/v2.3-next-steps.md` (just-minted; comparison anchor).
- `docs/v2.2-backlog.md` §"Carry-forwards from v2.2".
- `docs/adr/ADR-18-mvp-surface-freeze.md` Amendments A / B / C.
- `project_v22_cycle_close.md`.
