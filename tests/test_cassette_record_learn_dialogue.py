"""v1.3 Path-A: cassette recorder Learn Mode dialogue extension.

Validates that the recorder's ``_record_lm_dialogue`` helper:

1. Publishes ``desktop_prompt`` + ``user_reply`` envelopes for every pair
   in ``_LM_DIALOGUE_PAIRS`` (10 pairs).
2. Calls the categorizer per pair (mocked via the ``runner`` injection
   point exposed by ``learn_categorizer.categorize_pair``).
3. Returns one ``learn_dialogue`` cassette row per pair with the new
   schema fields populated.
4. Falls back to ``unknown`` / 0.0 confidence on categorizer failure.

Real Sonnet calls are NOT exercised here — that's the job of M2 / M3.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import cassette_record  # noqa: E402
from stream_manager.message_bus import MessageBus  # noqa: E402


@pytest.fixture
def fresh_bus(tmp_path):
    db = tmp_path / "cassette_bus.db"
    bus = MessageBus(str(db))
    bus.open_session("cassette-test", project_slug="test", pid=0)
    try:
        yield bus
    finally:
        bus.close_session("cassette-test")
        bus.close()


def _fake_runner_factory(category: str = "approve", confidence: float = 0.9):
    """Return a runner that mimics ``subprocess.run`` returning a Sonnet
    envelope with the given category/confidence.
    """
    class _Result:
        def __init__(self, stdout):
            self.stdout = stdout
            self.returncode = 0

    inner = json.dumps({
        "category": category,
        "confidence": confidence,
        "reasoning": "test",
    })
    envelope = json.dumps({"is_error": False, "result": inner})

    def _runner(cmd, **kwargs):
        return _Result(envelope)

    return _runner


def test_record_lm_dialogue_emits_one_row_per_pair(fresh_bus):
    runner = _fake_runner_factory()
    rows = cassette_record._record_lm_dialogue(
        fresh_bus, "cassette-test", start_idx=60, runner=runner
    )
    assert len(rows) == len(cassette_record._LM_DIALOGUE_PAIRS) == 10
    for offset, row in enumerate(rows):
        assert row["kind"] == "learn_dialogue"
        assert row["idx"] == 60 + offset
        # Required cassette schema fields are present so old replay
        # validation passes.
        for k in ("kind", "content", "recorded_latency_ms", "decision"):
            assert k in row
        # New v1.3 fields.
        for k in (
            "desktop_prompt",
            "user_reply",
            "recorded_categorize_latency_ms",
            "category_result",
        ):
            assert k in row
        # Decision is ALLOW + carries the category in reasoning.
        assert row["decision"]["action"] == "ALLOW"
        assert row["decision"]["reasoning"].startswith("category=")
        # Category result mirrors the runner verdict.
        assert row["category_result"]["category"] == "approve"
        assert row["category_result"]["confidence"] == pytest.approx(0.9)


def test_record_lm_dialogue_publishes_paired_envelopes(fresh_bus):
    runner = _fake_runner_factory(category="reject", confidence=0.7)
    cassette_record._record_lm_dialogue(
        fresh_bus, "cassette-test", start_idx=0, runner=runner
    )
    # Each pair publishes one desktop_prompt + one user_reply with pair_id.
    rows = fresh_bus.fetch_rows(
        "SELECT type, content, metadata FROM messages "
        "WHERE session_id='cassette-test' AND type IN ('desktop_prompt','user_reply') "
        "ORDER BY id ASC"
    )
    assert len(rows) == 20  # 10 prompts + 10 replies
    prompts = [r for r in rows if r[0] == "desktop_prompt"]
    replies = [r for r in rows if r[0] == "user_reply"]
    assert len(prompts) == 10 and len(replies) == 10
    for r in replies:
        meta = json.loads(r[2])
        assert "pair_id" in meta and meta["pair_id"]
        assert meta.get("synthetic") is True


def test_record_lm_dialogue_falls_back_on_categorizer_failure(fresh_bus):
    """If the runner returns malformed output, the row records an
    ``unknown`` category with 0.0 confidence — no exception escapes.
    """
    class _Result:
        stdout = "<not json>"
        returncode = 0

    def _bad_runner(cmd, **kwargs):
        return _Result()

    rows = cassette_record._record_lm_dialogue(
        fresh_bus, "cassette-test", start_idx=0, runner=_bad_runner
    )
    assert len(rows) == 10
    for row in rows:
        assert row["category_result"]["category"] == "unknown"
        assert row["category_result"]["confidence"] == 0.0


def test_lm_dialogue_pairs_contains_actionable_categories():
    """The pre-canned table covers approve + reject (the only categories
    that produce an actionable bias hint per learn_categorizer §3.2).
    """
    pairs = cassette_record._LM_DIALOGUE_PAIRS
    assert len(pairs) == 10
    # Spot check that the expected actionable category prompts are present.
    prompts = [p for p, _ in pairs]
    assert any("force push" in p.lower() for p in prompts)
    assert any("rm -rf" in p.lower() or "drop user_settings" in p.lower()
               for p in prompts)
