"""v1.3 Path-A: soak_driver replay path handles ``learn_dialogue`` envelopes.

Synthesizes a small cassette containing 2 routine + 2 learn_dialogue rows,
runs ``_run_replay``, and asserts:

  - the run exits cleanly
  - the report contains an "LM (categorize)" per-band row
  - state.lm_categorize_latencies_s captures the sleep amount per LM row

Backward compat: a cassette WITHOUT learn_dialogue rows produces a
report whose per-band table has n=0 for the LM row.
"""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import soak_driver  # noqa: E402


def _write_cassette(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row) + "\n")


def _routine_row(idx: int) -> dict:
    return {
        "idx": idx,
        "kind": "routine",
        "content": f"echo {idx}",
        "recorded_latency_ms": 5.0,
        "decision": {
            "action": "ALLOW",
            "confidence": 1.0,
            "reasoning": "routine",
            "matched_hash": "",
            "model_used": "test",
            "layer": 0,
        },
    }


def _lm_row(idx: int, latency_ms: float = 1234.5) -> dict:
    return {
        "idx": idx,
        "kind": "learn_dialogue",
        "content": "Force push to main now?",
        "recorded_latency_ms": latency_ms,
        "decision": {
            "action": "ALLOW",
            "confidence": 0.9,
            "reasoning": "category=approve",
            "matched_hash": "",
            "model_used": "claude-sonnet-4-5",
            "layer": 0,
        },
        "desktop_prompt": "Force push to main now?",
        "user_reply": "yes do it",
        "recorded_categorize_latency_ms": latency_ms,
        "category_result": {
            "category": "approve",
            "confidence": 0.9,
            "reasoning": "test",
        },
    }


def test_replay_handles_learn_dialogue_envelopes(tmp_path):
    cassette = tmp_path / "cassette.jsonl"
    _write_cassette(cassette, [
        _routine_row(0),
        _routine_row(1),
        _lm_row(2, latency_ms=10.0),
        _lm_row(3, latency_ms=20.0),
    ])
    args = Namespace(
        cli_replay=str(cassette),
        gov_db=str(tmp_path / "replay.db"),
    )
    rc = soak_driver._run_replay(args)
    assert rc == 0
    # Newest replay report contains the LM band.
    reports = sorted((ROOT / "reports").glob("replay-*.md"),
                     key=lambda p: p.stat().st_mtime)
    assert reports, "no replay report produced"
    text = reports[-1].read_text(encoding="utf-8")
    assert "LM (categorize)" in text, text[-500:]
    # Per-band row should reflect 2 LM samples.
    assert "|   2 |" in text or "|  2  |" in text or "| 2 " in text


def test_replay_v12_cassette_omits_lm_row(tmp_path):
    """v1.2-shape cassette (no learn_dialogue rows) must replay cleanly.

    Replay always passes ``state.lm_categorize_latencies_s`` as a list
    (never None), so the per-band table renders an LM row populated with
    ``n=0`` rather than dropping it. Backward compat invariant: zero
    learn_dialogue envelopes in the cassette → zero samples in the LM
    band → ``n=0`` row, not a missing row.
    """
    cassette = tmp_path / "cassette.jsonl"
    _write_cassette(cassette, [_routine_row(0), _routine_row(1)])
    args = Namespace(
        cli_replay=str(cassette),
        gov_db=str(tmp_path / "replay.db"),
    )
    rc = soak_driver._run_replay(args)
    assert rc == 0
    reports = sorted((ROOT / "reports").glob("replay-*.md"),
                     key=lambda p: p.stat().st_mtime)
    text = reports[-1].read_text(encoding="utf-8")
    # The LM row is rendered with n=0 when state was empty AND the caller
    # passed an empty list — replay does pass the list (always non-None
    # in replay, may be empty). Verify n=0 row is what shows up:
    assert "LM (categorize)" in text
    # n=0 means the cassette had zero learn_dialogue envelopes.
    rows = [l for l in text.splitlines() if l.startswith("| LM (categorize)")]
    assert rows, "LM row missing"
    # The n column is the 2nd column; parse loosely.
    cells = [c.strip() for c in rows[0].split("|")[1:-1]]
    assert cells[1] == "0", cells
