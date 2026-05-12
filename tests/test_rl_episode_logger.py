"""v10 P1 — tests for rl.episode_logger."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from rl.episode_logger import (
    EpisodeLogger,
    SelfMonitorRefusal,
    _ingest_jsonl,
)


def _envelope(
    *,
    session_id: str = "sess-1",
    trace_id: str = "trace-1",
    verdict: str = "ALLOW",
    confidence: float = 0.85,
    fr_og_7_pass: int | None = None,
    hitl_override: int | None = None,
    state: dict | None = None,
) -> dict:
    return {
        "session_id": session_id,
        "trace_id": trace_id,
        "verdict": verdict,
        "confidence": confidence,
        "action_taken": 0.70,
        "action_propensity": 1.0,
        "latency_ms": 1234.5,
        "budget_violation": 0,
        "fr_og_7_pass": fr_og_7_pass,
        "hitl_override": hitl_override,
        "state": state or {
            "content": "ship the feature",
            "latency_ms_last5": [100.0, 110.0, 120.0],
            "session_history_actions": ["ALLOW", "ALLOW"],
            "routing_band": 2,
            "trigger_factor": 0,
            "learn_mode_bias_hint": 0.0,
        },
    }


def test_logger_inserts_one_row_per_envelope(tmp_path: Path) -> None:
    db = tmp_path / "rl_episodes.db"
    with EpisodeLogger(db) as logger:
        for i in range(5):
            logger.record_decision(
                _envelope(trace_id=f"trace-{i}"),
                source="live",
            )
    conn = sqlite3.connect(str(db))
    count = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
    assert count == 5


def test_logger_unique_constraint(tmp_path: Path) -> None:
    db = tmp_path / "rl_episodes.db"
    with EpisodeLogger(db) as logger:
        logger.record_decision(_envelope(), source="live")
        with pytest.raises(sqlite3.IntegrityError):
            logger.record_decision(_envelope(), source="live")


def test_logger_wal_mode(tmp_path: Path) -> None:
    db = tmp_path / "rl_episodes.db"
    with EpisodeLogger(db) as logger:
        assert logger.journal_mode() == "wal"


def test_logger_ingest_cassette_tag(tmp_path: Path) -> None:
    db = tmp_path / "rl_episodes.db"
    cassette = tmp_path / "soak_cassette_20260507T120000Z.jsonl"
    with cassette.open("w", encoding="utf-8") as fh:
        for i in range(3):
            fh.write(json.dumps(_envelope(trace_id=f"trace-{i}")) + "\n")

    inserted = _ingest_jsonl(db, cassette, source="cassette", cycle_tag=None)
    assert inserted == 3

    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT source, cycle_tag FROM episodes WHERE source='cassette'"
    ).fetchall()
    assert len(rows) == 3
    for src, tag in rows:
        assert src == "cassette"
        assert tag == "soak_cassette_20260507T120000Z"


def test_logger_no_self_monitor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "rl_episodes.db"
    monkeypatch.setenv("BRIDGE_SM_SELF_SESSION_ID", "sm-self-session")
    with EpisodeLogger(db) as logger:
        with pytest.raises(SelfMonitorRefusal):
            logger.record_decision(
                _envelope(session_id="sm-self-session"),
                source="live",
            )
    conn = sqlite3.connect(str(db))
    count = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
    assert count == 0


def test_logger_refuses_sm_project_slug_default(tmp_path: Path) -> None:
    """v10 P4 B': polarity-flip slug filter. Default slug set =
    {"streamManager"}; envelope with that slug must refuse, regardless
    of BRIDGE_SM_SELF_SESSION_ID."""
    db = tmp_path / "rl_episodes.db"
    env = _envelope(session_id="other-sess")
    env["project_slug"] = "streamManager"
    with EpisodeLogger(db) as logger:
        with pytest.raises(SelfMonitorRefusal) as exc:
            logger.record_decision(env, source="live")
        assert "project_slug" in str(exc.value)
    conn = sqlite3.connect(str(db))
    count = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
    assert count == 0


def test_logger_allows_non_sm_project_slug(tmp_path: Path) -> None:
    """v10 P4 B': default polarity-flip permits non-SM project slugs."""
    db = tmp_path / "rl_episodes.db"
    env = _envelope()
    env["project_slug"] = "certPortal"
    with EpisodeLogger(db) as logger:
        logger.record_decision(env, source="live")
    conn = sqlite3.connect(str(db))
    count = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
    assert count == 1


def test_logger_slug_set_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BRIDGE_SM_PROJECT_SLUGS env adds worktree-slug variants."""
    db = tmp_path / "rl_episodes.db"
    monkeypatch.setenv(
        "BRIDGE_SM_PROJECT_SLUGS", "streamManager,streamManager-1,sm-dev"
    )
    env = _envelope(session_id="other-sess")
    env["project_slug"] = "sm-dev"
    with EpisodeLogger(db) as logger:
        with pytest.raises(SelfMonitorRefusal):
            logger.record_decision(env, source="live")


def test_logger_fr_og_7_pass_null_on_live(tmp_path: Path) -> None:
    db = tmp_path / "rl_episodes.db"
    with EpisodeLogger(db) as logger:
        # live envelope: no ground-truth signal → NULL
        logger.record_decision(
            _envelope(trace_id="live-1", fr_og_7_pass=None),
            source="live",
        )
        # golden replay where verdict matches → 1
        logger.record_decision(
            _envelope(trace_id="golden-1", fr_og_7_pass=1),
            source="golden",
        )
        # golden replay regression → 0
        logger.record_decision(
            _envelope(trace_id="golden-2", fr_og_7_pass=0),
            source="golden",
        )

    conn = sqlite3.connect(str(db))
    rows = dict(
        conn.execute(
            "SELECT trace_id, fr_og_7_pass FROM episodes ORDER BY trace_id"
        ).fetchall()
    )
    assert rows == {"live-1": None, "golden-1": 1, "golden-2": 0}


def test_logger_state_features_json_round_trips(tmp_path: Path) -> None:
    db = tmp_path / "rl_episodes.db"
    with EpisodeLogger(db) as logger:
        logger.record_decision(_envelope(), source="live")
    conn = sqlite3.connect(str(db))
    raw = conn.execute("SELECT state_features_json FROM episodes").fetchone()[0]
    features = json.loads(raw)
    assert "latency_ms_last5_p95" in features
    assert "session_history_action_share" in features
    assert isinstance(features["session_history_action_share"], list)


def test_logger_rejects_unknown_verdict(tmp_path: Path) -> None:
    db = tmp_path / "rl_episodes.db"
    with EpisodeLogger(db) as logger:
        with pytest.raises(ValueError):
            logger.record_decision(_envelope(verdict="GARBAGE"), source="live")


def test_logger_rejects_unknown_source(tmp_path: Path) -> None:
    db = tmp_path / "rl_episodes.db"
    with EpisodeLogger(db) as logger:
        with pytest.raises(ValueError):
            logger.record_decision(_envelope(), source="unknown")


def test_ingest_skips_malformed_json_lines(tmp_path: Path) -> None:
    db = tmp_path / "rl_episodes.db"
    cassette = tmp_path / "soak_cassette_20260507T120000Z.jsonl"
    with cassette.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(_envelope(trace_id="trace-0")) + "\n")
        fh.write("{ this is not valid json\n")
        fh.write("\n")  # blank line — also skipped
        fh.write(json.dumps(_envelope(trace_id="trace-1")) + "\n")

    inserted = _ingest_jsonl(db, cassette, source="cassette", cycle_tag=None)
    assert inserted == 2

    conn = sqlite3.connect(str(db))
    count = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
    assert count == 2
