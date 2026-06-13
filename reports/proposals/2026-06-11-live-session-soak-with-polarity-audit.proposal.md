# Frame D: Live Session Soak Control Panel with Polarity Audit

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (flywheel) 2026-06-11; idea SOAK-1; boldness STRETCH; refute verdict SHIP-PROPOSAL; effort L.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

Section 5.3 of the proposal context identifies that 1252 active sessions is mostly stale entries, drowning out busiest targets. Operators cannot deterministically pick a live non-SM session to soak against. Tier 1.5/3 soaks inject synthetic load and skip the real JsonlTailWorker tail path, never validating the polarity gate (project_slug NOT IN streamManager) or the learn-mode ingest front-half. This creates a 30-minute blind spot where polarity regressions go undetected until ship-gate completes.

## Proposal

Introduce Frame D 'Soak Control Panel' as a dashboard-only surface (opt-in visibility toggle in settings). Panel contains: (A) 'Live Session Selector' ranking non-SM sessions by (busy_score, last_update_recency); displays name/project_slug/last_msg_timestamp/session_id; excludes session_id == BRIDGE_SM_SELF_SESSION_ID and rejects cwd paths matching firewalled patterns. (B) 'Soak Launch' button fires new Tier 4 soak: tools/soak_driver.py --live-session <session_id> --duration-seconds 300. Attaches to JSONL tail, runs live for 5min, emits per-band latency report (ALLOW/L2/L3/L4), plus polarity audit row: 'project_slug rejection count' (count of filtered sessions where project_slug IN streamManager). Operator sees progress as SSE events (message count / decision count / elapsed, ~1s cadence). On completion, dashboard embeds soak report markdown inline with polarity audit failures in hard red badge. No auto-gate enforcement; operator reviews and decides.

## Operator value

Operators can select known-good non-SM sessions by name/recency instead of grepping .claude/gov.db. One-click 5-minute live soak with immediate dashboard results (no terminal context-switch). Polarity audit closes #r1 feedback loop: if project_slug filter breaks, rejection counts spike visibly before ship-gate. Eliminates 30-minute blind spot and automates polarity validation at low cost (~5 real claude calls per run vs 60 for Tier 3).

## Surfaces touched / added

- dashboard/ui-next/src/routes/Soak.svelte (new Frame D component)
- dashboard/ui-next/src/lib/SessionSelector.svelte (session picker subcomponent)
- dashboard/ui-next/src/lib/SoakProgress.svelte (live progress display)
- dashboard/server.py:/api/soak/sessions (endpoint: list non-SM sessions, ranked by recency+activity)
- dashboard/server.py:/api/soak/launch (endpoint: POST to fire live-session soak, returns soak_id)
- dashboard/server.py:/api/soak/status/<soak_id> (endpoint: SSE or polling, progress + final report)
- tools/soak_driver.py (new --live-session flag + Tier 4 impl)
- tools/soak_driver.py (polarity audit subroutine: count rejections by project_slug)
- docs/adr/ADR-17-soak-tiers.md (Tier 4 amendment + polarity audit spec)

## Feasibility

FEASIBLE. All surfaces additive (~1200 LOC total across dashboard + soak_driver). No FROZEN surface mutations (governance.py, message_bus.py, cli_governance.py, model_router.py, cli_pool.py remain untouched). Tier 4 follows existing Tier 1.5 pattern: real-CLI calls, same engine.evaluate loop, no new envelope types. Polarity filtering precedent established in learn-mode ingest (project_context.py, governance.py lines 902-941). Test precedent for HITL routing + SSE progress already established in existing dashboard.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS -- dual filters at /api/soak/sessions endpoint AND in Frame D subcomponent (project_slug != streamManager AND session_id != SM_SELF) prevent certPortal coupling. No read of certPortal repo. Firewall enforced in Python WHERE clause (durable, loud on zero rows) + cheap post-hoc filter (defense-in-depth).
- **Polarity (G2):** PASS -- architecture prevents SM monitoring itself. /api/soak/sessions query includes WHERE project_slug NOT IN (streamManager) AND session_id != BRIDGE_SM_SELF_SESSION_ID. No sweep-stale logic that could self-include. Soak report surfaces polarity audit so regressions are visible.
- **ADR-18 MUST floor:** PASS -- ADR-18 M1-M9 all satisfied. M2 (escalation-only foreground) enforced: soak verdict button routes through Frame A HITL modal via message-driven workflow (soak_ready_for_ship_gate -> hitl_pending -> Frame A escalation), not inline in Frame C. M4 (paired label+color): SoakProgress badges show STATE + label ('IN_PROGRESS', 'COMPLETE', 'FAILED'). All MUSTs preserved; proposal adds non-mandatory UI surface.
- **Frozen-surface note:** No FROZEN surface touched. Proposal is purely additive to dashboard + tools/soak_driver.py. No amendment to ADR-18 required for UI constraints (M1-M9 already satisfied by design). Soak-tiers amendment (Tier 4) is additive to ADR-17; no core-tier logic changes.
- **New-envelope note:** One new internal bus envelope: soak_ready_for_ship_gate (fired by soak harness when polarity audit complete, routed to HITL pending queue). MUST have cassette_record.py + soak_driver.py coverage per NEW BUS ENVELOPE RULE. Envelope is internal-only (tested via existing HITL fixtures + new Tier 4 soak replay test). Cassette schema: {kind: 'soak_polarity_audit', decision_count: int, rejection_count: int, recorded_latency_ms: float, polarity_pass: bool}. Backward compat: v1.2 cassettes (zero soak audit rows) replay unchanged; new LM row reads n=0 (precedent from ADR-17 v1.3 amendment).

## Grounding

- docs/adr/ADR-17-soak-tiers.md:116-184 (Tier 1.5 precedent, cassette compat rule, trigger matrix)
- docs/adr/ADR-18-mvp-surface-freeze.md:65-108 (M1-M9 MUST floor, M2 escalation-only, M4 label+color)
- UI-DESIGN-SPEC.md:65-148 (M1-M19 binding constraints, Frame A/B/C presence, badge semantics)
- CLAUDE.md:31-45 (polarity-flip rule, session-source exception, BRIDGE_SM_SELF_SESSION_ID filter, project_slug durable key)
- tools/soak_driver.py:1-60 (Tier structure, synthetic load mix, _DriverState instrumentation)
- src/stream_manager/message_bus.py:658-732 (governance_decision envelope schema, FROZEN precedent, subscriber pattern)
- dashboard/server.py:1-75 (dashboard architecture, MessageBus + HITL queue singletons, env setup)
