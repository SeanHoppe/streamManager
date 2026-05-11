"""Schema-parity test for tools.rl_test_helper.db_summary.

Builds in-memory rl_episodes.db by executing the *real* `rl/schema.sql`
(no copy-paste), inserts one synthetic row matching the full schema, then
calls summarise_episodes / summarise_shadow. Asserts no OperationalError
and that summary fields reflect the inserted row.

Issue: https://github.com/SeanHoppe/streamManager/issues/118
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tools.rl_test_helper.db_summary import (
    EpisodeSummary,
    ShadowSummary,
    summarise_episodes,
    summarise_shadow,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
EPISODES_SCHEMA = REPO_ROOT / "rl" / "schema.sql"

# Shadow schema mirrored from docs/prompts/v10-orchestration/phase-5-shadow-stop-conditions.md
# (P5 not yet merged → no canonical rl/shadow_schema.sql exists). When P5 lands and
# the shadow DDL moves into rl/, swap this inline string for a file read.
SHADOW_SCHEMA_SQL = """
CREATE TABLE shadow_episodes (
    shadow_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc               TEXT NOT NULL,
    session_id           TEXT NOT NULL,
    trace_id             TEXT NOT NULL,
    state_features_json  TEXT NOT NULL,
    production_action    REAL NOT NULL,
    production_verdict   TEXT NOT NULL,
    candidate_action     REAL NOT NULL,
    candidate_verdict    TEXT NOT NULL,
    agree                INTEGER NOT NULL,
    ground_truth_known   INTEGER NOT NULL,
    ground_truth_verdict TEXT,
    soak_run_id          TEXT NOT NULL,
    UNIQUE(session_id, trace_id, soak_run_id)
);
PRAGMA journal_mode=WAL;
"""


@pytest.fixture
def episodes_db_real_schema(tmp_path: Path) -> Path:
    assert EPISODES_SCHEMA.is_file(), f"missing canonical schema: {EPISODES_SCHEMA}"
    db = tmp_path / "rl_episodes.db"
    conn = sqlite3.connect(db)
    try:
        conn.executescript(EPISODES_SCHEMA.read_text(encoding="utf-8"))
        conn.execute(
            """
            INSERT INTO episodes(
                ts_utc, session_id, trace_id, state_features_json,
                action_taken, action_propensity, verdict, confidence,
                hitl_override, latency_ms, fr_og_7_pass, budget_violation,
                source, cycle_tag
            ) VALUES (
                '2026-05-11T00:00:00Z', 's1', 't1', '{}',
                1.0, 0.5, 'ALLOW', 0.9,
                NULL, 42.0, 1, 0,
                'live', 'v2.1-parity-test'
            )
            """
        )
        conn.commit()
    finally:
        conn.close()
    return db


@pytest.fixture
def shadow_db_designed_schema(tmp_path: Path) -> Path:
    db = tmp_path / "rl_shadow.db"
    conn = sqlite3.connect(db)
    try:
        conn.executescript(SHADOW_SCHEMA_SQL)
        conn.execute(
            """
            INSERT INTO shadow_episodes(
                ts_utc, session_id, trace_id, state_features_json,
                production_action, production_verdict,
                candidate_action, candidate_verdict,
                agree, ground_truth_known, ground_truth_verdict, soak_run_id
            ) VALUES (
                '2026-05-11T00:00:00Z', 's1', 't1', '{}',
                1.0, 'ALLOW',
                0.0, 'BLOCK',
                0, 0, NULL, 'soak-parity'
            )
            """
        )
        conn.commit()
    finally:
        conn.close()
    return db


def test_summarise_episodes_against_real_schema(episodes_db_real_schema: Path):
    """summarise_episodes must succeed against the v10 P1 schema exactly as
    defined in rl/schema.sql. Any SELECT clause referencing a renamed/dropped
    column raises sqlite3.OperationalError here — and this test fails.
    """
    s = summarise_episodes(episodes_db_real_schema, sm_self_session_id=None)
    assert isinstance(s, EpisodeSummary)
    assert s.total == 1
    assert s.by_source == {"live": 1}
    assert s.by_verdict == {"ALLOW": 1}
    assert s.propensity_off_support_fraction == pytest.approx(1.0)
    assert s.self_monitor_rows == 0
    assert s.wal_mode is True


def test_summarise_shadow_against_designed_schema(shadow_db_designed_schema: Path):
    s = summarise_shadow(shadow_db_designed_schema, sm_self_session_id=None)
    assert isinstance(s, ShadowSummary)
    assert s.total == 1
    assert s.agree_rate == pytest.approx(0.0)
    assert s.disagreements_by_verdict_pair == {"ALLOW->BLOCK": 1}
    assert s.soak_run_ids == ["soak-parity"]
    assert s.self_monitor_rows == 0


def test_helper_select_clauses_match_real_columns(episodes_db_real_schema: Path):
    """Belt-and-braces: every column the helper SELECTs must exist in the real schema.

    Guards against silent drift if a P1 col rename slips past the calls above
    (e.g. a future helper SELECT added behind a flag).
    """
    referenced_cols = {
        "source",
        "verdict",
        "action_propensity",
        "session_id",
    }
    with sqlite3.connect(episodes_db_real_schema) as conn:
        actual_cols = {row[1] for row in conn.execute("PRAGMA table_info(episodes)")}
    missing = referenced_cols - actual_cols
    assert not missing, f"helper SELECTs reference columns absent from rl/schema.sql: {missing}"
