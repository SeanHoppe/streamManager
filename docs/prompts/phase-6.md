# Phase 6 — Dashboard Completeness (Ship Gate)

**Sequence:** Last. Requires all prior phases complete.
**Estimated time:** 1 session.
**FR refs:** Integrates FR-AR-6/7, FR-HITL, §5.6, FR-OG-7 into unified UI.

**Dependency:** All phases 0–5 must be complete. This phase touches only
`dashboard/server.py` and `dashboard/static/index.html`. No changes to
`src/stream_manager/*.py`.

---

## Context

After Phases 1–5, the dashboard has accumulated:
- Decisions table (shipped)
- Session stats (shipped)
- Agent column + badge (Phase 1)
- HITL Queue panel (Phase 2/3)
- Annotate affordance (Phase 3)
- Settings panel (Phase 3)
- Layer column (Phase 4)
- Ring status panel (Phase 5)

What's missing for ship readiness:
1. Per-agent governance mode override (click agent → override for session)
2. JSONL export of decisions (soak analysis + cc-canary input)
3. Bus event log panel (raw event stream for debugging)
4. Governance mode global indicator with visual urgency hierarchy
5. Session selector (if multiple sessions running)
6. Empty states, loading states, error handling for all panels

---

## Deliverables

### Modified files only

| File | Changes |
|------|---------|
| `dashboard/server.py` | `GET /api/decisions/export`, `POST /api/agents/{id}/override-mode`, bus event log endpoint |
| `dashboard/static/index.html` | Per-agent mode override, JSONL export button, bus event log, global governance mode, session selector, empty/error states |

---

## Prompt

```
Implement Phase 6 of the StreamManager viable product roadmap.
This is a dashboard-only phase. Do not modify any files in src/stream_manager/.
Reference: dashboard/server.py, dashboard/static/index.html.
All Phases 1–5 must be complete.

### 1. Per-agent governance mode override

In the active-agent badge panel (added in Phase 1), add an "Override Mode" affordance:

    Click agent chip → inline dropdown appears:
        [ OBSERVE | SUGGEST | GUIDE | INTERVENE | BLOCK ]
        Currently active mode highlighted.
        Selecting new mode → POST /api/agents/{agent_id}/override-mode
            Body: {"mode": "GUIDE"} (or whichever selected)
        On success: badge updates to show overridden mode with "⚡" indicator
        Indicator means: mode is manually overridden for this session (not from profile default)
        Reset option: "↺ Reset to profile default"
            → POST /api/agents/{agent_id}/override-mode with {"mode": null}

In dashboard/server.py add:
    POST /api/agents/{agent_id}/override-mode
    Body: {"mode": str | null}
    If mode is None: remove override, revert to profile default_action
    If mode is valid Mode value: store in-memory override map {session_id: {agent_id: mode}}
    This override map is read by GovernanceEngine._evaluate_inner() via the registry
    (add a method AgentRegistry.get_mode_override(session_id, agent_id) -> str | None)

### 2. JSONL decisions export

In dashboard/server.py add:
    GET /api/decisions/export
    Query params: ?session_id=... (optional; omit for all sessions)
    Response: Content-Type: application/x-ndjson
    Each line: one decision record as JSON, including:
        decision_id, session_id, timestamp, action, confidence, reasoning,
        matched_hash, model_used, layer, agent_profile_slug, trigger_reason (if HITL)

In dashboard/static/index.html:
    Add "Export JSONL" button to decisions table header.
    Click → fetch GET /api/decisions/export, trigger browser download as
    "sm-decisions-{ISO-date}.jsonl"

### 3. Bus event log panel

Add collapsible "Event Log" panel at the bottom of the dashboard.
Toggle open/closed via header button "[ EVENT LOG ]".
Default state: collapsed.

When open:
    Live SSE stream feeds all bus events into scrolling log.
    Each entry: timestamp (HH:MM:SS.mmm), event type (monospaced chip), content (truncated 100 chars)
    Color-code by event type:
        governance_negative_regression  → red
        governance_variance_alert        → orange
        nfr_model_routing_alert          → yellow
        hitl_sync_queued                 → blue
        hitl_async_flagged               → teal
        agent_identified                 → gray
        desktop_pause                    → white/bright
        all others                       → dim gray
    Max 200 entries in DOM; older entries removed as new arrive.
    "Clear" button to flush visible log.
    "Pause" toggle to stop auto-scroll (new events still queue, resume scrolls to latest).

In dashboard/server.py:
    SSE /events stream already exists; ensure ALL bus event types are forwarded,
    not just decision events. Verify the SSE handler queries the messages table
    broadly (not just type="governance_eval") so event log receives all types.

### 4. Global governance mode indicator

In the dashboard header bar, add a large governance mode indicator:
    Shows current session's worst active governance mode across all agents.
    Worst = highest IntEnum value (BLOCK > INTERVENE > GUIDE > SUGGEST > OBSERVE).

    Visual: full-width thin bar under header, color-coded:
        OBSERVE   → dim gray
        SUGGEST   → blue
        GUIDE     → yellow
        INTERVENE → orange
        BLOCK     → pulsing red (CSS animation: 1s pulse)

    Updates via SSE on any new decision event.
    Tooltip: "Worst active governance mode across all agents in session"

### 5. Session selector

If multiple sessions exist in the WAL bus (sessions table), show a session selector
in the header. Default: most recently started session.

    Session selector:
        Dropdown listing sessions by: "{project_slug} — started {HH:MM:SS}" (most recent first)
        Selecting session → dashboard re-fetches all panels for that session_id
        All API calls that accept ?session_id= switch to selected session
        SSE stream filters to selected session_id

In dashboard/server.py:
    All existing endpoints already accept ?session_id (verify this is true; add if missing)
    GET /api/sessions already exists; ensure it returns project_slug + started_at

### 6. Empty states and error handling

For every panel, add:

    Empty state (no data yet):
        Show centered message in panel area: "Waiting for {panel name} data…"
        Subtle animated ellipsis (CSS only)

    Error state (fetch failed):
        Show: "⚠ Failed to load {panel name}" in panel color-scheme
        "Retry" button → re-fetches immediately

    Loading state (initial fetch in progress):
        Show skeleton pulse animation (CSS, no JS library) matching panel layout

    Specifically ensure:
        - Decisions table empty state: "No decisions yet. Start a governed session."
        - HITL Queue empty state: panel hidden (already specified in Phase 3, verify)
        - Ring panel absent when maturity not active (already Phase 5, verify)
        - Event log empty state: "No events yet." (only when log panel is open)

### 7. Final integration checks in server.py

Verify (and fix if needed):
    - SSE /events forwards ALL message types (not filtered to governance_eval only)
    - GET /api/decisions returns agent_profile_slug if agents table exists
    - GET /api/sessions returns project_slug + started_at + hitl_mode + hitl_floor
    - All endpoints return proper HTTP 404 / 422 / 500 with JSON error body
      {"error": "description"} — not bare text or unhandled exceptions

### 8. Cross-browser and cross-theme smoke check

After implementing, start the dashboard server and manually verify:
    1. Load page → all panels render (ring hidden if no maturity data)
    2. Switch themes OBSIDIAN → PHOSPHOR → PAPER: all new panels re-style correctly
    3. Open event log → "No events yet." or live events visible
    4. Export JSONL button → file downloads (may be empty if no decisions)
    5. Global mode bar visible in header
    6. Session selector visible if >1 session in WAL, hidden if only 1
    7. Settings panel (Phase 3) still works after Phase 6 changes
    8. HITL Queue panel (Phase 3) still works after Phase 6 changes
```

---

## STOP + VERIFY

Before marking Phase 6 complete (= ship gate), confirm **all** of the following:

**Per-agent mode override**
- [ ] Clicking agent chip opens mode dropdown
- [ ] All 5 modes selectable (OBSERVE / SUGGEST / GUIDE / INTERVENE / BLOCK)
- [ ] POST `/api/agents/{id}/override-mode` stores override server-side
- [ ] "⚡" indicator shown when override active
- [ ] "↺ Reset" removes override; badge reverts to profile default

**JSONL export**
- [ ] "Export JSONL" button visible in decisions table header
- [ ] Click triggers browser download (not new tab)
- [ ] Downloaded file is valid NDJSON (one JSON object per line)
- [ ] All required fields present: decision_id, session_id, timestamp, action, confidence, reasoning, matched_hash, model_used, layer, agent_profile_slug

**Bus event log**
- [ ] Panel collapsed by default
- [ ] Toggle button opens/closes with animation
- [ ] Live SSE events appear in log when open
- [ ] All 7 color-coded event types render correctly
- [ ] Max 200 entries enforced (older dropped)
- [ ] "Clear" button flushes DOM entries
- [ ] "Pause" toggle stops auto-scroll without losing queued events

**Global governance mode bar**
- [ ] Thin bar visible under header at all times
- [ ] Color matches worst active mode across agents
- [ ] BLOCK mode shows pulsing red animation
- [ ] Bar updates on new decision SSE events

**Session selector**
- [ ] Hidden when only 1 session in WAL
- [ ] Shown when >1 session; lists by start time descending
- [ ] Selecting session switches all panels to that session's data
- [ ] SSE stream filters to selected session_id

**Empty / error states**
- [ ] Every panel has an empty state (text + animated ellipsis)
- [ ] Every panel has an error state (⚠ message + Retry button)
- [ ] Decisions table empty state text is correct
- [ ] Loading skeleton visible briefly on initial fetch

**server.py integrity**
- [ ] SSE `/events` forwards all message types
- [ ] All endpoints return JSON error body on failure
- [ ] `GET /api/sessions` includes project_slug + hitl_mode
- [ ] No unhandled exceptions (500 responses return `{"error": "..."}`)

**Cross-theme**
- [ ] All new Phase 6 UI elements styled for OBSIDIAN theme
- [ ] All new Phase 6 UI elements styled for PHOSPHOR theme
- [ ] All new Phase 6 UI elements styled for PAPER theme

**Regression: prior phases still work**
- [ ] HITL Queue panel (Phase 3) renders and functions
- [ ] Settings panel (Phase 3) opens/closes and POSTs correctly
- [ ] Layer column (Phase 4) visible in decisions table
- [ ] Ring panel (Phase 5) renders when maturity active

**If any check fails:** fix before declaring ship. This is the final gate.

---

## Definition of Done

The dashboard is a complete operational interface for SM: live governance decisions
with agent identity, HITL queue + annotation, model tier visibility, maturity ring
(when configured), per-agent mode override, raw event log, and JSONL export.
An operator can run SM for a certPortal session and understand everything happening
without looking at a terminal or log file.

Commit message:
```
feat(dashboard): Phase 6 ship gate — per-agent override, export, event log, global mode bar, session selector
```
