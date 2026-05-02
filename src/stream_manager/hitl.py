"""Human-in-the-Loop queue — FR-HITL §4.9 / ADR-9.

Provides a switchable sync/async governance gate:

    sync mode  — block in route() until a human resolves the queued row,
                 or until self.timeout_seconds elapses.
    async mode — pass the original decision through and emit a flag event
                 so the dashboard can surface it for retroactive annotation.

Both modes share a single feedback loop (`apply_feedback`) that:
    * stores the override in `hitl_overrides`
    * adjusts decision-graph confidence on the matched hash
        +0.05 (cap 1.0) when the human approved the engine's call
        -0.10 (floor 0.0) when the human picked a different action
    * caches up to N=5 short notes per matched hash for later prompt prefix
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stream_manager.decision_graph import DecisionGraph
    from stream_manager.governance import GovDecision
    from stream_manager.message_bus import MessageBus

log = logging.getLogger(__name__)


# FR-HITL-2 trigger 3 fallback heuristic. JSONL `stopReason=end_turn` is
# the primary signal (handled by the desktop_pause_active flag); these
# patterns are the text fallback used when the JSONL tail is unavailable
# or lagging.
PAUSE_PATTERNS = re.compile(
    r"(\?\s*$|should\s+i\b|please\s+confirm\b)",
    re.IGNORECASE,
)


_NOTE_TOKEN_CAP = 50
_NOTE_HASH_CAP = 5
_POLL_INTERVAL_S = 0.5
_VALID_RESOLUTION_PREFIXES = ("approved", "overridden:", "timeout", "dismissed")


class TriggerReason(StrEnum):
    NEW_PATTERN = "new_pattern"
    LOW_CONFIDENCE = "low_confidence"
    DESKTOP_PAUSE = "desktop_pause"
    CROSS_SESSION_FLAG = "cross_session_flag"


def dispatch_resolution(
    bus: MessageBus, pending_id: int, resolution: str
) -> None:
    """Apply side-effects for a resolved hitl_pending row.

    Today only `trigger_reason == "cross_session_flag"` carries side-effects:
    on `approved` the underlying pattern hash (encoded in proposed_action as
    `flag_cross_session:<hash>`) is flagged for cross-session hydration.
    Rejection or override leaves the flag at 0.
    """
    try:
        row = bus.get_hitl_pending_row(pending_id)
    except Exception:
        log.exception("dispatch_resolution: get_hitl_pending_row failed")
        return
    if row is None:
        return
    if row.get("trigger_reason") != TriggerReason.CROSS_SESSION_FLAG.value:
        return
    if resolution != "approved":
        return
    proposed = str(row.get("proposed_action") or "")
    if not proposed.startswith("flag_cross_session:"):
        return
    hash_ = proposed.split(":", 1)[1]
    if not hash_:
        return
    try:
        bus.flag_pattern_cross_session(hash_)
    except Exception:
        log.exception("dispatch_resolution: flag_pattern_cross_session failed")


def _truncate_to_tokens(text: str, max_tokens: int = _NOTE_TOKEN_CAP) -> str:
    """Whitespace-tokenize and truncate to <= max_tokens tokens."""
    if not text:
        return ""
    parts = text.split()
    if len(parts) <= max_tokens:
        return " ".join(parts)
    return " ".join(parts[:max_tokens])


@dataclass
class HitlQueue:
    bus: MessageBus
    timeout_seconds: float = 60.0
    graph: DecisionGraph | None = None
    poll_interval_s: float = _POLL_INTERVAL_S
    _notes_by_hash: dict[str, list[str]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # ── classification ───────────────────────────────────────────────

    def classify_trigger(
        self,
        decision: GovDecision,
        message_content: str,
        desktop_pause_active: bool,
    ) -> TriggerReason | None:
        """Return the first matching trigger, or None.

        Reads the session's confidence floor from the WAL bus. Falls back
        to 0.60 if no session row is available.
        """
        # Trigger 1: new pattern (engine took the default branch).
        if decision.source == "default":
            return TriggerReason.NEW_PATTERN

        # Trigger 2: low confidence relative to session floor.
        floor = self._floor_for(decision)
        if decision.confidence < floor:
            return TriggerReason.LOW_CONFIDENCE

        # Trigger 3: desktop pause (JSONL primary, text-heuristic fallback).
        if desktop_pause_active:
            return TriggerReason.DESKTOP_PAUSE
        if message_content and PAUSE_PATTERNS.search(message_content):
            return TriggerReason.DESKTOP_PAUSE

        return None

    def _floor_for(self, decision: GovDecision) -> float:
        # Decisions don't carry session_id directly; the engine's caller
        # already passes session context to route(). For classify_trigger
        # standalone use we can't read the session floor without that
        # context, so fall back to the default. Engines that wire HITL in
        # will go through route() which reads the session row.
        return 0.60

    # ── routing ──────────────────────────────────────────────────────

    def route(
        self,
        decision: GovDecision,
        message_id: str,
        message_content: str,
        session_id: str,
        desktop_pause_active: bool,
    ) -> GovDecision:
        """Hold (sync) or pass-through (async) a decision based on session mode."""
        from stream_manager.governance import GovDecision  # local import: avoid cycle

        mode, floor = ("async", 0.60)
        try:
            mode, floor = self.bus.get_hitl_mode(session_id)
        except Exception:
            log.debug("hitl: get_hitl_mode failed, defaulting to async/0.60",
                      exc_info=True)

        # Re-classify against the actual session floor (classify_trigger
        # uses default 0.60 because it has no session context).
        trigger: TriggerReason | None = None
        if decision.source == "default":
            trigger = TriggerReason.NEW_PATTERN
        elif decision.confidence < floor:
            trigger = TriggerReason.LOW_CONFIDENCE
        elif desktop_pause_active or (message_content and PAUSE_PATTERNS.search(message_content)):
            trigger = TriggerReason.DESKTOP_PAUSE

        if trigger is None:
            return decision

        if mode == "sync":
            return self._route_sync(
                decision, message_id, session_id, trigger, GovDecision
            )
        return self._route_async(
            decision, message_id, session_id, trigger, GovDecision
        )

    def _route_async(
        self,
        decision: GovDecision,
        message_id: str,
        session_id: str,
        trigger: TriggerReason,
        GovDecisionCls: type,
    ) -> GovDecision:
        try:
            self._emit_event(
                session_id,
                "hitl_async_flagged",
                message_id,
                {
                    "trigger_reason": trigger.value,
                    "proposed_action": decision.action,
                    "proposed_confidence": decision.confidence,
                },
            )
        except Exception:
            log.exception("hitl: async flag emit failed")
        return decision

    def _route_sync(
        self,
        decision: GovDecision,
        message_id: str,
        session_id: str,
        trigger: TriggerReason,
        GovDecisionCls: type,
    ) -> GovDecision:
        try:
            pending_id = self.bus.queue_hitl(
                message_id=message_id,
                proposed_action=decision.action,
                proposed_confidence=decision.confidence,
                trigger_reason=trigger.value,
            )
        except Exception:
            log.exception("hitl: queue_hitl failed; passing through")
            return decision

        try:
            self._emit_event(
                session_id,
                "hitl_sync_queued",
                message_id,
                {
                    "pending_id": pending_id,
                    "trigger_reason": trigger.value,
                    "proposed_action": decision.action,
                    "proposed_confidence": decision.confidence,
                },
            )
        except Exception:
            log.exception("hitl: sync queue emit failed")

        deadline = time.monotonic() + max(0.0, self.timeout_seconds)
        resolution: str | None = None
        while True:
            now = time.monotonic()
            if now >= deadline:
                break
            try:
                row = self.bus.get_hitl_pending_row(pending_id)
            except Exception:
                log.exception("hitl: get_hitl_pending_row failed")
                row = None
            if row is not None and row.get("resolution"):
                resolution = str(row["resolution"])
                break
            # Sleep at most until deadline, capped at poll interval.
            remaining = deadline - now
            time.sleep(min(self.poll_interval_s, max(0.0, remaining)))

        if resolution is None:
            # Timeout: record + emit + return original decision.
            try:
                self.bus.resolve_hitl(pending_id, "timeout")
            except Exception:
                log.exception("hitl: resolve_hitl(timeout) failed")
            try:
                self._emit_event(
                    session_id,
                    "hitl_timeout",
                    message_id,
                    {"pending_id": pending_id, "trigger_reason": trigger.value},
                )
            except Exception:
                log.exception("hitl: timeout emit failed")
            return decision

        if resolution == "approved" or resolution == "dismissed":
            return decision

        if resolution.startswith("overridden:"):
            override_action = resolution.split(":", 1)[1] or decision.action
            try:
                from dataclasses import replace
                return replace(
                    decision,
                    action=override_action,
                    reasoning=f"hitl override: {decision.reasoning}",
                    original_action=decision.original_action or decision.action,
                    source="hitl",
                )
            except Exception:
                log.exception("hitl: override replace failed; passing original")
                return decision

        # Unknown resolution string: be conservative and return original.
        log.warning("hitl: unknown resolution %r, passing original", resolution)
        return decision

    # ── feedback loop ────────────────────────────────────────────────

    def apply_feedback(
        self,
        decision_id: str,
        override_action: str,
        note: str | None,
        mode: str,
    ) -> None:
        """Persist override + adjust graph confidence + cache note."""
        decision_row = None
        try:
            decision_row = self.bus.get_decision_by_id(decision_id)
        except Exception:
            log.exception("hitl: get_decision_by_id failed")

        original_action = (
            str(decision_row["action"]) if decision_row else override_action
        )
        matched_hash = (
            str(decision_row.get("matched_hash") or "") if decision_row else ""
        )

        truncated_note: str | None = None
        if note:
            truncated_note = _truncate_to_tokens(note)

        try:
            self.bus.annotate_decision(
                decision_id=decision_id,
                original_action=original_action,
                override_action=override_action,
                note=truncated_note,
                mode=mode,
            )
        except Exception:
            log.exception("hitl: annotate_decision failed")

        # Confidence adjustment: only meaningful when we know the matched
        # hash AND have a graph reference.
        approved = override_action == original_action
        if matched_hash and self.graph is not None:
            try:
                pattern = self.graph.patterns.get(matched_hash)
                if pattern is not None:
                    if approved:
                        # +0.05 cap 1.0 — bias success rate upward.
                        pattern.successes += 1
                        pattern.occurrences += 1
                    else:
                        # -0.10 floor 0.0 -- bias success rate downward.
                        # Approximate by recording a failure-weighted obs.
                        pattern.occurrences += 1
                    self._clamp_pattern_rate(pattern, approved)
            except Exception:
                log.exception("hitl: graph confidence adjustment failed")
        elif matched_hash and self.graph is None:
            log.warning(
                "hitl: matched_hash=%s present but no DecisionGraph wired; "
                "override stored but confidence not adjusted",
                matched_hash[:8],
            )

        if matched_hash and truncated_note:
            with self._lock:
                bucket = self._notes_by_hash.setdefault(matched_hash, [])
                bucket.append(truncated_note)
                if len(bucket) > _NOTE_HASH_CAP:
                    # Keep the newest N notes.
                    del bucket[: len(bucket) - _NOTE_HASH_CAP]

    @staticmethod
    def _clamp_pattern_rate(pattern: Any, approved: bool) -> None:
        """Best-effort clamp of pattern success_rate to [0, 1].

        Pattern.success_rate is derived from successes/occurrences. The
        FR-HITL spec asks for ±delta with caps; we approximate by
        nudging the underlying counts so the derived rate moves in the
        right direction without introducing a separate confidence field.
        """
        try:
            rate = pattern.success_rate
        except Exception:
            return
        if rate < 0.0 or rate > 1.0:
            # Renormalize: clamp by adjusting successes within bounds.
            occ = max(1, int(pattern.occurrences))
            succ = max(0, min(occ, int(pattern.successes)))
            pattern.successes = succ
            pattern.occurrences = occ

    def get_active_notes(self, matched_hash: str) -> list[str]:
        """Return up to N=5 most recent ≤50-token notes for a hash."""
        if not matched_hash:
            return []
        with self._lock:
            cached = list(self._notes_by_hash.get(matched_hash, []))
        if cached:
            return cached[-_NOTE_HASH_CAP:]
        # Fallback: pull from WAL the last N overrides for this hash.
        try:
            rows = self.bus.get_overrides_for_hash(matched_hash, limit=_NOTE_HASH_CAP)
        except Exception:
            return []
        notes: list[str] = []
        for row in rows:
            n = row.get("note")
            if n:
                notes.append(_truncate_to_tokens(str(n)))
        # rows are newest-first from the WAL; reverse so caller sees
        # oldest→newest, matching the in-memory bucket ordering.
        notes.reverse()
        return notes

    # ── helpers ──────────────────────────────────────────────────────

    def _emit_event(
        self,
        session_id: str,
        event_type: str,
        message_id: str,
        metadata: dict[str, object],
    ) -> None:
        """Publish a bus event so the dashboard SSE can surface it."""
        try:
            from stream_manager.message_bus import Message as _BusMessage
            self.bus.publish(
                _BusMessage.new(
                    session_id=session_id,
                    type=event_type,
                    direction="inbound",
                    content=message_id,
                    metadata=metadata,
                )
            )
        except Exception:
            log.exception("hitl: bus emit %s failed", event_type)
