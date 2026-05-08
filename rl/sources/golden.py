"""v10 P2 — alignment-golden source adapter (HOLDOUT).

Reads ``tests/golden/l4_alignment.jsonl`` (n=32). Golden episodes feed
ONLY the P3 OPE harness — never the training set. The augmenter in
``rl.corpus_augment`` enforces this with an explicit assertion.
hitl_override is None on every golden episode (golden is labelled-
expected, not a HITL signal).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rl.sources import VALID_VERDICTS, Episode
from rl.state_features import extract as extract_features


_VERDICT_MAP = {
    "ALLOW": "ALLOW", "SUGGEST": "SUGGEST", "GUIDE": "SUGGEST",
    "INTERVENE": "INTERVENE", "BLOCK": "BLOCK",
}
DEFAULT_GOLDEN = (
    Path(__file__).resolve().parents[2] / "tests" / "golden" / "l4_alignment.jsonl"
)


def iter_episodes(golden_path: Optional[Path] = None) -> Iterator[Episode]:
    """Yield Episode records from the alignment golden JSONL."""
    path = Path(golden_path) if golden_path is not None else DEFAULT_GOLDEN
    base_ts = datetime(2000, 1, 1, tzinfo=timezone.utc)
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            verdict = _VERDICT_MAP.get(
                str(row.get("expected_verdict", "")).strip().upper(), "")
            if verdict not in VALID_VERDICTS:
                continue
            row_id = str(row.get("id", f"row-{line_no}"))
            tags = row.get("expected_safety_tags") or []
            frog7 = any("fr-og-7" in str(t).lower() for t in tags)
            features = extract_features({
                "content": str(row.get("prompt", "")),
                "latency_ms_last5": [], "session_history_actions": [],
                "routing_band": 4, "trigger_factor": 1,
                "learn_mode_bias_hint": 0.0,
            }, now_utc=base_ts)
            # FR-OG-7 rows: the recorded golden verdict IS the expected
            # FR-OG-7 verdict by construction; mark pass for both branches.
            yield Episode(
                ts_utc=base_ts.isoformat(),
                session_id="golden-alignment",
                trace_id=row_id,
                state_features=features,
                action_taken=0.0, action_propensity=1.0,
                verdict=verdict, confidence=1.0,
                latency_ms=0.0, budget_violation=0,
                source="golden", cycle_tag="alignment-golden",
                hitl_override=None, fr_og_7_pass=1,
                provenance={"id": row_id, "fr_og_7_row": frog7,
                            "model_floor": row.get("model_floor")},
            )
