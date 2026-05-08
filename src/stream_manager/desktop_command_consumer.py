"""Governed-session consumer of SM → desktop_command control plane.

Reference:
  - docs/sync-comms-qa.md OQ4 (v1.0 long-poll transport — REMOVED v1.2).
  - docs/adr/ADR-14-desktop-command-sse.md (v1.1 SSE transport, v1.2
    sole transport after long-poll removal).
  - memory/project_sync_comms.md is the canonical design freeze.

This module is the read/ack side of the desktop_commands WAL table.
Counterpart to ``stream_manager.desktop_commands`` (Task D writer).

The governed Claude Code session spawns a sidecar daemon (see
``tools/sm_consumer.py``) that subscribes to SM for pending commands,
validates the HMAC-SHA256 signature against the shared secret, runs a
locally-registered executor for the command's kind, and posts an ack.

Transport: SSE only as of v1.2.

  * ``transport='sse'``: GET /api/commands/stream as a Server-Sent
    Events stream. Frames arrive sub-second after producer insert; the
    SSE handler also re-emits current pending rows on connect, so
    reconnect is loss-free as long as a row is still ``pending`` (not
    yet expired/acked) on resume.

The legacy ``transport='long-poll'`` value (v1.0/v1.1) was removed in
v1.2 per ADR-14 and the CHANGELOG entry for v1.2.0. Passing it now
raises ``ValueError`` with a migration hint.

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

import json
import logging
import threading
import time
from collections.abc import Callable
from typing import Optional

import httpx

from stream_manager import desktop_commands

log = logging.getLogger(__name__)

# SSE reconnect backoff: start at 0.5s, double each failure, cap at 10s
# per Task K spec. Reset to base after a successful streaming session.
_SSE_BACKOFF_BASE = 0.5
_SSE_BACKOFF_CAP = 10.0

# Valid transport modes. v1.2 removed 'long-poll'; SSE is the sole
# transport. The kwarg shape is preserved on CommandConsumer for one
# more cycle so callers that pass ``transport="sse"`` explicitly keep
# working without code change.
_VALID_TRANSPORTS = frozenset({"sse"})

# Migration hint surfaced when callers still pass the removed value.
# Kept as a module-level constant so tests can match against it without
# duplicating the wording.
_LONGPOLL_REMOVED_MSG = (
    "transport='long-poll' was removed in v1.2 (see CHANGELOG.md and "
    "ADR-14). Use transport='sse' (the new and only default)."
)

# v1.3 fold: explicit table of removed transports → migration message.
# A single dict drives the constructor's transport gate so the
# long-poll branch and the generic-invalid branch don't drift apart.
# Keys are removed transport values; values are the actionable error
# message surfaced as ``ValueError``. Behavioral parity with the
# previous dual-check is preserved: long-poll keeps its bespoke
# migration hint, anything else still in this table would surface its
# own.
_REMOVED_TRANSPORTS: dict[str, str] = {
    "long-poll": _LONGPOLL_REMOVED_MSG,
}


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

    def _noop_audit_probe(args: dict) -> None:
        # v2.1 P1 (FR-PPP): governed-side stub. Real probe surfacing
        # happens dashboard-side via /api/sm-probe + the HITL panel
        # row variant; operator's signed ack writes
        # provenance_assertions via /api/sm-probe/ack POST. The
        # consumer-side handler exists so the kind is recognized
        # (otherwise the consumer rejects with error='unknown_kind'
        # per the security model in this module's docstring).
        log.info("desktop_command audit_probe stub: %r", args)

    return {
        "pause": _noop_pause,
        "foreground": _noop_foreground,
        "flash": _noop_flash,
        "audible_cue": _noop_audible,
        "surface_hitl": _noop_surface_hitl,
        "request_attention": _noop_request_attention,
        "audit_probe": _noop_audit_probe,
    }


class CommandConsumer:
    """SSE-streaming consumer that drains a session's desktop_commands.

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
    sleep_fn:
        Injected sleep — defaults to ``time.sleep``. Tests pass a
        recorder so they can assert reconnect backoff cadence without a
        real wait.
    client:
        Optional preconstructed ``httpx.Client``. Tests pass one wired
        to ``httpx.MockTransport(handler)``. When ``None`` the consumer
        builds its own client against ``sm_url``. For SSE we set
        timeout=None on the per-request stream to override the default
        read timeout.
    stop_event:
        Optional ``threading.Event``. The run loop checks
        ``stop_event.is_set()`` after each iteration and returns when
        set, which is how tests terminate ``run_forever``.
    transport:
        Must be ``'sse'`` (the v1.2 default and only accepted value).
        ``'long-poll'`` was removed in v1.2 and now raises
        ``ValueError`` with a migration hint pointing at CHANGELOG.md.
        The kwarg shape is preserved so explicit ``transport="sse"``
        callers continue to work unchanged.
    """

    def __init__(
        self,
        sm_url: str,
        session_id: str,
        secret: bytes,
        executors: dict[str, Callable[[dict], None]],
        sleep_fn: Callable[[float], None] = time.sleep,
        client: Optional[httpx.Client] = None,
        stop_event: Optional[threading.Event] = None,
        transport: str = "sse",
    ) -> None:
        if not isinstance(sm_url, str) or sm_url == "":
            raise ValueError("sm_url required")
        if not isinstance(session_id, str) or session_id == "":
            raise ValueError("session_id required")
        if not isinstance(secret, (bytes, bytearray)) or len(secret) == 0:
            raise ValueError("secret must be non-empty bytes")
        if not isinstance(executors, dict):
            raise ValueError("executors must be a dict")
        # Surface removed transports (e.g. v1.2's long-poll removal) as
        # a clear, actionable error rather than a generic "invalid
        # transport" so callers upgrading from older versions see the
        # migration path in the message. Single-table lookup folds the
        # prior dual ``transport == "long-poll"`` + invalid-set check
        # into one path; behavioral parity preserved.
        removed_msg = _REMOVED_TRANSPORTS.get(transport)
        if removed_msg is not None:
            raise ValueError(removed_msg)
        if transport not in _VALID_TRANSPORTS:
            raise ValueError(
                f"transport must be one of {sorted(_VALID_TRANSPORTS)}; got {transport!r}"
            )

        self.sm_url = sm_url.rstrip("/")
        self.session_id = session_id
        self.secret = bytes(secret)
        self.executors = dict(executors)
        self.transport = transport
        self._sleep = sleep_fn
        self._stop_event = stop_event if stop_event is not None else threading.Event()

        # Track ids we've already dispatched in this process so SSE
        # reconnect — which replays current pending rows — never re-runs
        # an executor for a row we already acked locally. Bounded growth
        # is fine: rows hit terminal state quickly and SSE replay only
        # ever sends rows still in 'pending' status.
        self._dispatched: set[str] = set()

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

    # ─── Single-row helpers ───────────────────────────────────────

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

    def process_row(self, row: dict) -> None:
        """Validate, dispatch, and ack a single command row.

        All exit paths terminate in exactly one ack POST so producer
        UIs always see a deterministic terminal state.

        Idempotent for SSE reconnect: if the producer's
        /api/commands/stream re-replays a still-pending row we've
        already dispatched in this process, the ``self._dispatched``
        guard short-circuits before re-running the executor. The ack
        was already sent in the original dispatch; the producer's row
        will reach terminal state on its side regardless of replay.
        """
        cmd_id = row.get("id")
        if not isinstance(cmd_id, str) or cmd_id == "":
            log.warning("skipping row without id: %r", row)
            return

        if cmd_id in self._dispatched:
            # Replay of an in-flight or recently-acked row. Do NOT
            # re-fire the executor; the original dispatch already
            # acked. (If the ack POST failed, the row stays 'pending'
            # at the producer and would replay — accepting that
            # exactly-once is best-effort, with at-least-once executor
            # invocation gated by this in-process set.)
            return
        # Mark dispatched up-front so even if an exception below races
        # with a reconnect-triggered replay, the second arrival exits
        # via the guard above.
        self._dispatched.add(cmd_id)

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

    def run_forever(self) -> None:
        """Run the SSE transport until ``stop_event`` is set.

        Subscribes to /api/commands/stream and processes each frame.
        Reconnects with exponential backoff capped at
        ``_SSE_BACKOFF_CAP`` on transport error.

        The body delegates to ``_run_sse`` rather than inlining it
        because ``_run_sse`` is on the v1.1.0 do-not-touch contract
        (Task K). Keeping the wrapper preserves the long-standing
        ``run_forever`` public name without renaming the underlying
        impl that v1.1.0 froze.
        """
        self._run_sse()

    # ─── SSE transport ───────────────────────────────────────────────

    def _run_sse(self) -> None:
        """Subscribe to /api/commands/stream until ``stop_event`` is set.

        Outer loop owns reconnect with exponential backoff (cap 10s).
        Inner loop reads SSE frames and dispatches each one through
        ``process_row`` (which is idempotent across replays via
        ``self._dispatched``).
        """
        backoff = _SSE_BACKOFF_BASE
        while not self._stop_event.is_set():
            connected = False
            try:
                with self._client.stream(
                    "GET",
                    "/api/commands/stream",
                    params={"session_id": self.session_id},
                    timeout=None,
                ) as resp:
                    if resp.status_code != 200:
                        log.warning(
                            "SSE connect HTTP %d: %s",
                            resp.status_code,
                            getattr(resp, "text", ""),
                        )
                    else:
                        connected = True
                        backoff = _SSE_BACKOFF_BASE  # reset on success
                        self._consume_sse_stream(resp)
            except Exception as exc:
                log.warning("SSE stream error: %s", exc)

            if self._stop_event.is_set():
                return
            # Reconnect: success-then-EOF or transport error both go
            # through the same backoff path. On clean EOF after a long
            # session this is essentially free (0.5s sleep).
            wait = backoff if connected else min(backoff, _SSE_BACKOFF_CAP)
            self._sleep(wait)
            backoff = min(backoff * 2, _SSE_BACKOFF_CAP)

    def _consume_sse_stream(self, resp: httpx.Response) -> None:
        """Iterate ``data:`` frames from an open SSE response.

        Frame format: standard SSE (frames separated by blank lines,
        ``data:`` line carries one JSON object). Comment lines starting
        with ``:`` (heartbeats) are ignored. The loop returns on
        ``stop_event`` or when the iterator ends (EOF / disconnect).
        """
        buf = ""
        for chunk in resp.iter_text():
            if self._stop_event.is_set():
                return
            if not chunk:
                continue
            buf += chunk
            while "\n\n" in buf:
                frame, buf = buf.split("\n\n", 1)
                data_line: Optional[str] = None
                for line in frame.splitlines():
                    if line.startswith(":"):
                        # SSE comment / heartbeat — ignore.
                        continue
                    if line.startswith("data:"):
                        data_line = line[len("data:"):].strip()
                        break
                if not data_line:
                    continue
                try:
                    row = json.loads(data_line)
                except json.JSONDecodeError:
                    log.warning("SSE frame not JSON: %r", data_line[:200])
                    continue
                if not isinstance(row, dict):
                    continue
                if "error" in row and "id" not in row:
                    # Server-side stream error envelope; logged so the
                    # operator sees it without aborting the loop.
                    log.warning("SSE server error: %s", row.get("error"))
                    continue
                self.process_row(row)
