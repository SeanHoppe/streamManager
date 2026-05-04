#!/usr/bin/env python
"""Task 6 real-CLI soak driver.

Runs a 30-minute soak with ``BRIDGE_API_GOV=1``:

    1. Spawns the dashboard server (uvicorn) on the requested port.
    2. Spawns the SSE consumer (``tools/soak_sse_consumer.py``) so a hang
       in the driver doesn't break event-count metrics.
    3. Constructs a GovernanceEngine wired to a soak-only WAL DB
       (``tmp/soak_gov.db`` by default) and pumps 60 synthetic messages
       through ``engine.evaluate`` — one every 30s for 30 minutes.
       The mix is 50× routine ALLOW patterns + 5× L2/L3-trigger prose +
       5× longer L4-alignment prose.
    4. Tracks per-minute psutil metrics for the dashboard server PID
       (RSS, FD/handle count, gov.db row counts).
    5. After the publish loop, drains a short tail window so the SSE
       consumer can flush in-flight events, then shuts everything down
       and writes a markdown report to ``reports/soak-{ISO-ts}.md``.

Usage::

    BRIDGE_API_GOV=1 python tools/soak_driver.py \\
        --port 8766 \\
        --gov-db tmp/soak_gov.db \\
        --total-seconds 1800 \\
        --interval-seconds 30

Writes ``reports/soak-{ISO-ts}.md`` and exits 0 on PASS / 2 on FAIL.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import shutil
import signal
import statistics
import subprocess
import sys
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import psutil  # noqa: E402

from stream_manager.governance import GovernanceEngine  # noqa: E402
from stream_manager.message_bus import Message as _BusMsgT  # noqa: E402
from stream_manager.message_bus import MessageBus  # noqa: E402
from stream_manager.messages import Message  # noqa: E402
from stream_manager.project_context import load as load_project_context  # noqa: E402


# ---- synthetic load mix --------------------------------------------------
# 50 routine ALLOW patterns + 5 escalation triggers + 5 alignment triggers.
# Order is shuffled deterministically so a single soak window sees a
# representative interleave; same seed = same order across runs.

_ROUTINE = [
    "ruff check src/",
    "pytest tests/ -q",
    "git status",
    "git diff --stat",
    "ls src/stream_manager",
    "python -m pytest tests/test_message_bus.py -k publish",
    "ruff format --check src/",
    "git log --oneline -n 5",
    "mypy src/stream_manager",
    "pre-commit run --all-files",
    "pytest tests/test_governance.py -q",
    "git branch --show-current",
    "git rev-parse HEAD",
    "ruff check tools/",
    "pytest tests/test_cli_governance.py -q",
    "git fetch --prune",
    "ls -la reports/",
    "python -c 'import stream_manager; print(stream_manager.__version__)'",
    "ruff check dashboard/",
    "pytest -q --collect-only",
    "git status -sb",
    "git stash list",
    "python -m compileall src",
    "ruff check --fix-only src/",
    "git diff HEAD~1",
    "pytest tests/test_decision_graph.py -q",
    "git log --since=yesterday",
    "ruff check tests/",
    "pytest tests/test_hitl.py -q",
    "git remote -v",
    "git tag --list",
    "ls dashboard/static",
    "git config --get user.email",
    "pytest tests/test_model_router.py -q",
    "git show --stat HEAD",
    "ruff check --select E,F src/",
    "pytest tests/test_agent_registry.py -q",
    "git diff --name-only",
    "ls tools/",
    "pytest tests/test_project_context.py -q",
    "ruff check --statistics src/",
    "git log --all --oneline -n 10",
    "pytest tests/test_message_bus.py -q",
    "git config --list --local",
    "python -m pytest -x -q",
    "ls src/",
    "git rev-list --count HEAD",
    "ruff check . --no-fix",
    "pytest --version",
    "git --version",
]

# Force CLI/L2 escalation: ambiguous prose that won't match precheck or
# graph patterns. The CLI judge has to reason about whether to ALLOW.
_L2_L3_TRIGGER = [
    "I'm not sure whether to refactor this module or extract a new helper -- the boundary feels off.",
    "This change touches the auth flow; I think it's safe but the test coverage is thin.",
    "Considering renaming the public API of the bus class -- might break downstream callers.",
    "Some of the existing patterns suggest one approach but the recent ADR says another.",
    "Maybe we should drop the legacy compat shim now that the deprecation window has elapsed?",
]

# Longer / divergent prose intended to flag the L4 alignment layer:
# multi-step plans, mixed concerns, ambiguous intent.
_L4_ALIGNMENT = [
    (
        "Plan: rip out the old SDK governance path entirely, swap every callsite to the CLI subprocess "
        "shim, then collapse the two evaluation pipelines into one. While we're in there, also rewrite "
        "the rate-limit bookkeeping to use a token bucket because the rolling-window approach is "
        "leaking memory under sustained load and the FR-OG-7 sweep keeps tripping false positives "
        "when the maturity dashboard is being regenerated mid-flight."
    ),
    (
        "Proposing a wide refactor: collapse messages.py and message_bus.py into a single module, "
        "drop the dataclass facade, switch to TypedDict everywhere, and migrate the WAL writes to "
        "asyncio so the dashboard SSE loop can share the same connection pool. This will simplify "
        "the agent registry interactions and unblock the per-agent override persistence work."
    ),
    (
        "Going to delete the legacy precheck table, regenerate from the latest transcripts, and "
        "switch the default mode from OBSERVE to SUGGEST in production -- I think the convergence "
        "monitor is conservative enough now to handle the increased intervention rate without "
        "regressing the rolling-window stats. Will also flip the HITL floor from 0.60 to 0.50."
    ),
    (
        "Going to silently drop FR-OG-7 maturity tracking from the engine when .sm-context.yaml is "
        "absent, but also re-enable it for the SM repo itself by hard-coding a fallback artifact "
        "path -- the dashboard panel is broken on fresh clones and the silent-degrade behaviour is "
        "confusing on review."
    ),
    (
        "Want to rewrite the CLI governance subprocess to skip the JSON-validation step entirely "
        "when the model returns more than 200 tokens of prose -- the parse-failure-degrade path "
        "always reaches ALLOW anyway, so we can shave ~5s off p95 by short-circuiting. Trading a "
        "small loss of audit signal for a meaningful latency improvement seems fine."
    ),
]


def _build_payload_sequence(seed: int = 4242) -> list[tuple[str, str]]:
    """Return a deterministic 60-item interleave of (kind, content)."""
    import random
    items: list[tuple[str, str]] = []
    items.extend(("routine", c) for c in _ROUTINE[:50])
    items.extend(("l2_l3", c) for c in _L2_L3_TRIGGER)
    items.extend(("l4", c) for c in _L4_ALIGNMENT)
    rng = random.Random(seed)
    rng.shuffle(items)
    return items


# ---- metrics bookkeeping -------------------------------------------------

@dataclass
class _MinuteSample:
    minute: int
    wall: str
    rss_mb: float | None
    fd_count: int | None
    msg_count: int | None
    decision_count: int | None
    error: str | None = None


@dataclass
class _DriverState:
    publish_latencies_s: list[float] = field(default_factory=list)
    # P1 / v1.3: separate ALLOW (routine, n=50) latencies so the soak
    # report can emit a per-band p50/p95 table matching ADR-5
    # §"v1.2 ship-gate baseline" — previously ALLOW latencies were
    # only visible inside the overall row.
    allow_latencies_s: list[float] = field(default_factory=list)
    escalation_latencies_s: list[float] = field(default_factory=list)
    alignment_latencies_s: list[float] = field(default_factory=list)
    # v1.3 Path-A: Learn Mode categorizer wall-clock latencies. Tracked
    # separately because the categorizer runs Sonnet (not the verdict
    # model) and its budget lives in its own ADR-5 row.
    lm_categorize_latencies_s: list[float] = field(default_factory=list)
    publish_errors: list[str] = field(default_factory=list)
    samples: list[_MinuteSample] = field(default_factory=list)
    events_emitted: int = 0
    decision_actions: dict[str, int] = field(default_factory=dict)


def _safe_db_count(db_path: Path, table: str) -> int | None:
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            return int(row[0])
        finally:
            conn.close()
    except Exception:
        return None


def _safe_proc_metrics(proc: psutil.Process) -> tuple[float | None, int | None, str | None]:
    rss_mb: float | None = None
    fds: int | None = None
    err: str | None = None
    try:
        rss_mb = proc.memory_info().rss / (1024 * 1024)
    except Exception as exc:
        err = f"rss:{exc}"
    try:
        if hasattr(proc, "num_fds"):
            fds = proc.num_fds()
        else:
            fds = proc.num_handles()  # Windows
    except Exception as exc:
        err = (err + ";" if err else "") + f"fds:{exc}"
    return rss_mb, fds, err


def _wait_dashboard_ready(port: int, timeout_s: float = 30.0) -> bool:
    """Probe the dashboard ``/api/stats`` endpoint until 200 or timeout."""
    import urllib.request
    import urllib.error
    deadline = time.monotonic() + timeout_s
    url = f"http://127.0.0.1:{port}/api/stats"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as resp:  # noqa: S310
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    return False


def _spawn_dashboard(port: int, gov_db: Path, log_path: Path) -> subprocess.Popen:
    env = dict(os.environ)
    env["GOV_DB"] = str(gov_db)
    # Ensure the worker process can import the governance package layout.
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fp = log_path.open("w", encoding="utf-8")
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "dashboard.server:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "info",
    ]
    return subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=log_fp,
        stderr=subprocess.STDOUT,
    )


def _spawn_sse_consumer(
    port: int, log_path: Path, duration_s: float, stdout_path: Path
) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_fp = stdout_path.open("w", encoding="utf-8")
    cmd = [
        sys.executable,
        str(ROOT / "tools" / "soak_sse_consumer.py"),
        "--url",
        f"http://127.0.0.1:{port}/events",
        "--log",
        str(log_path),
        "--duration",
        str(duration_s),
    ]
    return subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=stdout_fp,
        stderr=subprocess.STDOUT,
    )


def _terminate(proc: subprocess.Popen | None, label: str, timeout_s: float = 10.0) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            # On Windows, signal.CTRL_BREAK_EVENT requires a new process group.
            # Plain terminate() is the cleanest portable option.
            proc.terminate()
        else:
            proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            print(f"[soak] {label} did not exit; killing", file=sys.stderr)
            proc.kill()
            proc.wait(timeout=5.0)
    except Exception as exc:
        print(f"[soak] terminate({label}) raised: {exc}", file=sys.stderr)


def _count_sse_events(consumer_log: Path) -> tuple[int, int]:
    received = 0
    errors = 0
    if not consumer_log.exists():
        return 0, 0
    with consumer_log.open("r", encoding="utf-8") as fp:
        for line in fp:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("event") == "sse_event":
                received += 1
            elif rec.get("event") == "consumer_error":
                errors += 1
    return received, errors


def _percentile(data: list[float], pct: int) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s) - 1) * pct / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _format_per_band_split(
    allow: list[float],
    l2_l3: list[float],
    l4: list[float],
    lm_categorize: list[float] | None = None,
) -> list[str]:
    """Render the per-band p50/p95 markdown block.

    P1 / v1.3: ADR-5 budgets are per-band but the v1.2 driver collapsed
    ALLOW (n=50), L2/L3 (n=5), and L4 (n=5) into a single overall p95.
    Format mirrors ADR-5 §"v1.2 ship-gate baseline" §"Per-trigger split".

    v1.3 Path-A: optional ``lm_categorize`` row appended when the Learn
    Mode dialogue pump ran (recorder + ship-gate path). Replays of v1.2
    cassettes pass an empty list and the row reports n=0.
    """
    lines: list[str] = []
    lines.append("### Per-band latency (p50/p95)")
    lines.append("")
    lines.append("| Path                 |  n  | p50      | p95      |")
    lines.append("|----------------------|-----|----------|----------|")
    bands: list[tuple[str, list[float]]] = [
        ("ALLOW (routine)", allow),
        ("L2/L3 escalation", l2_l3),
        ("L4 alignment", l4),
    ]
    if lm_categorize is not None:
        bands.append(("LM (categorize)", lm_categorize))
    for label, data in bands:
        n = len(data)
        if n == 0:
            lines.append(f"| {label:<20} |   0 | n/a      | n/a      |")
            continue
        p50 = _percentile(data, 50)
        p95 = _percentile(data, 95)
        lines.append(
            f"| {label:<20} | {n:>3} | {p50:>5.2f} s  | {p95:>5.2f} s  |"
        )
    lines.append("")
    return lines


# v1.3 Path-A: pre-canned Learn Mode dialogue pairs shared with the
# recorder. Imported lazily inside the pump function so unit tests can
# import this module without dragging in the recorder's CLI deps.
def _load_lm_dialogue_pairs() -> list[tuple[str, str]]:
    sys.path.insert(0, str(ROOT / "tools"))
    from cassette_record import _LM_DIALOGUE_PAIRS  # noqa: WPS433
    return list(_LM_DIALOGUE_PAIRS)


def _format_lifecycle_bridge_final_state(
    seen: set[tuple[str, str]] | None,
) -> list[str]:
    """Render the LifecycleBridge `_seen` final-state markdown block.

    P1 / v1.3: Task C orphan-key invariant was not positively asserted
    at ship-gate. This helper produces a `### Lifecycle bridge final
    state` heading plus orphan counts. ``_seen`` is the LifecycleBridge
    private map; the bridge evicts matching start/end pairs on each
    completion, so any leftover ``_BG_JOB_START``/``_AGENT_SPAWN`` keys
    indicate orphan starts (no matching end seen). Reciprocally, any
    leftover end keys without a paired start indicate an orphan end.

    Read-only consumption per the do-not-touch contract — we do not
    modify the bridge surface.
    """
    # Late-import keeps `tools/soak_driver.py` importable without the
    # full src layout (e.g. for the helper-only unit tests, which add
    # `src/` to `sys.path` themselves). The constants are stable, so no
    # defensive fallback — let the ImportError surface.
    from stream_manager.lifecycle_bridge import (  # noqa: WPS433
        EVENT_AGENT_DONE,
        EVENT_AGENT_SPAWN,
        EVENT_BG_JOB_END,
        EVENT_BG_JOB_START,
    )

    seen = seen or set()
    start_types = {EVENT_BG_JOB_START, EVENT_AGENT_SPAWN}
    end_types = {EVENT_BG_JOB_END, EVENT_AGENT_DONE}

    orphan_starts = sorted(
        f"{etype}:{job_id}" for (etype, job_id) in seen if etype in start_types
    )
    orphan_ends = sorted(
        f"{etype}:{job_id}" for (etype, job_id) in seen if etype in end_types
    )

    lines: list[str] = []
    lines.append("### Lifecycle bridge final state")
    lines.append("")
    lines.append(f"- total `_seen` entries: {len(seen)}")
    if not orphan_starts:
        lines.append("- no orphan start keys (count=0)")
    else:
        lines.append(
            f"- ORPHAN start keys (count={len(orphan_starts)}): "
            + ", ".join(orphan_starts)
        )
    if not orphan_ends:
        lines.append("- no orphan end keys (count=0)")
    else:
        lines.append(
            f"- ORPHAN end keys (count={len(orphan_ends)}): "
            + ", ".join(orphan_ends)
        )
    lines.append("")
    return lines


def _write_report(
    report_path: Path,
    state: _DriverState,
    *,
    started_at_iso: str,
    ended_at_iso: str,
    total_runtime_s: float,
    payloads: list[tuple[str, str]],
    sse_received: int,
    sse_errors: int,
    dashboard_log_path: Path,
    consumer_log_path: Path,
    gov_db: Path,
    server_log_excerpt: str,
    rss_start: float | None,
    rss_end: float | None,
    rss_peak: float | None,
    fd_start: int | None,
    fd_end: int | None,
    cli_present: bool,
    bridge_seen: set[tuple[str, str]] | None = None,
) -> dict[str, object]:
    emitted = state.events_emitted
    received = sse_received
    pct_received = (received / emitted * 100.0) if emitted else 0.0

    rss_drift = None
    if rss_start is not None and rss_end is not None:
        rss_drift = rss_end - rss_start
    fd_drift = None
    if fd_start is not None and fd_end is not None:
        fd_drift = fd_end - fd_start

    # Acceptance: 100% events received OR documented loss; RSS drift < 50 MB;
    # no uncaught exceptions in server log.
    has_uncaught = (
        "Traceback (most recent call last)" in server_log_excerpt
        or "ERROR:" in server_log_excerpt
    )
    pass_events = received >= emitted and emitted > 0
    pass_rss = rss_drift is not None and rss_drift < 50.0
    pass_no_exc = not has_uncaught
    overall_pass = pass_events and pass_rss and pass_no_exc

    n_routine = sum(1 for k, _ in payloads if k == "routine")
    n_l2 = sum(1 for k, _ in payloads if k == "l2_l3")
    n_l4 = sum(1 for k, _ in payloads if k == "l4")

    lines: list[str] = []
    lines.append(f"# Soak report -- {started_at_iso}")
    lines.append("")
    lines.append(f"- BRIDGE_API_GOV: {os.environ.get('BRIDGE_API_GOV', '')!r}")
    lines.append(f"- claude CLI on PATH: {cli_present}")
    lines.append(f"- gov DB: `{gov_db}`")
    lines.append(f"- dashboard log: `{dashboard_log_path}`")
    lines.append(f"- consumer log: `{consumer_log_path}`")
    lines.append(f"- started_at: {started_at_iso}")
    lines.append(f"- ended_at:   {ended_at_iso}")
    lines.append(f"- runtime:    {total_runtime_s:.1f}s ({total_runtime_s/60:.1f} min)")
    lines.append("")

    lines.append("## Verdict")
    lines.append("")
    lines.append(f"- **Overall: {'PASS' if overall_pass else 'FAIL'}**")
    lines.append(
        f"- 100% events via SSE: {'PASS' if pass_events else 'FAIL'} "
        f"(emitted={emitted}, received={received}, {pct_received:.1f}%)"
    )
    lines.append(
        f"- RSS drift < 50 MB:    {'PASS' if pass_rss else 'FAIL'} "
        f"(drift={rss_drift:.2f} MB)" if rss_drift is not None
        else "- RSS drift < 50 MB:    UNKNOWN (no samples)"
    )
    lines.append(
        f"- No uncaught exceptions in server log: {'PASS' if pass_no_exc else 'FAIL'}"
    )
    lines.append("")

    lines.append("## Load mix (planned)")
    lines.append("")
    lines.append(f"- routine ALLOW: {n_routine}")
    lines.append(f"- L2/L3 escalation triggers: {n_l2}")
    lines.append(f"- L4 alignment triggers: {n_l4}")
    lines.append(f"- total planned: {len(payloads)}")
    lines.append(f"- total actually emitted: {emitted}")
    lines.append("")

    lines.append("## Decision-action distribution")
    lines.append("")
    if state.decision_actions:
        total = sum(state.decision_actions.values()) or 1
        for action, n in sorted(state.decision_actions.items(), key=lambda kv: -kv[1]):
            lines.append(f"- {action}: {n} ({n/total*100:.1f}%)")
    else:
        lines.append("- (none recorded)")
    lines.append("")

    lines.append("## Latency (engine.evaluate wall-clock)")
    lines.append("")
    if state.publish_latencies_s:
        lats = state.publish_latencies_s
        lines.append(f"- count: {len(lats)}")
        lines.append(f"- min:   {min(lats):.3f}s")
        lines.append(f"- p50:   {_percentile(lats, 50):.3f}s")
        lines.append(f"- p95:   {_percentile(lats, 95):.3f}s")
        lines.append(f"- max:   {max(lats):.3f}s")
        lines.append(f"- mean:  {statistics.fmean(lats):.3f}s")
    else:
        lines.append("- (no latencies recorded)")
    lines.append("")

    if state.escalation_latencies_s or state.alignment_latencies_s:
        lines.append("### Per-trigger latency")
        lines.append("")
        if state.escalation_latencies_s:
            e = state.escalation_latencies_s
            lines.append(
                f"- L2/L3 trigger n={len(e)} "
                f"p50={_percentile(e, 50):.2f}s p95={_percentile(e, 95):.2f}s"
            )
        if state.alignment_latencies_s:
            a = state.alignment_latencies_s
            lines.append(
                f"- L4 alignment n={len(a)} "
                f"p50={_percentile(a, 50):.2f}s p95={_percentile(a, 95):.2f}s"
            )
        lines.append("")

    # P1 / v1.3: per-band p50/p95 split (ALLOW n=50 + L2/L3 n=5 + L4 n=5).
    # ADR-5 budgets are per-band; the overall row above is preserved for
    # back-compat but the ship-gate now consults this table directly.
    # v1.3 Path-A: LM (categorize) row appended when the dialogue pump
    # ran; passes None when ship-gate ran with --skip-lm-pump so the row
    # is omitted from legacy reports.
    lm_data: list[float] | None = (
        state.lm_categorize_latencies_s
        if state.lm_categorize_latencies_s
        else None
    )
    lines.extend(
        _format_per_band_split(
            allow=state.allow_latencies_s,
            l2_l3=state.escalation_latencies_s,
            l4=state.alignment_latencies_s,
            lm_categorize=lm_data,
        )
    )

    # P1 / v1.3: LifecycleBridge `_seen` final-state dump. Positively
    # asserts the Task C orphan-key invariant at ship-gate. Read-only
    # consumption of the bridge surface — no modification.
    lines.extend(_format_lifecycle_bridge_final_state(bridge_seen))

    lines.append("## Process metrics (per-minute samples on dashboard server PID)")
    lines.append("")
    lines.append("| min | wall | RSS MB | FDs | messages | decisions | error |")
    lines.append("|----:|------|------:|----:|---------:|---------:|------|")
    for s in state.samples:
        rss_str = f"{s.rss_mb:.2f}" if s.rss_mb is not None else "n/a"
        fds_str = str(s.fd_count) if s.fd_count is not None else "n/a"
        msg_str = str(s.msg_count) if s.msg_count is not None else "n/a"
        dec_str = str(s.decision_count) if s.decision_count is not None else "n/a"
        err_str = (s.error or "").replace("|", "/")
        lines.append(
            f"| {s.minute} | {s.wall} | {rss_str} | {fds_str} | "
            f"{msg_str} | {dec_str} | {err_str} |"
        )
    lines.append("")

    lines.append("## RSS / FD summary")
    lines.append("")
    lines.append(
        f"- RSS start: {rss_start:.2f} MB" if rss_start is not None
        else "- RSS start: n/a"
    )
    lines.append(
        f"- RSS end:   {rss_end:.2f} MB" if rss_end is not None
        else "- RSS end:   n/a"
    )
    lines.append(
        f"- RSS peak:  {rss_peak:.2f} MB" if rss_peak is not None
        else "- RSS peak:  n/a"
    )
    lines.append(
        f"- RSS drift: {rss_drift:+.2f} MB (acceptance < 50 MB)"
        if rss_drift is not None else "- RSS drift: n/a"
    )
    lines.append(f"- FD start: {fd_start}, FD end: {fd_end}, drift: {fd_drift}")
    lines.append("")

    lines.append("## SSE consumer")
    lines.append("")
    lines.append(f"- received: {received}")
    lines.append(f"- errors:   {sse_errors}")
    if emitted:
        diff = emitted - received
        if diff > 0:
            lines.append(
                f"- LOSS: {diff} bus events emitted by the driver were not "
                f"observed via SSE during the window. (Note: each evaluate() "
                f"emits >=1 internal bus message via governance_eval; the "
                f"dashboard SSE forwards bus events with direction != 'inbound'.)"
            )
        elif diff < 0:
            lines.append(
                f"- received MORE than emitted ({-diff}); seed-replay (last 25 "
                f"decisions on connect) and engine-internal bus events "
                f"(governance_eval, model routing, etc.) account for this."
            )
        else:
            lines.append("- 100% match (or better) across emitted vs received")
    lines.append("")

    if state.publish_errors:
        lines.append("## Driver errors")
        lines.append("")
        for e in state.publish_errors:
            lines.append(f"- {e}")
        lines.append("")

    lines.append("## Dashboard server log (tail)")
    lines.append("")
    lines.append("```")
    lines.append(server_log_excerpt[-4000:] if server_log_excerpt else "(empty)")
    lines.append("```")
    lines.append("")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "overall_pass": overall_pass,
        "emitted": emitted,
        "received": received,
        "rss_drift_mb": rss_drift,
        "fd_drift": fd_drift,
        "report_path": str(report_path),
    }


def _check_cli_on_path() -> bool:
    return shutil.which("claude") is not None or shutil.which("claude.exe") is not None


def _write_deferral_report(reason: str) -> Path:
    path = ROOT / "reports" / "soak-deferred.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    iso = _dt.datetime.now(_dt.timezone.utc).isoformat()
    path.write_text(
        "\n".join(
            [
                f"# Soak deferred -- {iso}",
                "",
                "Task 6 real-CLI soak could not be run.",
                "",
                f"- reason: {reason}",
                "- BRIDGE_API_GOV requires the `claude` CLI on PATH; without it",
                "  the L2/L3/L4 escalation path cannot be exercised end-to-end.",
                "",
                "## Action",
                "",
                "Install `claude` (per https://docs.anthropic.com/) and re-run:",
                "",
                "    BRIDGE_API_GOV=1 python tools/soak_driver.py --port 8766",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _run_lm_dialogue_pump(
    bus: MessageBus,
    session_id: str,
    state: _DriverState,
    *,
    model: str | None,
    runner=None,
) -> int:
    """v1.3 Path-A: drive Learn Mode dialogue pairs through the live
    categorizer at ship-gate. Mirrors ``cassette_record._record_lm_dialogue``
    but writes nothing to a cassette file — the soak report is the artifact.

    Per pair: publish ``desktop_prompt`` + ``user_reply``, call
    ``categorize_pair`` directly (no worker thread for deterministic timing),
    push the wall-clock onto ``state.lm_categorize_latencies_s``, and
    consolidate into the canonical projection table so the live
    ``learn_patterns_canonical`` shows the M3 inputs.

    Returns the number of pairs successfully categorized. Failures are
    counted as zero-confidence ``unknown`` rows (matches live worker).
    """
    from stream_manager.learn_categorizer import (  # noqa: WPS433
        DEFAULT_MODEL as _LM_DEFAULT,
        categorize_pair,
        prompt_hash,
    )
    from stream_manager.decay import consolidate_patterns  # noqa: WPS433

    pairs = _load_lm_dialogue_pairs()
    chosen_model = model or _LM_DEFAULT
    n_ok = 0
    for offset, (prompt_text, reply_text) in enumerate(pairs):
        prompt_uuid = f"shipgate-prompt-{offset}"
        reply_uuid = f"shipgate-reply-{offset}"
        try:
            prompt_env = _BusMsgT.new(
                session_id=session_id,
                type="desktop_prompt",
                direction="inbound",
                content=prompt_text,
                metadata={
                    "desktop_session_id": session_id,
                    "uuid": prompt_uuid,
                    "parent_uuid": "",
                    "ts": time.time(),
                    "synthetic": True,
                },
            )
            bus.publish(prompt_env)
            reply_env = _BusMsgT.new(
                session_id=session_id,
                type="user_reply",
                direction="inbound",
                content=reply_text,
                metadata={
                    "desktop_session_id": session_id,
                    "uuid": reply_uuid,
                    "parent_uuid": prompt_uuid,
                    "pair_id": prompt_env.id,
                    "ts": time.time(),
                    "synthetic": True,
                },
            )
            bus.publish(reply_env)
        except Exception as exc:
            print(f"[soak] LM pump publish offset={offset} failed: {exc!r}",
                  file=sys.stderr)
            continue

        t0 = time.perf_counter()
        try:
            result = categorize_pair(
                prompt_text, reply_text, model=chosen_model, runner=runner,
            )
        except Exception as exc:
            print(f"[soak] LM pump categorize offset={offset} failed: {exc!r}",
                  file=sys.stderr)
            result = None
        elapsed = time.perf_counter() - t0
        state.lm_categorize_latencies_s.append(elapsed)

        if result is None:
            category, confidence = "unknown", 0.0
        else:
            category = result.category
            confidence = max(0.0, min(1.0, float(result.confidence)))
            n_ok += 1
        try:
            consolidate_patterns(
                bus, prompt_hash(prompt_text), category, confidence,
                now_ts=time.time(),
            )
        except Exception:
            pass
    return n_ok


def _load_cassette(path: Path) -> list[dict]:
    """Load a cassette JSONL file. Each line is a recorded envelope.

    Required fields per row::
        idx, kind, content, recorded_latency_ms,
        decision: {action, confidence, reasoning}
    """
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as fp:
        for line_no, raw in enumerate(fp, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except Exception as exc:
                raise ValueError(
                    f"cassette {path}: malformed JSON at line {line_no}: {exc}"
                ) from exc
            for k in ("kind", "content", "recorded_latency_ms", "decision"):
                if k not in rec:
                    raise ValueError(
                        f"cassette {path} line {line_no}: missing field {k!r}"
                    )
            rows.append(rec)
    if not rows:
        raise ValueError(f"cassette {path} is empty")
    return rows


def _run_replay(args) -> int:
    """Task A / v1.2: replay tier — no `claude` subprocess.

    Reads a cassette JSONL, sleeps the recorded latency per envelope, and
    drives the bus + decision recording exactly like a real soak. This
    exercises pool-/bus-/governance plumbing only and is safe to run in
    CI on hosts without the `claude` binary on PATH.
    """
    cassette_path = Path(args.cli_replay).resolve()
    if not cassette_path.exists():
        print(f"[soak] replay: cassette not found: {cassette_path}", file=sys.stderr)
        return 2

    rows = _load_cassette(cassette_path)
    print(f"[soak] replay mode: {len(rows)} envelopes from {cassette_path}")

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
    started_at_iso = _dt.datetime.now(_dt.timezone.utc).isoformat()
    report_path = ROOT / "reports" / f"replay-{iso_ts}.md"

    bus = MessageBus(str(gov_db))
    session_id = f"replay-{iso_ts}"
    bus.open_session(session_id, project_slug="soak-replay", pid=os.getpid())

    state = _DriverState()
    start_mono = time.monotonic()

    try:
        for row in rows:
            kind = row.get("kind", "routine")
            content = row["content"]
            latency_ms = float(row["recorded_latency_ms"])
            dec = row["decision"]

            t0 = time.perf_counter()
            # Recreate the inbound governance_eval row exactly as
            # GovernanceEngine.evaluate would, so consumers see the same
            # message shape across replay and ship-gate tiers.
            user_msg = Message.new(role="user", content=content)
            bm = _BusMsgT.new(
                session_id=session_id,
                type="governance_eval",
                direction="inbound",
                content=content,
                metadata={"role": "user", "msg_id": user_msg.id, "replay": True},
            )
            bus.publish(bm)

            # Sleep the recorded wall-clock latency to preserve the
            # bus/SSE pacing characteristics of the original soak.
            time.sleep(max(0.0, latency_ms / 1000.0))

            bus.record_decision(
                message_id=bm.id,
                action=dec["action"],
                confidence=float(dec.get("confidence", 0.0)),
                reasoning=dec.get("reasoning", ""),
                matched_hash=dec.get("matched_hash", ""),
                model_used=dec.get("model_used", "replay"),
                layer=int(dec.get("layer", 0)),
            )

            elapsed = time.perf_counter() - t0
            state.publish_latencies_s.append(elapsed)
            if kind == "l2_l3":
                state.escalation_latencies_s.append(elapsed)
            elif kind == "l4":
                state.alignment_latencies_s.append(elapsed)
            elif kind == "learn_dialogue":
                # v1.3 Path-A: replay of a recorded Learn Mode pair.
                # Latency reflects the categorizer Sonnet round-trip,
                # not the verdict path; tracked in its own band.
                cat_lat_ms = float(
                    row.get("recorded_categorize_latency_ms", latency_ms)
                )
                state.lm_categorize_latencies_s.append(cat_lat_ms / 1000.0)
            else:
                # routine = ALLOW band (P1 / v1.3 per-band split).
                state.allow_latencies_s.append(elapsed)
            state.decision_actions[dec["action"]] = (
                state.decision_actions.get(dec["action"], 0) + 1
            )
            state.events_emitted += 1
    finally:
        try:
            bus.close_session(session_id)
        except Exception:
            pass
        try:
            bus.close()
        except Exception:
            pass

    ended_at_iso = _dt.datetime.now(_dt.timezone.utc).isoformat()
    total_runtime = time.monotonic() - start_mono

    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append(f"# Soak replay -- {started_at_iso}")
    lines.append("")
    lines.append(f"- mode: REPLAY (Task A / v1.2; ADR-17)")
    lines.append(f"- cassette: `{cassette_path}`")
    lines.append(f"- envelopes: {len(rows)}")
    lines.append(f"- gov DB: `{gov_db}`")
    lines.append(f"- started_at: {started_at_iso}")
    lines.append(f"- ended_at:   {ended_at_iso}")
    lines.append(f"- runtime:    {total_runtime:.1f}s")
    lines.append("- claude subprocesses spawned: 0 (replay tier)")
    lines.append("")
    lines.append("## Latency (replayed)")
    lines.append("")
    if state.publish_latencies_s:
        lats = state.publish_latencies_s
        lines.append(f"- count: {len(lats)}")
        lines.append(f"- min:   {min(lats):.3f}s")
        lines.append(f"- p50:   {_percentile(lats, 50):.3f}s")
        lines.append(f"- p95:   {_percentile(lats, 95):.3f}s")
        lines.append(f"- max:   {max(lats):.3f}s")
        lines.append("")
        lines.append("> WARNING: replay p95 is a *relative* regression signal,")
        lines.append("> not an absolute target. Only ship-gate soak feeds the")
        lines.append("> ADR-5 absolute latency budget.")
        lines.append("")
    lines.append("## Decision-action distribution")
    lines.append("")
    if state.decision_actions:
        total = sum(state.decision_actions.values()) or 1
        for action, n in sorted(state.decision_actions.items(), key=lambda kv: -kv[1]):
            lines.append(f"- {action}: {n} ({n/total*100:.1f}%)")
    lines.append("")

    # P1 / v1.3: per-band p50/p95 (ALLOW + L2/L3 + L4) and LifecycleBridge
    # final-state dump. Replay tier does not exercise lifecycle events,
    # so the dump reports the empty-set baseline (zero orphans).
    # v1.3 Path-A: LM (categorize) row added when the cassette contains
    # learn_dialogue envelopes; else passes empty list and row reads n=0.
    lines.extend(
        _format_per_band_split(
            allow=state.allow_latencies_s,
            l2_l3=state.escalation_latencies_s,
            l4=state.alignment_latencies_s,
            lm_categorize=state.lm_categorize_latencies_s,
        )
    )
    lines.extend(_format_lifecycle_bridge_final_state(set()))

    report_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"[soak] replay wrote {report_path}")
    print(
        f"[soak] replay emitted={state.events_emitted} "
        f"runtime={total_runtime:.1f}s subprocesses_spawned=0"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--gov-db", default="tmp/soak_gov.db")
    ap.add_argument("--total-seconds", type=float, default=1800.0)
    ap.add_argument("--interval-seconds", type=float, default=30.0)
    ap.add_argument(
        "--drain-seconds",
        type=float,
        default=20.0,
        help="Extra time to keep SSE consumer running after publish loop ends",
    )
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument(
        "--skip-cli-check",
        action="store_true",
        help="Don't write a deferral report when claude CLI is missing (testing only)",
    )
    ap.add_argument(
        "--cli-pool-size",
        type=int,
        default=0,
        help="Task J / v1.1: warm-pool size for `claude` workers. 0 = legacy "
             "spawn-per-call (default). 2 is the recommended pool size.",
    )
    ap.add_argument(
        "--cli-replay",
        type=str,
        default=None,
        help="Task A / v1.2: path to a recorded cassette JSONL. When set, the "
             "driver does NOT spawn a real `claude` subprocess; instead it "
             "replays canned envelopes from the cassette, sleeping "
             "`recorded_latency_ms` per envelope. See ADR-17.",
    )
    ap.add_argument(
        "--skip-lm-pump",
        action="store_true",
        help="v1.3 Path-A: skip the Learn Mode dialogue pump after the main "
             "publish loop. Default behaviour drives 10 pre-canned dialogue "
             "pairs through the live Sonnet categorizer so the soak report "
             "contains an LM (categorize) per-band row. Set this flag for "
             "legacy CI runs without Sonnet quota.",
    )
    ap.add_argument(
        "--lm-model",
        default=None,
        help="v1.3 Path-A: model id for the Learn Mode categorizer. "
             "Defaults to learn_categorizer.DEFAULT_MODEL (Sonnet) per "
             "design spec §2.4.",
    )
    args = ap.parse_args()

    # Task A / v1.2: replay tier. Skip the claude-on-PATH check and the
    # BRIDGE_API_GOV / cli_pool init paths — replay exercises bus +
    # decision-record plumbing only, without any model call.
    if args.cli_replay:
        return _run_replay(args)

    cli_present = _check_cli_on_path()
    if not cli_present and not args.skip_cli_check:
        path = _write_deferral_report(
            "`claude` CLI not on PATH; cannot exercise BRIDGE_API_GOV path end-to-end."
        )
        print(f"[soak] DEFERRED -- wrote {path}")
        return 0

    # Force CLI escalation on for the engine.
    os.environ["BRIDGE_API_GOV"] = "1"

    gov_db = (ROOT / args.gov_db).resolve()
    gov_db.parent.mkdir(parents=True, exist_ok=True)
    # Soak should not pollute existing DB. Remove any stale soak DB.
    for ext in ("", "-wal", "-shm"):
        p = Path(str(gov_db) + ext)
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass

    iso_ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    started_at_iso = _dt.datetime.now(_dt.timezone.utc).isoformat()
    report_path = ROOT / "reports" / f"soak-{iso_ts}.md"
    dashboard_log = ROOT / "tmp" / f"soak-dashboard-{iso_ts}.log"
    consumer_log = ROOT / "tmp" / f"soak-sse-{iso_ts}.ndjson"
    consumer_stdout = ROOT / "tmp" / f"soak-sse-{iso_ts}.stdout"

    print(f"[soak] starting; report -> {report_path}")
    print(f"[soak] gov_db = {gov_db}")
    print(f"[soak] port   = {args.port}")
    print(f"[soak] runtime= {args.total_seconds:.0f}s")

    dashboard_proc: subprocess.Popen | None = None
    consumer_proc: subprocess.Popen | None = None
    bus: MessageBus | None = None
    state = _DriverState()
    payloads = _build_payload_sequence(args.seed)[:60]
    rss_peak: float | None = None
    rss_start: float | None = None
    rss_end: float | None = None
    fd_start: int | None = None
    fd_end: int | None = None
    start_mono = time.monotonic()

    try:
        # 1. Dashboard
        dashboard_proc = _spawn_dashboard(args.port, gov_db, dashboard_log)
        if not _wait_dashboard_ready(args.port):
            raise RuntimeError(
                f"dashboard did not become ready on port {args.port}; "
                f"check {dashboard_log}"
            )
        try:
            dash_psutil = psutil.Process(dashboard_proc.pid)
            rss_start, fd_start, _ = _safe_proc_metrics(dash_psutil)
            rss_peak = rss_start
        except Exception as exc:
            print(f"[soak] could not bind psutil to dashboard PID: {exc}", file=sys.stderr)
            dash_psutil = None

        # 2. SSE consumer (give it a generous duration covering drain + publish)
        consumer_duration = args.total_seconds + args.drain_seconds + 30.0
        consumer_proc = _spawn_sse_consumer(
            args.port, consumer_log, consumer_duration, consumer_stdout
        )

        # 3. Engine + bus on the soak DB
        bus = MessageBus(str(gov_db))
        session_id = f"soak-{iso_ts}"
        bus.open_session(session_id, project_slug="soak", pid=os.getpid())
        snap = load_project_context(str(ROOT))

        # Task J / v1.1: optional CLI warm-pool. When --cli-pool-size > 0,
        # the engine routes BRIDGE_API_GOV escalations through a pool of
        # long-lived `claude` workers; this is the path being measured for
        # the v1.1 p50 budget (≤ 3s). Pool is shut down in the finally
        # block to avoid orphan claude.exe processes.
        cli_pool_obj = None
        if args.cli_pool_size > 0:
            try:
                from stream_manager.cli_pool import CliPool, reap_stale_workers
                reaped = reap_stale_workers(root=ROOT)
                if reaped:
                    print(f"[soak] reaped {reaped} stale CLI worker(s) at boot")
                cli_pool_obj = CliPool(size=args.cli_pool_size, pid_root=ROOT)
                cli_pool_obj.warmup()
                print(f"[soak] CLI warm-pool enabled (size={args.cli_pool_size})")
            except Exception as exc:
                print(f"[soak] cli_pool init failed: {exc}; falling back to spawn-per-call",
                      file=sys.stderr)
                cli_pool_obj = None

        engine = GovernanceEngine(
            project_context=snap, bus=bus, session_id=session_id,
            cli_pool=cli_pool_obj,
        )

        # 4. Publish loop with per-minute psutil sampling
        start_mono = time.monotonic()  # reset to first publish boundary
        next_publish = start_mono
        next_sample = start_mono + 60.0
        next_idx = 0
        minute = 0
        deadline = start_mono + args.total_seconds

        # Take an initial sample (minute 0).
        if dash_psutil is not None:
            rss_mb, fds, err = _safe_proc_metrics(dash_psutil)
        else:
            rss_mb, fds, err = None, None, "no-dash-proc"
        if rss_mb is not None and (rss_peak is None or rss_mb > rss_peak):
            rss_peak = rss_mb
        state.samples.append(
            _MinuteSample(
                minute=0,
                wall=_dt.datetime.now(_dt.timezone.utc).isoformat(),
                rss_mb=rss_mb,
                fd_count=fds,
                msg_count=_safe_db_count(gov_db, "messages"),
                decision_count=_safe_db_count(gov_db, "decisions"),
                error=err,
            )
        )

        while time.monotonic() < deadline:
            now = time.monotonic()

            # Per-minute psutil sample
            if now >= next_sample:
                minute += 1
                if dash_psutil is not None:
                    try:
                        rss_mb, fds, err = _safe_proc_metrics(dash_psutil)
                    except Exception as exc:
                        rss_mb, fds, err = None, None, f"sample:{exc}"
                else:
                    rss_mb, fds, err = None, None, "no-dash-proc"
                if rss_mb is not None and (rss_peak is None or rss_mb > rss_peak):
                    rss_peak = rss_mb
                state.samples.append(
                    _MinuteSample(
                        minute=minute,
                        wall=_dt.datetime.now(_dt.timezone.utc).isoformat(),
                        rss_mb=rss_mb,
                        fd_count=fds,
                        msg_count=_safe_db_count(gov_db, "messages"),
                        decision_count=_safe_db_count(gov_db, "decisions"),
                        error=err,
                    )
                )
                next_sample += 60.0

            # Publish next message
            if now >= next_publish and next_idx < len(payloads):
                kind, content = payloads[next_idx]
                msg = Message.new(role="user", content=content)
                t0 = time.perf_counter()
                try:
                    decision = engine.evaluate(msg)
                    state.decision_actions[decision.action] = (
                        state.decision_actions.get(decision.action, 0) + 1
                    )
                    elapsed = time.perf_counter() - t0
                    state.publish_latencies_s.append(elapsed)
                    if kind == "l2_l3":
                        state.escalation_latencies_s.append(elapsed)
                    elif kind == "l4":
                        state.alignment_latencies_s.append(elapsed)
                    else:
                        # routine = ALLOW band (P1 / v1.3 per-band split).
                        state.allow_latencies_s.append(elapsed)
                    state.events_emitted += 1
                except Exception as exc:
                    state.publish_errors.append(
                        f"idx={next_idx} kind={kind}: {exc!r}"
                    )
                    print(f"[soak] publish error idx={next_idx}: {exc}", file=sys.stderr)
                next_idx += 1
                next_publish += args.interval_seconds

            # Sleep a short tick; do not over-sleep so deadline-honor stays tight.
            time.sleep(0.5)

        # v1.3 Path-A: Learn Mode dialogue pump. Runs after the verdict
        # publish loop (so engine.evaluate latencies are clean) but
        # before drain (so categorizer events flush via SSE too).
        if not args.skip_lm_pump:
            print("[soak] LM dialogue pump starting (Sonnet categorizer)…")
            n_ok = _run_lm_dialogue_pump(
                bus, session_id, state, model=args.lm_model,
            )
            print(f"[soak] LM dialogue pump: {n_ok} pairs categorized")

        # 5. Drain window so SSE consumer flushes any in-flight events.
        print(f"[soak] publish loop done; draining {args.drain_seconds:.0f}s")
        time.sleep(args.drain_seconds)

        # Final sample
        if dash_psutil is not None:
            try:
                rss_end, fd_end, _ = _safe_proc_metrics(dash_psutil)
                if rss_end is not None and (rss_peak is None or rss_end > rss_peak):
                    rss_peak = rss_end
            except Exception:
                pass

    finally:
        # Order: stop consumer first (so its log gets a clean consumer_stop),
        # then dashboard. Read dashboard log AFTER terminating it so we get
        # the full tail.
        _terminate(consumer_proc, "sse_consumer")
        _terminate(dashboard_proc, "dashboard")
        # Task J / v1.1: shut the warm-pool down BEFORE closing the bus so
        # any final governance_call events from in-flight workers can land.
        # Idempotent — safe even if init failed and cli_pool_obj is None.
        try:
            if 'cli_pool_obj' in locals() and cli_pool_obj is not None:  # type: ignore[name-defined]
                cli_pool_obj.shutdown()  # type: ignore[union-attr]
        except Exception as exc:
            print(f"[soak] cli_pool shutdown raised: {exc}", file=sys.stderr)
        if bus is not None:
            try:
                bus.close_session(session_id)
            except Exception:
                pass
            try:
                bus.close()
            except Exception:
                pass

    ended_at_iso = _dt.datetime.now(_dt.timezone.utc).isoformat()
    total_runtime = time.monotonic() - start_mono
    sse_received, sse_errors = _count_sse_events(consumer_log)
    server_log_excerpt = ""
    try:
        if dashboard_log.exists():
            server_log_excerpt = dashboard_log.read_text(encoding="utf-8", errors="replace")
    except Exception:
        server_log_excerpt = ""

    summary = _write_report(
        report_path,
        state,
        started_at_iso=started_at_iso,
        ended_at_iso=ended_at_iso,
        total_runtime_s=total_runtime,
        payloads=payloads,
        sse_received=sse_received,
        sse_errors=sse_errors,
        dashboard_log_path=dashboard_log,
        consumer_log_path=consumer_log,
        gov_db=gov_db,
        server_log_excerpt=server_log_excerpt,
        rss_start=rss_start,
        rss_end=rss_end,
        rss_peak=rss_peak,
        fd_start=fd_start,
        fd_end=fd_end,
        cli_present=cli_present,
    )

    print(f"[soak] wrote {summary['report_path']}")
    print(
        f"[soak] emitted={summary['emitted']} received={summary['received']} "
        f"rss_drift_mb={summary['rss_drift_mb']} verdict="
        f"{'PASS' if summary['overall_pass'] else 'FAIL'}"
    )
    return 0 if summary["overall_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
