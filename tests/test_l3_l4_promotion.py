"""L3/L4 promotion validation (POC item #5).

The 70-msg synthetic POC fixture only exercised L0–L2; the production
ladder reaches L4 at 20 occurrences of a single content pattern. These
tests drive enough observations to chain through every level and assert
the architectural invariants at scale.
"""

from __future__ import annotations

import random

from stream_manager.decision_graph import (
    PROMOTION_THRESHOLDS,
    DecisionGraph,
    MIN_SUCCESS_RATE,
    PatternLevel,
)
from stream_manager.governance import GovernanceEngine, Mode
from stream_manager.messages import Message
from stream_manager.project_context import ProjectContextSnapshot


def test_chain_promotes_to_l3_at_threshold() -> None:
    g = DecisionGraph()
    threshold_to_l3 = PROMOTION_THRESHOLDS[PatternLevel.L2]  # 10
    for _ in range(threshold_to_l3):
        g.observe("npm run build", success=True)
    content = [p for p in g.patterns.values() if "npm" in p.canonical_text]
    assert len(content) == 1
    assert content[0].level == PatternLevel.L3
    assert content[0].occurrences == threshold_to_l3


def test_chain_promotes_to_l4_at_threshold() -> None:
    g = DecisionGraph()
    threshold_to_l4 = PROMOTION_THRESHOLDS[PatternLevel.L3]  # 20
    for _ in range(threshold_to_l4):
        g.observe("docker compose up", success=True)
    content = [p for p in g.patterns.values() if "docker" in p.canonical_text]
    assert len(content) == 1
    assert content[0].level == PatternLevel.L4
    assert content[0].occurrences == threshold_to_l4


def test_l4_is_terminal() -> None:
    """Once L4, additional observations don't break or escalate further."""
    g = DecisionGraph()
    for _ in range(40):
        g.observe("kubectl get pods", success=True)
    content = [p for p in g.patterns.values() if "kubectl" in p.canonical_text]
    assert content[0].level == PatternLevel.L4
    assert content[0].occurrences == 40


def test_low_success_rate_throughout_blocks_all_promotions() -> None:
    """If success_rate stays below MIN_SUCCESS_RATE at every step where the
    occurrence threshold is met, the pattern must stick at L0.

    Promotion is sticky once granted, so the test is sensitive to whether
    rate ever crosses 0.55 at a checkpoint. This sequence is ordered to
    keep rate ≤ 0.5 throughout the L0→L1 window.
    """
    g = DecisionGraph()
    pattern = [False, False, False, False, True, True, True, True, False, False]
    for s in pattern:
        g.observe("flaky integration test", success=s)
    content = [p for p in g.patterns.values() if "flaky" in p.canonical_text]
    assert content
    for p in content:
        assert p.success_rate < MIN_SUCCESS_RATE
        assert p.level == PatternLevel.L0


def test_long_multisession_holds_sub_linear_growth() -> None:
    """Synthetic 600-msg multi-session fixture.

    8 distinct routine commands rotate through with tiny noise. Total
    distinct content shapes stay bounded; pattern count must too.
    """
    rng = random.Random(42)
    routines = [
        "git status",
        "git diff",
        "pytest tests/",
        "npm run build",
        "docker compose up",
        "kubectl get pods",
        "ls -la",
        "cat README.md",
    ]

    g = DecisionGraph()
    snap = ProjectContextSnapshot(repo_path="/x")
    engine = GovernanceEngine(project_context=snap)

    n = 600
    for i in range(n):
        content = routines[i % len(routines)]
        # Light noise to ensure the cosine match logic, not exact-string memo.
        if rng.random() < 0.1:
            content = content + " "
        msg = Message.new("user", content)
        d = engine.evaluate(msg)
        engine.feedback(d, was_correct=True)
        engine.observe_for_learning(msg, success=True)

    ratio = len(engine.graph.patterns) / n
    assert ratio < 1.0, f"sub-linear growth violated: {ratio}"

    levels = {int(p.level): 0 for p in engine.graph.patterns.values()}
    for p in engine.graph.patterns.values():
        levels[int(p.level)] = levels.get(int(p.level), 0) + 1
    # With 600 obs / 8 routines (~75 per routine), every routine reaches L4
    # via the 20-occurrence threshold. We assert at least one L4 emerges.
    l4_patterns = [p for p in engine.graph.patterns.values() if p.level == PatternLevel.L4]
    assert l4_patterns, f"600 obs across 8 routines should yield L4 patterns; got {levels}"

    # Mode promotion should NOT happen — all decisions are routine ALLOWs
    # via default-allow (graph-source low-confidence) so they don't enter the
    # eligible window. Mode stays OBSERVE.
    assert engine.mode == Mode.OBSERVE


def test_long_session_does_not_promote_mode_on_routine_traffic() -> None:
    """Item #2 hardening: 600 successful routine ALLOWs must not ramp mode.

    Pre-fix this would have walked OBSERVE→SUGGEST→GUIDE→INTERVENE→BLOCK.
    """
    snap = ProjectContextSnapshot(repo_path="/x")
    engine = GovernanceEngine(project_context=snap)
    for _ in range(600):
        msg = Message.new("user", "git status")
        d = engine.evaluate(msg)
        engine.feedback(d, was_correct=True)
    assert engine.mode == Mode.OBSERVE
