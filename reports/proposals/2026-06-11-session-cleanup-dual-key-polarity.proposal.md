# Stale Session Cleanup (Dual-Key Polarity Fix)

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (flywheel) 2026-06-11; idea COMFORTS-1-stale-session-cleanup-constrained; boldness STRETCH; refute verdict CONSTRAIN; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

Operators accumulate exited sessions on the dashboard as Claude CLI processes exit, directories vanish, or JSONL tails stall. No signal distinguishes live vs. dead sessions; manual cwd checking is required before filtering. Dashboard glance-readability (INTENT.md:77-79) degrades as session list becomes noise. Additionally, a naive session-cleanup implementation risks SM self-monitoring breach by relying on session_id in the SQL WHERE, violating CLAUDE.md L42's dual-key durable-selector mandate.

## Proposal

Add POST /api/sessions/cleanup endpoint + dashboard settings banner that detects exited sessions and archives old rows. Scope: (1) session_watcher.py EVOLVING surface extended with list_exited_sessions() accessor, returns state=='exited' + last_seen >= 30min ago. (2) Dashboard settings panel (FR-UI-9 context) shows cleanup banner when exited_count > 0; operator clicks 'Sweep' to invoke cleanup. (3) POST /api/sessions/cleanup endpoint at dashboard/server.py (additive, no FROZEN modification) implements DUAL-KEY polarity filter: SQL WHERE clause filters on `project_slug NOT IN (?)` parameterized by BRIDGE_SM_PROJECT_SLUGS env (default {streamManager}), then applies optional post-hoc Python backstop `session_id != BRIDGE_SM_SELF_SESSION_ID` as defence-in-depth per CLAUDE.md L42-43 dual-key split (durable read key + cheap ephemeral backstop). Endpoint returns {count_archived, session_ids_purged, timestamp}. (4) New additive sessions_archive WAL table schema: id, session_id, project_slug, archived_at, reason (idle|process_gone|cwd_inaccessible). (5) Crucially: NO cleanup of SM-self rows even when BRIDGE_SM_SELF_SESSION_ID env unset (fail-loud precondition via project_slug NOT IN clause at SQL, not session_id reliance). (6) Optional: checkbox in settings enables daily auto-cleanup at 02:00 UTC (grace window: do not archive sessions with last_message_at <= 5min ago to avoid race with process restart).

## Operator value

Removes manual session hygiene toil. Dashboard stays lean (only active sessions visible by default). Operator regains focus on live work. Dual-key polarity compliance (project_slug as durable read key, session_id as Python backstop) ensures SM never archives its own session rows even when self-session env var is unset, eliminating silent self-monitor leakage risk.

## Surfaces touched / added

- dashboard/server.py -- new POST /api/sessions/cleanup endpoint with dual-key polarity filter (SQL WHERE project_slug NOT IN + Python backstop session_id !=), returns {count_archived, session_ids_purged, timestamp}
- src/stream_manager/message_bus.py -- new sessions_archive WAL table (schema: id, session_id, project_slug, archived_at, reason), archive-event envelope metadata-only extension (FROZEN-compliant)
- src/stream_manager/session_watcher.py -- new list_exited_sessions() accessor (EVOLVING surface, additive)
- dashboard/static/index.html -- cleanup banner in settings panel (FR-UI-9 context), shown when exited_count > 0, paired label + 'Archive' button, opt-in checkbox for daily auto-cleanup at 02:00 UTC with 5min grace window
- tools/cassette_record.py -- archive-event envelope handler in soak-replay mode
- tools/soak_driver.py -- emit archive-event under load + dual-key guard integration test

## Feasibility

FEASIBLE. session_watcher.py is EVOLVING (safe to extend). POST endpoint is additive to dashboard/server.py (no FROZEN modification). Dual-key filter pattern is well-established precedent in rl/corpus_augment.py:44-57 (project_slug durable WHERE) + rl/corpus_augment.py:91-95 (_filter_self_monitor Python backstop). SQL parameterization via BRIDGE_SM_PROJECT_SLUGS + os.environ.get() is trodden pattern (10+ uses in server.py, all correct). Grace window + audit trail are low-risk.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS -- no new certPortal coupling beyond learn-mode source registry. Archive targets sessions table only (domain-agnostic). No plugin/skill attribution.
- **Polarity (G2):** PASS -- DUAL-KEY filter at SQL WHERE + Python backstop per CLAUDE.md L42-43. Project_slug NOT IN (BRIDGE_SM_PROJECT_SLUGS) is durable read-side key (fails loud when env unset or SM-variant). Session_id != BRIDGE_SM_SELF_SESSION_ID is cheap post-hoc Python backstop (defence-in-depth on ephemeral key). SM-self rows never archived even when session_id env unset, because project_slug='streamManager' is excluded at SQL WHERE. Precedent: rl/corpus_augment.py:44-57 (SQL durable) + :91-95 (Python backstop).
- **ADR-18 MUST floor:** PASS -- no structural change to 3-frame layout (INTENT.md:77-79). Banner is informational paired label + button, shown only on demand (exited_count > 0). Does not auto-foreground. Non-blocking. Paired label + color badges per INTENT.md:85-86. Dashboard monitor-first model preserved. Color alone never a signal.
- **Frozen-surface note:** ZERO impact. session_watcher.py is EVOLVING (list_exited_sessions is additive accessor). dashboard/server.py not listed FROZEN in ADR-18 Table (57 lists FROZEN surfaces: cli_pool, bus envelopes, governance._evaluate_inner_core, model_router, LifecycleBridge, wirecli transport). POST /api/sessions/cleanup is new additive endpoint. message_bus.py envelope schemas FROZEN but new archive-event envelope is metadata-only extension. governance.py, cli_governance.py, model_router.py, cli_pool.py untouched.
- **New-envelope note:** NEW BUS ENVELOPE RULE applies: archive-event is a new additive envelope kind (distinct from governance_call / governance_decision / lifecycle / cleanup-event). MANDATORY same-PR coverage: (1) tools/cassette_record.py MUST recognize archive-event in soak-replay mode with {count_archived, session_ids_purged, timestamp, reason_breakdown} payload. (2) tools/soak_driver.py MUST emit archive-event under load (via background cleanup task during soak run) and validate envelope captured. (3) Integration test MUST verify dual-key hard-guard: attempt cleanup on exited SM-self session (project_slug='streamManager' or null), assert SM row NOT archived (prove project_slug WHERE clause fired). Without cassette scope, feature ships cassette-blind, breaking replay parity.

## Grounding

- C:/Users/SeanHoppe/vs/streamManager/CLAUDE.md:31-45 (Session-source exception rule, dual-key split, durable read key, cheap backstop)
- C:/Users/SeanHoppe/vs/streamManager/rl/corpus_augment.py:44-57 (project_slug WHERE precedent)
- C:/Users/SeanHoppe/vs/streamManager/rl/corpus_augment.py:91-95 (Python session backstop precedent)
- C:/Users/SeanHoppe/vs/streamManager/reports/proposals/2026-06-11-polarity-dual-key-read-write-split.proposal.md (dual-key split rationale + verified constraint)
- C:/Users/SeanHoppe/vs/streamManager/INTENT.md:77-79 (3-frame monitor-first, escalation-only foreground)
- C:/Users/SeanHoppe/vs/streamManager/docs/adr/ADR-18-mvp-surface-freeze.md:57-73 (surface state classification, EVOLVING vs FROZEN, new-envelope rule)
- C:/Users/SeanHoppe/vs/streamManager/dashboard/server.py:721-757 (existing /api/sessions endpoint structure, SM_OWN_SESSION_ID guard pattern)
