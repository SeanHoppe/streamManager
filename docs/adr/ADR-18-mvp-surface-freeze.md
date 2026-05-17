# ADR-18: MVP surface freeze + falsify-before-extend rule

- **Status**: Proposed (v2.0 P0)
- **Date**: 2026-05-07
- **Related**: ADR-5 (latency budget), ADR-17 (soak tiers), `docs/v2.0-backlog.md`, `docs/v2.0-task-plan.md`, memory: `feedback_cross_pr_seam_review.md`, `feedback_subagent_stale_mental_model.md`

## Context

Across v1.7 → v1.9 the project shipped three feature cycles with the same
pattern: a new lever was wired, ship-gate measured 0% fire rate, the
lever stayed dormant, and the next cycle added a new module on top of
the still-dormant code. Concretely:

- **v1.7 P2** wired a Haiku fastpath router. `is_ambiguous_block` /
  `is_hitl_synthesis` content-detection flags exist on `RoutingDecision`
  but the pre-CLI dispatch site never reads them; the fastpath has been
  wired-but-unused since v1.7.0. (v1.7 cycle close memory:
  *Haiku fastpath router shipped wired but DORMANT*.)
- **v1.8 P1** wired `is_ambiguous_block` / `is_hitl_synthesis` flag
  computation in `governance._evaluate_inner_core`. v1.8 ship-gate:
  `cli_dispatch_fallback_ms` p95 = 0.00 ms across 60 events. Lever
  fired 0%.
- **v1.9 P1** added a verdict==ENGAGE branch alongside the v1.8
  confidence-floor branch. v1.9 ship-gate: `cli_dispatch_fallback_ms`
  p95 = 0.00 ms across 60 events. Lever fired 0%, second consecutive
  cycle.

While levers were dormant, surface area expanded. v1.9 alone added the
external session watcher (`session_watcher.py` + bus envelopes + dashboard
panels) and Learn Mode JSONL source expansion (~2800 LOC across P2 +
P3) on top of two unfired levers from prior cycles.

The v1.9-task-plan do-not-touch list now spans v1.1 → v1.8 protected
symbols (24+ entries). The v2.0 backlog rolls 🟢 *CLI pool sizing >2*
forward for a third consecutive cycle. Carry-forwards no longer expire.

## Decision

Adopt two complementary rules.

### Rule 1: MVP surface freeze

Every module in the MVP surface is classified into one of three states:

- **FROZEN** — accept-only-bugfix. Public symbols and on-disk schemas
  are stable; modifications must be additive (new optional kwarg, new
  enum case, new metadata field) per the existing do-not-touch
  convention. No new caller paths.
- **EVOLVING** — actively under development. Feature work is allowed
  inside the module, but cross-module seams must reference the module
  in an open task plan or ADR.
- **EXPERIMENTAL** — sibling track. Code lives in the repo for
  observability/iteration but is not on the MVP critical path. Failure
  here cannot block ship-gate. (v10 RL companion track is the canonical
  example.)

Initial classification at the v2.0 P0 cycle frame:

| Module / surface | State | Notes |
|---|---|---|
| `cli_pool` (`CliPool`, `CliWorker`, `CliWorker.send`, `.bridge/cli-pool.pids`) | FROZEN | v1.1 Task J. Already on do-not-touch list. v2.0 P1b A/B uses optional kwargs only. |
| `bus` envelope schemas (`governance_call`, lifecycle envelopes) | FROZEN | Metadata-only extensions. (`governance_fallback_routed` + `governance_envelope_missing_confidence` schemas decommissioned at v2.0 P3 — see §"Decommissioned".) |
| `governance._evaluate_inner_core` content-detection helpers (`_looks_ambiguous_block`, `_looks_hitl_synthesis`, `_AMBIGUOUS_BLOCK_PATTERNS`) | FROZEN | v1.8 P1. Pattern list extends only; flag semantics fixed. Reusable by future work even though current consumer was ripped at v2.0 P3. |
| `model_router.py` band priority + `RoutingDecision` field set | FROZEN | NFR-M1-M5. Extend bands within, never reorder. (`fallback_model_id` field ripped at v2.0 P3 with the Haiku fastpath consumer; see §"Decommissioned".) |
| `LifecycleBridge` + `/api/lifecycle/jobs` + dashboard lifecycle pane | FROZEN | v1.2 Task C. |
| `wirecli` transport + `_VALID_TRANSPORTS = frozenset({"sse"})` | FROZEN | v1.1 Task N + v1.2 Task D. |
| `session_watcher.py` + bg task token registry | EVOLVING | v1.9 P2. Re-registration / pid-validation surface still maturing. |
| `learn_mode.py` (advisory bias, JSONL ingest, categorizer worker) | EVOLVING | v1.3 / v1.4 / v1.9 P3. Categorizer + decay ladder still iterating. |
| `sync_comms` design (gate-and-wait, Session Mirror frame, HMAC-signed bidi `desktop_command`) | EVOLVING | Design FROZEN per memory; impl ~6 sessions ahead. |
| `hitl` synthesis path + `hitl_overrides` WAL table | EVOLVING | Design captured in memory; surface still moving. |
| RL writeback (v10.x companion track) | EXPERIMENTAL | Sibling to v2.x. Cannot block ship-gate. |
| `certPortal` MVP ring | EXPERIMENTAL (separate repo) | FR-OG alignment ref via `MVP-100-PLAN.md` + `maturity-dashboard.html`. |

#### Decommissioned

Surfaces ripped under Rule 2 (DORMANT-N rip-or-revive) or Rule 2
§"What counts as a strike" (anticipatory rip on falsified revival).
Listed for history; symbols are no longer in `src/` and must not be
reintroduced without an ADR amendment.

| Module / surface | State entering rip | Rip date | Rip PR / cycle | Reason |
|---|---|---|---|---|
| Haiku fastpath router (`route()` `is_ambiguous_block` / `is_hitl_synthesis` kwargs + L4 sub-band logic + `RoutingDecision.fallback_model_id` field + pre-CLI dispatch site consumer) | DORMANT-3 | 2026-05-07 | v2.0 P3 | DORMANT-3 mandatory rip per Rule 2. Content-detection helpers (`_looks_ambiguous_block`, `_looks_hitl_synthesis`, `_AMBIGUOUS_BLOCK_PATTERNS`) preserved as FROZEN per v1.8 P1 row above. |
| Confidence-floor + verdict-based fallback retry (`cli_governance.evaluate()` retry branches, `_fallback_confidence_floor()`, `_fallback_mode()`, `BRIDGE_L4_FALLBACK_CONFIDENCE`, `BRIDGE_L4_FALLBACK_MODE`, `governance_fallback_routed` + `governance_envelope_missing_confidence` envelope emission, `cli_dispatch_fallback_ms` timing key) | DORMANT-2 + falsified | 2026-05-07 | v2.0 P3 | P1 A/B (`reports/v2-p1-cli-pool-ab-20260507T141200Z.md`) measured 0% fire rate at all four cli_pool worker-recycle cadences. Anticipatory rip authority per Rule 2 §"What counts as a strike". |

Bus envelope schemas for ripped levers stay on disk (append-only history)
so cassette replay + historical report parsing keep working.

State transitions require an ADR amendment (this document) or a
new ADR. State demotions (FROZEN → EVOLVING) are not allowed without
explicit user approval; the intent is one-way ratchet.

Practical implication: the do-not-touch list in each cycle's task plan
becomes a *read* of this ADR rather than a per-cycle snapshot. New
cycles inherit the FROZEN list automatically.

### Rule 2: falsify-before-extend

For any wired lever (a code path gated on a runtime flag or a
content-detection predicate):

- After **two consecutive ship-gate soaks** with measured fire rate
  = 0%, the lever is declared **DORMANT-2**. Ship-gate emits a WARN.
- After **three consecutive ship-gate soaks** with measured fire rate
  = 0%, the lever is declared **DORMANT-3**. Ship-gate **BLOCKs** the
  cycle. The next cycle MUST either:
  1. Run an A/B that produces a non-zero fire rate (lever revived), or
  2. Rip the lever code, including all dependent flags, instrumentation
     keys (additively-extended from `_last_phase_timings_ms`), and
     do-not-touch entries.

There is no third option. "Carry-forward" is not allowed past
DORMANT-3.

**What counts as a strike.** Counter strikes only on Tier 3
ship-gate soaks. A/B revival probes (e.g. v2.0 P1) do NOT strike;
they either reset the counter on non-zero fire OR feed the next
ship-gate strike via continued 0% fire. A/B falsification of a
revival hypothesis grants *anticipatory rip authority* under this
rule even before the next Tier 3 strike — i.e. a phase may rip the
lever in the same cycle as the failed revival probe rather than
waiting for the ship-gate strike.

Tracking lives in ADR-5 §lever-effect outcomes (existing format
already records fire rate per cycle). The DORMANT-N counter resets on
*any* non-zero fire rate (including A/B probe fire) or on a
deliberate rip.

Current lever ledger after v2.0 P3 rips:

| Lever | Wired in | Dormant cycles | Status |
|---|---|---|---|
| _(no wired levers)_ | — | — | Both prior levers ripped at v2.0 P3 — see §"Decommissioned". DORMANT-N gate inert until next lever introduction. |

<!-- WIRED_LEVER_LEDGER_COUNT: 0 -->

The HTML comment above is **load-bearing**: v2.0 P4 codifies a
DORMANT-N gate in `tools/soak_driver.py` that hard-codes a
`WIRED_LEVER_LEDGER` dict mirroring this ledger. A test asserts
`len(WIRED_LEVER_LEDGER) == int(re.search(r"WIRED_LEVER_LEDGER_COUNT:\s*(\d+)", ADR-18-text).group(1))`.
Any phase that adds, removes, or re-classifies a wired lever MUST
update both this comment and the dict in the same PR. P3 rip phases
update both; future feature phases that wire a new lever bump both.
After v2.0 P3 both numbers are 0; soak_driver `WIRED_LEVER_LEDGER` is
the empty dict and the post-soak summary emits the inert-gate line.

### Rule 3: cycle LOC budget

Every cycle declares a net-LOC delta target in P0 task plan. Default:
**≤500 LOC net add** (additions − deletions in `src/` + `tests/` +
`tools/` + `dashboard/`, computed via
`git --no-pager diff origin/main..HEAD --stat -- src tests tools dashboard`
at ship-gate). Deletion-positive cycles are explicitly allowed and
encouraged.

Exceeding the target requires either:
- An ADR amendment justifying the delta, or
- A consolidation cycle in the *next* version (zero feature additions,
  deletion-only).

v1.9 added ~2800 LOC. v2.0 is declared a **consolidation cycle**:
target ≤ 0 LOC net add (deletion-positive). See `docs/v2.0-task-plan.md`.

**v2.2 P2 Amendment C anchor clarification.** The `origin/main..HEAD`
diff command above is the cycle-discipline gate. v2.2 P0 Amendment A
§"Cycle-start commit anchor" cited the predecessor cycle's release-
tag SHA; v2.2 P2 Amendment C clarifies that **gate** measurement
anchors at the **P0-merge tip** of the cycle being shipped (cycle
budget binds cycle-authored work only — pre-cycle drift is reported
as narrative figure, not gated). See §"Amendments" 2026-05-17.

### Rule 4: phase budget

Maximum **3 numbered phases** per cycle (excluding P0 cycle frame and
the terminal ship-gate phase). v2.0 has P0 + P1 + P2 + P3 + P4 — three
work phases (P1, P2, P3) plus framing + ship-gate. v1.9 had four work
phases (P1, P1a, P2, P3) — one over budget; the overshoot drove the
~2800 LOC delta. Phase budget enforces scope discipline at frame time.

**Definition of "phase".** A *phase* is a top-level numbered work
unit that ships its own PR against `main`. Branch decisions inside
one phase (e.g. v2.0 P3 Branch A vs B), ship-gate sub-tasks (Sn
pattern from `docs/prompts/v1.6-shipgate/`), and post-merge
correctives (Cn sub-cycle pattern from v1.3 / v1.6 / v1.8) do NOT
count against the phase budget. v1.9 P1a counted because it shipped
its own PR; v2.0 P3 Branch A/B is one phase regardless of which
branch fires.

### Rule 5: backlog hard cap

A 🟢 backlog item that has been carried forward across **two cycles**
without graduation must, at the next cycle frame, either:

1. Be promoted to a numbered phase, or
2. Be promoted to an ADR with an explicit accept-as-permanent disposition, or
3. Be deleted from the backlog.

Currently 🟢 *CLI pool sizing >2* has been deferred at v1.7 P3, v1.8 P2,
v1.9 P0 — three cycles. v2.0 P0 must dispose. v2.0 task plan elects
**(2) ADR disposition** — the lever is not the bottleneck while the
fallback path is dormant; revive that first.

## Consequences

**Positive.**

- Cycle scope becomes legible at frame time (LOC budget + phase budget
  + state classification visible in one ADR).
- Dormant levers cannot accumulate indefinitely — DORMANT-3 forces
  rip-or-revive.
- Backlog cannot accumulate indefinitely — 2-cycle cap forces
  graduate-or-drop.
- The do-not-touch list becomes a read of one ADR rather than a per-cycle
  snapshot, eliminating drift between task plans.

**Negative / costs.**

- Adds a P0 obligation to update this ADR each cycle (state
  transitions, dormant-counter reads).
- Ship-gate soak script must read this ADR to compute DORMANT-N
  WARN/BLOCK signal. Initially manual; codify in v2.0 P4 ship-gate
  script extension (still inside LOC budget — purely subtractive after
  Haiku fastpath rip if A/B fails).
- Tightens future cycles' creative latitude. By design.

**Reversibility.** Rules 2–5 can be relaxed by ADR amendment. Rule 1
state transitions are one-way ratchet by intent (FROZEN → EVOLVING
requires explicit user approval).

## Migration

v2.0 P0 lands this ADR + the v2.0-task-plan + 5 phase prompts. No code
changes in P0. v2.0 P1 (cli_pool A/B) is the first phase to run under
the new rules and is also the revival attempt for the DORMANT-2
fallback lever.

If v2.0 P1 A/B produces 0% fire rate at all four arms: revival
hypothesis falsified. Lever stays DORMANT-2 by counter rules
(A/B is not a Tier 3 strike) but P3 invokes *anticipatory rip
authority* (Rule 2 §"What counts as a strike") to rip both the
fallback path AND the Haiku fastpath router (already DORMANT-3 at
cycle start) in the same cycle. P4 Tier 3 ship-gate then measures
the post-rip baseline; the would-be DORMANT-3 strike is moot
because the lever no longer exists. Net deletion target comfortably
met.

If v2.0 P1 A/B produces non-zero fire rate at any arm: fallback
counter resets immediately on the probe fire; v2.0 P3 rips only the
Haiku fastpath router (still DORMANT-3); P4 ship-gate measures the
new ADR-5 baseline. The recommended recycle cadence flows through
`tools/soak_driver.py --worker-recycle-every-n` only;
`CliPool.__init__` default stays `None` (Rule 1 FROZEN — no default
flip).

## Open questions

- Should EXPERIMENTAL state be subject to the same DORMANT-N rule? Initial
  answer: no — experimental tracks are explicitly allowed to ride along
  for observability.
- Does the LOC budget include `docs/`? Initial answer: no — docs are
  the cycle frame mechanism itself; capping them creates a perverse
  incentive against ADR coverage.

## Amendments

### 2026-05-07 — v2.0 P3: subtractive change to `_last_phase_timings_ms`

First-ever removal from the `_last_phase_timings_ms` FROZEN dict in
`src/stream_manager/governance.py` (Rule 1). The
`cli_dispatch_fallback_ms` key is removed alongside the
verdict-fallback retry path rip authorised under Rule 2 §"What counts
as a strike" (P1 A/B falsification at
`reports/v2-p1-cli-pool-ab-20260507T141200Z.md`).

**Precedent.** Subtractive change to a FROZEN timing-key dict is
allowed ONLY when the originating lever is ripped under Rule 2 (or
its anticipatory-rip extension). The key removal happens in the same
PR as the lever rip, never separately. Future subtractive changes
require their own amendment entry below — this precedent does not
generalise to keys belonging to active levers.

`tools/soak_driver.py` formatter additively skips absent keys
(per Rule 1 additivity guidance for cassette / historical-report
parsing); pre-rip soak reports continue to render unchanged.

### 2026-05-12 — v10 P4 B': new FROZEN envelope `governance_decision`

Mints a new bus envelope `governance_decision` as FROZEN under Rule 1.
The envelope is fanned out by `MessageBus.record_decision` to any
subscriber registered via the new `MessageBus.subscribe_decision`
hook. Schema (FROZEN, metadata-only extensions thereafter):

| field | type | source |
|---|---|---|
| `kind` | str (literal `"governance_decision"`) | bus constant |
| `decision_id` | str (UUID) | `decisions.id` |
| `trace_id` | str | alias of `decision_id` (RL convention) |
| `message_id` | str | bus arg |
| `session_id` | str | JOIN `messages.session_id` |
| `project_slug` | str | JOIN `sessions.project_slug` |
| `verdict` | str (`ALLOW`/`SUGGEST`/`INTERVENE`/`BLOCK`/`AMBIGUOUS`) | bus arg `action` |
| `confidence` | float | bus arg |
| `reasoning` | str | bus arg |
| `matched_hash` | str | bus arg |
| `model_used` | str | bus arg |
| `layer` | int | bus arg |
| `ts` | float (epoch) | bus internal `time.time()` |
| `latency_ms` | float | 0.0 at B' (see "Known limitation" below) |
| `action_taken` | float | alias of `confidence` (RL convention) |
| `action_propensity` | float | 1.0 default |
| `state` | dict | `{}` placeholder until state-extractor wired |

**Precedent.** ADR-18 line 62 already permits "Metadata-only
extensions" to FROZEN bus envelope schemas (`governance_call`,
lifecycle envelopes). Adding a new envelope that mirrors data already
written to the `decisions` table is additive and does not change any
existing envelope's shape. Subscriber wiring uses the same NFR-R6
defensive try/except pattern as the existing `_subscribers` /
`_envelope_subscribers` lists.

**Activation.** Subscribers are opt-in via
`BRIDGE_RL_LOGGER_ENABLED=1`. With the env unset the bus skips the
envelope build entirely (zero-cost — confirmed by the
`if self._decision_subscribers:` guard at `message_bus.py`).

**Known limitation (B').** `latency_ms` is hard-coded `0.0` in the
envelope because `_last_phase_timings_ms` is populated AFTER
`MessageBus.record_decision` returns at `governance.py:449`. Capturing
real per-decision latency requires either (a) the bus accepting a new
optional `latency_ms` kwarg (caller change at `governance.py:416` —
additive but touches FROZEN `governance.py`, needs its own amendment)
or (b) a post-record_decision update path. Reserved for a follow-up
amendment; B' ships with the zero value documented and a pinning test
(`tests/test_rl_bus_subscriber.py::test_subscriber_latency_ms_zero_in_b_prime`).

**Future-extension constraint.** Subsequent RL-driven extensions to
this envelope MUST be additive optional fields only. A FROZEN →
EVOLVING demotion of `governance_decision` requires explicit user
approval per Rule 1 §"State transitions"; this amendment does not
pre-authorize one.

### 2026-05-16 — v2.2 P0 Amendment A: Rule 3 extension — feature-cycle LOC soft target (closes #130)

**Rule 3 extension (v2.2 P0 Amendment A).** Consolidation cycles
retain net LOC ≤ 0 (unchanged). Feature cycles target ≤ 1500 LOC
by default; exceeding the soft target requires operator override
recorded verbatim in the cycle-frame doc. Soft target is
**PROVISIONAL** through v2.3 P0 — re-calibrate at ≥ 4 feature-
cycle data points (recompute via p75 or median + stddev across
{v1.9 ≈ +2800, v2.1 = +3874, v2.3 …, v2.4 …}).

**Net-LOC measurement scope = 3 buckets:**

- **Production** (`src/`) — load-bearing for the cap.
- **Test** (`tests/`) — advisory; reported alongside production.
- **Docs** (`docs/` + `*.md`) — advisory; reported but excluded
  from the cap per ADR-18 §"Open questions" (capping docs creates
  perverse incentive against ADR coverage).

`tools/` and `dashboard/` continue counting toward production for
Rule 3 measurement (unchanged from §Rule 3 main text).

**Cycle-start commit anchor.** Prior cycle's release-tag SHA.
v2.1.0 = `8303f38`; v2.2 measurement window = `8303f38..HEAD` at
ship-gate.

**Ship-gate diff command:**

```
git diff <prior-tag>...HEAD --stat -- src tests tools dashboard
```

**BLOCK threshold.** 1.5× soft target (= 2250 LOC for the 1500
default). Hard cap is NOT 2× (2× would retro-permit v1.9's +2800
which was the precedent driving Rule 3 in the first place).

**Why this shape.** v1.9 +2800, v2.1 +3874 set the precedent
that feature cycles drift unbounded without a soft anchor.
Soft + override + cap escalation (1× soft → 1.5× block) gives
operator room to recognise legitimate slope (e.g. PPP harness
end-to-end was structural; lever wiring is typically much smaller)
while making sub-cycle overage visible at cycle frame rather than
ship-gate. Provisional through v2.3 lets one more feature data
point refine the threshold before locking.

**Acceptance (#130).**

- [x] Amendment text in `docs/adr/ADR-18-mvp-surface-freeze.md`
      §"Amendments" (this entry).
- [x] §C1–C5 fold-ins per #130 issue body (addressed inline
      above — no separate §C subsections needed; threshold,
      override, anchor, and provisional-window decisions all
      captured in this Amendment body).
- [x] §C2 per-phase sub-question explicitly DROPPED (deferred
      post-v2.3; cycle-wide measurement only at v2.2).
- [x] `tools/soak_driver.py` post-soak LOC delta summary updated
      against new threshold (P2 ship-gate scope — additive output
      only). **LANDED v2.3 P1 Seed 4** (`task-amendment-soak-summary-
      dual-anchor.md`); dual-anchor block + stdout lines render
      cycle-tip (binding gate) + predecessor-tag (narrative) at
      every soak summary.

### 2026-05-16 — v2.2 P0 Amendment B: Rule 6 (NEW) — memory pre-flight at cycle frame (closes #133)

**Rule 6. Memory pre-flight at cycle frame.** Every cycle-frame
P0 PR verifies every load-bearing project memory cited in the
phase prompt against ground-truth code/repo state (grep / file
existence / status doc cross-check). Stale memories are updated
in the same P0 PR before cycle proceeds. INTENT.md is in pre-
flight scope (its §"Current cycle posture" / §"Authoritative
status references" rot at the same rate as project memories).

**Required output.** P0 PR body carries a "Memory pre-flight
stamp" block enumerating each verified memory + verdict
(fresh / updated-in-this-PR / superseded-by-X). Empty stamp =
non-compliant.

**Reason.** v2.1 P0 surfaced 5-day-stale `project_sync_comms.md`
that misled lever selection (recommended PPP only after
ground-truth-walking the sync-comms ship state). Cost: ~1
cycle-frame round-trip. Codifying the pre-flight prevents
recurrence and bounds the next round-trip cost to zero.

**Self-application.** This very amendment self-applies — the
v2.2 P0 PR body carries the first compliant pre-flight stamp.

**Acceptance (#133).**

- [x] Amendment text in `docs/adr/ADR-18-mvp-surface-freeze.md`
      §"Amendments" (this entry).
- [x] Cycle-frame prompt template
      (`docs/prompts/v2.2-orchestration/phase-0-cycle-frame.md`)
      already carries the DOD line enforcing pre-flight (minted
      at v2.1 P4 ship-gate).
- [x] First applied: this PR.

### 2026-05-17 — v2.2 P2 Amendment C: Rule 3 anchor — cycle-tip vs predecessor-tag (post-hoc clarification)

**Problem.** Rule 3 main text and v2.2 P0 Amendment A both anchor the
ship-gate LOC measurement at the prior cycle's release-tag SHA (v2.1.0
= `8303f38` for v2.2). v2.2 P2 ship-gate measurement against
`8303f38..HEAD` registered **+1251 LOC** despite the v2.2 cycle itself
(P0 + P1 measured at `fbd0fb2..HEAD`) coming in at **−6 LOC**. The
+1257 difference is post-v2.1.0-tag inter-cycle commits landed on
`main` between the v2.1 release tag and the v2.2 P0 cycle frame mint:

- PR #155 — v10 P4 B' live MessageBus → `rl_episodes.db` subscriber.
- PR #156 — backfill extractor (gov.db → rl-episodes JSONL).
- PR #159 — cassette CI guard for FR-PPP envelope kinds (#132).
- PR #163 — soak-summary probe-emit counter (~5 LOC additive).

None of those were v2.2-cycle work; they landed without cycle
classification (v10 RL companion track + minor v2.1-follow-up
hardening). The predecessor-tag anchor counted them against v2.2's
consolidation budget, producing a false BLOCK signal at the literal
`8303f38..HEAD` reading.

**Clarification.** Cycle-LOC discipline at ship-gate is measured at
the **P0-merge tip** of the cycle being shipped, NOT the
predecessor-cycle release tag. For v2.2 that is `fbd0fb2` (commit of
PR #167 `chore(v2.2): P0 cycle frame`). The predecessor-tag anchor
is retained for **cycle-impact narrative** in the close memory +
CHANGELOG (so operators read the full delta-since-last-tag), but the
**net-LOC BLOCK gates** (consolidation ≤ 0, feature ≤ 1500 soft /
2250 BLOCK per Amendment A) bind to the cycle-tip anchor.

**Why this shape.** Cycle budget is a *cycle-discipline* lever — its
job is to bind work done *within* the cycle's authored scope, not
work that drifted onto main between tag and frame. Pre-cycle drift
is real and worth tracking (post-tag PRs that landed without cycle
classification), but a cycle's discipline gate cannot police it
retroactively. ADR-18 Amendment B Rule 6 memory pre-flight covers
the operator-awareness side at frame time; this amendment makes the
gate-arithmetic side match.

**Cycle-tip anchor commands.**

- Consolidation cycle gate: `git diff <P0-merge-sha>..HEAD --stat --
  src tests tools dashboard` — net ≤ 0.
- Feature cycle gate (per Amendment A): same command, with net ≤
  1500 soft / 2250 BLOCK.
- Narrative figure (CHANGELOG + close memory): `git diff <prior-
  tag>..HEAD --stat -- src tests tools dashboard` — reported as
  cycle-impact-plus-drift, decomposed if material.

**v2.2 application (this PR).**

- Cycle delta vs `fbd0fb2` = **−6 LOC** (P1 gap-4 net deletion;
  consolidation gate PASS).
- Inter-cycle drift `8303f38..fbd0fb2` = **+1257 LOC** (PRs
  #155/#156/#159/#163; all EVOLVING-surface RL track + minor
  hardening, out of v2.2 scope).
- Predecessor-tag narrative `8303f38..HEAD` = **+1251 LOC**.

Cycle-tip anchor cleared; ship v2.2.0.

**Carry-forward.** v2.3 P0 cycle frame inherits this clarification.
Amendment A §"Cycle-start commit anchor" text reads as if predecessor-
tag is the gate anchor; that subsection is **superseded by Amendment
C** for gate purposes (anchor moves to P0-merge tip) and retained for
narrative purposes (anchor moves to prior tag). Future feature-cycle
P0 prompts MUST cite both anchors verbatim.

**Acceptance.**

- [x] Amendment text in this entry.
- [x] Rule 3 main text cross-link added (see §"Rule 3" / Amendment-C
      pointer below).
- [x] First applied: this PR (v2.2 P2 ship-gate).
- [x] `tools/soak_driver.py` post-soak LOC delta summary updated to
      emit both anchors (cycle-tip + predecessor-tag). **LANDED v2.3
      P1 Seed 4** (`task-amendment-soak-summary-dual-anchor.md`);
      shared acceptance with Amendment A L388 above.
