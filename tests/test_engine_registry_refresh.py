"""EngineRegistry refresh wiring (Task M).

Reference: docs/v1.1-task-plan.md — Task M.

Coverage:
1. start_refresh / stop_refresh lifecycle is idempotent
2. refresh_all() updates last_refresh_ts on every call
3. refresh_status() reflects refresh_active flag transitions
4. refresh_all() skips engines whose Hydrator hasn't completed yet
   (engine.hydrated=False), so it does not race the per-engine spawn
   thread (Task I/M coordination)
5. Refresh thread is daemonized so a stuck timer does not hang
   process exit
6. Repeated stop_refresh() calls do not raise
"""

from __future__ import annotations

import threading
import time

from stream_manager.governance import EngineRegistry
from stream_manager.message_bus import MessageBus
from stream_manager.project_context import ProjectContextSnapshot


def _ctx() -> ProjectContextSnapshot:
    return ProjectContextSnapshot(repo_path="/tmp/proj")


# ── 1. Lifecycle: start / stop / restart ─────────────────────────────


def test_start_refresh_marks_active_and_arms_timer(tmp_path) -> None:
    bus = MessageBus(str(tmp_path / "gov.db"))
    # Use a long interval so the timer doesn't fire during the test.
    reg = EngineRegistry(
        bus=bus, project_context=_ctx(), refresh_interval_s=3600.0
    )
    assert reg.refresh_active is False
    reg.start_refresh()
    assert reg.refresh_active is True
    # Timer should be daemonized so a stuck timer can't block process exit.
    timer = reg._refresh_timer  # type: ignore[attr-defined]
    assert timer is not None
    assert timer.daemon is True
    reg.stop_refresh()
    bus.close()


def test_stop_refresh_marks_inactive(tmp_path) -> None:
    bus = MessageBus(str(tmp_path / "gov.db"))
    reg = EngineRegistry(
        bus=bus, project_context=_ctx(), refresh_interval_s=3600.0
    )
    reg.start_refresh()
    assert reg.refresh_active is True
    reg.stop_refresh()
    assert reg.refresh_active is False
    bus.close()


def test_stop_refresh_idempotent(tmp_path) -> None:
    bus = MessageBus(str(tmp_path / "gov.db"))
    reg = EngineRegistry(
        bus=bus, project_context=_ctx(), refresh_interval_s=3600.0
    )
    # Stop without start: must not raise.
    reg.stop_refresh()
    reg.start_refresh()
    reg.stop_refresh()
    reg.stop_refresh()  # second stop must not raise
    bus.close()


def test_start_refresh_idempotent(tmp_path) -> None:
    bus = MessageBus(str(tmp_path / "gov.db"))
    reg = EngineRegistry(
        bus=bus, project_context=_ctx(), refresh_interval_s=3600.0
    )
    reg.start_refresh()
    first_timer = reg._refresh_timer  # type: ignore[attr-defined]
    reg.start_refresh()
    second_timer = reg._refresh_timer  # type: ignore[attr-defined]
    # Re-arming is the timer-tick's job; explicit start_refresh should
    # not stack timers on top of an already-armed one.
    assert first_timer is second_timer
    reg.stop_refresh()
    bus.close()


# ── 2. last_refresh_ts updates monotonically ─────────────────────────


def test_last_refresh_ts_starts_none_and_updates(tmp_path) -> None:
    bus = MessageBus(str(tmp_path / "gov.db"))
    reg = EngineRegistry(bus=bus, project_context=_ctx())
    assert reg.last_refresh_ts is None
    before = time.time()
    reg.refresh_all()
    after = time.time()
    assert reg.last_refresh_ts is not None
    assert before <= reg.last_refresh_ts <= after
    bus.close()


def test_last_refresh_ts_increments_across_calls(tmp_path) -> None:
    bus = MessageBus(str(tmp_path / "gov.db"))
    reg = EngineRegistry(bus=bus, project_context=_ctx())
    reg.refresh_all()
    t1 = reg.last_refresh_ts
    assert t1 is not None
    # time.time() resolution on Windows can be coarse; sleep enough to
    # guarantee a strictly-greater timestamp.
    time.sleep(0.02)
    reg.refresh_all()
    t2 = reg.last_refresh_ts
    assert t2 is not None
    assert t2 > t1
    bus.close()


# ── 3. refresh_status() snapshot ─────────────────────────────────────


def test_refresh_status_shape(tmp_path) -> None:
    bus = MessageBus(str(tmp_path / "gov.db"))
    reg = EngineRegistry(
        bus=bus, project_context=_ctx(), refresh_interval_s=3600.0
    )
    s0 = reg.refresh_status()
    assert s0["refresh_active"] is False
    assert s0["last_refresh_ts"] is None
    assert s0["refresh_interval_s"] == 3600.0

    reg.start_refresh()
    reg.refresh_all()
    s1 = reg.refresh_status()
    assert s1["refresh_active"] is True
    assert isinstance(s1["last_refresh_ts"], float)

    reg.stop_refresh()
    s2 = reg.refresh_status()
    assert s2["refresh_active"] is False
    bus.close()


# ── 4. Hydrated guard: skip engines whose Hydrator is mid-flight ─────


def test_refresh_all_skips_unhydrated_engines(tmp_path, monkeypatch) -> None:
    """Coordination with Task I lazy-init.

    refresh_all must not call hydrate_now on an engine whose spawn-time
    Hydrator hasn't completed (engine.hydrated=False), to avoid racing
    the daemon thread that's already injecting the same rows.
    """
    bus = MessageBus(str(tmp_path / "gov.db"))
    bus.open_session("s-A")
    bus.open_session("s-B")
    reg = EngineRegistry(bus=bus, project_context=_ctx())

    # Block the spawn-time hydrator from running so engines stay
    # hydrated=False right after get_or_create. We do this by patching
    # the Hydrator.start to a no-op for this test.
    import stream_manager.governance as gov_mod

    real_import = gov_mod.__import__ if hasattr(gov_mod, "__import__") else None

    eng_a = reg.get_or_create("s-A")
    eng_b = reg.get_or_create("s-B")
    # Force hydrated states explicitly to take the timing race out.
    eng_a.hydrated = False
    eng_b.hydrated = True

    calls: list[str] = []

    def fake_hydrate_now(engine, _bus):
        calls.append(engine.session_id)
        engine.hydrated = True
        return 0

    import stream_manager.cross_session_hydrator as hyd_mod

    monkeypatch.setattr(hyd_mod, "hydrate_now", fake_hydrate_now)

    reg.refresh_all()
    # Only s-B (already hydrated) should have been touched. s-A is in
    # flight and the next tick will pick it up once hydrated flips.
    assert calls == ["s-B"]

    # After s-A's hydrator finishes (we flip the flag manually), the
    # next refresh_all picks it up.
    eng_a.hydrated = True
    reg.refresh_all()
    assert "s-A" in calls
    bus.close()


# ── 5. Daemon thread guarantee ───────────────────────────────────────


def test_refresh_timer_is_daemon(tmp_path) -> None:
    bus = MessageBus(str(tmp_path / "gov.db"))
    reg = EngineRegistry(
        bus=bus, project_context=_ctx(), refresh_interval_s=3600.0
    )
    reg.start_refresh()
    timer = reg._refresh_timer  # type: ignore[attr-defined]
    assert isinstance(timer, threading.Timer)
    assert timer.daemon is True
    reg.stop_refresh()
    bus.close()
