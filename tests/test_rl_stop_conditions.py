"""v10 P5 — tests for rl.stop_conditions.evaluate_criteria."""

from __future__ import annotations

import inspect
import json
import sqlite3
from pathlib import Path

import pytest

import rl.stop_conditions as stop_conditions
from rl.shadow import SHADOW_SCHEMA
from rl.stop_conditions import (
    POSTERIOR_CI_CAP, SHADOW_REWARD_DELTA, ShipCriteria, evaluate_criteria,
)
from rl.validate import Candidate, L4_THRESHOLD_KEY


BASELINE_THR = 0.75


def _baseline() -> Candidate:
    return Candidate(thresholds={L4_THRESHOLD_KEY: BASELINE_THR})


def _make_db(tmp_path: Path) -> Path:
    db = tmp_path / "s.db"
    conn = sqlite3.connect(str(db), isolation_level=None)
    conn.executescript(SHADOW_SCHEMA)
    conn.close()
    return db


def _bulk(db: Path, rows: list[tuple]) -> None:
    conn = sqlite3.connect(str(db), isolation_level=None)
    try:
        for run, sess, trace, prod_v, cand_v, gt in rows:
            conn.execute(
                "INSERT INTO shadow_episodes (ts_utc, session_id, trace_id,"
                " state_features_json, production_action, production_verdict,"
                " candidate_action, candidate_verdict, agree,"
                " ground_truth_known, ground_truth_verdict, soak_run_id)"
                " VALUES (?, ?, ?, '{}', 0.75, ?, 0.65, ?, ?, ?, ?, ?)",
                ("2026-05-22T12:00:00+00:00", sess, trace, prod_v, cand_v,
                 1 if prod_v == cand_v else 0,
                 1 if gt is not None else 0, gt, run))
    finally:
        conn.close()


def _seed_pass_run(db: Path, rid: str) -> None:
    """100 gt-matching agree + 3 gt-known disagree (cand right) + 200 gt-
    unknown agree. delta ≈ 0.029 ≥ 0.02; agree ≈ 0.99 ≥ 0.98."""
    rows: list[tuple] = []
    i = 0
    for _ in range(100):
        rows.append((rid, f"sess-{rid}", f"t-{i}", "ALLOW", "ALLOW", "ALLOW"))
        i += 1
    for _ in range(3):
        rows.append((rid, f"sess-{rid}", f"t-{i}",
                     "INTERVENE", "ALLOW", "ALLOW"))
        i += 1
    for _ in range(200):
        rows.append((rid, f"sess-{rid}-noGT", f"t-{i}",
                     "ALLOW", "ALLOW", None))
        i += 1
    _bulk(db, rows)


def _write_manifest(
    mdir: Path, name: str, *, best_thr: float = 0.75, best_ci: float = 0.08,
) -> None:
    mdir.mkdir(parents=True, exist_ok=True)
    posterior = {f"arm_{i}_thr_{0.55 + i * 0.05:.2f}": {
        "alpha": 1.0, "beta": 1.0,
        "mean": 0.5 + (0.1 if i == 4 else 0.0),
        "ci_width_95": best_ci if i == 4 else 0.30,
    } for i in range(9)}
    candidates = [{"arm": i, "l4_threshold": best_thr if i == 4
                   else 0.55 + i * 0.05} for i in range(9)]
    (mdir / name).write_text(json.dumps({
        "seed": 42, "db_sha": "x", "hyperparams": {},
        "posterior": posterior, "candidates": candidates,
        "ips_per_candidate": {},
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seed_pass_manifests(mdir: Path) -> None:
    for ts in ("20260520T100000Z", "20260521T100000Z", "20260522T100000Z"):
        _write_manifest(mdir, f"{ts}.manifest.json")


def test_all_criteria_pass_returns_pass(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    for rid in ("20260520T120000Z", "20260521T120000Z", "20260522T120000Z"):
        _seed_pass_run(db, rid)
    mdir = tmp_path / "m"
    _seed_pass_manifests(mdir)
    report = evaluate_criteria(db, mdir, _baseline())
    failed = [(c.name, c.detail) for c in report.criteria if not c.passed]
    assert report.overall_passed, f"unexpected fails: {failed}"


def test_fr_og_7_failure_overrides_other_passes(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    for rid in ("20260520T120000Z", "20260521T120000Z", "20260522T120000Z"):
        _seed_pass_run(db, rid)
    _bulk(db, [("20260522T120000Z", "sess-violator", "t-violator",
                "ALLOW", "BLOCK", "ALLOW")])
    mdir = tmp_path / "m"
    _seed_pass_manifests(mdir)
    report = evaluate_criteria(db, mdir, _baseline())
    fr = next(c for c in report.criteria if c.name == "fr_og_7_violations")
    assert not fr.passed
    assert not report.overall_passed


def test_hitl_below_floor_fails(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    for rid in ("20260520T120000Z", "20260521T120000Z", "20260522T120000Z"):
        _seed_pass_run(db, rid)
    _bulk(db, [("20260522T120000Z", f"sess-d-{i}", f"t-d-{i}",
                "ALLOW", "INTERVENE", None) for i in range(200)])
    mdir = tmp_path / "m"
    _seed_pass_manifests(mdir)
    report = evaluate_criteria(db, mdir, _baseline())
    hitl = next(c for c in report.criteria if c.name == "hitl_agreement")
    assert not hitl.passed
    assert not report.overall_passed


def test_two_consecutive_shadows_insufficient(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    for rid in ("20260520T120000Z", "20260521T120000Z"):
        _seed_pass_run(db, rid)
    mdir = tmp_path / "m"
    _seed_pass_manifests(mdir)
    report = evaluate_criteria(db, mdir, _baseline())
    reward = next(c for c in report.criteria
                  if c.name == "shadow_reward_improvement")
    assert not reward.passed
    assert "insufficient shadow runs" in reward.detail
    assert not report.overall_passed


def test_parameter_drift_too_high_fails(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    for rid in ("20260520T120000Z", "20260521T120000Z", "20260522T120000Z"):
        _seed_pass_run(db, rid)
    mdir = tmp_path / "m"
    _write_manifest(mdir, "20260520T100000Z.manifest.json", best_thr=0.55)
    _write_manifest(mdir, "20260521T100000Z.manifest.json", best_thr=0.75)
    _write_manifest(mdir, "20260522T100000Z.manifest.json", best_thr=0.55)
    report = evaluate_criteria(db, mdir, _baseline())
    drift = next(c for c in report.criteria if c.name == "parameter_drift")
    assert not drift.passed
    assert not report.overall_passed


def test_thresholds_are_constants_not_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    src = inspect.getsource(stop_conditions)
    assert "os.environ" not in src
    monkeypatch.setenv("BRIDGE_RL_SHADOW_REWARD_DELTA", "0.001")
    spec = ShipCriteria()
    assert spec.shadow_reward_delta == SHADOW_REWARD_DELTA
    assert spec.posterior_ci_cap == POSTERIOR_CI_CAP
    with pytest.raises(Exception):
        spec.shadow_reward_delta = 0.0  # type: ignore[misc]
