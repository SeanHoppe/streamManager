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
from dataclasses import dataclass

from stream_manager.project_context import ProjectContextSnapshot

log = logging.getLogger(__name__)

ENV_FLAG = "BRIDGE_API_GOV"
MODEL = "claude-haiku-4-5"
TIMEOUT_SECONDS = 25.0
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
    ) -> None:
        self.project_context = project_context
        self._runner = runner or subprocess.run
        self._system: str | None = None

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
