# Task 3 — Per-card `Take action` button + naming-drift docs

**Branch:** `claude/hopeful-sutherland-89389d`
**Base PR:** #16
**Spec ref:** FR-UI-4 (mandates per-card `Take action` affordance for HITL OFF read-only cards)
**Status:** Gap — mode flip wired only to global Settings-panel sync/async radios

## Goal — two parts; bigger gap discovered during scoping

### PART A — the spec gap

FR-UI-4 mandates that in HITL OFF mode, every read-only decision card MUST expose a `Take action` affordance which:

1. Promotes the session to HITL ON sync mode.
2. Emits the `hitl_mode_promoted` bus event.
3. Opens the FR-UI-5 ranked-suggestion tray for that card.

Currently the mode flip is wired ONLY to the global Settings-panel sync/async radios (see `modeSync` / `modeAsync` handlers ~line 2549 in `dashboard/static/index.html`). No per-card button exists.

### Implementation

- `dashboard/static/index.html` — when `HITL.mode == 'async'` (HITL OFF semantics), render a `<button class="card-take-action">Take action</button>` on each decision row in the feed. On click: call the existing `postHitlMode('sync', 'take_action')` helper, then on success programmatically open the override tray for that decision (the same tray that fetches `/api/decisions/{id}/suggestions` ~line 2384). Style with NFR-UI-5 focus ring; use OBSERVING badge palette (slate) for the button.
- Hide the button when `HITL.mode == 'sync'` (already actionable).
- Add JS test or playwright/manual-instructions doc note.

### PART B — naming-drift documentation

Spec text in `REQUIREMENTS.md` and audit notes referred to `updateHitlModeBadge`; the live function is `updateModeBadge` (line 2342).

- Add a one-line comment above `function updateModeBadge()` clarifying it covers FR-HITL-1 mode badge state (this is the canonical name; spec drift). NO rename — keep code; align docs.
- Update `REQUIREMENTS.md` if it explicitly names `updateHitlModeBadge` anywhere (grep first); otherwise just the JSDoc comment.

## Run

Full pytest after change; manual smoke at `http://127.0.0.1:8765` to click `Take action` on an async-mode card and verify mode flips + tray opens.

## When done

One commit per part is fine, push, report under 200 words.
