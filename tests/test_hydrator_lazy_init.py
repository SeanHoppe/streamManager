"""Hydrator lazy-init (Task I, v1.1).

Task I moved the cross-session Hydrator off of ``EngineRegistry.get_or_create``:
the daemon thread is now spawned on the first ``evaluate()`` call, not at
construction. These tests pin the contract:

1. ``get_or_create`` does NOT block on Hydrator completion (it must not even
   trigger the Hydrator at all — engine.hydrated must remain False).
2. After the first ``evaluate()``, ``engine.hydrated`` transitions
   ``False → True`` within a bounded time.
3. The lazy spawn happens at most once per engine — repeated evaluate()
   calls do not spawn additional Hydrator threads.
4. The cross-session patterns the Hydrator was supposed to inject DO end
   up in the engine's graph (correctness regression guard for Task F).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from stream_manager import cross_session_hydrator as _hydrator_mod
from stream_manager.governance import EngineRegistry
from stream_manager.message_bus import MessageBus
from stream_manager.messages import Message
from stream_manager.project_context import load

_BOUNDED_TIME_S = 2.0


def _registry(tmp_path: Path) -> EngineRegistry:
    snap = load(tmp_path)
    bus = MessageBus(str(tmp_path / "gov.db"))
    return EngineRegistry(bus=bus, project_context=snap)


def _seed_cross_session_pattern(bus: MessageBus, hash_: str) -> None:
    """Insert a cross_session=1 row directly so Hydrator has work to do."""
    with bus._lock:  # type: ignore[attr-defined]
        bus._conn.execute(  # type: ignore[attr-defined]
            "INSERT OR REPLACE INTO patterns "
            "(hash, level, occurrences, success_rate, last_seen, payload, cross_session) "
            "VALUES (?, ?, ?, ?, ?, ?, 1)",
            (hash_, 1, 0, 0.0, time.time(), "seed pattern payload"),
        )


def _wait_until(predicate, timeout_s: float, interval_s: float = 0.01) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval_s)
    return False


def test_get_or_create_does_not_spawn_hydrator(tmp_path: Path) -> None:
    """get_or_create must NOT spawn the Hydrator — that's the lazy contract."""
    spawn_count = [0]
    original_start = _hydrator_mod.Hydrator.start

    def counting_start(self):  # type: ignore[no-untyped-def]
        spawn_count[0] += 1
        return original_start(self)

    _hydrator_mod.Hydrator.start = counting_start  # type: ignore[assignment]
    try:
        reg = _registry(tmp_path)
        eng = reg.get_or_create("s-A")
        # Construction-only: no evaluate() yet, so no spawn yet.
        assert spawn_count[0] == 0, (
            "EngineRegistry.get_or_create must not spawn the Hydrator; "
            "it should be lazy (Task I v1.1)."
        )
        assert eng.hydrated is False
    finally:
        _hydrator_mod.Hydrator.start = original_start  # type: ignore[assignment]


def test_first_evaluate_spawns_hydrator_and_flips_hydrated(tmp_path: Path) -> None:
    """First evaluate() must trigger Hydrator and engine.hydrated → True."""
    reg = _registry(tmp_path)
    bus = reg._bus  # type: ignore[attr-defined]
    assert bus is not None
    _seed_cross_session_pattern(bus, "h-lazy-1")
    eng = reg.get_or_create("s-A")
    assert eng.hydrated is False, "pre-evaluate engine must report hydrated=False"

    # First evaluate -- triggers lazy spawn. Since the Hydrator thread is
    # daemon=True it may set engine.hydrated either before or after
    # evaluate() returns; we only require the bounded post-call latch.
    eng.evaluate(Message.new(role="user", content="ls"))

    assert _wait_until(lambda: eng.hydrated is True, _BOUNDED_TIME_S), (
        f"engine.hydrated did not transition False -> True within "
        f"{_BOUNDED_TIME_S}s after first evaluate()"
    )

    # Cross-session pattern landed in the graph at L1 advisory level.
    assert "h-lazy-1" in eng.graph.patterns, (
        "Hydrator must inject the cross_session=1 pattern into the graph"
    )


def test_lazy_spawn_at_most_once(tmp_path: Path) -> None:
    """Subsequent evaluate() calls must not spawn additional Hydrators."""
    spawn_count = [0]
    original_start = _hydrator_mod.Hydrator.start

    def counting_start(self):  # type: ignore[no-untyped-def]
        spawn_count[0] += 1
        return original_start(self)

    _hydrator_mod.Hydrator.start = counting_start  # type: ignore[assignment]
    try:
        reg = _registry(tmp_path)
        eng = reg.get_or_create("s-A")
        eng.evaluate(Message.new(role="user", content="ls"))
        eng.evaluate(Message.new(role="user", content="git status"))
        eng.evaluate(Message.new(role="user", content="pytest"))
        assert spawn_count[0] == 1, (
            f"Hydrator spawned {spawn_count[0]} times; expected exactly 1 "
            f"(lazy one-shot semantics)"
        )
    finally:
        _hydrator_mod.Hydrator.start = original_start  # type: ignore[assignment]


def test_get_or_create_is_non_blocking_under_slow_hydrator(tmp_path: Path) -> None:
    """get_or_create must return without waiting on Hydrator work.

    Wraps Hydrator.run() to sleep for a bounded interval; the contract is
    that get_or_create returns essentially instantly because the Hydrator
    is not spawned during construction at all (Task I v1.1).
    """
    sleep_s = 0.5
    original_run = _hydrator_mod.Hydrator.run
    barrier = threading.Event()

    def slow_run(self):  # type: ignore[no-untyped-def]
        # Wait until the test releases the barrier — proves
        # get_or_create() did not block on this thread.
        barrier.wait(timeout=2.0)
        return original_run(self)

    _hydrator_mod.Hydrator.run = slow_run  # type: ignore[assignment]
    try:
        reg = _registry(tmp_path)
        t0 = time.perf_counter()
        eng = reg.get_or_create("s-A")
        construct_s = time.perf_counter() - t0
        assert construct_s < sleep_s, (
            f"get_or_create took {construct_s*1000:.1f} ms; the Hydrator "
            f"must NOT run inline."
        )

        # Now trigger the first evaluate (which spawns the Hydrator) and
        # confirm the call itself returns promptly even though the Hydrator
        # is intentionally blocked on the barrier.
        t1 = time.perf_counter()
        eng.evaluate(Message.new(role="user", content="ls"))
        eval_s = time.perf_counter() - t1
        assert eval_s < sleep_s, (
            f"evaluate() blocked for {eval_s*1000:.1f} ms; the Hydrator "
            f"thread must not block the hot path."
        )

        # Release the barrier so the Hydrator can finish; it should flip
        # engine.hydrated within a short bounded time.
        barrier.set()
        assert _wait_until(lambda: eng.hydrated is True, _BOUNDED_TIME_S)
    finally:
        _hydrator_mod.Hydrator.run = original_run  # type: ignore[assignment]
        barrier.set()


def test_no_hydrator_when_bus_is_none(tmp_path: Path) -> None:
    """Constructing an EngineRegistry without a bus should not crash and
    must not attempt to spawn a Hydrator on evaluate()."""
    snap = load(tmp_path)
    reg = EngineRegistry(bus=None, project_context=snap)
    eng = reg.get_or_create("s-A")
    # Should not raise. engine.hydrated may stay False forever — that's fine.
    eng.evaluate(Message.new(role="user", content="ls"))
    assert eng.hydrated is False
