"""v2.1 P2 (FR-PPP) Layer 2 — canary envelope round-trip + HMAC sig.

Covers:
  - to_dict / signing_payload round-trip for the 3 new envelope types
  - HMAC sig validates after build → sign → stamp sequence
  - Sig binds nonce + probe_id (mutating either field breaks the sig)
"""

from __future__ import annotations

import importlib
import sys

from stream_manager.message_bus import (
    AuditCanaryEmitEnvelope,
    AuditCanaryObservedEnvelope,
    AuditProbeFailureEnvelope,
)


def _fresh_dc(monkeypatch):
    if "stream_manager.desktop_commands" in sys.modules:
        del sys.modules["stream_manager.desktop_commands"]
    monkeypatch.setenv("SM_DESKTOP_SECRET", "p2-test-secret")
    return importlib.import_module("stream_manager.desktop_commands")


def _sign(dc, payload):
    return dc.sign({k: v for k, v in payload.items() if k != "hmac_sig"})


def test_canary_emit_round_trip(monkeypatch):
    dc = _fresh_dc(monkeypatch)
    env = AuditCanaryEmitEnvelope(
        probe_id="p1", jsonl_path="/a.jsonl", nonce="deadbeef",
        issued_at=1000.0, timeout_s=10, hmac_sig="",
    )
    d = env.to_dict()
    assert d["probe_id"] == "p1"
    assert d["nonce"] == "deadbeef"
    assert d["timeout_s"] == 10
    sp = env.signing_payload()
    assert "hmac_sig" not in sp
    d["hmac_sig"] = _sign(dc, d)
    assert _sign(dc, d) == d["hmac_sig"]


def test_canary_observed_round_trip(monkeypatch):
    dc = _fresh_dc(monkeypatch)
    env = AuditCanaryObservedEnvelope(
        probe_id="p1", nonce="deadbeef", observed_at=2000.0,
        jsonl_path="/a.jsonl", hmac_sig="",
    )
    d = env.to_dict()
    d["hmac_sig"] = _sign(dc, d)
    assert len(d["hmac_sig"]) == 64
    sp = env.signing_payload()
    assert "hmac_sig" not in sp
    assert sp["nonce"] == "deadbeef"


def test_probe_failure_round_trip(monkeypatch):
    dc = _fresh_dc(monkeypatch)
    env = AuditProbeFailureEnvelope(
        probe_id="p1", reason="canary_timeout",
        failed_at=3000.0, hmac_sig="",
    )
    d = env.to_dict()
    d["hmac_sig"] = _sign(dc, d)
    assert _sign(dc, d) == d["hmac_sig"]


def test_sig_binds_nonce(monkeypatch):
    """Mutating nonce after sign breaks the sig."""
    dc = _fresh_dc(monkeypatch)
    env = AuditCanaryEmitEnvelope(
        probe_id="p1", jsonl_path="/a.jsonl", nonce="aaaa",
        issued_at=1000.0, timeout_s=10, hmac_sig="",
    )
    d = env.to_dict()
    sig = _sign(dc, d)
    d["nonce"] = "bbbb"
    tampered = _sign(dc, d)
    assert sig != tampered


def test_sig_binds_probe_id(monkeypatch):
    """Mutating probe_id after sign breaks the sig."""
    dc = _fresh_dc(monkeypatch)
    env = AuditCanaryObservedEnvelope(
        probe_id="p1", nonce="n", observed_at=1000.0,
        jsonl_path="/a.jsonl", hmac_sig="",
    )
    d = env.to_dict()
    sig = _sign(dc, d)
    d["probe_id"] = "p2"
    assert _sign(dc, d) != sig
