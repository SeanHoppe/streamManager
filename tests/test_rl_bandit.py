"""v10 P4 — tests for Beta-Bernoulli Thompson bandit trainer."""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from rl.bandit import L4_THRESHOLDS, BanditTrainer

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_baseline_warm_start_prior():
    """Initial best arm is the baseline arm."""
    trainer = BanditTrainer(baseline_threshold=0.75)
    assert trainer.baseline_arm == 5
    assert trainer.best_arm() == 5


def test_epsilon_tilted_prior():
    """Initial posterior mean by distance: 0=0.70, ±1=~0.55, ±2+=0.50."""
    trainer = BanditTrainer(baseline_threshold=0.75)
    assert trainer.posterior_mean(5) == pytest.approx(0.70, abs=1e-12)
    assert trainer.posterior_mean(4) == pytest.approx(0.55, abs=1e-12)
    assert trainer.posterior_mean(6) == pytest.approx(0.55, abs=1e-12)
    for i in (0, 1, 2, 3, 7, 8):
        assert trainer.posterior_mean(i) == pytest.approx(0.50, abs=1e-12)


def test_update_concentrates_posterior():
    """Feeding 200 successes on one arm shrinks its CI below 0.10."""
    trainer = BanditTrainer(baseline_threshold=0.75)
    for _ in range(200):
        trainer.update(5, 1)
    assert trainer.posterior_ci_width(5) < 0.10


def test_promotion_gate_requires_both_n_and_ci():
    """Gate is conjunctive: n>=200 AND CI<=0.10."""
    # n=199 + tight CI → False (insufficient n).
    trainer = BanditTrainer(baseline_threshold=0.75)
    for _ in range(199):
        trainer.update(5, 1)
    assert trainer.total_episodes() == 199
    assert trainer.best_arm_posterior_ci() < 0.10
    assert trainer.is_ready_for_shadow() is False

    # n=200 + tight CI → True.
    trainer.update(5, 1)
    assert trainer.is_ready_for_shadow() is True

    # n=200 + wide CI → False. Construct directly: Beta(50,50) has
    # width ~0.195 > 0.10.
    t2 = BanditTrainer(baseline_threshold=0.75)
    t2.alpha = [50.0] * len(L4_THRESHOLDS)
    t2.beta = [50.0] * len(L4_THRESHOLDS)
    t2._total = 200
    assert t2.best_arm_posterior_ci() > 0.10
    assert t2.is_ready_for_shadow() is False


def test_thompson_does_not_sample_outside_action_space():
    trainer = BanditTrainer(baseline_threshold=0.75)
    rng = np.random.default_rng(42)
    for _ in range(500):
        arm = trainer.sample(rng)
        assert 0 <= arm < len(L4_THRESHOLDS)


def test_deterministic_with_seed():
    t1 = BanditTrainer(baseline_threshold=0.75)
    t2 = BanditTrainer(baseline_threshold=0.75)
    r1, r2 = np.random.default_rng(123), np.random.default_rng(123)
    assert [t1.sample(r1) for _ in range(50)] == [t2.sample(r2) for _ in range(50)]


def test_trainer_no_direct_subprocess_imports():
    """DOD: AST-level absence of subprocess / anthropic imports in the
    four trainer files (subprocess use is allowed ONLY transitively via
    rl.validate.validate at P3 stage 3)."""
    files = [
        REPO_ROOT / "rl" / "bandit.py",
        REPO_ROOT / "rl" / "constraints.py",
        REPO_ROOT / "rl" / "manifest.py",
        REPO_ROOT / "rl" / "cli" / "train.py",
    ]
    forbidden = {"subprocess", "anthropic"}
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden, \
                        f"{path.name} imports {alias.name!r}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden, \
                    f"{path.name} imports from {node.module!r}"
