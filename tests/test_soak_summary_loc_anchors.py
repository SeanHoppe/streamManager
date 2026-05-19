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
