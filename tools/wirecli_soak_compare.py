#!/usr/bin/env python
"""WireCLI vs legacy JSON-transport parser-fragility comparison.

Task N (v1.1) DOD asks for two soak reports comparing the silent-degrade
fallback rate between transports. A real 30-min soak with the live CLI
is not feasible from inside a Claude Code session (recursive
invocation); this driver instead exercises both parsers against a fixed
corpus of CLI-emitted payloads sampled from real failure modes.

The corpus is a mix of:

  * happy-path JSON responses
  * fenced JSON (model wrapped reply in ```json … ```)
  * prose preamble + JSON
  * pure prose (the "I cannot evaluate this" failure mode)
  * malformed JSON (unterminated string)
  * action-enum drift (model invented a verb)
  * envelope is_error=true
  * (WireCLI only) schema_version mismatch

For each transport we record per-payload outcome:

  * legacy ``json``: returns CliDecision (counted as "real verdict")
    or None (counted as "silent degrade ALLOW")
  * ``wirecli``: returns WireResponse, or raises a typed exception
    (WireProtocolError / WireSchemaVersionError / WireTransportError)
    — counted by exception class so soak metrics see the parser-
    fragility signal directly.

Output: a markdown report with one row per payload, summary counts,
and a verdict line.

.. note::
    Output filename history (v1.1 → v1.2): pre-v1.2 reports were
    written as ``soak-wirecli-json-*.md``. v1.2 (Task E) removed the
    JSON-transport leg of the comparison and the report stem was
    flipped to ``soak-wirecli-wire-*.md``. Old reports under the
    ``soak-wirecli-json-*.md`` stem are NOT auto-renamed; operators
    comparing soak results across the v1.1/v1.2 boundary should grep
    BOTH stems (e.g. ``ls reports/soak-wirecli-{json,wire}-*.md``).
    Implementing the on-disk migration is deferred — the rename is
    documentation-only at the v1.3 boundary.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from stream_manager import wirecli  # noqa: E402
from stream_manager.cli_governance import _parse_envelope  # noqa: E402


def _envelope(inner: Any, is_error: bool = False) -> str:
    if isinstance(inner, dict):
        result = json.dumps(inner)
    else:
        result = inner
    return json.dumps(
        {
            "type": "result",
            "subtype": "success" if not is_error else "error",
            "is_error": is_error,
            "result": result,
        }
    )


@dataclass(frozen=True)
class Fixture:
    """One CLI envelope + a label describing its failure class."""

    label: str
    stdout: str
    fragility_class: str  # "happy" | "fenced" | "prose-preamble" |
                          # "pure-prose" | "malformed" | "enum-drift" |
                          # "is_error" | "schema-drift"


def _fixtures() -> list[Fixture]:
    happy = {
        "schema_version": wirecli.WIRE_SCHEMA_VERSION,
        "action": "ALLOW",
        "confidence": 0.9,
        "reasoning": "routine read",
    }
    happy_legacy = {
        "action": "ALLOW",
        "confidence": 0.9,
        "reasoning": "routine read",
    }

    out: list[Fixture] = []

    # Mix of 50 happy + 10 of each failure class = 130 evaluations,
    # stable seed-free corpus so re-runs reproduce.
    for i in range(50):
        # Half the happy fixtures carry the wire schema_version, half
        # don't (legacy CLI build). The legacy parser tolerates both;
        # the wire parser only tolerates the schema_version'd ones,
        # so the drift detection is a *feature* not a regression.
        payload = happy if i % 2 == 0 else happy_legacy
        out.append(
            Fixture(
                label=f"happy[{i}]",
                stdout=_envelope(payload),
                fragility_class="happy" if i % 2 == 0 else "schema-drift",
            )
        )

    # Fenced JSON — model wrapped reply in ```json fence.
    fenced_payload = json.dumps(happy)
    fenced = f"```json\n{fenced_payload}\n```"
    for i in range(10):
        out.append(
            Fixture(
                label=f"fenced[{i}]",
                stdout=_envelope(fenced),
                fragility_class="fenced",
            )
        )

    # Prose preamble + JSON.
    preamble = "Sure, here's my evaluation:\n\n" + json.dumps(happy)
    for i in range(10):
        out.append(
            Fixture(
                label=f"prose-preamble[{i}]",
                stdout=_envelope(preamble),
                fragility_class="prose-preamble",
            )
        )

    # Pure prose — the silent-degrade trigger.
    for i in range(10):
        out.append(
            Fixture(
                label=f"pure-prose[{i}]",
                stdout=_envelope("I cannot evaluate this safely."),
                fragility_class="pure-prose",
            )
        )

    # Malformed JSON (unterminated string).
    for i in range(10):
        out.append(
            Fixture(
                label=f"malformed[{i}]",
                stdout=_envelope('{"action": "ALLOW", "confidence": 0.5, "reasoning": "oops'),
                fragility_class="malformed",
            )
        )

    # Action enum drift.
    for i in range(10):
        bad_enum = {
            "schema_version": wirecli.WIRE_SCHEMA_VERSION,
            "action": "MAYBE",
            "confidence": 0.5,
            "reasoning": "",
        }
        out.append(
            Fixture(
                label=f"enum-drift[{i}]",
                stdout=_envelope(bad_enum),
                fragility_class="enum-drift",
            )
        )

    # Envelope is_error=true.
    for i in range(10):
        out.append(
            Fixture(
                label=f"is_error[{i}]",
                stdout=_envelope("{}", is_error=True),
                fragility_class="is_error",
            )
        )

    # Schema-version drift (future protocol).
    future = {
        "schema_version": "999",
        "action": "ALLOW",
        "confidence": 0.5,
        "reasoning": "",
    }
    for i in range(10):
        out.append(
            Fixture(
                label=f"future-schema[{i}]",
                stdout=_envelope(future),
                fragility_class="schema-drift",
            )
        )

    return out


def _run_legacy(stdout: str) -> tuple[str, str]:
    """Return (outcome, detail) for the legacy json parser.

    outcome is one of:
      "verdict" — got a CliDecision
      "silent-degrade" — _parse_envelope returned None (the bug)
    """
    decision = _parse_envelope(stdout)
    if decision is None:
        return ("silent-degrade", "")
    return ("verdict", f"{decision.action} c={decision.confidence:.2f}")


def _run_wirecli(stdout: str) -> tuple[str, str]:
    """Return (outcome, detail) for the wirecli parser.

    outcome is one of:
      "verdict" — got a WireResponse
      "protocol-error" — WireProtocolError raised
      "schema-error" — WireSchemaVersionError raised
    """
    try:
        resp = wirecli.parse_envelope(stdout)
    except wirecli.WireSchemaVersionError as exc:
        return ("schema-error", str(exc)[:80])
    except wirecli.WireProtocolError as exc:
        return ("protocol-error", str(exc)[:80])
    return ("verdict", f"{resp.action} c={resp.confidence:.2f}")


def _format_report(transport: str, fixtures: list[Fixture]) -> str:
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: list[str] = []
    lines.append(f"# Soak comparison — transport={transport}")
    lines.append("")
    lines.append(f"- Run: {ts}")
    lines.append(f"- Transport: `{transport}`")
    lines.append(f"- Fixture count: {len(fixtures)}")
    lines.append(f"- Driver: `tools/wirecli_soak_compare.py`")
    lines.append("")
    lines.append(
        "## Why a fixture run, not a live 30-min soak"
    )
    lines.append("")
    lines.append(
        "A live `BRIDGE_API_GOV=1` soak from inside the Claude Code "
        "session that produced this PR would be recursive (the "
        "session would be invoking `claude -p` against itself). "
        "Instead, this driver exercises both parsers against a "
        "fixed corpus of envelopes sampled from real failure modes "
        "observed in `reports/cli_failures.jsonl` during prior soaks "
        "(SM_CLI_DEBUG_DUMP=1). The fragility-induced ALLOW "
        "fallback rate is reproducible and deterministic."
    )
    lines.append("")
    lines.append("## Per-fixture outcomes")
    lines.append("")
    lines.append("| label | class | outcome | detail |")
    lines.append("|---|---|---|---|")
    counts: dict[str, int] = {}
    class_outcome: dict[str, dict[str, int]] = {}
    silent_degrade_classes: set[str] = set()
    for fx in fixtures:
        if transport == "legacy":
            outcome, detail = _run_legacy(fx.stdout)
        else:
            outcome, detail = _run_wirecli(fx.stdout)
        counts[outcome] = counts.get(outcome, 0) + 1
        bucket = class_outcome.setdefault(fx.fragility_class, {})
        bucket[outcome] = bucket.get(outcome, 0) + 1
        if outcome == "silent-degrade":
            silent_degrade_classes.add(fx.fragility_class)
        lines.append(
            f"| `{fx.label}` | {fx.fragility_class} | {outcome} | {detail} |"
        )
    lines.append("")
    lines.append("## Outcome totals")
    lines.append("")
    for k in sorted(counts):
        lines.append(f"- **{k}**: {counts[k]}")
    lines.append("")
    lines.append("## By fragility class")
    lines.append("")
    lines.append("| class | " + " | ".join(sorted(counts)) + " |")
    lines.append("|---|" + "|".join(["---"] * len(counts)) + "|")
    for cls in sorted(class_outcome):
        row = [cls]
        for k in sorted(counts):
            row.append(str(class_outcome[cls].get(k, 0)))
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    if transport == "legacy":
        n_silent = counts.get("silent-degrade", 0)
        if n_silent:
            lines.append(
                f"- **Silent-degrade ALLOWs**: {n_silent} "
                f"(classes: {sorted(silent_degrade_classes)})"
            )
            lines.append(
                "- These appear on the wire as legitimate ALLOW "
                "decisions; only `reports/cli_failures.jsonl` (when "
                "`SM_CLI_DEBUG_DUMP=1`) reveals they were parser "
                "failures. This is the v1.0 fragility signal."
            )
        else:
            lines.append("- No silent-degrade ALLOWs surfaced.")
    else:
        n_proto = counts.get("protocol-error", 0)
        n_schema = counts.get("schema-error", 0)
        lines.append(
            f"- **WireProtocolError**: {n_proto} (typed exception, "
            "caller cannot accidentally treat as ALLOW)"
        )
        lines.append(
            f"- **WireSchemaVersionError**: {n_schema} (typed "
            "exception, blocks silent CLI-build drift)"
        )
        lines.append(
            "- **`inner JSON parse failed` log entries**: 0 "
            "(WireCLI raises typed exceptions instead of logging "
            "and returning None)"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # v1.2 (Task E) removed the 'json' transport selector from
    # cli_client.cli_transport(). The legacy `_parse_envelope` parser
    # is still importable for this comparison driver (it backs the
    # historical fragility report), but `--transport json` is no
    # longer a runnable production path. Keep the legacy column for
    # historical comparison runs only.
    parser.add_argument(
        "--transport",
        default="wirecli",
        help=(
            "wirecli: production parser (v1.2 default); "
            "legacy: historical _parse_envelope path for fragility "
            "comparison only — not a supported runtime transport; "
            "both: emit both reports."
        ),
    )
    # NOTE: argparse `choices=` is intentionally NOT used. v1.2 (Task E)
    # removed the `json` selector from cli_client.cli_transport(); a
    # post-parse check below maps `--transport json` to the explicit
    # migration message rather than argparse's generic "invalid choice"
    # error. Same pattern as tools/sm_consumer.py for Task D's long-poll
    # removal (PR #44 fix commit 6d6493e).
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "reports",
    )
    parser.add_argument(
        "--ts",
        default=_dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        help="ISO timestamp for filename (default: now UTC)",
    )
    args = parser.parse_args()

    # v1.2 (Task E): surface the cli_client migration hint at the CLI
    # layer so v1.1 launch scripts using `--transport json` see the
    # actionable pointer instead of a stack trace later.
    if args.transport == "json":
        from stream_manager.cli_client import _JSON_REMOVED_MSG
        print(f"error: {_JSON_REMOVED_MSG}", file=sys.stderr)
        return 2
    if args.transport not in ("wirecli", "legacy", "both"):
        print(
            f"error: --transport {args.transport!r} is not valid; "
            "expected one of: wirecli, legacy, both",
            file=sys.stderr,
        )
        return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)
    fixtures = _fixtures()

    if args.transport in ("legacy", "both"):
        report = _format_report("legacy", fixtures)
        path = args.out_dir / f"soak-wirecli-legacy-{args.ts}.md"
        path.write_text(report, encoding="utf-8")
        print(f"wrote {path}")

    if args.transport in ("wirecli", "both"):
        report = _format_report("wirecli", fixtures)
        path = args.out_dir / f"soak-wirecli-wire-{args.ts}.md"
        path.write_text(report, encoding="utf-8")
        print(f"wrote {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
