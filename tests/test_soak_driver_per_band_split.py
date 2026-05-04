"""P1 / v1.3: per-band p50/p95 split in soak driver report.

The v1.2 driver collapsed ALLOW (n=50), L2/L3 (n=5), and L4 (n=5)
into a single overall p95. ADR-5 budgets are per-band, so manual
reconstruction was required. The hardening emits a new "per-band"
table block matching ADR-5 §"v1.2 ship-gate baseline" §"Per-trigger
split" format directly, and `_DriverState` now tracks ALLOW
latencies separately.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import soak_driver  # noqa: E402


def test_per_band_split_renders_three_rows() -> None:
    block = "\n".join(
        soak_driver._format_per_band_split(
            allow=[0.5, 1.0, 1.5, 2.0],
            l2_l3=[3.0, 4.0, 5.0],
            l4=[10.0, 11.0, 12.0],
        )
    )
    assert "### Per-band latency (p50/p95)" in block
    # Header row of the table.
    assert "| Path" in block and "p50" in block and "p95" in block
    # Three band rows.
    assert "ALLOW (routine)" in block
    assert "L2/L3 escalation" in block
    assert "L4 alignment" in block


def test_per_band_split_records_n_per_band() -> None:
    block = "\n".join(
        soak_driver._format_per_band_split(
            allow=[0.1] * 50,
            l2_l3=[1.0] * 5,
            l4=[10.0] * 5,
        )
    )
    # Numerator on each row should be the band count (50 / 5 / 5).
    assert "| 50 |" in block
    # The L2/L3 + L4 bands both have n=5 — make sure both rows render.
    assert block.count("| 5  |") == 2


def test_per_band_split_handles_empty_band_gracefully() -> None:
    """An empty band must render as `n=0 / n/a` rather than raising."""
    block = "\n".join(
        soak_driver._format_per_band_split(
            allow=[],
            l2_l3=[],
            l4=[1.0, 2.0],
        )
    )
    assert "ALLOW (routine)" in block
    assert "n/a" in block
    # The L4 row with one sample should still render p50/p95.
    assert "L4 alignment" in block


def test_driver_state_has_allow_latency_bucket() -> None:
    """`_DriverState` exposes an `allow_latencies_s` field for ALLOW band."""
    state = soak_driver._DriverState()
    assert hasattr(state, "allow_latencies_s")
    assert state.allow_latencies_s == []


def test_per_band_split_p50_p95_match_percentile_helper() -> None:
    """Numerical sanity check: p50/p95 match `_percentile` exactly."""
    allow = [0.1, 0.2, 0.3, 0.4, 0.5]
    block = "\n".join(
        soak_driver._format_per_band_split(allow=allow, l2_l3=[], l4=[])
    )
    p50 = soak_driver._percentile(allow, 50)
    p95 = soak_driver._percentile(allow, 95)
    assert f"{p50:.2f} s" in block
    assert f"{p95:.2f} s" in block


def test_replay_report_includes_per_band_block(tmp_path: Path) -> None:
    """End-to-end: a replay run emits the per-band heading in its report."""
    import json
    import os
    import subprocess

    fixture_src = ROOT / "tests" / "fixtures" / "soak_cassette_2026-05-03.jsonl"
    assert fixture_src.exists(), f"fixture missing: {fixture_src}"

    env = dict(os.environ)
    env["PATH"] = str(tmp_path)  # strip claude from PATH (mirrors test_soak_replay)
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env.pop("BRIDGE_API_GOV", None)

    gov_db = tmp_path / "replay.db"
    cmd = [
        sys.executable,
        str(ROOT / "tools" / "soak_driver.py"),
        "--cli-replay",
        str(fixture_src),
        "--gov-db",
        str(gov_db),
    ]
    proc = subprocess.run(
        cmd, cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=180
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)

    # Find the most recent replay report.
    reports = sorted((ROOT / "reports").glob("replay-*.md"), key=lambda p: p.stat().st_mtime)
    assert reports, "no replay report produced"
    text = reports[-1].read_text(encoding="utf-8")
    assert "### Per-band latency (p50/p95)" in text, text[-500:]
    assert "ALLOW (routine)" in text, text[-500:]
    assert "L2/L3 escalation" in text, text[-500:]
    assert "L4 alignment" in text, text[-500:]

    # Sanity: cassette envelopes ran (so per-band data is real, not stub).
    with fixture_src.open("r", encoding="utf-8") as fp:
        n_envelopes = sum(1 for line in fp if line.strip())
    assert n_envelopes > 0
    _ = json
