"""v10 P2 — tests for rl.sources.golden (HOLDOUT)."""

from __future__ import annotations

import pytest

from rl.corpus_augment import GoldenInTrainingError, assemble_training_set
from rl.sources import Episode
from rl.sources.golden import DEFAULT_GOLDEN, iter_episodes


def test_golden_size() -> None:
    """alignment_eval golden has exactly 32 rows (frozen v1.7 P1)."""
    assert len(list(iter_episodes(DEFAULT_GOLDEN))) == 32


def test_golden_hitl_override_is_null() -> None:
    """Golden is labelled-expected (NOT HITL) — every ep has hitl_override IS NULL."""
    eps = list(iter_episodes(DEFAULT_GOLDEN))
    assert eps
    assert all(ep.hitl_override is None and ep.source == "golden"
               and ep.cycle_tag == "alignment-golden" for ep in eps)


def test_golden_holdout_assertion_in_augmenter() -> None:
    """include_golden=True raises GoldenInTrainingError."""
    with pytest.raises(GoldenInTrainingError):
        assemble_training_set(target_n=10, include_golden=True)


def test_golden_extra_episodes_path_blocked() -> None:
    """Threading golden through extra_episodes also raises."""
    eps = list(iter_episodes(DEFAULT_GOLDEN))
    assert eps
    with pytest.raises(GoldenInTrainingError):
        assemble_training_set(target_n=5, extra_episodes=[eps[0]])


def test_golden_fields_complete() -> None:
    """v10 schema parity for golden episodes."""
    for ep in iter_episodes(DEFAULT_GOLDEN):
        assert isinstance(ep, Episode)
        assert ep.verdict in ("ALLOW", "SUGGEST", "INTERVENE", "BLOCK", "AMBIGUOUS")
        assert ep.confidence == 1.0 and ep.action_propensity == 1.0
        assert ep.fr_og_7_pass == 1
