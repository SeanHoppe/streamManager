"""F5 cluster: cassette PPP/audit envelope rows must round-trip through
the soak-driver replay loader without a schema conflict.

Latent bug (F5-ppp-envelope-cassette-replay-gap and siblings):
``cassette_record._record_ppp_envelopes`` / ``_record_decoy_envelopes``
emit rows shaped ``{idx, kind, envelope}`` (and one ``{idx, kind, row}``
decoy-register entry), but ``soak_driver._load_cassette`` historically
mandated ``content`` / ``recorded_latency_ms`` / ``decision`` on EVERY
row. No committed cassette included PPP rows, so the conflict was
unreachable -- it would surface the moment a cassette carried the PPP
envelope set. These tests pin the envelope-aware loader behaviour so the
two ends of the seam stay compatible.
"""

from __future__ import annotations

import contextlib
import importlib
import json
import sys
from pathlib import Path

from stream_manager.message_bus import MessageBus

ROOT = Path(__file__).resolve().parent.parent
_TOOLS = str(ROOT / "tools")


def _load_cassette_record():
    if _TOOLS not in sys.path:
        sys.path.insert(0, _TOOLS)
    sys.modules.pop("cassette_record", None)
    return importlib.import_module("cassette_record")


def _load_soak_driver():
    if _TOOLS not in sys.path:
        sys.path.insert(0, _TOOLS)
    return importlib.import_module("soak_driver")


def _record_ppp_rows(tmp_path) -> list[dict]:
    cr = _load_cassette_record()
    bus = MessageBus(str(tmp_path / "ppp_bus.db"))
    bus.open_session("cs-ppp", project_slug="t", pid=1)
    try:
        return cr._record_ppp_envelopes(bus, "cs-ppp", start_idx=200)
    finally:
        with contextlib.suppress(Exception):
            bus.close_session("cs-ppp")
        with contextlib.suppress(Exception):
            bus.close()


def test_ppp_envelope_rows_are_envelope_shaped(tmp_path) -> None:
    """Every PPP/decoy coverage row is an envelope row (no verdict triple)."""
    sd = _load_soak_driver()
    rows = _record_ppp_rows(tmp_path)
    assert rows, "recorder produced no PPP rows"
    for row in rows:
        assert "kind" in row
        # These rows are envelope-shaped, not verdict-replay rows.
        assert sd._is_envelope_row(row), row
        # And they explicitly LACK the verdict-replay triple, which is the
        # exact mismatch the old loader choked on.
        assert "content" not in row
        assert "decision" not in row
        assert "recorded_latency_ms" not in row


def test_ppp_cassette_loads_without_schema_error(tmp_path) -> None:
    """A cassette mixing verdict rows + PPP envelope rows loads cleanly."""
    sd = _load_soak_driver()
    ppp_rows = _record_ppp_rows(tmp_path)

    verdict_row = {
        "idx": 0,
        "kind": "routine",
        "content": "git status",
        "recorded_latency_ms": 12.5,
        "decision": {
            "action": "ALLOW",
            "confidence": 0.99,
            "reasoning": "routine",
            "matched_hash": "",
            "model_used": "replay",
            "layer": 0,
        },
    }

    cassette = tmp_path / "mixed_ppp.jsonl"
    with cassette.open("w", encoding="utf-8") as fp:
        fp.write(json.dumps(verdict_row) + "\n")
        for row in ppp_rows:
            fp.write(json.dumps(row) + "\n")

    # Pre-fix this raised ValueError("missing field 'content'") on the
    # first PPP row.
    loaded = sd._load_cassette(cassette)
    assert len(loaded) == 1 + len(ppp_rows)
    # Verdict row preserved; envelope rows preserved and classified.
    assert loaded[0]["kind"] == "routine"
    envelope_rows = [r for r in loaded if sd._is_envelope_row(r)]
    assert len(envelope_rows) == len(ppp_rows)


def test_ppp_only_cassette_load_classifies_all_rows(tmp_path) -> None:
    """A PPP-only cassette loads; every row is envelope-classified."""
    sd = _load_soak_driver()
    ppp_rows = _record_ppp_rows(tmp_path)

    cassette = tmp_path / "ppp_only.jsonl"
    with cassette.open("w", encoding="utf-8") as fp:
        for row in ppp_rows:
            fp.write(json.dumps(row) + "\n")

    loaded = sd._load_cassette(cassette)
    assert loaded, "PPP-only cassette failed to load"
    assert all(sd._is_envelope_row(r) for r in loaded)


def test_verdict_row_still_requires_full_triple(tmp_path) -> None:
    """Envelope-aware loosening must NOT weaken verdict-row validation."""
    sd = _load_soak_driver()
    bad = tmp_path / "bad_verdict.jsonl"
    # A non-envelope row missing the verdict triple must still be rejected.
    bad.write_text(
        json.dumps({"kind": "routine", "content": "x"}) + "\n",
        encoding="utf-8",
    )
    import pytest

    with pytest.raises(ValueError, match="missing field"):
        sd._load_cassette(bad)
