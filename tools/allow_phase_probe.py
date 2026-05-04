#!/usr/bin/env python
"""v1.4 — ALLOW publish-path phase probe.

Drives N routine ALLOW envelopes through ``engine.evaluate()`` and
collects per-phase timings via ``engine._last_phase_timings_ms`` (the
v1.4 instrumentation hook). Diagnoses the ADR-5 v1.3 §"Caveats"
ALLOW p95 tail without burning model quota — routine envelopes are L0
short-circuit so no `claude` subprocess is spawned.

Output
------

Markdown report at ``reports/allow-phase-{ISO-ts}.md`` with per-phase
n / p50 / p95 / max in milliseconds. Stdout summary row.

Usage
-----

    PYTHONPATH=src python tools/allow_phase_probe.py --n 200

    # custom DB (defaults to a throwaway tmp/allow_probe_gov.db)
    PYTHONPATH=src python tools/allow_phase_probe.py --n 500 \\
        --gov-db tmp/perf_test.db

The probe is intentionally cheap: a 200-call probe completes in a
few seconds on a warm bus. Run it after a v1.4 publish-path change
to confirm no per-call regression sneaks in.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from stream_manager.governance import GovernanceEngine  # noqa: E402
from stream_manager.message_bus import MessageBus  # noqa: E402
from stream_manager.messages import Message  # noqa: E402
from stream_manager.project_context import load as load_project_context  # noqa: E402

# Reuse the soak driver's helpers + payload mix so probe attribution
# matches what the soak driver would record.
from soak_driver import (  # noqa: E402
    _ALLOW_PHASE_ORDER,
    _format_allow_phase_breakout,
    _percentile,
)


_DEFAULT_PAYLOADS = [
    "ruff check src/",
    "pytest tests/ -q",
    "git status",
    "git diff --stat",
    "ls src/stream_manager",
    "ruff format --check src/",
    "git log --oneline -n 5",
    "git branch --show-current",
    "git rev-parse HEAD",
    "ls -la reports/",
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=200,
                    help="Number of ALLOW envelopes to probe (default: 200)")
    ap.add_argument("--gov-db", default="tmp/allow_probe_gov.db",
                    help="Throwaway WAL DB for the probe session")
    ap.add_argument("--label", default="probe",
                    help="Label embedded in the report filename + header")
    args = ap.parse_args()

    gov_db = (ROOT / args.gov_db).resolve()
    gov_db.parent.mkdir(parents=True, exist_ok=True)
    for ext in ("", "-wal", "-shm"):
        p = Path(str(gov_db) + ext)
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass

    iso_ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = ROOT / "reports" / f"allow-phase-{args.label}-{iso_ts}.md"

    bus = MessageBus(str(gov_db))
    session_id = f"allow-probe-{iso_ts}"
    bus.open_session(session_id, project_slug="probe", pid=os.getpid())
    snap = load_project_context(str(ROOT))
    engine = GovernanceEngine(
        project_context=snap, bus=bus, session_id=session_id,
    )

    phase_ms: dict[str, list[float]] = {}
    overall_ms: list[float] = []
    started_at = _dt.datetime.now(_dt.timezone.utc).isoformat()
    t_start = time.perf_counter()
    try:
        for i in range(args.n):
            content = _DEFAULT_PAYLOADS[i % len(_DEFAULT_PAYLOADS)]
            msg = Message.new(role="user", content=content)
            t0 = time.perf_counter()
            engine.evaluate(msg)
            overall_ms.append((time.perf_counter() - t0) * 1000.0)
            timings = getattr(engine, "_last_phase_timings_ms", None)
            if isinstance(timings, dict):
                for k, v in timings.items():
                    phase_ms.setdefault(k, []).append(float(v))
    finally:
        try:
            bus.close_session(session_id)
        except Exception:
            pass
        try:
            bus.close()
        except Exception:
            pass
    runtime_s = time.perf_counter() - t_start
    ended_at = _dt.datetime.now(_dt.timezone.utc).isoformat()

    lines: list[str] = []
    lines.append(f"# ALLOW publish-path phase probe — {started_at}")
    lines.append("")
    lines.append(f"- label: `{args.label}`")
    lines.append(f"- envelopes: {args.n}")
    lines.append(f"- runtime: {runtime_s:.3f} s")
    lines.append(f"- gov DB:  `{gov_db}`")
    lines.append(f"- started: {started_at}")
    lines.append(f"- ended:   {ended_at}")
    lines.append("")
    lines.append("## Overall wall-clock per evaluate()")
    lines.append("")
    if overall_ms:
        lines.append(f"- count: {len(overall_ms)}")
        lines.append(f"- min:   {min(overall_ms):.3f} ms")
        lines.append(f"- p50:   {_percentile(overall_ms, 50):.3f} ms")
        lines.append(f"- p95:   {_percentile(overall_ms, 95):.3f} ms")
        lines.append(f"- max:   {max(overall_ms):.3f} ms")
        lines.append(f"- mean:  {statistics.fmean(overall_ms):.3f} ms")
    lines.append("")

    lines.extend(_format_allow_phase_breakout(phase_ms))

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")

    # Stdout summary so CI / operators can eyeball the result.
    p50 = _percentile(overall_ms, 50) if overall_ms else 0.0
    p95 = _percentile(overall_ms, 95) if overall_ms else 0.0
    print(f"[allow-phase] n={args.n} p50={p50:.2f}ms p95={p95:.2f}ms "
          f"runtime={runtime_s:.2f}s -> {report_path}")
    print("[allow-phase] dominant phases at p95 (top 3):")
    rank: list[tuple[str, float]] = []
    for k in _ALLOW_PHASE_ORDER:
        v = phase_ms.get(k, [])
        if not v or k == "total":
            continue
        rank.append((k, _percentile(v, 95)))
    rank.sort(key=lambda kv: -kv[1])
    for name, val in rank[:3]:
        print(f"  - {name:<24} p95={val:.3f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
