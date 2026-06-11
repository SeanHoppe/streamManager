"""v10 P2 — caveman-review findings source adapter (deferred stub).

This module is a P2 corpus-augmentation adapter (sibling of cassette.py,
probe.py, golden.py), NOT part of the P5 shadow A/B harness. P5 lives in
``rl/shadow.py`` + ``rl/stop_conditions.py`` (shadow recorder + ship
criteria) and has nothing to do with corpus augmentation.

Per phase-2 spec item 4, the review adapter reads a caveman-review
findings JSONL (path via ``BRIDGE_RL_REVIEW_FINDINGS``); when the env is
unset or the file is missing it yields zero episodes (silent no-op). The
full parse is deferred as P2 continuation work, so today this stub yields
zero episodes unconditionally, keeping the augmenter import path stable.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Optional

from rl.sources import Episode


def iter_episodes(findings_path: Optional[Path] = None) -> Iterator[Episode]:
    """P2 deferred stub: always yields zero episodes (see module docstring)."""
    if False:  # pragma: no cover - generator marker
        yield  # type: ignore[unreachable]
    return
