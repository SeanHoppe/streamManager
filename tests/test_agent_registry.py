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
