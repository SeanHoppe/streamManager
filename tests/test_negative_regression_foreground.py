"""FR-UI-3: governance_negative_regression auto-foreground wiring.

Verifies the contract between the governance engine (which emits the
bus event) and the dashboard JS listener (which raises ACTION REQUIRED
and calls autoForeground).

JS-unit testing is out of scope for this repo's tooling, so this test
exercises only the Python-side contract:

1. The event TYPE the governance engine emits is exactly the string
   the JS listener filters on (`governance_negative_regression`).
2. The dashboard's /events SSE endpoint forwards that bus event
   verbatim with `event_type` populated, so the browser-side handler
   can match it.

The corresponding JS check lives in dashboard/static/index.html in
EVENT_FOREGROUND_TYPES; this test will fail if the engine ever
renames the event without updating both ends.

Manual repro (FR-UI-3):
- Open the dashboard with the browser tab in the background.
- Trigger a negative cell movement in the maturity artifact.
- Expected: tab title flips to "(1) StreamManager", frame A scrolls
  into view and gains the .action-required pulse class for ~4s.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


# The exact bus-event type string the governance engine emits and the
# dashboard JS filters on. Changing this string is a coordinated rename
# that must touch governance.py + EVENT_FOREGROUND_TYPES in index.html.
NEGATIVE_REGRESSION_TYPE = "governance_negative_regression"


def test_governance_emits_canonical_event_type():
    """The governance engine source must contain the canonical type
    string. If someone renames it, this fails before runtime does."""
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "src" / "stream_manager" / "governance.py"
    text = src.read_text(encoding="utf-8")
    assert NEGATIVE_REGRESSION_TYPE in text, (
        f"Expected {NEGATIVE_REGRESSION_TYPE!r} in governance.py — "
        "if you renamed the event, also update EVENT_FOREGROUND_TYPES "
        "in dashboard/static/index.html."
    )


def test_dashboard_js_listens_for_canonical_event_type():
    """The dashboard JS must filter on the same canonical type string."""
    from pathlib import Path
    html = Path(__file__).resolve().parents[1] / "dashboard" / "static" / "index.html"
    text = html.read_text(encoding="utf-8")
    # Must appear in EVENT_FOREGROUND_TYPES (the listener that triggers
    # autoForeground), not just in the CSS class list.
    assert "EVENT_FOREGROUND_TYPES" in text
    # Locate the EVENT_FOREGROUND_TYPES Set and check it contains the
    # canonical type.
    idx = text.find("EVENT_FOREGROUND_TYPES")
    block = text[idx:idx + 400]
    assert NEGATIVE_REGRESSION_TYPE in block, (
        f"EVENT_FOREGROUND_TYPES must include {NEGATIVE_REGRESSION_TYPE!r} "
        "or auto-foreground will not fire on negative cell regressions."
    )


def test_bus_event_persisted_with_correct_type_and_direction(tmp_path):
    """Emit a governance_negative_regression bus message via the message
    bus and verify it is stored with direction='internal' (so the
    server's SSE forwarder picks it up — see dashboard/server.py: the
    /events tail SQL includes only direction != 'inbound')."""
    db = tmp_path / "gov.db"
    from stream_manager.message_bus import Message, MessageBus
    bus = MessageBus(str(db))
    bus.open_session("s-test")
    bus.publish(
        Message.new(
            session_id="s-test",
            type=NEGATIVE_REGRESSION_TYPE,
            direction="internal",
            content="cell A0 -> A-1 (drop)",
            metadata={"cell": "A0", "from": 0, "to": -1},
        )
    )

    import sqlite3
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT type, direction, content, metadata FROM messages "
        "WHERE type=?",
        (NEGATIVE_REGRESSION_TYPE,),
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    typ, direction, content, metadata = rows[0]
    assert typ == NEGATIVE_REGRESSION_TYPE
    # The /events handler skips direction='inbound'; internal is required
    # so the dashboard sees this event and the JS can autoForeground.
    assert direction == "internal"
    assert "cell A0" in content
    meta = json.loads(metadata)
    assert meta.get("cell") == "A0"


def test_sse_forwarder_matches_internal_direction(tmp_path, monkeypatch):
    """Verify the dashboard /events tail SQL forwards internal-direction
    bus events (the FR-UI-3 path). We don't iterate the SSE stream — that
    would hang the test — but we do confirm the server module exposes a
    handler that the static tests above pin the contract for."""
    db = tmp_path / "gov.db"
    monkeypatch.setenv("GOV_DB", str(db))

    import importlib
    import sys
    if "dashboard.server" in sys.modules:
        del sys.modules["dashboard.server"]
    server = importlib.import_module("dashboard.server")

    # The SSE generator filter must skip 'inbound' rows — this guards
    # against a regression where the event is emitted with the wrong
    # direction and gets duplicated into the decisions feed instead.
    import inspect
    src = inspect.getsource(server.sse_events)
    assert "direction != 'inbound'" in src, (
        "SSE forwarder must filter on direction != 'inbound' so internal "
        "bus events like governance_negative_regression are forwarded."
    )
