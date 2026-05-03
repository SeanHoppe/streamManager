"""Tests for tools.sm_cli (Task B v1.2 — session selector CLI)."""

from __future__ import annotations

import io
import json
import threading
import time

import pytest

from stream_manager.message_bus import Message, MessageBus
from tools import sm_cli


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_bus(tmp_path, sessions: list[tuple[str, int]]) -> MessageBus:
    """Open a MessageBus at tmp_path/gov.db and seed sessions+messages.

    ``sessions`` is a list of (session_id, message_count) pairs. Messages
    are inserted in deterministic order so last_msg_ts is reproducible.
    """
    bus = MessageBus(str(tmp_path / "gov.db"))
    for sid, count in sessions:
        bus.open_session(sid, project_slug=f"proj-{sid}", pid=1234)
        for i in range(count):
            bus.publish(
                Message.new(
                    session_id=sid,
                    type="chat",
                    direction="inbound",
                    content=f"msg-{sid}-{i}",
                )
            )
            # Stagger timestamps so MAX(timestamp) ordering is meaningful.
            # 20ms exceeds Windows clock resolution (~15ms) so consecutive
            # inserts always land on distinct ticks.
            time.sleep(0.02)
    return bus


# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------


def test_list_sessions_returns_rows_with_last_msg_ts(tmp_path):
    bus = _seed_bus(tmp_path, [("alpha", 2), ("beta", 0)])
    try:
        rows = sm_cli.list_sessions(tmp_path / "gov.db")
        assert {r["session_id"] for r in rows} == {"alpha", "beta"}
        by_id = {r["session_id"]: r for r in rows}
        # alpha has messages → last_msg_ts is a float.
        assert isinstance(by_id["alpha"]["last_msg_ts"], float)
        # beta has none → None.
        assert by_id["beta"]["last_msg_ts"] is None
        # Both sessions are open (no ended_at) → active fallback path.
        assert by_id["alpha"]["active"] is True
        assert by_id["beta"]["active"] is True
        assert by_id["alpha"]["_active_source"] == "ended_at"
    finally:
        bus.close()


def test_list_sessions_marks_closed_session_inactive(tmp_path):
    bus = _seed_bus(tmp_path, [("gamma", 1)])
    try:
        bus.close_session("gamma")
        rows = sm_cli.list_sessions(tmp_path / "gov.db")
        assert len(rows) == 1
        assert rows[0]["session_id"] == "gamma"
        assert rows[0]["active"] is False
    finally:
        bus.close()


def test_list_sessions_missing_db_returns_empty(tmp_path):
    rows = sm_cli.list_sessions(tmp_path / "does-not-exist.db")
    assert rows == []


def test_list_sessions_uses_registry_when_dashboard_url_set(
    tmp_path, monkeypatch
):
    bus = _seed_bus(tmp_path, [("alpha", 1), ("beta", 1)])
    try:
        # Both sessions are open in the DB. Without a registry, both would
        # be active. With the registry returning only alpha, beta must
        # flip to inactive.
        def fake_fetch(url):
            assert url == "http://example/"
            return {"alpha"}

        monkeypatch.setattr(sm_cli, "_fetch_active_session_ids", fake_fetch)
        rows = sm_cli.list_sessions(
            tmp_path / "gov.db", dashboard_url="http://example/"
        )
        by_id = {r["session_id"]: r for r in rows}
        assert by_id["alpha"]["active"] is True
        assert by_id["beta"]["active"] is False
        assert by_id["alpha"]["_active_source"] == "registry"
    finally:
        bus.close()


# ---------------------------------------------------------------------------
# render_sessions_table
# ---------------------------------------------------------------------------


def test_render_sessions_table_includes_headers_and_rows(tmp_path):
    bus = _seed_bus(tmp_path, [("zeta", 1)])
    try:
        rows = sm_cli.list_sessions(tmp_path / "gov.db")
        text = sm_cli.render_sessions_table(rows)
        assert "session_id" in text
        assert "started_at" in text
        assert "last_msg_ts" in text
        assert "active" in text
        assert "zeta" in text
        assert "yes" in text  # active
    finally:
        bus.close()


def test_render_sessions_table_handles_empty():
    text = sm_cli.render_sessions_table([])
    assert "no sessions" in text


# ---------------------------------------------------------------------------
# tail_session
# ---------------------------------------------------------------------------


def test_tail_session_yields_existing_envelopes(tmp_path):
    bus = _seed_bus(tmp_path, [("tailme", 3)])
    try:
        out = io.StringIO()
        n = sm_cli.tail_session(
            tmp_path / "gov.db",
            "tailme",
            poll_ms=10,
            out=out,
            stop_after=3,
        )
        assert n == 3
        lines = [
            json.loads(line) for line in out.getvalue().splitlines() if line
        ]
        assert len(lines) == 3
        assert all(line["session_id"] == "tailme" for line in lines)
        # Sequence numbers are 1..3 in order.
        assert [line["sequence"] for line in lines] == [1, 2, 3]
        # context/metadata get parsed from JSON-string back into objects.
        assert isinstance(lines[0]["metadata"], dict)
    finally:
        bus.close()


def test_tail_session_picks_up_envelopes_published_after_start(tmp_path):
    bus = _seed_bus(tmp_path, [("late", 1)])
    try:
        out = io.StringIO()

        # Run tail in a background thread; publish 2 more envelopes after
        # a tiny sleep so the WalReader picks them up live.
        def run_tail():
            sm_cli.tail_session(
                tmp_path / "gov.db",
                "late",
                poll_ms=20,
                out=out,
                stop_after=3,
            )

        t = threading.Thread(target=run_tail, daemon=True)
        t.start()
        # Give the reader a tick to drain the existing row.
        time.sleep(0.1)
        bus.publish(
            Message.new(
                session_id="late", type="chat", direction="inbound",
                content="live-1",
            )
        )
        bus.publish(
            Message.new(
                session_id="late", type="chat", direction="inbound",
                content="live-2",
            )
        )
        t.join(timeout=5.0)
        assert not t.is_alive(), "tail_session did not exit after stop_after"

        lines = [
            json.loads(line) for line in out.getvalue().splitlines() if line
        ]
        assert len(lines) == 3
        contents = [line["content"] for line in lines]
        assert contents[0].startswith("msg-late-")
        assert "live-1" in contents
        assert "live-2" in contents
    finally:
        bus.close()


# ---------------------------------------------------------------------------
# main / argparse
# ---------------------------------------------------------------------------


def test_main_sessions_list_json(tmp_path, capsys):
    bus = _seed_bus(tmp_path, [("argp", 1)])
    try:
        rc = sm_cli.main(
            ["--db", str(tmp_path / "gov.db"), "sessions", "list", "--json"]
        )
        assert rc == 0
        captured = capsys.readouterr()
        lines = [
            json.loads(line) for line in captured.out.splitlines() if line
        ]
        assert len(lines) == 1
        row = lines[0]
        assert row["session_id"] == "argp"
        assert "active" in row
        # Private bookkeeping field must not leak to JSON output.
        assert "_active_source" not in row
    finally:
        bus.close()


def test_main_sessions_list_table(tmp_path, capsys):
    bus = _seed_bus(tmp_path, [("tbl", 1)])
    try:
        rc = sm_cli.main(
            ["--db", str(tmp_path / "gov.db"), "sessions", "list"]
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "tbl" in out
        assert "session_id" in out
    finally:
        bus.close()


def test_main_sessions_tail_missing_db_returns_2(tmp_path, capsys):
    # No DB created.
    rc = sm_cli.main(
        [
            "--db",
            str(tmp_path / "missing.db"),
            "sessions",
            "tail",
            "anything",
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "db not found" in err


def test_main_requires_subcommand(capsys):
    with pytest.raises(SystemExit):
        sm_cli.main([])
