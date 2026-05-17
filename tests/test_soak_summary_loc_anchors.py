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

from tools.soak_driver import _fmt_loc_cell, _gate_verdict, _git_diff_loc


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
