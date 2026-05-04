"""v1.6 P1 — soak driver `### ALLOW _evaluate_inner CLI residue
breakout (v1.6)` block.

Validates that the new render helper produces a markdown block with
all five CLI residue rows when fed a synthesized phase-timings stream,
that the canonical render order is preserved, that the block is
suppressed for pre-v1.6 inputs, and that the existing v1.4 + v1.5
blocks render unchanged on the same input.

Diagnoses ADR-5 v1.5 §"Caveats" — v1.5 sub-phases summed to 0.13 ms
p95 vs `evaluate_inner` p95 = 5599 ms; the v1.6 residue block
attributes the remainder.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import soak_driver  # noqa: E402


_RESIDUE_PHASES = (
    "cli_setup_ms",
    "cli_dispatch_ms",
    "cli_pool_acquire_ms",
    "cli_pool_send_ms",
    "cli_parse_ms",
)


def _synthetic_v16_allow_phase_ms() -> dict[str, list[float]]:
    """Phase-timings stream a v1.6 engine would publish for routine
    ALLOW envelopes (CLI-traversed and non-CLI mixed). Numbers are
    illustrative; the helper renders via percentile so any non-empty
    list works."""
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
        # v1.6 P1 CLI residue keys.
        "cli_setup_ms":         [0.10, 0.12, 0.14, 0.16],
        "cli_dispatch_ms":      [400.0, 450.0, 500.0, 550.0],
        "cli_pool_acquire_ms":  [10.0, 12.0, 14.0, 16.0],
        "cli_pool_send_ms":     [380.0, 420.0, 460.0, 500.0],
        "cli_parse_ms":         [0.50, 0.55, 0.60, 0.65],
    }


def _synthetic_pre_v16_allow_phase_ms() -> dict[str, list[float]]:
    """Pre-v1.6 stream — only v1.4 + v1.5 keys. Used for suppression
    check on the v1.6 block."""
    return {
        "inbound_publish":  [0.05, 0.06, 0.07, 0.08],
        "evaluate_inner":   [1.20, 1.30, 1.40, 1.50],
        "bias_consult":     [0.02, 0.03, 0.04, 0.05],
        "record_decision":  [0.10, 0.11, 0.12, 0.13],
        "total":            [1.50, 1.60, 1.70, 1.80],
        "og7_check":            [0.01, 0.02, 0.03, 0.04],
        "fast_precheck":        [0.50, 0.55, 0.60, 0.65],
        "graph_classify":       [0.00, 0.00, 0.00, 0.00],
        "hydrator_state_read":  [0.005, 0.006, 0.007, 0.008],
        "routing_dispatch":     [0.30, 0.32, 0.34, 0.36],
    }


def test_v16_block_renders_all_residue_rows():
    block = "\n".join(
        soak_driver._format_evaluate_inner_cli_residue_breakout(
            _synthetic_v16_allow_phase_ms()
        )
    )
    # Heading present.
    assert "ALLOW _evaluate_inner CLI residue breakout (v1.6)" in block
    # All five residue rows render.
    for k in _RESIDUE_PHASES:
        assert k in block, f"missing residue row: {k!r}"


def test_v16_block_phase_order_is_canonical():
    """Residue phases render in code-path order: cli_setup_ms →
    cli_dispatch_ms → cli_pool_acquire_ms → cli_pool_send_ms →
    cli_parse_ms."""
    block = "\n".join(
        soak_driver._format_evaluate_inner_cli_residue_breakout(
            _synthetic_v16_allow_phase_ms()
        )
    )
    pos_setup = block.index("cli_setup_ms")
    pos_disp = block.index("cli_dispatch_ms")
    pos_acq = block.index("cli_pool_acquire_ms")
    pos_send = block.index("cli_pool_send_ms")
    pos_parse = block.index("cli_parse_ms")
    assert pos_setup < pos_disp < pos_acq < pos_send < pos_parse


def test_v16_block_suppressed_for_pre_v16_streams():
    """Pre-v1.6 engine build: the v1.6 block must NOT render against
    a v1.4 + v1.5 timings stream — keeps the report clean."""
    assert (
        soak_driver._format_evaluate_inner_cli_residue_breakout(
            _synthetic_pre_v16_allow_phase_ms()
        )
        == []
    )


def test_v16_block_handles_empty_state():
    assert soak_driver._format_evaluate_inner_cli_residue_breakout({}) == []
    assert soak_driver._format_evaluate_inner_cli_residue_breakout(None) == []


def test_v16_block_suppressed_for_partial_rollout_streams():
    """Partial-rollout invariant: a stream missing ANY of the five
    residue keys is treated as pre-v1.6 and suppressed. Avoids a
    confusing mix of populated rows + n/a rows in the soak report."""
    partial = {
        "inbound_publish":      [0.05, 0.06],
        "evaluate_inner":       [1.20, 1.30],
        "cli_dispatch_ms":      [400.0, 450.0],
        "cli_pool_send_ms":     [380.0, 420.0],
    }
    assert (
        soak_driver._format_evaluate_inner_cli_residue_breakout(partial)
        == []
    )


def test_v14_and_v15_blocks_unchanged_by_v16_keys():
    """Back-compat invariant: feeding the same combined v1.4 + v1.5 +
    v1.6 stream to the v1.4 and v1.5 helpers must still produce their
    original block headings and rows. The v1.6 keys do NOT break the
    v1.5 sub-phase block ordering or contents."""
    combined = _synthetic_v16_allow_phase_ms()
    block_v14 = "\n".join(
        soak_driver._format_allow_phase_breakout(combined)
    )
    assert "ALLOW publish-path phase breakout (v1.4)" in block_v14
    pos_pub = block_v14.index("inbound_publish")
    pos_inner = block_v14.index("evaluate_inner")
    pos_bias = block_v14.index("bias_consult")
    pos_rec = block_v14.index("record_decision")
    pos_total = block_v14.index("total")
    assert pos_pub < pos_inner < pos_bias < pos_rec < pos_total

    block_v15 = "\n".join(
        soak_driver._format_evaluate_inner_sub_phase_breakout(combined)
    )
    assert "ALLOW _evaluate_inner sub-phase breakout (v1.5)" in block_v15
    pos_og7 = block_v15.index("og7_check")
    pos_pre = block_v15.index("fast_precheck")
    pos_graph = block_v15.index("graph_classify")
    pos_hyd = block_v15.index("hydrator_state_read")
    pos_route = block_v15.index("routing_dispatch")
    assert pos_og7 < pos_pre < pos_graph < pos_hyd < pos_route


def test_v16_keys_in_canonical_allow_phase_order():
    """`_ALLOW_PHASE_ORDER` extension contract: the five v1.6 CLI
    residue keys must be present, inserted after `routing_dispatch`
    (v1.5 sub-phase) and before `bias_consult`."""
    order = soak_driver._ALLOW_PHASE_ORDER
    pos_route = order.index("routing_dispatch")
    pos_bias = order.index("bias_consult")
    for k in _RESIDUE_PHASES:
        assert k in order, f"v1.6 residue key not in _ALLOW_PHASE_ORDER: {k!r}"
        assert pos_route < order.index(k) < pos_bias, (
            f"{k!r} not between routing_dispatch and bias_consult"
        )


def test_v15_canonical_order_unchanged_by_v16_extension():
    """v1.5 do-not-touch contract: pre-existing entries in
    `_ALLOW_PHASE_ORDER` keep their relative positions."""
    order = soak_driver._ALLOW_PHASE_ORDER
    # v1.4 + v1.5 anchor pairs that must hold.
    expected_relative = [
        "inbound_publish",
        "evaluate_inner",
        "og7_check",
        "fast_precheck",
        "graph_classify",
        "hydrator_state_read",
        "routing_dispatch",
        "bias_consult",
        "hitl_classify_trigger",
        "hitl_route",
        "record_decision",
        "alert_publish",
        "total",
    ]
    indices = [order.index(k) for k in expected_relative]
    assert indices == sorted(indices), (
        f"v1.4/v1.5 entries reordered in _ALLOW_PHASE_ORDER: {order}"
    )
