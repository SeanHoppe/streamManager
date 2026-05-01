"""PreToolUse hook — routes proposed tool calls through GovernanceEngine.

Claude Code invokes this before every matched tool call. Protocol:
  stdin  : JSON {"session_id": "...", "tool_name": "...", "tool_input": {...}}
  stdout : blocking reason (only when exit 2)
  exit 0 : allow
  exit 2 : block/intervene (stdout shown to Claude + user as the reason)

Any failure degrades to exit 0 so governance never stalls legitimate work.
Engine starts in OBSERVE mode (all actions allowed, decisions recorded) and
promotes to enforcement modes as feedback accumulates.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from stream_manager.decision_graph import DecisionGraph  # noqa: E402
from stream_manager.governance import GovernanceEngine  # noqa: E402
from stream_manager.message_bus import MessageBus  # noqa: E402
from stream_manager.messages import Message  # noqa: E402
from stream_manager.project_context import load  # noqa: E402

log = logging.getLogger(__name__)

# Override with STREAM_MANAGER_BUS env var to point at a custom DB path.
DEFAULT_BUS_PATH = str(ROOT / ".claude" / "gov.db")
BLOCK_EXIT = 2


def _content_from_payload(payload: dict) -> str:
    """Distil hook payload into a string the governance engine can evaluate."""
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})

    if not tool_name:
        return ""

    if tool_name == "Bash":
        return tool_input.get("command", "")

    parts = [f"tool:{tool_name}"]
    for k, v in sorted(tool_input.items()):
        if isinstance(v, str) and v:
            parts.append(f"{k}={v[:400]}")
    return " ".join(parts)


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        return 0

    content = _content_from_payload(payload)
    if not content:
        return 0

    session_id = payload.get("session_id", "")
    bus_path = os.environ.get("STREAM_MANAGER_BUS", DEFAULT_BUS_PATH)

    try:
        snap = load(ROOT)
        graph = DecisionGraph.load(bus_path) if bus_path else DecisionGraph()
        bus: MessageBus | None = None
        if bus_path:
            bus = MessageBus(bus_path)
            if session_id:
                bus.open_session(session_id, project_slug=ROOT.name, pid=os.getpid())

        engine = GovernanceEngine(project_context=snap, graph=graph, bus=bus, session_id=session_id)
        decision = engine.evaluate(Message.new("tool", content))
        engine.observe_for_learning(Message.new("tool", content), success=True)

        if bus_path:
            graph.save(bus_path)
        if bus is not None:
            bus.close()

    except Exception:
        log.exception("governance hook error; degrading to allow")
        return 0

    if decision.action in {"BLOCK", "INTERVENE"}:
        print(f"[governance] {decision.action}: {decision.reasoning}")
        return BLOCK_EXIT

    return 0


if __name__ == "__main__":
    sys.exit(main())
