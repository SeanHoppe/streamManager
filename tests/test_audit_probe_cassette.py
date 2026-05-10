"""v2.1 P1 (FR-PPP) Layer 1 — cassette envelope round-trip.

Covers:
  - _record_ppp_envelopes returns 2 rows (audit_probe + audit_probe_ack)
  - rows are byte-identical JSON-encodable shapes
  - HMAC sig present on both
  - subscribe_envelope receives both during the helper run
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

from stream_manager.message_bus import MessageBus

_TOOLS = str(Path(__file__).resolve().parent.parent / "tools")


def test_record_ppp_envelopes_emits_pair(tmp_path, monkeypatch):
    monkeypatch.setenv("SM_DESKTOP_SECRET", "ppp-test-secret")
    for mod in ("stream_manager.desktop_commands", "cassette_record"):
        sys.modules.pop(mod, None)
    importlib.import_module("stream_manager.desktop_commands")
    if _TOOLS not in sys.path:
        sys.path.insert(0, _TOOLS)
    cr = importlib.import_module("cassette_record")

    bus = MessageBus(str(tmp_path / "bus.db"))
    bus.open_session("cs1", project_slug="t", pid=1)
    received: list[tuple[str, dict]] = []
    bus.subscribe_envelope(lambda t, p: received.append((t, p)))

    rows = cr._record_ppp_envelopes(bus, "cs1", start_idx=100)
    assert len(rows) == 2
    assert rows[0]["kind"] == "audit_probe"
    assert rows[1]["kind"] == "audit_probe_ack"
    # Both wrap envelope payloads.
    assert "envelope" in rows[0] and "envelope" in rows[1]
    # HMAC sig present + non-empty on both.
    assert rows[0]["envelope"]["hmac_sig"]
    assert rows[1]["envelope"]["hmac_sig"]
    # JSON round-trip preserves shape.
    for row in rows:
        s = json.dumps(row)
        assert json.loads(s) == row
    # Subscriber received both via bus.write_envelope inside the helper.
    types = [t for t, _ in received]
    assert types == ["audit.probe", "audit.probe_ack"]
