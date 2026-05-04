#!/usr/bin/env python
"""Task A / v1.2: cassette recorder for the replay-tier soak.

Runs a real soak with ``BRIDGE_API_GOV=1`` against the Haiku model,
captures each engine.evaluate result + its wall-clock latency, and writes
a re-runnable cassette to ``tests/fixtures/soak_cassette_<YYYY-MM-DD>.jsonl``.

Each output line is one JSON envelope::

    {
      "idx": <int>,
      "kind": "routine" | "l2_l3" | "l4",
      "content": "<original prompt>",
      "recorded_latency_ms": <float>,
      "decision": {
        "action": "ALLOW|SUGGEST|GUIDE|INTERVENE|BLOCK",
        "confidence": <0.0-1.0>,
        "reasoning": "<short>",
        "matched_hash": "",
        "model_used": "claude-haiku-4-5-20251001",
        "layer": <int>
      }
    }

The cassette is intended as a *cheap baseline refresh* — the replay tier
runs against this artifact to detect plumbing regressions without
incurring per-CI quota cost. Cassette p95 is a relative signal only;
absolute latency belongs to the ship-gate soak (see ADR-5, ADR-17).

Usage::

    BRIDGE_API_GOV=1 BRIDGE_CLI_MODEL=claude-haiku-4-5-20251001 \\
        python tools/cassette_record.py --out tests/fixtures/

Writes ``tests/fixtures/soak_cassette_<YYYY-MM-DD>.jsonl`` and exits 0
on success, 2 on partial failure (some envelopes recorded, some failed).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from stream_manager.governance import GovernanceEngine  # noqa: E402
from stream_manager.message_bus import MessageBus  # noqa: E402
from stream_manager.messages import Message  # noqa: E402
from stream_manager.project_context import load as load_project_context  # noqa: E402

# Re-use the deterministic load mix from the soak driver so the cassette
# matches the ship-gate soak shape one-for-one.
sys.path.insert(0, str(ROOT / "tools"))
from soak_driver import _build_payload_sequence  # noqa: E402


HAIKU_MODEL = "claude-haiku-4-5-20251001"

# Map cassette `kind` → governance routing layer. Mirrors the kind classes
# emitted by `_build_payload_sequence` and the layer integer that
# `engine.evaluate` persists via `bus.record_decision(layer=...)`.
_KIND_TO_LAYER = {"routine": 0, "l2_l3": 2, "l4": 4}


def _check_cli_on_path() -> bool:
    return shutil.which("claude") is not None or shutil.which("claude.exe") is not None


def _sample(payloads, n: int) -> list[tuple[str, str]]:
    if n <= 0 or n >= len(payloads):
        return list(payloads)
    return list(payloads[:n])


def _resolve_cassette_path(out_dir: Path, *, allow_overwrite: bool) -> Path:
    """Pick the output cassette path.

    P1 / v1.3 hardening: previously the filename was derived from
    ``_dt.date.today().isoformat()`` only — same-day re-records silently
    clobbered the prior cassette in place (M2 had to recover from the
    ``v1.2.0`` tag). The default behaviour now appends a UTC HHMMSS
    suffix so successive runs land at distinct paths. Operators who
    explicitly want to clobber the day's cassette in place may pass
    ``--allow-overwrite`` (the legacy filename shape).
    """
    today = _dt.date.today().isoformat()
    if allow_overwrite:
        return out_dir / f"soak_cassette_{today}.jsonl"
    hhmmss = _dt.datetime.now(_dt.timezone.utc).strftime("%H%M%S")
    path = out_dir / f"soak_cassette_{today}T{hhmmss}Z.jsonl"
    # P1 / v1.3 review fix (Fix A): two recorder runs in the same UTC
    # second silently clobbered. Refuse to overwrite unless the operator
    # explicitly asked for it.
    if path.exists():
        raise FileExistsError(
            f"cassette already exists: {path}; pass --allow-overwrite to clobber"
        )
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        default="tests/fixtures",
        help="Output directory; cassette filename auto-derived from today's date.",
    )
    ap.add_argument(
        "--allow-overwrite",
        action="store_true",
        help="Allow overwriting an existing same-day cassette (no UTC HHMMSS "
             "suffix; clobbers prior cassette in place). Default behaviour "
             "appends a UTC HHMMSS suffix so same-day re-records do NOT "
             "silently overwrite the prior cassette (P1 / v1.3 fix).",
    )
    ap.add_argument(
        "--gov-db",
        default="tmp/cassette_gov.db",
        help="Throwaway WAL DB for the recording session.",
    )
    ap.add_argument(
        "--seed",
        type=int,
        default=4242,
        help="Same default seed as soak_driver so cassette + ship-gate align.",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Cap envelope count (0 = full 60). Useful for sample cassettes.",
    )
    ap.add_argument(
        "--cli-pool-size",
        type=int,
        default=2,
        help="CLI warm-pool size; v1.1 baseline = 2.",
    )
    ap.add_argument(
        "--model",
        default=HAIKU_MODEL,
        help=f"CLI model id; defaults to {HAIKU_MODEL} for cheap refresh.",
    )
    args = ap.parse_args()

    out_dir = (ROOT / args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    cassette_path = _resolve_cassette_path(
        out_dir, allow_overwrite=bool(args.allow_overwrite)
    )

    if not _check_cli_on_path():
        print(
            "[cassette] `claude` not on PATH; cassette recorder requires the "
            "real CLI to capture authentic decisions. Aborting.",
            file=sys.stderr,
        )
        return 2

    os.environ["BRIDGE_API_GOV"] = "1"
    os.environ.setdefault("BRIDGE_CLI_MODEL", args.model)

    payloads = _build_payload_sequence(args.seed)
    if args.limit > 0:
        payloads = _sample(payloads, args.limit)
    payloads = payloads[:60]

    gov_db = (ROOT / args.gov_db).resolve()
    gov_db.parent.mkdir(parents=True, exist_ok=True)
    for ext in ("", "-wal", "-shm"):
        p = Path(str(gov_db) + ext)
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass

    iso_ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bus = MessageBus(str(gov_db))
    session_id = f"cassette-{iso_ts}"
    bus.open_session(session_id, project_slug="cassette", pid=os.getpid())
    snap = load_project_context(str(ROOT))

    cli_pool_obj = None
    if args.cli_pool_size > 0:
        try:
            from stream_manager.cli_pool import CliPool, reap_stale_workers
            reap_stale_workers(root=ROOT)
            cli_pool_obj = CliPool(size=args.cli_pool_size, pid_root=ROOT)
            cli_pool_obj.warmup()
        except Exception as exc:
            print(f"[cassette] cli_pool init failed: {exc}", file=sys.stderr)
            cli_pool_obj = None

    engine = GovernanceEngine(
        project_context=snap, bus=bus, session_id=session_id,
        cli_pool=cli_pool_obj,
    )

    failures = 0
    written = 0
    try:
        with cassette_path.open("w", encoding="utf-8") as fp:
            for idx, (kind, content) in enumerate(payloads):
                msg = Message.new(role="user", content=content)
                t0 = time.perf_counter()
                try:
                    dec = engine.evaluate(msg)
                    decision_action = dec.action
                    decision_conf = dec.confidence
                    decision_reason = dec.reasoning
                    decision_layer = _KIND_TO_LAYER.get(kind, 0)
                except Exception as exc:
                    failures += 1
                    print(
                        f"[cassette] idx={idx} kind={kind} failed: {exc!r}",
                        file=sys.stderr,
                    )
                    continue
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                envelope = {
                    "idx": idx,
                    "kind": kind,
                    "content": content,
                    "recorded_latency_ms": round(elapsed_ms, 3),
                    "decision": {
                        "action": decision_action,
                        "confidence": round(decision_conf, 4),
                        "reasoning": decision_reason,
                        "matched_hash": "",
                        "model_used": args.model,
                        "layer": decision_layer,
                    },
                }
                fp.write(json.dumps(envelope) + "\n")
                fp.flush()
                written += 1
    finally:
        try:
            if cli_pool_obj is not None:
                cli_pool_obj.shutdown()
        except Exception:
            pass
        try:
            bus.close_session(session_id)
        except Exception:
            pass
        try:
            bus.close()
        except Exception:
            pass

    print(f"[cassette] wrote {written} envelopes -> {cassette_path}")
    if failures:
        print(f"[cassette] {failures} envelope(s) failed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
