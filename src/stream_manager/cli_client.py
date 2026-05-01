from __future__ import annotations

import asyncio
import logging
import re
from typing import Sequence

from websockets.asyncio.server import ServerConnection, serve

log = logging.getLogger(__name__)

# CSI escape sequences (color, cursor moves, etc). Doesn't catch OSC/DCS, but
# those are rare in non-interactive CLI output. Documented gap.
ANSI_CSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
ANSI_OSC_RE = re.compile(r"\x1b\][^\x07\x1b]*(\x07|\x1b\\)")


def strip_ansi(text: str) -> str:
    text = ANSI_OSC_RE.sub("", text)
    return ANSI_CSI_RE.sub("", text)


class WireCLI:
    """Wraps a subprocess and exposes its stdio over a WebSocket server.

    Spike C scope: validates the IPC story end-to-end. No bus, no governance,
    no Desktop-side negotiation. Multi-client broadcast supported.
    """

    def __init__(
        self,
        cmd: Sequence[str],
        host: str = "127.0.0.1",
        port: int = 8767,
        strip_ansi_output: bool = True,
    ) -> None:
        self.cmd = list(cmd)
        self.host = host
        self.port = port
        self.strip_ansi_output = strip_ansi_output
        self.proc: asyncio.subprocess.Process | None = None
        self.clients: set[ServerConnection] = set()
        self._stdout_task: asyncio.Task[None] | None = None
        self._shutdown = asyncio.Event()

    async def _spawn(self) -> None:
        log.info("spawning subprocess: %s", " ".join(self.cmd))
        self.proc = await asyncio.create_subprocess_exec(
            *self.cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        log.info("subprocess pid=%d", self.proc.pid)

    async def _broadcast(self, line: str) -> None:
        if not self.clients:
            return
        await asyncio.gather(
            *[c.send(line) for c in list(self.clients)],
            return_exceptions=True,
        )

    async def _pump_stdout(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        buf = b""
        while True:
            chunk = await self.proc.stdout.read(4096)
            if not chunk:
                if buf:
                    text = buf.decode("utf-8", errors="replace")
                    if self.strip_ansi_output:
                        text = strip_ansi(text)
                    await self._broadcast(text)
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                text = line.decode("utf-8", errors="replace")
                if self.strip_ansi_output:
                    text = strip_ansi(text)
                await self._broadcast(text)
        log.info("subprocess stdout closed")
        self._shutdown.set()

    async def _handle_ws(self, ws: ServerConnection) -> None:
        self.clients.add(ws)
        log.info("client connected; total=%d", len(self.clients))
        try:
            async for raw in ws:
                if self.proc is None or self.proc.stdin is None or self.proc.stdin.is_closing():
                    break
                payload = raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")
                if not payload.endswith("\n"):
                    payload += "\n"
                self.proc.stdin.write(payload.encode("utf-8"))
                await self.proc.stdin.drain()
        finally:
            self.clients.discard(ws)
            log.info("client disconnected; total=%d", len(self.clients))

    async def run(self) -> int:
        await self._spawn()
        assert self.proc is not None
        self._stdout_task = asyncio.create_task(self._pump_stdout())
        try:
            async with serve(self._handle_ws, self.host, self.port):
                log.info("wire WS on ws://%s:%d wrapping pid=%d", self.host, self.port, self.proc.pid)
                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(self._shutdown.wait()),
                        asyncio.create_task(self.proc.wait()),
                    ],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()
        finally:
            await self._teardown()
        return self.proc.returncode if self.proc.returncode is not None else -1

    async def _teardown(self) -> None:
        if self.proc is None:
            return
        if self.proc.returncode is None:
            try:
                if self.proc.stdin is not None and not self.proc.stdin.is_closing():
                    self.proc.stdin.close()
            except OSError:
                pass
            try:
                await asyncio.wait_for(self.proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                log.warning("subprocess did not exit on stdin close; terminating")
                self.proc.terminate()
                try:
                    await asyncio.wait_for(self.proc.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    log.warning("subprocess unresponsive; killing")
                    self.proc.kill()
                    await self.proc.wait()
        if self._stdout_task and not self._stdout_task.done():
            self._stdout_task.cancel()
            try:
                await self._stdout_task
            except asyncio.CancelledError:
                pass
        log.info("teardown complete; subprocess returncode=%s", self.proc.returncode)
