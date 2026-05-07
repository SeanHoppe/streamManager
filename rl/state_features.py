"""v10 P1 — pure state-feature extraction.

Per docs/v10-rl-design.md §3, ``extract`` returns the v10 design-doc
feature vector exactly. Pure: no I/O, no clock reads. Caller supplies
``now_utc``. Regex helpers are v10-owned (no import from FROZEN
modules).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

# v10-owned destructive-content patterns. Mirrors the spirit of the
# v1.9 P1a probe corpus ground truth (>= 90% match expected on the
# wrapped probe set per phase-1 prompt §C1).
_DESTRUCTIVE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\brm\s+-rf\b",
        r"\bdrop\s+(table|database|schema)\b",
        r"\btruncate\s+table\b",
        r"\bdelete\s+from\b.*\bwhere\s+1\s*=\s*1\b",
        r"\bgit\s+(reset\s+--hard|push\s+--force|clean\s+-f)",
        r"\bsudo\s+rm\b",
        r"\bmkfs\.\w+",
        r"\bdd\s+if=.+of=/dev/(sd|nvme|hd)",
        r"\b:\s*\(\)\s*\{\s*:\|\:&\s*\}\s*;\s*:",  # fork bomb
        r"\bchmod\s+-R\s+0?777\b",
    )
)

# v10-owned alignment-trigger heuristic patterns. Match content that
# typically forces a routing-band escalation to L4 alignment-eval.
_ALIGNMENT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bproduction\b",
        r"\bcustomer[- ]facing\b",
        r"\bfinancial\b",
        r"\bregulator(y|ion)\b",
        r"\bcompliance\b",
        r"\bpii\b",
        r"\bauthent(icat|or)",
        r"\bsecret\b",
        r"\bcredential\b",
    )
)

VERDICTS: tuple[str, ...] = ("ALLOW", "SUGGEST", "INTERVENE", "BLOCK", "AMBIGUOUS")

FEATURE_KEYS: tuple[str, ...] = (
    "latency_ms_last5_p95",
    "content_length",
    "regex_destructive_match",
    "regex_alignment_match",
    "time_of_day_bucket",
    "session_history_action_share",
    "routing_band",
    "trigger_factor",
    "learn_mode_bias_hint",
)


def _percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    sorted_values = sorted(values)
    rank = (p / 100.0) * (len(sorted_values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = rank - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _action_share(history: Sequence[str]) -> list[float]:
    last_five = list(history)[-5:]
    if not last_five:
        return [0.0] * len(VERDICTS)
    counts = {v: 0 for v in VERDICTS}
    for verdict in last_five:
        if verdict in counts:
            counts[verdict] += 1
    total = float(len(last_five))
    return [counts[v] / total for v in VERDICTS]


def _regex_hit(content: str, patterns: Sequence[re.Pattern[str]]) -> int:
    return 1 if any(p.search(content) for p in patterns) else 0


def extract(
    state: Mapping[str, Any],
    *,
    now_utc: datetime | None = None,
) -> dict[str, float | int | list[float]]:
    """Return the v10 feature vector for a governance state dict.

    The function is pure: same input -> same output. Caller passes
    ``now_utc`` explicitly so the function does no clock reads.

    Expected ``state`` keys (defaults applied if absent):
        content                       : str
        latency_ms_last5              : Sequence[float]
        session_history_actions       : Sequence[str]  (verdicts)
        routing_band                  : int (1..4)
        trigger_factor                : int
        learn_mode_bias_hint          : float
    """
    if now_utc is None:
        now_utc = datetime(1970, 1, 1, tzinfo=timezone.utc)

    content = str(state.get("content", ""))
    latency_window = list(state.get("latency_ms_last5", []) or [])
    history = list(state.get("session_history_actions", []) or [])
    routing_band = int(state.get("routing_band", 0) or 0)
    trigger_factor = int(state.get("trigger_factor", 0) or 0)
    learn_mode_bias_hint = float(state.get("learn_mode_bias_hint", 0.0) or 0.0)

    return {
        "latency_ms_last5_p95": float(_percentile(latency_window, 95.0)),
        "content_length": len(content),
        "regex_destructive_match": _regex_hit(content, _DESTRUCTIVE_PATTERNS),
        "regex_alignment_match": _regex_hit(content, _ALIGNMENT_PATTERNS),
        "time_of_day_bucket": int(now_utc.astimezone(timezone.utc).hour),
        "session_history_action_share": _action_share(history),
        "routing_band": routing_band,
        "trigger_factor": trigger_factor,
        "learn_mode_bias_hint": learn_mode_bias_hint,
    }
