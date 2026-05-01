# Phase 4 — Model Routing

**Sequence:** Can be implemented after Phase 2; parallel-safe with Phase 3.
**Estimated time:** 1 session.
**FR refs:** §5.6 NFR-M1 through NFR-M5, ADR-10.

**Dependency:** Phase 1 must be complete (agent registry is the primary
caller of `GovernanceEngine.evaluate()` in role-scoped paths). Phase 4 does
not depend on Phase 2 or Phase 3 — it can be done in parallel with Phase 3.

---

## Context

Every LLM call currently goes through a single CLI subprocess path at
the same model tier. There is no cost differentiation based on decision
complexity. The NFR-M spec defines 5 layers:

| Layer | Trigger | Model |
|-------|---------|-------|
| L0 | Regex / static rule match (precheck) | No LLM |
| L1 | Graph hash match, confidence ≥ 0.85 | No LLM |
| L2 | Graph hash match, confidence 0.60–0.84 | Haiku |
| L3 | No graph match; pattern inference | Haiku |
| L4 | FR-OG alignment; ambiguous BLOCK; HITL note synthesis | Sonnet (minimum) |

Model IDs (from env vars, with sensible defaults):
- `BRIDGE_L2_MODEL` default: `claude-haiku-4-5-20251001`
- `BRIDGE_L4_MODEL` default: `claude-sonnet-4-6`

NFR-M4 convergence alert: if L4 calls exceed 20% of total calls in any
5-minute rolling window, emit `nfr_model_routing_alert` bus event.

---

## Deliverables

### New files

| File | Purpose |
|------|---------|
| `src/stream_manager/model_router.py` | `route()` function; `ModelLayer` enum; convergence counter |

### Modified files

| File | Changes |
|------|---------|
| `src/stream_manager/governance.py` | Replace single CLI call with routed dispatch; log `model_used` + `layer` |
| `src/stream_manager/message_bus.py` | Add `model_used` + `layer` columns to `decisions` table |
| `src/stream_manager/cli_governance.py` | Accept `model_id` parameter and pass `--model` flag to subprocess |
| `dashboard/server.py` | `GET /api/decisions` response includes `model_used` + `layer` |

---

## Prompt

```
Implement Phase 4 of the StreamManager viable product roadmap.
Reference: REQUIREMENTS.md §5.6 NFR-M1–M5, ADR-10.
Phase 1 (agent_registry.py) must already exist.

### 1. model_router.py

Create src/stream_manager/model_router.py:

import os
from enum import IntEnum
from dataclasses import dataclass

class ModelLayer(IntEnum):
    L0 = 0   # no LLM
    L1 = 1   # no LLM
    L2 = 2   # haiku
    L3 = 3   # haiku
    L4 = 4   # sonnet minimum

@dataclass(frozen=True)
class RoutingDecision:
    layer: ModelLayer
    model_id: str | None   # None for L0/L1

L2_MODEL_DEFAULT = "claude-haiku-4-5-20251001"
L4_MODEL_DEFAULT = "claude-sonnet-4-6"

def get_l2_model() -> str:
    return os.environ.get("BRIDGE_L2_MODEL", L2_MODEL_DEFAULT)

def get_l4_model() -> str:
    return os.environ.get("BRIDGE_L4_MODEL", L4_MODEL_DEFAULT)

def route(source: str, confidence: float, requires_alignment: bool = False,
          is_ambiguous_block: bool = False, is_hitl_synthesis: bool = False
          ) -> RoutingDecision:
    """
    Classify decision into routing layer.

    source values: "precheck" | "graph" | "cli" | "default" | "agent_profile:*"
    requires_alignment: True when FR-OG-7 alignment check is needed
    is_ambiguous_block: True when action is BLOCK but confidence < 0.85
    is_hitl_synthesis: True when generating HITL note context
    """
    # L4: alignment, ambiguous block, HITL synthesis
    if requires_alignment or is_ambiguous_block or is_hitl_synthesis:
        return RoutingDecision(ModelLayer.L4, get_l4_model())

    # L0: precheck (regex) or agent_profile rule (no LLM needed)
    if source in ("precheck", "agent_profile") or source.startswith("agent_profile:"):
        return RoutingDecision(ModelLayer.L0, None)

    # L1: high-confidence graph match
    if source == "graph" and confidence >= 0.85:
        return RoutingDecision(ModelLayer.L1, None)

    # L2: moderate-confidence graph match
    if source == "graph" and confidence >= 0.60:
        return RoutingDecision(ModelLayer.L2, get_l2_model())

    # L3: no graph match, pattern inference (source == "default" or "cli")
    return RoutingDecision(ModelLayer.L3, get_l2_model())


class ConvergenceMonitor:
    """Tracks L4 call rate in a 5-minute rolling window (NFR-M4)."""
    WINDOW_SECONDS = 300
    ALERT_THRESHOLD = 0.20

    def __init__(self):
        self._timestamps: list[float] = []   # all call timestamps
        self._l4_timestamps: list[float] = []

    def record(self, layer: ModelLayer) -> bool:
        """Record a call. Returns True if convergence alert should fire."""
        import time
        now = time.time()
        cutoff = now - self.WINDOW_SECONDS
        self._timestamps = [t for t in self._timestamps if t >= cutoff]
        self._l4_timestamps = [t for t in self._l4_timestamps if t >= cutoff]
        self._timestamps.append(now)
        if layer == ModelLayer.L4:
            self._l4_timestamps.append(now)
        total = len(self._timestamps)
        if total < 5:
            return False   # not enough data
        rate = len(self._l4_timestamps) / total
        return rate > self.ALERT_THRESHOLD

### 2. WAL schema — decisions table additions

In message_bus.py _SCHEMA, modify decisions table to add columns.
Because SQLite cannot ALTER TABLE to add columns with constraints,
use IF NOT EXISTS migration pattern in MessageBus.__init__:

    # Run after schema creation:
    for col, definition in [
        ("model_used", "TEXT NOT NULL DEFAULT ''"),
        ("layer",      "INTEGER NOT NULL DEFAULT 0"),
    ]:
        try:
            conn.execute(f"ALTER TABLE decisions ADD COLUMN {col} {definition}")
        except sqlite3.OperationalError:
            pass   # column already exists

Update MessageBus.record_decision() signature:
    def record_decision(self, message_id: str, action: str, confidence: float,
                        reasoning: str, matched_hash: str = "",
                        model_used: str = "", layer: int = 0) -> str:

### 3. Wire model_router into GovernanceEngine

In governance.py _evaluate_inner():

    After computing initial decision (from precheck / graph / cli / default):
        routing = route(
            source=decision.source,
            confidence=decision.confidence,
            is_ambiguous_block=(decision.action == "BLOCK" and decision.confidence < 0.85),
        )
        # If L2 or L3 and we would have called CLI anyway, pass model_id to CLI governor
        # If L4, call CLI governor with L4 model
        # If L0 or L1, skip CLI call entirely (decision already made)

    Store routing.layer and routing.model_id on decision for logging.

In cli_governance.py (CliGovernor or equivalent):
    Accept optional model_id: str | None parameter in evaluate() / call().
    If model_id is not None, add --model {model_id} to the subprocess args.
    If model_id is None, use the existing default (no --model flag).

In governance.py evaluate() (outer method), after record_decision():
    should_alert = self._convergence.record(routing.layer)
    if should_alert and self.bus is not None:
        self.bus.publish(Message.new(
            session_id=self.session_id,
            type="nfr_model_routing_alert",
            direction="internal",
            content=f"L4 rate exceeded 20% threshold in 5-minute window",
            metadata={"layer": int(routing.layer)},
        ))

Add to GovernanceEngine dataclass:
    _convergence: ConvergenceMonitor = field(default_factory=ConvergenceMonitor)

### 4. Dashboard: model/layer column

In dashboard/server.py, update GET /api/decisions response to include
model_used and layer fields from the decisions table.

In dashboard/static/index.html, add "Layer" column to decisions table:
    Show layer as badge: L0 (gray) | L1 (blue) | L2 (teal) | L3 (yellow) | L4 (orange/red)
    Tooltip on hover: model_used value (or "no LLM" for L0/L1)

### 5. Tests

Add tests/test_model_router.py covering:
    - route("precheck", 0.95) returns L0, model_id=None
    - route("graph", 0.90) returns L1, model_id=None
    - route("graph", 0.70) returns L2, model_id=haiku
    - route("default", 0.10) returns L3, model_id=haiku
    - route("cli", 0.50, requires_alignment=True) returns L4, model_id=sonnet
    - route("graph", 0.50, is_ambiguous_block=True) returns L4, model_id=sonnet
    - ConvergenceMonitor.record() returns False below threshold
    - ConvergenceMonitor.record() returns True when >20% L4 in window

    Also: BRIDGE_L2_MODEL env var override is picked up by get_l2_model()
          BRIDGE_L4_MODEL env var override is picked up by get_l4_model()

Run: pytest tests/test_model_router.py -v
All tests must pass.
```

---

## STOP + VERIFY

Before marking Phase 4 complete, confirm **all** of the following:

**model_router.py**
- [ ] File exists at `src/stream_manager/model_router.py`
- [ ] `ModelLayer` enum has L0–L4
- [ ] `route()` L0 path: precheck + agent_profile sources → no LLM
- [ ] `route()` L1 path: graph match ≥ 0.85 → no LLM
- [ ] `route()` L2 path: graph match 0.60–0.84 → haiku
- [ ] `route()` L3 path: default / no match → haiku
- [ ] `route()` L4 path: alignment / ambiguous BLOCK / HITL synthesis → sonnet
- [ ] `BRIDGE_L2_MODEL` env var respected; default is `claude-haiku-4-5-20251001`
- [ ] `BRIDGE_L4_MODEL` env var respected; default is `claude-sonnet-4-6`
- [ ] `ConvergenceMonitor` uses 5-minute rolling window
- [ ] Alert fires when L4 rate > 20% (not ≥ 20%)
- [ ] Alert suppressed when total call count < 5

**WAL schema**
- [ ] `model_used` + `layer` columns on `decisions` table
- [ ] Migration is additive (uses `ALTER TABLE ... ADD COLUMN` with try/except)
- [ ] `record_decision()` accepts `model_used` + `layer` params

**governance.py**
- [ ] `_convergence: ConvergenceMonitor` field on `GovernanceEngine`
- [ ] `nfr_model_routing_alert` bus event emitted when convergence alert fires
- [ ] `--model` flag passed to CLI subprocess when model_id is not None
- [ ] L0/L1 decisions skip CLI call entirely (no subprocess spawned)

**dashboard**
- [ ] `GET /api/decisions` includes `model_used` + `layer` in response
- [ ] "Layer" column in decisions table with L0–L4 badges
- [ ] Tooltip shows model name on hover

**tests**
- [ ] `tests/test_model_router.py` exists with all 10 test cases
- [ ] `pytest tests/test_model_router.py -v` passes
- [ ] `ruff check src/` passes
- [ ] `mypy src/stream_manager/` passes (or pre-existing only)

**If any check fails:** fix before marking Phase 4 done.

---

## Definition of Done

`GovernanceEngine` routes L0/L1 decisions with no LLM call, L2/L3 to Haiku,
and L4 to Sonnet. Model and layer are logged per decision. Cost convergence
is monitored and alerted via the bus. BRIDGE_L* env vars allow runtime override.

Commit message:
```
feat(model-routing): §5.6 NFR-M1–M5 — L0–L4 dispatch, Haiku/Sonnet tiers, convergence monitor
```
