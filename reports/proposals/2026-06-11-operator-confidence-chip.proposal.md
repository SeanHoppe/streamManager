# Operator Co-Pilot Confidence Chip

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (ux) 2026-06-11; idea WILDCARD-2; boldness WILD; refute verdict SHIP-PROPOSAL; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

When a pending HITL row queues waiting for operator approval, the operator must read the reasoning, scan the message context, review prior overrides, and pick from a ranked list. This is cognitively expensive during high-cadence SYNC sessions. Meanwhile, the governance engine has already computed a confidence score and ranked suggestions. The operator workflow is reactive ("a decision arrived, now I must act") rather than co-pilot-driven ("here is my top recommendation; one-tap approve, or dive deeper if you disagree").

## Proposal

For every HITL pending row in SYNC mode, render a proactive recommendation chip above the action buttons that surfaces: (a) the engine's top-ranked next action with a confidence dial (large, animated, spectrum-colored from pale to rich amber per M4 paired label+color rule); (b) a 1-button one-tap approve affordance that auto-resolves if the operator trusts the suggestion. Clicking through the dial reveals a ranking breakdown chart (graph-pattern match %, HITL override history recency-decay %, static-rule fire %, project-context precheck %). Keyboard shortcuts: Ctrl+Enter approves, Esc dismisses and surfaces the override dropdown. The chip is advisory-only, never silencing the override affordance (M6: ranked options always present). The chip does not render in HITL OFF / async mode (M7: operator opt-in).

## Operator value

Reduces cognitive load in high-cadence sessions by letting confidence-aligned decisions auto-approve with zero friction; preserves full operator control (no silent auto-resolve without a click); builds pattern muscle-memory faster via repeated one-tap approval flow; makes SYNC mode feel lightweight, co-pilot-driven rather than bottleneck-bound.

## Surfaces touched / added

- dashboard/ui-next/src/lib/components/HitlRecommendationChip.svelte (new; rendered inside HitlPendingRow above action buttons, paired with existing M6 affordances)
- dashboard/ui-next/src/lib/components/ConfidenceDial.svelte (new; animated confidence spectrum dial, M4 paired label+color, accessible)
- dashboard/ui-next/src/lib/components/ConfidenceBreakdown.svelte (new; reveal-on-click chart showing sourced_from blend breakdown, graph_pattern %, hitl_override %, static_rule %, project_context %)
- dashboard/ui-next/src/lib/components/HitlPendingRow.svelte (extend to render HitlRecommendationChip above AdvisoryChip; add Ctrl+Enter keyboard handler invoking commit('approve', ...); no logic change, only composition)
- dashboard/server.py (no change; /api/decisions/{id}/suggestions already wired at lines 1946-1994)
- src/stream_manager/governance.py (no change; GovDecision.confidence already frozen at lines 49-57)
- src/stream_manager/decision_suggestions.py (no change; Candidate.sourced_from, Candidate.confidence already exposed at lines 144, 152-154)

## Feasibility

FEASIBLE -- built entirely on existing contract surface. /api/decisions/{id}/suggestions (FR-UI-5, dashboard/server.py:1946-1994) is wired + live, returning Candidate.to_json() with confidence, sourced_from (graph_pattern, hitl_override, static_rule, project_context -- lines 149-157 decision_suggestions.py), and rationale. GovDecision.confidence is frozen (governance.py:49-57). HitlPendingRow envelope already carries action + confidence (tested via AdvisoryChip precedent; HitlPendingRow lines 79-105 tolerant field resolution). Svelte UI stack (HitlRecommendationChip, ConfidenceDial, ConfidenceBreakdown) are view-only leaf components consuming no new endpoints.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS -- no new certPortal/monitored-project coupling. Confidence metadata rendered from GovDecision.confidence (FROZEN). Source breakdown shows enum-like keys (graph_pattern, hitl_override, static_rule, project_context) from decision_suggestions.py lines 35-40, not monitored-project vocabulary. Session label rendered FROM DATA (M16 domain-agnostic pattern).
- **Polarity (G2):** PASS -- chip is advisory-only, emits no network calls. Chip provides no affordance to skip the override gate (M6: ranked options untouched). HitlDock.isSelf() + dropSelf() filters (lines 112-119) exclude SM-self rows before HitlPendingRow instantiation. No loopback to SM-self session.
- **ADR-18 MUST floor:** PASS -- M4 (paired label+color): ConfidenceDial uses amber spectrum with explicit label ('Confidence: 60%-85%'; color never sole signal). M6 (HITL ON = ranked options): chip sits ABOVE action buttons; OVERRIDE button fully interactive, never silenced. M7 (HITL OFF = opt-in): chip not rendered in HitlReadOnlyRow path (only in HitlPendingRow when hitlOn=true). M8 (Learn-Mode non-verdict): chip distinct from AdvisoryChip; confidence-ranking signal paired with +1 approve button, never bypasses gate. M9 (Countdown): chip inherits row's countdown, expires with row. M10 (Optimistic resolve): one-tap approve calls same commit('approve', ...) path as APPROVE button. M15 (Self-exclude): chip in HitlPendingRow, only instantiated after dropSelf() filter. M16 (Domain-agnostic): confidence numeric (60-85% range); recommendation breakdown shows FROZEN source enum keys, never monitored-project vocab. M18 (Post-hoc): chip view-only + one-tap, only new network call is POST in commit('approve', ...), identical to existing APPROVE button POST (/api/hitl/resolve).
- **Frozen-surface note:** No FROZEN surface modification required. GovDecision.confidence (governance.py:49-57) already exists; chip consumes it read-only. /api/decisions/{id}/suggestions (dashboard/server.py:1946-1994) already implemented; chip consumes response read-only. HitlPendingRow contract (lines 1-43 block comment, M6-M18) is extended, not violated.
- **New-envelope note:** NO new bus envelope kind introduced. Chip consumes existing hitl_pending row envelope (from /api/hitl/pending) + /api/decisions/{id}/suggestions response (both FROZEN contract, already tested). Keyboard handlers (Ctrl+Enter, Esc) are standard Svelte onkeydown; no message_bus envelope required.

## Grounding

- dashboard/ui-next/src/lib/components/HitlPendingRow.svelte:1-43 (M6-M18 contract; lines 79-105 tolerant envelope field resolution)
- dashboard/ui-next/src/lib/components/AdvisoryChip.svelte:1-42 (M8 precedent pattern: non-verdict chip, paired label+color rule M4, dashed chrome, no affordance to bypass gate)
- dashboard/server.py:1946-1994 (FR-UI-5 /api/decisions/{id}/suggestions endpoint, rank_candidates integration)
- src/stream_manager/decision_suggestions.py:139-158 (Candidate dataclass, sourced_from list [graph_pattern, hitl_override, static_rule, project_context], confidence float, to_json() serializer)
- src/stream_manager/decision_suggestions.py:35-40 (SuggestionWeights enum-like source keys, frozen per FR-UI-5 contract)
- src/stream_manager/governance.py:49-57 (GovDecision frozen dataclass with confidence field)
- dashboard/ui-next/src/lib/components/HitlDock.svelte:110-119 (isSelf + dropSelf M15 self-exclude filter, prevents SM-self rows reaching HitlPendingRow)
