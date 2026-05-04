"""Tests for v1.3 P5b — JSONL tail Learn Mode dialogue ingest.

Asserts that ``JsonlTailWorker`` extends Phase 1 ingest with two new
``messages.type`` values:

  - ``desktop_prompt`` — emitted for assistant text turns
  - ``user_reply``    — emitted for user text turns, with metadata.pair_id
                        linking back to the preceding desktop_prompt via
                        the parentUuid chain

Also verifies the no-self-monitor invariant
(memory: ``feedback_no_self_monitor.md``): turns whose ``sessionId``
matches ``SM_OWN_SESSION_ID`` are filtered out at ingest and produce no
envelope.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stream_manager import message_bus as _msg_bus
from stream_manager.agent_registry import AgentRegistry
from stream_manager.jsonl_tail import JsonlTailWorker

PROFILES_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "stream_manager"
    / "agent_profiles.yaml"
)
FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "learn_mode_jsonl_sample.jsonl"
)


@pytest.fixture
def bus(tmp_path: Path) -> _msg_bus.MessageBus:
    return _msg_bus.MessageBus(str(tmp_path / "bus.db"))


@pytest.fixture
def worker(bus: _msg_bus.MessageBus, tmp_path: Path) -> JsonlTailWorker:
    registry = AgentRegistry(profiles_path=PROFILES_PATH)
    w = JsonlTailWorker(
        projects_dir=tmp_path,
        registry=registry,
        bus=bus,
    )
    # Install a sm-side session id so envelopes land somewhere stable.
    w._session_id = "sm-side-session"
    w._project_slug = "fixture"
    return w


def _drive(worker: JsonlTailWorker, fixture_path: Path) -> None:
    """Replay a fixture JSONL through the tailer's per-line entry point."""
    for line in fixture_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        worker._process_line(line)


def _read_messages(bus: _msg_bus.MessageBus) -> list[dict]:
    rows = bus.fetch_rows(
        "SELECT id, session_id, sequence, type, direction, content, "
        "context, metadata, timestamp FROM messages ORDER BY sequence"
    )
    out: list[dict] = []
    for r in rows:
        meta = json.loads(r[7]) if r[7] else {}
        out.append(
            {
                "id": r[0],
                "session_id": r[1],
                "sequence": r[2],
                "type": r[3],
                "direction": r[4],
                "content": r[5],
                "metadata": meta,
            }
        )
    return out


def test_assistant_text_turn_emits_desktop_prompt(
    worker: JsonlTailWorker,
    bus: _msg_bus.MessageBus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # SM_OWN_SESSION_ID is set in production at SM boot. Set it here too
    # so SM-originated turns in the fixture are filtered (their dedicated
    # assertion lives in test_sm_originated_turn_is_filtered_out).
    monkeypatch.setenv("SM_OWN_SESSION_ID", "sm-owner-42")
    _drive(worker, FIXTURE_PATH)
    msgs = _read_messages(bus)
    desktop = [m for m in msgs if m["type"] == "desktop_prompt"]
    assert len(desktop) == 1
    assert desktop[0]["content"] == "Want me to run the failing tests first?"
    assert desktop[0]["metadata"]["uuid"] == "a1"


def test_user_text_turn_emits_user_reply_with_pair_id(
    worker: JsonlTailWorker,
    bus: _msg_bus.MessageBus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # SM_OWN_SESSION_ID is set in production at SM boot. Set it here too
    # so SM-originated turns in the fixture are filtered (their dedicated
    # assertion lives in test_sm_originated_turn_is_filtered_out).
    monkeypatch.setenv("SM_OWN_SESSION_ID", "sm-owner-42")
    _drive(worker, FIXTURE_PATH)
    msgs = _read_messages(bus)

    desktop = [m for m in msgs if m["type"] == "desktop_prompt"]
    user = [m for m in msgs if m["type"] == "user_reply"]
    assert len(desktop) == 1
    assert len(user) == 1

    desktop_id = desktop[0]["id"]
    assert user[0]["content"] == "yes please, just the failing ones"
    assert user[0]["metadata"]["parent_uuid"] == "a1"
    # The user_reply's pair_id MUST point at the preceding desktop_prompt's
    # envelope id — this is the link Learn Mode's categorizer follows.
    assert user[0]["metadata"]["pair_id"] == desktop_id


def test_tool_use_and_tool_result_are_not_dialogue_turns(
    worker: JsonlTailWorker,
    bus: _msg_bus.MessageBus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only chat *text* parts count as dialogue.

    Records whose only content parts are ``tool_use`` (assistant) or
    ``tool_result`` (user) MUST NOT emit desktop_prompt / user_reply
    envelopes — those are tool traffic, not Desktop ↔ user dialogue.
    """
    # SM_OWN_SESSION_ID is set in production at SM boot. Set it here too
    # so SM-originated turns in the fixture are filtered (their dedicated
    # assertion lives in test_sm_originated_turn_is_filtered_out).
    monkeypatch.setenv("SM_OWN_SESSION_ID", "sm-owner-42")
    _drive(worker, FIXTURE_PATH)
    msgs = _read_messages(bus)
    contents = {m["content"] for m in msgs if m["type"] in ("desktop_prompt", "user_reply")}
    # Tool traffic (a2 tool_use, u2 tool_result) must not appear.
    assert all("tool_use" not in c and "tool_result" not in c for c in contents)
    # And only the two text turns are emitted.
    text_turns = [m for m in msgs if m["type"] in ("desktop_prompt", "user_reply")]
    assert len(text_turns) == 2


def test_sm_originated_turn_is_filtered_out(
    worker: JsonlTailWorker,
    bus: _msg_bus.MessageBus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Turns whose sessionId == SM_OWN_SESSION_ID MUST NOT be emitted.

    Per ``feedback_no_self_monitor.md``: SM must never ingest its own
    HITL prompts/decisions back into the Learn Mode categorizer (creates
    an evaluation feedback loop). The fixture's ``sm-owner-42`` turns
    represent SM's own JSONL emission and must be excluded.
    """
    monkeypatch.setenv("SM_OWN_SESSION_ID", "sm-owner-42")
    _drive(worker, FIXTURE_PATH)
    msgs = _read_messages(bus)

    learn_msgs = [m for m in msgs if m["type"] in ("desktop_prompt", "user_reply")]
    # No envelope should originate from sm-owner-42.
    sources = {m["metadata"].get("session_id") for m in learn_msgs}
    assert "sm-owner-42" not in sources
    # The Desktop pair (sessionId=desktop-S1) is still emitted.
    assert len(learn_msgs) == 2
    assert all(m["metadata"].get("session_id") == "desktop-S1" for m in learn_msgs)


def test_learn_mode_emit_does_not_break_desktop_pause_path(
    worker: JsonlTailWorker,
    bus: _msg_bus.MessageBus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing emit paths (agent_identified, desktop_pause) must remain.

    Drives a record carrying both an assistant-text turn AND
    ``stopReason=end_turn`` to confirm the new Learn Mode path is
    additive: the legacy ``desktop_pause`` envelope still fires.
    """
    monkeypatch.delenv("SM_OWN_SESSION_ID", raising=False)
    record = {
        "type": "assistant",
        "sessionId": "desktop-S1",
        "uuid": "a99",
        "parentUuid": "",
        "stopReason": "end_turn",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "done."}],
        },
    }
    worker._process_line(json.dumps(record))
    msgs = _read_messages(bus)
    types = [m["type"] for m in msgs]
    assert "desktop_prompt" in types
    assert "desktop_pause" in types
