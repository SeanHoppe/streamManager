"""Spike B A/B test: replay the same fixture with INTENT.md loaded vs ignored."""

from __future__ import annotations

import argparse
from pathlib import Path

from spikes.poc_brain.replay import replay


def _diff_decisions(a: list[dict], b: list[dict]) -> list[dict]:
    diffs = []
    for da, db in zip(a, b):
        if da["got"] != db["got"]:
            diffs.append(
                {
                    "id": da["id"],
                    "with_intent": da["got"],
                    "without_intent": db["got"],
                    "source_with": da["source"],
                    "source_without": db["source"],
                }
            )
    return diffs


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--fixture", type=Path, default=Path(__file__).with_name("fixture.jsonl"))
    p.add_argument("--repo", type=Path, default=Path.cwd())
    args = p.parse_args()

    with_intent = replay(args.fixture, args.repo, ignore_intent=False)
    without_intent = replay(args.fixture, args.repo, ignore_intent=True)

    diffs = _diff_decisions(with_intent["decisions"], without_intent["decisions"])

    print("=== A/B intent test ===")
    print(f"with INTENT.md:    accuracy={with_intent['accuracy']:.3f} mode={with_intent['mode_final']}")
    print(f"without INTENT.md: accuracy={without_intent['accuracy']:.3f} mode={without_intent['mode_final']}")
    print(f"diverging decisions: {len(diffs)}")
    print()
    if diffs:
        print("Differences (id, with_intent, without_intent, source_with, source_without):")
        for d in diffs:
            print(
                f"  msg #{d['id']:3d}: {d['with_intent']:9s} vs {d['without_intent']:9s} "
                f"({d['source_with']} vs {d['source_without']})"
            )


if __name__ == "__main__":
    main()
