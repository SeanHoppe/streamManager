"""v10 P1 — tests for rl.state_features.extract."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rl.state_features import FEATURE_KEYS, VERDICTS, extract


def _baseline_state() -> dict:
    return {
        "content": "ship the feature today",
        "latency_ms_last5": [100.0, 120.0, 110.0, 130.0, 115.0],
        "session_history_actions": ["ALLOW", "ALLOW", "SUGGEST", "ALLOW", "ALLOW"],
        "routing_band": 3,
        "trigger_factor": 0,
        "learn_mode_bias_hint": 0.42,
    }


def test_extract_returns_design_doc_keys():
    state = _baseline_state()
    out = extract(state, now_utc=datetime(2026, 5, 7, 14, 0, 0, tzinfo=timezone.utc))
    assert set(out.keys()) == set(FEATURE_KEYS)


def test_extract_is_pure():
    state = _baseline_state()
    now = datetime(2026, 5, 7, 14, 0, 0, tzinfo=timezone.utc)
    first = extract(state, now_utc=now)
    for _ in range(100):
        assert extract(state, now_utc=now) == first


def test_action_share_length_5():
    out = extract(_baseline_state(), now_utc=datetime(2026, 5, 7, 14, 0, 0, tzinfo=timezone.utc))
    share = out["session_history_action_share"]
    assert isinstance(share, list)
    assert len(share) == len(VERDICTS) == 5
    assert sum(share) == pytest.approx(1.0, abs=1e-9)


def test_time_of_day_bucket_is_utc_hour():
    state = _baseline_state()
    for hour in (0, 6, 14, 23):
        now = datetime(2026, 5, 7, hour, 30, 0, tzinfo=timezone.utc)
        out = extract(state, now_utc=now)
        assert out["time_of_day_bucket"] == hour


def test_destructive_pattern_parity():
    """≥ 90 % of canonical destructive prompts trigger the regex hit."""
    destructive_prompts = [
        # wrapped — typical soak-cassette framing
        "User just typed: `rm -rf $HOME`. Should this be allowed?",
        "User wants to run: DELETE FROM users WHERE 1=1. Decision?",
        "User about to execute: DROP TABLE production_orders. Allow or block?",
        "Operator request: git push --force origin main",
        "Customer-facing migration about to run: TRUNCATE TABLE orders",
        "Engineer typed: sudo rm -rf /var/lib/postgres",
        "Run command: dd if=/dev/zero of=/dev/sda",
        "User: chmod -R 0777 /etc",
        "User asks: mkfs.ext4 /dev/nvme0n1",
        "User: git reset --hard HEAD~50",
        # bare — direct destructive imperatives
        "rm -rf /",
        "DROP DATABASE production",
        "DELETE FROM users WHERE 1=1",
        "git push --force origin main",
        "TRUNCATE TABLE orders",
        "sudo rm -rf /var",
        "drop table metrics_archive",
        "git clean -fd",
        "chmod -R 0777 /",
        ":(){ :|:& };:",
    ]

    hits = 0
    now = datetime(2026, 5, 7, 14, 0, 0, tzinfo=timezone.utc)
    for prompt in destructive_prompts:
        out = extract({"content": prompt}, now_utc=now)
        hits += int(out["regex_destructive_match"])

    rate = hits / len(destructive_prompts)
    assert rate >= 0.90, f"destructive parity {rate:.2%} below ≥ 90 % floor"


def test_alignment_pattern_hits_on_keywords():
    state = {"content": "Production credential rotation for customer-facing service"}
    out = extract(state, now_utc=datetime(2026, 5, 7, 14, 0, 0, tzinfo=timezone.utc))
    assert out["regex_alignment_match"] == 1


def test_empty_state_yields_zero_features():
    out = extract({}, now_utc=datetime(2026, 5, 7, 14, 0, 0, tzinfo=timezone.utc))
    assert out["latency_ms_last5_p95"] == 0.0
    assert out["content_length"] == 0
    assert out["regex_destructive_match"] == 0
    assert out["regex_alignment_match"] == 0
    assert out["routing_band"] == 0
    assert out["trigger_factor"] == 0
    assert out["learn_mode_bias_hint"] == 0.0
    assert out["session_history_action_share"] == [0.0] * 5
