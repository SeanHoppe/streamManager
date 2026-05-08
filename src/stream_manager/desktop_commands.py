"""SM → governed-session desktop_command outbound control plane.

Reference: docs/sync-comms-qa.md Q2 + OQ1–OQ4 locks.
memory/project_sync_comms.md is the canonical design freeze.

This module is the writer side of the desktop_commands WAL table. Given a
``MessageBus`` (only its ``_lock`` and ``_conn`` are used) and a session
id, ``emit_command`` inserts a signed, allowlisted command row with
status='pending'. The governed session reads the row, verifies the
HMAC-SHA256 signature against a shared secret, executes the command, and
ACKs by updating the row's status/acked_at. This module deliberately
does NOT call ``bus.publish()``: desktop commands are an out-of-band
control plane; they are not subject to engine.evaluate() and never land
in the messages table.

The signature covers the canonical JSON of {id, session_id, kind, args,
sent_at}. Verification uses ``hmac.compare_digest`` to defeat timing
oracles.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stream_manager.message_bus import MessageBus

ROOT = Path(__file__).resolve().parent.parent.parent
SECRET_PATH = ROOT / ".bridge" / "secret"

KIND_ALLOWLIST = frozenset(
    {
        "pause",
        "foreground",
        "flash",
        "audible_cue",
        "surface_hitl",
        "request_attention",
        "audit_probe",
    }
)


def _load_or_gen_secret() -> bytes:
    """Resolve the HMAC shared secret in priority order:

    1. Env ``SM_DESKTOP_SECRET`` (utf-8 encoded).
    2. File at ``SECRET_PATH``.
    3. Generate ``secrets.token_urlsafe(32)``, write to ``SECRET_PATH``
       with mode ``0o600`` (best-effort on Windows).

    Returns the secret as ``bytes``.
    """
    env_val = os.environ.get("SM_DESKTOP_SECRET")
    if env_val is not None and env_val != "":
        return env_val.encode("utf-8")

    if SECRET_PATH.exists():
        return SECRET_PATH.read_bytes()

    # Generate a fresh secret. ``token_urlsafe(32)`` returns ~43 chars of
    # urlsafe base64 (256 bits of entropy).
    new_secret = secrets.token_urlsafe(32)
    SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECRET_PATH.write_text(new_secret, encoding="utf-8")
    # chmod after write so the file is never readable mid-write. On
    # Windows this often silently no-ops or raises; swallow OSError.
    try:
        os.chmod(SECRET_PATH, 0o600)
    except OSError:
        pass
    return new_secret.encode("utf-8")


def _canonical_json(payload: dict) -> bytes:
    """Canonical JSON encoding for signing: sorted keys, no whitespace."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def sign(payload: dict, secret: bytes | None = None) -> str:
    """Return the HMAC-SHA256 hex digest of canonical-JSON(payload).

    The signed payload includes ``id``, ``session_id``, ``kind``,
    ``args``, and ``sent_at`` — the row primary key plus the body. The
    ``signature`` column on the desktop_commands row stores the digest
    of these exact fields.

    When ``secret`` is supplied, use it directly. Otherwise resolve via
    ``_load_or_gen_secret()`` (env → file → generate).
    """
    key = secret if secret is not None else _load_or_gen_secret()
    return hmac.new(key, _canonical_json(payload), hashlib.sha256).hexdigest()


def validate(payload: dict, signature: str, secret: bytes | None = None) -> bool:
    """Constant-time signature check via ``hmac.compare_digest``.

    Returns True iff ``signature`` matches ``sign(payload)``. Never use
    ``==`` here — that would leak information byte-by-byte to a remote
    attacker.

    Pass ``secret`` to avoid the global env/file lookup; useful for
    consumers that already hold the key in process memory.
    """
    expected = sign(payload, secret=secret)
    return hmac.compare_digest(expected, signature)


def emit_command(
    bus: MessageBus,
    session_id: str,
    kind: str,
    args: dict,
) -> str:
    """Insert a signed desktop_command row with status='pending'.

    Raises ``ValueError`` for empty session_id, SM_OWN_SESSION_ID match,
    or kind outside the allowlist. Returns the new command id.
    """
    if not isinstance(session_id, str) or session_id == "":
        raise ValueError("session_id required")
    sm_own = os.environ.get("SM_OWN_SESSION_ID", "").strip()
    if sm_own and session_id == sm_own:
        raise ValueError("session_id matches SM_OWN_SESSION_ID")
    if kind not in KIND_ALLOWLIST:
        raise ValueError(f"kind {kind!r} not in allowlist")
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ValueError("args must be a dict")

    cmd_id = str(uuid.uuid4())
    sent_at = time.time()
    payload = {
        "id": cmd_id,
        "session_id": session_id,
        "kind": kind,
        "args": args,
        "sent_at": sent_at,
    }
    signature = sign(payload)
    args_json = json.dumps(args, separators=(",", ":"))

    with bus._lock:
        bus._conn.execute(
            "INSERT INTO desktop_commands (id, session_id, kind, args_json, "
            "signature, sent_at, status) VALUES (?, ?, ?, ?, ?, ?, 'pending')",
            (cmd_id, session_id, kind, args_json, signature, sent_at),
        )
    return cmd_id
