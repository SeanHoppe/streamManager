"""BETA feature #32 "health-digest" -- additive read endpoint
``GET /api/sessions/health-digest``.

The health-digest rail widget collapses the prior 4 per-session fetches
(decisions / agents / lifecycle jobs / hitl pending) into ONE aggregated
read so the SessionRail can render a pre-computed health verdict per
governed session. The endpoint is READ-ONLY and additive: it opens the DB
with the same ``_open()`` (mode=ro) pattern as every other read endpoint,
touches NO FROZEN surface (no governance.py, no message_bus schema change,
no new bus envelope), and aggregates only ``sessions`` + ``decisions`` +
``messages`` (+ defensively ``agents`` / ``hitl_pending`` when present).

These tests pin the contract:

  1. Shape: the payload is {now, excluded_self, sessions:[...]} and each
     governed (non-SM) session row carries the documented keys
     (session_id, project_slug, started_at, ended_at, uptime_seconds,
     decision_count, latest_decision, active_agent_count, active_job_count,
     hitl_pending_count, hitl_mode, latest_escalation).
  2. Counts: decision_count + hitl_pending_count reflect seeded rows and an
     ACTION verdict is reachable (hitl_pending_count > 0).
  3. Empty DB: a fresh DB degrades to {sessions: []} with HTTP 200 -- never
     a 500 / stack leak.
  4. Polarity (G2): a session whose project_slug is in the SM exclusion set
     (streamManager) is EXCLUDED from sessions and counted in excluded_self
     (durable read key).
  5. Polarity (G2): a session whose id equals SM_OWN_SESSION_ID is EXCLUDED
     even when its project_slug is non-SM (session-id backstop).

Mirrors the TestClient + MessageBus idiom from
``tests/test_dashboard_health_sparklines.py``.
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
) -> str:
    """Publish a message + a decision so the endpoint has a row. Returns the
    message id so the caller can also queue a HITL row against it."""
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
    return msg.id


_DIGEST_KEYS = {
    "session_id",
    "project_slug",
    "started_at",
    "ended_at",
    "uptime_seconds",
    "decision_count",
    "latest_decision",
    "active_agent_count",
    "active_job_count",
    "hitl_pending_count",
    "hitl_mode",
    "latest_escalation",
}


def _digest_for(body, session_id):
    for row in body["sessions"]:
        if row["session_id"] == session_id:
            return row
    return None


def test_health_digest_shape_for_governed_session(dashboard_client):
    client, bus, db = dashboard_client
    for conf, act in ((0.91, "ALLOW"), (0.84, "ALLOW"), (0.34, "BLOCK")):
        _seed_decision(bus, NON_SM_SESSION, conf, act)

    resp = client.get("/api/sessions/health-digest")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Top-level shape.
    assert set(["now", "excluded_self", "sessions"]).issubset(body.keys())
    assert isinstance(body["sessions"], list)

    row = _digest_for(body, NON_SM_SESSION)
    assert row is not None, "the governed session must appear in the digest"
    assert _DIGEST_KEYS.issubset(row.keys())
    assert row["project_slug"] == "certPortal"
    assert int(row["decision_count"]) == 3
    # latest_decision is the newest seeded row (BLOCK).
    assert row["latest_decision"] is not None
    assert row["latest_decision"]["action"] == "BLOCK"
    assert 0.0 <= float(row["latest_decision"]["confidence"]) <= 1.0
    # No escalation table in the schema -- the contract field degrades to None
    # for live data (never fabricated).
    assert row["latest_escalation"] is None


def test_health_digest_action_verdict_reachable(dashboard_client):
    """hitl_pending_count > 0 drives the RED ACTION verdict in the UI."""
    client, bus, db = dashboard_client
    mid = _seed_decision(bus, NON_SM_SESSION, 0.40, "BLOCK")
    bus.queue_hitl(
        message_id=mid,
        proposed_action="BLOCK",
        proposed_confidence=0.40,
        trigger_reason="low_confidence",
    )

    resp = client.get("/api/sessions/health-digest")
    assert resp.status_code == 200, resp.text
    row = _digest_for(resp.json(), NON_SM_SESSION)
    assert row is not None
    assert int(row["hitl_pending_count"]) == 1, (
        "an unresolved hitl_pending row must raise hitl_pending_count "
        "(the ACTION verdict source)"
    )


def test_health_digest_empty_db_degrades_not_500(dashboard_client):
    client, bus, db = dashboard_client
    # No decisions seeded -- the sessions exist but carry zero activity; the
    # endpoint must NOT 500 and the governed session still appears with zeros.
    resp = client.get("/api/sessions/health-digest")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    row = _digest_for(body, NON_SM_SESSION)
    assert row is not None
    assert int(row["decision_count"]) == 0
    assert int(row["hitl_pending_count"]) == 0
    assert row["latest_decision"] is None


def test_health_digest_excludes_sm_self_by_project_slug(dashboard_client):
    """G2 polarity: a session on the SM project_slug is excluded + counted."""
    client, bus, db = dashboard_client
    for conf in (0.95, 0.93):
        _seed_decision(bus, SM_SELF_SLUG_SESSION, conf)

    resp = client.get("/api/sessions/health-digest")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert _digest_for(body, SM_SELF_SLUG_SESSION) is None, (
        "SM-self (project_slug) must never appear as a governed digest "
        "(no-self-monitor floor)"
    )
    assert int(body["excluded_self"]) >= 1, (
        "the polarity filter must surface the dropped self row count"
    )


def test_health_digest_excludes_sm_self_by_session_id(dashboard_client):
    """G2 polarity: a session whose id == SM_OWN_SESSION_ID is excluded even
    when its project_slug is non-SM (session-id backstop)."""
    client, bus, db = dashboard_client
    _seed_decision(bus, SM_SELF_ID_SESSION, 0.9)

    resp = client.get("/api/sessions/health-digest")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert _digest_for(body, SM_SELF_ID_SESSION) is None, (
        "SM own-session-id must be excluded from the digest (session-id backstop)"
    )
    assert int(body["excluded_self"]) >= 1
