"""F10-cli-pool-size-default-zero regression guard.

Finding: ``tools/soak_driver.py`` defaults ``--cli-pool-size`` to 0, which
spawns a fresh ``claude`` subprocess per call -- reintroducing the v1.0
cold-start latency profile (``feedback_soak_cli_pool_flag.md``). It does
NOT invalidate verdicts, because ``cli_governance`` degrades gracefully
under timeout (returns ``None`` rather than raising), so the engine falls
back to a safe verdict instead of failing the run.

These tests pin BOTH halves of the finding deterministically (no live
CLI):

  1. the documented latent default (``--cli-pool-size`` == 0), so a
     silent change to the default is caught; and
  2. the graceful-degrade contract that keeps the default-0 path from
     invalidating verdicts (timeout -> ``None``, no raise).

Named ``test_soak_*`` so it is collected by ``pytest -k test_soak``.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

from stream_manager.cli_governance import CliGovernor
from stream_manager.project_context import ProjectContextSnapshot

ROOT = Path(__file__).resolve().parent.parent
_TOOLS = str(ROOT / "tools")


class _TimeoutRunner:
    """subprocess.run stand-in that always times out (cold-start hang)."""

    def __call__(self, *args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=kwargs.get("timeout", 30.0))


def _build_parser():
    if _TOOLS not in sys.path:
        sys.path.insert(0, _TOOLS)
    sd = importlib.import_module("soak_driver")
    # Re-derive the parser the same way main() does, without running it.
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--cli-pool-size", type=int, default=0)
    return ap, sd


def test_cli_pool_size_default_is_zero_spawn_per_call():
    """Default --cli-pool-size is 0 (legacy spawn-per-call cold-start).

    This is the v1.0 latency-regression default the operator must
    override with --cli-pool-size 2 for a representative ship-gate soak.
    Pinning it makes a silent default change a loud test failure.
    """
    if _TOOLS not in sys.path:
        sys.path.insert(0, _TOOLS)
    sd = importlib.import_module("soak_driver")
    src = Path(sd.__file__).read_text(encoding="utf-8")
    # The argparse default for --cli-pool-size must remain 0, and the help
    # text must keep documenting the cold-start tradeoff.
    assert '"--cli-pool-size"' in src
    # Locate the default beside the flag declaration.
    flag_idx = src.index('"--cli-pool-size"')
    window = src[flag_idx:flag_idx + 400]
    assert "default=0" in window, window
    assert "spawn-per-call" in window, window


def test_default_pool_path_degrades_gracefully_under_timeout(monkeypatch):
    """At pool-size 0 (no pool) a CLI timeout degrades to None, not a raise.

    This is the invariant that keeps the cold-start default from
    invalidating soak verdicts: the engine treats None as a safe-fallback
    verdict rather than a failed evaluation.
    """
    monkeypatch.setenv("BRIDGE_API_GOV", "1")
    snap = ProjectContextSnapshot(repo_path="/x")
    # pool=None mirrors --cli-pool-size 0 (spawn-per-call), runner times out.
    gov = CliGovernor(snap, runner=_TimeoutRunner(), pool=None)
    decision = gov.evaluate("force-push main to roll back the broken merge")
    assert decision is None  # graceful degrade, no exception propagated


def test_default_pool_path_timeout_does_not_raise():
    """Belt-and-suspenders: evaluate must not propagate TimeoutExpired."""
    import os

    os.environ["BRIDGE_API_GOV"] = "1"
    try:
        snap = ProjectContextSnapshot(repo_path="/x")
        gov = CliGovernor(snap, runner=_TimeoutRunner(), pool=None)
        # Must complete (return None); a propagated TimeoutExpired here
        # would fail the soak run and invalidate verdicts.
        try:
            gov.evaluate("anything")
        except subprocess.TimeoutExpired:  # pragma: no cover - guard
            pytest.fail("timeout propagated; default-0 path would invalidate verdicts")
    finally:
        os.environ.pop("BRIDGE_API_GOV", None)
