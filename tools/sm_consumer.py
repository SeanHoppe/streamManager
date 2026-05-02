#!/usr/bin/env python
"""sm_consumer — governed-session daemon for SM desktop_command control plane.

Spawned alongside a Claude Code instance in a governed session. Long-polls
the SM dashboard for pending commands addressed to ``--session-id``,
validates HMAC, runs the matching executor, and acks.

Usage:
    python tools/sm_consumer.py \
        --sm-url http://127.0.0.1:8765 \
        --session-id $SESSION_ID \
        --secret-env SM_DESKTOP_SECRET

The shared secret is read from an env var (default ``SM_DESKTOP_SECRET``)
so the secret never appears on the command line / process list.
Reference: docs/sync-comms-qa.md OQ4.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from stream_manager.desktop_command_consumer import (  # noqa: E402
    CommandConsumer,
    _default_executors,
)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sm_consumer",
        description="Governed-session daemon: poll SM for desktop_command, validate, ack.",
    )
    parser.add_argument(
        "--sm-url",
        required=True,
        help="Base URL of the SM dashboard (e.g. http://127.0.0.1:8765).",
    )
    parser.add_argument(
        "--session-id",
        required=True,
        help="Governed session id this consumer represents.",
    )
    parser.add_argument(
        "--secret-env",
        default="SM_DESKTOP_SECRET",
        help="Env var holding the HMAC shared secret (default: SM_DESKTOP_SECRET).",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        help="Seconds between polls (default 1.0, OQ4 lock).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level (default INFO).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    secret = os.environ.get(args.secret_env, "").encode("utf-8")
    if not secret:
        print(
            f"error: env var {args.secret_env} is empty or unset", file=sys.stderr
        )
        return 2

    consumer = CommandConsumer(
        sm_url=args.sm_url,
        session_id=args.session_id,
        secret=secret,
        executors=_default_executors(),
        poll_interval=args.poll_interval,
    )
    try:
        consumer.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
