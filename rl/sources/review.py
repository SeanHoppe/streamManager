"""v10 P5 stub — caveman-review findings adapter (LOC-budget escape).

Per phase-2 spec §"LOC budget", review.py is moved to a P5 stub when
the augmenter + adapters draft exceeds 500 LOC. Full implementation
lands in P5; today this stub yields zero episodes unconditionally so
the augmenter import path is stable.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Optional

from rl.sources import Episode


def iter_episodes(findings_path: Optional[Path] = None) -> Iterator[Episode]:
    """P5 stub: always yields zero episodes."""
    if False:  # pragma: no cover - generator marker
        yield  # type: ignore[unreachable]
    return
