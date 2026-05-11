"""v2.1 P3 (FR-PPP-13) Layer 3 — JSONL hallucination detector.

Drives `JsonlTailWorker._process_line` directly. Asserts:

  - Synthetic parser report on a registered decoy path triggers
    `audit.hallucination_detected` envelope + WAL `triggered_at` stamp.
  - Unregistered path is a no-op.
  - Single-emit per (probe_id, jsonl_path): a second parsed-record
    after the first detection no-ops at the WAL row level (pop-then-emit).
  - SM-originated path is filtered BEFORE the decoy match
    (defense-in-depth: P2 `_is_sm_originated` filter still fires first).
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from stream_manager import message_bus as _msg_bus
from stream_manager.agent_registry import AgentRegistry
from stream_manager.governance import GovernanceEngine
from stream_manager.jsonl_tail import JsonlTailWorker
from stream_manager.project_context import ProjectContextSnapshot

PROFILES_PATH = (
    Path(__file__).resolve().parent.parent
    / "src" / "stream_manager" / "agent_profiles.yaml"
)


@pytest.fixture
def bus(tmp_path: Path, monkeypatch) -> _msg_bus.MessageBus:
    monkeypatch.setenv("SM_DESKTOP_SECRET", "p3-detect-test")
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


def _make_engine(bus, tmp_path) -> GovernanceEngine:
    return GovernanceEngine(
        project_context=ProjectContextSnapshot(repo_path=str(tmp_path)),
        bus=bus, session_id="s1",
    )


def _line(record_type: str = "user", session_id: str = "u-1") -> str:
    return json.dumps({
        "type": record_type, "sessionId": session_id,
        "uuid": "x", "parentUuid": "",
        "message": {"content": "hello"},
    })


def test_decoy_match_fires_envelope_and_stamps_wal(bus, tmp_path):
    """Parsed record on a registered decoy ⇒ envelope + WAL stamp."""
    decoy = str(tmp_path / "decoy.jsonl")
    engine = _make_engine(bus, tmp_path)
    probe_id, _, _ = engine.register_decoy_stream(jsonl_path=decoy)
    w = _make_worker(bus, tmp_path, governance=engine)
    w._current_jsonl_path = decoy
    captured: list[tuple[str, dict]] = []
    bus.subscribe_envelope(lambda t, p: captured.append((t, p)))

    w._process_line(_line())

    types = [t for t, _ in captured]
    assert "audit.hallucination_detected" in types
    env = next(p for t, p in captured if t == "audit.hallucination_detected")
    assert env["probe_id"] == probe_id
    assert env["jsonl_path"] == decoy
    assert len(env["hmac_sig"]) == 64
    # WAL stamped.
    row = bus._conn.execute(
        "SELECT triggered_at FROM provenance_decoys WHERE probe_id=?",
        (probe_id,),
    ).fetchone()
    assert isinstance(row[0], float)


def test_unregistered_path_is_no_op(bus, tmp_path):
    """Parser report on a path NOT registered as a decoy ⇒ silent."""
    engine = _make_engine(bus, tmp_path)
    w = _make_worker(bus, tmp_path, governance=engine)
    w._current_jsonl_path = str(tmp_path / "ordinary.jsonl")
    captured: list[str] = []
    bus.subscribe_envelope(lambda t, p: captured.append(t))
    w._process_line(_line())
    assert "audit.hallucination_detected" not in captured


def test_single_emit_per_probe_id(bus, tmp_path):
    """Two parsed records on the same decoy emit ONE envelope (single-
    write-wins at the WAL row level)."""
    decoy = str(tmp_path / "decoy.jsonl")
    engine = _make_engine(bus, tmp_path)
    probe_id, _, _ = engine.register_decoy_stream(jsonl_path=decoy)
    w = _make_worker(bus, tmp_path, governance=engine)
    w._current_jsonl_path = decoy
    captured: list[str] = []
    bus.subscribe_envelope(lambda t, p: captured.append(t))

    w._process_line(_line())
    w._process_line(_line())

    fires = [t for t in captured if t == "audit.hallucination_detected"]
    assert len(fires) == 1  # second match no-ops (mark_decoy_triggered False)


def test_self_monitor_filter_fires_before_decoy_match(bus, tmp_path):
    """SM-originated records MUST NOT trigger a decoy match (defense in
    depth: `_is_sm_originated` filter runs first)."""
    decoy = str(tmp_path / "decoy.jsonl")
    engine = _make_engine(bus, tmp_path)
    engine.register_decoy_stream(jsonl_path=decoy)
    w = _make_worker(bus, tmp_path, governance=engine)
    w._sm_own_session_id = "sm-self"
    w._current_jsonl_path = decoy
    captured: list[str] = []
    bus.subscribe_envelope(lambda t, p: captured.append(t))

    # sessionId matches SM_OWN_SESSION_ID → filtered before decoy check.
    w._process_line(_line(session_id="sm-self"))

    assert "audit.hallucination_detected" not in captured


def test_no_governance_ref_logs_and_skips(bus, tmp_path):
    """A worker constructed without a governance ref logs + skips the
    envelope fan-out instead of crashing (matches the canary-sweep
    dormant-governance pattern)."""
    decoy = str(tmp_path / "decoy.jsonl")
    engine = _make_engine(bus, tmp_path)
    engine.register_decoy_stream(jsonl_path=decoy)
    w = _make_worker(bus, tmp_path, governance=None)  # dormant
    w._current_jsonl_path = decoy
    captured: list[str] = []
    bus.subscribe_envelope(lambda t, p: captured.append(t))

    w._process_line(_line())

    # No envelope fired; WAL row is also unstamped (claim-first ordering
    # in `emit_audit_hallucination_detected` was never reached).
    assert "audit.hallucination_detected" not in captured
    row = bus._conn.execute(
        "SELECT triggered_at FROM provenance_decoys "
        "WHERE jsonl_path=?", (decoy,),
    ).fetchone()
    assert row[0] is None


def test_empty_current_jsonl_path_no_op(bus, tmp_path):
    """An unset `_current_jsonl_path` (early-startup) MUST NOT raise."""
    engine = _make_engine(bus, tmp_path)
    w = _make_worker(bus, tmp_path, governance=engine)
    w._current_jsonl_path = ""  # cold start
    captured: list[str] = []
    bus.subscribe_envelope(lambda t, p: captured.append(t))
    w._process_line(_line())
    assert "audit.hallucination_detected" not in captured
