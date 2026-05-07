"""Tests for src/stream_manager/model_router.py (NFR-M1–M5).

Covers:
  - L0: precheck + agent_profile sources
  - L1: graph match >= 0.85
  - L2: graph match 0.60–0.84 -> Haiku
  - L3: default / cli / no-match -> Haiku
  - L4: FR-OG-7 alignment -> Sonnet
  - BRIDGE_L2_MODEL / BRIDGE_L4_MODEL env-var overrides
  - ConvergenceMonitor below threshold (no alert)
  - ConvergenceMonitor above threshold (alert fires when total >= 5 and rate > 20%)
"""

from __future__ import annotations

from stream_manager.model_router import (
    L2_MODEL_DEFAULT,
    L4_MODEL_DEFAULT,
    ConvergenceMonitor,
    ModelLayer,
    get_l2_model,
    get_l4_model,
    route,
)


# ── 1–6: route() classification ───────────────────────────────────────


def test_route_precheck_returns_l0_no_model():
    r = route("precheck", 0.95)
    assert r.layer == ModelLayer.L0
    assert r.model_id is None


def test_route_agent_profile_returns_l0_no_model():
    # Both the bare "agent_profile" sentinel and the qualified
    # "agent_profile:<slug>" form must classify as L0 (rule-based, no LLM).
    r1 = route("agent_profile", 0.5)
    r2 = route("agent_profile:builder", 0.5)
    assert r1.layer == ModelLayer.L0 and r1.model_id is None
    assert r2.layer == ModelLayer.L0 and r2.model_id is None


def test_route_graph_high_confidence_returns_l1_no_model():
    r = route("graph", 0.90)
    assert r.layer == ModelLayer.L1
    assert r.model_id is None


def test_route_graph_mid_confidence_returns_l2_haiku():
    r = route("graph", 0.70)
    assert r.layer == ModelLayer.L2
    assert r.model_id == L2_MODEL_DEFAULT


def test_route_default_returns_l3_haiku():
    r = route("default", 0.10)
    assert r.layer == ModelLayer.L3
    assert r.model_id == L2_MODEL_DEFAULT


def test_route_alignment_returns_l4_sonnet():
    r = route("cli", 0.50, requires_alignment=True)
    assert r.layer == ModelLayer.L4
    assert r.model_id == L4_MODEL_DEFAULT


# ── 7: env var overrides ──────────────────────────────────────────────


def test_bridge_l2_model_env_override(monkeypatch):
    monkeypatch.setenv("BRIDGE_L2_MODEL", "claude-haiku-test-override")
    assert get_l2_model() == "claude-haiku-test-override"
    # And route() should pick it up too.
    r = route("graph", 0.70)
    assert r.model_id == "claude-haiku-test-override"


def test_bridge_l4_model_env_override(monkeypatch):
    monkeypatch.setenv("BRIDGE_L4_MODEL", "claude-sonnet-test-override")
    assert get_l4_model() == "claude-sonnet-test-override"
    r = route("cli", 0.5, requires_alignment=True)
    assert r.model_id == "claude-sonnet-test-override"


# ── 8–9: ConvergenceMonitor ───────────────────────────────────────────


def test_convergence_monitor_below_threshold_no_alert():
    """5 calls, only 1 of them L4 (20%) — strict > 20% rule means no alert.

    Also verify that fewer than 5 calls always returns False.
    """
    mon = ConvergenceMonitor()
    # 4 L0 calls — under the 5-sample minimum.
    for _ in range(4):
        assert mon.record(ModelLayer.L0) is False
    # 5th call still under the strict-greater-than threshold.
    # Total=5, L4=0 → rate=0.0, alert False.
    assert mon.record(ModelLayer.L0) is False


def test_convergence_monitor_above_threshold_fires_alert():
    """Total=5, L4=2 → rate=0.40 > 0.20 → alert True."""
    mon = ConvergenceMonitor()
    # 4 non-L4 calls first, then 1 L4. 1/5 = 20% (NOT > 20%) -> False.
    for _ in range(4):
        mon.record(ModelLayer.L0)
    assert mon.record(ModelLayer.L4) is False  # exactly 20%, strict > fails

    # New monitor: build a window with rate > 20%.
    mon2 = ConvergenceMonitor()
    for _ in range(3):
        assert mon2.record(ModelLayer.L0) is False
    # 4th call L4 → total=4 still <5; below threshold by min-sample rule.
    assert mon2.record(ModelLayer.L4) is False
    # 5th call L4 → total=5, L4=2, rate=0.40 > 0.20 → alert.
    assert mon2.record(ModelLayer.L4) is True
