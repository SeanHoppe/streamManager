"""v2.1 P2 (FR-PPP) Layer 2 — cassette coverage for canary triplet.

Asserts that ``tools.cassette_record._record_ppp_envelopes`` records
all 3 new envelope types same-cycle per
``feedback_cassette_must_cover_new_envelopes.md``.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from stream_manager import message_bus as _msg_bus


@pytest.fixture
def bus(tmp_path: Path, monkeypatch) -> _msg_bus.MessageBus:
    monkeypatch.setenv("SM_DESKTOP_SECRET", "p2-cassette-test")
    if "stream_manager.desktop_commands" in sys.modules:
        del sys.modules["stream_manager.desktop_commands"]
    importlib.import_module("stream_manager.desktop_commands")
    return _msg_bus.MessageBus(str(tmp_path / "bus.db"))


def test_cassette_records_canary_triplet(bus):
    captured: list[tuple[str, dict]] = []
    bus.subscribe_envelope(lambda t, p: captured.append((t, p)))
    cassette = importlib.import_module("tools.cassette_record")
    rows = cassette._record_ppp_envelopes(bus, session_id="sess", start_idx=0)
    kinds = {r["kind"] for r in rows}
    assert {"audit_canary_emit", "audit_canary_observed",
            "audit_probe_failure"} <= kinds
    env_types = {t for t, _ in captured}
    assert {"audit.canary_emit", "audit.canary_observed",
            "audit.probe_failure"} <= env_types
    # Sanity: each envelope carries a 64-char SHA-256 hex sig.
    for t, p in captured:
        if t.startswith("audit.canary") or t == "audit.probe_failure":
            assert len(p["hmac_sig"]) == 64
