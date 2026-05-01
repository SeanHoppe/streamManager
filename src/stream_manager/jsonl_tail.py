"""JSONL tail worker — FR-AR-7.

Tails the newest `*.jsonl` file in `~/.claude/projects/{slug}/` in a
background thread. Parses each new record and:
    1. resolves attribution to an agent profile via AgentRegistry
    2. updates the registry's per-session active profile
    3. upserts the agent row in the WAL bus
    4. emits an `agent_identified` bus event on attribution change
    5. emits a `desktop_pause` bus event on `stopReason=end_turn`

This worker MUST be non-blocking (FR-AR-7): exceptions from JSON parsing,
file IO, or downstream callbacks are logged and swallowed so a stuck
JSONL never blocks WebSocket forwarding.
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
import time
from pathlib import Path

from stream_manager import message_bus as _msg_bus
from stream_manager.agent_registry import AgentRegistry

log = logging.getLogger(__name__)

POLL_INTERVAL_S = 0.5


class JsonlTailWorker:
    def __init__(
        self,
        projects_dir: Path,
        registry: AgentRegistry,
        bus: _msg_bus.MessageBus,
    ) -> None:
        self.projects_dir = Path(projects_dir)
        self.registry = registry
        self.bus = bus
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._session_id: str = ""
        self._project_slug: str = ""
        self._last_attribution: str | None = None

    def start(self, session_id: str, project_slug: str) -> None:
        if self._thread is not None and self._thread.is_alive():
            log.warning("JsonlTailWorker already running; ignoring start()")
            return
        self._session_id = session_id
        self._project_slug = project_slug
        self._last_attribution = None
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"jsonl-tail-{project_slug}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None

    def _newest_jsonl(self) -> Path | None:
        slug_dir = self.projects_dir / self._project_slug
        if not slug_dir.is_dir():
            return None
        try:
            candidates = [p for p in slug_dir.glob("*.jsonl") if p.is_file()]
        except OSError:
            return None
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)

    def _run(self) -> None:
        path: Path | None = None
        fh = None
        try:
            while not self._stop_event.is_set():
                # Re-resolve newest file in case rotation happens.
                newest = self._newest_jsonl()
                if newest is None:
                    if self._stop_event.wait(POLL_INTERVAL_S):
                        break
                    continue
                if newest != path:
                    if fh is not None:
                        with contextlib.suppress(OSError):
                            fh.close()
                    path = newest
                    try:
                        fh = path.open("r", encoding="utf-8", errors="replace")
                        fh.seek(0, 2)  # tail: skip existing content
                    except OSError:
                        log.exception("jsonl_tail: open failed for %s", path)
                        fh = None
                        if self._stop_event.wait(POLL_INTERVAL_S):
                            break
                        continue
                if fh is None:
                    if self._stop_event.wait(POLL_INTERVAL_S):
                        break
                    continue
                line = fh.readline()
                if not line:
                    if self._stop_event.wait(POLL_INTERVAL_S):
                        break
                    continue
                self._process_line(line)
        finally:
            if fh is not None:
                with contextlib.suppress(OSError):
                    fh.close()

    def _process_line(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            log.debug("jsonl_tail: bad JSON line; skipping")
            return
        if not isinstance(record, dict):
            return
        attribution_plugin = str(record.get("attributionPlugin", "") or "")
        attribution_skill = str(record.get("attributionSkill", "") or "")
        is_sidechain = bool(record.get("isSidechain", False))
        stop_reason = str(record.get("stopReason", "") or "")
        session_id_jsonl = str(record.get("sessionId", "") or "")

        if attribution_plugin and attribution_plugin != self._last_attribution:
            try:
                profile = self.registry.resolve(
                    attribution_plugin, attribution_skill, is_sidechain
                )
                self.registry.update_active(self._session_id, profile)
                try:
                    self.bus.upsert_agent(
                        session_id=self._session_id,
                        attribution_plugin=attribution_plugin,
                        attribution_skill=attribution_skill,
                        is_sidechain=is_sidechain,
                        profile_slug=profile.slug,
                    )
                except Exception:
                    log.exception("jsonl_tail: bus.upsert_agent failed")
                try:
                    self.bus.publish(
                        _msg_bus.Message.new(
                            session_id=self._session_id,
                            type="agent_identified",
                            direction="inbound",
                            content=attribution_plugin,
                            metadata={
                                "profile_slug": profile.slug,
                                "is_sidechain": is_sidechain,
                                "attribution_skill": attribution_skill,
                            },
                        )
                    )
                except Exception:
                    log.exception("jsonl_tail: bus.publish(agent_identified) failed")
                self._last_attribution = attribution_plugin
            except Exception:
                log.exception("jsonl_tail: attribution handling failed")

        if stop_reason == "end_turn":
            try:
                self.bus.publish(
                    _msg_bus.Message.new(
                        session_id=self._session_id,
                        type="desktop_pause",
                        direction="inbound",
                        content="end_turn",
                        metadata={
                            "session_id": session_id_jsonl,
                            "ts": time.time(),
                        },
                    )
                )
            except Exception:
                log.exception("jsonl_tail: bus.publish(desktop_pause) failed")
