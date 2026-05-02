"""Governed-session consumer of SM → desktop_command control plane.

Reference: docs/sync-comms-qa.md OQ4 (long-poll transport lock).
memory/project_sync_comms.md is the canonical design freeze.

This module is the read/ack side of the desktop_commands WAL table.
Counterpart to ``stream_manager.desktop_commands`` (Task D writer).

The governed Claude Code session spawns a sidecar daemon (see
``tools/sm_consumer.py``) that long-polls SM for pending commands,
validates the HMAC-SHA256 signature against the shared secret, runs a
locally-registered executor for the command's kind, and posts an ack.

Security model:
  - The HMAC secret never leaves the consumer process; it's loaded once
    from env / file / disk via the producer's ``_load_or_gen_secret``.
  - Signature validation reuses ``desktop_commands.validate`` so the
    canonical-JSON convention can never drift between writer & reader.
  - An unknown ``kind`` (not in the local executors map) ack-rejects
    even if it appears in ``KIND_ALLOWLIST`` — the consumer trusts only
    its own registered executors, never the producer's allowlist.
  - Executor exceptions are caught, logged, and ack-rejected with
    ``error=str(exc)[:200]`` so a single bad command can't crash the
    daemon.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Optional

import httpx

from stream_manager import desktop_commands

log = logging.getLogger(__name__)

# Default poll cadence — OQ4 lock specifies long-poll @ 1 Hz so the
# producer side sees ~1s of ack latency in the steady state.
_DEFAULT_POLL_INTERVAL = 1.0


def _default_executors() -> dict[str, Callable[[dict], None]]:
    """Stub executors for every kind in the allowlist.

    Real Claude-Code-side wiring lives in the spawning hook (see
    ``tools/sm_consumer.py``); these defaults are no-ops that just log
    so the daemon is functional out of the box for smoke tests.
    """

    def _noop_pause(args: dict) -> None:
        log.info("desktop_command pause stub: %r", args)

    def _noop_foreground(args: dict) -> None:
        log.info("desktop_command foreground stub: %r", args)

    def _noop_flash(args: dict) -> None:
        log.info("desktop_command flash stub: %r", args)

    def _noop_audible(args: dict) -> None:
        log.info("desktop_command audible_cue stub: %r", args)

    def _noop_surface_hitl(args: dict) -> None:
        # ``surface_hitl`` is normally wired through the existing HITL
        # plumbing; the daemon overrides this when run with full
        # governance context.
        log.info("desktop_command surface_hitl stub: %r", args)

    def _noop_request_attention(args: dict) -> None:
        log.info("desktop_command request_attention stub: %r", args)

    return {
        "pause": _noop_pause,
        "foreground": _noop_foreground,
        "flash": _noop_flash,
        "audible_cue": _noop_audible,
        "surface_hitl": _noop_surface_hitl,
        "request_attention": _noop_request_attention,
    }


class CommandConsumer:
    """Long-polling consumer that drains a session's desktop_commands.

    Parameters
    ----------
    sm_url:
        Base URL of the streamManager dashboard
        (e.g. ``http://127.0.0.1:8765``).
    session_id:
        Governed session id this consumer represents. Only commands
        addressed to this session are pulled.
    secret:
        HMAC shared secret. Held in process memory only and passed
        explicitly to ``desktop_commands.validate`` per call; no global
        env mutation.
    executors:
        Mapping of kind → callable. Each callable takes the command's
        ``args`` dict and returns ``None``. It MUST raise on failure
        (the exception's ``str()[:200]`` is forwarded as the ack error).
        A kind absent from this dict is rejected with
        ``error='unknown_kind'`` — the consumer trusts only its own
        registered executors, never the producer's allowlist.
    poll_interval:
        Seconds to wait between polls (default ``1.0`` per OQ4 lock).
    sleep_fn:
        Injected sleep — defaults to ``time.sleep``. Tests pass a
        recorder so they can assert cadence without a real wait.
    client:
        Optional preconstructed ``httpx.Client``. Tests pass one wired
        to ``httpx.MockTransport(handler)``. When ``None`` the consumer
        builds its own client against ``sm_url``.
    stop_event:
        Optional ``threading.Event``. The run loop checks
        ``stop_event.is_set()`` after each iteration and returns when
        set, which is how tests terminate ``run_forever``.
    """

    def __init__(
        self,
        sm_url: str,
        session_id: str,
        secret: bytes,
        executors: dict[str, Callable[[dict], None]],
        poll_interval: float = _DEFAULT_POLL_INTERVAL,
        sleep_fn: Callable[[float], None] = time.sleep,
        client: Optional[httpx.Client] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        if not isinstance(sm_url, str) or sm_url == "":
            raise ValueError("sm_url required")
        if not isinstance(session_id, str) or session_id == "":
            raise ValueError("session_id required")
        if not isinstance(secret, (bytes, bytearray)) or len(secret) == 0:
            raise ValueError("secret must be non-empty bytes")
        if not isinstance(executors, dict):
            raise ValueError("executors must be a dict")

        self.sm_url = sm_url.rstrip("/")
        self.session_id = session_id
        self.secret = bytes(secret)
        self.executors = dict(executors)
        self.poll_interval = float(poll_interval)
        self._sleep = sleep_fn
        self._stop_event = stop_event if stop_event is not None else threading.Event()

        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(
            base_url=self.sm_url, timeout=10.0
        )

    # ─── Lifecycle ─────────────────────────────────────────────────

    def stop(self) -> None:
        """Signal ``run_forever`` to exit at the next iteration boundary."""
        self._stop_event.set()

    def close(self) -> None:
        """Close the owned httpx client (no-op for injected clients)."""
        if self._owns_client:
            try:
                self._client.close()
            except Exception:
                pass

    # ─── Single-iteration helpers ─────────────────────────────────

    def _fetch_pending(self) -> list[dict]:
        """GET /api/commands/pending — returns [] on transport error."""
        try:
            resp = self._client.get(
                "/api/commands/pending",
                params={"session_id": self.session_id},
            )
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                log.warning("pending response was not a list: %r", type(data))
                return []
            return data
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("fetch pending failed: %s", exc)
            return []

    def _ack(self, cmd_id: str, status: str, error: Optional[str] = None) -> None:
        """POST /api/commands/{id}/ack — best-effort, never raises."""
        body: dict[str, object] = {"status": status}
        if error is not None:
            body["error"] = error
        try:
            resp = self._client.post(f"/api/commands/{cmd_id}/ack", json=body)
            # 4xx/5xx are logged but never crash the loop.
            if resp.status_code >= 400:
                log.warning(
                    "ack %s for %s returned HTTP %d: %s",
                    status,
                    cmd_id,
                    resp.status_code,
                    resp.text,
                )
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("ack POST failed for %s: %s", cmd_id, exc)

    def _process_one(self, row: dict) -> None:
        """Validate, dispatch, and ack a single command row.

        All exit paths terminate in exactly one ack POST so producer
        UIs always see a deterministic terminal state.
        """
        cmd_id = row.get("id")
        if not isinstance(cmd_id, str) or cmd_id == "":
            log.warning("skipping row without id: %r", row)
            return

        try:
            payload = row.get("payload")
            signature = row.get("signature")
            if not isinstance(payload, dict) or not isinstance(signature, str):
                self._ack(cmd_id, "rejected", "bad_sig")
                return

            # Reuse the producer's validator — single source of truth for
            # canonical-JSON encoding + constant-time compare.
            if not desktop_commands.validate(payload, signature, secret=self.secret):
                self._ack(cmd_id, "rejected", "bad_sig")
                return

            kind = payload.get("kind")
            args = payload.get("args") or {}
            if not isinstance(args, dict):
                args = {}

            executor = self.executors.get(kind) if isinstance(kind, str) else None
            if executor is None:
                # Note: even if kind is in KIND_ALLOWLIST, an absent
                # executor still rejects — consumer trusts only itself.
                self._ack(cmd_id, "rejected", "unknown_kind")
                return

            try:
                executor(args)
            except Exception as exc:
                self._ack(cmd_id, "rejected", str(exc)[:200])
                return

            self._ack(cmd_id, "ok")
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("unexpected error processing command %s", cmd_id)
            try:
                self._ack(cmd_id, "rejected", str(exc)[:200])
            except Exception:
                pass

    # ─── Main loop ─────────────────────────────────────────────────

    def run_once(self) -> int:
        """Run a single poll → process → ack cycle. Returns row count."""
        rows = self._fetch_pending()
        for row in rows:
            if not isinstance(row, dict):
                continue
            self._process_one(row)
        return len(rows)

    def run_forever(self) -> None:
        """Long-poll loop until ``stop_event`` is set.

        Each iteration: fetch pending, process each, sleep
        ``poll_interval``, then check the stop flag. The sleep happens
        before the stop check so tests can drive N iterations by setting
        the event after observing N sleep calls.
        """
        while True:
            try:
                self.run_once()
            except Exception:  # pragma: no cover - defensive
                log.exception("run_once failed; continuing loop")
            self._sleep(self.poll_interval)
            if self._stop_event.is_set():
                return
