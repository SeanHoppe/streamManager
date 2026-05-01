"""Optional CLI-backed L2 escalation for the governance engine.

Activated by ``BRIDGE_API_GOV=true``. When unset, this module is a stub that
returns ``None`` — the engine falls back to its local-only path (precheck +
graph). When enabled, ambiguous content (no precheck hit, no high-confidence
graph match) escalates to the locally-installed Claude Code CLI via
``subprocess.run``. There is no Anthropic API key path; auth lives in the
user's logged-in CLI session.

Design choices:

  • Transport: ``claude -p <prompt> --output-format json --model <id>``.
    Subprocess run with a wall-clock timeout. The CLI cold-start dominates
    latency, so the budget is 5s (vs. the SDK path's old 2s).
  • Output shape: the CLI emits ``{"type": "result", "result": "<text>", ...}``.
    The inner ``result`` string is what the model produced; we parse it as
    JSON against ``_DECISION_SCHEMA``. Schema enforcement is prompt-only —
    the CLI does not pass through json_schema constraints to the model.
  • Errors: any failure (CLI missing, non-zero exit, timeout, malformed
    JSON, action-enum mismatch) returns ``None`` so the engine degrades
    cleanly to local-only behavior.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass

from stream_manager.project_context import ProjectContextSnapshot

log = logging.getLogger(__name__)

ENV_FLAG = "BRIDGE_API_GOV"
MODEL = "claude-haiku-4-5"
TIMEOUT_SECONDS = 5.0
CLI_BIN = "claude"

_VALID_ACTIONS = frozenset({"ALLOW", "SUGGEST", "GUIDE", "INTERVENE", "BLOCK"})

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
    "the project's intent. Choose ALLOW for routine safe actions, SUGGEST "
    "for borderline cases worth flagging, GUIDE/INTERVENE for actions that "
    "should be redirected, and BLOCK only for clearly destructive or "
    "intent-violating actions. Reply ONLY with a single JSON object matching "
    "this schema (no prose, no markdown fence):\n"
    "{schema}\n\n"
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
    ) -> None:
        self.project_context = project_context
        self._runner = runner or subprocess.run
        self._system: str | None = None

    def _system_prompt(self) -> str:
        if self._system is not None:
            return self._system
        intent = self.project_context.intent_text or "(no INTENT.md loaded)"
        self._system = _SYSTEM_TEMPLATE.format(
            schema=json.dumps(_DECISION_SCHEMA),
            intent=intent[:8000],
        )
        return self._system

    def evaluate(self, content: str) -> CliDecision | None:
        if not is_enabled():
            return None

        prompt = f"{self._system_prompt()}\n\nEvaluate this proposed action:\n\n{content[:4000]}"
        cmd = [CLI_BIN, "-p", prompt, "--output-format", "json", "--model", MODEL]

        try:
            result = self._runner(
                cmd,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                check=False,
            )
        except FileNotFoundError:
            log.warning("BRIDGE_API_GOV set but `%s` CLI not on PATH; degrading", CLI_BIN)
            return None
        except subprocess.TimeoutExpired:
            log.warning("cli governance timeout (>%.1fs); degrading", TIMEOUT_SECONDS)
            return None

        if result.returncode != 0:
            log.warning(
                "cli governance non-zero exit %d; degrading (stderr=%r)",
                result.returncode,
                (result.stderr or "")[:200],
            )
            return None

        return _parse_envelope(result.stdout or "")


def _parse_envelope(stdout: str) -> CliDecision | None:
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError:
        log.warning("cli governance: outer JSON parse failed; degrading")
        return None

    if envelope.get("is_error"):
        log.warning("cli governance: envelope is_error=true; degrading")
        return None

    inner_text = envelope.get("result")
    if not isinstance(inner_text, str) or not inner_text:
        return None

    try:
        data = json.loads(inner_text)
    except json.JSONDecodeError:
        log.warning("cli governance: inner JSON parse failed; degrading")
        return None

    action = data.get("action")
    if action not in _VALID_ACTIONS:
        return None
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    reasoning = str(data.get("reasoning", ""))[:500]
    return CliDecision(action=action, confidence=confidence, reasoning=reasoning)
