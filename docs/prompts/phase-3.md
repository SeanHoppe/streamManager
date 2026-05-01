# Phase 3 — HITL UI

**Sequence:** Fourth. Requires Phase 2 complete (API endpoints must exist).
**Estimated time:** 1 session.
**FR refs:** FR-HITL §4.9 (UI affordances).

**Dependency:** Phase 2 REST endpoints (`/api/hitl/*`) and SSE event types
(`hitl_sync_queued`, `hitl_async_flagged`) must be live before this phase.

---

## Context

The dashboard exists (`dashboard/static/index.html`) with 3 themes (OBSIDIAN,
PHOSPHOR, PAPER) and a live decision table via SSE. It has no HITL affordances.

This phase adds:
1. **HITL Queue panel** — live list of pending sync decisions; Approve / Override buttons
2. **Annotate affordance** — per-decision-row expand to add note + override (async mode)
3. **Settings panel** — confidence floor, timeout, HITL mode toggle, pause-detection toggle

The aesthetic must match the existing 3-theme system. No new CSS framework.
All interactions use the existing `fetch()` + SSE pattern already in the dashboard.

---

## Deliverables

### Modified files only (no new files)

| File | Changes |
|------|---------|
| `dashboard/static/index.html` | HITL Queue panel, Annotate row expand, Settings panel, SSE handler for HITL events |
| `dashboard/server.py` | Wire `HitlQueue` instance into server (it was added in Phase 2; ensure it is instantiated and accessible to route handlers) |

---

## Prompt

```
Implement Phase 3 of the StreamManager viable product roadmap.
Reference: REQUIREMENTS.md §4.9 FR-HITL, dashboard/server.py, dashboard/static/index.html.
Phase 2 (hitl.py, REST endpoints) must already exist and be working.

Work only in dashboard/static/index.html and dashboard/server.py.
Do not create new files. Do not change src/stream_manager/*.py.

### 1. HITL Queue Panel (sync mode)

Add a "HITL Queue" panel to the dashboard. Placement: between the session stats
row and the decisions table. Hide panel completely when queue is empty.

Panel structure:
    Header: "HITL QUEUE" + badge showing count of pending items
    For each pending item:
        - Timestamp (queued_at, formatted as HH:MM:SS)
        - Trigger reason chip: "NEW PATTERN" | "LOW CONF" | "PAUSE"
        - Proposed action chip (styled per existing action color scheme)
        - Proposed confidence value
        - Message content preview (first 80 chars, truncated with …)
        - Timeout countdown: visual bar draining from full → empty over timeout_seconds
          Update every second via setInterval. When bar hits zero, item grays out
          (timeout resolution will be set server-side by HitlQueue.route).
        - Buttons:
            [APPROVE]   → POST /api/hitl/resolve  {pending_id, resolution: "approved"}
            [GUIDE]     → POST /api/hitl/resolve  {pending_id, resolution: "overridden:GUIDE"}
            [BLOCK]     → POST /api/hitl/resolve  {pending_id, resolution: "overridden:BLOCK"}
            [ALLOW]     → POST /api/hitl/resolve  {pending_id, resolution: "overridden:ALLOW"}

On SSE event type "hitl_sync_queued":
    Fetch GET /api/hitl/pending and re-render queue panel.

On successful POST /api/hitl/resolve:
    Remove that item from panel immediately (optimistic update).
    Re-fetch queue to sync.

Style per active theme:
    OBSIDIAN: panel background #1a1a1a, amber border, countdown bar amber
    PHOSPHOR: panel background #0a0f0a, green border, countdown bar green
    PAPER:    panel background #f5f0e8, dark border, countdown bar charcoal

### 2. Annotate Affordance (async mode)

In the decisions table, add an expand toggle to each row.
Expand reveals an annotation tray below the row (inline, same row width):

    Annotation tray:
        - Textarea: placeholder "Add note (≤50 tokens stored)…"
        - Override action selector: [Keep original ▾] | ALLOW | GUIDE | INTERVENE | BLOCK
        - [ANNOTATE] button → POST /api/hitl/annotate
            Body: {decision_id, override_action (or original if "keep"), note}
        - On success: close tray, show "✓ Annotated" flash on row for 2s

Row expand trigger: click anywhere on row (except action buttons).
Only one tray open at a time — opening a new row closes any open tray.

On SSE event type "hitl_async_flagged":
    Flash the corresponding decision row with a subtle pulse animation (1s).
    This signals the row is a candidate for annotation.

### 3. Settings Panel

Add a settings panel accessible via a gear icon (⚙) in the dashboard header.
Toggle open/close on click. Panel slides in from the right (CSS transition).

Settings panel sections:

    HITL MODE
        Radio/toggle: Sync ● | Async ○
        On change → POST /api/hitl/settings {hitl_mode: "sync"|"async"}

    CONFIDENCE FLOOR
        Slider: 0.50 → 0.90, step 0.05, current value shown numerically
        On change (debounced 500ms) → POST /api/hitl/settings {hitl_floor: value}

    SYNC TIMEOUT
        Number input: 15–300 seconds
        On change (debounced 500ms) → POST /api/hitl/settings {timeout_seconds: value}

    PAUSE DETECTION
        Toggle: ON / OFF
        Controls whether desktop_pause trigger fires HITL.
        On change → POST /api/hitl/settings {pause_detection_enabled: bool}
        (server stores in session record; governance engine reads at evaluate time)

    On panel open: GET /api/hitl/settings and populate current values.

### 4. Session header badge

In the session stats header row, add:
    - HITL mode badge: [SYNC] or [ASYNC] — styled like the existing action badges
    - If sync mode + queue is non-empty: badge shows "[SYNC · N]" where N = queue count
    - Badge updates live via SSE

### 5. Wire HitlQueue in server.py

Ensure dashboard/server.py has a module-level HitlQueue instance accessible to
the /api/hitl/* route handlers. It must share the same MessageBus instance used
by the rest of the server. If not already wired from Phase 2, add:

    from stream_manager.hitl import HitlQueue
    _hitl_queue: HitlQueue | None = None  # initialized on startup with shared bus

Also add POST /api/hitl/settings handler that:
    - Calls bus.set_hitl_mode(session_id, mode, floor) for the active session
    - Stores timeout_seconds + pause_detection_enabled in a server-side config dict
      (these don't need WAL persistence — session-scoped in memory is fine for now)
```

---

## STOP + VERIFY

Before marking Phase 3 complete, confirm **all** of the following:

**HITL Queue panel**
- [ ] Panel only visible when `hitl_pending` has unresolved rows
- [ ] Each pending item shows: timestamp, trigger chip, action chip, confidence, message preview
- [ ] Countdown bar animates from full to empty over `timeout_seconds`
- [ ] APPROVE / GUIDE / BLOCK / ALLOW buttons each POST correct resolution string
- [ ] SSE `hitl_sync_queued` event triggers re-fetch + re-render
- [ ] Panel styled correctly for all 3 themes (OBSIDIAN / PHOSPHOR / PAPER)

**Annotate affordance**
- [ ] Each decision row is clickable to expand annotation tray
- [ ] Only one tray open at a time
- [ ] Textarea present + override action selector has all 5 options
- [ ] ANNOTATE button POSTs to `/api/hitl/annotate` with correct body
- [ ] "✓ Annotated" flash shown on success
- [ ] SSE `hitl_async_flagged` event pulses the flagged row

**Settings panel**
- [ ] Gear icon (⚙) in header opens/closes panel
- [ ] Panel slides in/out (CSS transition, not instant show/hide)
- [ ] All 4 settings render with current values on open
- [ ] HITL MODE radio updates immediately on change (POST fires)
- [ ] CONFIDENCE FLOOR slider debounced 500ms before POST
- [ ] SYNC TIMEOUT input debounced 500ms before POST
- [ ] PAUSE DETECTION toggle fires POST on change

**Session header badge**
- [ ] Badge shows [SYNC] or [ASYNC] reflecting current mode
- [ ] Badge shows queue count when sync mode + non-empty queue
- [ ] Badge updates via SSE (no page reload needed)

**server.py**
- [ ] Module-level `HitlQueue` instance wired to shared `MessageBus`
- [ ] `POST /api/hitl/settings` accepts and stores `timeout_seconds` + `pause_detection_enabled`
- [ ] All existing endpoints (`/api/stats`, `/api/decisions`, `/api/sessions`, `/events`) still work

**Cross-theme check**
- [ ] Switch to OBSIDIAN — HITL panel renders with amber border + amber countdown
- [ ] Switch to PHOSPHOR — green border + green countdown
- [ ] Switch to PAPER — dark border + charcoal countdown

**If any check fails:** fix before proceeding to Phase 4.

---

## Definition of Done

A human operator can see pending HITL decisions in real time, approve or override
them with one click (sync mode), annotate any past decision (async mode), and
configure all HITL parameters from the dashboard without touching config files.

Commit message:
```
feat(dashboard-hitl): Phase 3 — HITL queue panel, annotate affordance, settings panel
```
