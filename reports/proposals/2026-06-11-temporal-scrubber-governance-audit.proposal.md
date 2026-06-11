# Temporal Scrubber: Governance Policy Archaeology via Replay Diff

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (ux) 2026-06-11; idea WILDCARD-1; boldness SAFE; refute verdict CONSTRAIN; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

When an operator asks "why did we gate this differently on Tuesday vs today?", there is no time-travel surface. Governance decisions are logged to the message bus, but comparing two policy versions (L4 thresholds, mode ladders, static rules) or seeing how the engine behaved across a session timeline requires grepping CSV dumps or reconstructing mental state. This friction slows debugging, root-cause analysis, and trust-building in new policy changes.

## Proposal

Ship a bespoke temporal-scrubber panel reshaped to comply with ADR-18 constraints:

(1) UI RESHAPE (compliance: ADR-18 M1 three-frame presence): The scrubber renders as a MODAL overlay inside the AppShell escalation-foreground slot (M2), not a fourth persistent frame. The modal is triggered by a timestamp-range selector in the Frame A decision stream (existing REPL). When dismissed, Frame A returns to foreground; the three-frame presence (A/B/C) is never regressed. Content: two-pane replay diff showing decision verdicts at T1 vs T2 side-by-side, with a heat-map of confidence deltas and a policy-mutation timeline strand (when static rules or thresholds changed).

(2) BACKEND REPLAY (compliance: ADR-18 polarity, POLARITY violation remediation): The endpoint `/api/decisions/replay` (POST) accepts `session_id, time_window_start, time_window_end | policy_version_a, policy_version_b` and applies DUAL-KEY polarity filter BEFORE feeding messages to the replay graph:
  (a) SQL WHERE clause (durable): `messages.session_id IN (SELECT id FROM sessions WHERE project_slug NOT IN ('streamManager'))` -- excludes all SM-self sessions at query level.
  (b) Python read-time backstop: `session_id != BRIDGE_SM_SELF_SESSION_ID` check before rendering results.
  (c) Fail-loud: endpoint returns HTTP 400 if the filtered query returns zero rows AND `SM_OWN_SESSION_ID` is set.
  Replay graph is a shallow-copy of DecisionGraph (immutable snapshot), fed only non-SM messages, returning a decision stream (read-only, no bus writes, no engine mutation).

(3) INFRASTRUCTURE (compliance: NEW BUS ENVELOPE note): If a new bus envelope kind is introduced for policy-timeline events, cassette_record.py and soak_driver.py MUST be extended in the same PR to capture that envelope in test fixtures.

(4) POLICY VERSIONING (prerequisite infrastructure): A new FROZEN table `policy_snapshots` tracks when static rules or thresholds change:
  - `policy_snapshots(id, created_at, policy_hash, config_blob, change_log)` 
  - Populated on governance.py configuration mutation (additive to existing code path, never backfilled retroactively).
  - `/api/governance/policy-timeline` returns the snapshot history (GET, read-only). Initial release: timestamps + change_log text only. Future extension: full config_blob diffing. This endpoint is wired but ships with a documented "v2 policy diff roadmap" -- no dead-end endpoint.

(5) DESIGN MANDATE (ADR-18 freshness, freshness floor): All operator-facing text in the scrubber (confidence labels, mode ladder names, policy-change descriptions) must be rendered from CONFIG, never from domain-specific role names. A "policy-change" event like "threshold raised to 0.75" is domain-agnostic; a change like "engineer promotion logic changed" is NOT (the former ships, the latter defers).

(6) SESSION FILTER MANDATORY: The scrubber modal always displays a "monitored-project filter" dropdown prepopulated with all non-SM project_slugs from the past 7 days. Operator MUST explicitly select a project (or "all non-SM") before the replay fires. Default is locked to a sentinel empty state (no buttons enabled) until operator confirms filter. This is the human-readable enforcement of the polarity backstop.

## Operator value

Eliminates manual decision archaeology; builds operator confidence in new governance policies by showing side-by-side proof of behavior change; enables rapid root-cause analysis when an operator suspects a regression; creates an auditable narrative of why a particular message was handled differently across time or policy versions. Medium value because temporal comparison requires first establishing baseline confidence in the governance engine itself (prerequisite: ADR-18 FROZEN surfaces) and because policy-mutation timeline is advisory-only (human must verify change-log text). The core 2-pane replay diff is high-confidence; policy timeline is aspirational-assistance.

## Surfaces touched / added

- dashboard/ui-next/src/lib/components/TemporalScrubber.svelte (new modal component, constrained to M2 escalation slot, not a fourth frame)
- dashboard/ui-next/src/lib/components/FrameA_Sessions.svelte (add 'Replay' button to decision rows, triggers scrubber modal)
- dashboard/server.py: /api/decisions/replay (POST, SM-self polarity filter durable + Python backstop, shallow-copy replay graph, read-only)
- dashboard/server.py: /api/governance/policy-timeline (GET, policy_snapshots history, v1 change-log text only)
- src/stream_manager/decision_graph.py: shallow_copy_for_replay() method (immutable snapshot, no state mutation)
- src/stream_manager/message_bus.py: policy_snapshots table schema (FROZEN additive to existing schema, append-only)
- src/stream_manager/governance.py: configuration-mutation hook (emit policy_snapshot record on rule/threshold change, additive to existing hot path)
- tools/cassette_record.py + soak_driver.py: policy-timeline envelope coverage (if new envelope kind introduced, must add fixture coverage same PR)

## Feasibility

MEDIUM-HIGH. Core replay graph (shallow copy + re-feed) is straightforward (parallel to cassette_replay.py existing machinery, L=S). Polarity filter (SQL + Python backstop + fail-loud) is straightforward (L=S). Session-selector UI is standard modal pattern inside escalation slot (L=S). Policy versioning infrastructure requires a new durable table + hook (L=M, but additive, no FROZEN surface mutation). The constraint-critical risk is the modal-fit into AppShell: the escalation-foreground slot (M2) already reserves space for HITL synthesis + other transient overlays; a second consumer requires clear arbitration of space/z-order. HITL team owns that slot; a reshaped v2 requires design review with HITL but does not demand code changes to AppShell itself (slots are composable). Latency: `/api/decisions/replay` is a batch operation (T1:T2 time window, typically <100 messages) and runs off-verdict-path; acceptable for operator-initiated archaeology. BLOCK: None. Recommendation: phased: Phase 1 (v2.5 or later) ship v1 (2-pane diff, single session, no policy-timeline). Phase 2 (v2.6+) add policy-snapshots + timeline if demand signal surfaces.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS -- replay is read-only against gov.db messages table (no monitored-project code read). Time window + session filter allow operator to scope away from certPortal entirely if desired. No FIREWALL G1 entanglement.
- **Polarity (G2):** REMEDIATED per constraint -- dual-key filter (SQL WHERE + Python backstop) applied to ALL /api/decisions/replay operations. SM-self session exclusion is durable (WHERE clause in message_bus.py query) and read-time-guarded (Python filter + fail-loud on zero-row result). This surfaces the POLARITY-FAIL constraint as a user-visible modal-confirmation step (project selector locked until explicit operator pick), closing the governance-of-governance loop without operator surprise.
- **ADR-18 MUST floor:** COMPLIANT -- modal-in-M2-slot maintains ADR-18 MUST M1 (three-frame A/B/C presence guaranteed). Modal is transient (escalation-foreground pattern, same lifecycle as HITL alerts); when closed, Frame A returns to view. No fourth persistent frame. M2 escalation-only-foreground is honored (replay diff is not auto-escalated; operator must explicitly trigger via Frame A button).
- **Frozen-surface note:** No FROZEN surface mutation required. message_bus.py schema extends additively (policy_snapshots table, append-only). governance.py hook is additive (configuration-mutation event emission, no existing hot-path change). decision_graph.py gains shallow_copy_for_replay() method (new method, no public signature change). dashboard/server.py endpoints are new (/api/decisions/replay, /api/governance/policy-timeline). No amendment needed for core surfaces (AppShell, Frame.svelte, governance_call bus envelope, model_router bands).
- **New-envelope note:** CONDITIONAL: if a new bus envelope kind is introduced to carry policy-mutation timeline events (e.g., 'governance_policy_snapshot' or 'governance_threshold_change'), that envelope MUST be added to cassette_record.py fixture coverage and soak_driver.py envelope accounting in the same PR. Current proposal ships policy_snapshots as a durable table (not a transient bus event), so new envelope is NOT required for v1. If timeline feature is extended to emit real-time policy-change notifications (future, post-v2.5), that extension requires envelope + cassette coverage amendment.

## Grounding

- docs/adr/ADR-18-mvp-surface-freeze.md:1-100 (three-frame M1 guarantee, escalation M2 foreground, FROZEN surface rules)
- dashboard/ui-next/src/lib/components/AppShell.svelte:1-50 (M1 three-frame presence, escalation slot ownership)
- dashboard/ui-next/src/lib/components/Frame.svelte:1-30 (M2 flag-in-place vs escalation-foreground distinction)
- dashboard/ui-next/src/lib/stores/layout.js:24-36 (FRAME_KEYS exhaustive set, FRAME_META domain-agnostic)
- dashboard/server.py:589-620 (existing /api/decisions GET pattern, session_id filtering model)
- src/stream_manager/decision_graph.py:75-110 (DecisionGraph.observe() pattern, stateful graph mutation)
- tools/cassette_replay.py:68-100 (cassette replay loop, GovernanceEngine.evaluate() re-feed pattern)
- src/stream_manager/governance.py:306-450 (GovernanceEngine.evaluate() method, bus.record_decision() seam, routing attribution)
- docs/adr/ADR-18-mvp-surface-freeze.md:539-563 (Amendment D v10 P5 shadow infrastructure, mode-recording pattern for non-ship-criteria runs)
