"""Phase 7 / governance_call lifecycle event tests.

Covers the four required behaviors from
``docs/prompts/task-1-governance-call-event.md``:

  1. ``running`` event emitted before subprocess.
  2. ``exited`` event emits with ``latency_ms > 0`` and token fields when
     envelope contains ``usage``.
  3. ``failed`` event when subprocess returns non-zero.
  4. ``bus=None`` path silent (back-compat).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from stream_manager.cli_governance import CliGovernor
from stream_manager.message_bus import MessageBus
from stream_manager.project_context import ProjectContextSnapshot


@dataclass
class _CompletedProcess:
    returncode: int
    stdout: str
    stderr: str = ""


def _make_runner(
    inner_payload: dict[str, Any] | None = None,
    *,
    returncode: int = 0,
    usage: dict[str, int] | None = None,
    cost_usd: float | None = None,
):
    """Build a subprocess.run stand-in that emits a Claude CLI envelope."""

    def _runner(cmd, **kwargs):
        envelope: dict[str, Any] = {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": (
                json.dumps(inner_payload) if inner_payload is not None else ""
            ),
        }
        if usage is not None:
            envelope["usage"] = usage
        if cost_usd is not None:
            envelope["total_cost_usd"] = cost_usd
        return _CompletedProcess(returncode=returncode, stdout=json.dumps(envelope))

    return _runner


def _bus(tmp_path: Path) -> MessageBus:
    return MessageBus(str(tmp_path / "bus.db"))


def _governance_call_events(bus: MessageBus, session_id: str) -> list[dict[str, Any]]:
    """Pull all governance_call rows for a session as dicts (newest last)."""
    cur = bus._conn.execute(
        "SELECT metadata, content, type, direction, sequence "
        "FROM messages WHERE session_id=? AND type='governance_call' "
        "ORDER BY sequence ASC",
        (session_id,),
    )
    rows: list[dict[str, Any]] = []
    for meta, content, mtype, direction, seq in cur.fetchall():
        rows.append(
            {
                "metadata": json.loads(meta),
                "content": content,
                "type": mtype,
                "direction": direction,
                "sequence": seq,
            }
        )
    return rows


# ── Test 1: running event emitted before subprocess ─────────────────


def test_running_event_emitted_before_subprocess(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    bus = _bus(tmp_path)
    session_id = "s-running"
    bus.open_session(session_id)

    observed_status_at_call: list[str | None] = []

    def _runner(cmd, **kwargs):
        # By the time subprocess.run is reached, exactly one running event
        # must already exist on the bus.
        events = _governance_call_events(bus, session_id)
        observed_status_at_call.append(
            events[-1]["metadata"]["status"] if events else None
        )
        return _CompletedProcess(
            returncode=0,
            stdout=json.dumps(
                {
                    "type": "result",
                    "is_error": False,
                    "result": json.dumps(
                        {"action": "ALLOW", "confidence": 0.9, "reasoning": "ok"}
                    ),
                }
            ),
        )

    snap = ProjectContextSnapshot(repo_path="/x")
    gov = CliGovernor(snap, runner=_runner, bus=bus, session_id=session_id)
    gov.evaluate("any content")

    assert observed_status_at_call == ["running"]
    events = _governance_call_events(bus, session_id)
    # 1 running + 1 exited
    assert [e["metadata"]["status"] for e in events] == ["running", "exited"]
    # running event has None token / cost / latency fields
    running = events[0]["metadata"]
    assert running["latency_ms"] is None
    assert running["input_tokens"] is None
    assert running["output_tokens"] is None
    assert running["cost_usd"] is None


# ── Test 2: exited event has latency_ms > 0 and token fields ────────


def test_exited_event_has_latency_and_tokens(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    bus = _bus(tmp_path)
    session_id = "s-exited"
    bus.open_session(session_id)

    runner = _make_runner(
        {"action": "ALLOW", "confidence": 0.9, "reasoning": "ok"},
        usage={"input_tokens": 128, "output_tokens": 64},
        cost_usd=0.0021,
    )
    snap = ProjectContextSnapshot(repo_path="/x")
    gov = CliGovernor(snap, runner=runner, bus=bus, session_id=session_id)
    gov.evaluate("merge to main")  # trigger=alignment

    events = _governance_call_events(bus, session_id)
    statuses = [e["metadata"]["status"] for e in events]
    assert statuses == ["running", "exited"]

    exited = events[1]["metadata"]
    assert exited["latency_ms"] is not None
    assert exited["latency_ms"] >= 0
    assert exited["input_tokens"] == 128
    assert exited["output_tokens"] == 64
    assert exited["cost_usd"] == pytest.approx(0.0021)
    # Default model is the legacy Haiku (MODEL constant) — Haiku → L3.
    assert exited["tier"] == "L3"
    assert exited["trigger"] == "alignment"


def test_exited_event_tokens_default_none_when_usage_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    bus = _bus(tmp_path)
    session_id = "s-no-usage"
    bus.open_session(session_id)

    runner = _make_runner(
        {"action": "ALLOW", "confidence": 0.9, "reasoning": "ok"},
        usage=None,
        cost_usd=None,
    )
    snap = ProjectContextSnapshot(repo_path="/x")
    gov = CliGovernor(snap, runner=runner, bus=bus, session_id=session_id)
    gov.evaluate("read README.md")

    events = _governance_call_events(bus, session_id)
    exited = events[-1]["metadata"]
    assert exited["status"] == "exited"
    assert exited["input_tokens"] is None
    assert exited["output_tokens"] is None
    assert exited["cost_usd"] is None


# ── Test 3: failed event on non-zero exit ───────────────────────────


def test_failed_event_on_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    bus = _bus(tmp_path)
    session_id = "s-failed"
    bus.open_session(session_id)

    runner = _make_runner(
        {"action": "ALLOW", "confidence": 0.9, "reasoning": "ok"},
        returncode=2,
    )
    snap = ProjectContextSnapshot(repo_path="/x")
    gov = CliGovernor(snap, runner=runner, bus=bus, session_id=session_id)
    decision = gov.evaluate("anything")

    assert decision is None  # non-zero exit degrades to None
    events = _governance_call_events(bus, session_id)
    statuses = [e["metadata"]["status"] for e in events]
    assert statuses == ["running", "failed"]
    failed = events[-1]["metadata"]
    assert failed["latency_ms"] is not None


# ── Test 4: bus=None path silent ────────────────────────────────────


def test_bus_none_path_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    runner = _make_runner(
        {"action": "ALLOW", "confidence": 0.9, "reasoning": "ok"}
    )
    snap = ProjectContextSnapshot(repo_path="/x")
    # Constructed with no bus / session_id — no error, no events.
    gov = CliGovernor(snap, runner=runner)
    decision = gov.evaluate("anything")
    assert decision is not None
    assert decision.action == "ALLOW"


def test_bus_publish_failure_does_not_crash_subprocess(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Mirror cli_client's NFR-R6: bus failures must not break the call."""
    monkeypatch.setenv("BRIDGE_API_GOV", "true")

    class _BrokenBus:
        def publish(self, msg):  # noqa: D401
            raise RuntimeError("bus is down")

    runner = _make_runner(
        {"action": "ALLOW", "confidence": 0.9, "reasoning": "ok"}
    )
    snap = ProjectContextSnapshot(repo_path="/x")
    gov = CliGovernor(
        snap, runner=runner, bus=_BrokenBus(), session_id="s-broken"
    )
    decision = gov.evaluate("anything")
    assert decision is not None
    assert decision.action == "ALLOW"


# ── Bonus: tier inference from model id ─────────────────────────────


def test_tier_l4_when_sonnet_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    bus = _bus(tmp_path)
    session_id = "s-l4"
    bus.open_session(session_id)

    runner = _make_runner(
        {"action": "ALLOW", "confidence": 0.9, "reasoning": "ok"},
        usage={"input_tokens": 10, "output_tokens": 5},
    )
    snap = ProjectContextSnapshot(repo_path="/x")
    gov = CliGovernor(snap, runner=runner, bus=bus, session_id=session_id)
    gov.evaluate("anything", model_id="claude-sonnet-4-6")

    events = _governance_call_events(bus, session_id)
    tiers = {e["metadata"]["tier"] for e in events}
    assert tiers == {"L4"}
