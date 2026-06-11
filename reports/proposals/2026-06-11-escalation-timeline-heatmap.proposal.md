# Escalation Timeline: Glance-readable heatmap of governance feedback density

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (ux) 2026-06-11; idea MONITOR-2; boldness STRETCH; refute verdict SHIP-PROPOSAL; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

Current HITL panel shows pending items only (current moment). No ambient signal of WHEN escalations happened during the session. Operator running a session at 14:00 asks: "did governance escalate a lot at 13:50? or was it steady?" Requires grepping the decision feed manually. A "quiet session" vs a "chaotic session" is invisible until pattern emerges from rereading history.

## Proposal

Render a 140-pixel vertical timeline (Y-axis = wall-clock time across session duration, typically 10--120 min). Each Y-pixel row shows whether an escalation (GUIDE/INTERVENE/BLOCK decision) fired in that 30-second bucket. Color = severity (GUIDE=amber dot, INTERVENE=orange dot, BLOCK=red dot). Stacking: a bucket with 3 BLOCK decisions gets a denser red. Rows with no escalations are transparent. Click any row to filter the Feed view to decisions in that 30-second window. The timeline lives in the Monitor frame header (left margin of the frame, 12px wide). It becomes the 'heatmap' the operator glances at to see if escalations were bursty (cluster of reds) or spread (even dots). Pairs with the Confidence Sparkline (MONITOR-1) to surface 'confidence dropped at 14:05 and escalations spiked at 14:07' in one visual read.

IMPLEMENTATION: (1) New endpoint /api/escalation-timeline?session_id=ID&bucket_ms=30000 (read-only, aggregates decisions by time bucket). (2) New EscalationTimeline.svelte component (12px wide, 140px tall, dot-per-bucket rendering). (3) Feed integration: timeline click filters ReplStream to time window via existing selectedSessionId + time-range support. (4) Schema: zero FROZEN-surface edits, decisions table already has action+timestamp. (5) Bus envelopes: zero new kinds.

## Operator value

Moves from "Was governance noisy?" to "Here's when and where escalations clustered." Supports session health post-mortems ("we had a burst of blocks around minute 8") without opening the feed. Enables early detection of pathological governance feedback loops. Glance-readable heatmap answers "steady or chaotic?" in ~500ms visual parse (laptop-first monitor use case). Pairs with Confidence Sparkline to surface temporal correlation: "confidence dropped at 14:05 and escalations spiked at 14:07."

## Surfaces touched / added

- dashboard/ui-next/src/lib/components/EscalationTimeline.svelte (new: 12px x 140px vertical timeline, renders 30s-bucket dots by severity, tap emits time-window event)
- dashboard/server.py: /api/escalation-timeline?session_id&bucket_ms=30000 (new read-only endpoint, aggregates decisions by time bucket, returns JSON)
- dashboard/ui-next/src/lib/components/ReplStream.svelte (extend: optional time-range parameter when timeline tap event filters Feed)
- dashboard/ui-next/src/lib/components/FrameHeader.svelte (monitor frame: reserve 12px left margin for timeline sidebar)

## Feasibility

FEASIBLE. Implementation is additive-only: (1) new read-only endpoint over indexed decisions(timestamp), similar complexity to /api/decisions; (2) new SVG timeline component, 12px x 140px, one-pixel-per-bucket, no animations; (3) Feed integration reuses existing selectedSessionId store + time-range scoping in ReplStream; (4) zero FROZEN-surface edits; (5) zero new bus envelope kinds; (6) no cassette/soak coverage burden. Zero production risk: purely observational, zero writes, UI-next dashboard only.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS. Zero certPortal coupling. References only existing SM surfaces (decisions table, /api/decisions pattern, dashboard components). No new monitored-project vocabulary.
- **Polarity (G2):** PASS. Explicit self-exclude via SM_OWN_SESSION_ID (same createSelfExcluder predicate as EscalationRail.svelte). Defense-in-depth: server endpoint has zero write path, client-side filter drops SM-own rows before rendering. Loud-fail-safe: empty/missing meta keeps all rows. SM-self session cannot appear in timeline aggregation.
- **ADR-18 MUST floor:** ADR-18 M2/M3/M4/M15/M16/M18 honored: (M2) Not a foreground surface, lives in monitor frame HEADER left margin (12px wide), no layout steal, no motion at rest, only density dots active. (M3) N/A to timeline (binds to tab title only). (M4) Uses BOTH label+color per row; color never sole signal, always accompanied by text label in Feed filter region (Escalations in [timestamp]). (M15) Self-exclude via SM_OWN_SESSION_ID predicate (ReplStream pattern). (M16) Domain-agnostic: aggregates by session_id, never named vocabularies. Tap-to-filter passes session_id+timestamp to Feed (data-sourced labels from row data). (M18) Read-only endpoint, zero writes, aggregates pre-existing decisions table rows. Client-side visualization is render-pass over already-streamed Feed data. No hot-path work, no verdict-path involvement.
- **Frozen-surface note:** ZERO FROZEN-SURFACE EDITS. Changes are purely additive: new dashboard/server.py endpoint (read-only query), new .svelte component in ui-next/src/components/. No modifications to governance.py, message_bus.py, cli_governance.py, cli_pool.py, or ADR-18 FROZEN list. All MUSTs remain inviolable.
- **New-envelope note:** ZERO NEW ENVELOPE KINDS. Timeline consumes pre-existing decisions table (WAL read-only). No feedback_cassette_must_cover_new_envelopes burden. No soak_driver.py or cassette_record.py coverage required. Endpoint pattern mirrors existing /api/decisions query; cassettes already capture this.

## Grounding

- dashboard/server.py:588-616 (/api/decisions endpoint pattern for time-scoped queries)
- dashboard/ui-next/src/lib/components/EscalationRail.svelte:197-206 (self-exclude predicate: createSelfExcluder, defense-in-depth)
- dashboard/ui-next/src/lib/components/ReplStream.svelte:61-85 (session-scoping + visibleRows filtering, time-range param fits architecture)
- src/stream_manager/message_bus.py:32-40 (decisions table: id, action, timestamp already indexed)
- dashboard/ui-next/src/lib/escalation.js:86-100 (GUIDE/INTERVENE/BLOCK severity mapping for dot colors)
- docs/adr/ADR-18-agent-role-binding.proposal.md (FROZEN surfaces, MUSTs M2-M18)
