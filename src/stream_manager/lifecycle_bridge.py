"""Claude Code lifecycle bridge — Task C (v1.2).

Surfaces Claude Code background jobs (`BG <id>`) and `Agent(...)` subagent
spawns into SM's MessageBus so the dashboard can show them.

Design notes
------------

Claude Code's stable hook surface today exposes ``UserPromptSubmit`` and
``TaskOutput`` only — neither carries explicit ``BackgroundJobStart`` /
``AgentSpawn`` lifecycle events. Rather than block on an upstream feature
request, this module takes the **shim path** documented in the task brief:

* It exposes a programmatic ingress (``on_bg_job_start`` / ``on_bg_job_end``
  / ``on_agent_spawn`` / ``on_agent_done``) that any caller wired up to a
  future hook stream — or a unit test simulating one — can drive directly.
* It also provides an optional polling worker (``HookFolderPoller``) that
  scans the Claude Code projects directory
  (``~/.claude/projects/<slug>/*.jsonl``) for tool-call records that look
  like background bashes or ``Task(...)`` subagent invocations and
  synthesises lifecycle envelopes from them. This is the durable path until
  Claude Code ships first-class lifecycle hooks.

Output contract
---------------

Every lifecycle event published via this bridge becomes a single
``MessageBus`` row with:

* ``type = "lifecycle"`` (so existing subscribers can ignore it cheaply)
* ``direction = "inbound"``
* ``content = job/agent identifier`` (human-readable)
* ``metadata.event_type ∈ {bg_job_start, bg_job_end, agent_spawn, agent_done}``
* ``metadata.job_id`` / ``metadata.agent_id``
* ``metadata.track_only = True`` — flag used by the governance engine to
  short-circuit before any L1/L2/L3/L4 routing. The engine only sees the
  lifecycle row if its subscribe-filter mistakenly forwards it; the flag
  is the second line of defence so the bridge never burns L4 quota on
  itself (DOD §3).

No governance decision is recorded for lifecycle envelopes. ``track_only``
is asserted by the unit tests in ``tests/test_lifecycle_bridge.py``.
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import-time only
    from stream_manager.message_bus import MessageBus

log = logging.getLogger(__name__)

# Public event_type constants. Anyone consuming the bus (dashboard, test
# fixtures, downstream tools) should compare against these — don't inline
# string literals.
EVENT_BG_JOB_START = "bg_job_start"
EVENT_BG_JOB_END = "bg_job_end"
EVENT_AGENT_SPAWN = "agent_spawn"
EVENT_AGENT_DONE = "agent_done"

LIFECYCLE_EVENT_TYPES = frozenset(
    {
        EVENT_BG_JOB_START,
        EVENT_BG_JOB_END,
        EVENT_AGENT_SPAWN,
        EVENT_AGENT_DONE,
    }
)

# All bus rows authored by this bridge use a single ``type`` value so the
# dashboard's read-side query (``/api/lifecycle/jobs``) is one indexed
# lookup, and so existing decision-stream subscribers can filter the
# bridge out cheaply.
BUS_TYPE = "lifecycle"

# Shim-poll cadence. 0.5s gives the dashboard sub-2s reaction time
# (DOD §1/§2) with negligible CPU overhead.
DEFAULT_POLL_S = 0.5


@dataclass
class LifecycleEnvelope:
    """In-memory view of a single lifecycle event before it hits the bus.

    Kept narrow on purpose: the bus row is the source of truth, this
    dataclass is only used by tests and by the shim poller's dedup cache.
    """

    event_type: str
    session_id: str
    job_id: str
    name: str
    timestamp: float
    extra: dict[str, object] = field(default_factory=dict)


class LifecycleBridge:
    """Programmatic ingress for Claude Code lifecycle events.

    Callers (a future hook adapter, or the ``HookFolderPoller`` shim
    below) invoke ``on_bg_job_start`` / ``on_bg_job_end`` /
    ``on_agent_spawn`` / ``on_agent_done`` — each method is idempotent on
    ``(event_type, job_id)`` and publishes a single lifecycle row to
    the wired ``MessageBus``.
    """

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus
        # Dedup: track which (event_type, job_id) pairs we've already
        # published. The shim poller can re-emit the same record on a
        # subsequent tick (e.g. after a JSONL truncate-and-rewrite).
        self._seen: set[tuple[str, str]] = set()
        self._lock = threading.Lock()

    # ── BG jobs ────────────────────────────────────────────────────

    def on_bg_job_start(
        self,
        session_id: str,
        job_id: str,
        name: str = "",
        extra: dict[str, object] | None = None,
    ) -> bool:
        """Publish a BG-job-start envelope. Returns True on first publish."""
        return self._publish(
            EVENT_BG_JOB_START, session_id, job_id, name, extra
        )

    def on_bg_job_end(
        self,
        session_id: str,
        job_id: str,
        name: str = "",
        exit_code: int | None = None,
        extra: dict[str, object] | None = None,
    ) -> bool:
        """Publish a BG-job-end envelope. Returns True on first publish."""
        merged: dict[str, object] = dict(extra or {})
        if exit_code is not None:
            merged["exit_code"] = int(exit_code)
        return self._publish(
            EVENT_BG_JOB_END, session_id, job_id, name, merged
        )

    # ── Agents ────────────────────────────────────────────────────

    def on_agent_spawn(
        self,
        session_id: str,
        agent_id: str,
        name: str = "",
        extra: dict[str, object] | None = None,
    ) -> bool:
        """Publish an agent-spawn envelope. Returns True on first publish."""
        return self._publish(
            EVENT_AGENT_SPAWN, session_id, agent_id, name, extra
        )

    def on_agent_done(
        self,
        session_id: str,
        agent_id: str,
        name: str = "",
        extra: dict[str, object] | None = None,
    ) -> bool:
        """Publish an agent-done envelope. Returns True on first publish."""
        return self._publish(
            EVENT_AGENT_DONE, session_id, agent_id, name, extra
        )

    # ── Internals ─────────────────────────────────────────────────

    def _publish(
        self,
        event_type: str,
        session_id: str,
        job_id: str,
        name: str,
        extra: dict[str, object] | None,
    ) -> bool:
        if event_type not in LIFECYCLE_EVENT_TYPES:
            raise ValueError(f"unknown lifecycle event_type: {event_type}")
        if not session_id or not job_id:
            raise ValueError("session_id and job_id are required")
        key = (event_type, job_id)
        with self._lock:
            if key in self._seen:
                return False
            self._seen.add(key)
        meta: dict[str, object] = {
            "event_type": event_type,
            "job_id": job_id,
            "name": name,
            # track_only = True is the contractual signal to the
            # governance engine that this row must NOT trigger an L4
            # alignment round-trip (DOD §3, brief §"Governance opt-in").
            "track_only": True,
        }
        if extra:
            meta.update(extra)
        # Lazy import: keeps lifecycle_bridge importable in stub
        # environments where message_bus would pull sqlite3 etc. The
        # circular import guard above (TYPE_CHECKING) gives us types
        # without a runtime cost.
        from stream_manager.message_bus import Message

        msg = Message.new(
            session_id=session_id,
            type=BUS_TYPE,
            direction="inbound",
            content=name or job_id,
            metadata=meta,
        )
        try:
            self._bus.publish(msg)
        except Exception:
            log.exception("lifecycle_bridge: bus.publish failed")
            # Roll back the dedup so a later retry can succeed.
            with self._lock:
                self._seen.discard(key)
            return False
        return True


# ──────────────────────────────────────────────────────────────────────
# Optional shim: poll Claude Code's projects/<slug>/*.jsonl files for
# tool-call records that look like ``Bash(... &)`` background jobs or
# ``Task(...)`` subagent invocations and synthesise lifecycle envelopes
# from them. This is the durable path until upstream lifecycle hooks
# land. Driven by ``LifecycleBridge.on_*`` so the publish contract is
# the same as the programmatic path.
# ──────────────────────────────────────────────────────────────────────


def _record_event_type(rec: dict) -> str | None:
    """Map a Claude Code JSONL record to a lifecycle event_type, or None.

    The JSONL schema is upstream-controlled and not perfectly stable; we
    look for the smallest pattern that disambiguates BG jobs from Task
    spawns. ``message.content[*].name`` is the conventional Anthropic
    tool-use name for either Bash or Task. ``stop_reason`` / ``status``
    fields signal completion.
    """
    try:
        tool_name = ""
        msg = rec.get("message") or {}
        content_list = msg.get("content")
        if isinstance(content_list, list):
            for blk in content_list:
                if isinstance(blk, dict) and blk.get("type") == "tool_use":
                    tool_name = str(blk.get("name") or "")
                    break
        if not tool_name:
            tool_name = str(rec.get("tool_name") or "")
        is_completion = bool(
            rec.get("stopReason")
            or rec.get("stop_reason")
            or rec.get("status") == "completed"
            or rec.get("type") == "tool_result"
        )
        if tool_name in {"Bash", "BashOutput"} and rec.get("background"):
            return EVENT_BG_JOB_END if is_completion else EVENT_BG_JOB_START
        if tool_name == "Task":
            return EVENT_AGENT_DONE if is_completion else EVENT_AGENT_SPAWN
    except Exception:  # pragma: no cover - defensive
        log.debug("lifecycle_bridge: failed to classify record", exc_info=True)
    return None


def _record_job_id(rec: dict) -> str:
    """Stable id for a JSONL lifecycle record. Prefer explicit pid/uuid."""
    for key in ("pid", "task_id", "agent_id", "id", "uuid"):
        v = rec.get(key)
        if v:
            return str(v)
    msg = rec.get("message") or {}
    if isinstance(msg, dict):
        v = msg.get("id")
        if v:
            return str(v)
    return ""


def _record_name(rec: dict) -> str:
    """Human-readable label for the dashboard row."""
    msg = rec.get("message") or {}
    content_list = (msg.get("content") if isinstance(msg, dict) else None) or []
    if isinstance(content_list, list):
        for blk in content_list:
            if isinstance(blk, dict) and blk.get("type") == "tool_use":
                inp = blk.get("input") or {}
                if isinstance(inp, dict):
                    return str(
                        inp.get("description")
                        or inp.get("command")
                        or blk.get("name")
                        or ""
                    )[:200]
    return str(rec.get("name") or rec.get("description") or "")[:200]


class HookFolderPoller:
    """Poll Claude Code's projects/<slug>/*.jsonl for lifecycle rows.

    Designed as a thin shim — when upstream Claude Code ships first-class
    BackgroundJobStart/AgentSpawn hooks, this poller becomes redundant
    and can be retired without touching ``LifecycleBridge``.
    """

    def __init__(
        self,
        bridge: LifecycleBridge,
        session_id: str,
        projects_dir: Path,
        project_slug: str,
        poll_interval_s: float = DEFAULT_POLL_S,
    ) -> None:
        self._bridge = bridge
        self._session_id = session_id
        self._slug_dir = Path(projects_dir) / project_slug
        self._poll = max(0.05, float(poll_interval_s))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._offsets: dict[str, int] = {}
        # Track inode/mtime alongside offset so a truncate-and-rewrite
        # ("rotation") that produces a same-or-larger file is still
        # detected and the offset reset to 0.
        self._stamps: dict[str, tuple[int, float]] = {}

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="lifecycle-bridge-poller",
            daemon=True,
        )
        self._thread.start()

    def stop(self, join_timeout: float = 2.0) -> None:
        self._stop.set()
        t = self._thread
        if t is not None:
            t.join(timeout=join_timeout)
        self._thread = None

    def _run(self) -> None:  # pragma: no cover - covered indirectly
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("lifecycle_bridge poller: tick raised")
            if self._stop.wait(self._poll):
                return

    def tick(self) -> int:
        """Read newly-appended JSONL rows once. Returns # envelopes published.

        Public so tests can drive a deterministic single tick instead of
        relying on the background thread.
        """
        if not self._slug_dir.is_dir():
            return 0
        published = 0
        for path in sorted(self._slug_dir.glob("*.jsonl")):
            published += self._drain_file(path)
        return published

    def _drain_file(self, path: Path) -> int:
        try:
            st = path.stat()
        except OSError:
            return 0
        size = st.st_size
        key = str(path)
        prev_stamp = self._stamps.get(key)
        new_stamp = (int(st.st_ino), float(st.st_mtime))
        offset = self._offsets.get(key, 0)
        if offset > size:
            # File rotated/truncated — re-read from the top.
            offset = 0
        elif prev_stamp is not None and prev_stamp != new_stamp and offset >= size:
            # mtime/inode changed but size didn't grow — likely a
            # truncate-and-rewrite. Re-read from the top.
            offset = 0
        if offset == size and prev_stamp == new_stamp:
            return 0
        published = 0
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                fh.seek(offset)
                for line in fh:
                    if not line.strip():
                        continue
                    with contextlib.suppress(json.JSONDecodeError):
                        rec = json.loads(line)
                        if self._handle_record(rec):
                            published += 1
                self._offsets[key] = fh.tell()
                self._stamps[key] = new_stamp
        except OSError:
            log.exception("lifecycle_bridge: read failed for %s", path)
        return published

    def _handle_record(self, rec: dict) -> bool:
        et = _record_event_type(rec)
        if et is None:
            return False
        job_id = _record_job_id(rec)
        if not job_id:
            return False
        name = _record_name(rec)
        sid = self._session_id
        if et == EVENT_BG_JOB_START:
            return self._bridge.on_bg_job_start(sid, job_id, name)
        if et == EVENT_BG_JOB_END:
            return self._bridge.on_bg_job_end(sid, job_id, name)
        if et == EVENT_AGENT_SPAWN:
            return self._bridge.on_agent_spawn(sid, job_id, name)
        if et == EVENT_AGENT_DONE:
            return self._bridge.on_agent_done(sid, job_id, name)
        return False


# ──────────────────────────────────────────────────────────────────────
# Read-side helper. Used by ``dashboard/server.py`` to render the active
# jobs/agents pane and by tests asserting the round-trip. Read-only; no
# governance side-effects.
# ──────────────────────────────────────────────────────────────────────


def list_active_jobs(
    db_path: str,
    session_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Return open BG jobs + agent spawns from the WAL bus.

    Open == latest envelope for this job_id is a *_start* (no matching
    *_end / *_done observed yet). Newest-start first.
    """
    import sqlite3

    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        sql = (
            "SELECT id, session_id, type, content, metadata, timestamp "
            "FROM messages WHERE type=? "
        )
        params: list[object] = [BUS_TYPE]
        if session_id:
            sql += "AND session_id=? "
            params.append(session_id)
        sql += "ORDER BY timestamp ASC LIMIT ?"
        params.append(int(limit) * 4)  # x4 to allow dedup headroom
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    state: dict[str, dict] = {}
    for r in rows:
        try:
            meta = json.loads(r["metadata"] or "{}")
        except Exception:
            continue
        et = str(meta.get("event_type") or "")
        job_id = str(meta.get("job_id") or "")
        if et not in LIFECYCLE_EVENT_TYPES or not job_id:
            continue
        rec = state.setdefault(
            job_id,
            {
                "job_id": job_id,
                "session_id": r["session_id"],
                "name": meta.get("name") or r["content"] or "",
                "kind": "agent" if et.startswith("agent") else "bg_job",
                "started_at": None,
                "ended_at": None,
                "exit_code": meta.get("exit_code"),
                "status": "running",
            },
        )
        if et in (EVENT_BG_JOB_START, EVENT_AGENT_SPAWN):
            rec["started_at"] = float(r["timestamp"])
        else:
            rec["ended_at"] = float(r["timestamp"])
            rec["status"] = "done"
            if "exit_code" in meta:
                rec["exit_code"] = meta.get("exit_code")
    open_rows = [r for r in state.values() if r["status"] == "running"]
    open_rows.sort(key=lambda d: d.get("started_at") or 0, reverse=True)
    return open_rows[: int(limit)]


def filter_lifecycle(messages: Iterable[dict]) -> list[dict]:
    """Helper for callers iterating bus rows in-memory (e.g. tests)."""
    out: list[dict] = []
    for m in messages:
        if m.get("type") != BUS_TYPE:
            continue
        try:
            meta = m.get("metadata")
            if isinstance(meta, str):
                meta = json.loads(meta)
        except Exception:
            continue
        if (meta or {}).get("event_type") in LIFECYCLE_EVENT_TYPES:
            out.append(m)
    return out


__all__ = [
    "BUS_TYPE",
    "DEFAULT_POLL_S",
    "EVENT_AGENT_DONE",
    "EVENT_AGENT_SPAWN",
    "EVENT_BG_JOB_END",
    "EVENT_BG_JOB_START",
    "HookFolderPoller",
    "LIFECYCLE_EVENT_TYPES",
    "LifecycleBridge",
    "LifecycleEnvelope",
    "filter_lifecycle",
    "list_active_jobs",
]


def _now() -> float:
    """Monotonic-ish time for envelope ordering. Shimmable for tests."""
    return time.time()
