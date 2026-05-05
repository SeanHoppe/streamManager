from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import IntEnum

from stream_manager import message_bus as _msg_bus
from stream_manager.agent_registry import AgentProfile, AgentRegistry
from stream_manager.cli_governance import CliGovernor
from stream_manager.cli_governance import is_enabled as _cli_enabled
from stream_manager.decision_graph import DecisionGraph
from stream_manager.hitl import PAUSE_PATTERNS, HitlQueue
from stream_manager.learn_categorizer import BiasHint, bias_for
from stream_manager.maturity_reader import MaturityReader
from stream_manager.messages import Message
from stream_manager.model_router import (
    ConvergenceMonitor,
    ModelLayer,
    RoutingDecision,
    get_l2_model,
    route,
)
from stream_manager.project_context import (
    EVAL_EXEC_INJECTION_RE,
    ProjectContextSnapshot,
    fast_precheck,
)

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


# Phase 4 follow-up / NFR-M2: keywords that mark a message as an
# "alignment-requiring action" — i.e. a release/merge/deploy or an action
# in oversight/ paths. When this fires AND maturity is active AND FR-OG-7
# would consider the message, the pre-routing pass classifies the call as
# L4 so the CLI subprocess runs against Sonnet (BRIDGE_L4_MODEL) instead
# of Haiku. Heuristic only — substring match, no NLP.
_ALIGNMENT_KEYWORDS: tuple[str, ...] = ("release", "merge", "deploy", "oversight/")


def _looks_alignment_action(content: str) -> bool:
    """True if message content appears to be an alignment-requiring action."""
    if not content:
        return False
    lowered = content.lower()
    return any(kw in lowered for kw in _ALIGNMENT_KEYWORDS)


# v1.8 P1: ambiguous-BLOCK heuristic — destructive intent that did NOT
# trigger the strict `project_context._DESTRUCTIVE` patterns at fast_precheck
# (which require, e.g., `rm -rf /` with anchored root, `git push --force`
# to a *protected* branch, or `DROP DATABASE/TABLE`). When precheck misses
# but content carries destructive signal, the pre-routing site sets
# `is_ambiguous_block=True` so `model_router.route()` places the call on
# the L4 Haiku-fastpath sub-band: Haiku primary with Sonnet fallback on
# low-confidence retry. Single source of truth — referenced once at the
# pre-routing call site in `_evaluate_inner_core`.
_AMBIGUOUS_BLOCK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\brm\s+-rf\b"),
    re.compile(r"\bgit\s+push\s+(?:--force|-f)\b"),
    re.compile(r"\bDROP\s+(?:DATABASE|TABLE|SCHEMA)\b", re.IGNORECASE),
    re.compile(r"\bTRUNCATE\s+(?:TABLE\s+)?\w+", re.IGNORECASE),
    re.compile(r"\bDELETE\s+FROM\s+\w+", re.IGNORECASE),
    re.compile(r"\bchmod\s+777\b"),
    re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"),
    re.compile(r"\bshutdown\s+(?:-[hr]\b|now\b)", re.IGNORECASE),
    re.compile(r"\bmkfs(?:\.\w+)?\b"),
    re.compile(r"\bdd\s+if=.*\bof="),
)


def _looks_ambiguous_block(content: str) -> bool:
    """v1.8 P1: True when content carries destructive-action signal that
    did not strict-match the precheck patterns. Activates the L4
    Haiku-fastpath sub-band so escalation cost stays bounded.
    """
    if not content:
        return False
    for pat in _AMBIGUOUS_BLOCK_PATTERNS:
        if pat.search(content):
            return True
    return False


def _looks_hitl_synthesis(
    content: str,
    hitl: HitlQueue | None,
    desktop_pause_active: bool,
) -> bool:
    """v1.8 P1: pre-routing proxy for HITL synthesis context.

    Returns True when HITL is wired AND a pre-decision signal indicates
    `HitlQueue.classify_trigger` would fire DESKTOP_PAUSE: either the
    engine has been signaled by a Desktop end_turn pause, or content
    matches the same `PAUSE_PATTERNS` regex used by classify_trigger.

    NEW_PATTERN and LOW_CONFIDENCE triggers require a completed decision
    (source / confidence) and are intentionally not reflected here.
    """
    if hitl is None:
        return False
    if desktop_pause_active:
        return True
    if not content:
        return False
    return bool(PAUSE_PATTERNS.search(content))


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
    # Phase 5 / FR-OG-7: optional MaturityReader. When None, all FR-OG-7
    # signals are dormant (gate condition).
    maturity: MaturityReader | None = None
    # Task J / v1.1: optional CLI warm-pool. When supplied, the lazily-built
    # CliGovernor inherits this pool and routes escalation through it
    # instead of spawning a fresh subprocess per call. None = legacy path.
    cli_pool: object | None = None
    _sweep_job_agents_seen: list[str] = field(default_factory=list)

    _eligible_window: deque[bool] = field(default_factory=lambda: deque(maxlen=ROLLING_WINDOW))
    _intervention_window: deque[bool] = field(default_factory=lambda: deque(maxlen=ROLLING_WINDOW))
    _intervention_log: deque[float] = field(default_factory=lambda: deque(maxlen=120))
    _cli_governor: CliGovernor | None = None
    _desktop_pause_active: bool = False
    _convergence: ConvergenceMonitor = field(default_factory=ConvergenceMonitor)
    # Phase 4: routing decision attached during _evaluate_inner so the outer
    # evaluate() can persist model_used/layer and feed the convergence monitor.
    _last_routing: RoutingDecision | None = None
    # Task F: True once the cross-session Hydrator thread (or sync hydrate)
    # has injected operator-approved cross_session=1 patterns. evaluate()
    # does NOT block on this — pre-hydration decisions just skip the
    # cross-session advisory (no graph entry → no match, like today).
    hydrated: bool = False
    # v1.4: Per-evaluate phase-timing breakouts (ms). Populated at the
    # end of each evaluate() call; tools (soak driver, perf_probe) read
    # this attribute to attribute the ALLOW p95 tail (ADR-5 v1.3
    # §"Caveats"). Keys are phase names; missing key = phase not exercised
    # on the call. The wall-clock budget is dominated by `evaluate_inner`
    # for L2+ (CLI subprocess) and by `inbound_publish` / `record_decision`
    # for L0 ALLOW.
    _last_phase_timings_ms: dict[str, float] | None = None
    # v1.5: transient handoff slot for sub-phase timings collected inside
    # `_evaluate_inner` and `_evaluate_inner_core`. The outer evaluate()
    # merges these into _last_phase_timings_ms and clears the slot. Live
    # for one call only; never read from outside the engine.
    _sub_timings_in_flight: dict[str, float] | None = None
    _pending_sub_phase_timings_ms: dict[str, float] | None = None

    def signal_desktop_pause(self) -> None:
        """Mark the next evaluate() as following a Desktop end_turn pause.

        FR-HITL-2 trigger 3 primary signal. The flag is consumed (reset to
        False) by `evaluate()` after each call so a single pause only
        triggers once.
        """
        self._desktop_pause_active = True

    def evaluate(self, msg: Message) -> GovDecision:
        # v1.4: per-phase wall-clock breakout. Cheap (single perf_counter
        # delta per phase). Populated incrementally and surfaced on
        # ``self._last_phase_timings_ms`` after the call returns so
        # external profilers (soak driver, perf_probe) can attribute the
        # ALLOW p95 tail without having to wrap evaluate() themselves.
        from time import perf_counter as _pc
        timings: dict[str, float] = {}
        _t_total_start = _pc()

        bus_msg: _msg_bus.Message | None = None
        if self.bus is not None and self.session_id:
            bus_msg = _msg_bus.Message.new(
                session_id=self.session_id,
                type="governance_eval",
                direction="inbound",
                content=msg.content,
                metadata={"role": msg.role, "msg_id": msg.id},
            )
            _t = _pc()
            self.bus.publish(bus_msg)
            timings["inbound_publish"] = (_pc() - _t) * 1000.0

        _t = _pc()
        decision = self._evaluate_inner(msg)
        timings["evaluate_inner"] = (_pc() - _t) * 1000.0
        # v1.5: fold sub-phase timings collected inside _evaluate_inner /
        # _evaluate_inner_core. Additive only — never overwrites an
        # existing key on `timings`. If a sub-phase didn't fire on this
        # path (e.g. og7_check return → graph_classify didn't run), the
        # key is still recorded with 0.0 by the inner instrumentation
        # so the soak block stays consistent across runs.
        pending_sub = getattr(self, "_pending_sub_phase_timings_ms", None)
        if isinstance(pending_sub, dict):
            for _sub_k, _sub_v in pending_sub.items():
                timings.setdefault(_sub_k, _sub_v)
        self._pending_sub_phase_timings_ms = None

        # v1.3 P5d: consult Learn Mode advisory bias. The bias is read
        # ONLY here, AFTER the existing ladder placement (precheck →
        # graph → CLI) has produced its decision. The hint never
        # mutates the decision — it pre-fills the HITL prompt and emits
        # a silent audit row. Safety-first invariants from INTENT.md
        # (§"Safety priorities") have already short-circuited inside
        # _evaluate_inner_core via fast_precheck before we ever get
        # here, so a high-confidence "approve" pattern cannot promote
        # a `rm -rf /` past BLOCK. The bias-application site below
        # additionally refuses to attach the hint when the message
        # content matches any of those classes, as belt-and-suspenders.
        _t = _pc()
        bias = self._consult_learn_mode_bias(msg.content, decision)
        timings["bias_consult"] = (_pc() - _t) * 1000.0

        # FR-HITL §4.9: route through the HITL queue if one is wired AND
        # we have a bus message to anchor the pending row to. The
        # classify_trigger pre-check is cheap and avoids a route() call
        # when no trigger fires. The desktop-pause flag is consumed
        # (reset) at the end of evaluate so a single pause only triggers
        # once.
        if self.hitl is not None and bus_msg is not None and self.session_id:
            _t = _pc()
            try:
                trigger = self.hitl.classify_trigger(
                    decision, msg.content, self._desktop_pause_active
                )
            except Exception:
                log.exception("hitl: classify_trigger raised; skipping route")
                trigger = None
            timings["hitl_classify_trigger"] = (_pc() - _t) * 1000.0
            if trigger is not None:
                # v1.3 P5d: bias fires ONLY when the HITL gate is going
                # to engage anyway. Even at confidence=1.0 the bias
                # never short-circuits the gate — the operator still
                # confirms. The audit envelope records that bias was
                # offered.
                if bias is not None:
                    self._emit_learn_mode_bias_applied(
                        bus_msg.id, msg.content, bias, trigger
                    )
                _t = _pc()
                try:
                    # v1.3 P5d (Fix B): pass bias hint into HITL route so
                    # it lands on the pending row's bias_hint column and
                    # the dashboard can pre-fill the operator prompt.
                    decision = self.hitl.route(
                        decision,
                        bus_msg.id,
                        msg.content,
                        self.session_id,
                        self._desktop_pause_active,
                        bias_hint=bias,
                    )
                except Exception:
                    log.exception("hitl: route raised; using original decision")
                timings["hitl_route"] = (_pc() - _t) * 1000.0
        # Always reset the pause flag, whether or not we routed.
        self._desktop_pause_active = False

        # Phase 4 / NFR-M3: capture the routing classification produced by
        # _evaluate_inner so we can persist model_used + layer alongside the
        # decision row, and feed the convergence monitor (NFR-M4).
        routing = self._last_routing
        self._last_routing = None
        if routing is None:
            # HITL re-route or other path that did not set routing —
            # default to L0 (no LLM, no model attribution).
            routing = RoutingDecision(ModelLayer.L0, None)

        if self.bus is not None and bus_msg is not None:
            _t = _pc()
            self.bus.record_decision(
                message_id=bus_msg.id,
                action=decision.action,
                confidence=decision.confidence,
                reasoning=decision.reasoning,
                matched_hash=decision.matched_hash,
                model_used=routing.model_id or "",
                layer=int(routing.layer),
            )
            timings["record_decision"] = (_pc() - _t) * 1000.0

        # NFR-M4 convergence alert: if L4 share exceeds 20% in the rolling
        # 5-minute window, publish an internal bus event so the dashboard /
        # operator can react. Total < 5 suppresses noisy early alerts.
        should_alert = self._convergence.record(routing.layer)
        if should_alert and self.bus is not None and self.session_id:
            _t = _pc()
            try:
                self.bus.publish(
                    _msg_bus.Message.new(
                        session_id=self.session_id,
                        type="nfr_model_routing_alert",
                        direction="internal",
                        content="L4 rate exceeded 20% threshold in 5-minute window",
                        metadata={"layer": int(routing.layer)},
                    )
                )
            except Exception:
                log.exception("convergence alert publish failed")
            timings["alert_publish"] = (_pc() - _t) * 1000.0

        # v1.4: surface per-phase timings to external profilers. Captured
        # AFTER all instrumented phases so the dict is complete on read.
        timings["total"] = (_pc() - _t_total_start) * 1000.0
        self._last_phase_timings_ms = timings
        return decision

    def _evaluate_inner(self, msg: Message) -> GovDecision:
        # v1.5: sub-phase wall-clock breakout inside `_evaluate_inner`.
        # Diagnoses ADR-5 v1.4 §"Caveats" — 100% of the ALLOW p95 tail
        # now sits inside this function and is opaque to the v1.4 phase
        # block. Sub-phases are additive; verdict path is byte-identical.
        # The outer `evaluate_inner` aggregate timing in evaluate() stays;
        # these new keys land alongside it on the same dict.
        from time import perf_counter as _pc
        sub_timings: dict[str, float] = {}

        profile: AgentProfile | None = None
        if self.registry is not None and self.session_id:
            profile = self.registry.active_profile(self.session_id)
        active_profile_slug = profile.slug if profile is not None else None

        # FR-OG-7 (Phase 5): maturity-ring signals run BEFORE precheck so
        # ring-derived overrides (negative regression BLOCK, sweep-JOB
        # ALLOW, AAR-without-deviations GUIDE) win over the static
        # precheck rules. The gate condition lives inside _check_fr_og7:
        # when self.maturity is None, the method returns None immediately
        # and normal evaluation continues unchanged.
        _t = _pc()
        og7 = self._check_fr_og7(msg, active_profile_slug)
        sub_timings["og7_check"] = (_pc() - _t) * 1000.0
        if og7 is not None:
            # Route the override decision into a layer for cost accounting
            # and convergence monitoring, just like the normal codepath.
            is_ambiguous_block = (
                og7.action == "BLOCK" and og7.confidence < 0.85
            )
            self._last_routing = route(
                source=og7.source,
                confidence=og7.confidence,
                is_ambiguous_block=is_ambiguous_block,
            )
            # v1.6 P1: FR-OG-7 hit does NOT traverse the CLI — pre-populate
            # the five residue keys with 0.0 so soak rows stay dense.
            self._zero_cli_residue_keys(sub_timings)
            self._record_sub_phase_timings(sub_timings)
            return og7

        # FR-AR-6: blocked_ops are unconditional — short-circuit before any
        # other routing so an agent cannot smuggle a forbidden op past a
        # graph match or default ALLOW.
        if profile is not None:
            ops = _classify_ops(msg.content)
            blocked_hit = ops & set(profile.blocked_ops)
            if blocked_hit:
                # v1.6 P1: FR-AR-6 blocked-op short-circuits before CLI —
                # zero out the residue keys for dense soak rows.
                self._zero_cli_residue_keys(sub_timings)
                self._record_sub_phase_timings(sub_timings)
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

        # v1.5: hydrator-fed state read. The graph patterns dict is
        # populated by `_install_lazy_hydrator` (Task I, v1.1) before
        # _evaluate_inner_core consults it via `graph.match`. We capture
        # a read-only timing on the hydrated flag + patterns count; we
        # do NOT mutate the hydrator surface.
        _t = _pc()
        _hydrated_flag = bool(getattr(self, "hydrated", False))
        _patterns_count = len(self.graph.patterns)
        sub_timings["hydrator_state_read"] = (_pc() - _t) * 1000.0
        # Reference values to avoid lint complaints about unused locals;
        # values themselves are not part of the verdict path.
        _ = (_hydrated_flag, _patterns_count)

        # _evaluate_inner_core internally runs fast_precheck → graph.match →
        # CLI. We instrument those sub-phases via attribute writes on a
        # transient `self._sub_timings_in_flight` dict that the core
        # reads/writes during the call. This keeps the verdict path
        # byte-identical (same return values, same ordering).
        self._sub_timings_in_flight = sub_timings
        try:
            decision = self._evaluate_inner_core(msg)
        finally:
            # Detach immediately so any unrelated code-path that calls
            # evaluate_inner_core never sees a stale reference.
            self._sub_timings_in_flight = None

        # routing_dispatch spans profile constraints + final route() call
        # — i.e. everything from _evaluate_inner_core return to the
        # _evaluate_inner return.
        _t = _pc()
        if profile is not None:
            decision = self._apply_profile_constraints(decision, profile, msg.content)

        # Phase 4 / NFR-M1-M3: classify the final decision into a routing
        # layer for cost accounting + convergence monitoring. is_ambiguous_block
        # is derived here (caller does not need to compute it).
        is_ambiguous_block = (
            decision.action == "BLOCK" and decision.confidence < 0.85
        )
        self._last_routing = route(
            source=decision.source,
            confidence=decision.confidence,
            is_ambiguous_block=is_ambiguous_block,
        )
        sub_timings["routing_dispatch"] = (_pc() - _t) * 1000.0
        # v1.6 P1: ensure all five CLI residue keys are present on the
        # final dict regardless of which inner-core branch fired
        # (precheck-hit, graph-high-confidence-hit, CLI-escalation,
        # default ALLOW). `setdefault` semantics — branches that DID
        # call the CLI keep their populated values.
        self._zero_cli_residue_keys(sub_timings)
        self._record_sub_phase_timings(sub_timings)
        return decision

    def _record_sub_phase_timings(self, sub_timings: dict[str, float]) -> None:
        """v1.5: stash sub-phase timings on a transient attribute so the
        outer evaluate() can fold them into _last_phase_timings_ms.

        Additive: never removes or renames existing keys. The outer
        evaluate() reads `_pending_sub_phase_timings_ms` after
        `_evaluate_inner` returns, merges into the timings dict, then
        clears the pending attr.
        """
        self._pending_sub_phase_timings_ms = sub_timings

    @staticmethod
    def _zero_cli_residue_keys(sub: dict[str, float]) -> None:
        """v1.6 P1: pre-populate the CLI residue keys with 0.0 on non-CLI
        branches (FR-OG-7 hit, FR-AR-6 blocked-op, precheck-hit,
        graph-high-confidence-hit, default ALLOW with no CLI).

        v1.7 P2 adds `cli_dispatch_fallback_ms` (Haiku→Sonnet fallback
        wall-clock; 0.0 unless the L4 sub-band fires the retry).

        Soak rows must be dense across all branches so percentile math
        is honest about the precheck-hit ratio (ADR-5 v1.5 §"Caveats").
        Uses setdefault so a CLI-traversed branch that already populated
        a key is never overwritten.
        """
        sub.setdefault("cli_setup_ms", 0.0)
        sub.setdefault("cli_dispatch_ms", 0.0)
        sub.setdefault("cli_pool_acquire_ms", 0.0)
        sub.setdefault("cli_pool_send_ms", 0.0)
        sub.setdefault("cli_parse_ms", 0.0)
        sub.setdefault("cli_dispatch_fallback_ms", 0.0)

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

        # Phase 6 follow-up: a per-agent override replaces profile.default_action
        # ONLY. blocked_ops/restricted_ops still fire — operators cannot lower
        # the safety floor by setting OBSERVE.
        override = None
        if self.registry is not None and self.session_id:
            try:
                override = self.registry.get_mode_override(
                    self.session_id, profile.slug
                )
            except Exception:
                override = None
        effective_default = override if override else profile.default_action

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

        # Default-action floor: when an operator override is set, ensure
        # the final action is at least as restrictive as the override.
        # Without an override we preserve Phase 1 behavior (no default_action
        # enforcement) to keep backward compat.
        if override:
            floored_default = _cap_action(new_action, effective_default)
            if floored_default != new_action:
                new_action = floored_default
                new_reason = (
                    f"agent_profile {profile.slug} override={effective_default}"
                    f" -> floored; {decision.reasoning}"
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

    # ── FR-OG-7 (Phase 5): maturity-ring signals ──────────────────────
    #
    # Canonical sweep-JOB order: developer → code_reviewer → tester →
    # researcher. When the active-profile slug stream matches that exact
    # 4-tuple, the JOB is recognized as the legitimate sweep pipeline and
    # is allowed through with confidence=0.95.
    _SWEEP_ORDER: tuple[str, ...] = (
        "developer",
        "code_reviewer",
        "tester",
        "researcher",
    )

    def _check_fr_og7(
        self, msg: Message, active_profile_slug: str | None
    ) -> GovDecision | None:
        """Return an overriding GovDecision if any FR-OG-7 signal fires.

        Gate condition: when ``self.maturity`` is None, FR-OG-7 is
        dormant — return None immediately so evaluate() proceeds with
        the standard precheck/graph/cli flow.
        """
        if self.maturity is None:
            return None

        # Refresh maturity snapshot (debounced; tolerant of bad files).
        try:
            delta = self.maturity.refresh()
        except Exception:
            log.exception("fr-og7: maturity.refresh raised; skipping signals")
            delta = None

        # Signal: negative cell regression → BLOCK + emit
        # governance_negative_regression bus event.
        if delta is not None and delta.regressed_cells:
            if self.bus is not None and self.session_id:
                try:
                    self.bus.publish(
                        _msg_bus.Message.new(
                            session_id=self.session_id,
                            type="governance_negative_regression",
                            direction="internal",
                            content=(
                                "Cells regressed: "
                                + ", ".join(delta.regressed_cells)
                            ),
                            metadata={
                                "cells": delta.regressed_cells,
                                "delta": delta.delta,
                            },
                        )
                    )
                except Exception:
                    log.exception("fr-og7: regression event publish failed")
            return GovDecision(
                action="BLOCK",
                confidence=1.0,
                reasoning=(
                    f"FR-OG-7: negative cell regression — "
                    f"{delta.regressed_cells}"
                ),
                mode=self.mode,
                source="fr_og7_regression",
            )

        # Signal: ring delta > 5% in 24h → emit governance_variance_alert
        # (FYI event only — does NOT short-circuit the decision).
        if (
            delta is not None
            and abs(delta.delta) > 5.0
            and delta.elapsed_seconds < 86400
            and self.bus is not None
            and self.session_id
        ):
            try:
                self.bus.publish(
                    _msg_bus.Message.new(
                        session_id=self.session_id,
                        type="governance_variance_alert",
                        direction="internal",
                        content=(
                            f"Ring delta {delta.delta:+.1f}% in "
                            f"{delta.elapsed_seconds / 3600:.1f}h"
                        ),
                        metadata={
                            "delta": delta.delta,
                            "elapsed_seconds": delta.elapsed_seconds,
                        },
                    )
                )
            except Exception:
                log.exception("fr-og7: variance event publish failed")

        # Signal: ≥3 cells promoted in same session → variance alert (FYI).
        if (
            delta is not None
            and len(delta.promoted_cells) >= 3
            and self.bus is not None
            and self.session_id
        ):
            try:
                self.bus.publish(
                    _msg_bus.Message.new(
                        session_id=self.session_id,
                        type="governance_variance_alert",
                        direction="internal",
                        content=(
                            f"3+ cells promoted: {delta.promoted_cells}"
                        ),
                        metadata={"cells": delta.promoted_cells},
                    )
                )
            except Exception:
                log.exception("fr-og7: promotion event publish failed")

        # Signal: sweep-JOB pattern detected → ALLOW override.
        # The sliding window keeps the last 4 profile slugs seen; we
        # match exactly against the canonical sweep order. The window
        # is NOT cleared on match — it slides naturally, so a partial
        # re-match later still requires the full 4-tuple.
        if active_profile_slug:
            self._sweep_job_agents_seen.append(active_profile_slug)
            self._sweep_job_agents_seen = self._sweep_job_agents_seen[-4:]
            if (
                tuple(self._sweep_job_agents_seen) == self._SWEEP_ORDER
            ):
                return GovDecision(
                    action="ALLOW",
                    confidence=0.95,
                    reasoning="FR-OG-7: sweep JOB pattern recognized",
                    mode=self.mode,
                    source="fr_og7_sweep",
                )

        # Signal: AAR message missing ## Deviations section → GUIDE.
        # AAR detection: heuristic on content (the literal "AAR", or the
        # phrase "after action", or the explicit "## deviations" header
        # mention) AND the literal "## Deviations" header is absent.
        content = msg.content or ""
        is_aar = (
            "AAR" in content
            or "after action" in content.lower()
            or "## deviations" in content.lower()
        )
        if is_aar and "## Deviations" not in content:
            return GovDecision(
                action="GUIDE",
                confidence=0.80,
                reasoning=(
                    "FR-OG-7: AAR missing ## Deviations section "
                    "(invariant 9)"
                ),
                mode=self.mode,
                source="fr_og7_aar",
            )

        return None

    # ── v1.3 P5d: Learn Mode advisory bias ───────────────────────────
    #
    # Bias is consulted ADDITIVELY after _evaluate_inner. It never
    # mutates the decision; it only pre-fills the HITL prompt and
    # records a silent audit row. INTENT.md safety priorities ALWAYS
    # WIN — destructive shell, force-push to protected branches,
    # eval/exec injection, and credential exfiltration are short-
    # circuited by fast_precheck inside _evaluate_inner_core BEFORE
    # bias is consulted. The check below is belt-and-suspenders: even
    # if a future refactor reordered the ladder, bias would still
    # refuse to attach to a message whose content matches any safety-
    # priority regex.

    def _is_safety_priority_content(self, content: str) -> bool:
        """True if the message hits any INTENT.md §"Safety priorities" class.

        Matches the same regexes used elsewhere in this module so we
        share a single source of truth. The check is read-only; a True
        answer means bias must NOT be offered for this message,
        regardless of pattern strength.
        """
        if not content:
            return False
        if _DESTRUCTIVE_SHELL_RE.search(content):
            return True
        if _FORCE_PUSH_RE.search(content):
            return True
        if _CRED_EXFIL_RE.search(content):
            return True
        # Code-injection patterns: eval(/exec( in untrusted bodies
        # (priority #3). Fix C (review): share the canonical regex with
        # ``project_context.fast_precheck`` so the two checks cannot
        # drift. A previous version used a substring check that would
        # have missed e.g. `eval (` (whitespace before paren).
        if EVAL_EXEC_INJECTION_RE.search(content):
            return True
        return False

    def _consult_learn_mode_bias(
        self, content: str, decision: GovDecision
    ) -> BiasHint | None:
        """Return the Learn Mode bias hint for ``content``, or None.

        Returns None when:
          * No bus is wired (bias requires the ``learn_patterns`` table).
          * The decision already reached a non-ALLOW outcome — the
            existing ladder placement is more authoritative than a
            historical pattern, and we never want to weaken a BLOCK.
          * The message content matches any INTENT.md safety priority
            (belt-and-suspenders; precheck already short-circuited).
          * No matching pattern exists or confidence is below
            ``MIN_BIAS_CONFIDENCE``.
        """
        if self.bus is None:
            return None
        # Defense in depth: never bias a safety-priority decision. The
        # standard ladder has already produced a BLOCK/INTERVENE for
        # these via fast_precheck; we additionally refuse to surface a
        # hint regardless of how confident the pattern is.
        if self._is_safety_priority_content(content):
            return None
        # Bias is only meaningful when the verdict is ALLOW-shaped or
        # OBSERVE — i.e. a path where the operator is genuinely free to
        # confirm or reject via HITL. For BLOCK/INTERVENE we never want
        # to suggest "approve" via the HITL pre-fill.
        #
        # Fix D (review): in OBSERVE mode ``_apply_mode`` already rewrote
        # ``decision.action`` to ALLOW (with the original verdict
        # preserved on ``original_action``). Reading ``decision.action``
        # alone would let a BLOCK leak through as ALLOW-shaped and
        # acquire bias. Resolve to the effective action first.
        effective_action = decision.original_action or decision.action
        if effective_action in {"BLOCK", "INTERVENE"}:
            return None
        try:
            return bias_for(content, self.bus)
        except Exception:
            log.exception("learn_mode bias_for raised; skipping bias")
            return None

    def _emit_learn_mode_bias_applied(
        self,
        bus_msg_id: str,
        content: str,
        bias: BiasHint,
        trigger: object,
    ) -> None:
        """Emit the silent ``learn_mode_bias_applied`` audit envelope.

        Per FR-LM-5 (design §2.6): no toast, no undo. The dashboard
        decisions feed renders this row as a silent audit entry. The
        envelope carries the bias hint metadata so operators can trace
        what was offered without the categorizer running synchronously
        on the hot path.
        """
        if self.bus is None or not self.session_id:
            return
        try:
            self.bus.publish(
                _msg_bus.Message.new(
                    session_id=self.session_id,
                    type="learn_mode_bias_applied",
                    direction="internal",
                    content=(
                        f"Learn Mode bias offered (category="
                        f"{bias.category}, confidence={bias.confidence:.2f})"
                    ),
                    metadata={
                        "anchor_msg_id": bus_msg_id,
                        "category": bias.category,
                        "confidence": bias.confidence,
                        "ladder_step_suggestion": bias.ladder_step_suggestion,
                        "pattern_id": bias.pattern_id,
                        "last_reinforced_ts": bias.last_reinforced_ts,
                        "hitl_trigger": getattr(trigger, "value", str(trigger)),
                    },
                )
            )
        except Exception:
            log.exception("learn_mode_bias_applied: publish failed")

    def _evaluate_inner_core(self, msg: Message) -> GovDecision:
        # v1.5: sub-phase timing capture. The transient slot
        # `_sub_timings_in_flight` is set by _evaluate_inner before this
        # call and cleared after; if it is None (defensive — direct
        # caller invokes core without _evaluate_inner), we record into a
        # local throwaway dict so the verdict path is unaffected.
        from time import perf_counter as _pc
        sub = self._sub_timings_in_flight
        if sub is None:
            sub = {}

        _t = _pc()
        pre = fast_precheck(msg.content, self.project_context)
        sub["fast_precheck"] = (_pc() - _t) * 1000.0
        if pre is not None:
            # graph_classify did not run on this branch — record 0.0 so
            # the soak block has a row rather than a missing key. The
            # n=0 case is for engines that never hit ALLOW; here we
            # always record a value so p50/p95 reflect the precheck-hit
            # ratio honestly.
            sub.setdefault("graph_classify", 0.0)
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

        _t = _pc()
        match = self.graph.match(msg.content)
        sub["graph_classify"] = (_pc() - _t) * 1000.0
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
        # Phase 4 follow-up / NFR-M2: pre-route the CLI call so the
        # subprocess uses the right tier. At this point precheck missed and
        # no high-confidence graph match resolved it, so the source is "cli"
        # (L3 by default). If the message looks like an alignment-requiring
        # action AND maturity is wired (FR-OG-7 active), promote to L4 →
        # Sonnet. Otherwise fall back to Haiku (L2/L3 model).
        pre_requires_alignment = (
            self.maturity is not None
            and _looks_alignment_action(msg.content)
        )
        # v1.7 P2: pre_routing carries an optional fallback_model_id —
        # None for FR-OG-7 alignment (Sonnet only) and for the v1.7 default
        # state, Sonnet when the L4 sub-band picks the Haiku fastpath.
        # v1.8 P1: is_ambiguous_block / is_hitl_synthesis are now computed
        # from content + HITL state. Routing precedence (alignment beats
        # the sub-band) is enforced inside `model_router.route()` — flags
        # are passed raw, no call-site precedence check.
        pre_is_ambiguous_block = _looks_ambiguous_block(msg.content)
        pre_is_hitl_synthesis = _looks_hitl_synthesis(
            msg.content, self.hitl, self._desktop_pause_active
        )
        pre_routing = route(
            source="cli",
            confidence=0.0,
            requires_alignment=pre_requires_alignment,
            is_ambiguous_block=pre_is_ambiguous_block,
            is_hitl_synthesis=pre_is_hitl_synthesis,
        )
        cli_model_id = pre_routing.model_id or get_l2_model()
        cli_decision = self._maybe_cli_evaluate(
            cli_content,
            cli_model_id,
            fallback_model_id=pre_routing.fallback_model_id,
        )
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

    def _maybe_cli_evaluate(
        self,
        content: str,
        model_id: str | None = None,
        fallback_model_id: str | None = None,
    ):
        # v1.6 P1: residue-level wall-clock instrumentation. cli_setup_ms
        # spans entry → just before CliGovernor.evaluate(...) (covers
        # lazy CliGovernor() construction and _system_prompt() cache
        # build on first call). The four CLI-side keys
        # (cli_dispatch_ms / cli_pool_acquire_ms / cli_pool_send_ms /
        # cli_parse_ms) are populated by CliGovernor.evaluate when we
        # thread `sub_timings=sub` through. v1.7 P2 adds
        # `cli_dispatch_fallback_ms` populated by the same path.
        from time import perf_counter as _pc
        _t_setup_start = _pc()
        # `_sub_timings_in_flight` is set by _evaluate_inner before this
        # call. Defensive: fall back to a throwaway dict for direct
        # callers (tests that exercise _maybe_cli_evaluate without going
        # through _evaluate_inner) so the verdict path is unaffected.
        sub = self._sub_timings_in_flight
        if sub is None:
            sub = {}
        if not _cli_enabled():
            # Per phase-1 prompt: branches that return early WITHOUT
            # calling the CLI MUST set all keys to 0.0 on `sub`. The few
            # microseconds of `_cli_enabled()` overhead are intentionally
            # NOT recorded — they would muddy the precheck-hit-ratio
            # percentile math the soak block relies on. The non-zero
            # `cli_setup_ms` only fires when the branch actually traverses
            # the CLI dispatch.
            sub["cli_setup_ms"] = 0.0
            sub.setdefault("cli_dispatch_ms", 0.0)
            sub.setdefault("cli_pool_acquire_ms", 0.0)
            sub.setdefault("cli_pool_send_ms", 0.0)
            sub.setdefault("cli_parse_ms", 0.0)
            sub.setdefault("cli_dispatch_fallback_ms", 0.0)
            return None
        if self._cli_governor is None:
            # Phase 7: thread bus + session_id through so CliGovernor can
            # emit governance_call lifecycle events. Both are optional —
            # CliGovernor silently skips publish when either is unset
            # (preserves back-compat for callers that build CliGovernor
            # directly without a bus).
            self._cli_governor = CliGovernor(
                self.project_context,
                bus=self.bus,
                session_id=self.session_id or None,
                pool=self.cli_pool,  # type: ignore[arg-type]
            )
        # Phase 4 / NFR-M2: caller selects the model tier via the
        # pre-routing pass in _evaluate_inner_core. When omitted, fall back
        # to the L2/L3 Haiku default for backward compatibility with
        # callers that haven't been updated.
        chosen = model_id if model_id is not None else get_l2_model()
        sub["cli_setup_ms"] = (_pc() - _t_setup_start) * 1000.0
        return self._cli_governor.evaluate(
            content,
            model_id=chosen,
            sub_timings=sub,
            fallback_model_id=fallback_model_id,
        )

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
        # Snapshot levels before observe() so we can detect L2→L3 transitions
        # for cross-session HITL flagging (Task F).
        pre_levels = {h: int(p.level) for h, p in self.graph.patterns.items()}
        pattern = self.graph.observe(msg.content, success)
        self._maybe_emit_cross_session_hitl(msg, pattern, pre_levels)

    def _maybe_emit_cross_session_hitl(
        self,
        msg: Message,
        pattern: object,
        pre_levels: dict[str, int],
    ) -> None:
        """Emit a HITL queue entry when a pattern transitions to L3.

        OQ5/OQ6/OQ8: cross-session promotion is gated on operator approval.
        Auto-flagging is replaced by a HITL row with trigger_reason
        "cross_session_flag"; the pattern hash travels in the dedicated
        hitl_pending.matched_hash column (Task L, v1.1; replaces the v1.0
        `flag_cross_session:<hash>` proposed_action hack).
        """
        if self.bus is None or not self.session_id:
            return
        try:
            new_level = int(getattr(pattern, "level", 0))
            new_hash = str(getattr(pattern, "hash", ""))
        except Exception:
            return
        if new_level < 3 or not new_hash:
            return
        if pre_levels.get(new_hash, -1) >= 3:
            return  # already at L3+; not a fresh transition

        # Persist the pattern to the bus so the Hydrator can find it once
        # the operator approves the cross-session flag.
        try:
            self.bus.upsert_pattern(
                hash=new_hash,
                level=new_level,
                occurrences=int(getattr(pattern, "occurrences", 0)),
                success_rate=float(getattr(pattern, "success_rate", 0.0)),
                last_seen=float(getattr(pattern, "last_seen", time.time())),
                payload=str(getattr(pattern, "canonical_text", "")),
            )
        except Exception:
            log.exception("cross-session: upsert_pattern failed")
            return

        # Anchor the HITL row to a fresh bus message so existing pending
        # joins on messages.session_id continue to work for filtering.
        try:
            anchor = _msg_bus.Message.new(
                session_id=self.session_id,
                type="cross_session_promotion",
                direction="internal",
                content=str(getattr(pattern, "canonical_text", new_hash))[:200],
                metadata={"matched_hash": new_hash, "level": new_level},
            )
            self.bus.publish(anchor)
            self.bus.queue_hitl(
                message_id=anchor.id,
                proposed_action="flag",
                proposed_confidence=0.9,
                trigger_reason="cross_session_flag",
                matched_hash=new_hash,
            )
        except Exception:
            log.exception("cross-session: queue_hitl failed")

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


# ── EngineRegistry: per-session engine instancing (Task B) ─────────────
#
# Long-lived processes (dashboard, soak driver, future SM daemon) need
# one GovernanceEngine per governed session_id. The registry constructs
# engines lazily on first `get_or_create(session_id)` and isolates all
# in-memory state (mode ladder, rolling windows, convergence monitor,
# DecisionGraph) per instance — no shared mutable globals across sessions.
#
# SM-never-self-monitor enforcement (Task B spec §4): if a caller passes
# the SM's own session_id (via SM_OWN_SESSION_ID env var, set at SM boot),
# get_or_create raises ValueError. This blocks the eval feedback loop where
# SM would govern its own bus events.
#
# Hook payload integration: callers route incoming hook events with
#     registry.get_or_create(session_id).evaluate(msg)
# instead of holding a singleton engine.

DecisionGraphFactory = Callable[[], DecisionGraph]


class EngineRegistry:
    """Holds one GovernanceEngine per session_id. Thread-safe."""

    def __init__(
        self,
        bus: _msg_bus.MessageBus | None,
        project_context: ProjectContextSnapshot,
        graph_factory: DecisionGraphFactory | None = None,
        agent_registry: AgentRegistry | None = None,
        hitl: HitlQueue | None = None,
        maturity: MaturityReader | None = None,
        rate_limit_per_min: int = DEFAULT_RATE_LIMIT_PER_MIN,
        auto_refresh: bool = False,
        refresh_interval_s: float = 60.0,
        cli_pool: object | None = None,
    ) -> None:
        self._bus = bus
        self._project_context = project_context
        self._graph_factory: DecisionGraphFactory = graph_factory or (lambda: DecisionGraph())
        self._agent_registry = agent_registry
        self._hitl = hitl
        self._maturity = maturity
        self._rate_limit_per_min = rate_limit_per_min
        # Task J / v1.1: optional shared CLI warm-pool, propagated to every
        # engine instantiated by this registry.
        self._cli_pool = cli_pool
        self._engines: dict[str, GovernanceEngine] = {}
        self._lock = threading.RLock()
        # Task F: cross-session pattern refresh. Disabled by default —
        # auto-start causes timer-driven flakiness in tests. Long-lived
        # processes opt in via auto_refresh=True or start_refresh().
        self._refresh_interval_s = float(refresh_interval_s)
        self._refresh_timer: threading.Timer | None = None
        self._refresh_stopped = True
        # Task M: timestamp (epoch seconds) of the last refresh_all() return,
        # or None if refresh_all has never completed. Surfaced via
        # /api/registry/active for operator visibility.
        self.last_refresh_ts: float | None = None
        if auto_refresh:
            self.start_refresh()

    @staticmethod
    def _sm_own_session_id() -> str:
        return os.environ.get("SM_OWN_SESSION_ID", "")

    def get_or_create(self, session_id: str) -> GovernanceEngine:
        if not session_id:
            raise ValueError("session_id required")
        sm_own = self._sm_own_session_id()
        if sm_own and session_id == sm_own:
            raise ValueError(
                f"SM cannot self-monitor: session_id matches SM_OWN_SESSION_ID ({sm_own!r})"
            )
        with self._lock:
            eng = self._engines.get(session_id)
            if eng is not None:
                return eng
            eng = GovernanceEngine(
                project_context=self._project_context,
                graph=self._graph_factory(),
                bus=self._bus,
                session_id=session_id,
                registry=self._agent_registry,
                hitl=self._hitl,
                maturity=self._maturity,
                rate_limit_per_min=self._rate_limit_per_min,
                cli_pool=self._cli_pool,
            )
            self._engines[session_id] = eng
            # Task I (v1.1): Hydrator is now lazy — it does NOT spawn during
            # engine construction. The first evaluate() call after creation
            # spawns the daemon thread, so the cost of reading the patterns
            # table is not paid on the synchronous get_or_create path. This
            # frees the dashboard hot-path of any sync DB read.
            #
            # Hydrator semantics are unchanged: still daemon=True, still
            # publishes via engine.hydrated, still idempotent on the
            # patterns-already-present case.
            if self._bus is not None:
                self._install_lazy_hydrator(eng)
            return eng

    @staticmethod
    def _install_lazy_hydrator(eng: GovernanceEngine) -> None:
        """Wrap ``eng.evaluate`` so the first call spawns the Hydrator.

        Subsequent evaluate() calls cost a single attribute read + a
        method-call hop. The Hydrator thread itself is daemon=True so
        evaluate() never blocks on it.
        """
        bus = eng.bus
        if bus is None:
            return
        original_evaluate = eng.evaluate
        # Use a list as a one-shot latch — closures + bool would need
        # ``nonlocal`` which dataclass-bound methods can't access cleanly.
        spawned = [False]

        def evaluate_with_lazy_hydrator(msg: Message) -> GovDecision:
            if not spawned[0]:
                spawned[0] = True
                try:
                    from stream_manager.cross_session_hydrator import Hydrator
                    Hydrator(eng, bus).start()
                except Exception:
                    log.exception("registry: lazy hydrator spawn failed")
            return original_evaluate(msg)

        # Bind on the instance — this shadows the class method only for
        # this engine. type:ignore — dataclass field binding is fine here.
        eng.evaluate = evaluate_with_lazy_hydrator  # type: ignore[method-assign]

    def close(self, session_id: str) -> None:
        """Drop the engine for a session. Idempotent."""
        with self._lock:
            self._engines.pop(session_id, None)

    def active_session_ids(self) -> list[str]:
        with self._lock:
            return list(self._engines.keys())

    def __len__(self) -> int:
        with self._lock:
            return len(self._engines)

    def __contains__(self, session_id: object) -> bool:
        with self._lock:
            return session_id in self._engines

    # ── Task F: periodic cross-session pattern refresh ────────────────

    def refresh_all(self) -> int:
        """Re-hydrate every active engine from bus.cross_session=1 rows.

        Idempotent: existing pattern hashes are not downgraded. Returns
        the total number of newly-injected entries across all engines.
        Tests call this directly to avoid timer races.

        Task M coordination with Task I lazy-init: engines whose initial
        spawn-time Hydrator hasn't completed (engine.hydrated=False) are
        skipped to avoid racing the per-engine background thread. The
        next 60s tick will pick them up once the lazy hydrator finishes.
        """
        # Always update the timestamp so /api/registry/active reflects
        # liveness even when there's nothing to inject (no bus, no engines).
        self.last_refresh_ts = time.time()
        if self._bus is None:
            return 0
        try:
            from stream_manager.cross_session_hydrator import hydrate_now
        except Exception:
            log.exception("registry: refresh_all import failed")
            return 0
        total = 0
        with self._lock:
            engines = list(self._engines.values())
        for eng in engines:
            # Task I/M coordination: if the per-engine spawn-time Hydrator
            # is still in flight, skip — re-running hydrate_now now would
            # race the background thread and double-inject the same rows.
            if not getattr(eng, "hydrated", False):
                continue
            try:
                total += hydrate_now(eng, self._bus)
            except Exception:
                log.exception("registry: refresh_all engine hydrate failed")
        return total

    def start_refresh(self) -> None:
        """Begin chained 60s timer that calls refresh_all() each tick."""
        with self._lock:
            self._refresh_stopped = False
            if self._refresh_timer is None:
                self._arm_refresh_locked()

    def stop_refresh(self, join_timeout: float = 1.0) -> None:
        """Stop the periodic refresh timer. Idempotent.

        Task M: cancel the pending Timer and best-effort join it so a
        host process (uvicorn shutdown) doesn't hang on a daemon timer
        whose payload is mid-flight. Daemon=True already prevents hangs
        at process exit, but explicit join makes shutdown deterministic.
        """
        with self._lock:
            self._refresh_stopped = True
            timer = self._refresh_timer
            self._refresh_timer = None
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                log.exception("registry: timer cancel failed")
            try:
                timer.join(timeout=join_timeout)
            except Exception:
                log.exception("registry: timer join failed")

    @property
    def refresh_active(self) -> bool:
        """True iff start_refresh() has been called and stop_refresh() hasn't."""
        with self._lock:
            return not self._refresh_stopped

    def refresh_status(self) -> dict:
        """Snapshot of refresh-loop liveness for /api/registry/active."""
        with self._lock:
            return {
                "refresh_active": not self._refresh_stopped,
                "last_refresh_ts": self.last_refresh_ts,
                "refresh_interval_s": self._refresh_interval_s,
            }

    def _arm_refresh_locked(self) -> None:
        # Caller holds self._lock.
        if self._refresh_stopped:
            return
        t = threading.Timer(self._refresh_interval_s, self._on_refresh_tick)
        t.daemon = True
        self._refresh_timer = t
        t.start()

    def _on_refresh_tick(self) -> None:
        try:
            self.refresh_all()
        except Exception:
            log.exception("registry: refresh tick failed")
        finally:
            with self._lock:
                self._refresh_timer = None
                self._arm_refresh_locked()
