"""v10 P4 — tests for reproducibility manifest + trainer exit codes."""

from __future__ import annotations

from pathlib import Path

from rl.manifest import compute_db_sha, read_manifest, write_manifest


def test_manifest_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "manifest.json"
    write_manifest(
        target,
        seed=42,
        db_sha="deadbeef" * 8,
        hyperparams={"alpha_beta_sum": 20.0, "delta": 0.02},
        posterior={"arm_0": {"alpha": 1.0, "beta": 1.0, "mean": 0.5}},
        candidates=[{"arm": 0, "l4_threshold": 0.5}],
        ips_per_candidate={"0.50": 0.85, "0.75": 0.9},
    )
    got = read_manifest(target)
    assert got["envelope"] == "rl_train_manifest"
    assert got["seed"] == 42
    assert got["db_sha"] == "deadbeef" * 8
    assert got["hyperparams"] == {"alpha_beta_sum": 20.0, "delta": 0.02}
    assert got["candidates"] == [{"arm": 0, "l4_threshold": 0.5}]
    assert got["ips_per_candidate"] == {"0.50": 0.85, "0.75": 0.9}


def test_manifest_db_sha_changes_with_db(tmp_path: Path) -> None:
    db = tmp_path / "rl_episodes.db"
    db.write_bytes(b"version 1")
    sha1 = compute_db_sha(db)
    db.write_bytes(b"version 2")
    sha2 = compute_db_sha(db)
    assert sha1 != sha2
    assert len(sha1) == 64


def test_exit_codes_0_no_lift_10_promote_1_error():
    """DOD: exit codes unix convention (0=baseline retained, 10=promote, 1=error)."""
    from rl.cli.train import EXIT_ERROR, EXIT_PROMOTE, EXIT_RETAIN_BASELINE
    assert EXIT_RETAIN_BASELINE == 0
    assert EXIT_PROMOTE == 10
    assert EXIT_ERROR == 1
