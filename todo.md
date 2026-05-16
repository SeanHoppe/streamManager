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
- [x] **Stale-issue hygiene** — CLOSED 2026-05-16 (PM sweep, no
      successors minted, zero residual scope):
      - #128 (v2.1 P1 probe transport — shipped PR #138).
      - #129 (v2.1 P3 candidate-discovery surfaces — shipped PR #145).
      - #107 (v10 P0 formal design — shipped PR #121).
      - #108 (v10 P1 episode logging — shipped PR #121).
      - #109 (v10 P2 corpus augmentation — shipped PR #122).
- [x] **Correct `docs/jobs/MASTER.md`** row for #111 — "HELD (Q4)" →
      "READY corpus-gated" to mirror `docs/v10-mvp-status.md` §2.
      LANDED PR #158 (2026-05-16). MASTER.md rows for #107 / #108 /
      #109 / #128 / #129 reconciled in same PR (LANDED bucket added,
      legend extended with READY).

### 🟡 Carry-forwards from v2.1 (re-triage at v2.2 P0)

- [x] **Sonnet 0.95 → 0.8636 alignment dip row-level audit.** 🟡
      LANDED PR #161 (2026-05-16, Step 1 of audit DOD). Two newly-
      stably-wrong rows identified: `frog7-wirecli-module-10` and
      `ambig-block-rm-reports-15` — both drift toward weaker verdict.
      Step 2 (cassette replay) operator-bound; ADR-5 §"Caveats" + v2.1-
      backlog §"Alignment-recovery" updated with row table + AUDITED
      stamp. Disposition options: golden update / REQUIREMENTS
      amendment / transient re-run — operator decides after Step 2.
- [ ] **Dormant `JsonlTailWorker.start()` production wiring.** 🟢
      ~30 LOC non-additive runtime-shape change. No prompt yet — fold
      into v2.2 P1 task plan at cycle frame.
- [x] **Soak-summary probe-emit counter.** LANDED 2026-05-16 (chore
      branch `chore/soak-summary-probe-counter`). 7 LOC additive in
      `tools/soak_driver.py`: `_DriverState.ppp_auto_probes_emitted`
      counter, callsite bump in `--ppp-auto-probe` block, soak-summary
      closing print `[soak] PPP auto-probes emitted: N`. Closes v2.1
      carry-forward observability gap per ADR-5 §"PPP cadence note".

### 🟢 Standalone hardening (parallel to v2.2 substance)

- [x] **Cassette CI guard (#132).** LANDED PR #159 (2026-05-16).
      `src/stream_manager/envelope_kinds.py` allowlist + 
      `tests/test_envelope_coverage.py` (2 assertions: cassette
      coverage + write_envelope backfill audit). Scoped to
      `bus.write_envelope` kinds; `Message.type` coverage remains
      convention. Memory `feedback_cassette_must_cover_new_envelopes.md`
      updated convention → enforced rule.
- [x] **Robin capability hooks (#116 + #117).** LANDED PR #160
      (2026-05-16). Pre-spike confirmed: PreToolUse hooks can target
      `agent_type == "robin"` cleanly. `.claude/hooks/robin-bash-
      timeout.ps1` rejects robin Bash with timeout > 300_000 ms; main
      thread exempt. `permissions.deny` extended with
      `Bash(sqlite3 *rl_episodes.db*)` + `Bash(sqlite3 *rl_shadow.db*)`
      symmetric to main + robin (Python sqlite3 module remains
      allowed).

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
   analysis. **Step 1 of audit DOD landed (PR #161, 2026-05-16)**:
   2 newly-stably-wrong rows identified (`frog7-wirecli-module-10`
   golden=SUGGEST → live=NONE; `ambig-block-rm-reports-15` golden=
   GUIDE → live=SUGGEST) — both drift toward weaker. Step 2
   (cassette replay) operator-bound. Promote to 🔴 only if v2.2 P0
   reproduces on fresh control.
4. ~~**MASTER.md is stale**~~ RESOLVED 2026-05-16 (PR #158). Row for
   #111 corrected (HELD Q4 → READY corpus-gated); LANDED rows added
   for #107 / #108 / #109 / #128 / #129; status legend extended with
   `READY`.
5. ~~**#128 + #129 GH issues are stale-OPEN.**~~ RESOLVED 2026-05-16.
   PM hygiene sweep closed five stale-OPEN issues: #107, #108, #109
   (v10 P0/P1/P2 — all shipped via PRs #106/#121/#122) + #128, #129
   (v2.1 P1/P3 — shipped via PRs #138/#145). MASTER.md reconciliation
   shipped in PR #158.
6. **v2.2 cycle type undecided.** Feature vs consolidation — affects
   LOC budget, whether carry-forwards can fold in, and whether v2.x
   blocks the v10.x cycle slot (per #131 trigger cond 2). Operator
   decision at v2.2 P0 fire.
7. ~~**#116 PreToolUse pre-spike**~~ RESOLVED 2026-05-16 (PR #160).
   `agent_type` field in PreToolUse JSON discriminates main vs robin
   cleanly per [docs](https://code.claude.com/docs/en/hooks). Full
   capability-layer fix shipped (Bash timeout hook + sqlite3 deny).
8. ~~**No `--total-events` flag**~~ RESOLVED 2026-05-16 (path B,
   docs-only). ADR-17 + `docs/soak-trigger-matrix.md` rewritten to
   reference `--total-seconds 120 --interval-seconds 20` form;
   `tools/soak_driver.py` flag set unchanged. v2.1-backlog 🟡 item
   marked RESOLVED. If a future cycle prefers Path A (add the flag),
   reopen as a feature-cycle item.
9. **INTENT.md ↔ todo.md gap analysis (2026-05-16).** 12 gaps logged
   in [`docs/intent-todo-gap-2026-05-16.md`](docs/intent-todo-gap-2026-05-16.md).
   Gaps 1–4 (cadence FR / sub-agent scope-escalation FR / dashboard
   regression watch / API-timeout invariant test) are v2.2 P0 phase
   candidates. Gaps 5–9 graduate to `docs/v2.2-backlog.md` at P0
   mint (promotion criteria stated per seed). Gaps 10–12 are
   bookkeeping drift — refresh at INTENT pre-flight pass per #133.
   Operator decisions required at P0 mint: cycle type, ADR-18 Rule 5
   cap-bump acceptance for backlog growth 1→6.
