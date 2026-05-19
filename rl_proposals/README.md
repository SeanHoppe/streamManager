# rl_proposals/ — pinning convention

Two categories of artefact live here:

## 1. Sample / fixture (working data)

Files matching `v10p4-sample.*`. Tracked. Regenerable. Used as smoke
fixtures by `tools/rl_test_helper/` and ad-hoc local runs.

## 2. Pinned evidence snapshots (immutable, dated)

Files matching `v10p4-live-<YYYYMMDD>.json` and the paired
`v10p4-live-<YYYYMMDD>.manifest.json`. The date in the filename is
the snapshot date and is the immutability anchor.

**Rule.** Once committed, a dated snapshot pair is frozen. Future
re-runs of the live train MUST write to a new dated filename
(`v10p4-live-<new-date>.json` + `.manifest.json`). Overwriting an
existing dated snapshot or deleting one without ADR-grade
justification is a review-blocking finding.

**Why we pin instead of regenerate.** These snapshots back specific
named events in project history (e.g. `v10p4-live-20260518.*` is the
live-train evidence cited by Amendment D / issue #177 / memory
`project_v10_p5_gate_deadlock.md`). Regenerating in place would
silently rewrite the cited evidence and break review trails.

## Current snapshots

- `v10p4-live-20260518.{json,manifest.json}` — 2026-05-18 live train
  against `tmp/rl_episodes.db` (240 raw rows). Evidence anchor for
  issue #177 and ADR-18 Amendment D. Result: `ready=False`,
  `n_actual=79/200`, `best_arm_ci_width_95=0.119/0.10`.
