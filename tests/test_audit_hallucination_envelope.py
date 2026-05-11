"""v2.1 P3 (FR-PPP) Layer 3 — hallucination envelope round-trip + HMAC sig.

Covers:
  - to_dict / signing_payload round-trip for AuditHallucinationDetectedEnvelope
  - HMAC sig validates after build → sign → stamp sequence
  - Sig binds jsonl_path + probe_id (mutating either field breaks the sig)
"""

from __future__ import annotations

import importlib
import sys

from stream_manager.message_bus import AuditHallucinationDetectedEnvelope


def _fresh_dc(monkeypatch):
    if "stream_manager.desktop_commands" in sys.modules:
        del sys.modules["stream_manager.desktop_commands"]
    monkeypatch.setenv("SM_DESKTOP_SECRET", "p3-test-secret")
    return importlib.import_module("stream_manager.desktop_commands")


def _sign(dc, payload):
    return dc.sign({k: v for k, v in payload.items() if k != "hmac_sig"})


def test_hallucination_round_trip(monkeypatch):
    dc = _fresh_dc(monkeypatch)
    env = AuditHallucinationDetectedEnvelope(
        probe_id="p1", jsonl_path="/tmp/decoy.jsonl",
        detected_at=1000.0, hmac_sig="",
    )
    d = env.to_dict()
    assert d["probe_id"] == "p1"
    assert d["jsonl_path"] == "/tmp/decoy.jsonl"
    assert d["detected_at"] == 1000.0
    sp = env.signing_payload()
    assert "hmac_sig" not in sp
    d["hmac_sig"] = _sign(dc, d)
    assert len(d["hmac_sig"]) == 64
    assert _sign(dc, d) == d["hmac_sig"]


def test_sig_binds_jsonl_path(monkeypatch):
    """Mutating jsonl_path after sign breaks the sig."""
    dc = _fresh_dc(monkeypatch)
    env = AuditHallucinationDetectedEnvelope(
        probe_id="p1", jsonl_path="/tmp/a.jsonl",
        detected_at=1000.0, hmac_sig="",
    )
    d = env.to_dict()
    sig = _sign(dc, d)
    d["jsonl_path"] = "/tmp/b.jsonl"
    assert _sign(dc, d) != sig


def test_sig_binds_probe_id(monkeypatch):
    """Mutating probe_id after sign breaks the sig."""
    dc = _fresh_dc(monkeypatch)
    env = AuditHallucinationDetectedEnvelope(
        probe_id="p1", jsonl_path="/tmp/a.jsonl",
        detected_at=1000.0, hmac_sig="",
    )
    d = env.to_dict()
    sig = _sign(dc, d)
    d["probe_id"] = "p2"
    assert _sign(dc, d) != sig


def test_signing_payload_excludes_hmac_sig(monkeypatch):
    """signing_payload() MUST drop hmac_sig (canonical sign-then-stamp)."""
    _fresh_dc(monkeypatch)
    env = AuditHallucinationDetectedEnvelope(
        probe_id="p1", jsonl_path="/tmp/a.jsonl",
        detected_at=1000.0, hmac_sig="already-set",
    )
    sp = env.signing_payload()
    assert "hmac_sig" not in sp
    assert sp["probe_id"] == "p1"
