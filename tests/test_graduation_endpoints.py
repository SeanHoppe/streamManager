"""ADR-18 Amendment F — graduation candidate-scan + confirm endpoint tests.

Covers the read-only candidate scan (eligibility gates + polarity dual-key
+ excluded_self), the operator-confirm POST (M8: writes a rule only on
explicit confirm, re-verifies server-side), the demote reversal
(invariant #5), and the no-auto-write guarantee. Generic protocol vocab
only (M16) — no monitored-project identities.
"""

from __future__ import annotations

import importlib
import sys

import pytest
from fastapi.testclient import TestClient

from stream_manager.message_bus import MessageBus


@pytest.fixture
def client_bus(tmp_path, monkeypatch):
    db = tmp_path / "gov.db"
    monkeypatch.setenv("GOV_DB", str(db))
    monkeypatch.setenv("BRIDGE_SM_PROJECT_SLUGS", "streamManager")
    monkeypatch.delenv("SM_OWN_SESSION_ID", raising=False)
    if "dashboard.server" in sys.modules:
        del sys.modules["dashboard.server"]
    server = importlib.import_module("dashboard.server")
    bus = MessageBus(str(db))
    server._bus = bus
    return TestClient(server.app), bus


def _seed_shape(
    bus: MessageBus, *, session_id: str, project_slug: str, shape_hash: str,
    content: str, n_allow: int, n_block: int = 0, confidence: float = 0.97,
    n_override: int = 0,
) -> None:
    bus.execute_write(
        "INSERT OR IGNORE INTO sessions (id, project_slug, started_at) "
        "VALUES (?, ?, ?)", (session_id, project_slug, 1.0))
    seq = 0

    def _row(action: str, idx: int) -> str:
        nonlocal seq
        mid = f"{shape_hash}-m-{action}-{idx}"
        did = f"{shape_hash}-d-{action}-{idx}"
        bus.execute_write(
            "INSERT INTO messages (id, session_id, sequence, type, "
            "direction, content, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (mid, session_id, seq, "user", "in", content, 1.0))
        bus.execute_write(
            "INSERT INTO decisions (id, message_id, action, confidence, "
            "reasoning, matched_hash, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (did, mid, action, confidence, "ok", shape_hash, 1.0))
        seq += 1
        return did

    for i in range(n_allow):
        did = _row("ALLOW", i)
        if i < n_override:
            bus.execute_write(
                "INSERT INTO hitl_overrides (decision_id, original_action, "
                "override_action, note, mode, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (did, "ALLOW", "INTERVENE", "", "ENFORCE", "2026-01-01"))
    for i in range(n_block):
        _row("BLOCK", i)


def _hashes(resp) -> set[str]:
    return {c["shape_hash"] for c in resp.json()["candidates"]}


# ── candidate scan ───────────────────────────────────────────────────


def test_scan_surfaces_eligible_shape(client_bus):
    client, bus = client_bus
    _seed_shape(bus, session_id="s1", project_slug="demo-app",
                shape_hash="routine1", content="git status", n_allow=35)
    r = client.get("/api/graduation/candidates")
    assert r.status_code == 200
    assert "routine1" in _hashes(r)
    cand = next(c for c in r.json()["candidates"] if c["shape_hash"] == "routine1")
    assert cand["n_allow"] == 35
    assert cand["n_block_ever"] == 0


def test_scan_excludes_too_few_allow(client_bus):
    client, bus = client_bus
    _seed_shape(bus, session_id="s1", project_slug="demo-app",
                shape_hash="rare1", content="git log", n_allow=20)
    assert "rare1" not in _hashes(client.get("/api/graduation/candidates"))


def test_scan_excludes_safety_floor_shape(client_bus):
    # Acceptance: a destructive-shell shape at 100% ALLOW history is NOT
    # offered as a candidate (invariant #2, safety-floor ineligibility).
    client, bus = client_bus
    _seed_shape(bus, session_id="s1", project_slug="demo-app",
                shape_hash="danger1", content="rm -rf /var/data",
                n_allow=80, confidence=0.99)
    assert "danger1" not in _hashes(client.get("/api/graduation/candidates"))


def test_scan_excludes_drop_database_shape(client_bus):
    # Invariant #2 regression (adversarial review): a DROP DATABASE shape is
    # caught by the precheck but was NOT by the governance-local DROP TABLE
    # regex. The candidate gate (now a precheck superset) must exclude it AND
    # confirm must refuse it, even with clean routine stats.
    client, bus = client_bus
    _seed_shape(bus, session_id="s1", project_slug="demo-app",
                shape_hash="dropdb1", content="DROP DATABASE analytics",
                n_allow=60, confidence=0.99)
    assert "dropdb1" not in _hashes(client.get("/api/graduation/candidates"))
    r = client.post("/api/graduation/confirm", json={"shape_hash": "dropdb1"})
    assert r.status_code == 409
    assert bus.lookup_graduated_rule("dropdb1") is None


def test_scan_excludes_block_ever(client_bus):
    client, bus = client_bus
    _seed_shape(bus, session_id="s1", project_slug="demo-app",
                shape_hash="mixed1", content="make deploy",
                n_allow=40, n_block=1)
    assert "mixed1" not in _hashes(client.get("/api/graduation/candidates"))


def test_scan_excludes_overridden_shape(client_bus):
    client, bus = client_bus
    _seed_shape(bus, session_id="s1", project_slug="demo-app",
                shape_hash="over1", content="npm test",
                n_allow=40, n_override=2)
    assert "over1" not in _hashes(client.get("/api/graduation/candidates"))


def test_scan_polarity_excludes_sm_self(client_bus):
    # A shape that lives ONLY on an SM-self session (project_slug in the SM
    # set) is never surfaced; excluded_self tallies the dropped rows.
    client, bus = client_bus
    _seed_shape(bus, session_id="sm1", project_slug="streamManager",
                shape_hash="self1", content="git status", n_allow=50)
    r = client.get("/api/graduation/candidates")
    assert "self1" not in _hashes(r)
    assert r.json()["excluded_self"] >= 50


# ── operator-confirm (M8) ────────────────────────────────────────────


def test_confirm_writes_rule_only_on_request(client_bus):
    client, bus = client_bus
    _seed_shape(bus, session_id="s1", project_slug="demo-app",
                shape_hash="routine1", content="git status", n_allow=35)
    # Scan alone writes nothing (M8 — no auto-graduation).
    client.get("/api/graduation/candidates")
    assert bus.list_graduated_rules() == []
    # Explicit confirm writes the rule.
    r = client.post("/api/graduation/confirm", json={"shape_hash": "routine1"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["graduated"] is True
    assert body["n_allow_at_grad"] == 35
    rule = bus.lookup_graduated_rule("routine1")
    assert rule is not None and rule["active"] == 1


def test_confirm_refuses_safety_floor(client_bus):
    client, bus = client_bus
    _seed_shape(bus, session_id="s1", project_slug="demo-app",
                shape_hash="danger1", content="rm -rf /var/data",
                n_allow=80, confidence=0.99)
    r = client.post("/api/graduation/confirm", json={"shape_hash": "danger1"})
    assert r.status_code == 409
    assert bus.lookup_graduated_rule("danger1") is None


def test_confirm_unknown_shape_404(client_bus):
    client, _bus = client_bus
    r = client.post("/api/graduation/confirm", json={"shape_hash": "nope"})
    assert r.status_code == 404


def test_confirm_requires_shape_hash(client_bus):
    client, _bus = client_bus
    r = client.post("/api/graduation/confirm", json={})
    assert r.status_code == 400


def test_confirm_refuses_sm_self_shape(client_bus):
    # Polarity on the write path: a shape that exists only on SM-self
    # cannot be confirmed (the re-verify scan yields None → 404).
    client, bus = client_bus
    _seed_shape(bus, session_id="sm1", project_slug="streamManager",
                shape_hash="self1", content="git status", n_allow=50)
    r = client.post("/api/graduation/confirm", json={"shape_hash": "self1"})
    assert r.status_code == 404
    assert bus.lookup_graduated_rule("self1") is None


# ── demote reversal (invariant #5) ───────────────────────────────────


def test_demote_reverses_graduation(client_bus):
    client, bus = client_bus
    _seed_shape(bus, session_id="s1", project_slug="demo-app",
                shape_hash="routine1", content="git status", n_allow=35)
    client.post("/api/graduation/confirm", json={"shape_hash": "routine1"})
    assert bus.lookup_graduated_rule("routine1") is not None
    r = client.post("/api/patterns/routine1/demote")
    assert r.status_code == 200, r.text
    assert bus.lookup_graduated_rule("routine1") is None  # stops firing
