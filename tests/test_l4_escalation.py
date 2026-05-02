"""Tests for L4 Sonnet escalation wired through the CLI subprocess.

Phase 4 follow-up to NFR-M2: when the pre-routing pass classifies a CLI
escalation as L4 (alignment-requiring action + maturity active), the
subprocess `--model` flag MUST be the L4 (Sonnet) model id; otherwise it
falls back to L2/L3 (Haiku). L0/L1 paths must skip the CLI entirely.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from stream_manager.cli_governance import CliGovernor
from stream_manager.governance import GovernanceEngine, Mode
from stream_manager.maturity_reader import MaturityReader
from stream_manager.messages import Message
from stream_manager.model_router import L2_MODEL_DEFAULT, L4_MODEL_DEFAULT
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
        returncode: int = 0,
    ) -> None:
        self.inner_payload = inner_payload
        self.returncode = returncode
        self.calls: list[dict[str, Any]] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append({"cmd": cmd, "kwargs": kwargs})
        envelope = {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": (
                json.dumps(self.inner_payload)
                if self.inner_payload is not None
                else ""
            ),
        }
        return _CompletedProcess(
            returncode=self.returncode,
            stdout=json.dumps(envelope),
        )


def _write_maturity(path: Path) -> None:
    """Write a minimal valid maturity.yaml so MaturityReader is "active"."""
    path.write_text(
        "axes:\n"
        "  - name: A\n"
        "    cells:\n"
        "      - id: A-1\n"
        "        threshold: 1\n"
        "        current: 1\n",
        encoding="utf-8",
    )


# ── L4: alignment trigger → Sonnet model in subprocess args ──────────


def test_alignment_trigger_routes_cli_to_sonnet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Maturity active + alignment keyword in content → CLI gets --model Sonnet."""
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    p = tmp_path / "maturity.yaml"
    _write_maturity(p)
    reader = MaturityReader(p)

    snap = ProjectContextSnapshot(repo_path="/x")
    runner = _RecordingRunner(
        {"action": "GUIDE", "confidence": 0.7, "reasoning": "alignment check"}
    )
    engine = GovernanceEngine(
        project_context=snap,
        mode=Mode.GUIDE,
        maturity=reader,
    )
    engine._cli_governor = CliGovernor(snap, runner=runner)

    # Content that doesn't trip precheck or graph but contains an alignment
    # keyword ("deploy") so the pre-routing pass returns L4. The "docker"
    # token gets the message past the no-actionable-signal precheck rule.
    decision = engine.evaluate(
        Message.new("user", "run docker deploy on the staging cluster")
    )

    assert decision.source == "cli"
    assert len(runner.calls) == 1
    cmd = runner.calls[0]["cmd"]
    assert "--model" in cmd
    model_idx = cmd.index("--model")
    assert cmd[model_idx + 1] == L4_MODEL_DEFAULT


def test_l4_sonnet_env_override_applies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """BRIDGE_L4_MODEL override propagates to the subprocess --model flag."""
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    monkeypatch.setenv("BRIDGE_L4_MODEL", "claude-sonnet-test-override")
    p = tmp_path / "maturity.yaml"
    _write_maturity(p)
    reader = MaturityReader(p)

    snap = ProjectContextSnapshot(repo_path="/x")
    runner = _RecordingRunner(
        {"action": "ALLOW", "confidence": 0.6, "reasoning": "ok"}
    )
    engine = GovernanceEngine(
        project_context=snap,
        mode=Mode.GUIDE,
        maturity=reader,
    )
    engine._cli_governor = CliGovernor(snap, runner=runner)

    # "git" keyword triggers the actionable-signal regex; "merge" is the
    # alignment keyword that promotes routing to L4.
    engine.evaluate(
        Message.new("user", "git checkout main and merge the feature branch")
    )
    assert len(runner.calls) == 1
    cmd = runner.calls[0]["cmd"]
    model_idx = cmd.index("--model")
    assert cmd[model_idx + 1] == "claude-sonnet-test-override"


# ── L2/L3: no alignment trigger → Haiku model in subprocess args ─────


def test_no_alignment_trigger_routes_cli_to_haiku(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No maturity reader and no alignment keyword → CLI gets --model Haiku."""
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    snap = ProjectContextSnapshot(repo_path="/x")
    runner = _RecordingRunner(
        {"action": "INTERVENE", "confidence": 0.7, "reasoning": "borderline"}
    )
    engine = GovernanceEngine(project_context=snap, mode=Mode.GUIDE)
    engine._cli_governor = CliGovernor(snap, runner=runner)

    decision = engine.evaluate(
        Message.new("user", "delete some old logs from /var/log")
    )

    assert decision.source == "cli"
    assert len(runner.calls) == 1
    cmd = runner.calls[0]["cmd"]
    model_idx = cmd.index("--model")
    assert cmd[model_idx + 1] == L2_MODEL_DEFAULT


def test_alignment_keyword_without_maturity_stays_haiku(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Alignment keyword but no maturity reader → still Haiku (gate condition)."""
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    snap = ProjectContextSnapshot(repo_path="/x")
    runner = _RecordingRunner(
        {"action": "ALLOW", "confidence": 0.6, "reasoning": "ok"}
    )
    engine = GovernanceEngine(project_context=snap, mode=Mode.GUIDE)
    engine._cli_governor = CliGovernor(snap, runner=runner)

    # Same alignment-keyword content as the override test but no maturity →
    # gate condition keeps routing at L2/L3 (Haiku) regardless of keyword.
    engine.evaluate(
        Message.new("user", "git checkout main and merge the feature branch")
    )

    assert len(runner.calls) == 1
    cmd = runner.calls[0]["cmd"]
    model_idx = cmd.index("--model")
    assert cmd[model_idx + 1] == L2_MODEL_DEFAULT


# ── L0/L1: short-circuit, no subprocess at all ───────────────────────


def test_l0_precheck_skips_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """precheck hit → L0, CLI subprocess never invoked."""
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    snap = ProjectContextSnapshot(repo_path="/x")
    runner = _RecordingRunner(
        {"action": "BLOCK", "confidence": 1.0, "reasoning": "should not run"}
    )
    engine = GovernanceEngine(project_context=snap)
    engine._cli_governor = CliGovernor(snap, runner=runner)

    decision = engine.evaluate(Message.new("user", "rm -rf /"))

    assert decision.source == "precheck"
    assert runner.calls == []


def test_l1_high_confidence_graph_skips_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """High-confidence graph match → L1, CLI subprocess never invoked."""
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    snap = ProjectContextSnapshot(repo_path="/x")
    runner = _RecordingRunner(
        {"action": "BLOCK", "confidence": 1.0, "reasoning": "should not run"}
    )
    engine = GovernanceEngine(project_context=snap, mode=Mode.GUIDE)
    engine._cli_governor = CliGovernor(snap, runner=runner)

    # Seed the graph with multiple successes so success_rate is high enough
    # to short-circuit before the CLI fallback runs.
    content = "look at the configuration in app.yaml please"
    for _ in range(20):
        engine.observe_for_learning(Message.new("user", content), True)

    decision = engine.evaluate(Message.new("user", content))
    assert decision.source == "graph"
    assert runner.calls == []
