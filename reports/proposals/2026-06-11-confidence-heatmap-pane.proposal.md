# Add Confidence Heat Map grid pane to Frame B (role x time-bucket trend spotting)

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (flywheel) 2026-06-11; idea MONITOR-4; boldness STRETCH; refute verdict CONSTRAIN; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

Governance operator lacks visual pattern-recognition surface for agent-role confidence trends. Today discovery requires manual row-by-row feed scanning or export to external tools (notebook). Latent patterns (e.g., 'code reviewers drifted cautious', 'frontend architect confidence collapsed in last 15 min') are invisible without computational aid.

## Proposal

Add Frame B optional pane toggle rendering a 2D grid: Y-axis = agent roles (sorted by current mean confidence DESC); X-axis = 12 time buckets (5-min windows, rolling 60-min window). Each cell displays {count, mean_confidence, color-coded by confidence band (green >=0.75, yellow 0.60-0.75, orange 0.45-0.60, red <0.45)}. Hover reveals tooltip {role}: {N} decisions in {window}, mean {confidence}%. Click cell opens mini-tray listing the 5-10 decisions comprising that cell. Heat map updates live as new decisions arrive for the current 5-min bucket (no network fetch, coalesce burst updates 1/500ms per role+bucket). On time-bucket roll (every 5 min), oldest column slides left; new empty column appears on right. Surfaces: (1) ConfidenceHeatMap.svelte new component (grid + cell color logic + tooltip + mini-tray); (2) GET /api/heatmap?session_id&minutes=60 endpoint (backend aggregates decisions by agent_profile.role + 5-min bucket, returns {role, bucket_5min_idx, count, mean_confidence, action_breakdown:{ALLOW,GUIDE,SUGGEST,INTERVENE,BLOCK}:N}); (3) message_bus.py new SSE envelope kind 'decision_heatmap_cell_update' emitted whenever a decision lands (event-driven aggregation feeds live pane). Implementation complies with CONSTRAINT-1 (G2 polarity: /api/heatmap filters out SM_OWN_SESSION_ID server-side in docstring), CONSTRAINT-2 (cassette_record.py + soak_driver.py coverage for new envelope schema), CONSTRAINT-3 (M18 latency: coalesce bursts to 1/500ms per cell).

## Operator value

Spot confidence trends at a glance without manual row scan or export. Enables data-driven governance tuning: 'which role is most volatile?', 'did mode-override improve agent stability?', 'which role-time window needs HITL?'. Observation surface (not control); pairs with HITL suggest to close decision loop.

## Surfaces touched / added

- dashboard/ui-next/src/lib/components/ConfidenceHeatMap.svelte (NEW: renders Y=role x X=5min-bucket grid; color-coded cells; hover tooltip; click mini-tray showing 5-10 decisions in cell)
- dashboard/server.py (NEW: GET /api/heatmap?session_id&minutes=60 endpoint; SQL GROUP BY agent.profile_slug, time_bucket; filters SM_OWN_SESSION_ID server-side per CONSTRAINT-1 docstring)
- src/stream_manager/message_bus.py (NEW: emit 'decision_heatmap_cell_update' envelope on every decision with {role, bucket_idx, count, mean_confidence, action_breakdown} payload; optional SSE subscriber)
- src/stream_manager/envelope_kinds.py (ADD to ENVELOPE_KINDS: 'decision_heatmap_cell_update')

## Feasibility

HIGH. All surfaces are additive (new component, new endpoint, new envelope kind). No FROZEN file edits (governance.py, message_bus.py schema tables, model_router.py remain untouched). Grid rendering is straightforward Svelte (standard table-like layout, color swatch, hover/click state). Backend aggregation is a simple SQL GROUP BY (role, bucket_idx) or in-memory accumulation via envelope stream. Envelope capture in cassette_record.py is 20-line boilerplate (mirror existing audit.probe pattern).

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS -- no certPortal vocab baked in, no monitored-project role names (uses data.agent_profile.role from /api/agents).
- **Polarity (G2):** PASS with CONSTRAINT-1 binding -- /api/heatmap endpoint MUST include explicit docstring clause: 'Rows whose session_id matches SM_OWN_SESSION_ID are filtered server-side (no-self-monitor enforcement per G2).' Mirror existing /api/events + /api/agents no-self-monitor pattern (line 2826, server.py).
- **ADR-18 MUST floor:** BENDS-SHOULD (M18 acceptable) -- live-update rendering on the pane is observational use. To keep latency clean, cap cell-update frequency to 1 coalesce per 500ms per role+bucket pair (document in ConfidenceHeatMap.svelte comment). M13/M16 clean (no inter-agent blocking shown; no domain vocab rendered -- all identities from /api/agents role field). M1/M2/M3/M4 not affected (pane is optional toggle inside existing Frame B, no new escalation logic, paired label+color badges only).
- **Frozen-surface note:** No amendments required. All FROZEN surfaces untouched (governance.py, message_bus.py, model_router.py, cli_governance.py remain accept-only-bugfix). Additive-safe: new optional column in decisions UI, new HTTP endpoint, new bus envelope kind.
- **New-envelope note:** NEW ENVELOPE 'decision_heatmap_cell_update' REQUIRES cassette_record.py + soak_driver.py coverage per NEW BUS ENVELOPE RULE. PR shipping this proposal MUST land: (1) cassette_record.py: add 20-30 line helper _record_heatmap_envelopes(bus, session_id, start_idx) emitting decision_heatmap_cell_update envelope(s) with schema {role:str, bucket_idx:int, count:int, mean_confidence:float, action_breakdown:{ALLOW:int,GUIDE:int,SUGGEST:int,INTERVENE:int,BLOCK:int}}; (2) tests/test_envelope_coverage.py assertion that 'decision_heatmap_cell_update' is in cassette recording. No cassette case = cassette-ci guard blocks merge.

## Grounding

- src/stream_manager/message_bus.py:32-70 (decisions table schema, agents table schema, agent.profile_slug field)
- dashboard/server.py:2725-2850 (G2 polarity pattern: SM_OWN_SESSION_ID filtering in /api/events + /api/agents)
- dashboard/ui-next/src/lib/components/FrameB_SubAgents.svelte:1-50 (Frame B contract M13/M16: no domain vocab, no blocking ui)
- src/stream_manager/envelope_kinds.py:1-30 (envelope registry + cassette coverage requirement)
- tools/cassette_record.py:283-360 (_record_ppp_envelopes pattern for envelope emit + HMAC signing)
- dashboard/ui-next/src/lib/components/Frame.svelte:1-80 (M1/M2/M3 frame isolation + escalation gating)
- docs/adr/ADR-18-mvp-surface-freeze.md:39-145 (FROZEN list, Rule 1 additive-safe scope, Rule 3 LOC budget)
