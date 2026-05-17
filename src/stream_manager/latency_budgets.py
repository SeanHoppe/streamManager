"""Latency budgets consumed by governance-bridge regression tests.

Single source of truth for any threshold a test pins to a "live"
constant. Re-baselining ADR-5 means editing this file only.

Lives outside the ADR-18-FROZEN modules (governance.py, model_router.py,
cli_governance.py, message_bus.py) so the constant can be re-baselined
without touching a frozen surface.
"""

# Bridge forward latency must stay below this even when the CLI
# governance API times out. Value = cli_governance.TIMEOUT_SECONDS
# (25.0) * 1.4 rounded up to the nearest 5_000 ms, giving headroom
# for the timeout + fallback path + downstream forward step.
BRIDGE_FALLBACK_LATENCY_BUDGET_MS = 35_000
