"""v10 P5 — tests for rl.cli.shadow CLI surface."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from rl.cli import shadow as cli_shadow
from rl.shadow import SHADOW_SCHEMA


def _proposal(tmp_path: Path) -> Path:
    p = tmp_path / "rl_proposals" / "20260522T120000Z.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "envelope": "rl_proposals", "baseline": {"arm": 4},
        "proposals": [],
    }), encoding="utf-8")
    return p


def _baseline(tmp_path: Path) -> Path:
    p = tmp_path / "b.json"
    p.write_text(json.dumps({
        "thresholds": {"BRIDGE_L4_FALLBACK_CONFIDENCE": 0.65},
    }), encoding="utf-8")
    return p


def test_build_soak_command_required_flags(tmp_path: Path) -> None:
    proposal = _baseline(tmp_path)
    shadow_db = tmp_path / "s.db"
    cmd = cli_shadow.build_soak_command(
        proposal=proposal, shadow_db=shadow_db, soak_args="")
    assert "--cli-pool-size" in cmd
    assert cmd[cmd.index("--cli-pool-size") + 1] == "2"
    assert cmd[cmd.index("--shadow-recorder") + 1] == str(shadow_db)
    assert cmd[cmd.index("--shadow-proposal") + 1] == str(proposal)
    assert any("soak_driver.py" in part for part in cmd)


def test_build_soak_command_extra_args(tmp_path: Path) -> None:
    cmd = cli_shadow.build_soak_command(
        proposal=_baseline(tmp_path), shadow_db=tmp_path / "s.db",
        soak_args="--total-seconds 60 --interval-seconds 5")
    assert cmd[cmd.index("--total-seconds") + 1] == "60"
    assert cmd[cmd.index("--interval-seconds") + 1] == "5"


def test_main_dry_run_prints_without_spawning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proposal = _proposal(tmp_path)
    shadow_db = tmp_path / "s.db"
    rc = cli_shadow.main([
        "--proposal", str(proposal), "--shadow-db", str(shadow_db),
        "--dry-run", "--soak-args", "--total-seconds 5",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "soak_driver.py" in out
    assert "--shadow-recorder" in out and "--shadow-proposal" in out
    assert not shadow_db.exists()


def test_main_missing_proposal_returns_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = cli_shadow.main([
        "--proposal", str(tmp_path / "nope.json"),
        "--shadow-db", str(tmp_path / "s.db"), "--dry-run",
    ])
    assert rc == 1
    assert "proposal not found" in capsys.readouterr().err


def test_summarise_empty(tmp_path: Path) -> None:
    summary = cli_shadow._summarise_shadow_db(tmp_path / "x.db", "any")
    assert summary["n"] == 0


def test_summarise_and_write_report(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    conn = sqlite3.connect(str(db), isolation_level=None)
    conn.executescript(SHADOW_SCHEMA)
    for i, (cand, prod) in enumerate([
        ("ALLOW", "ALLOW"), ("ALLOW", "ALLOW"), ("ALLOW", "INTERVENE")
    ]):
        conn.execute(
            "INSERT INTO shadow_episodes (ts_utc, session_id, trace_id,"
            " state_features_json, production_action, production_verdict,"
            " candidate_action, candidate_verdict, agree,"
            " ground_truth_known, ground_truth_verdict, soak_run_id)"
            " VALUES (?, ?, ?, '{}', 0.75, ?, 0.65, ?, ?, 1, 'ALLOW', 'R')",
            ("2026-05-22T12:00:00+00:00", f"s-{i}", f"t-{i}",
             prod, cand, 1 if prod == cand else 0))
    conn.close()
    s = cli_shadow._summarise_shadow_db(db, "R")
    assert s["n"] == 3
    assert s["fr_og_7_violations"] == 0
    assert s["candidate_reward"] == pytest.approx(1.0)
    assert s["production_reward"] == pytest.approx(2 / 3)
    path = tmp_path / "reports" / "v10-shadow-R.md"
    cli_shadow.write_report(path, Path("p.json"), "R", s)
    body = path.read_text(encoding="utf-8")
    assert "v10 shadow report" in body
    assert "FR-OG-7 violations: 0" in body
