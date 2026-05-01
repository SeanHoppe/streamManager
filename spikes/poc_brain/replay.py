"""Spike B replay harness. Drives a synthetic CLI session through governance + decision_graph."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any

from stream_manager.governance import GovernanceEngine, Mode
from stream_manager.messages import Message
from stream_manager.project_context import fast_precheck, load


def _record_timing_us(content: str, snap: object) -> float:
    t0 = time.perf_counter_ns()
    fast_precheck(content, snap)  # type: ignore[arg-type]
    t1 = time.perf_counter_ns()
    return (t1 - t0) / 1000.0


def replay(fixture_path: Path, repo_path: Path, ignore_intent: bool) -> dict[str, Any]:
    snap = load(repo_path, ignore_intent=ignore_intent)
    engine = GovernanceEngine(project_context=snap)

    decisions: list[dict[str, Any]] = []
    precheck_us: list[float] = []
    mode_trajectory: list[str] = [engine.mode.name]
    correct = 0
    total = 0

    with fixture_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            msg = Message.new(entry["role"], entry["content"])

            precheck_us.append(_record_timing_us(msg.content, snap))

            decision = engine.evaluate(msg)
            engine.observe_for_learning(msg, success=(entry["expected"] == "ALLOW"))

            expected = entry["expected"]
            if expected == "INTERVENE_IF_INTENT":
                expected_resolved = "INTERVENE" if snap.has_intent_file else "ALLOW"
            else:
                expected_resolved = expected

            if engine.mode == Mode.OBSERVE and expected_resolved != "ALLOW":
                expected_for_observe = "ALLOW"
            else:
                expected_for_observe = expected_resolved
            was_correct = decision.action == expected_for_observe

            engine.feedback(decision, was_correct)
            decisions.append(
                {
                    "id": entry["id"],
                    "role": entry["role"],
                    "expected": expected_resolved,
                    "got": decision.action,
                    "source": decision.source,
                    "confidence": decision.confidence,
                    "mode": engine.mode.name,
                    "graph_match": decision.matched_hash[:8] if decision.matched_hash else "",
                }
            )
            mode_trajectory.append(engine.mode.name)
            total += 1
            if was_correct:
                correct += 1

    return {
        "ignore_intent": ignore_intent,
        "has_intent_file": snap.has_intent_file,
        "total": total,
        "correct": correct,
        "accuracy": correct / total if total else 0.0,
        "graph_stats": engine.graph.stats(),
        "graph_summary": engine.graph.summarize(max_chars=400),
        "mode_final": engine.mode.name,
        "mode_changes": _count_mode_changes(mode_trajectory),
        "precheck_us_median": statistics.median(precheck_us) if precheck_us else 0.0,
        "precheck_us_p99": _pct(precheck_us, 0.99) if precheck_us else 0.0,
        "decisions": decisions,
    }


def _count_mode_changes(traj: list[str]) -> int:
    changes = 0
    for i in range(1, len(traj)):
        if traj[i] != traj[i - 1]:
            changes += 1
    return changes


def _pct(values: list[float], q: float) -> float:
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(q * len(s))))
    return s[idx]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--fixture", type=Path, default=Path(__file__).with_name("fixture.jsonl"))
    p.add_argument("--repo", type=Path, default=Path.cwd())
    p.add_argument("--ignore-intent", action="store_true")
    args = p.parse_args()

    result = replay(args.fixture, args.repo, args.ignore_intent)
    print(f"intent_loaded   = {result['has_intent_file'] and not args.ignore_intent}")
    print(f"messages        = {result['total']}")
    print(f"accuracy        = {result['accuracy']:.3f} ({result['correct']}/{result['total']})")
    print(f"final mode      = {result['mode_final']}")
    print(f"mode changes    = {result['mode_changes']}")
    print(f"precheck median = {result['precheck_us_median']:.2f} us")
    print(f"precheck p99    = {result['precheck_us_p99']:.2f} us")
    print(f"graph stats     = {result['graph_stats']}")
    print()
    print("graph summary:")
    print(result["graph_summary"])


if __name__ == "__main__":
    main()
