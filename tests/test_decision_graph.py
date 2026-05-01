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


def test_promoted_pattern_continues_to_match_same_content() -> None:
    g = DecisionGraph()
    for _ in range(10):
        g.observe("pytest tests/", success=True)
    content_patterns = [p for p in g.patterns.values() if "pytest" in p.canonical_text]
    assert len(content_patterns) == 1, (
        "promoted patterns must keep matching their own content "
        f"(got {len(content_patterns)} fragments: {[(p.level.name, p.occurrences) for p in content_patterns]})"
    )
    assert content_patterns[0].occurrences == 10


def test_pattern_chain_promotes_through_levels() -> None:
    g = DecisionGraph()
    for _ in range(5):
        g.observe("git status", success=True)
    content = [p for p in g.patterns.values() if "git" in p.canonical_text]
    levels = {p.level for p in content}
    assert PatternLevel.L2 in levels, (
        f"5 same-content observations should chain L0->L1->L2; got levels {levels}"
    )


# ---------------------------------------------------------------------------
# Persistence — save / load
# ---------------------------------------------------------------------------


def test_save_load_round_trips_all_fields(tmp_path) -> None:
    db = str(tmp_path / "graph.db")
    g = DecisionGraph()
    for _ in range(3):
        g.observe("pytest tests/", True)
    g.observe("git status", False)
    g.save(db)

    g2 = DecisionGraph.load(db)
    assert len(g2.patterns) == len(g.patterns)
    for h, p in g.patterns.items():
        assert h in g2.patterns
        p2 = g2.patterns[h]
        assert p2.occurrences == p.occurrences
        assert p2.successes == p.successes
        assert p2.level == p.level
        assert abs(p2.last_seen - p.last_seen) < 1e-6
        assert p2.canonical_text == p.canonical_text


def test_load_missing_db_returns_empty_graph(tmp_path) -> None:
    g = DecisionGraph.load(str(tmp_path / "nonexistent.db"))
    assert len(g.patterns) == 0


def test_load_missing_table_returns_empty_graph(tmp_path) -> None:
    import sqlite3
    db = str(tmp_path / "empty.db")
    sqlite3.connect(db).close()  # valid DB, no graph_patterns table
    g = DecisionGraph.load(db)
    assert len(g.patterns) == 0


def test_save_upserts_incremented_counts(tmp_path) -> None:
    db = str(tmp_path / "graph.db")
    g = DecisionGraph()
    g.observe("pytest tests/", True)
    g.save(db)

    g.observe("pytest tests/", True)
    g.save(db)

    g2 = DecisionGraph.load(db)
    pat = next(p for p in g2.patterns.values() if "pytest" in p.canonical_text)
    assert pat.occurrences == 2
    assert pat.successes == 2


def test_save_preserves_promoted_level(tmp_path) -> None:
    db = str(tmp_path / "graph.db")
    g = DecisionGraph()
    for _ in range(PROMOTION_THRESHOLDS[0]):  # L0 threshold
        g.observe("ruff check .", True)
    g.save(db)

    g2 = DecisionGraph.load(db)
    pat = next(p for p in g2.patterns.values() if "ruff" in p.canonical_text)
    assert pat.level >= PatternLevel.L1


def test_save_preserves_sequence_children(tmp_path) -> None:
    db = str(tmp_path / "graph.db")
    g = DecisionGraph()
    # Observe same pair twice to materialize a sequence pattern
    for _ in range(2):
        g.observe("git add .", True)
        g.observe("git commit -m x", True)
    g.save(db)

    g2 = DecisionGraph.load(db)
    seq_patterns = [p for p in g2.patterns.values() if p.children]
    assert seq_patterns, "sequence pattern with children should persist"
    assert len(seq_patterns[0].children) == 2
