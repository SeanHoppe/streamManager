from __future__ import annotations

import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field, replace
from enum import IntEnum

from stream_manager import message_bus as _msg_bus
from stream_manager.agent_registry import AgentProfile, AgentRegistry
from stream_manager.cli_governance import CliGovernor, is_enabled as _cli_enabled
from stream_manager.decision_graph import DecisionGraph
from stream_manager.hitl import HitlQueue
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
    original_action: str = ""


PROMOTE_AT = 0.75
DEMOTE_AT = 0.40
ROLLING_WINDOW = 10
DEFAULT_RATE_LIMIT_PER_MIN = 10
MIN_INTERVENTIONS_FOR_PROMOTE = 3

# Sources where the engine actually exercised judgment. The "default" branch
# returning ALLOW with confidence 0.1 carries no information about engine
# accuracy and must not contribute to the rolling window.
ELIGIBLE_SOURCES: frozenset[str] = frozenset({"precheck", "graph", "cli"})
INTERVENTION_ACTIONS: frozenset[str] = frozenset({"SUGGEST", "GUIDE", "INTERVENE", "BLOCK"})


def _was_intervention_attempt(decision: GovDecision) -> bool:
    effective = decision.original_action or decision.action
    return effective in INTERVENTION_ACTIONS


# ── Operation classification (FR-AR-6) ────────────────────────────────
#
# Heuristic mapping from message content to operation categories used in
# agent_profiles.yaml. Intentionally simple: regex/substring match. The
# AgentRegistry profile's blocked_ops/restricted_ops are checked against
# this set to decide whether to BLOCK / cap action.

_DESTRUCTIVE_SHELL_RE = re.compile(
    r"\brm\s+-rf\b|\bDROP\s+TABLE\b|\bdd\s+if=|\btruncate\b",
    re.IGNORECASE,
)
_FORCE_PUSH_RE = re.compile(
    r"git\s+push.*(?:--force|-f)\b.*\b(?:main|master|production)\b",
    re.IGNORECASE | re.DOTALL,
)
_CRED_EXFIL_RE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_\-]{16,}|"  # OpenAI-style keys
    r"AKIA[0-9A-Z]{16}|"             # AWS access keys
    r"ghp_[A-Za-z0-9]{20,}|"          # GitHub PAT
    r"xox[baprs]-[A-Za-z0-9\-]{10,})\b",
)
_SHELL_HINT_RE = re.compile(
    r"(?:^|\s)(?:bash|sh|cmd|powershell|pwsh)\s|"
    r"\$\(|`[^`]+`|"
    r"\b(?:ls|cat|grep|find|chmod|chown|kill|systemctl|docker|kubectl|"
    r"npm|pip|pytest|make|cargo|go)\s+",
    re.IGNORECASE,
)
_FILE_WRITE_RE = re.compile(
    r"\b(?:write\s+to|create\s+file|save\s+to|new\s+file)\b",
    re.IGNORECASE,
)
_FILE_EDIT_RE = re.compile(
    r"\b(?:edit|modify|update|patch)\b.*\.[A-Za-z0-9]+",
    re.IGNORECASE,
)
_FILE_READ_RE = re.compile(
    r"\b(?:read|open|show\s+me|cat|view)\b.*\.[A-Za-z0-9]+",
    re.IGNORECASE,
)


def _classify_ops(content: str) -> set[str]:
    """Return the set of operation categories the message content matches."""
    ops: set[str] = set()
    if not content:
        return ops
    if _DESTRUCTIVE_SHELL_RE.search(content):
        ops.add("destructive_shell")
    if _FORCE_PUSH_RE.search(content):
        ops.add("force_push_protected")
    if _CRED_EXFIL_RE.search(content):
        ops.add("credential_exfiltration")
    if _SHELL_HINT_RE.search(content):
        ops.add("shell_command")
        ops.add("tool_execution")
    if _FILE_WRITE_RE.search(content):
        ops.add("file_write")
    if _FILE_EDIT_RE.search(content):
        ops.add("file_edit")
    if _FILE_READ_RE.search(content):
        ops.add("file_read")
    return ops


_ACTION_RANK: dict[str, int] = {
    "ALLOW": 0,
    "OBSERVE": 0,
    "SUGGEST": 1,
    "GUIDE": 2,
    "INTERVENE": 3,
    "BLOCK": 4,
}


def _cap_action(current: str, ceiling: str) -> str:
    """Return whichever of (current, ceiling) is strictly more restrictive.

    The ceiling raises the floor — i.e. if current is less restrictive than
    the ceiling, return ceiling; otherwise keep current.
    """
    cur_rank = _ACTION_RANK.get(current, 0)
    ceil_rank = _ACTION_RANK.get(ceiling, 0)
    return ceiling if ceil_rank > cur_rank else current


@dataclass
class GovernanceEngine:
    project_context: ProjectContextSnapshot
    graph: DecisionGraph = field(default_factory=DecisionGraph)
    mode: Mode = Mode.OBSERVE
    rate_limit_per_min: int = DEFAULT_RATE_LIMIT_PER_MIN

    bus: _msg_bus.MessageBus | None = None
    session_id: str = ""
    registry: AgentRegistry | None = None
    hitl: HitlQueue | None = None

    _eligible_window: deque[bool] = field(default_factory=lambda: deque(maxlen=ROLLING_WINDOW))
    _intervention_window: deque[bool] = field(default_factory=lambda: deque(maxlen=ROLLING_WINDOW))
    _intervention_log: deque[float] = field(default_factory=lambda: deque(maxlen=120))
    _cli_governor: CliGovernor | None = None
    _desktop_pause_active: bool = False

    def signal_desktop_pause(self) -> None:
        """Mark the next evaluate() as following a Desktop end_turn pause.

        FR-HITL-2 trigger 3 primary signal. The flag is consumed (reset to
        False) by `evaluate()` after each call so a single pause only
        triggers once.
        """
        self._desktop_pause_active = True

    def evaluate(self, msg: Message) -> GovDecision:
        bus_msg: _msg_bus.Message | None = None
        if self.bus is not None and self.session_id:
            bus_msg = _msg_bus.Message.new(
                session_id=self.session_id,
                type="governance_eval",
                direction="inbound",
                content=msg.content,
                metadata={"role": msg.role, "msg_id": msg.id},
            )
            self.bus.publish(bus_msg)
        decision = self._evaluate_inner(msg)

        # FR-HITL §4.9: route through the HITL queue if one is wired AND
        # we have a bus message to anchor the pending row to. The
        # classify_trigger pre-check is cheap and avoids a route() call
        # when no trigger fires. The desktop-pause flag is consumed
        # (reset) at the end of evaluate so a single pause only triggers
        # once.
        if self.hitl is not None and bus_msg is not None and self.session_id:
            try:
                trigger = self.hitl.classify_trigger(
                    decision, msg.content, self._desktop_pause_active
                )
            except Exception:
                log.exception("hitl: classify_trigger raised; skipping route")
                trigger = None
            if trigger is not None:
                try:
                    decision = self.hitl.route(
                        decision,
                        bus_msg.id,
                        msg.content,
                        self.session_id,
                        self._desktop_pause_active,
                    )
                except Exception:
                    log.exception("hitl: route raised; using original decision")
        # Always reset the pause flag, whether or not we routed.
        self._desktop_pause_active = False

        if self.bus is not None and bus_msg is not None:
            self.bus.record_decision(
                message_id=bus_msg.id,
                action=decision.action,
                confidence=decision.confidence,
                reasoning=decision.reasoning,
                matched_hash=decision.matched_hash,
            )
        return decision

    def _evaluate_inner(self, msg: Message) -> GovDecision:
        profile: AgentProfile | None = None
        if self.registry is not None and self.session_id:
            profile = self.registry.active_profile(self.session_id)

        # FR-AR-6: blocked_ops are unconditional — short-circuit before any
        # other routing so an agent cannot smuggle a forbidden op past a
        # graph match or default ALLOW.
        if profile is not None:
            ops = _classify_ops(msg.content)
            blocked_hit = ops & set(profile.blocked_ops)
            if blocked_hit:
                return GovDecision(
                    action="BLOCK",
                    confidence=1.0,
                    reasoning=(
                        f"agent_profile {profile.slug} blocks op(s): "
                        f"{', '.join(sorted(blocked_hit))}"
                    ),
                    mode=self.mode,
                    source=f"agent_profile:{profile.slug}",
                )

        decision = self._evaluate_inner_core(msg)

        if profile is not None:
            decision = self._apply_profile_constraints(decision, profile, msg.content)
        return decision

    def _apply_profile_constraints(
        self,
        decision: GovDecision,
        profile: AgentProfile,
        content: str,
    ) -> GovDecision:
        ops = _classify_ops(content)
        changed = False
        new_action = decision.action
        new_reason = decision.reasoning

        # Restricted ops: cap final action at profile.escalate_to.
        restricted_hit = ops & set(profile.restricted_ops)
        if restricted_hit:
            capped = _cap_action(new_action, profile.escalate_to)
            if capped != new_action:
                new_action = capped
                new_reason = (
                    f"agent_profile {profile.slug} restricted op(s) "
                    f"{','.join(sorted(restricted_hit))} -> capped to "
                    f"{profile.escalate_to}; {decision.reasoning}"
                )
                changed = True

        # Confidence floor: if the engine's confidence is below the floor,
        # escalate to at least GUIDE.
        if decision.confidence < profile.confidence_floor:
            floored = _cap_action(new_action, "GUIDE")
            if floored != new_action:
                new_action = floored
                new_reason = (
                    f"agent_profile {profile.slug} confidence_floor "
                    f"{profile.confidence_floor:.2f} (got "
                    f"{decision.confidence:.2f}) -> escalated to GUIDE; "
                    f"{decision.reasoning}"
                )
                changed = True

        if not changed:
            return decision
        return replace(
            decision,
            action=new_action,
            reasoning=new_reason,
            source=f"agent_profile:{profile.slug}",
            original_action=decision.original_action or decision.action,
        )

    def _evaluate_inner_core(self, msg: Message) -> GovDecision:
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

        # FR-HITL-7: inject the most recent HITL notes for this hash
        # (≤50 tokens each, capped at N=5) as a short prefix to the CLI
        # prompt so prior human guidance shapes the next decision.
        cli_content = msg.content
        if self.hitl is not None and match is not None and match.hash:
            try:
                notes = self.hitl.get_active_notes(match.hash)
            except Exception:
                notes = []
            if notes:
                # Cheap string slice: cap to 250 chars total to stay well
                # within the existing 4000-char content budget.
                joined = " | ".join(notes)[:250]
                cli_content = f"[HITL notes: {joined}]\n\n{msg.content}"
        cli_decision = self._maybe_cli_evaluate(cli_content)
        if cli_decision is not None:
            decision = self._apply_mode(
                GovDecision(
                    action=cli_decision.action,
                    confidence=cli_decision.confidence,
                    reasoning=cli_decision.reasoning,
                    mode=self.mode,
                    source="cli",
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
            elif decision.action in {"INTERVENE", "BLOCK"}:
                self._intervention_log.append(time.time())
            return decision

        return GovDecision(
            action="ALLOW",
            confidence=0.1,
            reasoning="default allow (no rules / no graph match)",
            mode=self.mode,
            source="default",
        )

    def _maybe_cli_evaluate(self, content: str):
        if not _cli_enabled():
            return None
        if self._cli_governor is None:
            self._cli_governor = CliGovernor(self.project_context)
        return self._cli_governor.evaluate(content)

    def _apply_mode(self, decision: GovDecision) -> GovDecision:
        if self.mode == Mode.OBSERVE:
            return replace(
                decision,
                action="ALLOW",
                reasoning=f"observed: {decision.reasoning}",
                original_action=decision.action,
            )
        if self.mode == Mode.SUGGEST and decision.action in {"INTERVENE", "BLOCK"}:
            return replace(
                decision,
                action="SUGGEST",
                reasoning=f"suggested: {decision.reasoning}",
                original_action=decision.action,
            )
        if self.mode == Mode.GUIDE and decision.action == "BLOCK":
            return replace(
                decision,
                action="GUIDE",
                reasoning=f"guided: {decision.reasoning}",
                original_action=decision.action,
            )
        if self.mode == Mode.INTERVENE and decision.action == "BLOCK":
            return replace(
                decision,
                action="INTERVENE",
                reasoning=f"intervened: {decision.reasoning}",
                original_action=decision.action,
            )
        return decision

    def _rate_limited(self) -> bool:
        cutoff = time.time() - 60.0
        recent = sum(1 for t in self._intervention_log if t > cutoff)
        return recent >= self.rate_limit_per_min

    def feedback(self, decision: GovDecision, was_correct: bool) -> None:
        # Eligibility: only decisions where the engine actually exercised
        # judgment count toward the rolling accuracy window. The default-allow
        # branch carries no signal and would otherwise let routine ALLOW-only
        # traffic ramp the mode ladder all the way to BLOCK (the bug fixed
        # by hardening item #2).
        if decision.source in ELIGIBLE_SOURCES:
            self._eligible_window.append(was_correct)
            self._intervention_window.append(_was_intervention_attempt(decision))
        if decision.matched_hash:
            self.graph.feedback(decision.matched_hash, was_correct)
        self._update_mode()

    def observe_for_learning(self, msg: Message, success: bool) -> None:
        self.graph.observe(msg.content, success)

    def _update_mode(self) -> None:
        if len(self._eligible_window) < ROLLING_WINDOW:
            return
        accuracy = sum(self._eligible_window) / len(self._eligible_window)
        intervention_count = sum(self._intervention_window)

        can_promote = (
            accuracy >= PROMOTE_AT
            and int(self.mode) < int(Mode.BLOCK)
            and intervention_count >= MIN_INTERVENTIONS_FOR_PROMOTE
        )
        if can_promote:
            self.mode = Mode(int(self.mode) + 1)
            log.info(
                "mode promoted to %s (acc=%.2f, interventions_in_window=%d)",
                self.mode.name,
                accuracy,
                intervention_count,
            )
        elif accuracy <= DEMOTE_AT and int(self.mode) > int(Mode.OBSERVE):
            self.mode = Mode(int(self.mode) - 1)
            log.info("mode demoted to %s (acc=%.2f)", self.mode.name, accuracy)

    def stats(self) -> dict[str, object]:
        cutoff = time.time() - 60.0
        return {
            "mode": self.mode.name,
            "graph": self.graph.stats(),
            "eligible_decisions_in_window": len(self._eligible_window),
            "eligible_accuracy": (
                sum(self._eligible_window) / len(self._eligible_window)
                if self._eligible_window
                else 0.0
            ),
            "interventions_in_window": sum(self._intervention_window),
            "interventions_last_min": sum(1 for t in self._intervention_log if t > cutoff),
        }
