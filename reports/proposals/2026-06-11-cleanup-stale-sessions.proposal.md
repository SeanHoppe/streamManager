# Dashboard Stale Session Cleanup (Auto + Manual)

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (ux) 2026-06-11; idea COMFORTS-1; boldness STRETCH; refute verdict CONSTRAIN; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

External Claude sessions accumulate on the dashboard when processes exit (SIGKILL, terminal close). Operators must manually scan the external-sessions panel and cross-reference session_ids with current work. Multiple lingering sessions compound cognitive load. SM's own session must be rigorously excluded (polarity mandate). The operator cannot regain dashboard focus without manual bookkeeping.

## Proposal

Add a new POST /api/sessions/cleanup endpoint and dashboard banner+checkbox that detects exited sessions and purges message/decision/hitl rows older than 24h. Breakdown: (1) Session.list_exited_sessions() (added to session_watcher.py, EVOLVING surface) filters sessions.state == "exited" + last_seen >= 30min ago. (2) Dashboard banner appears when exited_count > 0; operator clicks "Clean Stale Sessions" to invoke cleanup. (3) POST /api/sessions/cleanup (additive endpoint in dashboard/server.py, no FROZEN modification) verifies SM_OWN_SESSION_ID != target_session_id at every row (hard guard per polarity mandate). (4) Backend hard-deletes message/decision/hitl rows with timestamp < (now - 86400s) for exited sessions only. (5) Emits cleanup_event envelope to bus (new additive envelope) with manifest {count_deleted, session_ids_purged, timestamp} for audit. (6) Optional: checkbox in FR-UI-9 settings row 9 enables auto-cleanup daily at 02:00 UTC (configurable). Auto-cleanup fires cleanup_event + logs to new cleanup_log table (schema: id, session_id, action, count_deleted, timestamp) and MUST exclude sessions whose last_message_at <= 5min ago (grace window for process restart races). Cleanup is irrevocable but fully audited via cleanup_event + cleanup_log. Non-goal: does not restore deleted data; purely operational hygiene.

## Operator value

Removes manual session bookkeeping burden. Dashboard stays lean (only active sessions visible by default). Operator regains focus on live work. Auto-cleanup (opt-in via checkbox) is the "calm-away" comfort that lets Sean step away from laptop for a meeting without returning to a cruft pile of exited processes. Audit trail (cleanup_event + cleanup_log) preserves forensic transparency -- who deleted what, when, why (grace window filter, age cutoff). Irrevocable cleanup trades data retention for operational sanity, with HITL boundary well-marked.

## Surfaces touched / added

- dashboard/server.py (new POST /api/sessions/cleanup endpoint, SM_OWN_SESSION_ID hard guard, returns {count_deleted, session_ids_purged, timestamp})
- src/stream_manager/message_bus.py (purge_exited_session(session_id: str, before_timestamp: float) method; new cleanup_log table schema: id TEXT PK, session_id TEXT, action TEXT, count_deleted INT, timestamp REAL; new cleanup_event envelope schema FROZEN as metadata-only extension)
- src/stream_manager/session_watcher.py (new list_exited_sessions() accessor, returns state='exited' sessions >= 30min stale; EVOLVING surface, safe to extend)
- dashboard/static/index.html (cleanup banner: hidden by default, shown when exited_count > 0; FR-UI-9 row 9: checkbox 'Enable daily cleanup at 02:00 UTC', persisted to FR-UI-9 localStorage + WAL session record, emits cleanup_event listener on checkbox toggle)
- tools/cassette_record.py (add cleanup_event envelope handler in _record_ppp_envelopes or new _record_cleanup_events function; recognize cleanup_event in soak-replay mode with {count_deleted, session_ids_purged, timestamp} payload)
- tools/soak_driver.py (add cleanup_event telemetry collection + integration test: emit cleanup_event under load, verify envelope captured + cleanup_log rows created, validate SM_OWN_SESSION_ID exclusion via hard-code grep or hook-inject)

## Feasibility

FEASIBLE. session_watcher.py is EVOLVING (safe to extend). POST endpoint is additive (no FROZEN modification). cleanup_event is metadata-only FROZEN extension. SM_OWN_SESSION_ID guard via os.environ.get() + hard string comparison is well-trodden pattern in server.py (grep shows 10+ existing uses, all correct). Grace window (5min age filter) + audit trail (cleanup_event + cleanup_log) are low-risk additions. The cassette/soak scope (new-envelope coverage) is standard per ADR-18 INTENT.md -- capture envelope shape, validate under soak load, test self-exclusion guard.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS -- no new certPortal coupling beyond learn-mode source registry. Cleanup targets sessions table only (no plugin/skill attribution); domain-agnostic.
- **Polarity (G2):** PASS -- hard guard via SM_OWN_SESSION_ID != target_session_id at every purge row. Grace window + audit trail (cleanup_event + cleanup_log) ensure no silent self-deletion. Cleanup is HITL-gated: user clicks banner OR opts into auto-schedule. SM monitors external sessions only; self-monitor silently skipped at registration (pre-existing guard in session_watcher._is_self_session). Double-layer exclusion: registration skip + cleanup hard-check.
- **ADR-18 MUST floor:** PASS -- no structural change to 3-frame layout. Cleanup banner is informational (paired label + 'Clean Stale Sessions' button), appears only on demand (exited_count > 0). Does not auto-foreground. Non-blocking. Audit-logged. Fully compliant with monitor-first + escalation-only foreground mandate. Color alone is never a signal; banner is text-first.
- **Frozen-surface note:** ZERO impact. session_watcher.py is EVOLVING (list_exited_sessions is additive accessor). dashboard/server.py is not listed FROZEN in ADR-18 Table; POST /api/sessions/cleanup is a new additive endpoint. message_bus.py envelope schemas are FROZEN but cleanup_event is metadata-only extension (within scope). governance.py, cli_governance.py, model_router.py, cli_pool.py untouched.
- **New-envelope note:** NEW BUS ENVELOPE RULE applies: cleanup_event is a new additive envelope kind (distinct from governance_call / governance_decision / lifecycle envelopes). MANDATORY same-PR coverage: (1) tools/cassette_record.py MUST recognize cleanup_event in soak-replay mode with {count_deleted, session_ids_purged, timestamp} payload. (2) tools/soak_driver.py MUST emit cleanup_event under load (via background cleanup task triggered during soak run) and validate envelope captured + cleanup_log rows exist. (3) Integration test MUST verify SM_OWN_SESSION_ID hard-guard: attempt cleanup on exited session, assert SM_OWN_SESSION_ID row is NOT deleted (grep cassette for exclusion proof). Without cassette scope, feature ships wired but cassette-blind, breaking replay parity. The constraint binds this proposal.

## Grounding

- C:/Users/SeanHoppe/vs/streamManager/docs/adr/ADR-18-mvp-surface-freeze.md:62 (bus envelope FROZEN metadata-only rule)
- C:/Users/SeanHoppe/vs/streamManager/INTENT.md:77-79 (3-frame monitor-first, escalation-only foreground, paired label+color)
- C:/Users/SeanHoppe/vs/streamManager/src/stream_manager/session_watcher.py:1-73 (SessionWatcher.list_active_sessions pattern + EVOLVING state)
- C:/Users/SeanHoppe/vs/streamManager/dashboard/server.py:2408-2412 (SM_OWN_SESSION_ID hard-guard pattern, well-established in 10+ endpoints)
- C:/Users/SeanHoppe/vs/streamManager/src/stream_manager/message_bus.py:17-150 (schema freeze pattern, additive extensions via new table + envelope type)
- C:/Users/SeanHoppe/vs/streamManager/docs/adr/ADR-18-mvp-surface-freeze.md:140-145 (cassette + soak coverage requirement for new envelopes)
