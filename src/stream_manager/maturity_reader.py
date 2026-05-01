"""FR-OG-7 maturity-ring reader (Phase 5).

Reads a project's `maturity.yaml` artifact and tracks ring-percentage
delta over time. The ring percentage is defined as

    ring_percent = count(cells where current >= threshold) / total_cells * 100

`MaturityReader.read()` is exception-tolerant by design: a missing file,
malformed YAML, or unexpected schema returns ``None`` so the governance
engine can dormant-skip FR-OG-7 signals without crashing the evaluation
pipeline.

`MaturityReader.refresh()` is debounced (10s) and returns a
``RingDelta`` describing the cells that crossed the threshold (in either
direction) since the previous successful read.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CellState:
    id: str
    threshold: int
    current: int

    @property
    def at_threshold(self) -> bool:
        return self.current >= self.threshold


@dataclass
class RingSnapshot:
    total: int
    at_threshold: int
    percent: float
    timestamp: float
    cells: list[CellState]


@dataclass
class RingDelta:
    old_percent: float
    new_percent: float
    delta: float
    regressed_cells: list[str]   # cell IDs that dropped below threshold
    promoted_cells: list[str]    # cell IDs that crossed threshold up
    elapsed_seconds: float


class MaturityReader:
    DEBOUNCE_SECONDS = 10.0

    def __init__(self, artifact_path: Path, bus: Any | None = None) -> None:
        self._path = Path(artifact_path)
        self._bus = bus
        self._last_snapshot: RingSnapshot | None = None
        self._last_read: float = 0.0

    def read(self) -> RingSnapshot | None:
        """Read maturity.yaml. Returns None on missing file or parse error."""
        if not self._path.exists():
            return None
        try:
            import yaml  # type: ignore[import-untyped]

            data = yaml.safe_load(self._path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        cells: list[CellState] = []
        try:
            for axis in data.get("axes", []) or []:
                if not isinstance(axis, dict):
                    continue
                for cell in axis.get("cells", []) or []:
                    if not isinstance(cell, dict):
                        continue
                    cid = cell.get("id")
                    if not isinstance(cid, str) or not cid:
                        continue
                    cells.append(
                        CellState(
                            id=cid,
                            threshold=int(cell.get("threshold", 1)),
                            current=int(cell.get("current", 0)),
                        )
                    )
        except Exception:
            return None
        total = len(cells)
        at_thresh = sum(1 for c in cells if c.at_threshold)
        pct = (at_thresh / total * 100) if total > 0 else 0.0
        return RingSnapshot(
            total=total,
            at_threshold=at_thresh,
            percent=pct,
            timestamp=time.time(),
            cells=cells,
        )

    def refresh(self) -> RingDelta | None:
        """Re-read if debounce elapsed; return RingDelta vs prior snapshot.

        Returns None when:
        - the debounce window has not elapsed yet, OR
        - the artifact is missing / unparseable, OR
        - this is the first successful read (no prior snapshot to diff).

        Otherwise returns a RingDelta. If the snapshot is unchanged, the
        delta will have ``delta == 0``, empty ``regressed_cells`` and
        empty ``promoted_cells`` — callers that want to filter no-op
        deltas should check those fields.
        """
        now = time.time()
        if now - self._last_read < self.DEBOUNCE_SECONDS:
            return None
        self._last_read = now
        new = self.read()
        if new is None:
            return None
        if self._last_snapshot is None:
            self._last_snapshot = new
            return None
        old = self._last_snapshot
        old_by_id = {c.id: c for c in old.cells}
        regressed = [
            c.id
            for c in new.cells
            if not c.at_threshold
            and old_by_id.get(c.id) is not None
            and old_by_id[c.id].at_threshold
        ]
        promoted = [
            c.id
            for c in new.cells
            if c.at_threshold
            and old_by_id.get(c.id) is not None
            and not old_by_id[c.id].at_threshold
        ]
        delta = RingDelta(
            old_percent=old.percent,
            new_percent=new.percent,
            delta=new.percent - old.percent,
            regressed_cells=regressed,
            promoted_cells=promoted,
            elapsed_seconds=new.timestamp - old.timestamp,
        )
        self._last_snapshot = new
        return delta

    @property
    def current_snapshot(self) -> RingSnapshot | None:
        return self._last_snapshot
