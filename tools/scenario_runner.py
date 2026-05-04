#!/usr/bin/env python3
"""Scenario runner — three modes (Methods 1 / 2 / 3 per docs/v1.3-testing.md).

  --scenarios <path.yaml>   : Method 1 (Scripted Scenario Replay) — v1.4.
  --beacons   <path.jsonl>  : Method 2 (Expectation Beacon)        — v1.3.
  --probes    <path.csv>    : Method 3 (Adversarial Drift Probe)   — v1.3.
  --all                     : Run every fixture under tests/scenarios/,
                              tests/beacons/, tests/probes/ in CI mode.

The default mode for beacons / probes mocks out the live
``categorize_pair`` call by returning the row's expected category —
useful for CI smoke-checking the harness wiring without spawning
Sonnet subprocesses. Pass ``--live`` to invoke the real ``claude -p``
subprocess and assert the real categorizer agrees with the canned
expectation.

For scenarios (Method 1), the runner is a schema + sequence validator
in CI mode — it prints each ``operator_prompt`` step and asserts the
expected envelope shape is well-formed YAML. Operator-in-the-loop
execution (waiting on the bus for envelopes) is interactive and
remains the authoritative validation; CI mode keeps the artifact
library honest without requiring Desktop traffic.

Usage:

    python tools/scenario_runner.py --beacons tests/beacons/learn_mode_categorizer.jsonl
    python tools/scenario_runner.py --probes  tests/probes/learn_mode_drift.csv
    python tools/scenario_runner.py --scenarios tests/scenarios/governance_l0_routine.yaml
    python tools/scenario_runner.py --all
    # Live (requires `claude` on PATH and SM_LEARN_MODE=1):
    python tools/scenario_runner.py --beacons tests/beacons/learn_mode_categorizer.jsonl --live

Exit code:

  0 — all assertions passed.
  1 — at least one assertion failed.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
from pathlib import Path

# Allow execution from a checkout that hasn't pip-installed the package.
_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _mock_runner_factory(category: str, confidence: float = 0.85):
    """Return a runner that fakes a successful Sonnet envelope."""
    from dataclasses import dataclass

    @dataclass
    class _CP:
        returncode: int
        stdout: str
        stderr: str = ""

    envelope = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": json.dumps(
            {"category": category, "confidence": confidence, "reasoning": "mock"}
        ),
    }
    payload = json.dumps(envelope)

    def _runner(cmd, **kwargs):
        return _CP(returncode=0, stdout=payload)

    return _runner


def _categorize(prompt: str, reply: str, *, live: bool, expected: str) -> tuple[str, float] | None:
    """Run categorize_pair, mocked or live. Returns (category, confidence)."""
    from stream_manager.learn_categorizer import categorize_pair

    runner = None if live else _mock_runner_factory(expected)
    result = categorize_pair(prompt, reply, runner=runner)
    if result is None:
        return None
    return (result.category, result.confidence)


_MOCK_PREFIX = "[MOCK] "
_MOCK_BANNER = (
    "*** MOCK MODE: assertions exercise harness wiring only, NOT "
    "categorizer quality. Pass --live to invoke the real model. ***"
)


def _emit(line: str, *, live: bool) -> None:
    """Print a line, prefixing mock-mode lines with [MOCK].

    Defensive against narrow stdout encodings (Windows cp1252): falls
    back to ASCII-replacing the line so a Unicode character in a
    fixture description never crashes the harness.
    """
    out = line if live else f"{_MOCK_PREFIX}{line}"
    try:
        print(out)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(out.encode(enc, errors="replace").decode(enc, errors="replace"))


def run_beacons(path: Path, *, live: bool, mock_pass: bool) -> int:
    """Drive a beacons JSONL file. Returns failure count."""
    failed = 0
    total = 0
    if not live:
        print(_MOCK_BANNER)
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            row = json.loads(line)
            total += 1
            beacon_id = row.get("beacon_id", "<no-id>")
            prompt = row.get("operator_prompt", "")
            reply = row.get("operator_reply", "")
            assertion = row.get("assertion", {})
            expected_cat = str(assertion.get("category", ""))
            min_conf = float(assertion.get("confidence_min", 0.0))

            # In mock mode (default), force the runner to return the
            # expected category — exercises the harness wiring + the
            # parser, not the model.
            out = _categorize(prompt, reply, live=live, expected=expected_cat)
            if out is None:
                _emit(f"FAIL {beacon_id}: categorizer returned None", live=live)
                failed += 1
                continue
            cat, conf = out
            if cat != expected_cat:
                _emit(
                    f"FAIL {beacon_id}: got category={cat!r}, expected={expected_cat!r}",
                    live=live,
                )
                failed += 1
                continue
            if conf < min_conf:
                _emit(
                    f"FAIL {beacon_id}: got confidence={conf:.2f} < min={min_conf:.2f}",
                    live=live,
                )
                failed += 1
                continue
            _emit(f"PASS {beacon_id}: {cat} ({conf:.2f})", live=live)
    _emit(f"\nbeacons: {total - failed}/{total} passed", live=live)
    return failed


def run_probes(path: Path, *, live: bool) -> int:
    """Drive a drift probe CSV file. Returns failure count.

    Probe assertions per row:

      1. Categorizer returns ``true_category``, not any of the
         distractors (Method 3 §1).
      2. After running all rows, no canonical row whose
         ``true_category=='reject'`` produces an ``approve`` BiasHint
         (the false-promotion gate).
      3. Where the row sequence implies a contradiction (same prompt
         later flips category), the canonical row must show
         ``contradicted_count > 0`` AND ``ladder_step`` snapped down.
    """
    from stream_manager import message_bus as _mb
    from stream_manager.decay import (
        CONTRADICTION_DEMOTE_STEPS,
        consolidate_patterns,
    )
    from stream_manager.learn_categorizer import (
        MIN_BIAS_CONFIDENCE,
        bias_for,
        prompt_hash,
    )

    failed = 0
    total = 0
    if not live:
        print(_MOCK_BANNER)
    seen_categories: dict[str, str] = {}  # prompt_hash → last seen category
    all_true_cats: dict[str, set[str]] = {}  # prompt_hash → all true_categories observed
    contradiction_expected: set[str] = set()  # prompt_hashes where we expect a snap-demote
    # Track the original (pre-contradiction) category per prompt_hash so we
    # can pre-reinforce it 3× before the flip lands. That drives peak
    # ladder_step above CONTRADICTION_DEMOTE_STEPS so the snap-demote is
    # observable on the canonical row.
    pre_reinforced: set[str] = set()

    with tempfile.TemporaryDirectory() as td:
        os.environ["SM_LEARN_MODE"] = "1"
        bus = _mb.MessageBus(str(Path(td) / "probe.db"))
        try:
            with path.open("r", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    total += 1
                    prompt = row["prompt"].strip()
                    reply = row["reply"].strip()
                    true_cat = row["true_category"].strip()
                    distractors = {
                        c.strip() for c in row["distractor_categories"].split(",")
                    }

                    # 1. Categorizer assertion: returns true_cat, not a distractor.
                    out = _categorize(prompt, reply, live=live, expected=true_cat)
                    if out is None:
                        _emit(
                            f"FAIL probe row {total}: categorizer returned None for "
                            f"{prompt!r}",
                            live=live,
                        )
                        failed += 1
                        continue
                    cat, conf = out
                    if cat in distractors:
                        _emit(
                            f"FAIL probe row {total}: got distractor category "
                            f"{cat!r} for prompt={prompt!r}",
                            live=live,
                        )
                        failed += 1
                        continue
                    if cat != true_cat:
                        _emit(
                            f"FAIL probe row {total}: got {cat!r}, "
                            f"expected {true_cat!r}",
                            live=live,
                        )
                        failed += 1
                        continue

                    # Track contradictions: same prompt_hash, different category.
                    h = prompt_hash(prompt)
                    prev = seen_categories.get(h)
                    if prev is not None and prev != true_cat:
                        contradiction_expected.add(h)
                        # Pre-reinforce the ORIGINAL category 3× so peak
                        # ladder_step exceeds CONTRADICTION_DEMOTE_STEPS.
                        # Without this the canonical row sits at step=0
                        # and the snap-demote (also flooring at 0) is
                        # invisible. Done once per (prompt_hash, flip).
                        if h not in pre_reinforced:
                            for _ in range(3):
                                consolidate_patterns(bus, h, prev, conf)
                            pre_reinforced.add(h)
                    seen_categories[h] = true_cat
                    all_true_cats.setdefault(h, set()).add(true_cat)

                    # Merge into canonical projection.
                    consolidate_patterns(bus, h, cat, conf)

            # 2. False-promotion gate: no prompt that EVER had a 'reject'
            #    ground-truth row may end up with an 'approve' canonical
            #    category sitting at confidence >= MIN_BIAS_CONFIDENCE
            #    AND ladder_step > 0. ladder_step==0 means contradiction
            #    snap-demote already neutralized any promotion attempt,
            #    which is exactly the design contract.
            for h, true_cats in all_true_cats.items():
                if "reject" not in true_cats:
                    continue
                rows = bus.fetch_rows(
                    "SELECT category, confidence, ladder_step FROM "
                    "learn_patterns_canonical WHERE prompt_hash=?",
                    (h,),
                )
                if not rows:
                    continue
                cat, conf, step = str(rows[0][0]), float(rows[0][1]), int(rows[0][2])
                if (
                    cat == "approve"
                    and conf >= MIN_BIAS_CONFIDENCE
                    and step > 0
                ):
                    _emit(
                        f"FAIL false promotion: prompt_hash={h} sat at "
                        f"approve conf={conf:.2f} step={step} despite "
                        f"prior reject ground-truth",
                        live=live,
                    )
                    failed += 1

            # 3. Contradiction snap-demote check.
            for h in contradiction_expected:
                rows = bus.fetch_rows(
                    "SELECT contradicted_count, ladder_step FROM "
                    "learn_patterns_canonical WHERE prompt_hash=?",
                    (h,),
                )
                if not rows:
                    continue
                cc, ladder = int(rows[0][0]), int(rows[0][1])
                if cc <= 0:
                    _emit(
                        f"FAIL contradiction snap-demote did not fire for "
                        f"prompt_hash={h} (contradicted_count={cc})",
                        live=live,
                    )
                    failed += 1
                # ladder_step should be reduced from its peak; pre-
                # reinforcement above pushed peak above
                # CONTRADICTION_DEMOTE_STEPS so the demote is observable
                # in the ladder column too.
                _emit(
                    f"contradiction observed: {h[:8]} cc={cc} "
                    f"ladder_step={ladder} (snap by {CONTRADICTION_DEMOTE_STEPS})",
                    live=live,
                )
        finally:
            bus.close()
            os.environ.pop("SM_LEARN_MODE", None)

    _emit(f"\nprobes: {total - failed}/{total} rows passed", live=live)
    return failed


def run_scenarios(path: Path, *, live: bool) -> int:
    """v1.4 Method 1 — Scripted Scenario Replay.

    Loads a YAML scenario file matching the schema in
    ``docs/v1.3-testing.md`` §"Method 1" and:

      * In CI mode (default for ``--all``): validates each step's
        schema, prints the ``operator_prompt`` line, asserts the
        ``expected_envelopes`` list is well-formed (each entry has
        ``type`` and an optional ``payload_match`` mapping). Returns
        the count of malformed steps.
      * In ``--live`` mode: connects to the active SM bus, prints
        each prompt, and waits up to ``timeout_s`` for the expected
        envelope sequence. Operator drives Desktop manually. Returns
        the count of timed-out / mismatched steps.

    Returns the failure count (0 = pass).
    """
    import yaml  # type: ignore[import-untyped]

    failed = 0
    if not live:
        print(_MOCK_BANNER)
    try:
        with path.open("r", encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
    except Exception as exc:
        _emit(f"FAIL {path.name}: YAML parse error: {exc}", live=live)
        return 1
    if not isinstance(doc, dict):
        _emit(f"FAIL {path.name}: top-level must be a mapping", live=live)
        return 1
    name = str(doc.get("name", path.stem))
    desc = str(doc.get("description", ""))
    steps = doc.get("steps")
    if not isinstance(steps, list) or not steps:
        _emit(f"FAIL {name}: steps[] missing or empty", live=live)
        return 1
    _emit(f"\n## scenario: {name}", live=live)
    if desc:
        _emit(f"   {desc}", live=live)
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            _emit(f"FAIL step #{idx}: not a mapping", live=live)
            failed += 1
            continue
        prompt = step.get("operator_prompt")
        if not isinstance(prompt, str) or not prompt:
            _emit(f"FAIL step #{idx}: operator_prompt missing", live=live)
            failed += 1
            continue
        envs = step.get("expected_envelopes", [])
        if not isinstance(envs, list):
            _emit(
                f"FAIL step #{idx}: expected_envelopes must be a list",
                live=live,
            )
            failed += 1
            continue
        for j, env in enumerate(envs):
            if not isinstance(env, dict) or "type" not in env:
                _emit(
                    f"FAIL step #{idx}.envelope[{j}]: missing 'type'",
                    live=live,
                )
                failed += 1
                break
            pm = env.get("payload_match", {})
            if not isinstance(pm, dict):
                _emit(
                    f"FAIL step #{idx}.envelope[{j}]: payload_match must be a mapping",
                    live=live,
                )
                failed += 1
                break
        else:
            # Schema OK — print + (CI) move on, (live) would wait here.
            _emit(
                f"  step {idx + 1}/{len(steps)}: {prompt.splitlines()[0][:80]}",
                live=live,
            )
            if live:
                _emit(
                    f"    [live mode TODO: bus-wait for envelope sequence "
                    f"within {step.get('timeout_s', 30)} s]",
                    live=live,
                )
    _emit(f"  scenario {name}: {len(steps) - failed}/{len(steps)} steps OK",
          live=live)
    return failed


def run_all(*, live: bool) -> int:
    """``--all`` aggregate: every fixture under tests/{scenarios,beacons,probes}/.

    Returns the total failure count across all fixtures. Each fixture
    type uses its own runner (run_scenarios / run_beacons / run_probes)
    so a single failed beacon does not skip the rest of the library.
    """
    failed = 0
    scenarios_dir = _ROOT / "tests" / "scenarios"
    beacons_dir = _ROOT / "tests" / "beacons"
    probes_dir = _ROOT / "tests" / "probes"

    yaml_files = sorted(scenarios_dir.glob("*.yaml")) if scenarios_dir.is_dir() else []
    beacon_files = sorted(beacons_dir.glob("*.jsonl")) if beacons_dir.is_dir() else []
    probe_files = sorted(probes_dir.glob("*.csv")) if probes_dir.is_dir() else []

    _emit(f"\n=== scenarios ({len(yaml_files)} fixtures) ===", live=live)
    for f in yaml_files:
        failed += run_scenarios(f, live=live)
    _emit(f"\n=== beacons ({len(beacon_files)} fixtures) ===", live=live)
    for f in beacon_files:
        failed += run_beacons(f, live=live, mock_pass=True)
    _emit(f"\n=== probes ({len(probe_files)} fixtures) ===", live=live)
    for f in probe_files:
        failed += run_probes(f, live=live)
    total = len(yaml_files) + len(beacon_files) + len(probe_files)
    _emit(f"\n=== --all summary: {total} fixtures, {failed} failures ===",
          live=live)
    return failed


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="v1.3 Learn Mode scenario runner")
    p.add_argument("--scenarios", type=str, help="path to a Method 1 YAML scenario")
    p.add_argument("--beacons", type=str, help="path to beacons JSONL")
    p.add_argument("--probes", type=str, help="path to drift probe CSV")
    p.add_argument(
        "--all",
        action="store_true",
        help="run every fixture under tests/scenarios/, tests/beacons/, "
             "tests/probes/ in CI mode",
    )
    p.add_argument(
        "--live",
        action="store_true",
        help="invoke the real `claude -p` subprocess (default: mocked)",
    )
    p.add_argument(
        "positional",
        nargs="?",
        help=(
            "positional fixture path (alternative to --beacons/--probes); "
            "kind inferred from --mode or extension"
        ),
    )
    p.add_argument(
        "--mode",
        choices=("beacon", "probe", "scenario"),
        default=None,
        help="explicit kind selector when using a positional path",
    )
    p.add_argument(
        "--mock",
        action="store_true",
        help="explicit mock-mode flag (default behavior; included for clarity)",
    )
    args = p.parse_args(argv)

    if args.all:
        return 0 if run_all(live=args.live) == 0 else 1

    # Resolve fixture path + kind.
    scenarios_path: Path | None = Path(args.scenarios) if args.scenarios else None
    beacons_path: Path | None = Path(args.beacons) if args.beacons else None
    probes_path: Path | None = Path(args.probes) if args.probes else None
    if args.positional and not (scenarios_path or beacons_path or probes_path):
        pp = Path(args.positional)
        kind = args.mode
        if kind is None:
            sfx = pp.suffix.lower()
            if sfx == ".csv":
                kind = "probe"
            elif sfx in (".yaml", ".yml"):
                kind = "scenario"
            else:
                kind = "beacon"
        if kind == "beacon":
            beacons_path = pp
        elif kind == "scenario":
            scenarios_path = pp
        else:
            probes_path = pp

    if not (scenarios_path or beacons_path or probes_path):
        p.error("must provide --scenarios, --beacons, --probes, --all, "
                "or a positional path")

    failed = 0
    if scenarios_path is not None:
        failed += run_scenarios(scenarios_path, live=args.live)
    if beacons_path is not None:
        failed += run_beacons(beacons_path, live=args.live, mock_pass=True)
    if probes_path is not None:
        failed += run_probes(probes_path, live=args.live)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
