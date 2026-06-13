# Time Machine: counterfactual governance replay in Settings drawer

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (flywheel) 2026-06-11; idea WILDCARD-2; boldness STRETCH; refute verdict CONSTRAIN; effort L.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

Operators cannot measure the blast radius of governance tuning changes retrospectively. When an operator overrides a decision or adjusts HITL settings (e.g., confidence floor 0.60 -> 0.50), the change applies prospectively only. There is no way to ask: 'Which decisions over the last 2 hours would have been DIFFERENT under the new config?' This blocks data-driven policy tuning and makes it impossible to audit counterfactuals ('we almost caught case X with this setting').

## Proposal

Add a Time Machine scrubber to the Settings drawer (FR-UI-9, ADR-20 EXPERIMENTAL ui-next path): a slider pair + play button that selects a time window (T0 to T1, default 1 hour), accepts a configuration delta (confidence floor, HITL mode, timeout, rate-limit thresholds), and **replays all decisions in that window under the modified config WITHOUT PERSISTING** (sandboxed test-only bus transaction). Results render in a diff matrix showing: decision_id | original action | replay action | affected? (RED if different, GREEN if same, GRAY if config knob doesn't apply). Clicking a row expands the reasoning delta. Operators can export the diff as an annotated report (markdown/PDF) for team review.

The replay re-uses the live `governance.evaluate()` API with a temporary config override via context manager (no FROZEN surface edits). New bus envelope kind `governance_decision_replay` carries replay diffs (tentatively `{kind, original_decision_id, original_action, replay_action, original_confidence, replay_confidence, config_delta_applied, affected: bool}`). Cost is a full re-evaluation loop (expensive, but off-band; max window 1 hour). M15/G2 enforced: the drawer's `selectedSessionId` binding ensures replay never targets the SM's own session.

## Operator value

Operators gain **counterfactual visibility** into governance tuning. Measure the exact impact of a threshold change before rolling it live (e.g., 'lowering confidence floor 0.60->0.50 catches 3 new BLOCK cases but releases 2 others'). Reduces review cycles on policy tweaks by making the data explicit. Laptop-first users benefit directly: one click to see before/after diffs over a configurable window, enabling faster iteration on HITL thresholds without trial-and-error on live sessions.

## Surfaces touched / added

- dashboard/ui-next/src/lib/components/SettingsDrawer.svelte (add Time Machine sub-panel under FR-UI-9)
- dashboard/ui-next/src/lib/components/TimeMachineReplay.svelte (NEW: slider pair + play button + diff matrix + export)
- dashboard/server.py (POST /api/time-machine/replay endpoint; accepts {config_delta, time_range_start, time_range_end}, returns decision diffs)
- src/stream_manager/governance.py (config override context manager for replay path; no schema edits, purely internal)
- src/stream_manager/message_bus.py (expose decision replay query and new governance_decision_replay envelope emission)
- tools/cassette_record.py (record governance_decision_replay envelopes in cassette)
- tools/soak_driver.py (replay-tier coverage for governance_decision_replay envelope)

## Feasibility

FEASIBLE. The API surface is straightforward: POST /api/time-machine/replay accepts config_delta + time_range, calls the existing decisions query (decisions table has all the fields needed: message_id, action, confidence, reasoning, timestamp), re-runs governance.evaluate() in a loop with a temp config override (context manager), and diffs the results. Message bus already exposes record_decision + decision queries. The UI uses existing SettingsDrawer structure + Svelte patterns (DecisionRow, Badge, slider). Latency: the re-evaluation is expensive (~O(window_size * evaluate_cost)), but runs off-band in the dashboard backend process without blocking hot paths. Max window 1 hour keeps memory/latency bounded per operator UX.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS. The proposal touches zero certPortal files or dependencies. Governance.py, message_bus.py, and server.py are SM-internal surfaces with no monitored-project coupling. The replay re-uses the live governance.evaluate() API without introducing cross-project vocabulary.
- **Polarity (G2):** PASS. The Time Machine sidebar sits in SettingsDrawer (FR-UI-9, ambient still-water panel per ADR-20 M2). It never foregrounds unless the operator opens it. The sandbox bus transaction never persists, and the selectedSessionId binding (SettingsDrawer line 96) explicitly enforces M15/G2: replay targets NON-SELF sessions only. No path exists for SM to monitor/govern its own session.
- **ADR-18 MUST floor:** PASS on all three-frame MUSTs (ADR-20 M1-M9, UI-DESIGN-SPEC M1-M19). (1) Presence: Time Machine is a deferred inspection tool in the Settings drawer (still-water ambient), never foregrounding unless user opens it. Monitor-first default preserved (M1). (2) Escalation-only foreground: Time Machine never auto-foregrounds; it's an operator opt-in inspection pane (M2). (3) Paired label+color badges: diff matrix uses text labels ('decision_id', 'original', 'replay', 'affected') + color (RED/GREEN/GRAY), never color alone per M5. A11y: slider pair + play button are native HTML controls with explicit labels (aria-label, aria-valuetext); focus management defers to SettingsDrawer's existing focus trap. Latency: pure post-hoc inspection, off the verdict hot path (M18 / latency budget untouched).
- **Frozen-surface note:** ZERO FROZEN surface edits. The config override mechanism is internal (governance.py context manager, no schema mutation). No ADR amendment required; the replay path is purely new, not a modification of frozen governance.evaluate() signature or message_bus.py record_decision schema. Message_bus.py amendment 2026-05-12 (governance_decision envelope FROZEN, metadata-only extensions thereafter) is satisfied: governance_decision_replay is a NEW envelope kind, not an extension of governance_decision.
- **New-envelope note:** BINDING CONSTRAINT: This proposal introduces a new bus envelope kind, `governance_decision_replay` (or similar). Per ADR-18 Rule 1 envelope schemas FROZEN + the NEW BUS ENVELOPE RULE stated in the refuter gate, shipping REQUIRES same-PR coverage in: (1) tools/cassette_record.py: add recording of governance_decision_replay envelopes to the cassette JSONL with schema {kind: 'governance_decision_replay', original_decision_id, original_action, replay_action, original_confidence, replay_confidence, config_delta_applied, affected, timestamp}. (2) tools/soak_driver.py: extend soak replay tier to exercise the governance_decision_replay envelope path (e.g., replay a subset of decisions with a config delta, verify the envelope is emitted + captured). (3) Envelope schema must be FROZEN immediately after first ship (metadata-only extensions thereafter per ADR-18 amendment 2026-05-12). Without cassette + soak coverage, the replay mechanism has no automated regression harness, violating feedback_cassette_must_cover_new_envelopes per the constraint.

## Grounding

- dashboard/ui-next/src/lib/components/SettingsDrawer.svelte:1-100 (FR-UI-9 panel structure, selectedSessionId binding at line 96)
- src/stream_manager/message_bus.py:658-732 (record_decision signature + governance_decision envelope schema, FROZEN per amendment 2026-05-12)
- src/stream_manager/governance.py:628-634 (confidence_floor applied to decisions)
- dashboard/server.py:1538-1650 (POST /api/hitl/settings pattern for server-scoped settings)
- tools/cassette_record.py:1-50 (envelope kind definition + _KIND_TO_LAYER mapping)
- tools/soak_driver.py:1-30 (soak load mix + cassette architecture)
- docs/adr/ADR-20-ui-redesign-experimental-spike.md:19-60 (MUST-floor M1-M9, three-frame invariants, still-water ambient)
- docs/adr/ADR-18-mvp-surface-freeze.md:39-92 (Rule 1 surface classification, FROZEN/EVOLVING/EXPERIMENTAL, envelope metadata-only extension precedent)
