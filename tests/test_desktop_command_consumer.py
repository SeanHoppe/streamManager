"""Tests for the governed-side desktop_command consumer (Task E).

Covers the security-critical happy + failure paths:
  - valid signed command → executor called → ack=ok
  - bad signature → executor NOT called → ack=rejected, error='bad_sig'
  - unknown kind → ack=rejected, error='unknown_kind'
  - executor raises → ack=rejected, error=str(exc)[:200]
  - poll loop sleeps poll_interval between iterations (recorded sleep_fn)

The HMAC secret is set via monkeypatch on SM_DESKTOP_SECRET so the test
never touches the real ``.bridge/secret`` file.
"""

from __future__ import annotations

import importlib
import sys
import threading
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


class _Recorder:
    """Captures every request the consumer issues against MockTransport."""

    def __init__(self) -> None:
        self.gets: list[httpx.Request] = []
        self.acks: list[tuple[str, dict]] = []

    def make_handler(self, pending_queue: list[list[dict]]):
        """Returns an httpx.MockTransport handler.

        ``pending_queue`` is a list-of-lists; each consumer GET pops the
        next list to return. When exhausted, returns ``[]`` forever.
        """

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET" and request.url.path == "/api/commands/pending":
                self.gets.append(request)
                rows = pending_queue.pop(0) if pending_queue else []
                return httpx.Response(200, json=rows)
            if (
                request.method == "POST"
                and request.url.path.startswith("/api/commands/")
                and request.url.path.endswith("/ack")
            ):
                # /api/commands/{id}/ack
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


# ─── Tests ────────────────────────────────────────────────────────────


def test_valid_command_executes_and_acks_ok(consumer_module, desktop_commands):
    row = _make_row(desktop_commands, cmd_id="cmd-ok", kind="pause", args={"why": "test"})
    rec = _Recorder()
    transport = httpx.MockTransport(rec.make_handler([[row]]))
    client = httpx.Client(transport=transport, base_url=SM_URL)

    seen: list[dict] = []

    def pause_executor(args: dict) -> None:
        seen.append(args)

    consumer = consumer_module.CommandConsumer(
        sm_url=SM_URL,
        session_id=SESSION_ID,
        secret=SECRET,
        executors={"pause": pause_executor},
        client=client,
    )

    n = consumer.run_once()
    assert n == 1
    assert seen == [{"why": "test"}]
    assert rec.acks == [("cmd-ok", {"status": "ok"})]


def test_bad_signature_rejects_without_executing(
    consumer_module, desktop_commands
):
    row = _make_row(desktop_commands, cmd_id="cmd-bad", tamper=True)
    rec = _Recorder()
    transport = httpx.MockTransport(rec.make_handler([[row]]))
    client = httpx.Client(transport=transport, base_url=SM_URL)

    calls = {"n": 0}

    def pause_executor(args: dict) -> None:
        calls["n"] += 1

    consumer = consumer_module.CommandConsumer(
        sm_url=SM_URL,
        session_id=SESSION_ID,
        secret=SECRET,
        executors={"pause": pause_executor},
        client=client,
    )

    consumer.run_once()
    assert calls["n"] == 0
    assert rec.acks == [("cmd-bad", {"status": "rejected", "error": "bad_sig"})]


def test_unknown_kind_rejects(consumer_module, desktop_commands):
    # Kind is in producer's KIND_ALLOWLIST but the consumer didn't register
    # an executor for it — this MUST still reject. Defence-in-depth: the
    # consumer trusts only its own executors map, never the producer.
    assert "audible_cue" in desktop_commands.KIND_ALLOWLIST
    row = _make_row(desktop_commands, cmd_id="cmd-unk", kind="audible_cue")
    rec = _Recorder()
    transport = httpx.MockTransport(rec.make_handler([[row]]))
    client = httpx.Client(transport=transport, base_url=SM_URL)

    consumer = consumer_module.CommandConsumer(
        sm_url=SM_URL,
        session_id=SESSION_ID,
        secret=SECRET,
        executors={"pause": lambda args: None},  # only pause registered
        client=client,
    )

    consumer.run_once()
    assert rec.acks == [
        ("cmd-unk", {"status": "rejected", "error": "unknown_kind"})
    ]


def test_executor_raises_acks_with_truncated_error(
    consumer_module, desktop_commands
):
    row = _make_row(desktop_commands, cmd_id="cmd-raise", kind="pause")
    rec = _Recorder()
    transport = httpx.MockTransport(rec.make_handler([[row]]))
    client = httpx.Client(transport=transport, base_url=SM_URL)

    def boom(args: dict) -> None:
        raise RuntimeError("kaboom")

    consumer = consumer_module.CommandConsumer(
        sm_url=SM_URL,
        session_id=SESSION_ID,
        secret=SECRET,
        executors={"pause": boom},
        client=client,
    )

    consumer.run_once()
    assert rec.acks == [
        ("cmd-raise", {"status": "rejected", "error": "kaboom"})
    ]


def test_executor_long_error_is_truncated(consumer_module, desktop_commands):
    row = _make_row(desktop_commands, cmd_id="cmd-long", kind="pause")
    rec = _Recorder()
    transport = httpx.MockTransport(rec.make_handler([[row]]))
    client = httpx.Client(transport=transport, base_url=SM_URL)

    long_msg = "x" * 500

    def boom(args: dict) -> None:
        raise RuntimeError(long_msg)

    consumer = consumer_module.CommandConsumer(
        sm_url=SM_URL,
        session_id=SESSION_ID,
        secret=SECRET,
        executors={"pause": boom},
        client=client,
    )

    consumer.run_once()
    assert len(rec.acks) == 1
    cmd_id, body = rec.acks[0]
    assert cmd_id == "cmd-long"
    assert body["status"] == "rejected"
    assert body["error"] == "x" * 200
    assert len(body["error"]) == 200


def test_run_forever_sleeps_poll_interval_between_iterations(
    consumer_module, desktop_commands
):
    rec = _Recorder()
    # Three iterations of empty pending lists.
    transport = httpx.MockTransport(rec.make_handler([[], [], []]))
    client = httpx.Client(transport=transport, base_url=SM_URL)

    sleeps: list[float] = []
    stop_event = threading.Event()

    def recording_sleep(secs: float) -> None:
        sleeps.append(secs)
        if len(sleeps) >= 3:
            stop_event.set()

    consumer = consumer_module.CommandConsumer(
        sm_url=SM_URL,
        session_id=SESSION_ID,
        secret=SECRET,
        executors={"pause": lambda args: None},
        client=client,
        poll_interval=1.0,
        sleep_fn=recording_sleep,
        stop_event=stop_event,
    )

    consumer.run_forever()
    assert sleeps == [1.0, 1.0, 1.0]
    # Three GETs were issued (one per iteration, before the sleep).
    assert len(rec.gets) == 3


def test_stop_method_terminates_loop(consumer_module, desktop_commands):
    rec = _Recorder()
    transport = httpx.MockTransport(rec.make_handler([[]]))
    client = httpx.Client(transport=transport, base_url=SM_URL)

    stop_event = threading.Event()
    sleeps: list[float] = []

    def recording_sleep(secs: float) -> None:
        sleeps.append(secs)

    consumer = consumer_module.CommandConsumer(
        sm_url=SM_URL,
        session_id=SESSION_ID,
        secret=SECRET,
        executors={"pause": lambda args: None},
        client=client,
        poll_interval=0.1,
        sleep_fn=recording_sleep,
        stop_event=stop_event,
    )
    # Pre-set the stop event so the loop runs exactly once and exits.
    stop_event.set()
    consumer.run_forever()
    # Loop must have iterated at least once before checking stop.
    assert len(sleeps) == 1


def test_default_executors_cover_full_allowlist(
    consumer_module, desktop_commands
):
    execs = consumer_module._default_executors()
    assert set(execs.keys()) == set(desktop_commands.KIND_ALLOWLIST)
    # Each is callable with a dict and returns None without raising.
    for fn in execs.values():
        assert fn({}) is None


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
