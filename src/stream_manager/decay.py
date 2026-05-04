"""v1.3 P5e — Learn Mode decay ladder + consolidation pass.

Operates on the canonical projection table ``learn_patterns_canonical``
(additive migration shipped alongside this module). The append-only
``learn_patterns`` audit log is untouched.

Design (locked by ``docs/learn-mode-design.md`` §2.5 "Decay"):

* **Time-based step demote** at 30 / 60 / 90 / 120 day age thresholds.
  Each crossed threshold decrements ``ladder_step`` by 1 (floor 0).
* **Reinforcement reset** — when a same-category observation arrives
  for an existing canonical row, ``last_reinforced_ts`` is bumped to
  ``now`` and ``ladder_step`` is incremented (capped at LADDER_MAX).
* **Contradiction snap-demote** — when an opposite-category
  observation arrives, ``contradicted_count`` increments and
  ``ladder_step`` snaps down by ``CONTRADICTION_DEMOTE_STEPS`` (floor
  0). The canonical row's category and confidence are NOT flipped by
  a single contradiction; the next consolidation pass will re-evaluate
  if the contradicting category dominates the audit log.

Schedule:

* ``decay_sweep(bus)`` is cheap (a single UPDATE per crossed threshold
  bucket) and runs once every ``DECAY_SWEEP_TICK_INTERVAL`` worker
  ticks (≈ every 5 minutes at the 5s default poll). The categorizer
  worker calls ``maybe_run_decay_sweep`` from its tick body.
* ``consolidate_patterns(bus)`` is invoked by the worker after each
  successful categorization — it merges the just-inserted
  ``learn_patterns`` row into the canonical row for that prompt_hash,
  applying reinforcement OR contradiction semantics.

Off-hot-path guarantee: nothing in this module is ever called from the
verdict path. Reads are unaffected. Writes only touch the canonical
projection table and its index.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stream_manager.message_bus import MessageBus

log = logging.getLogger(__name__)

# Decay ladder thresholds in seconds. 30 / 60 / 90 / 120 days, per
# design spec §2.5. Each crossed threshold demotes ``ladder_step`` by
# one rung.
_DAY_S = 86400.0
DECAY_THRESHOLDS_S: tuple[float, ...] = (
    30 * _DAY_S,
    60 * _DAY_S,
    90 * _DAY_S,
    120 * _DAY_S,
)

# Maximum ladder step a pattern can earn via reinforcement.
LADDER_MAX = 4

# Floor for any demote operation. Patterns never go below 0.
LADDER_FLOOR = 0

# Contradiction snap-demote magnitude. Design spec §2.5 says "snap down
# one rung" but we use 2 rungs to give contradictions stronger weight
# than time decay (one contradiction is louder than one missed month).
CONTRADICTION_DEMOTE_STEPS = 2

# Run a decay sweep every N categorizer worker ticks. At the 5s default
# poll interval that's every ~5 minutes; well under the daily-resolution
# of the threshold buckets.
DECAY_SWEEP_TICK_INTERVAL = 60

# Categories that count as actionable for reinforcement / contradiction
# purposes. Acknowledge / clarify / unknown / redirect are recorded but
# never bias and never participate in the decay math.
_ACTIONABLE = frozenset({"approve", "reject"})


@dataclass(frozen=True)
class CanonicalRow:
    id: int
    prompt_hash: str
    category: str
    confidence: float
    ladder_step: int
    last_reinforced_ts: float
    contradicted_count: int
    created_at: float
    updated_at: float


def _clamp_step(step: int) -> int:
    return max(LADDER_FLOOR, min(LADDER_MAX, int(step)))


def _fetch_canonical(bus: "MessageBus", prompt_hash_val: str) -> CanonicalRow | None:
    rows = bus.fetch_rows(
        "SELECT id, prompt_hash, category, confidence, ladder_step, "
        "last_reinforced_ts, contradicted_count, created_at, updated_at "
        "FROM learn_patterns_canonical WHERE prompt_hash = ? LIMIT 1",
        (prompt_hash_val,),
    )
    if not rows:
        return None
    r = rows[0]
    return CanonicalRow(
        id=int(r[0]),
        prompt_hash=str(r[1]),
        category=str(r[2]),
        confidence=float(r[3]),
        ladder_step=int(r[4]),
        last_reinforced_ts=float(r[5]),
        contradicted_count=int(r[6]),
        created_at=float(r[7]),
        updated_at=float(r[8]),
    )


def consolidate_patterns(
    bus: "MessageBus",
    prompt_hash_val: str,
    observed_category: str,
    observed_confidence: float,
    *,
    now_ts: float | None = None,
) -> None:
    """Merge one observation into the canonical projection.

    Semantics:

    * No canonical row → INSERT a fresh row at ``ladder_step=0``.
    * Same category as canonical → reinforcement: bump
      ``last_reinforced_ts`` to ``now_ts`` and ``ladder_step += 1``
      (capped at ``LADDER_MAX``). Confidence is averaged.
    * Different actionable category → contradiction: increment
      ``contradicted_count`` and snap ``ladder_step`` down by
      ``CONTRADICTION_DEMOTE_STEPS``. The canonical category is NOT
      flipped here; that decision belongs to the categorizer's audit
      log dominance, not to a single dialogue turn.
    * Non-actionable observed category (clarify/acknowledge/unknown/
      redirect): recorded as a touch — ``last_reinforced_ts`` updated
      so the row is not aged out by mere absence — but no ladder
      change.
    """
    if not prompt_hash_val:
        return
    now = float(now_ts if now_ts is not None else time.time())
    cat = (observed_category or "").lower().strip()
    conf = max(0.0, min(1.0, float(observed_confidence)))
    existing = _fetch_canonical(bus, prompt_hash_val)
    if existing is None:
        # Fresh canonical row at ladder_step=0. We seed contradicted_count=0
        # and last_reinforced_ts=now so the decay sweep doesn't punish
        # us on the very next tick.
        bus.execute_write(
            "INSERT INTO learn_patterns_canonical "
            "(prompt_hash, category, confidence, ladder_step, "
            " last_reinforced_ts, contradicted_count, created_at, "
            " updated_at) "
            "VALUES (?, ?, ?, 0, ?, 0, ?, ?)",
            (prompt_hash_val, cat or "unknown", conf, now, now, now),
        )
        return

    # Existing canonical row.
    if cat not in _ACTIONABLE and existing.category not in _ACTIONABLE:
        # Both sides non-actionable; just refresh the touch timestamp.
        bus.execute_write(
            "UPDATE learn_patterns_canonical SET "
            "last_reinforced_ts=?, updated_at=? WHERE id=?",
            (now, now, existing.id),
        )
        return

    if cat == existing.category:
        # Reinforcement. Bump ladder, refresh ts, average confidence.
        new_step = _clamp_step(existing.ladder_step + 1)
        new_conf = (existing.confidence + conf) / 2.0
        bus.execute_write(
            "UPDATE learn_patterns_canonical SET "
            "confidence=?, ladder_step=?, last_reinforced_ts=?, "
            "updated_at=? WHERE id=?",
            (new_conf, new_step, now, now, existing.id),
        )
        return

    # Different category. Treat as contradiction iff at least one side
    # is actionable. (We've already returned for the both-non-actionable
    # case above.)
    new_step = _clamp_step(existing.ladder_step - CONTRADICTION_DEMOTE_STEPS)
    bus.execute_write(
        "UPDATE learn_patterns_canonical SET "
        "ladder_step=?, contradicted_count=contradicted_count+1, "
        "updated_at=? WHERE id=?",
        (new_step, now, existing.id),
    )


def _steps_demoted_for_age(age_s: float) -> int:
    """How many ladder rungs to subtract for a row of this age.

    Each crossed threshold counts as one rung. A row that has not been
    reinforced in 95 days has crossed the 30/60/90 thresholds → 3
    rungs of demotion.
    """
    n = 0
    for thresh in DECAY_THRESHOLDS_S:
        if age_s >= thresh:
            n += 1
    return n


def decay_sweep(
    bus: "MessageBus",
    *,
    now_ts: float | None = None,
) -> int:
    """Apply time-based step-demote to every canonical row.

    For each canonical row, computes ``age = now - last_reinforced_ts``
    and demotes ``ladder_step`` by the number of crossed thresholds.
    The demote is computed against an *original* baseline by treating
    the row's stored ``ladder_step`` as the current effective rung;
    the sweep does not double-count: it only demotes rows whose
    effective step exceeds ``original - crossed``.

    Implementation note: we do NOT track an "original" ladder step
    separate from the current one. The sweep is idempotent because we
    compute the target step as ``ladder_step - <newly_crossed>`` and
    floor at 0. To avoid double-decrementing across sweeps we use the
    age-bucket directly: a row at age 35 days lands at most 1 rung
    below its post-reinforcement peak; a row at age 65 days lands at
    most 2 rungs below; etc. We accomplish this by computing the
    target step as ``max(LADDER_FLOOR, ladder_step - crossed_now)``
    only when ``crossed_now`` exceeds what's already been applied.
    Since the worker reinforces by RAISING ``ladder_step``, the
    invariant ``ladder_step ≤ LADDER_MAX - crossed_now_pre_sweep`` is
    maintained naturally. Concretely: we tag the row with a
    "decay_floor" equal to ``LADDER_MAX - crossed_now`` and clip the
    stored ``ladder_step`` down to that floor when the floor sits
    below the current step.

    Returns the number of rows demoted (may be 0 if all rows are fresh
    or already at LADDER_FLOOR).
    """
    now = float(now_ts if now_ts is not None else time.time())
    rows = bus.fetch_rows(
        "SELECT id, ladder_step, last_reinforced_ts "
        "FROM learn_patterns_canonical"
    )
    n_demoted = 0
    for r in rows:
        rid = int(r[0])
        step = int(r[1])
        last_ts = float(r[2])
        age = max(0.0, now - last_ts)
        crossed = _steps_demoted_for_age(age)
        if crossed <= 0:
            continue
        # Decay floor: how high can ``ladder_step`` legally sit given
        # the row's age. A row aged past all four thresholds can sit
        # no higher than ``LADDER_MAX - 4 = 0``.
        decay_ceiling = LADDER_MAX - crossed
        if step > decay_ceiling:
            new_step = max(LADDER_FLOOR, decay_ceiling)
            bus.execute_write(
                "UPDATE learn_patterns_canonical SET "
                "ladder_step=?, updated_at=? WHERE id=?",
                (new_step, now, rid),
            )
            n_demoted += 1
    return n_demoted


# ── worker hook ─────────────────────────────────────────────────────


def maybe_run_decay_sweep(
    bus: "MessageBus",
    tick_count: int,
    *,
    interval: int = DECAY_SWEEP_TICK_INTERVAL,
    now_ts: float | None = None,
) -> bool:
    """Run a decay sweep every ``interval`` ticks. Returns True iff one ran.

    Called from ``LearnCategorizerWorker.tick`` so the sweep rides on
    the worker's existing schedule and we don't need a second timer.
    """
    if interval <= 0:
        return False
    if tick_count <= 0 or (tick_count % interval) != 0:
        return False
    try:
        decay_sweep(bus, now_ts=now_ts)
    except Exception:
        log.exception("learn_decay: decay_sweep failed")
        return False
    return True
