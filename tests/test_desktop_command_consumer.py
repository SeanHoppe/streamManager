"""Unit tests for the governed-side desktop_command consumer.

Covers the security-critical happy + failure paths that are independent
of the SSE transport layer:
  - valid signed command → executor called → ack=ok
  - bad signature → executor NOT called → ack=rejected, error='bad_sig'
  - unknown kind → ack=rejected, error='unknown_kind'
  - executor raises → ack=rejected, error=str(exc)[:200]
  - executor exception is truncated to 200 chars
  - constructor input validation
  - _dispatched dedupe set prevents replay double-fire
  - transport='long-poll' is rejected with the v1.2 removal message

End-to-end SSE behaviour (transport, reconnect, backoff) is covered by
``tests/test_desktop_command_sse.py`` against a live uvicorn fixture.

The HMAC secret is set via monkeypatch on SM_DESKTOP_SECRET so the test
never touches the real ``.bridge/secret`` file.

Note: v1.2 (Task D) removed the long-poll transport. The SSE
``run_once``-equivalent shape is exercised by calling ``process_row``
directly with a synthesized row, which is the post-parse hand-off point
shared by both the (now-removed) long-poll fetch path and the surviving
SSE frame iterator.
"""

from __future__ import annotations

import importlib
import os
import sys
from typing import Any

import httpx
import pytest


SECRET = b"test-shared-secret-deadbeef"
SESSION_ID = "sess-abc"
SM_URL = "http://sm.test"


# ─── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def desktop_commands(monkeypatch):
    """Reload desktop_commands with the test secret pinned via env."""
    monkeypatch.setenv("SM_DESKTOP_SECRET", SECRET.decode("utf-8"))
    monkeypatch.delenv("SM_OWN_SESSION_ID", raising=False)
    if "stream_manager.desktop_commands" in sys.modules:
        del sys.modules["stream_manager.desktop_commands"]
    if "stream_manager.desktop_command_consumer" in sys.modules:
        del sys.modules["stream_manager.desktop_command_consumer"]
    return importlib.import_module("stream_manager.desktop_commands")


@pytest.fixture
def consumer_module(desktop_commands):
    return importlib.import_module("stream_manager.desktop_command_consumer")


# ─── Helpers ──────────────────────────────────────────────────────────


def _make_row(
    desktop_commands_mod,
    *,
    cmd_id: str = "cmd-1",
    kind: str = "pause",
    args: dict | None = None,
    sent_at: float = 1700000000.0,
    tamper: bool = False,
) -> dict:
    args = args or {}
    payload = {
        "id": cmd_id,
        "session_id": SESSION_ID,
        "kind": kind,
        "args": args,
        "sent_at": sent_at,
    }
    sig = desktop_commands_mod.sign(payload)
    if tamper:
        # Flip a hex char so signature no longer matches.
        sig = ("0" if sig[0] != "0" else "1") + sig[1:]
    return {
        "id": cmd_id,
        "session_id": SESSION_ID,
        "kind": kind,
        "args": args,
        "sent_at": sent_at,
        "status": "pending",
        "signature": sig,
        "payload": payload,
    }


class _AckRecorder:
    """Captures every ack POST the consumer issues against MockTransport.

    GETs to the (removed) /api/commands/pending endpoint return 404 so
    any accidental long-poll fetch in this test file would fail loud.
    """

    def __init__(self) -> None:
        self.acks: list[tuple[str, dict]] = []

    def make_handler(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if (
                request.method == "POST"
                and request.url.path.startswith("/api/commands/")
                and request.url.path.endswith("/ack")
            ):
                parts = request.url.path.split("/")
                cmd_id = parts[3]
                body = (
                    {} if not request.content else _safe_json(request.content)
                )
                self.acks.append((cmd_id, body))
                return httpx.Response(
                    200, json={"id": cmd_id, "status": body.get("status")}
                )
            return httpx.Response(404, json={"detail": "not mocked"})

        return handler


def _safe_json(content: bytes) -> dict:
    import json

    try:
        return json.loads(content)
    except Exception:
        return {}


def _build_consumer(consumer_module, executors: dict, client: httpx.Client):
    """Construct a CommandConsumer wired to ``client``."""
    return consumer_module.CommandConsumer(
        sm_url=SM_URL,
        session_id=SESSION_ID,
        secret=SECRET,
        executors=executors,
        client=client,
    )


# ─── Tests ────────────────────────────────────────────────────────────


def test_valid_command_executes_and_acks_ok(consumer_module, desktop_commands):
    row = _make_row(desktop_commands, cmd_id="cmd-ok", kind="pause", args={"why": "test"})
    rec = _AckRecorder()
    transport = httpx.MockTransport(rec.make_handler())
    client = httpx.Client(transport=transport, base_url=SM_URL)

    seen: list[dict] = []

    def pause_executor(args: dict) -> None:
        seen.append(args)

    consumer = _build_consumer(consumer_module, {"pause": pause_executor}, client)
    consumer.process_row(row)

    assert seen == [{"why": "test"}]
    assert rec.acks == [("cmd-ok", {"status": "ok"})]


def test_bad_signature_rejects_without_executing(
    consumer_module, desktop_commands
):
    row = _make_row(desktop_commands, cmd_id="cmd-bad", tamper=True)
    rec = _AckRecorder()
    transport = httpx.MockTransport(rec.make_handler())
    client = httpx.Client(transport=transport, base_url=SM_URL)

    calls = {"n": 0}

    def pause_executor(args: dict) -> None:
        calls["n"] += 1

    consumer = _build_consumer(consumer_module, {"pause": pause_executor}, client)
    consumer.process_row(row)

    assert calls["n"] == 0
    assert rec.acks == [("cmd-bad", {"status": "rejected", "error": "bad_sig"})]


def test_unknown_kind_rejects(consumer_module, desktop_commands):
    # Kind is in producer's KIND_ALLOWLIST but the consumer didn't register
    # an executor for it — this MUST still reject. Defence-in-depth: the
    # consumer trusts only its own executors map, never the producer.
    assert "audible_cue" in desktop_commands.KIND_ALLOWLIST
    row = _make_row(desktop_commands, cmd_id="cmd-unk", kind="audible_cue")
    rec = _AckRecorder()
    transport = httpx.MockTransport(rec.make_handler())
    client = httpx.Client(transport=transport, base_url=SM_URL)

    consumer = _build_consumer(
        consumer_module, {"pause": lambda args: None}, client
    )  # only pause registered
    consumer.process_row(row)

    assert rec.acks == [
        ("cmd-unk", {"status": "rejected", "error": "unknown_kind"})
    ]


def test_executor_raises_acks_with_truncated_error(
    consumer_module, desktop_commands
):
    row = _make_row(desktop_commands, cmd_id="cmd-raise", kind="pause")
    rec = _AckRecorder()
    transport = httpx.MockTransport(rec.make_handler())
    client = httpx.Client(transport=transport, base_url=SM_URL)

    def boom(args: dict) -> None:
        raise RuntimeError("kaboom")

    consumer = _build_consumer(consumer_module, {"pause": boom}, client)
    consumer.process_row(row)

    assert rec.acks == [
        ("cmd-raise", {"status": "rejected", "error": "kaboom"})
    ]


def test_executor_long_error_is_truncated(consumer_module, desktop_commands):
    row = _make_row(desktop_commands, cmd_id="cmd-long", kind="pause")
    rec = _AckRecorder()
    transport = httpx.MockTransport(rec.make_handler())
    client = httpx.Client(transport=transport, base_url=SM_URL)

    long_msg = "x" * 500

    def boom(args: dict) -> None:
        raise RuntimeError(long_msg)

    consumer = _build_consumer(consumer_module, {"pause": boom}, client)
    consumer.process_row(row)

    assert len(rec.acks) == 1
    cmd_id, body = rec.acks[0]
    assert cmd_id == "cmd-long"
    assert body["status"] == "rejected"
    assert body["error"] == "x" * 200
    assert len(body["error"]) == 200


def test_dispatched_dedupe_prevents_double_fire(
    consumer_module, desktop_commands
):
    """Replay of an already-dispatched row must NOT re-fire the executor.

    This is the SSE reconnect-replay safety net the consumer relies on
    after the long-poll fetch path was removed in v1.2.
    """
    row = _make_row(desktop_commands, cmd_id="cmd-dup", kind="pause")
    rec = _AckRecorder()
    transport = httpx.MockTransport(rec.make_handler())
    client = httpx.Client(transport=transport, base_url=SM_URL)

    fires = {"n": 0}

    def pause_executor(args: dict) -> None:
        fires["n"] += 1

    consumer = _build_consumer(consumer_module, {"pause": pause_executor}, client)

    consumer.process_row(row)
    consumer.process_row(row)  # replay
    consumer.process_row(row)  # replay

    assert fires["n"] == 1
    # Only the first dispatch acked; subsequent replays short-circuit
    # before any HTTP call.
    assert rec.acks == [("cmd-dup", {"status": "ok"})]


def test_default_executors_cover_full_allowlist(
    consumer_module, desktop_commands
):
    execs = consumer_module._default_executors()
    assert set(execs.keys()) == set(desktop_commands.KIND_ALLOWLIST)
    # Each is callable with a dict and returns None without raising.
    for fn in execs.values():
        assert fn({}) is None


def test_consumer_does_not_touch_sm_desktop_secret_env(
    consumer_module, monkeypatch
):
    """Constructing a CommandConsumer must NOT set ``SM_DESKTOP_SECRET``."""
    monkeypatch.delenv("SM_DESKTOP_SECRET", raising=False)
    consumer = consumer_module.CommandConsumer(
        sm_url="http://example",
        session_id="s-x",
        secret=b"ctor-secret",
        executors={},
    )
    assert "SM_DESKTOP_SECRET" not in os.environ
    consumer.close()


def test_consumer_does_not_overwrite_existing_env(
    consumer_module, monkeypatch
):
    """Constructing a CommandConsumer must NOT overwrite a pre-existing
    ``SM_DESKTOP_SECRET`` set by the operator."""
    monkeypatch.setenv("SM_DESKTOP_SECRET", "operator-set")
    consumer_module.CommandConsumer(
        sm_url="http://example",
        session_id="s-y",
        secret=b"ctor-secret",
        executors={},
    ).close()
    assert os.environ["SM_DESKTOP_SECRET"] == "operator-set"


def test_constructor_validates_inputs(consumer_module):
    with pytest.raises(ValueError):
        consumer_module.CommandConsumer(
            sm_url="", session_id="x", secret=b"k", executors={}
        )
    with pytest.raises(ValueError):
        consumer_module.CommandConsumer(
            sm_url=SM_URL, session_id="", secret=b"k", executors={}
        )
    with pytest.raises(ValueError):
        consumer_module.CommandConsumer(
            sm_url=SM_URL, session_id="s", secret=b"", executors={}
        )


def test_longpoll_transport_rejected_with_migration_message(consumer_module):
    """v1.2 (Task D) removed the long-poll transport. Passing it now must
    raise ValueError with a clear migration hint pointing operators at
    CHANGELOG.md / ADR-14, not a generic "invalid transport"."""
    with pytest.raises(ValueError) as exc_info:
        consumer_module.CommandConsumer(
            sm_url=SM_URL,
            session_id="s",
            secret=SECRET,
            executors={},
            transport="long-poll",
        )
    msg = str(exc_info.value)
    # The message must reference both v1.2 (the removal cycle) and SSE
    # (the survivor) so a v1.1 operator stack-trace is self-explanatory.
    assert "v1.2" in msg
    assert "sse" in msg
    assert "CHANGELOG" in msg or "ADR-14" in msg


def test_default_transport_is_sse(consumer_module):
    """The v1.2 default flipped from 'long-poll' to 'sse'."""
    consumer = consumer_module.CommandConsumer(
        sm_url=SM_URL,
        session_id="s",
        secret=SECRET,
        executors={},
    )
    assert consumer.transport == "sse"
    consumer.close()


# ── v1.3 P4 item 5: removed-transports lookup parity ──────────────────


def test_removed_transports_table_carries_longpoll(consumer_module):
    """v1.3 folded the dual transport gate (``transport == "long-poll"``
    + ``not in _VALID_TRANSPORTS``) into a single
    ``_REMOVED_TRANSPORTS`` lookup. The table must continue to carry
    the long-poll migration message verbatim so operators upgrading from
    v1.1 see the same actionable hint.
    """
    assert "long-poll" in consumer_module._REMOVED_TRANSPORTS
    msg = consumer_module._REMOVED_TRANSPORTS["long-poll"]
    assert msg == consumer_module._LONGPOLL_REMOVED_MSG


def test_unknown_transport_uses_generic_message(consumer_module):
    """A transport that is not in ``_REMOVED_TRANSPORTS`` and not in
    ``_VALID_TRANSPORTS`` must fall through to the generic 'must be one
    of …' error — NOT the long-poll migration message. This guards
    behavioral parity with v1.2 after the table fold.
    """
    with pytest.raises(ValueError) as exc_info:
        consumer_module.CommandConsumer(
            sm_url=SM_URL,
            session_id="s",
            secret=SECRET,
            executors={},
            transport="websocket",
        )
    msg = str(exc_info.value)
    assert "must be one of" in msg
    assert "websocket" in msg
    # Critically, the long-poll migration hint must NOT leak into the
    # generic-invalid path.
    assert "long-poll" not in msg
    assert "ADR-14" not in msg
