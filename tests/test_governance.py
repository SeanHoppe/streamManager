from __future__ import annotations

from stream_manager.governance import (
    MIN_INTERVENTIONS_FOR_PROMOTE,
    ROLLING_WINDOW,
    GovDecision,
    GovernanceEngine,
    Mode,
)
from stream_manager.messages import Message
from stream_manager.project_context import ProjectContextSnapshot


def _engine() -> GovernanceEngine:
    return GovernanceEngine(project_context=ProjectContextSnapshot(repo_path="/tmp"))


def _allow_eligible(mode: Mode = Mode.OBSERVE) -> GovDecision:
    return GovDecision(
        action="ALLOW",
        confidence=0.8,
        reasoning="graph match",
        mode=mode,
        source="graph",
    )


def _intervene_eligible(mode: Mode = Mode.OBSERVE) -> GovDecision:
    return GovDecision(
        action="ALLOW",
        confidence=0.95,
        reasoning="observed: would intervene",
        mode=mode,
        source="precheck",
        original_action="INTERVENE",
    )


def _default_allow(mode: Mode = Mode.OBSERVE) -> GovDecision:
    return GovDecision(
        action="ALLOW",
        confidence=0.1,
        reasoning="default allow",
        mode=mode,
        source="default",
    )


def test_default_source_decisions_do_not_advance_mode() -> None:
    engine = _engine()
    for _ in range(50):
        engine.feedback(_default_allow(), was_correct=True)
    assert engine.mode == Mode.OBSERVE
    assert engine.stats()["eligible_decisions_in_window"] == 0


def test_eligible_allows_alone_do_not_promote_without_interventions() -> None:
    engine = _engine()
    for _ in range(ROLLING_WINDOW * 3):
        engine.feedback(_allow_eligible(), was_correct=True)
    assert engine.mode == Mode.OBSERVE, (
        "all eligible-and-correct ALLOWs without interventions must not promote"
    )


def test_promotion_requires_min_interventions_in_window() -> None:
    engine = _engine()
    # 9 eligible ALLOWs + 1 eligible intervention attempt = 1 intervention < 3 threshold
    for _ in range(9):
        engine.feedback(_allow_eligible(), was_correct=True)
    engine.feedback(_intervene_eligible(), was_correct=True)
    assert engine.mode == Mode.OBSERVE
    assert engine.stats()["interventions_in_window"] == 1


def test_promotion_fires_when_threshold_met() -> None:
    engine = _engine()
    for _ in range(7):
        engine.feedback(_allow_eligible(), was_correct=True)
    for _ in range(MIN_INTERVENTIONS_FOR_PROMOTE):
        engine.feedback(_intervene_eligible(), was_correct=True)
    assert engine.mode == Mode.SUGGEST
    stats = engine.stats()
    assert stats["interventions_in_window"] == MIN_INTERVENTIONS_FOR_PROMOTE


def test_demotion_on_low_eligible_accuracy() -> None:
    engine = _engine()
    engine.mode = Mode.SUGGEST
    for _ in range(ROLLING_WINDOW):
        engine.feedback(_allow_eligible(mode=Mode.SUGGEST), was_correct=False)
    assert engine.mode == Mode.OBSERVE


def test_evaluate_returns_default_source_for_novel_content() -> None:
    engine = _engine()
    decision = engine.evaluate(Message.new("user", "completely novel content nothing risky"))
    assert decision.source == "default"
    assert decision.action == "ALLOW"


def test_evaluate_returns_precheck_source_for_destructive_command() -> None:
    engine = _engine()
    decision = engine.evaluate(Message.new("user", "rm -rf / --no-preserve-root"))
    assert decision.source == "precheck"
    assert decision.action == "ALLOW", "OBSERVE mode must downgrade BLOCK to ALLOW"
    assert decision.original_action == "BLOCK"


def test_full_block_mode_reaches_block_only_with_sustained_intervention_pressure() -> None:
    engine = _engine()
    # Need 4 promotions: OBSERVE -> SUGGEST -> GUIDE -> INTERVENE -> BLOCK.
    # Each promotion needs ROLLING_WINDOW eligible and >= 3 interventions in window.
    # Feed sustained mixed traffic to verify the ladder STILL works under
    # pressure (not just that the gate blocks routine traffic).
    for _ in range(60):
        engine.feedback(_intervene_eligible(mode=engine.mode), was_correct=True)
    assert engine.mode == Mode.BLOCK
