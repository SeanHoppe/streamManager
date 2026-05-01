"""Spike A — fake Desktop side. Sends N pings, measures round-trip latency."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time

from websockets.asyncio.client import connect


async def bench(uri: str, n: int) -> list[float]:
    latencies_ms: list[float] = []
    async with connect(uri) as ws:
        for i in range(n):
            t0 = time.perf_counter()
            await ws.send(json.dumps({"id": i, "ping": t0}))
            _ = await ws.recv()
            t1 = time.perf_counter()
            latencies_ms.append((t1 - t0) * 1000.0)
    return latencies_ms


def _pct(values: list[float], q: float) -> float:
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(q * len(s))))
    return s[idx]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--uri", default="ws://127.0.0.1:8765")
    p.add_argument("--n", type=int, default=1000)
    args = p.parse_args()

    t0 = time.perf_counter()
    latencies = asyncio.run(bench(args.uri, args.n))
    elapsed = time.perf_counter() - t0

    print(f"n           = {args.n}")
    print(f"elapsed     = {elapsed:.3f} s")
    print(f"throughput  = {args.n / elapsed:.1f} msg/s")
    print(f"median (ms) = {statistics.median(latencies):.2f}")
    print(f"p95    (ms) = {_pct(latencies, 0.95):.2f}")
    print(f"p99    (ms) = {_pct(latencies, 0.99):.2f}")
    print(f"min    (ms) = {min(latencies):.2f}")
    print(f"max    (ms) = {max(latencies):.2f}")


if __name__ == "__main__":
    main()
