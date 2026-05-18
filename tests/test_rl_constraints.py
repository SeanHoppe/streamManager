"""v10 P4 — tests for CMDP feasibility filter."""

from __future__ import annotations

import inspect

from rl.constraints import ConstraintBundle, feasible_action_set, is_feasible
from rl.validate import L4_THRESHOLD_KEY, Candidate, StageResult, ValidationReport


def _candidate(thr: float = 0.75) -> Candidate:
    return Candidate(thresholds={L4_THRESHOLD_KEY: thr})


def _report(*, regressions: int = 0, fr_total: int = 10,
            ips_target: float = 0.5) -> ValidationReport:
    cand = base = _candidate(0.75)
    s1 = StageResult(
        "stage_1_golden", regressions == 0,
        "ok" if regressions == 0 else f"{regressions} fail",
        {"fr_og_7_total": fr_total,
         "regressions": [str(i) for i in range(regressions)]},
    )
    s2 = StageResult("stage_2_ips", True, "ips ok", {"ips_target": ips_target})
    return ValidationReport(candidate=cand, baseline=base, delta=0.02,
                            stages=[s1, s2])


def test_fr_og_7_violation_is_infeasible():
    r = _report(regressions=1, fr_total=10, ips_target=0.9)
    bundle = ConstraintBundle(0, 0.5, 0.0)
    assert is_feasible(r.candidate, bundle, r) is False


def test_hitl_floor_violation_is_infeasible():
    r = _report(regressions=0, ips_target=0.40)
    bundle = ConstraintBundle(0, 0.50, 0.0)
    assert is_feasible(r.candidate, bundle, r) is False


def test_alignment_pass_floor_violation_is_infeasible():
    # 9/10 FR-OG-7 pass = 0.90 pass rate; floor = 1.0 → infeasible.
    r = _report(regressions=1, fr_total=10, ips_target=0.9)
    bundle = ConstraintBundle(fr_og_7_floor=1,
                              hitl_agreement_floor=0.5,
                              alignment_pass_rate_floor=1.0)
    assert is_feasible(r.candidate, bundle, r) is False


def test_all_constraints_pass():
    r = _report(regressions=0, fr_total=10, ips_target=0.9)
    bundle = ConstraintBundle(0, 0.5, 1.0)
    assert is_feasible(r.candidate, bundle, r) is True


def test_empty_feasible_set_returns_empty():
    bundle = ConstraintBundle(0, 0.5, 1.0)
    out = feasible_action_set(
        [_candidate(t) for t in (0.5, 0.6, 0.7)],
        bundle,
        lambda _c: _report(regressions=5, ips_target=0.0),
    )
    assert out == []


def test_no_penalty_term_in_bandit():
    """DOD: CMDP filter is the gate, NOT a reward penalty."""
    from rl import bandit
    assert "penalty" not in inspect.getsource(bandit).lower(), (
        "rl.bandit must not parameterise a constraint-penalty term"
    )
