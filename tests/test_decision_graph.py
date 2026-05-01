from __future__ import annotations

from stream_manager.decision_graph import (
    PROMOTION_THRESHOLDS,
    DecisionGraph,
    PatternLevel,
    cosine,
    project,
)


def test_project_returns_normalized_vector() -> None:
    v = project("git status")
    assert len(v) == 64
    norm_sq = sum(x * x for x in v)
    assert abs(norm_sq - 1.0) < 1e-9


def test_cosine_self_similarity_is_one() -> None:
    v = project("pytest tests/")
    assert abs(cosine(v, v) - 1.0) < 1e-9


def test_dissimilar_strings_have_low_cosine() -> None:
    a = project("git status")
    b = project("DROP DATABASE production")
    assert cosine(a, b) < 0.5


def test_repeated_observation_promotes_l0_to_l1() -> None:
    g = DecisionGraph()
    threshold = PROMOTION_THRESHOLDS[PatternLevel.L0]
    for _ in range(threshold):
        g.observe("git status", success=True)
    matches = [p for p in g.patterns.values() if "git" in p.canonical_text]
    assert any(p.level == PatternLevel.L1 for p in matches)


def test_low_success_rate_blocks_promotion() -> None:
    g = DecisionGraph()
    threshold = PROMOTION_THRESHOLDS[PatternLevel.L0]
    for i in range(threshold + 1):
        g.observe("git push --force", success=(i == 0))
    matches = [p for p in g.patterns.values() if "force" in p.canonical_text]
    assert all(p.level == PatternLevel.L0 for p in matches), (
        "should not promote when success_rate < 0.55"
    )


def test_sequence_pattern_emerges_in_window() -> None:
    g = DecisionGraph()
    for _ in range(3):
        g.observe("git diff", success=True)
        g.observe("git commit -m wip", success=True)
    sequences = [p for p in g.patterns.values() if p.canonical_text.startswith("sequence:")]
    assert sequences, "expected at least one L1 sequence pattern"


def test_singleton_sequences_do_not_materialize() -> None:
    g = DecisionGraph()
    g.observe("apple bread", success=True)
    g.observe("zebra glow", success=True)
    sequences = [p for p in g.patterns.values() if p.canonical_text.startswith("sequence:")]
    assert sequences == [], "single observation must stay in the candidates dict"
    assert g.stats()["sequence_candidates"] >= 1


def test_sequences_materialize_on_second_observation() -> None:
    g = DecisionGraph()
    g.observe("alpha widget", success=True)
    g.observe("beta sprocket", success=True)
    g.observe("alpha widget", success=True)
    g.observe("beta sprocket", success=True)
    sequences = [p for p in g.patterns.values() if p.canonical_text.startswith("sequence:")]
    materialized = [p for p in sequences if p.occurrences >= 2]
    assert materialized, "sequence seen twice must be materialized as a Pattern"


def test_match_returns_existing_pattern_when_similar(tmp_path) -> None:  # type: ignore[no-untyped-def]
    g = DecisionGraph()
    g.observe("git status", success=True)
    m = g.match("git status")
    assert m is not None
    assert "git" in m.canonical_text
