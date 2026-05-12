#!/usr/bin/env python
"""v10 P4 B' — subscriber overhead micro-bench (ADR-5 ship-gate).

Direct measurement of ``MessageBus.record_decision`` latency with vs
without the live-bus ``rl.bus_subscriber`` attached. Replaces the
soak-derived ``cli_dispatch_ms`` p95 gate in ADR-5 §"v10 logging
overhead" for the B' ship verification.

Why micro-bench instead of paired soak:
    1. Subscriber overhead lives **inside ``record_decision``'s lock +
       fan-out loop**, not inside ``cli_dispatch_ms``. The soak metric
       is a proxy by aggregation; direct timing of ``record_decision``
       is the exact seam B' modified.
    2. Runs in seconds, not minutes — eliminates soak-harness noise
       (cli_pool warmup, LM dialogue pump, SSE consumer, psutil
       sampling) none of which the subscriber path touches.
    3. Reproducible across machines / CI without spawning dashboard or
       claude workers.

Pass criterion (ADR-5 §B' addendum, post-tweak):
    Absolute ceilings on (ON - OFF) overhead. Relative-to-baseline does
    not work because record_decision baseline is sub-millisecond
    (single INSERT), so any subscriber adds a multi-hundred-percent
    relative diff while remaining trivial vs the cli_dispatch_ms p95
    budget (~2000ms). Ceilings are sized at <1% of that budget:
        - p50 overhead <= 1.0 ms   (0.05% of 2000ms cli_dispatch p95)
        - p95 overhead <= 5.0 ms   (0.25% of 2000ms)
        - p99 overhead <= 20.0 ms  (1.0%  of 2000ms; WAL flush spikes)

Usage::

    python tools/bench_subscriber_overhead.py [--n 10000]

Exit 0 on PASS, 2 on FAIL.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from stream_manager.message_bus import Message, MessageBus  # noqa: E402
from rl import bus_subscriber  # noqa: E402


def _percentile(xs: list[float], p: float) -> float:
    s = sorted(xs)
    if not s:
        return float("nan")
    k = int(round((p / 100.0) * (len(s) - 1)))
    return s[k]


def _stats(xs: list[float]) -> dict[str, float]:
    return {
        "n": float(len(xs)),
        "p50": _percentile(xs, 50),
        "p95": _percentile(xs, 95),
        "p99": _percentile(xs, 99),
        "mean": statistics.fmean(xs),
        "stdev": statistics.stdev(xs) if len(xs) > 1 else 0.0,
    }


def _run(*, n: int, with_subscriber: bool) -> list[float]:
    """One arm: seed n messages, time n record_decision calls."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        bus = MessageBus(str(td_path / "gov.db"))
        bus.open_session("bench-sess", project_slug="bench", pid=os.getpid())

        # Pre-seed messages so record_decision has FK-valid message_ids.
        msg_ids: list[str] = []
        for i in range(n):
            m = Message.new(
                session_id="bench-sess",
                type="tool",
                direction="inbound",
                content=f"m{i}",
            )
            bus.publish(m)
            msg_ids.append(m.id)

        close_fn = lambda: None  # noqa: E731
        if with_subscriber:
            os.environ["BRIDGE_RL_LOGGER_ENABLED"] = "1"
            close_fn = bus_subscriber.attach(bus, td_path / "rl_episodes.db")

        samples: list[float] = []
        for mid in msg_ids:
            t0 = time.perf_counter()
            bus.record_decision(
                message_id=mid,
                action="ALLOW",
                confidence=0.9,
                reasoning="bench",
            )
            samples.append((time.perf_counter() - t0) * 1000.0)

        try:
            close_fn()
        finally:
            os.environ.pop("BRIDGE_RL_LOGGER_ENABLED", None)
        bus.close()
    return samples


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10_000,
                    help="record_decision iterations per arm (default 10_000)")
    # Absolute ms ceilings on (ON - OFF) overhead. Defaults sized at
    # <1% of typical cli_dispatch_ms p95 budget (~2000ms).
    ap.add_argument("--p50-gate-ms", type=float, default=1.0)
    ap.add_argument("--p95-gate-ms", type=float, default=5.0)
    ap.add_argument("--p99-gate-ms", type=float, default=20.0)
    args = ap.parse_args(argv)

    n = args.n
    print(f"[bench] n={n} per arm; warming…")
    _ = _run(n=min(500, n), with_subscriber=False)  # warm caches
    print(f"[bench] OFF arm running…")
    t0 = time.perf_counter()
    off = _run(n=n, with_subscriber=False)
    off_wall = time.perf_counter() - t0
    print(f"[bench] OFF wall={off_wall:.1f}s")
    print(f"[bench] ON  arm running…")
    t0 = time.perf_counter()
    on = _run(n=n, with_subscriber=True)
    on_wall = time.perf_counter() - t0
    print(f"[bench] ON  wall={on_wall:.1f}s")

    off_s = _stats(off)
    on_s = _stats(on)
    print("\n=== MessageBus.record_decision latency (ms) ===")
    print(f"OFF (control)    : {off_s}")
    print(f"ON  (subscriber) : {on_s}")
    print()
    print("=== overhead (ON - OFF) absolute ms ===")
    failed: list[str] = []
    gates_ms = {"p50": args.p50_gate_ms, "p95": args.p95_gate_ms,
                "p99": args.p99_gate_ms}
    for key, gate_ms in gates_ms.items():
        base = off_s[key]
        delta_ms = on_s[key] - base
        rel_pct = (delta_ms / base * 100.0) if base > 0 else float("inf")
        status = "PASS" if delta_ms <= gate_ms else "FAIL"
        print(f"  d{key:>3}: {delta_ms:+.4f}ms  (rel {rel_pct:+.1f}% of "
              f"baseline; budget <={gate_ms:.1f}ms)  {status}")
        if status == "FAIL":
            failed.append(f"{key} {delta_ms:+.4f}ms > {gate_ms:.1f}ms")

    # Side-info: mean is sensitive to long-tail; report for context only.
    mean_delta = on_s["mean"] - off_s["mean"]
    mean_delta_pct = ((mean_delta / off_s["mean"]) * 100.0
                      if off_s["mean"] > 0 else 0.0)
    print(f"  dmean (info): {mean_delta:+.4f}ms ({mean_delta_pct:+.1f}%)")

    if failed:
        print(f"\nFAIL: {len(failed)} gate(s) breached — {', '.join(failed)}")
        return 2
    print("\nPASS: all gates within budget.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
