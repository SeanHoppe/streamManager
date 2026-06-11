# Session health digest endpoint for operator glance-readability

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (flywheel) 2026-06-11; idea BACKEND-2; boldness STRETCH; refute verdict SHIP-PROPOSAL; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

Operators checking on a background session must execute 4 separate HTTP calls (/api/decisions?session_id=X, /api/agents?session_id=X, /api/lifecycle/jobs?session_id=X, /api/hitl/pending?session_id=X) to build a mental model of session state. No single endpoint synthesizes recent activity, latest escalation, agent roster, or job queue into an operator-consumable summary. This 4x chattiness burdens the session-picker UI, forcing either poll-hell or forced page refreshes, and prevents rapid triage of which sessions need attention.

## Proposal

Add a new GET /api/sessions/{id}/digest endpoint to dashboard/server.py that returns a single JSON object aggregating six dimensions of session state: {session_id, project_slug, started_at, ended_at, uptime_seconds, decision_count, latest_decision: {id, action, confidence, agent_id, timestamp}, active_agent_count, agents: [{id, profile_slug, last_seen_ts, event_count}], active_job_count, hitl_pending_count, hitl_mode, latest_escalation: {type, timestamp, severity}}. Scope to dashboard server only; implement with a 2s per-session TTL cache to amortize repeated polls. The digest aggregates existing schema (sessions, decisions, agents, lifecycle, hitl_pending tables) using well-known SQL join patterns already used by api_decisions, api_agents, api_hitl_pending, and api_lifecycle_jobs. Apply _reject_sm_own(session_id) guard to prevent SM self-monitoring. No UI changes, no new envelope types, no FROZEN surface modifications -- proposal is backend-only. ui-next session-picker would later consume digest.hitl_pending_count + digest.latest_escalation.severity to power badge rendering (paired label+color per M4 MUST), but that UI work is out-of-scope; the endpoint is data-source-ready.

## Operator value

Cuts chattiness 4x on repeated operator session checks by collapsing 4 roundtrips into 1, with 2s TTL cache enabling high hit-rate on typical laptop monitor-first workflow (10+ concurrent sessions, rapid glance-checks). Directly addresses INTENT.md glance-readability (line 77-80) and UI-DESIGN-SPEC.md 2 operator profile (D2-2, wants session picker to filter without opening each card). Powers session-picker health badges (red if hitl_pending_count > 0, amber if latest_escalation.severity='governance_variance_alert', green if quiet) without requiring SSE plumbing or per-session subscriptions. Single operator, single laptop: latency improvement is real for 10+ concurrent sessions; backend reduces bottleneck.

## Surfaces touched / added

- dashboard/server.py -- new GET /api/sessions/{id}/digest endpoint (queries sessions, decisions, agents, hitl_pending, lifecycle tables; applies _reject_sm_own guard; implements 2s TTL in-memory cache)
- dashboard/ui-next/ -- out-of-scope; ideation only -- session-picker dropdown to consume digest.{hitl_pending_count, latest_escalation.severity} for badge rendering (paired label+color per M4 MUST floor)

## Feasibility

FEASIBLE. The endpoint aggregates six read-only queries over existing schema (message_bus.py:17-150 tables: sessions, decisions, agents, hitl_pending, messages, desktop_commands). All required tables exist and carry proper indexes (idx_messages_session_seq, idx_decisions_message, idx_agents_session, idx_hitl_pending_unresolved). Queries follow well-known patterns already live in api_decisions (line 589-615), api_agents (line 619-660), api_hitl_pending (line 878-919), and api_lifecycle_jobs (line 689-717). SQL aggregates are simple COUNT/MAX/JOIN patterns; most effort is plumbing the 2s TTL cache (straightforward in-memory dict with expiry check on __get__). The _reject_sm_own guard pattern exists at server.py:2406 and is already applied to /api/sm-probe and /api/commands/stream. Estimated 60-80 LOC (endpoint handler + cache helper + 3-4 SELECT statements). Zero risk of schema migration or envelope breakage.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS. The endpoint adds a new read-only path scoped to the dashboard server; no new coupling to certPortal beyond the already-designed learn-mode source registry and project_context. Session identity and project_slug flow from the data (caller provides session_id, rows are filtered by that param), not from hardcoded vocabulary. No monitored-project JOB-IDs, roles, or domain-specific labels are baked into the endpoint implementation.
- **Polarity (G2):** PASS. The endpoint is read-only observation of session state where the caller supplies session_id. Per server.py:2406-2413, _reject_sm_own(session_id) must be applied on entry to prevent SM from querying its own digest (SM_OWN_SESSION_ID gate). Per INTENT.md v2.3 P1 Seed 6 (polarity-flip enforcement on read-only observation), SM-self is barred from self-monitoring digest; dashboard read of external sessions is safe. The 2s TTL cache is per-session and does not introduce cross-session observation leaks.
- **ADR-18 MUST floor:** PASS. The endpoint is read-only observational; introduces zero UI changes (ui-next ideation is out-of-scope). The M4 MUST (paired label+color, always) is preserved because the future session-picker badge consumer would pair digest.hitl_pending_count with a text label ('ACTION REQUIRED') and color (#d97706 amber) per the M4 constraint (INTENT.md:85-86, UI-DESIGN-SPEC.md:3b). The endpoint itself does not modify UI behavior, only provides the data source for a future ui-next implementation to satisfy M4. No 3-frame presence change (M1), no escalation-only foreground change (M2), no frame action-count change (M3). All 19 MUSTs remain intact.
- **Frozen-surface note:** No FROZEN surface modifications. The proposal is entirely new endpoint + cache helper in dashboard/server.py (EVOLVING per ADR-18). Does not touch governance.py, message_bus.py, cli_governance.py, model_router.py, or cli_pool.py (all FROZEN per ADR-18). Per INTENT.md hot zones (line 125-128), dashboard/server.py is actively touched per cycle; this work is on the natural evolution path.
- **New-envelope note:** No new bus envelope kinds. The endpoint reads existing schema only (sessions, decisions, agents, hitl_pending tables; messages for joins). Does NOT emit any new message type / bus envelope. If a future feature requires a new envelope kind (e.g., 'session_digest_cached' for audit), that ship would require same-PR cassette_record.py + soak_driver.py coverage per feedback_cassette_must_cover_new_envelopes; this proposal is exempt because it is read-only and introduces zero new envelope emission.

## Grounding

- dashboard/server.py:589-615 -- api_decisions pattern for session_id filter
- dashboard/server.py:619-660 -- api_agents pattern for session-scoped query
- dashboard/server.py:878-919 -- api_hitl_pending pattern for unresolved count
- dashboard/server.py:689-717 -- api_lifecycle_jobs aggregation via lifecycle_bridge.list_active_jobs
- dashboard/server.py:2406-2413 -- _reject_sm_own guard pattern
- src/stream_manager/message_bus.py:17-150 -- schema definition (sessions, decisions, agents, hitl_pending, messages)
- src/stream_manager/lifecycle_bridge.py:481-560 -- list_active_jobs SQL window-function pattern (dedup + latest envelope per job_id)
- INTENT.md:77-80 -- glance-readability principle; operator needs session picker to filter without context-switching
- UI-DESIGN-SPEC.md:54-59 -- operator profile; wants to triage sessions at a glance via badges
- UI-DESIGN-SPEC.md:82-90 -- M4 MUST floor (paired label+color, always; never color-only)
- docs/adr/ADR-18-mvp-surface-freeze.md:59-73 -- surface classification (dashboard/server.py is EVOLVING, not FROZEN)
