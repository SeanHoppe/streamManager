"""Read-only summarisers over rl_episodes.db / rl_shadow.db for the rl-test-orchestrator agent.

NEVER writes. NEVER mutates schema. Opens with `mode=ro` URI.
"""
from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import quote


@dataclass
class EpisodeSummary:
    total: int
    by_source: dict[str, int]
    by_verdict: dict[str, int]
    propensity_off_support_fraction: float
    self_monitor_rows: int
    wal_mode: bool


@dataclass
class ShadowSummary:
    total: int
    agree_rate: float
    disagreements_by_verdict_pair: dict[str, int]
    soak_run_ids: list[str]
    self_monitor_rows: int


def _ro_connect(db_path: Path) -> sqlite3.Connection:
    # Windows-correct file URI form: `file:/C:/...?mode=ro` (per SQLite spec).
    # Mirrors rl/ope.py:load_episodes_from_db (PR #123 A3 fix).
    safe = quote(db_path.resolve().as_posix().lstrip("/"), safe="/:")
    return sqlite3.connect(f"file:/{safe}?mode=ro", uri=True)


def _resolve_self_session_id(sm_self_session_id: str | None) -> str | None:
    if sm_self_session_id is not None:
        return sm_self_session_id
    return os.environ.get("BRIDGE_SM_SELF_SESSION_ID")


def _journal_mode(conn: sqlite3.Connection) -> str:
    row = conn.execute("PRAGMA journal_mode").fetchone()
    return (row[0] if row else "").lower()


def summarise_episodes(db_path: Path, sm_self_session_id: str | None = None) -> EpisodeSummary:
    sm_self_session_id = _resolve_self_session_id(sm_self_session_id)
    with closing(_ro_connect(db_path)) as conn:
        wal = _journal_mode(conn) == "wal"
        total = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
        by_source = dict(conn.execute(
            "SELECT source, COUNT(*) FROM episodes GROUP BY source").fetchall())
        by_verdict = dict(conn.execute(
            "SELECT verdict, COUNT(*) FROM episodes GROUP BY verdict").fetchall())
        off_support = conn.execute(
            "SELECT COUNT(*) FROM episodes WHERE action_propensity != 1.0"
        ).fetchone()[0]
        self_monitor_rows = 0
        if sm_self_session_id:
            self_monitor_rows = conn.execute(
                "SELECT COUNT(*) FROM episodes WHERE session_id = ?", (sm_self_session_id,)
            ).fetchone()[0]
    return EpisodeSummary(
        total=total,
        by_source=by_source,
        by_verdict=by_verdict,
        propensity_off_support_fraction=(off_support / total) if total else 0.0,
        self_monitor_rows=self_monitor_rows,
        wal_mode=wal,
    )


def summarise_shadow(db_path: Path, sm_self_session_id: str | None = None) -> ShadowSummary:
    sm_self_session_id = _resolve_self_session_id(sm_self_session_id)
    with closing(_ro_connect(db_path)) as conn:
        total = conn.execute("SELECT COUNT(*) FROM shadow_episodes").fetchone()[0]
        agreed = conn.execute("SELECT COUNT(*) FROM shadow_episodes WHERE agree=1").fetchone()[0]
        disagree_rows = conn.execute(
            "SELECT production_verdict, candidate_verdict FROM shadow_episodes WHERE agree=0"
        ).fetchall()
        pair_counter: Counter[str] = Counter(f"{p}->{c}" for p, c in disagree_rows)
        soak_ids = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT soak_run_id FROM shadow_episodes ORDER BY soak_run_id"
            ).fetchall()
        ]
        self_monitor_rows = 0
        if sm_self_session_id:
            self_monitor_rows = conn.execute(
                "SELECT COUNT(*) FROM shadow_episodes WHERE session_id = ?", (sm_self_session_id,)
            ).fetchone()[0]
    return ShadowSummary(
        total=total,
        agree_rate=(agreed / total) if total else 0.0,
        disagreements_by_verdict_pair=dict(pair_counter),
        soak_run_ids=soak_ids,
        self_monitor_rows=self_monitor_rows,
    )


def summary_to_json(summary: EpisodeSummary | ShadowSummary) -> str:
    return json.dumps(asdict(summary), indent=2, sort_keys=True)
