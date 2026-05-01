"""Spike C runner. Wraps a subprocess in WireCLI; defaults to the echo subprocess."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from stream_manager.cli_client import WireCLI


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8767)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--no-strip-ansi", action="store_true")
    p.add_argument("cmd", nargs=argparse.REMAINDER, help="subprocess command (after --)")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    if not args.cmd:
        default = [sys.executable, str(Path(__file__).with_name("echo_subprocess.py"))]
        cmd = default
    else:
        cmd = args.cmd[1:] if args.cmd and args.cmd[0] == "--" else args.cmd

    wire = WireCLI(cmd=cmd, host=args.host, port=args.port, strip_ansi_output=not args.no_strip_ansi)
    return asyncio.run(wire.run())


if __name__ == "__main__":
    sys.exit(main())
