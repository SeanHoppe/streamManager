# Task 4 — Bundled spec-completion sweep (gaps A–E)

**Branch:** `claude/hopeful-sutherland-89389d`
**Base PR:** #16
**Spec refs:** NFR-UI-7, FR-UI-7, FR-UI-9, FR-UI-1, FR-UI-3
**Status:** Five small spec-completion gaps surfaced during ship-readiness audit

## Goal

Close five small spec-completion gaps. Single PR / commit chain (one commit per gap is fine).

## GAP A (NFR-UI-7) — Reduced-motion override applies

Settings row exists at line ~1863 (`Reduced motion override`: `system` / `force-reduce` / `force-allow`), but verify the CSS rules at lines 161 + 1593 (`@media (prefers-reduced-motion: reduce)`) actually respect the override. Wire it:

- `force-reduce` → apply the no-pulse rules unconditionally.
- `force-allow` → suppress the media query.
- `system` → current behaviour.

Persist to `localStorage` AND to session record (FR-UI-9 intent — persist to WAL).

## GAP B (FR-UI-7) — Tab-title open-action count

Update `document.title` whenever total `ACTION REQUIRED` count across all three frames changes.

- Format: `(N) StreamManager` where N is total open.
- When N==0, title is just `StreamManager`.
- Test: count is the sum used by `FrameState.actionCount` across frames A/B/C.

## GAP C (FR-UI-9) — Settings persistence to WAL session record

Currently settings hit `localStorage` only. For each FR-UI-9 control (sync timeout, audible cue, activity window, reduced-motion override, etc), POST to a NEW endpoint `POST /api/sessions/{id}/settings` that updates the `sessions` table (add columns or a JSON `settings` blob — your call, prefer JSON blob to avoid migration churn). Server emits `session_settings_updated` bus event. Client reads back on connect.

## GAP D (FR-UI-1 + FR-UI-9) — Activity window setting actually consumed

The swim-lane re-pin tick (frame B) currently uses a hardcoded 10 s threshold? Check; if hardcoded, read from `FrameState.activityWindowSec` which is sourced from the FR-UI-9 setting.

## GAP E (FR-UI-3) — `negative_regression` auto-foreground wiring

Spec lists `negative_regression` as auto-foreground trigger. CSS class exists (`.evt-governance_negative_regression` line 1279) and the `EVENT_FOREGROUND_TYPES` array exists (line 2956) — verify the event TYPE the bus actually emits matches what the JS listener filters on (likely `governance_negative_regression` from gov-engine). If mismatch, fix the JS to listen for the actual type. Add a test (JS-unit if possible, else doc'd manual repro) that sending a `governance_negative_regression` event triggers `autoForeground()`.

## Commit strategy

For each gap, commit separately for clean review. Run full pytest after the bundle. Push.

## Out of scope

- Visual eyeball verification (user task).
- `axe-core` audit (separate task).

## When done

Report under 250 words listing what changed per gap and any deferrals.
