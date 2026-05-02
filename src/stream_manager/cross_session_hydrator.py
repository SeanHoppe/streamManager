"""Cross-session pattern hydration (Task F).

Reference: docs/sync-comms-qa.md Q3 + OQ5/OQ6/OQ8 locks.

Operator-approved cross_session=1 patterns are injected into other engines'
DecisionGraph at L1 advisory level. Local re-validation gates (PROMOTE_AT,
MIN_INTERVENTIONS_FOR_PROMOTE) still apply — the hydrator does NOT seed
local occurrence counts. A receiving engine cannot promote an inherited
L1 pattern to L2 without local evidence.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from stream_manager.decision_graph import FEATURE_DIM, Pattern, PatternLevel

if TYPE_CHECKING:
    from stream_manager.governance import GovernanceEngine
    from stream_manager.message_bus import MessageBus

log = logging.getLogger(__name__)


class Hydrator(threading.Thread):
    """Inject bus.cross_session=1 patterns into a target engine at L1.

    Idempotent: if the engine.graph already has the hash at any level,
    the hydrator leaves it alone — never downgrades a locally-promoted
    pattern. New rows are inserted as L1 advisory with zero local
    occurrences so promotion gates fire only on local re-validation.
    """

    def __init__(self, engine: GovernanceEngine, bus: MessageBus) -> None:
        super().__init__(daemon=True, name="cross-session-hydrator")
        self.engine = engine
        self.bus = bus

    def run(self) -> None:
        try:
            self._inject_all()
        finally:
            try:
                self.engine.hydrated = True
            except Exception:
                log.exception("hydrator: setting engine.hydrated raised")

    def _inject_all(self) -> int:
        try:
            rows = self.bus.get_cross_session_patterns()
        except Exception:
            log.exception("hydrator: get_cross_session_patterns failed")
            return 0
        injected = 0
        graph = self.engine.graph
        for row in rows:
            h = str(row.get("hash") or "")
            if not h:
                continue
            if h in graph.patterns:
                # Idempotent: never downgrade a locally-known pattern.
                continue
            payload = str(row.get("payload") or "")
            graph.patterns[h] = Pattern(
                hash=h,
                level=PatternLevel.L1,
                vector=[0.0] * FEATURE_DIM,
                canonical_text=payload[:200],
                occurrences=0,
                successes=0,
                last_seen=float(row.get("last_seen") or time.time()),
            )
            injected += 1
        return injected


def hydrate_now(engine: GovernanceEngine, bus: MessageBus) -> int:
    """Synchronous one-shot hydration. Returns number of newly-injected rows.

    Used by EngineRegistry.refresh_all() and by tests that want to drive
    the hydrator without spawning a thread.
    """
    h = Hydrator(engine, bus)
    n = h._inject_all()
    try:
        engine.hydrated = True
    except Exception:
        log.exception("hydrate_now: setting engine.hydrated raised")
    return n
