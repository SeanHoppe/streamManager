"""v10 P3 — tests for OPE estimators.

DR estimator is scoped out of P3 per the phase prompt's LOC-budget
escape hatch and aliased to IPS in ``rl.ope``. The DR-shaped tests
verify the alias contract (DR returns IPS-equivalent statistics).
DR-with-Q ships in a P3 follow-up.
"""

from __future__ import annotations

import math
import sqlite3
import uuid
from pathlib import Path

from rl.ope import (
    cross_validated_dr,
    doubly_robust_estimate,
    hitl_agreement_reward,
    ips_estimate,
    load_episodes_from_db,
)
from rl.sources import Episode


def _ep(action: float = 0.75, propensity: float = 1.0, hitl: int | None = None,
        reward_hint: float = 0.0, content_length: int = 100) -> Episode:
    return Episode(
        ts_utc="2026-05-01T00:00:00+00:00",
        session_id="s",
        trace_id=f"t-{uuid.uuid4().hex}",
        state_features={
            "latency_ms_last5_p95": 1000.0, "content_length": content_length,
            "regex_destructive_match": 0, "regex_alignment_match": 0,
            "time_of_day_bucket": 12, "routing_band": 4,
            "trigger_factor": 0, "learn_mode_bias_hint": reward_hint,
        },
        action_taken=action, action_propensity=propensity,
        verdict="ALLOW", confidence=0.9, latency_ms=1234.0,
        budget_violation=0, source="live", cycle_tag=None,
        hitl_override=hitl, fr_og_7_pass=None,
    )


def _const_policy(action: float):
    return lambda _state: action


def test_hitl_agreement_reward_branches():
    assert hitl_agreement_reward(_ep(hitl=None)) == 1.0
    assert hitl_agreement_reward(_ep(hitl=0)) == 1.0
    assert hitl_agreement_reward(_ep(hitl=1)) == -1.0


def test_ips_uniform_propensity_matches_mean_reward():
    """Deterministic propensity (=1.0) and target == taken → IPS reduces to
    the mean reward (Hájek normalisation cancels the constant weight)."""
    eps = [_ep(action=0.75, propensity=1.0, hitl=None) for _ in range(10)]
    eps += [_ep(action=0.75, propensity=1.0, hitl=1) for _ in range(2)]
    res = ips_estimate(eps, _const_policy(0.75))
    expected = (10 * 1.0 + 2 * -1.0) / 12.0
    assert math.isclose(res.mean, expected, abs_tol=1e-9)
    assert res.off_support_fraction == 0.0
    assert res.n == 12


def test_ips_clips_extreme_weights():
    """Tiny propensity → weight clipped to ceiling; counter increments."""
    eps = [_ep(action=0.75, propensity=1e-9, hitl=None)]
    res = ips_estimate(eps, _const_policy(0.75))
    assert res.clipped_count == 1
    assert math.isfinite(res.mean)
    # Hájek-normalised IPS with single clipped weight → mean reduces to the
    # underlying reward (default reward=1.0 for hitl=None).
    assert math.isclose(res.mean, 1.0, abs_tol=1e-9)


def test_ips_off_support_when_target_diverges():
    """Target picks an action != recorded action → off-support."""
    eps = [_ep(action=0.75, propensity=1.0) for _ in range(5)]
    res = ips_estimate(eps, _const_policy(0.55))
    assert res.off_support_fraction == 1.0


def test_ips_empty_episodes_returns_zero():
    res = ips_estimate([], _const_policy(0.75))
    assert res.n == 0 and res.mean == 0.0


def test_dr_alias_matches_ips_in_p3():
    """DR is aliased to IPS in P3 per LOC-budget scope-back."""
    eps = [_ep(action=0.75, propensity=1.0, hitl=0) for _ in range(8)]
    eps += [_ep(action=0.75, propensity=1.0, hitl=1) for _ in range(2)]
    target = _const_policy(0.75)
    ips = ips_estimate(eps, target)
    dr = doubly_robust_estimate(eps, target, q_model=lambda _s, _a: 0.0)
    assert math.isclose(dr.mean, ips.mean, abs_tol=1e-9)
    assert dr.n == ips.n


def test_cv_dr_5_fold_alias_matches_ips():
    """CV-DR aliased to IPS in P3; signature accepts k_folds/seed/alpha."""
    eps = [_ep(action=0.75, propensity=1.0,
               hitl=(1 if i % 7 == 0 else 0),
               content_length=100 + i * 5) for i in range(25)]
    target = _const_policy(0.75)
    cv = cross_validated_dr(eps, target, k_folds=5, seed=42, alpha=0.5)
    ips = ips_estimate(eps, target)
    assert math.isclose(cv.mean, ips.mean, abs_tol=1e-9)
    assert cv.n == ips.n


def test_load_episodes_from_db(tmp_path: Path):
    """DB loader pulls (live, soak) rows by default and parses
    state_features_json into a dict."""
    db_path = tmp_path / "ep.db"
    schema = (Path(__file__).resolve().parents[1]
              / "rl" / "schema.sql").read_text()
    conn = sqlite3.connect(str(db_path))
    conn.executescript(schema)
    conn.execute(
        "INSERT INTO episodes(ts_utc, session_id, trace_id,"
        " state_features_json, action_taken, action_propensity, verdict,"
        " confidence, latency_ms, budget_violation, source)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("2026-05-01T00:00:00+00:00", "s1", "t1", '{"routing_band": 4}',
         0.75, 1.0, "ALLOW", 0.9, 100.0, 0, "live"),
    )
    conn.execute(
        "INSERT INTO episodes(ts_utc, session_id, trace_id,"
        " state_features_json, action_taken, action_propensity, verdict,"
        " confidence, latency_ms, budget_violation, source)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("2026-05-01T00:00:00+00:00", "s2", "t2", '{"routing_band": 4}',
         0.75, 1.0, "ALLOW", 0.9, 100.0, 0, "probe"),
    )
    conn.commit()
    conn.close()
    rows = load_episodes_from_db(db_path, sources=("live", "soak"))
    assert len(rows) == 1
    assert rows[0]["session_id"] == "s1"
    assert rows[0]["state_features"] == {"routing_band": 4}
