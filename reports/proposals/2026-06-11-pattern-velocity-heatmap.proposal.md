# Pattern Velocity Heatmap: Ambient Session-Health Signal via L0--L4 Learning Dynamics

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (ux) 2026-06-11; idea MONITOR-4; boldness WILD; refute verdict SHIP-PROPOSAL; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

Current Monitor frame Feed shows pattern L0--L4 layer badge as a static snapshot of today's level, but operator never observes RATE of promotion. A pattern at L2 could have fast-tracked from L0 this morning (engine learning, high confidence trajectory) or stalled at L1 for 30 min (thrashing, low success rate). The velocity -- how fast patterns rise through levels -- is an invisible signal. OBSERVE mode with auto-demotion amplifies the blindness: operator cannot glance and tell if the engine is learning robustly or cycling through degradation loops. A pattern stuck at L1--L2 oscillating between decisions is a governance pathology that only shows up as sustained escalation spike in the Timeline (MONITOR-2), never as an ambient health indicator.

## Proposal

Introduce a 2D heatmap mini-panel (Pattern Velocity Heatmap) integrated into the Monitor Frame as a monitor-first (M1) ambient diagnostic surface. Design: Y-axis = pattern level L0 to L4 (5 rows), X-axis = rolling 30-minute time window (1 pixel = 1 minute, 30-pixel width). Each cell (level, minute) is shaded by COUNT of patterns promoted TO that level in that minute. Color semantic: green cells (L3, L4 lit) = engine learning fast, high-confidence precedent accumulating; amber cells (L1, L2 cells lit repeatedly minute-over-minute) = patterns stuck mid-level, possible thrashing; red cells (L0 cells bright, L3/L4 dark) = engine resetting patterns via demotion, possibly negative feedback loop. Hover any cell to show the pattern hashes promoted in that minute plus their canonical text. Click a cell to filter the Feed to decisions matching those pattern hashes, enabling root-cause pairing with escalation timeline (MONITOR-2): e.g. 'escalations spiked at minute 8 AND heatmap L2 cells lit at minute 8' means 'escalations arrived but pattern precedent was mid-level confidence, next iteration will have L3 depth and escalation load will drop.' Backend: new `GET /api/pattern-velocity?session_id=<id>&window_ms=1800000` endpoint aggregates `patterns.level + patterns.last_seen` by level plus 1-minute time bucket via pure SELECT query. Response envelope: `[{level: 0-4, minute_bucket: 0-29, count: N, hashes: [...], texts: [...]}, ...]`. Polarity-flip constraint: endpoint MUST filter at the SQL WHERE boundary `AND sessions.project_slug NOT IN (BRIDGE_SM_PROJECT_SLUGS)` (same defensive pattern as `/api/sessions` and `/api/patterns/cross_session`) to block self-monitoring. Frontend: new Svelte component `dashboard/ui-next/src/lib/components/PatternVelocityHeatmap.svelte` renders 5x30 grid, cell sizing 16px x 14px, flex layout for responsive fit into the monitor-first context pane. No canvas/canvas2d (accessibility requirement M5 plus hover-target size). Optional enhancement: decision_suggestions.py may weight pattern velocity into confidence scoring (SHOULD, not MUST).

## Operator value

HIGH for monitor-first users running secondary-display governance dashboards. Moves operator cognition from 'what patterns are live?' (current Feed snapshot) to 'is the engine learning or thrashing?' (ambient velocity signal visible in a glance). Detects pathological governance loops (e.g., L1--L2 oscillation, L0 resets without recovery) that manifest only as sustained escalation noise in Timeline; heatmap surfaces them as explicit learning-health indicators. Pairs with Escalation Timeline (MONITOR-2) to enable root-cause debugging: spiked escalations plus correlated heatmap anomaly equals evidence for next iteration refinement. No new computational load on hot paths (query runs ~50ms on typical 30-min window, async endpoint, UI updates on 5s refresh boundary).

## Surfaces touched / added

- dashboard/ui-next/src/lib/components/PatternVelocityHeatmap.svelte (new; Svelte plus Tailwind, 5x30 grid, 60 LOC)
- dashboard/server.py: GET /api/pattern-velocity?session_id&window_ms=1800000 (new endpoint, 40 LOC, SELECT patterns.level, COUNT(*), GROUP BY minute_bucket WHERE sessions.project_slug NOT IN (BRIDGE_SM_PROJECT_SLUGS))
- src/stream_manager/message_bus.py: patterns plus decisions plus messages plus sessions tables (read-only; level plus last_seen plus project_slug columns already present, no schema migration)
- dashboard/ui-next/src/App.svelte or FrameA_Sessions.svelte: integrate PatternVelocityHeatmap component into monitor-frame context pane (minor prop threading)

## Feasibility

FEASIBLE. Message bus schema already carries `patterns.level + patterns.last_seen` (read-only columns, no schema extension needed). SQL query groups-and-counts without new indexes or table mutations. Endpoint wires into existing `dashboard/server.py` FastAPI app (one new route, 25 LOC). Frontend uses native Svelte plus Tailwind (no external heatmap library required; custom 5x30 grid is 60 LOC component). No FROZEN surface modifications (governance.py, message_bus.py schema, cli_governance.py, model_router.py, cli_pool.py remain untouched). Latency budget: query ~50ms for typical 30-min pattern sparse dataset, acceptable for async sideband endpoint. Deployment: adds one route, one Svelte component; zero changes to governance hot path. Testing: unit test for aggregation query, e2e test for endpoint plus UI render plus filter interaction.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS. Proposal touches only dashboard/ui-next (new component), dashboard/server.py (new endpoint), and read-only patterns plus sessions tables. Zero coupling to certPortal. CertPortal is separate repo; no inter-repo schema sync required.
- **Polarity (G2):** PASS IF constraint implemented. Endpoint must apply explicit WHERE filter at SQL boundary: `AND sessions.project_slug NOT IN (BRIDGE_SM_PROJECT_SLUGS)` (same frozenset pattern used by `/api/sessions` at line 735 and `/api/patterns/cross_session` at line 1445). This prevents dashboard monitoring SM-own sessions (feedback_no_self_monitor.md compliance). Default BRIDGE_SM_PROJECT_SLUGS={'streamManager'} (configurable via env, line 295). Filter must be stated IN the proposal code sketch so no ambiguity on HITL gate.
- **ADR-18 MUST floor:** PASS. ADR-18 MUST floor (M1--M9) fully respected: M1 monitor-first (mini-panel integration, not foreground escalation), M2 no auto-escalation (heatmap is ambient signal, click-to-filter only), M5 color plus label plus hover (not color-only; cells carry accessible label on hover plus pattern text), M8 domain-agnostic (L0--L4 canonical governance levels, patterns rendered from data, no hardcoded role/JOB vocabulary), M9 self-exclude inherited (via polarity filter). Latency budget (M6/ADR-5): endpoint ~50ms acceptable for sideband, not on verdict hot path.
- **Frozen-surface note:** No FROZEN surface modifications. Read-only access to message_bus.py patterns plus sessions tables (no schema mutation). dashboard/server.py is EVOLVING per ADR-18 (Phase 6 notes indicate ongoing endpoint expansion), so new route is additive.
- **New-envelope note:** No new bus envelope kind introduced. Endpoint reads only existing patterns plus decisions plus sessions columns. Response envelope ({level, minute_bucket, count, hashes, texts}) is HTTP-only, never written to message_bus WAL. Zero cassette_record.py / soak_driver.py coverage needed (not a governance decision envelope).

## Grounding

- docs/adr/ADR-18-mvp-surface-freeze.md:64 (FROZEN list; dashboard/server.py is EVOLVING)
- dashboard/server.py:295 (BRIDGE_SM_PROJECT_SLUGS pattern; polarity filter example)
- dashboard/server.py:1445 (cross_session endpoint query pattern; shows project_slug polarity defense)
- src/stream_manager/message_bus.py:44-50 (patterns table schema; level plus last_seen columns available)
- dashboard/ui-next/src/lib/components/Frame.svelte:1-30 (M1 monitor-first frame structure; shows ambient-signal integration pattern)
- docs/KingModePrompt.txt:1-40 (avant-garde UI design directive; bespoke, asymmetric, not template-derived)
