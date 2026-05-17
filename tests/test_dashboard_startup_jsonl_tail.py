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


def _reload_server(tmp_path, monkeypatch, project_slug="test-slug"):
    """Reload ``dashboard.server`` + ``jsonl_tail`` with fresh state.

    Reloading ``jsonl_tail`` clears the per-process ``_ACTIVE_WORKER``
    global between tests so ``get_active_worker()`` returns ``None``
    pre-startup in every run.
    """
    db = tmp_path / "gov.db"
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    monkeypatch.setenv("GOV_DB", str(db))
    monkeypatch.setenv("BRIDGE_PROJECTS_DIR", str(projects_dir))
    monkeypatch.setenv("BRIDGE_PROJECT_SLUG", project_slug)
    monkeypatch.setenv("SM_OWN_SESSION_ID", "test-own-session")
    for mod in (
        "dashboard.server",
        "stream_manager.desktop_commands",
        "stream_manager.jsonl_tail",
    ):
        if mod in sys.modules:
            del sys.modules[mod]
    importlib.import_module("stream_manager.desktop_commands")
    importlib.import_module("stream_manager.jsonl_tail")
    return importlib.import_module("dashboard.server")


@pytest.fixture
def reloaded_server(tmp_path, monkeypatch):
    return _reload_server(tmp_path, monkeypatch)


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


def test_polarity_flip_refusal_when_slug_is_sm(tmp_path, monkeypatch):
    """Refuse to start when project_slug is in SM exclusion set.

    Per CLAUDE.md §"Session-source exception rule (polarity-flip)":
    default-exclude SM by project-slug. If operator misconfigures
    BRIDGE_PROJECT_SLUG to streamManager (or a worktree variant), the
    wire-site MUST refuse and log loudly rather than tail SM-self.
    """
    server = _reload_server(tmp_path, monkeypatch, project_slug="streamManager")
    from stream_manager.jsonl_tail import get_active_worker

    with TestClient(server.app):
        assert get_active_worker() is None, (
            "JsonlTailWorker started despite project_slug=streamManager. "
            "Polarity-flip wire-site refusal failed."
        )
