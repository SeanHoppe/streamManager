from __future__ import annotations

from pathlib import Path

from stream_manager.governance import GovernanceEngine, Mode
from stream_manager.project_context import ProjectContextSnapshot
from stream_manager.transcript_loader import load_transcript

FIXTURE = Path(__file__).parent / "fixtures" / "mini_session.jsonl"


def test_loader_filters_to_user_assistant_messages() -> None:
    events = load_transcript(FIXTURE)
    # 9 events in fixture, 1 is queue-operation, 8 are user/assistant.
    # All 8 carry non-empty content after extraction.
    assert len(events) == 8
    roles = [e.message.role for e in events]
    assert roles.count("user") == 4
    assert roles.count("assistant") == 4


def test_loader_infers_success_from_following_tool_result() -> None:
    events = load_transcript(FIXTURE)
    assistants = [e for e in events if e.message.role == "assistant"]
    # First assistant emits tool_use → next user has is_error=false → success=True.
    assert assistants[0].has_signal is True
    assert assistants[0].success is True
    # Third assistant (index 2) emits tool_use → is_error=true → success=False.
    assert assistants[2].has_signal is True
    assert assistants[2].success is False


def test_replay_through_engine_holds_targets_on_real_shape() -> None:
    """Even on a tiny fixture: sub-linear ratio, no premature BLOCK."""
    snap = ProjectContextSnapshot(repo_path="/tmp/fake")
    engine = GovernanceEngine(project_context=snap)
    events = load_transcript(FIXTURE)
    for ev in events:
        d = engine.evaluate(ev.message)
        if ev.has_signal:
            engine.feedback(d, was_correct=ev.success)
        engine.observe_for_learning(ev.message, ev.success)

    ratio = len(engine.graph.patterns) / len(events)
    assert ratio < 1.0, f"sub-linear growth violated: {ratio}"
    assert engine.mode != Mode.BLOCK, "premature BLOCK on tiny session"
