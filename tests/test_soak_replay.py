"""Task A / v1.2: replay-tier soak smoke test.

Exercises the ``tools/soak_driver.py --cli-replay`` path end-to-end against
a tiny committed cassette. Asserts:

  1. The driver exits cleanly with rc=0.
  2. Bus rows are written: governance_eval messages == cassette envelopes,
     decision rows == cassette envelopes.
  3. **No `claude` subprocess is spawned.** A monkeypatched
     ``subprocess.Popen`` recorded in the driver's process is the wrong
     scope (the driver is its own process); we instead verify by running
     with ``PATH`` stripped of any ``claude`` binary directory and assert
     the run still passes. If the replay path tried to spawn the CLI it
     would either FileNotFoundError or print the deferral message.

Replay must NOT depend on the `claude` binary being on PATH — that is the
core promise of ADR-17.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "soak_cassette_2026-05-03.jsonl"


def _count_table(db_path: Path, table: str, where: str = "") -> int:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        sql = f"SELECT COUNT(*) FROM {table}"
        if where:
            sql += f" WHERE {where}"
        return int(conn.execute(sql).fetchone()[0])
    finally:
        conn.close()


def test_replay_runs_without_claude_on_path(tmp_path: Path) -> None:
    """End-to-end: replay tier completes with rc=0 and no CLI on PATH."""
    assert FIXTURE.exists(), f"sample cassette missing: {FIXTURE}"

    # Strip the `claude` binary directory from PATH before invoking the
    # driver. If replay accidentally spawned `claude`, this would fail.
    env = dict(os.environ)
    # Empty PATH on Windows breaks Python's own DLL loader; instead point
    # PATH at a directory that can't contain `claude`.
    env["PATH"] = str(tmp_path)
    # Ensure the child can import the project package layout.
    env["PYTHONPATH"] = (
        str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    )
    # Force-disable BRIDGE_API_GOV so even the engine path (if reached
    # accidentally) couldn't escalate to a real model call.
    env.pop("BRIDGE_API_GOV", None)

    gov_db = tmp_path / "replay.db"

    cmd = [
        sys.executable,
        str(ROOT / "tools" / "soak_driver.py"),
        "--cli-replay",
        str(FIXTURE),
        "--gov-db",
        str(gov_db),
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, (
        f"replay exited rc={proc.returncode}\n"
        f"stdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}"
    )

    # Plumbing assertion: bus rows match cassette length.
    with FIXTURE.open("r", encoding="utf-8") as fp:
        n_envelopes = sum(1 for line in fp if line.strip())
    assert n_envelopes > 0

    # The driver writes through the same MessageBus schema used in
    # production; we count the governance_eval messages and decisions.
    n_msgs = _count_table(
        gov_db, "messages", where="type = 'governance_eval'"
    )
    n_decisions = _count_table(gov_db, "decisions")
    assert n_msgs == n_envelopes, (
        f"expected {n_envelopes} governance_eval rows, got {n_msgs}"
    )
    assert n_decisions == n_envelopes, (
        f"expected {n_envelopes} decision rows, got {n_decisions}"
    )

    # The replay banner should appear and the run should NOT print the
    # deferral message that the ship-gate path uses when claude is missing.
    assert "replay mode" in proc.stdout, proc.stdout
    assert "DEFERRED" not in proc.stdout, proc.stdout


def test_cassette_envelope_shape() -> None:
    """The committed sample cassette must conform to the documented shape."""
    required_top = {"idx", "kind", "content", "recorded_latency_ms", "decision"}
    required_decision = {"action", "confidence", "reasoning"}
    valid_actions = {"ALLOW", "SUGGEST", "GUIDE", "INTERVENE", "BLOCK"}

    with FIXTURE.open("r", encoding="utf-8") as fp:
        rows = [json.loads(line) for line in fp if line.strip()]
    assert rows, "cassette is empty"
    for row in rows:
        missing = required_top - row.keys()
        assert not missing, f"row missing keys {missing}: {row}"
        assert isinstance(row["recorded_latency_ms"], (int, float))
        assert row["recorded_latency_ms"] >= 0
        dec = row["decision"]
        missing_d = required_decision - dec.keys()
        assert not missing_d, f"decision missing keys {missing_d}: {dec}"
        assert dec["action"] in valid_actions
        assert 0.0 <= float(dec["confidence"]) <= 1.0


def test_replay_load_cassette_helper_validates_shape(tmp_path: Path) -> None:
    """``_load_cassette`` rejects malformed rows up-front."""
    sys.path.insert(0, str(ROOT / "tools"))
    import soak_driver  # noqa: WPS433  -- script-style import is intentional

    bad = tmp_path / "bad.jsonl"
    bad.write_text(
        json.dumps({"kind": "routine", "content": "x"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing field"):
        soak_driver._load_cassette(bad)

    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        soak_driver._load_cassette(empty)
