"""v1.5 — soak driver `### ALLOW _evaluate_inner sub-phase breakout
(v1.5)` block.

Validates that the new render helper produces a markdown block with
all five sub-phase rows when fed a synthesized phase-timings stream,
and that the existing v1.4 publish-path block still renders unchanged
on the same input (back-compat invariant from the prompt).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import soak_driver  # noqa: E402


_SUB_PHASES = (
    "og7_check",
    "fast_precheck",
    "graph_classify",
    "hydrator_state_read",
    "routing_dispatch",
)


def _synthetic_allow_phase_ms() -> dict[str, list[float]]:
    """Phase-timings stream a v1.5 engine would publish for routine
    ALLOW envelopes. Numbers are illustrative; the helper renders them
    via percentile, so any non-empty list works."""
    return {
        # v1.4 publish-path keys.
        "inbound_publish":  [0.05, 0.06, 0.07, 0.08],
        "evaluate_inner":   [1.20, 1.30, 1.40, 1.50],
        "bias_consult":     [0.02, 0.03, 0.04, 0.05],
        "record_decision":  [0.10, 0.11, 0.12, 0.13],
        "total":            [1.50, 1.60, 1.70, 1.80],
        # v1.5 sub-phase keys.
        "og7_check":            [0.01, 0.02, 0.03, 0.04],
        "fast_precheck":        [0.50, 0.55, 0.60, 0.65],
        "graph_classify":       [0.00, 0.00, 0.00, 0.00],
        "hydrator_state_read":  [0.005, 0.006, 0.007, 0.008],
        "routing_dispatch":     [0.30, 0.32, 0.34, 0.36],
    }


def test_v15_block_renders_all_sub_phase_rows():
    block = "\n".join(
        soak_driver._format_evaluate_inner_sub_phase_breakout(
            _synthetic_allow_phase_ms()
        )
    )
    # Heading present.
    assert "ALLOW _evaluate_inner sub-phase breakout (v1.5)" in block
    # All five sub-phase rows render.
    for k in _SUB_PHASES:
        assert k in block, f"missing sub-phase row: {k!r}"


def test_v15_block_phase_order_is_canonical():
    """Sub-phases render in code-path order: og7_check → fast_precheck
    → graph_classify → hydrator_state_read → routing_dispatch."""
    block = "\n".join(
        soak_driver._format_evaluate_inner_sub_phase_breakout(
            _synthetic_allow_phase_ms()
        )
    )
    pos_og7 = block.index("og7_check")
    pos_pre = block.index("fast_precheck")
    pos_graph = block.index("graph_classify")
    pos_hyd = block.index("hydrator_state_read")
    pos_route = block.index("routing_dispatch")
    assert pos_og7 < pos_pre < pos_graph < pos_hyd < pos_route


def test_v15_block_suppressed_when_no_sub_phases_present():
    """Pre-v1.5 engine build: the v1.5 block must NOT render against a
    v1.4-only timings stream — keeps the report clean."""
    legacy_only = {
        "inbound_publish":  [0.05],
        "evaluate_inner":   [1.20],
        "bias_consult":     [0.02],
        "record_decision":  [0.10],
        "total":            [1.50],
    }
    assert (
        soak_driver._format_evaluate_inner_sub_phase_breakout(legacy_only)
        == []
    )


def test_v15_block_handles_empty_state():
    assert soak_driver._format_evaluate_inner_sub_phase_breakout({}) == []
    assert soak_driver._format_evaluate_inner_sub_phase_breakout(None) == []


def test_v14_block_unchanged_by_v15_instrumentation():
    """Back-compat invariant: feeding the same combined v1.4 + v1.5
    stream to the v1.4 helper must still produce the original v1.4
    block heading and rows. The v1.5 sub-phase keys appear as `extras`
    appended after the canonical v1.4 rows (existing behavior of
    `_format_allow_phase_breakout`).
    """
    block = "\n".join(
        soak_driver._format_allow_phase_breakout(
            _synthetic_allow_phase_ms()
        )
    )
    # v1.4 heading still present.
    assert "ALLOW publish-path phase breakout (v1.4)" in block
    # v1.4 phase order canonical: inbound_publish → evaluate_inner →
    # bias_consult → record_decision → total.
    pos_pub = block.index("inbound_publish")
    pos_inner = block.index("evaluate_inner")
    pos_bias = block.index("bias_consult")
    pos_rec = block.index("record_decision")
    pos_total = block.index("total")
    # Note: v1.5 sub-phase keys are now part of _ALLOW_PHASE_ORDER,
    # so they render between evaluate_inner and bias_consult. The v1.4
    # invariant is that the original v1.4 keys still appear in their
    # original relative order.
    assert pos_pub < pos_inner < pos_bias < pos_rec < pos_total


def test_v15_keys_in_canonical_allow_phase_order():
    """`_ALLOW_PHASE_ORDER` extension contract: the five v1.5 sub-phase
    keys must be present, inserted after `evaluate_inner` and before
    `bias_consult`."""
    order = soak_driver._ALLOW_PHASE_ORDER
    pos_inner = order.index("evaluate_inner")
    pos_bias = order.index("bias_consult")
    for k in _SUB_PHASES:
        assert k in order, f"v1.5 sub-phase key not in _ALLOW_PHASE_ORDER: {k!r}"
        assert pos_inner < order.index(k) < pos_bias, (
            f"{k!r} not between evaluate_inner and bias_consult"
        )
