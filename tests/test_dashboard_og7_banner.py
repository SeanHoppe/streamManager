"""SSE forwarding test for FR-OG-7 loud-degrade `og7_unconfigured` event.

Verifies: when the bus publishes an `og7_unconfigured` row, a
connected `/events` SSE client receives a frame whose `event_type`
matches and whose metadata carries `expected_path` + `project_root`
so the dashboard banner can render.
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

from stream_manager.message_bus import Message


SESSION_ID = "s-og7-banner"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def live_server(tmp_path, monkeypatch):
    db = tmp_path / "gov.db"
    monkeypatch.setenv("GOV_DB", str(db))

    if "dashboard.server" in sys.modules:
        del sys.modules["dashboard.server"]
    server = importlib.import_module("dashboard.server")

    from stream_manager.message_bus import MessageBus
    bus = MessageBus(str(db))
    bus.open_session(SESSION_ID)
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


async def _consume_until_og7(
    base_url: str, saw: asyncio.Event, captured: dict, started: asyncio.Event,
) -> None:
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
                        (ln for ln in frame.splitlines()
                         if ln.startswith("data:")),
                        None,
                    )
                    if data_line is None:
                        continue
                    try:
                        payload = json.loads(data_line[len("data:"):].strip())
                    except json.JSONDecodeError:
                        continue
                    ev_type = payload.get("event_type") or payload.get("type")
                    if ev_type == "og7_unconfigured":
                        captured["payload"] = payload
                        saw.set()
                        return


async def test_og7_unconfigured_arrives_via_sse(live_server):
    base_url, bus = live_server

    saw = asyncio.Event()
    started = asyncio.Event()
    captured: dict = {}

    consumer = asyncio.create_task(
        _consume_until_og7(base_url, saw, captured, started)
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=3.0)
        # Past the SSE seed phase (handler sleeps 0.5s between polls).
        await asyncio.sleep(0.6)

        bus.publish(
            Message.new(
                session_id=SESSION_ID,
                type="og7_unconfigured",
                direction="internal",
                content="FR-OG-7 inactive: .sm-context.yaml missing",
                metadata={
                    "project_root": "/tmp/proj",
                    "expected_path": "/tmp/proj/.sm-context.yaml",
                },
            )
        )

        try:
            await asyncio.wait_for(saw.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pytest.fail("no og7_unconfigured SSE frame within 2s of publish")

        payload = captured["payload"]
        ev_type = payload.get("event_type") or payload.get("type")
        assert ev_type == "og7_unconfigured"
        assert payload.get("session_id") == SESSION_ID

        meta = payload.get("metadata")
        if isinstance(meta, str):
            meta = json.loads(meta)
        assert meta is not None, payload
        assert meta.get("project_root") == "/tmp/proj"
        assert meta.get("expected_path", "").endswith(".sm-context.yaml")
    finally:
        consumer.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await consumer
