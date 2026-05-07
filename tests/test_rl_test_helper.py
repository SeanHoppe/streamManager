"""Unit tests for tools/rl_test_helper."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tools.rl_test_helper.db_summary import (
    EpisodeSummary,
    ShadowSummary,
    summarise_episodes,
    summarise_shadow,
    summary_to_json,
)
from tools.rl_test_helper.test_matrix import extract_dod_rows, render_matrix_md


@pytest.fixture
def episodes_db(tmp_path: Path) -> Path:
    db = tmp_path / "rl_episodes.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE episodes (
            episode_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            trace_id TEXT NOT NULL,
            action_propensity REAL NOT NULL DEFAULT 1.0,
            verdict TEXT NOT NULL,
            source TEXT NOT NULL,
            UNIQUE(session_id, trace_id)
        );
        INSERT INTO episodes(session_id, trace_id, action_propensity, verdict, source) VALUES
          ('s1','t1',1.0,'ALLOW','live'),
          ('s1','t2',1.0,'BLOCK','live'),
          ('s2','t1',0.5,'ALLOW','soak'),
          ('SM-SELF','t1',1.0,'ALLOW','live'),
          ('s3','t1',1.0,'BLOCK','probe');
        """
    )
    conn.commit()
    conn.close()
    return db


@pytest.fixture
def shadow_db(tmp_path: Path) -> Path:
    db = tmp_path / "rl_shadow.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE shadow_episodes (
            shadow_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            trace_id TEXT NOT NULL,
            production_verdict TEXT NOT NULL,
            candidate_verdict TEXT NOT NULL,
            agree INTEGER NOT NULL,
            soak_run_id TEXT NOT NULL,
            UNIQUE(session_id, trace_id, soak_run_id)
        );
        INSERT INTO shadow_episodes(session_id,trace_id,production_verdict,candidate_verdict,agree,soak_run_id) VALUES
          ('s1','t1','ALLOW','ALLOW',1,'soak-A'),
          ('s1','t2','ALLOW','BLOCK',0,'soak-A'),
          ('s2','t1','BLOCK','BLOCK',1,'soak-B'),
          ('SM-SELF','t1','ALLOW','ALLOW',1,'soak-A');
        """
    )
    conn.commit()
    conn.close()
    return db


def test_summarise_episodes_counts_and_off_support(episodes_db: Path):
    s = summarise_episodes(episodes_db, sm_self_session_id="SM-SELF")
    assert isinstance(s, EpisodeSummary)
    assert s.total == 5
    assert s.by_source == {"live": 3, "soak": 1, "probe": 1}
    assert s.by_verdict == {"ALLOW": 3, "BLOCK": 2}
    assert s.propensity_off_support_fraction == pytest.approx(0.2)
    assert s.self_monitor_rows == 1
    assert s.wal_mode is True


def test_summarise_episodes_no_self_session_arg(episodes_db: Path):
    s = summarise_episodes(episodes_db, sm_self_session_id=None)
    assert s.self_monitor_rows == 0


def test_summarise_shadow_agree_rate(shadow_db: Path):
    s = summarise_shadow(shadow_db, sm_self_session_id="SM-SELF")
    assert isinstance(s, ShadowSummary)
    assert s.total == 4
    assert s.agree_rate == pytest.approx(0.75)
    assert s.disagreements_by_verdict_pair == {"ALLOW->BLOCK": 1}
    assert s.soak_run_ids == ["soak-A", "soak-B"]
    assert s.self_monitor_rows == 1


def test_summary_to_json_roundtrips(episodes_db: Path):
    import json
    s = summarise_episodes(episodes_db, sm_self_session_id=None)
    j = summary_to_json(s)
    parsed = json.loads(j)
    assert parsed["total"] == 5


def test_extract_dod_rows_parses_phase1_style_dod(tmp_path: Path):
    p = tmp_path / "phase-x.md"
    p.write_text(
        "# Phase X\n\n"
        "Some prose.\n\n"
        "## DOD\n\n"
        "- [ ] First requirement\n"
        "- [ ] Second requirement with `code` and *emphasis*\n"
        "- [x] Already done — should still be ignored (only unchecked)\n"
        "- [ ] Third requirement\n"
        "\n## Mint-new-phase rule\n\n"
        "- [ ] not in DOD section\n",
        encoding="utf-8",
    )
    rows = extract_dod_rows(p)
    assert [r.requirement for r in rows] == [
        "First requirement",
        "Second requirement with `code` and *emphasis*",
        "Third requirement",
    ]
    assert [r.index for r in rows] == [1, 2, 3]


def test_render_matrix_md_has_header_and_one_row_per_req(tmp_path: Path):
    p = tmp_path / "phase-y.md"
    p.write_text("## DOD\n- [ ] only one\n", encoding="utf-8")
    rows = extract_dod_rows(p)
    md = render_matrix_md(p, rows, "20260507T120000Z")
    assert "20260507T120000Z" in md
    assert "| 1 | only one |" in md
    assert "| Requirement | Status |" in md


def test_extract_dod_handles_no_dod_section(tmp_path: Path):
    p = tmp_path / "phase-z.md"
    p.write_text("# No DOD here\n\nProse only.\n", encoding="utf-8")
    assert extract_dod_rows(p) == []
