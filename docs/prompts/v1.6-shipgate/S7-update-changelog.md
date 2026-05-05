# S7 — Update CHANGELOG w/ [1.6.0] entry

**Goal:** Append `## [1.6.0] - 2026-05-05` (or actual ship date) section to
`CHANGELOG.md` documenting cycle scope.

## Context

CHANGELOG style is Keep-a-Changelog flavored per prior v1.x entries. v1.6
scope: P0 cycle frame, P1 CLI residue instrumentation (5 keys), ship-gate
attribution finding.

## Steps

1. Read existing `CHANGELOG.md`. Match style/heading depth of `## [1.5.0]`.
2. Add new section above v1.5.0:
   ```
   ## [1.6.0] - 2026-05-05

   ### Added
   - `_evaluate_inner` CLI residue instrumentation: 5 new sub-phase wall-clock
     keys (`cli_setup_ms`, `cli_dispatch_ms`, `cli_pool_acquire_ms`,
     `cli_pool_send_ms`, `cli_parse_ms`) populated on CLI escalation branch.
   - Soak driver `### ALLOW _evaluate_inner CLI residue breakout (v1.6)` block.

   ### Changed
   - ADR-5 §"Caveats" updated w/ v1.6 attribution finding (was: residue
     unidentified).

   ### Findings
   - Driver localization: <component> p95=<X>ms accounts for ~<Y>% of
     `evaluate_inner` p95 tail. v1.7 lever: <lever>.
   - LM categorize p95 trend: <closed/extended/regression>.

   ### Notes
   - Verdict path byte-identical to v1.5 (telemetry-only addition).
   - `--cli-pool-size 2` remains ship-gate default.
   ```
3. Fill `<component>`, `<X>`, `<Y>`, `<lever>` from S4. Fill LM line from S5.

## Acceptance

- `## [1.6.0]` section drafted, all placeholders resolved.
- Style matches v1.5.0 entry.

## On-done ack

`- [x] CHANGELOG.md **S7 — Update CHANGELOG** ([1.6.0] drafted)`

## Mint-new check

None expected. If CHANGELOG style drifted (linter/CI complaint), mint
`S7a-changelog-fmt-fix.md`.
