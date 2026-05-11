"""v2.1 P2 (FR-PPP) Layer 2 — JSONL canary observer + sweep tests.

Drives `JsonlTailWorker._process_line` directly (mirrors the P5b learn-
mode test pattern). Asserts:

  - register_canary + observer scan: nonce in user-text turn whose
    JSONL path matches the registered target ⇒ `audit.canary_observed`
    envelope fired AND `provenance_assertions.canary_confirmed_at`
    stamped.
  - Timeout sweep: entries past `timeout_s` are popped + routed to
    `governance.emit_audit_probe_failure`.
  - Self-monitor guard: SM-originated user-text turns are NOT scanned
    (existing `_is_sm_originated` filter inherited).
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from stream_manager import message_bus as _msg_bus
from stream_manager.agent_registry import AgentRegistry
from stream_manager.jsonl_tail import JsonlTailWorker

PROFILES_PATH = (
    Path(__file__).resolve().parent.parent
    / "src" / "stream_manager" / "agent_profiles.yaml"
)


@pytest.fixture
def bus(tmp_path: Path, monkeypatch) -> _msg_bus.MessageBus:
    # Refresh desktop_commands so sign uses a known test secret.
    monkeypatch.setenv("SM_DESKTOP_SECRET", "p2-observer-test")
    if "stream_manager.desktop_commands" in sys.modules:
        del sys.modules["stream_manager.desktop_commands"]
    importlib.import_module("stream_manager.desktop_commands")
    return _msg_bus.MessageBus(str(tmp_path / "bus.db"))


def _make_worker(bus, tmp_path, governance=None) -> JsonlTailWorker:
    w = JsonlTailWorker(
        projects_dir=tmp_path,
        registry=AgentRegistry(profiles_path=PROFILES_PATH),
        bus=bus,
        governance=governance,
    )
    w._session_id = "sm-session"
    w._project_slug = "fixture"
    return w


def _write_assertion(bus: _msg_bus.MessageBus, probe_id: str,
                     jsonl_path: str) -> None:
    bus.write_provenance_assertion(
        probe_id=probe_id, session_id="user-session",
        jsonl_path=jsonl_path, brain_id=None, prompt_hash=None,
        signed_at=1000.0, expires_at=9999999999.0, hmac_sig="x",
    )


def _user_text_line(text: str, session_id: str = "u-1") -> str:
    return json.dumps({
        "type": "user", "sessionId": session_id, "uuid": "u-uuid",
        "parentUuid": "", "message": {"content": text},
    })


def test_observer_match_emits_observed_and_marks_confirmed(
    bus, tmp_path, monkeypatch,
):
    target = str(tmp_path / "real.jsonl")
    _write_assertion(bus, "p1", target)
    w = _make_worker(bus, tmp_path)
    w._current_jsonl_path = target
    captured: list[tuple[str, dict]] = []
    bus.subscribe_envelope(lambda t, p: captured.append((t, p)))
    w.register_canary(
        probe_id="p1", nonce="deadbeef",
        target_jsonl_path=target, timeout_s=10.0,
    )
    w._process_line(_user_text_line("please type deadbeef now"))
    # Observed envelope fired.
    types = [t for t, _ in captured]
    assert "audit.canary_observed" in types
    obs = next(p for t, p in captured if t == "audit.canary_observed")
    assert obs["probe_id"] == "p1"
    assert obs["nonce"] == "deadbeef"
    assert obs["jsonl_path"] == target
    assert obs["hmac_sig"]
    # Assertion row stamped.
    row = bus._conn.execute(
        "SELECT canary_nonce, canary_confirmed_at "
        "FROM provenance_assertions WHERE probe_id='p1'"
    ).fetchone()
    assert row[0] == "deadbeef"
    assert isinstance(row[1], float)
    # Registry cleared post-match.
    assert "p1" not in w._canary_registry


def test_observer_no_match_when_path_mismatches(bus, tmp_path):
    target = str(tmp_path / "real.jsonl")
    _write_assertion(bus, "p1", target)
    w = _make_worker(bus, tmp_path)
    # Tailing a DIFFERENT jsonl than the registered target.
    w._current_jsonl_path = str(tmp_path / "other.jsonl")
    captured: list[str] = []
    bus.subscribe_envelope(lambda t, p: captured.append(t))
    w.register_canary("p1", "deadbeef", target_jsonl_path=target)
    w._process_line(_user_text_line("deadbeef"))
    assert "audit.canary_observed" not in captured
    assert "p1" in w._canary_registry  # entry still pending


def test_sweep_timeout_routes_to_governance(bus, tmp_path):
    """Sweep pops expired entries and routes to governance.emit_audit_probe_failure."""

    class _StubGov:
        def __init__(self):
            self.calls: list[dict] = []
        def emit_audit_probe_failure(self, probe_id, reason,
                                     candidate_streams=None,
                                     ttl_seconds=1800):
            self.calls.append({
                "probe_id": probe_id, "reason": reason,
                "candidates": list(candidate_streams or []),
            })
            return ({}, 1, None)

    gov = _StubGov()
    w = _make_worker(bus, tmp_path, governance=gov)
    w.register_canary(
        probe_id="p1", nonce="n", target_jsonl_path="/x.jsonl",
        timeout_s=10.0,
    )
    # Fast-forward: pretend the canary was registered 20s ago.
    w._canary_registry["p1"].started_at -= 20.0
    w._sweep_canaries_once()
    assert gov.calls and gov.calls[0]["probe_id"] == "p1"
    assert gov.calls[0]["reason"] == "canary_timeout"
    # Entry popped — R7 mitigation: no second sweep for same probe.
    assert "p1" not in w._canary_registry
    w._sweep_canaries_once()
    assert len(gov.calls) == 1


def test_self_monitor_guard_skips_sm_originated(bus, tmp_path):
    """SM-originated user-text turns are filtered before canary scan."""
    target = str(tmp_path / "real.jsonl")
    _write_assertion(bus, "p1", target)
    w = _make_worker(bus, tmp_path)
    w._sm_own_session_id = "sm-self"
    w._current_jsonl_path = target
    captured: list[str] = []
    bus.subscribe_envelope(lambda t, p: captured.append(t))
    w.register_canary("p1", "deadbeef", target_jsonl_path=target)
    # SessionId matches SM_OWN_SESSION_ID ⇒ filtered upstream of canary.
    w._process_line(_user_text_line("deadbeef", session_id="sm-self"))
    assert "audit.canary_observed" not in captured
    assert "p1" in w._canary_registry
