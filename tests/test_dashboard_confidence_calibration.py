"""BETA feature #8 "confidence-calibration-loop" -- additive read endpoint
``GET /api/governance/calibration``.

The calibration endpoint buckets the existing governed decisions by predicted
confidence (deciles) and, for each decile, computes realized operator-agreement
= 1 - override_rate against ``hitl_overrides``. It is READ-ONLY and additive: it
opens the DB with the same ``_open()`` (mode=ro) pattern as every other read
endpoint, touches NO FROZEN surface (no governance.py, no message_bus schema
change, no new bus envelope, no new table, no change to engine confidence
semantics), and joins only ``decisions`` + ``messages`` + ``sessions`` +
``hitl_overrides``.

These tests pin the contract:

  1. Shape: the payload carries the documented headline keys + a ``buckets``
     list whose rows carry {idx, lo, hi, predicted, realized, gap, sign, band,
     n, overrides}.
  2. Realized agreement: an overridden decision lowers the bucket's realized
     agreement (1 - override_rate); an un-overridden decision keeps it at 1.0.
  3. Empty DB: a fresh DB degrades to total_decisions:0 with HTTP 200 -- never a
     500 / stack leak.
  4. Polarity (G2): a session whose project_slug is in the SM exclusion set
     (streamManager) contributes NO decision to the curve (durable read key).
  5. Polarity (G2): a session whose id equals SM_OWN_SESSION_ID contributes NO
     decision even when its project_slug is non-SM (session-id backstop).

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


def _seed_decision(bus, session_id, confidence, action="ALLOW"):
    """Publish a message + a decision; return the decision id so the caller can
    attach a hitl_overrides row (an operator override = disagreement)."""
    msg = Message.new(
        session_id=session_id, type="user", direction="in", content="do the thing"
    )
    bus.publish(msg)
    return bus.record_decision(
        message_id=msg.id,
        action=action,
        confidence=confidence,
        reasoning="test seed",
        matched_hash="",
        layer=0,
    )


def _override(bus, decision_id, original="ALLOW", override="BLOCK"):
    bus.annotate_decision(
        decision_id=decision_id,
        original_action=original,
        override_action=override,
        note="operator disagreed",
        mode="async",
    )


_HEAD_KEYS = {
    "now_ms",
    "bucket_count",
    "days",
    "excluded_self",
    "total_decisions",
    "total_overrides",
    "overall_agreement",
    "brier",
    "scope",
    "buckets",
    "transform",
}
_BUCKET_KEYS = {
    "idx",
    "lo",
    "hi",
    "mid",
    "n",
    "overrides",
    "predicted",
    "realized",
    "gap",
    "sign",
    "band",
}


def _bucket_for_conf(body, conf):
    idx = min(9, int(conf * 10))
    for b in body["buckets"]:
        if b["idx"] == idx:
            return b
    return None


def test_calibration_shape(dashboard_client):
    client, bus, _ = dashboard_client
    # 4 governed decisions in the 0.9 decile; 1 of them overridden.
    ids = [_seed_decision(bus, NON_SM_SESSION, 0.95) for _ in range(4)]
    _override(bus, ids[0])

    resp = client.get("/api/governance/calibration")
    assert resp.status_code == 200
    body = resp.json()
    assert _HEAD_KEYS.issubset(body.keys())
    assert body["total_decisions"] == 4
    assert body["total_overrides"] == 1
    assert isinstance(body["buckets"], list) and body["buckets"]
    for b in body["buckets"]:
        assert _BUCKET_KEYS.issubset(b.keys())


def test_calibration_realized_agreement(dashboard_client):
    client, bus, _ = dashboard_client
    # 4 decisions at 0.95 predicted; 1 overridden => realized agreement 0.75.
    ids = [_seed_decision(bus, NON_SM_SESSION, 0.95) for _ in range(4)]
    _override(bus, ids[0])

    body = client.get("/api/governance/calibration").json()
    b = _bucket_for_conf(body, 0.95)
    assert b is not None
    assert b["n"] == 4
    assert b["overrides"] == 1
    assert abs(b["realized"] - 0.75) < 1e-6
    # predicted ~0.95 vs realized 0.75 => OVER-confident (gap < -tolerance).
    assert b["sign"] == "OVER"
    assert b["gap"] < 0
    # overall agreement = 1 - 1/4 = 0.75.
    assert abs(body["overall_agreement"] - 0.75) < 1e-6


def test_calibration_empty_db_degrades(dashboard_client):
    client, _bus, _ = dashboard_client
    resp = client.get("/api/governance/calibration")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_decisions"] == 0
    assert body["buckets"] == []
    assert body["transform"] == []


def test_calibration_excludes_sm_self_by_slug(dashboard_client):
    client, bus, _ = dashboard_client
    _seed_decision(bus, NON_SM_SESSION, 0.95)
    # A decision on an SM-slug session must NOT contribute to the curve.
    _seed_decision(bus, SM_SELF_SLUG_SESSION, 0.10)

    body = client.get("/api/governance/calibration").json()
    assert body["total_decisions"] == 1
    # The 0.10-confidence SM-self decision never appears in any bucket.
    assert _bucket_for_conf(body, 0.10) is None


def test_calibration_excludes_sm_self_by_session_id(dashboard_client):
    client, bus, _ = dashboard_client
    _seed_decision(bus, NON_SM_SESSION, 0.95)
    # A decision on the SM own-session id (non-SM slug) must be excluded too.
    _seed_decision(bus, SM_SELF_ID_SESSION, 0.10)

    body = client.get("/api/governance/calibration").json()
    assert body["total_decisions"] == 1
    assert _bucket_for_conf(body, 0.10) is None
