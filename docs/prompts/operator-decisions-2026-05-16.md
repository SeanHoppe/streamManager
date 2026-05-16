# Operator-decision prompt — 2026-05-16

> Minted out of the goal-driven dispatch pass on `docs/open-tasks-
> 2026-05-16.md`. Two open items shipped (1.3 PR #163, 1.5 path B PR
> pending). The remaining items below are blocked on **operator
> decisions** or **operator-only operational fires** that an agent
> cannot resolve from the dev session.
>
> Each section: item ref → root cause → recommended solution →
> exact next action.
>
> **Lifetime.** Delete this file when v2.2 P0 cycle frame mints
> (same lifetime as `open-tasks-2026-05-16.md`).

---

## 1.1 — Mint v2.2 P0 cycle frame (operator-only)

**Root cause.** Cycle-type decision (feature vs consolidation) and
lever-ledger posture decision are operator-only per
`docs/prompts/v2.2-orchestration/phase-0-cycle-frame.md` §"Operator
decisions". An agent dev session cannot choose between feature vs
consolidation without operator input — the choice depends on
business priorities, not codebase signals.

**Recommended solution.** Operator fires the existing phase-0
prompt:
```
docs/prompts/v2.2-orchestration/phase-0-cycle-frame.md
```
Pre-flight already partly done (memories verified fresh 2026-05-16
PM snapshot).

**Closes.** #130, #133. Unlocks v10.x freeze-lift slot if cycle is
short (≤4 phases).

**Next.** Operator fires P0 when ready.

---

## 1.2 — Dormant `JsonlTailWorker.start()` production wiring

**Root cause.** Blocked on 1.1. Whether the wiring lands in v2.2 P1
or defers to v2.3 depends on the cycle-type decision in 1.1
(consolidation cycle = wire it; feature cycle = defer to v2.3).

**Recommended solution.** No standalone prompt needed. Folded into
v2.2 P0 task plan at cycle frame minting.

**Next.** Wait for 1.1.

---

## 1.4a — INTENT.md gap-analysis fold-in (operator-only at P0)

**Root cause.** Agent gap-synthesis pass (2026-05-16) over INTENT.md
+ todo.md surfaced 12 gaps. Gaps 1–4 (cadence FR / sub-agent scope-
escalation FR / dashboard regression watch / API-timeout invariant
test) are P0 phase candidates. Gaps 5–9 graduate to v2.2-backlog.
Fold-in decision depends on cycle-type (1.1) AND ADR-18 Rule 1 carve-
out (gap 2 touches FROZEN `governance.py`) AND Rule 5 backlog cap-
bump acceptance (1 → 6 seeds).

**Recommended solution.** Operator reads
```
docs/intent-todo-gap-2026-05-16.md
```
at v2.2 P0 fire and decides per-gap at §"Backlog graduation
procedure".

**Individual prompts minted 2026-05-16** under
`docs/prompts/v2.2-orchestration/gap-*.md` (12 files, one per gap).
Operator dispatches each at P0:

| Gap | Prompt | Disposition at P0 |
|---|---|---|
| 1 | `gap-1-cadence-enforcement-fr.md` | Fold into v2.2 P-N IF cycle = feature; else defer v2.3 |
| 2 | `gap-2-subagent-scope-escalation-fr.md` | Fold IF cycle = feature AND Rule 1 carve-out accepted |
| 3 | `gap-3-dashboard-regression-watch.md` | Fold either cycle type (cheap) |
| 4 | `gap-4-api-timeout-invariant-test.md` | Fold either cycle type (ADR-18-clean) |
| 5 | `gap-5-context-rank-budget-invariant.md` | Graduate to v2.2-backlog (already pre-seeded) |
| 6 | `gap-6-learn-mode-allow-promotion.md` | Graduate to v2.2-backlog |
| 7 | `gap-7-topology-discovery-coverage.md` | Graduate to v2.2-backlog |
| 8 | `gap-8-out-of-scope-guard-scans.md` | Graduate to v2.2-backlog |
| 9 | `gap-9-messages-not-transitions-boundary.md` | Graduate to v2.2-backlog |
| 10 | `gap-10-loc-ceiling-asymmetry.md` | Apply at INTENT-refresh (Option A vs B) |
| 11 | `gap-11-wired-lever-ledger-surface.md` | Apply IF lever counter bumps in P0 |
| 12 | `gap-12-master-stale-ref-strike.md` | Apply at INTENT-refresh (single-line strike) |

**Closes.** Gap-analysis tracking artifact (file deletes when gaps
1–4 land or reject).

**Next.** Operator fires P0 → reads gap-analysis doc → per-gap
decisions inline in P0 prompt response, dispatching individual
gap-N prompts as decided.

---

## 1.4 — Remote-CLI monitoring (backlog seed)

**Root cause.** Promotion-gated. Stays as backlog seed until a
concrete remote-monitoring use case lands on deck.

**Recommended solution.** No action. Re-triage at v2.2 P0.

**Next.** Operator surfaces a concrete use case OR the seed sits at
`docs/v2.2-backlog.md` until cycle close.

---

## 2.1 — Run v10 corpus-fill (≥200 live episodes)

**Root cause.** Operator-only. Long-running soak (>5 min) launches
via `run_in_background` + `ScheduleWakeup`; subagent path forbidden
per `feedback_subagent_long_task_abandonment.md`. The agent main
thread *could* technically launch it, but the operator owns the
quota + the wallclock window — this is an operational fire, not a
code task.

**Recommended solution.** Operator fires the existing prompt:
```
docs/prompts/v10-orchestration/task-p4-corpus-fill.md
```

**Closes.** Unblocks #111 → unblocks 2.2 → 2.3 → 2.4 → 2.5 + 2.6
(the 5-deep v10 chain).

**Next.** Operator schedules the soak / backfill window.

---

## 2.2–2.6 — v10 RL chain (sequentially blocked on 2.1)

**Root cause.** Each link gates on the previous link closing. No
agent action possible until 2.1 fires.

**Recommended solution.** Existing prompts cover the work:
- 2.2 `docs/prompts/v10-orchestration/phase-4-bandit-trainer.md`
- 2.3 `docs/prompts/v10-orchestration/phase-5-shadow-stop-conditions.md`
- 2.4 `docs/prompts/v10x-orchestration/phase-0-cycle-frame.md`
- 2.5 + 2.6 — phase prompts minted inside v10.x P0 (per #131 +
  scoping doc).

**Next.** Wait for 2.1 → 2.2 → 2.3 → 2.4.

---

## 3.1 — PR #154 robin self-vs-other monitoring (DRAFT)

**Root cause.** Operator sign-off required before any code lands.
Design is doc-only; 12 tests still to write.

**Recommended solution.** Operator reviews PR #154 body §"Design"
and either signs off (→ agent writes 12 tests + code) or rejects
(→ close PR + follow-up #153).

**Next.** Operator reviews + signs off OR rejects.

---

## Summary table

| Item | Blocker type | Action owner | Existing prompt? |
|---|---|---|---|
| 1.1 | Cycle-type decision | Operator | Yes — v2.2 P0 prompt |
| 1.2 | Sequential on 1.1 | None until 1.1 | No (folds into v2.2 P0 task plan) |
| 1.4a | Gap-analysis fold-in | Operator at P0 | Yes — intent-todo-gap-2026-05-16 |
| 1.4 | Promotion criterion | Operator | N/A (backlog seed) |
| 2.1 | Operational fire | Operator | Yes — task-p4-corpus-fill |
| 2.2 | Sequential on 2.1 | Wait | Yes — phase-4-bandit-trainer |
| 2.3 | Sequential on 2.2 | Wait | Yes — phase-5-shadow-stop-conditions |
| 2.4 | Sequential on 2.3 | Wait | Yes (skeleton) — v10.x phase-0 |
| 2.5 | Sequential on 2.4 | Wait | No (mint inside v10.x P0) |
| 2.6 | Sequential on 2.4 | Wait | No (mint inside v10.x P0) |
| 3.1 | Operator sign-off | Operator | Embedded in PR #154 body |

---

## What an agent dev session CAN do right now

Nothing additional beyond the 2 PRs already dispatched
(PR #163 + path-B PR). Every remaining item is blocked on
operator decision, operator sign-off, or operator-only operational
fire (long-running soak). Agent will idle on this doc until v2.2
P0 mints OR a new agent-dispatchable item lands on deck.

---

## Cross-refs

- `docs/open-tasks-2026-05-16.md` — full open-task scoping.
- `todo.md` — canonical state.
- `docs/jobs/MASTER.md` — cross-cycle issue tracker.
- `docs/v10-mvp-status.md` — v10 RL track ledger.
- ADR-18 §"Surface freeze" — frames what an agent may modify
  without operator review.
