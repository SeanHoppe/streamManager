# Recorded Session Replay Forensics: Operator Root-Cause Analysis via Side-by-Side Decision Deltas

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (flywheel) 2026-06-11; idea SOAK-2; boldness WILD; refute verdict CONSTRAIN; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

When a live soak discovers a regression or unexpected governance decision (e.g. a decision that was SUGGEST earlier but now shows GUIDE on replay), there is no fast path to replay that exact sequence of recorded envelopes frame-by-frame with full governance context. Operators must hand-parse logs or re-run entire soaks (consuming quota, time, and latency budget). The learn-mode ingest pipeline processes real `desktop_prompt` + `user_reply` pairs that synthetic load never exercises. Today there is no deterministic replay harness for real operator transcripts, blocking operators from validating governance behavior on recorded non-SM sessions and from detecting regressions in decision logic across code iterations.

## Proposal

Ship SOAK-2 as two focused PRs per refuter constraint (new-envelope-rule compliance). PR-1 delivers: (1) New `/api/soak/replay/{recorded_session_uuid}` endpoint (GET, dashboard/server.py) accepting optional frame range (start_idx, end_idx) and returning JSON array of forensics triples: [{ original_decision, replayed_decision, delta }]. Guard: if session_id == SM_OWN_SESSION_ID, raise ValueError (polarity-flip enforcement). (2) New SoakReplayForensicsDrawer.svelte component (dashboard/ui-next/src/lib/components/, EXPERIMENTAL per ADR-20) rendering three-column side-by-side diff: left=original decision (frame 1), middle=replayed decision (frame 2), right=delta (reasoning_delta, layer_delta, matched_hash_delta). Paired label+color, opt-in drawer under soak report card. (3) Emit soak_forensics_opened bus event (audit trail, no governance mutation). (4) Extend cassette schema: additive optional `recorded_session_uuid` field in soak_cassette_*.jsonl per ADR-17 append-only rule (v1.2 cassettes have zero UUID fields, backward compatible). Extend cassette_record.py to emit recorded_session_uuid. (5) Decision_graph snapshot helpers: preserve matched_hash + confidence at decision time (deferred live L-level/confidence-trajectory drill-down to future work, not MVP). Endpoint signature: `GET /api/soak/replay/{recorded_session_uuid}?start_idx=0&end_idx=60&session_id={session_id}`. Replay logic: soak_driver loads cassette, re-streams envelopes through fresh in-memory bus + governance engine (cassette-time settings), captures (original_decision, replayed_decision, delta) triples per frame, returns JSON. Replayed decision determinism is the load-bearing operator value: same inputs always produce same governance output across code iterations, enabling regression detection. PR-2 (paired cassette coverage): cassette_record.py extension to record recorded_session_uuid when cassette is generated, soak_driver.py extension to consume + replay it. Both PRs required in same merge to comply with new-envelope-rule (cassette schema amendment + soak driver coverage in same PR).

## Operator value

Operator discovers a live-soak governance surprise (Learn-Mode bias shifted a decision). Clicks Forensics drawer, scrubs to the frame in question, sees side-by-side original vs replayed decision deltas in <1 second without parsing logs or re-running soak (zero model cost per investigation). Enables root-cause analysis: isolates which field changed (reasoning vs layer vs matched_hash) and when. Teaching tool: new operators study past complex L3/L4 escalations legibly. Audit trail: soak_forensics_opened event + operator notes persist, creating investigation record. Fixture sharing: operators record real governance traffic from a live non-SM session (zero quota cost), snapshot it as a fixture, replay it offline deterministically, and share problematic transcripts with reviewers ('here is a session where the engine misbehaved').

## Surfaces touched / added

- dashboard/server.py:/api/soak/replay/{recorded_session_uuid} (new GET endpoint)
- dashboard/ui-next/src/lib/components/SoakReplayForensicsDrawer.svelte (new component, EXPERIMENTAL)
- tools/soak_driver.py: extend --replay mode to handle recorded_session_uuid cassette field
- tools/cassette_record.py: emit recorded_session_uuid to cassette schema (additive)
- src/stream_manager/decision_graph.py: snapshot helpers for matched_hash + confidence preservation (deferred: L-level trajectory drill-down)

## Feasibility

FEASIBLE. Endpoint architecture: (1) Soak_driver loads recorded cassette or replay-db. (2) Re-streams envelopes through fresh in-memory bus + governance engine with cassette-time settings. (3) For each frame captures (original_decision, replayed_decision, delta) triples. (4) Returns JSON to dashboard. (5) SoakReplayForensicsDrawer renders static 3-column table. Decision_graph already exposes matched_hash and confidence; no new data-model work required for MVP. Cassette schema amendment is purely additive (new optional recorded_session_uuid field); v1.2 cassettes replay unchanged with uuid = null. No architectural blocker. Test coverage: existing test_soak_replay.py patterns already exercise cassette load + envelope re-stream; extend with new field assertion. Soak_forensics_opened event is emitted client-side (opt-in drawer open), not requiring new cassette kind.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS. Endpoint + UI component + soak_driver flag touch only intra-session state (original decision, replayed decision, delta columns). No new certPortal coupling beyond existing learn-mode source registry + project_context + agent_profiles. Forensics drawer is domain-agnostic: shows (reasoning_delta, layer_delta, matched_hash_delta) with no project-specific vocabulary.
- **Polarity (G2):** PASS. Endpoint guard: if session_id == SM_OWN_SESSION_ID, raise ValueError (mirroring EngineRegistry.get_or_create pattern at governance.py:1672-1679). Forensics drawer emits soak_forensics_opened event (audit-trail only, not governance decision). Feature is deterministic replay, not re-evaluation; does not make SM govern itself. Recorded_session_uuid is durable key for non-SM sessions only; cassette schema excludes SM-self by construction.
- **ADR-18 MUST floor:** PASS (ADR-18 / ADR-20 binding MUSTs M1-M9). Forensics pane is opt-in drawer (no auto-foreground). Paired label+color: 'Forensics' label + visual badge (color not alone). Domain-agnostic: frame deltas only. Latency-neutral: static side-by-side render, no live model call. Non-goals correctly stated (no IDE, multiplexer, multi-tenant). 3-column layout is nice-to-have forensics UI (bends SHOULD, not MUST).
- **Frozen-surface note:** Replay endpoint re-streams through governance engine (governance.py line 1672+), which is FROZEN (ADR-18 Rule 1). No modifications to engine core logic. Cassette schema amendment is additive only (new optional recorded_session_uuid field); cassette itself is FROZEN per ADR-17 append-only constraint. No ADR amendment required.
- **New-envelope note:** Cassette schema amendment: optional recorded_session_uuid field added to soak_cassette_*.jsonl per ADR-17 additive rule. Same PR MUST include cassette_record.py emission of recorded_session_uuid + soak_driver.py recording of the field (both covered in PR-1 + PR-2 joint landing per refuter constraint feedback_cassette_must_cover_new_envelopes). soak_forensics_opened event is client-side audit emission, not a new bus envelope kind requiring cassette coverage. Per ADR-18 new-envelope-rule: cassette schema extension ships with same-PR cassette_record.py + soak_driver.py coverage (both PRs land together).

## Grounding

- src/stream_manager/governance.py:1672-1679 (EngineRegistry.get_or_create polarity-flip guard)
- src/stream_manager/decision_graph.py:1-100 (Pattern + DecisionGraph structure; matched_hash, confidence fields)
- dashboard/server.py:77-192 (lazy-init bus/registry/engine_registry patterns)
- tools/soak_driver.py:1-300 (cassette load, envelope re-stream shape, replay mode)
- tools/cassette_record.py:1-150 (existing cassette schema, kind enum, recorder pattern)
- tests/fixtures/soak_cassette_latest.jsonl:1-10 (live cassette structure; extend with recorded_session_uuid field)
- docs/adr/ADR-18-mvp-surface-freeze.md:Rule 1 + Rule 2 + Decommissioned (surface classification, FROZEN governance.py + cassette)
- docs/adr/ADR-20-ui-redesign-experimental-spike.md:M1-M9 (binding UI MUSTs)
- docs/adr/ADR-17-soak-tiers.md:Tier 1 replay + cassette schema (append-only constraint)
- tests/test_envelope_coverage.py:1-73 (cassette CI guard pattern; new envelope kinds require coverage)
- tests/test_soak_replay.py:existing (replay mode test patterns to extend)
- INTENT.md:UI / HITL principles (monitor-first, paired label+color, domain-agnostic)
- CLAUDE.md:Firewall + Zero contamination + Session-source exception rule
