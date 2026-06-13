# Session-per-Agent Pinning with Visual Affordance (Frame B Swim-Lane)

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (ux) 2026-06-11; idea COMFORTS-3; boldness SAFE; refute verdict SHIP-PROPOSAL; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

Sub-Agents frame B defaults to "most-recently-active-first" ordering (FR-UI-1 spec, active_window default 10s). When operator switches focus or pauses for a call, the active-agent set shuffles; watched agents fall below the fold. No affordance exists to say "always keep Developer pinned at top" or "keep Reviewer visible during inactivity," causing operator to lose track of key agents during multi-agent workflows on resource-constrained displays (13-inch laptop).

## Proposal

Add session-per-agent pinning to frame B swim-lane with persistent storage and visual affordance. Surfaces: (1) New WAL table `pinned_agents(session_id TEXT, agent_id TEXT, pinned_at REAL, PRIMARY KEY(session_id, agent_id))` in `message_bus.py` schema. (2) REST endpoints in `dashboard/server.py`: POST `/api/agents/{agent_id}/pin` to toggle pin state (idempotent; stores or deletes row), GET `/api/agents/pinned?session_id=X` to fetch list of pinned agent IDs for rendering order. (3) UI changes in `dashboard/static/index.html` frame B swim-lane: add unfilled pin icon (4px next to agent name); clicking toggles filled (amber `#f59e0b`) state and POSTs toggle. On render, sort agents: (1) pinned (earliest pin_at first), (2) active (last_seen within window), (3) inactive. Pin state persists across page reloads (stored in WAL, not localStorage). Optional: emit `agent_pin_toggled` audit event (if this is a live SSE envelope, same-PR cassette + soak coverage required per ADR-18 Amendment 2026-05-12). Bonus affordance: render pinned-count badge (e.g., " 2") in frame B header.

## Operator value

Operators stop losing track of key agents (main Developer, Reviewer) when they pause or go silent for 15+ minutes. Pinning is gesture-driven (visible icon, one click) and immediate. Reduces cognitive load in multi-agent workflows; eliminates manual scroll-to-find during compressed-screen sessions. The pin state is visible at a glance (filled amber icon), persists across page reloads, and is per-session (not global) so switching between concurrent governance sessions does not interfere. Direct measure: reduces search latency in Frame B swim-lane from ~3s (manual scroll) to ~100ms (gaze anchor).

## Surfaces touched / added

- src/stream_manager/message_bus.py (new pinned_agents table: session_id TEXT NOT NULL, agent_id TEXT NOT NULL, pinned_at REAL NOT NULL, PRIMARY KEY(session_id, agent_id); new method toggle_pin(session_id, agent_id))
- dashboard/server.py (new POST /api/agents/{agent_id}/pin endpoint, GET /api/agents/pinned?session_id endpoint; both read/write pinned_agents table)
- dashboard/static/index.html (add pin button/icon to each agent row in swim-lane frame B; click handler POSTs toggle request, re-renders sort order; optional pinned-count badge in frame B header)

## Feasibility

All surfaces are additive. No FROZEN surface modifications (message_bus.py and server.py are EVOLVING per ADR-18; dashboard/static/index.html is actively touched per cycle). New table is append-only + delete-on-unpin (no schema breaking changes). REST endpoints are straightforward CRUD. UI button is a simple click handler + re-sort. No new async patterns, no new encryption, no changes to the SSE contract. Estimated effort: ~1-2 days (table + endpoints + UI + manual test). Straightforward implementation, no architectural surprises.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS. New table (pinned_agents) and endpoints (/api/agents/{agent_id}/pin, GET /api/agents/pinned) contain zero monitored-project vocabulary. agent_id is opaque UUID (already exists in agents table), session_id is generic reference. No learn-mode source registry changes, no project_context coupling, no certPortal-new-dependency. Firewall constraint respected.
- **Polarity (G2):** PASS. Proposal contains no cleanup/sweep logic that could self-monitor SM's own session. Any future stale-pinned-agent purge MUST exclude SM-self per session filtering (default-exclude self). Polarity-flip constraint satisfied.
- **ADR-18 MUST floor:** PASS on all 9 governance MUSTs and 5 binding UI MUSTs (ADR-20 M1-M19): M1 (3-frame presence unchanged), M2 (pinning does NOT auto-foreground; re-sorts to position 1 only), M3 (frame/tab action counts unchanged), M4 (filled amber pin icon + agent name text + badge count = triple signal; color alone insufficient), M5 (paired label+color honored), M6 (three-domain visibility preserved), M7 (non-goals intact), M8 (domain-agnostic: checked), M9 (polarity: checked). Escalation-only foreground rule preserved; no unsolicited foreground on pin toggle. Three-frame presence unaffected.
- **Frozen-surface note:** message_bus.py and governance.py are classified FROZEN in ADR-18. This proposal touches message_bus.py to add pinned_agents table (additive table, no modification to existing schemas per ADR-18 Rule 1 metadata-only-extension guidance). governance.py is NOT touched. dashboard/server.py and dashboard/static/index.html are EVOLVING per INTENT.md Hot zones (actively touched per cycle). No frozen surface violation. No ADR amendment required.
- **New-envelope note:** Proposal mentions optional 'emit agent_pin_toggled bus event for audit' in the UI section. CRITICAL CLARIFICATION REQUIRED: Is agent_pin_toggled a new live SSE envelope kind (routed via bus.write_envelope() and subscribed by dashboard /events channel) or audit-trail-only? If new envelope: Shipping requires same-PR cassette_record.py + soak_driver.py coverage per feedback_cassette_must_cover_new_envelopes rule (ADR-18 Amendments + INTENT.md Hot zones tooling note). If audit-trail-only (no live SSE emission): No cassette requirement. Proposer MUST clarify bus semantics in updated proposal text.

## Grounding

- INTENT.md:77-80 (three-domain monitor-first layout; Frame B Sub-Agents swim-lane)
- REQUIREMENTS.md:378-386 (FR-UI-1 Frame B spec: active-agents pinned to top, swimlane ordering, persistence)
- UI-DESIGN-SPEC.md:70-74 (M1 three-frame presence; M2 escalation-only foreground)
- UI-DESIGN-SPEC.md:82-90 (M4-M5 paired label+color badges; M5 HITL ON/OFF semantics -- pinning orthogonal)
- ADR-18-mvp-surface-freeze.md:60-73 (surface classification FROZEN/EVOLVING/EXPERIMENTAL; pinned_agents is additive to EVOLVING message_bus.py)
- ADR-20-ui-redesign-experimental-spike.md:36-62 (9 governance-level MUST invariants M1-M9; pin affordance does not violate any)
- dashboard/server.py:1-40,688-717 (existing /api/agents endpoint pattern; lifecycle bridge precedent for server extensions)
- src/stream_manager/message_bus.py:60-70 (agents table schema; pinned_agents parallel structure)
