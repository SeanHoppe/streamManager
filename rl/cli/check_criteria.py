"""v10 P5 — Ship-criteria checker CLI: ``python -m rl.cli.check_criteria``."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from rl.stop_conditions import CriteriaReport, evaluate_criteria

ROOT = Path(__file__).resolve().parents[2]
EXIT_ALL_PASS = 0
EXIT_FAIL = 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rl.cli.check_criteria")
    p.add_argument("--shadow-db", type=Path, required=True)
    p.add_argument("--manifests", type=Path, required=True)
    p.add_argument("--reports-dir", type=Path, default=ROOT / "reports")
    p.add_argument(
        "--mode", choices=["v10.1", "v10.3"], default="v10.3",
        help="v10.1 = baseline-vs-baseline infra validation"
             " (shadow_reward_improvement DORMANT, verdict PASS-INFRA);"
             " v10.3 = real candidate promotion gate (ADR-18 Amendment D)")
    return p


def render_report(report: CriteriaReport, ts: str) -> str:
    runs = report.shadow_run_ids
    runs_line = (
        f"- Shadow soak_run_ids (window): {', '.join(f'`{r}`' for r in runs)}"
        if runs else "- Shadow soak_run_ids (window): _none_"
    )
    if report.mode == "v10.1":
        verdict = "PASS-INFRA" if report.overall_passed else "FAIL"
    else:
        verdict = "PASS" if report.overall_passed else "FAIL"
    lines = [
        f"# v10 ship-criteria report — {ts}",
        "",
        f"- Mode: **{report.mode}**",
        f"- Overall verdict: **{verdict}**",
        runs_line,
        "",
        "## Per-criterion outcomes",
        "",
    ]
    for c in report.criteria:
        flag = "DORMANT" if c.dormant else ("PASS" if c.passed else "FAIL")
        lines.append(f"- **{c.name}** — {flag}")
        lines.append(f"  - {c.detail}")
    lines.append("")
    lines.append("_Pre-registered thresholds — see `docs/v10-rl-design.md`._")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = evaluate_criteria(args.shadow_db, args.manifests, mode=args.mode)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    args.reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.reports_dir / f"v10-criteria-{ts}.md"
    report_path.write_text(render_report(report, ts), encoding="utf-8")
    print(f"[rl.check_criteria] wrote {report_path}")
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return EXIT_ALL_PASS if report.overall_passed else EXIT_FAIL


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
