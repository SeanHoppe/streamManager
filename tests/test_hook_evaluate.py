"""Tests for tools/hook_evaluate.py — the PreToolUse governance hook."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

# tools/ is not a package; load via path manipulation before importing.
_TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import hook_evaluate  # noqa: E402

from stream_manager.governance import GovDecision, GovernanceEngine, Mode  # noqa: E402


# ---------------------------------------------------------------------------
# _content_from_payload
# ---------------------------------------------------------------------------


def test_content_bash_returns_command():
    assert (
        hook_evaluate._content_from_payload(
            {"tool_name": "Bash", "tool_input": {"command": "pytest tests/"}}
        )
        == "pytest tests/"
    )


def test_content_bash_empty_command():
    assert hook_evaluate._content_from_payload({"tool_name": "Bash", "tool_input": {}}) == ""


def test_content_other_tool_includes_tool_name_and_fields():
    content = hook_evaluate._content_from_payload(
        {"tool_name": "Edit", "tool_input": {"file_path": "foo.py", "new_string": "x"}}
    )
    assert "tool:Edit" in content
    assert "file_path=foo.py" in content


def test_content_non_string_fields_skipped():
    content = hook_evaluate._content_from_payload(
        {"tool_name": "Write", "tool_input": {"file_path": "out.py", "lines": 42}}
    )
    assert "tool:Write" in content
    assert "42" not in content  # int field skipped


def test_content_empty_payload():
    assert hook_evaluate._content_from_payload({}) == ""


def test_content_truncates_long_fields():
    long_val = "x" * 1000
    content = hook_evaluate._content_from_payload(
        {"tool_name": "Read", "tool_input": {"file_path": long_val}}
    )
    assert len(content) < 500


# ---------------------------------------------------------------------------
# main() — allow path
# ---------------------------------------------------------------------------


def _stdin(payload: dict):
    return io.StringIO(json.dumps(payload))


def test_main_allows_safe_bash(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.stdin", _stdin(
        {"session_id": "s1", "tool_name": "Bash", "tool_input": {"command": "pytest tests/"}}
    ))
    monkeypatch.setenv("STREAM_MANAGER_BUS", str(tmp_path / "gov.db"))
    assert hook_evaluate.main() == 0


def test_main_allows_when_no_content(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.stdin", _stdin({"tool_name": "Bash", "tool_input": {}}))
    monkeypatch.setenv("STREAM_MANAGER_BUS", str(tmp_path / "gov.db"))
    assert hook_evaluate.main() == 0


def test_main_publishes_to_bus(monkeypatch, tmp_path):
    import sqlite3

    db = str(tmp_path / "gov.db")
    monkeypatch.setattr("sys.stdin", _stdin(
        {"session_id": "s2", "tool_name": "Bash", "tool_input": {"command": "ls -la"}}
    ))
    monkeypatch.setenv("STREAM_MANAGER_BUS", db)
    hook_evaluate.main()

    conn = sqlite3.connect(db)
    count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    conn.close()
    assert count == 1


# ---------------------------------------------------------------------------
# main() — block path
# ---------------------------------------------------------------------------


def test_main_exits_2_on_block(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("sys.stdin", _stdin(
        {"session_id": "s1", "tool_name": "Bash", "tool_input": {"command": "something"}}
    ))
    monkeypatch.setenv("STREAM_MANAGER_BUS", str(tmp_path / "gov.db"))

    def _fake_evaluate(self, msg):
        return GovDecision(
            action="BLOCK", confidence=0.99, reasoning="test block",
            mode=Mode.BLOCK, source="precheck",
        )

    monkeypatch.setattr(GovernanceEngine, "evaluate", _fake_evaluate)
    code = hook_evaluate.main()
    assert code == 2
    out = capsys.readouterr().out
    assert "[governance] BLOCK" in out
    assert "test block" in out


def test_main_exits_2_on_intervene(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("sys.stdin", _stdin(
        {"session_id": "s1", "tool_name": "Bash", "tool_input": {"command": "something"}}
    ))
    monkeypatch.setenv("STREAM_MANAGER_BUS", str(tmp_path / "gov.db"))

    def _fake_evaluate(self, msg):
        return GovDecision(
            action="INTERVENE", confidence=0.85, reasoning="intervene reason",
            mode=Mode.INTERVENE, source="precheck",
        )

    monkeypatch.setattr(GovernanceEngine, "evaluate", _fake_evaluate)
    code = hook_evaluate.main()
    assert code == 2
    assert "[governance] INTERVENE" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# main() — degradation
# ---------------------------------------------------------------------------


def test_main_degrade_bad_json(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
    assert hook_evaluate.main() == 0


def test_main_degrade_empty_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert hook_evaluate.main() == 0


def test_main_degrade_engine_exception(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.stdin", _stdin(
        {"tool_name": "Bash", "tool_input": {"command": "ls"}}
    ))
    monkeypatch.setenv("STREAM_MANAGER_BUS", str(tmp_path / "gov.db"))

    def _boom(self, msg):
        raise RuntimeError("engine exploded")

    monkeypatch.setattr(GovernanceEngine, "evaluate", _boom)
    assert hook_evaluate.main() == 0  # degrade, never re-raise


# ---------------------------------------------------------------------------
# Graph persistence across hook invocations
# ---------------------------------------------------------------------------


def test_hook_accumulates_graph_across_invocations(monkeypatch, tmp_path):
    from stream_manager.decision_graph import DecisionGraph

    db = str(tmp_path / "gov.db")
    monkeypatch.setenv("STREAM_MANAGER_BUS", db)

    for _ in range(3):
        monkeypatch.setattr(
            "sys.stdin",
            _stdin({"session_id": "s1", "tool_name": "Bash", "tool_input": {"command": "pytest tests/"}}),
        )
        hook_evaluate.main()

    g = DecisionGraph.load(db)
    assert any("pytest" in p.canonical_text for p in g.patterns.values())
    pat = next(p for p in g.patterns.values() if "pytest" in p.canonical_text)
    assert pat.occurrences >= 3


def test_hook_graph_survives_process_restart(monkeypatch, tmp_path):
    """Simulate process restart: reload hook module state between calls."""
    import importlib
    from stream_manager.decision_graph import DecisionGraph

    db = str(tmp_path / "gov.db")
    monkeypatch.setenv("STREAM_MANAGER_BUS", db)

    # First "process"
    monkeypatch.setattr(
        "sys.stdin",
        _stdin({"session_id": "s1", "tool_name": "Bash", "tool_input": {"command": "ruff check ."}}),
    )
    hook_evaluate.main()

    # Second "process" — graph loaded from DB, not in-memory
    monkeypatch.setattr(
        "sys.stdin",
        _stdin({"session_id": "s2", "tool_name": "Bash", "tool_input": {"command": "ruff check ."}}),
    )
    hook_evaluate.main()

    g = DecisionGraph.load(db)
    pat = next((p for p in g.patterns.values() if "ruff" in p.canonical_text), None)
    assert pat is not None
    assert pat.occurrences >= 2
