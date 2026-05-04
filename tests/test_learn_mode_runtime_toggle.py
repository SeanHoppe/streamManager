"""v1.4 — Learn Mode runtime slide-toggle.

Tests the runtime enable flag added in this cycle:

  1. ``get_runtime_enabled`` falls back to env var when no row exists.
  2. ``set_runtime_enabled`` writes to ``learn_categorizer_state`` and
     a subsequent ``get_runtime_enabled`` reads it back.
  3. ``LearnCategorizerWorker.tick()`` short-circuits to 0 when the
     runtime flag is False, even if pairs are queued.
  4. ``LearnCategorizerWorker.tick()`` resumes work when the runtime
     flag flips back to True.
  5. Dashboard ``GET /api/learn-mode/state`` returns the current flag.
  6. Dashboard ``POST /api/learn-mode/state`` flips the flag and
     persists.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from stream_manager import message_bus as _msg_bus  # noqa: E402
from stream_manager.learn_categorizer import (  # noqa: E402
    LearnCategorizerWorker,
    RUNTIME_ENABLED_KEY,
    get_runtime_enabled,
    set_runtime_enabled,
)


@pytest.fixture
def fresh_bus(tmp_path, monkeypatch):
    # Default: env unset so the env-fallback in get_runtime_enabled
    # returns False unless the test sets the flag.
    monkeypatch.delenv("SM_LEARN_MODE", raising=False)
    db = tmp_path / "lm_toggle.db"
    bus = _msg_bus.MessageBus(str(db))
    bus.open_session("toggle-test", project_slug="test", pid=0)
    try:
        yield bus
    finally:
        bus.close_session("toggle-test")
        bus.close()


def test_get_runtime_enabled_falls_back_to_env_when_no_row(fresh_bus, monkeypatch):
    # Env unset → False.
    assert get_runtime_enabled(fresh_bus) is False
    # Env set → True via the existing ``is_enabled()`` boot gate.
    monkeypatch.setenv("SM_LEARN_MODE", "1")
    assert get_runtime_enabled(fresh_bus) is True


def test_set_runtime_enabled_persists_and_reads_back(fresh_bus):
    set_runtime_enabled(fresh_bus, True)
    assert get_runtime_enabled(fresh_bus) is True
    set_runtime_enabled(fresh_bus, False)
    assert get_runtime_enabled(fresh_bus) is False


def test_set_runtime_enabled_overrides_env_var(fresh_bus, monkeypatch):
    """Once the runtime flag is written, it takes precedence over the
    env var. (This matches the design: env is the BOOT gate; the
    runtime flag is what the worker consults each tick.)"""
    monkeypatch.setenv("SM_LEARN_MODE", "1")
    set_runtime_enabled(fresh_bus, False)
    assert get_runtime_enabled(fresh_bus) is False
    monkeypatch.delenv("SM_LEARN_MODE")
    set_runtime_enabled(fresh_bus, True)
    assert get_runtime_enabled(fresh_bus) is True


def _publish_pair(bus, prompt_text="prompt?", reply_text="reply"):
    """Helper: publish one paired desktop_prompt + user_reply."""
    p = _msg_bus.Message.new(
        session_id="toggle-test",
        type="desktop_prompt",
        direction="inbound",
        content=prompt_text,
        metadata={"uuid": "p1", "synthetic": True},
    )
    bus.publish(p)
    u = _msg_bus.Message.new(
        session_id="toggle-test",
        type="user_reply",
        direction="inbound",
        content=reply_text,
        metadata={"pair_id": p.id, "uuid": "u1", "synthetic": True},
    )
    bus.publish(u)


def _category_runner(category="approve", confidence=0.85):
    """Mock a `subprocess.run` call returning a Sonnet envelope."""
    inner = json.dumps({"category": category, "confidence": confidence,
                        "reasoning": "test"})
    envelope = json.dumps({"is_error": False, "result": inner})

    class _Result:
        def __init__(self):
            self.stdout = envelope
            self.returncode = 0

    def _run(cmd, **kwargs):
        return _Result()

    return _run


def test_tick_short_circuits_when_runtime_explicitly_disabled(fresh_bus):
    """A pair queued in the bus is NOT categorized while the runtime
    flag is explicitly set to disabled. tick() returns 0 immediately.

    Backward-compat note: the worker's hot-path gate uses
    ``get_runtime_explicit_disable`` which only returns True when the
    row is present AND value=='0'. Pre-v1.4 deployments without a
    written toggle keep the v1.3 behaviour (worker drains).
    """
    set_runtime_enabled(fresh_bus, False)  # writes "0" to the row
    _publish_pair(fresh_bus)
    worker = LearnCategorizerWorker(fresh_bus, runner=_category_runner())
    n = worker.tick()
    assert n == 0
    rows = fresh_bus.fetch_rows("SELECT COUNT(*) FROM learn_patterns")
    assert int(rows[0][0]) == 0


def test_tick_resumes_when_runtime_re_enabled(fresh_bus):
    """Flipping the flag back to True allows the worker to drain the
    queued pair on the next tick."""
    set_runtime_enabled(fresh_bus, False)
    _publish_pair(fresh_bus)
    worker = LearnCategorizerWorker(fresh_bus, runner=_category_runner())
    assert worker.tick() == 0
    set_runtime_enabled(fresh_bus, True)
    n = worker.tick()
    assert n == 1
    rows = fresh_bus.fetch_rows("SELECT COUNT(*) FROM learn_patterns")
    assert int(rows[0][0]) == 1


def test_tick_drains_when_no_toggle_row_exists(fresh_bus, monkeypatch):
    """v1.3 backward-compat: with no toggle row written, the worker
    must drain pairs (matches pre-v1.4 behaviour). The boot env gate
    is set so the worker would have started in production.
    """
    monkeypatch.setenv("SM_LEARN_MODE", "1")
    _publish_pair(fresh_bus)
    worker = LearnCategorizerWorker(fresh_bus, runner=_category_runner())
    n = worker.tick()
    assert n == 1


def test_runtime_state_table_uses_dedicated_key(fresh_bus):
    """Sanity: the toggle row lands at the expected key, not colliding
    with the existing ``last_id_seen`` ledger key."""
    set_runtime_enabled(fresh_bus, True)
    rows = fresh_bus.fetch_rows(
        "SELECT key, value FROM learn_categorizer_state ORDER BY key"
    )
    keys = {r[0]: r[1] for r in rows}
    assert RUNTIME_ENABLED_KEY in keys
    assert keys[RUNTIME_ENABLED_KEY] == "1"
    # last_id_seen is written lazily by the worker on first advance,
    # so it may or may not be present at this point. Don't assert on it.


# ── dashboard endpoint tests ─────────────────────────────────────────


@pytest.fixture
def dashboard_client(tmp_path, monkeypatch):
    """Build a TestClient backed by a fresh on-disk gov.db so the
    server's ``_get_bus`` finds a usable instance.

    The dashboard module reads ``GOV_DB`` at import time, so we point
    it at the temp path BEFORE importing.
    """
    monkeypatch.delenv("SM_LEARN_MODE", raising=False)
    db = tmp_path / "dash_lm.db"
    monkeypatch.setenv("GOV_DB", str(db))
    # Pre-create the schema so the ``learn_categorizer_state`` table
    # exists when the endpoint touches it.
    bus = _msg_bus.MessageBus(str(db))
    bus.open_session("dash-test", project_slug="test", pid=0)
    bus.close_session("dash-test")
    bus.close()

    # Force a fresh dashboard module import so DB_PATH and the lazy
    # `_bus` global are bound to the temp DB.
    for mod in [k for k in list(sys.modules) if k.startswith("dashboard")]:
        del sys.modules[mod]
    from dashboard import server as dashboard_server  # noqa: WPS433

    from fastapi.testclient import TestClient
    return TestClient(dashboard_server.app)


def test_endpoint_get_returns_default_state(dashboard_client):
    r = dashboard_client.get("/api/learn-mode/state")
    assert r.status_code == 200
    j = r.json()
    assert j["bus_available"] is True
    # Env unset → env_enabled False; no row → runtime_enabled echoes env.
    assert j["env_enabled"] is False
    assert j["runtime_enabled"] is False


def test_endpoint_post_flips_state(dashboard_client):
    r = dashboard_client.post(
        "/api/learn-mode/state", json={"enabled": True}
    )
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["runtime_enabled"] is True

    g = dashboard_client.get("/api/learn-mode/state")
    assert g.json()["runtime_enabled"] is True

    r2 = dashboard_client.post(
        "/api/learn-mode/state", json={"enabled": False}
    )
    assert r2.json()["runtime_enabled"] is False


def test_endpoint_post_rejects_non_boolean(dashboard_client):
    r = dashboard_client.post(
        "/api/learn-mode/state", json={"enabled": "yes"}
    )
    assert r.status_code == 400


def test_endpoint_post_rejects_missing_body(dashboard_client):
    r = dashboard_client.post(
        "/api/learn-mode/state", json={}
    )
    assert r.status_code == 400
