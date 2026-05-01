"""Tests for FR-HITL §4.9 / ADR-9 — sync/async HITL queue.

Coverage:
    1. classify_trigger returns NEW_PATTERN when source=="default"
    2. classify_trigger returns LOW_CONFIDENCE when confidence < floor
    3. classify_trigger returns DESKTOP_PAUSE when message ends with "?"
    4. classify_trigger returns None when no trigger fires
    5. route() in async mode returns original decision unchanged
    6. route() in sync mode times out and returns original decision
    7. apply_feedback increases graph confidence on approved override
    8. apply_feedback decreases graph confidence on action override
"""

from __future__ import annotations

import threading
import time
import uuid

import pytest

from stream_manager.decision_graph import DecisionGraph, Pattern, PatternLevel
from stream_manager.governance import GovDecision, Mode
from stream_manager.hitl import HitlQueue, TriggerReason
from stream_manager.message_bus import Message, MessageBus


# ── helpers ──────────────────────────────────────────────────────────


def _bus(tmp_path) -> MessageBus:
    return MessageBus(str(tmp_path / "hitl.db"))


def _publish_msg(bus: MessageBus, session_id: str, content: str = "test") -> str:
    msg = Message.new(session_id=session_id, type="governance_eval",
                      direction="inbound", content=content)
    bus.publish(msg)
    return msg.id


def _open_session(bus: MessageBus, session_id: str = "s1",
                   mode: str = "async", floor: float = 0.60) -> str:
    bus.open_session(session_id)
    bus.set_hitl_mode(session_id, mode, floor)
    return session_id


def _decision(action: str = "ALLOW", confidence: float = 0.9,
              source: str = "graph", matched_hash: str = "") -> GovDecision:
    return GovDecision(
        action=action,
        confidence=confidence,
        reasoning="test",
        mode=Mode.OBSERVE,
        matched_hash=matched_hash,
        source=source,
    )


# ── classify_trigger ─────────────────────────────────────────────────


def test_classify_trigger_new_pattern(tmp_path):
    bus = _bus(tmp_path)
    queue = HitlQueue(bus=bus)
    decision = _decision(source="default", confidence=0.9)
    trigger = queue.classify_trigger(decision, "anything", False)
    assert trigger == TriggerReason.NEW_PATTERN
    bus.close()


def test_classify_trigger_low_confidence(tmp_path):
    bus = _bus(tmp_path)
    queue = HitlQueue(bus=bus)
    decision = _decision(source="graph", confidence=0.40)
    trigger = queue.classify_trigger(decision, "ok", False)
    assert trigger == TriggerReason.LOW_CONFIDENCE
    bus.close()


def test_classify_trigger_desktop_pause_question(tmp_path):
    bus = _bus(tmp_path)
    queue = HitlQueue(bus=bus)
    decision = _decision(source="graph", confidence=0.95)
    trigger = queue.classify_trigger(decision, "should I proceed?", False)
    assert trigger == TriggerReason.DESKTOP_PAUSE
    bus.close()


def test_classify_trigger_none(tmp_path):
    bus = _bus(tmp_path)
    queue = HitlQueue(bus=bus)
    decision = _decision(source="graph", confidence=0.95)
    trigger = queue.classify_trigger(decision, "no trigger here.", False)
    assert trigger is None
    bus.close()


# ── route() ──────────────────────────────────────────────────────────


def test_route_async_returns_original_unchanged(tmp_path):
    bus = _bus(tmp_path)
    sid = _open_session(bus, "s_async", mode="async")
    queue = HitlQueue(bus=bus, timeout_seconds=1.0)
    msg_id = _publish_msg(bus, sid, "should I proceed?")
    decision = _decision(source="graph", confidence=0.95)
    out = queue.route(decision, msg_id, "should I proceed?", sid, False)
    # Async mode passes the decision straight through.
    assert out is decision
    # And queues nothing.
    assert bus.get_pending_hitl(sid) == []
    bus.close()


def test_route_sync_times_out_returns_original(tmp_path):
    bus = _bus(tmp_path)
    sid = _open_session(bus, "s_sync", mode="sync")
    # Tight timeout so the test is fast but still exercises the poll loop.
    queue = HitlQueue(bus=bus, timeout_seconds=1.0, poll_interval_s=0.2)
    msg_id = _publish_msg(bus, sid, "anything")
    decision = _decision(source="default", confidence=0.1, action="ALLOW")
    started = time.monotonic()
    out = queue.route(decision, msg_id, "anything", sid, False)
    elapsed = time.monotonic() - started
    assert 0.9 <= elapsed < 3.0, f"timeout did not fire in expected window: {elapsed}"
    assert out.action == decision.action
    assert out.confidence == decision.confidence
    # Pending row should be marked timeout.
    pending = bus.get_pending_hitl(sid)
    assert pending == []  # resolved (timeout) so no longer "pending"
    bus.close()


def test_route_sync_resolves_with_override(tmp_path):
    bus = _bus(tmp_path)
    sid = _open_session(bus, "s_sync_ok", mode="sync")
    queue = HitlQueue(bus=bus, timeout_seconds=3.0, poll_interval_s=0.2)
    msg_id = _publish_msg(bus, sid, "anything")
    decision = _decision(source="default", confidence=0.1, action="ALLOW")

    def _resolve_after_delay():
        time.sleep(0.4)
        rows = bus.get_pending_hitl(sid)
        assert rows
        bus.resolve_hitl(rows[0]["id"], "overridden:BLOCK")

    t = threading.Thread(target=_resolve_after_delay, daemon=True)
    t.start()
    out = queue.route(decision, msg_id, "anything", sid, False)
    t.join(timeout=4.0)
    assert out.action == "BLOCK"
    bus.close()


# ── apply_feedback ───────────────────────────────────────────────────


def _seed_pattern(graph: DecisionGraph, pattern_hash: str,
                  successes: int = 5, occurrences: int = 10) -> Pattern:
    p = Pattern(
        hash=pattern_hash,
        level=PatternLevel.L1,
        vector=[0.0] * 64,
        canonical_text="seeded",
        occurrences=occurrences,
        successes=successes,
        last_seen=time.time(),
    )
    graph.patterns[pattern_hash] = p
    return p


def test_apply_feedback_approved_increases_confidence(tmp_path):
    bus = _bus(tmp_path)
    sid = _open_session(bus, "s_fb", mode="async")
    graph = DecisionGraph()
    pattern_hash = "abc123"
    pat = _seed_pattern(graph, pattern_hash, successes=5, occurrences=10)
    initial_rate = pat.success_rate
    initial_succ = pat.successes
    initial_occ = pat.occurrences

    queue = HitlQueue(bus=bus, graph=graph)
    msg_id = _publish_msg(bus, sid, "test")
    decision_id = bus.record_decision(
        message_id=msg_id,
        action="ALLOW",
        confidence=0.7,
        reasoning="test",
        matched_hash=pattern_hash,
    )
    # Approved == override_action equals original_action.
    queue.apply_feedback(
        decision_id=decision_id,
        override_action="ALLOW",
        note="looks good",
        mode="async",
    )
    assert pat.successes == initial_succ + 1
    assert pat.occurrences == initial_occ + 1
    assert pat.success_rate >= initial_rate, (
        "approved feedback should not decrease confidence"
    )
    # Override row was persisted.
    overrides = bus.get_overrides_for_hash(pattern_hash, limit=5)
    assert len(overrides) == 1
    assert overrides[0]["override_action"] == "ALLOW"
    bus.close()


def test_apply_feedback_overridden_decreases_confidence(tmp_path):
    bus = _bus(tmp_path)
    sid = _open_session(bus, "s_fb_neg", mode="async")
    graph = DecisionGraph()
    pattern_hash = "def456"
    pat = _seed_pattern(graph, pattern_hash, successes=8, occurrences=10)
    initial_rate = pat.success_rate
    initial_succ = pat.successes

    queue = HitlQueue(bus=bus, graph=graph)
    msg_id = _publish_msg(bus, sid, "test")
    decision_id = bus.record_decision(
        message_id=msg_id,
        action="ALLOW",
        confidence=0.7,
        reasoning="test",
        matched_hash=pattern_hash,
    )
    queue.apply_feedback(
        decision_id=decision_id,
        override_action="BLOCK",
        note="not safe",
        mode="async",
    )
    # Successes unchanged, occurrences incremented -> rate goes down.
    assert pat.successes == initial_succ
    assert pat.success_rate < initial_rate
    overrides = bus.get_overrides_for_hash(pattern_hash, limit=5)
    assert len(overrides) == 1
    assert overrides[0]["override_action"] == "BLOCK"
    assert overrides[0]["note"] == "not safe"
    bus.close()


# ── note cap + token truncation ─────────────────────────────────────


def test_active_notes_capped_at_five_per_hash(tmp_path):
    bus = _bus(tmp_path)
    sid = _open_session(bus, "s_notes", mode="async")
    graph = DecisionGraph()
    pattern_hash = "cap_test"
    _seed_pattern(graph, pattern_hash)
    queue = HitlQueue(bus=bus, graph=graph)

    msg_id = _publish_msg(bus, sid, "test")
    for i in range(8):
        d_id = bus.record_decision(
            message_id=msg_id,
            action="ALLOW",
            confidence=0.7,
            reasoning="r",
            matched_hash=pattern_hash,
        )
        queue.apply_feedback(d_id, "ALLOW", f"note number {i}", "async")
    notes = queue.get_active_notes(pattern_hash)
    assert len(notes) <= 5
    bus.close()


def test_note_truncated_to_fifty_tokens(tmp_path):
    bus = _bus(tmp_path)
    sid = _open_session(bus, "s_tok", mode="async")
    graph = DecisionGraph()
    pattern_hash = "tok_test"
    _seed_pattern(graph, pattern_hash)
    queue = HitlQueue(bus=bus, graph=graph)
    msg_id = _publish_msg(bus, sid, "test")
    d_id = bus.record_decision(
        message_id=msg_id,
        action="ALLOW",
        confidence=0.7,
        reasoning="r",
        matched_hash=pattern_hash,
    )
    long_note = " ".join(f"word{i}" for i in range(120))
    queue.apply_feedback(d_id, "ALLOW", long_note, "async")
    notes = queue.get_active_notes(pattern_hash)
    assert notes
    assert len(notes[-1].split()) <= 50
    bus.close()
