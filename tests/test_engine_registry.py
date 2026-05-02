"""EngineRegistry: per-session engine instancing (Task B).

Verifies isolation guarantees between sessions, lifecycle ops
(get_or_create / close / active_session_ids), and SM-never-self-monitor
enforcement via SM_OWN_SESSION_ID.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stream_manager.decision_graph import DecisionGraph
from stream_manager.governance import EngineRegistry, GovernanceEngine, Mode
from stream_manager.message_bus import MessageBus
from stream_manager.project_context import load


def _registry(tmp_path: Path, **kwargs) -> EngineRegistry:
    snap = load(tmp_path)
    bus = MessageBus(str(tmp_path / "gov.db"))
    return EngineRegistry(bus=bus, project_context=snap, **kwargs)


def test_get_or_create_returns_engine_keyed_on_session_id(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    e1 = reg.get_or_create("s-A")
    e2 = reg.get_or_create("s-A")
    assert e1 is e2
    assert isinstance(e1, GovernanceEngine)
    assert e1.session_id == "s-A"


def test_two_sessions_get_distinct_engines_and_graphs(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    a = reg.get_or_create("s-A")
    b = reg.get_or_create("s-B")
    assert a is not b
    assert a.session_id == "s-A" and b.session_id == "s-B"
    # Distinct DecisionGraph objects: mutating one's hash table must not
    # be visible in the other.
    assert a.graph is not b.graph
    assert isinstance(a.graph, DecisionGraph)
    assert isinstance(b.graph, DecisionGraph)


def test_mode_promotion_in_session_a_does_not_flip_session_b(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    a = reg.get_or_create("s-A")
    b = reg.get_or_create("s-B")
    assert a.mode == Mode.OBSERVE
    assert b.mode == Mode.OBSERVE
    a.mode = Mode.BLOCK
    assert a.mode == Mode.BLOCK
    assert b.mode == Mode.OBSERVE, "session B's mode must not follow session A"


def test_close_releases_engine_instance(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    a = reg.get_or_create("s-A")
    assert "s-A" in reg
    reg.close("s-A")
    assert "s-A" not in reg
    a2 = reg.get_or_create("s-A")
    assert a2 is not a, "after close, get_or_create must construct a fresh engine"


def test_close_idempotent(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.close("never-existed")  # no raise
    reg.get_or_create("s-A")
    reg.close("s-A")
    reg.close("s-A")  # no raise


def test_active_session_ids(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    assert reg.active_session_ids() == []
    reg.get_or_create("s-A")
    reg.get_or_create("s-B")
    ids = sorted(reg.active_session_ids())
    assert ids == ["s-A", "s-B"]
    reg.close("s-A")
    assert reg.active_session_ids() == ["s-B"]


def test_empty_session_id_rejected(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    with pytest.raises(ValueError):
        reg.get_or_create("")


def test_sm_own_session_id_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SM_OWN_SESSION_ID", "sm-owner-42")
    reg = _registry(tmp_path)
    # Other sessions OK.
    reg.get_or_create("s-A")
    # SM's own session id must be rejected to prevent self-monitor loop.
    with pytest.raises(ValueError, match="self-monitor"):
        reg.get_or_create("sm-owner-42")


def test_sm_own_unset_does_not_block_arbitrary_ids(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SM_OWN_SESSION_ID", raising=False)
    reg = _registry(tmp_path)
    # Empty SM_OWN_SESSION_ID must not coincidentally reject other sessions.
    reg.get_or_create("anything")
    reg.get_or_create("else")


def test_graph_factory_invoked_per_engine(tmp_path: Path) -> None:
    calls = {"n": 0}

    def factory() -> DecisionGraph:
        calls["n"] += 1
        return DecisionGraph()

    reg = _registry(tmp_path, graph_factory=factory)
    reg.get_or_create("s-A")
    reg.get_or_create("s-B")
    reg.get_or_create("s-A")  # cache hit, no new factory call
    assert calls["n"] == 2
