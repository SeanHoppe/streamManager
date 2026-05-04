"""Tests for the desktop_command outbound control plane (Task D, v1.0).

Covers:
  - secret auto-generation on first call + 0600 perm (POSIX only)
  - env override beats file
  - sign / validate round-trip
  - kind allowlist rejection (ValueError)
  - SM_OWN_SESSION_ID rejection (ValueError + HTTP 400)
  - dashboard POST /api/commands → row in DB →
    POST /api/commands/{id}/ack updates status
  - emit_command does not touch the messages table (no engine.evaluate
    can fire because no row was published)

v1.2 (Task D long-poll removal): the legacy
``GET /api/commands/pending`` endpoint was removed. Tests previously
covering its read-side TTL expiry and pending-list shape were dropped;
the SSE handler retains the same TTL behaviour and is exercised by
``tests/test_desktop_command_sse.py``.
"""

from __future__ import annotations

import importlib
import os
import sqlite3
import sys
import time

import pytest
from fastapi.testclient import TestClient

from stream_manager.message_bus import MessageBus


# ── Module-level helpers ────────────────────────────────────────────


def _fresh_desktop_commands_module(tmp_path, monkeypatch):
    """Reload the desktop_commands module with SECRET_PATH pinned into tmp."""
    # Force a clean module so SECRET_PATH/ROOT pick up the patched env.
    if "stream_manager.desktop_commands" in sys.modules:
        del sys.modules["stream_manager.desktop_commands"]
    monkeypatch.delenv("SM_DESKTOP_SECRET", raising=False)
    monkeypatch.delenv("SM_OWN_SESSION_ID", raising=False)
    mod = importlib.import_module("stream_manager.desktop_commands")
    monkeypatch.setattr(mod, "SECRET_PATH", tmp_path / ".bridge" / "secret")
    return mod


# ── Secret resolution ───────────────────────────────────────────────


def test_secret_auto_generated_on_first_call(tmp_path, monkeypatch):
    mod = _fresh_desktop_commands_module(tmp_path, monkeypatch)
    assert not mod.SECRET_PATH.exists()
    secret = mod._load_or_gen_secret()
    assert isinstance(secret, bytes)
    assert len(secret) > 0
    assert mod.SECRET_PATH.exists()
    # Second call returns the same value (read from disk).
    again = mod._load_or_gen_secret()
    assert again == secret


@pytest.mark.skipif(os.name == "nt", reason="POSIX-only chmod 0o600 check")
def test_secret_file_has_0600_perm(tmp_path, monkeypatch):
    mod = _fresh_desktop_commands_module(tmp_path, monkeypatch)
    mod._load_or_gen_secret()
    perm = mod.SECRET_PATH.stat().st_mode & 0o777
    assert perm == 0o600


def test_env_override_beats_file(tmp_path, monkeypatch):
    mod = _fresh_desktop_commands_module(tmp_path, monkeypatch)
    # Pre-populate the file with one value.
    mod.SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    mod.SECRET_PATH.write_text("from-disk", encoding="utf-8")
    monkeypatch.setenv("SM_DESKTOP_SECRET", "from-env")
    assert mod._load_or_gen_secret() == b"from-env"


# ── sign / validate ─────────────────────────────────────────────────


def test_sign_validate_round_trip(tmp_path, monkeypatch):
    mod = _fresh_desktop_commands_module(tmp_path, monkeypatch)
    monkeypatch.setenv("SM_DESKTOP_SECRET", "test-secret-123")
    payload = {
        "id": "abc",
        "session_id": "s1",
        "kind": "pause",
        "args": {"reason": "manual"},
        "sent_at": 1714694400.0,
    }
    sig = mod.sign(payload)
    assert isinstance(sig, str)
    assert len(sig) == 64  # sha256 hex
    assert mod.validate(payload, sig) is True
    # Tamper detection.
    assert mod.validate({**payload, "kind": "flash"}, sig) is False
    # Different sig fails.
    assert mod.validate(payload, "0" * 64) is False


def test_sign_with_explicit_secret_kwarg_matches_manual_hmac(tmp_path, monkeypatch):
    """``sign(payload, secret=...)`` must produce the same digest as a manual
    ``hmac.new`` reference using the same canonical-JSON encoding."""
    import hashlib
    import hmac as _hmac

    mod = _fresh_desktop_commands_module(tmp_path, monkeypatch)
    # Pin a different env-resolved secret so we can prove the kwarg wins.
    monkeypatch.setenv("SM_DESKTOP_SECRET", "env-secret-should-be-ignored")
    explicit = b"explicit-kwarg-secret"
    payload = {
        "id": "abc",
        "session_id": "s1",
        "kind": "pause",
        "args": {"reason": "manual"},
        "sent_at": 1714694400.0,
    }
    sig = mod.sign(payload, secret=explicit)
    expected = _hmac.new(
        explicit, mod._canonical_json(payload), hashlib.sha256
    ).hexdigest()
    assert sig == expected
    # Round-trip with the same secret validates.
    assert mod.validate(payload, sig, secret=explicit) is True


def test_validate_with_wrong_explicit_secret_returns_false(tmp_path, monkeypatch):
    """When the kwarg secret is wrong, validate must reject — even if the
    env/file-resolved secret would have matched."""
    mod = _fresh_desktop_commands_module(tmp_path, monkeypatch)
    monkeypatch.setenv("SM_DESKTOP_SECRET", "env-secret-matches")
    payload = {
        "id": "abc",
        "session_id": "s1",
        "kind": "pause",
        "args": {},
        "sent_at": 1.0,
    }
    # Sign with the env-resolved secret (no kwarg).
    sig = mod.sign(payload)
    # Sanity: validating with no kwarg uses the env secret and passes.
    assert mod.validate(payload, sig) is True
    # But supplying a different explicit secret must reject.
    assert mod.validate(payload, sig, secret=b"some-other-secret") is False


def test_default_sign_validate_still_uses_load_or_gen(tmp_path, monkeypatch):
    """Default behavior (no ``secret`` kwarg) must still resolve the secret
    via ``_load_or_gen_secret`` (env → file → generate)."""
    mod = _fresh_desktop_commands_module(tmp_path, monkeypatch)
    monkeypatch.setenv("SM_DESKTOP_SECRET", "default-path-secret")
    calls = {"n": 0}
    real_loader = mod._load_or_gen_secret

    def counting_loader():
        calls["n"] += 1
        return real_loader()

    monkeypatch.setattr(mod, "_load_or_gen_secret", counting_loader)
    payload = {
        "id": "abc",
        "session_id": "s1",
        "kind": "pause",
        "args": {},
        "sent_at": 1.0,
    }
    sig = mod.sign(payload)  # no kwarg
    assert mod.validate(payload, sig) is True  # no kwarg
    # sign + validate both went through the loader.
    assert calls["n"] >= 2


def test_sign_is_canonical_json(tmp_path, monkeypatch):
    """Different key ordering must produce the same signature."""
    mod = _fresh_desktop_commands_module(tmp_path, monkeypatch)
    monkeypatch.setenv("SM_DESKTOP_SECRET", "test-secret-123")
    p1 = {"id": "x", "session_id": "s", "kind": "pause", "args": {}, "sent_at": 1.0}
    p2 = {"sent_at": 1.0, "kind": "pause", "args": {}, "id": "x", "session_id": "s"}
    assert mod.sign(p1) == mod.sign(p2)


# ── emit_command ────────────────────────────────────────────────────


def _bus(tmp_path):
    return MessageBus(str(tmp_path / "gov.db"))


def test_emit_command_inserts_pending_row(tmp_path, monkeypatch):
    mod = _fresh_desktop_commands_module(tmp_path, monkeypatch)
    monkeypatch.setenv("SM_DESKTOP_SECRET", "test-secret")
    bus = _bus(tmp_path)
    bus.open_session("s-target")
    cmd_id = mod.emit_command(bus, "s-target", "pause", {"reason": "hitl"})
    assert isinstance(cmd_id, str) and len(cmd_id) > 0

    rows = bus.fetch_rows(
        "SELECT id, session_id, kind, args_json, signature, sent_at, "
        "acked_at, status, error FROM desktop_commands"
    )
    assert len(rows) == 1
    r = rows[0]
    assert r[0] == cmd_id
    assert r[1] == "s-target"
    assert r[2] == "pause"
    assert r[3] == '{"reason":"hitl"}'
    assert r[4]  # signature populated
    assert r[5] > 0  # sent_at
    assert r[6] is None  # acked_at
    assert r[7] == "pending"
    assert r[8] is None  # error
    bus.close()


def test_emit_command_does_not_touch_messages_table(tmp_path, monkeypatch):
    """Desktop commands must NOT flow through bus.publish() — no row in
    messages, no engine.evaluate() fired.
    """
    mod = _fresh_desktop_commands_module(tmp_path, monkeypatch)
    monkeypatch.setenv("SM_DESKTOP_SECRET", "s")
    bus = _bus(tmp_path)
    bus.open_session("s-target")

    spy_calls: list = []

    def spy(_msg) -> None:
        spy_calls.append(_msg)

    bus.subscribe(spy)
    mod.emit_command(bus, "s-target", "flash", {})
    msg_count = bus.fetch_rows(
        "SELECT COUNT(*) FROM messages"
    )[0][0]
    assert msg_count == 0
    assert spy_calls == []
    bus.close()


def test_emit_command_kind_allowlist_rejection(tmp_path, monkeypatch):
    mod = _fresh_desktop_commands_module(tmp_path, monkeypatch)
    monkeypatch.setenv("SM_DESKTOP_SECRET", "s")
    bus = _bus(tmp_path)
    bus.open_session("s-target")
    with pytest.raises(ValueError, match="not in allowlist"):
        mod.emit_command(bus, "s-target", "rm_rf", {})
    bus.close()


def test_emit_command_rejects_sm_own(tmp_path, monkeypatch):
    mod = _fresh_desktop_commands_module(tmp_path, monkeypatch)
    monkeypatch.setenv("SM_DESKTOP_SECRET", "s")
    monkeypatch.setenv("SM_OWN_SESSION_ID", "sm-owner")
    bus = _bus(tmp_path)
    with pytest.raises(ValueError, match="SM_OWN_SESSION_ID"):
        mod.emit_command(bus, "sm-owner", "pause", {})
    bus.close()


def test_emit_command_rejects_empty_session(tmp_path, monkeypatch):
    mod = _fresh_desktop_commands_module(tmp_path, monkeypatch)
    monkeypatch.setenv("SM_DESKTOP_SECRET", "s")
    bus = _bus(tmp_path)
    with pytest.raises(ValueError, match="session_id"):
        mod.emit_command(bus, "", "pause", {})
    bus.close()


# ── Dashboard endpoints ─────────────────────────────────────────────


def _dashboard(tmp_path, monkeypatch, *, sm_own: str | None = None):
    """Reload the dashboard module against a tmp DB and return (TestClient, bus)."""
    db = tmp_path / "gov.db"
    monkeypatch.setenv("GOV_DB", str(db))
    monkeypatch.setenv("SM_DESKTOP_SECRET", "test-secret-dashboard")
    if sm_own is not None:
        monkeypatch.setenv("SM_OWN_SESSION_ID", sm_own)
    else:
        monkeypatch.delenv("SM_OWN_SESSION_ID", raising=False)

    if "stream_manager.desktop_commands" in sys.modules:
        del sys.modules["stream_manager.desktop_commands"]
    if "dashboard.server" in sys.modules:
        del sys.modules["dashboard.server"]
    server = importlib.import_module("dashboard.server")
    # Reload the desktop_commands module so its SECRET_PATH and the env
    # snapshot pick up the patched env.
    importlib.import_module("stream_manager.desktop_commands")

    bus = MessageBus(str(db))
    bus.open_session("s-target")
    server._bus = bus
    return TestClient(server.app), bus


def test_dashboard_emit_then_ack_round_trip(tmp_path, monkeypatch):
    """Round-trip: POST /api/commands → DB row → POST /api/commands/{id}/ack.

    v1.2 (Task D): the GET /api/commands/pending readback step was
    removed along with the endpoint; the row's signed shape is now
    asserted by reading the desktop_commands row directly through the
    bus connection and re-validating. Live SSE delivery is covered by
    tests/test_desktop_command_sse.py.
    """
    client, bus = _dashboard(tmp_path, monkeypatch)
    try:
        # Emit
        resp = client.post(
            "/api/commands",
            json={"session_id": "s-target", "kind": "pause", "args": {"why": "x"}},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        cmd_id = body["id"]
        assert body["status"] == "pending"

        # Read the row directly from the WAL table and verify the
        # signed payload round-trips. This replaces the removed
        # GET /api/commands/pending readback.
        from stream_manager.desktop_commands import validate
        import json as _json
        _rows = bus.fetch_rows(
            "SELECT id, session_id, kind, args_json, signature, sent_at, "
            "status FROM desktop_commands WHERE id=?",
            (cmd_id,),
        )
        row = _rows[0] if _rows else None
        assert row is not None
        assert row[0] == cmd_id
        assert row[1] == "s-target"
        assert row[2] == "pause"
        assert _json.loads(row[3]) == {"why": "x"}
        assert row[4]  # signature non-empty
        assert row[6] == "pending"
        payload = {
            "id": row[0],
            "session_id": row[1],
            "kind": row[2],
            "args": _json.loads(row[3]),
            "sent_at": float(row[5]),
        }
        assert validate(payload, row[4]) is True

        # ACK
        resp = client.post(
            f"/api/commands/{cmd_id}/ack",
            json={"status": "ok"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "ok"

        # Row updated in DB
        _rows = bus.fetch_rows(
            "SELECT status, acked_at, error FROM desktop_commands WHERE id=?",
            (cmd_id,),
        )
        row = _rows[0]
        assert row[0] == "ok"
        assert row[1] is not None
        assert row[2] is None
    finally:
        bus.close()


def test_dashboard_pending_endpoint_returns_404(tmp_path, monkeypatch):
    """v1.2 (Task D) removed the legacy ``GET /api/commands/pending``
    long-poll endpoint. The dashboard must now 404 it; SSE
    (``GET /api/commands/stream``) is the sole desktop_command transport.
    """
    client, bus = _dashboard(tmp_path, monkeypatch)
    try:
        resp = client.get(
            "/api/commands/pending", params={"session_id": "s-target"}
        )
        assert resp.status_code == 404, (
            f"/api/commands/pending should be removed; got {resp.status_code}"
        )
    finally:
        bus.close()


def test_dashboard_rejects_sm_own(tmp_path, monkeypatch):
    client, bus = _dashboard(tmp_path, monkeypatch, sm_own="sm-owner")
    try:
        resp = client.post(
            "/api/commands",
            json={"session_id": "sm-owner", "kind": "pause", "args": {}},
        )
        assert resp.status_code == 400
        assert "SM_OWN_SESSION_ID" in resp.json()["detail"]

        # SM_OWN check on the SSE transport (the v1.2 sole transport).
        # The legacy long-poll endpoint check is gone with the endpoint.
        resp = client.get(
            "/api/commands/stream", params={"session_id": "sm-owner"}
        )
        assert resp.status_code == 400
    finally:
        bus.close()


def test_dashboard_rejects_invalid_kind(tmp_path, monkeypatch):
    client, bus = _dashboard(tmp_path, monkeypatch)
    try:
        resp = client.post(
            "/api/commands",
            json={"session_id": "s-target", "kind": "rm_rf", "args": {}},
        )
        assert resp.status_code == 400
        assert "allowlist" in resp.json()["detail"]
    finally:
        bus.close()


def test_dashboard_ack_invalid_status(tmp_path, monkeypatch):
    client, bus = _dashboard(tmp_path, monkeypatch)
    try:
        resp = client.post(
            "/api/commands",
            json={"session_id": "s-target", "kind": "pause", "args": {}},
        )
        cmd_id = resp.json()["id"]
        resp = client.post(
            f"/api/commands/{cmd_id}/ack", json={"status": "weird"}
        )
        assert resp.status_code == 400
    finally:
        bus.close()


def test_dashboard_ack_unknown_id(tmp_path, monkeypatch):
    client, bus = _dashboard(tmp_path, monkeypatch)
    try:
        resp = client.post(
            "/api/commands/does-not-exist/ack", json={"status": "ok"}
        )
        assert resp.status_code == 404
    finally:
        bus.close()


def test_desktop_commands_table_present_after_bus_init(tmp_path):
    bus = MessageBus(str(tmp_path / "gov.db"))
    try:
        rows = bus.fetch_rows(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='desktop_commands'"
        )
        assert len(rows) == 1
        # Index too.
        rows = bus.fetch_rows(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name='idx_dc_pending'"
        )
        assert len(rows) == 1
    finally:
        bus.close()
