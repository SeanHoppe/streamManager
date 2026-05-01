"""Spike C test subprocess. Reads stdin lines, echoes with ANSI noise, exits on EOF.

Used in place of `claude` for self-contained testing — proves the wire can
proxy a real subprocess without depending on the Claude CLI being installed.
"""

from __future__ import annotations

import sys


def main() -> None:
    sys.stdout.write("\x1b[36m[echo subprocess ready]\x1b[0m\n")
    sys.stdout.flush()
    for line in sys.stdin:
        line = line.rstrip("\n")
        sys.stdout.write(f"\x1b[33m[echo]\x1b[0m {line}\n")
        sys.stdout.flush()
    sys.stdout.write("\x1b[31m[echo subprocess exiting]\x1b[0m\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
