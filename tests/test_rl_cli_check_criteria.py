"""v10 P5 — tests for rl.cli.check_criteria CLI surface."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from rl.cli import check_criteria as cli_check
from rl.shadow import SHADOW_SCHEMA


def _make_db(tmp_path: Path) -> Path:
    db = tmp_path / "s.db"
    conn = sqlite3.connect(str(db), isolation_level=None)
    conn.executescript(SHADOW_SCHEMA)
    conn.close()
    return db


def _bulk_run(db: Path, rid: str) -> None:
    conn = sqlite3.connect(str(db), isolation_level=None)
    try:
        rows: list[tuple] = []
        i = 0
        for _ in range(100):
            rows.append((rid, f"s-{rid}", f"t-{i}", "ALLOW", "ALLOW", "ALLOW"))
            i += 1
        for _ in range(3):
            rows.append((rid, f"s-{rid}", f"t-{i}",
                         "INTERVENE", "ALLOW", "ALLOW"))
            i += 1
        for _ in range(200):
            rows.append((rid, f"s-{rid}-nG", f"t-{i}",
                         "ALLOW", "ALLOW", None))
            i += 1
        for run, sess, trace, prod, cand, gt in rows:
            conn.execute(
                "INSERT INTO shadow_episodes (ts_utc, session_id, trace_id,"
                " state_features_json, production_action, production_verdict,"
                " candidate_action, candidate_verdict, agree,"
                " ground_truth_known, ground_truth_verdict, soak_run_id)"
                " VALUES (?, ?, ?, '{}', 0.75, ?, 0.65, ?, ?, ?, ?, ?)",
                ("2026-05-22T12:00:00+00:00", sess, trace, prod, cand,
                 1 if prod == cand else 0,
                 1 if gt is not None else 0, gt, run))
    finally:
        conn.close()


def _manifest(mdir: Path, name: str, *, best_ci: float = 0.08) -> None:
    mdir.mkdir(parents=True, exist_ok=True)
    posterior = {f"arm_{i}_thr_{0.55 + i * 0.05:.2f}": {
        "alpha": 1.0, "beta": 1.0,
        "mean": 0.5 + (0.1 if i == 4 else 0.0),
        "ci_width_95": best_ci if i == 4 else 0.30,
    } for i in range(9)}
    candidates = [{"arm": i, "l4_threshold": 0.75 if i == 4
                   else 0.55 + i * 0.05} for i in range(9)]
    (mdir / name).write_text(json.dumps({
        "seed": 42, "db_sha": "x", "hyperparams": {},
        "posterior": posterior, "candidates": candidates,
        "ips_per_candidate": {},
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seed_passing(tmp_path: Path) -> tuple[Path, Path]:
    db = _make_db(tmp_path)
    for rid in ("20260520T120000Z", "20260521T120000Z", "20260522T120000Z"):
        _bulk_run(db, rid)
    mdir = tmp_path / "m"
    for ts in ("20260520T100000Z", "20260521T100000Z", "20260522T100000Z"):
        _manifest(mdir, f"{ts}.manifest.json")
    return db, mdir


def test_exit_zero_on_all_pass(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db, mdir = _seed_passing(tmp_path)
    rc = cli_check.main([
        "--shadow-db", str(db), "--manifests", str(mdir),
        "--reports-dir", str(tmp_path / "reports"),
    ])
    assert rc == 0
    reports = list((tmp_path / "reports").glob("v10-criteria-*.md"))
    assert reports
    assert "Overall verdict: **PASS**" in reports[0].read_text(encoding="utf-8")


def test_exit_one_on_any_fail(tmp_path: Path) -> None:
    db, mdir = _seed_passing(tmp_path)
    _manifest(mdir, "20260522T100000Z.manifest.json", best_ci=0.50)
    rc = cli_check.main([
        "--shadow-db", str(db), "--manifests", str(mdir),
        "--reports-dir", str(tmp_path / "reports"),
    ])
    assert rc == 1
    body = next((tmp_path / "reports").glob("v10-criteria-*.md")
                ).read_text(encoding="utf-8")
    assert "Overall verdict: **FAIL**" in body
    assert "posterior_ci" in body


def test_report_header_lists_soak_run_ids(tmp_path: Path) -> None:
    db, mdir = _seed_passing(tmp_path)
    rc = cli_check.main([
        "--shadow-db", str(db), "--manifests", str(mdir),
        "--reports-dir", str(tmp_path / "reports"),
    ])
    assert rc == 0
    body = next((tmp_path / "reports").glob("v10-criteria-*.md")
                ).read_text(encoding="utf-8")
    for rid in ("20260520T120000Z", "20260521T120000Z", "20260522T120000Z"):
        assert rid in body


def test_render_report_lists_all_criteria() -> None:
    from rl.stop_conditions import CriteriaReport, CriterionResult
    report = CriteriaReport(criteria=[
        CriterionResult(n, True, "ok") for n in (
            "shadow_reward_improvement", "fr_og_7_violations",
            "cand_prod_agreement", "alignment_pass_rate",
            "posterior_ci", "parameter_drift")])
    body = cli_check.render_report(report, "T")
    for n in ("shadow_reward_improvement", "fr_og_7_violations",
              "cand_prod_agreement", "alignment_pass_rate",
              "posterior_ci", "parameter_drift"):
        assert n in body
    assert "Overall verdict: **PASS**" in body


def test_v10_1_mode_prints_pass_infra_and_dormant(tmp_path: Path) -> None:
    # ADR-18 Amendment D legibility: --mode v10.1 renders the reward
    # criterion DORMANT, the verdict as PASS-INFRA, and exits 0.
    db, mdir = _seed_passing(tmp_path)
    rc = cli_check.main([
        "--shadow-db", str(db), "--manifests", str(mdir),
        "--reports-dir", str(tmp_path / "reports"), "--mode", "v10.1",
    ])
    assert rc == 0
    body = next((tmp_path / "reports").glob("v10-criteria-*.md")
                ).read_text(encoding="utf-8")
    assert "Mode: **v10.1**" in body
    assert "Overall verdict: **PASS-INFRA**" in body
    assert "**shadow_reward_improvement** — DORMANT" in body
