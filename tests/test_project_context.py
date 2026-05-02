from __future__ import annotations

import time
from pathlib import Path

from stream_manager import project_context as _pc
from stream_manager.project_context import fast_precheck, load, load_sm_context


def test_load_picks_up_intent_when_present(tmp_path: Path) -> None:
    (tmp_path / "INTENT.md").write_text("# Project intent\nNo force-push.\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Hello\n", encoding="utf-8")
    snap = load(tmp_path)
    assert snap.has_intent_file is True
    assert "force-push" in snap.intent_text.lower()
    assert "README.md" in snap.docs


def test_ignore_intent_skips_intent_file(tmp_path: Path) -> None:
    (tmp_path / "INTENT.md").write_text("anything", encoding="utf-8")
    snap = load(tmp_path, ignore_intent=True)
    assert snap.has_intent_file is False
    assert snap.intent_text == ""


def test_fast_precheck_blocks_destructive_root_rm(tmp_path: Path) -> None:
    snap = load(tmp_path)
    d = fast_precheck("rm -rf / --no-preserve-root", snap)
    assert d is not None
    assert d.action == "BLOCK"


def test_fast_precheck_intervenes_on_force_push_main(tmp_path: Path) -> None:
    snap = load(tmp_path)
    d = fast_precheck("git push --force origin main", snap)
    assert d is not None
    assert d.action == "INTERVENE"


def test_fast_precheck_intent_rule_only_fires_with_intent(tmp_path: Path) -> None:
    (tmp_path / "INTENT.md").write_text(
        "Safety: no plaintext token storage in repo files.", encoding="utf-8"
    )
    snap_with = load(tmp_path)
    snap_without = load(tmp_path, ignore_intent=True)
    msg = "session_token = 'abc123def456'"
    d_with = fast_precheck(msg, snap_with)
    d_without = fast_precheck(msg, snap_without)
    assert d_with is not None and d_with.action == "INTERVENE"
    assert d_without is None


# ── FR-OG-7 loud-degrade ──────────────────────────────────────────────


class _RecordingBus:
    def __init__(self) -> None:
        self.published: list = []

    def publish(self, msg) -> int:
        self.published.append(msg)
        return len(self.published)


def _reset_og7_guard() -> None:
    _pc._OG7_UNCONFIGURED_EMITTED.clear()


def test_load_sm_context_emits_og7_unconfigured_when_file_absent(tmp_path: Path) -> None:
    _reset_og7_guard()
    bus = _RecordingBus()
    result = load_sm_context(tmp_path, bus=bus, session_id="test-sid")
    assert result is None
    assert len(bus.published) == 1
    msg = bus.published[0]
    assert msg.type == "og7_unconfigured"
    assert msg.direction == "internal"
    assert msg.session_id == "test-sid"
    assert msg.metadata.get("project_root") == str(tmp_path)
    assert msg.metadata.get("expected_path", "").endswith(".sm-context.yaml")


def test_load_sm_context_emits_only_once_per_project_root(tmp_path: Path) -> None:
    _reset_og7_guard()
    bus = _RecordingBus()
    load_sm_context(tmp_path, bus=bus)
    load_sm_context(tmp_path, bus=bus)
    load_sm_context(tmp_path, bus=bus)
    assert len(bus.published) == 1


def test_load_sm_context_no_emit_when_file_present(tmp_path: Path) -> None:
    _reset_og7_guard()
    (tmp_path / ".sm-context.yaml").write_text("maturity:\n  artifact_path: maturity.yaml\n", encoding="utf-8")
    bus = _RecordingBus()
    result = load_sm_context(tmp_path, bus=bus)
    assert isinstance(result, dict)
    assert bus.published == []


def test_load_sm_context_no_bus_returns_none_silently(tmp_path: Path) -> None:
    _reset_og7_guard()
    # Backwards-compat: callers without bus get the original silent behavior.
    assert load_sm_context(tmp_path) is None
    assert load_sm_context(tmp_path, bus=None) is None


# ---------------------------------------------------------------------------
# Meta-content precheck — must ALLOW without CLI escalation
# ---------------------------------------------------------------------------

def test_precheck_allows_thinking_block(tmp_path: Path) -> None:
    snap = load(tmp_path)
    d = fast_precheck("<thinking>\nSome chain-of-thought here.\n</thinking>", snap)
    assert d is not None
    assert d.action == "ALLOW"
    assert "thinking" in d.reasoning


def test_precheck_allows_local_command_caveat(tmp_path: Path) -> None:
    snap = load(tmp_path)
    d = fast_precheck(
        "<local-command-caveat>These messages generated locally.</local-command-caveat>", snap
    )
    assert d is not None
    assert d.action == "ALLOW"
    assert "cli-metadata" in d.reasoning


def test_precheck_allows_command_name_tag(tmp_path: Path) -> None:
    snap = load(tmp_path)
    d = fast_precheck("<command-name>/compact</command-name>", snap)
    assert d is not None
    assert d.action == "ALLOW"


def test_precheck_allows_tool_use_xml(tmp_path: Path) -> None:
    snap = load(tmp_path)
    d = fast_precheck('<parameter name="command">ls -la</parameter>', snap)
    assert d is not None
    assert d.action == "ALLOW"


def test_precheck_allows_caveman_mode_active(tmp_path: Path) -> None:
    snap = load(tmp_path)
    d = fast_precheck("CAVEMAN MODE ACTIVE — level: ultra", snap)
    assert d is not None
    assert d.action == "ALLOW"
    assert "plugin-mode-switch" in d.reasoning


def test_precheck_allows_caveman_ultra(tmp_path: Path) -> None:
    snap = load(tmp_path)
    d = fast_precheck("caveman ultra ON.", snap)
    assert d is not None
    assert d.action == "ALLOW"


def test_precheck_allows_short_conversational_ack(tmp_path: Path) -> None:
    snap = load(tmp_path)
    for ack in ("go", "yes", "ok", "continue", "proceed", "done", "got it"):
        d = fast_precheck(ack, snap)
        assert d is not None and d.action == "ALLOW", f"ack {ack!r} should be ALLOW"


def test_precheck_does_not_allow_shell_in_short_message(tmp_path: Path) -> None:
    snap = load(tmp_path)
    # "rm" is a shell command — must NOT be short-circuited by conversational rule
    d = fast_precheck("rm", snap)
    assert d is None or d.action != "ALLOW" or "meta-content" not in d.reasoning


def test_precheck_destructive_still_fires_before_meta(tmp_path: Path) -> None:
    snap = load(tmp_path)
    # Even if message contains a thinking tag, destructive pattern wins
    d = fast_precheck("rm -rf / <thinking>oops</thinking>", snap)
    assert d is not None
    assert d.action == "BLOCK"


def test_fast_precheck_is_under_one_ms(tmp_path: Path) -> None:
    (tmp_path / "INTENT.md").write_text("No force-push.", encoding="utf-8")
    snap = load(tmp_path)
    samples = []
    for _ in range(200):
        t0 = time.perf_counter_ns()
        fast_precheck("pytest tests/", snap)
        samples.append(time.perf_counter_ns() - t0)
    median_us = sorted(samples)[len(samples) // 2] / 1000.0
    assert median_us < 1000.0, f"median fast_precheck = {median_us:.2f} us, target < 1000 us"


def test_precheck_allows_conversational_explanation(tmp_path: Path) -> None:
    snap = load(tmp_path)
    d = fast_precheck(
        "Let me explain the approach I will take for this refactor.", snap
    )
    assert d is not None
    assert d.action == "ALLOW"
    assert "no-actionable-signal" in d.reasoning


def test_precheck_allows_multi_sentence_plan(tmp_path: Path) -> None:
    snap = load(tmp_path)
    d = fast_precheck(
        "I'll read the relevant files first, then identify the bug, "
        "then propose a fix in the response.", snap
    )
    assert d is not None
    assert d.action == "ALLOW"


def test_precheck_does_not_allow_content_with_shell_command(tmp_path: Path) -> None:
    snap = load(tmp_path)
    # "git" is an actionable signal → should NOT be short-circuited
    d = fast_precheck("I am going to run git status to check the repo.", snap)
    assert d is None or "no-actionable-signal" not in (d.reasoning or "")


def test_precheck_does_not_allow_content_with_file_extension(tmp_path: Path) -> None:
    snap = load(tmp_path)
    d = fast_precheck("Editing governance.py to add the new feature.", snap)
    assert d is None or "no-actionable-signal" not in (d.reasoning or "")


def test_precheck_does_not_allow_content_with_url(tmp_path: Path) -> None:
    snap = load(tmp_path)
    d = fast_precheck("Fetching data from https://api.example.com/endpoint.", snap)
    assert d is None or "no-actionable-signal" not in (d.reasoning or "")


def test_precheck_destructive_still_wins_over_no_signal_rule(tmp_path: Path) -> None:
    snap = load(tmp_path)
    # rm -rf / has no extension/URL but IS in destructive list — must still BLOCK
    d = fast_precheck("rm -rf /", snap)
    assert d is not None
    assert d.action == "BLOCK"
