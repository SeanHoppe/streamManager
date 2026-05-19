"""v2.3 P1 Seed 4 — cycle-discipline LOC delta dual-anchor.

Tests the ``_git_diff_loc`` + ``_gate_verdict`` + ``_fmt_loc_cell``
helpers in ``tools.soak_driver``. Subprocess ``git diff --shortstat``
calls are mocked to make the test hermetic.

Closes ADR-18 Amendment A acceptance L388 + introduces Amendment C
cycle-tip rendering at the soak-summary site.
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

from tools.soak_driver import (
    _fmt_loc_cell,
    _gate_verdict,
    _git_diff_loc,
    _loc_pathspec_from_env,
)


def _mock_diff(stdout: str = "", *, raises: type | None = None):
    """Build a patch for ``subprocess.run`` returning fixed stdout
    (or raising the given exception class).
    """
    def _side_effect(*args, **kwargs):
        if raises is not None:
            raise raises(1, args[0])
        return subprocess.CompletedProcess(args[0], 0, stdout=stdout, stderr="")
    return _side_effect


def test_unset_anchor_returns_sentinel():
    assert _git_diff_loc("") == "UNSET"


def test_valid_anchor_parses_shortstat():
    out = " 3 files changed, 42 insertions(+), 17 deletions(-)\n"
    with patch("tools.soak_driver.subprocess.run", side_effect=_mock_diff(out)):
        result = _git_diff_loc("abc1234")
    assert result == (42, 17, 25)


def test_empty_diff_returns_zero():
    with patch("tools.soak_driver.subprocess.run", side_effect=_mock_diff("")):
        result = _git_diff_loc("abc1234")
    assert result == (0, 0, 0)


def test_invalid_sha_returns_sentinel():
    with patch(
        "tools.soak_driver.subprocess.run",
        side_effect=_mock_diff(raises=subprocess.CalledProcessError),
    ):
        result = _git_diff_loc("nonexistent")
    assert result == "INVALID-SHA"


def test_no_git_binary_returns_sentinel():
    with patch(
        "tools.soak_driver.subprocess.run",
        side_effect=lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError("git")),
    ):
        result = _git_diff_loc("abc1234")
    assert result == "NOT-A-GIT-REPO"


def test_insertions_only_diff():
    out = " 1 file changed, 42 insertions(+)\n"
    with patch("tools.soak_driver.subprocess.run", side_effect=_mock_diff(out)):
        result = _git_diff_loc("abc1234")
    assert result == (42, 0, 42)


def test_deletions_only_diff():
    out = " 1 file changed, 17 deletions(-)\n"
    with patch("tools.soak_driver.subprocess.run", side_effect=_mock_diff(out)):
        result = _git_diff_loc("abc1234")
    assert result == (0, 17, -17)


# ---- _gate_verdict cases (per task-amendment-soak-summary-dual-anchor.md) ----


def test_gate_consolidation_negative_net_passes():
    """Case 3: consolidation + net = -6 → PASS."""
    assert _gate_verdict((10, 16, -6), "consolidation") == "PASS"


def test_gate_consolidation_zero_net_passes():
    assert _gate_verdict((0, 0, 0), "consolidation") == "PASS"


def test_gate_consolidation_positive_net_blocks():
    """Case 3: consolidation + net = +5 → BLOCK."""
    assert _gate_verdict((10, 5, 5), "consolidation") == "BLOCK"


def test_gate_feature_under_soft_passes():
    """Case 4: feature + net = +1499 → PASS (soft)."""
    assert _gate_verdict((1499, 0, 1499), "feature") == "PASS"


def test_gate_feature_just_under_hard_passes():
    """Case 5: feature + net = +2249 → PASS (still < 1.5× hard)."""
    assert _gate_verdict((2249, 0, 2249), "feature") == "PASS"


def test_gate_feature_at_hard_blocks():
    """Case 6: feature + net = +2250 → BLOCK (≥ 1.5× hard)."""
    assert _gate_verdict((2250, 0, 2250), "feature") == "BLOCK"


def test_gate_unknown_cycle_type_returns_unknown():
    assert _gate_verdict((100, 0, 100), "") == "UNKNOWN"
    assert _gate_verdict((100, 0, 100), "garbage") == "UNKNOWN"


def test_gate_sentinel_result_returns_unknown():
    """Case 2: cycle-tip UNSET → gate verdict = UNKNOWN."""
    assert _gate_verdict("UNSET", "feature") == "UNKNOWN"
    assert _gate_verdict("INVALID-SHA", "consolidation") == "UNKNOWN"


# ---- _fmt_loc_cell ----


def test_fmt_loc_cell_positive_net():
    assert _fmt_loc_cell((42, 17, 25)) == "+42 / -17 / +25"


def test_fmt_loc_cell_negative_net():
    assert _fmt_loc_cell((10, 16, -6)) == "+10 / -16 / -6"


def test_fmt_loc_cell_zero():
    assert _fmt_loc_cell((0, 0, 0)) == "+0 / -0 / +0"


def test_fmt_loc_cell_sentinel_passes_through():
    assert _fmt_loc_cell("UNSET") == "UNSET"
    assert _fmt_loc_cell("INVALID-SHA") == "INVALID-SHA"
    assert _fmt_loc_cell("NOT-A-GIT-REPO") == "NOT-A-GIT-REPO"


# ---- Seed v2.4-O: bucket-scoped LOC pathspec ----
#
# Regression cover for the gate-correctness bug where ``_git_diff_loc``
# ran whole-repo diffs while the ship-gate accounted bucket-scoped LOC
# out-of-band. ADR-18 Amendment C binds against the helper; helper now
# accepts ``paths`` to forward as ``git diff ... -- <pathspec>``.


def _capture_cmd(stdout: str = ""):
    """Side-effect that records the argv passed to subprocess.run."""
    captured: dict[str, list[str]] = {}

    def _side_effect(*args, **kwargs):
        captured["argv"] = list(args[0])
        return subprocess.CompletedProcess(args[0], 0, stdout=stdout, stderr="")

    return _side_effect, captured


def test_diff_default_is_whole_repo_no_pathspec():
    """Default (no paths) preserves legacy behaviour: no ``--`` separator."""
    side_effect, captured = _capture_cmd(" 1 file changed, 5 insertions(+)\n")
    with patch("tools.soak_driver.subprocess.run", side_effect=side_effect):
        _git_diff_loc("abc1234")
    assert "--" not in captured["argv"]


def test_diff_with_pathspec_forwards_dash_dash():
    """Explicit paths get forwarded after ``--`` to git."""
    side_effect, captured = _capture_cmd(" 1 file changed, 5 insertions(+)\n")
    with patch("tools.soak_driver.subprocess.run", side_effect=side_effect):
        _git_diff_loc("abc1234", ["src/", "tools/"])
    argv = captured["argv"]
    assert "--" in argv
    sep = argv.index("--")
    assert argv[sep + 1 :] == ["src/", "tools/"]


def test_diff_empty_pathspec_is_whole_repo():
    """``paths=[]`` (falsy) keeps legacy whole-repo behaviour."""
    side_effect, captured = _capture_cmd("")
    with patch("tools.soak_driver.subprocess.run", side_effect=side_effect):
        _git_diff_loc("abc1234", [])
    assert "--" not in captured["argv"]


# ---- _loc_pathspec_from_env ----


def test_pathspec_env_unset_returns_none(monkeypatch):
    monkeypatch.delenv("BRIDGE_LOC_PATHSPEC", raising=False)
    assert _loc_pathspec_from_env() is None


def test_pathspec_env_empty_returns_none(monkeypatch):
    monkeypatch.setenv("BRIDGE_LOC_PATHSPEC", "")
    assert _loc_pathspec_from_env() is None


def test_pathspec_env_single_entry(monkeypatch):
    monkeypatch.setenv("BRIDGE_LOC_PATHSPEC", "src/")
    assert _loc_pathspec_from_env() == ["src/"]


def test_pathspec_env_multiple_entries_strip_whitespace(monkeypatch):
    monkeypatch.setenv("BRIDGE_LOC_PATHSPEC", "src/, tools/ ,tests/")
    assert _loc_pathspec_from_env() == ["src/", "tools/", "tests/"]


def test_pathspec_env_blank_entries_dropped(monkeypatch):
    monkeypatch.setenv("BRIDGE_LOC_PATHSPEC", ",src/,,tools/,")
    assert _loc_pathspec_from_env() == ["src/", "tools/"]


# ---- Seed v2.4-O regression: scope × tolerance matrix ----
#
# Per feedback_cycle_tolerance_masks_bugs.md: helper bug is invisible at
# feature tolerance (2249 < 2250 PASS either way) but immediately fires
# BLOCK at consolidation tolerance (any net > 0 BLOCK). Both tolerances
# × both scopings must be covered.


def test_consolidation_bucket_scoped_zero_passes():
    """Bucket-scoped = 0 net → consolidation PASS (v2.4 ship case)."""
    side_effect, _ = _capture_cmd("")
    with patch("tools.soak_driver.subprocess.run", side_effect=side_effect):
        result = _git_diff_loc("abc1234", ["src/"])
    assert _gate_verdict(result, "consolidation") == "PASS"


def test_consolidation_whole_repo_phantom_positive_blocks():
    """Whole-repo unscoped phantom +746 → consolidation BLOCK (the bug)."""
    out = " 12 files changed, 800 insertions(+), 54 deletions(-)\n"
    side_effect, _ = _capture_cmd(out)
    with patch("tools.soak_driver.subprocess.run", side_effect=side_effect):
        result = _git_diff_loc("abc1234")
    assert result == (800, 54, 746)
    assert _gate_verdict(result, "consolidation") == "BLOCK"


def test_consolidation_bucket_scoped_with_real_delta_blocks():
    """Bucket-scoped, real positive net (+5) → consolidation BLOCK.

    Inverse of ``test_consolidation_bucket_scoped_zero_passes``: locks
    the tolerance asymmetry in both directions. Bucket-scoping does
    NOT hide a real positive delta — only phantom out-of-bucket churn.
    Mirrors the (+10, -5, +5) case from the PR #184 review feedback.
    """
    out = " 2 files changed, 10 insertions(+), 5 deletions(-)\n"
    side_effect, _ = _capture_cmd(out)
    with patch("tools.soak_driver.subprocess.run", side_effect=side_effect):
        result = _git_diff_loc("abc1234", ["src/"])
    assert result == (10, 5, 5)
    assert _gate_verdict(result, "consolidation") == "BLOCK"


def test_feature_bucket_scoped_under_soft_passes():
    """Feature tolerance, bucket-scoped, +1499 → PASS."""
    out = " 3 files changed, 1499 insertions(+)\n"
    side_effect, _ = _capture_cmd(out)
    with patch("tools.soak_driver.subprocess.run", side_effect=side_effect):
        result = _git_diff_loc("abc1234", ["src/"])
    assert _gate_verdict(result, "feature") == "PASS"


def test_feature_whole_repo_masks_bug_under_hard():
    """Feature tolerance, whole-repo, +2200 < 2250 → still PASS.

    Documents the masking: at feature tolerance the helper bug never
    surfaces unless the phantom delta crosses 2250. Consolidation
    surfaces it at +1.
    """
    out = " 9 files changed, 2200 insertions(+)\n"
    side_effect, _ = _capture_cmd(out)
    with patch("tools.soak_driver.subprocess.run", side_effect=side_effect):
        result = _git_diff_loc("abc1234")
    assert _gate_verdict(result, "feature") == "PASS"


def test_feature_whole_repo_over_hard_blocks():
    """Feature tolerance, whole-repo, +2400 ≥ 2250 → BLOCK (loud)."""
    out = " 15 files changed, 2400 insertions(+)\n"
    side_effect, _ = _capture_cmd(out)
    with patch("tools.soak_driver.subprocess.run", side_effect=side_effect):
        result = _git_diff_loc("abc1234")
    assert _gate_verdict(result, "feature") == "BLOCK"


# ---- PR #184 review-fix: require_paths sentinel ----
#
# Closes the silent whole-repo fallback at the ship-gate binding site:
# when ``BRIDGE_LOC_PATHSPEC`` is unset, ``_loc_pathspec_from_env``
# returns ``None`` and the legacy two-arg call to ``_git_diff_loc``
# silently ran whole-repo. ADR-18 Amendment C bound against that
# inflated delta and would false-BLOCK the next consolidation. The
# fix forces the binding site to pass ``require_paths=True`` which
# returns a loud ``"PATHSPEC-UNSET"`` sentinel.


def test_require_paths_unset_returns_pathspec_unset_sentinel():
    """require_paths=True + paths=None → loud sentinel, no subprocess call."""
    side_effect, captured = _capture_cmd("")
    with patch("tools.soak_driver.subprocess.run", side_effect=side_effect):
        result = _git_diff_loc("abc1234", None, require_paths=True)
    assert result == "PATHSPEC-UNSET"
    assert "argv" not in captured  # short-circuited before subprocess


def test_require_paths_empty_list_returns_sentinel():
    """require_paths=True + paths=[] (falsy) → sentinel."""
    side_effect, captured = _capture_cmd("")
    with patch("tools.soak_driver.subprocess.run", side_effect=side_effect):
        result = _git_diff_loc("abc1234", [], require_paths=True)
    assert result == "PATHSPEC-UNSET"
    assert "argv" not in captured


def test_require_paths_with_pathspec_runs_normally():
    """require_paths=True + non-empty paths → normal shortstat path."""
    out = " 1 file changed, 5 insertions(+)\n"
    side_effect, captured = _capture_cmd(out)
    with patch("tools.soak_driver.subprocess.run", side_effect=side_effect):
        result = _git_diff_loc("abc1234", ["src/"], require_paths=True)
    assert result == (5, 0, 5)
    assert "--" in captured["argv"]
    sep = captured["argv"].index("--")
    assert captured["argv"][sep + 1 :] == ["src/"]


def test_require_paths_default_is_false_preserves_legacy():
    """Default require_paths=False keeps legacy whole-repo behaviour."""
    out = " 1 file changed, 5 insertions(+)\n"
    side_effect, captured = _capture_cmd(out)
    with patch("tools.soak_driver.subprocess.run", side_effect=side_effect):
        result = _git_diff_loc("abc1234")  # no kwarg
    assert result == (5, 0, 5)
    assert "--" not in captured["argv"]


def test_gate_verdict_pathspec_unset_returns_unknown():
    """The new sentinel must short-circuit the gate to UNKNOWN, not BLOCK/PASS."""
    assert _gate_verdict("PATHSPEC-UNSET", "consolidation") == "UNKNOWN"
    assert _gate_verdict("PATHSPEC-UNSET", "feature") == "UNKNOWN"


def test_fmt_loc_cell_pathspec_unset_passes_through():
    """Sentinel renders verbatim so the soak summary surfaces the cause."""
    assert _fmt_loc_cell("PATHSPEC-UNSET") == "PATHSPEC-UNSET"


def test_unset_anchor_beats_pathspec_unset():
    """Empty anchor short-circuits before the pathspec check."""
    assert _git_diff_loc("", None, require_paths=True) == "UNSET"


# ---- PR #184 review-fix: end-to-end ship-gate env-to-argv threading ----
#
# Helper-only tests left a gap: a future regression that deletes the
# ``_loc_pathspec_from_env()`` call at one of the two ship-gate sites
# (``_write_report`` or ``main``) would leave the helper tests green
# but silently revert ship-gate to whole-repo. These e2e tests set
# ``BRIDGE_LOC_PATHSPEC`` + mock ``git diff`` and assert the captured
# argv carries the bucket scope through both code paths.


def _multi_capture_cmd(stdouts: list[str] | None = None):
    """Side-effect that records EVERY subprocess.run argv across calls."""
    calls: list[list[str]] = []
    stdouts = list(stdouts or [""])

    def _side_effect(*args, **kwargs):
        calls.append(list(args[0]))
        idx = min(len(calls) - 1, len(stdouts) - 1)
        return subprocess.CompletedProcess(args[0], 0, stdout=stdouts[idx], stderr="")

    return _side_effect, calls


def _git_diff_calls(calls: list[list[str]]) -> list[list[str]]:
    """Filter argv list to only ``git diff --shortstat`` invocations."""
    return [argv for argv in calls if argv[:3] == ["git", "diff", "--shortstat"]]


def _write_report_kwargs(report_path):
    """Minimal kwargs to invoke ``_write_report`` for the LOC-anchor block."""
    from pathlib import Path

    return {
        "started_at_iso": "2026-05-19T00:00:00+00:00",
        "ended_at_iso": "2026-05-19T00:30:00+00:00",
        "total_runtime_s": 1800.0,
        "payloads": [],
        "sse_received": 0,
        "sse_errors": 0,
        "dashboard_log_path": Path(report_path.parent / "dashboard.log"),
        "consumer_log_path": Path(report_path.parent / "consumer.log"),
        "gov_db": Path(report_path.parent / "gov.db"),
        "server_log_excerpt": "",
        "rss_start": 100.0,
        "rss_end": 100.0,
        "rss_peak": 100.0,
        "fd_start": 10,
        "fd_end": 10,
        "cli_present": True,
    }


def test_write_report_threads_bridge_loc_pathspec_to_git(monkeypatch, tmp_path):
    """``_write_report`` call site (the binding gate write) honours the env.

    A future regression that deletes the ``_loc_pathspec_from_env()`` call
    at the binding-gate site would silently revert to whole-repo. Helper
    tests would still pass; this e2e test fires the BLOCK signal.
    """
    from tools import soak_driver

    monkeypatch.setenv("BRIDGE_LOC_PATHSPEC", "src/,tools/")
    monkeypatch.setenv("BRIDGE_CYCLE_TIP_SHA", "tip12345")
    monkeypatch.setenv("BRIDGE_PREDECESSOR_TAG_SHA", "pred1234")
    monkeypatch.setenv("BRIDGE_CYCLE_TYPE", "consolidation")

    side_effect, calls = _multi_capture_cmd([" 0 files changed\n"])
    state = soak_driver._DriverState()
    report_path = tmp_path / "soak.md"
    with patch("tools.soak_driver.subprocess.run", side_effect=side_effect):
        soak_driver._write_report(
            report_path, state, **_write_report_kwargs(report_path)
        )

    diff_calls = _git_diff_calls(calls)
    assert diff_calls, "_write_report did not invoke `git diff --shortstat`"
    for argv in diff_calls:
        assert "--" in argv, f"`--` separator missing from argv: {argv}"
        sep = argv.index("--")
        assert argv[sep + 1 :] == ["src/", "tools/"], (
            f"bucket pathspec not threaded: argv tail = {argv[sep + 1 :]}"
        )


def test_write_report_unset_env_yields_pathspec_unset_in_report(monkeypatch, tmp_path):
    """``_write_report`` with unset env writes ``PATHSPEC-UNSET`` (no silent revert)."""
    from tools import soak_driver

    monkeypatch.delenv("BRIDGE_LOC_PATHSPEC", raising=False)
    monkeypatch.setenv("BRIDGE_CYCLE_TIP_SHA", "tip12345")
    monkeypatch.setenv("BRIDGE_PREDECESSOR_TAG_SHA", "pred1234")
    monkeypatch.setenv("BRIDGE_CYCLE_TYPE", "consolidation")

    side_effect, calls = _multi_capture_cmd([" 99 files changed, 5000 insertions(+)\n"])
    state = soak_driver._DriverState()
    report_path = tmp_path / "soak.md"
    with patch("tools.soak_driver.subprocess.run", side_effect=side_effect):
        soak_driver._write_report(
            report_path, state, **_write_report_kwargs(report_path)
        )

    diff_calls = _git_diff_calls(calls)
    assert diff_calls == [], (
        f"expected zero git-diff calls under unset env (short-circuit), got: {diff_calls}"
    )
    body = report_path.read_text(encoding="utf-8")
    assert "PATHSPEC-UNSET" in body, "report must surface PATHSPEC-UNSET sentinel"
    assert "**Gate verdict (Amendment C):** UNKNOWN" in body, (
        "gate must read UNKNOWN under PATHSPEC-UNSET sentinel (not PASS/BLOCK)"
    )
