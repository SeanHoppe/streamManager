from __future__ import annotations

import time
from pathlib import Path

from stream_manager.project_context import fast_precheck, load


def test_load_picks_up_intent_when_present(tmp_path: Path) -> None:
    (tmp_path / "INTENT.md").write_text("# Project intent\nNo force-push.\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Hello\n", encoding="utf-8")
    snap = load(tmp_path)
    assert snap.has_intent_file is True
    assert "force-push" in snap.intent_text.lower()
    assert "README.md" in snap.docs


def test_ignore_intent_skips_intent_file(tmp_path: Path) -> None:
    (tmp_path / "INTENT.md").write_text("anything", encoding="utf-8")
    snap = load(tmp_path, ignore_intent=True)
    assert snap.has_intent_file is False
    assert snap.intent_text == ""


def test_fast_precheck_blocks_destructive_root_rm(tmp_path: Path) -> None:
    snap = load(tmp_path)
    d = fast_precheck("rm -rf / --no-preserve-root", snap)
    assert d is not None
    assert d.action == "BLOCK"


def test_fast_precheck_intervenes_on_force_push_main(tmp_path: Path) -> None:
    snap = load(tmp_path)
    d = fast_precheck("git push --force origin main", snap)
    assert d is not None
    assert d.action == "INTERVENE"


def test_fast_precheck_intent_rule_only_fires_with_intent(tmp_path: Path) -> None:
    (tmp_path / "INTENT.md").write_text(
        "Safety: no plaintext token storage in repo files.", encoding="utf-8"
    )
    snap_with = load(tmp_path)
    snap_without = load(tmp_path, ignore_intent=True)
    msg = "session_token = 'abc123def456'"
    d_with = fast_precheck(msg, snap_with)
    d_without = fast_precheck(msg, snap_without)
    assert d_with is not None and d_with.action == "INTERVENE"
    assert d_without is None


def test_fast_precheck_is_under_one_ms(tmp_path: Path) -> None:
    (tmp_path / "INTENT.md").write_text("No force-push.", encoding="utf-8")
    snap = load(tmp_path)
    samples = []
    for _ in range(200):
        t0 = time.perf_counter_ns()
        fast_precheck("pytest tests/", snap)
        samples.append(time.perf_counter_ns() - t0)
    median_us = sorted(samples)[len(samples) // 2] / 1000.0
    assert median_us < 1000.0, f"median fast_precheck = {median_us:.2f} us, target < 1000 us"
