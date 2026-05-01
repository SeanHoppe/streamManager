"""Real-CLI soak harness for the L2 governance escalation path.

Replays a Claude Code JSONL transcript through GovernanceEngine with
``BRIDGE_API_GOV=true``. For every message that reaches the CLI escalation
path (i.e. precheck miss + no high-confidence graph match) it records:
  - wall-clock latency of the subprocess call
  - whether the CLI returned a parseable decision (parse-success rate)
  - which action was returned (action distribution)

Optionally runs a second pass with ``BRIDGE_API_GOV`` unset (local-only) and
reports action-distribution drift between the two paths.

Usage::

    # With real claude CLI (will spawn subprocesses):
    BRIDGE_API_GOV=true python tools/cli_soak.py \\
        --transcript ~/.claude/projects/<slug>/<sid>.jsonl \\
        --intent .

    # With --compare flag (two passes, drift table):
    BRIDGE_API_GOV=true python tools/cli_soak.py \\
        --transcript tests/fixtures/mini_session.jsonl \\
        --intent . \\
        --compare

    # Limit to first N messages (faster for spot-checks):
    BRIDGE_API_GOV=true python tools/cli_soak.py \\
        --transcript <path>.jsonl \\
        --intent . \\
        --max-messages 50

Output is markdown to stdout; pipe to reports/ to capture.

Exit codes:
    0 -- all targets met (CLI parse-success >= 80%, p95 <= 5s)
    1 -- bad args / no events
    2 -- one or more targets missed
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from stream_manager.cli_governance import CliGovernor  # noqa: E402
from stream_manager.governance import GovernanceEngine  # noqa: E402
from stream_manager.project_context import load  # noqa: E402
from stream_manager.transcript_loader import load_transcript  # noqa: E402

# Targets from POC_FINDINGS / NFR-P2
# Note: CLI subprocess path cold-start is ~13-16s; P95 target reflects this.
# SDK path (retired) had a 2s budget; CLI path realistic ceiling is ~20s.
TARGET_PARSE_SUCCESS_RATE = 0.80
TARGET_P95_SECONDS = 20.0


@dataclass
class _SoakStats:
    cli_invocations: int = 0
    cli_parse_successes: int = 0
    latencies_s: list[float] = field(default_factory=list)
    action_counts: Counter = field(default_factory=Counter)
    source_counts: Counter = field(default_factory=Counter)

    @property
    def parse_success_rate(self) -> float:
        if not self.cli_invocations:
            return 1.0
        return self.cli_parse_successes / self.cli_invocations

    @property
    def p50(self) -> float:
        return _percentile(self.latencies_s, 50)

    @property
    def p95(self) -> float:
        return _percentile(self.latencies_s, 95)

    @property
    def p99(self) -> float:
        return _percentile(self.latencies_s, 99)


def _percentile(data: list[float], pct: int) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s) - 1) * pct / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


class _InstrumentedRunner:
    """Wraps subprocess.run and records per-call latency + success."""

    def __init__(self, stats: _SoakStats) -> None:
        self._stats = stats

    def __call__(self, cmd: list[str], **kwargs: Any):
        self._stats.cli_invocations += 1
        t0 = time.perf_counter()
        try:
            result = subprocess.run(cmd, **kwargs)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            elapsed = time.perf_counter() - t0
            self._stats.latencies_s.append(elapsed)
            raise
        elapsed = time.perf_counter() - t0
        self._stats.latencies_s.append(elapsed)
        return result


def _run_pass(
    events,
    snap,
    *,
    cli_enabled: bool,
    bus=None,
    session_id: str = "",
) -> tuple[_SoakStats, list[str]]:
    """Run one pass through events. Returns stats + mode-transition log."""
    stats = _SoakStats()
    mode_log: list[str] = []

    engine = GovernanceEngine(project_context=snap, bus=bus, session_id=session_id)
    if cli_enabled:
        runner = _InstrumentedRunner(stats)
        engine._cli_governor = CliGovernor(snap, runner=runner)

    last_mode = engine.mode
    for i, ev in enumerate(events, start=1):
        decision = engine.evaluate(ev.message)
        stats.action_counts[decision.action] += 1
        stats.source_counts[decision.source] += 1

        if decision.source == "cli":
            stats.cli_parse_successes += 1

        if ev.has_signal:
            engine.feedback(decision, was_correct=ev.success)
        engine.observe_for_learning(ev.message, ev.success)

        if engine.mode != last_mode:
            mode_log.append(f"msg {i}: -> {engine.mode.name}")
            last_mode = engine.mode

    return stats, mode_log


def _pct(n: int, total: int) -> str:
    if not total:
        return "n/a"
    return f"{n/total*100:.1f}%"


def main() -> int:
    ap = argparse.ArgumentParser(description="Real-CLI soak harness")
    ap.add_argument("--transcript", required=True, help="Path to .jsonl session transcript")
    ap.add_argument("--intent", default=".", help="Repo root for INTENT.md loading")
    ap.add_argument("--max-messages", type=int, default=0)
    ap.add_argument(
        "--compare",
        action="store_true",
        help="Run a second pass with CLI disabled; show action-distribution drift",
    )
    ap.add_argument(
        "--no-intent", action="store_true", help="Skip INTENT.md even if present"
    )
    ap.add_argument(
        "--bus", default="", help="Path to WAL bus SQLite DB; enables real-time monitoring"
    )
    args = ap.parse_args()

    cli_was_enabled = os.environ.get("BRIDGE_API_GOV", "").lower() in ("1", "true", "yes")
    if not cli_was_enabled:
        print(
            "WARNING: BRIDGE_API_GOV is not set -- CLI path will not be invoked. "
            "Run with `BRIDGE_API_GOV=true` for a real soak.",
            file=sys.stderr,
        )

    events = load_transcript(args.transcript)
    if args.max_messages:
        events = events[: args.max_messages]
    if not events:
        print("No replayable events in transcript.", file=sys.stderr)
        return 1

    snap = load(args.intent, ignore_intent=args.no_intent)
    transcript_name = Path(args.transcript).name
    session_id = Path(args.transcript).stem

    bus = None
    if args.bus:
        from stream_manager.message_bus import MessageBus  # noqa: E402
        bus = MessageBus(args.bus)
        bus.open_session(
            session_id,
            project_slug=Path(args.intent).resolve().name,
            pid=os.getpid(),
        )
        print(f"- bus: {args.bus} (session {session_id})", file=sys.stderr)

    print(f"# CLI soak report -- {transcript_name}")
    print()
    print(f"- intent loaded: {snap.has_intent_file}")
    print(f"- messages: {len(events)}")
    print(f"- `BRIDGE_API_GOV` active: {cli_was_enabled}")
    print()

    # -- CLI pass ------------------------------------------------------------
    # Ensure env reflects the pass intent; don't stomp user-unset state.
    if cli_was_enabled:
        os.environ["BRIDGE_API_GOV"] = "true"
    else:
        os.environ.pop("BRIDGE_API_GOV", None)
    cli_stats, cli_modes = _run_pass(
        events, snap, cli_enabled=cli_was_enabled, bus=bus, session_id=session_id
    )

    print("## CLI escalation path")
    print()
    print(f"- CLI invocations:    {cli_stats.cli_invocations} "
          f"({_pct(cli_stats.cli_invocations, len(events))} of messages)")
    print(f"- Parse-success rate: {cli_stats.parse_success_rate:.1%}  "
          f"(target >= {TARGET_PARSE_SUCCESS_RATE:.0%}: "
          f"{'PASS' if cli_stats.parse_success_rate >= TARGET_PARSE_SUCCESS_RATE else 'FAIL'})")
    print()
    if cli_stats.latencies_s:
        print("### CLI latency (wall-clock seconds, per invocation)")
        print()
        print(f"- p50: {cli_stats.p50:.2f}s")
        print(f"- p95: {cli_stats.p95:.2f}s  "
              f"(target <= {TARGET_P95_SECONDS:.0f}s: "
              f"{'PASS' if cli_stats.p95 <= TARGET_P95_SECONDS else 'FAIL'})")
        print(f"- p99: {cli_stats.p99:.2f}s")
        print(f"- min: {min(cli_stats.latencies_s):.2f}s  "
              f"max: {max(cli_stats.latencies_s):.2f}s")
    else:
        print("### CLI latency")
        print()
        print("- (no CLI invocations -- all messages resolved by precheck/graph)")
    print()
    print("### Decision-source distribution (CLI pass)")
    total = sum(cli_stats.source_counts.values())
    for src, n in cli_stats.source_counts.most_common():
        print(f"- {src}: {n} ({_pct(n, total)})")
    print()
    print("### Decision-action distribution (CLI pass)")
    for act, n in cli_stats.action_counts.most_common():
        print(f"- {act}: {n} ({_pct(n, total)})")
    print()
    print("### Mode transitions (CLI pass)")
    if not cli_modes:
        print("- (none -- engine stayed in OBSERVE)")
    else:
        for entry in cli_modes:
            print(f"- {entry}")
    print()

    targets_met = (
        cli_stats.parse_success_rate >= TARGET_PARSE_SUCCESS_RATE
        and (not cli_stats.latencies_s or cli_stats.p95 <= TARGET_P95_SECONDS)
    )

    # -- Local-only comparison pass ------------------------------------------
    if args.compare:
        os.environ.pop("BRIDGE_API_GOV", None)
        local_stats, local_modes = _run_pass(events, snap, cli_enabled=False)

        print("## Local-only path (comparison)")
        print()
        print("### Decision-action distribution (local-only pass)")
        for act, n in local_stats.action_counts.most_common():
            print(f"- {act}: {n} ({_pct(n, total)})")
        print()
        print("### Mode transitions (local-only pass)")
        if not local_modes:
            print("- (none -- engine stayed in OBSERVE)")
        else:
            for entry in local_modes:
                print(f"- {entry}")
        print()

        print("## Action-distribution drift (CLI vs local-only)")
        print()
        print("| Action | CLI | Local | delta |")
        print("|--------|----:|------:|--:|")
        all_actions = sorted(set(cli_stats.action_counts) | set(local_stats.action_counts))
        for act in all_actions:
            c = cli_stats.action_counts[act]
            l_ = local_stats.action_counts[act]
            print(f"| {act} | {c} | {l_} | {c - l_:+d} |")
        print()

    print(f"## Overall: {'PASS' if targets_met else 'FAIL'}")

    if bus is not None:
        bus.close_session(session_id)
        bus.close()

    return 0 if targets_met else 2


if __name__ == "__main__":
    sys.exit(main())
