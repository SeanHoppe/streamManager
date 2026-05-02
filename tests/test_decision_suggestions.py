"""FR-UI-5: tests for decision_suggestions ranking + weights validation.

Coverage:
    1. load_weights hard-fails when weights don't sum to 1.0
    2. load_weights hard-fails when a weight is out of [0,1]
    3. load_weights hard-fails when half-life is non-positive
    4. load_weights returns defaults when .sm-context.yaml is absent
    5. recency decay: older overrides score lower than newer ones
    6. fallback engine-proposal candidate is always returned
    7. exact ranking on synthetic input (graph + override + static rule)
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from stream_manager.decision_suggestions import (
    SuggestionWeights,
    Candidate,
    _hitl_override_candidates,
    _recency_weight,
    load_weights,
    rank_candidates,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def db_conn(tmp_path):
    p = tmp_path / "sug.db"
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE messages (
            id TEXT PRIMARY KEY, session_id TEXT, sequence INTEGER,
            type TEXT, direction TEXT, content TEXT, context TEXT,
            metadata TEXT, timestamp REAL
        );
        CREATE TABLE decisions (
            id TEXT PRIMARY KEY, message_id TEXT, action TEXT,
            confidence REAL, reasoning TEXT, matched_hash TEXT,
            timestamp REAL
        );
        CREATE TABLE hitl_overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_id TEXT, original_action TEXT, override_action TEXT,
            note TEXT, mode TEXT, timestamp TEXT
        );
        CREATE TABLE graph_patterns (
            hash TEXT PRIMARY KEY, level INTEGER, vector TEXT,
            canonical_text TEXT, occurrences INTEGER, successes INTEGER,
            last_seen REAL, children TEXT
        );
    """)
    conn.commit()
    yield conn
    conn.close()


def _seed_decision(
    conn, decision_id="d1", matched_hash="h1", content="hello", action="ALLOW"
):
    conn.execute(
        "INSERT INTO messages (id,session_id,sequence,type,direction,"
        "content,context,metadata,timestamp) "
        "VALUES (?, ?, 1, 't', 'inbound', ?, '{}', '{}', 0)",
        (f"m-{decision_id}", "s1", content),
    )
    conn.execute(
        "INSERT INTO decisions (id,message_id,action,confidence,reasoning,"
        "matched_hash,timestamp) VALUES (?, ?, ?, 0.5, '', ?, 0)",
        (decision_id, f"m-{decision_id}", action, matched_hash),
    )
    conn.commit()


def _add_override(conn, decision_id, override_action, days_ago=0):
    ts = (
        datetime.now(timezone.utc) - timedelta(days=days_ago)
    ).isoformat()
    conn.execute(
        "INSERT INTO hitl_overrides (decision_id, original_action, "
        "override_action, note, mode, timestamp) VALUES (?, ?, ?, NULL, "
        "'async', ?)",
        (decision_id, "ALLOW", override_action, ts),
    )
    conn.commit()


# ── Weights validation ────────────────────────────────────────────────


def test_load_weights_hard_fail_sum_mismatch(tmp_path):
    p = tmp_path / ".sm-context.yaml"
    p.write_text(
        "decision_suggestion_weights:\n"
        "  graph_match: 0.5\n"
        "  hitl_override: 0.5\n"
        "  static_rule: 0.5\n"
        "  project_context: 0.5\n"
        "  recency_half_life_days: 14\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="sum to 1.0"):
        load_weights(p)


def test_load_weights_hard_fail_out_of_range(tmp_path):
    p = tmp_path / ".sm-context.yaml"
    p.write_text(
        "decision_suggestion_weights:\n"
        "  graph_match: 1.5\n"
        "  hitl_override: -0.5\n"
        "  static_rule: 0.0\n"
        "  project_context: 0.0\n"
        "  recency_half_life_days: 14\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="out of range"):
        load_weights(p)


def test_load_weights_hard_fail_negative_half_life(tmp_path):
    p = tmp_path / ".sm-context.yaml"
    p.write_text(
        "decision_suggestion_weights:\n"
        "  graph_match: 0.40\n"
        "  hitl_override: 0.35\n"
        "  static_rule: 0.15\n"
        "  project_context: 0.10\n"
        "  recency_half_life_days: -1\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="recency_half_life_days"):
        load_weights(p)


def test_load_weights_defaults_when_missing(tmp_path):
    w = load_weights(tmp_path / "nonexistent.yaml")
    assert isinstance(w, SuggestionWeights)
    assert abs(
        w.graph_match + w.hitl_override + w.static_rule + w.project_context
        - 1.0
    ) < 0.001


# ── Recency decay ─────────────────────────────────────────────────────


def test_recency_weight_decays():
    # half_life = 14d → at 14d age the weight should be ≈ 0.5.
    fresh = _recency_weight(0.0, 14.0)
    half = _recency_weight(14.0, 14.0)
    old = _recency_weight(28.0, 14.0)
    assert fresh > half > old
    assert abs(half - 0.5) < 0.01


def test_hitl_override_recency_orders_candidates(db_conn):
    _seed_decision(db_conn, decision_id="d1", matched_hash="h1")
    _seed_decision(db_conn, decision_id="d2", matched_hash="h1")
    # Newer override → BLOCK; older override → GUIDE
    _add_override(db_conn, "d1", "BLOCK", days_ago=1)
    _add_override(db_conn, "d2", "GUIDE", days_ago=60)
    weights = SuggestionWeights()
    cands = _hitl_override_candidates(db_conn, "h1", weights)
    by_action = {c.action: c for c in cands}
    assert by_action["BLOCK"].score > by_action["GUIDE"].score


# ── Fallback / ranking ────────────────────────────────────────────────


def test_fallback_returned_when_no_source(db_conn):
    # Empty content hits no static rule, no graph match (empty patterns
    # table), no project_context precheck (only fires on non-empty
    # stripped content), and no overrides → engine fallback path runs.
    _seed_decision(db_conn, decision_id="d1", matched_hash="", content="")
    weights = SuggestionWeights()
    row = {
        "id": "d1",
        "action": "ALLOW",
        "confidence": 0.42,
        "matched_hash": "",
        "content": "",
    }
    cands = rank_candidates(row, db_conn, weights)
    assert len(cands) >= 1
    assert cands[0].action == "ALLOW"
    assert "graph_pattern" in cands[0].sourced_from


def test_static_rule_outranks_default_on_destructive(db_conn):
    content = "rm -rf / && mkfs.ext4 /dev/sda1"
    _seed_decision(db_conn, decision_id="d1", matched_hash="", content=content)
    weights = SuggestionWeights()
    row = {
        "id": "d1",
        "action": "ALLOW",
        "confidence": 0.1,
        "matched_hash": "",
        "content": content,
    }
    cands = rank_candidates(row, db_conn, weights)
    # The top candidate should come from the static rule (BLOCK).
    assert cands[0].action == "BLOCK"
    assert "static_rule" in cands[0].sourced_from


def test_ranking_blends_sources(db_conn):
    """A hash with many recent BLOCK overrides should outrank a single
    competing static_rule INTERVENE candidate."""
    content = "git push --force main"  # static rule fires INTERVENE
    _seed_decision(
        db_conn, decision_id="d1", matched_hash="hX", content=content
    )
    # 5 fresh BLOCK overrides on the same hash
    for i in range(5):
        _seed_decision(
            db_conn,
            decision_id=f"x{i}",
            matched_hash="hX",
            content=content,
        )
        _add_override(db_conn, f"x{i}", "BLOCK", days_ago=0)
    weights = SuggestionWeights()
    row = {
        "id": "d1",
        "action": "ALLOW",
        "confidence": 0.1,
        "matched_hash": "hX",
        "content": content,
    }
    cands = rank_candidates(row, db_conn, weights)
    assert cands[0].action == "BLOCK"
    assert any("hitl_override" in c.sourced_from for c in cands)
    # historical_precedent_count must reflect the 5 prior BLOCKs.
    block = next(c for c in cands if c.action == "BLOCK")
    assert block.historical_precedent_count == 5


def test_candidate_to_json_shape():
    c = Candidate(
        action="BLOCK",
        confidence=0.87,
        historical_precedent_count=3,
        sourced_from=["graph_pattern", "hitl_override"],
        rationale="x" * 200,
        matched_hash="abc",
        score=0.5,
    )
    j = c.to_json()
    # rationale must be capped at 140 chars per spec.
    assert len(j["rationale"]) <= 140
    assert j["action"] == "BLOCK"
    assert j["historical_precedent_count"] == 3
    assert "graph_pattern" in j["sourced_from"]
