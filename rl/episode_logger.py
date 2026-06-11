"""v10 P1 — episode logger (single-writer SQLite WAL).

Writes one row per governance decision into ``rl_episodes.db``.
Reads only from gov state (governance_decision envelope dict,
hitl_overrides table, _last_phase_timings_ms). NEVER edits any
FROZEN gov surface.

Self-monitor refusal (two layers per
``feedback_no_self_monitor.md`` §"Polarity flip"):

1. If the envelope's ``session_id`` matches the
   ``BRIDGE_SM_SELF_SESSION_ID`` env var, the row is rejected.
2. If the envelope's ``project_slug`` is in the SM-self slug set
   (``BRIDGE_SM_PROJECT_SLUGS`` env, default ``{"streamManager"}``),
   the row is rejected. Polarity-flip default: include iff
   project_slug is NOT in the SM set, so corpus building defaults to
   non-SM sessions and SM-self leakage surfaces as zero rows rather
   than silent contamination.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rl.state_features import extract as extract_features

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")

VALID_VERDICTS = ("ALLOW", "SUGGEST", "INTERVENE", "BLOCK", "AMBIGUOUS")
VALID_SOURCES = ("soak", "cassette", "probe", "golden", "review", "live")

_DEFAULT_SM_SLUGS = "streamManager"


def _sm_slug_set() -> frozenset[str]:
    """Read SM self-slug set from env each call (cheap, test-friendly)."""
    raw = os.environ.get("BRIDGE_SM_PROJECT_SLUGS", _DEFAULT_SM_SLUGS)
    return frozenset(s.strip() for s in raw.split(",") if s.strip())


class SelfMonitorRefusal(ValueError):
    """Raised when a logger envelope matches the SM's own session id
    or carries an SM ``project_slug``."""


class EpisodeLogger:
    """Single-writer SQLite WAL logger for v10 episodes.

    Usage::

        logger = EpisodeLogger(Path("rl_episodes.db"))
        logger.record_decision(envelope, source="live")
        logger.close()

    Writer is a single process. WAL mode provides single-writer
    multi-reader semantics. Multi-instance SM is NOT supported in
    v10.0; revisit with explicit IPC if it lands later.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> EpisodeLogger:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def record_decision(
        self,
        envelope: Mapping[str, Any],
        *,
        source: str = "live",
        cycle_tag: str | None = None,
        now_utc: datetime | None = None,
    ) -> int:
        """Insert one episode row from a governance_decision envelope.

        Returns inserted episode_id. Raises SelfMonitorRefusal if the
        envelope's session_id matches BRIDGE_SM_SELF_SESSION_ID.
        Raises sqlite3.IntegrityError on duplicate (session_id, trace_id).
        """
        if source not in VALID_SOURCES:
            raise ValueError(f"unknown source {source!r}; expected one of {VALID_SOURCES}")

        session_id = str(envelope["session_id"])
        trace_id = str(envelope["trace_id"])

        sm_self = os.environ.get("BRIDGE_SM_SELF_SESSION_ID", "").strip()
        if sm_self and session_id == sm_self:
            raise SelfMonitorRefusal("self-monitor refusal (session_id match)")

        project_slug = str(envelope.get("project_slug", "")).strip()
        if project_slug and project_slug in _sm_slug_set():
            raise SelfMonitorRefusal(
                f"self-monitor refusal (project_slug={project_slug!r} in SM set)"
            )

        verdict = str(envelope["verdict"])
        if verdict not in VALID_VERDICTS:
            raise ValueError(f"unknown verdict {verdict!r}; expected one of {VALID_VERDICTS}")

        if now_utc is None:
            now_utc = datetime.now(timezone.utc)

        state = envelope.get("state") or {}
        features = extract_features(state, now_utc=now_utc)

        action_taken = float(envelope.get("action_taken", envelope.get("threshold", 0.0)))
        action_propensity = float(envelope.get("action_propensity", 1.0))
        confidence = float(envelope.get("confidence", 0.0))
        latency_ms = float(envelope.get("latency_ms", 0.0))
        budget_violation = int(bool(envelope.get("budget_violation", 0)))
        hitl_override = envelope.get("hitl_override")
        if hitl_override is not None:
            hitl_override = int(bool(hitl_override))
        fr_og_7_pass = envelope.get("fr_og_7_pass")  # may be None / 0 / 1
        if fr_og_7_pass is not None:
            fr_og_7_pass = int(bool(fr_og_7_pass))

        cur = self._conn.execute(
            "INSERT INTO episodes ("
            " ts_utc, session_id, trace_id, state_features_json,"
            " action_taken, action_propensity, verdict, confidence,"
            " hitl_override, latency_ms, fr_og_7_pass, budget_violation,"
            " source, cycle_tag, project_slug"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                now_utc.astimezone(timezone.utc).isoformat(),
                session_id,
                trace_id,
                json.dumps(features),
                action_taken,
                action_propensity,
                verdict,
                confidence,
                hitl_override,
                latency_ms,
                fr_og_7_pass,
                budget_violation,
                source,
                cycle_tag,
                # Persist project_slug so corpus reads can enforce the
                # polarity-flip at the SQL WHERE (CLAUDE.md L42), in addition
                # to the write-time refusal above. NULL when absent.
                project_slug or None,
            ),
        )
        return int(cur.lastrowid or 0)

    def journal_mode(self) -> str:
        row = self._conn.execute("PRAGMA journal_mode").fetchone()
        return str(row[0]).lower() if row else ""


def _ingest_jsonl(
    db_path: Path,
    jsonl_path: Path,
    *,
    source: str,
    cycle_tag: str | None,
) -> int:
    """Bulk-ingest envelopes from a JSONL file. Returns row count.

    When ``cycle_tag`` is None the filename stem is used (matches the
    UTC-stamped cassette / probe naming convention).
    """
    if cycle_tag is None:
        cycle_tag = jsonl_path.stem
    inserted = 0
    with EpisodeLogger(db_path) as logger:
        with jsonl_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    envelope = json.loads(line)
                except json.JSONDecodeError:
                    # Malformed line — skip silently (matches the
                    # IntegrityError + SelfMonitorRefusal pattern: do
                    # not crash a bulk ingest on one bad row).
                    continue
                try:
                    logger.record_decision(
                        envelope,
                        source=source,
                        cycle_tag=cycle_tag,
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    # Duplicate (session_id, trace_id) — bus-replay
                    # double-insert defended; skip silently.
                    continue
                except SelfMonitorRefusal:
                    # Per feedback_no_self_monitor.md: skip silently
                    # but do not crash ingest.
                    continue
    return inserted


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rl.episode_logger")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="bulk-ingest envelopes from JSONL")
    p_ingest.add_argument("--db", type=Path, default=Path("rl_episodes.db"))
    p_ingest.add_argument(
        "--source",
        type=str,
        choices=VALID_SOURCES,
        required=True,
    )
    p_ingest.add_argument("--file", type=Path, required=True)
    p_ingest.add_argument("--cycle-tag", type=str, default=None)

    args = parser.parse_args(argv)

    if args.cmd == "ingest":
        cycle_tag = args.cycle_tag
        if cycle_tag is None:
            cycle_tag = args.file.stem  # filename UTC stamp default
        count = _ingest_jsonl(
            args.db,
            args.file,
            source=args.source,
            cycle_tag=cycle_tag,
        )
        print(json.dumps({"inserted": count, "source": args.source, "cycle_tag": cycle_tag}))
        return 0

    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_cli(sys.argv[1:]))
