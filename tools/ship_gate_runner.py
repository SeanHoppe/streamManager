"""v2.x ship-gate test runner.

Orchestrates the verification steps from the active cycle's ship-gate
prompt (v2.6 P2 origin; v2.7+ forward — single shared runner with
per-cycle constants pinned below). For v2.7 the source prompt is
``docs/prompts/v2.7-orchestration/phase-3-ship-gate.md``:

- ``preflight``  — git HEAD lineage + branch + cycle-tip SHA sanity
- ``wipe``       — S1 + S1.1 (clean .bridge + untracked reports/, assert
                   tracked drift = empty)
- ``inspect-soak`` — S3 parse soak summary for invariant canary + Seed 4
                   dual-anchor LOC block + alignment with manual LOC
- ``align``      — S4 alignment-eval with prior-cycle-aware --runs branch
                   + escape-hatch evaluator
- ``loc``        — S5 manual cycle-tip + predecessor-tag LOC delta
- ``ledger``     — S6 lever-ledger posture verification
- ``s6.5``       — S6.5 print Seed v2.5-A diagnosis summary (pre-executed)
- ``all``        — runs everything except ``soak`` (long-running) and
                   ``align`` (must operate-bound on --runs choice)

The Tier-3 soak (S2) is NOT fired by this runner — per
``feedback_subagent_long_task_abandonment.md`` it must launch from the
main thread with ``run_in_background`` + ``ScheduleWakeup``. This runner
verifies the soak output after the fact.

Read-only by default. Pass ``--apply`` only on the ``wipe`` subcommand
(the only destructive step). All other subcommands are pure inspection.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

# Force UTF-8 on stdout/stderr at import time so Windows cp1252 consoles
# don't choke on ASCII-only output further down (defensive — we ASCII-ify
# all print() strings, but keep this in case future edits regress).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parent.parent

# Cycle-frame constants — pinned per-cycle. Hard-coded here so the
# runner is self-contained; if cycle-tip rebases, edit explicitly.
# v2.7 P3 constants (pinned at v2.7 P0 fire PR #200 per
# docs/v2.7-task-plan.md §"Operator decisions" #8):
CYCLE_TIP_SHA = "4902cca440b33c14fddd9357116923ae5fe1fa4b"
PREDECESSOR_TAG_SHA = "c3a964c"
CYCLE_TYPE = "feature"
LOC_PATHSPEC = ["src", "tests", "tools", "dashboard"]
EXPECTED_BRANCH = "ship/v2.7-p3-ship-gate"

# Feature-cycle gate (Amendment A + C; cycle-tip anchor binding).
LOC_SOFT_TARGET = 1500
LOC_BLOCK = 2250

# Alignment-eval prior-cycle inputs (v2.6 P2 n=6 baseline per
# project_v26_cycle_close.md).
PRIOR_CYCLE_SONNET_PASS_RATE = 0.9412
FR_OG_7_FLOOR = 0.80
FR_OG_7_FLOOR_DISTANCE_TRIGGER = 0.05  # n=6 mandate (hatch 1) when prior < 0.85
PRIOR_CYCLE_UNSTABLE_SONNET = 15        # hatch (3): mandates --runs 6 when
PRIOR_CYCLE_TOTAL_ROWS = 32             # unstable/total > trigger (15/32 = 47% > 25% at v2.6 P2)
UNSTABLE_SONNET_RATIO_TRIGGER = 0.25    # shared by _resolve_runs (hatch 3) + _eval_escape_hatch

# Lever ledger posture (entering P3 of v2.7).
LEDGER_PRODUCTION_EXPECTED = 3  # v2.3 Seed 6 + v2.6 P1 Seed v2.5-G step (1) + v2.7 P1 Seed v2.6-G step (2)
LEDGER_SOAK_EXPECTED = 0


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check, cwd=ROOT)


def _git(*args: str, check: bool = True) -> str:
    return _run(["git", *args], check=check).stdout.rstrip("\n")


def _print_header(title: str) -> None:
    bar = "=" * 72
    print(f"\n{bar}\n[ship-gate] {title}\n{bar}", flush=True)


# ============================================================
# preflight
# ============================================================

def cmd_preflight(_args: argparse.Namespace) -> int:
    _print_header("preflight -- branch + cycle-tip lineage")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    head_sha = _git("rev-parse", "HEAD")
    print(f"  branch       = {branch}")
    print(f"  HEAD         = {head_sha}")
    print(f"  cycle-tip    = {CYCLE_TIP_SHA}")
    print(f"  predecessor  = {PREDECESSOR_TAG_SHA}")
    print(f"  cycle-type   = {CYCLE_TYPE}")

    # Cycle-tip reachable from HEAD?
    rc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", CYCLE_TIP_SHA, "HEAD"],
        cwd=ROOT, check=False,
    ).returncode
    if rc != 0:
        print(f"  FAIL: cycle-tip {CYCLE_TIP_SHA} not ancestor of HEAD", file=sys.stderr)
        return 2
    print("  PASS: cycle-tip is ancestor of HEAD")

    # Branch sanity
    if branch != EXPECTED_BRANCH:
        print(f"  WARN: branch != {EXPECTED_BRANCH} (got {branch}). "
              "Continue only if intentional.")
    else:
        print(f"  PASS: branch == {EXPECTED_BRANCH}")
    return 0


# ============================================================
# wipe  (S1 + S1.1)
# ============================================================

def _wipe_apply() -> None:
    bridge = ROOT / ".bridge"
    soak_dir = bridge / "soak-driver"
    pids = bridge / "cli-pool.pids"
    if soak_dir.exists():
        for p in soak_dir.iterdir():
            try:
                p.unlink()
            except (OSError, IsADirectoryError):
                pass
        print(f"  wiped: {soak_dir}/*")
    if pids.exists():
        pids.unlink()
        print(f"  wiped: {pids}")
    # Untracked reports/ only — preserves tracked baselines.
    out = _run(["git", "clean", "-df", "reports/"]).stdout
    if out.strip():
        print("  git clean -df reports/:")
        for line in out.rstrip("\n").splitlines():
            print(f"    {line}")
    else:
        print("  git clean -df reports/: (nothing untracked)")


def _wipe_assert() -> int:
    # S1.1 — tracked drift in reports/ must be empty
    drift = _git("status", "--short", "--untracked-files=no", "reports/")
    if drift.strip():
        print("  FAIL: tracked reports/ in drift:")
        for line in drift.splitlines():
            print(f"    {line}")
        return 1
    print("  PASS: tracked reports/ clean")
    return 0


def cmd_wipe(args: argparse.Namespace) -> int:
    _print_header("S1 wipe + S1.1 assertion")
    if args.apply:
        _wipe_apply()
    else:
        print("  (dry-run; pass --apply to execute)")
    return _wipe_assert()


# ============================================================
# inspect-soak  (S3)
# ============================================================

# Canary line in the soak summary markdown:
#   `- Invariant-degrade canary: PASS (degrade_count=0)`
# (the `[soak]` prefix appears only in stdout, not the report).
CANARY_RE = re.compile(r"Invariant-degrade canary:\s*(PASS|FAIL)", re.IGNORECASE)

# Dual-anchor block lives in a markdown table:
#   | Cycle-tip (Amend C) | <sha> | BINDING   | +X / -Y / +Z |
#   | Predecessor-tag (A) | <sha> | NARRATIVE | +X / -Y / +Z |
# Then a verdict line: `**Gate verdict (Amendment C):** PASS`
CYCLE_ANCHOR_RE = re.compile(
    r"\|\s*Cycle-tip[^|]*\|\s*([0-9a-fA-F]+)\s*\|\s*BINDING\s*\|\s*"
    r"\+(\d+)\s*/\s*-(\d+)\s*/\s*\+(\d+)\s*\|",
)
PRED_ANCHOR_RE = re.compile(
    r"\|\s*Predecessor-tag[^|]*\|\s*([0-9a-fA-F]+)\s*\|\s*NARRATIVE\s*\|\s*"
    r"\+(\d+)\s*/\s*-(\d+)\s*/\s*\+(\d+)\s*\|",
)
GATE_VERDICT_RE = re.compile(
    r"\*\*Gate verdict[^:]*:\*\*\s*(PASS|BLOCK)", re.IGNORECASE
)


def _latest_soak_report() -> Path | None:
    """Pick newest by mtime; lex sort across `soak-*.md` is wrong because
    older `soak-wirecli-*` files lexically sort above plain `soak-2026*`."""
    reports = ROOT / "reports"
    if not reports.is_dir():
        return None
    cands = [p for p in reports.glob("soak-*.md") if p.is_file()]
    if not cands:
        return None
    cands.sort(key=lambda p: p.stat().st_mtime)
    return cands[-1]


def cmd_inspect_soak(args: argparse.Namespace) -> int:
    _print_header("S3 inspect soak summary -- canary + Seed 4 dual-anchor")
    path = Path(args.path) if args.path else _latest_soak_report()
    if path is None or not path.exists():
        print("  FAIL: no soak report found at reports/soak-*.md")
        return 1
    print(f"  source: {path}")
    text = path.read_text(encoding="utf-8")

    canary_m = CANARY_RE.search(text)
    canary_ok = bool(canary_m) and canary_m.group(1).upper() == "PASS"
    print(f"  invariant-degrade canary: "
          f"{canary_m.group(1) if canary_m else 'NOT FOUND'}")

    cycle = CYCLE_ANCHOR_RE.search(text)
    pred = PRED_ANCHOR_RE.search(text)
    verdict_m = GATE_VERDICT_RE.search(text)
    if not cycle:
        print("  FAIL: cycle-tip anchor row not found in soak table")
        return 1
    sha, adds, dels, net = cycle.groups()
    net_int = int(net)
    verdict = verdict_m.group(1) if verdict_m else "?"
    print(f"  cycle-tip ({sha}..HEAD): +{adds}/-{dels}/+{net} [{verdict}]")
    if pred:
        pred_sha, p_adds, p_dels, p_net = pred.groups()
        print(f"  predecessor-tag ({pred_sha}..HEAD): "
              f"+{p_adds}/-{p_dels}/+{p_net}")

    # Manual LOC cross-check
    manual_net = _loc_net(CYCLE_TIP_SHA, "HEAD")
    print(f"  manual cycle-tip net: +{manual_net}")
    if manual_net != net_int:
        print(f"  WARN: soak-summary net ({net_int}) != manual ({manual_net})")
    else:
        print("  PASS: dual-anchor net matches manual byte-for-byte")

    # Feature-cycle gate
    if net_int > LOC_BLOCK:
        print(f"  FAIL: cycle-tip net {net_int} > BLOCK {LOC_BLOCK}")
        return 2
    if net_int > LOC_SOFT_TARGET:
        print(f"  WARN: cycle-tip net {net_int} > soft {LOC_SOFT_TARGET}")
    else:
        print(f"  PASS: cycle-tip net {net_int} <= soft {LOC_SOFT_TARGET}")

    if not canary_ok:
        return 1
    return 0


# ============================================================
# loc  (S5)
# ============================================================

def _loc_net(base: str, head: str) -> int:
    proc = _run(["git", "diff", f"{base}..{head}", "--shortstat",
                 "--", *LOC_PATHSPEC], check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"git diff {base}..{head} failed (rc={proc.returncode}): "
            f"{proc.stderr.strip()}"
        )
    out = proc.stdout.rstrip("\n")
    if not out:
        return 0
    # "X files changed, Y insertions(+), Z deletions(-)"
    ins = re.search(r"(\d+)\s+insertion", out)
    dels = re.search(r"(\d+)\s+deletion", out)
    i = int(ins.group(1)) if ins else 0
    d = int(dels.group(1)) if dels else 0
    return i - d


def _loc_detail(base: str, head: str) -> str:
    return _git("diff", f"{base}..{head}", "--stat",
                "--", *LOC_PATHSPEC, check=False)


def cmd_loc(_args: argparse.Namespace) -> int:
    _print_header("S5 LOC delta -- Amendment C cycle-tip binding")
    print("  pathspec: " + " ".join(LOC_PATHSPEC))
    print(f"\n  -- cycle-tip ({CYCLE_TIP_SHA[:7]}..HEAD) [BINDING] --")
    print(_loc_detail(CYCLE_TIP_SHA, "HEAD") or "  (no changes)")
    cycle_net = _loc_net(CYCLE_TIP_SHA, "HEAD")
    print(f"  cycle-tip net = {cycle_net}")
    print(f"\n  -- predecessor-tag ({PREDECESSOR_TAG_SHA}..HEAD) [NARRATIVE] --")
    print(_loc_detail(PREDECESSOR_TAG_SHA, "HEAD") or "  (no changes)")
    pred_net = _loc_net(PREDECESSOR_TAG_SHA, "HEAD")
    print(f"  predecessor-tag net = {pred_net}")
    print()
    if cycle_net > LOC_BLOCK:
        print(f"  FAIL: cycle-tip net {cycle_net} > BLOCK {LOC_BLOCK}")
        return 2
    if cycle_net > LOC_SOFT_TARGET:
        print(f"  WARN: cycle-tip net {cycle_net} > soft {LOC_SOFT_TARGET}")
        return 0
    print(f"  PASS: cycle-tip net {cycle_net} <= soft {LOC_SOFT_TARGET} (feature)")
    return 0


# ============================================================
# ledger  (S6)
# ============================================================

def _read_soak_ledger_dict_size() -> int | None:
    """Parse tools/soak_driver.py for WIRED_LEVER_LEDGER literal size via ast."""
    src = (ROOT / "tools" / "soak_driver.py").read_text(encoding="utf-8")
    m = re.search(
        r"^WIRED_LEVER_LEDGER\s*:[^=]*=\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})",
        src,
        re.MULTILINE,
    )
    if not m:
        return None
    try:
        d = ast.literal_eval(m.group(1))
    except (ValueError, SyntaxError):
        return None
    return len(d) if isinstance(d, dict) else None


def cmd_ledger(_args: argparse.Namespace) -> int:
    _print_header("S6 lever-ledger posture")
    soak_size = _read_soak_ledger_dict_size()
    print(f"  soak-scope WIRED_LEVER_LEDGER literal size: {soak_size}")
    if soak_size != LEDGER_SOAK_EXPECTED:
        print(f"  FAIL: soak-scope ledger size {soak_size} != "
              f"expected {LEDGER_SOAK_EXPECTED}")
        return 2
    print(f"  PASS: soak-scope ledger size == {LEDGER_SOAK_EXPECTED}")
    print(f"  production-scope expected: {LEDGER_PRODUCTION_EXPECTED} "
          "(v2.3 Seed 6 JsonlTailWorker + v2.6 P1 Seed v2.5-G step (1)); "
          "NOT auto-verified -- cross-check cycle-close memories")
    print("  HOLD at P2 -- no further wire/rip this phase")
    return 0


# ============================================================
# align  (S4)
# ============================================================

def _resolve_runs(prior_rate: float, override: int | None) -> int:
    if override is not None:
        return override
    # Hatch (1): n=6 when prior rate within FLOOR_DISTANCE_TRIGGER of floor
    # (per feedback_alignment_eval_stability_window.md).
    gap = prior_rate - FR_OG_7_FLOOR
    if gap < FR_OG_7_FLOOR_DISTANCE_TRIGGER:
        return 6
    # Hatch (3): n=6 when prior-cycle Sonnet instability ratio exceeds
    # UNSTABLE_SONNET_RATIO_TRIGGER. Bound at v2.6 P2 = 15/32 = 47% > 25%
    # → v2.7 P3 must fire at --runs 6.
    if PRIOR_CYCLE_TOTAL_ROWS > 0 and (
        PRIOR_CYCLE_UNSTABLE_SONNET / PRIOR_CYCLE_TOTAL_ROWS
        > UNSTABLE_SONNET_RATIO_TRIGGER
    ):
        return 6
    return 3


def _eval_escape_hatch(report_json: dict) -> tuple[bool, list[str]]:
    """Return (should_rerun_at_n6, reasons)."""
    reasons: list[str] = []
    summary = report_json["summary"]
    n = summary["total"]
    unstable = summary["unstable_sonnet"]
    if n > 0 and unstable / n > UNSTABLE_SONNET_RATIO_TRIGGER:
        reasons.append(
            f"unstable_sonnet={unstable}/{n} > "
            f"{UNSTABLE_SONNET_RATIO_TRIGGER:.0%}"
        )
    rows = report_json["rows"]
    runs = report_json["runs"]
    high_timeout_rows = [
        rid for rid, r in rows.items()
        if r.get("sonnet_timeout_count", 0) / max(runs, 1) >= 0.50
    ]
    if high_timeout_rows:
        reasons.append(
            f"rows with sonnet_timeout_count/runs ≥ 0.50: "
            f"{','.join(high_timeout_rows)}"
        )
    # S+D (unanimous-stable-and-diverges) is delegated to alignment_eval's
    # ci-gate exit code; this helper only flags unstable + timeout triggers.
    return (len(reasons) > 0, reasons)


def cmd_align(args: argparse.Namespace) -> int:
    _print_header("S4 alignment-eval -- prior-cycle-aware runs branch")
    runs = _resolve_runs(PRIOR_CYCLE_SONNET_PASS_RATE, args.runs)
    print(f"  prior cycle Sonnet pass_rate = {PRIOR_CYCLE_SONNET_PASS_RATE}")
    print(f"  gap to floor                  = "
          f"{PRIOR_CYCLE_SONNET_PASS_RATE - FR_OG_7_FLOOR:.4f}")
    print(f"  --runs resolved               = {runs}")
    if args.dry_run:
        print("  (dry-run; pass --execute to invoke tools/alignment_eval.py)")
        return 0

    cmd = [sys.executable, "-m", "tools.alignment_eval",
           "--runs", str(runs), "--ci-gate"]
    print(f"  exec: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=ROOT, check=False)
    print(f"  alignment_eval exit = {proc.returncode}")

    # Find newest reports/alignment-eval-*.json and parse summary.
    json_files = sorted((ROOT / "reports").glob("alignment-eval-*.json"))
    if not json_files:
        print("  WARN: no sidecar JSON found")
        return proc.returncode
    latest = json_files[-1]
    with latest.open() as f:
        report = json.load(f)
    summary = report["summary"]
    print(f"  report: {latest.name}")
    print(f"    sonnet_pass_rate = {summary['sonnet_pass_rate']} "
          f"({summary['sonnet_pass']}/{summary['sonnet_stable_count']})")
    print(f"    haiku_pass_rate  = {summary['haiku_pass_rate']} "
          f"({summary['haiku_pass']}/{summary['haiku_stable_count']})")
    print(f"    unstable_sonnet  = {summary['unstable_sonnet']}")
    print(f"    unstable_haiku   = {summary['unstable_haiku']}")
    print(f"    regression_rows  = {summary['regression_rows']}")
    print(f"  per-model wall-clock:")
    for label in ("sonnet", "haiku"):
        n = summary[f"{label}_duration_s_n"]
        if n == 0:
            print(f"    {label}: n=0 (skipped)")
            continue
        print(f"    {label}: n={n} p50={summary[f'{label}_duration_s_p50']}s "
              f"p95={summary[f'{label}_duration_s_p95']}s "
              f"p99={summary[f'{label}_duration_s_p99']}s "
              f"max={summary[f'{label}_duration_s_max']}s")

    rerun, reasons = _eval_escape_hatch(report)
    if rerun and runs < 6:
        print("  ESCAPE-HATCH triggered -- re-run at --runs 6:")
        for r in reasons:
            print(f"    - {r}")
    elif rerun:
        print("  ESCAPE-HATCH conditions present, but already at --runs 6:")
        for r in reasons:
            print(f"    - {r}")
    else:
        print("  no escape-hatch trigger")
    return proc.returncode


# ============================================================
# s6.5  Seed v2.5-A diagnosis summary  (pre-executed PR #197)
# ============================================================

def cmd_s65(_args: argparse.Namespace) -> int:
    _print_header("S6.5 Seed v2.5-A diagnosis (pre-executed PR #197)")
    diag = ROOT / "docs" / "seed-v2.5-a-row10-diagnosis.md"
    sidecar = ROOT / "reports" / "seed-v2.5-a" / "alignment-eval-20260520T172054Z.json"
    if not diag.exists() or not sidecar.exists():
        print(f"  FAIL: diagnosis or sidecar missing")
        return 1
    with sidecar.open() as f:
        d = json.load(f)
    row = d["rows"]["frog7-wirecli-module-10"]
    print(f"  fixture: reports/seed-v2.5-a/row10-fixture.jsonl")
    print(f"  sidecar: {sidecar.relative_to(ROOT)}")
    print(f"  diagnosis: {diag.relative_to(ROOT)}")
    print(f"  sonnet_runs      = {row['sonnet_runs']}")
    print(f"  sonnet_majority  = {row['sonnet_majority']}")
    print(f"  sonnet_stable    = {row['sonnet_stable']}")
    print(f"  sonnet_timeout_count = {row['sonnet_timeout_count']}/6")
    print(f"  sonnet p50/p95/p99/max = "
          f"{d['summary']['sonnet_duration_s_p50']}/"
          f"{d['summary']['sonnet_duration_s_p95']}/"
          f"{d['summary']['sonnet_duration_s_p99']}/"
          f"{d['summary']['sonnet_duration_s_max']} s")
    print(f"  verdict matrix -> row 3 (1-2 timeouts, INTERVENE majority != "
          f"expected SUGGEST)")
    print(f"  VERDICT: CONTENT-DRIFT (with partial boundary-timeout residual)")
    print(f"  disposition: Seed v2.5-A CLOSED;")
    print(f"               NEW Seed v2.6-A (content-drift watch);")
    print(f"               NEW Seed v2.6-A-T (timeout-boundary watch)")
    return 0


# ============================================================
# all
# ============================================================

def cmd_all(_args: argparse.Namespace) -> int:
    rcs = []
    rcs.append(cmd_preflight(_args))
    rcs.append(cmd_wipe(argparse.Namespace(apply=False)))
    rcs.append(cmd_loc(_args))
    rcs.append(cmd_ledger(_args))
    rcs.append(cmd_s65(_args))
    soak = _latest_soak_report()
    if soak:
        rcs.append(cmd_inspect_soak(argparse.Namespace(path=str(soak))))
    else:
        print("\n[ship-gate] inspect-soak SKIPPED -- no soak report yet")
    print("\n[ship-gate] non-zero exit counts:",
          sum(1 for r in rcs if r != 0), "of", len(rcs))
    return 0 if all(r == 0 for r in rcs) else 1


# ============================================================
# CLI entrypoint
# ============================================================

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("preflight").set_defaults(func=cmd_preflight)

    pw = sub.add_parser("wipe")
    pw.add_argument("--apply", action="store_true",
                    help="actually wipe (default: dry-run)")
    pw.set_defaults(func=cmd_wipe)

    pi = sub.add_parser("inspect-soak")
    pi.add_argument("--path", help="explicit soak report path "
                    "(default: newest reports/soak-*.md)")
    pi.set_defaults(func=cmd_inspect_soak)

    pa = sub.add_parser("align")
    pa.add_argument("--runs", type=int, default=None,
                    help="override runs (default: auto from prior-cycle rate)")
    pa.add_argument("--dry-run", action="store_true",
                    help="print resolved --runs but do not invoke")
    pa.add_argument("--execute", dest="dry_run", action="store_false")
    pa.set_defaults(func=cmd_align, dry_run=True)

    sub.add_parser("loc").set_defaults(func=cmd_loc)
    sub.add_parser("ledger").set_defaults(func=cmd_ledger)
    sub.add_parser("s6.5").set_defaults(func=cmd_s65)
    sub.add_parser("all").set_defaults(func=cmd_all)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
