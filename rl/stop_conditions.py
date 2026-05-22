"""v10 P5 — Pre-registered ship-criteria checker. Six criteria, frozen.
NOT relaxed at evaluation time. If unmet after 3 retrains × 3 shadows,
v10 enters DORMANT-N per ADR-18 Rule 2."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from rl.manifest import read_manifest
from rl.validate import Candidate

# Pre-registered constants — not environment-overridable.
SHADOW_REWARD_DELTA = 0.02
SHADOW_REWARD_WINDOW = 3
FR_OG_7_VIOLATION_FLOOR = 0
HITL_AGREEMENT_DELTA = 0.02
POSTERIOR_CI_CAP = 0.10
PARAMETER_DRIFT_CAP = 0.02
PARAMETER_DRIFT_WINDOW = 3


@dataclass(frozen=True)
class ShipCriteria:
    shadow_reward_delta: float = SHADOW_REWARD_DELTA
    shadow_reward_window: int = SHADOW_REWARD_WINDOW
    fr_og_7_violation_floor: int = FR_OG_7_VIOLATION_FLOOR
    hitl_agreement_delta: float = HITL_AGREEMENT_DELTA
    posterior_ci_cap: float = POSTERIOR_CI_CAP
    parameter_drift_cap: float = PARAMETER_DRIFT_CAP
    parameter_drift_window: int = PARAMETER_DRIFT_WINDOW


@dataclass
class CriterionResult:
    name: str
    passed: bool
    detail: str
    metrics: dict = field(default_factory=dict)


@dataclass
class CriteriaReport:
    criteria: list[CriterionResult] = field(default_factory=list)

    @property
    def overall_passed(self) -> bool:
        return bool(self.criteria) and all(c.passed for c in self.criteria)

    def to_dict(self) -> dict:
        return {"overall_passed": self.overall_passed,
                "criteria": [{"name": c.name, "passed": c.passed,
                              "detail": c.detail, "metrics": c.metrics}
                             for c in self.criteria]}


def _open_ro(db: Path) -> sqlite3.Connection:
    uri = f"file:/{db.resolve().as_posix().lstrip('/')}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _last_runs(shadow_db: Path, window: int):
    db = Path(shadow_db)
    if not db.exists():
        return [], {}
    conn = _open_ro(db)
    try:
        ids = [str(r["soak_run_id"]) for r in conn.execute(
            "SELECT soak_run_id, MAX(ts_utc) AS last_ts FROM shadow_episodes"
            " GROUP BY soak_run_id ORDER BY last_ts DESC LIMIT ?",
            (int(window),)).fetchall()]
        return ids, {rid: conn.execute(
            "SELECT * FROM shadow_episodes WHERE soak_run_id = ?", (rid,)
        ).fetchall() for rid in ids}
    finally:
        conn.close()


def _gt(r: sqlite3.Row) -> str | None:
    if not int(r["ground_truth_known"]) or r["ground_truth_verdict"] is None:
        return None
    return str(r["ground_truth_verdict"])


def _reward_means(rows: Iterable[sqlite3.Row]) -> tuple[float, float, int]:
    cand = prod = 0.0
    n = 0
    for r in rows:
        gt = _gt(r)
        if gt is None:
            continue
        cand += 1.0 if str(r["candidate_verdict"]) == gt else 0.0
        prod += 1.0 if str(r["production_verdict"]) == gt else 0.0
        n += 1
    return (cand / n, prod / n, n) if n else (0.0, 0.0, 0)


def _agree_rate(rows: Iterable[sqlite3.Row]) -> float:
    n = pos = 0
    for r in rows:
        n += 1
        pos += 1 if int(r["agree"]) == 1 else 0
    return pos / n if n else 0.0


def _fr_og_7(rows: Iterable[sqlite3.Row]) -> int:
    return sum(1 for r in rows
               if (gt := _gt(r)) is not None and str(r["candidate_verdict"]) != gt)


def _pass_rate(rows: Iterable[sqlite3.Row], field_: str) -> float:
    total = ok = 0
    for r in rows:
        gt = _gt(r)
        if gt is None:
            continue
        total += 1
        if str(r[field_]) == gt:
            ok += 1
    return ok / total if total else 1.0


def _last_manifests(manifest_dir: Path, window: int) -> list[dict]:
    base = Path(manifest_dir)
    if not base.exists():
        return []
    files = sorted(base.glob("*.manifest.json"),
                   key=lambda p: p.name, reverse=True)[:int(window)]
    return [read_manifest(p) for p in files]


def _best_arm(manifest: dict) -> tuple[float | None, float | None]:
    posterior = manifest.get("posterior") or {}
    candidates = manifest.get("candidates") or []
    best_name = None
    best_mean: float | None = None
    for name, payload in posterior.items():
        try:
            m = float(payload["mean"])
        except (KeyError, TypeError, ValueError):
            continue
        if best_mean is None or m > best_mean:
            best_mean, best_name = m, name
    if best_name is None:
        return None, None
    payload = posterior[best_name]
    try:
        ci = float(payload["ci_width_95"])
    except (KeyError, TypeError, ValueError):
        ci = None
    thr: float | None = None
    try:
        idx = int(best_name.split("_")[1])
        for c in candidates:
            if int(c.get("arm", -1)) == idx:
                thr = float(c["l4_threshold"])
                break
    except (ValueError, KeyError, IndexError):
        pass
    return ci, thr


def evaluate_criteria(
    shadow_db: Path, manifest_dir: Path, baseline: Candidate,
    *, criteria: ShipCriteria | None = None,
) -> CriteriaReport:
    spec = criteria or ShipCriteria()
    report = CriteriaReport()
    run_ids, by_run = _last_runs(shadow_db, spec.shadow_reward_window)

    def emit(name: str, passed: bool, detail: str, **metrics) -> None:
        report.criteria.append(CriterionResult(name, passed, detail, metrics))

    # 1. shadow reward improvement
    if len(run_ids) < spec.shadow_reward_window:
        emit("shadow_reward_improvement", False,
             f"insufficient shadow runs: have {len(run_ids)},"
             f" need {spec.shadow_reward_window}", n_runs=len(run_ids))
    else:
        deltas = [(c := _reward_means(by_run[rid]))[0] - c[1]
                  for rid in run_ids]
        emit("shadow_reward_improvement",
             all(d + 1e-12 >= spec.shadow_reward_delta for d in deltas),
             f"per-run reward delta = {[round(d, 4) for d in deltas]};"
             f" floor +{spec.shadow_reward_delta}", deltas=deltas)

    # 2. FR-OG-7 violations
    if not run_ids:
        emit("fr_og_7_violations", False,
             "insufficient shadow runs: have 0", n_runs=0)
    else:
        per_run = {rid: _fr_og_7(by_run[rid]) for rid in run_ids}
        total = sum(per_run.values())
        emit("fr_og_7_violations", total <= spec.fr_og_7_violation_floor,
             f"per-run candidate FR-OG-7 violations = {per_run};"
             f" floor {spec.fr_og_7_violation_floor}",
             per_run=per_run, total=total)

    # 3. HITL agreement
    if not run_ids:
        emit("hitl_agreement", False,
             "insufficient shadow runs: have 0", n_runs=0)
    else:
        rates = {rid: _agree_rate(by_run[rid]) for rid in run_ids}
        floor = 1.0 - spec.hitl_agreement_delta
        emit("hitl_agreement",
             all(r + 1e-12 >= floor for r in rates.values()),
             f"per-run HITL agreement = "
             f"{ {k: round(v, 4) for k, v in rates.items()} };"
             f" floor 1 - {spec.hitl_agreement_delta}",
             per_run=rates, floor=floor)

    # 4. alignment-eval pass rate
    if not run_ids:
        emit("alignment_pass_rate", False,
             "insufficient shadow runs: have 0", n_runs=0)
    else:
        pairs = {rid: (_pass_rate(by_run[rid], "candidate_verdict"),
                       _pass_rate(by_run[rid], "production_verdict"))
                 for rid in run_ids}
        emit("alignment_pass_rate",
             all(c + 1e-12 >= b for c, b in pairs.values()),
             f"per-run (candidate, baseline) pass = "
             f"{ {k: (round(c, 4), round(b, 4)) for k, (c, b) in pairs.items()} }",
             per_run=pairs)

    manifests = _last_manifests(manifest_dir, spec.parameter_drift_window)

    # 5. posterior CI on best arm
    if not manifests:
        emit("posterior_ci", False, "no manifests available", n_manifests=0)
    else:
        ci, _ = _best_arm(manifests[0])
        if ci is None:
            emit("posterior_ci", False,
                 "best-arm CI missing in latest manifest")
        else:
            emit("posterior_ci", ci <= spec.posterior_ci_cap + 1e-12,
                 f"latest best-arm CI = {ci:.4f};"
                 f" cap {spec.posterior_ci_cap}", ci_width_95=ci)

    # 6. parameter drift across last `window` retrains
    if len(manifests) < spec.parameter_drift_window:
        emit("parameter_drift", False,
             f"insufficient retrains: have {len(manifests)},"
             f" need {spec.parameter_drift_window}",
             n_retrains=len(manifests))
    else:
        thrs = [_best_arm(m)[1] for m in manifests]
        if any(t is None for t in thrs):
            emit("parameter_drift", False,
                 "best-arm threshold missing in one or more manifests",
                 thresholds=thrs)
        else:
            deltas = [abs(float(thrs[i]) - float(thrs[i + 1]))
                      for i in range(len(thrs) - 1)]
            emit("parameter_drift",
                 all(d <= spec.parameter_drift_cap + 1e-12 for d in deltas),
                 f"consecutive |Δθ| = {[round(d, 4) for d in deltas]};"
                 f" cap {spec.parameter_drift_cap}",
                 thresholds=thrs, deltas=deltas)

    return report
