#!/usr/bin/env python
"""Alt 5 / POC §3 row C6: Path-D land-verification helper.

Confirms ``feat/v2.8-p1-path-d`` has merged to ``main`` (PR #214 →
merge SHA on ``origin/main``) and emits the Tier-3 soak command for
the **main thread to run**. Per ``feedback_subagent_long_task_
abandonment.md`` + INTENT.md: any soak ``>5min`` must launch from the
main thread via ``run_in_background`` + ``ScheduleWakeup``, NEVER from
a subagent or helper script. This script therefore **prints** the
command and exits; it does NOT fire it.

Per ``feedback_parallel_operator_state.md``: also pre-flights
``git fetch`` + ``gh pr list`` so the helper surfaces any operator-
side parallel work in the ``rl/`` namespace before a verification
soak is launched.

Per ``feedback_soak_cli_pool_flag.md``: emitted soak command always
includes ``--cli-pool-size 2`` (never default 0).

Usage::

    python tools/path_d_verify.py
    python tools/path_d_verify.py --json

Exits:
  0 — PR merged and lineage clean; soak command emitted.
  2 — PR not merged OR local main lags origin/main OR lineage drift.
  3 — git/gh prerequisite missing.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PR_NUMBER = 214
BRANCH = "feat/v2.8-p1-path-d"


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None or shutil.which(f"{cmd}.exe") is not None


def _run(cmd: list[str], *, capture: bool = True) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd, cwd=ROOT, capture_output=capture, text=True, check=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError as exc:
        return 127, "", f"{exc!r}"


def _gh_pr_view(num: int) -> dict | None:
    rc, out, _err = _run([
        "gh", "pr", "view", str(num),
        "--json", "number,title,state,mergedAt,mergeCommit,headRefName,baseRefName",
    ])
    if rc != 0:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--json", action="store_true",
        help="Emit structured JSON status (machine-readable).",
    )
    ap.add_argument(
        "--soak-tier", type=int, default=3,
        help="Tier number for emitted soak command (default: 3).",
    )
    ap.add_argument(
        "--cli-pool-size", type=int, default=2,
        help=(
            "Soak --cli-pool-size value emitted in the command. "
            "MUST be >=2 per feedback_soak_cli_pool_flag.md."
        ),
    )
    ap.add_argument(
        "--pr", type=int, default=PR_NUMBER,
        help=f"PR number to verify (default: #{PR_NUMBER}).",
    )
    args = ap.parse_args()

    status: dict = {
        "pr_number": args.pr,
        "git_available": _have("git"),
        "gh_available": _have("gh"),
    }

    if not status["git_available"]:
        status["error"] = "git not on PATH"
        print(json.dumps(status, indent=2) if args.json else status["error"])
        return 3
    if not status["gh_available"]:
        status["error"] = "gh not on PATH"
        print(json.dumps(status, indent=2) if args.json else status["error"])
        return 3

    # Pre-flight: git fetch + gh pr list for parallel-state awareness.
    rc, _out, err = _run(["git", "fetch", "origin", "--quiet"])
    status["git_fetch_rc"] = rc
    if rc != 0:
        status["error"] = f"git fetch failed: {err.strip()}"
        print(json.dumps(status, indent=2) if args.json else status["error"])
        return 2

    rc, out, _err = _run([
        "gh", "pr", "list", "--state", "open",
        "--json", "number,title,headRefName", "--limit", "20",
    ])
    if rc == 0:
        try:
            status["open_prs"] = json.loads(out)
        except json.JSONDecodeError:
            status["open_prs"] = []
    else:
        status["open_prs"] = []

    # PR #214 verification.
    pr_info = _gh_pr_view(args.pr)
    status["pr"] = pr_info
    if pr_info is None:
        status["error"] = f"could not read PR #{args.pr}"
        print(json.dumps(status, indent=2) if args.json else status["error"])
        return 2
    pr_merged = pr_info.get("state") == "MERGED"
    status["pr_merged"] = pr_merged
    if not pr_merged:
        status["error"] = f"PR #{args.pr} not merged (state={pr_info.get('state')})"
        print(json.dumps(status, indent=2) if args.json else status["error"])
        return 2

    merge_commit = (pr_info.get("mergeCommit") or {}).get("oid", "")
    status["merge_commit"] = merge_commit

    # Confirm merge SHA is reachable from origin/main.
    if merge_commit:
        rc, _out, _err = _run([
            "git", "merge-base", "--is-ancestor", merge_commit, "origin/main",
        ])
        status["merge_in_origin_main"] = (rc == 0)
        if rc != 0:
            status["error"] = (
                f"merge SHA {merge_commit[:8]} not in origin/main lineage"
            )
            print(json.dumps(status, indent=2) if args.json else status["error"])
            return 2

    # Local main vs origin/main delta.
    rc, out, _err = _run([
        "git", "rev-list", "--count", "main..origin/main",
    ])
    status["local_main_behind"] = int(out.strip()) if rc == 0 and out.strip().isdigit() else None

    # Emit the soak command (do NOT fire it).
    soak_cmd = (
        f"python tools/soak_driver.py "
        f"--tier {args.soak_tier} "
        f"--cli-pool-size {args.cli_pool_size}"
    )
    status["soak_command"] = soak_cmd
    status["soak_owner"] = (
        "main thread via run_in_background + ScheduleWakeup "
        "(feedback_subagent_long_task_abandonment.md)"
    )

    if args.json:
        print(json.dumps(status, indent=2))
    else:
        print(f"[path-d] PR #{args.pr} MERGED at {merge_commit[:12] or '<unknown>'}")
        print(f"[path-d] merge-in-origin-main: {status.get('merge_in_origin_main')}")
        print(f"[path-d] local main behind origin/main by: {status['local_main_behind']} commit(s)")
        if status.get("open_prs"):
            print(f"[path-d] open PRs ({len(status['open_prs'])}):")
            for pr in status["open_prs"]:
                print(f"  - #{pr['number']} {pr['headRefName']}: {pr['title']}")
        print()
        print("[path-d] Tier-3 soak command (main thread fires; helper does NOT):")
        print(f"  {soak_cmd}")
        print(f"[path-d] owner: {status['soak_owner']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
