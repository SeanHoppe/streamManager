"""Round-trip tests for the Claude Code lifecycle bridge (Task C, v1.2).

Coverage:

* ``LifecycleBridge.on_*`` publishes a ``type=lifecycle`` row with the
  expected ``event_type`` and ``track_only=True`` metadata.
* The same ``(event_type, job_id)`` is deduped — a second call returns
  ``False`` and does not double-publish.
* ``HookFolderPoller`` synthesises lifecycle envelopes from a Claude
  Code-style JSONL file (the shim path).
* ``list_active_jobs`` returns open BG jobs / agents (start without a
  matching end) and closes them when the *_end* / *_done* row arrives.
* The dashboard's ``/api/lifecycle/jobs`` payload contains the synthesised
  rows — full round-trip from synthetic hook in → bus → API out.
* No governance decision is recorded for a lifecycle row.
"""

from __future__ import annotations

import importlib
import json
import sys

import pytest
from fastapi.testclient import TestClient

from stream_manager.lifecycle_bridge import (
    BUS_TYPE,
    EVENT_AGENT_DONE,
    EVENT_AGENT_SPAWN,
    EVENT_BG_JOB_END,
    EVENT_BG_JOB_START,
    HookFolderPoller,
    LifecycleBridge,
    filter_lifecycle,
    list_active_jobs,
)
from stream_manager.message_bus import MessageBus


# ── unit: programmatic ingress ─────────────────────────────────────────


def test_bg_job_start_publishes_lifecycle_row(tmp_path):
    bus = MessageBus(str(tmp_path / "gov.db"))
    bridge = LifecycleBridge(bus=bus)

    assert bridge.on_bg_job_start("s1", "job-1", name="long soak") is True

    rows = bus._conn.execute(
        "SELECT type, content, metadata FROM messages WHERE session_id=?",
        ("s1",),
    ).fetchall()
    assert len(rows) == 1
    row_type, content, meta_json = rows[0]
    meta = json.loads(meta_json)
    assert row_type == BUS_TYPE
    assert content == "long soak"
    assert meta["event_type"] == EVENT_BG_JOB_START
    assert meta["job_id"] == "job-1"
    assert meta["track_only"] is True
    bus.close()


def test_dedup_returns_false_on_second_publish(tmp_path):
    bus = MessageBus(str(tmp_path / "gov.db"))
    bridge = LifecycleBridge(bus=bus)
    assert bridge.on_agent_spawn("s1", "agent-A", name="cavecrew") is True
    assert bridge.on_agent_spawn("s1", "agent-A", name="cavecrew") is False
    rows = bus._conn.execute(
        "SELECT COUNT(*) FROM messages WHERE session_id=?", ("s1",)
    ).fetchone()
    assert rows[0] == 1
    bus.close()


def test_bg_end_carries_exit_code(tmp_path):
    bus = MessageBus(str(tmp_path / "gov.db"))
    bridge = LifecycleBridge(bus=bus)
    bridge.on_bg_job_start("s1", "job-2")
    bridge.on_bg_job_end("s1", "job-2", exit_code=0)
    rows = bus._conn.execute(
        "SELECT metadata FROM messages WHERE session_id=? ORDER BY sequence",
        ("s1",),
    ).fetchall()
    metas = [json.loads(r[0]) for r in rows]
    assert [m["event_type"] for m in metas] == [EVENT_BG_JOB_START, EVENT_BG_JOB_END]
    assert metas[1]["exit_code"] == 0
    bus.close()


def test_invalid_event_type_raises(tmp_path):
    bus = MessageBus(str(tmp_path / "gov.db"))
    bridge = LifecycleBridge(bus=bus)
    with pytest.raises(ValueError):
        bridge._publish("not_a_real_event", "s1", "j", "", None)
    bus.close()


# ── shim: JSONL polling path ───────────────────────────────────────────


def _bg_jsonl_record(pid: str, command: str, *, completed: bool = False) -> dict:
    """Build a minimal Claude Code-style tool_use record for a Bash &."""
    rec: dict = {
        "pid": pid,
        "background": True,
        "message": {
            "id": f"msg-{pid}",
            "content": [
                {
                    "type": "tool_use",
                    "name": "Bash",
                    "input": {
                        "command": command,
                        "description": command,
                        "run_in_background": True,
                    },
                }
            ],
        },
    }
    if completed:
        rec["status"] = "completed"
    return rec


def _agent_jsonl_record(task_id: str, desc: str, *, completed: bool = False) -> dict:
    rec: dict = {
        "task_id": task_id,
        "message": {
            "id": f"task-msg-{task_id}",
            "content": [
                {
                    "type": "tool_use",
                    "name": "Task",
                    "input": {
                        "description": desc,
                        "subagent_type": "general-purpose",
                    },
                }
            ],
        },
    }
    if completed:
        rec["stopReason"] = "end_turn"
    return rec


def test_poller_synthesizes_lifecycle_from_jsonl(tmp_path):
    bus = MessageBus(str(tmp_path / "gov.db"))
    bridge = LifecycleBridge(bus=bus)
    projects_dir = tmp_path / "projects"
    slug_dir = projects_dir / "myproj"
    slug_dir.mkdir(parents=True)
    jsonl = slug_dir / "session-abc.jsonl"
    jsonl.write_text(
        json.dumps(_bg_jsonl_record("12345", "pytest -q"))
        + "\n"
        + json.dumps(_agent_jsonl_record("t-1", "explore repo"))
        + "\n",
        encoding="utf-8",
    )
    poller = HookFolderPoller(
        bridge=bridge,
        session_id="s-shim",
        projects_dir=projects_dir,
        project_slug="myproj",
    )
    n = poller.tick()
    assert n == 2

    # Append a completion row; second tick must close it out.
    with jsonl.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_bg_jsonl_record("12345", "pytest -q", completed=True)) + "\n")
        fh.write(json.dumps(_agent_jsonl_record("t-1", "explore repo", completed=True)) + "\n")
    n2 = poller.tick()
    assert n2 == 2

    rows = bus._conn.execute(
        "SELECT metadata FROM messages WHERE session_id=? ORDER BY sequence",
        ("s-shim",),
    ).fetchall()
    metas = [json.loads(r[0]) for r in rows]
    types = [m["event_type"] for m in metas]
    assert types == [
        EVENT_BG_JOB_START,
        EVENT_AGENT_SPAWN,
        EVENT_BG_JOB_END,
        EVENT_AGENT_DONE,
    ]
    bus.close()


def test_poller_handles_truncate_and_rewrite(tmp_path):
    """Rotation safety: if the JSONL gets truncated, poller resets offset."""
    bus = MessageBus(str(tmp_path / "gov.db"))
    bridge = LifecycleBridge(bus=bus)
    projects_dir = tmp_path / "projects"
    slug_dir = projects_dir / "myproj"
    slug_dir.mkdir(parents=True)
    jsonl = slug_dir / "session-abc.jsonl"
    # Long enough to make the post-rotation file genuinely smaller, so
    # the offset>size truncate detection trips deterministically across
    # both POSIX and Windows fs mtime granularity.
    jsonl.write_text(
        json.dumps(_bg_jsonl_record("99", "first" + "x" * 200)) + "\n",
        encoding="utf-8",
    )
    poller = HookFolderPoller(
        bridge=bridge,
        session_id="s-rot",
        projects_dir=projects_dir,
        project_slug="myproj",
    )
    assert poller.tick() == 1
    # truncate + rewrite with a new id and a smaller payload.
    jsonl.write_text(
        json.dumps(_bg_jsonl_record("100", "second")) + "\n",
        encoding="utf-8",
    )
    assert poller.tick() == 1
    bus.close()


# ── round-trip: bus → list_active_jobs ─────────────────────────────────


def test_list_active_jobs_only_returns_open(tmp_path):
    db_path = str(tmp_path / "gov.db")
    bus = MessageBus(db_path)
    bridge = LifecycleBridge(bus=bus)
    bridge.on_bg_job_start("s1", "open-1", name="bg open")
    bridge.on_bg_job_start("s1", "closed-1", name="bg done")
    bridge.on_bg_job_end("s1", "closed-1", exit_code=0)
    bridge.on_agent_spawn("s1", "agent-open", name="explorer")

    out = list_active_jobs(db_path, session_id="s1")
    job_ids = {j["job_id"] for j in out}
    assert "open-1" in job_ids
    assert "agent-open" in job_ids
    assert "closed-1" not in job_ids
    # Kind tagging
    for j in out:
        if j["job_id"].startswith("agent"):
            assert j["kind"] == "agent"
        else:
            assert j["kind"] == "bg_job"
    bus.close()


def test_filter_lifecycle_helper(tmp_path):
    bus = MessageBus(str(tmp_path / "gov.db"))
    bridge = LifecycleBridge(bus=bus)
    bridge.on_bg_job_start("s1", "j-1", name="x")
    rows = bus._conn.execute(
        "SELECT type, metadata FROM messages WHERE session_id=?", ("s1",)
    ).fetchall()
    dicts = [{"type": r[0], "metadata": r[1]} for r in rows]
    filtered = filter_lifecycle(dicts)
    assert len(filtered) == 1
    bus.close()


# ── DOD §3: no governance decision is recorded for track_only events ──


def test_lifecycle_row_does_not_record_governance_decision(tmp_path):
    """A lifecycle envelope hitting the bus must NOT cause a decisions row.

    The bridge's contract is: publish to ``messages`` with
    ``track_only=True`` in metadata. Governance code that subscribes to
    the bus is expected to skip ``type=lifecycle`` rows entirely. This
    test asserts the bus state directly — no engine is wired here, so
    any decision count change would mean a contract leak.
    """
    bus = MessageBus(str(tmp_path / "gov.db"))
    before = bus.stats()["decisions"]
    bridge = LifecycleBridge(bus=bus)
    bridge.on_bg_job_start("s1", "soak-1", name="pytest -q")
    bridge.on_bg_job_end("s1", "soak-1", exit_code=0)
    bridge.on_agent_spawn("s1", "ag-1", name="explorer")
    bridge.on_agent_done("s1", "ag-1")
    after = bus.stats()["decisions"]
    assert after == before
    # And four lifecycle rows landed.
    assert bus.stats()["messages"] == 4
    bus.close()


# ── round-trip: dashboard /api/lifecycle/jobs returns synthesised rows ─


@pytest.fixture
def dashboard_client(tmp_path, monkeypatch):
    db = tmp_path / "gov.db"
    monkeypatch.setenv("GOV_DB", str(db))
    if "dashboard.server" in sys.modules:
        del sys.modules["dashboard.server"]
    server = importlib.import_module("dashboard.server")
    bus = MessageBus(str(db))
    server._bus = bus
    client = TestClient(server.app)
    try:
        yield client, bus
    finally:
        bus.close()
        client.close()


def test_dashboard_payload_contains_synthesised_row(dashboard_client):
    client, bus = dashboard_client
    bridge = LifecycleBridge(bus=bus)
    bridge.on_bg_job_start("s-target", "soak-42", name="pytest -q")
    bridge.on_agent_spawn("s-target", "agent-7", name="cavecrew-investigator")

    resp = client.get("/api/lifecycle/jobs?session_id=s-target")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    job_ids = {j["job_id"] for j in body["jobs"]}
    assert {"soak-42", "agent-7"} <= job_ids
    kinds = {j["job_id"]: j["kind"] for j in body["jobs"]}
    assert kinds["soak-42"] == "bg_job"
    assert kinds["agent-7"] == "agent"


def test_dashboard_filters_by_session_id(dashboard_client):
    client, bus = dashboard_client
    bridge = LifecycleBridge(bus=bus)
    bridge.on_bg_job_start("s-A", "job-A1", name="A")
    bridge.on_bg_job_start("s-B", "job-B1", name="B")
    resp_a = client.get("/api/lifecycle/jobs?session_id=s-A")
    resp_b = client.get("/api/lifecycle/jobs?session_id=s-B")
    a_ids = {j["job_id"] for j in resp_a.json()["jobs"]}
    b_ids = {j["job_id"] for j in resp_b.json()["jobs"]}
    assert a_ids == {"job-A1"}
    assert b_ids == {"job-B1"}


def test_dashboard_unscoped_returns_all_open(dashboard_client):
    client, bus = dashboard_client
    bridge = LifecycleBridge(bus=bus)
    bridge.on_bg_job_start("s-A", "job-A1", name="A")
    bridge.on_bg_job_start("s-B", "job-B1", name="B")
    bridge.on_bg_job_end("s-B", "job-B1")
    body = client.get("/api/lifecycle/jobs").json()
    open_ids = {j["job_id"] for j in body["jobs"]}
    assert "job-A1" in open_ids
    assert "job-B1" not in open_ids
