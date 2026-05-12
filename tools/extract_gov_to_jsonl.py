"""v10 P4 corpus extractor — `.claude/gov.db` → governance_decision JSONL.

Reads decisions+messages+sessions from the live SM governance bus and
emits one governance_decision envelope per JSONL line, ready for
``python -m rl.episode_logger ingest --source live --file <out.jsonl>``.

**Polarity-flip selection rule** (per
``feedback_no_self_monitor.md`` §"Polarity flip"):

    INCLUDE iff session.project_slug NOT IN (SM-slugs)
            AND session_id != $BRIDGE_SM_SELF_SESSION_ID

Default SM-slug set = ``{"streamManager"}``; override via
``--exclude-slug`` (comma list) or env ``BRIDGE_SM_PROJECT_SLUGS``.

This tool closes the L94 TODO at ``docs/v10-mvp-status.md``: no shipped
helper existed to materialise a governance_decision JSONL from the live
bus DB. v10 P4 corpus-fill gate now reads from the live bus, not the
isolated soak sandbox.

Read-only against ``.claude/gov.db``. Never writes to that DB.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

_DEFAULT_GOV_DB = Path(".claude/gov.db")
_DEFAULT_SLUG_EXCLUDE = "streamManager"


def _slug_set(raw: str) -> list[str]:
    return [s.strip() for s in raw.split(",") if s.strip()]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def extract(
    gov_db: Path,
    output: Path,
    *,
    exclude_slugs: list[str],
    exclude_session_id: str | None,
    since_epoch: float | None,
) -> dict[str, object]:
    """Materialise governance_decision JSONL from gov.db; return summary."""
    if not gov_db.exists():
        raise FileNotFoundError(f"gov_db not found: {gov_db}")
    if not exclude_slugs:
        raise ValueError(
            "refusing to extract with empty exclude-slug set; "
            "polarity-flip rule requires SM-slug exclusion"
        )

    output.parent.mkdir(parents=True, exist_ok=True)

    # mode=ro URI ensures we cannot write
    conn = sqlite3.connect(f"file:{gov_db}?mode=ro", uri=True)

    slug_placeholders = ",".join("?" for _ in exclude_slugs)
    params: list[object] = list(exclude_slugs)

    where_clauses = [f"s.project_slug NOT IN ({slug_placeholders})"]
    if exclude_session_id:
        where_clauses.append("m.session_id != ?")
        params.append(exclude_session_id)
    if since_epoch is not None:
        where_clauses.append("d.timestamp >= ?")
        params.append(since_epoch)

    query = f"""
        SELECT
            d.id            AS decision_id,
            d.action        AS verdict,
            d.confidence    AS confidence,
            d.layer         AS layer,
            d.model_used    AS model_used,
            d.timestamp     AS ts_epoch,
            m.session_id    AS session_id,
            m.content       AS content,
            s.project_slug  AS project_slug
        FROM decisions d
        JOIN messages m ON m.id = d.message_id
        JOIN sessions s ON s.id = m.session_id
        WHERE {" AND ".join(where_clauses)}
        ORDER BY d.timestamp ASC
    """

    # Also count what we excluded for the summary.
    excluded_by_slug = conn.execute(
        f"""
        SELECT COUNT(*) FROM decisions d
        JOIN messages m ON m.id = d.message_id
        JOIN sessions s ON s.id = m.session_id
        WHERE s.project_slug IN ({slug_placeholders})
        """,
        exclude_slugs,
    ).fetchone()[0]
    excluded_by_session = 0
    if exclude_session_id:
        excluded_by_session = conn.execute(
            """
            SELECT COUNT(*) FROM decisions d
            JOIN messages m ON m.id = d.message_id
            WHERE m.session_id = ?
            """,
            (exclude_session_id,),
        ).fetchone()[0]

    extracted = 0
    verdict_counts: dict[str, int] = {}
    with output.open("w", encoding="utf-8", newline="\n") as fh:
        for row in conn.execute(query, params):
            (
                decision_id,
                verdict,
                confidence,
                _layer,
                _model_used,
                _ts_epoch,
                session_id,
                _content,
                project_slug,
            ) = row
            envelope = {
                "session_id": session_id,
                "trace_id": decision_id,
                "verdict": verdict,
                "project_slug": project_slug,
                "confidence": float(confidence),
                "action_taken": float(confidence),
                "action_propensity": 1.0,
                "latency_ms": 0.0,
                "state": {},
            }
            fh.write(json.dumps(envelope, separators=(",", ":")) + "\n")
            extracted += 1
            verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1

    conn.close()

    return {
        "extracted": extracted,
        "excluded_by_slug": excluded_by_slug,
        "excluded_by_session": excluded_by_session,
        "verdict_dist": verdict_counts,
        "source_db_sha256": _sha256(gov_db),
        "output_path": str(output),
        "exclude_slugs": exclude_slugs,
        "exclude_session_id": exclude_session_id,
        "since_epoch": since_epoch,
    }


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tools.extract_gov_to_jsonl")
    parser.add_argument("--gov-db", type=Path, default=_DEFAULT_GOV_DB)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="JSONL path (UTC-stamped naming recommended)",
    )
    parser.add_argument(
        "--exclude-slug",
        type=str,
        default=os.environ.get("BRIDGE_SM_PROJECT_SLUGS", _DEFAULT_SLUG_EXCLUDE),
        help="comma-separated project_slug values to exclude (SM-self set)",
    )
    parser.add_argument(
        "--since-hours",
        type=float,
        default=None,
        help="only include decisions with timestamp within this window (default: all)",
    )
    args = parser.parse_args(argv)

    exclude_slugs = _slug_set(args.exclude_slug)
    exclude_session_id = os.environ.get("BRIDGE_SM_SELF_SESSION_ID", "").strip() or None

    since_epoch: float | None = None
    if args.since_hours is not None:
        since_epoch = time.time() - (args.since_hours * 3600.0)

    summary = extract(
        args.gov_db,
        args.output,
        exclude_slugs=exclude_slugs,
        exclude_session_id=exclude_session_id,
        since_epoch=since_epoch,
    )
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_cli(sys.argv[1:]))
