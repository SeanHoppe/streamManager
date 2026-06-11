# Spatial Session Overview Sidebar (Right-rail coexist mode)

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (ux) 2026-06-11; idea WILDCARD-3; boldness STRETCH; refute verdict CONSTRAIN; effort L.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

The 3-frame layout (REPL / Sub-Agents / Jobs) is linear and time-sequential. When the operator has 3+ concurrent sessions, they must switch between session-picker selects to compare activity across sessions. There is no glanceable spatial overview showing 'which sessions are currently active? Which one is hot? Which are blocked waiting for HITL?' The operator builds this mental model piecemeal from tab-switches, creating a bottleneck for high-volume or multi-operator scenarios.

## Proposal

Ship a **floating right-rail sidebar** (mutually coexistent with Frames A/B/C, never replacing them per ADR-18 M1 MUST) that renders a **force-directed D3 graph visualization** of cross-session governance state. Each session appears as a **card-node** in 2D space showing: session ID, project slug, last-activity timestamp, current mode (OBSERVE/SUGGEST/GUIDE/INTERVENE/BLOCK) as a color ring, and a **mini-sparkline** of decision latency trend over the last 10 decisions. Edges between nodes show **shared pattern flows** (if L3/L4 patterns learned in session-A appear in session-B's recent decisions, they are connected via a labeled edge showing pattern count). On hover, a tooltip displays open-HITL count, current agent slug, and a 1-click focus button that switches the main frame picker to that session. The sidebar is **zoomable** (scroll wheel) and **pannable** (drag background). Static rules fires and negative regressions render as **pulsing alerts on the node**. The sidebar toggle lives in the header next to the session picker and persists its collapsed/expanded state to localStorage. On narrow viewports, the sidebar gracefully collapses to a compact 1D horizontal timeline strip (same data, different projection). Frames A/B/C remain visible and independently scrollable at all times; the sidebar is a **reading-only complement**, never an alternative mode.

## Operator value

Gives operators a glanceable multi-session spatial overview without context-switching to a separate view mode or tab navigation. Makes pattern-flow visibility explicit ('these 5 sessions converged on the same policy'). Enables rapid detection of 'which session is on fire right now' via pulsing alerts. Builds spatial intuition about governance dynamics across sessions in a single visual frame that coexists with the familiar sequential 3-frame detail pane.

## Surfaces touched / added

- dashboard/ui-next/src/lib/components/SpatialSidebar.svelte (new; right-rail panel, toggleable, responsive collapse to 1D strip on mobile)
- dashboard/ui-next/src/lib/components/SessionNode.svelte (new; card node rendered inside D3 force layout, shows session ID, mode color ring, mini-sparkline, pulsing alerts)
- dashboard/ui-next/src/lib/components/AppShell.svelte (modify; add sidebar mount below three frames, ensure frames stay M1-present, wire collapsed-state toggle from header)
- dashboard/ui-next/src/lib/stores/sidebarState.ts (new; localStorage-backed collapsed/expanded + zoom/pan position per session)
- dashboard/ui-next/src/lib/stores/crossSessionPatterns.ts (new; subscribes to /api/sessions/pattern-edges polling, reactive edges list)
- dashboard/server.py (add /api/sessions/pattern-edges GET endpoint; returns {edges: [{from_session_id, to_session_id, pattern_count, pattern_hashes}], nodes: sessions list with latency sparkline data})
- src/stream_manager/decision_graph.py (add public method cross_session_pattern_edges(limit: int, min_pattern_count: int = 1) -> list[dict]; queries patterns + decisions to find shared L3/L4 hashes across session boundaries)
- docs/adr/ADR-20-ui-redesign-experimental-spike.md (add rationale section: sidebar as Spatial Awareness Augmentation, EXPERIMENTAL ui-next surface under the Spatial Overview sub-track)

## Feasibility

Medium-to-Hard. Backend adds cross-session pattern edge computation (new /api/sessions/pattern-edges GET endpoint querying patterns + decisions tables to find shared pattern hashes across session boundaries; ~40-60 LOC in server.py). Frontend ships D3 force-directed layout (~60KB minified), a new SvelteSpatialSidebar.svelte component (~300 LOC), SessionNode.svelte card sub-component (~150 LOC), and latency-sparkline rendering (~100 LOC). Telemetry adds lightweight latency tracking in governance.py's decision loop (one timestamp capture, already available via _last_phase_timings_ms). SSE updates or periodic re-fetch hook to refresh cross-session state when new decisions/patterns arrive. All feasible; D3 force-directed integration with Svelte is well-trodden (e.g. svelte-d3, nivo wrappers exist); latency tracking is non-breaking additive instrumentation.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS. All components render data-driven fields from /api/sessions and /api/sessions/pattern-edges. No certPortal vocabulary, monitored-project role bindings, or domain-specific job-IDs baked into the sidebar logic. Session node card fields are domain-agnostic (session_id, project_slug, governance_mode, pattern_hash list). No coupling beyond existing learn-mode source registry or project_context.
- **Polarity (G2):** PASS. The sidebar consumes the existing /api/sessions endpoint which already filters out SM-self per the SM_OWN_SESSION_ID env guard. No new self-monitoring sweep introduced; the canvas does not add any 'cleanup stale sessions' logic. It reads existing session state only.
- **ADR-18 MUST floor:** PASS (constraint remedied). ADR-18 M1 requires 'Frame A/B/C all present at page load, each independently scrollable.' Original toggle design violated M1 by replacing frames on mode switch. CONSTRAIN verdict reshaped this to a sidebar panel: Frames A/B/C remain visible, independently scrollable, and escalation-capable at all times. The spatial sidebar appears as a **collapsible/expanding right-rail overlay or fixed-width panel**, coexisting with the still-water frame scaffold, never occluding or hiding frames. M1 presence + M3 tab-title count + escalation foreground behavior unchanged. Sidebar is a pure read-side **augmentation**.
- **Frozen-surface note:** No FROZEN surfaces (governance.py, message_bus.py, cli_governance.py, model_router.py, cli_pool.py) are touched. The decision latency sparkline reads from _last_phase_timings_ms (FROZEN dict per ADR-18 L63, metadata-only extensions allowed). New cross-session pattern edge query in decision_graph.py (currently EVOLVING per L68) requires a public method `cross_session_pattern_edges(limit: int = 50) -> list[dict]` returning {from_session_id, to_session_id, shared_pattern_hashes: []}. This is EVOLVING surface, so the method addition is allowed. No FROZEN amendment required.
- **New-envelope note:** No new bus envelope kind introduced. Cross-session data flows via HTTP GET endpoints only (/api/sessions, existing; /api/sessions/pattern-edges, new). If telemetry enrichment later pipes latency sparkline data through a new bus envelope (e.g. governance_session_telemetry), the new envelope MUST have cassette_record.py + soak_driver.py coverage in the same PR per ADR-18 NEW BUS ENVELOPE RULE. For v1, HTTP polling / SSE refresh is sufficient; no envelope required.

## Grounding

- C:\Users\SeanHoppe\vs\streamManager\docs\adr\ADR-18-mvp-surface-freeze.md L59-65 (Frame presence MUST M1, arrangement free)
- C:\Users\SeanHoppe\vs\streamManager\dashboard\ui-next\src\lib\components\AppShell.svelte L1-30 (scaffold owns M1 presence guarantee, three frames always rendered)
- C:\Users\SeanHoppe\vs\streamManager\dashboard\server.py L720-757 (/api/sessions endpoint, existing schema with hitl_mode)
- C:\Users\SeanHoppe\vs\streamManager\src\stream_manager\decision_graph.py L59-110 (Pattern + DecisionGraph structure; cross-session query feasible via patterns table joins)
- C:\Users\SeanHoppe\vs\streamManager\dashboard\server.py L1429 (existing /api/patterns/cross_session as precedent for cross-session queries)
