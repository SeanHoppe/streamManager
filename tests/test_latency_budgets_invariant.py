"""Drift-guard: BRIDGE_FALLBACK_LATENCY_BUDGET_MS locked to TIMEOUT_SECONDS."""

from __future__ import annotations

import math

from stream_manager.cli_governance import TIMEOUT_SECONDS
from stream_manager.latency_budgets import BRIDGE_FALLBACK_LATENCY_BUDGET_MS


def test_bridge_fallback_budget_matches_formula() -> None:
    expected = int(math.ceil(TIMEOUT_SECONDS * 1.4 / 5.0) * 5_000)
    assert BRIDGE_FALLBACK_LATENCY_BUDGET_MS == expected
