"""Tests for v1.3 P5e — Learn Mode decay ladder + consolidation pass.

Covers:

  1. Time-based step demote at 30 / 60 / 90 / 120 day thresholds.
  2. Reinforcement: same-category observation bumps ``ladder_step``
     and refreshes ``last_reinforced_ts``.
  3. Contradiction snap-demote: opposite-category observation
     increments ``contradicted_count`` and snaps ``ladder_step`` down
     by ``CONTRADICTION_DEMOTE_STEPS`` (floor 0).
  4. Worker-level integration: ``LearnCategorizerWorker`` triggers a
     decay sweep on its configured cadence.
  5. Adversarial drift probe contract: rows tagged
     ``true_category=reject`` must never produce a hint above
     ``MIN_BIAS_CONFIDENCE``.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from stream_manager import message_bus as _msg_bus
from stream_manager.decay import (
    CONTRADICTION_DEMOTE_STEPS,
    DECAY_THRESHOLDS_S,
    LADDER_FLOOR,
    LADDER_MAX,
    consolidate_patterns,
    decay_sweep,
    maybe_run_decay_sweep,
)
from stream_manager.learn_categorizer import (
    LearnCategorizerWorker,
    prompt_hash,
)


# ── fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def bus(tmp_path: Path) -> _msg_bus.MessageBus:
    return _msg_bus.MessageBus(str(tmp_path / "decay.db"))


def _seed_canonical(
    bus: _msg_bus.MessageBus,
    *,
    prompt_hash_val: str = "deadbeefdeadbeef",
    category: str = "approve",
    confidence: float = 0.8,
    ladder_step: int = 0,
    last_reinforced_ts: float = 0.0,
    contradicted_count: int = 0,
    now_ts: float | None = None,
) -> int:
    now = float(now_ts if now_ts is not None else time.time())
    bus.execute_write(
        "INSERT INTO learn_patterns_canonical "
        "(prompt_hash, category, confidence, ladder_step, "
        " last_reinforced_ts, contradicted_count, created_at, "
        " updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            prompt_hash_val,
            category,
            confidence,
            ladder_step,
            last_reinforced_ts or now,
            contradicted_count,
            now,
            now,
        ),
    )
    rows = bus.fetch_rows(
        "SELECT id FROM learn_patterns_canonical WHERE prompt_hash=?",
        (prompt_hash_val,),
    )
    return int(rows[0][0])


def _read_canonical(bus: _msg_bus.MessageBus, rid: int) -> dict:
    rows = bus.fetch_rows(
        "SELECT id, prompt_hash, category, confidence, ladder_step, "
        "last_reinforced_ts, contradicted_count "
        "FROM learn_patterns_canonical WHERE id=?",
        (rid,),
    )
    assert rows, f"canonical row {rid} not found"
    r = rows[0]
    return {
        "id": int(r[0]),
        "prompt_hash": str(r[1]),
        "category": str(r[2]),
        "confidence": float(r[3]),
        "ladder_step": int(r[4]),
        "last_reinforced_ts": float(r[5]),
        "contradicted_count": int(r[6]),
    }


# ── schema ──────────────────────────────────────────────────────────


def test_canonical_table_exists(bus: _msg_bus.MessageBus) -> None:
    rows = bus.fetch_rows(
        "SELECT name FROM sqlite_master "
        "WHERE type IN ('table','index') "
        "AND name IN ('learn_patterns_canonical','idx_learn_patterns_canon_hash') "
        "ORDER BY name"
    )
    names = [r[0] for r in rows]
    assert "learn_patterns_canonical" in names
    assert "idx_learn_patterns_canon_hash" in names


def test_canonical_unique_prompt_hash(bus: _msg_bus.MessageBus) -> None:
    """The canonical table must enforce UNIQUE(prompt_hash)."""
    h = prompt_hash("test prompt")
    now = time.time()
    bus.execute_write(
        "INSERT INTO learn_patterns_canonical "
        "(prompt_hash, category, confidence, ladder_step, "
        " last_reinforced_ts, contradicted_count, created_at, updated_at) "
        "VALUES (?, 'approve', 0.9, 1, ?, 0, ?, ?)",
        (h, now, now, now),
    )
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        bus.execute_write(
            "INSERT INTO learn_patterns_canonical "
            "(prompt_hash, category, confidence, ladder_step, "
            " last_reinforced_ts, contradicted_count, created_at, updated_at) "
            "VALUES (?, 'reject', 0.5, 0, ?, 0, ?, ?)",
            (h, now, now, now),
        )


# ── decay math ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "age_days,starting_step,expected_step",
    [
        # Fresh pattern (0 days): no demote.
        (0, 4, 4),
        # 29 days: still inside the first window.
        (29, 4, 4),
        # 31 days: crossed 1 threshold → ceiling=3.
        (31, 4, 3),
        # 61 days: crossed 2 thresholds → ceiling=2.
        (61, 4, 2),
        # 91 days: crossed 3 thresholds → ceiling=1.
        (91, 4, 1),
        # 121 days: crossed 4 thresholds → ceiling=0.
        (121, 4, 0),
        # Already at floor: stays at floor.
        (200, 0, 0),
        # Step already below decay ceiling: untouched.
        (31, 1, 1),
    ],
)
def test_decay_sweep_demotes_to_correct_ceiling(
    bus: _msg_bus.MessageBus,
    age_days: int,
    starting_step: int,
    expected_step: int,
) -> None:
    """Each crossed threshold drops the ladder ceiling by 1."""
    now = 1_700_000_000.0  # fixed epoch for deterministic age math
    last_ts = now - age_days * 86400.0
    rid = _seed_canonical(
        bus,
        prompt_hash_val=f"h_{age_days}_{starting_step}",
        ladder_step=starting_step,
        last_reinforced_ts=last_ts,
        now_ts=last_ts,
    )
    decay_sweep(bus, now_ts=now)
    row = _read_canonical(bus, rid)
    assert row["ladder_step"] == expected_step


def test_decay_sweep_idempotent(bus: _msg_bus.MessageBus) -> None:
    """Running the sweep twice must not double-demote."""
    now = 1_700_000_000.0
    last_ts = now - 35 * 86400.0  # 35d → 1 threshold crossed
    rid = _seed_canonical(
        bus,
        ladder_step=4,
        last_reinforced_ts=last_ts,
        now_ts=last_ts,
    )
    decay_sweep(bus, now_ts=now)
    after_first = _read_canonical(bus, rid)
    decay_sweep(bus, now_ts=now)
    after_second = _read_canonical(bus, rid)
    assert after_first["ladder_step"] == after_second["ladder_step"] == 3


def test_decay_thresholds_match_design_spec() -> None:
    """The 4 thresholds must be 30/60/90/120 days in seconds."""
    expected = (30, 60, 90, 120)
    actual = tuple(int(t / 86400) for t in DECAY_THRESHOLDS_S)
    assert actual == expected


# ── reinforcement ───────────────────────────────────────────────────


def test_reinforcement_bumps_ladder_and_ts(bus: _msg_bus.MessageBus) -> None:
    """A matching observation reinforces (ladder+1, ts→now)."""
    now0 = 1_700_000_000.0
    h = prompt_hash("ship the v1.3 PR")
    rid = _seed_canonical(
        bus,
        prompt_hash_val=h,
        category="approve",
        confidence=0.7,
        ladder_step=2,
        last_reinforced_ts=now0,
        now_ts=now0,
    )
    later = now0 + 35 * 86400.0  # 35d later — pre-reinforce age would have demoted
    consolidate_patterns(bus, h, "approve", 0.9, now_ts=later)
    row = _read_canonical(bus, rid)
    # Reinforcement bumps step by 1, regardless of age.
    assert row["ladder_step"] == 3
    assert row["last_reinforced_ts"] == pytest.approx(later)
    # Confidence is averaged.
    assert row["confidence"] == pytest.approx((0.7 + 0.9) / 2.0)
    # No contradiction.
    assert row["contradicted_count"] == 0


def test_reinforcement_caps_at_ladder_max(bus: _msg_bus.MessageBus) -> None:
    """Reinforcement saturates at LADDER_MAX."""
    h = prompt_hash("recurring approve")
    rid = _seed_canonical(
        bus,
        prompt_hash_val=h,
        category="approve",
        ladder_step=LADDER_MAX,
    )
    consolidate_patterns(bus, h, "approve", 0.95)
    row = _read_canonical(bus, rid)
    assert row["ladder_step"] == LADDER_MAX


def test_consolidate_inserts_new_canonical_row(bus: _msg_bus.MessageBus) -> None:
    """First observation creates a fresh canonical row at step=0."""
    h = prompt_hash("brand new prompt")
    consolidate_patterns(bus, h, "approve", 0.85)
    rows = bus.fetch_rows(
        "SELECT prompt_hash, category, confidence, ladder_step, "
        "contradicted_count FROM learn_patterns_canonical "
        "WHERE prompt_hash=?",
        (h,),
    )
    assert len(rows) == 1
    r = rows[0]
    assert str(r[0]) == h
    assert str(r[1]) == "approve"
    assert float(r[2]) == pytest.approx(0.85)
    assert int(r[3]) == 0
    assert int(r[4]) == 0


# ── contradiction snap-demote ───────────────────────────────────────


def test_contradiction_snap_demotes_and_increments_count(
    bus: _msg_bus.MessageBus,
) -> None:
    """An opposite-category observation snaps step down by N and ++count."""
    h = prompt_hash("approve me please")
    rid = _seed_canonical(
        bus,
        prompt_hash_val=h,
        category="approve",
        confidence=0.9,
        ladder_step=3,
    )
    consolidate_patterns(bus, h, "reject", 0.8)
    row = _read_canonical(bus, rid)
    assert row["ladder_step"] == max(LADDER_FLOOR, 3 - CONTRADICTION_DEMOTE_STEPS)
    assert row["contradicted_count"] == 1
    # Canonical category does NOT flip on a single contradiction.
    assert row["category"] == "approve"


def test_contradiction_floors_at_zero(bus: _msg_bus.MessageBus) -> None:
    """Snap-demote cannot push ladder_step below LADDER_FLOOR."""
    h = prompt_hash("low pattern")
    rid = _seed_canonical(
        bus,
        prompt_hash_val=h,
        category="approve",
        ladder_step=1,
    )
    consolidate_patterns(bus, h, "reject", 0.7)
    row = _read_canonical(bus, rid)
    assert row["ladder_step"] == LADDER_FLOOR


def test_repeated_contradictions_accumulate(bus: _msg_bus.MessageBus) -> None:
    h = prompt_hash("contradicted often")
    rid = _seed_canonical(
        bus,
        prompt_hash_val=h,
        category="approve",
        ladder_step=4,
    )
    consolidate_patterns(bus, h, "reject", 0.7)
    consolidate_patterns(bus, h, "reject", 0.6)
    row = _read_canonical(bus, rid)
    assert row["contradicted_count"] == 2
    # Each contradiction snap-demotes by CONTRADICTION_DEMOTE_STEPS.
    assert row["ladder_step"] == LADDER_FLOOR


# ── worker integration ─────────────────────────────────────────────


def test_worker_runs_decay_sweep_every_n_ticks(bus: _msg_bus.MessageBus) -> None:
    """The worker's tick body invokes decay sweep on the configured cadence."""

    # Seed an aged canonical row that the sweep will demote.
    now = time.time()
    rid = _seed_canonical(
        bus,
        prompt_hash_val="aged_h",
        category="approve",
        ladder_step=4,
        last_reinforced_ts=now - 121 * 86400.0,
        now_ts=now - 121 * 86400.0,
    )
    # Configure a tight decay interval so the sweep fires after 1 tick.
    worker = LearnCategorizerWorker(bus, decay_sweep_interval=1)
    # No pairs in the bus → tick returns 0 but still ticks the counter.
    assert worker.tick() == 0
    row = _read_canonical(bus, rid)
    # 121d aged → all 4 thresholds crossed → ladder must be at floor.
    assert row["ladder_step"] == LADDER_FLOOR


def test_maybe_run_decay_sweep_respects_interval(bus: _msg_bus.MessageBus) -> None:
    now = time.time()
    rid = _seed_canonical(
        bus,
        prompt_hash_val="cadence_h",
        category="approve",
        ladder_step=4,
        last_reinforced_ts=now - 35 * 86400.0,
        now_ts=now - 35 * 86400.0,
    )
    # Tick 1 with interval 5 → no sweep.
    assert maybe_run_decay_sweep(bus, 1, interval=5) is False
    row = _read_canonical(bus, rid)
    assert row["ladder_step"] == 4  # untouched
    # Tick 5 → sweep fires.
    assert maybe_run_decay_sweep(bus, 5, interval=5) is True
    row = _read_canonical(bus, rid)
    assert row["ladder_step"] == 3  # 35d → 1 threshold crossed


# ── adversarial drift probe contract ───────────────────────────────


def test_reject_prompts_never_promote_to_bias(bus: _msg_bus.MessageBus) -> None:
    """A 'reject' canonical row must never satisfy the bias-actionable contract.

    bias_for() (P5d) gates on category in {approve, reject} AND
    confidence >= MIN_BIAS_CONFIDENCE. A 'reject' row is actionable
    (it tells the verdict path "operator typically rejects this") —
    but the adversarial drift probe asserts that no row whose
    canonical category is 'reject' falsely promotes the prompt to an
    'approve' bias.

    Concretely: even a 'reject' row at ladder_step=4, confidence=1.0,
    when surfaced as a BiasHint, MUST carry category='reject', not
    'approve'. The verdict path treats 'reject' as a soft veto.
    """
    import os
    os.environ["SM_LEARN_MODE"] = "1"
    try:
        from stream_manager.learn_categorizer import bias_for
        h = prompt_hash("force push to main please")
        # v1.3 C1: bias_for reads ``learn_patterns_canonical`` (P5e UPSERT
        # projection), not the append-only audit log. Plant the row in
        # canonical so bias_for() can find it.
        _seed_canonical(
            bus,
            prompt_hash_val=h,
            category="reject",
            confidence=0.95,
            ladder_step=4,
        )
        hint = bias_for("force push to main please", bus)
        assert hint is not None
        assert hint.category == "reject"
        # Critically, never 'approve'.
        assert hint.category != "approve"
    finally:
        os.environ.pop("SM_LEARN_MODE", None)


# ── synthesis: pattern at age X with Y reinforcements ───────────────


def test_aged_then_reinforced_round_trip(bus: _msg_bus.MessageBus) -> None:
    """Pattern aged 35 days at ladder_step=2; reinforce → step=3, ts=now."""
    now = time.time()
    h = prompt_hash("aged then reinforced")
    rid = _seed_canonical(
        bus,
        prompt_hash_val=h,
        category="approve",
        confidence=0.7,
        ladder_step=2,
        last_reinforced_ts=now - 35 * 86400.0,
        now_ts=now - 35 * 86400.0,
    )
    consolidate_patterns(bus, h, "approve", 0.8, now_ts=now)
    row = _read_canonical(bus, rid)
    assert row["ladder_step"] == 3
    assert row["last_reinforced_ts"] == pytest.approx(now)


def test_aged_then_contradicted_round_trip(bus: _msg_bus.MessageBus) -> None:
    """Existing approve pattern; contradicting reply → count++ and demote -2."""
    now = time.time()
    h = prompt_hash("aged then contradicted")
    rid = _seed_canonical(
        bus,
        prompt_hash_val=h,
        category="approve",
        confidence=0.85,
        ladder_step=3,
        last_reinforced_ts=now - 10 * 86400.0,
        now_ts=now - 10 * 86400.0,
    )
    consolidate_patterns(bus, h, "reject", 0.7, now_ts=now)
    row = _read_canonical(bus, rid)
    assert row["contradicted_count"] == 1
    assert row["ladder_step"] == max(LADDER_FLOOR, 3 - CONTRADICTION_DEMOTE_STEPS)
