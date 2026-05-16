# INTENT.md ↔ todo.md gap analysis — 2026-05-16

> Source: agent gap-synthesis pass over `INTENT.md` + `todo.md` after
> v2.1.0 ship (tag `8303f38`). Surfaces INTENT-stated scope not tracked
> in todo + todo scope not reflected in INTENT, with concrete promotion
> destinations.
>
> **Lifetime.** Delete this file when v2.2 P0 cycle frame mints AND
> gaps 1–4 have either landed as P0 phase items or been explicitly
> rejected by operator with rationale recorded. Gaps 5–9 graduate to
> `docs/v2.2-backlog.md` at v2.2 P0 mint (see §"Backlog graduation").

---

## Destination summary

| Gap | INTENT § | Destination | Action owner |
|---|---|---|---|
| 1 Cadence FR | §"Safety priorities" frame | v2.2 P0 phase candidate | Operator (cycle-type decision) |
| 2 Sub-agent scope-escalation FR | §"Sub-agent governance principles" | v2.2 P0 phase candidate | Operator |
| 3 Dashboard regression watch | §"UI / HITL principles" + §"Hot zones" | v2.2 P0 phase candidate | Operator |
| 4 API-timeout invariant test | Safety priority #5 | v2.2 P0 phase candidate | Operator |
| 5 Context rank + 400-tok budget invariant | §"Project context loading" | v2.2-backlog seed | Promotion-gated |
| 6 Learn-mode ALLOW-promotion regression | §"What governance should learn" | v2.2-backlog seed | Promotion-gated |
| 7 Topology-discovery coverage | §"What this project is" | v2.2-backlog seed | Promotion-gated |
| 8 Out-of-scope guard scans | §"Out of scope" | v2.2-backlog seed | Promotion-gated |
| 9 "Governs messages, not transitions" boundary | §"Sub-agent governance principles" | v2.2-backlog seed | Promotion-gated |
| 10–12 | Bookkeeping drift | Refresh at v2.2 P0 (no new tracking) | Agent |

---

## High — fold into v2.2 P0 cycle frame as candidate phase items

### Gap 1 — Cadence enforcement FR

**INTENT claim.** §"Safety priorities" frame: "SM enforces two things
beyond raw safety: plan alignment and cadence (is the session making
forward progress?)."

**Gap.** Plan alignment has a 🟡 row (Sonnet dip audit Step 1, PR #161).
Cadence has zero todo coverage. No FR, no detector, no test, no
regression watch.

**Phase candidate shape.**
- One FR-cadence-N requirement: define "forward progress" signal
  (e.g. monotone-decreasing open-item count, monotone-increasing
  closed-PR count, or assistant-turn novelty score over rolling window).
- One detector wired into governance.evaluate path advisory-only
  (consistent with ADR-18 Rule 2 — DORMANT-1 at first wiring).
- One regression test in `tests/` exercising the detector against a
  fixture session.

**Promotion criterion for v2.2 P0 fold-in.** Operator confirms cycle
type = **feature** (consolidation cycle = defer).

---

### Gap 2 — Sub-agent scope-escalation FR

**INTENT claim.** §"Sub-agent governance principles": "Agent profiles
that repeatedly exceed scope MUST escalate governance mode for that
agent specifically." Plus: "Reviewer agents: SUGGEST scope only;
direct CLI execution from a reviewer → BLOCK" and "Developer agents
near protected files: GUIDE → INTERVENE".

**Gap.** Zero todo items track these scope-escalation paths. PR #154
robin self-vs-other monitoring is monitoring, not scope-escalation
enforcement.

**Phase candidate shape.**
- One FR-sub-agent-scope-N requirement: define "repeatedly exceed
  scope" threshold (count + window) per agent_type.
- One escalation hook: agent-specific governance mode bump persisted
  in `agent_profiles` table.
- One regression test: synthesised reviewer-agent CLI fire fixture
  → assert BLOCK.

**Promotion criterion.** Cycle type = **feature** AND operator confirms
agent_profiles schema extension is in-cycle scope. Touches FROZEN
surface `governance.py` — needs ADR-18 Rule 1 carve-out decision at P0.

---

### Gap 3 — Dashboard regression watch

**INTENT claim.** §"Hot zones (current)": "`dashboard/server.py`,
`dashboard/static/index.html` — actively touched per cycle." §"UI /
HITL principles" lists monitor-first three-frame, `desktop_pause`/
negative-regression/static-rule auto-foreground rules, ranked-option
memory, paired label+color discipline.

**Gap.** todo.md zero dashboard items. Hot zone unwatched — any
v2.x P-N could regress the three-frame contract silently.

**Phase candidate shape.**
- One smoke test: `tests/test_dashboard_smoke.py` asserts
  `dashboard/server.py` returns 200 + index.html contains the three
  frame anchors (Interactive REPL, Sub-Agents, Background Jobs).
- One badge-discipline lint: AST/regex check that any new badge in
  `dashboard/static/index.html` has paired label + color (no
  color-only signals per INTENT §"UI / HITL principles" final
  bullet).

**Promotion criterion.** Either cycle type — dashboard regression
watch is cheap (~30 LOC, additive tests). Could land in
consolidation cycle.

---

### Gap 4 — API-timeout invariant test

**INTENT claim.** Safety priority #5: "API timeouts must never block
forwarding. A governance API failure degrades to OBSERVE; it does
not stall the bridge."

**Gap.** No todo regression test. v2.x refactors could silently break
the OBSERVE-degrade contract; no canary catches it.

**Phase candidate shape.**
- One regression test: simulate `claude -p` timeout / API 500 →
  assert governance verdict = OBSERVE AND bridge forward latency
  bounded under timeout-fallback budget.
- Add to ship-gate Tier-3 ledger (currently latency + alignment;
  add invariant-degrade as third gate column).

**Promotion criterion.** Either cycle type. Pure additive test;
ADR-18-clean.

---

## Medium — graduate to v2.2-backlog seeds at v2.2 P0 mint

Each seed below ships to `docs/v2.2-backlog.md` with the promotion
criterion stated. ADR-18 Rule 5 backlog cap currently = 1 seed;
adding 5 = 6 total. Operator must decide at P0 mint whether to (a)
accept the cap-bump explicitly, (b) graduate some/all to phase items,
or (c) defer some to v2.3.

### Gap 5 — Project-context rank + 400-token budget invariant test

**Promotion criterion.** Any PR touches `project_context.py` OR
INTENT-priority field rank changes OR alignment dip recurs and root
cause traces to context-loading drift. Until then: seed.

### Gap 6 — Learn-mode ALLOW-promotion regression

**Promotion criterion.** Learn Mode telemetry shows promotion count
drop ≥ 30% week-over-week OR user reports a routine command (e.g.
`pytest`) failing to promote after the documented threshold. Until
then: seed.

### Gap 7 — Topology-discovery coverage

**Promotion criterion.** New unknown-agent pattern surfaces in
production logs (i.e. `agent_profiles` row with `role = "unknown"`
persists > 1 cycle) OR a known-agent profile mis-classifies in a
ship-gate run. Until then: seed.

### Gap 8 — Out-of-scope guard scans

**Promotion criterion.** Security review surfaces a concrete
attack-vector PoC against one of the three INTENT §"Out of scope"
items (transport modification, plaintext token storage, bus DB
exfil) OR a related CVE-class issue is filed. Until then: seed.

### Gap 9 — "Governs messages, not transitions" boundary regression

**Promotion criterion.** A todo / PR review surfaces a code path
where SM gates one agent on another's completion (the exact INTENT-
forbidden pattern) OR `governance.py` review surfaces transition-
gating helpers. Until then: seed.

---

## Low — bookkeeping drift (refresh at v2.2 P0, no new tracking)

### Gap 10 — Feature-cycle LOC ceiling carry-forward asymmetry

**State.** INTENT §"Current cycle posture" lists 4 v2.2 carry-forwards
including "feature-cycle LOC ceiling". todo.md folds it into #130
ADR-18 amendment paired with cycle-gate item. Tracking is correct,
just asymmetric vs INTENT bullet list.

**Action.** At v2.2 P0 mint, decide: either (a) re-add feature-cycle
LOC ceiling as its own todo row alongside dormant JsonlTailWorker /
soak counter / alignment dip; or (b) trim the INTENT bullet to "see
#130 ADR-18 amendment" pointer.

### Gap 11 — `WIRED_LEVER_LEDGER_COUNT` = 0 surface

**State.** INTENT §"ADR-18 governance regime" records counter = 0,
DORMANT-N gate inert. Not surfaced as a plan-alignment-watch in todo.

**Action.** Add a one-line watch entry to todo §"Sticking points" at
v2.2 P0 mint IF v2.2 wires any new lever (counter bumps 0→1).
Otherwise no-op.

### Gap 12 — `docs/jobs/MASTER.md` stale reference in INTENT

**State.** INTENT §"Authoritative status references" still reads
"still rows-stale on #111 hold-lift; update pending". todo sticking
point 4 marks RESOLVED via PR #158 (2026-05-16).

**Action.** Strike the stale-suffix at v2.2 P0 INTENT-refresh pass
(per ADR-18 Rule 6 memory pre-flight #133 — INTENT.md is in pre-
flight scope).

---

## Cross-cut observation

INTENT describes SM as a **forward-enforcing** governance product
(alignment + cadence + sub-agent independence + HITL discipline).
todo.md is dominated by **cycle/track-mechanics** items (P0 mint,
corpus-fill, freeze-lift chain). Forward-enforcement of INTENT's
actual product surface (gaps 1–9) is under-represented relative to
its prominence in the spec.

This asymmetry is expected immediately after a feature-cycle ship
(v2.1.0) — track-mechanics dominates the post-ship triage window.
The risk is the asymmetry **persisting** past v2.2 P0 without
explicit operator decision on which gaps land as phase items.

---

## Backlog graduation procedure

At v2.2 P0 mint, the operator decision flow is:

1. **Cycle type — feature vs consolidation.**
   - Consolidation → gaps 1, 2 deferred to v2.3 (large surfaces);
     gaps 3, 4 still graduate (additive tests, ADR-18-clean);
     gaps 5–9 graduate to backlog regardless.
   - Feature → all four high-priority gaps are P-N phase candidates;
     gap 2 still needs ADR-18 Rule 1 carve-out decision separately.
2. **Backlog cap reconciliation.** v2.2-backlog currently 1 seed.
   Adding gaps 5–9 = 6 total. ADR-18 Rule 5 caps **growth per
   cycle**, not absolute seed count, so adding 5 seeds at P0 mint
   is in-bounds provided the operator explicitly accepts.
3. **Bookkeeping drift.** Gaps 10–12 strike-through at INTENT-refresh
   pass during P0 pre-flight (per #133).

---

## Cross-refs

- `INTENT.md` §"Current cycle posture (as of 2026-05-16)".
- `todo.md` §"Non-v10 (v2.x main cycle)" + §"Sticking points".
- `docs/v2.2-backlog.md` — destination for gaps 5–9 at P0 mint.
- `docs/prompts/v2.2-orchestration/phase-0-cycle-frame.md` — destination
  for gaps 1–4 fold-in decision.
- `docs/prompts/operator-decisions-2026-05-16.md` — companion operator-
  bound queue (gaps 1–4 add to this queue's 1.1 item).
- ADR-18 Rule 5 (backlog cap) + Rule 6 (#133 memory pre-flight, by
  extension INTENT.md pre-flight).
