"""v10 P2 — tests for rl.sources.review.

The review adapter (caveman-review findings JSONL, path via
``BRIDGE_RL_REVIEW_FINDINGS``) is a P2 corpus-augmentation source, a
sibling of cassette / probe / golden. It is currently a deferred stub
that yields zero episodes. These tests lock in that behavior AND guard
against the prior phase-scope conflation that mislabeled the module as a
"P5 stub" (P5 = the shadow A/B harness in rl/shadow.py +
rl/stop_conditions.py, unrelated to corpus augmentation).
"""

from __future__ import annotations

from pathlib import Path

import rl.sources.review as review_mod
from rl.sources import Episode
from rl.sources.review import iter_episodes


def test_iter_episodes_yields_zero_when_unconfigured() -> None:
    eps = list(iter_episodes())
    assert eps == []


def test_iter_episodes_yields_zero_for_missing_findings_path() -> None:
    eps = list(iter_episodes(Path("does-not-exist-review-findings.jsonl")))
    assert eps == []


def test_iter_episodes_return_type_is_episode_iterator() -> None:
    # Stub yields nothing today, but the declared element type must stay
    # Episode so the augmenter import path is stable.
    for ep in iter_episodes():
        assert isinstance(ep, Episode)


def test_docstring_phase_scope_is_p2_not_p5() -> None:
    doc = review_mod.__doc__ or ""
    # Module belongs to P2 corpus augmentation, not the P5 shadow harness.
    assert "v10 P2" in doc
    assert "P5 stub" not in doc
