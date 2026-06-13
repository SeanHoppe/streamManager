"""BETA feature #12 "decision-oracle" -- additive read endpoint
``GET /api/patterns/{hash}/pedigree``.

The Decision Oracle whisper-pane reconstructs a pattern's pedigree (the L0-L4
promotion ladder + a success/age stat strip + an ancestral-replay observation
timeline) for a single ``decision.matched_hash``. The endpoint is READ-ONLY and
additive: it touches NO FROZEN surface (no governance.py, no message_bus schema
change, no new bus envelope) and joins only ``graph_patterns`` + ``decisions`` +
``messages`` + ``sessions``.

These tests pin the contract:

  1. Shape: a known non-SM pattern returns the documented JSON
     (pattern_hash, level, occurrences, successes, success_rate, observations[],
     overfit{}) with the observation timeline reconstructed from the messages
     whose decisions matched the hash.
  2. Empty / unknown: an absent hash (and a fresh empty DB) degrade to HTTP 404,
     never a 500 / stack leak.
  3. Polarity (G2): a pattern whose decisions live ONLY on an SM-self session
     (project_slug in the SM exclusion set) returns 404 -- the oracle never
     exposes SM-self pedigree, mirroring the no-self-monitor floor.

Mirrors the TestClient + MessageBus idiom from
``tests/test_dashboard_hitl_bias_hint.py``.
"""

from __future__ import annotations

import importlib
import json
import sqlite3
import sys
import time

import pytest
from fastapi.testclient import TestClient

from stream_manager.message_bus import Message, MessageBus


NON_SM_SESSION = "s-governed"
SM_SELF_SESSION = "s-self"
NON_SM_HASH = "9f2c1a77b4e03d56"
SM_SELF_HASH = "deadbeefcafef00d"


@pytest.fixture
def dashboard_client(tmp_path, monkeypatch):
    db = tmp_path / "gov.db"
    monkeypatch.setenv("GOV_DB", str(db))
    # Default SM exclusion set is {"streamManager"}; pin it explicitly so the
    # test is robust to a developer's ambient env.
    monkeypatch.setenv("BRIDGE_SM_PROJECT_SLUGS", "streamManager")
    if "dashboard.server" in sys.modules:
        del sys.modules["dashboard.server"]
    server = importlib.import_module("dashboard.server")

    bus = MessageBus(str(db))
    # A governed (non-SM) session and an SM-self session (polarity target).
    bus.open_session(NON_SM_SESSION, project_slug="certPortal")
    bus.open_session(SM_SELF_SESSION, project_slug="streamManager")
    server._bus = bus
    return TestClient(server.app), bus, str(db)


def _seed_observation(
    bus: MessageBus, session_id: str, hash_: str, content: str, action: str = "GUIDE"
) -> None:
    """Publish a message + a decision that matched ``hash_`` (one observation)."""
    msg = Message.new(session_id=session_id, type="user", direction="in", content=content)
    bus.publish(msg)
    bus.record_decision(
        message_id=msg.id,
        action=action,
        confidence=0.62,
        reasoning="graph match",
        matched_hash=hash_,
        layer=2,
    )


def _seed_pattern(
    db_path: str, hash_: str, level: int, occurrences: int, successes: int
) -> None:
    """Insert a graph_patterns row (the DecisionGraph.save() schema)."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS graph_patterns (
                hash TEXT PRIMARY KEY,
                level INTEGER NOT NULL,
                vector TEXT NOT NULL,
                canonical_text TEXT NOT NULL,
                occurrences INTEGER NOT NULL,
                successes INTEGER NOT NULL,
                last_seen REAL NOT NULL,
                children TEXT NOT NULL
            )"""
        )
        conn.execute(
            "INSERT OR REPLACE INTO graph_patterns "
            "(hash, level, vector, canonical_text, occurrences, successes, last_seen, children) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                hash_,
                int(level),
                json.dumps([0.0] * 64),
                "run the integration suite before tagging",
                int(occurrences),
                int(successes),
                time.time(),
                json.dumps([]),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_pedigree_returns_shape_for_governed_pattern(dashboard_client):
    client, bus, db = dashboard_client
    _seed_pattern(db, NON_SM_HASH, level=2, occurrences=47, successes=39)
    # Three observations on the governed session -> the ancestral-replay timeline.
    for txt in (
        "run the full integration suite before tagging the release candidate",
        "kick off the integration tests, do not skip the slow ones this time",
        "running integration before the version bump as usual",
    ):
        _seed_observation(bus, NON_SM_SESSION, NON_SM_HASH, txt)

    resp = client.get(f"/api/patterns/{NON_SM_HASH}/pedigree")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["pattern_hash"] == NON_SM_HASH
    assert body["level"] == 2
    assert body["occurrences"] == 47
    assert body["successes"] == 39
    # success_rate is a 0..1 float (39/47 ~= 0.83).
    assert 0.0 <= float(body["success_rate"]) <= 1.0
    assert round(float(body["success_rate"]), 2) == round(39 / 47, 2)

    # The ancestral-replay timeline reconstructs from the matched messages.
    obs = body["observations"]
    assert isinstance(obs, list) and len(obs) == 3
    first = obs[0]
    assert "fingerprint" in first and first["fingerprint"]
    assert "ts_label" in first
    # overfit is always present (flagged bool + pct + profile), never tint-only.
    assert "overfit" in body and isinstance(body["overfit"], dict)
    assert "flagged" in body["overfit"]


def test_pedigree_unknown_hash_is_404(dashboard_client):
    client, bus, db = dashboard_client
    resp = client.get("/api/patterns/0000000000000000/pedigree")
    assert resp.status_code == 404


def test_pedigree_empty_db_degrades_to_404_not_500(dashboard_client):
    client, bus, db = dashboard_client
    # No graph_patterns table at all (nothing seeded) -- must NOT 500.
    resp = client.get(f"/api/patterns/{NON_SM_HASH}/pedigree")
    assert resp.status_code == 404


def test_pedigree_excludes_sm_self_pattern(dashboard_client):
    """G2 polarity: a pattern whose observations live ONLY on an SM-self
    session (project_slug == streamManager) must 404 -- the oracle never
    exposes SM-self pedigree."""
    client, bus, db = dashboard_client
    _seed_pattern(db, SM_SELF_HASH, level=1, occurrences=5, successes=4)
    # Observations ONLY on the SM-self session.
    _seed_observation(bus, SM_SELF_SESSION, SM_SELF_HASH, "sm self decision one")
    _seed_observation(bus, SM_SELF_SESSION, SM_SELF_HASH, "sm self decision two")

    resp = client.get(f"/api/patterns/{SM_SELF_HASH}/pedigree")
    assert resp.status_code == 404, (
        "SM-self pattern pedigree must be suppressed (no-self-monitor floor)"
    )
