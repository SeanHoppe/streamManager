#!/usr/bin/env python
"""v1.4 — regenerate Learn Mode beacon JSONL from cassette pairs.

Single source of truth for the canonical Learn Mode dialogue pair
set is ``tools/cassette_record.py::_LM_DIALOGUE_PAIRS_WITH_CATEGORY``.
This script regenerates ``tests/beacons/learn_mode_cassette_pairs.jsonl``
by serialising those pairs into the Method 2 (Expectation Beacon)
JSONL schema documented in ``docs/v1.3-testing.md``.

Run after editing ``_LM_DIALOGUE_PAIRS_WITH_CATEGORY`` to keep the
cassette and beacon libraries in sync.

Usage::

    python tools/regenerate_lm_beacons.py

Exits 0 on success, 1 on write failure.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from cassette_record import _LM_DIALOGUE_PAIRS_WITH_CATEGORY  # noqa: E402


# Confidence floor matches the existing learn_mode_categorizer.jsonl
# beacon set so the harness behaviour is consistent across both files.
_CONFIDENCE_MIN = 0.5
# Default bus-wait timeout per beacon row; matches the existing file.
_TIMEOUT_S = 30


def _row(idx: int, prompt: str, reply: str, category: str) -> dict:
    row = {
        "beacon_id": f"lm-cassette-{idx:03d}",
        "operator_prompt": prompt,
        "operator_reply": reply,
        "assertion": {"category": category},
        "timeout_s": _TIMEOUT_S,
    }
    # Categories whose ladder-step bias is actionable in v1.3 (approve /
    # reject) get a confidence floor; clarify / acknowledge / redirect
    # categorize without a floor since they're not actionable hints.
    if category in ("approve", "reject"):
        row["assertion"]["confidence_min"] = _CONFIDENCE_MIN
    return row


def main() -> int:
    out_path = ROOT / "tests" / "beacons" / "learn_mode_cassette_pairs.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        _row(idx, prompt, reply, cat)
        for idx, (prompt, reply, cat) in enumerate(
            _LM_DIALOGUE_PAIRS_WITH_CATEGORY, start=1
        )
    ]
    try:
        with out_path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")
    except OSError as exc:
        print(f"[regen] write failed: {exc}", file=sys.stderr)
        return 1
    print(f"[regen] wrote {len(rows)} rows -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
