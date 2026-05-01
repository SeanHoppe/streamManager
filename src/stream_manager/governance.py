from __future__ import annotations

import logging
from dataclasses import dataclass

from stream_manager.message_bus import Message, MessageBus

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GovDecision:
    action: str
    confidence: float
    reasoning: str
    matched_hash: str = ""


class NoOpGovernance:
    """Spike A placeholder. Always ALLOW. Records every evaluation to the bus."""

    def __init__(self, bus: MessageBus | None = None) -> None:
        self.bus = bus
        self.eval_count = 0

    def evaluate(self, msg: Message) -> GovDecision:
        self.eval_count += 1
        decision = GovDecision(
            action="ALLOW",
            confidence=0.0,
            reasoning="noop",
        )
        if self.bus is not None:
            self.bus.record_decision(
                message_id=msg.id,
                action=decision.action,
                confidence=decision.confidence,
                reasoning=decision.reasoning,
                matched_hash=decision.matched_hash,
            )
        log.debug("evaluate %s seq=%d -> %s", msg.id, msg.sequence, decision.action)
        return decision
