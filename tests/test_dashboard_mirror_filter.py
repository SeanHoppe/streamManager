"""SSE filter tests for the Session Mirror frame (Task C).

Covers:
  1. With ``?session_id=X&types=tool_call,tool_result``, the stream
     yields only matching rows.
  2. Rows whose ``session_id`` matches ``SM_OWN_SESSION_ID`` are
     filtered server-side regardless of params (no-self-monitor).
  3. Type allowlist ignores unknown / malicious values.

Reuses the live-uvicorn pattern from test_hitl_mode_sse_roundtrip.py.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import json
import socket
import sys

import httpx
import pytest
import uvicorn

from stream_manager.message_bus import Message, MessageBus


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def live_server(tmp_path, monkeypatch):
    db = tmp_path / "gov.db"
    monkeypatch.setenv("GOV_DB", str(db))
    monkeypatch.setenv("SM_OWN_SESSION_ID", "sm-owner")

    if "dashboard.server" in sys.modules:
        del sys.modules["dashboard.server"]
    server = importlib.import_module("dashboard.server")

    bus = MessageBus(str(db))
    bus.open_session("s-target")
    bus.open_session("s-other")
    bus.open_session("sm-owner")
    server._bus = bus

    port = _free_port()
    config = uvicorn.Config(
        app=server.app, host="127.0.0.1", port=port,
        log_level="warning", lifespan="off",
    )
    uv = uvicorn.Server(config)
    serve_task = asyncio.create_task(uv.serve())

    deadline = asyncio.get_event_loop().time() + 5.0
    while not uv.started and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.05)
    if not uv.started:
        uv.should_exit = True
        await serve_task
        raise RuntimeError("uvicorn failed to start within 5s")

    try:
        yield f"http://127.0.0.1:{port}", bus
    finally:
        uv.should_exit = True
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await asyncio.wait_for(serve_task, timeout=5.0)


def _publish(bus: MessageBus, session_id: str, msg_type: str, content: str = "") -> None:
    bus.publish(
        Message.new(
            session_id=session_id,
            type=msg_type,
            direction="inbound",
            content=content,
            metadata={},
        )
    )


async def _consume(base_url: str, query: str, captured: list, started: asyncio.Event,
                   stop: asyncio.Event) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=None) as client:
        async with client.stream("GET", f"/events?{query}") as resp:
            assert resp.status_code == 200
            started.set()
            buf = ""
            async for chunk in resp.aiter_text():
                if stop.is_set():
                    return
                buf += chunk
                while "\n\n" in buf:
                    frame, buf = buf.split("\n\n", 1)
                    data_line = next(
                        (ln for ln in frame.splitlines()
                         if ln.startswith("data:")),
                        None,
                    )
                    if data_line is None:
                        continue
                    try:
                        captured.append(
                            json.loads(data_line[len("data:"):].strip())
                        )
                    except json.JSONDecodeError:
                        continue


async def _drive(live_server, query: str, publishes: list[tuple[str, str, str]],
                 settle_seconds: float = 1.5) -> list[dict]:
    base_url, bus = live_server
    captured: list = []
    started = asyncio.Event()
    stop = asyncio.Event()

    consumer = asyncio.create_task(_consume(base_url, query, captured, started, stop))
    try:
        await asyncio.wait_for(started.wait(), timeout=3.0)
        # Past SSE seed phase (handler sleeps 0.5s between polls).
        await asyncio.sleep(0.6)
        for sid, mtype, content in publishes:
            _publish(bus, sid, mtype, content)
        await asyncio.sleep(settle_seconds)
    finally:
        stop.set()
        consumer.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await consumer
    return captured


async def test_mirror_filters_to_session_and_types(live_server):
    captured = await _drive(
        live_server,
        "session_id=s-target&types=tool_call,tool_result",
        [
            ("s-target", "tool_call",   "ls -la"),
            ("s-target", "tool_result", "ok"),
            ("s-other",  "tool_call",   "noisy"),       # wrong session
            ("s-target", "governance_eval", "noise"),   # wrong type
        ],
    )
    types = [(p.get("session_id"), p.get("event_type") or p.get("type")) for p in captured]
    # Only s-target tool_call + tool_result should flow.
    assert ("s-target", "tool_call") in types
    assert ("s-target", "tool_result") in types
    # Cross-session row must be filtered.
    assert ("s-other", "tool_call") not in types
    # Wrong type must be filtered.
    assert ("s-target", "governance_eval") not in types


async def test_mirror_filters_sm_own_session_id(live_server):
    captured = await _drive(
        live_server,
        "session_id=sm-owner&types=tool_call,tool_result",
        [
            ("sm-owner", "tool_call", "self-monitor attempt"),
            ("s-target", "tool_call", "legit"),
        ],
    )
    sids = {p.get("session_id") for p in captured}
    assert "sm-owner" not in sids, "SM_OWN_SESSION_ID rows must be filtered server-side"


async def test_mirror_types_allowlist_ignores_unknown(live_server):
    # Pass a junk type alongside a valid one; only the valid one should
    # reach the SQL. Unknown type names must NOT widen the stream.
    captured = await _drive(
        live_server,
        "session_id=s-target&types=tool_call,governance_eval",  # 2nd ignored
        [
            ("s-target", "tool_call",       "valid"),
            ("s-target", "governance_eval", "should-not-pass"),
        ],
    )
    types = [(p.get("session_id"), p.get("event_type") or p.get("type")) for p in captured]
    assert ("s-target", "tool_call") in types
    assert ("s-target", "governance_eval") not in types
