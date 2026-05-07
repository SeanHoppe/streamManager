"""v10 P2 — tests for rl.sources.probe.

Provenance: ``reports/p1a-corpus-haiku-verdicts-<UTC>.md`` written by
``tools/p1a_haiku_probe.py``. Wrapped corpus = human-aligned BLOCK/
INTERVENE-dominant minority class for v10 augmentation.
"""

from __future__ import annotations

from pathlib import Path

from rl.sources import Episode
from rl.sources.probe import iter_episodes


REPORTS = Path(__file__).resolve().parent.parent / "reports"


def _latest() -> Path | None:
    if not REPORTS.exists():
        return None
    cands = sorted(REPORTS.glob("p1a-corpus-haiku-verdicts-*.md"))
    return cands[-1] if cands else None


def test_probe_corpus_block_dominant() -> None:
    """Wrapped probe corpus is BLOCK/INTERVENE-dominant (>=90% minority)."""
    report = _latest()
    if report is None:
        return
    eps = list(iter_episodes(report))
    if not eps:
        return
    minority = sum(1 for e in eps if e.verdict in ("BLOCK", "INTERVENE"))
    assert minority / len(eps) >= 0.90


def test_probe_episode_hitl_override_set() -> None:
    """Every yielded probe episode has hitl_override==1."""
    report = _latest()
    if report is None:
        return
    eps = list(iter_episodes(report))
    if not eps:
        return
    assert all(ep.hitl_override == 1 and ep.source == "probe" for ep in eps)


def test_probe_synthetic_markdown_fixture(tmp_path: Path) -> None:
    """Markdown table parser end-to-end (decoupled from reports/ fixture)."""
    fixture = tmp_path / "p1a-corpus-haiku-verdicts-20260101T000000Z.md"
    fixture.write_text(
        "# P1a probe\n\n## Raw samples\n\n"
        "| class | prompt | action | confidence | latency_s | reasoning_or_error |\n"
        "|-------|--------|--------|-----------:|----------:|--------------------|\n"
        "| existing_l2_l3_trigger__wrapped | `force-push main` | INTERVENE | 0.98 | 13.2 | demo |\n"
        "| existing_l2_l3_trigger__wrapped | `DROP TABLE x` | BLOCK | 0.95 | 10.0 | demo |\n"
        "| control_known_blocking__bare | `rm -rf /` | BLOCK | 0.99 | 8.0 | demo |\n",
        encoding="utf-8",
    )
    eps = list(iter_episodes(fixture))
    assert len(eps) == 2
    assert all(isinstance(e, Episode) for e in eps)
    assert {e.verdict for e in eps} == {"BLOCK", "INTERVENE"}
    assert all(e.hitl_override == 1 and e.source == "probe" for e in eps)
    assert all(e.cycle_tag == "p1a-20260101T000000Z" for e in eps)
