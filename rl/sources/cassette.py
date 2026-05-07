"""v10 P2 — cassette source adapter.

Reads soak cassettes (``tests/fixtures/soak_cassette_*.jsonl``, ADR-17
Tier 2 frozen format). Cassette is a fixed-Haiku-policy recording
(action_propensity=1.0) that excludes alignment-required rows
(fr_og_7_pass=1, hitl_override=None).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from rl.sources import VALID_VERDICTS, Episode
from rl.state_features import extract as extract_features


_VERDICT_NORMALIZE = {
    "ALLOW": "ALLOW", "SUGGEST": "SUGGEST", "GUIDE": "SUGGEST",
    "INTERVENE": "INTERVENE", "BLOCK": "BLOCK", "AMBIGUOUS": "AMBIGUOUS",
}


def iter_episodes(cassette_path: Path) -> Iterator[Episode]:
    """Yield Episode records from a soak cassette JSONL file."""
    cassette_path = Path(cassette_path)
    cycle_tag = cassette_path.stem
    base_ts = datetime(2000, 1, 1, tzinfo=timezone.utc)
    with cassette_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            decision = row.get("decision") or {}
            verdict = _VERDICT_NORMALIZE.get(
                str(decision.get("action", "")).strip().upper(), "")
            if verdict not in VALID_VERDICTS:
                continue
            content = str(row.get("content", ""))
            confidence = float(decision.get("confidence", 0.0) or 0.0)
            latency_ms = float(row.get("recorded_latency_ms", 0.0) or 0.0)
            idx = int(row.get("idx", 0) or 0)
            features = extract_features({
                "content": content,
                "latency_ms_last5": [latency_ms],
                "session_history_actions": [],
                "routing_band": int(decision.get("layer", 0) or 0),
                "trigger_factor": 0,
                "learn_mode_bias_hint": 0.0,
            }, now_utc=base_ts)
            yield Episode(
                ts_utc=base_ts.isoformat(),
                session_id=f"cassette-{cycle_tag}",
                trace_id=f"{cycle_tag}-{idx}",
                state_features=features,
                action_taken=0.0, action_propensity=1.0,
                verdict=verdict, confidence=confidence,
                latency_ms=latency_ms, budget_violation=0,
                source="cassette", cycle_tag=cycle_tag,
                hitl_override=None, fr_og_7_pass=1,
                provenance={"kind": str(row.get("kind", "")), "idx": idx},
            )
