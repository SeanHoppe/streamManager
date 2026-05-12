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
from stream_manager.governance import EngineRegistry  # noqa: E402
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
    _startup_cwd = Path.cwd()
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

    rl_logger_close = None  # set by rl.bus_subscriber.attach when env-enabled
    try:
        snap = load(ROOT)
        bus: MessageBus | None = None
        if bus_path:
            bus = MessageBus(bus_path)
            if session_id:
                slug = os.environ.get("STREAM_MANAGER_PROJECT") or _startup_cwd.name
                bus.open_session(session_id, project_slug=slug, pid=os.getpid())
            # v10 P4 B': opt-in subscribe `rl_episodes.db` to live
            # decisions. No-op when BRIDGE_RL_LOGGER_ENABLED unset
            # (ADR-5 §"v10 logging overhead" zero-cost default).
            try:
                from rl.bus_subscriber import attach as _rl_attach
                rl_db = os.environ.get("BRIDGE_RL_EPISODES_DB", "rl_episodes.db")
                rl_logger_close = _rl_attach(bus, rl_db)
            except Exception:
                log.exception("rl bus_subscriber attach failed; gov continues")

        # Per-session engine via registry. The hook process is short-lived,
        # so the registry holds at most one engine per invocation; the
        # routing pattern matches long-lived contexts (dashboard, soak).
        registry = EngineRegistry(
            bus=bus,
            project_context=snap,
            graph_factory=(
                (lambda: DecisionGraph.load(bus_path)) if bus_path else (lambda: DecisionGraph())
            ),
        )
        engine = registry.get_or_create(session_id or "default")
        decision = engine.evaluate(Message.new("tool", content))
        engine.observe_for_learning(Message.new("tool", content), success=True)

        if bus_path:
            engine.graph.save(bus_path)
        if rl_logger_close is not None:
            try:
                rl_logger_close()
            except Exception:
                log.exception("rl bus_subscriber close failed")
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
