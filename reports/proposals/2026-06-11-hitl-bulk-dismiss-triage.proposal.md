# HITL bulk-dismiss triage modal with keyboard preset logic

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (flywheel) 2026-06-11; idea COMFORTS-2; boldness STRETCH; refute verdict SHIP-PROPOSAL; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

HITL queue accumulates 20-50+ pending rows during long governance sessions, especially when confidence floor is low (0.2-0.4) or desktop_pause detection is noisy. Operators must click APPROVE/DISMISS individually on each row (dashboard/static/index.html:3380-3426), one countdown bar at a time. High friction for common scenario: dismiss all pending rows older than 2 minutes below 0.55 confidence (typical cool-down sweep). No batch affordance; no hotkey chain. Operators tap-farm instead of triage.

## Proposal

New HITL panel affordance: 'Bulk Dismiss' button (gear-icon, low emphasis) that opens a scoped triage modal. Modal offers three radio presets: (1) dismiss all pending rows (with red warning), (2) dismiss rows greater than N seconds old below confidence threshold (operator picks threshold via slider 0.0-1.0, default 0.55), (3) dismiss rows with specific trigger_reason set (checkbox list). Each row shows: queued_at, confidence, trigger_reason, and a per-row checkbox (checked by default). Operator can uncheck rows to exclude them. On 'CONFIRM', batch-POST to `/api/hitl/batch-dismiss` with {pending_ids: [], resolution: 'dismissed'} plus session_id for polarity-flip safety. Modal warns in red text: 'Dismissed rows revert to decided and annotate-only in async mode. Sync mode resumes on next new pattern.' Keyboard trigger: Alt+D (settings panel establishes per FR-UI-9). No auto-clear; every dismiss requires explicit CONFIRM button press.

Implementation surfaces:
- `dashboard/server.py` -- new endpoint `/api/hitl/batch-dismiss` (POST, calls hitl.py batch resolver, filters pending_ids via session_id check before dispatch)
- `dashboard/static/index.html` -- new 'Bulk Dismiss' button plus modal template (3 radio presets, per-row checkboxes, threshold slider 0.0-1.0, explicit CONFIRM), Alt+D listener, batch API call plus error toast
- `src/stream_manager/hitl.py` -- optional batch resolver method `dispatch_batch_resolutions(bus, pending_ids, resolution)` that iterates pending_ids and calls existing `dispatch_resolution()` on each

## Operator value

MEDIUM. Eliminates mechanical repetition during high-chatter sessions. Keyboard shortcut keeps hands on keyboard for dense governance. Presets self-educate (no free-form SQL). Slider damps false positives. Improves session cadence (less time stalled on UI, more time on real work). Real value for sustained 20-30 pending rows; plateaus in practice per observed session profiles. Not HIGH because operators rarely sustain 50+ rows; typical peak is 20-30.

## Surfaces touched / added

- dashboard/server.py -- new endpoint `/api/hitl/batch-dismiss` (POST, calls hitl.py batch resolver, session_id check for polarity-flip safety)
- dashboard/static/index.html -- new 'Bulk Dismiss' button (gear-icon, low emphasis) plus modal template (3 radio presets, per-row checkboxes, confidence slider 0.0-1.0, explicit CONFIRM, red warning text), Alt+D listener, batch API call
- src/stream_manager/hitl.py -- optional batch resolver method `dispatch_batch_resolutions(bus, pending_ids, resolution)` calling dispatch_resolution() on each

## Feasibility

FEASIBLE. Additive endpoint, reuses existing `dispatch_resolution()` and `resolve_hitl()` paths. `hitl_pending` schema unchanged. No new envelope kind required (reuses existing resolved_at and resolution columns). Batch iteration is straightforward. Session-scoping via session_id check at endpoint validation time (not post-fetch) ensures polarity-flip safety.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS. No certPortal coupling. Domain-agnostic (session_id is config, not hardcoded monitored-project vocab). Batch logic is generic triage affordance.
- **Polarity (G2):** PASS. Batch-dismiss endpoint filters pending_ids via session_id check before dispatch. SM-self session excluded via SM_OWN_SESSION_ID (same pattern as jsonl_tail polarity-flip wire-site refusal in server.py:294-301). Batch resolution dispatch calls dispatch_resolution() which is already polarity-safe.
- **ADR-18 MUST floor:** PASS all M1-M9 (ADR-20 decision line 35-59). M1 (monitor-first): gear icon, not auto-foreground. M2 (escalation-only): explicit Alt+D trigger, modal dialog (no interrupt). M3-M4 (HITL ON/OFF semantics): batch dispatch wraps existing dispatch_resolution, preserves trigger_reason. M5 (label+color badges): text label plus gear icon plus red warning (multi-signal, not color-alone). M6 (three domains): untouched. M7 (non-goals): no IDE/multiplexer/multi-tenant. M8 (domain-agnostic): no hardcoded project vocab. M9 (polarity-flip self-exclude): batch logic filters session_id not equal to self.
- **Frozen-surface note:** Proposal touches HITL surfaces classified EVOLVING per ADR-18: hitl.py (hitl synthesis path and dispatch_resolution), server.py HITL endpoints (/api/hitl/resolve, /api/hitl/pending), and index.html HITL panel. No FROZEN surface touched. Additive endpoint to `dispatch_resolution()` logic is optional method, preserving EVOLVING surface semantics (no FROZEN surface modified).
- **New-envelope note:** No new bus envelope kind introduced. Batch-dismiss reuses existing resolved_at and resolution columns on hitl_pending table. dispatch_resolution() call chain unchanged. If implementation deviates to emit new envelope type (e.g., hitl_batch_dismissed), same-PR cassette_record.py and soak_driver.py coverage required per NEW_BUS_ENVELOPE_RULE. Current proposal stays envelope-transparent: constraint for shipping is KEEP_BATCH_DISMISS_ENVELOPE_TRANSPARENT (additive only).

## Grounding

- src/stream_manager/hitl.py:61-101 (dispatch_resolution)
- dashboard/server.py:933-970 (existing /api/hitl/resolve endpoint)
- dashboard/server.py:878-920 (/api/hitl/pending payload)
- dashboard/server.py:922-930 (_VALID_RESOLUTIONS set)
- dashboard/static/index.html:3380-3426 (current resolveHitl and hitlList click handler)
- src/stream_manager/message_bus.py:72-84 (hitl_pending table schema)
- docs/adr/ADR-20-ui-redesign-experimental-spike.md:35-59 (M1-M9 MUST floor)
- docs/adr/ADR-18-mvp-surface-freeze.md:68 (HITL marked EVOLVING)
- CLAUDE.md (Session-source exception rule, Zero contamination, Firewall principles)
