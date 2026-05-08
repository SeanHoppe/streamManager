"""v10 P2 — P1a Haiku probe source adapter.

Parses ``reports/p1a-corpus-haiku-verdicts-<UTC>.md`` (markdown table,
stable since v1.9). Wrapped corpus only — wrapped framing matches what
the soak / governor sends to Haiku. Each yielded episode has
hitl_override=1: BLOCK is the human-aligned outcome on destructive
content.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from rl.sources import VALID_VERDICTS, Episode
from rl.state_features import extract as extract_features


_RAW_HEADER = "## Raw samples"
_ROW_RE = re.compile(
    r"^\|\s*(?P<cls>[^|]+?)\s*"
    r"\|\s*`?(?P<prompt>[^`|]+?)`?\s*"
    r"\|\s*(?P<action>[A-Z]+|—|-)\s*"
    r"\|\s*(?P<confidence>[0-9.]+|—|-)\s*"
    r"\|\s*(?P<latency_s>[0-9.]+|—|-)\s*"
    r"\|\s*(?P<note>.*?)\s*\|\s*$"
)


def _stamp(path: Path) -> str:
    m = re.search(r"(\d{8}T\d{6}Z)", path.name)
    if m:
        return m.group(1)
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ")


def iter_episodes(corpus_path: Path) -> Iterator[Episode]:
    """Yield Episode records from a P1a probe markdown report."""
    corpus_path = Path(corpus_path)
    text = corpus_path.read_text(encoding="utf-8")
    stamp = _stamp(corpus_path)
    cycle_tag = f"p1a-{stamp}"
    base_ts = datetime(2000, 1, 1, tzinfo=timezone.utc)

    in_raw = False
    seen_sep = False
    idx = 0
    for line in text.splitlines():
        if line.strip().startswith(_RAW_HEADER):
            in_raw = True; seen_sep = False
            continue
        if not in_raw or not line.strip().startswith("|"):
            continue
        if "---" in line:
            seen_sep = True
            continue
        if not seen_sep:
            continue
        m = _ROW_RE.match(line)
        if not m:
            continue
        cls = m.group("cls")
        if "__wrapped" not in cls:
            continue
        action = m.group("action").upper()
        if action not in VALID_VERDICTS:
            continue
        prompt = m.group("prompt")
        try:
            confidence = float(m.group("confidence"))
        except ValueError:
            confidence = 0.0
        try:
            latency_ms = float(m.group("latency_s")) * 1000.0
        except ValueError:
            latency_ms = 0.0
        features = extract_features({
            "content": prompt, "latency_ms_last5": [latency_ms],
            "session_history_actions": [], "routing_band": 0,
            "trigger_factor": 0, "learn_mode_bias_hint": 0.0,
        }, now_utc=base_ts)
        idx += 1
        yield Episode(
            ts_utc=base_ts.isoformat(),
            session_id=f"probe-{stamp}",
            trace_id=f"{cycle_tag}-{idx}",
            state_features=features,
            action_taken=0.0, action_propensity=1.0,
            verdict=action, confidence=confidence,
            latency_ms=latency_ms, budget_violation=0,
            source="probe", cycle_tag=cycle_tag,
            hitl_override=1, fr_og_7_pass=None,
            provenance={"prompt_class": cls, "prompt": prompt},
        )
