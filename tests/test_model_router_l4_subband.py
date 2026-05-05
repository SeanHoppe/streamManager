"""v1.7 P2 L4 sub-band routing tests.

Asserts the new RoutingDecision.fallback_model_id field and the L4 sub-band
priority:
  - requires_alignment      → Sonnet only, NO fallback (FR-OG-7 protected)
  - is_ambiguous_block      → Haiku-first with Sonnet fallback
  - is_hitl_synthesis       → Haiku-first with Sonnet fallback
  - requires_alignment beats both other flags when set together

Verdict-path invariant: priority order alignment > L0 > L1 > L2 > L3
is unchanged. The L4 sub-band only refines the model selection within
L4; layer assignment for non-L4 paths is identical to v1.6.
"""

from __future__ import annotations

from stream_manager.model_router import (
    L2_MODEL_DEFAULT,
    L4_MODEL_DEFAULT,
    ModelLayer,
    RoutingDecision,
    route,
)


def test_routing_decision_fallback_model_id_default_none():
    # v1.6 callers construct with 2 positional args; fallback_model_id
    # must default to None so they observe identical behavior.
    rd = RoutingDecision(ModelLayer.L4, L4_MODEL_DEFAULT)
    assert rd.fallback_model_id is None


def test_alignment_only_returns_sonnet_no_fallback():
    r = route("cli", 0.50, requires_alignment=True)
    assert r.layer == ModelLayer.L4
    assert r.model_id == L4_MODEL_DEFAULT
    assert r.fallback_model_id is None  # FR-OG-7: never fall back to Haiku


def test_ambiguous_block_only_returns_haiku_with_sonnet_fallback():
    r = route("graph", 0.50, is_ambiguous_block=True)
    assert r.layer == ModelLayer.L4
    assert r.model_id == L2_MODEL_DEFAULT
    assert r.fallback_model_id == L4_MODEL_DEFAULT


def test_hitl_synthesis_only_returns_haiku_with_sonnet_fallback():
    r = route("default", 0.50, is_hitl_synthesis=True)
    assert r.layer == ModelLayer.L4
    assert r.model_id == L2_MODEL_DEFAULT
    assert r.fallback_model_id == L4_MODEL_DEFAULT


def test_alignment_plus_ambiguous_block_alignment_wins():
    # requires_alignment beats is_ambiguous_block — FR-OG-7 protected.
    r = route("graph", 0.50, requires_alignment=True, is_ambiguous_block=True)
    assert r.layer == ModelLayer.L4
    assert r.model_id == L4_MODEL_DEFAULT
    assert r.fallback_model_id is None


def test_alignment_plus_hitl_synthesis_alignment_wins():
    r = route("default", 0.50, requires_alignment=True, is_hitl_synthesis=True)
    assert r.layer == ModelLayer.L4
    assert r.model_id == L4_MODEL_DEFAULT
    assert r.fallback_model_id is None


def test_ambiguous_block_plus_hitl_synthesis_both_fastpath():
    # Neither flag is alignment; both want the fastpath. Result is the
    # same as either alone — Haiku with Sonnet fallback.
    r = route("default", 0.50, is_ambiguous_block=True, is_hitl_synthesis=True)
    assert r.layer == ModelLayer.L4
    assert r.model_id == L2_MODEL_DEFAULT
    assert r.fallback_model_id == L4_MODEL_DEFAULT


def test_l4_subband_trumps_l0_precheck_source():
    # Priority order invariant: L4 alignment branch beats L0 precheck source.
    r = route("precheck", 1.0, requires_alignment=True)
    assert r.layer == ModelLayer.L4
    assert r.fallback_model_id is None


def test_l4_fastpath_trumps_l1_high_confidence_graph():
    # Priority order invariant: L4 fastpath beats L1 graph 0.85+.
    r = route("graph", 0.99, is_ambiguous_block=True)
    assert r.layer == ModelLayer.L4
    assert r.model_id == L2_MODEL_DEFAULT
    assert r.fallback_model_id == L4_MODEL_DEFAULT


def test_no_l4_flags_falls_through_priority_bands_unchanged():
    # When no L4 flag is set, layer assignment is identical to v1.6.
    # fallback_model_id is None for non-L4 layers.
    assert route("precheck", 0.0).layer == ModelLayer.L0
    assert route("graph", 0.90).layer == ModelLayer.L1
    assert route("graph", 0.70).layer == ModelLayer.L2
    assert route("default", 0.0).layer == ModelLayer.L3
    for src, conf in [("precheck", 0.0), ("graph", 0.90), ("graph", 0.70), ("default", 0.0)]:
        assert route(src, conf).fallback_model_id is None


def test_env_override_propagates_to_fallback_model_id(monkeypatch):
    monkeypatch.setenv("BRIDGE_L4_MODEL", "claude-sonnet-test-override")
    monkeypatch.setenv("BRIDGE_L2_MODEL", "claude-haiku-test-override")
    r = route("graph", 0.50, is_ambiguous_block=True)
    assert r.model_id == "claude-haiku-test-override"
    assert r.fallback_model_id == "claude-sonnet-test-override"
