"""WireCLI — structured RPC transport over the Claude CLI subprocess.

Task N (v1.1): re-incorporation of the spike-c-final wire work, scrubbed
of WebSocket / SDK-era artifacts. The original spike (tag
``spike-c-final``, sha f05febbe) proved a stdio-pumped subprocess
wrapper. This module narrows that mechanic to a request/response RPC
shape suitable for governance escalation.

Why a new transport
-------------------

The legacy path lives in ``cli_governance._parse_envelope``: it shells
out to ``claude -p ... --output-format json``, then tries to recover an
inner ``{"action": ..., "confidence": ..., "reasoning": ...}`` JSON
object from the CLI envelope's ``result`` field. The model can return:

  * raw JSON (happy path)
  * fenced JSON (`````json\\n{...}\\n`````)
  * prose preamble + JSON
  * prose only (no JSON at all)
  * malformed JSON

When parsing fails, ``cli_governance`` returns ``None`` and the engine
"degrades" to a default ALLOW. Operationally this looks identical to a
real ALLOW — there is no signal that the model's reply was corrupt.
Soak logs surface this as the "inner JSON parse failed; degrading"
warning.

WireCLI replaces the silent-degrade fallback with a *typed* protocol:

  1. The request carries an explicit schema version
     (``WIRE_SCHEMA_VERSION``).
  2. The response is validated against ``WireResponse``.
  3. Parse failures raise :class:`WireProtocolError` (a typed
     exception). Callers MUST catch it explicitly and decide whether to
     degrade or surface — they cannot accidentally treat it as ALLOW.
  4. Schema-version mismatch raises
     :class:`WireSchemaVersionError` so a stale CLI build can't silently
     route through.

v1.1 scope
----------

This module is opt-in. ``cli_client.cli_transport()`` defaults to
``"json"`` (legacy ``cli_governance`` path). ``transport="wirecli"``
selects this module. ADR-15 plans the v1.2 default flip.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Sequence

log = logging.getLogger(__name__)

# Schema version embedded in every request and required to match in
# every response. Bump only on backwards-incompatible payload changes.
WIRE_SCHEMA_VERSION = "1"

DEFAULT_TIMEOUT_SECONDS = 25.0
DEFAULT_CLI_BIN = "claude"
DEFAULT_MODEL = "claude-haiku-4-5"

_VALID_ACTIONS = frozenset({"ALLOW", "SUGGEST", "GUIDE", "INTERVENE", "BLOCK"})

# Code-fence stripping: tolerate the ````json\n...\n```` envelope the
# legacy parser also tolerates, but ONLY as a last resort. Strict mode
# refuses fenced output entirely (see WireRequest.strict_fence).
_FENCE_RE = re.compile(r"^```(?:json)?\s*\n(.*?)\n```\s*$", re.DOTALL)


class WireError(Exception):
    """Base for all WireCLI transport errors."""


class WireProtocolError(WireError):
    """Response could not be parsed into a valid :class:`WireResponse`.

    Distinct from a model-level disagreement — the model returned
    bytes that don't match the wire schema at all. Callers should NOT
    silently degrade to ALLOW when this is raised; the right move is
    to surface the failure (governance call status=failed) so soak
    diagnostics see the parser-fragility signal.
    """


class WireSchemaVersionError(WireError):
    """Response schema_version did not match :data:`WIRE_SCHEMA_VERSION`.

    Indicates a CLI / model build that's emitting a different protocol
    revision. Caller must NOT proceed — schema drift would silently
    misroute decisions.
    """


class WireTransportError(WireError):
    """Subprocess invocation itself failed (non-zero exit, missing CLI,
    timeout). Callers may degrade for these — the parser saw nothing
    to parse, so the failure is operational, not protocol-level.
    """


@dataclass(frozen=True)
class WireRequest:
    """A structured RPC request to the Claude CLI."""

    content: str
    intent: str = ""
    model: str = DEFAULT_MODEL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    cli_bin: str = DEFAULT_CLI_BIN
    strict_fence: bool = False  # if True, code-fenced replies are rejected.


@dataclass(frozen=True)
class WireResponse:
    """Structured response from a WireCLI evaluation.

    ``schema_version`` is included so callers can audit drift even
    after parse succeeds. ``action`` is one of the five governance
    verbs; ``confidence`` is in [0.0, 1.0]; ``reasoning`` is bounded
    to keep WAL row sizes predictable.
    """

    schema_version: str
    action: str
    confidence: float
    reasoning: str


def _build_system_prompt(intent: str) -> str:
    """Compose the governance system-prompt with an embedded schema preamble.

    The preamble pins the wire schema — the model is told exactly which
    JSON shape to emit AND which schema_version string to stamp. This
    is the contract that distinguishes WireCLI from the legacy ad-hoc
    ``_SYSTEM_TEMPLATE`` in ``cli_governance``.
    """
    intent_block = (intent or "(no INTENT.md loaded)")[:8000]
    return (
        "You are a code-action governance evaluator running over a "
        "structured RPC protocol named WireCLI. Reply with EXACTLY one "
        "JSON object and nothing else — no prose, no markdown fences, "
        "no commentary. The object MUST have these fields:\n\n"
        '  {\n'
        f'    "schema_version": "{WIRE_SCHEMA_VERSION}",\n'
        '    "action": "ALLOW|SUGGEST|GUIDE|INTERVENE|BLOCK",\n'
        '    "confidence": <number in 0.0 .. 1.0>,\n'
        '    "reasoning": "<short string, <=500 chars>"\n'
        '  }\n\n'
        "Choose ALLOW for routine safe actions, SUGGEST for borderline "
        "cases, GUIDE/INTERVENE for actions that should be redirected, "
        "and BLOCK only for clearly destructive or intent-violating "
        "actions. If the content is not a proposed action (narration, "
        "code output, etc.), use action=ALLOW with confidence=0.5.\n\n"
        "Project intent:\n"
        f"{intent_block}"
    )


def _build_cmd(req: WireRequest, system_prompt: str) -> list[str]:
    """Build the argv list for the underlying ``claude -p`` invocation."""
    user_prompt = (
        f"Evaluate this proposed action under WireCLI schema "
        f"v{WIRE_SCHEMA_VERSION}:\n\n{req.content[:4000]}"
    )
    return [
        req.cli_bin,
        "-p",
        user_prompt,
        "--system-prompt",
        system_prompt,
        "--output-format",
        "json",
        "--model",
        req.model,
        "--no-session-persistence",
        "--tools",
        "",
    ]


def _strip_fence(text: str, *, strict: bool) -> str:
    """Strip a single trailing ```json fence if present.

    In ``strict=True`` mode, fenced responses raise WireProtocolError —
    the schema explicitly forbids fences, so a fenced reply is a
    protocol violation. In permissive mode (default) we tolerate them
    so v1.1 callers can opt in without retraining the model first.
    """
    s = text.strip()
    m = _FENCE_RE.match(s)
    if m:
        if strict:
            raise WireProtocolError("response wrapped in code fence; strict mode forbids")
        return m.group(1).strip()
    return s


def _parse_inner(inner: str, *, strict_fence: bool) -> WireResponse:
    """Parse the CLI envelope's ``result`` string into a WireResponse.

    Raises:
        WireProtocolError: payload is not a JSON object, or required
            fields are missing / wrong type, or action is not in the
            valid set.
        WireSchemaVersionError: parsed but schema_version mismatch.
    """
    s = _strip_fence(inner, strict=strict_fence)
    try:
        obj = json.loads(s)
    except json.JSONDecodeError as exc:
        raise WireProtocolError(f"inner JSON parse failed: {exc.msg}") from exc

    if not isinstance(obj, dict):
        raise WireProtocolError(
            f"inner payload not a JSON object (got {type(obj).__name__})"
        )

    schema_version = obj.get("schema_version")
    if schema_version is None:
        raise WireProtocolError("missing required field: schema_version")
    if not isinstance(schema_version, str):
        raise WireProtocolError(
            f"schema_version must be string, got {type(schema_version).__name__}"
        )
    if schema_version != WIRE_SCHEMA_VERSION:
        raise WireSchemaVersionError(
            f"schema_version mismatch: got {schema_version!r}, "
            f"expected {WIRE_SCHEMA_VERSION!r}"
        )

    action = obj.get("action")
    if action not in _VALID_ACTIONS:
        raise WireProtocolError(
            f"action must be one of {sorted(_VALID_ACTIONS)}, got {action!r}"
        )

    raw_conf = obj.get("confidence")
    if not isinstance(raw_conf, (int, float)) or isinstance(raw_conf, bool):
        raise WireProtocolError(
            f"confidence must be number, got {type(raw_conf).__name__}"
        )
    confidence = float(raw_conf)
    if not (0.0 <= confidence <= 1.0):
        raise WireProtocolError(
            f"confidence out of range [0.0, 1.0]: {confidence}"
        )

    raw_reason = obj.get("reasoning", "")
    if not isinstance(raw_reason, str):
        raise WireProtocolError(
            f"reasoning must be string, got {type(raw_reason).__name__}"
        )
    reasoning = raw_reason[:500]

    return WireResponse(
        schema_version=schema_version,
        action=action,
        confidence=confidence,
        reasoning=reasoning,
    )


def parse_envelope(stdout: str, *, strict_fence: bool = False) -> WireResponse:
    """Parse a full ``claude -p --output-format json`` envelope.

    The CLI emits ``{"type": "result", "is_error": bool, "result": ...,
    ...}``. ``result`` may be a dict (newer CLIs) or a JSON string
    (older ones). Either way, we route through :func:`_parse_inner`.

    Raises:
        WireProtocolError: envelope itself is unparseable, or
            ``is_error`` is true, or ``result`` is missing/wrong-typed.
        WireSchemaVersionError: inner schema_version mismatch.
    """
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise WireProtocolError(f"outer JSON parse failed: {exc.msg}") from exc

    if not isinstance(envelope, dict):
        raise WireProtocolError(
            f"envelope not a JSON object (got {type(envelope).__name__})"
        )

    if envelope.get("is_error"):
        raise WireProtocolError("CLI envelope is_error=true")

    inner = envelope.get("result")
    if inner is None:
        raise WireProtocolError("envelope missing required field: result")

    if isinstance(inner, dict):
        # Newer CLIs may emit `result` already-parsed. Re-serialize and
        # parse so validation is unified.
        inner_str = json.dumps(inner)
    elif isinstance(inner, str):
        inner_str = inner
    else:
        raise WireProtocolError(
            f"envelope.result must be dict or string, got {type(inner).__name__}"
        )

    return _parse_inner(inner_str, strict_fence=strict_fence)


# Subprocess runner type — same shape as ``subprocess.run``.
RunnerFn = Callable[..., subprocess.CompletedProcess[str]]


def call(
    req: WireRequest,
    *,
    runner: RunnerFn | None = None,
) -> WireResponse:
    """Execute a WireRequest synchronously and return a typed response.

    ``runner`` is injectable for tests. Defaults to ``subprocess.run``.

    Raises:
        WireTransportError: subprocess invocation itself failed (CLI
            not on PATH, timeout, non-zero exit). Callers may degrade.
        WireProtocolError: subprocess succeeded but the response is
            not a valid WireCLI payload. Callers should NOT silently
            degrade — surface the failure.
        WireSchemaVersionError: schema drift. Callers must NOT
            proceed.
    """
    run = runner if runner is not None else subprocess.run
    system_prompt = _build_system_prompt(req.intent)
    cmd = _build_cmd(req, system_prompt)

    try:
        result = run(
            cmd,
            capture_output=True,
            text=True,
            timeout=req.timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise WireTransportError(f"CLI binary not found: {req.cli_bin}") from exc
    except subprocess.TimeoutExpired as exc:
        raise WireTransportError(
            f"CLI subprocess timed out after {req.timeout_seconds}s"
        ) from exc

    if result.returncode != 0:
        stderr_excerpt = (result.stderr or "")[:200]
        raise WireTransportError(
            f"CLI exited with code {result.returncode}: {stderr_excerpt!r}"
        )

    return parse_envelope(result.stdout or "", strict_fence=req.strict_fence)


def call_from_string(
    stdout: str,
    *,
    strict_fence: bool = False,
) -> WireResponse:
    """Convenience parser for callers that already captured CLI stdout.

    Useful when WireCLI runs *inside* the warm-pool path
    (``cli_pool.CliWorker.send`` returns the raw envelope) so we don't
    spawn a fresh subprocess just to re-parse. The pool path doesn't
    use :func:`call` — it uses this directly.
    """
    return parse_envelope(stdout, strict_fence=strict_fence)


__all__ = [
    "WIRE_SCHEMA_VERSION",
    "WireRequest",
    "WireResponse",
    "WireError",
    "WireProtocolError",
    "WireSchemaVersionError",
    "WireTransportError",
    "call",
    "call_from_string",
    "parse_envelope",
]
