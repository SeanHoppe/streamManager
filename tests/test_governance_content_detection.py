"""v1.8 P1 — content-detection wiring at the pre-routing call site.

Validates:
  * `_looks_ambiguous_block` heuristic — destructive intent that did NOT
    strict-match the precheck patterns in `project_context._DESTRUCTIVE`.
  * `_looks_hitl_synthesis` proxy — HITL wired AND a pre-decision
    DESKTOP_PAUSE-style signal (engine pause flag or PAUSE_PATTERNS
    match in content).
  * `engine.evaluate(...)` threads both flags through to
    `model_router.route()` such that:
      - destructive content       → `pre_routing.fallback_model_id == get_l4_model()`
      - HITL synthesis context     → `pre_routing.fallback_model_id == get_l4_model()`
      - benign content             → `pre_routing.fallback_model_id is None`
      - alignment-required content → `requires_alignment=True` and
                                     `fallback_model_id is None` REGARDLESS
                                     of the other two flags (FR-OG-7
                                     protected; precedence enforced by
                                     `model_router.route()`).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from stream_manager import message_bus as _msg_bus  # noqa: E402
from stream_manager.governance import (  # noqa: E402
    GovernanceEngine,
    _looks_ambiguous_block,
    _looks_hitl_synthesis,
)
from stream_manager.hitl import HitlQueue  # noqa: E402
from stream_manager.maturity_reader import MaturityReader  # noqa: E402
from stream_manager.messages import Message  # noqa: E402
from stream_manager.model_router import get_l2_model, get_l4_model  # noqa: E402
from stream_manager.project_context import ProjectContextSnapshot  # noqa: E402


# ────────────────────────────────────────────────────────────────────
# Pure-helper unit tests
# ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "content",
    [
        "rm -rf node_modules",                    # broader than precheck (no /-anchor)
        "git push --force feature/test",          # any branch (precheck only protected)
        "DROP SCHEMA app",                        # SCHEMA not in precheck
        "TRUNCATE TABLE users",                   # not in precheck
        "DELETE FROM accounts WHERE 1=1",         # not in precheck
        "chmod 777 /var/www",                     # not in precheck
        ":(){:|:&};:",                            # fork bomb
        "shutdown -h now",                        # not in precheck
        # P1a prose forms — cassette prompts + L4 soak content that missed
        # the literal-only patterns:
        "Force push to main now?",                # cassette: force-push prose
        "force-push to the release branch",       # hyphenated variant
        "Drop user_settings table?",              # cassette: drop-X-table prose
        "drop the legacy_precheck table",         # drop + article + table
        "Going to delete the legacy precheck table, regenerate from transcripts",  # L4 soak form
        "delete the user_events table before migration",  # delete ... table prose
        # P1c-B hybrid prompts — deliberative+destructive; must stay True or
        # soak fallback path breaks (these are in _L2_L3_TRIGGER verbatim):
        "Should I force push this branch? The history is messy.",
        "Not sure whether to drop the staging table or archive it first.",
        "Wondering whether to delete the old metrics table or migrate the data.",
    ],
)
def test_looks_ambiguous_block_positive(content: str) -> None:
    assert _looks_ambiguous_block(content) is True


@pytest.mark.parametrize(
    "content",
    [
        "",
        "let's discuss the architecture",
        "the README mentions config flags",
        "git status",
        "list the files in src/",
        "I would like to understand the routing layer",
        "can you summarize the design doc",
        # P1a negative controls: prose that SOUNDS similar but must not fire
        "I pushed a change forcefully to unblock the team",   # "force" but not "force push"
        "we should drop the feature flag for dark mode",      # drop + non-table target
        "delete unused imports from the module",              # delete without table
        "rip out the old compat shim",                        # destructive verb, no pattern
        "silently drop FR-OG-7 maturity tracking",            # drop + tracking, not table
        "drop the shadow from the element",                   # drop + non-table target (no "table" token)
        "delete table",                                        # bare SQL form — {1,4} requires ≥1 word between
    ],
)
def test_looks_ambiguous_block_negative(content: str) -> None:
    assert _looks_ambiguous_block(content) is False


def test_looks_hitl_synthesis_no_hitl_returns_false() -> None:
    assert _looks_hitl_synthesis("should I proceed?", None, False) is False
    assert _looks_hitl_synthesis("anything", None, True) is False


def test_looks_hitl_synthesis_pause_pattern_match(tmp_path) -> None:
    bus = _msg_bus.MessageBus(str(tmp_path / "hitl.db"))
    try:
        hitl = HitlQueue(bus=bus)
        assert _looks_hitl_synthesis("should I proceed?", hitl, False) is True
        assert _looks_hitl_synthesis("Please confirm before merging.", hitl, False) is True
        assert _looks_hitl_synthesis("are we good to go?", hitl, False) is True
    finally:
        bus.close()


def test_looks_hitl_synthesis_desktop_pause_active(tmp_path) -> None:
    bus = _msg_bus.MessageBus(str(tmp_path / "hitl.db"))
    try:
        hitl = HitlQueue(bus=bus)
        # desktop pause set → True regardless of content shape
        assert _looks_hitl_synthesis("just running tests", hitl, True) is True
        assert _looks_hitl_synthesis("", hitl, True) is True
    finally:
        bus.close()


def test_looks_hitl_synthesis_benign_content_returns_false(tmp_path) -> None:
    bus = _msg_bus.MessageBus(str(tmp_path / "hitl.db"))
    try:
        hitl = HitlQueue(bus=bus)
        assert _looks_hitl_synthesis("running pytest now", hitl, False) is False
        assert _looks_hitl_synthesis("git status", hitl, False) is False
    finally:
        bus.close()


# ────────────────────────────────────────────────────────────────────
# Integration: engine.evaluate threads flags → pre_routing → CLI
# ────────────────────────────────────────────────────────────────────


@dataclass
class _CapturedCall:
    content: str
    model_id: str | None
    fallback_model_id: str | None


class _CapturingCliGovernor:
    """Stand-in CliGovernor that captures evaluate() args without spawning a
    subprocess. `engine._maybe_cli_evaluate` calls `_cli_governor.evaluate`
    after the pre-routing decision; recording `fallback_model_id` here
    proves the flag was threaded correctly through `pre_routing`.
    """

    def __init__(self) -> None:
        self.calls: list[_CapturedCall] = []

    def evaluate(
        self,
        content: str,
        *,
        model_id: str | None = None,
        sub_timings: dict | None = None,
        fallback_model_id: str | None = None,
    ):
        self.calls.append(
            _CapturedCall(
                content=content,
                model_id=model_id,
                fallback_model_id=fallback_model_id,
            )
        )
        # Populate residue keys so the post-decision routing path stays
        # byte-identical with the v1.6 instrumentation contract.
        if sub_timings is not None:
            for k in (
                "cli_dispatch_ms",
                "cli_pool_acquire_ms",
                "cli_pool_send_ms",
                "cli_parse_ms",
                "cli_dispatch_fallback_ms",
            ):
                sub_timings.setdefault(k, 0.0)
        return None  # → engine falls through to default ALLOW


def _make_cli_engine(tmp_path, name: str, monkeypatch) -> tuple[
    GovernanceEngine, _msg_bus.MessageBus, str, _CapturingCliGovernor
]:
    monkeypatch.setenv("BRIDGE_API_GOV", "true")
    db = tmp_path / f"{name}.db"
    bus = _msg_bus.MessageBus(str(db))
    sid = f"content-detect-{name}"
    bus.open_session(sid, project_slug="test", pid=0)
    snap = ProjectContextSnapshot(repo_path=str(ROOT))
    eng = GovernanceEngine(project_context=snap, bus=bus, session_id=sid)
    cap = _CapturingCliGovernor()
    eng._cli_governor = cap  # type: ignore[assignment]
    return eng, bus, sid, cap


def _close(bus: _msg_bus.MessageBus, sid: str) -> None:
    try:
        bus.close_session(sid)
    except Exception:
        pass
    try:
        bus.close()
    except Exception:
        pass


def test_destructive_content_threads_fallback_to_cli(tmp_path, monkeypatch) -> None:
    """`rm -rf node_modules` misses precheck → reaches pre_routing →
    `is_ambiguous_block=True` → router places call on L4 sub-band with
    Haiku primary + Sonnet fallback. CLI captures the threaded flags."""
    eng, bus, sid, cap = _make_cli_engine(tmp_path, "destructive", monkeypatch)
    try:
        msg = Message.new(role="user", content="rm -rf node_modules in the repo root")
        eng.evaluate(msg)
        assert len(cap.calls) == 1, "CLI escalation should fire exactly once"
        call = cap.calls[0]
        assert call.model_id == get_l2_model(), "Haiku-fastpath primary"
        assert call.fallback_model_id == get_l4_model(), (
            "ambiguous-BLOCK heuristic should activate Sonnet fallback"
        )
    finally:
        _close(bus, sid)


def test_benign_content_keeps_fallback_none(tmp_path, monkeypatch) -> None:
    """Non-destructive content keeps the v1.7 default: pre_routing returns
    L3/Haiku with `fallback_model_id is None` (sub-band dormant)."""
    eng, bus, sid, cap = _make_cli_engine(tmp_path, "benign", monkeypatch)
    try:
        msg = Message.new(
            role="user",
            content="run npm install in the package directory",
        )
        eng.evaluate(msg)
        assert len(cap.calls) == 1
        call = cap.calls[0]
        assert call.model_id == get_l2_model()
        assert call.fallback_model_id is None, (
            "v1.7 default state — sub-band must stay dormant on benign content"
        )
    finally:
        _close(bus, sid)


def test_hitl_synthesis_context_threads_fallback(tmp_path, monkeypatch) -> None:
    """HITL wired + desktop_pause_active → `is_hitl_synthesis=True` →
    sub-band activates with Haiku primary + Sonnet fallback."""
    eng, bus, sid, cap = _make_cli_engine(tmp_path, "hitl", monkeypatch)
    try:
        eng.hitl = HitlQueue(bus=bus)
        eng.signal_desktop_pause()
        msg = Message.new(role="user", content="run npm install in the package dir")
        eng.evaluate(msg)
        assert len(cap.calls) == 1
        call = cap.calls[0]
        assert call.model_id == get_l2_model()
        assert call.fallback_model_id == get_l4_model(), (
            "HITL synthesis context should activate Sonnet fallback"
        )
    finally:
        _close(bus, sid)


def test_alignment_keeps_sonnet_only_regardless_of_other_flags(
    tmp_path, monkeypatch
) -> None:
    """FR-OG-7 protected: `requires_alignment=True` always wins inside
    `model_router.route()` and returns Sonnet with `fallback_model_id=None`,
    even when the other two flags are also True. Precedence is enforced
    inside the router — the call site just passes flags raw."""
    eng, bus, sid, cap = _make_cli_engine(tmp_path, "align", monkeypatch)
    try:
        # Maturity wired so `_looks_alignment_action` activates.
        eng.maturity = MaturityReader(artifact_path=tmp_path / "no-such-maturity.yaml")
        eng.hitl = HitlQueue(bus=bus)
        eng.signal_desktop_pause()  # also forces is_hitl_synthesis=True
        # Content carries alignment kw ("merge") AND destructive shape
        # (`rm -rf node_modules`) AND HITL-pause ("should I"). All three
        # pre-routing flags True → router must still pick Sonnet-only.
        msg = Message.new(
            role="user",
            content=(
                "should I merge release/v1.8 after rm -rf node_modules to clean up?"
            ),
        )
        eng.evaluate(msg)
        assert len(cap.calls) == 1
        call = cap.calls[0]
        assert call.model_id == get_l4_model(), (
            "alignment must pin primary to Sonnet"
        )
        assert call.fallback_model_id is None, (
            "FR-OG-7 alignment must NEVER carry a Haiku fallback"
        )
    finally:
        _close(bus, sid)


def test_v17_default_state_byte_identical(tmp_path, monkeypatch) -> None:
    """Verdict-path invariant: when both new flags are False (v1.7 default),
    pre_routing.fallback_model_id is None and `_maybe_cli_evaluate` is
    invoked with `fallback_model_id=None`. Same as v1.7 ship-gate baseline.
    """
    eng, bus, sid, cap = _make_cli_engine(tmp_path, "v17-default", monkeypatch)
    try:
        # No HITL wired (default), no destructive content, no alignment.
        assert eng.hitl is None
        msg = Message.new(role="user", content="run npm install foo")
        eng.evaluate(msg)
        assert len(cap.calls) == 1
        assert cap.calls[0].fallback_model_id is None
    finally:
        _close(bus, sid)
