from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any

import pytest

from stream_manager.cli_governance import CliDecision, CliGovernor, is_enabled
from stream_manager.governance import GovernanceEngine, Mode
from stream_manager.messages import Message
from stream_manager.project_context import ProjectContextSnapshot


@dataclass
class _CompletedProcess:
    returncode: int
    stdout: str
    stderr: str = ""


class _RecordingRunner:
    """Stand-in for subprocess.run that records every invocation."""

    def __init__(
        self,
        inner_payload: dict[str, Any] | None = None,
        *,
        envelope_override: dict[str, Any] | None = None,
        returncode: int = 0,
        raise_exc: BaseException | None = None,
    ) -> None:
        self.inner_payload = inner_payload
        self.envelope_override = envelope_override
        self.returncode = returncode
        self.raise_exc = raise_exc
        self.calls: list[dict[str, Any]] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append({"cmd": cmd, "kwargs": kwargs})
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.envelope_override is not None:
            stdout = json.dumps(self.envelope_override)
        else:
            envelope = {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": json.dumps(self.inner_payload) if self.inner_payload is not None else "",
            }
            stdout = json.dumps(envelope)
        return _CompletedProcess(returncode=self.returncode, stdout=stdout)


def test_disabled_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BRIDGE_API_GOV", raising=False)
    snap = ProjectContextSnapshot(repo_path="/x")
    runner = _RecordingRunner({"action": "ALLOW", "confidence": 0.9, "reasoning": "ok"})
    gov = CliGovernor(snap, runner=runner)
    assert gov.evaluate("rm test.txt") is None
    assert runner.calls == []  # subprocess never invoked when disabled


def test_enabled_invokes_cli_with_model_and_intent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    snap = ProjectContextSnapshot(
        repo_path="/x",
        intent_text="Project intent: no force-push.",
        has_intent_file=True,
    )
    payload = {"action": "INTERVENE", "confidence": 0.82, "reasoning": "force-push risk"}
    runner = _RecordingRunner(payload)
    gov = CliGovernor(snap, runner=runner)

    decision = gov.evaluate("git push --force origin main")

    assert decision == CliDecision(action="INTERVENE", confidence=0.82, reasoning="force-push risk")
    assert len(runner.calls) == 1
    cmd = runner.calls[0]["cmd"]
    assert cmd[0] == "claude"
    assert "-p" in cmd
    assert "--output-format" in cmd and "json" in cmd
    assert "--model" in cmd
    assert "claude-haiku-4-5" in cmd
    prompt = cmd[cmd.index("-p") + 1]
    assert "Project intent: no force-push" in prompt
    assert "git push --force origin main" in prompt
    kwargs = runner.calls[0]["kwargs"]
    assert kwargs["timeout"] == 5.0
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True


def test_invalid_action_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    snap = ProjectContextSnapshot(repo_path="/x")
    runner = _RecordingRunner({"action": "WAT", "confidence": 1, "reasoning": ""})
    gov = CliGovernor(snap, runner=runner)
    assert gov.evaluate("rm -rf x") is None


def test_cli_missing_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    snap = ProjectContextSnapshot(repo_path="/x")
    runner = _RecordingRunner(raise_exc=FileNotFoundError("claude"))
    gov = CliGovernor(snap, runner=runner)
    assert gov.evaluate("anything") is None


def test_timeout_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    snap = ProjectContextSnapshot(repo_path="/x")
    runner = _RecordingRunner(raise_exc=subprocess.TimeoutExpired(cmd="claude", timeout=5.0))
    gov = CliGovernor(snap, runner=runner)
    assert gov.evaluate("anything") is None


def test_nonzero_exit_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    snap = ProjectContextSnapshot(repo_path="/x")
    runner = _RecordingRunner({"action": "ALLOW", "confidence": 1, "reasoning": ""}, returncode=1)
    gov = CliGovernor(snap, runner=runner)
    assert gov.evaluate("anything") is None


def test_envelope_is_error_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    snap = ProjectContextSnapshot(repo_path="/x")
    runner = _RecordingRunner(
        envelope_override={"type": "result", "is_error": True, "result": ""},
    )
    gov = CliGovernor(snap, runner=runner)
    assert gov.evaluate("anything") is None


def test_outer_json_garbage_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    snap = ProjectContextSnapshot(repo_path="/x")

    def runner(cmd, **kwargs):
        return _CompletedProcess(returncode=0, stdout="not json at all")

    gov = CliGovernor(snap, runner=runner)
    assert gov.evaluate("anything") is None


def test_inner_json_garbage_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    snap = ProjectContextSnapshot(repo_path="/x")
    runner = _RecordingRunner(
        envelope_override={
            "type": "result",
            "is_error": False,
            "result": "definitely not json",
        }
    )
    gov = CliGovernor(snap, runner=runner)
    assert gov.evaluate("anything") is None


def test_engine_skips_cli_when_precheck_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    snap = ProjectContextSnapshot(repo_path="/x")
    engine = GovernanceEngine(project_context=snap)
    runner = _RecordingRunner({"action": "BLOCK", "confidence": 1, "reasoning": "cli"})
    engine._cli_governor = CliGovernor(snap, runner=runner)
    decision = engine.evaluate(Message.new("user", "rm -rf /"))
    assert decision.source == "precheck"
    assert runner.calls == []


def test_engine_uses_cli_when_uncertain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    snap = ProjectContextSnapshot(repo_path="/x")
    engine = GovernanceEngine(project_context=snap, mode=Mode.GUIDE)
    runner = _RecordingRunner(
        {"action": "INTERVENE", "confidence": 0.7, "reasoning": "borderline"}
    )
    engine._cli_governor = CliGovernor(snap, runner=runner)
    decision = engine.evaluate(Message.new("user", "delete some old logs from /var/log"))
    assert decision.source == "cli"
    assert decision.action == "INTERVENE"
    assert decision.reasoning.endswith("borderline")


def test_is_enabled_truthy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for v in ("1", "true", "TRUE", "yes"):
        monkeypatch.setenv("BRIDGE_API_GOV", v)
        assert is_enabled() is True
    for v in ("", "0", "false", "no", "off"):
        monkeypatch.setenv("BRIDGE_API_GOV", v)
        assert is_enabled() is False
