"""v2.1 P1 (FR-PPP) Layer 1 — emit_audit_probe + HITL ack lifecycle.

Covers:
  - emit_audit_probe returns (probe_id, hitl_row_id, delivered_count)
  - HITL row queued with trigger_reason="audit_probe"
  - delivered_count reflects subscriber count
  - resolve_hitl marks the row as resolved
  - write_provenance_assertion + get_active_provenance_assertion latest-wins
"""

from __future__ import annotations

import importlib
import sys
import time

import pytest

from stream_manager.message_bus import AuditProbeCandidate, MessageBus
from stream_manager.project_context import ProjectContextSnapshot


def _fresh_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("SM_DESKTOP_SECRET", "ppp-test-secret")
    if "stream_manager.desktop_commands" in sys.modules:
        del sys.modules["stream_manager.desktop_commands"]
    importlib.import_module("stream_manager.desktop_commands")
    from stream_manager.governance import GovernanceEngine
    bus = MessageBus(str(tmp_path / "bus.db"))
    bus.open_session("s1", project_slug="t", pid=1)
    engine = GovernanceEngine(
        project_context=ProjectContextSnapshot(repo_path=str(tmp_path)),
        bus=bus, session_id="s1",
    )
    return engine, bus


def _candidate(slug: str = "p", path: str = "/tmp/a.jsonl") -> AuditProbeCandidate:
    return AuditProbeCandidate(
        slug=slug, jsonl_path=path, brain_id="b1",
        last_event_ts=1000.0, prompt_hash="",
    )


def test_emit_returns_probe_hitl_delivered_tuple(tmp_path, monkeypatch):
    engine, bus = _fresh_engine(tmp_path, monkeypatch)
    received: list[tuple[str, dict]] = []
    bus.subscribe_envelope(lambda t, p: received.append((t, p)))

    probe_id, hitl_id, delivered = engine.emit_audit_probe([_candidate()])

    assert isinstance(probe_id, str) and len(probe_id) == 32  # uuid hex
    assert hitl_id > 0
    assert delivered == 1
    assert received[0][0] == "audit.probe"
    assert received[0][1]["probe_id"] == probe_id


def test_emit_zero_subscriber_returns_zero_delivered(tmp_path, monkeypatch):
    engine, bus = _fresh_engine(tmp_path, monkeypatch)
    _, hitl_id, delivered = engine.emit_audit_probe([_candidate()])
    assert delivered == 0
    # HITL row exists; caller (dashboard handler) is responsible for
    # resolving it as "no_subscriber" + returning 503.
    row = bus.get_hitl_pending_row(hitl_id)
    assert row is not None
    assert row["trigger_reason"] == "audit_probe"
    assert row["resolved_at"] is None


def test_resolve_hitl_marks_row_resolved(tmp_path, monkeypatch):
    engine, bus = _fresh_engine(tmp_path, monkeypatch)
    _, hitl_id, _ = engine.emit_audit_probe([_candidate()])
    bus.resolve_hitl(hitl_id, "approved")
    row = bus.get_hitl_pending_row(hitl_id)
    assert row is not None
    assert row["resolved_at"] is not None
    assert row["resolution"] == "approved"


def test_provenance_latest_signed_at_wins(tmp_path, monkeypatch):
    """get_active_provenance_assertion returns the row with the largest
    signed_at among non-expired rows for a session_id (per `idx_provenance
    _session_active`)."""
    _, bus = _fresh_engine(tmp_path, monkeypatch)
    now = time.time()
    bus.write_provenance_assertion(
        probe_id="p1", session_id="s1", jsonl_path="/old.jsonl",
        brain_id="b1", prompt_hash="",
        signed_at=now - 100.0, expires_at=now + 100.0, hmac_sig="sig1",
    )
    bus.write_provenance_assertion(
        probe_id="p2", session_id="s1", jsonl_path="/new.jsonl",
        brain_id="b1", prompt_hash="",
        signed_at=now - 10.0, expires_at=now + 100.0, hmac_sig="sig2",
    )
    active = bus.get_active_provenance_assertion("s1", now=now)
    assert active is not None
    assert active["jsonl_path"] == "/new.jsonl"
    assert active["probe_id"] == "p2"


def test_provenance_expired_row_skipped(tmp_path, monkeypatch):
    _, bus = _fresh_engine(tmp_path, monkeypatch)
    now = time.time()
    bus.write_provenance_assertion(
        probe_id="p1", session_id="s1", jsonl_path="/x.jsonl",
        brain_id="b1", prompt_hash="",
        signed_at=now - 1000.0, expires_at=now - 100.0, hmac_sig="sig",
    )
    assert bus.get_active_provenance_assertion("s1", now=now) is None
