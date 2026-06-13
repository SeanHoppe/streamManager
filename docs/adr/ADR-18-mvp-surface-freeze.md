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
| `graduated_short_circuit` (governance `_evaluate_inner_core` graduated-ALLOW branch) | v2.x Amendment F feature PR | DORMANT-0 | Wired at feature-build (first soak-ledger lever post-P3). Metric = graduated-hit fire rate; the Tier-1.5 soak measures it. DORMANT-N strikes per Rule 2 if 0% for 2/3 consecutive ship-gate soaks. |

<!-- WIRED_LEVER_LEDGER_COUNT: 1 -->

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

### 2026-05-18 — v2.4 P0 Amendment D: v10 P5 entry-gate split (v10.1-mode vs v10.3-mode) (closes #177)

**Problem.** The v10 P5 phase prompt
(`docs/prompts/v10-orchestration/phase-5-shadow-stop-conditions.md`
L8) ABORTs if no manifest with `is_ready_for_shadow() == True`
exists. `is_ready_for_shadow()` is defined in `rl/bandit.py` L99-101
as `(self._total >= PROMOTION_N_FLOOR
AND self.best_arm_posterior_ci() <= PROMOTION_CI_CAP)`, where
`PROMOTION_N_FLOOR = 200` and `PROMOTION_CI_CAP = 0.10`
(`rl/bandit.py` L23-24). Under v10.1's deterministic production policy
(threshold fixed at baseline_thr=0.70), the trainer's offline-replay
loop in `rl/cli/train.py` L120-123 only conjugate-updates the
baseline arm — off-baseline arms receive zero on-support data and
their posterior CI stays at the warm-start floor (~0.43 for
`Beta(10,10)`). The 0.10 CI cap is therefore unreachable on any
non-baseline arm regardless of episode count. Even if the baseline
arm itself clears both conditions, the train CLI's exit-10 (PROMOTE)
path requires `best_arm != baseline_arm` (`train.py:221`), so the P5
entry signal remains unreachable.

This creates a chicken-and-egg deadlock: P5 entry requires off-arm
CI shrinkage → off-arm CI requires on-support updates → on-support
updates require stochastic propensities → stochastic propensities
arrive with v10.3 writeback → v10.3 writeback requires P5 ALL PASS.
v10 RL track is pre-DORMANT deadlocked at the P5 entry, with no
designed escape path. Live train evidence (2026-05-18,
`rl_proposals/v10p4-live-20260518.json`): n_actual=79/200,
best_arm_ci_width_95=0.119/0.10, ready=False.

**Amendment.** Split the v10 P5 entry gate into two modes:

| Mode | Active when | Gate condition | P5 outcome |
|---|---|---|---|
| **v10.1-mode** | v10.x track stages 0-2 (deterministic production policy) | baseline arm `_total >= 200` effective updates AND `posterior_ci_width(baseline_arm) <= 0.10` | P5 shadow harness fires as **infrastructure validation**: candidate = baseline (sanity), recorder writes a baseline-vs-baseline shadow run, harness exercises end-to-end without claiming promotion |
| **v10.3-mode** | v10.3 stochastic propensity writeback active | original gate: non-baseline `best_arm` clears `_total >= 200 AND best_arm_posterior_ci() <= 0.10` | P5 shadow run measures real candidate-vs-production divergence; ship-criteria checker may exit 0 (ALL PASS) and open v10.3 writeback gate |

`rl/bandit.py` adds a sibling method `is_ready_for_shadow_v10_1()`
returning the v10.1-mode condition. `is_ready_for_shadow()` retains
its current semantics (v10.3-mode). P5 phase prompt re-minted at
v2.4 P0 with a header section disambiguating which mode is being
exercised in the current cycle.

The `proposals.promotion_gate` JSON envelope grows two additive
keys: `ready_v10_1` (v10.1-mode bool) and `mode` (string literal
`"v10.1"` or `"v10.3"` indicating which mode is active per the
caller's `BRIDGE_RL_MODE` env or CLI flag). The existing `ready`
key (v10.3-mode) is preserved verbatim — additive extension per
ADR-18 Rule 1 §"Metadata-only extensions to FROZEN bus envelope
schemas".

The v10.1-mode shadow harness MUST record its mode in
`shadow_episodes.soak_run_id` (string suffix `--mode=v10.1`) so
post-hoc analysis can distinguish infrastructure-validation runs
from real-data shadow runs. v10.3 ship-criteria checker
(`rl.cli.check_criteria`) ignores rows with `--mode=v10.1` suffix
when computing the 6 pre-registered ship criteria — those rows are
infrastructure-only and cannot count toward writeback promotion.

**Scope.** v10 EXPERIMENTAL track per ADR-18 row table L71. No
FROZEN surface touched. `bandit.py`, `train.py`, `manifest.py`,
phase-5 prompt — all are v10-track files in the EXPERIMENTAL
classification.

**Reason.** The v10 design doc §10 specifies 6 pre-registered ship
criteria with the implicit assumption that stochastic propensities
are available when criteria are evaluated. v10.1's deterministic
policy violates that assumption silently — the gate compiles, runs,
and returns False forever. Amendment D acknowledges the assumption
gap explicitly and provides a documented v10.1-mode escape that:

1. Lets the P5 shadow harness ship and be exercised end-to-end
   without waiting on v10.3.
2. Reserves the original (v10.3-mode) ship criteria verbatim,
   preserving the pre-registration discipline of §10.
3. Surfaces the mode boundary in the data (via `soak_run_id`
   suffix) so v10.3 writeback promotion cannot be accidentally
   triggered by infrastructure-validation runs.

Without Amendment D, the v10 track either (a) stalls indefinitely
at P5 entry, (b) tempts ad-hoc threshold relaxation (p-hacking
against pre-registration), or (c) blocks until v10.3 stochastic
writeback ships first — but v10.3 requires P5 ALL PASS, which
loops to (a). Amendment D is the minimum-surface break of the
loop that preserves all other invariants.

**Self-application.** Amendment D body (docs-only) lands in the
cycle's P0 PR. Implementation-side acceptance items below
(bandit / train / phase-5 prompt / shadow harness) are
cycle-conditional: they fire only when the cycle electing Path-D
P5 implementation runs (`Seed v2.4-C` or successor). Consolidation
cycles defer those items to the next feature cycle electing P5;
the docs side of Amendment D self-applies regardless of cycle
classification. Cycle-bound disposition for the v2.4 cycle is
recorded in `docs/v2.4-task-plan.md`.

**Acceptance (#177).**

- [x] Amendment text in `docs/adr/ADR-18-mvp-surface-freeze.md`
      §"Amendments" (this entry, copied verbatim from staging
      draft and re-located).
- [x] `docs/adr/ADR-18-amendment-d-draft.md` (staging file)
      deleted in this PR — staging artefact must not outlive the
      relocation, or it rots into a stale duplicate.
- [x] ~~Verify `shadow_episodes` schema exposes the `soak_run_id`
      column (currently designed in `phase-5-shadow-stop-
      conditions.md` L71 as `soak_run_id TEXT NOT NULL`) BEFORE
      Path-D synthetic-fixture P5 implementation fires. If the
      schema lands without that column, Amendment D's
      `--mode=v10.1` suffix mechanism has no carrier.~~ **DEFERRED
      v2.5** (verified at Path-D P5 impl).
- [x] ~~`rl/bandit.py` adds `is_ready_for_shadow_v10_1()` method;
      `is_ready_for_shadow()` semantics unchanged.~~ **DEFERRED v2.5**
      (consolidation cycle choice).
- [x] ~~`rl/cli/train.py` `promotion_gate` envelope adds
      `ready_v10_1` + `mode` keys; existing `ready` preserved.~~
      **DEFERRED v2.5**.
- [x] ~~Phase-5 prompt re-minted with mode-disambiguation header
      OR new `phase-1-shadow-synthetic.md` prompt minted for
      v2.5 (operator decides at v2.5 P0).~~ **DEFERRED v2.5**.
- [x] ~~Path-D shadow harness records `soak_run_id` with
      `--mode=v10.1` suffix for v10.1-mode runs.~~ **DEFERRED v2.5**.
- [x] ~~`rl.cli.check_criteria` ignores `--mode=v10.1` rows when
      computing ship criteria.~~ **DEFERRED v2.5**.
- [x] Issue #177 auto-closes via this PR body `Closes #177`.
- [x] ~~`project_v10_p5_gate_deadlock.md` memory updated to record
      Amendment D as the resolution (status moves from OPEN to
      AMENDMENT-LANDED; implementation DEFERRED v2.5).~~ **DEFERRED
      v2.5** (memory update bundled with Path-D P5 implementation
      PR; current memory body already records Amendment D as the
      filed resolution path per PR #178 mint 2026-05-18).
- [x] `docs/v10-rl-design.md` §10 footnote appended cross-
      referencing Amendment D (one-line additive doc edit).

### 2026-05-19 — v2.4 P0 Amendment E: Rule 5 cycle-handoff exemption for externally-triggered seeds

**Problem.** Rule 5 (ADR-18 §"Decision" L189-201) caps 🟢 backlog
at "2 cycles without graduation" and forces promote-to-phase,
promote-to-ADR, or delete at the next cycle frame. The cap counts
every carry-forward seed equally, but some carry-forwards are
bound to **external triggers** (a documented promotion criterion
OR a documented demand signal), not to operator inattention. v2.4
enters with 14 open seeds: 8 newly minted at v2.4 P0, 6 carried
from v2.3 (Seeds v2.4-I–N: 5 INTENT-graduated promotion-criterion-
bound + 1 demand-bound). The 6 carry-forwards have explicit
external waiting conditions; their continued presence is correctly-
gated future work, not staleness.

Without an exemption, the cap forces operators to either (a) accept
escalating cap-bumps every cycle (v2.2=6, v2.3=11, v2.4=14, ad
infinitum), or (b) prematurely promote/delete seeds whose external
trigger has not yet fired, losing the original promotion-criterion
record and creating churn without surfacing real prioritization
decisions.

**Amendment.** A backlog seed is **exempt from the Rule 5 2-cycle
cap** at cycle-handoff if and only if BOTH of the following hold:

1. The seed has a written **external trigger** (promotion criterion
   OR demand signal) cited verbatim in the predecessor cycle's
   next-steps file (`docs/vN.M-next-steps.md`).
2. The trigger has not yet fired (criterion still false, or demand
   still absent).

Triggers MUST be **specific, falsifiable conditions** — not "review
next cycle" or "consider in vN.M+1". Examples of valid triggers:

- Promotion criterion: "promote on next regression of behavior X"
  (INTENT-graduated regression-coverage seeds).
- Demand signal: "promote when monitored project surfaces concrete
  use case" (Remote-CLI seed).

Invalid triggers (still cap-counted):

- "Worth re-evaluating later."
- "Carry forward for now."
- "TBD."

Exempt seeds remain in the backlog without striking the 2-cycle cap.
Once a trigger fires, the seed re-enters the cap regime at the next
cycle's P0 (operator must promote-to-phase, promote-to-ADR, or
delete in the cycle following trigger fire).

**Reason.** Rule 5's intent (per §"Decision" L208-212) was to
prevent indefinite operator drift on stale items. Promotion-
criterion-bound and demand-bound seeds are not drift — they are
correctly-gated future work. The exemption is **narrow**: it
requires a written, falsifiable trigger in the predecessor
cycle's next-steps file. Operators cannot retroactively claim
exemption by inserting a vague clause; the trigger must already
exist in the predecessor doc that the current cycle's P0 frame
is reconciling against.

**Scope.** Docs-discipline-only. No `src/`, `tests/`, `tools/`,
or `dashboard/` surface change. Rule 5 main text retains current
wording; Amendment E adds the exemption clause as an addendum
read in conjunction with the main text.

**Self-application.** v2.4 P0 backlog at fire = 14 open seeds.
Apply Amendment E:

- 8 NEW v2.4 seeds (Seeds v2.4-A through v2.4-H) — counted (new
  this cycle; no 2-cycle drift yet).
- 5 INTENT-graduated carry-forwards (Seeds v2.4-I, v2.4-J, v2.4-K,
  v2.4-L, v2.4-M) — **EXEMPT** (promotion-criterion-bound; each
  cites verbatim "promote on next regression of behavior X" in
  `docs/v2.4-next-steps.md`).
- 1 demand-bound carry-forward (Seed v2.4-N, Remote-CLI monitoring
  extension) — **EXEMPT** (demand signal "concrete use case
  surfaces" cited verbatim).

Effective cap reading at v2.4 P0 = **8** (well under the prior
11-cap and under any reasonable feature-cycle ceiling).

**Acceptance.**

- [x] Amendment text in `docs/adr/ADR-18-mvp-surface-freeze.md`
      §"Amendments" (this entry).
- [x] `docs/v2.4-task-plan.md` §"Operator decisions" records
      the Amendment E disposition + 8 cap-counted / 6 exempt
      breakdown.
- [ ] v2.4 P2 ship-gate prompt (`docs/prompts/v2.4-orchestration/
      phase-2-ship-gate-finalize.md`) MUST include a regression-
      check step that re-reads `docs/v2.4-next-steps.md` for the
      verbatim external-trigger citation of each Amendment E
      exempt seed (v2.4-I..N). Acceptance of this Amendment E
      item is satisfied when (a) the P2 prompt mints with that
      step, OR (b) the v2.4 P2 PR body carries the regression-
      check output directly. Prompt-mint scheduled at v2.4 P1
      close per `docs/v2.4-task-plan.md` §"PHASE P2".
- [ ] Future cycle next-steps files use the verbatim "promotion
      criterion" or "demand signal" language for any seed
      claiming Amendment E exemption.

### 2026-06-13 -- v2.x Amendment F: allow-pattern auto-graduation seam (operator-confirmed static ALLOW)

**Problem.** INTENT.md ("what governance should learn": routine -> ALLOW
within the POC window) specifies that a command-shape observed ALLOWed at
high confidence many times with zero operator override is, empirically, a
rule. Today that knowledge stays implicit: every `git status`, `ruff
check`, `pytest -q` re-evaluates from scratch (latency + CLI quota)
instead of graduating to a cheap static ALLOW. The corpus knows the
answer; the policy never promotes it. The blocker is purely surface:
promoting a proven-routine shape to a static ALLOW requires (a) a new
short-circuit in the FROZEN verdict ladder and (b) a new FROZEN bus
envelope kind. ADR-18 Rule 1 forbids both without this amendment.

**Amendment.** Grant a NARROW, single-purpose exception to Rule 1 for the
auto-graduation seam, bounded by the invariants below. The exception
permits exactly:

| FROZEN surface | Permission granted | Bound |
|---|---|---|
| `ENVELOPE_KINDS` frozenset (`envelope_kinds.py`) | Add one kind: `"pattern_graduated"` | Emitted ONCE per graduation event (operator confirm), never on the hot path. Same-PR `cassette_record.py` + `soak_driver.py` coverage MANDATORY (`test_envelope_coverage.py` enforces). |
| `governance._evaluate_inner_core` verdict ladder | Add ONE new short-circuit branch: graduated-rule lookup -> `GovDecision(action="ALLOW", source="graduated")` | Branch is positioned strictly AFTER `fast_precheck` (the safety floor) and is read-only against a new `graduated_rules` table. No other ladder edit. |

No other FROZEN surface moves. `model_router` bands, `RoutingDecision`
fields, `cli_pool`, `LifecycleBridge`, `wirecli`, and the existing
governance_decision / lifecycle envelope schemas are untouched.

**Invariants (all MANDATORY -- the amendment is void if any is dropped).**

1. **Safety floor wins, structurally.** `fast_precheck` runs FIRST in
   `_evaluate_inner_core` (`governance.py:955`) and returns before any
   graduated-rule branch. A graduated rule therefore CANNOT override a
   BLOCK/INTERVENE even if one were somehow written. This is the second
   of two guarantees; the first (below) is that a safety-floor shape can
   never be graduated in the first place.

2. **Safety-floor shapes are PERMANENTLY ineligible.** The candidate scan
   excludes any shape that ever matched a safety-floor rule
   (destructive-shell / force-push / credential-exfil / eval-exec
   injection -- reuse `_is_safety_priority_content` +
   `EVAL_EXEC_INJECTION_RE` so the eligibility predicate cannot drift
   from the precheck regexes). `n_block_ever == 0` is a hard gate. The
   floor is not learnable.

3. **Operator-confirmed, no auto-apply (M8 absolute).** Graduation NEVER
   happens automatically. The scan only proposes CANDIDATES; a static
   ALLOW rule is written ONLY on an explicit one-tap operator confirm.
   Grep invariant: no code path writes a `graduated_rules` row without an
   operator-initiated request.

4. **Polarity dual-key on the scan.** The candidate corpus read excludes
   SM-self: SQL `project_slug NOT IN (STREAM_MANAGER_PROJECT_SLUGS)` +
   `session_id != BRIDGE_SM_SELF_SESSION_ID` backstop. The endpoint
   surfaces `excluded_self`.

5. **Reversible.** Every graduation is demote-able; reuse the existing
   `/api/patterns/{hash}/demote` affordance. A demoted rule stops
   short-circuiting immediately.

6. **Graduation eligibility predicate (the candidate gate), per shape:**
   `n_allow >= 30` AND `mean_confidence >= 0.95` AND `n_override == 0`
   AND `n_block_ever == 0` AND never-matched-safety-floor. (Thresholds
   are config constants, not magic literals; defaults from the proposal.)

7. **Graduated hits carry no judgment signal.** `source="graduated"` is
   deliberately NOT added to `ELIGIBLE_SOURCES` (`governance.py:69`); a
   static ALLOW must not feed the rolling-accuracy window or it ramps the
   mode ladder (the bug the eligibility gate exists to prevent). Likewise
   the graduated branch's `matched_hash` is for provenance + demote-keying
   only: `feedback()` (`:1167`) would otherwise route a graduated hit into
   `graph.feedback()` and let a static rule mutate the probabilistic
   graph's success_rate. The impl MUST either guard that call for
   `source=="graduated"` OR accept warm-keeping as a documented, tested
   choice -- not leave it implicit.

**Scope.** Touches two FROZEN surfaces under the bounded permission above;
one new additive table (`graduated_rules`); one read-only scan endpoint;
one new Svelte component (`GraduationCandidates.svelte`) + poller; reuses
the existing demote affordance. The feature ships default-OFF behind a
BETA flag like the other 45; the verdict short-circuit is additionally
gated so that with the flag OFF and zero graduated rows the ladder is
byte-for-byte the current ladder (the branch is a no-op lookup returning
None on an empty table).

**Reason.** This is the data-flywheel INTENT made concrete: routine toil
stops costing a model call + a glance; the operator's repeated "yes this
is fine" graduates into a rule once, with explicit sign-off. The
amendment is the minimum-surface break: one new envelope (audit-only,
cold path) + one new verdict branch (read-only, safety-floor-subordinate)
+ additive storage. Every safety invariant of the current ladder is
preserved by construction (precheck-first ordering) AND by the candidate
filter (safety shapes never graduate).

**Soak tier.** Promotion of this seam past BETA requires a **Tier-1.5
soak** per the ADR-17 trigger matrix (verdict-path change touching the
decision ladder), driven from a live non-SM Claude session
(`feedback_soak_needs_live_non_sm_session`), `--cli-pool-size 2`
(`feedback_soak_cli_pool_flag`). The soak MUST exercise: (a) a graduated
ALLOW hit (`source="graduated"`, 0 CLI dispatch), (b) a safety-floor
shape that is offered NO candidate, (c) the `pattern_graduated` emit on
confirm, (d) a demote reversing a graduation.

**Lever-ledger note.** The graduated-rule short-circuit is a WIRED LEVER
under Rule 2. It enters the WIRED_LEVER_LEDGER at wire-time and is subject
to the DORMANT-N falsify-before-extend gate: if ship-gate soaks measure a
0% graduated-hit fire rate for two/three consecutive cycles, it strikes
DORMANT-2 / DORMANT-3 like any other lever. (Expected fire rate is
non-zero by construction once any rule is graduated against the routine
corpus mix, but the ledger discipline still applies.)

**Self-application / Acceptance (gates BEFORE any feature code merges).**

> **Feature-PR completion stamp (2026-06-13).** Amendment relocated + feature
> built in the same working tree. Items 1-8 satisfied below; item 9
> (Tier-1.5 soak) remains OPEN — firewall-blocked, see note.

- [x] Amendment F text relocated VERBATIM into
      `ADR-18-mvp-surface-freeze.md` §"Amendments" after the Amendment E
      block; staging file `ADR-18-amendment-f-draft.md` deleted.
- [x] WIRED_LEVER_LEDGER table + `<!-- WIRED_LEVER_LEDGER_COUNT -->`
      counter incremented 0 -> 1 in this feature PR alongside the
      cassette/soak coverage (`tools/soak_driver.WIRED_LEVER_LEDGER`
      + the ledger comment + table row above;
      `tests/test_dormant_ledger_consistency.py` green).
- [x] `pattern_graduated` added to `ENVELOPE_KINDS`; `cassette_record.py`
      records it (`_record_pattern_graduated_envelope`); `soak_driver.py`
      exercises the emit (`_emit_pattern_graduated`);
      `tests/test_envelope_coverage.py` + `test_cassette_roundtrip.py` green.
- [x] Safety-floor ineligibility test: a seeded destructive-shell shape at
      100% ALLOW history is NOT offered as a candidate
      (`test_graduation_endpoints.test_scan_excludes_safety_floor_shape`,
      `test_confirm_refuses_safety_floor`) AND if force-written is still
      precheck-owned (`test_graduated_rules.test_safety_floor_wins_over_graduated`).
- [x] Polarity test: candidate scan excludes SM-self rows (project_slug +
      session_id) and surfaces `excluded_self`
      (`test_graduation_endpoints.test_scan_polarity_excludes_sm_self`,
      `test_confirm_refuses_sm_self_shape`).
- [x] Operator-confirm test: no `graduated_rules` row without an explicit
      confirm (`test_confirm_writes_rule_only_on_request` — scan writes
      nothing; only POST /confirm writes, re-verifying server-side).
- [x] Demote test: a graduated rule stops short-circuiting after demote
      (`test_graduation_endpoints.test_demote_reverses_graduation`,
      `test_graduated_rules.test_store_demote_stops_lookup`).
- [x] Mode-ladder test: graduated ALLOW hits do NOT move the rolling
      window / mode ladder (`source="graduated"` excluded from
      `ELIGIBLE_SOURCES`) AND a graduated hit does not mutate the graph's
      success_rate — guarded in `feedback()` (invariant 7, the documented
      tested choice): `test_graduated_rules.test_graduated_feedback_does_not_
      mutate_graph` + `..._does_not_move_mode_ladder`.
- [ ] Tier-1.5 soak run recorded (live non-SM session) before promotion
      past BETA. **OPEN — blocked:** the only live non-SM sessions are
      certPortal-cwd, whose `~/.claude/projects/` transcript path is denied
      by the enforced `.claude/settings.local.json` firewall, and an idle
      session yields no tail data. Ships default-OFF behind the BETA flag +
      the `BRIDGE_GRADUATED_RULES` engine gate until the soak runs.

#### Implementation design (informative -- the impl PR realizes this; not law)

##### New envelope: `pattern_graduated`

Audit-only, emitted ONCE at operator-confirm time (never per hit). Shape
mirrors the `audit.probe` family (cold-path audit envelope):

```
kind:     "pattern_graduated"
metadata:
  shape_hash:        <decision_graph sha256[:16] of canonical_text>
  canonical_text:    <the graduated shape, generic protocol vocab only>
  n_allow:           <int>      # corpus evidence at graduation
  mean_confidence:   <float>
  n_override:        0
  n_block_ever:      0
  excluded_self:     <int>      # polarity rows dropped from the scan
  confirmed_by:      "operator" # M8 -- always operator, never auto
  graduated_ts:      <iso8601>
```

Decision-time HITS do NOT emit this envelope; they carry
`GovDecision.source="graduated"` (free-string field, additive) so the
dashboard decisions feed can render provenance without a new envelope on
the hot path.

##### New table: `graduated_rules` (additive DDL)

```
CREATE TABLE IF NOT EXISTS graduated_rules (
    shape_hash      TEXT PRIMARY KEY,   -- decision_graph hash; one canonicalization, no drift
    canonical_text  TEXT NOT NULL,
    confirmed_ts    REAL NOT NULL,
    n_allow_at_grad INTEGER NOT NULL,
    active          INTEGER NOT NULL DEFAULT 1  -- demote flips to 0
);
```

`shape_hash` reuses the existing `DecisionGraph` projection/hash so there
is exactly one canonicalization shared between the corpus, the graph, and
the graduated store -- a second hashing scheme would be a drift bug.

##### Verdict-ladder branch (the one new caller path)

Inserted in `_evaluate_inner_core` AFTER the `fast_precheck` return block
(`governance.py:984`) and BEFORE the probabilistic `graph.match`
(`governance.py:986`) -- operator-confirmed rules outrank the
probabilistic graph but are strictly subordinate to the safety floor:

```
# Amendment F: operator-confirmed graduated ALLOW. Subordinate to
# fast_precheck (already returned above); outranks graph.match.
grad = self._graduated_lookup(msg.content)   # see contract below
if grad is not None:
    return GovDecision(
        action="ALLOW",
        confidence=1.0,
        reasoning=f"graduated rule (n_allow={grad.n_allow_at_grad}, operator-confirmed)",
        mode=self.mode,
        matched_hash=grad.shape_hash,   # provenance/demote-key only; see invariant 7
        source="graduated",             # deliberately NOT in ELIGIBLE_SOURCES
    )
```

`_graduated_lookup` contract (explicit, so the no-op claim is testable):
checks the BETA flag FIRST and returns None WITHOUT querying when OFF;
when ON, looks up `graduated_rules` by the decision_graph shape-hash and
returns the row only if `active == 1`. With the flag OFF or an empty/all-
demoted table it returns None and the ladder is byte-for-byte the current
ladder -- a zero-cost early return, no SQL on the OFF path.

##### Design alternatives considered

- **Reuse `graph_patterns` (pin a synthetic Pattern at success_rate=1.0)
  instead of a new table + branch.** Strictly smaller FROZEN footprint
  (only the new envelope; the existing `graph.match` short-circuit at
  `:989` catches it). REJECTED as the primary design because it conflates
  operator-confirmed provenance with probabilistic online-learned
  success_rate, and `observe()`/decay would mutate a graduated rule unless
  a `pinned` flag is added anyway. The new-table design keeps graduation
  auditable and immutable-by-default. NOTE: this alternative is a strict
  SUBSET of the permission Amendment F grants, so the operator may elect
  it at impl time without re-amending.

##### Same-PR cassette + soak coverage

- `cassette_record.py`: add a `pattern_graduated` recording path
  (audit-envelope shape, analogous to the existing audit.probe coverage);
  `_KIND_TO_LAYER` is decision-layer only and does NOT gain a row (this
  envelope is not a decision layer).
- `soak_driver.py`: add a `_write_pattern_graduated(...)` helper modeled
  on `_write_ppp_probe` (`:1559`, which writes `audit.probe` directly) to
  emit one synthetic `pattern_graduated` envelope so the soak corpus
  covers the kind without requiring a live operator-confirm in the soak;
  keep `--cli-pool-size 2`.
- `tests/test_envelope_coverage.py`: passes once both above land.

---
