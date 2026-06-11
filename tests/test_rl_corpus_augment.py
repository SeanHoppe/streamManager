"""v10 P2 — tests for rl.corpus_augment.

Covers ratio cap, real >= synthetic, balance warning + error, deterministic
seed, self-monitor filter (per feedback_no_self_monitor.md), and the
golden-holdout invariant.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from rl.corpus_augment import (
    CorpusBalanceError, GoldenInTrainingError, assemble_training_set,
)
from rl.episode_logger import EpisodeLogger
from rl.sources import Episode


def _make_real_db(tmp_path: Path, n: int) -> Path:
    db = tmp_path / "rl_episodes.db"
    with EpisodeLogger(db) as logger:
        for i in range(n):
            logger.record_decision({
                "session_id": f"sess-{i}", "trace_id": f"trace-{i}",
                "verdict": "ALLOW", "confidence": 0.9,
                "action_taken": 0.7, "action_propensity": 1.0,
                "latency_ms": 100.0 + i, "budget_violation": 0,
                "fr_og_7_pass": 1, "hitl_override": None,
                "state": {"content": "ship it", "latency_ms_last5": [100.0],
                          "session_history_actions": ["ALLOW"],
                          "routing_band": 1, "trigger_factor": 0,
                          "learn_mode_bias_hint": 0.0},
            }, source="live")
    return db


def _synth(i: int, source: str = "cassette") -> Episode:
    return Episode(
        ts_utc=datetime(2000, 1, 1, tzinfo=timezone.utc).isoformat(),
        session_id=f"{source}-sess", trace_id=f"{source}-{i}",
        state_features={"content_length": 10},
        action_taken=0.0, action_propensity=1.0,
        verdict="BLOCK", confidence=0.95,
        latency_ms=10.0, budget_violation=0,
        source=source, cycle_tag=f"{source}-tag",
        hitl_override=(1 if source == "probe" else None),
        fr_og_7_pass=(1 if source == "cassette" else None),
    )


def test_ratio_cap_enforced(tmp_path: Path) -> None:
    db = _make_real_db(tmp_path, n=200)
    out = assemble_training_set(
        target_n=100, ratio_synthetic=0.30, seed=1, db_path=db,
        extra_episodes=[_synth(i) for i in range(200)],
    )
    n_synth = sum(1 for ep in out if ep.source == "cassette")
    assert n_synth <= int(round(0.30 * 100))


def test_real_outweighs_synthetic(tmp_path: Path) -> None:
    db = _make_real_db(tmp_path, n=200)
    extras = [_synth(i) for i in range(200)]
    for seed in (0, 1, 7, 42, 99):
        out = assemble_training_set(
            target_n=100, ratio_synthetic=0.30, seed=seed,
            db_path=db, extra_episodes=extras,
        )
        n_real = sum(1 for ep in out if ep.source in ("live", "soak"))
        n_synth = sum(1 for ep in out if ep.source not in ("live", "soak"))
        assert n_real >= n_synth, f"seed={seed} real={n_real} synth={n_synth}"


def test_class_balance_warning(tmp_path: Path,
                               caplog: pytest.LogCaptureFixture) -> None:
    """Deviation in (0.10, 0.25] warns but does not raise."""
    db = _make_real_db(tmp_path, n=200)
    # target_n=20, ratio=0.30 -> target_synth=6; only 2 synth available
    # -> actual=2/20=0.10 -> deviation 0.20 (warn band).
    caplog.set_level(logging.WARNING, logger="rl.corpus_augment")
    out = assemble_training_set(
        target_n=20, ratio_synthetic=0.30, seed=1, db_path=db,
        extra_episodes=[_synth(i) for i in range(2)],
    )
    assert any("rl_corpus_class_balance" in r.message and "deviation" in r.message
               for r in caplog.records), [r.message for r in caplog.records]
    assert len(out) <= 20


def test_class_balance_error(tmp_path: Path) -> None:
    """Deviation > 25 % raises CorpusBalanceError."""
    db = _make_real_db(tmp_path, n=10)
    with pytest.raises(CorpusBalanceError):
        assemble_training_set(
            target_n=10, ratio_synthetic=0.30, seed=1,
            db_path=db, extra_episodes=[],
        )


def test_deterministic_with_seed(tmp_path: Path) -> None:
    db = _make_real_db(tmp_path, n=200)
    extras = [_synth(i) for i in range(200)]
    runs = []
    for _ in range(5):
        out = assemble_training_set(
            target_n=100, ratio_synthetic=0.30, seed=42,
            db_path=db, extra_episodes=extras,
        )
        runs.append([(ep.source, ep.trace_id) for ep in out])
    for r in runs[1:]:
        assert r == runs[0]


def test_no_self_monitor_episodes(tmp_path: Path,
                                  monkeypatch: pytest.MonkeyPatch) -> None:
    """feedback_no_self_monitor.md: SM-self episodes are filtered."""
    db = _make_real_db(tmp_path, n=200)
    sm_self = "sm-self-session-xyz"
    monkeypatch.setenv("BRIDGE_SM_SELF_SESSION_ID", sm_self)
    poison = Episode(
        ts_utc=datetime(2000, 1, 1, tzinfo=timezone.utc).isoformat(),
        session_id=sm_self, trace_id="poison-1",
        state_features={"content_length": 0},
        action_taken=0.0, action_propensity=1.0,
        verdict="BLOCK", confidence=0.99,
        latency_ms=0.0, budget_violation=0,
        source="cassette", cycle_tag="poison",
        hitl_override=None, fr_og_7_pass=1,
    )
    out = assemble_training_set(
        target_n=100, ratio_synthetic=0.30, seed=1, db_path=db,
        extra_episodes=[poison, *(_synth(i) for i in range(50))],
    )
    assert all(ep.session_id != sm_self and ep.trace_id != "poison-1"
               for ep in out)


def test_golden_holdout_invariant() -> None:
    with pytest.raises(GoldenInTrainingError):
        assemble_training_set(target_n=5, include_golden=True)


def test_sql_where_excludes_sm_project_slug(tmp_path: Path) -> None:
    """Defense-in-depth: even if an SM-slug row reaches rl_episodes.db
    (write-time refusal bypassed), the corpus read filters it at the SQL
    WHERE per CLAUDE.md L42. NULL project_slug rows are retained."""
    import sqlite3 as _sqlite3

    # Build a DB the normal way (NULL project_slug rows).
    db = _make_real_db(tmp_path, n=10)
    # Inject one SM-slug row directly, bypassing the write-time guard.
    conn = _sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO episodes(ts_utc, session_id, trace_id, state_features_json,"
        " action_taken, action_propensity, verdict, confidence, latency_ms,"
        " budget_violation, source, project_slug)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ("2026-05-01T00:00:00+00:00", "sm-poison-sess", "sm-poison-trace",
         "{}", 0.7, 1.0, "ALLOW", 0.9, 100.0, 0, "live", "streamManager"),
    )
    conn.commit()
    conn.close()

    out = assemble_training_set(
        target_n=20, ratio_synthetic=0.0, seed=1, db_path=db,
        extra_episodes=[],
    )
    assert all(ep.session_id != "sm-poison-sess" for ep in out)
    assert all(ep.trace_id != "sm-poison-trace" for ep in out)
