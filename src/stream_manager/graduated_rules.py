"""ADR-18 Amendment F -- operator-confirmed graduated-ALLOW rule store.

A *graduated rule* is a command-shape the operator has explicitly
confirmed is routine: observed ALLOWed at high confidence many times,
with zero operator override, and never matching a safety-floor class.
Once confirmed it short-circuits the governance verdict ladder to a
cheap static ALLOW (``source="graduated"``) -- subordinate to
``fast_precheck`` (the safety floor ALWAYS wins) and outranking the
probabilistic graph.

Default-OFF: the verdict short-circuit is gated by the
``BRIDGE_GRADUATED_RULES`` env flag. When OFF, :meth:`GraduatedRuleStore.lookup`
returns ``None`` WITHOUT touching the bus, so the ladder is byte-for-byte
the pre-amendment ladder (invariant: no SQL on the OFF path).

Storage lives in the shared gov.db ``graduated_rules`` table via dedicated
:class:`~stream_manager.message_bus.MessageBus` accessors; this module
owns only the feature flag and the eligibility predicate (the candidate
gate). Graduation is NEVER automatic -- a row is written only on an
explicit operator confirm (M8), enforced at the server endpoint.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids import cycle
    from stream_manager.message_bus import MessageBus

ENV_FLAG = "BRIDGE_GRADUATED_RULES"

# Eligibility thresholds (invariant #6). Config constants, not magic
# literals scattered in the scan; defaults from the BETA proposal.
MIN_ALLOW = 30
MIN_MEAN_CONFIDENCE = 0.95
MAX_OVERRIDE = 0
MAX_BLOCK_EVER = 0


def is_enabled() -> bool:
    """True iff the graduated-rule verdict short-circuit is enabled.

    Default OFF. Mirrors the ``cli_governance.is_enabled()`` convention so
    the engine path stays consistent with the other env-gated levers."""
    return os.environ.get(ENV_FLAG, "").strip().lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class CandidateStats:
    """Per-shape corpus evidence for one graduation candidate.

    ``safety_floor`` MUST be computed by the caller via
    ``governance.is_safety_priority_content`` over ``canonical_text`` --
    keeping the regex source of truth in governance (invariant #2)."""

    shape_hash: str
    canonical_text: str
    n_allow: int
    mean_confidence: float
    n_override: int
    n_block_ever: int
    safety_floor: bool


def is_eligible(stats: CandidateStats) -> bool:
    """Graduation candidate gate (invariants #2 + #6).

    A shape is eligible iff it is proven-routine AND has never touched the
    safety floor. Two INDEPENDENT safety guarantees apply here:

    1. ``not safety_floor`` -- the canonical text never matches a
       safety-priority regex (caller computes via
       ``governance.is_safety_priority_content``; invariant #2).
    2. ``n_block_ever == 0`` -- the corpus never produced a BLOCK for this
       shape.

    Either alone blocks a safety-floor shape from ever being offered.
    """
    return (
        not stats.safety_floor
        and stats.n_block_ever <= MAX_BLOCK_EVER
        and stats.n_override <= MAX_OVERRIDE
        and stats.n_allow >= MIN_ALLOW
        and stats.mean_confidence + 1e-9 >= MIN_MEAN_CONFIDENCE
    )


@dataclass
class GraduatedRuleStore:
    """Engine-side seam for the operator-confirmed graduated-ALLOW table.

    Holds a MessageBus reference. The hot-path :meth:`lookup` gates on the
    ``BRIDGE_GRADUATED_RULES`` env flag and never touches the bus when OFF.
    The store does NOT decide eligibility or write rules autonomously --
    graduation is an explicit operator-confirmed server action (M8). The
    confirm/demote/list passthroughs are management operations and are NOT
    env-gated (they manage the table; only the verdict-ladder lookup is).
    """

    bus: MessageBus

    def lookup(self, shape_hash: str) -> dict[str, object] | None:
        """Hot-path verdict-ladder lookup: the active graduated rule for
        ``shape_hash``, or None.

        Checks the feature flag FIRST and returns None WITHOUT touching the
        bus when OFF -- zero SQL on the OFF path; the ladder is byte-for-byte
        unchanged."""
        if not is_enabled():
            return None
        return self.bus.lookup_graduated_rule(shape_hash)

    def graduate(
        self, shape_hash: str, canonical_text: str,
        confirmed_ts: float, n_allow_at_grad: int,
    ) -> None:
        """Persist one operator-confirmed graduation. The CALLER guarantees
        this is an explicit operator confirm (M8 -- never auto)."""
        self.bus.insert_graduated_rule(
            shape_hash, canonical_text, confirmed_ts, n_allow_at_grad)

    def demote(self, shape_hash: str) -> bool:
        """Reverse a graduation (active 1 -> 0). Returns True if demoted."""
        return self.bus.demote_graduated_rule(shape_hash)

    def is_graduated(self, shape_hash: str) -> bool:
        """True iff an ACTIVE graduated rule exists (ungated -- management
        read used by the candidate scan to exclude already-graduated shapes)."""
        return self.bus.lookup_graduated_rule(shape_hash) is not None

    def list_active(self) -> list[dict[str, object]]:
        return self.bus.list_graduated_rules(active_only=True)
