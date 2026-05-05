"""v1.7 P2 soak driver residue-block tests.

Covers the v1.6 CLI residue breakout block's new 6th row
(`cli_dispatch_fallback_ms`) + ensures pre-v1.7 stream suppression keeps
the v1.6 block byte-identical for legacy soak inputs. Also verifies the
v1.4 publish-path block + v1.5 sub-phase block render unchanged.
"""

from __future__ import annotations

from tools.soak_driver import (
    _ALLOW_PHASE_ORDER,
    _format_allow_phase_breakout,
    _format_evaluate_inner_cli_residue_breakout,
    _format_evaluate_inner_sub_phase_breakout,
)


def _v16_stream() -> dict[str, list[float]]:
    """Synthesize a pre-v1.7 (v1.6 engine) stream — all 5 v1.6 CLI residue
    keys present, no cli_dispatch_fallback_ms."""
    return {
        "inbound_publish": [0.5, 0.6, 0.7],
        "evaluate_inner": [5500.0, 5600.0, 5700.0],
        "og7_check": [0.01, 0.02, 0.01],
        "fast_precheck": [0.03, 0.04, 0.03],
        "graph_classify": [0.05, 0.06, 0.05],
        "hydrator_state_read": [0.02, 0.03, 0.02],
        "routing_dispatch": [0.01, 0.01, 0.01],
        "cli_setup_ms": [0.10, 0.12, 0.11],
        "cli_dispatch_ms": [5499.0, 5599.0, 5699.0],
        "cli_pool_acquire_ms": [10.0, 11.0, 12.0],
        "cli_pool_send_ms": [5470.0, 5570.0, 5670.0],
        "cli_parse_ms": [0.5, 0.6, 0.5],
        "bias_consult": [0.01, 0.01, 0.01],
        "hitl_classify_trigger": [0.0, 0.0, 0.0],
        "hitl_route": [0.0, 0.0, 0.0],
        "record_decision": [0.05, 0.06, 0.05],
        "alert_publish": [0.0, 0.0, 0.0],
        "total": [5500.7, 5600.8, 5700.9],
    }


def _v17_stream() -> dict[str, list[float]]:
    """Synthesize a v1.7 stream — same as v1.6 plus cli_dispatch_fallback_ms."""
    s = _v16_stream()
    s["cli_dispatch_fallback_ms"] = [0.0, 0.0, 1234.5]
    return s


def test_allow_phase_order_includes_fallback_after_parse():
    idx_parse = _ALLOW_PHASE_ORDER.index("cli_parse_ms")
    idx_fallback = _ALLOW_PHASE_ORDER.index("cli_dispatch_fallback_ms")
    assert idx_fallback == idx_parse + 1, (
        "cli_dispatch_fallback_ms must immediately follow cli_parse_ms in "
        "_ALLOW_PHASE_ORDER (do NOT reorder existing entries)."
    )


def test_v16_stream_renders_5_row_residue_block_no_fallback():
    """Pre-v1.7 stream — v1.6 CLI residue block must render exactly the
    5 v1.6 rows. The cli_dispatch_fallback_ms row is suppressed so legacy
    soak inputs produce byte-identical block output."""
    lines = _format_evaluate_inner_cli_residue_breakout(_v16_stream())
    body_rows = [ln for ln in lines if ln.startswith("| cli_")]
    assert len(body_rows) == 5
    expected_keys = [
        "cli_setup_ms",
        "cli_dispatch_ms",
        "cli_pool_acquire_ms",
        "cli_pool_send_ms",
        "cli_parse_ms",
    ]
    for key, row in zip(expected_keys, body_rows):
        assert key in row, f"row {row!r} missing key {key!r}"
    assert not any("cli_dispatch_fallback_ms" in ln for ln in lines)


def test_v17_stream_renders_6_row_residue_block_with_fallback():
    lines = _format_evaluate_inner_cli_residue_breakout(_v17_stream())
    body_rows = [ln for ln in lines if ln.startswith("| cli_")]
    assert len(body_rows) == 6
    assert any("cli_dispatch_fallback_ms" in ln for ln in lines)
    # Order: fallback row is the 6th (last) cli_ row.
    assert "cli_dispatch_fallback_ms" in body_rows[5]


def test_v17_stream_fallback_row_zero_data_renders_n_eq_zero():
    s = _v17_stream()
    s["cli_dispatch_fallback_ms"] = []  # key present but no samples
    lines = _format_evaluate_inner_cli_residue_breakout(s)
    fb = [ln for ln in lines if "cli_dispatch_fallback_ms" in ln]
    assert len(fb) == 1
    assert "n/a" in fb[0]


def test_v17_stream_fallback_row_with_data_renders_percentiles():
    lines = _format_evaluate_inner_cli_residue_breakout(_v17_stream())
    fb = [ln for ln in lines if "cli_dispatch_fallback_ms" in ln]
    assert len(fb) == 1
    # Stream has [0.0, 0.0, 1234.5] — p95 should reflect the spike.
    assert "1234" in fb[0] or "1235" in fb[0]


def test_v15_stream_suppresses_v16_block_unchanged():
    """Pre-v1.6 stream (only v1.5 sub-phases, no CLI residue keys) must
    suppress the entire v1.6 block. v1.7 changes must not regress this."""
    s = {
        "inbound_publish": [0.5],
        "evaluate_inner": [5500.0],
        "og7_check": [0.01],
        "fast_precheck": [0.03],
        "graph_classify": [0.05],
        "hydrator_state_read": [0.02],
        "routing_dispatch": [0.01],
    }
    assert _format_evaluate_inner_cli_residue_breakout(s) == []


def test_v15_sub_phase_block_unchanged_under_v17_stream():
    lines = _format_evaluate_inner_sub_phase_breakout(_v17_stream())
    # v1.5 block renders the 5 v1.5 sub-phase rows — must not include
    # any v1.7 cli_dispatch_fallback_ms row.
    assert lines  # block renders
    assert not any("cli_dispatch_fallback_ms" in ln for ln in lines)


def test_v14_publish_path_block_renders_fallback_row_for_v17_stream():
    lines = _format_allow_phase_breakout(_v17_stream())
    fb = [ln for ln in lines if "cli_dispatch_fallback_ms" in ln]
    assert len(fb) == 1


def test_v14_publish_path_block_renders_zero_row_for_v16_stream():
    """Pre-v1.7 stream in the v1.4 publish-path block: cli_dispatch_fallback_ms
    is in _ALLOW_PHASE_ORDER so it renders as n=0 / n/a. Block keeps its
    canonical column shape."""
    lines = _format_allow_phase_breakout(_v16_stream())
    fb = [ln for ln in lines if "cli_dispatch_fallback_ms" in ln]
    assert len(fb) == 1
    assert "n/a" in fb[0]
