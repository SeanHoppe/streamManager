"""FR-UI-9: tests for the per-session settings persistence endpoint.

Covers:
- POST validates each known field against its FR-UI-9 range.
- POST persists into the sessions.settings JSON blob.
- POST emits a `session_settings_updated` bus event carrying the merged
  blob (not just the patch).
- GET returns the merged settings.
- The migration adds a `settings` column on existing DBs.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "gov.db"
    monkeypatch.setenv("GOV_DB", str(db))

    import importlib
    import sys

    if "dashboard.server" in sys.modules:
        del sys.modules["dashboard.server"]
    server = importlib.import_module("dashboard.server")

    from stream_manager.message_bus import MessageBus
    bus = MessageBus(str(db))
    bus.open_session("s-test")
    server._bus = bus

    return TestClient(server.app), bus


def test_post_persists_settings_to_blob(client):
    c, bus = client
    r = c.post(
        "/api/sessions/s-test/settings",
        json={
            "sync_timeout_sec": 90,
            "activity_window_sec": 15,
            "audible_cue": True,
            "motion": "reduce",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["session_id"] == "s-test"
    s = data["settings"]
    assert s["sync_timeout_sec"] == 90.0
    assert s["activity_window_sec"] == 15.0
    assert s["audible_cue"] is True
    assert s["motion"] == "reduce"

    persisted = bus.get_session_settings("s-test")
    assert persisted == s


def test_post_merges_into_existing_blob(client):
    c, bus = client
    c.post(
        "/api/sessions/s-test/settings",
        json={"audible_cue": True, "motion": "reduce"},
    )
    r = c.post(
        "/api/sessions/s-test/settings",
        json={"motion": "allow"},
    )
    assert r.status_code == 200
    s = r.json()["settings"]
    # Earlier audible_cue must be preserved across the patch.
    assert s["audible_cue"] is True
    assert s["motion"] == "allow"


def test_post_emits_session_settings_updated_event(client):
    c, bus = client
    r = c.post(
        "/api/sessions/s-test/settings",
        json={"sync_timeout_sec": 120},
    )
    assert r.status_code == 200

    import sqlite3
    conn = sqlite3.connect(str(bus.db_path))
    rows = conn.execute(
        "SELECT type, content, metadata FROM messages "
        "WHERE type='session_settings_updated'"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    meta = json.loads(rows[0][2])
    # Server-side bus event must carry the FULL merged settings blob.
    assert "settings" in meta
    assert meta["settings"]["sync_timeout_sec"] == 120.0
    # And echo the patch for audit.
    assert meta["patch"] == {"sync_timeout_sec": 120.0}


def test_get_returns_persisted_settings(client):
    c, _bus = client
    c.post(
        "/api/sessions/s-test/settings",
        json={"motion": "system", "audible_cue": False},
    )
    r = c.get("/api/sessions/s-test/settings")
    assert r.status_code == 200
    data = r.json()
    assert data["session_id"] == "s-test"
    assert data["settings"]["motion"] == "system"
    assert data["settings"]["audible_cue"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {"sync_timeout_sec": 5},          # below 10
        {"sync_timeout_sec": 601},        # above 600
        {"activity_window_sec": 0},       # below 1
        {"activity_window_sec": 1000},    # above 600
        {"confidence_floor": -0.1},       # below 0.0
        {"confidence_floor": 1.1},        # above 1.0
        {"motion": "bogus"},              # not in enum
        {"hitl_mode": "weird"},           # not in enum
        {"audible_cue": "yes"},           # not bool
        {"sync_timeout_sec": "fast"},     # not numeric
    ],
)
def test_post_rejects_invalid_values(client, payload):
    c, _bus = client
    r = c.post("/api/sessions/s-test/settings", json=payload)
    assert r.status_code == 400, r.text


def test_post_rejects_empty_recognised_keys(client):
    c, _bus = client
    r = c.post("/api/sessions/s-test/settings", json={"unknown_key": 1})
    assert r.status_code == 400


def test_migration_adds_settings_column(tmp_path):
    """The settings column must be added by the additive migration even
    when the DB pre-existed without it."""
    import sqlite3

    db = tmp_path / "old.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            project_slug TEXT NOT NULL DEFAULT '',
            pid INTEGER,
            started_at REAL NOT NULL,
            ended_at REAL
        );
        """
    )
    conn.commit()
    conn.close()

    from stream_manager.message_bus import MessageBus
    bus = MessageBus(str(db))
    bus.open_session("s-old")
    bus.set_session_settings("s-old", {"motion": "reduce"})
    assert bus.get_session_settings("s-old") == {"motion": "reduce"}
