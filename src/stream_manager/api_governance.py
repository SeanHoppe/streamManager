"""Optional LLM-backed L2 escalation for the governance engine.

Activated by `BRIDGE_API_GOV=true`. When unset, this module is a stub that
returns None — the engine falls back to its local-only path (precheck +
graph). When enabled, ambiguous content (no precheck hit, no high-confidence
graph match) escalates to Claude Haiku 4.5 with a hard 2s wall-clock budget
(NFR-P2 from POC_FINDINGS) and a structured-output schema.

Design choices justified by `claude-api` skill guidance:

  • Model: `claude-haiku-4-5` — fast + cheap; no `effort` param (Haiku
    doesn't support it; would 400).
  • Thinking: omitted (Haiku 4.5 has no adaptive thinking).
  • Output: `output_config.format` json_schema (NOT prefill — prefill 400s
    on Opus/Sonnet 4.6+ family; we use the same shape for consistency and
    forward-compat if we swap models).
  • Caching: stable system+intent prefix carries cache_control. Below the
    Haiku 4096-token minimum the cache won't fire — silent, by design.
  • Errors: typed SDK exceptions (RateLimitError, APIError) — never string
    matching. On any failure we return a low-confidence ALLOW so the engine
    degrades to local-only behavior.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

from stream_manager.project_context import ProjectContextSnapshot

log = logging.getLogger(__name__)

ENV_FLAG = "BRIDGE_API_GOV"
MODEL = "claude-haiku-4-5"
TIMEOUT_SECONDS = 2.0
MAX_TOKENS = 256

_DECISION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["ALLOW", "SUGGEST", "GUIDE", "INTERVENE", "BLOCK"],
        },
        "confidence": {"type": "number"},
        "reasoning": {"type": "string"},
    },
    "required": ["action", "confidence", "reasoning"],
    "additionalProperties": False,
}

_SYSTEM_TEMPLATE = (
    "You are a code-action governance evaluator. Given a proposed action a "
    "developer assistant is about to take, decide whether it aligns with "
    "the project's intent. Choose ALLOW for routine safe actions, SUGGEST "
    "for borderline cases worth flagging, GUIDE/INTERVENE for actions that "
    "should be redirected, and BLOCK only for clearly destructive or "
    "intent-violating actions. Reply ONLY with JSON matching the schema.\n\n"
    "Project intent:\n{intent}"
)


@dataclass(frozen=True)
class ApiDecision:
    action: str
    confidence: float
    reasoning: str


def is_enabled() -> bool:
    return os.environ.get(ENV_FLAG, "").lower() in ("1", "true", "yes")


class ApiGovernor:
    """Wraps the Anthropic client with the governance prompt + caching.

    Constructed lazily so the SDK isn't imported when the flag is off.
    """

    def __init__(self, project_context: ProjectContextSnapshot, client: object | None = None):
        self.project_context = project_context
        self._client = client
        self._system: list[dict] | None = None

    def _ensure_client(self) -> object:
        if self._client is not None:
            return self._client
        import anthropic
        self._client = anthropic.Anthropic()
        return self._client

    def _system_blocks(self) -> list[dict]:
        if self._system is not None:
            return self._system
        intent = self.project_context.intent_text or "(no INTENT.md loaded)"
        text = _SYSTEM_TEMPLATE.format(intent=intent[:8000])
        self._system = [
            {
                "type": "text",
                "text": text,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        return self._system

    def evaluate(self, content: str) -> ApiDecision | None:
        """Return an ApiDecision, or None on failure / when disabled."""
        if not is_enabled():
            return None

        try:
            import anthropic
        except ImportError:
            log.warning("BRIDGE_API_GOV set but anthropic SDK not installed")
            return None

        client = self._ensure_client()
        try:
            response = client.with_options(timeout=TIMEOUT_SECONDS).messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=self._system_blocks(),
                messages=[{"role": "user", "content": _user_prompt(content)}],
                output_config={
                    "format": {
                        "type": "json_schema",
                        "schema": _DECISION_SCHEMA,
                    }
                },
            )
        except anthropic.APITimeoutError:
            log.warning("api governance timeout (>%.1fs); degrading", TIMEOUT_SECONDS)
            return None
        except anthropic.RateLimitError:
            log.warning("api governance rate-limited; degrading")
            return None
        except anthropic.APIError as e:
            log.warning("api governance error (%s); degrading", e.__class__.__name__)
            return None

        return _parse_response(response)


def _user_prompt(content: str) -> str:
    return f"Evaluate this proposed action:\n\n{content[:4000]}"


def _parse_response(response: object) -> ApiDecision | None:
    text = ""
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", "") or ""
            break
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("api governance: non-JSON response despite schema; degrading")
        return None

    action = data.get("action")
    if action not in {"ALLOW", "SUGGEST", "GUIDE", "INTERVENE", "BLOCK"}:
        return None
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    reasoning = str(data.get("reasoning", ""))[:500]
    return ApiDecision(action=action, confidence=confidence, reasoning=reasoning)
