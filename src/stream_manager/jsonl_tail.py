"""JSONL tail worker — FR-AR-7.

Tails the newest `*.jsonl` file in `~/.claude/projects/{slug}/` in a
background thread. Parses each new record and:
    1. resolves attribution to an agent profile via AgentRegistry
    2. updates the registry's per-session active profile
    3. upserts the agent row in the WAL bus
    4. emits an `agent_identified` bus event on attribution change
    5. emits a `desktop_pause` bus event on `stopReason=end_turn`
    6. (v1.3 P5b — Learn Mode) emits `desktop_prompt` for assistant text
       turns and `user_reply` for user text turns, paired via the
       `parentUuid` chain (each `user_reply` carries a `pair_id` linking
       to its preceding `desktop_prompt`). SM-originated turns
       (sessionId == SM_OWN_SESSION_ID) are filtered out at ingest to
       enforce the no-self-monitor rule (memory:
       feedback_no_self_monitor.md).

This worker MUST be non-blocking (FR-AR-7): exceptions from JSON parsing,
file IO, or downstream callbacks are logged and swallowed so a stuck
JSONL never blocks WebSocket forwarding.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
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
        # v1.3 P5b — Learn Mode pairing state. Maps a (Desktop session id,
        # turn uuid) tuple to the `desktop_prompt` envelope id that emitted
        # it, so that the next `user_reply` whose parentUuid points at it
        # can copy that id into its own metadata.pair_id field. Keying by
        # the (session_id_jsonl, uuid) tuple prevents two concurrent
        # Desktop sessions from colliding on a shared uuid namespace.
        # Bounded FIFO trim keeps this from growing without limit on a
        # long-lived tail.
        self._uuid_to_pair: dict[tuple[str, str], str] = {}
        self._pair_cache_max = 2048
        # v1.3 P5b — cached at start(); see start() docstring.
        self._sm_own_session_id: str = ""

    def start(self, session_id: str, project_slug: str) -> None:
        """Start the tail worker.

        Caches ``SM_OWN_SESSION_ID`` from the environment once at start
        time (used by ``_is_sm_originated`` to filter SM-self transcripts
        per ``feedback_no_self_monitor.md``). The operator is responsible
        for setting this env var before invoking ``start()`` — if it is
        unset or empty at start time, no SM-self filtering will be
        applied for the lifetime of this worker.
        """
        if self._thread is not None and self._thread.is_alive():
            log.warning("JsonlTailWorker already running; ignoring start()")
            return
        self._session_id = session_id
        self._project_slug = project_slug
        self._last_attribution = None
        self._sm_own_session_id = (
            os.environ.get("SM_OWN_SESSION_ID") or ""
        ).strip()
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

        # ── v1.3 P5b — Learn Mode dialogue ingest ────────────────────
        # Extract Desktop ↔ user dialogue turns and emit:
        #   - assistant text → messages.type='desktop_prompt'
        #   - user text     → messages.type='user_reply' (with pair_id
        #                     linking to the parent desktop_prompt)
        # SM-originated turns (sessionId == SM_OWN_SESSION_ID) are
        # filtered out to enforce the no-self-monitor rule.
        try:
            self._maybe_emit_learn_mode(record, session_id_jsonl)
        except Exception:
            log.exception("jsonl_tail: learn-mode emit failed")

    # ── v1.3 P5b — Learn Mode helpers ───────────────────────────────

    @staticmethod
    def _extract_text(message: object) -> str:
        """Return the joined text content of a Desktop transcript message.

        Desktop transcripts represent ``message.content`` either as a
        plain string or a list of typed parts (``{"type": "text",
        "text": "..."}`` for chat text, ``tool_use``/``tool_result`` for
        tool traffic). Learn Mode only ingests chat text — tool-use
        and tool-result parts are skipped so the categorizer never sees
        them. Returns ``""`` when no text content is present.
        """
        if not isinstance(message, dict):
            return ""
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    txt = item.get("text", "")
                    if isinstance(txt, str) and txt:
                        parts.append(txt)
            return "\n".join(parts)
        return ""

    def _is_sm_originated(self, session_id_jsonl: str) -> bool:
        """Filter SM-self transcripts per feedback_no_self_monitor.md.

        Returns True when the JSONL record's ``sessionId`` matches the
        cached ``SM_OWN_SESSION_ID`` (captured at ``start()``). When the
        cached value is empty (env var unset at start), no filtering
        applies.
        """
        sm_own = self._sm_own_session_id
        if not sm_own:
            return False
        return session_id_jsonl == sm_own

    def _remember_pair(
        self, session_id_jsonl: str, uuid: str, pair_id: str
    ) -> None:
        if not uuid or not pair_id:
            return
        key = (session_id_jsonl, uuid)
        # Bounded FIFO; drop oldest insertions when over budget.
        if len(self._uuid_to_pair) >= self._pair_cache_max:
            # Pop the oldest ~10% in insertion order to avoid thrashing.
            drop = max(1, self._pair_cache_max // 10)
            for k in list(self._uuid_to_pair.keys())[:drop]:
                self._uuid_to_pair.pop(k, None)
        self._uuid_to_pair[key] = pair_id

    def _maybe_emit_learn_mode(
        self, record: dict, session_id_jsonl: str
    ) -> None:
        record_type = str(record.get("type", "") or "")
        if record_type not in ("assistant", "user"):
            return
        # No-self-monitor: drop SM's own transcript turns.
        if self._is_sm_originated(session_id_jsonl):
            return
        message = record.get("message")
        text = self._extract_text(message)
        if not text:
            return
        uuid = str(record.get("uuid", "") or "")
        parent_uuid = str(record.get("parentUuid", "") or "")
        if record_type == "assistant":
            envelope = _msg_bus.Message.new(
                session_id=self._session_id,
                type="desktop_prompt",
                direction="inbound",
                content=text,
                metadata={
                    "desktop_session_id": session_id_jsonl,
                    "uuid": uuid,
                    "parent_uuid": parent_uuid,
                    "ts": time.time(),
                },
            )
            try:
                self.bus.publish(envelope)
            except Exception:
                log.exception("jsonl_tail: bus.publish(desktop_prompt) failed")
                return
            # Remember the envelope id keyed by (Desktop session, uuid)
            # so the next user_reply whose parentUuid points at it can
            # carry the pair_id forward without colliding across
            # concurrent Desktop sessions.
            self._remember_pair(session_id_jsonl, uuid, envelope.id)
            return
        # record_type == "user"
        pair_id = self._uuid_to_pair.get((session_id_jsonl, parent_uuid))
        metadata: dict = {
            "desktop_session_id": session_id_jsonl,
            "uuid": uuid,
            "parent_uuid": parent_uuid,
            "ts": time.time(),
        }
        # Only attach pair_id when we actually matched a parent prompt;
        # omitting the key (vs. setting it to "") lets the categorizer
        # distinguish "no parent" (cold start / eviction / SM-filtered)
        # via metadata.get("pair_id") returning None.
        if pair_id:
            metadata["pair_id"] = pair_id
        envelope = _msg_bus.Message.new(
            session_id=self._session_id,
            type="user_reply",
            direction="inbound",
            content=text,
            metadata=metadata,
        )
        try:
            self.bus.publish(envelope)
        except Exception:
            log.exception("jsonl_tail: bus.publish(user_reply) failed")
