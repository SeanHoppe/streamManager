"""v1.7 P2 fallback-routing tests for CliGovernor.evaluate.

Real-LLM independence per P2 spec: stubs subprocess.run via _MultiRunner
so the parsed `confidence` field is deterministic per case. Validates four
scenarios + the timing key:

  (a) confidence >= floor          → no fire, no envelope
  (b) confidence < floor           → retry fires, exactly one
                                     governance_fallback_routed envelope
  (c) fallback_model_id=None (FR-OG-7) → never fires, no envelope
  (d) missing `confidence` field   → treat as 1.0, no fire, exactly one
                                     governance_envelope_missing_confidence
                                     envelope (warning)
  (e) cli_dispatch_fallback_ms     → 0.0 when no fire, > 0 when fire
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from stream_manager.cli_governance import (
    FALLBACK_CONFIDENCE_DEFAULT,
    CliGovernor,
)
from stream_manager.project_context import ProjectContextSnapshot


@dataclass
class _CompletedProcess:
    returncode: int
    stdout: str
    stderr: str = ""


class _MultiRunner:
    """subprocess.run stub that serves a list of payloads sequentially.

    Each call pops the next payload from the queue. payloads can be:
      - dict           → wrapped in standard CLI envelope (result = JSON-string)
      - "RAW:<json>"   → used verbatim as the outer envelope
      - "DROP_CONF"    → envelope with action+reasoning but NO confidence key
                         (tests the missing-confidence branch)
    """

    def __init__(self, payloads: list[Any]) -> None:
        self.payloads = list(payloads)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append({"cmd": cmd, "kwargs": kwargs})
        if not self.payloads:
            raise AssertionError("MultiRunner exhausted; unexpected extra call")
        payload = self.payloads.pop(0)
        if isinstance(payload, str) and payload == "DROP_CONF":
            inner = {"action": "ALLOW", "reasoning": "missing-conf-test"}
            envelope = {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": json.dumps(inner),
            }
            stdout = json.dumps(envelope)
        elif isinstance(payload, str) and payload.startswith("RAW:"):
            stdout = payload[len("RAW:"):]
        else:
            envelope = {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": json.dumps(payload),
            }
            stdout = json.dumps(envelope)
        return _CompletedProcess(returncode=0, stdout=stdout)


class _CapturingBus:
    """Minimal bus stub: records every publish() call's Message.type and metadata."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    def publish(self, msg) -> int:  # noqa: ANN001
        self.published.append((msg.type, dict(msg.metadata)))
        return 1

    def types(self) -> list[str]:
        return [t for t, _ in self.published]

    def by_type(self, type_name: str) -> list[dict]:
        return [m for t, m in self.published if t == type_name]


def _governor(runner: _MultiRunner, bus: _CapturingBus | None = None) -> CliGovernor:
    snap = ProjectContextSnapshot(repo_path="/x")
    return CliGovernor(snap, runner=runner, bus=bus, session_id="test-session")


def test_a_confidence_at_floor_no_fire(monkeypatch: pytest.MonkeyPatch) -> None:
    """Primary confidence == floor (0.70) → no retry (strict-below gate)."""
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    runner = _MultiRunner([
        {"action": "BLOCK", "confidence": FALLBACK_CONFIDENCE_DEFAULT, "reasoning": "at floor"},
    ])
    bus = _CapturingBus()
    sub: dict[str, float] = {}
    decision = _governor(runner, bus).evaluate(
        "drop the users table",
        model_id="claude-haiku-4-5-20251001",
        sub_timings=sub,
        fallback_model_id="claude-sonnet-4-6",
    )
    assert decision is not None
    assert decision.action == "BLOCK"
    assert decision.confidence == FALLBACK_CONFIDENCE_DEFAULT
    assert len(runner.calls) == 1  # primary only
    assert sub["cli_dispatch_fallback_ms"] == 0.0
    assert "governance_fallback_routed" not in bus.types()


def test_b_confidence_below_floor_retries_on_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    runner = _MultiRunner([
        {"action": "SUGGEST", "confidence": 0.45, "reasoning": "haiku unsure"},
        {"action": "INTERVENE", "confidence": 0.92, "reasoning": "sonnet certain"},
    ])
    bus = _CapturingBus()
    sub: dict[str, float] = {}
    decision = _governor(runner, bus).evaluate(
        "force push to main",
        model_id="claude-haiku-4-5-20251001",
        sub_timings=sub,
        fallback_model_id="claude-sonnet-4-6",
    )
    assert decision is not None
    # Retry's verdict wins.
    assert decision.action == "INTERVENE"
    assert decision.confidence == 0.92
    assert len(runner.calls) == 2  # primary + retry
    assert sub["cli_dispatch_fallback_ms"] > 0.0
    fb_envs = bus.by_type("governance_fallback_routed")
    assert len(fb_envs) == 1
    fb = fb_envs[0]
    assert fb["primary_model"] == "claude-haiku-4-5-20251001"
    assert fb["fallback_model"] == "claude-sonnet-4-6"
    assert fb["primary_confidence"] == 0.45
    assert fb["fallback_confidence"] == 0.92
    assert fb["fallback_ms"] > 0.0


def test_c_alignment_row_no_fallback_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-OG-7 protected: fallback_model_id is None → never retry, never emit
    governance_fallback_routed even when primary confidence is rock-bottom."""
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    runner = _MultiRunner([
        {"action": "INTERVENE", "confidence": 0.10, "reasoning": "rock bottom"},
    ])
    bus = _CapturingBus()
    sub: dict[str, float] = {}
    decision = _governor(runner, bus).evaluate(
        "alignment-protected action",
        model_id="claude-sonnet-4-6",
        sub_timings=sub,
        fallback_model_id=None,
    )
    assert decision is not None
    assert decision.action == "INTERVENE"
    assert len(runner.calls) == 1  # no retry
    assert sub["cli_dispatch_fallback_ms"] == 0.0
    assert "governance_fallback_routed" not in bus.types()


def test_d_missing_confidence_treated_as_one_with_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    runner = _MultiRunner(["DROP_CONF"])
    bus = _CapturingBus()
    sub: dict[str, float] = {}
    decision = _governor(runner, bus).evaluate(
        "missing-confidence test",
        model_id="claude-haiku-4-5-20251001",
        sub_timings=sub,
        fallback_model_id="claude-sonnet-4-6",
    )
    assert decision is not None
    assert decision.action == "ALLOW"
    assert len(runner.calls) == 1  # no retry — treated as 1.0
    assert sub["cli_dispatch_fallback_ms"] == 0.0
    warns = bus.by_type("governance_envelope_missing_confidence")
    assert len(warns) == 1
    assert warns[0]["model"] == "claude-haiku-4-5-20251001"


def test_e_v16_caller_no_fallback_kwarg_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Backward compat: v1.6 callers passing no fallback_model_id observe
    byte-identical behavior, plus the new cli_dispatch_fallback_ms key
    populated as 0.0 so soak-driver percentile math sees consistent shape."""
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    runner = _MultiRunner([
        {"action": "ALLOW", "confidence": 0.5, "reasoning": "v16 path"},
    ])
    bus = _CapturingBus()
    sub: dict[str, float] = {}
    decision = _governor(runner, bus).evaluate(
        "v16 backward-compat",
        model_id="claude-haiku-4-5-20251001",
        sub_timings=sub,
    )
    assert decision is not None
    assert decision.action == "ALLOW"
    assert len(runner.calls) == 1
    assert sub["cli_dispatch_fallback_ms"] == 0.0
    assert "governance_fallback_routed" not in bus.types()
    assert "governance_envelope_missing_confidence" not in bus.types()


def test_f_env_override_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Floor reads BRIDGE_L4_FALLBACK_CONFIDENCE; raising it makes a 0.85
    primary trigger fallback even though it would not at the default 0.70."""
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    monkeypatch.setenv("BRIDGE_L4_FALLBACK_CONFIDENCE", "0.95")
    runner = _MultiRunner([
        {"action": "SUGGEST", "confidence": 0.85, "reasoning": "below 0.95"},
        {"action": "INTERVENE", "confidence": 0.99, "reasoning": "fallback"},
    ])
    bus = _CapturingBus()
    sub: dict[str, float] = {}
    decision = _governor(runner, bus).evaluate(
        "tight-floor test",
        model_id="claude-haiku-4-5-20251001",
        sub_timings=sub,
        fallback_model_id="claude-sonnet-4-6",
    )
    assert decision is not None
    assert decision.action == "INTERVENE"
    assert len(runner.calls) == 2
    assert len(bus.by_type("governance_fallback_routed")) == 1


def test_g_fallback_retry_failure_falls_back_to_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When fallback retry itself returns a structurally bad envelope,
    keep the primary verdict so we never silently lose a usable decision.
    Envelope is_error=true on the retry path."""
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    err_envelope = json.dumps({
        "type": "result",
        "subtype": "error",
        "is_error": True,
        "result": "",
    })
    runner = _MultiRunner([
        {"action": "SUGGEST", "confidence": 0.40, "reasoning": "primary"},
        f"RAW:{err_envelope}",
    ])
    bus = _CapturingBus()
    sub: dict[str, float] = {}
    decision = _governor(runner, bus).evaluate(
        "retry-failure test",
        model_id="claude-haiku-4-5-20251001",
        sub_timings=sub,
        fallback_model_id="claude-sonnet-4-6",
    )
    assert decision is not None
    # Primary preserved when retry fails.
    assert decision.action == "SUGGEST"
    assert decision.confidence == 0.40
    assert len(runner.calls) == 2
    # Envelope still emitted so dashboards see the attempted retry.
    fb_envs = bus.by_type("governance_fallback_routed")
    assert len(fb_envs) == 1
    assert fb_envs[0]["fallback_confidence"] is None
