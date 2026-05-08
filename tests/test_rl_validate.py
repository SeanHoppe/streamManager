"""v10 P3 - tests for the 5-stage validation gauntlet (stages 1-4)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from rl.cli import validate as cli_validate
from rl.sources import Episode
from rl.validate import (
    L4_THRESHOLD_KEY,
    Candidate,
    _stage_1_golden,
    _stage_2_ips,
    _stage_3_cassette,
    _stage_4_adversarial,
    render_markdown,
    validate,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _baseline(thr: float = 0.75) -> Candidate:
    return Candidate(
        thresholds={L4_THRESHOLD_KEY: thr},
        manifest_sha="baseline",
        seed=0,
    )


def _candidate(thr: float = 0.75) -> Candidate:
    return Candidate(
        thresholds={L4_THRESHOLD_KEY: thr},
        manifest_sha="candidate",
        seed=0,
    )


def _ep(action: float = 0.75, hitl: int | None = None) -> Episode:
    return Episode(
        ts_utc="2026-05-01T00:00:00+00:00",
        session_id="s", trace_id=f"t-{action}-{hitl}",
        state_features={"routing_band": 4, "content_length": 100,
                        "regex_destructive_match": 0, "regex_alignment_match": 0,
                        "time_of_day_bucket": 12, "trigger_factor": 0,
                        "learn_mode_bias_hint": 0.0,
                        "latency_ms_last5_p95": 1000.0},
        action_taken=action,
        action_propensity=1.0,
        verdict="ALLOW", confidence=0.9, latency_ms=100.0, budget_violation=0,
        source="live", cycle_tag=None, hitl_override=hitl, fr_og_7_pass=None,
    )


# ---- Stage 1 -------------------------------------------------------------

def test_stage_1_passes_at_baseline():
    res = _stage_1_golden(_candidate(0.75), _baseline(0.75))
    assert res.passed, res.detail
    assert res.metrics["fr_og_7_total"] > 0


def test_stage_1_rejects_fr_og_7_regression():
    """Candidate threshold dropping >1 bin below baseline triggers
    sonnet-floor (FR-OG-7) regression."""
    res = _stage_1_golden(_candidate(0.55), _baseline(0.75))
    assert not res.passed
    assert "FR-OG-7" in res.detail or "regression" in res.detail.lower()


# ---- Stage 2 -------------------------------------------------------------

def test_stage_2_skips_when_db_empty(tmp_path: Path):
    res = _stage_2_ips(_candidate(), _baseline(), 0.02, db_path=tmp_path / "missing.db")
    assert res.passed
    assert res.metrics["skipped"] is True


def test_stage_2_rejects_low_ips():
    """Synthetic episodes engineered so candidate IPS < baseline + delta."""
    # All episodes have action_taken=0.75 (production) and recorded reward
    # via hitl_override. Candidate at 0.55 → off-support → mean=0.0.
    # Baseline at 0.75 → on-support → mean = +1.0.
    eps = [_ep(action=0.75, hitl=0) for _ in range(20)]
    res = _stage_2_ips(_candidate(0.55), _baseline(0.75), 0.02, episodes=eps)
    assert not res.passed
    assert res.metrics["off_support_fraction"] > 0.5


def test_stage_2_passes_with_aligned_candidate():
    eps = [_ep(action=0.75, hitl=0) for _ in range(20)]
    res = _stage_2_ips(_candidate(0.75), _baseline(0.75), 0.02, episodes=eps)
    assert res.passed


# ---- Stage 3 -------------------------------------------------------------

def test_stage_3_passes_at_baseline():
    cassette = REPO_ROOT / "tests" / "fixtures" / "soak_cassette_latest.jsonl"
    res = _stage_3_cassette(_candidate(0.75), _baseline(0.75), cassette_path=cassette)
    # candidate == baseline → identical metrics, must PASS
    assert res.passed, res.detail


def test_stage_3_rejects_action_distribution_shift(tmp_path: Path):
    """Big threshold drop → many fallback fires → AMBIGUOUS spike → action
    distribution TV-shift > cap → reject."""
    # Build a cassette with confidence values straddling 0.55.
    rows = []
    for i in range(100):
        rows.append({
            "idx": i, "kind": "routine", "content": f"cmd-{i}",
            "recorded_latency_ms": 100.0,
            "decision": {"action": "ALLOW",
                         "confidence": 0.6 if i < 80 else 0.95,
                         "reasoning": "synthetic", "matched_hash": "",
                         "model_used": "haiku", "layer": 0},
        })
    cassette = tmp_path / "soak_cassette_synth.jsonl"
    cassette.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    # Baseline 0.5 → all confidences pass; candidate 0.75 → 80% fall below
    # → AMBIGUOUS spike.
    res = _stage_3_cassette(_candidate(0.75), _baseline(0.50),
                             cassette_path=cassette)
    assert not res.passed
    assert "TV-shift" in res.detail or "p95 regress" in res.detail


# ---- Stage 4 -------------------------------------------------------------

def test_stage_4_skips_when_no_adversarial():
    res = _stage_4_adversarial(_candidate(), _baseline(), 0.02)
    assert res.passed
    assert res.metrics["skipped"] is True


def test_stage_4_rejects_adversarial_drop():
    """Adversarial subset with hitl_override=1 (human disagreed) under a
    candidate that goes off-support → reward drops below baseline-δ."""
    adversarial = []
    for i in range(10):
        ep = Episode(
            ts_utc="2026-05-01T00:00:00+00:00",
            session_id=f"adv-{i}", trace_id=f"adv-{i}",
            state_features={"routing_band": 4, "content_length": 50,
                            "regex_destructive_match": 1, "regex_alignment_match": 1,
                            "time_of_day_bucket": 12, "trigger_factor": 1,
                            "learn_mode_bias_hint": 0.0,
                            "latency_ms_last5_p95": 100.0},
            action_taken=0.75,  # baseline action recorded
            action_propensity=1.0,
            verdict="BLOCK", confidence=0.9,
            latency_ms=100.0, budget_violation=0,
            source="probe", cycle_tag="adv", hitl_override=0,
            fr_og_7_pass=None,
            provenance={"adversarial": True},
        )
        adversarial.append(ep)
    # Baseline matches recorded action → reward ~1.0.
    # Candidate diverges → off-support → 0.0 → drops below baseline-δ.
    res = _stage_4_adversarial(_candidate(0.55), _baseline(0.75), 0.02,
                                extra_episodes=adversarial)
    assert not res.passed


# ---- Pipeline driver -----------------------------------------------------

def test_pipeline_short_circuits_on_stage_1():
    """When stage 1 rejects, stages 2-4 must NOT run."""
    with patch("rl.validate._stage_2_ips") as m2, \
         patch("rl.validate._stage_3_cassette") as m3, \
         patch("rl.validate._stage_4_adversarial") as m4:
        report = validate(_candidate(0.55), _baseline(0.75), delta=0.02)
        assert not report.passed
        assert len(report.stages) == 1
        m2.assert_not_called()
        m3.assert_not_called()
        m4.assert_not_called()


def test_pipeline_short_circuits_on_stage_3(tmp_path: Path):
    """Stage 3 reject → stage 4 must NOT run."""
    rows = []
    for i in range(40):
        rows.append({
            "idx": i, "kind": "routine", "content": f"c-{i}",
            "recorded_latency_ms": 50.0,
            "decision": {"action": "ALLOW", "confidence": 0.6,
                         "reasoning": "", "matched_hash": "",
                         "model_used": "haiku", "layer": 0},
        })
    cassette = tmp_path / "soak_cassette_synth.jsonl"
    cassette.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    with patch("rl.validate._stage_4_adversarial") as m4:
        report = validate(
            _candidate(0.75), _baseline(0.50), delta=0.02,
            cassette_path=cassette, episodes=[],
        )
        assert not report.passed
        assert report.first_failure.name == "stage_3_cassette"
        m4.assert_not_called()


def test_pass_through_returns_full_report():
    """Identical candidate / baseline → all 4 stages PASS."""
    cassette = REPO_ROOT / "tests" / "fixtures" / "soak_cassette_latest.jsonl"
    report = validate(
        _candidate(0.75), _baseline(0.75), delta=0.02,
        cassette_path=cassette, episodes=[],
    )
    assert report.passed
    assert len(report.stages) == 4
    for s in report.stages:
        assert s.passed, f"{s.name}: {s.detail}"


def test_render_markdown_includes_all_stages():
    cassette = REPO_ROOT / "tests" / "fixtures" / "soak_cassette_latest.jsonl"
    report = validate(
        _candidate(0.75), _baseline(0.75), delta=0.02,
        cassette_path=cassette, episodes=[],
    )
    md = render_markdown(report)
    for stage_name in ("stage_1_golden", "stage_2_ips", "stage_3_cassette",
                        "stage_4_adversarial"):
        assert stage_name in md
    assert "VERDICT: PASS" in md


# ---- OPE-only invariant: no live `claude` calls --------------------------

def test_no_live_cli_calls(tmp_path: Path):
    """CLI runs to completion with PATH scrubbed of any `claude` binary."""
    cand_path = tmp_path / "candidate.json"
    base_path = tmp_path / "baseline.json"
    payload = {"thresholds": {L4_THRESHOLD_KEY: 0.75}, "manifest_sha": "x", "seed": 0}
    cand_path.write_text(json.dumps(payload), encoding="utf-8")
    base_path.write_text(json.dumps(payload), encoding="utf-8")
    report_path = tmp_path / "report.md"
    cassette = REPO_ROOT / "tests" / "fixtures" / "soak_cassette_latest.jsonl"

    # Subprocess with PATH = "" (Windows) / "/nonexistent" (POSIX) so no
    # `claude` binary is reachable. Empty string PATH on Windows still
    # finds CWD; safer to point it at a directory that exists but
    # contains no executables.
    scrubbed_dir = tmp_path / "no_bins"
    scrubbed_dir.mkdir()
    env = {
        "PATH": str(scrubbed_dir),
        "PYTHONPATH": str(REPO_ROOT),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
    }
    proc = subprocess.run(
        [sys.executable, "-m", "rl.cli.validate",
         "--candidate", str(cand_path), "--baseline", str(base_path),
         "--delta", "0.02", "--db", str(tmp_path / "missing.db"),
         "--cassette", str(cassette),
         "--report-path", str(report_path)],
        env=env, cwd=str(REPO_ROOT),
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, (
        f"CLI failed without claude on PATH:\nstdout={proc.stdout}\n"
        f"stderr={proc.stderr}"
    )
    assert report_path.exists()
    md = report_path.read_text(encoding="utf-8")
    assert "VERDICT: PASS" in md


def test_cli_reject_returns_exit_1(tmp_path: Path):
    cand_path = tmp_path / "c.json"
    base_path = tmp_path / "b.json"
    cand_path.write_text(json.dumps({"thresholds": {L4_THRESHOLD_KEY: 0.55},
                                      "manifest_sha": "c", "seed": 0}), encoding="utf-8")
    base_path.write_text(json.dumps({"thresholds": {L4_THRESHOLD_KEY: 0.75},
                                      "manifest_sha": "b", "seed": 0}), encoding="utf-8")
    report_path = tmp_path / "r.md"
    rc = cli_validate.main([
        "--candidate", str(cand_path), "--baseline", str(base_path),
        "--delta", "0.02", "--db", str(tmp_path / "x.db"),
        "--report-path", str(report_path),
    ])
    assert rc == 1
    assert "REJECT at" in report_path.read_text(encoding="utf-8")
