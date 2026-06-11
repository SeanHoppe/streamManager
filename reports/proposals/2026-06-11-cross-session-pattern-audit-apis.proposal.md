# Cross-session pattern audit & applicability APIs

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (flywheel) 2026-06-11; idea BACKEND-4; boldness STRETCH; refute verdict CONSTRAIN; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

FR-DG-6 & FR-PC-9 enable patterns to persist across sessions (L1+ patterns queued as HITL on cross-session emergence). No endpoint queries which patterns learned in prior sessions are hydrating a current session or shows which patterns would fire on a hypothetical message. Operators can't audit 'which learned rules are governing this new session?' and can't make data-driven decisions about pattern demotion (FR-HITL-7 feedback loop, FR-UI-5 suggestions).

## Proposal

Add two new dashboard APIs on top of existing cross_session_patterns infrastructure:

**1. GET /api/patterns/cross-session/{session_id}/hydrated** -- returns array of hydrated cross-session patterns injected into the target session at engine init time. Schema: {pattern_hash, level, last_seen_session_id, last_seen_ts, occurrence_count, success_rate, matched_decision_count_this_session, sourced_from, decay_status}. Sourced from: patterns table (existing cross_session=1 rows) + decisions table (join decisions.matched_hash -> patterns.hash -> messages.session_id to compute matched_decision_count_this_session and to backfill last_seen_session_id if not yet stored). Query filters to session_id != current_session AND cross_session=1.

**2. GET /api/patterns/{hash}/would-apply?message_content={text}** -- post-hoc pattern matching endpoint. Input: raw message text. Output: {applies: bool, match_confidence: 0.0-1.0, sourced_from: [list of decision_suggestions.Candidate.sourced_from entries], rationale: string}. Uses existing decision_graph.DecisionGraph.match() cosine-similarity logic (SIMILARITY_THRESHOLD = 0.72) over the pattern's vector. Returns applicability without triggering a decision path. Timeout 500ms hard cap; on timeout or error returns {applies: false, match_confidence: 0.0, sourced_from: [], rationale: 'matching engine unavailable'}.

**Implementation surfaces:**
- `dashboard/server.py` -- two new GET endpoints wired to MessageBus methods.
- `src/stream_manager/message_bus.py` -- new query methods: get_hydrated_patterns_for_session(session_id) + get_pattern_applicability(pattern_hash, message_text).
- `src/stream_manager/decision_suggestions.py` or new `src/stream_manager/pattern_applicability.py` -- pattern matching + applicability scoring logic (wraps decision_graph match).

Patterns table schema changes (additive migration):
- Add optional columns: last_seen_session_id (TEXT), sourced_from (TEXT), decay_status (TEXT).
- Default to NULL / '' / 'unknown' on backfill.
- Idempotent migration guard.

Dashboard UX (out-of-scope for this proposal; ideation only):
- "Live learned rules" panel per session showing which hydrated patterns are actively firing (via live filter over the decisions feed).
- Pattern drill-down tray for manual "would this pattern fire?" QA queries.

This directly powers FR-UI-5 suggestion ranking (decision_suggestion_weights: graph_match + cross_session patterns) and FR-HITL-7 feedback loop (show operator which override patterns are active in similar sessions).

## Operator value

Operators audit cross-session learning: 'which rules from my last soak are now governing my new session?'. Enables operator-driven pattern demotion (reject a learned rule that feels over-broad). Powers hypothesis testing: 'if I change this message slightly, would the same pattern still fire?'. Closes the FR-HITL-7 feedback loop by making pattern provenance and applicability inspectable, not opaque. Directly supports Learn-Mode advisory bias validation (FR-LM-3/5) -- operator can verify 'was this suggestion justified by a real pattern, or a hallucination?'.

## Surfaces touched / added

- dashboard/server.py -- new GET /api/patterns/cross-session/{session_id}/hydrated, GET /api/patterns/{hash}/would-apply endpoints
- src/stream_manager/message_bus.py -- get_hydrated_patterns_for_session(), get_pattern_applicability() methods
- src/stream_manager/decision_suggestions.py or new src/stream_manager/pattern_applicability.py -- pattern matching + applicability scoring logic

## Feasibility

HIGH. Infrastructure is 85% in place: patterns table (with cross_session flag), decisions linkage (decisions.matched_hash -> patterns.hash), decision_graph.match() cosine similarity (SIMILARITY_THRESHOLD 0.72), existing CrossSessionPatterns.svelte hydrator, decay.py, decision_suggestions.Candidate.sourced_from. Schema extensions are additive only (three new optional columns). Bus methods already exist (get_cross_session_patterns, get_pattern). Decision linking is straightforward SQL (decisions.matched_hash -> patterns.hash -> messages.session_id). No FROZEN surfaces touched; all work lands in dashboard/server.py + message_bus.py (both EVOLVING per ADR-18). The would-apply endpoint is post-hoc only (M18 safe) and sits on the dashboard observation path, not the verdict path.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS -- no certPortal coupling introduced beyond already-designed (learn-mode source registry, project_context, agent_profiles).
- **Polarity (G2):** PASS -- proposal does not add SM self-monitoring. SM monitors NON-SM sessions only (session_id NOT IN {streamManager} AND session_id != self). Hydrated patterns query filters to cross_session=1 from OTHER sessions.
- **ADR-18 MUST floor:** PASS -- does not violate ADR-18 binding UI MUSTs. No FROZEN surfaces (governance.py, message_bus.py schema shape, model_router.py, cli_pool.py, cli_governance.py) are modified. New endpoints sit in EVOLVING dashboard/server.py + message_bus.py. No changes to 3-frame presence, escalation-only foreground, paired label+color badges, HITL gate, domain-agnostic rendering, a11y, latency budget, or non-goals (IDE/multiplexer/multi-tenant).
- **Frozen-surface note:** No FROZEN surfaces touched. ADR-18 classification: patterns table schema extensions are ADDITIVE (ADR-18 Rule 1 'new optional kwarg, new enum case, new metadata field'). decisions table remains FROZEN shape; new queries only. bus envelopes unchanged.
- **New-envelope note:** If would-apply endpoint introduces a NEW bus envelope kind (e.g., pattern_applicability_query for live pattern queries), the same PR must add cassette_record.py + soak_driver.py test coverage per feedback_cassette_must_cover_new_envelopes rule (ADR-18). If would-apply queries are pure computation (no envelope emission), this constraint is void.

## Grounding

- src/stream_manager/message_bus.py:43--50 (patterns table schema)
- src/stream_manager/message_bus.py:1383--1401 (get_cross_session_patterns existing method)
- src/stream_manager/message_bus.py:1403--1421 (get_pattern existing method)
- src/stream_manager/cross_session_hydrator.py:51--77 (hydration injection logic)
- src/stream_manager/decision_graph.py:PatternLevel, Pattern, SIMILARITY_THRESHOLD=0.72, match() method
- src/stream_manager/decision_suggestions.py:140--157 (Candidate with sourced_from)
- src/stream_manager/governance.py:999 (FR-HITL-7 reference)
- REQUIREMENTS.md:143 (FR-DG-6), 185 (FR-PC-9), 338 (FR-HITL-7), 406 (FR-UI-5), 496 (FR-LM-3), 505 (FR-LM-5)
- docs/adr/ADR-18-mvp-surface-freeze.md:59--73 (FROZEN/EVOLVING classification)
- docs/adr/ADR-5-latency-budget.md (M18 latency post-hoc observability floor)
