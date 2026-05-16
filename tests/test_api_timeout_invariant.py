"""gap-4 / INTENT §"Safety priorities" #5 — API-timeout invariant.

CLI timeout + 5xx must NOT stall the bridge: ``CliGovernor`` returns
``None`` on degrade and ``GovernanceEngine.evaluate`` falls through to
default ALLOW (governance.py:1055-1061), inside
``BRIDGE_FALLBACK_LATENCY_BUDGET_MS``.

Assertion is at the bridge boundary (``decision.action == "ALLOW"``
+ ``decision.source == "default"``) so the test protects against
future engine refactors that might mistranslate the CLI degrade signal.

Patch site: ``CliGovernor._runner`` (spawn path; pool=None). Both fault
classes exercise cleanly without warm-pool scaffolding. TimeoutExpired
is raised immediately by the fake runner; total wall-clock is
millisecond order, not 25 real seconds.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass

import pytest

from stream_manager.cli_governance import CliGovernor, TIMEOUT_SECONDS
from stream_manager.governance import GovernanceEngine
from stream_manager.latency_budgets import BRIDGE_FALLBACK_LATENCY_BUDGET_MS
from stream_manager.messages import Message
from stream_manager.project_context import ProjectContextSnapshot


@dataclass
class _FakeCompletedProcess:
    returncode: int
    stdout: str = ""
    stderr: str = ""


# "cp /tmp/a /tmp/b" carries an actionable shell signal (``cp`` is in
# project_context._ACTIONABLE_SIGNAL) so precheck does not fast-ALLOW
# via the no-actionable-signal path. It matches no destructive pattern,
# no force-push rule, no plaintext-token rule. With a fresh engine
# (empty graph), the message reaches the CLI layer; the faulted runner
# then makes the engine fall through to default ALLOW at
# governance.py:1055-1061.
_SAFE = "cp /tmp/a /tmp/b"


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
