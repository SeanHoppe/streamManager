"""BETA feature #21 "policy-preview-chip" -- additive read endpoint
``GET /api/governance/predict``.

The policy-preview chip reads "what governance would do" from the historical
decision corpus for the selected session's command-shape. The endpoint is
READ-ONLY and additive: it opens the DB with the same ``_open()`` (mode=ro)
pattern as every other read endpoint, derives a per-action distribution from
the EXISTING ``decisions`` + ``messages`` (+ ``sessions``) rows, touches NO
FROZEN surface (no governance.py, no message_bus schema change, no new bus
envelope), and NEVER calls the live engine (M18: off the verdict hot path).

These tests pin the contract:

  1. Shape: the payload carries {shape, session_id, n, match_kind, action_hist,
     dominant_action, dominant_share, mean_conf, dominant_layer, excluded_self,
     mock} and the action_hist counts reflect the seeded rows.
  2. Exact-shape match: rows sharing a matched_hash aggregate into the
     distribution with match_kind == 'exact'.
  3. Empty DB / cold shape: a fresh DB (or a session with no history) degrades
     to {n:0, match_kind:'none'} with HTTP 200 -- never a 500 / stack leak.
  4. Polarity (G2): a session whose project_slug is in the SM exclusion set
     (streamManager) is EXCLUDED from the corpus and counted in excluded_self
     (durable read key).
  5. Polarity (G2): a session whose id equals SM_OWN_SESSION_ID is EXCLUDED even
     when its project_slug is non-SM (session-id backstop).

Mirrors the TestClient + MessageBus idiom from
``tests/test_dashboard_health_digest.py``.
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
SHAPE = "shape-abc123"


@pytest.fixture
def dashboard_client(tmp_path, monkeypatch):
    db = tmp_path / "gov.db"
    monkeypatch.setenv("GOV_DB", str(db))
    monkeypatch.setenv("BRIDGE_SM_PROJECT_SLUGS", "streamManager")
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
    matched_hash: str = SHAPE,
) -> str:
    msg = Message.new(
        session_id=session_id, type="user", direction="in", content="do the thing"
    )
    bus.publish(msg)
    bus.record_decision(
        message_id=msg.id,
        action=action,
        confidence=confidence,
        reasoning="test seed",
        matched_hash=matched_hash,
        layer=1,
    )
    return msg.id


_KEYS = {
    "shape",
    "session_id",
    "n",
    "match_kind",
    "action_hist",
    "dominant_action",
    "dominant_share",
    "mean_conf",
    "dominant_layer",
    "excluded_self",
    "mock",
}


def test_predict_shape_and_distribution(dashboard_client):
    client, bus, db = dashboard_client
    # 14 ALLOW + 1 SUGGEST on the same matched_hash -> exact-shape distribution.
    for _ in range(14):
        _seed_decision(bus, NON_SM_SESSION, 0.97, "ALLOW")
    _seed_decision(bus, NON_SM_SESSION, 0.80, "SUGGEST")

    resp = client.get(
        "/api/governance/predict", params={"session_id": NON_SM_SESSION, "shape": SHAPE}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert _KEYS.issubset(body.keys())
    assert body["match_kind"] == "exact"
    assert int(body["n"]) == 15
    assert int(body["action_hist"]["ALLOW"]) == 14
    assert int(body["action_hist"]["SUGGEST"]) == 1
    assert body["dominant_action"] == "ALLOW"
    assert abs(float(body["dominant_share"]) - (14 / 15)) < 1e-3
    assert 0.0 <= float(body["mean_conf"]) <= 1.0
    assert body["dominant_layer"] == "L1"
    assert body["mock"] is False


def test_predict_cold_shape_degrades_not_500(dashboard_client):
    """A session with no history degrades to n:0 / match none, HTTP 200."""
    client, bus, db = dashboard_client
    resp = client.get(
        "/api/governance/predict", params={"session_id": NON_SM_SESSION}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert int(body["n"]) == 0
    assert body["match_kind"] == "none"
    assert body["dominant_action"] is None
    assert body["action_hist"] in ({}, {"ALLOW": 0, "SUGGEST": 0, "GUIDE": 0, "INTERVENE": 0, "BLOCK": 0})


def test_predict_excludes_sm_self_by_project_slug(dashboard_client):
    """G2 polarity: SM project_slug rows never enter the predictive corpus."""
    client, bus, db = dashboard_client
    for _ in range(5):
        _seed_decision(bus, SM_SELF_SLUG_SESSION, 0.99, "ALLOW")

    # Query by the SM-self shape directly -- the corpus must still be empty.
    resp = client.get("/api/governance/predict", params={"shape": SHAPE})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert int(body["n"]) == 0, (
        "SM-self (project_slug) decisions must never enter the predictive corpus"
    )
    assert int(body["excluded_self"]) >= 5, (
        "the polarity filter must surface the dropped self-row count"
    )


def test_predict_excludes_sm_self_by_session_id(dashboard_client):
    """G2 polarity: a session whose id == SM_OWN_SESSION_ID is excluded even when
    its project_slug is non-SM (session-id backstop)."""
    client, bus, db = dashboard_client
    for _ in range(3):
        _seed_decision(bus, SM_SELF_ID_SESSION, 0.95, "ALLOW")

    resp = client.get(
        "/api/governance/predict",
        params={"session_id": SM_SELF_ID_SESSION, "shape": SHAPE},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert int(body["n"]) == 0, (
        "SM own-session-id decisions must be excluded from the corpus (backstop)"
    )
    assert int(body["excluded_self"]) >= 3
