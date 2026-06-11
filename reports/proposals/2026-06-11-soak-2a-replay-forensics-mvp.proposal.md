# Live-soak replay forensics: operator root-cause via side-by-side decision deltas (MVP tier)

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (ux) 2026-06-11; idea SOAK-2; boldness WILD; refute verdict CONSTRAIN; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

When a live soak discovers a regression or unexpected decision (e.g., a governance surprise where an earlier decision was SUGGEST but replay shows GUIDE), there is no fast path to replay that exact sequence of tailed envelopes frame-by-frame with full governance context so the operator can isolate what changed. Today: hand-parse logs or re-run the entire soak (cost + latency). Needed: deterministic replay of engine logic with the same inputs, rendered as a legible side-by-side diff.

## Proposal

Ship SOAK-2a (this cycle): MVP basic forensics, split into two focused PRs per the refuter constraint.

PR 1 deliverables: (1) New `/api/soak/replay/{recorded_session_uuid}` endpoint on dashboard/server.py that accepts optional frame range (start_idx, end_idx) and returns JSON array of forensics triples. (2) New SoakForensicsDrawer.svelte component in dashboard/ui-next/src/lib/components/ (EXPERIMENTAL surface per ADR-20) that renders three-column side-by-side diff: left=original decision (frame 1), middle=replayed decision (frame 2), right=delta (reasoning_delta, layer_delta, matched_hash_delta). Opt-in drawer under soak report card. (3) Emit soak_forensics_opened bus event for audit trail. (4) Extend soak_driver.py with --record-session-uuid flag to cassette output (additive to v1.2 schema). (5) Decision_graph snapshot helpers: preserve matched_hash + confidence at decision time (deferred live L-level/confidence-trajectory drill-down to SOAK-2b).

Key constraint: **omit confidence-trajectory drill-down** (requires decision_graph.snapshot(frame_idx) design, out of scope for MVP). The basic 3-column delta (reasoning/layer/matched_hash) is the load-bearing operator value.

Endpoint signature: GET /api/soak/replay/{recorded_session_uuid}?start_idx=0&end_idx=60&session_id={session_id}

Guard: if session_id == SM_OWN_SESSION_ID, raise ValueError (polarity-flip enforcement per ADR-18 / EngineRegistry pattern).

Cassette amendment: new optional field recorded_session_uuid appended to soak_cassette_*.jsonl (per ADR-17 append-only). No schema break; v1.2-era code sees no change.

Non-goal: re-run the model; goal is deterministic replay of engine logic only.

## Operator value

Operator discovers a live-soak governance surprise (e.g., Learn-Mode bias shifted a decision). Clicks Forensics drawer, scrubs to the frame in question, sees side-by-side original vs replayed decision deltas. Answers what changed in <1s without parsing logs or re-running soak. No model cost per investigation. Teaching tool: new operators study past complex L3/L4 escalations legibly. Audit trail: soak_forensics_opened event + operator notes persist, creating investigation record.

## Surfaces touched / added

- dashboard/server.py:/api/soak/replay/{recorded_session_uuid} (new GET endpoint)
- dashboard/ui-next/src/lib/components/SoakForensicsDrawer.svelte (new Svelte component, EXPERIMENTAL)
- tools/soak_driver.py:emit --record-session-uuid flag to cassette output
- src/stream_manager/decision_graph.py:snapshot-at-decision preservers (matched_hash + confidence only; L-level trajectory deferred to SOAK-2b)

## Feasibility

FEASIBLE. Endpoint architecture: (1) Soak_driver loads recorded cassette or replay-db. (2) Re-streams envelopes through fresh in-memory bus + governance engine with cassette-time settings. (3) For each frame captures (original_decision, replayed_decision, delta) triples. (4) Returns JSON to dashboard. (5) SoakForensicsDrawer renders static 3-column table. Decision_graph already exposes matched_hash and confidence; no new data-model work required for MVP. Deferred work (SOAK-2b): decision_graph.snapshot(frame_idx) design for L-level + confidence-trajectory inspection (blocks only the drill-down sub-feature, not MVP ship).

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS. Endpoint + UI component + soak_driver flag touch only intra-session state (original decision, replayed decision, delta columns). No new certPortal coupling beyond existing learn-mode source registry + project_context + agent_profiles. Forensics drawer is domain-agnostic: shows (reasoning_delta, layer_delta, matched_hash_delta) with no project-specific vocabulary.
- **Polarity (G2):** PASS. Endpoint guard: if session_id == SM_OWN_SESSION_ID, raise ValueError (mirroring EngineRegistry.get_or_create pattern at governance.py:1672-1679). Forensics drawer emits soak_forensics_opened event (audit-trail only, not governance decision). Feature is deterministic replay, not re-evaluation; does not make SM govern itself.
- **ADR-18 MUST floor:** PASS (ADR-18 / ADR-20 binding MUSTs M1-M9). Forensics pane is opt-in drawer (no auto-foreground). Paired label+color: '-- Forensics' label + visual badge (color not alone). Domain-agnostic: frame deltas only. Latency-neutral: static side-by-side render, no live model call. Non-goals correctly stated (no IDE, multiplexer, multi-tenant). 3-column layout is nice-to-have forensics UI (bends SHOULD, not MUST).
- **Frozen-surface note:** Replay endpoint re-streams through governance engine (governance.py line 1672+), which is FROZEN (ADR-18 Rule 1). No modifications to engine core logic. Cassette schema amendment is additive only (new optional recorded_session_uuid field); cassette itself is FROZEN per ADR-17 append-only constraint. No ADR amendment required.
- **New-envelope note:** Cassette schema amendment: optional recorded_session_uuid field added to soak_cassette_*.jsonl per ADR-17 additive rule. Same PR MUST include cassette_record.py emission of recorded_session_uuid + soak_driver.py recording of the field (both covered in PR 1 deliverables). Per ADR-18 new-envelope-rule: cassette schema extension ships with same-PR coverage.

## Grounding

- src/stream_manager/governance.py:1672-1679 (EngineRegistry.get_or_create polarity-flip guard)
- src/stream_manager/decision_graph.py:1-100 (Pattern + DecisionGraph structure; matched_hash, confidence fields)
- dashboard/server.py:77-192 (lazy-init bus/registry/engine_registry patterns)
- tools/soak_driver.py:1-100 (cassette load, envelope re-stream shape)
- tools/cassette_record.py:1-100 (existing cassette schema, kind enum)
- docs/adr/ADR-18-mvp-surface-freeze.md:Rule 1 + Rule 2 + Decommissioned (surface classification)
- docs/adr/ADR-20-ui-redesign-experimental-spike.md:M1-M9 (binding UI MUSTs)
- docs/adr/ADR-17-soak-tiers.md:Tier 1 replay + cassette schema (append-only)
- INTENT.md:UI / HITL principles (monitor-first, paired label+color, domain-agnostic)
- CLAUDE.md:Firewall + Zero contamination + Session-source exception rule
