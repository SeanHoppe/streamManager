"""gap-4 / INTENT §"Safety priorities" #5 — API-timeout invariant.

CLI timeout + 5xx must degrade ``CliGovernor.evaluate`` to ``None``
(the engine's degrade signal → default-allow → bridge forwards, never
blocks) and complete under ``BRIDGE_FALLBACK_LATENCY_BUDGET_MS``
imported LIVE (no literal ms pin).

Patch target: ``CliGovernor._runner`` (spawn path, pool=None) — chosen
because both fault classes exercise cleanly without warm-pool scaffolding.
TimeoutExpired is raised immediately by the fake runner; the test runs
in millisecond wall-clock, not 25 real seconds.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass

import pytest

from stream_manager.cli_governance import CliGovernor, TIMEOUT_SECONDS
from stream_manager.latency_budgets import BRIDGE_FALLBACK_LATENCY_BUDGET_MS
from stream_manager.project_context import ProjectContextSnapshot


@dataclass
class _FakeCompletedProcess:
    returncode: int
    stdout: str = ""
    stderr: str = ""


def _governor(runner) -> CliGovernor:
    return CliGovernor(ProjectContextSnapshot(repo_path="/x"), runner=runner)


def test_cli_timeout_degrades_to_observe_under_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timeout fault class: subprocess.TimeoutExpired -> evaluate() == None."""
    monkeypatch.setenv("BRIDGE_API_GOV", "true")

    def _runner_raises_timeout(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=TIMEOUT_SECONDS)

    gov = _governor(_runner_raises_timeout)
    start = time.monotonic()
    decision = gov.evaluate("git push --force origin main")
    elapsed_ms = (time.monotonic() - start) * 1000.0

    assert decision is None, "CLI timeout must degrade evaluate() to None"
    assert elapsed_ms < BRIDGE_FALLBACK_LATENCY_BUDGET_MS, (
        f"timeout degrade took {elapsed_ms:.1f} ms; budget is "
        f"{BRIDGE_FALLBACK_LATENCY_BUDGET_MS} ms"
    )


@pytest.mark.parametrize("status_code", [500, 502, 503])
def test_cli_5xx_error_degrades_to_observe_under_budget(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
) -> None:
    """5xx fault class: non-zero exit w/ 5xx-shaped stderr -> evaluate() == None."""
    monkeypatch.setenv("BRIDGE_API_GOV", "true")

    def _runner_returns_5xx(cmd, **kwargs):
        return _FakeCompletedProcess(
            returncode=1, stderr=f"upstream {status_code} Internal Server Error\n"
        )

    gov = _governor(_runner_returns_5xx)
    start = time.monotonic()
    decision = gov.evaluate("git push --force origin main")
    elapsed_ms = (time.monotonic() - start) * 1000.0

    assert decision is None, f"CLI {status_code} must degrade evaluate() to None"
    assert elapsed_ms < BRIDGE_FALLBACK_LATENCY_BUDGET_MS, (
        f"{status_code} degrade took {elapsed_ms:.1f} ms; budget is "
        f"{BRIDGE_FALLBACK_LATENCY_BUDGET_MS} ms"
    )
