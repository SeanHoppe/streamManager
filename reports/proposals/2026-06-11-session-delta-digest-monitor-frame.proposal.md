# Session Delta Digest: Multi-Session Activity Snapshot in Monitor Frame

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (ux) 2026-06-11; idea MONITOR-3; boldness STRETCH; refute verdict CONSTRAIN; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

Operator context-switches between async governance sessions or steps away for 2+ minutes. Returns to dashboard: which sessions saw new escalations? which agents shifted mode? which patterns promoted? All are buried in the Feed. Operator must re-read the entire decision log per session to catch the delta. Async HITL mode makes this worse -- decisions complete while the operator is monitoring a different session. The "did anything change?" whiplash breaks flow.

## Proposal

Introduce a lightweight SessionDeltaDigest panel in the Monitor frame, positioned below the HITL queue (collapsed by default, expands on new activity). Renders as a compact 5-row summary per monitored session:
(1) elapsed time since operator last clicked into that session;
(2) count of new GUIDE/INTERVENE/BLOCK decisions (numeric badge paired with text label per M5);
(3) count of agent-mode escalations (engineer -> INTERVENE mode);
(4) count of L4-pattern promotions;
(5) one representative decision reason (e.g., "Negative regression in xyz").

Rows with non-zero activity render with an amber background PLUS a paired numeric/text badge (e.g., "[+4 decisions]", "[2 escalations]") to satisfy ADR-20 M5 (paired label+color, color never alone). On click, the panel jumps to that session and expands the Feed to show the new decisions. Digest resets when operator navigates into a session (acknowledgment semantics). SSE-driven; no polling. For multi-session operators, the digest becomes the "what did I miss?" dashboard without context-switching.

## Operator value

Eliminates context-switch friction and decision-backlog re-reading. Operator manages 3-5 async sessions in parallel ("I'll check back in 5 min") knowing the digest surfaces changes at a glance via paired badges, not requiring full Feed re-scan on return. Supports distributed governance workflows where different operators monitor different session groups. Latency under 200ms per SSE tick (aggregation query over existing decisions/messages tables).

## Surfaces touched / added

- dashboard/ui-next/src/components/SessionDeltaDigest.svelte (new component)
- dashboard/ui-next/src/components/SessionDeltaRow.svelte (new sub-component for each row, enforcing M5 paired badge contract)
- dashboard/server.py: /api/session-delta?since_ts=<last_seen> (new endpoint, returns compact summary per session, excludes SM-self per polarity rule)
- dashboard/server.py: /api/session-delta-reset (new POST endpoint to clear last_seen timestamp on operator navigate-in)
- message_bus.py: optional delta-summary aggregation view (materialized view or computed on-the-fly from decisions/messages tables, filtering by session_id AND decision.timestamp > session.last_operator_interaction)

## Feasibility

FEASIBLE. Aggregation query is straightforward SQL over existing decisions/messages tables (indexed on session_id, timestamp). Svelte integration is a peer to existing ui-next components (DecisionRow, Badge). SSE wiring uses existing dashboard infrastructure (App.svelte already listens to sse.js). The backend exclusion of SM-self session is a read-only WHERE clause (polarity already enforced at /api/decisions and /api/sessions endpoints). No new message-bus envelope kinds; no cassette/soak coverage required. M5 compliance is enforced structurally via Badge.svelte (color without paired text label is impossible by construction, per Badge.svelte L96-102).

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS. Feature is domain-agnostic -- the digest renders governed-target identities (session_id, agent_profile_slug, decision count, pattern count) entirely from data, never hard-codes monitored-project vocabulary. New endpoints (/api/session-delta, /api/session-delta-reset) accept query params (session_id) and return data-driven summaries (no certification-portal coupling, no monitored-project slugs baked into SM).
- **Polarity (G2):** PASS. /api/session-delta explicitly excludes SM-self session via WHERE clause (reads SM_OWN_SESSION_ID env var, same pattern as _reject_sm_own() at server.py L2406). Polarity rule: 'SM monitors NON-SM sessions only (project_slug NOT IN {streamManager} AND session_id != self)'. This proposal's SM-self exclusion at the query layer satisfies the session_id != self half (project_slug filtering is operator-side session picker). Digest will never surface the SM's own session as a row to the operator.
- **ADR-18 MUST floor:** COMPLIANT per refuter constraint. ADR-20 M5 requires 'Actionable vs informational state visible at a glance via paired label + color badges. Color alone is not a signal.' Original proposal framing used 'rows with non-zero activity glow amber' as the sole signal (color-only breach of M5). CONSTRAINED: every row that renders with amber background MUST pair with a text+numeric badge (e.g., '[+4 decisions]', '[2 escalations]', '[1 L4 promotion]', '[0 new decisions]'). Amber glow is visual emphasis; paired badge is the durable signal. This is enforced at the SessionDeltaRow component level (enforces Badge.svelte contract: no badge construction without a label, per Badge.svelte L96-102 structural throw). The constraint is SHOULD-level UX refinement (no architectural cost; just row formatting), not a MUST violation that kills the idea.
- **Frozen-surface note:** None. Proposal touches NO FROZEN surfaces per ADR-18. dashboard/server.py is EVOLVING (v1.9 P2, session_watcher.py + bg task token registry maturing). New /api/session-delta endpoints are additive (no shape change to existing frozen endpoints /api/decisions, /api/sessions, /api/lifecycle/jobs). message_bus.py is FROZEN for existing envelope schemas, but this proposal does NOT introduce a new envelope kind (aggregation happens at query time, not via bus). No amendment to ADR-18 required.
- **New-envelope note:** None. Proposal does NOT introduce a new bus envelope kind. Session delta summary is computed on-the-fly via SQL query over existing decisions/messages tables, or rendered via materialized view (optional optimization, same data, no new envelope). No cassette/soak coverage required per NEW BUS ENVELOPE RULE.

## Grounding

- docs/adr/ADR-20-ui-redesign-experimental-spike.md:48 (M5 paired label+color definition)
- docs/adr/ADR-18-mvp-surface-freeze.md:71 (dashboard/server.py EVOLVING state)
- dashboard/ui-next/src/lib/components/Badge.svelte:96-102 (structural M4 enforcement: no badge without label, color-without-text impossible by construction)
- dashboard/ui-next/src/lib/components/DecisionRow.svelte:4-10 (M4 contract: paired label+color badges, reused in SessionDeltaRow)
- dashboard/server.py:2406-2412 (_reject_sm_own pattern for polarity enforcement, applied to new endpoints)
- dashboard/server.py:588-619 (existing /api/decisions + /api/agents endpoints as aggregation-query precedent)
