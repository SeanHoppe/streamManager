"""v10 P5 — tests for rl.shadow.ShadowRecorder."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from rl.shadow import ShadowRecorder, candidate_decision
from rl.validate import Candidate, L4_THRESHOLD_KEY


BASELINE_THR = 0.75
CANDIDATE_THR = 0.65


def _cand(thr: float = CANDIDATE_THR) -> Candidate:
    return Candidate(thresholds={L4_THRESHOLD_KEY: thr})


def _env(**kw) -> dict:
    base: dict = {"session_id": "sess-target", "trace_id": "trace-1",
                  "verdict": "INTERVENE", "confidence": 0.70,
                  "action_taken": BASELINE_THR, "project_slug": "certPortal",
                  "state_features": {"latency_p95_ms": 1200}}
    base.update(kw)
    return base


def _rows(db: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        return list(conn.execute("SELECT * FROM shadow_episodes"))
    finally:
        conn.close()


def test_shadow_does_not_block_bus(tmp_path: Path) -> None:
    rec = ShadowRecorder(_cand(), tmp_path / "s.db", soak_run_id="r1")
    timings = []
    try:
        for i in range(1000):
            env = _env(trace_id=f"t-{i}", confidence=0.5 + (i % 50) / 100.0)
            t0 = time.perf_counter_ns()
            rec.on_governance_decision(env)
            timings.append((time.perf_counter_ns() - t0) / 1e6)
    finally:
        rec.close()
    timings.sort()
    # Nearest-rank p95 over n=1000 samples = ceil(0.95 * n) = 950th value
    # = index 949 (zero-indexed). The prior `timings[int(0.95 * n)]` =
    # index 950 was the 951st value (off-by-one slack).
    p95_index = max(0, int(round(0.95 * len(timings))) - 1)
    p95 = timings[p95_index]
    assert p95 < 50.0, f"p95 {p95:.2f} ms > 50 ms"


def test_shadow_records_disagreement(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    rec = ShadowRecorder(_cand(), db, soak_run_id="r1")
    rec.on_governance_decision(_env(verdict="INTERVENE", confidence=0.70))
    rec.close()
    rows = _rows(db)
    assert len(rows) == 1
    assert rows[0]["production_verdict"] == "INTERVENE"
    assert rows[0]["candidate_verdict"] == "ALLOW"
    assert int(rows[0]["agree"]) == 0


def test_shadow_drops_on_overrun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    emitted: list[dict] = []
    rec = ShadowRecorder(_cand(), tmp_path / "s.db", soak_run_id="r1",
                         bus_emit=emitted.append, non_invasion_budget_ms=0.001)

    def _slow(_c, _e):
        time.sleep(0.005)
        return CANDIDATE_THR, "ALLOW"
    monkeypatch.setattr("rl.shadow.candidate_decision", _slow)
    rec.on_governance_decision(_env())
    rec.close()
    assert _rows(tmp_path / "s.db") == []
    assert rec.dropped == 1
    assert emitted and emitted[0]["envelope"] == "rl_shadow_dropped"
    assert emitted[0]["reason"] == "candidate_eval_overrun"


def test_shadow_isolated_db(tmp_path: Path) -> None:
    episodes_db = tmp_path / "rl_episodes.db"
    shadow_db = tmp_path / "rl_shadow.db"
    rec = ShadowRecorder(_cand(), shadow_db, soak_run_id="r1")
    rec.on_governance_decision(_env())
    rec.close()
    assert shadow_db.exists() and not episodes_db.exists()
    conn = sqlite3.connect(str(shadow_db))
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert "shadow_episodes" in tables
    assert "episodes" not in tables


def test_shadow_unique_constraint(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    rec = ShadowRecorder(_cand(), db, soak_run_id="r1")
    env = _env()
    rec.on_governance_decision(env)
    rec.on_governance_decision(env)
    rec.close()
    assert len(_rows(db)) == 1
    rec2 = ShadowRecorder(_cand(), db, soak_run_id="r2")
    rec2.on_governance_decision(env)
    rec2.close()
    assert len(_rows(db)) == 2


def test_shadow_no_self_monitor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "s.db"
    monkeypatch.setenv("BRIDGE_SM_SELF_SESSION_ID", "sm-self")
    rec = ShadowRecorder(_cand(), db, soak_run_id="r1")
    rec.on_governance_decision(_env(session_id="sm-self"))
    rec.close()
    assert _rows(db) == []

    monkeypatch.delenv("BRIDGE_SM_SELF_SESSION_ID", raising=False)
    monkeypatch.setenv("BRIDGE_SM_PROJECT_SLUGS", "streamManager")
    rec = ShadowRecorder(_cand(), db, soak_run_id="r2")
    rec.on_governance_decision(_env(project_slug="streamManager"))
    rec.close()
    assert _rows(db) == []

    rec = ShadowRecorder(_cand(), db, soak_run_id="r3")
    rec.on_governance_decision(_env(project_slug="certPortal"))
    rec.close()
    assert len(_rows(db)) == 1


def test_candidate_decision_action_equal_preserves_verdict() -> None:
    cand = _cand(thr=BASELINE_THR)
    action, verdict = candidate_decision(
        cand, _env(verdict="INTERVENE", action_taken=BASELINE_THR))
    assert action == pytest.approx(BASELINE_THR)
    assert verdict == "INTERVENE"
