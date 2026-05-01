from __future__ import annotations

import asyncio
import logging

from websockets.asyncio.server import ServerConnection, serve

from stream_manager.config import BridgeConfig
from stream_manager.governance import NoOpGovernance
from stream_manager.message_bus import Message, MessageBus

log = logging.getLogger(__name__)


class Router:
    """Two WebSocket servers wired through the bus + governance hookpoint.

    Spike A scope: persists every message, evaluates noop governance, broadcasts
    forward. Renamed from the doc's stream_manager.py to avoid colliding with
    the package name.
    """

    def __init__(
        self,
        config: BridgeConfig,
        bus: MessageBus,
        governance: NoOpGovernance,
        session_id: str,
    ) -> None:
        self.config = config
        self.bus = bus
        self.governance = governance
        self.session_id = session_id
        self.desktop_clients: set[ServerConnection] = set()
        self.cli_clients: set[ServerConnection] = set()

    async def _route(
        self,
        ws: ServerConnection,
        peer_set: set[ServerConnection],
        own_set: set[ServerConnection],
        direction: str,
        msg_type: str,
    ) -> None:
        own_set.add(ws)
        try:
            async for raw in ws:
                content = raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")
                msg = Message.new(self.session_id, msg_type, direction, content)
                self.bus.publish(msg)
                decision = self.governance.evaluate(msg)
                if decision.action == "BLOCK":
                    continue
                if peer_set:
                    await asyncio.gather(
                        *[peer.send(content) for peer in list(peer_set)],
                        return_exceptions=True,
                    )
        finally:
            own_set.discard(ws)

    async def _handle_desktop(self, ws: ServerConnection) -> None:
        await self._route(ws, self.cli_clients, self.desktop_clients, "desktop_to_cli", "user")

    async def _handle_cli(self, ws: ServerConnection) -> None:
        await self._route(ws, self.desktop_clients, self.cli_clients, "cli_to_desktop", "assistant")

    async def run(self) -> None:
        self.bus.open_session(self.session_id)
        try:
            async with (
                serve(self._handle_desktop, self.config.host, self.config.desktop_port) as ds,
                serve(self._handle_cli, self.config.host, self.config.cli_port) as cs,
            ):
                log.info(
                    "Desktop WS ws://%s:%d  CLI WS ws://%s:%d  session=%s",
                    self.config.host,
                    self.config.desktop_port,
                    self.config.host,
                    self.config.cli_port,
                    self.session_id,
                )
                _ = ds, cs
                await asyncio.Future()
        finally:
            self.bus.close_session(self.session_id)
