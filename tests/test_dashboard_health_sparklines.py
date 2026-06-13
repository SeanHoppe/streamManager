"""BETA feature #34 "health-sparklines" -- additive read endpoint
``GET /api/sessions/{session_id}/sparkline-data``.

The health-sparklines strips are derived 100% client-side from the already-open
decision feed; this endpoint serves ONLY the drawer's "last N decisions" detail
for ONE session (timestamp + confidence + action + trigger_reason + a coarse
throughput proxy). It is READ-ONLY and additive: it touches NO FROZEN surface
(no governance.py, no message_bus schema change, no new bus envelope) and joins
only ``decisions`` + ``messages`` + ``sessions`` (+ a defensive left-join to
``hitl_pending`` for trigger_reason when that table exists).

These tests pin the contract:

  1. Shape: a governed (non-SM) session returns the documented JSON
     ({session_id, count, mock:false, rows:[{timestamp, confidence, action,
     trigger_reason, throughput}]}) newest-first.
  2. Empty / unknown: an unknown session (and a fresh empty DB) degrade to an
     empty row set with mock:false and HTTP 200 -- never a 500 / stack leak.
  3. Polarity (G2): a session whose project_slug is in the SM exclusion set
     (streamManager) returns ZERO rows -- the endpoint never exposes SM-self
     decision detail, mirroring the no-self-monitor floor.
  4. Polarity (G2): a session whose id equals SM_OWN_SESSION_ID returns ZERO
     rows even if its project_slug is non-SM (session-id backstop).

Mirrors the TestClient + MessageBus idiom from
``tests/test_dashboard_decision_oracle.py``.
"""

from __future__ import annotations

import importlib
import sys

import pytest
from fastapi.testclient import TestClient

from stream_manager.message_bus import Message, MessageBus


NON_SM_SESSION = "s-governed"
SM_SELF_SLUG_SESSION = "s-self-slug"
SM_SELF_ID_SESSION = "s-self-id"


@pytest.fixture
def dashboard_client(tmp_path, monkeypatch):
    db = tmp_path / "gov.db"
    monkeypatch.setenv("GOV_DB", str(db))
    # Default SM exclusion set is {"streamManager"}; pin it explicitly so the
    # test is robust to a developer's ambient env.
    monkeypatch.setenv("BRIDGE_SM_PROJECT_SLUGS", "streamManager")
    # The session-id backstop reads SM_OWN_SESSION_ID; pin it to the self-id row.
    monkeypatch.setenv("SM_OWN_SESSION_ID", SM_SELF_ID_SESSION)
    if "dashboard.server" in sys.modules:
        del sys.modules["dashboard.server"]
    server = importlib.import_module("dashboard.server")

    bus = MessageBus(str(db))
    bus.open_session(NON_SM_SESSION, project_slug="certPortal")
    bus.open_session(SM_SELF_SLUG_SESSION, project_slug="streamManager")
    # Non-SM project_slug but the session id IS the SM own session id.
    bus.open_session(SM_SELF_ID_SESSION, project_slug="certPortal")
    server._bus = bus
    return TestClient(server.app), bus, str(db)


def _seed_decision(
    bus: MessageBus,
    session_id: str,
    confidence: float,
    action: str = "ALLOW",
) -> None:
    """Publish a message + a decision so the endpoint has a row to serve."""
    msg = Message.new(
        session_id=session_id, type="user", direction="in", content="do the thing"
    )
    bus.publish(msg)
    bus.record_decision(
        message_id=msg.id,
        action=action,
        confidence=confidence,
        reasoning="test seed",
        matched_hash="",
        layer=0,
    )


def test_sparkline_data_shape_for_governed_session(dashboard_client):
    client, bus, db = dashboard_client
    for conf in (0.91, 0.84, 0.62, 0.55):
        _seed_decision(bus, NON_SM_SESSION, conf)

    resp = client.get(f"/api/sessions/{NON_SM_SESSION}/sparkline-data")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["session_id"] == NON_SM_SESSION
    assert body["mock"] is False
    assert int(body["count"]) == 4
    rows = body["rows"]
    assert isinstance(rows, list) and len(rows) == 4

    # Each row carries the documented keys.
    for r in rows:
        assert set(["timestamp", "confidence", "action", "trigger_reason", "throughput"]).issubset(
            r.keys()
        )
        assert 0.0 <= float(r["confidence"]) <= 1.0
        assert isinstance(r["throughput"], (int, float))

    # newest-first ordering (the live decisions / decisionsStore contract).
    ts = [float(r["timestamp"]) for r in rows]
    assert ts == sorted(ts, reverse=True)


def test_sparkline_data_respects_limit(dashboard_client):
    client, bus, db = dashboard_client
    for i in range(8):
        _seed_decision(bus, NON_SM_SESSION, 0.8)

    resp = client.get(f"/api/sessions/{NON_SM_SESSION}/sparkline-data?limit=3")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert int(body["count"]) == 3
    assert len(body["rows"]) == 3


def test_sparkline_data_unknown_session_empty_not_500(dashboard_client):
    client, bus, db = dashboard_client
    resp = client.get("/api/sessions/does-not-exist/sparkline-data")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rows"] == []
    assert int(body["count"]) == 0
    assert body["mock"] is False


def test_sparkline_data_empty_db_degrades_not_500(dashboard_client):
    client, bus, db = dashboard_client
    # No decisions seeded at all -- must NOT 500; empty row set.
    resp = client.get(f"/api/sessions/{NON_SM_SESSION}/sparkline-data")
    assert resp.status_code == 200, resp.text
    assert resp.json()["rows"] == []


def test_sparkline_data_excludes_sm_self_by_project_slug(dashboard_client):
    """G2 polarity: a session on the SM project_slug returns ZERO rows."""
    client, bus, db = dashboard_client
    for conf in (0.95, 0.93):
        _seed_decision(bus, SM_SELF_SLUG_SESSION, conf)

    resp = client.get(f"/api/sessions/{SM_SELF_SLUG_SESSION}/sparkline-data")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rows"] == [], (
        "SM-self (project_slug) sparkline detail must be suppressed "
        "(no-self-monitor floor)"
    )
    assert int(body["count"]) == 0


def test_sparkline_data_excludes_sm_self_by_session_id(dashboard_client):
    """G2 polarity: a session whose id == SM_OWN_SESSION_ID returns ZERO rows
    even when its project_slug is non-SM (session-id backstop)."""
    client, bus, db = dashboard_client
    for conf in (0.9, 0.88):
        _seed_decision(bus, SM_SELF_ID_SESSION, conf)

    resp = client.get(f"/api/sessions/{SM_SELF_ID_SESSION}/sparkline-data")
    assert resp.status_code == 200, resp.text
    assert resp.json()["rows"] == [], (
        "SM own-session-id sparkline detail must be suppressed (session-id backstop)"
    )
