# Session Story: narrative arc panel w/ bi-directional feed linking

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (ux) 2026-06-11; idea WILDCARD-4; boldness STRETCH; refute verdict CONSTRAIN; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

The REPL feed displays each decision in isolation (timestamp, action, reason snippet). After a long session, operators lack a cohesive **narrative arc** that ties decisions together into "what is the session trying to accomplish, and did we govern it well?" For post-hoc audit, incident review, and compliance workflows, this narrative gap forces manual scrolling and reconstruction. No human-readable summary exists alongside the machine-readable feed.

## Proposal

Ship a **Session Story panel** (togglable frame-sized card in the EXPERIMENTAL ui-next spike) that, on-demand via a 'Compose Story' button or on session-close (configurable), invokes a **lightweight Sonnet narrative generator** (off the verdict hot path, via Learn Mode worker queue). The generator reads:
(a) session's ranked project context (existing `project_context` registry, read-only)
(b) all decisions from the session (action + reasoning + timestamp, last-100 max)
(c) aggregated Learn Mode patterns observed during the session
...and produces a **concise 3-5 paragraph markdown narrative** that reads like a calm project-manager summary: "Session started 2:43pm, goal: refactor auth module. Agent made 7 file edits under GUIDE governance, no blocks. Learned two new patterns: conditional-import checks (+3 confidence), async-function-safety checks (+2 confidence). Session ended cleanly, no regressions."

**CONSTRAINT (per refuter feedback): Store narrative as metadata-only extension to existing `sessions` table** (not a new table). Add three optional columns:
- `narrative_markdown TEXT DEFAULT NULL` -- the rendered markdown story
- `narrative_composed_at REAL DEFAULT NULL` -- UNIX timestamp
- `narrative_model TEXT DEFAULT NULL` -- which model (e.g., "claude-sonnet-4-5")

This satisfies ADR-18 Rule 1 (metadata-only additive extension to FROZEN schema).

**UI rendering**: Narrative is read-only, rendered with markdown styling. Badge semantics (paired label+color for tone: 'clean', 'turbulent', 'blocked', 'learning') per ADR-20 M5. Clicking any phrase highlights the corresponding decision row in the feed below (bi-directional narrativefeed link via a new NarrativeToFeed overlay component).

**Export**: Session JSONL export (existing `/api/decisions/export?session_id=...` endpoint) prepends the narrative as markdown frontmatter block if available, enabling post-hoc audit narrative retrieval.

**Async model invocation**: Runs via existing Learn Mode worker queue or on-demand task (reuses `learn_categorizer.py` subprocess pattern: CLI Sonnet call, envelope parsing, timeout/degradation handling). Task returns `job_id` for polling; client polls `/api/sessions/{id}/story-result?job_id=...` until composition completes.

**Self-session exclusion**: POST `/api/sessions/{id}/compose-story` endpoint explicitly checks `session_id != SM_OWN_SESSION_ID` before accepting (mirrors existing `_reject_sm_own` guard at dashboard/server.py:2406-2413).

**No new bus envelopes required**. Narrative is metadata stored on sessions table, not a message-bus event. If a future cycle wants to emit narrative as a Learn Mode signal source, that is a separate ADR amendment (would incur cassette/soak coverage per NEW BUS ENVELOPE RULE).

## Operator value

Transforms raw decision logs into a legible narrative; enables rapid post-hoc audit and incident review; builds operator intuition about what 'normal' sessions feel like (tone is a signal); archives human-readable session summary alongside machine-readable feed; supports compliance/audit workflows that require narrative transcripts, not just CSV export.

## Surfaces touched / added

- dashboard/ui-next/src/lib/components/SessionStory.svelte (new panel; markdown renderer + tone badge + 'Compose Story' button; togglable frame)
- dashboard/ui-next/src/lib/components/NarrativeToFeed.svelte (new; bi-directional link overlay, highlights decision rows on phrase click)
- dashboard/server.py: POST /api/sessions/{id}/compose-story (async; checks SM_OWN_SESSION_ID, triggers narrative generation via Learn Mode worker, returns {job_id}); GET /api/sessions/{id}/story-result?job_id=... (polls for narrative_markdown result)
- src/stream_manager/message_bus.py: Add three columns to sessions table: narrative_markdown TEXT DEFAULT NULL, narrative_composed_at REAL DEFAULT NULL, narrative_model TEXT DEFAULT NULL
- src/stream_manager/learn_categorizer.py: Add narrative-compose task type to EngineRegistry worker (reuses existing Sonnet subprocess pattern + envelope parsing)
- dashboard/server.py: api_decisions_export endpoint -- prepend narrative markdown frontmatter block if narrative_markdown is not NULL

## Feasibility

FEASIBLE. The Learn Mode Sonnet categorizer (src/stream_manager/learn_categorizer.py:1-80) already demonstrates the pattern: off-hot-path subprocess invocation, CLI Sonnet calls, timeout/degradation handling, async task queuing. Reusing the same worker queue (or spawning a narrative-compose task type) is straightforward and fits the existing EngineRegistry lifecycle. Metadata-only schema extension (3 columns) is zero-risk per ADR-18 precedent.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS. No certPortal coupling introduced. The proposal reads `project_context` (DESIGN-DOCUMENTED source), aggregates Learn Mode patterns (existing), and outputs narrative markdown. No new instrumentation vocabulary enters SM.
- **Polarity (G2):** PASS. Self-monitoring exclusion is already in place at dashboard/server.py:2406-2413 (_reject_sm_own guard). The POST `/api/sessions/{id}/compose-story` endpoint explicitly checks `session_id != SM_OWN_SESSION_ID` before accepting the request (mirrors existing pattern).
- **ADR-18 MUST floor:** PASS. ADR-18 Rule 1 permits metadata-only additive extensions to FROZEN schemas. Three new columns on existing `sessions` table (narrative_markdown, narrative_composed_at, narrative_model) are structural metadata, not new tables. Follows the precedent of governance_decision envelope metadata addition per Amendment B.
- **Frozen-surface note:** message_bus.py: Sessions table schema is FROZEN per ADR-18. The three new columns are metadata-only additive extensions per Rule 1 precedent. No structural schema change; no new table required. No ADR amendment needed for metadata-only extension.
- **New-envelope note:** No new bus envelope kind introduced. Narrative is stored as metadata on sessions table, not emitted as a message-bus event. If a future cycle chooses to emit narrative as a Learn Mode signal source (separate feature), that would introduce a new envelope kind and would require cassette_record.py + soak_driver.py coverage per ADR-18 Rule 1 Metadata-only extensions precedent. This proposal does not trigger that requirement.

## Grounding

- docs/adr/ADR-18-mvp-surface-freeze.md:41-91 (Rule 1 metadata-only extensions, FROZEN surface classification)
- docs/adr/ADR-20-ui-redesign-experimental-spike.md:35-59 (M5 badge semantics, M8 domain-agnostic rendering, M9 self-session exclusion)
- dashboard/server.py:2406-2413 (_reject_sm_own guard pattern for SM_OWN_SESSION_ID checks)
- dashboard/server.py:2290-2350 (api_decisions_export NDJSON streaming pattern, frontmatter insertion point)
- src/stream_manager/learn_categorizer.py:1-80 (subprocess invocation, CLI Sonnet call, timeout/degradation pattern)
- src/stream_manager/message_bus.py:52-58 (sessions table schema -- insertion point for three new columns)
- src/stream_manager/message_bus.py:463-735 (governance_decision envelope + envelope_subscribers callback precedent for async event emission)
