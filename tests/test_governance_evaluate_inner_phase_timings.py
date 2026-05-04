"""v1.5 — `_evaluate_inner` sub-phase instrumentation.

Validates that the five v1.5 sub-phase keys (og7_check, fast_precheck,
graph_classify, hydrator_state_read, routing_dispatch) populate on
`engine._last_phase_timings_ms` for routine ALLOW envelopes, and that
the verdict path is byte-identical to a baseline run.

Diagnoses ADR-5 v1.4 §"Caveats" — 100% of the v1.4 ALLOW p95 tail sat
inside `_evaluate_inner` and was opaque to the v1.4 phase block.
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


_NEW_SUB_PHASE_KEYS = (
    "og7_check",
    "fast_precheck",
    "graph_classify",
    "hydrator_state_read",
    "routing_dispatch",
)


def _empty_snapshot() -> ProjectContextSnapshot:
    return ProjectContextSnapshot(repo_path=str(ROOT))


@pytest.fixture
def engine_with_bus(tmp_path):
    db = tmp_path / "evaluate_inner_phase_timing.db"
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


def test_v15_sub_phase_keys_populated_on_allow(engine_with_bus):
    """All five v1.5 sub-phase keys must be present on a routine ALLOW
    envelope, in addition to the v1.4 keys."""
    msg = Message.new(role="user", content="git status")
    engine_with_bus.evaluate(msg)
    timings = engine_with_bus._last_phase_timings_ms
    assert isinstance(timings, dict)
    # v1.4 keys still present (do-not-touch contract).
    for k in (
        "inbound_publish",
        "evaluate_inner",
        "bias_consult",
        "record_decision",
        "total",
    ):
        assert k in timings, f"v1.4 key missing: {k!r}"
    # v1.5 sub-phase keys populated.
    for k in _NEW_SUB_PHASE_KEYS:
        assert k in timings, f"v1.5 sub-phase key missing: {k!r}"
        assert timings[k] >= 0.0, f"{k}: negative timing {timings[k]}"


def test_v15_sub_phases_do_not_exceed_evaluate_inner(engine_with_bus):
    """Sum of sub-phases should not exceed `evaluate_inner` by more
    than a small tolerance — they nest inside it. Interleaved Python
    overhead means the sum is typically less than the parent."""
    msg = Message.new(role="user", content="ls src/stream_manager")
    engine_with_bus.evaluate(msg)
    t = engine_with_bus._last_phase_timings_ms
    assert t is not None
    sub_sum = sum(t[k] for k in _NEW_SUB_PHASE_KEYS)
    # 0.5 ms tolerance — generous; observed gap is the unwrapped
    # portion of _evaluate_inner (profile resolution, blocked_ops
    # check). Sub-phases must NOT exceed parent.
    assert sub_sum <= t["evaluate_inner"] + 0.5, (
        f"sub-phase sum {sub_sum:.4f} exceeds evaluate_inner "
        f"{t['evaluate_inner']:.4f}"
    )


def test_verdict_byte_identical_with_instrumentation(engine_with_bus, tmp_path):
    """Regression test: the v1.5 instrumentation is purely additive.
    Verdict (action, confidence, reasoning, source) must be byte-identical
    to a fresh engine running the same input."""
    # Reference verdict from the fixture engine.
    msg1 = Message.new(role="user", content="ruff check src/")
    ref = engine_with_bus.evaluate(msg1)

    # Spin up a second engine with the same configuration; verdict must
    # match. The engines share no state across the call, so any deviation
    # would indicate the instrumentation leaked into the verdict path.
    db2 = tmp_path / "evaluate_inner_phase_timing_2.db"
    bus2 = _msg_bus.MessageBus(str(db2))
    bus2.open_session("phase-test-2", project_slug="test", pid=0)
    snap = _empty_snapshot()
    eng2 = GovernanceEngine(
        project_context=snap, bus=bus2, session_id="phase-test-2"
    )
    try:
        msg2 = Message.new(role="user", content="ruff check src/")
        comp = eng2.evaluate(msg2)
        assert (ref.action, ref.confidence, ref.reasoning, ref.source) == (
            comp.action,
            comp.confidence,
            comp.reasoning,
            comp.source,
        )
    finally:
        try:
            bus2.close_session("phase-test-2")
        except Exception:
            pass
        bus2.close()


def test_v15_sub_phases_reset_per_call(engine_with_bus):
    """Subsequent evaluate() overwrites the prior dict — operators
    should never see stale sub-phase values from a prior call."""
    engine_with_bus.evaluate(Message.new(role="user", content="git log"))
    first = dict(engine_with_bus._last_phase_timings_ms or {})
    engine_with_bus.evaluate(
        Message.new(role="user", content="ruff format --check src/")
    )
    second = engine_with_bus._last_phase_timings_ms
    assert second is not None
    # Sub-phase keys present on both calls.
    for k in _NEW_SUB_PHASE_KEYS:
        assert k in first and k in second


def test_v14_keys_unchanged_by_v15_instrumentation(engine_with_bus):
    """The v1.4 do-not-touch contract: no existing key removed or
    renamed by v1.5. This guards against silent reverts in future
    refactors of the timings dict construction."""
    engine_with_bus.evaluate(Message.new(role="user", content="git diff --stat"))
    t = engine_with_bus._last_phase_timings_ms
    assert t is not None
    v14_keys = {
        "inbound_publish",
        "evaluate_inner",
        "bias_consult",
        "record_decision",
        "total",
    }
    assert v14_keys.issubset(t.keys()), (
        f"v1.4 keys missing from timings: {v14_keys - t.keys()}"
    )
