"""v1.3 C10 — dashboard surfaces ``hitl_pending.bias_hint`` to operator.

Audit gap (`docs/v1.3-drift-audit.md` §2.1): ``HitlQueue.route``
populates ``hitl_pending.bias_hint`` with a JSON-encoded Learn Mode
advisory, but the dashboard's ``/api/hitl/pending`` endpoint dropped
the column on the floor — the operator never saw the advisory.

These tests assert the API:

  1. Projects ``bias_hint`` and decodes it server-side into an object
     when a row was queued with one (matching ``_encode_bias_hint``'s
     output shape: category + confidence + ladder_step_suggestion +
     pattern_id + last_reinforced_ts).
  2. Returns ``bias_hint: None`` when the column is empty (older rows
     or no canonical match at queueing time).
  3. Returns ``bias_hint: None`` when the column holds malformed JSON
     (defensive — never break the HITL pane on bad data).

The render path is verified by code inspection only (pure JS in
``dashboard/static/index.html`` ``renderHitlPanel``); the API contract
is what this test pins.
"""

from __future__ import annotations

import importlib
import json
import sys

import pytest
from fastapi.testclient import TestClient

from stream_manager.message_bus import Message, MessageBus


SESSION_ID = "s-c10"


@pytest.fixture
def dashboard_client(tmp_path, monkeypatch):
    db = tmp_path / "gov.db"
    monkeypatch.setenv("GOV_DB", str(db))
    if "dashboard.server" in sys.modules:
        del sys.modules["dashboard.server"]
    server = importlib.import_module("dashboard.server")

    bus = MessageBus(str(db))
    bus.open_session(SESSION_ID)
    server._bus = bus
    return TestClient(server.app), bus


def _seed_message(bus: MessageBus, *, content: str = "ls -la") -> str:
    msg = Message.new(
        session_id=SESSION_ID,
        type="user",
        direction="in",
        content=content,
    )
    bus.publish(msg)
    return msg.id


def test_api_hitl_pending_decodes_bias_hint_when_present(dashboard_client):
    client, bus = dashboard_client
    message_id = _seed_message(bus, content="rm -rf node_modules")

    payload = {
        "category": "destructive_shell",
        "confidence": 0.82,
        "ladder_step_suggestion": 3,
        "pattern_id": 17,
        "last_reinforced_ts": 1714780000.0,
    }
    bus.queue_hitl(
        message_id=message_id,
        proposed_action="GUIDE",
        proposed_confidence=0.55,
        trigger_reason="low_confidence",
        bias_hint=json.dumps(payload),
    )

    r = client.get("/api/hitl/pending")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert isinstance(rows, list) and len(rows) == 1
    row = rows[0]

    assert row["proposed_action"] == "GUIDE"
    assert row["trigger_reason"] == "low_confidence"
    bh = row["bias_hint"]
    assert isinstance(bh, dict)
    assert bh["category"] == "destructive_shell"
    assert bh["confidence"] == pytest.approx(0.82)
    assert bh["ladder_step_suggestion"] == 3
    assert bh["pattern_id"] == 17
    assert bh["last_reinforced_ts"] == pytest.approx(1714780000.0)


def test_api_hitl_pending_returns_none_when_bias_hint_absent(dashboard_client):
    client, bus = dashboard_client
    message_id = _seed_message(bus, content="git status")

    bus.queue_hitl(
        message_id=message_id,
        proposed_action="ALLOW",
        proposed_confidence=0.95,
        trigger_reason="new_pattern",
        # bias_hint omitted → defaults to ''
    )

    r = client.get("/api/hitl/pending")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["bias_hint"] is None


def test_api_hitl_pending_returns_none_on_malformed_bias_hint(dashboard_client):
    client, bus = dashboard_client
    message_id = _seed_message(bus, content="echo hi")

    # Insert a row with a deliberately malformed bias_hint payload.
    bus.queue_hitl(
        message_id=message_id,
        proposed_action="ALLOW",
        proposed_confidence=0.9,
        trigger_reason="new_pattern",
        bias_hint="{not valid json",
    )

    r = client.get("/api/hitl/pending")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    # Defensive: malformed payload must not break the pane.
    assert rows[0]["bias_hint"] is None


def test_api_hitl_pending_session_filter_preserves_bias_hint(dashboard_client):
    """The session_id-filtered branch uses a separate SELECT — make sure
    bias_hint is projected there too."""
    client, bus = dashboard_client
    message_id = _seed_message(bus, content="curl example.com")

    payload = {
        "category": "network_call",
        "confidence": 0.7,
        "ladder_step_suggestion": 2,
        "pattern_id": 5,
        "last_reinforced_ts": 1714780123.0,
    }
    bus.queue_hitl(
        message_id=message_id,
        proposed_action="SUGGEST",
        proposed_confidence=0.6,
        trigger_reason="low_confidence",
        bias_hint=json.dumps(payload),
    )

    r = client.get(f"/api/hitl/pending?session_id={SESSION_ID}")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    bh = rows[0]["bias_hint"]
    assert isinstance(bh, dict)
    assert bh["category"] == "network_call"
    assert bh["ladder_step_suggestion"] == 2
