"""gap-4 / INTENT §"Safety priorities" #5 — CLI timeout + 5xx must not
stall the bridge. CliGovernor returns None on degrade; evaluate falls
through to default ALLOW (governance.py:1055-1061) within the budget.
Patch site: CliGovernor._runner (spawn path)."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass

import pytest

from stream_manager.cli_governance import CliGovernor, TIMEOUT_SECONDS
from stream_manager.governance import GovernanceEngine
from stream_manager.latency_budgets import BRIDGE_FALLBACK_LATENCY_BUDGET_MS
from stream_manager.messages import Message
from stream_manager.project_context import _ACTIONABLE_SIGNAL, ProjectContextSnapshot


@dataclass
class _FakeCompletedProcess:
    returncode: int
    stdout: str = ""
    stderr: str = ""


# Actionable-signal payload that no destructive / force-push / token
# rule matches; with empty graph the engine reaches the faulted CLI
# and falls through to default ALLOW.
_SAFE = "cp /tmp/a /tmp/b"

def test_precheck_contract_locked() -> None:
    # If _SAFE stops matching _ACTIONABLE_SIGNAL, fast_precheck short-
    # circuits to ALLOW and the degrade-path tests below silently pass
    # via the wrong code path. Surface the regression as a clean fail.
    assert _ACTIONABLE_SIGNAL.search(_SAFE), "precheck contract broken; pick new _SAFE"


def _engine(runner) -> GovernanceEngine:
    snap = ProjectContextSnapshot(repo_path="/x")
    eng = GovernanceEngine(project_context=snap)
    eng._cli_governor = CliGovernor(snap, runner=runner)
    return eng


def _assert_degrade_to_allow(engine: GovernanceEngine, label: str) -> None:
    start = time.monotonic()
    decision = engine.evaluate(Message.new("user", _SAFE))
    elapsed_ms = (time.monotonic() - start) * 1000.0
    assert decision.action == "ALLOW", f"{label}: action={decision.action}"
    assert decision.source == "default", f"{label}: source={decision.source}"
    assert elapsed_ms < BRIDGE_FALLBACK_LATENCY_BUDGET_MS, (
        f"{label}: {elapsed_ms:.1f} ms > {BRIDGE_FALLBACK_LATENCY_BUDGET_MS}"
    )


def test_engine_returns_default_allow_on_cli_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")

    def runner(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=TIMEOUT_SECONDS)

    _assert_degrade_to_allow(_engine(runner), "timeout")


@pytest.mark.parametrize("status_code", [500, 502, 503])
def test_engine_returns_default_allow_on_cli_5xx(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")

    def runner(cmd, **kwargs):
        return _FakeCompletedProcess(
            returncode=1, stderr=f"upstream {status_code} Internal Server Error\n"
        )

    _assert_degrade_to_allow(_engine(runner), f"{status_code}")
