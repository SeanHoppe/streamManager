"""v10 P2 — corpus augmentation (data-source bias mitigation).

Mixes synthetic minority episodes (cassette + probe) into the live
training set, capped at ratio_synthetic (default 0.30). Deterministic
with caller-supplied seed. Self-monitor episodes are filtered per
``feedback_no_self_monitor.md``. Golden source is HOLDOUT — passing
``include_golden=True`` raises ``GoldenInTrainingError``.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import random
import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path

from rl.episode_logger import _sm_slug_set, ensure_project_slug_column
from rl.sources import VALID_VERDICTS, Episode
from rl.sources import cassette as cassette_src
from rl.sources import probe as probe_src

logger = logging.getLogger(__name__)

WARN_DEVIATION = 0.10
ERROR_DEVIATION = 0.25
DEFAULT_DB = Path("rl_episodes.db")


class CorpusBalanceError(RuntimeError):
    """Raised when synthetic ratio deviates > ERROR_DEVIATION from target."""


class GoldenInTrainingError(AssertionError):
    """Raised if a golden-source episode reaches the training output."""


def _load_real_from_db(db_path: Path) -> list[Episode]:
    if not db_path.exists():
        return []
    # Polarity self-exclusion (CLAUDE.md "Session-source exception rule").
    # project_slug is the DURABLE read-side key: the SQL WHERE below default-
    # excludes SM-self slug values. NULL/unstamped project_slug is retained by
    # the WHERE and instead caught by the session backstop (_filter_self_monitor,
    # applied in assemble_training_set). The session_id half is the load-bearing
    # WRITE-time gate (episode_logger raises SelfMonitorRefusal; env-conditional)
    # and a cheap read-time backstop on an ephemeral key -- belt-and-suspenders,
    # not the durable selector, so it is NOT in the SQL WHERE.
    sm_slugs = sorted(_sm_slug_set())
    slug_placeholders = ",".join("?" for _ in sm_slugs)
    slug_clause = (
        f" AND (project_slug IS NULL OR project_slug NOT IN ({slug_placeholders}))"
        if sm_slugs
        else ""
    )
    conn = sqlite3.connect(str(db_path))
    try:
        if conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='episodes'"
        ).fetchone() is None:
            return []
        # Legacy-schema migration (idempotent): a pre-`project_slug`
        # episodes db (created before rl/schema.sql added the column) would
        # raise "no such column: project_slug" on the WHERE below, defeating
        # the SQL-WHERE polarity key (CLAUDE.md L42). Add the nullable
        # column so the durable read key ALWAYS applies; legacy rows get
        # NULL slug -> retained by the WHERE -> caught by the session
        # backstop (_filter_self_monitor).
        ensure_project_slug_column(conn)
        rows = conn.execute(
            "SELECT ts_utc, session_id, trace_id, state_features_json,"
            " action_taken, action_propensity, verdict, confidence,"
            " hitl_override, latency_ms, fr_og_7_pass, budget_violation,"
            " source, cycle_tag FROM episodes WHERE source IN ('live','soak')"
            + slug_clause,
            tuple(sm_slugs),
        ).fetchall()
    finally:
        conn.close()
    out: list[Episode] = []
    for r in rows:
        try:
            features = json.loads(r[3])
        except (TypeError, json.JSONDecodeError):
            features = {}
        out.append(Episode(
            ts_utc=str(r[0]), session_id=str(r[1]), trace_id=str(r[2]),
            state_features=features,
            action_taken=float(r[4]), action_propensity=float(r[5]),
            verdict=str(r[6]), confidence=float(r[7]),
            hitl_override=(int(r[8]) if r[8] is not None else None),
            latency_ms=float(r[9]),
            fr_og_7_pass=(int(r[10]) if r[10] is not None else None),
            budget_violation=int(r[11]),
            source=str(r[12]),
            cycle_tag=(str(r[13]) if r[13] is not None else None),
        ))
    return out


def _filter_self_monitor(episodes: Iterable[Episode]) -> list[Episode]:
    sm_self = os.environ.get("BRIDGE_SM_SELF_SESSION_ID", "").strip()
    if not sm_self:
        return list(episodes)
    return [e for e in episodes if e.session_id != sm_self]


def _load_synthetic(
    cassette_paths: Sequence[Path] | None,
    probe_paths: Sequence[Path] | None,
) -> list[Episode]:
    out: list[Episode] = []
    for p in cassette_paths or []:
        out.extend(cassette_src.iter_episodes(Path(p)))
    for p in probe_paths or []:
        out.extend(probe_src.iter_episodes(Path(p)))
    return out


def _verdict_counts(episodes: Sequence[Episode]) -> dict[str, int]:
    counts = {v: 0 for v in VALID_VERDICTS}
    for ep in episodes:
        if ep.verdict in counts:
            counts[ep.verdict] += 1
    return counts


def _emit_balance_log(
    real: Sequence[Episode], synthetic: Sequence[Episode],
    final: Sequence[Episode], ratio_synthetic: float,
) -> dict:
    per_source: dict[str, int] = {}
    for ep in final:
        per_source[ep.source] = per_source.get(ep.source, 0) + 1
    n_total = max(1, len(final))
    actual = sum(1 for ep in final if ep.source not in ("live", "soak")) / n_total
    payload = {
        "envelope": "rl_corpus_class_balance",
        "n_real_input": len(real), "n_synthetic_input": len(synthetic),
        "n_final": len(final),
        "ratio_synthetic_target": ratio_synthetic,
        "ratio_synthetic_actual": actual,
        "per_source": per_source,
        "per_verdict": _verdict_counts(final),
    }
    print(json.dumps(payload, sort_keys=True))
    return payload


def assemble_training_set(
    target_n: int, *, ratio_synthetic: float = 0.30, seed: int = 0,
    db_path: Path | None = None,
    cassette_paths: Sequence[Path] | None = None,
    probe_paths: Sequence[Path] | None = None,
    extra_episodes: Sequence[Episode] | None = None,
    include_golden: bool = False,
) -> list[Episode]:
    """Assemble training set <= target_n. See module docstring for rules."""
    if not 0.0 <= ratio_synthetic <= 1.0:
        raise ValueError(f"ratio_synthetic must be in [0,1]; got {ratio_synthetic!r}")
    if target_n < 0:
        raise ValueError(f"target_n must be >= 0; got {target_n!r}")
    if include_golden:
        raise GoldenInTrainingError("golden source is HOLDOUT")

    rng = random.Random(seed)
    db = db_path if db_path is not None else DEFAULT_DB
    real = _filter_self_monitor(_load_real_from_db(db))
    synthetic = _filter_self_monitor(_load_synthetic(cassette_paths, probe_paths))
    if extra_episodes:
        synthetic.extend(_filter_self_monitor(extra_episodes))
    for ep in synthetic:
        if ep.source == "golden":
            raise GoldenInTrainingError(f"golden ep {ep.trace_id!r} in pool")

    cap_synth = int(round(ratio_synthetic * target_n))
    n_synth = min(len(synthetic), cap_synth)
    n_real = min(len(real), max(n_synth, target_n - n_synth))
    if n_real < n_synth:
        n_synth = n_real

    real_sample = list(real); rng.shuffle(real_sample)
    synth_sample = list(synthetic); rng.shuffle(synth_sample)
    chosen = real_sample[:n_real] + synth_sample[:n_synth]
    rng.shuffle(chosen)
    for ep in chosen:
        if ep.source == "golden":
            raise GoldenInTrainingError(f"golden ep {ep.trace_id!r} in output")

    payload = _emit_balance_log(real, synthetic, chosen, ratio_synthetic)
    deviation = abs(float(payload["ratio_synthetic_actual"]) - ratio_synthetic)
    if deviation > ERROR_DEVIATION:
        raise CorpusBalanceError(
            f"synthetic ratio deviation {deviation:.3f} > error {ERROR_DEVIATION}"
        )
    if deviation > WARN_DEVIATION:
        logger.warning(
            "rl_corpus_class_balance deviation %.3f > warn %.3f"
            " (target=%.2f actual=%.2f)",
            deviation, WARN_DEVIATION,
            ratio_synthetic, payload["ratio_synthetic_actual"],
        )
    return chosen
