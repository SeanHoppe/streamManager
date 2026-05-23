#!/usr/bin/env python
"""Replay safety-pack cassettes through GovernanceEngine.evaluate and
assert each decision matches the recorded `expected_verdict`. Closes
the C10 GAP blocker #2 (no dedicated replay surface for the safety
pack written by `tools/cassette_record_safety.py`).

Scope: this skeleton replays p1-p4 through the static L1-L3 ladder
(`project_context.fast_precheck` + ops classification) which does NOT
require a CLI pool. p5 (API-timeout → OBSERVE) requires
`BRIDGE_FALLBACK_LATENCY_BUDGET_MS=1` at record time + a forced
timeout at replay time; for now p5 cassettes are skipped with a
SKIP row. Coordinator will extend this surface (or fold into pytest)
once the p5 re-record lands.

Usage::

    python tools/cassette_replay.py --pack tests/cassettes/safety

Exits 0 if all replayed verdicts match `expected_verdict`, 1 on any
mismatch, 2 if no cassettes found.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pack", default="tests/cassettes/safety")
    args = ap.parse_args()

    from stream_manager.governance import GovernanceEngine
    from stream_manager.message_bus import MessageBus
    from stream_manager.messages import Message
    from stream_manager.project_context import load as load_project_context

    pack = (ROOT / args.pack).resolve()
    cassettes = sorted(pack.glob("p*.json"))
    if not cassettes:
        print(f"[cassette-replay] no cassettes under {pack}", file=sys.stderr)
        return 2

    db = ROOT / "tmp" / "cassette_replay_gov.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    bus = MessageBus(str(db))
    sid = "cassette-replay"
    bus.open_session(sid, project_slug="cassette-replay", pid=0)
    engine = GovernanceEngine(
        project_context=load_project_context(str(ROOT)),
        bus=bus, session_id=sid,
    )
    fails = 0
    try:
        for path in cassettes:
            env = json.loads(path.read_text(encoding="utf-8"))
            if env["priority"] == "p5":
                print(f"[{env['priority']}] SKIP (timeout-simulation re-record pending)")
                continue
            dec = engine.evaluate(Message.new(role="user", content=env["prompt"]))
            ok = dec.action == env["expected_verdict"]
            fails += 0 if ok else 1
            tag = "PASS" if ok else "FAIL"
            print(f"[{env['priority']}] expected={env['expected_verdict']} got={dec.action} {tag}")
    finally:
        bus.close_session(sid)
        bus.close()
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
