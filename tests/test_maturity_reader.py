"""Tests for the FR-OG-7 maturity-ring governance path (Phase 5).

Covers:
    - MaturityReader.read() shape + missing/parse-fail tolerance
    - MaturityReader.refresh() debounce + delta detection
    - GovernanceEngine._check_fr_og7() gate + signal short-circuits
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stream_manager.governance import GovernanceEngine
from stream_manager.maturity_reader import (
    CellState,
    MaturityReader,
    RingDelta,
    RingSnapshot,
)
from stream_manager.messages import Message
from stream_manager.project_context import ProjectContextSnapshot


# ── helpers ──────────────────────────────────────────────────────────


def _write_yaml(path: Path, axes: list[dict]) -> None:
    """Write a maturity.yaml-shaped file with the given axes structure."""
    import yaml

    path.write_text(yaml.safe_dump({"axes": axes}), encoding="utf-8")


def _engine_with_maturity(reader: MaturityReader | None) -> GovernanceEngine:
    return GovernanceEngine(
        project_context=ProjectContextSnapshot(repo_path="/tmp"),
        maturity=reader,
    )


# ── MaturityReader.read() ────────────────────────────────────────────


def test_read_returns_none_when_file_missing(tmp_path: Path) -> None:
    reader = MaturityReader(tmp_path / "missing.yaml")
    assert reader.read() is None


def test_read_parses_cells_and_computes_percent(tmp_path: Path) -> None:
    p = tmp_path / "maturity.yaml"
    _write_yaml(
        p,
        axes=[
            {
                "name": "Architecture",
                "cells": [
                    {"id": "AR-1", "threshold": 3, "current": 3},
                    {"id": "AR-2", "threshold": 3, "current": 1},
                ],
            },
            {
                "name": "Process",
                "cells": [
                    {"id": "PR-1", "threshold": 2, "current": 2},
                    {"id": "PR-2", "threshold": 5, "current": 5},
                ],
            },
        ],
    )
    reader = MaturityReader(p)
    snap = reader.read()
    assert snap is not None
    assert snap.total == 4
    assert snap.at_threshold == 3   # AR-1, PR-1, PR-2
    assert snap.percent == pytest.approx(75.0)
    ids = sorted(c.id for c in snap.cells)
    assert ids == ["AR-1", "AR-2", "PR-1", "PR-2"]


# ── MaturityReader.refresh() ─────────────────────────────────────────


def test_refresh_returns_none_when_debounce_not_elapsed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "maturity.yaml"
    _write_yaml(p, axes=[{"cells": [{"id": "X-1", "threshold": 1, "current": 1}]}])
    reader = MaturityReader(p)

    fake_now = [1000.0]
    monkeypatch.setattr(
        "stream_manager.maturity_reader.time.time", lambda: fake_now[0]
    )
    # First refresh seeds; returns None.
    assert reader.refresh() is None
    # Second call within the debounce window: also None (NOT due to seeding).
    fake_now[0] += 1.0
    assert reader.refresh() is None


def test_refresh_returns_delta_with_regressed_cells(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "maturity.yaml"
    _write_yaml(
        p,
        axes=[
            {
                "cells": [
                    {"id": "AR-1", "threshold": 3, "current": 3},
                    {"id": "AR-2", "threshold": 3, "current": 3},
                ]
            }
        ],
    )
    reader = MaturityReader(p)

    fake_now = [1000.0]
    monkeypatch.setattr(
        "stream_manager.maturity_reader.time.time", lambda: fake_now[0]
    )
    # Seed.
    assert reader.refresh() is None

    # Advance past debounce; regress AR-2 below threshold.
    fake_now[0] += 30.0
    _write_yaml(
        p,
        axes=[
            {
                "cells": [
                    {"id": "AR-1", "threshold": 3, "current": 3},
                    {"id": "AR-2", "threshold": 3, "current": 1},
                ]
            }
        ],
    )
    delta = reader.refresh()
    assert delta is not None
    assert delta.regressed_cells == ["AR-2"]
    assert delta.promoted_cells == []
    assert delta.delta == pytest.approx(-50.0)


def test_refresh_returns_delta_with_promoted_cells(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "maturity.yaml"
    _write_yaml(
        p,
        axes=[
            {
                "cells": [
                    {"id": "AR-1", "threshold": 3, "current": 1},
                    {"id": "AR-2", "threshold": 3, "current": 1},
                ]
            }
        ],
    )
    reader = MaturityReader(p)

    fake_now = [2000.0]
    monkeypatch.setattr(
        "stream_manager.maturity_reader.time.time", lambda: fake_now[0]
    )
    assert reader.refresh() is None  # seed

    fake_now[0] += 30.0
    _write_yaml(
        p,
        axes=[
            {
                "cells": [
                    {"id": "AR-1", "threshold": 3, "current": 3},
                    {"id": "AR-2", "threshold": 3, "current": 1},
                ]
            }
        ],
    )
    delta = reader.refresh()
    assert delta is not None
    assert delta.promoted_cells == ["AR-1"]
    assert delta.regressed_cells == []
    assert delta.delta == pytest.approx(50.0)


# ── GovernanceEngine._check_fr_og7() ─────────────────────────────────


def test_check_fr_og7_returns_none_when_maturity_disabled() -> None:
    """Gate condition: maturity=None -> FR-OG-7 dormant -> returns None."""
    engine = _engine_with_maturity(None)
    msg = Message.new(role="user", content="anything")
    assert engine._check_fr_og7(msg, active_profile_slug="developer") is None


def test_check_fr_og7_returns_block_on_negative_regression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative cell regression must short-circuit to BLOCK with confidence=1.0."""

    class _StubReader:
        current_snapshot = None

        def refresh(self) -> RingDelta:
            return RingDelta(
                old_percent=50.0,
                new_percent=40.0,
                delta=-10.0,
                regressed_cells=["AR-2"],
                promoted_cells=[],
                elapsed_seconds=600.0,
            )

    engine = _engine_with_maturity(_StubReader())   # type: ignore[arg-type]
    msg = Message.new(role="user", content="hello")
    decision = engine._check_fr_og7(msg, active_profile_slug=None)
    assert decision is not None
    assert decision.action == "BLOCK"
    assert decision.confidence == pytest.approx(1.0)
    assert decision.source == "fr_og7_regression"


def test_check_fr_og7_returns_allow_for_sweep_job_pattern() -> None:
    """developer→code_reviewer→tester→researcher slug stream → ALLOW@0.95."""

    class _NoopReader:
        current_snapshot = None

        def refresh(self) -> None:
            return None

    engine = _engine_with_maturity(_NoopReader())   # type: ignore[arg-type]
    msg = Message.new(role="user", content="msg")

    # First three slugs should not match yet.
    for slug in ("developer", "code_reviewer", "tester"):
        d = engine._check_fr_og7(msg, active_profile_slug=slug)
        assert d is None, f"unexpected match at slug={slug!r}: {d}"

    # The 4th (researcher) closes the window — ALLOW@0.95.
    decision = engine._check_fr_og7(msg, active_profile_slug="researcher")
    assert decision is not None
    assert decision.action == "ALLOW"
    assert decision.confidence == pytest.approx(0.95)
    assert decision.source == "fr_og7_sweep"


def test_check_fr_og7_returns_guide_for_aar_missing_deviations() -> None:
    """AAR text without `## Deviations` literal -> GUIDE@0.80."""

    class _NoopReader:
        current_snapshot = None

        def refresh(self) -> None:
            return None

    engine = _engine_with_maturity(_NoopReader())   # type: ignore[arg-type]
    aar = Message.new(
        role="user",
        content="AAR for sprint 7\n## Outcomes\nshipped\n## Lessons\n...",
    )
    decision = engine._check_fr_og7(aar, active_profile_slug=None)
    assert decision is not None
    assert decision.action == "GUIDE"
    assert decision.confidence == pytest.approx(0.80)
    assert decision.source == "fr_og7_aar"

    # Sanity: when ## Deviations IS present, no GUIDE fires.
    aar_ok = Message.new(
        role="user",
        content="AAR for sprint 7\n## Deviations\nnone\n",
    )
    assert engine._check_fr_og7(aar_ok, active_profile_slug=None) is None


# ── Bonus: dataclass plumbing ────────────────────────────────────────


def test_cellstate_at_threshold_property() -> None:
    assert CellState(id="X", threshold=3, current=3).at_threshold is True
    assert CellState(id="X", threshold=3, current=2).at_threshold is False


def test_ringsnapshot_dataclass_shape() -> None:
    s = RingSnapshot(
        total=2, at_threshold=1, percent=50.0, timestamp=0.0,
        cells=[CellState("A", 1, 1), CellState("B", 1, 0)],
    )
    assert s.total == 2 and s.at_threshold == 1 and s.percent == 50.0
