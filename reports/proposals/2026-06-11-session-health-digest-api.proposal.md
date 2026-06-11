# Session health digest endpoints for operator multi-session triage

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (ux) 2026-06-11; idea BACKEND-2; boldness WILD; refute verdict CONSTRAIN; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

The operator cannot answer "which of my concurrent sessions needs attention right now?" without piecing together multiple API panes (/api/sessions, /api/decisions, /api/lifecycle/jobs, /api/hitl/pending). UC-01: Matt's session had no visible signal that it was stalled until manual triage (7 manual steps). Multi-session operators on a laptop monitor need a glance-friendly health summary to switch focus without context pane shuffling.

## Proposal

Expose two new backend endpoints reading from the existing SQLite bus (governance.py, message_bus.py, dashboard/server.py):

1. **GET /api/sessions/{session_id}/digest** -- returns condensed object: {session_id, project_slug, state (active|stalled|completed), last_message_ts, message_count, decision_count, pending_hitl_count, lifecycle_job_count, latest_action, health_signal ("healthy"|"slow"|"stalled"|"blocked"|"attention-required")}.

2. **GET /api/sessions/digest** (bulk) -- returns array of digest objects sorted by health_signal urgency (blocked > attention-required > slow > stalled > healthy). Latency budget: <200ms per session (indexed on session_id, timestamp ranges).

health_signal is computed server-side from indexed queries (no external calls):
- time since last_message > 5 min -> stalled
- pending_hitl_count > 0 -> attention-required
- governance_negative_regression event in decision stream (last 2 min) -> blocked
- sustained GUIDE/INTERVENE rate >50% of decisions in rolling 10-minute window -> slow
- else -> healthy

3. **POST /api/sessions/{id}/health-check** (async, optional) -- runs a Sonnet in background (<30s) to classify if the session is 'worth waiting for' (job in progress, recent commands, clear next step) vs 'dead in the water' (terminal state, no recent activity). Returns {is_live, classification_reason, suggested_action} when complete. Explicitly out-of-band, user-triggered, NOT part of the governance decision pipeline; does not block operator (async call with status polling). Sonnet call site is dashboard/server.py, NOT governance.py (stays out of FROZEN surfaces).

All metrics read from existing bus tables in a single indexed query per session. Dashboard Frame A can wire the active session's digest as a color-coded header showing urgency. Operator can switch sessions and see digest flip without pane re-layout. Health-check is a per-operator optional "is it worth waiting?" curiosity button.

## Operator value

Operator can see at a glance which session is sick WITHOUT context-switching between panes (monitor-first principle). Health summary acts as a health monitor for the multi-session case. One-off deep-dive classification ('is Matt's session worth waiting for?') answers UC-01 triage question in <30s instead of 7 manual steps. Reduces context switching when governing multiple concurrent projects. Directly enables UC-01 operator action: "triage a stalled session in <30s instead of 7 manual steps."

## Surfaces touched / added

- dashboard/server.py (GET /api/sessions/{id}/digest, GET /api/sessions/digest bulk, POST /api/sessions/{id}/health-check async endpoint)
- src/stream_manager/message_bus.py (new health_digest query method, rolling-window decision rate SQL -- additive only, no FROZEN table modifications)
- dashboard/ui-next/ (optional: session digest header rendering, urgency-color badges, health-check modal with classification reason -- deferred to ui-next build phase)

## Feasibility

FEASIBLE. The indexes exist (idx_messages_session_seq, idx_decisions_message, idx_hitl_pending_unresolved). Rolling-window GUIDE/INTERVENE rate (10-minute window) requires a compound query but is O(N) over the rolling set (narrow timestamp range). Stalled detection (5-min no message) is a single comparison. Governance_negative_regression event detection requires a regex/JSON search on decision.reasoning or an optional new enum field on decisions table (additive, no breaking change). The async health-check offloads to Sonnet (fast, anthropic/SDK call, <30s SLA is reasonable for a user-triggered background task). Batch digest endpoint uses the same session-list query already in /api/sessions, then fans out the health computation per session.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS. Proposal references only core SM tables (messages, decisions, hitl_pending, sessions) and does NOT introduce new SM<>certPortal coupling. Zero certPortal references. All queries read from existing SM-owned tables.
- **Polarity (G2):** PASS. Proposal includes explicit self-filtering: SM monitors NON-SM sessions only (project_slug NOT IN {streamManager} AND session_id != self). The bulk digest endpoint is sorted by health_signal urgency (blocked > attention-required > slow > stalled > healthy) with the intent that Operator can see which session is sick WITHOUT context-switching. The on-demand health-check endpoint is optional classification (for operator curiosity), not a governance gate. No risk of SM monitoring its own session or sweeping SM-self.
- **ADR-18 MUST floor:** PASS. Proposal targets ui-next (EXPERIMENTAL, ADR-20 spike). No direct UI surface is mandated in the backend proposal itself (dashboard Frame A is an example, not a mandate; actual UI rendering deferred to ui-next build). The /api/sessions/{id}/digest endpoint is backend-only (GET, read-only). The /api/sessions/digest bulk endpoint is read-only, non-interrupting. The /api/sessions/{id}/health-check endpoint is async background (user-triggered, <30s, returns optional suggestion). Neither endpoint violates ADR-18 UI MUST floor (M1-M9): M1 (monitor-first): digest is read-only, non-interrupting. M2 (escalation-only foreground): health-check is async, user-triggered, read-only suggestion. M5 (paired label+color badges): proposal defers color-coded session header to ui-next build (backend is domain-agnostic). M8 (domain-agnostic, no hard-coded vocab): the health_signal enum (healthy|slow|stalled|blocked|attention-required) is generic operational language, not monitored-project vocab. M9 (polarity-flip): explicitly designed in via self-exclusion.
- **Frozen-surface note:** Proposal does NOT touch FROZEN surfaces: governance.py, message_bus.py, cli_governance.py, model_router.py, cli_pool.py are read-only. The health_digest endpoint is in dashboard/server.py (additive HTTP endpoint, not a FROZEN module modification). If a follow-on phase wants to inline health_signal computation at decision-publish time (optimization: so digest query is O(1) lookup, not O(N) aggregation), that would require inlining logic into governance.py (FROZEN) -- such a phase would need to file an ADR amendment first, but the current proposal avoids this by keeping the computation post-hoc in dashboard/server.py.
- **New-envelope note:** CONSTRAINT: Proposal does NOT introduce a new bus envelope (it reads from existing tables only). However, if a follow-on phase adds a new envelope kind (e.g., 'session_health_probe' with candidate classification) to the bus, the ADR-18 New-Bus-Envelope Rule triggers: 'if a proposal introduces a new bus envelope kind, it MUST note that shipping requires same-PR cassette_record.py + soak_driver.py coverage (feedback_cassette_must_cover_new_envelopes)'. The current proposal avoids this by using async out-of-band Sonnet calls, not bus envelopes. BINDING CONSTRAINT: Any follow-on that brings the Sonnet health classification into the bus (e.g., emitting a session_health_decision envelope) must land cassette coverage for the new envelope kind in the same PR. Current proposal is bus-envelope-free.

## Grounding

- src/stream_manager/message_bus.py:17-84 (schema: messages, decisions, sessions, hitl_pending tables + indexes)
- src/stream_manager/governance.py:41-76 (Mode enum, GovDecision dataclass, INTERVENTION_ACTIONS)
- dashboard/server.py:720-757 (existing /api/sessions endpoint + SQLite patterns)
- docs/adr/ADR-18-mvp-surface-freeze.md:1-250 (FROZEN/EVOLVING surface classification, Rule 1, MUST-floor inviolability)
- docs/adr/ADR-20-ui-redesign-experimental-spike.md:1-80 (EXPERIMENTAL spike classification, M1-M9 invariants)
