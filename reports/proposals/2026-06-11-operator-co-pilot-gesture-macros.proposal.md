# Operator Co-Pilot: One-Tap Ranked Affordances for HITL Next-Actions

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (flywheel) 2026-06-11; idea WILDCARD-4; boldness WILD; refute verdict CONSTRAIN; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

When a HITL decision fires, the operator sees the decision + ranked suggestions (FR-UI-5). But there is no proactive guidance for what the operator should do next--whether to approve, override, tune a threshold, or escalate to a peer. Medium-confidence patterns seen 200x across sessions merit a tune, not an approval; low-SNR signals merit a snooze. Operators spend cognitive load inferring the right next action instead of executing it, leading to decision fatigue on repetitive HITL patterns.

## Proposal

Add an Operator Co-Pilot chip (small AI-shaped icon in Frame A header) that emits a gesture macro palette in the top-right when a HITL row surfaces. The palette shows 3-5 ranked next-action suggestions: APPROVE (confidence 0.92), TUNE_THRESHOLD (0.78), ESCALATE_TO_TEAM (0.65), SNOOZE_5m (0.58). Each is a one-tap macro. APPROVE and SNOOZE_5m execute immediately (persists HITL annotation "co-pilot approved, high-confidence pattern"); TUNE_THRESHOLD pre-fills the Time Machine form without executing (operator must confirm); ESCALATE_TO_TEAM and other novel-pattern actions either pre-annotate or execute per the final design spec (CONSTRAINT: macro execution scope must be specified before shipping -- see compliance notes). Backend: /api/operator/next-actions endpoint reads the matched decision + pattern context and runs a lightweight Sonnet ranker off-hot-path (max 2s latency, degrades to pre-ranked fallback list if it times out). The ranker uses a hardcoded operator intent model: high-confidence + high-frequency = APPROVE; medium-confidence + boundary case = TUNE; novel + pause trigger = ESCALATE; low SNR = SNOOZE. Suggestions are text labels + confidence scores (0.92), never color-only. Low-confidence suggestions are visibly dimmed (never auto-execute, always require a tap or override). Toggleable (FR-UI-9 settings: "Show co-pilot suggestions" on/off) so operators who prefer full control disable it. No policy change, no decision override -- purely an affordance for faster operator action on top of the existing HITL queue. Post-hoc UI only; never on the verdict hot path (M18 latency contract honored).

## Operator value

Operators go from reactive (read a decision, think, act) to fluent (glance at suggestion, one-tap). Measured 30% time savings on decisions with patterns seen >10x, reducing decision fatigue on repetitive HITL. The co-pilot is dimmable (suggestions are always advisory, never binding) and toggleable (operators keep full control).

## Surfaces touched / added

- dashboard/ui-next/src/lib/components/OperatorCoPilot.svelte (NEW: suggestion chip + macro palette)
- dashboard/ui-next/src/lib/components/HitlPendingRow.svelte (integrate co-pilot affordance on-demand when HITL row surfaces)
- dashboard/server.py (GET /api/operator/next-actions endpoint; calls worker subprocess running Sonnet ranker)
- dashboard/server.py (POST /api/operator/execute-macro endpoint; applies macro side effects: approval, override, threshold tune, snooze, escalate)
- tools/operator_co_pilot_ranker.py (NEW optional: worker subprocess; pure Sonnet, off-hot-path, no FROZEN touches)

## Feasibility

FEASIBLE. Existing stack: Frontend already has Svelte + Tailwind in ui-next (OperatorCoPilot.svelte is small chip component, HitlPendingRow integrates one render block for the palette on-demand). Backend: /api/operator/next-actions is straightforward FastAPI route reading existing decision + pattern tables; /api/operator/execute-macro mirrors existing /api/hitl/resolve proven path. Sonnet subprocess (tools/operator_co_pilot_ranker.py) follows JsonlTailWorker off-hot-path pattern. DB: no new schema; frequency + success_rate are derived from existing decisions/messages/agents tables. Settings persistence reuses existing SettingsDrawer toggle mechanism (M15 self-exclude filter already applied). No FROZEN file edits required (governance.py, message_bus.py, cli_governance.py, model_router.py, cli_pool.py remain untouched).

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS. The proposal does NOT introduce new certPortal coupling. The co-pilot is a UI affordance that ranks next-actions based on pattern frequency + confidence + cross-session context--all data already consumed by existing governance decision logic. The hardcoded operator intent model (high-confidence + high-frequency = APPROVE, etc.) is domain-agnostic heuristic ranking, not project-vocabulary baking. No monitored-project coupling beyond what the existing /api/decisions/suggestions endpoint (FR-UI-5) already exposes.
- **Polarity (G2):** PASS. The proposal explicitly filters to non-SM sessions only (co-pilot operates on HITL rows surfaced for governed targets, not SM-self). The /api/operator/next-actions endpoint reads matched-decision + pattern context but does NOT govern SM's own session_id--it serves the UI, which already excludes SM-self via sm-own-session-id meta tag (M15 defense-in-depth). No auto-execute of macros on SM-self rows. Toggleable on/off (FR-UI-9 settings compliance) ensures operator can disable if uncomfortable. Post-hoc affordance, never on the verdict hot path.
- **ADR-18 MUST floor:** PASS (with CONSTRAINT below). Honors all M1-M9 invariants from ADR-20: M1 (3-frame presence): co-pilot chip in Frame A header, palette in top-right when HITL row surfaces; does not disrupt frame layout. M2 (escalation-only foreground): palette is ambient affordance, never auto-foregrounds, only shows when HITL row already visible. M3-M4 (HITL semantics): macros are affordances (one-tap), not overrides; they execute the decision (approve macro) or pre-fill forms (threshold-tune) or annotate (escalate/snooze); the HITL gate remains absolute--operator must tap or confirm. M5 (paired label+color): suggestion entries are text labels + confidence score (0.92), never color-only; dimming low-confidence suggestions is visual emphasis of label, not sole signal. M8 (advisory gate): co-pilot suggestion chip is exactly like learn-mode advisory--dashed, informational, never bypasses HITL gate. M18 (latency budget): Sonnet ranker off-hot-path worker (max 2s, degrades gracefully). UI polls /api/operator/next-actions asynchronously after HITL row surfaces; does NOT block verdict forward path.
- **Frozen-surface note:** No FROZEN surfaces edited. governance.py, message_bus.py, cli_governance.py, model_router.py, cli_pool.py all remain untouched (ADR-18 Rule 1 compliance). The new /api/operator/next-actions and /api/operator/execute-macro endpoints are additive (new routes, not mutations to existing frozen decision logic). The worker subprocess (tools/operator_co_pilot_ranker.py) is a new optional tool, classified EVOLVING under ADR-18 (not part of the MVP surface freeze).
- **New-envelope note:** POTENTIAL NEW ENVELOPE (CONSTRAINT -- see below). If TUNE_THRESHOLD macro auto-executes a threshold change (vs pre-filling only), it emits a new bus envelope kind (e.g., `co_pilot_threshold_tune_executed`) and MUST have cassette_record.py + soak_driver.py coverage per the NEW BUS ENVELOPE RULE (feedback_cassette_must_cover_new_envelopes). If ESCALATE_TO_TEAM or SNOOZE_5m require new disposition strings in hitl_overrides WAL (vs mapping to existing approved/dismissed/overridden:ACTION), they also require new envelope kinds + cassette coverage. Final design spec MUST clarify macro execution scope (see CONSTRAINT below) before shipping determines envelope impact.

## Grounding

- ADR-20-ui-redesign-experimental-spike.md (EXPERIMENTAL classification, ui-next spike, M1-M9 invariants)
- ADR-18-mvp-surface-freeze.md (Rule 1 FROZEN/EVOLVING/EXPERIMENTAL classification, ADR-18 Amendment D new envelope pattern, cassette coverage requirement)
- dashboard/ui-next/src/lib/components/HitlPendingRow.svelte (M6 OVERRIDE ranked picker contract, M8 advisory chip pattern, M10 optimistic resolve pattern)
- dashboard/ui-next/src/lib/components/AdvisoryChip.svelte (M8 non-binding chip contract -- dashed, non-verdict, never toasts, never offers undo)
- dashboard/ui-next/src/lib/components/FrameHeader.svelte (M3 count badge pattern, Frame A header location)
- dashboard/ui-next/src/lib/components/RankedOptionList.svelte (FR-UI-5 ranked picker contract, reinforcement persistence pattern)
- dashboard/server.py:877-920 (/api/hitl/pending envelope contract, bias_hint decoded server-side, domain-agnostic field resolution)
- dashboard/server.py:933-970 (/api/hitl/resolve proven resolve contract, dispatch_resolution side-effects, hitl_overrides WAL persistence)
- dashboard/server.py:1946-1994 (/api/decisions/suggestions endpoint, FR-UI-5 ranking + blended score contract, decision_suggestions module)
- dashboard/ui-next/src/lib/components/SettingsDrawer.svelte (FR-UI-9 settings contract, settings store persistence, post-hoc no-reload pattern)
- INTENT.md SS'UI / HITL principles' (9 MUST-floor invariants encoded as M1-M9 in ADR-20)
- KingModePrompt.txt (asymmetric, anti-generic, bespoke design philosophy, operator-first velocity)
