# Proposals index -- 2026-06-11 (directives #5/#6 + follow-ups E/F)

**49 proposals** in `reports/proposals/`, produced by two `sm-ux-propose` workflow passes (UX/comforts + data-flywheel; 0 killed across 42 refuted ideas) plus 5 hand-authored to fill gaps the fixed lanes diluted (SOT determination + the 4 core flywheel concepts). Each carries a full firewall/polarity/ADR-18-MUST/frozen-surface/new-envelope compliance block. ASCII-only.

> All are EXPERIMENTAL-spike proposals: a written brief authorizes NO FROZEN-surface edit. Shipping any is a normal v2.x cycle frame.

| # | Proposal | Bold | Verdict | File |
|---|---|---|---|---|
| 1 | ALLOW-pattern auto-graduation (learn-mode -> static rule, operator-confirmed) | WILD | -- | `2026-06-11-allow-pattern-auto-graduation.proposal.md` |
| 2 | Ambient Soak Task -- Continuous polarity validation via background Cron | WILD | CONSTRAIN | `2026-06-11-ambient-soak-task.proposal.md` |
| 3 | Bulk-dismiss toolbar for async HITL queue cleanup | SAFE | CONSTRAIN | `2026-06-11-async-hitl-bulk-dismiss.proposal.md` |
| 4 | Away/Calm Mode + Activity Summary Replay for SSE Operators | STRETCH | SHIP-PROPOSAL | `2026-06-11-away-mode-activity-summary.proposal.md` |
| 5 | Breach Cartography: Temporal Decision Causation UI (Constrained v1) | WILD | CONSTRAIN | `2026-06-11-breach-cartography-constrained.proposal.md` |
| 6 | Proposal: replace `run_shadow`'s direct `bus._conn` poke with a test-only insert helper | -- | -- | `2026-06-11-cassette-shadow-bus-internals.proposal.md` |
| 7 | Dashboard Stale Session Cleanup (Auto + Manual) | STRETCH | CONSTRAIN | `2026-06-11-cleanup-stale-sessions.proposal.md` |
| 8 | Confidence-calibration loop: make "confidence" mean something | STRETCH | -- | `2026-06-11-confidence-calibration-loop.proposal.md` |
| 9 | Add Confidence Heat Map grid pane to Frame B (role x time-bucket trend spotting) | STRETCH | CONSTRAIN | `2026-06-11-confidence-heatmap-pane.proposal.md` |
| 10 | Coverage Analyzer dashboard widget (Frame D sub-section) | SAFE | SHIP-PROPOSAL | `2026-06-11-coverage-analyzer-dashboard.proposal.md` |
| 11 | Cross-session pattern audit & applicability APIs | STRETCH | CONSTRAIN | `2026-06-11-cross-session-pattern-audit-apis.proposal.md` |
| 12 | Decision Oracle: inline pattern pedigree + ancestral replay | STRETCH | SHIP-PROPOSAL | `2026-06-11-decision-oracle-pattern-provenance.proposal.md` |
| 13 | Escalation Timeline: Forensic causal-chain visibility for governance decisions | STRETCH | CONSTRAIN | `2026-06-11-escalation-timeline-causal-forensics.proposal.md` |
| 14 | Escalation Timeline: Glance-readable heatmap of governance feedback density | STRETCH | SHIP-PROPOSAL | `2026-06-11-escalation-timeline-heatmap.proposal.md` |
| 15 | HITL bulk-dismiss triage modal with keyboard preset logic | STRETCH | SHIP-PROPOSAL | `2026-06-11-hitl-bulk-dismiss-triage.proposal.md` |
| 16 | Frame D: Live Session Soak Control Panel with Polarity Audit | STRETCH | SHIP-PROPOSAL | `2026-06-11-live-session-soak-with-polarity-audit.proposal.md` |
| 17 | Operator Co-Pilot: One-Tap Ranked Affordances for HITL Next-Actions | WILD | CONSTRAIN | `2026-06-11-operator-co-pilot-gesture-macros.proposal.md` |
| 18 | Operator Co-Pilot Confidence Chip | WILD | SHIP-PROPOSAL | `2026-06-11-operator-confidence-chip.proposal.md` |
| 19 | Pattern Velocity Heatmap: Ambient Session-Health Signal via L0--L4 Learning Dynamics | WILD | SHIP-PROPOSAL | `2026-06-11-pattern-velocity-heatmap.proposal.md` |
| 20 | Proposal: clarify CLAUDE.md L35-42 to document the dual-key write-time / read-time split | -- | -- | `2026-06-11-polarity-dual-key-read-write-split.proposal.md` |
| 21 | Policy-preview chip: "what will governance do" from the corpus | STRETCH | -- | `2026-06-11-policy-preview-chip.proposal.md` |
| 22 | Quick-Filter Presets: Named Settings Shortcuts for FR-UI-9 | STRETCH | SHIP-PROPOSAL | `2026-06-11-quick-filter-presets-fr-ui-9.proposal.md` |
| 23 | Recorded Session Replay Forensics: Operator Root-Cause Analysis via Side-by-Side Decision Deltas | WILD | CONSTRAIN | `2026-06-11-recorded-session-replay-forensics.proposal.md` |
| 24 | Regret-mining: close the operator-override feedback loop | STRETCH | -- | `2026-06-11-regret-mining-override-loop.proposal.md` |
| 25 | Session-per-Agent Pinning with Visual Affordance (Frame B Swim-Lane) | SAFE | SHIP-PROPOSAL | `2026-06-11-session-agent-pinning-swim-lane.proposal.md` |
| 26 | Session checkpoint versioning for post-mortem drift analysis | STRETCH | CONSTRAIN | `2026-06-11-session-checkpoint-versioning.proposal.md` |
| 27 | Stale Session Cleanup (Dual-Key Polarity Fix) | STRETCH | CONSTRAIN | `2026-06-11-session-cleanup-dual-key-polarity.proposal.md` |
| 28 | Render per-session confidence trend sparklines in SessionPicker with paired text labels | STRETCH | CONSTRAIN | `2026-06-11-session-confidence-sparkline.proposal.md` |
| 29 | Session Delta Digest: Multi-Session Activity Snapshot in Monitor Frame | STRETCH | CONSTRAIN | `2026-06-11-session-delta-digest-monitor-frame.proposal.md` |
| 30 | Session DNA Heatmap: Cross-session pattern topology visualization with confidence per-session | STRETCH | CONSTRAIN | `2026-06-11-session-dna-heatmap-cross-pattern-topology.proposal.md` |
| 31 | Durable session event cursor -- browser resumption across refreshes | WILD | SHIP-PROPOSAL | `2026-06-11-session-event-append-stream.proposal.md` |
| 32 | Session health digest endpoint for operator glance-readability | STRETCH | SHIP-PROPOSAL | `2026-06-11-session-health-digest-api-flywheel.proposal.md` |
| 33 | Session health digest endpoints for operator multi-session triage | WILD | CONSTRAIN | `2026-06-11-session-health-digest-api.proposal.md` |
| 34 | Render per-session health sparklines (confidence + throughput) in SessionLane headers | STRETCH | SHIP-PROPOSAL | `2026-06-11-session-health-sparklines-confidence-throughput.proposal.md` |
| 35 | Session housekeeping API: stale-session discovery and bulk-purge endpoints with cascade cleanup | SAFE | CONSTRAIN | `2026-06-11-session-housekeeping-api.proposal.md` |
| 36 | Session Picker: Favorites + Filters + Hotkey | SAFE | CONSTRAIN | `2026-06-11-session-quick-filter-presets.proposal.md` |
| 37 | Session Story: narrative arc panel w/ bi-directional feed linking | STRETCH | CONSTRAIN | `2026-06-11-session-story-panel-narrative-arc.proposal.md` |
| 38 | Shadow Soak Audit Lane with Polarity-Safe Filtering | STRETCH | CONSTRAIN | `2026-06-11-shadow-soak-lane-audit-refactored.proposal.md` |
| 39 | Single Source of Truth -- determination + lightest mechanism | -- | -- | `2026-06-11-single-source-of-truth.proposal.md` |
| 40 | Live Non-SM Session Soak Dashboard Harness | STRETCH | CONSTRAIN | `2026-06-11-soak-1-live-session-shadow-harness.proposal.md` |
| 41 | Live-soak replay forensics: operator root-cause via side-by-side decision deltas (MVP tier) | WILD | CONSTRAIN | `2026-06-11-soak-2a-replay-forensics-mvp.proposal.md` |
| 42 | Soak Coverage Matrix (Governed Sessions Only) | SAFE | CONSTRAIN | `2026-06-11-soak-coverage-matrix-excluded-sm.proposal.md` |
| 43 | Session soak_id + soak_metadata tagging for audit hygiene | SAFE | CONSTRAIN | `2026-06-11-soak-session-metadata-tagging.proposal.md` |
| 44 | Sonification as Derived Escalation Confirmation Layer | STRETCH | CONSTRAIN | `2026-06-11-sonification-escalation-layer.proposal.md` |
| 45 | Spatial Session Overview Sidebar (Right-rail coexist mode) | STRETCH | CONSTRAIN | `2026-06-11-spatial-session-sidebar.proposal.md` |
| 46 | Operator-driven stale session cleanup with soft-delete + restore | SAFE | SHIP-PROPOSAL | `2026-06-11-stale-session-cleanup.proposal.md` |
| 47 | Temporal Scrubber: Governance Policy Archaeology via Replay Diff | SAFE | CONSTRAIN | `2026-06-11-temporal-scrubber-governance-audit.proposal.md` |
| 48 | Time Machine: counterfactual governance replay in Settings drawer | STRETCH | CONSTRAIN | `2026-06-11-time-machine-governance-replay.proposal.md` |
| 49 | What Changed Digest: page-focus synthesis overlay | SAFE | SHIP-PROPOSAL | `2026-06-11-what-changed-digest-page-focus.proposal.md` |
