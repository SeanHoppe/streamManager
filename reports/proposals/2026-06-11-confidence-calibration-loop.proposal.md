# Confidence-calibration loop: make "confidence" mean something

**Status:** Proposal (data-flywheel, directive follow-up F). Boldness STRETCH; effort M.
**Scope:** proposal only. ASCII-only (cp1252).
**Floor:** advisory recalibration only; never overrides a verdict or the safety floor; polarity dual-key.

## Problem

Governance attaches a confidence to every decision, and the operator (and the advisory bias) trust that
number. But nothing checks whether it is CALIBRATED: does "0.95 confidence" actually correspond to ~95%
operator agreement, or is the model over/under-confident? With 21k decisions + `hitl_overrides`, the
ground truth exists to measure this -- and it is never measured. An uncalibrated confidence silently
mis-ranks what the operator should look at, and mis-weights the advisory bias.

## Proposal

A **calibration loop** -- measure predicted-confidence vs realized agreement, surface it, and feed the
correction back as an advisory confidence transform:

1. Backend `tools/calibration.py` (read-only): bucket decisions by predicted confidence (deciles), and
   for each bucket compute realized agreement = `1 - override_rate` against `hitl_overrides`. Output a
   reliability table (predicted vs actual per bucket) + a single calibration curve. Polarity dual-key.
2. UI: a small **reliability diagram** in settings/observability -- the predicted=actual diagonal plus the
   measured curve, so the operator can SEE "the model is 8 points over-confident in the 0.9 band." Paired
   label + chart; color never the sole signal.
3. Feedback: expose the fitted monotonic transform as an OPTIONAL advisory recalibration -- the displayed
   advisory confidence (and the Learn-Mode bias weighting) can be calibration-adjusted. The RAW model
   confidence and the verdict are untouched; only the advisory presentation is corrected, behind an
   operator opt-in.

## Operator value

"Confidence" becomes trustworthy: the operator learns where to discount the number, and the advisory
surfaces (policy-preview, regret, bias pre-fill) inherit a calibrated signal. The flywheel sharpens its
own dial -- more decided/overridden history -> better-calibrated confidence -> better-ranked attention.

## Surfaces touched / added

- `tools/calibration.py` (new, read-only) + additive `GET /api/governance/calibration`
- `dashboard/ui-next/src/lib/components/ReliabilityDiagram.svelte` (new) in settings/observability
- optional advisory-confidence transform applied ONLY at the advisory presentation layer (not the verdict)

## Feasibility

FEASIBLE for the measurement + diagram (pure aggregation over `decisions` x `hitl_overrides`). The
optional advisory transform must be carefully scoped to presentation only -- if it touched the verdict's
confidence in `governance.py` that is FROZEN (see note). Ship measurement + diagram first; the transform
is a follow-on behind an opt-in.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS -- SM corpus only; domain-agnostic.
- **Polarity (G2):** PASS -- dual-key corpus read; SM-self excluded.
- **ADR-18 MUST floor:** PASS -- read-only measurement + an opt-in ADVISORY transform; the verdict, the raw confidence, and the safety floor are untouched (M8 advisory-only); monitor-first preserved.
- **Frozen-surface note:** the measurement touches nothing FROZEN. The advisory transform must live at the presentation/advisory layer; applying it inside `governance.py` confidence assignment is FROZEN and would need an ADR-18 amendment -- explicitly out of scope for the v1 measurement.
- **New-envelope note:** none (REST read + a tool); a future `calibration_recomputed` envelope would need same-PR cassette + soak coverage.

## Grounding

- gov.db `decisions.confidence` + `hitl_overrides` = predicted vs realized ground truth
- `CLAUDE.md:31-45` (dual-key polarity read)
- `REQUIREMENTS.md` FR-OG-7 / alignment-eval (existing notion of governance correctness to anchor against)
- `docs/adr/ADR-18-mvp-surface-freeze.md` (governance.py confidence assignment FROZEN)

### Verify
- `GET /api/governance/calibration` returns 10 buckets with predicted vs realized agreement; SM-self rows absent.
- The advisory transform is opt-in and changes only displayed advisory confidence, never `decisions.confidence` or any verdict (grep: no write to the verdict path).
