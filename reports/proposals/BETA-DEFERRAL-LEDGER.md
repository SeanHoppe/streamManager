# BETA proposals -- ship / defer ledger (2026-06-11)

Operator directive (/goal 2026-06-11): build BETA (toggleable) features from
`reports/proposals/PROPOSALS-INDEX.md` -- all 49 are optional, default-OFF, with
the ability to be promoted to permanent one day. Pilot **batch-1 = 15
SHIP-PROPOSAL** proposals; document everything we do NOT ship in batch-1 here
(operator note, AskUserQuestion 2026-06-11).

ASCII-only. Counts pinned: 49 total = 15 SHIP-PROPOSAL + 27 CONSTRAIN + 7 no-verdict.
In scope as features this initiative = 46 (49 minus 3 process-only: #6 / #20 / #39).

---

## SHIPPING NOW -- batch-1 (15 SHIP-PROPOSAL)

Built behind a BETA toggle (default OFF) via the `sm-proposal-research` ->
mockup-gate -> `sm-proposal-build` pipeline. Listed for completeness; full
treatment in `docs/2026-06-11-beta-proposals-initiative.md`.

| # | Proposal | File |
|---|---|---|
| 4 | Away/Calm Mode + Activity Summary Replay | `2026-06-11-away-mode-activity-summary.proposal.md` |
| 10 | Coverage Analyzer dashboard widget | `2026-06-11-coverage-analyzer-dashboard.proposal.md` |
| 12 | Decision Oracle: inline pattern pedigree | `2026-06-11-decision-oracle-pattern-provenance.proposal.md` |
| 14 | Escalation Timeline heatmap | `2026-06-11-escalation-timeline-heatmap.proposal.md` |
| 15 | HITL bulk-dismiss triage modal | `2026-06-11-hitl-bulk-dismiss-triage.proposal.md` |
| 16 | Frame D: Live Session Soak Control Panel w/ Polarity Audit | `2026-06-11-live-session-soak-with-polarity-audit.proposal.md` |
| 18 | Operator Co-Pilot Confidence Chip | `2026-06-11-operator-confidence-chip.proposal.md` |
| 19 | Pattern Velocity Heatmap | `2026-06-11-pattern-velocity-heatmap.proposal.md` |
| 22 | Quick-Filter Presets (FR-UI-9) | `2026-06-11-quick-filter-presets-fr-ui-9.proposal.md` |
| 25 | Session-per-Agent Pinning swim-lane | `2026-06-11-session-agent-pinning-swim-lane.proposal.md` |
| 31 | Durable session event cursor | `2026-06-11-session-event-append-stream.proposal.md` |
| 32 | Session health digest endpoint | `2026-06-11-session-health-digest-api-flywheel.proposal.md` |
| 34 | Per-session health sparklines | `2026-06-11-session-health-sparklines-confidence-throughput.proposal.md` |
| 46 | Operator-driven stale session cleanup (soft-delete + restore) | `2026-06-11-stale-session-cleanup.proposal.md` |
| 49 | What Changed Digest (page-focus synthesis) | `2026-06-11-what-changed-digest-page-focus.proposal.md` |

---

## NOT SHIPPING in batch-1 -- DEFERRED (34)

### Group A -- batch-2 candidates: CONSTRAIN verdict (27)

Bold ideas the adversarial refute pass marked **CONSTRAIN** (compliant only with
named constraints binding). Deferred so batch-1 proves the pipeline first.
**Revisit trigger:** batch-1 ships green (backend + Playwright --headed PASS) AND
operator elects a batch-2 frame.

| # | Proposal | Deferral note |
|---|---|---|
| 2 | Ambient Soak Task (background Cron) | Cron-driven soak; needs ambient-task lifecycle + polarity guard wired first. |
| 3 | Bulk-dismiss toolbar (async HITL cleanup) | Overlaps #15 (batch-1); fold in after #15 lands to avoid duplicate triage surface. |
| 5 | Breach Cartography (temporal causation UI) | Heavy new visualization; constrained to read-only causal view. |
| 7 | Dashboard Stale Session Cleanup (auto+manual) | Overlaps #46 (batch-1); reconcile against #46 soft-delete model. |
| 9 | Confidence Heat Map grid (Frame B) | New pane; constrained to role x time-bucket read. |
| 11 | Cross-session pattern audit + applicability APIs | New API surface; constrain to additive read endpoints. |
| 13 | Escalation Timeline forensic causal-chain | Superset of #14 (batch-1 heatmap); land #14 first. |
| 17 | Operator Co-Pilot one-tap ranked affordances | Action macros; constrain to advisory (never auto-act). |
| 23 | Recorded Session Replay Forensics | Side-by-side decision deltas; needs replay store first. |
| 26 | Session checkpoint versioning | New persistence; constrain to read snapshots. |
| 27 | Stale Session Cleanup (dual-key polarity fix) | Overlaps #46; merge polarity-fix detail into #46 impl. |
| 28 | Per-session confidence sparkline (SessionPicker) | Overlaps #34 (batch-1); reconcile sparkline component. |
| 29 | Session Delta Digest (Monitor Frame) | Overlaps #49 (batch-1 What-Changed); land #49 first. |
| 30 | Session DNA Heatmap (cross-pattern topology) | New viz; constrain to read topology. |
| 33 | Session health digest endpoints (multi-session triage) | Overlaps #32 (batch-1); extend #32 endpoint, do not fork. |
| 35 | Session housekeeping API (bulk-purge + cascade) | Mutation-heavy; constrain to soft-delete (pairs #46). |
| 36 | Session Picker favorites + filters + hotkey | Overlaps #22 (batch-1 presets); extend #22. |
| 37 | Session Story narrative-arc panel | New pane; constrain to read narrative. |
| 38 | Shadow Soak Audit Lane (polarity-safe) | Pairs #16 (batch-1 soak panel); land #16 first. |
| 40 | Live Non-SM Session Soak Dashboard Harness | Pairs #16; needs live non-SM session (#r1) to soak. |
| 41 | Live-soak replay forensics (MVP tier) | Pairs #16/#40; needs soak store. |
| 42 | Soak Coverage Matrix (governed sessions only) | Pairs #16; read matrix over soak runs. |
| 43 | Session soak_id + soak_metadata tagging | Schema-adjacent; additive tag columns, pairs #16. |
| 44 | Sonification as escalation confirmation layer | Audio layer; constrain to derived (never primary) signal. |
| 45 | Spatial Session Overview sidebar (right-rail) | New layout mode; constrain to coexist (no displace 3-frame). |
| 47 | Temporal Scrubber (policy archaeology replay) | Replay diff; needs policy-version store. |
| 48 | Time Machine (counterfactual governance replay) | Counterfactual engine; constrain to read replay in Settings drawer. |

### Group B -- batch-3 candidates: no-verdict gap-fill features (4)

Hand-authored gap-fills lacking an adversarial refute verdict; real
functionality but unranked. **Revisit trigger:** after batch-2, OR operator
priority signal. Each needs a refute pass before it enters the pipeline.

| # | Proposal | Deferral note |
|---|---|---|
| 1 | ALLOW-pattern auto-graduation (learn-mode -> static rule) | WILD; touches learn-mode + rule store; needs operator-confirm UX + refute pass. |
| 8 | Confidence-calibration loop ("confidence" means something) | Touches confidence semantics; cross-cuts many panes; sequence after read-only features land. |
| 21 | Policy-preview chip ("what will governance do") | Needs corpus-preview compute; refute pass for polarity (must not eval SM-self). |
| 24 | Regret-mining override loop | Closes operator-override feedback loop; touches `hitl_overrides`; refute pass needed. |

### Group C -- NOT features (process/doc only) -- never enter the BETA pipeline (3)

These are internal refactor / doc-clarification proposals, not end-user features.
They route to normal SM dev (or are already addressed), NOT the proposal->feature
BETA pipeline. Listed so the denominator stays honest (46 feature proposals, not 49).

| # | Proposal | Disposition |
|---|---|---|
| 6 | Replace `run_shadow` `bus._conn` poke with test-only insert helper | Test-harness refactor. Route to normal dev; partially covered by `project_bus_public_seams.md` (public `fetch_rows`/`execute_write` seams already exist). |
| 20 | Clarify CLAUDE.md L35-42 dual-key write/read split | Doc clarification. Already landed (CLAUDE.md polarity section + `project_polarity_read_filter_split.md`). CLOSED. |
| 39 | Single Source of Truth -- determination + lightest mechanism | Architecture determination doc. Route to normal dev / ADR, not a UI feature. |

---

## BATCH-2 disposition (2026-06-11, operator decision)

Batch-2 research produced 27 mockups (0 blocked). Operator chose: build the ~14
genuinely-NEW proposals (constrained-additive); mark the ~13 that overlap an
already-shipped batch-1 feature as **COVERED BY BATCH-1** (functionality shipped
via the canonical member -- no redundant BETA flag).

### Batch-2 BUILDING (14 new, constrained-additive)

ambient-soak-task (#2), breach-cartography-constrained (#5), confidence-heatmap-pane
(#9), cross-session-pattern-audit-apis (#11), escalation-timeline-causal-forensics
(#13), operator-co-pilot-gesture-macros (#17), recorded-session-replay-forensics
(#23), session-checkpoint-versioning (#26), session-dna-heatmap-cross-pattern-topology
(#30), session-story-panel-narrative-arc (#37), sonification-escalation-layer (#44),
spatial-session-sidebar (#45), temporal-scrubber-governance-audit (#47),
time-machine-governance-replay (#48).

### Batch-2 COVERED BY BATCH-1 (13 overlaps -- not re-built)

| Batch-2 proposal | Covered by batch-1 |
|---|---|
| async-hitl-bulk-dismiss (#3) | hitl-bulk-dismiss (#15) |
| cleanup-stale-sessions (#7) | stale-cleanup (#46) |
| session-cleanup-dual-key-polarity (#27) | stale-cleanup (#46) |
| session-housekeeping-api (#35) | stale-cleanup (#46) |
| session-confidence-sparkline (#28) | health-sparklines (#34) |
| session-delta-digest-monitor-frame (#29) | what-changed (#49) |
| session-health-digest-api (#33) | health-digest (#32) |
| session-quick-filter-presets (#36) | quick-filters (#22) |
| shadow-soak-lane-audit-refactored (#38) | soak-panel (#16) |
| soak-1-live-session-shadow-harness (#40) | soak-panel (#16) |
| soak-2a-replay-forensics-mvp (#41) | soak-panel (#16) + recorded-replay (#23) |
| soak-coverage-matrix-excluded-sm (#42) | soak-panel (#16) + coverage-analyzer (#10) |
| soak-session-metadata-tagging (#43) | soak-panel (#16) |

## Notes

- "Default OFF" is load-bearing: every shipped BETA feature is gated by the BETA
  flag registry and renders nothing until the operator toggles it on at the UI
  level (Settings drawer -> BETA panel). Promotion to permanent (flag removed,
  always-on) is a later, separate v2.x cycle decision per feature.
- Overlap clusters flagged above (HITL triage #3/#15; stale-cleanup #7/#27/#35/#46;
  health digest #32/#33; sparklines #28/#34; soak #16/#38/#40/#41/#42/#43;
  presets #22/#36; what-changed/delta #29/#49; escalation #13/#14) are intentional
  -- batch-1 lands the canonical member; batch-2 EXTENDS it rather than forking a
  parallel surface. The build pipeline's union-find partitioner keeps same-file
  work serial to prevent collision.
