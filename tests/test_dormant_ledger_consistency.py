"""v2.0 P4 drift-detection: WIRED_LEVER_LEDGER ↔ ADR-18 HTML comment.

ADR-18 Rule 2 (DORMANT-N) codification has two co-located surfaces:
  1. `tools/soak_driver.WIRED_LEVER_LEDGER` (dict, source of truth for
     post-soak summary signal).
  2. `docs/adr/ADR-18-mvp-surface-freeze.md` `<!-- WIRED_LEVER_LEDGER_COUNT: N -->`
     HTML comment (governance ledger row count).

Future re-introductions or rips MUST update both in the same PR. This
test catches drift between the two.
"""

from __future__ import annotations

import re
from pathlib import Path

from tools.soak_driver import WIRED_LEVER_LEDGER


REPO_ROOT = Path(__file__).resolve().parents[1]
ADR_18_PATH = REPO_ROOT / "docs" / "adr" / "ADR-18-mvp-surface-freeze.md"


def _read_adr_18_count() -> int:
    text = ADR_18_PATH.read_text(encoding="utf-8")
    match = re.search(r"WIRED_LEVER_LEDGER_COUNT:\s*(\d+)", text)
    assert match is not None, (
        f"WIRED_LEVER_LEDGER_COUNT HTML comment missing in {ADR_18_PATH}. "
        "Restore it to keep the dormant-ledger drift-detection test "
        "honest."
    )
    return int(match.group(1))


def test_wired_lever_ledger_matches_adr_18():
    adr_count = _read_adr_18_count()
    dict_count = len(WIRED_LEVER_LEDGER)
    assert dict_count == adr_count, (
        f"ADR-18 says {adr_count} wired levers; soak_driver dict has "
        f"{dict_count}. Update both in the same PR (ADR-18 HTML "
        "comment + tools/soak_driver.WIRED_LEVER_LEDGER)."
    )
