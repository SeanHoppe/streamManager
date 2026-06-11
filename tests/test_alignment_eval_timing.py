"""v2.6 P1 wall-clock instrumentation unit tests; no live CLI."""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

from stream_manager.cli_governance import TIMEOUT_SECONDS
from tools.alignment_eval import (
    _percentile,
    _timeout_count,
    evaluate_row,
    majority,
    render_report,
)

_GOLDEN = Path(__file__).resolve().parent / "golden" / "l4_alignment.jsonl"


class _StubGovernor:
    def __init__(self, action="ALLOW", sleep_s=0.0, return_none=False):
        self._action, self._sleep_s, self._return_none = action, sleep_s, return_none

    def evaluate(self, content, model_id):
        if self._sleep_s:
            time.sleep(self._sleep_s)
        return None if self._return_none else SimpleNamespace(action=self._action)


class _SequencedGovernor:
    """Returns a pre-scripted action per call (deterministic distribution).

    Models a row whose verdict is drawn from an unstable distribution so a
    test can replay the exact n=6-unanimous-vs-n=12-split behaviour the
    F4 frog7 finding describes, without any live CLI subprocess.
    """

    def __init__(self, actions):
        self._actions = list(actions)
        self._i = 0

    def evaluate(self, content, model_id):
        action = self._actions[self._i % len(self._actions)]
        self._i += 1
        return SimpleNamespace(action=action)


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
    # threshold = TIMEOUT_SECONDS - 0.5 (subprocess teardown slack).
    from stream_manager.cli_governance import TIMEOUT_SECONDS as _CAP
    assert _timeout_count(
        [1.0, _CAP - 1.0, _CAP - 0.4, _CAP]) == 2
    assert _timeout_count([]) == 0


def test_subprocess_cap_is_30s_not_25s():
    """F4-cap-clip: the subprocess timeout cap that censors the p99 tail
    must be the post-audit 30s value, not the v2.6 P1 25s cap.

    The 25s cap mechanically clipped Sonnet response times, so the
    measured p99=25.048s was an approximation of clip frequency, not a
    true tail. The audit raised the cap to 30s; pin it so a regression
    back to 25s (which would re-censor the distribution) fails loudly.
    """
    assert TIMEOUT_SECONDS == 30.0


def test_timeout_count_attributes_clipped_runs_at_current_cap():
    """The censoring proxy must fire for any run at/above the 30s cap.

    A run that lands within 0.5s of the cap is treated as a clipped
    (censored) sample. This makes the cap-clip measurement artefact
    OBSERVABLE in the report rather than silently folded into the p99,
    which was the unresolved risk the v2.7 P2 audit flagged.
    """
    cap = TIMEOUT_SECONDS
    # A 30s+92ms run is the v2.7-P2 over-the-recommendation case; it is
    # at the cap and so counts as a censored/clipped sample.
    durations = [1.0, 5.0, cap, cap + 0.092]
    assert _timeout_count(durations) == 2
    # Runs comfortably below the cap are NOT counted as clipped.
    assert _timeout_count([1.0, cap - 5.0, cap - 0.6]) == 0


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


# --- F4-haiku-frog7-boundary-instability: timing-introspective rows ---------
# Root cause per the finding: Haiku instability on frog7-prefixed
# timing-introspective rows is the high-side tail of an unstable
# distribution, NOT a timeout-boundary mechanism. These tests pin that
# distinction deterministically (no live CLI).


def _golden_rows() -> list[dict]:
    with _GOLDEN.open("r", encoding="utf-8") as fp:
        return [json.loads(line) for line in fp if line.strip()]


def test_frog7_rows_present_in_golden_and_sonnet_floored():
    """The frog7 timing-introspective rows exist and are sonnet-floored.

    A frog7 regression is only an FR-OG-7 gate failure when the row's
    model_floor is sonnet; pin that the golden set still satisfies the
    precondition the finding's regression analysis assumes.
    """
    rows = _golden_rows()
    frog7 = [r for r in rows if r["id"].startswith("frog7-")]
    assert frog7, "no frog7 rows in golden set"
    # The phase-timings row named in the finding root cause must exist.
    ids = {r["id"] for r in frog7}
    assert "frog7-phase-timings-keys-05" in ids
    assert all(r["model_floor"] == "sonnet" for r in frog7)


def test_frog7_n6_unanimous_is_high_side_tail_not_stable_at_n12():
    """n=6 unanimous ALLOW is an outlier of an unstable distribution.

    The finding measured ~58% ALLOW / 33% SUGGEST / 8% GUIDE at n=12 for
    frog7-phase-timings-keys-05. A 6-sample unanimous-ALLOW window is a
    high-side tail draw; the same underlying distribution at n=12 is NOT
    unanimous, so ``majority`` reports it unstable. This is the
    tail-of-distribution behaviour, not a deterministic boundary.
    """
    # n=12 mix matching the re-measured frequency (7 ALLOW / 4 SUGGEST /
    # 1 GUIDE). Front-loaded with 6 ALLOWs so a 6-run window reads
    # unanimous while the full 12-run window does not.
    n12_actions = (
        ["ALLOW"] * 6 + ["SUGGEST", "ALLOW", "SUGGEST", "GUIDE", "SUGGEST", "SUGGEST"]
    )
    gov = _SequencedGovernor(n12_actions)

    actions_n6, _ = evaluate_row(gov, "frog7 timing prompt", "claude-haiku-4-5", runs=6)
    _maj6, stable6 = majority(actions_n6)
    assert actions_n6 == ["ALLOW"] * 6
    assert stable6 is True  # n=6 window reads (falsely) stable

    # Continue the same distribution for the remaining 6 draws; the full
    # n=12 read is NOT unanimous -> unstable.
    actions_rest, _ = evaluate_row(gov, "frog7 timing prompt", "claude-haiku-4-5", runs=6)
    _maj12, stable12 = majority(actions_n6 + actions_rest)
    assert stable12 is False, "n=12 distribution must read unstable"


def test_frog7_instability_is_not_timeout_boundary():
    """Frog7 verdict instability is unrelated to the timeout boundary.

    Every run completes well under TIMEOUT_SECONDS, yet the verdict still
    flips across runs. _timeout_count must report zero, proving the
    instability is distributional, not a censored-clip/timeout artefact.
    """
    gov = _SequencedGovernor(["ALLOW", "SUGGEST", "GUIDE"])
    actions, durations = evaluate_row(
        gov, "frog7 timing prompt", "claude-haiku-4-5", runs=3)
    # Verdict is unstable (3-way split) ...
    _maj, stable = majority(actions)
    assert stable is False
    # ... but no run is anywhere near the timeout boundary.
    assert all(d < TIMEOUT_SECONDS - 0.5 for d in durations)
    assert _timeout_count(durations) == 0
