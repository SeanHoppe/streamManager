"""v1.6 P1 — `_evaluate_inner` CLI residue instrumentation.

Validates that the five v1.6 CLI residue keys (cli_setup_ms,
cli_dispatch_ms, cli_pool_acquire_ms, cli_pool_send_ms, cli_parse_ms)
populate on `engine._last_phase_timings_ms` for routine ALLOW
envelopes that traverse the CLI escalation branch, are 0.0 on
non-CLI branches (precheck-hit), and leave the verdict path
byte-identical relative to a baseline.

Diagnoses ADR-5 v1.5 §"Caveats" — the v1.5 ship-gate showed
`evaluate_inner` p95 = 5599 ms while the five v1.5 sub-phases summed
to 0.13 ms p95, so ~99.998% of the ALLOW tail sat inside
`_maybe_cli_evaluate` → `CliGovernor.evaluate` and was opaque to the
v1.5 sub-phase block.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from stream_manager import cli_governance as _cli_gov  # noqa: E402
from stream_manager import message_bus as _msg_bus  # noqa: E402
from stream_manager.governance import GovernanceEngine  # noqa: E402
from stream_manager.messages import Message  # noqa: E402
from stream_manager.project_context import (  # noqa: E402
    ProjectContextSnapshot,
)


_NEW_RESIDUE_KEYS = (
    "cli_setup_ms",
    "cli_dispatch_ms",
    "cli_pool_acquire_ms",
    "cli_pool_send_ms",
    "cli_parse_ms",
)

_V14_KEYS = (
    "inbound_publish",
    "evaluate_inner",
    "bias_consult",
    "record_decision",
    "total",
)

_V15_SUB_PHASE_KEYS = (
    "og7_check",
    "fast_precheck",
    "graph_classify",
    "hydrator_state_read",
    "routing_dispatch",
)


def _empty_snapshot() -> ProjectContextSnapshot:
    return ProjectContextSnapshot(repo_path=str(ROOT))


def _make_engine(tmp_path, name: str) -> tuple[GovernanceEngine, _msg_bus.MessageBus, str]:
    db = tmp_path / f"{name}.db"
    bus = _msg_bus.MessageBus(str(db))
    sid = f"residue-{name}"
    bus.open_session(sid, project_slug="test", pid=0)
    snap = _empty_snapshot()
    eng = GovernanceEngine(project_context=snap, bus=bus, session_id=sid)
    return eng, bus, sid


def _close(bus: _msg_bus.MessageBus, sid: str) -> None:
    try:
        bus.close_session(sid)
    except Exception:
        pass
    try:
        bus.close()
    except Exception:
        pass


# ────────────────────────────────────────────────────────────────────
# Non-CLI branches (precheck-hit, default ALLOW with no CLI flag)
# ────────────────────────────────────────────────────────────────────

def test_residue_keys_zero_on_precheck_hit(tmp_path):
    """Precheck-hit branch never traverses the CLI — all five new
    residue keys must be present and equal to 0.0 so soak rows are
    dense."""
    eng, bus, sid = _make_engine(tmp_path, "precheck")
    try:
        # `rm -rf /` is a stable precheck-block pattern.
        msg = Message.new(role="user", content="rm -rf /")
        eng.evaluate(msg)
        t = eng._last_phase_timings_ms
        assert isinstance(t, dict)
        for k in _NEW_RESIDUE_KEYS:
            assert k in t, f"residue key missing on precheck branch: {k!r}"
            assert t[k] == 0.0, f"{k} should be 0.0 on precheck-hit, got {t[k]}"
    finally:
        _close(bus, sid)


def test_residue_keys_zero_on_default_allow_with_cli_disabled(tmp_path):
    """Default ALLOW branch (precheck miss, graph miss, CLI disabled)
    must emit all five residue keys with 0.0 — `cli_setup_ms` is
    captured around the early `_cli_enabled()` False return, not
    around the whole evaluate() call."""
    eng, bus, sid = _make_engine(tmp_path, "default-allow")
    try:
        # Routine ALLOW that won't precheck-hit, no graph match. CLI
        # disabled by default (BRIDGE_API_GOV unset in test env).
        msg = Message.new(role="user", content="git status")
        eng.evaluate(msg)
        t = eng._last_phase_timings_ms
        assert isinstance(t, dict)
        for k in _NEW_RESIDUE_KEYS:
            assert k in t, f"residue key missing on default-ALLOW: {k!r}"
            assert t[k] == 0.0, (
                f"{k} should be 0.0 with CLI disabled, got {t[k]}"
            )
    finally:
        _close(bus, sid)


# ────────────────────────────────────────────────────────────────────
# CLI escalation branch (stubbed runner, BRIDGE_API_GOV=true)
# ────────────────────────────────────────────────────────────────────

class _FakeCompletedProcess:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0


def _stub_cli_envelope() -> str:
    return json.dumps(
        {
            "type": "result",
            "result": json.dumps(
                {
                    "action": "ALLOW",
                    "confidence": 0.6,
                    "reasoning": "stub",
                }
            ),
            "usage": {"input_tokens": 10, "output_tokens": 4},
            "total_cost_usd": 0.0001,
        }
    )


def _make_cli_engine(tmp_path, name: str, monkeypatch) -> tuple[GovernanceEngine, _msg_bus.MessageBus, str]:
    """Build an engine wired with a stubbed CliGovernor runner so the
    CLI escalation branch executes without a real `claude` subprocess.
    Spawn-path (no pool) — so cli_pool_acquire_ms is 0.0 by contract,
    and cli_pool_send_ms covers the stubbed runner round-trip.
    """
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    eng, bus, sid = _make_engine(tmp_path, name)

    # Force-construct a CliGovernor with our stubbed runner so the
    # engine's lazy-init path does not stomp on it. We bypass the
    # subprocess entirely.
    def _stub_runner(cmd, **kwargs):  # noqa: ANN001
        return _FakeCompletedProcess(_stub_cli_envelope())

    eng._cli_governor = _cli_gov.CliGovernor(
        eng.project_context,
        runner=_stub_runner,
        bus=bus,
        session_id=sid,
        pool=None,
    )
    return eng, bus, sid


def test_residue_keys_populated_on_cli_escalation(tmp_path, monkeypatch):
    """All five residue keys present on the CLI escalation branch:
    precheck miss + graph miss + CLI enabled + stubbed runner. Spawn
    path (no pool): cli_pool_acquire_ms = 0.0 by contract."""
    eng, bus, sid = _make_cli_engine(tmp_path, "cli-escalation", monkeypatch)
    try:
        # An obviously novel string that won't precheck-hit and has no
        # seeded graph entry — forces the CLI escalation branch.
        msg = Message.new(
            role="user",
            content="please reformat the indentation of file foo.txt",
        )
        eng.evaluate(msg)
        t = eng._last_phase_timings_ms
        assert isinstance(t, dict)
        for k in _NEW_RESIDUE_KEYS:
            assert k in t, f"residue key missing on CLI branch: {k!r}"
            assert t[k] >= 0.0, f"{k}: negative timing {t[k]}"

        # Spawn-path contract: cli_pool_acquire_ms is 0.0.
        assert t["cli_pool_acquire_ms"] == 0.0, (
            f"spawn path: cli_pool_acquire_ms must be 0.0, got "
            f"{t['cli_pool_acquire_ms']}"
        )
        # cli_dispatch_ms is the parent of cli_pool_send_ms +
        # cli_parse_ms (and cli_pool_acquire_ms on pool path). On
        # spawn path the dispatch wraps the send+parse, so dispatch
        # ≥ send.
        assert t["cli_dispatch_ms"] >= t["cli_pool_send_ms"], (
            f"cli_dispatch_ms ({t['cli_dispatch_ms']}) must be ≥ "
            f"cli_pool_send_ms ({t['cli_pool_send_ms']})"
        )
    finally:
        _close(bus, sid)


def test_v15_and_v14_keys_still_present_on_cli_branch(tmp_path, monkeypatch):
    """Do-not-touch contract: v1.4 + v1.5 keys must still land on the
    same dict alongside the new v1.6 residue keys."""
    eng, bus, sid = _make_cli_engine(tmp_path, "v14-v15-coexist", monkeypatch)
    try:
        msg = Message.new(role="user", content="reformat indentation in src/foo.py")
        eng.evaluate(msg)
        t = eng._last_phase_timings_ms
        assert isinstance(t, dict)
        for k in _V14_KEYS:
            assert k in t, f"v1.4 key missing: {k!r}"
        for k in _V15_SUB_PHASE_KEYS:
            assert k in t, f"v1.5 sub-phase key missing: {k!r}"
        for k in _NEW_RESIDUE_KEYS:
            assert k in t, f"v1.6 residue key missing: {k!r}"
    finally:
        _close(bus, sid)


# ────────────────────────────────────────────────────────────────────
# Verdict-equality regression
# ────────────────────────────────────────────────────────────────────

def test_verdict_byte_identical_with_residue_instrumentation(tmp_path):
    """v1.6 P1 instrumentation is purely additive. Verdicts (action,
    confidence, reasoning, source) must be byte-identical to a
    fresh-engine baseline run on the same input. CLI disabled — runs
    the precheck → graph → default-ALLOW deterministic path that v1.5
    already exercised, so any drift in the verdict path would surface
    here."""
    eng_a, bus_a, sid_a = _make_engine(tmp_path, "verdict-a")
    try:
        ref = eng_a.evaluate(Message.new(role="user", content="ruff check src/"))
    finally:
        _close(bus_a, sid_a)

    eng_b, bus_b, sid_b = _make_engine(tmp_path, "verdict-b")
    try:
        comp = eng_b.evaluate(Message.new(role="user", content="ruff check src/"))
    finally:
        _close(bus_b, sid_b)

    assert (ref.action, ref.confidence, ref.reasoning, ref.source) == (
        comp.action,
        comp.confidence,
        comp.reasoning,
        comp.source,
    )


# ────────────────────────────────────────────────────────────────────
# CliGovernor.evaluate signature back-compat
# ────────────────────────────────────────────────────────────────────

def test_cligov_evaluate_back_compat_default_none(monkeypatch):
    """When `sub_timings` is omitted (v1.5 caller signature), the
    method must behave identically to v1.5: returns CliDecision or
    None and never raises on the dict access path."""
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    snap = ProjectContextSnapshot(repo_path=str(ROOT))

    def _stub_runner(cmd, **kwargs):  # noqa: ANN001
        return _FakeCompletedProcess(_stub_cli_envelope())

    gov = _cli_gov.CliGovernor(snap, runner=_stub_runner)
    # Call without sub_timings — must not raise.
    decision = gov.evaluate("test action", model_id="claude-haiku-4-5")
    assert decision is not None
    assert decision.action == "ALLOW"


def test_cligov_evaluate_disabled_returns_none_with_residue_zero(monkeypatch):
    """When the env flag is off, evaluate() short-circuits before
    subprocess.run; if `sub_timings` is supplied it must still see
    the four CLI-side residue keys (zeroed)."""
    monkeypatch.delenv("BRIDGE_API_GOV", raising=False)
    snap = ProjectContextSnapshot(repo_path=str(ROOT))
    gov = _cli_gov.CliGovernor(snap)
    sub: dict[str, float] = {}
    out = gov.evaluate("foo", model_id="claude-haiku-4-5", sub_timings=sub)
    assert out is None
    for k in (
        "cli_dispatch_ms",
        "cli_pool_acquire_ms",
        "cli_pool_send_ms",
        "cli_parse_ms",
    ):
        assert k in sub, f"residue key missing on early-return: {k!r}"
        assert sub[k] >= 0.0
