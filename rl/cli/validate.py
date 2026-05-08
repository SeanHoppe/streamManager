"""v10 P3 - CLI entry: ``python -m rl.cli.validate ...``.

Drives the 5-stage gauntlet (stages 1-4 in P3) and writes a Markdown
report. Exit 0 on PASS, 1 on REJECT. Makes ZERO live ``claude -p``
calls - the CLI reads cassette / golden files in-process only.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from rl.validate import Candidate, render_markdown, validate


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rl.cli.validate")
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--delta", type=float, default=0.02)
    p.add_argument("--db", type=Path, default=Path("rl_episodes.db"),
                   help="rl_episodes.db (stage 2)")
    p.add_argument("--cassette", type=Path, default=None,
                   help="soak cassette JSONL (stage 3); auto-resolves latest")
    p.add_argument("--golden", type=Path, default=None,
                   help="alignment golden JSONL (stage 1)")
    p.add_argument("--probe", type=Path, default=None,
                   help="P1a probe markdown (stage 4)")
    p.add_argument("--review", type=Path, default=None,
                   help="caveman-review findings (stage 4)")
    p.add_argument("--report-path", type=Path, default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = validate(
        Candidate.from_json(args.candidate),
        Candidate.from_json(args.baseline),
        delta=args.delta, db_path=args.db, cassette_path=args.cassette,
        golden_path=args.golden, probe_path=args.probe, review_path=args.review,
    )
    if args.report_path is None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        args.report_path = Path("reports") / f"v10-validate-{stamp}.md"
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"[rl.validate] wrote {args.report_path}")
    if report.passed:
        return 0
    fail = report.first_failure
    print(f"[rl.validate] REJECT at {fail.name if fail else '(unknown)'}: "
          f"{fail.detail if fail else ''}", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
