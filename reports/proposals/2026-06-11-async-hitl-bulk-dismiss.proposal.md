# Bulk-dismiss toolbar for async HITL queue cleanup

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (ux) 2026-06-11; idea COMFORTS-4; boldness SAFE; refute verdict CONSTRAIN; effort L.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

In ASYNC HITL mode (FR-HITL-6), operators accumulate resolved governance decisions in the async-hitl-section over multi-hour sessions. With 50+ decisions, the UI list fills with dimmed rows (resolution=timeout, age >1h) that clutter the workspace. Operators manually click DISMISS on each aged row one at a time, creating repetitive click fatigue. Expired rows (opacity .35) are visually distinguished but remain actionable, causing confusion about pending vs. expired state. No batch cleanup action exists; the cleanup is entirely manual and tedious.

## Proposal

Add a constrained bulk-dismiss toolbar to the async-hitl-section that:

1. VISIBILITY GATE: toolbar renders ONLY when (a) HITL mode is ASYNC, (b) asyncHitlList contains >=3 children, AND (c) asyncHitlSection is not hidden. CSS display:none when guard fails; JS guard on `.children.length > 0` before rendering buttons.

2. FILTERS (no hard-coded vocab):
   - Checkbox 'Show expired only' filters visible rows to resolution='timeout' only.
   - Age-slider 'Dismiss older than X minutes' (range 1--120min, default 60min) with accompanying 'Dismiss stale' button.
   - Both filters apply to the same underlying query via filter param {expired|age_minutes} in the POST body.

3. API ENDPOINT (new, subject to cassette+soak coverage):
   - POST /api/hitl/bulk-dismiss with body {session_id, filter: string, age_minutes?: int}
   - MUST validate session_id != 'streamManager' in the handler and reject with HTTP 403 Forbidden + detail 'Cannot bulk-dismiss SM self-monitoring session' (polarity gate at API boundary).
   - Marks matching hitl_pending rows with resolution='dismissed' and resolved_at=NOW.
   - Returns {ok: true, count: int, filter: string, timestamp: string}.

4. EMIT BUS ENVELOPE (new):
   - After successful POST, emit hitl_bulk_dismissed envelope via bus.write_envelope('hitl_bulk_dismissed', {kind: 'hitl_bulk_dismissed', count, filter, timestamp}) for audit trail.
   - Envelope is domain-agnostic: no job_id, role, or project_slug baked in; contains only {count, filter, timestamp}.
   - NOTE: This is a NEW envelope kind. Same PR MUST include cassette_record.py + soak_driver.py updates to record and replay the hitl_bulk_dismissed envelope per the NEW BUS ENVELOPE RULE.

5. UI CONFIRMATION (BENDS-SHOULD, not VIOLATES):
   - If >10 rows would be dismissed, render a confirm modal with count display and a 10s countdown bar (matching the hitl-pending countdown pattern for consistency).
   - Modal is confirmation-only, not escalation. Bends the 'escalation-only auto-foreground' SHOULD because bulk cleanup is routine operator maintenance, not a true escalation (no negative regression, no static-rule fire, no desktop_pause signal).
   - DESIGN SALVAGE: modal can be made optional (confirmation opt-in) rather than mandatory countdown if friction is deemed too high. ADR-18 MUSTs (3-frame layout, paired label+color badges, color-alone never a signal) remain unviolated either way.

6. UI OPTIMISM:
   - Dismissed rows vanish immediately from asyncHitlList (optimistic UI). Rows remain in hitl_pending table (resolution='dismissed', never deleted).
   - Toolbar hides automatically when asyncHitlList.children.length hits 0.
   - Count badge in frame-head decrements in real time.

7. DEAD CODE GUARD:
   - Toolbar MUST only render when asyncHitlList is populated AND parent asyncHitlSection is visible. Prevents false affordance if async-hitl display infra is not yet wired.
   - HTML scaffold exists at dashboard/static/index.html lines 2365--2371; the async-hitl-section body is unpopulated by design (no code currently wires hitl_async_flagged rows into that display). Toolbar is a co-feature and inherits that dependency.

## Operator value

Genuine operator value for high-volume async HITL loads (reduces click fatigue from 50+ manual dismissals to 1--2 bulk actions). Workspace clutter decreases; expired-row confusion is reduced via explicit 'Show expired only' filter. However: semantic tension exists. Async mode is fire-and-forget by design (proposedAction passes through immediately; operator annotations are retroactive). Bulk cleanup implies HITL row accumulation and debt, which signals sync-mode failure (sync auto-times out stale rows, creating cleanup pressure). In healthy async operations, pending items resolve individually as operators annotate them live; bulk cleanup should be rare. Use case is stronger for operators managing sync-mode debt who are temporarily using async mode, or for async sessions with annotation delays. Filter-by-age is a workaround, not a root fix. Value estimate: MEDIUM (solves real UX pain but does not address root cause of accumulation).

## Surfaces touched / added

- dashboard/server.py (new POST /api/hitl/bulk-dismiss endpoint ~15 lines, session_id != streamManager validation, filter dispatch)
- dashboard/static/index.html (bulk-dismiss toolbar markup above async-hitl-section; confirm modal; event handlers; display:none guard on .children.length > 0)
- src/stream_manager/hitl.py (optional: bulk_dismiss(session_id, filter_type, age_minutes) helper method calling hitl_pending UPDATE in batch; or UPDATE logic lives in server.py POST handler)
- tools/cassette_record.py (record hitl_bulk_dismissed envelope in cassette fixture)
- tools/soak_driver.py (replay hitl_bulk_dismissed envelope during soak phase)

## Feasibility

HARD. Three plumbing challenges: (1) NEW BUS ENVELOPE RULE applies -- hitl_bulk_dismissed is a novel envelope kind requiring cassette_record.py + soak_driver.py fixture coverage in the same PR (non-trivial schema integration, testing harness updates). (2) POST /api/hitl/bulk-dismiss endpoint must enforce new session-self validation contract (new API surface area, requires careful testing of the 403 path). (3) The async-hitl-section HTML scaffold exists but asyncHitlList remains unpopulated by design (no dashboard code currently wires hitl_async_flagged rows into that display). The toolbar would be dead code if async-hitl display infra is not wired first. Buildable if dependencies are managed carefully, but design has integration points that require coordination with async-hitl display wiring.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS: Proposal introduces no certPortal coupling. The hitl_bulk_dismissed bus envelope is domain-agnostic, containing only {count, filter, timestamp} with no monitored-project vocab, JOB-IDs, role names, or session-specific identifiers baked in.
- **Polarity (G2):** PASS (with API gate): Bulk-dismiss operates globally across non-SM sessions by design. Requires explicit session_id != 'streamManager' validation in POST /api/hitl/bulk-dismiss handler, returning HTTP 403 Forbidden + detail 'Cannot bulk-dismiss SM self-monitoring session'. This enforces the polarity rule at the API contract layer, preventing SM from sweeping its own HITL rows.
- **ADR-18 MUST floor:** BENDS-SHOULD (not VIOLATES): ADR-18 UI MUSTs (3-frame monitor-first layout, escalation-only auto-foreground, paired label+color badges, color-alone never a signal, absolute HITL gate) remain unviolated. The 10s countdown confirm modal for >10 dismissals BENDS the 'escalation-only foreground' SHOULD because bulk cleanup is routine operator housekeeping, not a true escalation (no negative_regression, no static-rule fire, no desktop_pause signal). Design is salvageable: omit the modal (pure friction reduction), or implement as optional confirmation opt-in rather than mandatory countdown. Toolbar buttons are explicit text (no color-alone signal). Label 'Show expired only' is paired with checkbox. Count display is text-based, never color-only.
- **Frozen-surface note:** FROZEN surfaces referenced: message_bus.py (envelope schema), governance.py (HITL row structure). Proposal does NOT modify FROZEN surfaces. New POST /api/hitl/bulk-dismiss is additive to server.py (EVOLVING). New hitl_bulk_dismissed envelope is additive to bus envelope registry. No ADR amendment required; new envelope kinds are explicitly anticipated in ADR-17 (soak tiers) and the NEW BUS ENVELOPE RULE in the refuter constraint.
- **New-envelope note:** NEW ENVELOPE: hitl_bulk_dismissed. Schema: {kind: 'hitl_bulk_dismissed' (str), count: int, filter: string (one of 'expired'|'age_X' where X is minutes), timestamp: string (ISO8601)}. CASSETTE COVERAGE REQUIRED (per NEW BUS ENVELOPE RULE): (1) cassette_record.py must emit a synthetic hitl_bulk_dismissed envelope in the recorded cassette when the bulk-dismiss POST fires during cassette-record runs (or add a minimal fixture envelope to the baseline cassette). (2) soak_driver.py must handle replay of hitl_bulk_dismissed envelopes during replay phase (existing envelope replay loop already supports arbitrary envelope kinds; no major changes needed). (3) Tests must verify envelope round-trips correctly through the bus and dashboard SSE stream. Envelope schema frozen at first ship; future extensions must be additive (new optional fields only).

## Grounding

- dashboard/static/index.html:2365--2371 (async-hitl-section scaffold)
- dashboard/server.py:933--970 (POST /api/hitl/resolve pattern template)
- src/stream_manager/hitl.py:1--20 (HITL queue docstring, async mode contract)
- tools/cassette_record.py:1--80 (cassette fixture structure, envelope recording pattern)
- docs/adr/ADR-18-mvp-surface-freeze.md:40--74 (FROZEN/EVOLVING classification, envelope schema rules)
