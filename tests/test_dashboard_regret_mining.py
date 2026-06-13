"""BETA feature #24 "regret-mining-override-loop" -- additive read endpoint
``GET /api/governance/regret``.

The regret ledger aggregates the operator's own OVERRIDES (hitl_overrides) joined
to their decisions + messages + sessions into ranked divergence clusters (per
matched_hash / routing layer). The endpoint is READ-ONLY and additive: it opens
the DB with the same ``_open()`` (mode=ro) pattern as every other read endpoint,
touches NO FROZEN surface (no governance.py, no message_bus schema change, no new
bus envelope, no new column), and writes nothing.

These tests pin the contract:

  1. Shape: the payload is {generated_at, window_days, excluded_self,
     own_session_id, total_overrides, mock, clusters:[...]} and each cluster row
     carries the documented keys; override_rate <= 1 and clusters are
     hottest-first (override_rate x volume).
  2. Empty DB: a fresh DB (no overrides) degrades to {clusters: []} with HTTP 200
     -- never a 500 / stack leak (the component then falls back to mock).
  3. Polarity (G2): an override whose decision's session is on the SM project_slug
     is EXCLUDED from clusters and counted in excluded_self (durable read key).
  4. Polarity (G2): an override whose session id equals SM_OWN_SESSION_ID is
     EXCLUDED even when its project_slug is non-SM (session-id backstop).

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
    bus.open_session(NON_SM_SESSION, project_slug="web-checkout")
    bus.open_session(SM_SELF_SLUG_SESSION, project_slug="streamManager")
    # Non-SM project_slug but the session id IS the SM own session id.
    bus.open_session(SM_SELF_ID_SESSION, project_slug="web-checkout")
    server._bus = bus
    return TestClient(server.app), bus, str(db)


def _seed_override(
    bus: MessageBus,
    session_id: str,
    original: str,
    override: str,
    *,
    matched_hash: str = "",
    content: str = "do the thing",
    note: str | None = None,
):
    """Publish a message + decision, then write a hitl_overrides row against the
    decision id (the same shape /api/hitl/annotate writes). Returns decision_id."""
    msg = Message.new(
        session_id=session_id, type="user", direction="in", content=content
    )
    bus.publish(msg)
    decision_id = bus.record_decision(
        message_id=msg.id,
        action=original,
        confidence=0.5,
        reasoning="test seed",
        matched_hash=matched_hash,
        layer=2 if matched_hash else 1,
    )
    import sqlite3

    conn = sqlite3.connect(str(bus.db_path) if hasattr(bus, "db_path") else _db_path(bus))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS hitl_overrides ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, decision_id TEXT, "
        "original_action TEXT, override_action TEXT, note TEXT, mode TEXT, "
        "timestamp TEXT)"
    )
    conn.execute(
        "INSERT INTO hitl_overrides (decision_id, original_action, "
        "override_action, note, mode, timestamp) VALUES (?,?,?,?,?,?)",
        (decision_id, original, override, note, "async", "2026-06-12T00:00:00Z"),
    )
    conn.commit()
    conn.close()
    return decision_id


def _db_path(bus):
    # Fallback: MessageBus stores its sqlite path; resolve defensively.
    for attr in ("db_path", "_db_path", "path", "_path"):
        v = getattr(bus, attr, None)
        if v:
            return str(v)
    raise RuntimeError("could not resolve bus db path")


_CLUSTER_KEYS = {
    "cluster_key",
    "label_dim",
    "identity",
    "layer",
    "n_decisions",
    "n_overridden",
    "override_rate",
    "dominant_direction",
    "direction_label",
    "from_action",
    "to_action",
    "sample_content",
    "project_slug",
    "overrides",
}


def test_regret_shape_for_governed_overrides(dashboard_client):
    client, bus, db = dashboard_client
    # 3 overrides of one matched_hash shape (all DISMISS of an INTERVENE).
    for _ in range(3):
        _seed_override(
            bus, NON_SM_SESSION, "INTERVENE", "DISMISS",
            matched_hash="9f2c1aZZZZ", content="force-push to the shared branch",
        )

    resp = client.get("/api/governance/regret")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert {
        "generated_at", "window_days", "excluded_self", "own_session_id",
        "total_overrides", "mock", "clusters",
    }.issubset(body.keys())
    assert body["mock"] is False
    assert isinstance(body["clusters"], list)
    assert len(body["clusters"]) >= 1
    assert int(body["total_overrides"]) == 3

    c = body["clusters"][0]
    assert _CLUSTER_KEYS.issubset(c.keys())
    assert c["label_dim"] == "matched_hash"
    assert c["identity"] == "9f2c1a"
    assert int(c["n_overridden"]) == 3
    assert int(c["n_decisions"]) >= 3
    assert 0.0 <= float(c["override_rate"]) <= 1.0
    assert c["dominant_direction"] in ("ESCALATED", "DE-ESCALATED")
    # INTERVENE -> DISMISS relaxes the verdict.
    assert c["dominant_direction"] == "DE-ESCALATED"
    assert isinstance(c["overrides"], list) and len(c["overrides"]) >= 1


def test_regret_empty_db_degrades_not_500(dashboard_client):
    client, bus, db = dashboard_client
    # No overrides seeded -- the endpoint must NOT 500; clusters is empty so the
    # UI falls back to mock.
    resp = client.get("/api/governance/regret")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["clusters"] == []
    assert int(body["total_overrides"]) == 0
    assert body["mock"] is False


def test_regret_excludes_sm_self_by_project_slug(dashboard_client):
    """G2 polarity: an override on an SM project_slug session is excluded +
    counted."""
    client, bus, db = dashboard_client
    _seed_override(
        bus, NON_SM_SESSION, "SUGGEST", "APPROVE",
        matched_hash="abcdefGOVN", content="governed shape",
    )
    _seed_override(
        bus, SM_SELF_SLUG_SESSION, "BLOCK", "APPROVE",
        matched_hash="abcdefSELF", content="self leak",
    )

    resp = client.get("/api/governance/regret")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    keys = {c["cluster_key"] for c in body["clusters"]}
    assert "h:abcdef" in keys or any(c["identity"] == "abcdef" for c in body["clusters"])
    # The SM-self override must NOT contribute (no-self-monitor floor). With both
    # hashes truncating to 'abcdef' the self override is dropped from the count.
    gov = next((c for c in body["clusters"] if c["identity"] == "abcdef"), None)
    assert gov is not None
    assert int(gov["n_overridden"]) == 1, (
        "only the governed override may be mined; the SM-self override is excluded"
    )
    assert int(body["excluded_self"]) >= 1, (
        "the polarity filter must surface the dropped self override count"
    )
    # No mined override may carry an SM project_slug.
    for c in body["clusters"]:
        for o in c["overrides"]:
            assert o["project_slug"].lower() != "streammanager"


def test_regret_excludes_sm_self_by_session_id(dashboard_client):
    """G2 polarity: an override whose session id == SM_OWN_SESSION_ID is excluded
    even when its project_slug is non-SM (session-id backstop)."""
    client, bus, db = dashboard_client
    _seed_override(
        bus, SM_SELF_ID_SESSION, "SUGGEST", "APPROVE",
        matched_hash="deadbeef00", content="self by id",
    )

    resp = client.get("/api/governance/regret")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["clusters"] == [], (
        "an override on the SM own-session-id must be excluded (session-id backstop)"
    )
    assert int(body["excluded_self"]) >= 1