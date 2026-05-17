"""v2.3 P1 Seed 6 — JsonlTailWorker production wiring regression test.

Asserts that ``dashboard.server`` starts a ``JsonlTailWorker`` at
FastAPI startup and stops it at shutdown. Locks the lever wire
(``WIRED_LEVER_LEDGER_COUNT`` 0 → 1 at v2.3 ship-gate).
"""

from __future__ import annotations

import importlib
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def reloaded_server(tmp_path, monkeypatch):
    """Reload ``dashboard.server`` with a tmp gov.db and tmp projects_dir."""
    db = tmp_path / "gov.db"
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    monkeypatch.setenv("GOV_DB", str(db))
    monkeypatch.setenv("BRIDGE_PROJECTS_DIR", str(projects_dir))
    monkeypatch.setenv("BRIDGE_PROJECT_SLUG", "test-slug")
    monkeypatch.setenv("SM_OWN_SESSION_ID", "test-own-session")
    if "dashboard.server" in sys.modules:
        del sys.modules["dashboard.server"]
    if "stream_manager.desktop_commands" in sys.modules:
        del sys.modules["stream_manager.desktop_commands"]
    importlib.import_module("stream_manager.desktop_commands")
    server = importlib.import_module("dashboard.server")
    return server


def test_jsonl_tail_worker_started_at_startup(reloaded_server):
    """JsonlTailWorker active after FastAPI startup."""
    from stream_manager.jsonl_tail import get_active_worker

    assert get_active_worker() is None  # pre-startup

    with TestClient(reloaded_server.app):
        worker = get_active_worker()
        assert worker is not None, (
            "JsonlTailWorker not registered after dashboard startup. "
            "Check dashboard/server.py @app.on_event('startup') wiring."
        )
        assert worker._thread is not None and worker._thread.is_alive(), (
            "JsonlTailWorker thread not alive after start()."
        )


def test_jsonl_tail_worker_stopped_at_shutdown(reloaded_server):
    """JsonlTailWorker cleared from active registry after shutdown."""
    from stream_manager.jsonl_tail import get_active_worker

    with TestClient(reloaded_server.app):
        assert get_active_worker() is not None

    # Post-shutdown: worker cleared via set_active_worker(None) in stop().
    assert get_active_worker() is None, (
        "JsonlTailWorker still registered after dashboard shutdown. "
        "Check @app.on_event('shutdown') wiring + worker.stop() call."
    )
