"""v2.1 P1a (FR-PPP-7) — replay protection: endpoint 409 + DB UNIQUE.

Covers FR-PPP-7 (`REQUIREMENTS.md` §4.13):
  - POST /api/sm-probe/ack twice with the same probe_id ⇒ HTTP 409
    on the second request (first write wins).
  - `bus.write_provenance_assertion` returns True on first call and
    False on a duplicate-probe_id call (UNIQUE constraint at SQLite
    level guarantees no duplicate row writes regardless of caller
    concurrency).

Carries the P1 deferral recorded in `docs/v2.1-p1-scope.md` §3 LOC
tracker (P1a `tests/test_audit_probe_replay.py` row).
"""

from __future__ import annotations

import importlib
import sys
import time

import pytest
from fastapi.testclient import TestClient

from stream_manager.message_bus import Message, MessageBus


SESSION_ID = "s-replay"


@pytest.fixture
def dashboard_client(tmp_path, monkeypatch):
    db = tmp_path / "gov.db"
    monkeypatch.setenv("GOV_DB", str(db))
    if "dashboard.server" in sys.modules:
        del sys.modules["dashboard.server"]
    if "stream_manager.desktop_commands" in sys.modules:
        del sys.modules["stream_manager.desktop_commands"]
    importlib.import_module("stream_manager.desktop_commands")
    server = importlib.import_module("dashboard.server")

    bus = MessageBus(str(db))
    bus.open_session(SESSION_ID, project_slug="t", pid=1)
    server._bus = bus
    return TestClient(server.app), bus


def _queue_hitl(bus: MessageBus, probe_id: str) -> int:
    """Publish an anchor message + queue a hitl_pending row pointing at
    it (mirrors `governance.emit_audit_probe`). Returns the hitl row id."""
    anchor = Message.new(
        session_id=SESSION_ID, type="audit_probe", direction="internal",
        content=probe_id,
    )
    bus.publish(anchor)
    return bus.queue_hitl(
        message_id=anchor.id,
        proposed_action="select_stream",
        proposed_confidence=0.0,
        trigger_reason="audit_probe",
    )


def test_endpoint_409_on_replay(dashboard_client):
    """Second POST with the same probe_id MUST return HTTP 409."""
    client, bus = dashboard_client
    probe_id = "p-replay-1"
    hitl_id = _queue_hitl(bus, probe_id)
    body = {
        "probe_id": probe_id,
        "hitl_id": hitl_id,
        "session_id": SESSION_ID,
        "selected_jsonl_path": "/tmp/a.jsonl",
    }
    r1 = client.post("/api/sm-probe/ack", json=body)
    assert r1.status_code == 200, r1.text
    assert r1.json()["written"] is True

    # Re-queue a fresh hitl row so the second call's resolve_hitl target
    # exists (the first POST already resolved the original row).
    hitl_id2 = _queue_hitl(bus, probe_id)
    body2 = dict(body, hitl_id=hitl_id2)
    r2 = client.post("/api/sm-probe/ack", json=body2)
    assert r2.status_code == 409, r2.text


def test_db_unique_constraint_raises(tmp_path):
    """`write_provenance_assertion` returns True/False without raising;
    second call MUST return False (ON CONFLICT DO NOTHING)."""
    bus = MessageBus(str(tmp_path / "bus.db"))
    bus.open_session(SESSION_ID, project_slug="t", pid=1)
    now = time.time()
    written1 = bus.write_provenance_assertion(
        probe_id="p-db-1", session_id=SESSION_ID, jsonl_path="/x.jsonl",
        brain_id="b", prompt_hash="",
        signed_at=now, expires_at=now + 300.0, hmac_sig="sig",
    )
    assert written1 is True
    written2 = bus.write_provenance_assertion(
        probe_id="p-db-1", session_id=SESSION_ID, jsonl_path="/y.jsonl",
        brain_id="b2", prompt_hash="hash",
        signed_at=now + 1, expires_at=now + 600.0, hmac_sig="sig2",
    )
    assert written2 is False
    # First-write-wins: row state is the original.
    row = bus.get_active_provenance_assertion(SESSION_ID, now=now + 2)
    assert row is not None
    assert row["jsonl_path"] == "/x.jsonl"
    assert row["hmac_sig"] == "sig"


def test_endpoint_first_write_wins_state(dashboard_client):
    """After replay-409, the persisted row is the FIRST write's state."""
    client, bus = dashboard_client
    probe_id = "p-replay-2"
    hitl_id = _queue_hitl(bus, probe_id)
    r1 = client.post("/api/sm-probe/ack", json={
        "probe_id": probe_id, "hitl_id": hitl_id, "session_id": SESSION_ID,
        "selected_jsonl_path": "/first.jsonl",
    })
    assert r1.status_code == 200, r1.text

    hitl_id2 = _queue_hitl(bus, probe_id)
    r2 = client.post("/api/sm-probe/ack", json={
        "probe_id": probe_id, "hitl_id": hitl_id2, "session_id": SESSION_ID,
        "selected_jsonl_path": "/second-EVIL.jsonl",
    })
    assert r2.status_code == 409

    row = bus.get_active_provenance_assertion(SESSION_ID, now=time.time())
    assert row is not None
    assert row["jsonl_path"] == "/first.jsonl"


def test_endpoint_v2_sig_includes_brain_id_and_prompt_hash(dashboard_client):
    """R14: sig_v=2 enrichment — brain_id + prompt_hash flow into WAL +
    are bound into the HMAC sig."""
    from stream_manager import desktop_commands as dc
    from stream_manager.message_bus import AuditProbeAckEnvelope

    client, bus = dashboard_client
    probe_id = "p-v2-1"
    hitl_id = _queue_hitl(bus, probe_id)
    r = client.post("/api/sm-probe/ack", json={
        "probe_id": probe_id, "hitl_id": hitl_id, "session_id": SESSION_ID,
        "selected_jsonl_path": "/x.jsonl",
        "brain_id": "brain-xyz", "prompt_hash": "deadbeef",
    })
    assert r.status_code == 200, r.text
    assert r.json().get("sig_v") == 2

    row = bus.get_active_provenance_assertion(SESSION_ID, now=time.time())
    assert row is not None
    assert row["brain_id"] == "brain-xyz"
    assert row["prompt_hash"] == "deadbeef"

    # Sig MUST cover brain_id + prompt_hash: re-construct under v2 and
    # confirm the stored sig matches.
    ack = AuditProbeAckEnvelope(
        probe_id=probe_id, selected_jsonl_path="/x.jsonl",
        signed_at=float(row["signed_at"]), expires_at=float(row["expires_at"]),
        hmac_sig="", brain_id="brain-xyz", prompt_hash="deadbeef", sig_v=2,
    )
    assert dc.sign(ack.signing_payload()) == row["hmac_sig"]

    # Tampering with brain_id post-sign breaks validation.
    ack_evil = AuditProbeAckEnvelope(
        probe_id=probe_id, selected_jsonl_path="/x.jsonl",
        signed_at=float(row["signed_at"]), expires_at=float(row["expires_at"]),
        hmac_sig="", brain_id="brain-EVIL", prompt_hash="deadbeef", sig_v=2,
    )
    assert dc.sign(ack_evil.signing_payload()) != row["hmac_sig"]


def test_v1_signing_payload_omits_v2_fields():
    """Backwards compat: sig_v=1 signing_payload MUST NOT include
    brain_id/prompt_hash/sig_v so existing v1 sigs validate unchanged."""
    from stream_manager.message_bus import AuditProbeAckEnvelope

    ack_v1 = AuditProbeAckEnvelope(
        probe_id="p", selected_jsonl_path="/x.jsonl",
        signed_at=1.0, expires_at=2.0, hmac_sig="",
    )
    sp = ack_v1.signing_payload()
    assert set(sp.keys()) == {"probe_id", "selected_jsonl_path", "signed_at", "expires_at"}
    assert "brain_id" not in sp
    assert "prompt_hash" not in sp
    assert "sig_v" not in sp


def test_v2_signing_payload_includes_all_enrichment():
    """sig_v=2 signing_payload binds brain_id, prompt_hash, sig_v."""
    from stream_manager.message_bus import AuditProbeAckEnvelope

    ack_v2 = AuditProbeAckEnvelope(
        probe_id="p", selected_jsonl_path="/x.jsonl",
        signed_at=1.0, expires_at=2.0, hmac_sig="",
        brain_id="b", prompt_hash="h", sig_v=2,
    )
    sp = ack_v2.signing_payload()
    assert sp["brain_id"] == "b"
    assert sp["prompt_hash"] == "h"
    assert sp["sig_v"] == 2
    assert "hmac_sig" not in sp
