"""Model router — classifies governance decisions into routing layers (NFR-M1-M5).

Every governance decision is mapped to one of five layers (L0-L4) based on
its source, confidence, and special flags (alignment / ambiguous BLOCK / HITL
synthesis). The layer determines the model used:

  L0 (no LLM) — precheck regex match or agent_profile rule
  L1 (no LLM) — graph hash match, confidence >= 0.85
  L2 (Haiku) — graph hash match, confidence 0.60-0.84
  L3 (Haiku) — no graph match; pattern inference (default / cli)
  L4 (Sonnet) — FR-OG-7 alignment / ambiguous BLOCK / HITL note synthesis

Model IDs are env-var overridable:
  BRIDGE_L2_MODEL  default: claude-haiku-4-5-20251001
  BRIDGE_L4_MODEL  default: claude-sonnet-4-6

NFR-M4 convergence alert: when the L4 share of all calls exceeds 20% within a
5-minute rolling window (and total >= 5), `ConvergenceMonitor.record()`
returns True so the engine can emit `nfr_model_routing_alert` on the bus.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import IntEnum


class ModelLayer(IntEnum):
    L0 = 0  # no LLM
    L1 = 1  # no LLM
    L2 = 2  # haiku
    L3 = 3  # haiku
    L4 = 4  # sonnet (minimum)


@dataclass(frozen=True)
class RoutingDecision:
    layer: ModelLayer
    model_id: str | None  # None for L0/L1
    # v1.7 P2 Haiku fastpath: when set, the engine retries the L4 call on
    # `fallback_model_id` if the primary call's confidence drops below
    # BRIDGE_L4_FALLBACK_CONFIDENCE (default 0.70). None for v1.6 callers
    # and for the FR-OG-7 alignment sub-band (Sonnet-only, no fallback).
    fallback_model_id: str | None = None


L2_MODEL_DEFAULT = "claude-haiku-4-5-20251001"
L4_MODEL_DEFAULT = "claude-sonnet-4-6"


def get_l2_model() -> str:
    return os.environ.get("BRIDGE_L2_MODEL", L2_MODEL_DEFAULT)


def get_l4_model() -> str:
    return os.environ.get("BRIDGE_L4_MODEL", L4_MODEL_DEFAULT)


def route(
    source: str,
    confidence: float,
    requires_alignment: bool = False,
    is_ambiguous_block: bool = False,
    is_hitl_synthesis: bool = False,
) -> RoutingDecision:
    """Classify a governance decision into its routing layer.

    Priority order is non-negotiable:
      1. L4 — alignment / ambiguous BLOCK / HITL synthesis (Sonnet or Haiku-fastpath)
      2. L0 — precheck or agent_profile source (no LLM)
      3. L1 — graph match >= 0.85 (no LLM)
      4. L2 — graph match 0.60-0.84 (Haiku)
      5. L3 — fallback / pattern inference (Haiku)

    L4 sub-band (v1.7 P2 Haiku fastpath):
      - requires_alignment      → Sonnet only, no fallback (FR-OG-7 protected)
      - is_ambiguous_block      → Haiku-first with Sonnet fallback
      - is_hitl_synthesis       → Haiku-first with Sonnet fallback
      Priority within the sub-band: requires_alignment beats the other two.

    Args:
        source: one of "precheck" | "graph" | "cli" | "default" |
            "agent_profile" | "agent_profile:<slug>" | "rate_limit"
        confidence: decision confidence in [0.0, 1.0]
        requires_alignment: True when an FR-OG-7 alignment check is needed.
        is_ambiguous_block: True when action is BLOCK and confidence < 0.85.
        is_hitl_synthesis: True when generating HITL note context.
    """
    # L4: alignment / ambiguous block / HITL synthesis
    if requires_alignment:
        # FR-OG-7 protected — Sonnet only, never fall back to Haiku.
        return RoutingDecision(ModelLayer.L4, get_l4_model())
    if is_ambiguous_block or is_hitl_synthesis:
        # Haiku fastpath with Sonnet fallback. Engine retries on
        # fallback_model_id when primary confidence < BRIDGE_L4_FALLBACK_CONFIDENCE.
        return RoutingDecision(
            ModelLayer.L4,
            get_l2_model(),
            fallback_model_id=get_l4_model(),
        )

    # L0: precheck or agent_profile rule (no LLM needed)
    if source in ("precheck", "agent_profile") or source.startswith("agent_profile:"):
        return RoutingDecision(ModelLayer.L0, None)

    # L1: high-confidence graph match
    if source == "graph" and confidence >= 0.85:
        return RoutingDecision(ModelLayer.L1, None)

    # L2: moderate-confidence graph match
    if source == "graph" and confidence >= 0.60:
        return RoutingDecision(ModelLayer.L2, get_l2_model())

    # L3: default / cli / no match — pattern inference via Haiku
    return RoutingDecision(ModelLayer.L3, get_l2_model())


@dataclass
class ConvergenceMonitor:
    """Tracks L4 call rate within a 5-minute rolling window (NFR-M4).

    Alert fires (record() returns True) when:
      - total calls in window >= 5, AND
      - L4 share of total > 0.20 (strict greater-than)
    """

    WINDOW_SECONDS: float = 300.0
    ALERT_THRESHOLD: float = 0.20

    _timestamps: list[float] = field(default_factory=list)
    _l4_timestamps: list[float] = field(default_factory=list)

    def record(self, layer: ModelLayer) -> bool:
        """Record a routing-layer call; return True iff a convergence alert fires."""
        now = time.time()
        cutoff = now - self.WINDOW_SECONDS
        self._timestamps = [t for t in self._timestamps if t >= cutoff]
        self._l4_timestamps = [t for t in self._l4_timestamps if t >= cutoff]
        self._timestamps.append(now)
        if layer == ModelLayer.L4:
            self._l4_timestamps.append(now)
        total = len(self._timestamps)
        if total < 5:
            return False  # insufficient data
        rate = len(self._l4_timestamps) / total
        return rate > self.ALERT_THRESHOLD
