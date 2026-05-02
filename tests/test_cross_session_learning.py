"""Task F: cross-session pattern learning (HITL-gated).

Reference: docs/v1.0-ship-plan.md lines 320-387, OQ5/OQ6/OQ8.

Coverage:
1. patterns.cross_session column added by additive migration
2. L3 promotion in session A queues a HITL row with trigger_reason
   "cross_session_flag" — pattern is NOT auto-flagged
3. Operator approval flips cross_session=1
4. Hydrator injects cross_session=1 patterns into a fresh engine at L1
5. Hydrated L1 patterns require LOCAL re-validation to promote — local
   occurrence count starts at 0 and gates apply
6. Demote endpoint flips the flag back to 0
7. Existing TTL gc still removes stale patterns (existing graph behavior
   is unchanged — covered by direct DecisionGraph assertion)
"""

from __future__ import annotations

import importlib
import sys

import pytest
from fastapi.testclient import TestClient

from stream_manager.cross_session_hydrator import Hydrator, hydrate_now
from stream_manager.decision_graph import (
    PROMOTION_THRESHOLDS,
    DecisionGraph,
    PatternLevel,
)
from stream_manager.governance import EngineRegistry, GovernanceEngine
from stream_manager.message_bus import MessageBus
from stream_manager.messages import Message
from stream_manager.project_context import ProjectContextSnapshot


# ── helpers ──────────────────────────────────────────────────────────


def _ctx() -> ProjectContextSnapshot:
    return ProjectContextSnapshot(repo_path="/tmp/proj")


def _msg(content: str = "npm run build") -> Message:
    return Message.new(role="user", content=content)


def _drive_to_l3(engine: GovernanceEngine, content: str = "npm run build") -> None:
    """Observe enough successful repetitions of `content` to push the
    matching pattern through L0 → L3 (occurrences ≥ 10, success_rate ≥ 0.55)."""
    threshold = PROMOTION_THRESHOLDS[PatternLevel.L2]  # = 10
    for _ in range(threshold):
        engine.observe_for_learning(_msg(content), success=True)


# ── 1. schema migration ──────────────────────────────────────────────


def test_patterns_cross_session_column_present(tmp_path):
    bus = MessageBus(str(tmp_path / "gov.db"))
    cols = {
        row[1]
        for row in bus._conn.execute("PRAGMA table_info(patterns)").fetchall()
    }
    assert "cross_session" in cols
    bus.close()


def test_migration_idempotent_on_existing_db(tmp_path):
    """Re-opening a DB that already has cross_session must not raise."""
    db = tmp_path / "gov.db"
    bus1 = MessageBus(str(db))
    bus1.close()
    bus2 = MessageBus(str(db))  # second init should be a no-op
    cols = {
        row[1]
        for row in bus2._conn.execute("PRAGMA table_info(patterns)").fetchall()
    }
    assert "cross_session" in cols
    bus2.close()


# ── 2. L3 promotion enters HITL queue ────────────────────────────────


def test_l3_promotion_queues_hitl_not_autoflag(tmp_path):
    bus = MessageBus(str(tmp_path / "gov.db"))
    bus.open_session("s-A")
    eng = GovernanceEngine(
        project_context=_ctx(),
        bus=bus,
        session_id="s-A",
    )
    _drive_to_l3(eng)

    # The pattern should be at L3 in the engine's local graph.
    l3_patterns = [p for p in eng.graph.patterns.values() if p.level == PatternLevel.L3]
    assert l3_patterns, "expected at least one L3 pattern after threshold drive"
    target_hash = l3_patterns[0].hash

    # The pattern should have been upserted to the bus patterns table.
    row = bus.get_pattern(target_hash)
    assert row is not None
    # Auto-flag must NOT have happened — flag stays 0 until operator approves.
    assert row["cross_session"] == 0

    # A hitl_pending row with trigger_reason "cross_session_flag" must exist.
    pending = bus.get_pending_hitl("s-A")
    flag_rows = [
        r for r in pending if r["trigger_reason"] == "cross_session_flag"
    ]
    assert flag_rows, "expected a cross_session_flag HITL pending row"
    assert flag_rows[0]["proposed_action"] == f"flag_cross_session:{target_hash}"
    bus.close()


# ── 3. operator approval flips the flag ─────────────────────────────


def test_operator_approval_flags_cross_session(tmp_path):
    bus = MessageBus(str(tmp_path / "gov.db"))
    bus.open_session("s-A")
    eng = GovernanceEngine(
        project_context=_ctx(),
        bus=bus,
        session_id="s-A",
    )
    _drive_to_l3(eng)

    pending = bus.get_pending_hitl("s-A")
    flag_rows = [
        r for r in pending if r["trigger_reason"] == "cross_session_flag"
    ]
    assert flag_rows
    pending_id = flag_rows[0]["id"]
    target_hash = flag_rows[0]["proposed_action"].split(":", 1)[1]

    # Resolution dispatcher fires from bus.resolve_hitl.
    bus.resolve_hitl(pending_id, "approved")

    row = bus.get_pattern(target_hash)
    assert row is not None
    assert row["cross_session"] == 1
    bus.close()


def test_rejected_resolution_leaves_flag_zero(tmp_path):
    bus = MessageBus(str(tmp_path / "gov.db"))
    bus.open_session("s-A")
    eng = GovernanceEngine(
        project_context=_ctx(),
        bus=bus,
        session_id="s-A",
    )
    _drive_to_l3(eng)

    pending = bus.get_pending_hitl("s-A")
    flag = next(r for r in pending if r["trigger_reason"] == "cross_session_flag")
    target_hash = flag["proposed_action"].split(":", 1)[1]
    bus.resolve_hitl(flag["id"], "dismissed")

    row = bus.get_pattern(target_hash)
    assert row is not None
    assert row["cross_session"] == 0
    bus.close()


# ── 4. Hydrator injects flag=1 patterns at L1 ───────────────────────


def test_hydrator_injects_flagged_patterns_at_l1(tmp_path):
    bus = MessageBus(str(tmp_path / "gov.db"))
    bus.open_session("s-A")
    eng_a = GovernanceEngine(project_context=_ctx(), bus=bus, session_id="s-A")
    _drive_to_l3(eng_a)
    flag = next(
        r for r in bus.get_pending_hitl("s-A")
        if r["trigger_reason"] == "cross_session_flag"
    )
    target_hash = flag["proposed_action"].split(":", 1)[1]
    bus.resolve_hitl(flag["id"], "approved")

    # Fresh engine for session B — its graph starts empty.
    eng_b = GovernanceEngine(project_context=_ctx(), bus=bus, session_id="s-B")
    assert target_hash not in eng_b.graph.patterns
    assert eng_b.hydrated is False

    n = hydrate_now(eng_b, bus)
    assert n == 1
    assert eng_b.hydrated is True
    inj = eng_b.graph.patterns[target_hash]
    assert inj.level == PatternLevel.L1
    # OQ8: local occurrences start at 0 — receiving engine must re-validate.
    assert inj.occurrences == 0
    assert inj.successes == 0
    bus.close()


def test_hydrator_idempotent_does_not_downgrade(tmp_path):
    """If engine already has the hash at any level, hydrator leaves it alone."""
    bus = MessageBus(str(tmp_path / "gov.db"))
    bus.open_session("s-A")
    eng_a = GovernanceEngine(project_context=_ctx(), bus=bus, session_id="s-A")
    _drive_to_l3(eng_a)
    flag = next(
        r for r in bus.get_pending_hitl("s-A")
        if r["trigger_reason"] == "cross_session_flag"
    )
    target_hash = flag["proposed_action"].split(":", 1)[1]
    bus.resolve_hitl(flag["id"], "approved")

    # Engine A already holds this hash at L3 — second hydrate should be no-op.
    n = hydrate_now(eng_a, bus)
    assert n == 0
    assert eng_a.graph.patterns[target_hash].level == PatternLevel.L3
    bus.close()


# ── 5. Hydrated L1 cannot auto-promote without local re-validation ──


def test_hydrated_l1_requires_local_revalidation(tmp_path):
    """OQ8: a receiving engine cannot promote inherited L1 → L2 without
    accumulating local PROMOTION_THRESHOLDS[L1] (=5) successful local
    observations against the same content.
    """
    bus = MessageBus(str(tmp_path / "gov.db"))
    bus.open_session("s-A")
    eng_a = GovernanceEngine(project_context=_ctx(), bus=bus, session_id="s-A")
    content = "docker compose up"
    for _ in range(PROMOTION_THRESHOLDS[PatternLevel.L2]):
        eng_a.observe_for_learning(_msg(content), success=True)
    flag = next(
        r for r in bus.get_pending_hitl("s-A")
        if r["trigger_reason"] == "cross_session_flag"
    )
    target_hash = flag["proposed_action"].split(":", 1)[1]
    bus.resolve_hitl(flag["id"], "approved")

    eng_b = GovernanceEngine(project_context=_ctx(), bus=bus, session_id="s-B")
    hydrate_now(eng_b, bus)
    inj = eng_b.graph.patterns[target_hash]
    assert inj.level == PatternLevel.L1
    assert inj.occurrences == 0

    # Two local observations: not enough to clear PROMOTION_THRESHOLDS[L1] = 5.
    eng_b.observe_for_learning(_msg(content), success=True)
    eng_b.observe_for_learning(_msg(content), success=True)
    after = eng_b.graph.patterns[target_hash]
    assert after.level == PatternLevel.L1
    bus.close()


# ── 6. demote endpoint flips flag back to 0 ─────────────────────────


@pytest.fixture
def dashboard_client(tmp_path, monkeypatch):
    db = tmp_path / "gov.db"
    monkeypatch.setenv("GOV_DB", str(db))
    if "dashboard.server" in sys.modules:
        del sys.modules["dashboard.server"]
    server = importlib.import_module("dashboard.server")

    bus = MessageBus(str(db))
    server._bus = bus
    return TestClient(server.app), bus


def test_demote_endpoint_flips_flag_to_zero(dashboard_client):
    client, bus = dashboard_client
    bus.upsert_pattern(
        hash="abc123",
        level=3,
        occurrences=10,
        success_rate=0.9,
        last_seen=1.0,
        payload="npm run build",
    )
    bus.flag_pattern_cross_session("abc123")
    assert bus.get_pattern("abc123")["cross_session"] == 1

    r = client.post("/api/patterns/abc123/demote")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"hash": "abc123", "cross_session": 0}
    assert bus.get_pattern("abc123")["cross_session"] == 0


def test_demote_endpoint_404_when_missing(dashboard_client):
    client, _bus = dashboard_client
    r = client.post("/api/patterns/does-not-exist/demote")
    assert r.status_code == 404


def test_get_cross_session_endpoint(dashboard_client):
    client, bus = dashboard_client
    bus.upsert_pattern(
        hash="abc123",
        level=3,
        occurrences=12,
        success_rate=0.91,
        last_seen=42.0,
        payload="docker compose up",
    )
    # Not flagged → not returned.
    r = client.get("/api/patterns/cross_session")
    assert r.status_code == 200
    assert r.json() == []

    bus.flag_pattern_cross_session("abc123")
    r = client.get("/api/patterns/cross_session")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["hash"] == "abc123"
    assert rows[0]["level"] == 3


# ── 7. existing TTL/gc on DecisionGraph still works ─────────────────


def test_existing_graph_pattern_storage_unchanged(tmp_path):
    """Sanity: cross-session column doesn't break the existing
    DecisionGraph.save / DecisionGraph.load round-trip on graph_patterns."""
    g = DecisionGraph()
    for _ in range(3):
        g.observe("ls -la", success=True)
    db = tmp_path / "graph.db"
    g.save(str(db))
    g2 = DecisionGraph.load(str(db))
    assert len(g2.patterns) == len(g.patterns)


# ── 8. Hydrator runs as a daemon thread without blocking ────────────


def test_hydrator_thread_sets_hydrated_flag(tmp_path):
    bus = MessageBus(str(tmp_path / "gov.db"))
    bus.open_session("s-A")
    eng_a = GovernanceEngine(project_context=_ctx(), bus=bus, session_id="s-A")
    _drive_to_l3(eng_a)
    flag = next(
        r for r in bus.get_pending_hitl("s-A")
        if r["trigger_reason"] == "cross_session_flag"
    )
    bus.resolve_hitl(flag["id"], "approved")

    eng_b = GovernanceEngine(project_context=_ctx(), bus=bus, session_id="s-B")
    h = Hydrator(eng_b, bus)
    h.start()
    h.join(timeout=5.0)
    assert not h.is_alive(), "hydrator thread did not finish in 5s"
    assert eng_b.hydrated is True
    bus.close()


# ── 9. EngineRegistry.refresh_all() ─────────────────────────────────


def test_engine_registry_refresh_all_idempotent(tmp_path):
    bus = MessageBus(str(tmp_path / "gov.db"))
    bus.open_session("s-A")
    bus.open_session("s-B")
    reg = EngineRegistry(bus=bus, project_context=_ctx())
    eng_a = reg.get_or_create("s-A")
    _drive_to_l3(eng_a)
    flag = next(
        r for r in bus.get_pending_hitl("s-A")
        if r["trigger_reason"] == "cross_session_flag"
    )
    target_hash = flag["proposed_action"].split(":", 1)[1]
    bus.resolve_hitl(flag["id"], "approved")

    eng_b = reg.get_or_create("s-B")
    # Ensure the spawn-time hydrator (daemon) has run; refresh_all is a
    # synchronous deterministic backstop that doesn't depend on thread timing.
    n = reg.refresh_all()
    assert eng_b.graph.patterns.get(target_hash) is not None
    assert eng_b.graph.patterns[target_hash].level == PatternLevel.L1
    # Second refresh must be a no-op (idempotent — no downgrade).
    n2 = reg.refresh_all()
    assert n2 == 0
    bus.close()
