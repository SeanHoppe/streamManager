from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from websockets.asyncio.client import connect

from stream_manager.cli_client import WireCLI, strip_ansi

ECHO_SCRIPT = Path(__file__).parent.parent / "spikes" / "poc_wire" / "echo_subprocess.py"


def test_strip_ansi_removes_color_codes() -> None:
    raw = "\x1b[33mhello\x1b[0m world"
    assert strip_ansi(raw) == "hello world"


def test_strip_ansi_removes_cursor_moves() -> None:
    raw = "before\x1b[2J\x1b[H\x1b[1;5Hafter"
    assert strip_ansi(raw) == "beforeafter"


def test_strip_ansi_passes_through_plain_text() -> None:
    raw = "plain ASCII line\nwith newline"
    assert strip_ansi(raw) == raw


def test_strip_ansi_handles_osc_sequences() -> None:
    raw = "title:\x1b]0;window-title\x07after"
    assert strip_ansi(raw) == "title:after"


async def _read_until(ws, needle: str, timeout: float = 3.0) -> str:  # type: ignore[no-untyped-def]
    end = asyncio.get_event_loop().time() + timeout
    collected: list[str] = []
    while asyncio.get_event_loop().time() < end:
        remaining = end - asyncio.get_event_loop().time()
        try:
            line = await asyncio.wait_for(ws.recv(), timeout=remaining)
        except asyncio.TimeoutError:
            break
        collected.append(str(line))
        if needle in str(line):
            return str(line)
    raise AssertionError(f"never saw {needle!r}; got: {collected}")


@pytest.mark.asyncio
async def test_wire_cli_proxies_subprocess_to_ws_client(unused_tcp_port: int) -> None:
    wire = WireCLI(cmd=[sys.executable, str(ECHO_SCRIPT)], port=unused_tcp_port)
    server_task = asyncio.create_task(wire.run())
    try:
        await asyncio.sleep(0.5)
        async with connect(f"ws://127.0.0.1:{unused_tcp_port}") as ws:
            await ws.send("ping")
            reply = await _read_until(ws, "ping")
            assert "[echo]" in reply
            assert "\x1b" not in reply, "ANSI should be stripped"
    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_wire_cli_supports_multi_client_broadcast(unused_tcp_port: int) -> None:
    wire = WireCLI(cmd=[sys.executable, str(ECHO_SCRIPT)], port=unused_tcp_port)
    server_task = asyncio.create_task(wire.run())
    try:
        await asyncio.sleep(0.5)
        async with (
            connect(f"ws://127.0.0.1:{unused_tcp_port}") as ws_a,
            connect(f"ws://127.0.0.1:{unused_tcp_port}") as ws_b,
        ):
            await ws_a.send("broadcast-me")
            reply_a = await _read_until(ws_a, "broadcast-me")
            reply_b = await _read_until(ws_b, "broadcast-me")
            assert "[echo]" in reply_a
            assert "[echo]" in reply_b
    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_wire_cli_terminates_subprocess_on_stop(unused_tcp_port: int) -> None:
    wire = WireCLI(cmd=[sys.executable, str(ECHO_SCRIPT)], port=unused_tcp_port)
    server_task = asyncio.create_task(wire.run())
    await asyncio.sleep(0.5)
    assert wire.proc is not None
    assert wire.proc.returncode is None

    server_task.cancel()
    try:
        await server_task
    except asyncio.CancelledError:
        pass
    await asyncio.sleep(0.5)
    assert wire.proc.returncode is not None, "subprocess must be reaped after server task cancel"
