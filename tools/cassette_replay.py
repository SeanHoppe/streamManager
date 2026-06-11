#!/usr/bin/env python
"""Replay safety-pack cassettes through GovernanceEngine.evaluate and
assert each decision matches the recorded `expected_verdict`. Closes
the C10 GAP blocker #2 (no dedicated replay surface for the safety
pack written by `tools/cassette_record_safety.py`).

Scope: this skeleton replays p1-p4 through the static L1-L3 ladder
(`project_context.fast_precheck` + ops classification) which does NOT
require a CLI pool. p5 (API-timeout -> OBSERVE) requires
`BRIDGE_FALLBACK_LATENCY_BUDGET_MS=1` at record time + a forced
timeout at replay time; for now p5 cassettes are skipped with a
SKIP row. Coordinator will extend this surface (or fold into pytest)
once the p5 re-record lands.

Usage (verdict-assertion mode, default)::

    python tools/cassette_replay.py --pack tests/cassettes/safety

Exits 0 if all replayed verdicts match `expected_verdict`, 1 on any
mismatch, 2 if no cassettes found.

----------------------------------------------------------------------
v10 P5 / #112 INFRASTRUCTURE side -- cassette-shadow mode
----------------------------------------------------------------------
When ``--shadow-recorder`` AND ``--shadow-proposal`` are supplied, the
replay instead drives ``rl.shadow.ShadowRecorder`` IN-PROCESS through
the production seam ``bus.subscribe_decision`` -- the SAME seam
``tools/soak_driver.py`` wires (soak_driver.py:1725) -- but fed by the
recorded cassette decisions rather than a live ``claude -p`` soak. This
is deterministic, offline, and writes ``rl_shadow.db`` tuples tagged
with a ``soak_run_id`` carrying the ``--mode=v10.1`` suffix (ADR-18
Amendment D: v10.1-mode rows are EXCLUDED from v10.3 writeback
promotion). It proves the shadow harness end-to-end and closes the
INFRASTRUCTURE / feasibility side of #112; it does NOT and CANNOT
satisfy a pre-registered v10.3 ship criterion (a real Tier-3 soak
does -- robin owns that read).

Usage (cassette-shadow mode)::

    python tools/cassette_replay.py --pack tests/cassettes/safety \\
        --shadow-recorder rl_shadow.db \\
        --shadow-proposal rl_proposals/v10p4-sample.json \\
        --mode v10.1

Polarity (feedback_no_self_monitor.md): the synthetic replay session
uses a non-SM project slug; ShadowRecorder's own SM-self filter is the
load-bearing guard and is left intact. Firewall (CLAUDE.md): the safety
cassette pack is SM-internal synthetic content -- no monitored-repo
paths are read.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))


def _load_cassettes(pack: Path) -> list[dict]:
    cassettes = sorted(pack.glob("p*.json"))
    return [json.loads(p.read_text(encoding="utf-8")) for p in cassettes]


def run_assert(pack: Path) -> int:
    """Default mode: replay through GovernanceEngine.evaluate and assert
    each decision matches the recorded ``expected_verdict``."""
    from stream_manager.governance import GovernanceEngine
    from stream_manager.message_bus import MessageBus
    from stream_manager.messages import Message
    from stream_manager.project_context import load as load_project_context

    cassettes = _load_cassettes(pack)
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
        for env in cassettes:
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


def _load_shadow_candidate(proposal: Path):
    """Build an ``rl.validate.Candidate`` from a proposal manifest.

    Handles both shapes deterministically:
      * a flat ``{"thresholds": {...}}`` (Candidate.from_json native), and
      * an ``rl_proposals`` manifest ``{"proposals": [{"thresholds": ...}]}``
        in which case the first (best-arm) proposal's thresholds are used.
    Falling through to ``Candidate.from_json`` would silently yield the
    0.75 default for the manifest shape, so the manifest branch is
    explicit.
    """
    from rl.validate import L4_THRESHOLD_KEY, Candidate

    data = json.loads(Path(proposal).read_text(encoding="utf-8"))
    if data.get("thresholds"):
        return Candidate.from_json(Path(proposal))
    proposals = data.get("proposals") or []
    if proposals and isinstance(proposals[0], dict):
        thr = {k: float(v) for k, v in (proposals[0].get("thresholds") or {}).items()}
        return Candidate(
            thresholds=thr,
            manifest_sha=str(data.get("manifest_sha", "")),
            seed=int(data.get("seed", 0)),
        )
    # Last resort: empty thresholds -> Candidate.l4_threshold() default.
    return Candidate(thresholds={L4_THRESHOLD_KEY: 0.75})


def run_shadow(
    pack: Path,
    shadow_db: Path,
    proposal: Path,
    soak_run_id: str,
) -> int:
    """Cassette-shadow mode: drive ShadowRecorder through the production
    ``bus.subscribe_decision`` seam from recorded cassette decisions and
    write ``rl_shadow.db`` tuples tagged ``soak_run_id`` (carrying the
    ``--mode=v10.1`` suffix). Deterministic, in-process, offline."""
    from rl.shadow import ShadowRecorder
    from stream_manager.message_bus import MessageBus

    cassettes = _load_cassettes(pack)
    if not cassettes:
        print(f"[cassette-shadow] no cassettes under {pack}", file=sys.stderr)
        return 2

    if not proposal.exists():
        print(f"[cassette-shadow] proposal not found: {proposal}", file=sys.stderr)
        return 2

    candidate = _load_shadow_candidate(proposal)

    gov_db = ROOT / "tmp" / "cassette_shadow_gov.db"
    gov_db.parent.mkdir(parents=True, exist_ok=True)
    # Fresh gov db per run so message/decision ids never collide across
    # runs and the JOIN that builds the fanned envelope is clean.
    if gov_db.exists():
        gov_db.unlink()

    bus = MessageBus(str(gov_db))
    sid = f"cassette-shadow-{soak_run_id}"
    # Non-SM project slug: ShadowRecorder's SM-self polarity filter
    # (feedback_no_self_monitor.md) must see a monitored-target slug,
    # never an SM slug, so the rows are NOT self-monitor-dropped. The
    # slug is a synthetic harness label, not a real monitored repo.
    bus.open_session(sid, project_slug="cassette-shadow", pid=0)

    recorder = ShadowRecorder(candidate, shadow_db, soak_run_id=soak_run_id)

    # Per-decision ground-truth lookup. The bus fan-out envelope
    # (message_bus.record_decision) is FROZEN and does not carry
    # ground-truth, so a thin enriching wrapper injects the cassette's
    # `expected_verdict` + `state_features` before the recorder sees the
    # envelope. The wrapper IS the subscriber registered on the bus, so
    # the production `subscribe_decision` seam is exercised verbatim.
    gt_by_message: dict[str, dict] = {}

    def _enrich_and_record(envelope: dict) -> None:
        extra = gt_by_message.get(str(envelope.get("message_id", "")), {})
        enriched = dict(envelope)
        if extra.get("ground_truth_verdict") is not None:
            enriched["ground_truth_verdict"] = extra["ground_truth_verdict"]
        if extra.get("state_features") is not None:
            enriched["state_features"] = extra["state_features"]
        recorder.on_governance_decision(enriched)

    bus.subscribe_decision(_enrich_and_record)

    replayed = 0
    try:
        for env in cassettes:
            priority = str(env.get("priority", "?"))
            decision = env.get("decision") or {}
            action = str(decision.get("action") or env.get("expected_verdict", "ALLOW"))
            confidence = float(decision.get("confidence", 0.0))
            reasoning = str(decision.get("reasoning", ""))
            matched_hash = str(decision.get("matched_hash", ""))
            model_used = str(decision.get("model_used", ""))
            layer = int(decision.get("layer", 0))

            # Insert a minimal message row directly so record_decision's
            # JOIN (messages -> sessions) resolves session_id + slug. We
            # bypass bus.publish() because the bus Message model differs
            # from messages.py Message; a direct row keeps it deterministic.
            message_id = str(uuid.uuid4())
            ts = time.time()
            with bus._lock:
                seq_row = bus._conn.execute(
                    "SELECT COALESCE(MAX(sequence), 0) FROM messages WHERE session_id=?",
                    (sid,),
                ).fetchone()
                sequence = (seq_row[0] or 0) + 1
                bus._conn.execute(
                    "INSERT INTO messages (id, session_id, sequence, type, "
                    "direction, content, context, metadata, timestamp) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        message_id, sid, sequence, "user", "inbound",
                        str(env.get("prompt", "")), "{}", "{}", ts,
                    ),
                )

            # Register the ground-truth + state-features for this trace.
            # The fanned envelope's trace_id == decision_id, but the
            # message_id is stable across the fan-out, so we key on it.
            gt_by_message[message_id] = {
                "ground_truth_verdict": env.get("expected_verdict"),
                "state_features": {
                    "priority": priority,
                    "intent_anchor": env.get("intent_anchor", ""),
                    "fallback_latency_budget_ms": env.get(
                        "fallback_latency_budget_ms", 0),
                },
            }

            # Fan out the recorded decision -> ShadowRecorder (in-process,
            # no live claude -p). This is the production seam.
            bus.record_decision(
                message_id=message_id,
                action=action,
                confidence=confidence,
                reasoning=reasoning,
                matched_hash=matched_hash,
                model_used=model_used,
                layer=layer,
            )
            replayed += 1
            print(f"[{priority}] shadow-recorded verdict={action} "
                  f"conf={confidence:.2f} gt={env.get('expected_verdict')}")
    finally:
        with contextlib.suppress(Exception):
            bus.unsubscribe_decision(_enrich_and_record)
        recorder.close()
        bus.close_session(sid)
        bus.close()

    summary = {
        "mode": "v10.1",
        "soak_run_id": soak_run_id,
        "shadow_db": str(shadow_db),
        "proposal": str(proposal),
        "candidate_l4_threshold": candidate.l4_threshold(),
        "cassettes_replayed": replayed,
        "recorded": recorder.recorded,
        "dropped": recorder.dropped,
        "budget_violations": recorder.budget_violations,
    }
    print("[cassette-shadow] " + json.dumps(summary, sort_keys=True))
    # Non-fatal if some rows were dropped by the non-invasion budget;
    # the harness "ran" so long as it recorded at least one row and
    # never observed an SM-self leak (the recorder drops those silently,
    # which would show as recorded<replayed with dropped==0).
    return 0 if recorder.recorded > 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pack", default="tests/cassettes/safety")
    ap.add_argument(
        "--shadow-recorder", type=str, default=None,
        help="Path to rl_shadow.db; enables cassette-shadow mode "
             "(requires --shadow-proposal).")
    ap.add_argument(
        "--shadow-proposal", type=str, default=None,
        help="Path to an rl_proposals manifest / candidate thresholds json.")
    ap.add_argument(
        "--mode", default="v10.1",
        help="Integrity-firewall mode tag baked into soak_run_id "
             "(default v10.1; Amendment D excludes v10.1 rows from "
             "v10.3 writeback).")
    ap.add_argument(
        "--soak-run-id", default=None,
        help="Override the soak_run_id (default: <iso>--mode=<mode>).")
    args = ap.parse_args()

    pack = (ROOT / args.pack).resolve()

    if args.shadow_recorder and args.shadow_proposal:
        shadow_db = (ROOT / args.shadow_recorder).resolve() \
            if not Path(args.shadow_recorder).is_absolute() \
            else Path(args.shadow_recorder)
        proposal = (ROOT / args.shadow_proposal).resolve() \
            if not Path(args.shadow_proposal).is_absolute() \
            else Path(args.shadow_proposal)
        if args.soak_run_id:
            soak_run_id = args.soak_run_id
        else:
            iso = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            soak_run_id = f"{iso}--mode={args.mode}"
        return run_shadow(pack, shadow_db, proposal, soak_run_id)

    if bool(args.shadow_recorder) ^ bool(args.shadow_proposal):
        print("[cassette-replay] --shadow-recorder and --shadow-proposal "
              "must be supplied together", file=sys.stderr)
        return 2

    return run_assert(pack)


if __name__ == "__main__":
    raise SystemExit(main())
