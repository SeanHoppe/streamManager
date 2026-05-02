"""Tests for AgentRegistry + per-agent governance (FR-AR-6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from stream_manager.agent_registry import AgentRegistry
from stream_manager.governance import GovernanceEngine, Mode
from stream_manager.messages import Message
from stream_manager.project_context import ProjectContextSnapshot

PROFILES_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "stream_manager"
    / "agent_profiles.yaml"
)


@pytest.fixture
def registry() -> AgentRegistry:
    return AgentRegistry(profiles_path=PROFILES_PATH)


def _engine(registry: AgentRegistry, mode: Mode = Mode.INTERVENE) -> GovernanceEngine:
    eng = GovernanceEngine(
        project_context=ProjectContextSnapshot(repo_path="/tmp"),
        registry=registry,
        session_id="test-session",
        mode=mode,
    )
    return eng


def test_resolve_known_example_agent_returns_correct_profile(
    registry: AgentRegistry,
) -> None:
    profile = registry.resolve("Dave", "", is_sidechain=False)
    assert profile.slug == "developer"
    profile = registry.resolve("Jen", "", is_sidechain=False)
    assert profile.slug == "code_reviewer"
    profile = registry.resolve("Michael", "", is_sidechain=False)
    assert profile.slug == "prompt_constructor"


def test_resolve_sidechain_returns_sub_agent_profile(
    registry: AgentRegistry,
) -> None:
    # Unknown plugin name + is_sidechain=True → sub_agent profile.
    profile = registry.resolve("SomeUnknownAgent", "", is_sidechain=True)
    assert profile.slug == "sub_agent"


def test_resolve_unknown_plugin_falls_back_to_unknown_profile(
    registry: AgentRegistry,
) -> None:
    profile = registry.resolve("TotallyUnknown", "", is_sidechain=False)
    assert profile.slug == "unknown"
    # Empty plugin + not sidechain also falls back.
    profile = registry.resolve("", "", is_sidechain=False)
    assert profile.slug == "unknown"


def test_blocked_ops_returns_block_in_governance_evaluate(
    registry: AgentRegistry,
) -> None:
    # code_reviewer (Jen) blocks shell_command and file_write.
    jen_profile = registry.resolve("Jen", "", is_sidechain=False)
    assert "shell_command" in jen_profile.blocked_ops
    engine = _engine(registry)
    registry.update_active("test-session", jen_profile)

    msg = Message.new(role="user", content="bash run pytest -v")
    decision = engine.evaluate(msg)
    assert decision.action == "BLOCK"
    assert decision.confidence == 1.0
    assert decision.source == "agent_profile:code_reviewer"


def test_set_mode_override_round_trip(registry: AgentRegistry) -> None:
    assert registry.get_mode_override("s1", "developer") is None
    registry.set_mode_override("s1", "developer", "BLOCK")
    assert registry.get_mode_override("s1", "developer") == "BLOCK"
    # Independent (session, agent) keys are isolated.
    assert registry.get_mode_override("s2", "developer") is None
    assert registry.get_mode_override("s1", "code_reviewer") is None


def test_set_mode_override_clear_removes(registry: AgentRegistry) -> None:
    registry.set_mode_override("s1", "developer", "GUIDE")
    assert registry.get_mode_override("s1", "developer") == "GUIDE"
    registry.set_mode_override("s1", "developer", None)
    assert registry.get_mode_override("s1", "developer") is None
    # Session map is also pruned when empty.
    assert registry.get_session_overrides("s1") == {}


def test_set_mode_override_rejects_invalid(registry: AgentRegistry) -> None:
    with pytest.raises(ValueError):
        registry.set_mode_override("s1", "developer", "FROBNICATE")
    with pytest.raises(ValueError):
        registry.set_mode_override("s1", "developer", "block")  # case-sensitive
    # None is valid (clear).
    registry.set_mode_override("s1", "developer", None)


def test_get_session_overrides_shape(registry: AgentRegistry) -> None:
    registry.set_mode_override("s1", "developer", "GUIDE")
    registry.set_mode_override("s1", "code_reviewer", "BLOCK")
    registry.set_mode_override("s2", "developer", "OBSERVE")
    s1 = registry.get_session_overrides("s1")
    assert s1 == {"developer": "GUIDE", "code_reviewer": "BLOCK"}
    s2 = registry.get_session_overrides("s2")
    assert s2 == {"developer": "OBSERVE"}
    assert registry.get_session_overrides("nonexistent") == {}


def test_clear_session_overrides_drops_all(registry: AgentRegistry) -> None:
    registry.set_mode_override("s1", "developer", "GUIDE")
    registry.set_mode_override("s1", "code_reviewer", "BLOCK")
    registry.clear_session_overrides("s1")
    assert registry.get_session_overrides("s1") == {}
    assert registry.get_mode_override("s1", "developer") is None


def test_override_block_enforced_in_governance(registry: AgentRegistry) -> None:
    # developer profile default_action=ALLOW; override → BLOCK.
    dev = registry.resolve("Dave", "", is_sidechain=False)
    assert dev.slug == "developer"
    engine = _engine(registry, mode=Mode.BLOCK)
    registry.update_active("test-session", dev)
    registry.set_mode_override("test-session", "developer", "BLOCK")

    # Innocuous content that hits no precheck and no graph match — would
    # normally hit the default ALLOW branch with confidence 0.1.
    msg = Message.new(role="user", content="hello world")
    decision = engine.evaluate(msg)
    assert decision.action == "BLOCK"
    assert decision.source == "agent_profile:developer"


def test_override_none_falls_back_to_phase1_behavior(
    registry: AgentRegistry,
) -> None:
    # No override → behavior matches Phase 1: default ALLOW for innocuous
    # content under the developer profile.
    dev = registry.resolve("Dave", "", is_sidechain=False)
    engine = _engine(registry, mode=Mode.BLOCK)
    registry.update_active("test-session", dev)
    # Explicit no-override.
    assert registry.get_mode_override("test-session", "developer") is None

    msg = Message.new(role="user", content="hello world")
    decision = engine.evaluate(msg)
    assert decision.action == "ALLOW"


def test_override_does_not_bypass_blocked_ops(registry: AgentRegistry) -> None:
    # code_reviewer (Jen) blocks shell_command. Setting override=OBSERVE
    # must NOT bypass blocked_ops — the safety floor is preserved.
    jen = registry.resolve("Jen", "", is_sidechain=False)
    assert "shell_command" in jen.blocked_ops
    engine = _engine(registry, mode=Mode.BLOCK)
    registry.update_active("test-session", jen)
    registry.set_mode_override("test-session", "code_reviewer", "OBSERVE")

    msg = Message.new(role="user", content="bash run pytest -v")
    decision = engine.evaluate(msg)
    assert decision.action == "BLOCK"
    assert decision.source == "agent_profile:code_reviewer"


def test_restricted_ops_caps_action_at_escalate_to(
    registry: AgentRegistry,
) -> None:
    # developer (Dave) lists schema_change as restricted with escalate_to=INTERVENE.
    # We exercise the cap path more directly: use `unknown` profile, which has
    # restricted_ops=[file_edit, shell_command, tool_execution] and
    # escalate_to=INTERVENE. A default-ALLOW message that triggers
    # shell_command classification must be capped to INTERVENE.
    unknown = registry.get("unknown")
    assert unknown is not None
    assert unknown.escalate_to == "INTERVENE"
    assert "shell_command" in unknown.restricted_ops

    engine = _engine(registry, mode=Mode.INTERVENE)
    registry.update_active("test-session", unknown)

    # A message that classifies as shell_command but doesn't trip precheck.
    msg = Message.new(role="user", content="please run pytest -k smoke")
    decision = engine.evaluate(msg)
    # Action capped at escalate_to (INTERVENE) — must not be ALLOW.
    assert decision.action in {"INTERVENE", "BLOCK"}
    # Source reflects the agent_profile origin once the cap kicks in.
    assert decision.source.startswith("agent_profile:unknown") or decision.action == "BLOCK"
