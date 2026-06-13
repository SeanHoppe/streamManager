# Breach Cartography: Temporal Decision Causation UI (Constrained v1)

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (flywheel) 2026-06-11; idea WILDCARD-5; boldness WILD; refute verdict CONSTRAIN; effort L.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

When governance_negative_regression or governance_variance_alert fires (FR-OG-7), the operator knows a maturity regression occurred but not why or which decision caused it. Root-cause tracing requires manual log archaeology. On maturity-driven projects, blind reversions are expensive -- operators need surgical visibility into the decision chain that led to regression before rollback.

## Proposal

Add a modal-overlay Breach Cartography panel (M2 escalation-foreground slot, transient, dismissible) activated when a negative regression or variance alert fires. The modal renders a swimlane causation diagram: decisions sorted by decision_id (Y-axis) vs time (X-axis), each decision node rendered with size=confidence, color=action (red=BLOCK, orange=INTERVENE, yellow=GUIDE, green=ALLOW), and a paired text label (cell e.g. "GUIDE conf=0.92") below the color indicator (ADR-18 M5 compliance: label+color, never color-alone). Arrows connect decisions to their matched pattern hash. A time-rewind slider scrubs backward to show causation chains at different points. On hover, tooltip shows: decision message (100 chars), pattern hash, confidence, HITL override notes, maturity-score delta at that moment. Bottom panel lists "Surgical Revert Proposals" (heuristic ranking: pattern-frequency + confidence, not counterfactual replay per v1 design). Operator explicitly accepts one proposal; SM records override and increments audit trail. Modal is non-persistent, dismisses on action or 30s timeout. Backend: new GET /api/breach/cartography/{alert_id} endpoint with mandatory SQL + Python guard: WHERE project_slug NOT IN ('streamManager') AND session_id != BRIDGE_SM_SELF_SESSION_ID (dual-key polarity filter per G2), fail-loud if SM_OWN_SESSION_ID set and returns zero rows. UI disables "Surgical Revert" button if current session_id matches SM self-session. Maturity snapshots table (maturity_snapshots: id, timestamp, ring_percent, cell_states_json) added to schema; governance.py hook records snapshot after each decision. Counterfactual impact ranking deferred to FR-OG-8 follow-up; v1 ships with heuristic ranking (pattern frequency + highest confidence). No new message bus envelope kind introduced (uses existing governance_decision + governance_negative_regression structures); all async work off hot-path.

## Operator value

Operators on maturity-driven projects gain full visual traceability of how decisions impacted scores. Surgical reversions replace blind rollbacks. Post-incident reviews become data-rich. Governance confidence improves by showing exact decision chains. Medium applicability for general operators (requires maturity.yaml adoption + pattern-graph literacy); high value for FR-OG-7 shops conducting incident response.

## Surfaces touched / added

- dashboard/ui-next/src/lib/components/BreachCartographyModal.svelte (NEW: swimlane causation-chain viz + temporal scrubber, d3-driven or similar)
- dashboard/ui-next/src/lib/components/SurgicalRevertPanel.svelte (NEW: heuristic-ranked proposal list + acceptance UI)
- dashboard/ui-next/src/lib/components/FrameC_Jobs.svelte (integrate modal trigger on governance_negative_regression alert via escalation bus)
- dashboard/server.py (GET /api/breach/cartography/{alert_id} endpoint; dual-key SM-self filter; traces decision history + computes causal graph + maturity deltas)
- src/stream_manager/message_bus.py (add maturity_snapshots table to schema; add optional read-only snapshot_id to decisions table for linking; no breaking changes)
- src/stream_manager/governance.py (add post-decision hook to record maturity snapshot; callable only, no modification to decision verdict path)

## Feasibility

Maturity snapshots additive infrastructure is straightforward. /api/breach/cartography endpoint traces decision history and computes causal graph (each decision links to pattern; pattern links to promoting decisions) -- moderate complexity but no architectural innovation. Heuristic ranking (confidence + pattern frequency) is low-cost; counterfactual replay (toggling decision action, re-feeding, recomputing maturity deltas) is deferred to v2, mitigating complexity. Modal overlay render (swimlane diagram + slider + hover tooltips) requires d3 or similar but reuses existing component patterns. Dual-key polarity guards (SQL WHERE + Python backstop + UI lockout) are standard governance pattern-matching infrastructure. All constraints are design/infra work, not blockers.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS. Proposal uses existing read-only decision/pattern/maturity paths; no new certPortal coupling; domain-agnostic project_slug rendering from data.
- **Polarity (G2):** PASS (REMEDIED). Endpoint now includes mandatory SM-self session filter: SQL WHERE project_slug NOT IN ('streamManager') AND session_id != BRIDGE_SM_SELF_SESSION_ID, Python backstop (fail-loud if SM_OWN_SESSION_ID set and zero rows), UI button lockout for SM-self session. Dual-key gate per G2.
- **ADR-18 MUST floor:** PASS (REMEDIED). (1) Modal overlay in M2 escalation-foreground slot (not persistent fourth frame) resolves M1 three-frame presence. (2) Transient modal (dismiss on action or 30s timeout) complies with M2 escalation-only foreground (non-permanent, user-driven close). (3) Every swimlane node renders label+color (e.g. 'GUIDE conf=0.92') paired with color indicator; color-alone never a signal (M5 compliance).
- **Frozen-surface note:** Proposal does NOT touch FROZEN surfaces (governance.py, message_bus.py, cli_governance.py, model_router.py, cli_pool.py). Maturity snapshots table is additive schema extension (governance.py hook to record snapshot post-decision is a NEW optional call, not a modification to frozen API). No ADR amendment required; infrastructure-only addition.
- **New-envelope note:** No new bus envelope kind introduced. Proposal reuses existing governance_decision and governance_negative_regression envelope structures. All async computation off hot-path (maturity snapshots written by worker, not on decision-verdict path). Cassette/soak coverage: if v1 scales decision-history queries (pre-fetching maturity snapshots for replay), cassette_record.py + soak_driver.py must cover maturity-snapshot read patterns in same PR.

## Grounding

- C:\Users\SeanHoppe\vs\streamManager\src\stream_manager\governance.py:696-768 (FR-OG-7 regression + variance alert logic)
- C:\Users\SeanHoppe\vs\streamManager\src\stream_manager\message_bus.py:17-150 (bus schema; maturity_snapshots added here)
- C:\Users\SeanHoppe\vs\streamManager\src\stream_manager\decision_graph.py:76-200 (Pattern + DecisionGraph structure for causal linking)
- C:\Users\SeanHoppe\vs\streamManager\src\stream_manager\maturity_reader.py:26-54 (RingSnapshot + RingDelta structures)
- C:\Users\SeanHoppe\vs\streamManager\dashboard\ui-next\src\lib\components\Frame.svelte:65-71 (M2 escalation-foreground pattern)
- C:\Users\SeanHoppe\vs\streamManager\dashboard\ui-next\src\lib\components\FrameC_Jobs.svelte:34-80 (Frame C integration + action-count signaling)
- C:\Users\SeanHoppe\vs\streamManager\dashboard\server.py:77-100 (bus singleton pattern for query execution)
- C:\Users\SeanHoppe\vs\streamManager\docs\adr\ADR-18-mvp-surface-freeze.md:1-100 (FROZEN surface list + M1-M5 constraints)
