"""v1.8 P1 — content-detection helper unit tests.

Validates:
  * `_looks_ambiguous_block` heuristic — destructive intent that did NOT
    strict-match the precheck patterns in `project_context._DESTRUCTIVE`.
  * `_looks_hitl_synthesis` proxy — HITL wired AND a pre-decision
    DESKTOP_PAUSE-style signal (engine pause flag or PAUSE_PATTERNS
    match in content).

Helpers remain FROZEN per ADR-18 §"Initial classification" (v1.8 P1 row).
The Haiku fastpath router that consumed these flags was ripped at
v2.0 P3 (see ADR-18 §"Decommissioned"); the helpers themselves are
preserved for reuse by future work.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from stream_manager import message_bus as _msg_bus  # noqa: E402
from stream_manager.governance import (  # noqa: E402
    _looks_ambiguous_block,
    _looks_hitl_synthesis,
)
from stream_manager.hitl import HitlQueue  # noqa: E402


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
        # P2a imperative declarative forms — replaced P1c-B deliberative questions;
        # these are in _L2_L3_TRIGGER verbatim (soak positions 5 and 55):
        "Going to force-push main to roll back the broken merge — history already diverged.",
        "Running DELETE FROM governance_log WHERE age > 90 to reclaim disk space.",
        "Drop the metrics_archive table — nothing has referenced it in 60 days.",
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
