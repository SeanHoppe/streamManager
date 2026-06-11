# Decision Oracle: inline pattern pedigree + ancestral replay

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (flywheel) 2026-06-11; idea WILDCARD-1; boldness STRETCH; refute verdict SHIP-PROPOSAL; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

Operators cannot inspect decision causation without context-switching to SQL. On a low-confidence GUIDE or INTERVENE verdict, there is no direct UI affordance to see: (1) the pattern hash + which L0-L4 rung it occupies, (2) the success_rate + age + last reinforcement, (3) the sequence of observations that lifted the pattern through promotion thresholds. Decision rows are opaque black boxes; the matched_hash alone is not human-readable. Operators must manually correlate decision.id -> decision.matched_hash -> database pattern lookup to understand why a verdict fired. This blocks trust-building in low-confidence patterns and makes pattern overfitting (e.g., a pattern matching only one agent repeatedly) invisible in the UI.

## Proposal

Introduce a **Decision Oracle** micro-interaction: a **non-modal whisper pane** (small side-sheet, coexists with all other panes per m1-calm-ambient spec) triggered on hover or tap of a new sparkle icon on every decision row. The oracle renders **two collapsible layers**:

**Layer 1: Pattern Pedigree** -- static metadata stripe showing: pattern_hash (truncated, clickable to copy), current level (L0-L4 rendered as colored rungs), rung_confidence % (how close to next promotion), success_rate, age_days, last_reinforced_at (human-readable ISO timestamp).

**Layer 2: Ancestral Replay** -- a non-interactive vertical timeline of the N observations that led to the pattern's current level. Each row shows: timestamp, sequence index, matched_content_fingerprint (first 50 chars of the message that triggered the match), detected_intent (from governance.reasoning field, if available), match_confidence (if the ranking system captures it). A **read-only playback scrubber** (HTML5 range input, visual-feedback only) lets the operator step through the sequence; no actual audio/animation replay, but tapping a row highlights it and shows a hover tooltip with the full 50-char fingerprint. This is read-only, post-hoc observability.

**Backend (1-3 DB queries):** New endpoint GET /api/decisions/{decision_id}/oracle hits the decisions, messages, and graph_patterns (decision_graph.py persistence table) to walk the pattern's children field and reconstruct the rung ladder. Returns JSON: {pattern_hash, level, success_rate, occurrences, last_seen, children_hashes[], observation_timeline}. Latency budget: sub-50ms (local DB joins, no external APIs).

**Frontend (Svelte leaf component):** New DecisionOracle.svelte (whisper pane, non-modal). Zero event dispatch back to governance; read-only rendering. Paired with a small icon trigger on DecisionRow.svelte (sparkle or info glyph, calm styling, paired with implicit 'oracle available' affordance text in aria-label).

**Compatibility:** Does NOT touch FROZEN surfaces (governance.py, message_bus.py, cli_governance.py, model_router.py, cli_pool.py, bus envelope schemas). Operates entirely on read-only queries over decisions + messages + existing graph_patterns table. No new bus envelope kinds introduced.

## Operator value

HIGH. Directly unblocks trust-building in low-confidence decisions by making pattern ancestry auditable without SQL. Operators can inspect pattern overfitting (e.g., 'this pattern fires 200x on agent_foo, never on agent_bar') inline. In async-HITL mode, the oracle provides annotatable context for operator override notes. Bonus: pattern learning becomes teachable and transparent. Non-intrusive (hover-triggered); zero friction to dismiss. Enables pattern-behavior auditing as a routine part of operator workflow.

## Surfaces touched / added

- dashboard/ui-next/src/lib/components/DecisionRow.svelte (add sparkle trigger icon on hover, paired with 'show pattern pedigree' aria-label)
- dashboard/ui-next/src/lib/components/DecisionOracle.svelte (NEW: non-modal whisper pane, renders 2-layer pedigree + timeline scrubber, read-only)
- dashboard/server.py (add GET /api/decisions/{decision_id}/oracle endpoint, hits decisions+messages+graph_patterns tables, <50ms latency)
- src/stream_manager/decision_graph.py (add oracle_trace(pattern_hash) -> dict method to reconstruct rung ladder + observation sequence)

## Feasibility

FEASIBLE. Backend: 1-3 standard SQL joins over existing tables (decisions, messages, graph_patterns from DecisionGraph.save()). The graph_patterns table already persists the pattern hierarchy (children field is JSON list of child hashes); walking it is shallow recursion (max depth ~4 rungs). Oracle_trace() is ~30-line method. Frontend: Svelte whisper pane following SettingsDrawer pattern (non-modal side-sheet). Zero breaking changes to existing APIs. No animation, no fetch-on-hover. Total scope: 1-2 days (1 day backend, 0.5 day frontend, 0.5 day integration + a11y audit). No infrastructure changes.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS -- oracle reads only from decisions, messages, and graph_patterns tables (all FROZEN read-only surfaces). No new coupling to certPortal, project_context, or monitored-project identity. Pattern hash is domain-agnostic, rendered from data only.
- **Polarity (G2):** PASS -- oracle is read-only, post-hoc observability. Non-action: never changes a decision, never dispatches back to governance. Self-exclude filter: oracle respects existing decisions API filtering (already excludes SM self session per G2/ADR-18). When decision_id resolves to SM-internal session, oracle returns 404.
- **ADR-18 MUST floor:** PASS -- M1: whisper pane is non-modal, coexists with all frames (calm-ambient). M2: escalation-only foreground (oracle does not foreground anything; hover-triggered only). M3-M4: oracle does not participate in HITL state or decision verdicts (read-only observability). M5: oracle does not replace decision row DECIDED/BLOCKED badge (paired label+color constraint upheld). M6: oracle pane does not block frame reachability (side-sheet, dismiss-on-blur). M7: oracle is pure read-only, no IDE/multiplexer. M8: advisory context rendered as data, never as lone color or motion. M9: self-exclude filtering inherited from decisions API. PASS.
- **Frozen-surface note:** Oracle reads only from FROZEN surfaces: decisions table (message_bus.py schema, append-only), messages table (read-only), graph_patterns table (DecisionGraph.save() output, append-only). Does NOT modify governance.py, message_bus.py, cli_governance.py, model_router.py, or cli_pool.py. No ADR amendment required.
- **New-envelope note:** No new bus envelope kinds introduced. Oracle endpoint returns derived JSON (pattern lineage) but does not emit bus messages. cassette_record.py and soak_driver.py remain untouched. Existing cassettes remain valid.

## Grounding

- src/stream_manager/decision_graph.py:60-73 (Pattern dataclass with children field, parent for oracle_trace)
- src/stream_manager/decision_graph.py:206-244 (DecisionGraph.save persists graph_patterns table, oracle reads this)
- dashboard/server.py:588-615 (GET /api/decisions endpoint pattern, oracle endpoint follows same SQL+JSON shape)
- dashboard/server.py:1946-1994 (GET /api/decisions/{decision_id}/suggestions precedent for decision-scoped read endpoint)
- dashboard/ui-next/src/lib/components/SettingsDrawer.svelte:1-60 (non-modal side-sheet pattern, oracle whisper pane reuses this)
- dashboard/ui-next/src/lib/components/Badge.svelte:1-50 (M4 paired label+color contract, oracle icon trigger respects this)
- dashboard/ui-next/src/lib/components/DecisionRow.svelte:1-50 (decision row structure, oracle trigger icon added here)
- src/stream_manager/message_bus.py:32-50 (decisions+messages schema, oracle reads only)
- docs/adr/ADR-18-mvp-surface-freeze.md:40-90 (FROZEN surface classification, oracle respects decision_graph.py+governance.py boundaries)
