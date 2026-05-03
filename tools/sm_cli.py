#!/usr/bin/env python
"""sm — Stream Manager operator CLI.

Subcommands:
    sm sessions list                  — print sessions table (id, started_at,
                                        last_msg_ts, active)
    sm sessions tail <session_id>     — stream that session's bus envelopes
                                        as JSONL on stdout (Ctrl-C to exit)

Active flag resolution order:
    1. If ``--dashboard-url`` is supplied (or ``SM_DASHBOARD_URL`` is set), the
       CLI calls ``GET /api/registry/active`` and treats those session_ids as
       active. This consumes the EngineRegistry surface (Task M output) and
       does not modify it.
    2. Otherwise, falls back to ``sessions.ended_at IS NULL`` from the bus DB.

DB path resolution:
    --db CLI arg → ``GOV_DB`` env var → ``.claude/gov.db`` under repo root.

Wired via ``[project.scripts]`` in pyproject.toml as ``sm`` so
``pip install -e .`` exposes it on PATH.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from stream_manager.message_bus import WalReader  # noqa: E402


def _default_db_path() -> Path:
    env = os.environ.get("GOV_DB")
    if env:
        return Path(env)
    return ROOT / ".claude" / "gov.db"


def _fetch_active_session_ids(dashboard_url: str | None) -> set[str]:
    """Hit /api/registry/active and return active_session_ids set.

    Returns empty set on any failure (network, parse, missing field). Lazy
    httpx import keeps the CLI usable in environments without httpx.
    """
    if not dashboard_url:
        return set()
    try:
        import httpx  # noqa: WPS433 — lazy import is intentional
    except ImportError:
        return set()
    url = dashboard_url.rstrip("/") + "/api/registry/active"
    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return set()
            data = resp.json()
    except Exception:
        return set()
    ids = data.get("active_session_ids") if isinstance(data, dict) else None
    if not isinstance(ids, list):
        return set()
    return {str(x) for x in ids if x}


def list_sessions(
    db_path: Path,
    dashboard_url: str | None = None,
) -> list[dict[str, Any]]:
    """Return rows for ``sm sessions list``.

    Each row has: session_id, started_at, last_msg_ts, active.

    last_msg_ts is the max(messages.timestamp) for that session_id (None if
    the session has no messages yet).

    active is True when:
        - the registry surface lists this id (preferred), OR
        - the registry is unavailable AND ``sessions.ended_at IS NULL``.
    """
    if not db_path.exists():
        return []
    active_from_registry = _fetch_active_session_ids(dashboard_url)
    have_registry = bool(active_from_registry) or bool(dashboard_url)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute("PRAGMA journal_mode=WAL")
        rows = conn.execute(
            "SELECT s.id AS session_id, s.started_at, s.ended_at, "
            "(SELECT MAX(timestamp) FROM messages m WHERE m.session_id = s.id) "
            "  AS last_msg_ts "
            "FROM sessions s "
            "ORDER BY s.started_at DESC"
        ).fetchall()
    finally:
        conn.close()
    out: list[dict[str, Any]] = []
    for r in rows:
        sid = str(r["session_id"])
        if dashboard_url:
            active = sid in active_from_registry
        else:
            active = r["ended_at"] is None
        out.append(
            {
                "session_id": sid,
                "started_at": r["started_at"],
                "last_msg_ts": r["last_msg_ts"],
                "active": bool(active),
                # Carry the resolution mode forward so callers (and tests)
                # can tell whether `active` came from the registry or the
                # ended_at fallback.
                "_active_source": "registry" if have_registry else "ended_at",
            }
        )
    return out


def _fmt_ts(ts: float | None) -> str:
    if ts is None:
        return "-"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(ts)))
    except (TypeError, ValueError, OverflowError):
        return "-"


def render_sessions_table(rows: list[dict[str, Any]]) -> str:
    """Format ``sm sessions list`` rows as a fixed-width table."""
    headers = ["session_id", "started_at", "last_msg_ts", "active"]
    if not rows:
        return "  ".join(headers) + "\n(no sessions)"
    body: list[list[str]] = []
    for r in rows:
        body.append(
            [
                r["session_id"],
                _fmt_ts(r["started_at"]),
                _fmt_ts(r["last_msg_ts"]),
                "yes" if r["active"] else "no",
            ]
        )
    widths = [
        max(len(h), *(len(row[i]) for row in body)) for i, h in enumerate(headers)
    ]
    fmt = "  ".join("{:<" + str(w) + "}" for w in widths)
    lines = [fmt.format(*headers)]
    lines.append(fmt.format(*("-" * w for w in widths)))
    for row in body:
        lines.append(fmt.format(*row))
    return "\n".join(lines)


def tail_session(
    db_path: Path,
    session_id: str,
    poll_ms: int = 250,
    out=None,
    stop_after: int | None = None,
) -> int:
    """Stream message envelopes for ``session_id`` as JSONL on ``out``.

    Each line is a JSON object with the message row fields. ``stop_after``
    is for tests: when an int N is supplied, the function returns after
    yielding N lines instead of running forever.

    Returns the number of envelopes written.
    """
    out = out if out is not None else sys.stdout
    written = 0
    reader = WalReader(str(db_path), session_id, poll_ms=poll_ms)
    try:
        for row in reader:
            # context/metadata are stored as JSON strings in the DB; parse
            # them so the JSONL line is a clean nested object.
            for key in ("context", "metadata"):
                v = row.get(key)
                if isinstance(v, str):
                    try:
                        row[key] = json.loads(v) if v else {}
                    except (TypeError, ValueError):
                        row[key] = {}
            out.write(json.dumps(row, separators=(",", ":")) + "\n")
            out.flush()
            written += 1
            if stop_after is not None and written >= stop_after:
                break
    finally:
        reader.close()
    return written


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sm",
        description="Stream Manager operator CLI.",
    )
    p.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to gov.db (default: $GOV_DB or .claude/gov.db).",
    )
    p.add_argument(
        "--dashboard-url",
        default=os.environ.get("SM_DASHBOARD_URL"),
        help=(
            "Base URL of the SM dashboard (e.g. http://127.0.0.1:8765). "
            "When set, the active flag in `sessions list` is sourced from "
            "/api/registry/active. Default: $SM_DASHBOARD_URL."
        ),
    )

    sub = p.add_subparsers(dest="command", required=True)

    sessions = sub.add_parser("sessions", help="Inspect bus sessions.")
    sessions_sub = sessions.add_subparsers(dest="action", required=True)

    list_p = sessions_sub.add_parser("list", help="List sessions in the bus.")
    list_p.add_argument(
        "--json",
        action="store_true",
        help="Emit one JSON object per session instead of a table.",
    )

    tail_p = sessions_sub.add_parser(
        "tail", help="Stream a session's bus envelopes as JSONL."
    )
    tail_p.add_argument("session_id", help="Session id to tail.")
    tail_p.add_argument(
        "--poll-ms",
        type=int,
        default=250,
        help="Poll interval for new messages (default: 250).",
    )

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    db_path: Path = args.db or _default_db_path()

    if args.command == "sessions" and args.action == "list":
        rows = list_sessions(db_path, dashboard_url=args.dashboard_url)
        if args.json:
            for row in rows:
                # Strip the private bookkeeping field from JSON output.
                clean = {k: v for k, v in row.items() if not k.startswith("_")}
                sys.stdout.write(json.dumps(clean, separators=(",", ":")) + "\n")
        else:
            sys.stdout.write(render_sessions_table(rows) + "\n")
        return 0

    if args.command == "sessions" and args.action == "tail":
        if not db_path.exists():
            sys.stderr.write(f"sm: db not found at {db_path}\n")
            return 2
        try:
            tail_session(db_path, args.session_id, poll_ms=args.poll_ms)
        except KeyboardInterrupt:
            return 0
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
