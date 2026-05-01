from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from stream_manager.api_governance import ApiDecision, ApiGovernor, is_enabled
from stream_manager.governance import GovernanceEngine, Mode
from stream_manager.messages import Message
from stream_manager.project_context import ProjectContextSnapshot


@dataclass
class _FakeBlock:
    type: str
    text: str


@dataclass
class _FakeResponse:
    content: list[_FakeBlock]


class _RecordingClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    def with_options(self, **kwargs: Any) -> "_RecordingClient":
        self.calls.append({"with_options": kwargs})
        return self

    @property
    def messages(self) -> "_RecordingClient":
        return self

    def create(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"create": kwargs})
        return _FakeResponse(content=[_FakeBlock(type="text", text=json.dumps(self.payload))])


def test_disabled_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BRIDGE_API_GOV", raising=False)
    snap = ProjectContextSnapshot(repo_path="/x")
    gov = ApiGovernor(snap, client=_RecordingClient({"action": "ALLOW", "confidence": 0.9, "reasoning": "ok"}))
    assert gov.evaluate("rm test.txt") is None


def test_enabled_calls_haiku_with_cached_system(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    snap = ProjectContextSnapshot(
        repo_path="/x",
        intent_text="Project intent: no force-push.",
        has_intent_file=True,
    )
    payload = {"action": "INTERVENE", "confidence": 0.82, "reasoning": "force-push risk"}
    client = _RecordingClient(payload)
    gov = ApiGovernor(snap, client=client)

    decision = gov.evaluate("git push --force origin main")

    assert decision == ApiDecision(action="INTERVENE", confidence=0.82, reasoning="force-push risk")
    create_calls = [c for c in client.calls if "create" in c]
    assert len(create_calls) == 1
    kwargs = create_calls[0]["create"]
    assert kwargs["model"] == "claude-haiku-4-5"
    system = kwargs["system"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert "Project intent: no force-push" in system[0]["text"]
    assert "format" in kwargs["output_config"]
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    timeout_calls = [c for c in client.calls if "with_options" in c]
    assert timeout_calls and timeout_calls[0]["with_options"]["timeout"] == 2.0


def test_invalid_action_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    snap = ProjectContextSnapshot(repo_path="/x")
    client = _RecordingClient({"action": "WAT", "confidence": 1, "reasoning": ""})
    gov = ApiGovernor(snap, client=client)
    assert gov.evaluate("rm -rf x") is None


def test_engine_skips_api_when_precheck_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    snap = ProjectContextSnapshot(repo_path="/x")
    engine = GovernanceEngine(project_context=snap)
    # Inject a recording governor; if API is reached, we'd see a call.
    engine._api_governor = ApiGovernor(snap, client=_RecordingClient(
        {"action": "BLOCK", "confidence": 1, "reasoning": "api"}
    ))
    decision = engine.evaluate(Message.new("user", "rm -rf /"))
    # Precheck hits BLOCK; mode=OBSERVE wraps to ALLOW with original_action=BLOCK.
    assert decision.source == "precheck"
    assert engine._api_governor._client.calls == []  # API never invoked


def test_engine_uses_api_when_uncertain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    snap = ProjectContextSnapshot(repo_path="/x")
    engine = GovernanceEngine(project_context=snap, mode=Mode.GUIDE)
    engine._api_governor = ApiGovernor(snap, client=_RecordingClient(
        {"action": "INTERVENE", "confidence": 0.7, "reasoning": "borderline"}
    ))
    # Content matches no precheck pattern and graph is empty → escalates to API.
    decision = engine.evaluate(Message.new("user", "delete some old logs from /var/log"))
    assert decision.source == "api"
    assert decision.action == "INTERVENE"
    assert decision.reasoning.endswith("borderline")


def test_is_enabled_truthy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for v in ("1", "true", "TRUE", "yes"):
        monkeypatch.setenv("BRIDGE_API_GOV", v)
        assert is_enabled() is True
    for v in ("", "0", "false", "no", "off"):
        monkeypatch.setenv("BRIDGE_API_GOV", v)
        assert is_enabled() is False
