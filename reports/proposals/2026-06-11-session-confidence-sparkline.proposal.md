# Render per-session confidence trend sparklines in SessionPicker with paired text labels

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (ux) 2026-06-11; idea MONITOR-1; boldness STRETCH; refute verdict CONSTRAIN; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

Operator glancing at the dashboard sees only the current decision; no ambient signal reveals whether a session's confidence has been climbing (healthy trend) or collapsing (regression into low-confidence limbo). Multi-session managers must read the full decision feed to spot that one session has drifted while others remain crisp--a task that takes minutes of scrolling and pattern-matching, not the 200ms glance-signal the product's calm-tech philosophy demands.

## Proposal

Render a 64-pixel horizontal confidence sparkline (rolling 100-decision window) in the SessionPicker's optgroup, wired to governance_decision events via the existing /events SSE stream (?session_id filtering). Each pixel represents one decision's confidence (Y-axis: 0--1.0). The sparkline color shifts: green (avg confidence >=0.75), amber (0.55--0.75), red (<0.55). Pair the sparkline with a mandatory TEXT LABEL ("Confidence trend" or "Health") rendered adjacent in the option row (M5 compliance: label + color together, never color alone). Overlay a faint dashed line at each session's confidence_floor setting (from FR-UI-9) so the operator sees at a glance if decisions are skirting the HITL trigger. The sparkline lives in the SessionPicker's optgroup label area (visible when the picker dropdown is open) and optionally in a pinned session-list widget in the header (if placement is elevated to HeaderBar, visibility and operator value rise to HIGH; confirm placement in wire-up). No new SSE envelope is minted; confidence already rides the FROZEN governance_decision envelope. No per-session fetch; data rides the existing SSE contract. The confidence window is per-session (rolling 100 decisions per session_id, separate buffers), not global-aggregate, so the operator can spot local drift without needing to read the global trend.

## Operator value

Operator can manage 10 concurrent sessions without opening each one, spot which session is losing confidence in 200ms, and land on it instantly. Confidence drift detection moves from 'reread the feed' to 'glance at the header'. Value is MEDIUM in dropdown-only placement (visible only when picker is open); value rises to HIGH if elevated to persistent HeaderBar widget.

## Surfaces touched / added

- dashboard/ui-next/src/lib/components/SessionSparkline.svelte (new component)
- dashboard/ui-next/src/lib/components/SessionPicker.svelte (modify optgroup to include sparkline + label)
- dashboard/ui-next/src/lib/stores/session.js (add rolling 100-decision confidence buffer per session_id, keyed to SSE event stream)
- dashboard/ui-next/src/lib/api.js (no new endpoint; confidence rides existing /events SSE)

## Feasibility

FEASIBLE. ThroughputLine.svelte demonstrates SVG sparkline rendering; pattern is directly reusable. governance_decision envelope (FROZEN per message_bus.py:704-724) carries confidence as float. /events SSE endpoint (server.py:2714+) supports per-session filtering. Rolling per-session buffers are straightforward Svelte stores. M5 compliance is enforced structurally via paired label+sparkline markup. M17 accessibility requires SVG title/desc elements and sufficient contrast on dashed line; native select handles keyboard.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS. No new certPortal coupling. SessionPicker and store already enforce domain-agnostic rendering from data (project_slug, id only). SM_OWN_SESSION_ID excluded server-side.
- **Polarity (G2):** PASS. Sparkline rendered per-session in optgroup, which self-excludes SM own session. setSessions() filters ownSessionId and OWN_PROJECT_SLUGS structurally. No aggregates that could include SM-self.
- **ADR-18 MUST floor:** COMPLIES with M5 (paired label+color, never color-alone). Mandatory text label is adjacent to sparkline in option row. Sparkline color is supplementary; label carries semantic meaning. Structure enforced: [text label] + [SVG sparkline] side-by-side.
- **Frozen-surface note:** governance_decision envelope (FROZEN per message_bus.py:704-724, ADR-18:286-314) already carries confidence field. No envelope schema mutation. SSE endpoint is EVOLVING. No ADR amendment required.
- **New-envelope note:** No new envelope kind. Sparkline rides existing FROZEN governance_decision envelope. No cassette_record.py or soak_driver.py coverage needed.

## Grounding

- C:/Users/SeanHoppe/vs/streamManager/dashboard/ui-next/src/lib/components/ThroughputLine.svelte:1-245 (sparkline pattern)
- C:/Users/SeanHoppe/vs/streamManager/dashboard/ui-next/src/lib/components/SessionPicker.svelte:1-190 (target)
- C:/Users/SeanHoppe/vs/streamManager/src/stream_manager/message_bus.py:704-724 (governance_decision FROZEN)
- C:/Users/SeanHoppe/vs/streamManager/dashboard/server.py:2714-2813 (SSE /events, per-session filtering)
- C:/Users/SeanHoppe/vs/streamManager/dashboard/ui-next/src/lib/stores/session.js:83-112 (polarity enforcement)
- C:/Users/SeanHoppe/vs/streamManager/UI-DESIGN-SPEC.md:84-87 (M4: paired label+color mandate)
- C:/Users/SeanHoppe/vs/streamManager/docs/adr/ADR-20-ui-redesign-experimental-spike.md:33-60 (MUST-floor)
