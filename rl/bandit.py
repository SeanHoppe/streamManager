"""v10 P4 — Beta-Bernoulli Thompson sampler with baseline-warm-start.

Action space: 9 L4 threshold bins (0.50…0.90, step 0.05). Each arm has
a ``Beta(α, β)`` posterior with the ε-tilt warm-start prior — Beta(14,
6) at the baseline arm, Beta(11, 9) at ±1 step, Beta(10, 10) at ±2 or
more (prior totals satisfy ``α + β = 20``).

Promotion to v10 P5 shadow requires BOTH ``total_episodes >= 200`` AND
``best_arm_posterior_ci() <= 0.10``. Posterior CIs use the Wald
(Normal) approximation; scipy is intentionally NOT a project dep.
"""

from __future__ import annotations

import math

import numpy as np

L4_THRESHOLDS: tuple[float, ...] = (
    0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90,
)
ALPHA_BETA_SUM = 20.0
PROMOTION_N_FLOOR = 200
PROMOTION_CI_CAP = 0.10
_Z_95 = 1.959963984540054


def baseline_arm_index(baseline_threshold: float) -> int:
    """Snap a continuous L4 threshold to the nearest of the 9 bins."""
    return min(range(len(L4_THRESHOLDS)),
               key=lambda i: abs(L4_THRESHOLDS[i] - baseline_threshold))


def epsilon_tilted_prior(arm: int, baseline_arm: int) -> tuple[float, float]:
    """ε-tilt warm-start prior; ``(alpha, beta)`` summing to 20."""
    dist = abs(arm - baseline_arm)
    if dist == 0:
        return (14.0, 6.0)
    if dist == 1:
        return (11.0, 9.0)
    return (10.0, 10.0)


class BanditTrainer:
    """Constrained Thompson sampler over the 9-bin L4 action space.

    Conjugate Bernoulli update: ``α += reward; β += (1 - reward)``.
    """

    def __init__(self, baseline_threshold: float) -> None:
        self.baseline_arm = baseline_arm_index(baseline_threshold)
        priors = [epsilon_tilted_prior(i, self.baseline_arm)
                  for i in range(len(L4_THRESHOLDS))]
        self.alpha: list[float] = [a for a, _ in priors]
        self.beta: list[float] = [b for _, b in priors]
        self._total = 0

    def update(self, arm: int, reward: int) -> None:
        if not 0 <= arm < len(L4_THRESHOLDS):
            raise IndexError(f"arm {arm!r} outside 0..{len(L4_THRESHOLDS) - 1}")
        if reward not in (0, 1):
            raise ValueError(f"reward must be 0 or 1; got {reward!r}")
        if reward == 1:
            self.alpha[arm] += 1.0
        else:
            self.beta[arm] += 1.0
        self._total += 1

    def sample(self, rng: np.random.Generator) -> int:
        draws = np.array([
            float(rng.beta(self.alpha[i], self.beta[i]))
            for i in range(len(L4_THRESHOLDS))
        ])
        return int(np.argmax(draws))

    def posterior_mean(self, arm: int) -> float:
        a, b = self.alpha[arm], self.beta[arm]
        return a / (a + b)

    def posterior_ci_width(self, arm: int, level: float = 0.95) -> float:
        """Wald (Normal-approx) Beta CI width. Only ``level=0.95`` supported."""
        if abs(level - 0.95) > 1e-9:
            raise NotImplementedError("v10 P4 supports level=0.95 only")
        a, b = self.alpha[arm], self.beta[arm]
        n = a + b
        stderr = math.sqrt((a * b) / (n * n * (n + 1.0)))
        return float(2.0 * _Z_95 * stderr)

    def best_arm(self) -> int:
        means = [self.posterior_mean(i) for i in range(len(L4_THRESHOLDS))]
        return int(np.argmax(np.array(means)))

    def best_arm_posterior_ci(self) -> float:
        return self.posterior_ci_width(self.best_arm())

    def total_episodes(self) -> int:
        return self._total

    def is_ready_for_shadow(self) -> bool:
        return (self._total >= PROMOTION_N_FLOOR
                and self.best_arm_posterior_ci() <= PROMOTION_CI_CAP)
