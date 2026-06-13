# Soak Coverage Matrix (Governed Sessions Only)

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (ux) 2026-06-11; idea SOAK-3; boldness SAFE; refute verdict CONSTRAIN; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

Synthetic soak (Tier 1.5/3) and live non-SM-session soak exercise different code paths. Polarity, Learn-Mode, and JsonlTailWorker exist only in the non-SM path. The audit (#112 chain) surfaced this coverage gap, but operators have no UI to see which subsystems are covered by which soak tier. Today's workaround is ad-hoc coverage spreadsheets. Operators ship blind on whether all paths are ship-gate-ready.

## Proposal

Add a new **Soak Coverage Matrix** dashboard pane (right-column slide-out, informational-only) that renders coverage for **non-SM governed sessions only**. Matrix structure: rows = code paths/subsystems (cli_pool sends, cassette playback, engine.evaluate, JsonlTailWorker tail envelopes, polarity filter, Learn-Mode categorizer), columns = Tier 1 / Tier 1.5 / Tier 2 / Tier 3 / Live-Session. Cells marked green if that tier exercises that path (inferred from soak report telemetry: `cli_pool_send_ms > 0`, `cassette_record playback count > 0`, `engine.evaluate calls`, `JsonlTailWorker events count`, `polarity filter applied count`, `learn_mode_categorizer fired count`). Blank cells are red + warning tooltip. Bottom section lists highest-priority uncovered paths (e.g. 'polarity + learn-mode + tail' = P0 if all three missing). Pane is populated from lightweight `/api/soak/coverage-matrix` endpoint that aggregates last N soak reports + live-session soaks, with an explicit filter: `project_slug NOT IN {streamManager} AND session_id != self` (mirroring governance.py:1676 self-monitor gate). Operator action: click "Generate coverage report" to emit structured JSON (via `/api/soak/coverage-report/generate`) feeding v2.9+ shadow-stabilization decision per ADR-18 Amendment C. No model calls; pure telemetry aggregation. The pane is informational (coverage gaps are insights, not action-blocking escalations), so no auto-foreground, no 4th frame. Fits within 3-frame guarantee + escalation-only foreground MUSTs.

## Operator value

Operator sees at a glance which subsystems are ship-gate-ready (all tiers + live green) vs which have coverage gaps. Closes the audit loop: INTENT.md states "real live soak validates"; this surfaces exactly which parts of "real" are covered. Eliminates ad-hoc spreadsheets. Feeds deterministic v2.9+ shadow-stabilization gate with ground-truth coverage data.

## Surfaces touched / added

- dashboard/ui-next/src/lib/components/SoakCoverageMatrix.svelte (new; EXPERIMENTAL)
- dashboard/server.py:/api/soak/coverage-matrix?days=7&exclude_streammanager=true (new endpoint; additive to server.py)
- dashboard/server.py:/api/soak/coverage-report/generate (new endpoint; POST; generates JSON for v2.9+ shadow-stabilization)
- tools/soak_driver.py:telemetry aggregation layer (additive; does NOT require new bus envelope if data stays in existing soak_reports table)
- docs/adr/ADR-18-mvp-surface-freeze.md (zero changes; POLARITY gate enforcement is endpoint-level, not ADR amendment)

## Feasibility

FEASIBLE. Proposal relies on (a) existing soak_driver.py / cassette_record.py telemetry collection (wired); (b) new lightweight aggregation endpoint (pure SQL join + filter over existing soak_reports table, no new model calls); (c) SoakCoverageMatrix.svelte as a new EXPERIMENTAL UI component (additive to ui-next stack, no FROZEN surface touched); (d) coverage-report JSON generator (lightweight schema following ADR-18 Amendment C structure). No architectural blocker. Self-monitor gate is enforced in the endpoint filter (SQL WHERE clause + runtime assertion on project_slug/session_id).

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS. Zero new references to certPortal beyond already-designed learn-mode source registry, project_context, agent_profiles. Monitored-project vocab is domain-agnostic soak tiers (Tier 1/1.5/2/3/Live-Session), not JOB-ID or role-hardcoding. No Z11-contamination.
- **Polarity (G2):** PASS (CONSTRAINED). Explicit filter in /api/soak/coverage-matrix endpoint enforces `project_slug NOT IN {streamManager} AND session_id != self` (line-for-line mirror of governance.py:1676 self-monitor gate). Proposal surfaces only coverage for non-SM governed sessions. Surfaces list explicitly clarifies Live-Session = live sessions of GOVERNED projects, not SM itself. SoakCoverageMatrix.svelte docstring documents: 'Renders coverage for non-SM sessions only per ADR-18 POLARITY gate.' SM's own session is structurally excluded from all aggregation + live-soak tracking.
- **ADR-18 MUST floor:** PASS (RESPECTS ALL MUSTS). (1) 3-frame PRESENCE MUST M1 unbent: pane is right-column slide-out (optional secondary view), not a 4th frame. A/B/C frames remain guaranteed present. (2) Escalation-only foreground MUST: pane is informational-only (coverage insights, not action-required blocks). No auto-foreground, no escalation trigger. Paired label+color badges are out of scope (matrix cells already show label 'Tier 1'/'green' together; not color-only). ADR-18 MUST floor fully respected.
- **Frozen-surface note:** Zero FROZEN surface touched. Proposal is purely additive: new endpoint /api/soak/coverage-matrix + /api/soak/coverage-report/generate (not FROZEN governance/message_bus/cli_governance/model_router/cli_pool surfaces), new component SoakCoverageMatrix.svelte (ui-next EXPERIMENTAL), new lightweight aggregation layer. No edits to governance.py, message_bus.py, cli_governance.py, model_router.py, cli_pool.py. No ADR amendment required.
- **New-envelope note:** NEW BUS ENVELOPE RULE applies if proposal emits a new bus envelope kind. Proposal description lists 'tools/soak_driver.py: emit telemetry `coverage_signals` in report JSON' which suggests new envelope. CONSTRAINT: if this envelope ships, same-PR cassette_record.py + soak_driver.py coverage is MANDATORY per ADR-18 L128 ('new bus envelope kinds require same-PR cassette + soak coverage'). If coverage is not added in same PR, proposal BLOCKS until coverage lands. Alternatively, soak telemetry may be emitted into existing envelope schemas (e.g. metadata-only extension to `soak_run` or cassette envelope) to avoid new-envelope overhead; that path requires no cassette amendment. Recommend: aggregate telemetry via SQL without emitting a new envelope kind in v1 (pure data layer, no bus change).

## Grounding

- src/stream_manager/governance.py:1676 (SM_OWN_SESSION_ID self-monitor gate)
- docs/adr/ADR-18-mvp-surface-freeze.md:ADR-18 Rule 1 FROZEN classification table (governance.py, message_bus.py, cli_governance.py, model_router.py, cli_pool.py all FROZEN; ui-next EXPERIMENTAL; dashboard/server.py EVOLVING)
- docs/adr/ADR-18-mvp-surface-freeze.md L77-80 (3-frame PRESENCE MUST M1; escalation-only foreground MUST)
- INTENT.md L54 ('SM MUST NOT gate one agent based on another's completion state'; self-monitor boundary)
- dashboard/ui-next/src/lib/components/Frame.svelte:L2-70 (3-frame guarantee + escalation-only foreground + Frame.svelte refuse-to-auto-foreground-unless-escalated structure)
- tools/soak_driver.py L128 (NEW BUS ENVELOPE RULE: cassette + soak coverage required for new envelope kinds)
