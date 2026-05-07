"""v10 P2 — tests for rl.sources.cassette (read-only over ADR-17 cassettes)."""

from __future__ import annotations

import json
from pathlib import Path

from rl.sources import VALID_VERDICTS, Episode
from rl.sources.cassette import iter_episodes


KNOWN = Path(__file__).resolve().parent / "fixtures" / "soak_cassette_latest.jsonl"


def test_iter_episodes_from_known_cassette() -> None:
    n_lines = sum(1 for ln in KNOWN.read_text(encoding="utf-8").splitlines() if ln.strip())
    eps = list(iter_episodes(KNOWN))
    assert 0 < len(eps) <= n_lines


def test_cassette_excludes_alignment_required_rows() -> None:
    """ADR-17: cassette excludes alignment rows -> fr_og_7_pass==1 always."""
    eps = list(iter_episodes(KNOWN))
    assert eps and all(ep.fr_og_7_pass == 1 for ep in eps)


def test_cassette_episode_fields_complete() -> None:
    """v10 schema parity for every yielded Episode."""
    eps = list(iter_episodes(KNOWN))
    assert eps
    for ep in eps:
        assert isinstance(ep, Episode)
        assert ep.source == "cassette"
        assert ep.cycle_tag == KNOWN.stem
        assert ep.action_propensity == 1.0
        assert ep.verdict in VALID_VERDICTS
        assert ep.session_id and ep.trace_id
        assert "regex_destructive_match" in ep.state_features
        assert "content_length" in ep.state_features
        assert ep.hitl_override is None and ep.budget_violation == 0


def test_cassette_skips_unknown_verdict(tmp_path: Path) -> None:
    fixture = tmp_path / "soak_cassette_test.jsonl"
    fixture.write_text("\n".join([
        json.dumps({"idx": 0, "kind": "x", "content": "ok",
                    "recorded_latency_ms": 1.0,
                    "decision": {"action": "ALLOW", "confidence": 0.9}}),
        json.dumps({"idx": 1, "kind": "x", "content": "x",
                    "recorded_latency_ms": 2.0,
                    "decision": {"action": "WAT", "confidence": 0.0}}),
        "", "not-json",
    ]) + "\n", encoding="utf-8")
    eps = list(iter_episodes(fixture))
    assert len(eps) == 1 and eps[0].verdict == "ALLOW"
