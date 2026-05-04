"""v1.4 — `engine._last_phase_timings_ms` instrumentation.

Validates that the per-phase wall-clock breakout added in v1.4
(governance.evaluate) populates correctly across the verdict ladder
and that the soak-driver report block renders the data without
losing keys to a future instrumentation addition.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from stream_manager import message_bus as _msg_bus  # noqa: E402
from stream_manager.governance import GovernanceEngine  # noqa: E402
from stream_manager.messages import Message  # noqa: E402
from stream_manager.project_context import (  # noqa: E402
    ProjectContextSnapshot,
)


def _empty_snapshot() -> ProjectContextSnapshot:
    return ProjectContextSnapshot(repo_path=str(ROOT))


@pytest.fixture
def engine_with_bus(tmp_path):
    db = tmp_path / "phase_timing.db"
    bus = _msg_bus.MessageBus(str(db))
    bus.open_session("phase-test", project_slug="test", pid=0)
    snap = _empty_snapshot()
    eng = GovernanceEngine(
        project_context=snap, bus=bus, session_id="phase-test"
    )
    yield eng
    try:
        bus.close_session("phase-test")
    except Exception:
        pass
    bus.close()


def test_phase_timings_populated_after_evaluate(engine_with_bus):
    msg = Message.new(role="user", content="git status")
    engine_with_bus.evaluate(msg)
    timings = engine_with_bus._last_phase_timings_ms
    assert isinstance(timings, dict)
    # Phases that always fire on a routine ALLOW with a bus wired:
    for k in (
        "inbound_publish",
        "evaluate_inner",
        "bias_consult",
        "record_decision",
        "total",
    ):
        assert k in timings, f"missing phase {k!r}"
        assert timings[k] >= 0.0


def test_phase_timings_total_sane_relative_to_components(engine_with_bus):
    """Total wall-clock should be at least as large as evaluate_inner.
    Other phases nest sequentially, so total ≥ sum of any single phase.
    """
    msg = Message.new(role="user", content="ls src/stream_manager")
    engine_with_bus.evaluate(msg)
    t = engine_with_bus._last_phase_timings_ms
    assert t is not None
    assert t["total"] >= t["evaluate_inner"]
    assert t["total"] >= t["inbound_publish"]


def test_phase_timings_reset_per_call(engine_with_bus):
    """Subsequent evaluate() overwrites the prior dict — operators
    should never see stale values from a prior call."""
    engine_with_bus.evaluate(Message.new(role="user", content="git log"))
    first = dict(engine_with_bus._last_phase_timings_ms or {})
    engine_with_bus.evaluate(Message.new(role="user", content="ruff check src/"))
    second = engine_with_bus._last_phase_timings_ms
    assert second is not None
    # Same shape, different values (almost certainly — perf_counter
    # delta of zero across two calls is implausible).
    assert set(first) == set(second)


def test_format_allow_phase_breakout_renders_canonical_order():
    """The report helper renders phases in the canonical order so the
    ship-gate report is consistent across runs."""
    import soak_driver
    block = "\n".join(
        soak_driver._format_allow_phase_breakout(
            {
                "inbound_publish": [0.05, 0.07, 0.09],
                "evaluate_inner":  [0.03, 0.04, 0.05],
                "record_decision": [0.04, 0.06, 0.08],
                "total":           [0.15, 0.20, 0.25],
            }
        )
    )
    # Heading present.
    assert "ALLOW publish-path phase breakout (v1.4)" in block
    # Canonical order: inbound_publish appears before evaluate_inner
    # which appears before record_decision which appears before total.
    pos_pub = block.index("inbound_publish")
    pos_inner = block.index("evaluate_inner")
    pos_rec = block.index("record_decision")
    pos_total = block.index("total")
    assert pos_pub < pos_inner < pos_rec < pos_total


def test_format_allow_phase_breakout_handles_empty_state():
    """No samples → empty list (skips block entirely)."""
    import soak_driver
    assert soak_driver._format_allow_phase_breakout({}) == []
    assert soak_driver._format_allow_phase_breakout(None) == []


def test_format_allow_phase_breakout_includes_unknown_phase_extras():
    """A future engine instrumentation addition should NOT be silently
    dropped from the report — extras render after the canonical rows.
    """
    import soak_driver
    block = "\n".join(
        soak_driver._format_allow_phase_breakout(
            {
                "inbound_publish": [0.1],
                "future_phase":    [0.2],
            }
        )
    )
    assert "future_phase" in block
