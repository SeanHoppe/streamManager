"""Spike C smoke client. Connects to wire CLI, sends N prompts, prints responses."""

from __future__ import annotations

import argparse
import asyncio

from websockets.asyncio.client import connect


async def smoke(uri: str, prompts: list[str], timeout: float) -> list[str]:
    received: list[str] = []
    async with connect(uri) as ws:
        for prompt in prompts:
            await ws.send(prompt)
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    received.append(str(msg))
                    if str(msg).strip():
                        break
            except asyncio.TimeoutError:
                received.append("(timeout)")
    return received


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--uri", default="ws://127.0.0.1:8767")
    p.add_argument("--timeout", type=float, default=2.0)
    p.add_argument("prompts", nargs="*", default=["hello world", "second message"])
    args = p.parse_args()
    results = asyncio.run(smoke(args.uri, args.prompts, args.timeout))
    for line in results:
        print(line)


if __name__ == "__main__":
    main()
