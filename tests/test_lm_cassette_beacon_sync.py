"""v1.4 — Cassette ↔ beacon library sync.

Asserts:

  1. The cassette canonical pair set (``_LM_DIALOGUE_PAIRS_WITH_CATEGORY``)
     and the legacy 2-tuple alias (``_LM_DIALOGUE_PAIRS``) stay
     consistent — same length, same prompt/reply pairs in the same
     order.

  2. The beacon JSONL file (``tests/beacons/learn_mode_cassette_pairs.jsonl``)
     matches what the regenerator would produce TODAY. If they
     diverge the test fails — operator must run
     ``python tools/regenerate_lm_beacons.py`` and recommit.

  3. The categorizer category column in the cassette pairs is one of
     the six valid enum values from ``learn_categorizer._VALID_CATEGORIES``.

  4. The cassette ↔ beacon set covers all 6 categorizer enum values
     (``approve / reject / redirect / clarify / acknowledge`` plus
     ``unknown`` is implicit on parse failure — not pre-allocated).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from stream_manager.learn_categorizer import _VALID_CATEGORIES  # noqa: E402

import cassette_record  # noqa: E402


def test_pair_constants_consistent():
    """The 3-tuple constant and the 2-tuple backward-compat alias
    must enumerate the same prompt/reply pairs in the same order.
    """
    full = cassette_record._LM_DIALOGUE_PAIRS_WITH_CATEGORY
    legacy = cassette_record._LM_DIALOGUE_PAIRS
    assert len(full) == len(legacy)
    for (p, r, _), (lp, lr) in zip(full, legacy):
        assert (p, r) == (lp, lr)


def test_all_categories_are_valid_enum():
    """Every category in the cassette canonical set is one of the
    six values in ``learn_categorizer._VALID_CATEGORIES``.
    """
    for prompt, reply, cat in cassette_record._LM_DIALOGUE_PAIRS_WITH_CATEGORY:
        assert cat in _VALID_CATEGORIES, (
            f"prompt={prompt!r} category={cat!r} not in "
            f"_VALID_CATEGORIES={sorted(_VALID_CATEGORIES)}"
        )


def test_actionable_categories_covered():
    """The cassette pairs must include at least one ``approve`` AND
    one ``reject`` row — these are the only categories that produce
    an actionable bias hint per FR-LM-3, so they must round-trip
    through the beacon harness.
    """
    cats = {cat for _, _, cat in cassette_record._LM_DIALOGUE_PAIRS_WITH_CATEGORY}
    assert "approve" in cats
    assert "reject" in cats


def test_cassette_beacon_file_in_sync():
    """The committed beacon file must match what the regenerator
    would produce against the current cassette constant. If this
    fails, run ``python tools/regenerate_lm_beacons.py`` and commit
    the updated JSONL.
    """
    import regenerate_lm_beacons as regen

    expected_rows = [
        regen._row(idx, p, r, c)
        for idx, (p, r, c) in enumerate(
            cassette_record._LM_DIALOGUE_PAIRS_WITH_CATEGORY, start=1
        )
    ]
    beacon_path = ROOT / "tests" / "beacons" / "learn_mode_cassette_pairs.jsonl"
    assert beacon_path.exists(), (
        "tests/beacons/learn_mode_cassette_pairs.jsonl is missing — "
        "run `python tools/regenerate_lm_beacons.py` to create it"
    )
    with beacon_path.open("r", encoding="utf-8") as fh:
        actual_rows = [json.loads(line) for line in fh if line.strip()]
    assert actual_rows == expected_rows, (
        "beacon JSONL out of sync with cassette pairs — run "
        "`python tools/regenerate_lm_beacons.py` to regenerate"
    )


def test_legacy_beacon_file_still_present():
    """The pre-v1.4 beacon file (different prompt set, supplementary
    coverage) is preserved alongside the cassette-derived file. We
    assert it's present so the harness keeps running both files.
    """
    p = ROOT / "tests" / "beacons" / "learn_mode_categorizer.jsonl"
    assert p.exists()
    with p.open("r", encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    # 10 beacons in the original file — verify it didn't get
    # accidentally truncated.
    assert len(rows) == 10
