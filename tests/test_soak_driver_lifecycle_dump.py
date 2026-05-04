"""P1 / v1.3: LifecycleBridge `_seen` final-state dump in soak report.

Task C orphan-key invariant was not positively asserted at ship-gate.
The hardening adds a `### Lifecycle bridge final state` heading to
the soak report with explicit orphan counts. The driver consumes
`LifecycleBridge._seen` read-only — no method/field renames.

These tests synthesize bridge state and exercise the formatter
helper directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

import soak_driver  # noqa: E402
from stream_manager.lifecycle_bridge import (  # noqa: E402
    EVENT_AGENT_DONE,
    EVENT_AGENT_SPAWN,
    EVENT_BG_JOB_END,
    EVENT_BG_JOB_START,
    LifecycleBridge,
)
from stream_manager.message_bus import MessageBus  # noqa: E402


def test_empty_bridge_reports_no_orphans() -> None:
    """Clean bridge (`_seen` empty) renders zero-orphan positive assertion."""
    block = "\n".join(soak_driver._format_lifecycle_bridge_final_state(set()))
    assert "### Lifecycle bridge final state" in block
    assert "no orphan start keys (count=0)" in block
    assert "no orphan end keys (count=0)" in block
    assert "ORPHAN" not in block  # no upper-case orphan flag


def test_none_bridge_renders_clean_state() -> None:
    """`None` is treated as the empty-set baseline (driver may not own a bridge)."""
    block = "\n".join(soak_driver._format_lifecycle_bridge_final_state(None))
    assert "### Lifecycle bridge final state" in block
    assert "no orphan start keys" in block
    assert "no orphan end keys" in block


def test_orphan_start_flagged(tmp_path: Path) -> None:
    """A BG-job-start with no matching end must be flagged as an orphan."""
    db = tmp_path / "orphan.db"
    bus = MessageBus(str(db))
    try:
        bus.open_session("sess-1", project_slug="test", pid=0)
        bridge = LifecycleBridge(bus)
        # Synthesize: only a start, no end → orphan start key in `_seen`.
        bridge.on_bg_job_start("sess-1", "job-A", name="long-runner")
        seen = set(bridge._seen)  # read-only consumption
    finally:
        try:
            bus.close()
        except Exception:
            pass

    assert (EVENT_BG_JOB_START, "job-A") in seen
    block = "\n".join(soak_driver._format_lifecycle_bridge_final_state(seen))
    assert "ORPHAN start keys (count=1)" in block, block
    assert "job-A" in block, block
    # Pair landed → no orphan ends.
    assert "no orphan end keys (count=0)" in block, block


def test_paired_bridge_state_clean(tmp_path: Path) -> None:
    """A start+end pair evicts both keys; final-state shows zero orphans."""
    db = tmp_path / "paired.db"
    bus = MessageBus(str(db))
    try:
        bus.open_session("sess-1", project_slug="test", pid=0)
        bridge = LifecycleBridge(bus)
        bridge.on_bg_job_start("sess-1", "job-A", name="X")
        bridge.on_bg_job_end("sess-1", "job-A", name="X", exit_code=0)
        seen = set(bridge._seen)
    finally:
        try:
            bus.close()
        except Exception:
            pass

    # Per LifecycleBridge.on_bg_job_end eviction logic, both keys are
    # discarded once the pair lands.
    assert (EVENT_BG_JOB_START, "job-A") not in seen
    assert (EVENT_BG_JOB_END, "job-A") not in seen
    block = "\n".join(soak_driver._format_lifecycle_bridge_final_state(seen))
    assert "no orphan start keys (count=0)" in block
    assert "no orphan end keys (count=0)" in block


def test_orphan_agent_spawn_flagged() -> None:
    """An `agent_spawn` without `agent_done` is flagged on the start side."""
    seen = {(EVENT_AGENT_SPAWN, "agent-7")}
    block = "\n".join(soak_driver._format_lifecycle_bridge_final_state(seen))
    assert "ORPHAN start keys (count=1)" in block
    assert "agent-7" in block


def test_orphan_end_without_start_flagged() -> None:
    """An end key with no matching start (data corruption / replay bug) is flagged."""
    seen = {(EVENT_AGENT_DONE, "ghost-agent")}
    block = "\n".join(soak_driver._format_lifecycle_bridge_final_state(seen))
    assert "no orphan start keys (count=0)" in block
    assert "ORPHAN end keys (count=1)" in block
    assert "ghost-agent" in block
