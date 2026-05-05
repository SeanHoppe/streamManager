# S3 — Pull soak report on wake

**Goal:** Read newest `reports/soak-<ts>Z.md`, verify v1.6 residue block
populated + protected v1.4/v1.5 blocks unchanged.

## Context

Wake fires after S2's ScheduleWakeup. Soak driver finalizes by writing a
markdown report to `reports/`.

## Steps

1. `ls -t reports/soak-*Z.md | head -1` → newest report path.
2. Read newest report. Confirm sections:
   - `### ALLOW publish-path phase breakout (v1.4)` — unchanged.
   - `### ALLOW _evaluate_inner sub-phase breakout (v1.5)` — unchanged.
   - `### ALLOW _evaluate_inner CLI residue breakout (v1.6)` — NEW, all 5 rows:
     `cli_setup_ms`, `cli_dispatch_ms`, `cli_pool_acquire_ms`,
     `cli_pool_send_ms`, `cli_parse_ms`.
3. Capture key numbers:
   - `evaluate_inner` p95 (parent).
   - Each residue row p95 (children).
   - LM categorize p95 (for S5).
4. Verify parent ≥ children invariant: sum of residue p95 ≤ `evaluate_inner` p95
   (within rounding; not strict eq — branches mean some samples don't traverse all 5).

## Acceptance

- Report exists, has v1.6 block, all 5 rows present (non-`n/a`).
- v1.4 + v1.5 blocks structurally unchanged from v1.5.0 ship-gate.
- Numbers captured for downstream phases.

## On-done ack

`- [x] reports/soak-<ts>Z.md **S3 — Pull soak report on wake** (eval_inner p95=<X>ms; cli_dispatch p95=<Y>ms)`

## Mint-new check

- If v1.6 block missing OR all rows `n/a`/zero on CLI escalation samples →
  instrumentation bug. Mint `S3a-residue-debug.md`. **BLOCKS S6.**
- If parent < sum(children), mint `S3b-residue-double-count.md` (timing bug —
  same wall-clock counted twice).
- If v1.4/v1.5 block diff vs prior ship-gate, mint `S3c-protected-symbol-regression.md`.
