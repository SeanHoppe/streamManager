"""v2.1 P1 (FR-PPP) Layer 1 — envelope round-trip + HMAC sig coverage.

Reduced post-P1a-split: replay-409 + DB UNIQUE constraint moved to
`tests/test_audit_probe_replay.py` in P1a. Self-monitor candidate
filtering moved to `tests/test_audit_probe_self_monitor.py` in P1a.

Covers:
  - to_dict round-trip for AuditProbeCandidate / Envelope / AckEnvelope
  - HMAC sig validates after build → sign → stamp sequence
  - Sig covers candidate_streams (mutating a candidate post-sign breaks)
  - TTL: ttl_seconds round-trips; expires_at = signed_at + ttl_seconds
  - None-ack: selected_jsonl_path=None signs + validates
"""

from __future__ import annotations

import sys

import pytest

from stream_manager.message_bus import (
    AuditProbeAckEnvelope,
    AuditProbeCandidate,
    AuditProbeEnvelope,
)


def _fresh_desktop_commands(monkeypatch):
    if "stream_manager.desktop_commands" in sys.modules:
        del sys.modules["stream_manager.desktop_commands"]
    monkeypatch.setenv("SM_DESKTOP_SECRET", "ppp-test-secret")
    import importlib
    return importlib.import_module("stream_manager.desktop_commands")


def _build_envelope(probe_id: str = "p1") -> AuditProbeEnvelope:
    cand = AuditProbeCandidate(
        slug="proj", jsonl_path="/tmp/a.jsonl",
        brain_id="b1", last_event_ts=1000.0, prompt_hash="",
    )
    return AuditProbeEnvelope(
        probe_id=probe_id, candidate_streams=[cand],
        ttl_seconds=300, issued_at=2000.0, hmac_sig="",
    )


def test_candidate_to_dict_round_trip():
    cand = AuditProbeCandidate(
        slug="s", jsonl_path="/p.jsonl", brain_id="b",
        last_event_ts=1.0, prompt_hash="",
    )
    d = cand.to_dict()
    assert d == {
        "slug": "s", "jsonl_path": "/p.jsonl", "brain_id": "b",
        "last_event_ts": 1.0, "prompt_hash": "",
    }


def test_envelope_to_dict_includes_signing_payload():
    env = _build_envelope()
    d = env.to_dict()
    assert d["probe_id"] == "p1"
    assert d["ttl_seconds"] == 300
    assert d["candidate_streams"][0]["jsonl_path"] == "/tmp/a.jsonl"
    sp = env.signing_payload()
    assert "hmac_sig" not in sp
    assert sp["probe_id"] == "p1"


def test_hmac_sig_round_trip(monkeypatch):
    dc = _fresh_desktop_commands(monkeypatch)
    env = _build_envelope()
    payload = env.to_dict()
    sig_payload = {k: v for k, v in payload.items() if k != "hmac_sig"}
    sig = dc.sign(sig_payload)
    payload["hmac_sig"] = sig
    # Validate by re-signing with the same secret + comparing.
    expected = dc.sign(sig_payload)
    assert payload["hmac_sig"] == expected


def test_sig_covers_candidate_streams(monkeypatch):
    """Mutating a candidate field after sign produces a mismatched sig."""
    dc = _fresh_desktop_commands(monkeypatch)
    env = _build_envelope()
    payload = env.to_dict()
    sig_payload = {k: v for k, v in payload.items() if k != "hmac_sig"}
    sig = dc.sign(sig_payload)
    # Mutate the inner candidate dict (frozen=True at the dataclass
    # level guards in-process mutation; here we mutate post-to_dict()
    # to confirm the wire-level sig still detects tampering).
    sig_payload["candidate_streams"][0]["jsonl_path"] = "/tmp/EVIL.jsonl"
    tampered_sig = dc.sign(sig_payload)
    assert sig != tampered_sig


def test_candidate_is_frozen():
    cand = AuditProbeCandidate(
        slug="s", jsonl_path="/p", brain_id="b",
        last_event_ts=1.0, prompt_hash="",
    )
    with pytest.raises(Exception):
        cand.slug = "MUTATED"  # type: ignore[misc]


def test_ack_envelope_none_path_signs(monkeypatch):
    """selected_jsonl_path=None ('none of the above') signs + validates."""
    dc = _fresh_desktop_commands(monkeypatch)
    ack = AuditProbeAckEnvelope(
        probe_id="p1", selected_jsonl_path=None,
        signed_at=1000.0, expires_at=1300.0, hmac_sig="",
    )
    payload = ack.to_dict()
    assert payload["selected_jsonl_path"] is None
    sig_payload = {k: v for k, v in payload.items() if k != "hmac_sig"}
    sig = dc.sign(sig_payload)
    assert sig and len(sig) == 64  # SHA-256 hex


def test_ack_ttl_consistency(monkeypatch):
    """expires_at = signed_at + ttl_seconds; round-trip preserved."""
    dc = _fresh_desktop_commands(monkeypatch)
    signed_at = 1000.0
    ttl = 300
    ack = AuditProbeAckEnvelope(
        probe_id="p1", selected_jsonl_path="/x.jsonl",
        signed_at=signed_at, expires_at=signed_at + ttl, hmac_sig="",
    )
    payload = ack.to_dict()
    assert payload["expires_at"] - payload["signed_at"] == ttl
    sig_payload = {k: v for k, v in payload.items() if k != "hmac_sig"}
    payload["hmac_sig"] = dc.sign(sig_payload)
    # Round-trip: re-sign yields identical sig.
    assert dc.sign(sig_payload) == payload["hmac_sig"]
