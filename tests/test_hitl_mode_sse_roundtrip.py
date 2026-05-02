"""Live-wire SSE round-trip test for `hitl_mode_promoted`.

POST /api/hitl/mode and verify a `hitl_mode_promoted` SSE frame arrives at a
connected /events client within 2 seconds. Covers FR-HITL-1 / FR-UI-4 /
FR-UI-8 end-to-end (previously only indirect coverage via the
``direction='internal'`` forwarder in test_hitl_mode_persist.py).

Why a real uvicorn server: httpx's ASGITransport buffers the entire response
body before returning (it appends to ``body_parts`` and only finalizes when
``more_body=False``). SSE generators never complete, so an in-process
ASGITransport hangs forever on the streaming GET. Booting uvicorn on an
ephemeral port keeps the test self-contained while exercising the real
ASGI/HTTP path that browsers use.
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


SESSION_ID = "s-sse-roundtrip"


def _free_port() -> int:
    """Reserve an ephemeral TCP port and release it for uvicorn to bind."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def live_server(tmp_path, monkeypatch):
    """Boot dashboard.server in-process under uvicorn on an ephemeral port.

    Mirrors the importlib.reload pattern from test_hitl_mode_persist.py so
    the module re-reads ``GOV_DB`` on import. Pre-seeds a session row so
    POST /api/hitl/mode won't 422.
    """
    db = tmp_path / "gov.db"
    monkeypatch.setenv("GOV_DB", str(db))

    if "dashboard.server" in sys.modules:
        del sys.modules["dashboard.server"]
    server = importlib.import_module("dashboard.server")

    from stream_manager.message_bus import MessageBus
    bus = MessageBus(str(db))
    bus.open_session(SESSION_ID)
    bus.set_hitl_mode(SESSION_ID, "async", 0.60)
    server._bus = bus

    port = _free_port()
    config = uvicorn.Config(
        app=server.app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        lifespan="off",
    )
    uv = uvicorn.Server(config)
    serve_task = asyncio.create_task(uv.serve())

    # Wait for the server to start accepting connections (bounded).
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


async def _consume_until_promoted(
    base_url: str,
    saw_promoted: asyncio.Event,
    captured: dict,
    started: asyncio.Event,
) -> None:
    """Stream /events; set ``saw_promoted`` once a hitl_mode_promoted arrives."""
    async with httpx.AsyncClient(base_url=base_url, timeout=None) as client:
        async with client.stream("GET", "/events") as resp:
            assert resp.status_code == 200
            started.set()
            buf = ""
            async for chunk in resp.aiter_text():
                buf += chunk
                while "\n\n" in buf:
                    frame, buf = buf.split("\n\n", 1)
                    data_line = next(
                        (
                            ln for ln in frame.splitlines()
                            if ln.startswith("data:")
                        ),
                        None,
                    )
                    if data_line is None:
                        continue
                    try:
                        payload = json.loads(
                            data_line[len("data:"):].strip()
                        )
                    except json.JSONDecodeError:
                        continue
                    # Bus events are forwarded with `type` renamed to
                    # `event_type` (see dashboard.server SSE handler);
                    # tolerate either spelling.
                    ev_type = (
                        payload.get("event_type") or payload.get("type")
                    )
                    if ev_type == "hitl_mode_promoted":
                        captured["payload"] = payload
                        saw_promoted.set()
                        return


async def test_hitl_mode_promoted_arrives_via_sse(live_server):
    base_url, _bus = live_server

    saw_promoted = asyncio.Event()
    started = asyncio.Event()
    captured: dict = {}

    consumer = asyncio.create_task(
        _consume_until_promoted(base_url, saw_promoted, captured, started)
    )
    try:
        # Wait for the SSE stream to be open and past its seed phase before
        # we POST, so the bus row will arrive on a later poll iteration and
        # the consumer is guaranteed to observe it (rather than racing with
        # the seed snapshot of MAX(rowid)).
        await asyncio.wait_for(started.wait(), timeout=3.0)
        # 0.6s > the SSE handler's 0.5s sleep — guarantees seed phase done.
        await asyncio.sleep(0.6)

        async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as c:
            r = await c.post(
                "/api/hitl/mode",
                json={
                    "session_id": SESSION_ID,
                    "mode": "sync",
                    "reason": "take_action",
                },
            )
            assert r.status_code == 200, r.text

        try:
            await asyncio.wait_for(saw_promoted.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pytest.fail(
                "no hitl_mode_promoted SSE frame seen within 2s of POST"
            )

        payload = captured["payload"]
        ev_type = payload.get("event_type") or payload.get("type")
        assert ev_type == "hitl_mode_promoted"
        assert payload.get("session_id") == SESSION_ID

        # metadata is JSON-encoded in the messages row; decode if str.
        meta = payload.get("metadata")
        if isinstance(meta, str):
            meta = json.loads(meta)
        assert meta is not None, payload
        # Server emits new_mode/old_mode; the spec calls it "mode" but the
        # actual emitted field is new_mode. Accept either to stay robust.
        mode_val = meta.get("new_mode") or meta.get("mode")
        assert mode_val == "sync", meta
        assert meta.get("reason") == "take_action", meta
    finally:
        consumer.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await consumer
