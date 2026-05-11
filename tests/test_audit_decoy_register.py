"""v2.1 P3 (FR-PPP-12) Layer 3 — decoy registration + WAL row shape.

Covers:
  - write_provenance_decoy + WAL row shape
  - probe_id UNIQUE constraint (first-write-wins)
  - jsonl_path UNIQUE constraint (idempotent re-register on same path)
  - is_registered_decoy_path reader returns the probe_id for a hit
  - mark_decoy_triggered single-write-wins (WHERE triggered_at IS NULL)
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from stream_manager import message_bus as _msg_bus


@pytest.fixture
def bus(tmp_path: Path, monkeypatch) -> _msg_bus.MessageBus:
    monkeypatch.setenv("SM_DESKTOP_SECRET", "p3-decoy-test")
    if "stream_manager.desktop_commands" in sys.modules:
        del sys.modules["stream_manager.desktop_commands"]
    importlib.import_module("stream_manager.desktop_commands")
    return _msg_bus.MessageBus(str(tmp_path / "bus.db"))


def test_write_provenance_decoy_first_write_returns_true(bus):
    ok = bus.write_provenance_decoy(
        probe_id="p1", jsonl_path="/tmp/decoy-1.jsonl",
        registered_at=1000.0, hmac_sig="sigA",
    )
    assert ok is True
    row = bus._conn.execute(
        "SELECT probe_id, jsonl_path, registered_at, triggered_at, "
        "hmac_sig FROM provenance_decoys WHERE probe_id='p1'"
    ).fetchone()
    assert row == ("p1", "/tmp/decoy-1.jsonl", 1000.0, None, "sigA")


def test_write_provenance_decoy_dupe_path_returns_false(bus):
    """Re-register on the same jsonl_path is idempotent (no-op, not error)."""
    assert bus.write_provenance_decoy(
        "p1", "/tmp/decoy-2.jsonl", 1000.0, "sigA"
    ) is True
    # Different probe_id, same path — UNIQUE on jsonl_path triggers no-op.
    assert bus.write_provenance_decoy(
        "p2", "/tmp/decoy-2.jsonl", 2000.0, "sigB"
    ) is False
    # The row keeps the FIRST registration; second write was discarded.
    row = bus._conn.execute(
        "SELECT probe_id, registered_at, hmac_sig FROM provenance_decoys "
        "WHERE jsonl_path='/tmp/decoy-2.jsonl'"
    ).fetchone()
    assert row == ("p1", 1000.0, "sigA")


def test_is_registered_decoy_path_returns_probe_id(bus):
    bus.write_provenance_decoy(
        "p1", "/tmp/decoy-3.jsonl", 1000.0, "sig",
    )
    assert bus.is_registered_decoy_path("/tmp/decoy-3.jsonl") == "p1"
    assert bus.is_registered_decoy_path("/tmp/unknown.jsonl") is None
    assert bus.is_registered_decoy_path("") is None


def test_mark_decoy_triggered_single_write_wins(bus):
    bus.write_provenance_decoy(
        "p1", "/tmp/decoy-4.jsonl", 1000.0, "sig",
    )
    assert bus.mark_decoy_triggered("p1", 2000.0) is True
    # Second stamp must no-op (WHERE triggered_at IS NULL).
    assert bus.mark_decoy_triggered("p1", 3000.0) is False
    row = bus._conn.execute(
        "SELECT triggered_at FROM provenance_decoys WHERE probe_id='p1'"
    ).fetchone()
    assert row[0] == 2000.0  # first stamp wins; second value not applied


def test_mark_decoy_triggered_unknown_probe_id_returns_false(bus):
    assert bus.mark_decoy_triggered("never-registered", 1000.0) is False


def test_register_decoy_stream_via_engine(bus, tmp_path):
    """End-to-end via governance.register_decoy_stream: row landed +
    sig binds {probe_id, jsonl_path, registered_at}."""
    from stream_manager.governance import GovernanceEngine
    from stream_manager.project_context import ProjectContextSnapshot
    engine = GovernanceEngine(
        project_context=ProjectContextSnapshot(repo_path=str(tmp_path)),
        bus=bus, session_id="s1",
    )
    probe_id, reg, first = engine.register_decoy_stream(
        jsonl_path="/tmp/engine-decoy.jsonl",
    )
    assert first is True
    assert set(reg.keys()) == {
        "probe_id", "jsonl_path", "registered_at", "hmac_sig",
    }
    assert reg["probe_id"] == probe_id
    assert reg["jsonl_path"] == "/tmp/engine-decoy.jsonl"
    assert len(reg["hmac_sig"]) == 64

    # Re-register same path → first_write False, row unchanged.
    probe_id2, reg2, first2 = engine.register_decoy_stream(
        jsonl_path="/tmp/engine-decoy.jsonl",
    )
    assert first2 is False
