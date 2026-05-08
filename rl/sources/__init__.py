"""v10 P2 — corpus source adapters.

Each adapter exposes ``iter_episodes(...)`` yielding :class:`Episode`
matching the v10 schema in ``rl/schema.sql`` field-for-field. Adapters
are READ-ONLY over their underlying artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


VALID_VERDICTS: tuple[str, ...] = (
    "ALLOW", "SUGGEST", "INTERVENE", "BLOCK", "AMBIGUOUS",
)
VALID_SOURCES: tuple[str, ...] = (
    "soak", "cassette", "probe", "golden", "review", "live",
)


@dataclass
class Episode:
    """In-memory v10 episode record. Field semantics match rl/schema.sql."""

    ts_utc: str
    session_id: str
    trace_id: str
    state_features: dict
    action_taken: float
    action_propensity: float
    verdict: str
    confidence: float
    latency_ms: float
    budget_violation: int
    source: str
    cycle_tag: Optional[str] = None
    hitl_override: Optional[int] = None
    fr_og_7_pass: Optional[int] = None
    provenance: dict = field(default_factory=dict)
