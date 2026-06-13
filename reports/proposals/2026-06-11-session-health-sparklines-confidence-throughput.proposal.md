# Render per-session health sparklines (confidence + throughput) in SessionLane headers

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (flywheel) 2026-06-11; idea MONITOR-1; boldness STRETCH; refute verdict SHIP-PROPOSAL; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

Operator scanning 3-5 concurrent sessions cannot glance-read which ones are healthy vs. degraded. Frame headers show raw decision counts; they don't signal pattern (confidence climbing vs. collapsing; throughput steady vs. stuck). A session with low confidence or stalled throughput disappears visually in favor of noise, forcing the operator to context-switch and read the full decision feed to spot confidence regression or escalation pile-up.

## Proposal

Render a compact 60-second sparkline (8-10 data points) above each non-self SessionLane in the session rail, showing two interleaved traces: (a) rolling 10-decision mean confidence (0.0-1.0, Y-axis), and (b) throughput normalized (messages/second, 0-1.0, Y-axis). Sparkline colors match MUST badge semantics: slate for OBSERVING (healthy, confident), amber for ACTION REQUIRED (confidence drifting, escalations pending), red for BLOCKED (confidence floor breached). The sparkline updates every 2 seconds via SSE using a new session_sparkline_update envelope kind (emitted by message_bus on each governance_decision). Hovering the sparkline opens a mini-drawer with the last 100-decision time-series (confidence + throughput as interleaved line traces, trigger-reason enum breakdown as a stacked bar chart). The sparkline is structurally domain-agnostic (session_id + numeric metrics only; no project vocab baked in). M3 compliance: each sparkline is paired with a LIVE tally badge (per-session ACTION REQUIRED count) in the SessionLane header. M2: sparkline color is supplementary; the paired label badge is the semantic signal. M1: sparkline embeds in the existing SessionLane header (3-frame presence preserved). M18: sparkline data rides SSE post-hoc; it is not on the verdict hot path. The proposed surfaces are: (1) SessionLane header component modification to embed sparkline above the action tally; (2) new GET /api/sessions/{session_id}/sparkline-data endpoint returning {timestamp, confidence, throughput, trigger_reason}[] for UI drawer population; (3) new session_sparkline_update envelope kind in message_bus emitted on each decision; (4) Svelte SessionSparkline.svelte component (new; SVG-based, M17 a11y title/desc elements, sufficient contrast). No modifications to FROZEN surfaces (governance.py, message_bus.py as envelope writer, cli_governance.py, model_router.py, cli_pool.py). The SSE endpoint is EVOLVING and absorbs the new envelope kind as a broadcast. Cassette_record.py and soak_driver.py MUST be updated in the same PR to cover the session_sparkline_update envelope shape (feedback_cassette_must_cover_new_envelopes rule).

## Operator value

Reduces context-switch time when juggling multiple sessions; enables instant visual triage (glance time ~200ms). Operator spots confidence degradation or stuck throughput before escalations pile up. HIGH value for laptop monitor-first workflow (ADR-20 / INTENT.md "glance-readability across concurrent sessions").

## Surfaces touched / added

- dashboard/ui-next/src/lib/components/SessionLane.svelte (modify to embed sparkline above action-count badge)
- dashboard/ui-next/src/lib/components/SessionSparkline.svelte (new component; SVG sparkline with confidence+throughput traces, hover drawer)
- dashboard/ui-next/src/lib/stores/session.js (add rolling-window sparkline buffers per session_id, keyed to SSE events)
- dashboard/server.py (new GET /api/sessions/{session_id}/sparkline-data endpoint; return last 100 decisions' {timestamp, confidence, throughput, trigger_reason}[])
- src/stream_manager/message_bus.py (add session_sparkline_update envelope emission in record_decision; FROZEN envelope contract, additive-only)
- tools/cassette_record.py (synthesize + record session_sparkline_update envelopes during soak; serialize to fixture JSONL)
- tools/soak_driver.py (load + replay session_sparkline_update envelopes in verdict loop; F5 cluster pattern)
- tests/fixtures/soak_cassette_<YYYY-MM-DD>.jsonl (updated fixture with new envelope kind)

## Feasibility

FEASIBLE. ThroughputLine.svelte demonstrates SVG sparkline rendering with rolling buffers (reusable pattern). governance_decision envelope (FROZEN per message_bus.py:703-724, ADR-18 amendment 2026-05-12) carries confidence + latency_ms. /events SSE endpoint (server.py:2714+) supports per-session filtering. Rolling per-session buffers are straightforward Svelte stores. M4+M17 compliance is enforced structurally via paired label+sparkline markup + SVG title/desc. Estimated scope: 40 LOC (cassette), 30 LOC (soak), 50 LOC (API endpoint), 200 LOC (Svelte component + store integration).

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS -- No certPortal coupling or monitored-project vocabulary baked into the data model or UI component. Sparkline receives session_id + numeric metrics (confidence, throughput) only; no project_slug or role names rendered. SM_OWN_SESSION_ID already excluded server-side by parent session filter logic.
- **Polarity (G2):** PASS -- Sparkline rendered per-session in SessionLane, which self-excludes SM own session structurally. setSessions() filters ownSessionId and OWN_PROJECT_SLUGS in session.js:83-112. SSE endpoint receives pre-filtered session_id from parent (SessionRail already enforces exclusion per ADR-18 G2); sparkline endpoint is read-only and carries the same session_id scoping. No aggregates that could include SM-self.
- **ADR-18 MUST floor:** COMPLIES with M1-M19 (ADR-20 / UI-DESIGN-SPEC.md). M1: sparkline embeds in existing SessionLane header (3-frame presence preserved, no layout disruption). M2: escalation-only foreground (sparkline does not auto-pop or toast; color is supplementary per M4). M3: sparkline pairs with per-session ACTION REQUIRED count badge in header. M4: paired label (numeric badge with 'ACTION' or 'OBSERVING' text) + color sparkline, never color alone. M5+M6: HITL semantics unchanged; sparkline is observational only. M15: domain-agnostic (no project vocab). M17: a11y enforced via SVG title/desc + sufficient contrast (no color-alone signal). M18: latency budget respected (async SSE, post-hoc observability, not on verdict hot path). M19: non-goals hold (no IDE/multiplexer/multi-tenant).
- **Frozen-surface note:** No modifications to FROZEN surfaces. governance_decision envelope (FROZEN per message_bus.py:703-724, ADR-18 amendment 2026-05-12) already carries confidence field -- no schema mutation. SSE endpoint (server.py) is EVOLVING and absorbs the new session_sparkline_update envelope kind as a broadcast. No ADR amendment required for the envelope itself; the NEW BUS ENVELOPE RULE (below) governs cassette coverage instead.
- **New-envelope note:** CRITICAL -- NEW BUS ENVELOPE RULE applies. Proposal introduces session_sparkline_update envelope kind (emitted by message_bus.subscribe_decision_event on each governance_decision). Shipping REQUIRES same-PR cassette_record.py + soak_driver.py coverage: (1) cassette_record.py must synthesize session_sparkline_update envelopes in the soak run and serialize them to the fixture JSONL, (2) soak_driver.py must load + replay the envelope kind in _load_cassette + verdict-replay loop (F5 cluster pattern). The envelope shape is {kind: session_sparkline_update, session_id: str, timestamp: float, mean_confidence: float, throughput_msgs_sec: float, trigger_reason_enum: str}. See feedback_cassette_must_cover_new_envelopes.md (implied; not yet merged but exemplified in cassette_record.py:283-354 audit.probe pattern).

## Grounding

- C:/Users/SeanHoppe/vs/streamManager/dashboard/ui-next/src/lib/components/ThroughputLine.svelte:1-100 (sparkline pattern, rolling buffers)
- C:/Users/SeanHoppe/vs/streamManager/dashboard/ui-next/src/lib/components/SessionLane.svelte:1-50 (target component)
- C:/Users/SeanHoppe/vs/streamManager/src/stream_manager/message_bus.py:703-724 (governance_decision FROZEN envelope)
- C:/Users/SeanHoppe/vs/streamManager/dashboard/server.py:2714-2813 (SSE /events endpoint, per-session filtering)
- C:/Users/SeanHoppe/vs/streamManager/dashboard/ui-next/src/lib/stores/session.js:83-112 (polarity enforcement)
- C:/Users/SeanHoppe/vs/streamManager/UI-DESIGN-SPEC.md:65-150 (M1-M19 MUST floor)
- C:/Users/SeanHoppe/vs/streamManager/docs/adr/ADR-20-ui-redesign-experimental-spike.md:1-100 (authorization + EXPERIMENTAL classification)
- C:/Users/SeanHoppe/vs/streamManager/docs/adr/ADR-18-mvp-surface-freeze.md:40-90 (FROZEN classification, additive-only covenant)
