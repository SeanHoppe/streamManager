"""v2.6 P1 wall-clock instrumentation unit tests; no live CLI."""

from __future__ import annotations

import time
from types import SimpleNamespace

from tools.alignment_eval import (
    _percentile,
    _timeout_count,
    evaluate_row,
    render_report,
)


class _StubGovernor:
    def __init__(self, action="ALLOW", sleep_s=0.0, return_none=False):
        self._action, self._sleep_s, self._return_none = action, sleep_s, return_none

    def evaluate(self, content, model_id):
        if self._sleep_s:
            time.sleep(self._sleep_s)
        return None if self._return_none else SimpleNamespace(action=self._action)


def test_evaluate_row_returns_actions_and_durations_lists():
    actions, durations = evaluate_row(
        _StubGovernor(action="GUIDE", sleep_s=0.01), "x", "claude-sonnet-4-6", runs=3)
    assert actions == ["GUIDE", "GUIDE", "GUIDE"]
    assert len(durations) == 3
    assert all(isinstance(d, float) and d >= 0.0 for d in durations)


def test_evaluate_row_handles_none_decision():
    actions, durations = evaluate_row(
        _StubGovernor(return_none=True), "x", "claude-haiku-4-5", runs=2)
    assert actions == ["NONE", "NONE"]
    assert len(durations) == 2 and all(isinstance(d, float) for d in durations)


def test_percentile_helper_known_distribution():
    v = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert _percentile(v, 0.50) == 3.0
    assert _percentile(v, 0.95) == 4.8
    assert _percentile(v, 0.99) == 4.96


def test_percentile_empty_list_returns_zero():
    assert _percentile([], 0.95) == 0.0


def test_timeout_count_threshold():
    # TIMEOUT_SECONDS=25.0 -> threshold >=24.5; 24.6 + 25.0 hit.
    assert _timeout_count([1.0, 24.0, 24.6, 25.0]) == 2
    assert _timeout_count([]) == 0


def test_render_report_includes_wall_clock_section():
    rows = [{"id": "s1", "prompt": "x", "expected_verdict": "ALLOW",
             "expected_safety_tags": [], "source_note": "syn", "model_floor": "any"}]
    summary_keys = {
        "total": 1, "sonnet_stable_count": 1, "sonnet_pass": 1, "sonnet_pass_rate": 1.0,
        "haiku_stable_count": 1, "haiku_pass": 1, "haiku_pass_rate": 1.0,
        "haiku_regression_vs_sonnet": 0, "haiku_regression_frog7": 0,
        "unstable_sonnet": 0, "unstable_haiku": 0, "regression_rows": [],
    }
    duration_keys = {f"{m}_duration_s_{k}": v for m in ("sonnet", "haiku")
                     for k, v in (("p50", 1.0), ("p95", 2.0), ("p99", 3.0),
                                  ("max", 3.0), ("n", 3))}
    results = {
        "s1": {"sonnet_runs": ["ALLOW"], "sonnet_majority": "ALLOW",
               "sonnet_stable": True, "haiku_runs": ["ALLOW"],
               "haiku_majority": "ALLOW", "haiku_stable": True, "agree": True},
        "__summary__": {**summary_keys, **duration_keys},
    }
    md = render_report(rows, results, runs=3,
                       control_model="claude-sonnet-4-6",
                       candidate_model="claude-haiku-4-5")
    assert "## Per-model wall-clock distributions" in md
    assert "| sonnet |" in md and "| haiku  |" in md
    results["__summary__"]["haiku_duration_s_n"] = 0
    assert "n=0; (skipped)" in render_report(
        rows, results, runs=3, control_model="claude-sonnet-4-6",
        candidate_model="claude-haiku-4-5")
