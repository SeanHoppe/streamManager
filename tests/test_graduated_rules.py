"""ADR-18 Amendment F — allow-pattern auto-graduation backend tests.

Covers the GraduatedRuleStore (env-flag gate + passthroughs), the
eligibility predicate (invariants #2 + #6), and the verdict-ladder
behaviour: graduated ALLOW fires, the safety floor structurally wins
(invariant #1), a static graduated hit never mutates the probabilistic
graph (invariant #7), and graduated hits never move the mode ladder.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stream_manager.decision_graph import DecisionGraph
from stream_manager.governance import ELIGIBLE_SOURCES, GovDecision, GovernanceEngine
from stream_manager.graduated_rules import (
    CandidateStats,
    GraduatedRuleStore,
    is_eligible,
    is_enabled,
)
from stream_manager.message_bus import MessageBus
from stream_manager.messages import Message
from stream_manager.project_context import ProjectContextSnapshot

ENV_FLAG = "BRIDGE_GRADUATED_RULES"


def _bus(tmp_path: Path) -> MessageBus:
    return MessageBus(str(tmp_path / "gov.db"))


def _ctx() -> ProjectContextSnapshot:
    return ProjectContextSnapshot(repo_path="/tmp/proj")


def _msg(content: str) -> Message:
    return Message.new(role="user", content=content)


def _stats(**kw) -> CandidateStats:
    base = dict(
        shape_hash="h", canonical_text="git status", n_allow=40,
        mean_confidence=0.97, n_override=0, n_block_ever=0, safety_floor=False,
    )
    base.update(kw)
    return CandidateStats(**base)


# ── env flag ─────────────────────────────────────────────────────────


def test_is_enabled_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_FLAG, raising=False)
    assert is_enabled() is False


@pytest.mark.parametrize("val,expected", [
    ("1", True), ("true", True), ("YES", True),
    ("0", False), ("", False), ("off", False),
])
def test_is_enabled_values(monkeypatch, val, expected) -> None:
    monkeypatch.setenv(ENV_FLAG, val)
    assert is_enabled() is expected


# ── eligibility predicate (invariants #2 + #6) ───────────────────────


def test_is_eligible_happy_path() -> None:
    assert is_eligible(_stats()) is True


def test_is_eligible_rejects_safety_floor() -> None:
    # Invariant #2: a safety-floor shape is never eligible, even with
    # otherwise-perfect routine stats.
    assert is_eligible(_stats(safety_floor=True)) is False


def test_is_eligible_rejects_any_block_ever() -> None:
    assert is_eligible(_stats(n_block_ever=1)) is False


def test_is_eligible_rejects_any_override() -> None:
    assert is_eligible(_stats(n_override=1)) is False


def test_is_eligible_rejects_too_few_allow() -> None:
    assert is_eligible(_stats(n_allow=29)) is False


def test_is_eligible_rejects_low_confidence() -> None:
    assert is_eligible(_stats(mean_confidence=0.94)) is False


def test_safety_check_is_superset_of_precheck() -> None:
    # Invariant #2 regression (adversarial review): the candidate-gate safety
    # check (is_safety_priority_content) must be a strict SUPERSET of the
    # precheck. Patterns the precheck blocks but the governance-local regexes
    # alone missed (DROP DATABASE / mkfs / dd-to-raw-device) MUST be flagged,
    # so such a shape can never be offered for graduation.
    from stream_manager.governance import is_safety_priority_content
    from stream_manager.project_context import (
        ProjectContextSnapshot, fast_precheck,
    )
    snap = ProjectContextSnapshot(repo_path="/tmp/proj")
    for danger in ("DROP DATABASE app", "mkfs.ext4 /dev/sda",
                   "dd if=/dev/zero of=/dev/sda"):
        assert is_safety_priority_content(danger), danger
        assert fast_precheck(danger, snap) is not None, danger  # parity


# ── store: env-flag gate + passthroughs ──────────────────────────────


def test_store_lookup_off_returns_none_without_bus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # OFF path must not touch the bus at all. Use a sentinel bus whose any
    # attribute access raises, proving the flag short-circuits first.
    monkeypatch.delenv(ENV_FLAG, raising=False)

    class _Boom:
        def __getattr__(self, _name):  # pragma: no cover - must not run
            raise AssertionError("bus touched on OFF path")

    store = GraduatedRuleStore(bus=_Boom())
    assert store.lookup("anyhash") is None


def test_store_lookup_on_returns_active_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_FLAG, "1")
    bus = _bus(tmp_path)
    store = GraduatedRuleStore(bus=bus)
    bus.insert_graduated_rule("h1", "git status", 1234.0, 42)
    rule = store.lookup("h1")
    assert rule is not None
    assert rule["shape_hash"] == "h1"
    assert rule["n_allow_at_grad"] == 42
    bus.close()


def test_store_demote_stops_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_FLAG, "1")
    bus = _bus(tmp_path)
    store = GraduatedRuleStore(bus=bus)
    bus.insert_graduated_rule("h1", "git status", 1234.0, 42)
    assert store.lookup("h1") is not None
    assert store.demote("h1") is True
    assert store.lookup("h1") is None          # demoted → no short-circuit
    assert store.demote("h1") is False         # already demoted
    bus.close()


# ── verdict ladder ───────────────────────────────────────────────────


def _engine_with_graduated(tmp_path, content: str, monkeypatch):
    """Build an engine whose graph matches `content` and whose
    graduated_rules table has an active rule for that shape."""
    monkeypatch.setenv(ENV_FLAG, "1")
    bus = _bus(tmp_path)
    graph = DecisionGraph()
    pat = graph.observe(content, True)
    bus.insert_graduated_rule(pat.hash, content[:200], 1.0, 50)
    eng = GovernanceEngine(
        project_context=_ctx(), graph=graph, bus=bus,
        graduated_rules=GraduatedRuleStore(bus=bus),
    )
    return eng, bus, pat


def test_graduated_rule_short_circuits_to_allow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    eng, bus, pat = _engine_with_graduated(tmp_path, "git status", monkeypatch)
    d = eng._evaluate_inner_core(_msg("git status"))
    assert d.action == "ALLOW"
    assert d.source == "graduated"
    assert d.confidence == pytest.approx(1.0)
    assert d.matched_hash == pat.hash
    bus.close()


def test_graduated_off_flag_falls_through_to_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # With the flag OFF the store returns None without SQL → the ladder is
    # the pre-amendment ladder (graph branch, source="graph").
    eng, bus, _pat = _engine_with_graduated(tmp_path, "git status", monkeypatch)
    monkeypatch.setenv(ENV_FLAG, "0")
    d = eng._evaluate_inner_core(_msg("git status"))
    assert d.source != "graduated"
    bus.close()


def test_safety_floor_wins_over_graduated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Invariant #1: even if a destructive-shell shape were somehow
    # graduated, fast_precheck returns BEFORE the graduated branch, so it
    # can never be flipped to ALLOW.
    danger = "rm -rf /"
    eng, bus, _pat = _engine_with_graduated(tmp_path, danger, monkeypatch)
    d = eng._evaluate_inner_core(_msg(danger))
    # Precheck OWNS the verdict — the graduated branch was never reached.
    # (In OBSERVE mode the applied action is downgraded to ALLOW for
    # observe-only, but source/original_action prove precheck won the
    # branch; that mode-independent fact is the structural safety floor.)
    assert d.source == "precheck"
    assert d.source != "graduated"
    assert d.original_action == "BLOCK"
    bus.close()


# ── invariant #7: no judgment-signal leak ────────────────────────────


def test_graduated_source_excluded_from_eligible_sources() -> None:
    assert "graduated" not in ELIGIBLE_SOURCES


def test_graduated_feedback_does_not_mutate_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Invariant #7: a static graduated hit must NOT feed graph.feedback()
    # (which would mutate the probabilistic pattern's success tracking).
    bus = _bus(tmp_path)
    graph = DecisionGraph()
    pat = graph.observe("git status", True)
    before_occ = pat.occurrences
    eng = GovernanceEngine(project_context=_ctx(), graph=graph, bus=bus)
    grad = GovDecision(action="ALLOW", confidence=1.0, reasoning="g",
                       mode=eng.mode, matched_hash=pat.hash, source="graduated")
    eng.feedback(grad, was_correct=False)
    assert graph.patterns[pat.hash].occurrences == before_occ  # unchanged
    # A graph-source decision with the same hash DOES mutate it (control).
    graphd = GovDecision(action="ALLOW", confidence=0.9, reasoning="g",
                         mode=eng.mode, matched_hash=pat.hash, source="graph")
    eng.feedback(graphd, was_correct=True)
    assert graph.patterns[pat.hash].occurrences == before_occ + 1
    bus.close()


def test_graduated_feedback_does_not_move_mode_ladder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Invariant #7: graduated hits carry no judgment signal → the rolling
    # accuracy window is untouched, so a stream of them cannot ramp the mode.
    bus = _bus(tmp_path)
    eng = GovernanceEngine(project_context=_ctx(), graph=DecisionGraph(), bus=bus)
    for _ in range(20):
        grad = GovDecision(action="ALLOW", confidence=1.0, reasoning="g",
                           mode=eng.mode, matched_hash="h", source="graduated")
        eng.feedback(grad, was_correct=True)
    assert len(eng._eligible_window) == 0
    bus.close()
