# Ambient Soak Task -- Continuous polarity validation via background Cron

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (ux) 2026-06-11; idea SOAK-4; boldness WILD; refute verdict CONSTRAIN; effort L.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

Soak validation today is fire-and-forget: the operator runs `tools/soak_driver.py`, collects a report, manually inspects it. There is no continuous validation that governance polarity behaves correctly on live non-SM sessions. A stale session in the active list could silently accumulate a polarity leak (SM-self-monitoring regression) and no one would notice until ship-gate manual review. The gap is expensive: dormant leaks surface late, ship-gate unblocks them too slowly, and cycle discipline erodes. Real operators need low-friction continuous signal between ship-gates.

## Proposal

Ship a lightweight **Ambient Soak Task** as an **EXPERIMENTAL** feature (operator opt-in via settings toggle, disabled by default). The task is a background Cron job that runs every 30 minutes when enabled. Flow: (1) Query `/api/sessions?exclude_sm=true&order_by=last_message_at_desc&limit=1` (new query params, backward-compatible optional additions) to fetch the single most-recently-active non-SM session. If that session has produced >= 5 new message envelopes since last check, (2) spawn `tools/soak_driver.py --live-session <session-id> --duration 60 --mode ambient` in non-blocking background (CLI exits async after submission, no wait). (3) On completion, write a minimal **ambient report** (JSON summary: session_id, timestamp, polarity_pass, coverage_gaps) to `~/.sm-ambient/soak-<session-id>-<ts>.jsonl`, maintaining a rolling FIFO queue (10 reports, env-var override, FIFO eviction on overflow). (4) Parse the report; if polarity_violation or coverage_gap detected, emit a quiet bus event `ambient_soak_coverage_gap` (new envelope type, FROZEN at ADR-18) and flag it in the dashboard soak hub as a muted `MONITOR` badge (no foreground escalation, just a discrete note the operator can click to drill into the ambient history). The entire feature is **opt-in** (settings + Cron gate) so it never auto-runs on a fresh clone. Polarity logic (session_id NOT IN streamManager, session_id != self) is enforced in `soak_driver.py --mode ambient` via dedicated tests, NOT in the ambient task itself.

## Operator value

Continuous low-touch signal that governance polarity is not leaking on live traffic between ship-gates. Catches SM-self-monitor regressions hours/days before ship-gate review. The ambient JSONL history (rolled up when SOAK-3 lands) becomes a data source for the coverage-trend matrix, showing operators 'learn-mode path covered every 2h' vs 'never' over time. Early warning + trend visibility + zero manual soak-running overhead after first toggle flip.

## Surfaces touched / added

- dashboard/server.py: /api/sessions endpoint extension (new optional params exclude_sm, order_by, limit; backward-compatible)
- tools/soak_driver.py: --live-session, --duration, --mode ambient flags + ambient report writer (JSON to ~/.sm-ambient/) + polarity validation logic in ambient mode
- dashboard/ui-next/src/lib/components/SoakCoverageMatrix.svelte: (placeholder) ambient history drilldown panel (scoped to SOAK-3)
- src/stream_manager/message_bus.py: ambient_soak_coverage_gap envelope schema (FROZEN, cassette-tested)
- dashboard/server.py __main__ or ambient_soak_task.py: Cron job wiring (APScheduler or similar, opt-in via settings)
- Settings UI (FR-UI-9): Toggle 'Enable continuous session validation' (persisted to settings.json, default OFF)

## Feasibility

HARD (not infeasible). Requires 6 additive components: (1) API param extension + query logic, (2) new bus envelope type + cassette test, (3) ambient report writer + FIFO rotator + env-var config, (4) Cron scheduling + settings toggle, (5) soak_driver --mode flag + polarity logic, (6) dashboard badge + event subscription. None blocks the others. Implementation ~8--12 dev days in isolation. No dependency on SOAK-3 for baseline ship (SOAK-3 adds the trend-history UI). Risks: (a) ambient task spawns are fire-and-forget so failure mode is silent (mitigated: soak_driver --mode ambient is lower-overhead, tested separately); (b) FIFO rotation under concurrent writes needs lock or atomic rename (mitigated: use a dedicated .lock file or atomic fs ops); (c) polarity validation logic must be exact copy of CLI dispatch polarity check (mitigated: dedicate a testable function in soak_driver, call it from both CLI + ambient mode).

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS (no certPortal coupling introduced; data flow is SM -- non-SM sessions only, per G1 FIREWALL gate)
- **Polarity (G2):** PASS (G2 POLARITY: ambient task validates sessions with project_slug NOT IN {streamManager} AND session_id != self; no SM-self-monitoring enabled; polarity enforced in soak_driver.py --mode ambient, tested)
- **ADR-18 MUST floor:** PASS (ADR-18 MUSTs intact: 3-frame presence maintained; escalation-only foreground preserved via EXPERIMENTAL classification + muted MONITOR badge; paired label+color badge enforced via Badge.svelte contract; absolute HITL gate unaffected; domain-agnostic session filtering; a11y via Badge title/aria-label; latency budget unaffected for standard soak -- ambient mode is optional background task; non-goals: no IDE/multiplexer/multi-tenant expansion)
- **Frozen-surface note:** No FROZEN surfaces modified per ADR-18 scope. New envelope kind (ambient_soak_coverage_gap) is FROZEN from day one per CONSTRAINT-2. /api/sessions extension is additive optional params (backward-compatible). No changes to governance.py, message_bus.py (core schema), cli_governance.py (polarity logic is in soak_driver only), model_router.py, or cli_pool.py.
- **New-envelope note:** New envelope kind: ambient_soak_coverage_gap (payload: session_id, timestamp, polarity_violation_bool, coverage_gaps_list). CONSTRAINT-2 mandates cassette_record.py + soak_driver.py test coverage for this envelope on day-one ship. Test: soak_driver --mode ambient --cassette fixtures/ambient-soak-test.jsonl emits ambient_soak_coverage_gap when polarity drift detected, cassette recorder captures the envelope shape for replay validation.

## Grounding

- C:\Users\SeanHoppe\vs\streamManager\docs\adr\ADR-18-mvp-surface-freeze.md:1--90 (FROZEN surface classification, EXPERIMENTAL tier definition)
- C:\Users\SeanHoppe\vs\streamManager\tools\soak_driver.py:1--30 (existing soak infrastructure, envelope emission pattern)
- C:\Users\SeanHoppe\vs\streamManager\dashboard\server.py:721--756 (existing /api/sessions endpoint, query pattern)
- C:\Users\SeanHoppe\vs\streamManager\src\stream_manager\message_bus.py:52--58 (sessions table schema with project_slug)
- C:\Users\SeanHoppe\vs\streamManager\dashboard\ui-next\src\lib\components\Badge.svelte:1--43 (M4 paired label+color contract, MONITOR variant extensibility)
- C:\Users\SeanHoppe\vs\streamManager\src\stream_manager\governance.py:1--100 (Mode enum, polarity enforcement patterns)
