#!/usr/bin/env python
"""Task I — per-call latency probe.

Measures, per ``engine.evaluate()`` call:

- ``wall_total_s``        : wall-clock around the whole evaluate() call
- ``registry_s``          : time inside ``EngineRegistry.get_or_create`` (0
                            after the first call for a given session_id —
                            cached engine path)
- ``hydrator_inline_s``   : time spent inside ``Hydrator.run`` if the thread
                            happened to complete *during* this call's window
                            (otherwise 0 — the hydrator is daemon-async)
- ``cli_subprocess_s``    : sum of ``latency_ms`` from ``cli_governance``
                            events the engine published during this call
                            (0 when no escalation fired)
- ``decision_action``     : engine's final decision action (ALLOW / BLOCK / …)

Also tracks once-per-run startup costs:

- ``engine_construct_s``  : first ``get_or_create`` call latency (engine
                            object construction + initial Hydrator.start)
- ``hydrator_total_s``    : end-to-end Hydrator thread runtime (start→finish)

Run modes
---------

The probe runs through the same payload mix the soak driver uses, but
condensed to fit a 5-minute window (one publish every 5s for ~50 messages,
deterministic shuffle of the soak 50/5/5 mix).

Usage::

    # cold cache
    rm -rf tmp/perf_gov.db tmp/perf_gov.db-wal tmp/perf_gov.db-shm
    BRIDGE_API_GOV=1 python tools/perf_probe.py --label cold --duration 300

    # warm cache (re-uses tmp/perf_gov.db from the cold run)
    BRIDGE_API_GOV=1 python tools/perf_probe.py --label warm --duration 300

Writes ``reports/perf-hydrator-{ISO-ts}.md`` with cold + warm tables.
The report path can be reused across modes via ``--report``.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import shutil
import statistics
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from stream_manager import cross_session_hydrator as _hydrator_mod  # noqa: E402
from stream_manager.governance import EngineRegistry  # noqa: E402
from stream_manager.message_bus import MessageBus  # noqa: E402
from stream_manager.messages import Message  # noqa: E402
from stream_manager.project_context import load as load_project_context  # noqa: E402

# Reuse the soak driver's payload mix — same shape, smaller window.
sys.path.insert(0, str(ROOT / "tools"))
from soak_driver import _build_payload_sequence  # noqa: E402  type: ignore[import-not-found]

# ---------------------------------------------------------------------------
# Hydrator instrumentation: capture (start_ts, end_ts) of the daemon thread
# so we can both report total runtime and intersect it against per-call
# windows to detect inline cost.
# ---------------------------------------------------------------------------

@dataclass
class _HydratorTrace:
    constructed_at: float | None = None
    start_called_at: float | None = None
    run_started_at: float | None = None
    run_finished_at: float | None = None


_HYDRATOR_TRACES: list[_HydratorTrace] = []
_HYDRATOR_LOCK = threading.Lock()


def _install_hydrator_instrumentation() -> None:
    """Wrap Hydrator.__init__/start/run to record timestamps.

    Called once per probe process before any engine construction.
    """
    Original = _hydrator_mod.Hydrator
    orig_init = Original.__init__
    orig_start = Original.start
    orig_run = Original.run

    def init(self: Any, engine: Any, bus: Any) -> None:  # type: ignore[no-redef]
        orig_init(self, engine, bus)
        trace = _HydratorTrace(constructed_at=time.perf_counter())
        with _HYDRATOR_LOCK:
            _HYDRATOR_TRACES.append(trace)
        self._probe_trace = trace

    def start(self: Any) -> None:  # type: ignore[no-redef]
        trace: _HydratorTrace | None = getattr(self, "_probe_trace", None)
        if trace is not None:
            trace.start_called_at = time.perf_counter()
        return orig_start(self)

    def run(self: Any) -> None:  # type: ignore[no-redef]
        trace: _HydratorTrace | None = getattr(self, "_probe_trace", None)
        if trace is not None:
            trace.run_started_at = time.perf_counter()
        try:
            orig_run(self)
        finally:
            if trace is not None:
                trace.run_finished_at = time.perf_counter()

    Original.__init__ = init  # type: ignore[assignment]
    Original.start = start  # type: ignore[assignment]
    Original.run = run  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# CLI subprocess instrumentation: subscribe to bus and read cli_governance
# events to attribute per-call subprocess latency. We snapshot the bus tail
# before/after each evaluate() call.
# ---------------------------------------------------------------------------

def _read_cli_latency_ms_since(gov_db: Path, since_ts: float) -> int:
    """Sum cli_governance latency_ms where messages.timestamp >= since_ts.

    Reads via a fresh read-only sqlite connection to avoid cross-thread
    issues with the live MessageBus connection. Returns 0 on any error.
    """
    try:
        import sqlite3
        conn = sqlite3.connect(f"file:{gov_db}?mode=ro", uri=True, timeout=2.0)
        try:
            cur = conn.execute(
                "SELECT metadata FROM messages WHERE type=? AND timestamp >= ?",
                ("governance_call", since_ts),
            )
            total_ms = 0
            for (meta_raw,) in cur.fetchall():
                try:
                    meta = json.loads(meta_raw) if isinstance(meta_raw, str) else {}
                except Exception:
                    meta = {}
                # cli_governance lifecycle status is one of: running, exited,
                # failed. Only the terminal events carry latency_ms.
                if meta.get("status") not in ("exited", "failed"):
                    continue
                lat = meta.get("latency_ms")
                if isinstance(lat, (int, float)):
                    total_ms += int(lat)
            return total_ms
        finally:
            conn.close()
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Per-call result row + aggregation
# ---------------------------------------------------------------------------

@dataclass
class _CallRow:
    idx: int
    kind: str
    wall_total_s: float
    registry_s: float
    hydrator_inline_s: float
    cli_subprocess_s: float
    decision_action: str


@dataclass
class _ProbeResult:
    label: str
    iso_ts: str
    duration_s: float
    cold: bool
    engine_construct_s: float
    hydrator_total_s: float | None
    rows: list[_CallRow] = field(default_factory=list)

    def lat_stats(self, attr: str) -> dict[str, float]:
        vals = [getattr(r, attr) for r in self.rows]
        if not vals:
            return {"n": 0, "min": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0, "mean": 0.0}
        s = sorted(vals)
        def p(pct: int) -> float:
            k = (len(s) - 1) * pct / 100
            lo, hi = int(k), min(int(k) + 1, len(s) - 1)
            return s[lo] + (s[hi] - s[lo]) * (k - lo)
        return {
            "n": len(vals),
            "min": min(vals),
            "p50": p(50),
            "p95": p(95),
            "max": max(vals),
            "mean": statistics.fmean(vals),
        }


# ---------------------------------------------------------------------------
# Probe driver
# ---------------------------------------------------------------------------

def run_probe(
    *,
    label: str,
    duration_s: float,
    interval_s: float,
    gov_db: Path,
    seed: int,
    skip_cli_check: bool,
) -> _ProbeResult:
    cli_present = shutil.which("claude") is not None or shutil.which("claude.exe") is not None
    if not cli_present and not skip_cli_check:
        print(
            "[perf] WARN: claude CLI not on PATH; CLI subprocess timings will be 0",
            file=sys.stderr,
        )

    cold = not gov_db.exists()
    iso_ts = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")

    _install_hydrator_instrumentation()

    gov_db.parent.mkdir(parents=True, exist_ok=True)
    bus = MessageBus(str(gov_db))
    snap = load_project_context(str(ROOT))
    session_id = f"perf-{label}-{iso_ts}"
    bus.open_session(session_id, project_slug="perf", pid=os.getpid())

    registry = EngineRegistry(bus=bus, project_context=snap)

    # First-touch engine construction -- this is the path that today
    # synchronously calls Hydrator.start() inside get_or_create.
    t_construct = time.perf_counter()
    registry.get_or_create(session_id)
    engine_construct_s = time.perf_counter() - t_construct

    payloads = _build_payload_sequence(seed)
    n_calls = max(1, int(duration_s / interval_s))
    payloads = payloads[:n_calls]

    rows: list[_CallRow] = []
    start_mono = time.perf_counter()
    deadline = start_mono + duration_s

    for idx, (kind, content) in enumerate(payloads):
        if time.perf_counter() >= deadline:
            break

        # snapshot wall time so we can attribute cli_governance events to this call
        call_started_wall = time.time()
        # snapshot active hydrator traces before the call so we can detect
        # ones whose .run_finished_at lands inside this call's window.
        with _HYDRATOR_LOCK:
            pre_traces = list(_HYDRATOR_TRACES)

        msg = Message.new(role="user", content=content)
        t_call_0 = time.perf_counter()

        # Re-issuing get_or_create on each call is the dashboard hot-path
        # shape: callers do not cache the engine across requests.
        t_reg_0 = time.perf_counter()
        eng = registry.get_or_create(session_id)
        registry_s = time.perf_counter() - t_reg_0

        try:
            decision = eng.evaluate(msg)
            action = decision.action
        except Exception as exc:  # pragma: no cover - probe must not crash
            action = f"ERROR:{exc!r}"

        wall_total_s = time.perf_counter() - t_call_0

        # Did any hydrator finish *inside* the call window?
        hydrator_inline_s = 0.0
        for t in pre_traces:
            if t.run_finished_at is None or t.run_started_at is None:
                continue
            # Intersect [run_started_at, run_finished_at] with [t_call_0, t_call_0+wall_total_s]
            window_end = t_call_0 + wall_total_s
            inter_start = max(t.run_started_at, t_call_0)
            inter_end = min(t.run_finished_at, window_end)
            if inter_end > inter_start:
                hydrator_inline_s += inter_end - inter_start

        cli_ms = _read_cli_latency_ms_since(gov_db, call_started_wall)

        rows.append(
            _CallRow(
                idx=idx,
                kind=kind,
                wall_total_s=wall_total_s,
                registry_s=registry_s,
                hydrator_inline_s=hydrator_inline_s,
                cli_subprocess_s=cli_ms / 1000.0,
                decision_action=action,
            )
        )

        # pace
        next_t = start_mono + (idx + 1) * interval_s
        sleep_for = next_t - time.perf_counter()
        if sleep_for > 0:
            time.sleep(min(sleep_for, max(0.0, deadline - time.perf_counter())))

    # Compute total Hydrator thread runtime for the first hydrator (the one
    # spawned during initial get_or_create). If it never started or never
    # finished within the probe window, leave None.
    hydrator_total_s: float | None = None
    with _HYDRATOR_LOCK:
        if _HYDRATOR_TRACES:
            t = _HYDRATOR_TRACES[0]
            if t.run_started_at is not None and t.run_finished_at is not None:
                hydrator_total_s = t.run_finished_at - t.run_started_at

    import contextlib
    with contextlib.suppress(Exception):
        bus.close_session(session_id)
    with contextlib.suppress(Exception):
        bus.close()

    return _ProbeResult(
        label=label,
        iso_ts=iso_ts,
        duration_s=duration_s,
        cold=cold,
        engine_construct_s=engine_construct_s,
        hydrator_total_s=hydrator_total_s,
        rows=rows,
    )


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _fmt_stats(s: dict[str, float]) -> str:
    return (
        f"n={s['n']:>3} min={s['min']:.3f}s p50={s['p50']:.3f}s "
        f"p95={s['p95']:.3f}s max={s['max']:.3f}s mean={s['mean']:.3f}s"
    )


def _append_section(lines: list[str], result: _ProbeResult) -> None:
    lines.append(f"## {result.label} run -- {result.iso_ts}")
    lines.append("")
    lines.append(f"- cold cache: {result.cold}")
    lines.append(f"- duration:   {result.duration_s:.0f}s")
    lines.append(
        f"- engine_construct (first get_or_create): "
        f"{result.engine_construct_s*1000:.2f} ms"
    )
    if result.hydrator_total_s is not None:
        lines.append(
            f"- hydrator total runtime (thread):        "
            f"{result.hydrator_total_s*1000:.2f} ms"
        )
    else:
        lines.append("- hydrator total runtime (thread):        n/a (not started or unfinished)")
    lines.append("")

    lines.append("### Per-attribute distributions")
    lines.append("")
    for attr, label in [
        ("wall_total_s", "wall_total"),
        ("registry_s", "registry.get_or_create"),
        ("hydrator_inline_s", "hydrator_inline"),
        ("cli_subprocess_s", "cli_subprocess"),
    ]:
        lines.append(f"- {label:<24} {_fmt_stats(result.lat_stats(attr))}")
    lines.append("")

    lines.append("### Per-call breakdown")
    lines.append("")
    lines.append("| idx | kind | wall_s | registry_ms | hydrator_inline_ms | cli_s | action |")
    lines.append("|----:|------|------:|-----------:|-------------------:|-----:|--------|")
    for r in result.rows:
        lines.append(
            f"| {r.idx} | {r.kind} | {r.wall_total_s:.3f} | "
            f"{r.registry_s*1000:.2f} | {r.hydrator_inline_s*1000:.2f} | "
            f"{r.cli_subprocess_s:.3f} | {r.decision_action} |"
        )
    lines.append("")


def _write_combined_report(
    report_path: Path,
    cold: _ProbeResult | None,
    warm: _ProbeResult | None,
) -> None:
    iso = _dt.datetime.now(_dt.UTC).isoformat()
    lines: list[str] = []
    lines.append(f"# Hydrator hot-path perf probe -- {iso}")
    lines.append("")
    lines.append(
        "Task I Step 1 measurement. Records per-call timing for "
        "`engine.evaluate()` over a focused 5-min window with the same "
        "payload mix shape as the 30-min soak."
    )
    lines.append("")
    lines.append("Attributes recorded per call:")
    lines.append("")
    lines.append("- `wall_total`     : entire evaluate() call (perf_counter)")
    lines.append(
        "- `registry`       : time inside `EngineRegistry.get_or_create` "
        "(approx. 0 after first call)"
    )
    lines.append(
        "- `hydrator_inline`: time the cross-session `Hydrator.run` thread "
        "happened to be executing *inside* the call window (intersection)"
    )
    lines.append(
        "- `cli_subprocess` : sum of `cli_governance.latency_ms` events "
        "published during the call (zero on routine ALLOW / no escalation)"
    )
    lines.append("")
    if cold is not None:
        _append_section(lines, cold)
    if warm is not None:
        _append_section(lines, warm)

    lines.append("## Diagnosis")
    lines.append("")
    if cold is not None and warm is not None:
        cold_wall = cold.lat_stats("wall_total_s")
        warm_wall = warm.lat_stats("wall_total_s")
        cold_reg = cold.lat_stats("registry_s")
        warm_reg = warm.lat_stats("registry_s")
        cold_hyd = cold.lat_stats("hydrator_inline_s")
        warm_hyd = warm.lat_stats("hydrator_inline_s")
        cold_cli = cold.lat_stats("cli_subprocess_s")
        warm_cli = warm.lat_stats("cli_subprocess_s")
        lines.append(f"- cold p95 wall_total:  {cold_wall['p95']:.3f}s")
        lines.append(f"- warm p95 wall_total:  {warm_wall['p95']:.3f}s")
        lines.append(
            f"- cold p95 registry:    {cold_reg['p95']*1000:.3f} ms "
            f"(warm {warm_reg['p95']*1000:.3f} ms)"
        )
        lines.append(
            f"- cold p95 hydrator_inline: {cold_hyd['p95']*1000:.3f} ms "
            f"(warm {warm_hyd['p95']*1000:.3f} ms)"
        )
        lines.append(
            f"- cold p95 cli_subprocess:  {cold_cli['p95']:.3f}s "
            f"(warm {warm_cli['p95']:.3f}s)"
        )
        lines.append(
            f"- cold engine_construct:    {cold.engine_construct_s*1000:.3f} ms "
            f"(warm {warm.engine_construct_s*1000:.3f} ms)"
        )
        if cold.hydrator_total_s is not None:
            lines.append(
                f"- cold hydrator total: {cold.hydrator_total_s*1000:.3f} ms"
            )
        if warm.hydrator_total_s is not None:
            lines.append(
                f"- warm hydrator total: {warm.hydrator_total_s*1000:.3f} ms"
            )
    lines.append("")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--label", choices=("cold", "warm", "both"), default="both")
    ap.add_argument("--duration", type=float, default=300.0)
    ap.add_argument("--interval", type=float, default=6.0,
                    help="Seconds between publishes (default 6 -> ~50 calls in 5 min)")
    ap.add_argument("--gov-db", default="tmp/perf_gov.db")
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--report", default=None,
                    help="Output report path; default reports/perf-hydrator-{ISO}.md")
    ap.add_argument("--skip-cli-check", action="store_true")
    args = ap.parse_args()

    os.environ.setdefault("BRIDGE_API_GOV", "1")

    gov_db = (ROOT / args.gov_db).resolve()
    iso_ts = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    report_path = Path(args.report) if args.report else (
        ROOT / "reports" / f"perf-hydrator-{iso_ts}.md"
    )

    cold_result: _ProbeResult | None = None
    warm_result: _ProbeResult | None = None

    if args.label in ("cold", "both"):
        # Force cold cache: drop the gov DB if present.
        import contextlib as _ctx
        for ext in ("", "-wal", "-shm"):
            p = Path(str(gov_db) + ext)
            if p.exists():
                with _ctx.suppress(Exception):
                    p.unlink()
        print(f"[perf] cold run -> {gov_db}")
        cold_result = run_probe(
            label="cold",
            duration_s=args.duration,
            interval_s=args.interval,
            gov_db=gov_db,
            seed=args.seed,
            skip_cli_check=args.skip_cli_check,
        )

    if args.label in ("warm", "both"):
        # Warm: reuse the same DB, but spawn a fresh process-local registry.
        # When called as --label both we already have rows from cold.
        print(f"[perf] warm run -> {gov_db}")
        warm_result = run_probe(
            label="warm",
            duration_s=args.duration,
            interval_s=args.interval,
            gov_db=gov_db,
            seed=args.seed,
            skip_cli_check=args.skip_cli_check,
        )

    _write_combined_report(report_path, cold_result, warm_result)
    print(f"[perf] wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
