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
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from stream_manager import message_bus as _msg_bus
from stream_manager.agent_registry import AgentRegistry

if TYPE_CHECKING:
    from stream_manager.governance import GovernanceEngine

log = logging.getLogger(__name__)

POLL_INTERVAL_S = 0.5
CANARY_SWEEP_INTERVAL_S = 1.0


# v2.1 P2 (FR-PPP) — per-process Layer-2 canary registry entry.
# `candidates_for_requeue` is captured at register_canary time so that
# the timeout sweep can re-fire Layer-1 HITL deterministically (R7 cap
# at 1 re-queue is enforced intrinsically: a swept entry is popped from
# the registry, so no second sweep can fire for the same probe_id).
@dataclass
class _CanaryState:
    nonce: str
    target_jsonl_path: str
    started_at: float
    timeout_s: float
    candidates_for_requeue: list[_msg_bus.AuditProbeCandidate] = field(
        default_factory=list
    )


class JsonlTailWorker:
    def __init__(
        self,
        projects_dir: Path,
        registry: AgentRegistry,
        bus: _msg_bus.MessageBus,
        governance: GovernanceEngine | None = None,
    ) -> None:
        self.projects_dir = Path(projects_dir)
        self.registry = registry
        self.bus = bus
        # Optional governance ref — required for v2.1 P2 canary timeout
        # re-fire. Pre-P2 callers (older tests, soak driver) construct
        # without it; the sweep thread degrades to envelope-only failure
        # (no Layer-1 re-queue) when governance is None.
        self.governance = governance
        self._thread: threading.Thread | None = None
        self._sweep_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._session_id: str = ""
        self._project_slug: str = ""
        self._last_attribution: str | None = None
        # v2.1 P2 — per-process canary registry. Key = probe_id (UUID hex
        # from emit_audit_canary). Lock scope is intentionally short
        # (registry mutations + path read), never held across bus or
        # governance calls — those happen with the dict copy.
        self._canary_lock = threading.Lock()
        self._canary_registry: dict[str, _CanaryState] = {}
        self._current_jsonl_path: str = ""
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
        # v2.1 P2 — sweep thread for canary timeout. Lifecycle bound to
        # the tail worker (same stop event, same start/stop signal).
        self._sweep_thread = threading.Thread(
            target=self._run_canary_sweep,
            name=f"jsonl-canary-sweep-{project_slug}",
            daemon=True,
        )
        self._sweep_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None
        sweep = self._sweep_thread
        if sweep is not None:
            sweep.join(timeout=2.0)
        self._sweep_thread = None

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
                    # v2.1 P2: canary observer uses this for jsonl_path
                    # match. Update before opening so a concurrent
                    # observer scan always sees the path being read.
                    self._current_jsonl_path = str(path)
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
        # v2.1 P2 — Layer-2 canary echo observer. Scan user text for any
        # active canary's nonce whose target_jsonl_path matches the
        # JSONL we are currently tailing. Self-monitor guard is upstream
        # (`_is_sm_originated` filter above this branch).
        try:
            self._check_canary_match(text)
        except Exception:
            log.exception("jsonl_tail: canary match check failed")
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

    # ── v2.1 P2 (FR-PPP) — Layer-2 canary echo registry + observer ────

    def register_canary(
        self,
        probe_id: str,
        nonce: str,
        target_jsonl_path: str,
        timeout_s: float = 10.0,
        candidates_for_requeue: (
            list[_msg_bus.AuditProbeCandidate] | None
        ) = None,
    ) -> None:
        """Register a Layer-2 canary on the per-process observer.

        Called by the dashboard /api/sm-canary/emit handler (or the
        auto-emit hook on /api/sm-probe/ack success) immediately after
        the matching `governance.emit_audit_canary` call. The probe_id
        + nonce here MUST match the envelope payload that was signed
        and fanned to subscribers — observer-side match keys are
        derived from this entry, not from the in-flight envelope dict.
        """
        if not probe_id or not nonce or not target_jsonl_path:
            return
        state = _CanaryState(
            nonce=nonce,
            target_jsonl_path=target_jsonl_path,
            started_at=time.time(),
            timeout_s=float(timeout_s),
            candidates_for_requeue=list(candidates_for_requeue or []),
        )
        with self._canary_lock:
            self._canary_registry[probe_id] = state

    def unregister_canary(self, probe_id: str) -> None:
        with self._canary_lock:
            self._canary_registry.pop(probe_id, None)

    def _check_canary_match(self, text: str) -> None:
        """Observer hook called from the user-text branch of ingest.

        Match conditions: nonce literal is a substring of `text` AND
        the registered `target_jsonl_path` equals the JSONL currently
        being tailed (`self._current_jsonl_path`). On match: emit
        `audit.canary_observed`, call `bus.mark_canary_confirmed`,
        clear the registry entry. The single-write-wins invariant is
        also enforced at the bus row level
        (`WHERE canary_confirmed_at IS NULL`); a second match between
        registry clear and the next bus call would no-op.
        """
        if not text:
            return
        current_path = self._current_jsonl_path
        if not current_path:
            return
        with self._canary_lock:
            snapshot = list(self._canary_registry.items())
        for probe_id, state in snapshot:
            if state.target_jsonl_path != current_path:
                continue
            if state.nonce not in text:
                continue
            observed_at = time.time()
            envelope = _msg_bus.AuditCanaryObservedEnvelope(
                probe_id=probe_id,
                nonce=state.nonce,
                observed_at=observed_at,
                jsonl_path=state.target_jsonl_path,
                hmac_sig="",
            )
            envelope_dict = envelope.to_dict()
            sig_payload = {
                k: v for k, v in envelope_dict.items() if k != "hmac_sig"
            }
            try:
                from stream_manager import desktop_commands as _dc

                sig = _dc.sign(sig_payload)
                envelope_dict["hmac_sig"] = sig
            except Exception:
                log.exception("jsonl_tail: canary observed sign failed")
                continue
            try:
                self.bus.write_envelope(
                    "audit.canary_observed", envelope_dict
                )
            except Exception:
                log.exception("jsonl_tail: write_envelope(observed) failed")
            try:
                self.bus.mark_canary_confirmed(
                    probe_id=probe_id,
                    nonce=state.nonce,
                    confirmed_at=observed_at,
                )
            except Exception:
                log.exception("jsonl_tail: mark_canary_confirmed failed")
            with self._canary_lock:
                self._canary_registry.pop(probe_id, None)

    def _run_canary_sweep(self) -> None:
        """1s sweep — emit failure envelope on entries past `timeout_s`.

        Sweep runs on its own daemon thread so a slow tail iteration
        (long `readline` wait on an empty JSONL) does not delay timeout
        detection. R7 mitigation (cap re-queue at 1 per probe_id) is
        intrinsic: a swept entry is popped from the registry, so no
        second sweep can fire for the same probe.
        """
        while not self._stop_event.is_set():
            try:
                self._sweep_canaries_once()
            except Exception:
                log.exception("jsonl_tail: canary sweep iteration failed")
            if self._stop_event.wait(CANARY_SWEEP_INTERVAL_S):
                break

    def _sweep_canaries_once(self) -> None:
        now = time.time()
        expired: list[tuple[str, _CanaryState]] = []
        with self._canary_lock:
            for probe_id, state in list(self._canary_registry.items()):
                if now - state.started_at > state.timeout_s:
                    expired.append((probe_id, state))
                    self._canary_registry.pop(probe_id, None)
        if not expired:
            return
        gov = self.governance
        for probe_id, state in expired:
            if gov is None:
                # No governance ref — log + skip re-queue. The envelope
                # path requires the governance.emit_audit_probe_failure
                # signer; without it we cannot stamp a verifiable sig.
                log.warning(
                    "jsonl_tail: canary timeout for probe_id=%s but no "
                    "governance ref available; envelope skipped",
                    probe_id,
                )
                continue
            try:
                gov.emit_audit_probe_failure(
                    probe_id=probe_id,
                    reason="canary_timeout",
                    candidate_streams=state.candidates_for_requeue,
                )
            except Exception:
                log.exception(
                    "jsonl_tail: emit_audit_probe_failure failed for %s",
                    probe_id,
                )
