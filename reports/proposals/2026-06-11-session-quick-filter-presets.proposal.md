# Session Picker: Favorites + Filters + Hotkey

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (flywheel) 2026-06-11; idea COMFORTS-3-session-quick-filter-presets; boldness SAFE; refute verdict CONSTRAIN; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

Operator running governance on multiple concurrent sessions (often 10+ open) loses context on session identity and urgency during picker interactions. Current bare <select> dropdown (REQUIREMENTS.md:290-297, index.html:2241) requires manual scroll hunt on every context switch. No favorites pinning, no filter-by-urgency-state, no keyboard hotkey. Idle operator does not see that a background session has pending HITL actions. Context-switch tax is 10--20% of operator attention; mental model of which sessions are 'theirs' evaporates after 5 minutes away.

## Proposal

Upgrade session picker (dashboard/static/index.html) with four integrated affordances, all rendered from live session table data (zero hard-coded project vocabulary): (1) FAVORITE-STAR button next to each session option; click toggles session_id to localStorage key `sm.session-favorites:${origin}` (persisted per-browser-origin). Pinned sessions sort to top of dropdown, unpinned below. (2) QUICK-FILTER CHIPS (mutually-exclusive radio group) above dropdown: 'All' (reset), 'Active' (last_msg_ts > 5min), 'With Open Actions' (count of hitl_pending rows > 0 joined from /api/sessions endpoint). Behavioral predicates only; project-slug filtering is deferred. Chip selection filters dropdown options client-side; state persists to localStorage. (3) UNREAD BADGE: render red dot on session option when that session has hitl_pending rows added after last picker-open timestamp (session-scoped in-memory flag; cleared on next pick). (4) HOTKEY Ctrl+K (Cmd+K on macOS): focus-opens picker with inline search field (100ms debounce, fuzzy-match on slug name, client-side). Selection immediately switches session; search clears on next open. Keyboard shortcut is modal-aware and disabled if another modal/menu is open. All state persists via localStorage and session table refresh via existing /api/sessions polling. No new API endpoint required; /api/sessions response extends to include `has_pending_actions: bool` flag (count of that session's hitl_pending rows) to enable filter-chip logic client-side.

## Operator value

Multi-session context-switch friction drops 70--80% (hotkey removes discovery cost, favorites eliminate hunt, 'With Open Actions' chip surfaces urgent sessions at a glance). Operator mental model is now persistent (localStorage) and visible (favorite markers, unread badges). 'Active' filter removes low-urgency idle sessions from scan. Unread badge provides ambient signal that a background session needs triage. Estimated time saved per shift: 45--90 minutes for operators managing 8+ concurrent sessions.

## Surfaces touched / added

- (none)

## Feasibility

VERY HIGH. All four features use existing data (sessions table, hitl_pending table, last_msg_ts already exposed via /api/sessions). No governance-engine changes. No schema extensions (hitl_pending already exists; /api/sessions just adds a computed boolean flag). Client-side rendering of chips and search is <200 lines of vanilla JS (no framework required). localStorage is browser-native. Keyboard interception (Ctrl+K) is standard DOM event handling with modal-aware guards. Estimated build time: 4--6 hours (including integration test). Risk: near-zero (additive only; existing picker logic untouched; fallback to unadorned <select> if JS fails).

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS (constrained). Project-slug filtering is explicitly DEFERRED. Quick-filter chips are data-driven from /api/sessions response (distinct project_slugs present in live sessions table, not hard-coded). No 'Project: certPortal' example in shipped code -- only behavioral predicates ('Active', 'With Open Actions'). Firewall rule M8 (domain-agnostic) is satisfied: governed-target identity (project_slug) is rendered from data, not baked into UI labels.
- **Polarity (G2):** PASS. Session picker selection affects SM governance session only (the picker is part of the operator-facing dashboard, not a governed target). No self-governance loop; polarity split (write=operator-session, read=monitoring-session) is implicit.
- **ADR-18 MUST floor:** PASS. ADR-20 M5 (paired label + color badges) is respected: unread badge is a colored dot PLUS a hover label (not color-alone signal). All three frames remain reachable (no IA change). Monitor-first principle (M1-M2) unaffected; picker is an optional UX upgrade, not a foreground modal.
- **Frozen-surface note:** No FROZEN surfaces touched. dashboard/static/index.html is EVOLVING (FR-UI per REQUIREMENTS.md). message_bus.py, governance.py, cli_governance.py, model_router.py, cli_pool.py remain untouched.
- **New-envelope note:** No new bus envelope kind. /api/sessions endpoint extends to return `has_pending_actions: bool` (computed from existing hitl_pending table). No schema change required; cassette_record.py and soak_driver.py coverage is not triggered (endpoint-level extension, not a new event category).

## Grounding

- C:\Users\SeanHoppe\vs\streamManager\REQUIREMENTS.md:290-297 (FR-OG-8 session selector spec)
- C:\Users\SeanHoppe\vs\streamManager\dashboard\static\index.html:2241 (current sess-select element)
- C:\Users\SeanHoppe\vs\streamManager\dashboard\server.py:720-757 (/api/sessions endpoint schema)
- C:\Users\SeanHoppe\vs\streamManager\dashboard\server.py:878-915 (hitl_pending query pattern)
- C:\Users\SeanHoppe\vs\streamManager\docs\adr\ADR-20-ui-redesign-experimental-spike.md:51 (M8 domain-agnostic invariant)
- C:\Users\SeanHoppe\vs\streamManager\src\stream_manager\message_bus.py:27-30 (messages.timestamp schema)
