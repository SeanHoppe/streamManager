"""Spike A — fake Claude CLI side. Connects to ws://host:cli_port and echoes."""

from __future__ import annotations

import argparse
import asyncio

from websockets.asyncio.client import connect


async def echo_loop(uri: str) -> None:
    async with connect(uri) as ws:
        async for msg in ws:
            await ws.send(msg)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--uri", default="ws://127.0.0.1:8766")
    args = p.parse_args()
    asyncio.run(echo_loop(args.uri))


if __name__ == "__main__":
    main()
