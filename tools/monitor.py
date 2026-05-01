"""Governance event bus monitor.

Commands::

    python tools/monitor.py --bus /tmp/gov.db list          # recent decisions
    python tools/monitor.py --bus /tmp/gov.db list -n 100   # last 100
    python tools/monitor.py --bus /tmp/gov.db watch         # tail new events

The bus is written by ``stream_manager.event_bus.EventBus``.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

# column widths
_W_ID = 6
_W_TIME = 8
_W_ROLE = 6
_W_SRC = 9
_W_ACT = 9
_W_CONF = 5
_W_MODE = 8
_W_SNIP = 55

_HEADER = (
    f"{'id':>{_W_ID}}  {'time':<{_W_TIME}}  {'role':<{_W_ROLE}}  "
    f"{'source':<{_W_SRC}}  {'action':<{_W_ACT}}  {'conf':>{_W_CONF}}  "
    f"[{'mode':<{_W_MODE}}]  snippet"
)
_SEP = "-" * (len(_HEADER) + 4)


def _fmt(row: sqlite3.Row) -> str:
    ts = time.strftime("%H:%M:%S", time.localtime(row["ts"]))
    conf = f"{row['confidence']:.2f}" if row["confidence"] is not None else "    -"
    snippet = (row["snippet"] or "")[:_W_SNIP]
    action = row["action"] or "?"
    orig = row["original_action"]
    if orig and orig != action:
        action = f"{action}({orig})"
    return (
        f"{row['id']:>{_W_ID}}  {ts:<{_W_TIME}}  {(row['role'] or '?'):<{_W_ROLE}}  "
        f"{(row['source'] or '?'):<{_W_SRC}}  {action:<{_W_ACT}}  {conf:>{_W_CONF}}  "
        f"[{(row['mode'] or '?'):<{_W_MODE}}]  {snippet}"
    )


def _open_ro(path: Path) -> sqlite3.Connection:
    if not path.exists():
        sys.exit(f"bus not found: {path}\n(run the governance engine to create it)")
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def cmd_list(conn: sqlite3.Connection, n: int) -> None:
    rows = conn.execute(
        "SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (n,)
    ).fetchall()
    if not rows:
        print("(no events in bus)")
        return
    print(_HEADER)
    print(_SEP)
    for row in reversed(rows):
        print(_fmt(row))
    print(_SEP)
    print(f"{len(rows)} row(s)")


def cmd_watch(conn: sqlite3.Connection) -> None:
    since_id: int = conn.execute(
        "SELECT COALESCE(MAX(id), 0) FROM decisions"
    ).fetchone()[0]

    print(_HEADER)
    print(_SEP)
    print(f"watching… (last id={since_id}, Ctrl-C to stop)")

    try:
        while True:
            rows = conn.execute(
                "SELECT * FROM decisions WHERE id > ? ORDER BY id", (since_id,)
            ).fetchall()
            for row in rows:
                print(_fmt(row))
                since_id = row["id"]
            time.sleep(0.4)
    except KeyboardInterrupt:
        print("\nstopped.")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Monitor governance event bus (SQLite WAL)"
    )
    ap.add_argument("--bus", required=True, metavar="PATH", help="bus DB path")
    sub = ap.add_subparsers(dest="cmd", required=True)

    lp = sub.add_parser("list", help="print recent decisions")
    lp.add_argument("-n", type=int, default=40, metavar="N", help="rows (default 40)")

    sub.add_parser("watch", help="tail new decisions in real-time")

    args = ap.parse_args()
    conn = _open_ro(Path(args.bus))

    if args.cmd == "list":
        cmd_list(conn, args.n)
    else:
        cmd_watch(conn)


if __name__ == "__main__":
    main()
