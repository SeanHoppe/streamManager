"""Replay a Claude Code session transcript through the governance brain.

Validates the architectural targets from POC_FINDINGS hardening items #1+#2
on real session data:

  • Sub-linear pattern growth: ratio = patterns_at_end / messages_processed < 1.0
  • No premature mode promotion: mode never reaches BLOCK without >= 3
    actual interventions in the rolling window.

Usage:
  PYTHONPATH=src python tools/replay_transcript.py \
      --transcript ~/.claude/projects/<slug>/<sid>.jsonl \
      --intent .

Output is markdown to stdout; pipe to a file under reports/ to capture.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from stream_manager.governance import GovernanceEngine, Mode  # noqa: E402
from stream_manager.project_context import load  # noqa: E402
from stream_manager.transcript_loader import load_transcript  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--intent", default=".", help="repo root for ProjectContextSnapshot")
    ap.add_argument("--max-messages", type=int, default=0)
    ap.add_argument("--no-intent", action="store_true")
    args = ap.parse_args()

    events = load_transcript(args.transcript)
    if args.max_messages:
        events = events[: args.max_messages]
    if not events:
        print("# Replay\n\nNo replayable events.")
        return 1

    snap = load(args.intent, ignore_intent=args.no_intent)
    engine = GovernanceEngine(project_context=snap)

    growth: list[tuple[int, int]] = []
    mode_history: list[tuple[int, str, int]] = []
    action_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    promotion_violation = False

    last_mode = engine.mode
    for i, ev in enumerate(events, start=1):
        decision = engine.evaluate(ev.message)
        action_counts[decision.action] += 1
        source_counts[decision.source] += 1

        if ev.has_signal:
            engine.feedback(decision, was_correct=ev.success)
        engine.observe_for_learning(ev.message, ev.success)

        if engine.mode != last_mode:
            mode_history.append((i, engine.mode.name, sum(engine._intervention_window)))
            last_mode = engine.mode

        if engine.mode == Mode.BLOCK and sum(engine._intervention_window) < 3:
            promotion_violation = True

        if i % 25 == 0 or i == len(events):
            growth.append((i, len(engine.graph.patterns)))

    final_msgs = len(events)
    final_patterns = len(engine.graph.patterns)
    ratio = final_patterns / final_msgs if final_msgs else 0.0
    stats = engine.stats()

    print(f"# Replay report — {Path(args.transcript).name}")
    print()
    print(f"- intent loaded: {snap.has_intent_file}")
    print(f"- messages replayed: {final_msgs}")
    print(f"- final patterns: {final_patterns}")
    print(f"- pattern/msg ratio: {ratio:.3f}  (target < 1.0: "
          f"{'PASS' if ratio < 1.0 else 'FAIL'})")
    print(f"- premature BLOCK guard: "
          f"{'FAIL' if promotion_violation else 'PASS'}")
    print(f"- final mode: {engine.mode.name}")
    print(f"- final eligible accuracy: {stats['eligible_accuracy']:.2f}")
    print(f"- final interventions in window: {stats['interventions_in_window']}")
    print()
    print("## Pattern level distribution (final)")
    print(f"```\n{stats['graph']}\n```")
    print()
    print("## Decision-action distribution")
    for a, n in action_counts.most_common():
        print(f"- {a}: {n}")
    print()
    print("## Decision-source distribution")
    for s, n in source_counts.most_common():
        print(f"- {s}: {n}")
    print()
    print("## Mode transitions (msg#, new_mode, interventions_in_window)")
    if not mode_history:
        print("- (none — engine stayed in OBSERVE)")
    else:
        for m, name, iv in mode_history:
            print(f"- msg {m}: → {name} (interventions={iv})")
    print()
    print("## Pattern growth (every 25 messages)")
    for m, n in growth:
        print(f"- {m}: {n} patterns ({n/m:.2f} per msg)")

    return 0 if (ratio < 1.0 and not promotion_violation) else 2


if __name__ == "__main__":
    sys.exit(main())
