# Session checkpoint versioning for post-mortem drift analysis

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (ux) 2026-06-11; idea BACKEND-4; boldness STRETCH; refute verdict CONSTRAIN; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

Operators managing long-running oversight pipelines (e.g., certPortal) lack the ability to snapshot session state at key milestones and later compare "what changed between the 2pm run and the 4pm run?" without manually exporting JSONL. Sessions are live-only; once ended_at is set, session state cannot be rewound or diffed to detect drift in governance decisions or HITL overrides between runs.

## Proposal

Introduce POST /api/sessions/{session_id}/checkpoint and GET /api/sessions/{id}/compare endpoints plus two additive SQLite tables (session_checkpoints, checkpoint_diffs) to enable read-only session versioning. POST /api/sessions/{session_id}/checkpoint?name=<name>&ttl_days=<int> records a named digest snapshot of session state (checkpoint_id, session_id, name, timestamp, digest_state, decision_count_at_checkpoint, message_count_at_checkpoint). GET /api/sessions/{id}/checkpoints lists all snapshots for a session (excludes SM-self via WHERE clause: session_id != $SM_OWN_SESSION_ID). GET /api/sessions/{id}/compare?checkpoint_1=<id>&checkpoint_2=<id> diffs two checkpoints, returning delta_decisions, delta_messages, new_hitl_overrides, policy_changes_learned. No hard-delete; checkpoints are archived with soft-delete (archived_at timestamp). Latency budget: checkpoint creation <100ms (INSERT one row); comparison <500ms (SQLite JSON diff on two rows). Critical: the checkpoint endpoints MUST filter WHERE session_id != $SM_OWN_SESSION_ID (read from env BRIDGE_SM_OWN_SESSION_ID) at query time to enforce polarity-flip self-monitoring exclusion. Attempting to checkpoint SM's own session returns 403 or silently no-ops (loud failure mode per ADR-18 polarity rule). If checkpoint creation/comparison emits a new bus envelope kind (e.g., "session_checkpoint_created"), it MUST be recorded in cassette_record.py + soak_driver.py before ship (same PR per ADR-18 "NEW BUS ENVELOPE RULE"). If no new envelopes are emitted (write-only to DB), standard SQLite contract validation in soak tests suffices.

## Operator value

Enables drift detection between consecutive runs of the same long-running pipeline ("what changed since the last checkpoint?") and supports compliance audit trails for oversight sessions. Particularly valuable for post-mortem analysis when session state varies unexpectedly across runs. Convenience feature (structured deltas vs. manual JSONL export) rather than necessity (row-by-row export already works); laptop-first single-operator context (UI-DESIGN-SPEC D2-1) means post-mortem visibility improves workflow but is not safety-critical.

## Surfaces touched / added

- dashboard/server.py (POST /api/sessions/{id}/checkpoint, GET /api/sessions/{id}/checkpoints, GET /api/sessions/{id}/compare endpoints with SM_OWN_SESSION_ID WHERE-clause filtering)
- src/stream_manager/message_bus.py (additive tables: session_checkpoints, checkpoint_diffs; methods to snapshot digest state and compute deltas)
- dashboard/ui-next/ (optional: checkpoint creation modal triggered during session, checkpoint timeline/compare view)
- tools/soak_driver.py (if new bus envelopes emitted: cassette envelope schema validation + contract test asserting checkpoint table exists + inserts work within latency budget)
- tests/ (new file: test_checkpoint_self_monitor.py -- polarity test asserting POST /checkpoint on SM_OWN_SESSION_ID returns 403 or no-ops, never modifies the DB)

## Feasibility

FEASIBLE. Existing API/SSE patterns in server.py (lines 720-758 show session listing; lines 877-919 show hitl_pending read pattern) establish the precedent. New endpoints slot naturally into FastAPI app. Tables are simple inserts (checkpoint creation ~100ms per latency budget); deltas compute via SQLite JSON aggregation (GROUP_CONCAT or json_group_array) in <500ms. No CLI subprocess round-trip; no state-machine complexity. The latency budget (ADR-5, p50  7s) gates *governance decisions* (verdict hot path); checkpoints are async background reads post-mortem, never on critical path.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS. Proposal adds zero certPortal coupling. sessions table (message_bus.py lines 52-58) already exists with project_slug field; new session_checkpoints + checkpoint_diffs tables are additive, domain-agnostic reference data (no monitored-project vocab hardcoded). No certPortal vocabulary introduced.
- **Polarity (G2):** PASS. Critical: does NOT modify the live session or break determinism; purely observational. Operators can version any session EXCEPT SM's own (enforced at query time). POST /checkpoint endpoint implementation MUST include WHERE clause filter: SELECT ... FROM sessions WHERE session_id=? AND session_id != $SM_OWN_SESSION_ID OR reject with HTTP 403. GET /checkpoints list endpoint MUST exclude SM-self: WHERE session_id=? AND session_id != $SM_OWN_SESSION_ID. Server-side pattern already established (dashboard/server.py lines 293-309 show BRIDGE_SM_PROJECT_SLUGS exclusion in jsonl_tail startup; lines 322-330 show SM_OWN_SESSION_ID filtering). Test requirement: test_checkpoint_self_monitor.py MUST assert that POST /api/sessions/{session_id}/checkpoint where session_id==$SM_OWN_SESSION_ID returns 403 or silently no-ops (loud failure, no DB mutation).
- **ADR-18 MUST floor:** PASS. Proposal targets EXPERIMENTAL ui-next spike + backend; does NOT touch FROZEN surfaces (ADR-18 lines 60-68 list FROZEN: cli_pool, bus envelope schemas, governance._evaluate_inner_core, model_router.py, LifecycleBridge, wirecli, sync_comms, hitl -- sessions table NOT listed, therefore additive-only). New checkpoint tables are additive schema (no modifications to FROZEN sessions/messages/decisions/hitl_* tables). UI-DESIGN-SPEC M1-M19 do not mention checkpoints; this is pure backend feature (optional operator tooling) not a MUST-floor requirement. Dashboard server.py can host new read-only endpoints without ADR-18 amendment.
- **Frozen-surface note:** NONE. No FROZEN surface is touched. message_bus.py lines 52-58 (sessions table) is not in FROZEN list. New tables (session_checkpoints, checkpoint_diffs) are additive schema additions, governed by Rule 1 (additive-only to non-FROZEN tables). If a future phase wishes to emit a new bus envelope kind from checkpoint creation (e.g., 'session_checkpoint_created'), that would require amending ADR-18 to add the envelope to the FROZEN bus envelopes row; current proposal assumes write-only to DB (no new envelope emission).
- **New-envelope note:** CONDITIONAL per ADR-18 'NEW BUS ENVELOPE RULE': (1) If checkpoint creation/comparison endpoints emit a new bus envelope kind, those envelope schemas MUST be recorded in cassette_record.py + soak_driver.py in the same PR before ship. Envelope must be additive-only metadata extension (no envelope-shape change to existing FROZEN schemas). (2) If NO new envelopes are emitted (checkpoint write-only to SQLite, no message bus fanout), then soak testing requires only standard SQLite contract validation: verify session_checkpoints table exists, INSERT succeeds atomically, diffs compute in <500ms latency budget. (3) MANDATORY polarity test in soak_driver.py or tests/: assert that POST /api/sessions/{id}/checkpoint where id==$SM_OWN_SESSION_ID returns HTTP 403 Forbidden or silently succeeds with no DB rows written (loud failure mode per feedback_no_self_monitor.md). Test file: tests/test_checkpoint_self_monitor.py.

## Grounding

- message_bus.py:52-58 (sessions table schema, project_slug field)
- dashboard/server.py:720-758 (session listing endpoint pattern)
- dashboard/server.py:877-919 (hitl_pending read pattern for reference)
- dashboard/server.py:293-309 (BRIDGE_SM_PROJECT_SLUGS polarity-flip wire-site refusal pattern)
- dashboard/server.py:322-330 (SM_OWN_SESSION_ID filtering example in jsonl_tail)
- docs/adr/ADR-18-mvp-surface-freeze.md:60-68 (FROZEN surface list)
- docs/adr/ADR-18-mvp-surface-freeze.md:41-90 (Rule 1 FROZEN classification + additive-only constraint)
- docs/adr/ADR-18-mvp-surface-freeze.md:286-340 (Amendment 2026-05-12 'NEW BUS ENVELOPE RULE' precedent + cassette coverage requirement)
- UI-DESIGN-SPEC.md:1-12,50-63 (operator profile, single-user, laptop-first context, post-mortem tooling value)
- ADR-5-latency-budget.md (latency budget p50  7s for governance; async checkpoint reads are off-critical-path)
