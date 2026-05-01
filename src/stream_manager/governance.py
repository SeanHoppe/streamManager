from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum

from stream_manager.decision_graph import DecisionGraph
from stream_manager.messages import Message
from stream_manager.project_context import ProjectContextSnapshot, fast_precheck

log = logging.getLogger(__name__)


class Mode(IntEnum):
    OBSERVE = 0
    SUGGEST = 1
    GUIDE = 2
    INTERVENE = 3
    BLOCK = 4


@dataclass(frozen=True)
class GovDecision:
    action: str
    confidence: float
    reasoning: str
    mode: Mode
    matched_hash: str = ""
    source: str = ""


PROMOTE_AT = 0.75
DEMOTE_AT = 0.40
ROLLING_WINDOW = 10
DEFAULT_RATE_LIMIT_PER_MIN = 10


@dataclass
class GovernanceEngine:
    project_context: ProjectContextSnapshot
    graph: DecisionGraph = field(default_factory=DecisionGraph)
    mode: Mode = Mode.OBSERVE
    rate_limit_per_min: int = DEFAULT_RATE_LIMIT_PER_MIN

    _accuracy_window: deque[bool] = field(default_factory=lambda: deque(maxlen=ROLLING_WINDOW))
    _intervention_log: deque[float] = field(default_factory=lambda: deque(maxlen=120))

    def evaluate(self, msg: Message) -> GovDecision:
        pre = fast_precheck(msg.content, self.project_context)
        if pre is not None:
            decision = self._apply_mode(
                GovDecision(
                    action=pre.action,
                    confidence=0.95,
                    reasoning=pre.reasoning,
                    mode=self.mode,
                    source="precheck",
                )
            )
            if decision.action in {"INTERVENE", "BLOCK"} and self._rate_limited():
                decision = GovDecision(
                    action="ALLOW",
                    confidence=0.5,
                    reasoning=f"rate-limited intervention ({decision.reasoning})",
                    mode=self.mode,
                    source="rate_limit",
                )
            else:
                if decision.action in {"INTERVENE", "BLOCK"}:
                    self._intervention_log.append(time.time())
            return decision

        match = self.graph.match(msg.content)
        if match is not None and match.success_rate >= 0.55:
            return GovDecision(
                action="ALLOW",
                confidence=match.success_rate,
                reasoning=f"matched L{int(match.level)} (succ={match.success_rate:.2f}, n={match.occurrences})",
                mode=self.mode,
                matched_hash=match.hash,
                source="graph",
            )

        return GovDecision(
            action="ALLOW",
            confidence=0.1,
            reasoning="default allow (no rules / no graph match)",
            mode=self.mode,
            source="default",
        )

    def _apply_mode(self, decision: GovDecision) -> GovDecision:
        if self.mode == Mode.OBSERVE:
            return _replace(decision, action="ALLOW", reasoning=f"observed: {decision.reasoning}")
        if self.mode == Mode.SUGGEST and decision.action in {"INTERVENE", "BLOCK"}:
            return _replace(decision, action="SUGGEST", reasoning=f"suggested: {decision.reasoning}")
        if self.mode == Mode.GUIDE and decision.action == "BLOCK":
            return _replace(decision, action="GUIDE", reasoning=f"guided: {decision.reasoning}")
        if self.mode == Mode.INTERVENE and decision.action == "BLOCK":
            return _replace(decision, action="INTERVENE", reasoning=f"intervened: {decision.reasoning}")
        return decision

    def _rate_limited(self) -> bool:
        cutoff = time.time() - 60.0
        recent = sum(1 for t in self._intervention_log if t > cutoff)
        return recent >= self.rate_limit_per_min

    def feedback(self, decision: GovDecision, was_correct: bool) -> None:
        self._accuracy_window.append(was_correct)
        if decision.matched_hash:
            self.graph.feedback(decision.matched_hash, was_correct)
        self._update_mode()

    def observe_for_learning(self, msg: Message, success: bool) -> None:
        self.graph.observe(msg.content, success)

    def _update_mode(self) -> None:
        if len(self._accuracy_window) < ROLLING_WINDOW:
            return
        accuracy = sum(self._accuracy_window) / len(self._accuracy_window)
        if accuracy >= PROMOTE_AT and int(self.mode) < int(Mode.BLOCK):
            self.mode = Mode(int(self.mode) + 1)
            log.info("mode promoted to %s (accuracy=%.2f)", self.mode.name, accuracy)
        elif accuracy <= DEMOTE_AT and int(self.mode) > int(Mode.OBSERVE):
            self.mode = Mode(int(self.mode) - 1)
            log.info("mode demoted to %s (accuracy=%.2f)", self.mode.name, accuracy)

    def stats(self) -> dict[str, object]:
        cutoff = time.time() - 60.0
        return {
            "mode": self.mode.name,
            "graph": self.graph.stats(),
            "accuracy": (
                sum(self._accuracy_window) / len(self._accuracy_window)
                if self._accuracy_window
                else 0.0
            ),
            "interventions_last_min": sum(1 for t in self._intervention_log if t > cutoff),
        }


def _replace(d: GovDecision, **kwargs: object) -> GovDecision:
    return GovDecision(
        action=str(kwargs.get("action", d.action)),
        confidence=float(kwargs.get("confidence", d.confidence)),
        reasoning=str(kwargs.get("reasoning", d.reasoning)),
        mode=d.mode,
        matched_hash=d.matched_hash,
        source=d.source,
    )
