"""v2.1 P3 (FR-PPP-14) Layer 3 — cassette coverage for hallucination
envelope + decoy registration row.

Asserts that ``tools.cassette_record._record_ppp_envelopes`` (the
existing PPP helper) ALSO records the Layer-3 surface same-cycle per
``feedback_cassette_must_cover_new_envelopes.md``:

  - One `audit.hallucination_detected` envelope fired on the bus
  - One `provenance_decoys` row landed in the WAL
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from stream_manager import message_bus as _msg_bus


@pytest.fixture
def bus(tmp_path: Path, monkeypatch) -> _msg_bus.MessageBus:
    monkeypatch.setenv("SM_DESKTOP_SECRET", "p3-cassette-test")
    if "stream_manager.desktop_commands" in sys.modules:
        del sys.modules["stream_manager.desktop_commands"]
    importlib.import_module("stream_manager.desktop_commands")
    return _msg_bus.MessageBus(str(tmp_path / "bus.db"))


def test_cassette_records_hallucination_envelope_and_decoy_row(bus):
    captured: list[tuple[str, dict]] = []
    bus.subscribe_envelope(lambda t, p: captured.append((t, p)))
    cassette = importlib.import_module("tools.cassette_record")
    rows = cassette._record_ppp_envelopes(bus, session_id="sess", start_idx=0)
    kinds = {r["kind"] for r in rows}
    assert "audit_hallucination_detected" in kinds
    assert "audit_decoy_register" in kinds

    env_types = {t for t, _ in captured}
    assert "audit.hallucination_detected" in env_types

    halluc = next(p for t, p in captured if t == "audit.hallucination_detected")
    # 64-char SHA-256 hex sig per FR-PPP-5 sign-then-mutate guard.
    assert len(halluc["hmac_sig"]) == 64
    assert halluc["probe_id"].startswith("cassette-decoy-")
    assert halluc["jsonl_path"].endswith(".jsonl")

    # WAL row landed + triggered_at stamped.
    row = bus._conn.execute(
        "SELECT probe_id, jsonl_path, registered_at, triggered_at, "
        "hmac_sig FROM provenance_decoys"
    ).fetchone()
    assert row is not None
    assert row[0] == halluc["probe_id"]
    assert row[1] == halluc["jsonl_path"]
    assert isinstance(row[2], float)
    assert isinstance(row[3], float)  # triggered_at stamped
    assert len(row[4]) == 64  # registration sig


def test_helper_isolated_from_layers_1_2(bus):
    """The Layer-3 helper records its own surface even when called
    directly (rather than through `_record_ppp_envelopes`). Useful for
    test fixtures that only want the Layer-3 row."""
    cassette = importlib.import_module("tools.cassette_record")
    rows = cassette._record_decoy_envelopes(bus, start_idx=10, issued_at=1.0)
    assert {r["kind"] for r in rows} == {
        "audit_decoy_register", "audit_hallucination_detected",
    }
    # Indices use the start_idx contiguous run.
    idxs = sorted(r["idx"] for r in rows)
    assert idxs == [10, 11]
