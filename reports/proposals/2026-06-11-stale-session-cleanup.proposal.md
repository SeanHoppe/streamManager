# Operator-driven stale session cleanup with soft-delete + restore

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (ux) 2026-06-11; idea BACKEND-1; boldness SAFE; refute verdict SHIP-PROPOSAL; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

Operators accumulate dead sessions in the governance bus over time with no TTL or archival mechanism. The dashboard lists all sessions newest-first but offers no affordance to clean up stale entries (ended >N hours ago, no recent messages, no pending HITL rows). Manual SQL DELETE statements are required, and forensic history is lost on hard-delete.

## Proposal

Expose POST /api/sessions/cleanup endpoint with two phases: (1) ?older_than_hours=24 returns a preview {matching_count, session_ids, deleted_message_count, deleted_decision_count} WITHOUT modifying the bus; (2) operator reviews in dashboard, then POSTs with ?confirm=1 to execute. Cleanup uses soft-delete (mark sessions.ended_at if NULL, set cleanup_ts timestamp; cascade soft-delete messages/decisions/hitl_pending/hitl_overrides/desktop_commands) rather than hard-DELETE so audit replay + forensics remain available via a separate GET /api/sessions/{id}/restore endpoint. SM's own session_id excluded via SM_OWN_SESSION_ID env var + comparison at both preview + confirm sites (loud-fail-safe filtering). Cleanup job is async background worker enqueued to avoid blocking the operator (latency budget <2s for preview query, indexed on sessions.ended_at). Does NOT touch patterns (L4 policies persist), learn_patterns (dialogue history separate), provenance_assertions (audit trail FROZEN). Surfaces: dashboard/server.py (POST /api/sessions/cleanup + async worker), message_bus.py (cleanup_session method + cascade logic), dashboard/ui-next/ (cleanup modal: confirmation list, preview count, restore per-session affordance), docs/jobs/ (new cleanup-API task entry).

## Operator value

One-click cleanup of stale sessions. Answers 'what can I safely delete' via preview. Prevents bus bloat + decision-feed spam. Maintains audit trail via soft-delete. Enables per-session forensic restore if needed.

## Surfaces touched / added

- dashboard/server.py (POST /api/sessions/cleanup endpoint, GET /api/sessions/{id}/restore, async worker dispatch)
- src/stream_manager/message_bus.py (cleanup_session method, cascade DELETE on messages/decisions/hitl_pending/hitl_overrides/desktop_commands)
- dashboard/ui-next/src/lib/components/SessionCleanupModal.svelte (confirmation list, preview count, restore per-session UI)
- docs/jobs/cleanup-api.md (new task entry documenting endpoint behavior + schema migration path)

## Feasibility

FEASIBLE. Cleanup operates on EVOLVING surfaces (sessions, messages, decisions, hitl_pending, hitl_overrides, desktop_commands tables -- all non-FROZEN). Database soft-delete migration pattern already established (see message_bus.py schema comments for provenance/learn_patterns append-only examples). Preview query uses existing indices on sessions.ended_at + timestamp; async worker pattern proven in jsonl_tail.py + learn_categorizer.py. Self-monitor firewall already wired in 5+ dashboard endpoints (SM_OWN_SESSION_ID filtering with loud-fail checks); no new infrastructure.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS -- no new certPortal coupling; cleanup operates on existing tables only (sessions, messages, decisions, hitl_pending, hitl_overrides, desktop_commands). Learn_patterns + provenance_assertions left untouched per FROZEN designation.
- **Polarity (G2):** PASS -- absolute SM-self firewall via SM_OWN_SESSION_ID env var + loud-fail-safe filtering at both preview (?older_than_hours) + confirm (?confirm=1) endpoints. Frontend selfExclude module already in place. Session firewall tested in existing endpoints (/api/sm-probe, /api/hitl/pending, /api/sessions). Cascade cleanup applies self-filter per-table to prevent cross-contamination.
- **ADR-18 MUST floor:** PASS -- proposal respects all ADR-18 3-frame UI MUSTs: (1) escalation-only foreground (cleanup is operator-initiated modal, not auto-triggered), (2) paired label+color badges (restore affordance includes session slug + ended_at timestamp, color per session state), (3) absolute HITL semantics unchanged (cleanup only affects messages/decisions/commands linked to ended sessions, no HITL override rewrites), (4) a11y axe gate applies to cleanup modal, (5) latency budget <2s for preview query (indexed scan on sessions.ended_at + ended_at IS NULL condition; no full-table joins), (6) non-goals respected (no IDE/multiplexer/multi-tenant features).
- **Frozen-surface note:** Zero FROZEN surfaces touched. Sessions/messages/decisions/hitl_pending/hitl_overrides/desktop_commands are all EVOLVING or appendable tables. Patterns (FROZEN per ADR-18) + learn_patterns (EVOLVING) + provenance_assertions (append-only FROZEN) all excluded from cleanup scope. No ADR amendment required.
- **New-envelope note:** No new bus envelope kind introduced. Cleanup is a synchronous API + async background worker; it does NOT emit governance_decision or any audit envelope. Existing bus infrastructure (governance.py + cli_governance.py) untouched. cassette_record.py + soak_driver.py require no new coverage (cleanup is operator-UI-driven, not a governance path that runs under soak).

## Grounding

- C:\Users\SeanHoppe\vs\streamManager\docs\adr\ADR-18-mvp-surface-freeze.md:58-71 (surface classification table, sessions/messages/decisions marked EVOLVING)
- C:\Users\SeanHoppe\vs\streamManager\src\stream_manager\message_bus.py:52-108 (sessions/messages/decisions/hitl_pending/hitl_overrides/desktop_commands schema definitions)
- C:\Users\SeanHoppe\vs\streamManager\dashboard\server.py:550-562 (SM_OWN_SESSION_ID meta-tag injection pattern)
- C:\Users\SeanHoppe\vs\streamManager\dashboard\server.py:2407-2412 (_check_not_own_session firewall function)
- C:\Users\SeanHoppe\vs\streamManager\docs\adr\ADR-5-latency-budget.md:1-50 (latency budget context; cleanup preview <2s acceptable within API tier)
