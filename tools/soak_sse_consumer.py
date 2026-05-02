#!/usr/bin/env python
"""SSE consumer for the Task 6 real-CLI soak.

Connects to the dashboard's ``/events`` SSE endpoint and writes a metrics
log: one line per received event with monotonic timestamp + event id.
Designed to run as a separate process from the soak driver so a hang on
either side doesn't break the other's metrics.

Usage::

    python tools/soak_sse_consumer.py \\
        --url http://127.0.0.1:8766/events \\
        --log tmp/soak_sse.log \\
        --duration 1900

The process exits cleanly after ``--duration`` seconds OR when the
dashboard closes the connection. All exceptions are logged + re-raised
only if they prevent any progress; transient HTTP errors get a backoff
retry so a brief server restart doesn't kill the consumer.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:  # pragma: no cover - environment guard
    print("httpx is required: pip install httpx", file=sys.stderr)
    sys.exit(1)


def _now_iso() -> str:
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def consume(url: str, log_path: Path, duration_s: float) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + duration_s
    received = 0
    errors = 0
    backoff = 1.0

    with log_path.open("w", encoding="utf-8") as logf:
        logf.write(
            json.dumps({
                "event": "consumer_start",
                "url": url,
                "duration_s": duration_s,
                "wall": _now_iso(),
            }) + "\n"
        )
        logf.flush()

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            try:
                # httpx stream context exits cleanly when the server
                # disconnects. Use a generous read timeout so the 0.5s
                # poll pulse from the server doesn't trip a timeout.
                timeout = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
                with httpx.Client(timeout=timeout) as client:
                    with client.stream("GET", url) as resp:
                        resp.raise_for_status()
                        backoff = 1.0  # reset on successful connect
                        last_event_id: str | None = None
                        for line in resp.iter_lines():
                            if time.monotonic() >= deadline:
                                break
                            if not line:
                                continue
                            if line.startswith("id:"):
                                last_event_id = line[3:].strip()
                                continue
                            if line.startswith("data:"):
                                received += 1
                                ts_mono = time.monotonic()
                                logf.write(
                                    json.dumps({
                                        "event": "sse_event",
                                        "n": received,
                                        "id": last_event_id,
                                        "wall": _now_iso(),
                                        "mono": ts_mono,
                                    }) + "\n"
                                )
                                logf.flush()
                # Connection closed by server before deadline; loop and reconnect.
                if time.monotonic() < deadline:
                    logf.write(
                        json.dumps({
                            "event": "stream_closed_reconnect",
                            "wall": _now_iso(),
                        }) + "\n"
                    )
                    logf.flush()
                    time.sleep(min(backoff, remaining))
                    backoff = min(backoff * 2.0, 10.0)
            except (httpx.HTTPError, OSError) as exc:
                errors += 1
                logf.write(
                    json.dumps({
                        "event": "consumer_error",
                        "err": str(exc),
                        "wall": _now_iso(),
                    }) + "\n"
                )
                logf.flush()
                time.sleep(min(backoff, max(0.0, deadline - time.monotonic())))
                backoff = min(backoff * 2.0, 10.0)

        logf.write(
            json.dumps({
                "event": "consumer_stop",
                "received": received,
                "errors": errors,
                "wall": _now_iso(),
            }) + "\n"
        )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default="http://127.0.0.1:8766/events")
    ap.add_argument("--log", required=True, help="Path to per-event NDJSON log")
    ap.add_argument(
        "--duration",
        type=float,
        default=1900.0,
        help="Seconds to consume before exiting (default 1900s ≈ 31m 40s)",
    )
    args = ap.parse_args()
    return consume(args.url, Path(args.log), args.duration)


if __name__ == "__main__":
    raise SystemExit(main())
