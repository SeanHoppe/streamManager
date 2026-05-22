"""v10 P5 — Ship-criteria checker CLI: ``python -m rl.cli.check_criteria``."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from rl.stop_conditions import CriteriaReport, evaluate_criteria
from rl.validate import Candidate

ROOT = Path(__file__).resolve().parents[2]
EXIT_ALL_PASS = 0
EXIT_FAIL = 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rl.cli.check_criteria")
    p.add_argument("--shadow-db", type=Path, required=True)
    p.add_argument("--manifests", type=Path, required=True)
    p.add_argument("--baseline-thresholds", type=Path, default=None)
    p.add_argument("--reports-dir", type=Path, default=ROOT / "reports")
    return p


def render_report(report: CriteriaReport, ts: str) -> str:
    lines = [
        f"# v10 ship-criteria report — {ts}",
        "",
        f"- Overall verdict: **{'PASS' if report.overall_passed else 'FAIL'}**",
        "",
        "## Per-criterion outcomes",
        "",
    ]
    for c in report.criteria:
        flag = "PASS" if c.passed else "FAIL"
        lines.append(f"- **{c.name}** — {flag}")
        lines.append(f"  - {c.detail}")
    lines.append("")
    lines.append("_Pre-registered thresholds — see `docs/v10-rl-design.md`._")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.baseline_thresholds and args.baseline_thresholds.exists():
        baseline = Candidate.from_json(args.baseline_thresholds)
    else:
        baseline = Candidate(thresholds={})
    report = evaluate_criteria(args.shadow_db, args.manifests, baseline)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    args.reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.reports_dir / f"v10-criteria-{ts}.md"
    report_path.write_text(render_report(report, ts), encoding="utf-8")
    print(f"[rl.check_criteria] wrote {report_path}")
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return EXIT_ALL_PASS if report.overall_passed else EXIT_FAIL


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
