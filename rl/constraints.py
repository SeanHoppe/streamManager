"""v10 P4 — CMDP feasibility filter.

Rejects infeasible candidates BEFORE Thompson sampling. Per the v10
design review §"Issue #5 — Reward gaming", constraint violations are
NEVER reward penalties — they REJECT the candidate from the action
set. Reads stage 1 (golden) + stage 2 (IPS) outputs from a
:class:`ValidationReport`; does NOT re-run stages.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from rl.validate import Candidate, StageResult, ValidationReport


@dataclass
class ConstraintBundle:
    """``fr_og_7_floor`` — max regression count (default 0).
    ``hitl_agreement_floor`` — minimum stage-2 IPS HITL agreement reward.
    ``alignment_pass_rate_floor`` — minimum stage-1 FR-OG-7 pass ratio."""

    fr_og_7_floor: int = 0
    hitl_agreement_floor: float = 0.0
    alignment_pass_rate_floor: float = 0.0


def _stage(report: ValidationReport, name: str) -> StageResult | None:
    return next((s for s in report.stages if s.name == name), None)


def is_feasible(
    candidate: Candidate,
    bundle: ConstraintBundle,
    validation_report: ValidationReport,
) -> bool:
    """True iff candidate satisfies all three constraints in ``bundle``."""
    del candidate
    s1 = _stage(validation_report, "stage_1_golden")
    s2 = _stage(validation_report, "stage_2_ips")
    if s1 is None or s2 is None:
        return False
    regressions = s1.metrics.get("regressions") or []
    if len(regressions) > bundle.fr_og_7_floor:
        return False
    fr_total = int(s1.metrics.get("fr_og_7_total", 0) or 0)
    pass_rate = ((fr_total - len(regressions)) / fr_total) if fr_total > 0 else 1.0
    if pass_rate < bundle.alignment_pass_rate_floor:
        return False
    # Stage 2 skipped on insufficient data → neutral (no IPS evidence).
    if not s2.metrics.get("skipped"):
        hitl_ips = float(s2.metrics.get("ips_target", 0.0) or 0.0)
        if hitl_ips < bundle.hitl_agreement_floor:
            return False
    return True


def feasible_action_set(
    candidates: list[Candidate],
    bundle: ConstraintBundle,
    validate_fn: Callable[[Candidate], ValidationReport],
) -> list[Candidate]:
    """Return only the feasible candidates. Empty list is valid."""
    return [c for c in candidates if is_feasible(c, bundle, validate_fn(c))]
