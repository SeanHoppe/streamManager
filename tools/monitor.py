"""WAL bus session monitor.

Usage::

    # List all sessions in a bus DB:
    python tools/monitor.py --bus /tmp/gov.db list

    # Stream the latest active session (blocks until Ctrl-C):
    python tools/monitor.py --bus /tmp/gov.db watch

    # Stream a specific session by ID:
    python tools/monitor.py --bus /tmp/gov.db watch --session-id <id>

    # Faster poll interval:
    python tools/monitor.py --bus /tmp/gov.db --poll-ms 50 watch
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from stream_manager.message_bus import WalReader, list_sessions  # noqa: E402


def _fmt_ts(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def cmd_list(db_path: str) -> int:
    sessions = list_sessions(db_path)
    if not sessions:
        print("No sessions in bus DB.")
        return 0
    print(f"{'ID':<40} {'slug':<20} {'pid':<8} {'started':<20} status")
    print("-" * 100)
    for s in sessions:
        status = "active" if s["ended_at"] is None else "closed"
        slug = (s["project_slug"] or "")[:18]
        pid = str(s["pid"] or "")
        print(f"{s['id']:<40} {slug:<20} {pid:<8} {_fmt_ts(s['started_at']):<20} {status}")
    return 0


def cmd_watch(db_path: str, session_id: str, poll_ms: int) -> int:
    print(f"Watching {session_id!r}  db={db_path!r}  poll={poll_ms}ms  (Ctrl-C to stop)")
    reader = WalReader(db_path, session_id, poll_ms=poll_ms)
    try:
        for row in reader:
            ts = _fmt_ts(row["timestamp"])
            action = ""
            # decisions are a separate table; show content type + direction here
            print(
                f"[{ts}] seq={row['sequence']:>4}  {row['type']:<20} {row['direction']}"
            )
            preview = (row["content"] or "")[:140].replace("\n", " ")
            print(f"  {preview}")
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        reader.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="WAL bus session monitor")
    ap.add_argument("--bus", required=True, help="Path to WAL bus SQLite DB")
    ap.add_argument("--poll-ms", type=int, default=100, help="Poll interval in ms (default 100)")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("list", help="List all sessions")

    watch_p = sub.add_parser("watch", help="Stream a session in real-time")
    watch_p.add_argument(
        "--session-id",
        default="",
        help="Session ID to watch (default: latest active session)",
    )

    args = ap.parse_args()

    if args.cmd == "list" or args.cmd is None:
        return cmd_list(args.bus)

    if args.cmd == "watch":
        session_id = args.session_id
        if not session_id:
            sessions = list_sessions(args.bus)
            active = [s for s in sessions if s["ended_at"] is None]
            if not active:
                print(
                    "No active sessions. Pass --session-id to watch a closed session.",
                    file=sys.stderr,
                )
                return 1
            session_id = active[0]["id"]
            print(f"Auto-selected latest active session: {session_id}")
        return cmd_watch(args.bus, session_id, args.poll_ms)

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
