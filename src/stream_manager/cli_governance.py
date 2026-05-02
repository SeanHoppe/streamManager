"""Optional CLI-backed L2 escalation for the governance engine.

Activated by ``BRIDGE_API_GOV=true``. When unset, this module is a stub that
returns ``None`` — the engine falls back to its local-only path (precheck +
graph). When enabled, ambiguous content (no precheck hit, no high-confidence
graph match) escalates to the locally-installed Claude Code CLI via
``subprocess.run``. There is no Anthropic API key path; auth lives in the
user's logged-in CLI session.

Design choices:

  • Transport: ``claude -p <content> --system-prompt <gov>
    --output-format json --model <id> --no-session-persistence --tools ""``.
    --system-prompt keeps governance instructions out of the user turn, avoiding
    Claude's injection-defense refusals. --tools "" disables all built-in tools
    so the model returns a direct JSON response in one turn. --no-session-persistence
    skips session disk writes for lower overhead. Markdown code fences are stripped
    from the inner result before JSON parsing.
  • Output shape: the CLI emits ``{"type": "result", "result": <data>, ...}``.
    With --json-schema the inner ``result`` may be a dict or a JSON string;
    _parse_envelope handles both.
  • Errors: any failure (CLI missing, non-zero exit, timeout, malformed
    JSON, action-enum mismatch) returns ``None`` so the engine degrades
    cleanly to local-only behavior.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from stream_manager.project_context import ProjectContextSnapshot

if TYPE_CHECKING:
    from stream_manager.message_bus import MessageBus

log = logging.getLogger(__name__)

ENV_FLAG = "BRIDGE_API_GOV"
MODEL = "claude-haiku-4-5"
TIMEOUT_SECONDS = 25.0
CLI_BIN = "claude"

_VALID_ACTIONS = frozenset({"ALLOW", "SUGGEST", "GUIDE", "INTERVENE", "BLOCK"})

# Phase 7 / governance_call: tier inference from model id. Sonnet → L4,
# everything else (Haiku) → L3 by default. The legacy MODEL constant
# below is Haiku, so callers that pass no model_id get L3.
_L4_MARKER = "sonnet"


def _infer_tier(model_id: str | None) -> str:
    if not model_id:
        return "L3"
    return "L4" if _L4_MARKER in model_id.lower() else "L3"


def _infer_trigger(content: str) -> str:
    """Best-effort heuristic mirroring _ALIGNMENT_KEYWORDS in governance.py.

    The CliGovernor itself can't see the routing decision; the caller could
    pass it explicitly, but the alignment keywords are stable enough that
    a local sniff suffices for telemetry (it never feeds back into routing).
    """
    if not content:
        return "unknown"
    lowered = content.lower()
    if any(kw in lowered for kw in ("release", "merge", "deploy", "oversight/")):
        return "alignment"
    return "unknown"

_DECISION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": sorted(_VALID_ACTIONS)},
        "confidence": {"type": "number"},
        "reasoning": {"type": "string"},
    },
    "required": ["action", "confidence", "reasoning"],
    "additionalProperties": False,
}

_SYSTEM_TEMPLATE = (
    "You are a code-action governance evaluator. Given a proposed action a "
    "developer assistant is about to take, decide whether it aligns with "
    "the project's intent.\n\n"
    "Choose ALLOW for routine safe actions, SUGGEST for borderline cases worth "
    "flagging, GUIDE/INTERVENE for actions that should be redirected, and BLOCK "
    "only for clearly destructive or intent-violating actions.\n\n"
    "If the content is not a proposed action — for example, it is an explanation, "
    "status update, code output, assistant narration, or chain-of-thought — "
    "respond with action=ALLOW and confidence=0.5.\n\n"
    "Reply with a JSON object only — no prose, no markdown fences:\n"
    "{{\"action\": \"ALLOW|SUGGEST|GUIDE|INTERVENE|BLOCK\", "
    "\"confidence\": <0.0-1.0>, \"reasoning\": \"<short string>\"}}\n\n"
    "Project intent:\n{intent}"
)


@dataclass(frozen=True)
class CliDecision:
    action: str
    confidence: float
    reasoning: str


def is_enabled() -> bool:
    return os.environ.get(ENV_FLAG, "").lower() in ("1", "true", "yes")


class CliGovernor:
    """Wraps the Claude CLI subprocess with the governance prompt.

    Constructed lazily so subprocess invocation is avoided when the flag is off.
    A ``runner`` callable can be injected for tests; it must accept the same
    arguments as ``subprocess.run`` and return a ``CompletedProcess``.
    """

    def __init__(
        self,
        project_context: ProjectContextSnapshot,
        runner=None,
        bus: "MessageBus | None" = None,
        session_id: str | None = None,
    ) -> None:
        self.project_context = project_context
        self._runner = runner or subprocess.run
        self._system: str | None = None
        # Bus injection is optional so existing unit tests can construct
        # CliGovernor without a bus. When either bus or session_id is None,
        # all governance_call event publishing is skipped silently.
        self._bus = bus
        self._session_id = session_id

    def _system_prompt(self) -> str:
        if self._system is not None:
            return self._system
        intent = self.project_context.intent_text or "(no INTENT.md loaded)"
        self._system = _SYSTEM_TEMPLATE.format(intent=intent[:8000])
        return self._system

    def evaluate(
        self,
        content: str,
        model_id: str | None = None,
    ) -> CliDecision | None:
        if not is_enabled():
            return None

        user_prompt = f"Evaluate this proposed action:\n\n{content[:4000]}"
        # Phase 4 / NFR-M2: caller (model_router) may pass model_id for
        # tier-aware dispatch (Haiku for L2/L3, Sonnet for L4). When None,
        # fall back to the legacy default so existing callers/tests are
        # unaffected.
        chosen_model = model_id if model_id is not None else MODEL
        cmd = [
            CLI_BIN, "-p", user_prompt,
            "--system-prompt", self._system_prompt(),
            "--output-format", "json",
            "--model", chosen_model,
            "--no-session-persistence",
            "--tools", "",
        ]

        tier = _infer_tier(chosen_model)
        trigger = _infer_trigger(content)

        # Emit one `running` event before subprocess.run.
        self._publish_event(
            model=chosen_model,
            tier=tier,
            status="running",
            trigger=trigger,
            latency_ms=None,
            input_tokens=None,
            output_tokens=None,
            cost_usd=None,
        )

        # latency_ms is measured strictly around the subprocess.run call —
        # JSON parsing, event publishing, and any other Python work must NOT
        # be included so the metric reflects external CLI cost only.
        start = time.monotonic()
        try:
            result = self._runner(
                cmd,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                check=False,
            )
        except FileNotFoundError:
            latency_ms = int((time.monotonic() - start) * 1000)
            log.warning("BRIDGE_API_GOV set but `%s` CLI not on PATH; degrading", CLI_BIN)
            self._publish_event(
                model=chosen_model,
                tier=tier,
                status="failed",
                trigger=trigger,
                latency_ms=latency_ms,
                input_tokens=None,
                output_tokens=None,
                cost_usd=None,
            )
            return None
        except subprocess.TimeoutExpired:
            latency_ms = int((time.monotonic() - start) * 1000)
            log.warning("cli governance timeout (>%.1fs); degrading", TIMEOUT_SECONDS)
            self._publish_event(
                model=chosen_model,
                tier=tier,
                status="failed",
                trigger=trigger,
                latency_ms=latency_ms,
                input_tokens=None,
                output_tokens=None,
                cost_usd=None,
            )
            return None
        latency_ms = int((time.monotonic() - start) * 1000)

        # Pull token / cost telemetry from the CLI envelope. Defaults are
        # None when `usage` is absent (e.g. older CLI builds).
        in_tok, out_tok, cost = _extract_usage(result.stdout or "")

        if result.returncode != 0:
            log.warning(
                "cli governance non-zero exit %d; degrading (stderr=%r)",
                result.returncode,
                (result.stderr or "")[:200],
            )
            self._publish_event(
                model=chosen_model,
                tier=tier,
                status="failed",
                trigger=trigger,
                latency_ms=latency_ms,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost_usd=cost,
            )
            return None

        self._publish_event(
            model=chosen_model,
            tier=tier,
            status="exited",
            trigger=trigger,
            latency_ms=latency_ms,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
        )

        return _parse_envelope(result.stdout or "")

    def _publish_event(
        self,
        *,
        model: str,
        tier: str,
        status: str,
        trigger: str,
        latency_ms: int | None,
        input_tokens: int | None,
        output_tokens: int | None,
        cost_usd: float | None,
    ) -> None:
        """Publish a governance_call lifecycle event.

        No-op when either bus or session_id is unset (back-compat for tests
        that construct CliGovernor without a bus). Bus failures are caught
        and logged; they MUST NOT crash the subprocess wrapper (mirrors
        cli_client._emit's NFR-R6 try/except).
        """
        if self._bus is None or not self._session_id:
            return
        try:
            from stream_manager.message_bus import Message as _BusMessage
        except Exception:
            log.exception("cli_governance: failed to import message_bus.Message")
            return
        metadata: dict[str, object] = {
            "model": model,
            "tier": tier,
            "status": status,
            "latency_ms": latency_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
            "trigger": trigger,
        }
        try:
            self._bus.publish(
                _BusMessage.new(
                    session_id=self._session_id,
                    type="governance_call",
                    direction="internal",
                    content="",
                    metadata=metadata,
                )
            )
        except Exception:
            log.exception("cli_governance: failed to publish governance_call event")


def _extract_json_object(text: str) -> dict | None:
    """Extract first JSON object from text. Tolerates code fences + trailing prose.

    Strategy:
      1. Strip leading fence if present.
      2. Use json.JSONDecoder.raw_decode to consume the first valid JSON value
         from the start of the (post-fence) string, ignoring trailing content.
      3. Fall back to scanning for ``{`` and trying raw_decode at each position
         (handles models that prepend a sentence before the JSON).
    """
    s = text.strip()
    fence_match = re.match(r"^```(?:json)?\s*\n", s)
    if fence_match:
        s = s[fence_match.end():]
    decoder = json.JSONDecoder()
    try:
        obj, _ = decoder.raw_decode(s)
    except json.JSONDecodeError:
        for idx in range(len(s)):
            if s[idx] != "{":
                continue
            try:
                obj, _ = decoder.raw_decode(s[idx:])
                break
            except json.JSONDecodeError:
                continue
        else:
            return None
    return obj if isinstance(obj, dict) else None


def _debug_dump(stage: str, payload: str) -> None:
    """Append failing CLI payload to reports/cli_failures.jsonl when SM_CLI_DEBUG_DUMP=1."""
    if os.environ.get("SM_CLI_DEBUG_DUMP", "").lower() not in ("1", "true", "yes"):
        return
    import time as _t
    from pathlib import Path as _Path
    out_dir = _Path("reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    record = {"ts": _t.time(), "stage": stage, "payload": payload[:8000]}
    try:
        with (out_dir / "cli_failures.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        pass


def _extract_usage(stdout: str) -> tuple[int | None, int | None, float | None]:
    """Pull (input_tokens, output_tokens, total_cost_usd) from a CLI envelope.

    The Claude CLI emits ``{"usage": {"input_tokens": N, "output_tokens": N},
    "total_cost_usd": F, ...}`` in the result envelope. Each field is
    optional; missing keys yield None. Any parse failure returns (None,
    None, None) — telemetry is best-effort and must never break the call.
    """
    try:
        envelope = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return (None, None, None)
    if not isinstance(envelope, dict):
        return (None, None, None)
    usage = envelope.get("usage")
    in_tok: int | None = None
    out_tok: int | None = None
    if isinstance(usage, dict):
        raw_in = usage.get("input_tokens")
        raw_out = usage.get("output_tokens")
        if isinstance(raw_in, int):
            in_tok = raw_in
        if isinstance(raw_out, int):
            out_tok = raw_out
    raw_cost = envelope.get("total_cost_usd")
    cost: float | None = None
    if isinstance(raw_cost, (int, float)):
        cost = float(raw_cost)
    return (in_tok, out_tok, cost)


def _parse_envelope(stdout: str) -> CliDecision | None:
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError:
        log.warning("cli governance: outer JSON parse failed; degrading")
        _debug_dump("outer", stdout)
        return None

    if envelope.get("is_error"):
        log.warning("cli governance: envelope is_error=true; degrading")
        return None

    inner = envelope.get("result")
    if inner is None:
        return None
    if isinstance(inner, dict):
        data = inner
    elif isinstance(inner, str) and inner:
        data = _extract_json_object(inner)
        if data is None:
            log.warning("cli governance: inner JSON parse failed; degrading")
            _debug_dump("inner", inner)
            return None
    else:
        return None

    action = data.get("action")
    if action not in _VALID_ACTIONS:
        _debug_dump("action_enum", json.dumps(data))
        return None
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    reasoning = str(data.get("reasoning", ""))[:500]
    return CliDecision(action=action, confidence=confidence, reasoning=reasoning)
