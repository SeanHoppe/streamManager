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
| `bus` envelope schemas (`governance_fallback_routed`, `governance_envelope_missing_confidence`, `governance_call`, lifecycle envelopes) | FROZEN | Metadata-only extensions. |
| `cli_governance.py` retry path + `BRIDGE_L4_FALLBACK_*` constants | FROZEN | v1.7/v1.8/v1.9 protected. |
| `governance._evaluate_inner_core` content-detection helpers | FROZEN | v1.8 P1. Pattern list extends only; flag semantics fixed. |
| `model_router.py` band priority + `RoutingDecision` field set | FROZEN | NFR-M1-M5 + v1.7 P2. Extend bands within, never reorder. |
| `LifecycleBridge` + `/api/lifecycle/jobs` + dashboard lifecycle pane | FROZEN | v1.2 Task C. |
| `wirecli` transport + `_VALID_TRANSPORTS = frozenset({"sse"})` | FROZEN | v1.1 Task N + v1.2 Task D. |
| `session_watcher.py` + bg task token registry | EVOLVING | v1.9 P2. Re-registration / pid-validation surface still maturing. |
| `learn_mode.py` (advisory bias, JSONL ingest, categorizer worker) | EVOLVING | v1.3 / v1.4 / v1.9 P3. Categorizer + decay ladder still iterating. |
| `sync_comms` design (gate-and-wait, Session Mirror frame, HMAC-signed bidi `desktop_command`) | EVOLVING | Design FROZEN per memory; impl ~6 sessions ahead. |
| `hitl` synthesis path + `hitl_overrides` WAL table | EVOLVING | Design captured in memory; surface still moving. |
| RL writeback (v10.x companion track) | EXPERIMENTAL | Sibling to v2.x. Cannot block ship-gate. |
| `certPortal` MVP ring | EXPERIMENTAL (separate repo) | FR-OG alignment ref via `MVP-100-PLAN.md` + `maturity-dashboard.html`. |

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

Current lever ledger at v2.0 P0:

| Lever | Wired in | Dormant cycles | Status entering v2.0 |
|---|---|---|---|
| Haiku fastpath router (read of `is_ambiguous_block` / `is_hitl_synthesis` at pre-CLI dispatch site) | v1.7 P2 | v1.7, v1.8, v1.9 | DORMANT-3 — BLOCK at v2.0 ship-gate unless revived |
| Confidence-floor + verdict-based fallback (`cli_governance.py` retry trigger) | v1.7 / v1.8 / v1.9 P1 | v1.8, v1.9 | DORMANT-2 — WARN; v2.0 P1b A/B is the revival lever |

<!-- WIRED_LEVER_LEDGER_COUNT: 2 -->

The HTML comment above is **load-bearing**: v2.0 P4 codifies a
DORMANT-N gate in `tools/soak_driver.py` that hard-codes a
`WIRED_LEVER_LEDGER` dict mirroring this ledger. A test asserts
`len(WIRED_LEVER_LEDGER) == int(re.search(r"WIRED_LEVER_LEDGER_COUNT:\s*(\d+)", ADR-18-text).group(1))`.
Any phase that adds, removes, or re-classifies a wired lever MUST
update both this comment and the dict in the same PR. P3 rip phases
update both; future feature phases that wire a new lever bump both.

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
