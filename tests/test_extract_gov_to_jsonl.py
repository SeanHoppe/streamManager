"""Tests for tools/extract_gov_to_jsonl.py (PR #156 review fixes).

Covers:
  1. empty exclude_slugs raises
  2. SM-slug rows excluded
  3. SM session_id excluded
  4. --since-hours window filter
  5. mode=ro prevents write
  6. summary counts no double-count
  7. envelope shape (no action_taken)
  8. timestamp type assertion under TEXT column
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest

from tools.extract_gov_to_jsonl import _cli, extract


def _make_gov_db(path, rows, *, ts_type="REAL"):
    """rows: list of dicts with keys session_id, project_slug, decision_id,
    verdict, confidence, timestamp, content."""
    conn = sqlite3.connect(str(path))
    conn.executescript(f"""
        CREATE TABLE sessions (id INTEGER PRIMARY KEY, project_slug TEXT);
        CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id INTEGER, content TEXT);
        CREATE TABLE decisions (
            id INTEGER PRIMARY KEY,
            message_id INTEGER,
            action TEXT,
            confidence REAL,
            layer TEXT,
            model_used TEXT,
            timestamp {ts_type}
        );
    """)
    seen_sessions = set()
    for i, r in enumerate(rows):
        if r["session_id"] not in seen_sessions:
            conn.execute(
                "INSERT INTO sessions (id, project_slug) VALUES (?, ?)",
                (r["session_id"], r["project_slug"]),
            )
            seen_sessions.add(r["session_id"])
        msg_id = i + 1
        conn.execute(
            "INSERT INTO messages (id, session_id, content) VALUES (?, ?, ?)",
            (msg_id, r["session_id"], r.get("content", "x")),
        )
        conn.execute(
            "INSERT INTO decisions (id, message_id, action, confidence, layer, model_used, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                r["decision_id"],
                msg_id,
                r["verdict"],
                r["confidence"],
                "L1",
                "haiku",
                r["timestamp"],
            ),
        )
    conn.commit()
    conn.close()


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_empty_exclude_slugs_raises(tmp_path):
    gov_db = tmp_path / "gov.db"
    _make_gov_db(gov_db, [])
    out = tmp_path / "out.jsonl"
    with pytest.raises(ValueError):
        extract(
            gov_db,
            out,
            exclude_slugs=[],
            exclude_session_id=None,
            since_epoch=None,
        )


def test_sm_slug_rows_excluded(tmp_path):
    gov_db = tmp_path / "gov.db"
    now = time.time()
    rows = [
        {"session_id": 1, "project_slug": "streamManager", "decision_id": 101,
         "verdict": "ALLOW", "confidence": 0.9, "timestamp": now},
        {"session_id": 2, "project_slug": "streamManager", "decision_id": 102,
         "verdict": "ALLOW", "confidence": 0.8, "timestamp": now},
        {"session_id": 3, "project_slug": "other", "decision_id": 103,
         "verdict": "ALLOW", "confidence": 0.7, "timestamp": now},
        {"session_id": 4, "project_slug": "other", "decision_id": 104,
         "verdict": "BLOCK", "confidence": 0.6, "timestamp": now},
        {"session_id": 5, "project_slug": "other", "decision_id": 105,
         "verdict": "ALLOW", "confidence": 0.5, "timestamp": now},
    ]
    _make_gov_db(gov_db, rows)
    out = tmp_path / "out.jsonl"
    summary = extract(
        gov_db,
        out,
        exclude_slugs=["streamManager"],
        exclude_session_id=None,
        since_epoch=None,
    )
    lines = _read_jsonl(out)
    assert len(lines) == 3
    assert summary["extracted"] == 3
    assert summary["excluded_by_slug"] == 2


def test_sm_session_id_excluded(tmp_path, monkeypatch):
    gov_db = tmp_path / "gov.db"
    now = time.time()
    rows = [
        {"session_id": 42, "project_slug": "other", "decision_id": 201,
         "verdict": "ALLOW", "confidence": 0.9, "timestamp": now},
        {"session_id": 7, "project_slug": "other", "decision_id": 202,
         "verdict": "ALLOW", "confidence": 0.8, "timestamp": now},
        {"session_id": 8, "project_slug": "other", "decision_id": 203,
         "verdict": "ALLOW", "confidence": 0.7, "timestamp": now},
    ]
    _make_gov_db(gov_db, rows)
    out = tmp_path / "out.jsonl"
    summary = extract(
        gov_db,
        out,
        exclude_slugs=["streamManager"],
        exclude_session_id="42",
        since_epoch=None,
    )
    lines = _read_jsonl(out)
    session_ids = {ln["session_id"] for ln in lines}
    assert 42 not in session_ids
    assert session_ids == {7, 8}
    assert summary["excluded_by_session"] == 1


def test_since_hours_window(tmp_path):
    gov_db = tmp_path / "gov.db"
    now = time.time()
    rows = [
        {"session_id": 1, "project_slug": "other", "decision_id": 301,
         "verdict": "ALLOW", "confidence": 0.9, "timestamp": now - 3600},
        {"session_id": 1, "project_slug": "other", "decision_id": 302,
         "verdict": "ALLOW", "confidence": 0.8, "timestamp": now - 7201},
        {"session_id": 1, "project_slug": "other", "decision_id": 303,
         "verdict": "ALLOW", "confidence": 0.7, "timestamp": now - 86400},
    ]
    _make_gov_db(gov_db, rows)
    out = tmp_path / "out.jsonl"
    since_epoch = now - (2 * 3600.0)
    summary = extract(
        gov_db,
        out,
        exclude_slugs=["streamManager"],
        exclude_session_id=None,
        since_epoch=since_epoch,
    )
    lines = _read_jsonl(out)
    assert len(lines) == 1
    assert lines[0]["trace_id"] == 301
    assert summary["extracted"] == 1


def test_mode_ro_prevents_write(tmp_path):
    gov_db = tmp_path / "gov.db"
    now = time.time()
    rows = [
        {"session_id": 1, "project_slug": "other", "decision_id": 401,
         "verdict": "ALLOW", "confidence": 0.9, "timestamp": now},
    ]
    _make_gov_db(gov_db, rows)
    out = tmp_path / "out.jsonl"
    extract(
        gov_db,
        out,
        exclude_slugs=["streamManager"],
        exclude_session_id=None,
        since_epoch=None,
    )
    # Verify that opening read-only and trying to UPDATE fails.
    ro_conn = sqlite3.connect(f"file:{gov_db}?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        ro_conn.execute("UPDATE decisions SET confidence = 0.0 WHERE id = 401")
    ro_conn.close()

    # Also assert the extractor source contains the mode=ro URI literal.
    # Anchor to repo root so the test works under any pytest cwd.
    src_path = Path(__file__).resolve().parents[1] / "tools" / "extract_gov_to_jsonl.py"
    src = src_path.read_text(encoding="utf-8")
    assert "mode=ro" in src


def test_summary_counts_no_double_count(tmp_path):
    gov_db = tmp_path / "gov.db"
    now = time.time()
    # session_id=42 has project_slug=streamManager → matches BOTH excluded
    # slug AND excluded session.
    rows = [
        {"session_id": 42, "project_slug": "streamManager", "decision_id": 501,
         "verdict": "ALLOW", "confidence": 0.9, "timestamp": now},
        {"session_id": 9, "project_slug": "other", "decision_id": 502,
         "verdict": "ALLOW", "confidence": 0.8, "timestamp": now},
    ]
    _make_gov_db(gov_db, rows)
    out = tmp_path / "out.jsonl"
    summary = extract(
        gov_db,
        out,
        exclude_slugs=["streamManager"],
        exclude_session_id="42",
        since_epoch=None,
    )
    assert summary["extracted"] == 1
    assert summary["excluded_by_slug"] == 1
    # The dual-match row is counted once by slug, NOT again by session.
    assert summary["excluded_by_session"] == 0


def test_envelope_shape(tmp_path):
    gov_db = tmp_path / "gov.db"
    now = time.time()
    rows = [
        {"session_id": 11, "project_slug": "other", "decision_id": 601,
         "verdict": "ALLOW", "confidence": 0.85, "timestamp": now},
    ]
    _make_gov_db(gov_db, rows)
    out = tmp_path / "out.jsonl"
    extract(
        gov_db,
        out,
        exclude_slugs=["streamManager"],
        exclude_session_id=None,
        since_epoch=None,
    )
    lines = _read_jsonl(out)
    assert len(lines) == 1
    env = lines[0]
    assert "action_taken" not in env
    for key in (
        "session_id",
        "trace_id",
        "verdict",
        "project_slug",
        "confidence",
        "action_propensity",
        "latency_ms",
        "state",
    ):
        assert key in env, f"missing key {key!r}"


def test_timestamp_type_assertion(tmp_path):
    gov_db = tmp_path / "gov.db"
    rows = [
        {"session_id": 1, "project_slug": "other", "decision_id": 701,
         "verdict": "ALLOW", "confidence": 0.9, "timestamp": "2026-05-12T00:00:00Z"},
    ]
    _make_gov_db(gov_db, rows, ts_type="TEXT")
    out = tmp_path / "out.jsonl"
    with pytest.raises(ValueError) as excinfo:
        extract(
            gov_db,
            out,
            exclude_slugs=["streamManager"],
            exclude_session_id=None,
            since_epoch=time.time() - 3600.0,
        )
    assert "TEXT" in str(excinfo.value)
