# streamManager — Open TODO roll-up

> PM snapshot 2026-05-16. Two-section split: v10 RL track + non-v10
> (v2.x main). Each item is a short imperative with a link to the
> minted prompt file (where one exists) or the canonical issue / job
> doc.
>
> **Authoritative companions** (do not duplicate state here, read
> directly):
> - `docs/jobs/MASTER.md` — cross-cycle issue tracker.
> - `docs/v10-mvp-status.md` — v10 RL track ledger.
> - `docs/v2.1-backlog.md` §"Carry-forwards from v2.1" — v2.2 cycle-
>   handoff items.
> - `docs/v2.2-backlog.md` — v2.2 seed list.

---

## Non-v10 (v2.x main cycle)

**State:** v2.1.0 shipped 2026-05-11 (tag `8303f38`, PR #150). v2.2
cycle frame **NOT yet minted**. ADR-18 surface freeze in force;
`WIRED_LEVER_LEDGER_COUNT` = 0; DORMANT-N gate inert.

### 🔴 Cycle-gate (must move before v2.2 substantive work)

- [ ] **Mint v2.2 P0 cycle frame** with paired ADR-18 §"Amendments"
      A (#130 Rule 3 LOC ceiling) + B (#133 Rule 6 memory pre-flight).
      Prompt: [phase-0-cycle-frame.md](docs/prompts/v2.2-orchestration/phase-0-cycle-frame.md).
      Closes #130 + #133.
- [ ] **Stale-issue hygiene** (fold into v2.2 P0 PR or paired hygiene
      PR): close #128 (DECIDED 2026-05-08, P1 shipped at PR #138);
      close #129 (P3 shipped at PR #145, task moot).
- [ ] **Correct `docs/jobs/MASTER.md`** row for #111 — "HELD (Q4)" →
      "READY corpus-gated" to mirror `docs/v10-mvp-status.md` §2.
      Fold into v2.2 P0.

### 🟡 Carry-forwards from v2.1 (re-triage at v2.2 P0)

- [ ] **Sonnet 0.95 → 0.8636 alignment dip row-level audit.** 🟡
      severity per `docs/v2.1-backlog.md`. Prompt:
      [task-alignment-dip-row-audit.md](docs/prompts/v2.2-orchestration/task-alignment-dip-row-audit.md).
- [ ] **Dormant `JsonlTailWorker.start()` production wiring.** 🟢
      ~30 LOC non-additive runtime-shape change. No prompt yet — fold
      into v2.2 P1 task plan at cycle frame.
- [ ] **Soak-summary probe-emit counter.** 🟢 ~5 LOC additive in
      `tools/soak_driver.py`. Trivial; no prompt — pick up at any
      sub-phase drain or v2.2 P0 hygiene.

### 🟢 Standalone hardening (parallel to v2.2 substance)

- [ ] **Cassette CI guard (#132).** Bootstrap baseline now available
      from v2.1 P1–P3 envelope kinds. Prompt:
      [task-cassette-ci-guard.md](docs/prompts/v2.2-orchestration/task-cassette-ci-guard.md).
- [ ] **Robin capability hooks (#116 + #117).** Low pri. Prompt:
      [task-robin-capability-hooks.md](docs/prompts/v2.2-orchestration/task-robin-capability-hooks.md).

### 🟢 v2.2 backlog seeds (do not promote without concrete use case)

- [ ] **Remote-CLI monitoring** — 🟡 seed at `docs/v2.2-backlog.md`.
      Promotion criterion: concrete remote-monitoring use case on deck.

---

## v10 RL companion track

**State:** P0/P0a/P1/P2/P3 shipped (5/7 phases; ~60% MVP). v10 P4
Q4 hold **LIFTED 2026-05-11**. Real blocker now = corpus-fill
(`rl_episodes.db` < 200 live episodes; baseline 0 at 2026-05-12).
PRs #155 + #156 just merged to enable corpus-fill paths.

### 🔴 Unblock-P4 path (operator-bound, sequential)

- [ ] **Run corpus-fill** to populate `rl_episodes.db` ≥ 200 live
      episodes. Prompt:
      [task-p4-corpus-fill.md](docs/prompts/v10-orchestration/task-p4-corpus-fill.md).
      Required before phase-4 fires.
- [ ] **Fire v10 P4 — Bandit trainer.** Existing prompt:
      [phase-4-bandit-trainer.md](docs/prompts/v10-orchestration/phase-4-bandit-trainer.md).
      Issue #111. Closes ⇒ unblocks #112.
- [ ] **Fire v10 P5 — Shadow A/B.** Existing prompt:
      [phase-5-shadow-stop-conditions.md](docs/prompts/v10-orchestration/phase-5-shadow-stop-conditions.md).
      Issue #112 (BLOCKED on #111). Closes ⇒ unblocks #131.

### 🔴 ADR-18 freeze-lift chain (BLOCKED on #112 close)

- [ ] **Fire v10.x cycle frame** when 3 trigger conds hold (#112
      closed; v2.x slot open; #124 + #125 still open). Skeleton
      already minted:
      [phase-0-cycle-frame.md](docs/prompts/v10x-orchestration/phase-0-cycle-frame.md).
      Issue #131.
- [ ] **v10.x P1 — wire `BRIDGE_L4_FALLBACK_CONFIDENCE`** + un-ADVISORY
      `_stage_1_golden`. Issue #124. No phase prompt yet (mint inside
      cycle frame P0). Job: `docs/jobs/issue-124.md`.
- [ ] **v10.x P2 — restore Ridge-Q DR estimator.** Issue #125. No
      phase prompt yet (mint inside cycle frame P0). Job:
      `docs/jobs/issue-125.md`.

### 🟡 Companion side-track

- [ ] **PR #154 — robin self-vs-other monitoring (DRAFT).** Doc-only
      design. Needs operator sign-off + 12 tests written before any
      code lands. Follow-up issue #153 (auto-export
      `BRIDGE_SM_SELF_SESSION_ID`).

---

## Sticking points / blockers (PM observations)

1. **v10 corpus-fill is the single biggest unblock right now.**
   Episode count = 0; gate = ≥ 200. Operator must run Tier-3 soak (or
   backfill) before phase-4 fires. Sub-prompt minted to make the run
   reproducible.
2. **v10 chain is 5-deep.** `corpus-fill → #111 → #112 → #131 → #124
   + #125`. Each link is a separate cycle stage. ADR-18 freeze-lift
   cannot mint until shadow ship-criteria pass. Tail-end deliverables
   may be a multi-month horizon.
3. **v2.1 P4 alignment dip (🟡)** is the open quality regression
   carried out of v2.1. Causally NOT PPP-attributable per close-out
   analysis, but ADR-5 caveat documents the drop. Promote to 🔴 only
   if v2.2 P0 reproduces on fresh control.
4. **MASTER.md is stale** on #111 status (still says HELD Q4; reality
   is hold lifted). One row edit; fold into v2.2 P0.
5. **#128 + #129 GH issues are stale-OPEN.** Decisions made + work
   shipped; closure is the only remaining step. Hygiene PR.
6. **v2.2 cycle type undecided.** Feature vs consolidation — affects
   LOC budget, whether carry-forwards can fold in, and whether v2.x
   blocks the v10.x cycle slot (per #131 trigger cond 2). Operator
   decision at v2.2 P0 fire.
7. **#116 PreToolUse pre-spike** (can hooks distinguish robin vs
   main?) is BLOCKING for #116 capability-layer fix. If NO, fallback
   is partial coverage; document the limit.
8. **No `--total-events` flag** in `tools/soak_driver.py` despite
   ADR-17 + soak-trigger matrix reference (v2.1-backlog 🟡 item).
   Disposition deferred from v2.1 to v2.2. Trivial PR either
   direction.
