# Open-task scoping — 2026-05-16

> Snapshot of unchecked items in `todo.md` after PRs #158/#159/#160/#161/#162
> landed. Each row = scope, owner-binding, blocker, est LOC, prompt ref,
> next action. Read alongside `todo.md` (canonical state) + `docs/jobs/MASTER.md`
> (cross-cycle tracker).
>
> **Lifetime:** discardable after v2.2 P0 cycle frame mints — at that point
> the live items either fold into v2.2 phase prompts or graduate to the
> v2.2 backlog. Delete this file at v2.2 P0 fire.

---

## Bucket 1 — v2.x main cycle (5 open)

### 1.1 🔴 Mint v2.2 P0 cycle frame

- **Scope.** Open `feat/v2.2-p0-cycle-frame` or `chore/v2.2-p0-cycle-frame`
  branch. Pick cycle type (feature vs consolidation). Land paired
  ADR-18 §"Amendments" A (#130 Rule 3 LOC ceiling) + B (#133 Rule 6
  memory pre-flight). Stub P1–P4 phase prompts. Write `docs/v2.2-
  task-plan.md`. Mint `project_v22_cycle_frame.md` memory.
- **Owner-bind.** Operator. Cycle-type call + lever-ledger posture
  decision = operator-only (per prompt §"Operator decisions").
- **Blocker.** None. Pre-flight already partly done (memories verified
  fresh as of 2026-05-16 PM snapshot).
- **Est LOC.** ~30 src/test (none expected — P0 is docs-only), ~400
  docs (ADR-18 amendments + task plan + phase prompt stubs).
- **Prompt.** `docs/prompts/v2.2-orchestration/phase-0-cycle-frame.md`.
- **Closes.** #130, #133. Unlocks v10.x freeze-lift slot if cycle is
  short (≤4 phases).
- **Next.** Operator fires P0 when ready. Drafter (this agent) cannot
  pick cycle type.

### 1.2 🟢 JsonlTailWorker.start() production wiring

- **Scope.** Call `JsonlTailWorker.start()` at startup site
  (`dashboard/server.py` startup hook or `streamManager` entry).
  Resolve `SM_OWN_SESSION_ID` at startup. Document non-additive
  runtime-shape change in PR body §"Disclosed non-additive seam
  hunk" per ADR-18.
- **Owner-bind.** Either main agent OR operator. Risk: production
  worker thread becomes live → behavioural change. Operator review
  required pre-merge.
- **Blocker.** v2.2 cycle type decision (whether worker wiring goes
  into v2.2 P1 or defers to v2.3).
- **Est LOC.** <30.
- **Prompt.** None yet. Mint inside v2.2 P0 task plan.
- **Closes.** v2.1 carry-forward item (per v2.1-backlog §"Carry-
  forwards").
- **Next.** Wait for v2.2 P0 disposition.

### 1.3 ✅ Soak-summary probe-emit counter — LANDED 2026-05-16

- **Scope.** Wire `_emit_ppp_auto_probe` to bump a counter; print
  `PPP auto-probes emitted: N` in soak-summary closing block.
- **Owner-bind.** Main agent. Trivial additive.
- **Blocker.** None.
- **Est LOC.** 7 additive in `tools/soak_driver.py` (close to ~5
  estimate).
- **Prompt.** None needed.
- **Closes.** v2.1 carry-forward 🟢. Observability gap per ADR-5
  §"PPP cadence note".
- **Status.** SHIPPED via PR #163 (branch
  `chore/soak-summary-probe-counter`). `_DriverState.ppp_auto_probes_emitted`
  field added; callsite bumps inside `args.ppp_auto_probe` block;
  summary closing block prints `[soak] PPP auto-probes emitted: N`.

### 1.4 🟢 Remote-CLI monitoring seed

- **Scope.** Promotion-gated. Stays as backlog seed until concrete
  remote-monitoring use case lands on deck.
- **Owner-bind.** Operator (promotion decision).
- **Blocker.** No concrete use case.
- **Est LOC.** N/A — not promoted.
- **Prompt.** N/A.
- **Next.** No action. Re-triage at v2.2 P0.

### 1.5 ✅ `--total-events` flag drift — RESOLVED Path B 2026-05-16

- **Scope.** Option A: add `--total-events` flag to `tools/soak_driver.py`
  matching ADR-17 + matrix wording. Option B: amend ADR-17 + matrix
  to reference `--total-seconds` form (drop flag from docs).
- **Owner-bind.** Either path. Operator picks A vs B.
- **Disposition.** Path B chosen (docs-only). Reversible — if Path A
  becomes preferred, reopen as a feature-cycle item.
- **Est LOC.** ~16 docs (B); 0 src/test.
- **Closes.** v2.1-backlog 🟡 §"`--total-events` flag drift".
- **Status.** SHIPPED via PR #164 (branch
  `docs/total-events-flag-drift-path-b`). ADR-17 Tier 1.5 + Tier
  4-candidate + matrix quick-ref + Tier 3 default flag-name updated
  to `--total-seconds`/`--interval-seconds` form. v2.1-backlog
  entry rewritten to RESOLVED.

---

## Bucket 2 — v10 RL companion track (6 open, mostly sequential)

### 2.1 🔴 Run v10 corpus-fill (≥200 live episodes)

- **Scope.** Fire Tier-3 soak or backfill extractor (PR #156) to fill
  `rl_episodes.db` to ≥200 live episodes (currently 0).
- **Owner-bind.** Operator only. Long-running soak (>5 min) launches
  via `run_in_background` + `ScheduleWakeup`; subagent path forbidden
  per `feedback_subagent_long_task_abandonment.md`. PR #155 + #156
  enabled the corpus-fill paths.
- **Blocker.** None (paths shipped).
- **Est LOC.** 0 (operational, not code).
- **Prompt.** `docs/prompts/v10-orchestration/task-p4-corpus-fill.md`.
- **Closes.** Unblocks #111.
- **Next.** Operator fires soak/backfill.

### 2.2 🔴 Fire v10 P4 — Bandit trainer (#111)

- **Scope.** Thompson + CMDP + promotion gate. Per v10 design §6.
- **Owner-bind.** Operator + main agent. Per ADR-18 ≤700 LOC cap.
- **Blocker.** 2.1 (corpus-fill ≥200 episodes).
- **Est LOC.** ≤700.
- **Prompt.** `docs/prompts/v10-orchestration/phase-4-bandit-trainer.md`.
- **Closes.** #111. Unblocks #112.
- **Next.** Wait for 2.1.

### 2.3 🔴 Fire v10 P5 — Shadow A/B (#112)

- **Scope.** Shadow A/B + ship criteria (3 hard constraints: FR-OG-7,
  HITL-agreement floor, alignment-eval pass-rate floor).
- **Owner-bind.** Operator + main agent.
- **Blocker.** 2.2 (#111 close).
- **Est LOC.** ≤600.
- **Prompt.** `docs/prompts/v10-orchestration/phase-5-shadow-stop-conditions.md`.
- **Closes.** #112. Unblocks #131.
- **Next.** Wait for 2.2.

### 2.4 🔴 Fire v10.x cycle frame (#131)

- **Scope.** Mint v10.x cycle frame when 3 trigger conds hold (#112
  closed; v2.x P0–P3 slot open; #124 + #125 still open).
- **Owner-bind.** Operator.
- **Blocker.** 2.3 (#112 close) + v2.x slot timing.
- **Est LOC.** ~400 docs.
- **Prompt.** `docs/prompts/v10x-orchestration/phase-0-cycle-frame.md`
  (skeleton minted).
- **Closes.** #131. Unblocks #124 + #125.
- **Next.** Wait for 2.3.

### 2.5 🔴 v10.x P1 — wire `BRIDGE_L4_FALLBACK_CONFIDENCE` (#124)

- **Scope.** Un-ADVISORY `_stage_1_golden`. Reclassify
  `model_router.route` callsite from FROZEN → EVOLVING (requires
  ADR-18 surface-freeze amendment minted at v10.x cycle frame P0).
- **Owner-bind.** Main agent + operator review (FROZEN seam touch).
- **Blocker.** 2.4 (v10.x cycle frame mint).
- **Est LOC.** TBD inside v10.x P0.
- **Prompt.** None yet. Mint inside v10.x P0.
- **Closes.** #124. Job doc: `docs/jobs/issue-124.md`.
- **Next.** Wait for 2.4.

### 2.6 🔴 v10.x P2 — restore Ridge-Q DR estimator (#125)

- **Scope.** Replace IPS aliases (`doubly_robust_estimate`,
  `cross_validated_dr`) with real Ridge-Q + Cholesky solver. v10 P3
  scoped-out at 600 LOC cap; restoration ~+80 LOC requires offset.
- **Owner-bind.** Main agent + operator review (OPE harness path).
- **Blocker.** 2.4 (v10.x cycle frame mint).
- **Est LOC.** ~80 additive (offset required per ADR-18 Rule 3).
- **Prompt.** None yet. Mint inside v10.x P0.
- **Closes.** #125. Job doc: `docs/jobs/issue-125.md`.
- **Next.** Wait for 2.4.

---

## Bucket 3 — companion side-track (1 open)

### 3.1 🟡 PR #154 — robin self-vs-other monitoring (DRAFT)

- **Scope.** Doc-only design currently. Needs operator sign-off + 12
  tests written before any code lands. Follow-up issue #153 (auto-
  export `BRIDGE_SM_SELF_SESSION_ID`).
- **Owner-bind.** Operator (sign-off) → main agent (12 tests + code).
- **Blocker.** Operator sign-off.
- **Est LOC.** TBD (post-sign-off).
- **Prompt.** None (design embedded in PR #154 body).
- **Closes.** PR #154 + #153.
- **Next.** Operator reviews + signs off OR rejects.

---

## Cross-cutting

### Sequential chain (5-deep)

`2.1 corpus-fill → 2.2 #111 → 2.3 #112 → 2.4 #131 → 2.5 #124 + 2.6 #125`.
Each link is a separate cycle stage. ADR-18 freeze-lift cannot mint
until shadow ship-criteria pass. Tail-end (2.5 + 2.6) is multi-month
horizon.

### Parallelisable items

Items doable in any order vs the v10 chain:
- 1.1 v2.2 P0 cycle frame (operator-bound).
- 1.2 JsonlTailWorker wiring (post-1.1).
- ~~1.3 Soak-summary probe-emit counter~~ — LANDED 2026-05-16.
- ~~1.5 `--total-events` flag~~ — LANDED 2026-05-16 (path B).
- 3.1 PR #154 sign-off (operator-bound).

### Operator-bound items

Cannot be dispatched by an agent dev session:
- 1.1 cycle-type decision.
- 1.4 promotion decision.
- 1.5 A vs B disposition.
- 2.1 long-running soak.
- 2.2 / 2.3 phase fires (operator gates each).
- 2.4 cycle frame fire.
- 3.1 sign-off.

### Agent-dispatchable items

Could be picked up by a future dispatch pass without operator gating:
- ~~1.3 soak-summary probe-emit counter~~ — LANDED 2026-05-16 (PR #163).
- ~~1.5 path B (docs-only ADR-17 amendment)~~ — LANDED 2026-05-16 (this branch).

### Operator-decision prompt minted 2026-05-16

After the agent-dispatch pass shipped 1.3 (PR #163) + 1.5 path B,
the remaining items are blocked on operator decisions / operator-
only operational fires. A consolidated decision prompt covers them:

```
docs/prompts/operator-decisions-2026-05-16.md
```

Sections: 1.1 cycle-type, 1.2 wiring (post-1.1), 1.4 promotion
seed, 2.1 corpus-fill fire, 2.2–2.6 v10 chain (sequentially gated),
3.1 PR #154 sign-off.

### Memory + doc anchors

- `docs/jobs/MASTER.md` — issue tracker.
- `docs/v10-mvp-status.md` — v10 phase ledger.
- `docs/v2.1-backlog.md` §"Carry-forwards from v2.1" — v2.2 handoff.
- `docs/v2.2-backlog.md` — v2.2 seed list (1 item: remote-CLI).
- `docs/adr/ADR-18-mvp-surface-freeze.md` — cycle-discipline rules.
- `docs/adr/ADR-5-latency-budget.md` §"v2.1 ship-gate baseline /
  Caveats" — alignment-dip row-level audit Step 1.
