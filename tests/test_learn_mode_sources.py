"""Tests for v1.9 P3 — Learn Mode JSONL source expansion.

Covers:
  * empty default → existing Desktop ingest unchanged, no extra threads
  * source turns tagged with ``metadata.source_label``
  * self-monitor guard — exact-path match (SM-internal session JSONL)
  * self-monitor guard — path-segment match (``stream_manager``)
  * self-monitor guard — does NOT raise; other sources unaffected
  * two-source isolation — labels independent, no cross-contamination
  * ``hitl_overrides.source_label`` column added (idempotent migration)
  * Desktop session turns leave ``source_label`` NULL

Memory: ``feedback_no_self_monitor.md`` — the guard never builds a
feedback loop. Memory: ``feedback_cassette_must_cover_new_envelopes.md``
— P3 introduces no new bus envelope types; verified inline below.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

import pytest

from stream_manager import learn_mode, message_bus as _msg_bus
from stream_manager.jsonl_tail import JsonlTailWorker
from stream_manager.agent_registry import AgentRegistry
from stream_manager.learn_mode import (
    LEARN_SOURCES_ENV,
    LearnSourceManager,
    LearnSourceWorker,
    SourceConfig,
    ensure_source_label_column,
    is_self_monitor_path,
    load_sources,
    record_override_with_source_label,
)


PROFILES_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "stream_manager"
    / "agent_profiles.yaml"
)


# ── shared fixtures ─────────────────────────────────────────────────


@pytest.fixture
def bus(tmp_path: Path) -> _msg_bus.MessageBus:
    return _msg_bus.MessageBus(str(tmp_path / "bus.db"))


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
                "type": r[3],
                "content": r[5],
                "metadata": meta,
            }
        )
    return out


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _assistant(uuid: str, parent: str, text: str, sid: str = "ext-S1") -> dict:
    return {
        "type": "assistant",
        "sessionId": sid,
        "uuid": uuid,
        "parentUuid": parent,
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
        },
    }


def _user(uuid: str, parent: str, text: str, sid: str = "ext-S1") -> dict:
    return {
        "type": "user",
        "sessionId": sid,
        "uuid": uuid,
        "parentUuid": parent,
        "message": {"role": "user", "content": text},
    }


def _seed_decision(bus: _msg_bus.MessageBus, decision_id: str) -> str:
    """Create a messages row + decisions row to satisfy FK constraints."""
    msg = _msg_bus.Message.new(
        session_id="seed-session",
        type="user_input",
        direction="inbound",
        content="seed",
    )
    bus.publish(msg)
    bus.execute_write(
        "INSERT INTO decisions (id, message_id, action, confidence, "
        "reasoning, matched_hash, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (decision_id, msg.id, "allow", 0.9, "seed", "", 1.0),
    )
    return msg.id


# ── 1. empty sources default ────────────────────────────────────────


def test_empty_sources_default_unchanged(
    bus: _msg_bus.MessageBus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No ``BRIDGE_LEARN_SOURCES`` → no LearnSourceWorker threads.

    Verifies the v1.3 Desktop ingest path is undisturbed: the manager
    starts with zero workers, no threads named ``learn-source-*`` exist,
    and existing thread count is preserved.
    """
    monkeypatch.delenv(LEARN_SOURCES_ENV, raising=False)
    assert load_sources() == []

    pre_threads = {t.name for t in threading.enumerate()}
    mgr = learn_mode.from_environment(bus)
    mgr.start()
    try:
        assert mgr.sources == []
        assert mgr.workers == []
        post_threads = {t.name for t in threading.enumerate()}
        new_threads = post_threads - pre_threads
        # No new tail-watcher thread created when config is empty.
        assert not any(n.startswith("learn-source-") for n in new_threads)
    finally:
        mgr.stop()


# ── 2. source turns tagged with label ───────────────────────────────


def test_source_turns_tagged_with_label(
    bus: _msg_bus.MessageBus, tmp_path: Path
) -> None:
    """Each ingested turn carries ``metadata.source_label``.

    Drives ``LearnSourceWorker.process_line`` directly (no thread) so
    the test is deterministic. Verifies that the same envelope shape
    used by ``JsonlTailWorker`` (``desktop_prompt`` / ``user_reply``
    paired via ``parentUuid``) flows through with the new label.
    """
    src = SourceConfig(
        path_glob=str(tmp_path / "oversight" / "*.jsonl"),
        label="certportal-oversight",
    )
    worker = LearnSourceWorker(src, bus)
    records = [
        _assistant("a1", "", "Want me to run QA?"),
        _user("u1", "a1", "yes"),
    ]
    for rec in records:
        worker.process_line(json.dumps(rec))
    msgs = _read_messages(bus)
    assert len(msgs) == 2
    assert {m["type"] for m in msgs} == {"desktop_prompt", "user_reply"}
    for m in msgs:
        assert m["metadata"]["source_label"] == "certportal-oversight"
    # Pair link is preserved.
    desktop = next(m for m in msgs if m["type"] == "desktop_prompt")
    user = next(m for m in msgs if m["type"] == "user_reply")
    assert user["metadata"]["pair_id"] == desktop["id"]


# ── 3. self-monitor guard — exact path ──────────────────────────────


def test_self_monitor_guard_sm_session_path(
    bus: _msg_bus.MessageBus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Glob resolving to SM's own session JSONL → rejected with WARNING.

    Stubs ``Path.home`` so the SM-internal path lives under tmp_path,
    then writes a JSONL file there. ``LearnSourceWorker.expand_glob``
    must drop it and ``WARNING``-log the rejection. No turns ingested.
    """
    fake_home = tmp_path / "home"
    fake_sessions = fake_home / ".claude" / "sessions"
    sm_session_id = "sm-self-007"
    sm_jsonl = fake_sessions / f"{sm_session_id}.jsonl"
    _write_jsonl(sm_jsonl, [_assistant("a1", "", "should not ingest")])

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setenv("SM_OWN_SESSION_ID", sm_session_id)

    src = SourceConfig(
        path_glob=str(fake_sessions / "*.jsonl"),
        label="bad-source",
    )
    worker = LearnSourceWorker(
        src, bus, sm_own_session_id=sm_session_id
    )
    with caplog.at_level(logging.WARNING, logger="stream_manager.learn_mode"):
        kept = worker.expand_glob()
    assert kept == []
    rejection_logs = [
        r for r in caplog.records
        if "rejecting path" in r.getMessage() and r.levelno == logging.WARNING
    ]
    assert len(rejection_logs) >= 1, (
        f"expected a WARNING-level rejection log; got {caplog.record_tuples!r}"
    )
    # No envelopes published.
    assert _read_messages(bus) == []


# ── 4. self-monitor guard — path segment ────────────────────────────


def test_self_monitor_guard_stream_manager_path_segment(
    bus: _msg_bus.MessageBus,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Any path containing a ``stream_manager`` segment → rejected.

    Path segment match is independent of the SM session id; covers the
    case where SM's own working tree is referenced directly (e.g.
    ``/repo/stream_manager/foo.jsonl``).
    """
    sm_dir = tmp_path / "stream_manager" / "logs"
    target = sm_dir / "session.jsonl"
    _write_jsonl(target, [_assistant("a1", "", "should not ingest")])

    src = SourceConfig(
        path_glob=str(tmp_path / "stream_manager" / "logs" / "*.jsonl"),
        label="bad-source",
    )
    worker = LearnSourceWorker(src, bus)
    with caplog.at_level(logging.WARNING, logger="stream_manager.learn_mode"):
        kept = worker.expand_glob()
    assert kept == []
    rejection_logs = [
        r for r in caplog.records
        if "rejecting path" in r.getMessage() and r.levelno == logging.WARNING
    ]
    assert len(rejection_logs) >= 1


# ── 5. self-monitor guard — does NOT raise; siblings unaffected ─────


def test_self_monitor_guard_does_not_raise(
    bus: _msg_bus.MessageBus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Rejection is a WARNING + continue; other sources keep ingesting.

    Two configured sources: one resolves to SM-internal (rejected), the
    other to an external file (ingested). The bad source's rejection
    must not raise an exception or prevent the good source's turns from
    landing.
    """
    fake_home = tmp_path / "home"
    sm_session_id = "sm-self-007"
    sm_jsonl = fake_home / ".claude" / "sessions" / f"{sm_session_id}.jsonl"
    _write_jsonl(sm_jsonl, [_assistant("aBad", "", "BAD do not ingest")])

    good_dir = tmp_path / "good"
    good_path = good_dir / "ext.jsonl"
    _write_jsonl(
        good_path,
        [
            _assistant("aGood", "", "good prompt"),
            _user("uGood", "aGood", "good reply"),
        ],
    )

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setenv("SM_OWN_SESSION_ID", sm_session_id)

    bad_src = SourceConfig(
        path_glob=str(fake_home / ".claude" / "sessions" / "*.jsonl"),
        label="bad-source",
    )
    good_src = SourceConfig(
        path_glob=str(good_dir / "*.jsonl"),
        label="good-source",
    )

    bad_worker = LearnSourceWorker(
        bad_src, bus, sm_own_session_id=sm_session_id
    )
    good_worker = LearnSourceWorker(
        good_src, bus, sm_own_session_id=sm_session_id
    )

    with caplog.at_level(logging.WARNING, logger="stream_manager.learn_mode"):
        bad_kept = bad_worker.expand_glob()  # MUST NOT RAISE
        good_kept = good_worker.expand_glob()

    assert bad_kept == []
    assert len(good_kept) == 1

    # Drive the good source's content through process_line to confirm
    # ingest is unaffected.
    for line in good_path.read_text(encoding="utf-8").splitlines():
        good_worker.process_line(line)
    msgs = _read_messages(bus)
    assert len(msgs) == 2
    assert all(m["metadata"]["source_label"] == "good-source" for m in msgs)


# ── 6. two-source isolation ─────────────────────────────────────────


def test_two_sources_isolated(
    bus: _msg_bus.MessageBus, tmp_path: Path
) -> None:
    """Two sources tagged independently; no cross-contamination.

    The categoriser is a separate process (worker thread); for the
    ingest pipeline the invariant is that label tagging is per-source
    metadata only. Verify by inspecting envelope metadata directly.
    """
    src_a = SourceConfig(
        path_glob=str(tmp_path / "a" / "*.jsonl"),
        label="source-a",
    )
    src_b = SourceConfig(
        path_glob=str(tmp_path / "b" / "*.jsonl"),
        label="source-b",
    )
    worker_a = LearnSourceWorker(src_a, bus)
    worker_b = LearnSourceWorker(src_b, bus)

    a_records = [
        _assistant("a1", "", "from A"),
        _user("u1", "a1", "ack A"),
    ]
    b_records = [
        _assistant("b1", "", "from B"),
        _user("v1", "b1", "ack B"),
    ]
    for rec in a_records:
        worker_a.process_line(json.dumps(rec))
    for rec in b_records:
        worker_b.process_line(json.dumps(rec))

    msgs = _read_messages(bus)
    label_for = {m["content"]: m["metadata"]["source_label"] for m in msgs}
    assert label_for["from A"] == "source-a"
    assert label_for["ack A"] == "source-a"
    assert label_for["from B"] == "source-b"
    assert label_for["ack B"] == "source-b"
    # Same-source pair links are intact (no leakage from B's pairing
    # cache into A's user_reply, and vice-versa).
    a_desktop = next(
        m for m in msgs
        if m["type"] == "desktop_prompt" and m["content"] == "from A"
    )
    a_user = next(
        m for m in msgs
        if m["type"] == "user_reply" and m["content"] == "ack A"
    )
    assert a_user["metadata"]["pair_id"] == a_desktop["id"]


# ── 7. hitl_overrides.source_label column added ─────────────────────


def test_hitl_overrides_has_source_label_column(
    bus: _msg_bus.MessageBus,
) -> None:
    """Migration is idempotent: column added on fresh + existing DBs.

    Asserts:
      * column ``source_label`` exists on ``hitl_overrides`` after
        migration;
      * existing rows (inserted before the migration) keep NULL;
      * second migration call is a no-op (no exception).
    """
    # Pre-migration: insert an existing override row via the legacy
    # path so we can prove existing rows are unaffected.
    bus.queue_hitl(
        message_id=_seed_decision(bus, "dec-pre-1"),
        proposed_action="allow",
        proposed_confidence=0.9,
        trigger_reason="seed",
    )
    bus.execute_write(
        "INSERT INTO hitl_overrides (decision_id, original_action, "
        "override_action, note, mode, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("dec-pre-1", "allow", "allow", None, "auto", "2026-05-07T00:00:00"),
    )

    ensure_source_label_column(bus)

    cols = {r[0] for r in bus.fetch_rows(
        "SELECT name FROM pragma_table_info('hitl_overrides')"
    )}
    assert "source_label" in cols

    # Existing row's source_label is NULL.
    rows = bus.fetch_rows(
        "SELECT decision_id, source_label FROM hitl_overrides"
    )
    assert len(rows) == 1
    assert rows[0][0] == "dec-pre-1"
    assert rows[0][1] is None

    # Idempotent: second call is a no-op.
    ensure_source_label_column(bus)  # MUST NOT RAISE
    cols2 = {r[0] for r in bus.fetch_rows(
        "SELECT name FROM pragma_table_info('hitl_overrides')"
    )}
    assert cols2 == cols


# ── 8. Desktop session turns → source_label NULL ────────────────────


def test_source_label_null_for_desktop_session(
    bus: _msg_bus.MessageBus, tmp_path: Path
) -> None:
    """Desktop turns (no source config) leave ``source_label`` NULL.

    Calls the legacy ``MessageBus.annotate_decision`` path (used by the
    Desktop session pipeline) and verifies the new ``source_label``
    column stays NULL — the v1.3 Desktop attribution invariant is
    preserved.

    Also verifies that the new
    ``record_override_with_source_label`` helper writes the label when
    a tagged turn is present, so the per-source attribution path works
    end-to-end.
    """
    ensure_source_label_column(bus)

    # 1. Desktop turn — no source label, uses legacy annotate_decision.
    _seed_decision(bus, "dec-desktop")
    bus.annotate_decision(
        decision_id="dec-desktop",
        original_action="allow",
        override_action="allow",
        note="from Desktop",
        mode="auto",
    )

    # 2. Tagged turn — uses the new helper.
    _seed_decision(bus, "dec-tagged")
    record_override_with_source_label(
        bus,
        decision_id="dec-tagged",
        original_action="allow",
        override_action="block",
        note="from oversight",
        mode="auto",
        source_label="certportal-oversight",
    )

    rows = {
        r[0]: r[1]
        for r in bus.fetch_rows(
            "SELECT decision_id, source_label FROM hitl_overrides"
        )
    }
    assert rows == {
        "dec-desktop": None,
        "dec-tagged": "certportal-oversight",
    }


# ── 9. (sanity) is_self_monitor_path exact-path + segment helper ────


def test_is_self_monitor_path_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Direct unit cover of the guard predicate for both branches.

    Not in the DOD list; a small belt-and-suspenders check that the
    public guard helper actually returns True for both rejection
    branches and False for an unrelated path.
    """
    fake_home = tmp_path / "home"
    sm_session_id = "sm-self-007"
    sm_jsonl = fake_home / ".claude" / "sessions" / f"{sm_session_id}.jsonl"
    _write_jsonl(sm_jsonl, [_assistant("a1", "", "x")])
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    # exact-path
    assert is_self_monitor_path(sm_jsonl, sm_own_session_id=sm_session_id)
    # segment
    seg_path = tmp_path / "stream_manager" / "x.jsonl"
    seg_path.parent.mkdir(parents=True, exist_ok=True)
    seg_path.write_text("{}", encoding="utf-8")
    assert is_self_monitor_path(seg_path)
    # neither
    ok_path = tmp_path / "elsewhere" / "y.jsonl"
    ok_path.parent.mkdir(parents=True, exist_ok=True)
    ok_path.write_text("{}", encoding="utf-8")
    assert not is_self_monitor_path(ok_path, sm_own_session_id=sm_session_id)


# ── 10. (sanity) load_sources malformed input ───────────────────────


def test_load_sources_malformed_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bad JSON / non-list / missing fields are all soft-failures.

    Belt-and-suspenders: ``load_sources`` must never raise — a
    misconfigured env var must not break SM startup. Skipped entries
    are logged at WARNING level.
    """
    monkeypatch.setenv(LEARN_SOURCES_ENV, "{not json")
    assert load_sources() == []
    monkeypatch.setenv(LEARN_SOURCES_ENV, '{"x": 1}')  # not a list
    assert load_sources() == []
    monkeypatch.setenv(LEARN_SOURCES_ENV, '[1, 2]')  # non-dict entries
    assert load_sources() == []
    monkeypatch.setenv(
        LEARN_SOURCES_ENV,
        '[{"label": "no-glob"}, {"path_glob": "/x", "label": "good"}]',
    )
    sources = load_sources()
    assert len(sources) == 1
    assert sources[0].label == "good"


# ── 11. Regression guard: no new bus envelope types ─────────────────


def test_no_new_envelope_types_in_module() -> None:
    """P3 must not introduce new ``learn_source*`` envelope types.

    Memory: ``feedback_cassette_must_cover_new_envelopes.md``. New
    envelope types would silently break cassette + soak driver coverage
    until the next cycle's ship-gate.
    """
    src_path = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "stream_manager"
        / "learn_mode.py"
    )
    text = src_path.read_text(encoding="utf-8")
    # The only acceptable envelope ``type=`` strings are the v1.3 pair.
    assert 'type="desktop_prompt"' in text
    assert 'type="user_reply"' in text
    assert 'type="learn_source' not in text
    assert '"learn_source_' not in text
