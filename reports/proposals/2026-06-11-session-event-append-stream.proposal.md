# Durable session event cursor -- browser resumption across refreshes

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (ux) 2026-06-11; idea BACKEND-3; boldness WILD; refute verdict SHIP-PROPOSAL; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

The dashboard refreshes decision feed on a 5s poll to /api/decisions + a persistent SSE /events connection. When the browser refreshes, the client loses buffered state (decision count, latest decision, open action counts, session digest) and must re-seed all endpoints. In high-latency or flaky-connection scenarios, operators lose monitoring context. No durable cursor enables a client to resume from "the last state I saw" without re-polling all endpoints.

## Proposal

Expose GET /api/sessions/{session_id}/events?since=&lt;last_event_id&gt;&amp;full=0 returning an append-only snapshot of the session's envelope stream: [{event_id, type, content, timestamp, digest_delta}]. The digest_delta is a partial-update object: {pending_hitl_count: +1, decision_count: +1, latest_action: 'BLOCK', ...} computed server-side so the client can accumulate without re-polling. Last-event-id is a cursor from the database (max(rowid) in messages/decisions/envelopes tables). Endpoint returns up to 100 events per call; caller uses ?since= to paginate. Browser SSE subscriber stores last_event_id in sessionStorage keyed on (session_id, dashboard-origin) so a page refresh resumes from the exact point it left off. Add optional ?full=1 query param to return the full digest state (not just delta) at the cursor position -- useful for cold-start / session switch. Latency budget: &lt;100ms for a 100-event span (indexed on session_id + event_id DESC). Implementation surfaces: (1) message_bus.py: new public method events_since(session_id, last_id) that UNIONs messages + decisions + named bus events + lifecycle envelopes, sorts by timestamp + rowid, computes digest_delta incrementally; (2) dashboard/server.py: GET /api/sessions/{id}/events?since=N&amp;full=1 endpoint with SM_OWN_SESSION_ID filtering; (3) dashboard/ui-next/: sessionStorage cursor tracking, SSE subscriber resume logic, cold-start full-digest load.

## Operator value

Session state persists across browser reloads. Operator can resume monitoring from where they left off instead of losing context. Reduces re-polling overhead by giving the client a durable cursor. Enables future 'resume from X minutes ago' audit review (load session digest at a past timestamp, then stream forward). For a multi-tab / multi-window operator workflow (bouncing between sessions), resumption from cursor without re-seeding is foundational. Assessed as MEDIUM for single-laptop baseline, MEDIUM-HIGH for fleet operators.

## Surfaces touched / added

- dashboard/server.py (GET /api/sessions/{id}/events?since=N&amp;full=1 endpoint with SM_OWN_SESSION_ID filtering per line 2740 pattern)
- src/stream_manager/message_bus.py (new public method events_since(session_id, last_id) that UNIONs messages + decisions + named bus events + lifecycle envelopes, sorts by timestamp + rowid, capped at 100 rows)
- dashboard/ui-next/src/lib/sse.js (sessionStorage cursor tracking, SSE subscriber resume logic, cold-start full-digest load)
- dashboard/ui-next/src/lib/stores/session.js (cursor persistence keyed on session_id + dashboard origin)

## Feasibility

The /api/sessions/{session_id}/events?since=&lt;last_id&gt;&amp;full=1 endpoint is a straightforward read: (1) Server: UNION query across (messages.rowid, decisions.rowid, bus envelopes from internal messages table) filtered by session_id and rowid &gt; last_id, sorted by timestamp + rowid, capped at 100 rows. Index on (session_id, rowid DESC) makes this &lt;100ms per spec. (2) Client: sessionStorage cursor keyed on (session_id, dashboard-origin); SSE subscriber stores event_id on each recv and resumes from it on reconnect. (3) Browser patterns: EventSource Last-Event-ID and sessionStorage are standard; the code already uses both (see sse.js lines 28-399, decision-row id: d{rid}:m{mrid} format). (4) No schema changes needed -- all data already in gov.db. FEASIBLE.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS -- No new certPortal coupling. The endpoint and bus query are purely SM-internal: session event stream from gov.db tables (messages, decisions, envelopes). No monitored-project vocabulary introduced (domain-agnostic, rendered from data only).
- **Polarity (G2):** PASS -- SM_OWN_SESSION_ID exclusion inherited from /events line 2740 pattern. Pseudo-code: if session_id == SM_OWN_SESSION_ID or is in BRIDGE_SM_PROJECT_SLUGS, return 403 Forbidden. The new endpoint MUST apply the same SM_OWN_SESSION_ID filter; no sweep of SM-self possible.
- **ADR-18 MUST floor:** PASS -- Proposal touches three surface classes: (1) message_bus.py -- FROZEN per ADR-18 L62. New public method events_since(session_id, last_id) is additive (no public symbol modification, no schema change to messages/decisions tables). Allowed per ADR-18 Rule 1 'additive extension'. (2) dashboard/server.py -- EVOLVING (FR-UI-8, Phase 6 live-monitor cited in comments). Feature work allowed. (3) dashboard/ui-next/ -- EVOLVING (KingMode spike, ADR-20). Feature work allowed. No FROZEN surface (governance.py, cli_governance.py, model_router.py, cli_pool.py) is touched.
- **Frozen-surface note:** message_bus.py is FROZEN per ADR-18 L62, but the proposal adds a new public method (events_since), which is additive and allowed. No schema changes to messages/decisions tables. No rip of prior symbols. No ADR amendment required.
- **New-envelope note:** The proposal does NOT introduce a new ENVELOPE_KINDS entry -- it exposes existing messages/decisions/lifecycle rows via HTTP pagination, not as a new bus envelope type. No cassette_record.py or test_envelope_coverage.py change required. The endpoint is a read-only view over existing tables; no new envelope kind on the wire.

## Grounding

- dashboard/server.py:2740 (SM_OWN_SESSION_ID filter pattern for /events)
- dashboard/ui-next/src/lib/sse.js:228-399 (existing SSE subscriber + sessionStorage cursor logic)
- src/stream_manager/message_bus.py:18-212 (schema + indexes for messages, decisions, envelopes)
- docs/adr/ADR-18-mvp-surface-freeze.md:41-72 (surface classification; message_bus FROZEN)
- docs/adr/ADR-20-ui-redesign-experimental-spike.md:63-77 (dashboard/ui-next EXPERIMENTAL classification)
