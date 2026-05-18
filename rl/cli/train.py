"""v10 P4 — trainer CLI: ``python -m rl.cli.train ...``.

Drives a constrained Thompson-sampling bandit over the 9-bin L4
threshold action space. Writes a proposals JSON (top-3 feasible
candidates by posterior mean) and a reproducibility manifest (seed +
db_sha + hyperparams + per-arm posterior + IPS per candidate).

Exit codes (unix convention):

- 0   baseline retained (no feasible lift OR insufficient confidence).
- 10  feasible candidate beats baseline AND ``best_arm_ci <= 0.10``
       AND ``total_episodes >= 200``.
- 1   trainer error (DB read fail, manifest write fail, etc.).

Outputs are PROPOSALS only — v10.1 NEVER writes them back into gov
config (writeback ships in v10.3, gated by separate ADR-18 amendment).
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from rl.bandit import (
    L4_THRESHOLDS,
    PROMOTION_CI_CAP,
    PROMOTION_N_FLOOR,
    BanditTrainer,
    baseline_arm_index,
)
from rl.constraints import ConstraintBundle, feasible_action_set
from rl.manifest import compute_db_sha, write_manifest
from rl.ope import hitl_agreement_reward, ips_estimate, load_episodes_from_db
from rl.validate import L4_THRESHOLD_KEY, Candidate, validate

EXIT_RETAIN_BASELINE = 0
EXIT_PROMOTE = 10
EXIT_ERROR = 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rl.cli.train")
    p.add_argument("--episodes-db", type=Path, required=True)
    p.add_argument("--baseline-thresholds", type=Path, required=True)
    p.add_argument("--proposals-out", type=Path, required=True)
    p.add_argument("--manifest-out", type=Path, required=True)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--delta", type=float, default=0.02)
    p.add_argument("--cassette", type=Path, default=None)
    p.add_argument("--golden", type=Path, default=None)
    p.add_argument("--probe", type=Path, default=None)
    p.add_argument("--review", type=Path, default=None)
    return p


def _bernoulli_reward(ep) -> int:
    return 1 if hitl_agreement_reward(ep) > 0 else 0


def _candidate_for_arm(arm: int) -> Candidate:
    return Candidate(
        thresholds={L4_THRESHOLD_KEY: float(L4_THRESHOLDS[arm])},
        manifest_sha=f"v10-p4-arm-{arm}", seed=0,
    )


def _filter_self_monitor(rows: list[dict]) -> list[dict]:
    sm = os.environ.get("BRIDGE_SM_SELF_SESSION_ID", "").strip()
    return rows if not sm else [r for r in rows if r.get("session_id") != sm]


def _stage(report, name):
    return next((s for s in report.stages if s.name == name), None)


def _arm_summary(trainer: BanditTrainer, arm: int, thr: float,
                 ips: dict[str, float]) -> dict:
    return {
        "arm": arm,
        "thresholds": {L4_THRESHOLD_KEY: thr},
        "posterior_mean": trainer.posterior_mean(arm),
        "posterior_ci_width_95": trainer.posterior_ci_width(arm),
        "ips": ips.get(f"{thr:.2f}", 0.0),
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    rng = np.random.default_rng(args.seed)

    try:
        baseline = Candidate.from_json(args.baseline_thresholds)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[rl.train] baseline read failed: {exc}", file=sys.stderr)
        return EXIT_ERROR
    baseline_thr = baseline.l4_threshold()
    baseline_arm = baseline_arm_index(baseline_thr)

    try:
        episodes = load_episodes_from_db(
            args.episodes_db, sources=("live", "soak"))
    except (OSError, sqlite3.Error) as exc:
        print(f"[rl.train] DB read failed: {exc}", file=sys.stderr)
        return EXIT_ERROR
    episodes = _filter_self_monitor(episodes)

    trainer = BanditTrainer(baseline_threshold=baseline_thr)
    # Offline replay: sample once per episode; conjugate-update only
    # when the drawn arm matches the arm the episode actually supports.
    # v10.1's deterministic production policy concentrates updates on
    # the baseline arm; off-baseline arms stay at warm-start priors
    # until propensities go stochastic (v10.3+).
    for ep in episodes:
        arm = trainer.sample(rng)
        if arm == baseline_arm_index(float(ep.get("action_taken", baseline_thr))):
            trainer.update(arm, _bernoulli_reward(ep))

    candidates = [_candidate_for_arm(i) for i in range(len(L4_THRESHOLDS))]
    ips_per_candidate: dict[str, float] = {}
    # v10.1: production is deterministic at baseline_thr → only the
    # baseline arm has on-support episodes; IPS for off-baseline arms
    # is structurally 0.0 here (off-support). v10.3+ stochastic
    # propensities will populate these.
    for c in candidates:
        thr = c.l4_threshold()
        ips_per_candidate[f"{thr:.2f}"] = ips_estimate(
            episodes, lambda _s, t=thr: t).mean

    def _vfn(c: Candidate):
        return validate(
            c, baseline, delta=args.delta, db_path=args.episodes_db,
            cassette_path=args.cassette, golden_path=args.golden,
            probe_path=args.probe, review_path=args.review, episodes=episodes,
        )

    base_report = _vfn(baseline)
    s2, s1 = _stage(base_report, "stage_2_ips"), _stage(base_report, "stage_1_golden")
    base_hitl = (float(s2.metrics.get("ips_target", 0.0) or 0.0)
                 if s2 and not s2.metrics.get("skipped") else 0.0)
    if s1 is not None:
        fr_t = int(s1.metrics.get("fr_og_7_total", 0) or 0)
        rg = len(s1.metrics.get("regressions") or [])
        base_pass = (fr_t - rg) / fr_t if fr_t > 0 else 1.0
    else:
        base_pass = 1.0
    bundle = ConstraintBundle(
        fr_og_7_floor=0,
        hitl_agreement_floor=base_hitl - 0.02,
        alignment_pass_rate_floor=base_pass,
    )

    feasible = feasible_action_set(candidates, bundle, _vfn)
    feasible.sort(
        key=lambda c: trainer.posterior_mean(
            baseline_arm_index(c.l4_threshold())), reverse=True)
    proposals = feasible[:3]

    payload = {
        "envelope": "rl_proposals",
        "generated_at": datetime.now(UTC).isoformat(),
        "baseline": _arm_summary(
            trainer, baseline_arm, baseline_thr, ips_per_candidate),
        "proposals": [
            _arm_summary(trainer, baseline_arm_index(p.l4_threshold()),
                         p.l4_threshold(), ips_per_candidate)
            for p in proposals
        ],
        "n_feasible": len(feasible),
        "n_candidates": len(candidates),
        "n_episodes": trainer.total_episodes(),
        "promotion_gate": {
            "n_floor": PROMOTION_N_FLOOR, "ci_cap": PROMOTION_CI_CAP,
            "n_actual": trainer.total_episodes(),
            "best_arm": trainer.best_arm(),
            "best_arm_ci_width_95": trainer.best_arm_posterior_ci(),
            "ready": trainer.is_ready_for_shadow(),
        },
    }
    posterior = {
        f"arm_{i}_thr_{L4_THRESHOLDS[i]:.2f}": {
            "alpha": trainer.alpha[i], "beta": trainer.beta[i],
            "mean": trainer.posterior_mean(i),
            "ci_width_95": trainer.posterior_ci_width(i),
        } for i in range(len(L4_THRESHOLDS))
    }

    try:
        Path(args.proposals_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.proposals_out).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        write_manifest(
            args.manifest_out,
            seed=args.seed,
            db_sha=compute_db_sha(args.episodes_db),
            hyperparams={"alpha_beta_sum": 20.0, "delta": args.delta,
                         "action_space": list(L4_THRESHOLDS)},
            posterior=posterior,
            candidates=[{"arm": i, "l4_threshold": float(L4_THRESHOLDS[i])}
                        for i in range(len(L4_THRESHOLDS))],
            ips_per_candidate=ips_per_candidate,
        )
    except OSError as exc:
        print(f"[rl.train] write failed: {exc}", file=sys.stderr)
        return EXIT_ERROR

    print(f"[rl.train] wrote proposals {args.proposals_out}")
    print(f"[rl.train] wrote manifest  {args.manifest_out}")

    if not proposals:
        return EXIT_RETAIN_BASELINE
    best = proposals[0]
    best_arm = baseline_arm_index(best.l4_threshold())
    if best_arm == baseline_arm or not trainer.is_ready_for_shadow():
        return EXIT_RETAIN_BASELINE
    if (ips_per_candidate[f"{best.l4_threshold():.2f}"]
            <= ips_per_candidate[f"{baseline_thr:.2f}"]):
        print("[rl.train] non-baseline IPS off-support or no lift; retain baseline",
              file=sys.stderr)
        return EXIT_RETAIN_BASELINE
    return EXIT_PROMOTE


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
