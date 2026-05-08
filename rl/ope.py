"""v10 P3 — Off-policy evaluation estimators (IPS-only build).

Pure-Python (stdlib only) IPS estimator for the v10 OPE harness.
Production policy at v10.0 is deterministic → live episodes record
``action_propensity = 1.0``. Off-support arises only when
``target_policy(state) != production_action``. IPS clips weights to
``[0.01, 100]`` and reports the off-support fraction (ADR-18
"OPE-only invariant").

DR / cross-validated-DR / Ridge Q-model are SCOPED OUT of P3 per the
phase prompt's explicit LOC-budget escape hatch. ``doubly_robust_estimate``
and ``cross_validated_dr`` are forward-compat IPS aliases until DR
ships in a follow-up.

Episode duck-type: ``state_features`` (dict), ``action_taken`` (float),
``action_propensity`` (float), ``hitl_override`` (0/1/None) — matches
both ``rl.sources.Episode`` and dict rows from ``load_episodes_from_db``.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

State = dict
Action = float
Episode = Any
TargetPolicy = Callable[[State], Action]
QModel = Callable[[State, Action], float]

_PROPENSITY_FLOOR = 0.01
_PROPENSITY_CEIL = 100.0
_ACTION_TOLERANCE = 1e-6


def hitl_agreement_reward(ep: Episode) -> float:
    """Stage-A reward: +1 if HITL agreed (or none), -1 if HITL overrode."""
    h = ep.get("hitl_override") if isinstance(ep, dict) else getattr(ep, "hitl_override", None)
    if h is None:
        return 1.0
    return -1.0 if int(h) == 1 else 1.0


def _f(ep: Episode, name: str, default: Any = None) -> Any:
    return ep.get(name, default) if isinstance(ep, dict) else getattr(ep, name, default)


def _state_of(ep: Episode) -> dict:
    return dict(_f(ep, "state_features", {}) or {})


def _clip_weight(prop: float) -> tuple[float, bool]:
    raw = 1.0 / max(prop, 1e-12)
    if raw < _PROPENSITY_FLOOR:
        return _PROPENSITY_FLOOR, True
    if raw > _PROPENSITY_CEIL:
        return _PROPENSITY_CEIL, True
    return raw, False


@dataclass
class IPSResult:
    mean: float
    half_width_95: float
    off_support_fraction: float
    clipped_count: int
    n: int


def ips_estimate(
    episodes: Sequence[Episode],
    target_policy: TargetPolicy,
    *,
    reward: Callable[[Episode], float] = hitl_agreement_reward,
) -> IPSResult:
    """Hájek-normalised IPS. Returns mean, 95% CI half-width, off-support
    fraction, clipped weight count, sample size."""
    if not episodes:
        return IPSResult(0.0, 0.0, 0.0, 0, 0)
    weights: list[float] = []
    weighted_rewards: list[float] = []
    off_support = clipped = 0
    for ep in episodes:
        a_target = float(target_policy(_state_of(ep)))
        a_taken = float(_f(ep, "action_taken", 0.0) or 0.0)
        if not math.isclose(a_taken, a_target, abs_tol=_ACTION_TOLERANCE):
            off_support += 1
            continue
        w, was_clipped = _clip_weight(float(_f(ep, "action_propensity", 1.0) or 1.0))
        if was_clipped:
            clipped += 1
        weights.append(w)
        weighted_rewards.append(w * float(reward(ep)))
    n = len(episodes)
    if not weights:
        return IPSResult(0.0, 0.0, 1.0, clipped, n)
    denom = sum(weights)
    mean = sum(weighted_rewards) / denom if denom else 0.0
    if len(weights) > 1:
        # TODO(v10.1): swap to ESS denom (Σw)²/Σw² when propensities go stochastic.
        var = sum(w * ((wr / w if w else 0.0) - mean) ** 2
                  for w, wr in zip(weights, weighted_rewards, strict=True)) / denom
        stderr = math.sqrt(var / len(weights))
    else:
        stderr = 0.0
    return IPSResult(mean, 1.96 * stderr, off_support / max(1, n), clipped, n)


# DR / cross-validated DR — scoped out of P3 per LOC-budget escape hatch.
# Aliased to IPS so callers can opt into DR later without API churn.
@dataclass
class DRResult:
    mean: float
    half_width_95: float
    off_support_fraction: float
    n: int


def doubly_robust_estimate(
    episodes: Sequence[Episode], target_policy: TargetPolicy, q_model: QModel,
    *, reward: Callable[[Episode], float] = hitl_agreement_reward,
) -> DRResult:
    """P3 DR alias — falls back to IPS (DR ships in a follow-up).
    ``q_model`` accepted for forward-compat but unused."""
    del q_model
    r = ips_estimate(episodes, target_policy, reward=reward)
    return DRResult(r.mean, r.half_width_95, r.off_support_fraction, r.n)


def cross_validated_dr(
    episodes: Sequence[Episode], target_policy: TargetPolicy, *,
    k_folds: int = 5,
    reward: Callable[[Episode], float] = hitl_agreement_reward,
    seed: int = 0, alpha: float = 1.0,
) -> DRResult:
    """P3 CV-DR alias — falls back to IPS. Forward-compat signature."""
    del k_folds, seed, alpha
    r = ips_estimate(episodes, target_policy, reward=reward)
    return DRResult(r.mean, r.half_width_95, r.off_support_fraction, r.n)


def load_episodes_from_db(
    db_path: Path,
    *,
    sources: Iterable[str] = ("live", "soak"),
) -> list[dict]:
    """Pull episode rows from rl_episodes.db (read-only). Parses
    state_features_json into a dict; matches schema in rl/schema.sql."""
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    uri = f"file:/{db_path.resolve().as_posix().lstrip('/')}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in sources)
    sql = (
        "SELECT episode_id, ts_utc, session_id, trace_id, state_features_json,"
        " action_taken, action_propensity, verdict, confidence, hitl_override,"
        " latency_ms, fr_og_7_pass, budget_violation, source, cycle_tag"
        f" FROM episodes WHERE source IN ({placeholders})"
    )
    rows = conn.execute(sql, tuple(sources)).fetchall()
    conn.close()
    out: list[dict] = []
    for r in rows:
        rec = dict(r)
        try:
            rec["state_features"] = json.loads(rec.pop("state_features_json"))
        except (TypeError, ValueError, json.JSONDecodeError):
            rec["state_features"] = {}
        out.append(rec)
    return out
