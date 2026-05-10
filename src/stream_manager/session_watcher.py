"""External session watcher — v1.9 P2.

Read-only observation subsystem for external ``claude -p`` subprocesses.
Discovers active Claude Code sessions via ``~/.claude/sessions/<pid>.json``,
verifies liveness with ``os.kill(pid, 0)``, and emits session-lifecycle
bus envelopes:

* ``external_session_registered`` — first liveness confirmation.
* ``external_session_exited`` — liveness check fails for a previously
  active session.
* ``bg_task_output_ready`` — a tracked background-task output file
  transitions from 0 bytes to non-zero (UC-01 AC-3).

Design constraints (memory references):

* ``feedback_no_self_monitor.md`` — never register SM's own session.
  Skip silently when ``cwd`` resolves to the SM working directory or
  when ``entrypoint`` contains an SM-identifying marker.
* ``feedback_monitoring_live_sessions.md`` — session discovery via
  ``~/.claude/sessions/``, PID liveness via ``os.kill(pid, 0)``,
  0-byte task output file does NOT mean the task is hung; only the
  0 → non-zero transition is reported.
* ``feedback_cassette_must_cover_new_envelopes.md`` — verified: the
  envelope types defined in this module are session-lifecycle only and
  do NOT enter the cassette/soak decision-output path. The cassette
  schema is unchanged.
* ``feedback_cross_pr_seam_review.md`` — the governance hot path
  (``governance.evaluate`` → ``cli_governance`` → decision publish)
  has zero calls into this module. The watcher is a passive observer.

NFR-R6: subscriber/poll exceptions are logged and swallowed; the
watcher daemon thread must never block the dashboard server.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

log = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────

#: Default poll interval for the session-discovery loop (seconds).
SESSION_POLL_INTERVAL_SECONDS = 5.0

#: Default poll interval for background-task-output liveness (seconds).
BG_TASK_POLL_INTERVAL_SECONDS = 30.0

#: Environment variable to override the session-discovery poll interval.
SESSION_WATCHER_POLL_ENV = "BRIDGE_SESSION_WATCHER_POLL_SECS"

#: Environment variable to override the bg-task-output poll interval.
BG_TASK_POLL_ENV = "BRIDGE_SESSION_WATCHER_BG_POLL_SECS"

#: Substrings in ``entrypoint`` that identify SM's own subprocess.
#: Per ``feedback_no_self_monitor.md``: SM must never observe itself.
_SM_ENTRYPOINT_MARKERS = ("stream_manager", "streamManager")

#: Bus envelope type names. Session-lifecycle only — verified absent
#: from ``tools/cassette_record.py`` and ``tools/soak_driver.py``.
ENVELOPE_REGISTERED = "external_session_registered"
ENVELOPE_EXITED = "external_session_exited"
ENVELOPE_BG_READY = "bg_task_output_ready"


# ── State records ──────────────────────────────────────────────────────


@dataclass
class SessionRecord:
    """In-memory record for a discovered external session."""

    sessionId: str
    pid: int
    cwd: str
    entrypoint: str
    registered_at: str
    last_seen: str
    state: Literal["active", "exited"] = "active"


@dataclass
class BgTaskRecord:
    """In-memory record for a tracked background-task token."""

    taskId: str
    output_path: str
    originating_session: str
    start_time: str
    last_size_bytes: int = 0


# ── Helpers ────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat()


def _read_env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        log.warning("session_watcher: invalid %s=%r; using default %s", name, raw, default)
        return default
    if value <= 0:
        return default
    return value


def _pid_alive(pid: int) -> bool:
    """``kill -0 <pid>`` semantics. Returns False on OSError."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    except Exception:  # pragma: no cover — defensive
        log.exception("session_watcher: unexpected error checking pid %s", pid)
        return False
    return True


def _is_self_session(
    cwd: str,
    entrypoint: str,
    sm_cwd: str,
) -> bool:
    """Return True when (cwd, entrypoint) identifies SM's own session.

    Per ``feedback_no_self_monitor.md``: never register a session whose
    working directory is SM's own working directory, or whose entrypoint
    contains an SM-identifying substring. The caller logs at DEBUG, not
    WARNING — these matches are expected during normal operation.
    """
    try:
        if cwd and sm_cwd and Path(cwd).resolve() == Path(sm_cwd).resolve():
            return True
    except (OSError, RuntimeError):
        # Path.resolve can raise on some Windows edge cases; fall through
        # to substring check.
        if cwd == sm_cwd:
            return True
    ep = (entrypoint or "").lower()
    for marker in _SM_ENTRYPOINT_MARKERS:
        if marker.lower() in ep:
            return True
    return False


def _read_session_file(path: Path) -> dict | None:
    """Parse a ``~/.claude/sessions/*.json`` registry file.

    Returns the parsed dict on success, or ``None`` if the file is
    unreadable / unparseable / missing required fields. Required fields:
    ``pid``, ``sessionId``, ``cwd``, ``entrypoint``.
    """
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    required = ("pid", "sessionId", "cwd", "entrypoint")
    if any(k not in data for k in required):
        return None
    try:
        pid = int(data["pid"])
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    return {
        "pid": pid,
        "sessionId": str(data["sessionId"]),
        "cwd": str(data["cwd"]),
        "entrypoint": str(data["entrypoint"]),
    }


def _scan_jsonl_for_bg_tasks(jsonl_path: Path) -> list[dict]:
    """Scan a session JSONL tail for ``backgroundTaskId`` entries.

    Returns a list of dicts with at least ``taskId`` and (when available)
    ``output_path``. Defensive against malformed lines.
    """
    out: list[dict] = []
    try:
        with jsonl_path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line or "backgroundTaskId" not in line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                tokens = _extract_bg_task_tokens(record)
                out.extend(tokens)
    except OSError:
        return out
    return out


def _extract_bg_task_tokens(record: object) -> list[dict]:
    """Recursively walk a parsed JSONL record for ``backgroundTaskId``.

    Returns a list of {"taskId", "output_path"?} dicts. ``output_path``
    is included when the record carries an explicit ``outputPath`` /
    ``output_path`` sibling field.
    """
    found: list[dict] = []

    def _walk(node: object) -> None:
        if isinstance(node, dict):
            if "backgroundTaskId" in node:
                task_id = node.get("backgroundTaskId")
                if isinstance(task_id, str) and task_id:
                    entry: dict = {"taskId": task_id}
                    out_path = node.get("outputPath") or node.get("output_path")
                    if isinstance(out_path, str) and out_path:
                        entry["output_path"] = out_path
                    found.append(entry)
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(record)
    return found


def _derive_bg_output_path(
    task_id: str,
    session_id: str,
    cwd: str,
    explicit: str | None = None,
) -> str:
    """Derive the on-disk task-output path.

    Per ``feedback_monitoring_live_sessions.md`` and UC-01: Claude Code
    stores task output at
    ``$TEMP/claude/<cwd-slug>/<sessionId>/tasks/<token>.output``.
    When the JSONL record carries an explicit ``outputPath``, prefer it.
    """
    if explicit:
        return explicit
    tmp = (
        os.environ.get("TEMP")
        or os.environ.get("TMP")
        or os.environ.get("TMPDIR")
        or "/tmp"
    )
    cwd_slug = (cwd or "").replace("\\", "-").replace("/", "-").strip("-")
    return str(
        Path(tmp) / "claude" / cwd_slug / session_id / "tasks" / f"{task_id}.output"
    )


# ── Watcher ────────────────────────────────────────────────────────────


class SessionWatcher:
    """Daemon-thread session-discovery + bg-task-token watcher.

    Read-only. Polls ``~/.claude/sessions/`` and any session JSONL tails
    for which an active session has been registered. Emits bus envelopes
    via the supplied ``MessageBus`` instance. Self-monitor guard rejects
    SM's own session before any envelope is emitted.

    Thread model: a single daemon thread runs ``_run_loop``. The watcher
    has no API surface beyond ``start()`` / ``stop()`` and read-only
    accessors used by the dashboard for rendering.
    """

    def __init__(
        self,
        bus: object,
        *,
        sessions_dir: Path | None = None,
        sm_cwd: str | None = None,
        sm_session_id: str = "session_watcher",
        poll_interval_s: float | None = None,
        bg_poll_interval_s: float | None = None,
        clock: callable = time.time,  # type: ignore[valid-type]
        pid_alive: callable = _pid_alive,  # type: ignore[valid-type]
    ) -> None:
        self._bus = bus
        self._sessions_dir = (
            sessions_dir
            if sessions_dir is not None
            else Path.home() / ".claude" / "sessions"
        )
        self._sm_cwd = sm_cwd if sm_cwd is not None else str(Path.cwd())
        self._sm_session_id = sm_session_id or "session_watcher"
        self._poll_interval_s = (
            poll_interval_s
            if poll_interval_s is not None
            else _read_env_float(
                SESSION_WATCHER_POLL_ENV, SESSION_POLL_INTERVAL_SECONDS
            )
        )
        self._bg_poll_interval_s = (
            bg_poll_interval_s
            if bg_poll_interval_s is not None
            else _read_env_float(BG_TASK_POLL_ENV, BG_TASK_POLL_INTERVAL_SECONDS)
        )
        self._clock = clock
        self._pid_alive = pid_alive

        self._lock = threading.Lock()
        self._sessions: dict[str, SessionRecord] = {}
        self._bg_tasks: dict[str, BgTaskRecord] = {}
        # Track which (session, taskId) tuples we've already seen so we
        # don't re-extract the same token from a JSONL tail every poll.
        self._seen_bg_tokens: set[tuple[str, str]] = set()
        self._last_bg_poll: float = 0.0

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self) -> None:
        """Spawn the daemon thread. Idempotent."""
        if self._thread is not None and self._thread.is_alive():
            log.debug("session_watcher: already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="session-watcher",
            daemon=True,
        )
        self._thread.start()
        log.info(
            "session_watcher: started (sessions_dir=%s, poll=%.1fs, bg_poll=%.1fs)",
            self._sessions_dir,
            self._poll_interval_s,
            self._bg_poll_interval_s,
        )

    def stop(self, timeout: float = 1.0) -> None:
        """Signal the daemon thread to exit and join briefly."""
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None

    # ── Read-only accessors (dashboard) ───────────────────────────────

    def list_active_sessions(self) -> list[dict]:
        """Snapshot of currently-known sessions for dashboard rendering."""
        with self._lock:
            return [
                {
                    "sessionId": r.sessionId,
                    "pid": r.pid,
                    "cwd": r.cwd,
                    "entrypoint": r.entrypoint,
                    "registered_at": r.registered_at,
                    "last_seen": r.last_seen,
                    "state": r.state,
                }
                for r in self._sessions.values()
            ]

    def build_audit_probe_candidates(
        self,
        *,
        brain_id_filter: str | None = None,
        sm_brain_id: str | None = None,
    ) -> list["AuditProbeCandidate"]:
        """Build frozen candidate list for FR-PPP-1 emit_audit_probe.

        Layer 1 uses ``sessionId`` as ``brain_id`` and empty
        ``prompt_hash``; P2 fills in real digest.

        ``sm_brain_id``: last-line drop of SM's own brain_id (primary
        guard is registration-time ``_is_self_session``).
        ``brain_id_filter``: prefix-include for self-monitor test.

        Skips rows whose ``cwd`` produces an empty ``slug`` — those
        would resolve to ``~/.claude/projects//<sid>.jsonl`` (broken
        path, double-slash) and the operator can never pick them.
        """
        from stream_manager.message_bus import AuditProbeCandidate
        with self._lock:
            snapshot = [
                (r.sessionId, r.cwd, r.last_seen)
                for r in self._sessions.values()
                if r.state == "active"
            ]
        out: list[AuditProbeCandidate] = []
        for session_id, cwd, last_seen in snapshot:
            if sm_brain_id and session_id == sm_brain_id:
                continue
            if brain_id_filter and not session_id.startswith(brain_id_filter):
                continue
            slug = (cwd or "").replace("\\", "-").replace("/", "-").strip("-")
            if not slug:
                continue
            jsonl_path = str(
                Path.home() / ".claude" / "projects" / slug / f"{session_id}.jsonl"
            )
            try:
                ts = _dt.datetime.fromisoformat(last_seen).timestamp()
            except (ValueError, TypeError):
                ts = 0.0
            out.append(
                AuditProbeCandidate(
                    slug=slug,
                    jsonl_path=jsonl_path,
                    brain_id=session_id,
                    last_event_ts=ts,
                    prompt_hash="",
                )
            )
        return out

    def list_pending_bg_tasks(self) -> list[dict]:
        """Snapshot of pending bg-task tokens for dashboard rendering."""
        with self._lock:
            return [
                {
                    "taskId": t.taskId,
                    "output_path": t.output_path,
                    "originating_session": t.originating_session,
                    "start_time": t.start_time,
                    "last_size_bytes": t.last_size_bytes,
                }
                for t in self._bg_tasks.values()
            ]

    # ── Single-tick entrypoints (testable without spawning a thread) ──

    def poll_once(self) -> None:
        """Run a single discovery + liveness pass. Test entrypoint."""
        try:
            self._poll_sessions()
        except Exception:
            log.exception("session_watcher: poll_sessions raised")

    def poll_bg_tasks_once(self) -> None:
        """Run a single bg-task-output liveness pass. Test entrypoint."""
        try:
            self._poll_bg_tasks()
        except Exception:
            log.exception("session_watcher: poll_bg_tasks raised")

    # ── Internal poll loop ────────────────────────────────────────────

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self.poll_once()
            now = self._clock()
            if now - self._last_bg_poll >= self._bg_poll_interval_s:
                self.poll_bg_tasks_once()
                self._last_bg_poll = now
            # Sleep in small slices so stop() returns promptly.
            slept = 0.0
            slice_s = 0.25
            while slept < self._poll_interval_s and not self._stop_event.is_set():
                time.sleep(min(slice_s, self._poll_interval_s - slept))
                slept += slice_s

    # ── Session discovery + liveness ─────────────────────────────────

    def _poll_sessions(self) -> None:
        sessions_dir = self._sessions_dir
        if not sessions_dir.exists():
            # No sessions directory yet — common on a fresh box. Nothing
            # to do, but still run the liveness sweep over already-known
            # sessions so we can mark exits.
            self._sweep_liveness(seen_session_ids=set())
            return

        seen_session_ids: set[str] = set()
        try:
            entries = list(sessions_dir.glob("*.json"))
        except OSError:
            log.exception("session_watcher: failed to list %s", sessions_dir)
            return

        for path in entries:
            data = _read_session_file(path)
            if data is None:
                continue
            session_id = data["sessionId"]
            pid = data["pid"]
            cwd = data["cwd"]
            entrypoint = data["entrypoint"]

            if _is_self_session(cwd, entrypoint, self._sm_cwd):
                log.debug(
                    "session_watcher: skipping self session sessionId=%s "
                    "(cwd=%s entrypoint=%s)",
                    session_id,
                    cwd,
                    entrypoint,
                )
                continue

            if not self._pid_alive(pid):
                # PID file present but process is dead. If we've never
                # registered this session, skip silently. If we *had*
                # registered it, _sweep_liveness below will emit
                # external_session_exited.
                continue

            seen_session_ids.add(session_id)
            with self._lock:
                existing = self._sessions.get(session_id)
                now_iso = _now_iso()
                if existing is None:
                    record = SessionRecord(
                        sessionId=session_id,
                        pid=pid,
                        cwd=cwd,
                        entrypoint=entrypoint,
                        registered_at=now_iso,
                        last_seen=now_iso,
                        state="active",
                    )
                    self._sessions[session_id] = record
                    emit = True
                else:
                    existing.last_seen = now_iso
                    if existing.state == "exited":
                        # Session re-appeared; treat as a new registration.
                        # Refresh pid/cwd/entrypoint so subsequent liveness
                        # sweeps probe the live process, not the prior dead
                        # one (PR #102 review fix).
                        existing.pid = pid
                        existing.cwd = cwd
                        existing.entrypoint = entrypoint
                        existing.state = "active"
                        existing.registered_at = now_iso
                        emit = True
                    else:
                        emit = False

            if emit:
                self._publish(
                    ENVELOPE_REGISTERED,
                    {
                        "sessionId": session_id,
                        "pid": pid,
                        "cwd": cwd,
                        "entrypoint": entrypoint,
                        "registered_at": now_iso,
                    },
                )

        self._sweep_liveness(seen_session_ids=seen_session_ids)

    def _sweep_liveness(self, *, seen_session_ids: set[str]) -> None:
        """Mark known-active sessions exited when their PID dies."""
        to_emit: list[dict] = []
        with self._lock:
            for session_id, record in list(self._sessions.items()):
                if record.state != "active":
                    continue
                # Either the session JSON file disappeared (not in
                # ``seen_session_ids``) or the PID has died.
                pid_alive = self._pid_alive(record.pid)
                file_present = session_id in seen_session_ids
                if file_present and pid_alive:
                    continue
                exit_iso = _now_iso()
                record.state = "exited"
                record.last_seen = exit_iso
                to_emit.append(
                    {
                        "sessionId": session_id,
                        "pid": record.pid,
                        "exit_time": exit_iso,
                    }
                )
        for payload in to_emit:
            self._publish(ENVELOPE_EXITED, payload)

    # ── Background task token tracking ───────────────────────────────

    def _poll_bg_tasks(self) -> None:
        # First, extract any newly-observed tokens from active sessions'
        # JSONL tails. The JSONL location is derived from the session
        # registry record (cwd + sessionId).
        with self._lock:
            active_snapshot = [
                (r.sessionId, r.cwd)
                for r in self._sessions.values()
                if r.state == "active"
            ]

        for session_id, cwd in active_snapshot:
            jsonl_path = self._derive_jsonl_path(session_id, cwd)
            if jsonl_path is None or not jsonl_path.exists():
                continue
            for token in _scan_jsonl_for_bg_tasks(jsonl_path):
                task_id = token.get("taskId")
                if not task_id:
                    continue
                key = (session_id, task_id)
                if key in self._seen_bg_tokens:
                    continue
                output_path = _derive_bg_output_path(
                    task_id=task_id,
                    session_id=session_id,
                    cwd=cwd,
                    explicit=token.get("output_path"),
                )
                with self._lock:
                    self._seen_bg_tokens.add(key)
                    if task_id not in self._bg_tasks:
                        self._bg_tasks[task_id] = BgTaskRecord(
                            taskId=task_id,
                            output_path=output_path,
                            originating_session=session_id,
                            start_time=_now_iso(),
                            last_size_bytes=0,
                        )

        # Then check size transitions for all tracked tokens.
        ready_payloads: list[dict] = []
        with self._lock:
            tracked = list(self._bg_tasks.values())

        for record in tracked:
            try:
                size = os.path.getsize(record.output_path)
            except OSError:
                # Output file not yet present — that's normal, output is
                # populated only on bg-task-chain exit. Per
                # feedback_monitoring_live_sessions: 0 / missing != hung.
                size = 0
            if size <= 0:
                continue
            with self._lock:
                # Re-check inside lock; another poll could have removed
                # this record already.
                cur = self._bg_tasks.get(record.taskId)
                if cur is None:
                    continue
                if cur.last_size_bytes > 0:
                    # Already reported.
                    continue
                cur.last_size_bytes = size
                ready_payloads.append(
                    {
                        "taskId": cur.taskId,
                        "output_path": cur.output_path,
                        "originating_session": cur.originating_session,
                        "start_time": cur.start_time,
                        "ready_at": _now_iso(),
                    }
                )
                # Remove from pending after emission per spec.
                self._bg_tasks.pop(cur.taskId, None)

        for payload in ready_payloads:
            self._publish(ENVELOPE_BG_READY, payload)

    def _derive_jsonl_path(self, session_id: str, cwd: str) -> Path | None:
        """Locate a session JSONL file.

        UC-01 documents the canonical layout
        ``~/.claude/projects/<cwd-slug>/<sessionId>.jsonl``. As a
        convenience, also fall back to ``<sessions_dir>/<sessionId>.jsonl``
        which is the layout used by some tests / older clients.
        """
        candidates: list[Path] = []
        slug = (cwd or "").replace("\\", "-").replace("/", "-").strip("-")
        candidates.append(
            Path.home() / ".claude" / "projects" / slug / f"{session_id}.jsonl"
        )
        candidates.append(self._sessions_dir / f"{session_id}.jsonl")
        for candidate in candidates:
            if candidate.exists():
                return candidate
        # Return the first candidate so the caller can call .exists() on
        # it cheaply; None reserved for "no plausible location".
        return candidates[0] if candidates else None

    # ── Bus publishing ────────────────────────────────────────────────

    def _publish(self, envelope_type: str, metadata: dict) -> None:
        """Publish a session-lifecycle envelope. NFR-R6: never raise."""
        bus = self._bus
        if bus is None:
            return
        try:
            from stream_manager.message_bus import Message as _BusMessage
        except Exception:
            log.exception("session_watcher: failed to import message_bus.Message")
            return
        try:
            bus.publish(
                _BusMessage.new(
                    session_id=self._sm_session_id,
                    type=envelope_type,
                    direction="internal",
                    content="",
                    metadata=metadata,
                )
            )
        except Exception:
            log.exception("session_watcher: failed to publish %s", envelope_type)


# ── Module-level start helper used by the dashboard ───────────────────

_watcher_singleton: SessionWatcher | None = None
_watcher_lock = threading.Lock()


def start_session_watcher(bus: object) -> SessionWatcher:
    """Lazily construct and start the module-level watcher singleton.

    Called from the dashboard server startup hook. Subsequent calls
    return the existing instance. Safe in the face of repeated startup
    events (FastAPI reload) — ``SessionWatcher.start()`` is idempotent.
    """
    global _watcher_singleton
    with _watcher_lock:
        if _watcher_singleton is None:
            _watcher_singleton = SessionWatcher(bus=bus)
        _watcher_singleton.start()
        return _watcher_singleton


def stop_session_watcher() -> None:
    """Stop the module-level watcher singleton if running."""
    global _watcher_singleton
    with _watcher_lock:
        if _watcher_singleton is None:
            return
        try:
            _watcher_singleton.stop()
        except Exception:
            log.exception("session_watcher: stop raised")
        _watcher_singleton = None


def get_session_watcher() -> SessionWatcher | None:
    """Return the live singleton if any, else ``None``. Read-only."""
    with _watcher_lock:
        return _watcher_singleton


__all__ = [
    "SessionWatcher",
    "SessionRecord",
    "BgTaskRecord",
    "ENVELOPE_REGISTERED",
    "ENVELOPE_EXITED",
    "ENVELOPE_BG_READY",
    "SESSION_POLL_INTERVAL_SECONDS",
    "BG_TASK_POLL_INTERVAL_SECONDS",
    "SESSION_WATCHER_POLL_ENV",
    "BG_TASK_POLL_ENV",
    "start_session_watcher",
    "stop_session_watcher",
    "get_session_watcher",
]
