"""Load Claude Code JSONL session transcripts into Message + success-hint pairs.

Real Claude Code sessions are recorded under ~/.claude/projects/<slug>/<sid>.jsonl.
Each line is one event with `type` ∈ {user, assistant, attachment, queue-operation, last-prompt}.
For governance replay we care about user/assistant messages and use the
following turn's tool_result.is_error flags as the success proxy.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from stream_manager.messages import Message


@dataclass(frozen=True)
class ReplayEvent:
    message: Message
    success: bool
    has_signal: bool


def _content_to_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                parts.append(str(block.get("text", "")))
            elif btype == "tool_use":
                name = block.get("name", "")
                inp = block.get("input", {})
                parts.append(f"<tool_use name={name} input={json.dumps(inp, default=str)[:400]}>")
            elif btype == "tool_result":
                inner = block.get("content", "")
                inner_txt = _content_to_text(inner) if not isinstance(inner, str) else inner
                parts.append(f"<tool_result>{inner_txt[:400]}")
            elif btype == "thinking":
                parts.append(f"<thinking>{str(block.get('thinking', ''))[:200]}")
        return "\n".join(parts)
    return ""


def _scan_tool_results(content: object) -> tuple[bool, bool]:
    """Return (has_tool_result, any_error). For success hint inference."""
    if not isinstance(content, list):
        return (False, False)
    has = False
    err = False
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            has = True
            if block.get("is_error") is True:
                err = True
    return (has, err)


def iter_events(path: str | Path) -> Iterator[ReplayEvent]:
    """Yield ReplayEvents in transcript order.

    Success hint:
      - For an assistant message that emits tool_use blocks, the success of
        the immediately following user message's tool_result is the hint.
      - For a user message (instructions): success hint = True (we have no
        signal that an instruction "failed"; the brain treats this as a
        positive ALLOW unless the next assistant turn errors out).
      - has_signal=False means the caller should NOT count the event toward
        the rolling accuracy window. We still observe it for pattern growth.
    """
    p = Path(path)
    raw: list[dict] = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                raw.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    for i, ev in enumerate(raw):
        t = ev.get("type")
        if t not in ("user", "assistant"):
            continue
        msg = ev.get("message", {})
        content_obj = msg.get("content", "")
        text = _content_to_text(content_obj)
        if not text:
            continue

        success = True
        has_signal = False
        if t == "assistant":
            for j in range(i + 1, min(i + 4, len(raw))):
                nxt = raw[j]
                if nxt.get("type") != "user":
                    continue
                nxt_msg = nxt.get("message", {})
                has_tr, err = _scan_tool_results(nxt_msg.get("content"))
                if has_tr:
                    has_signal = True
                    success = not err
                    break

        yield ReplayEvent(
            message=Message.new(role=t, content=text),
            success=success,
            has_signal=has_signal,
        )


def load_transcript(path: str | Path) -> list[ReplayEvent]:
    return list(iter_events(path))
