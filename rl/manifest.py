"""v10 P4 — Reproducibility manifest writer.

Snapshots seed + DB SHA-256 + hyperparams + per-arm posterior + IPS
estimate per candidate. One manifest per trainer run. Files are
written by :func:`write_manifest`; round-trip read via
:func:`read_manifest`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


_CHUNK_BYTES = 65536


def compute_db_sha(db_path: Path) -> str:
    """SHA-256 hex digest of ``db_path`` (raw bytes, streamed in chunks)."""
    h = hashlib.sha256()
    with Path(db_path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK_BYTES), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(
    path: Path,
    *,
    seed: int,
    db_sha: str,
    hyperparams: Mapping[str, Any],
    posterior: Mapping[str, Any],
    candidates: list,
    ips_per_candidate: dict[str, float],
) -> None:
    """Write the trainer manifest as JSON. Parent dir is auto-created."""
    payload = {
        "envelope": "rl_train_manifest",
        "seed": int(seed),
        "db_sha": str(db_sha),
        "hyperparams": dict(hyperparams),
        "posterior": dict(posterior),
        "candidates": list(candidates),
        "ips_per_candidate": {
            str(k): float(v) for k, v in ips_per_candidate.items()
        },
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_manifest(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
