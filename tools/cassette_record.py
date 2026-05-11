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
from stream_manager.message_bus import Message as _BusMsgT  # noqa: E402
from stream_manager.message_bus import MessageBus  # noqa: E402
from stream_manager.messages import Message  # noqa: E402
from stream_manager.project_context import load as load_project_context  # noqa: E402

# v1.3 Path-A extension: real Sonnet categorizer call from the recorder.
# `categorize_pair` is the same subprocess call the live worker uses.
from stream_manager.learn_categorizer import (  # noqa: E402
    DEFAULT_MODEL as _LM_DEFAULT_MODEL,
    categorize_pair as _lm_categorize_pair,
    prompt_hash as _lm_prompt_hash,
)
from stream_manager.decay import consolidate_patterns as _lm_consolidate  # noqa: E402

# Re-use the deterministic load mix from the soak driver so the cassette
# matches the ship-gate soak shape one-for-one.
sys.path.insert(0, str(ROOT / "tools"))
from soak_driver import _build_payload_sequence  # noqa: E402


HAIKU_MODEL = "claude-haiku-4-5-20251001"

# Map cassette `kind` → governance routing layer. Mirrors the kind classes
# emitted by `_build_payload_sequence` and the layer integer that
# `engine.evaluate` persists via `bus.record_decision(layer=...)`.
_KIND_TO_LAYER = {"routine": 0, "l2_l3": 2, "l4": 4, "learn_dialogue": 0}


# v1.3 Path-A extension: pre-canned Learn Mode dialogue pairs.
# v1.4: extended to (prompt, reply, expected_category) so the same
# canonical input set drives both the cassette refresh AND the
# beacon harness (`tests/beacons/learn_mode_cassette_pairs.jsonl`,
# regenerated via `tools/regenerate_lm_beacons.py`). Single source
# of truth — eliminates the v1.3 duplication between cassette and
# beacon fixtures called out in the v1.4 backlog.
#
# Ordering is deterministic (no shuffle) so cassette + ship-gate
# + beacon harness align on the same inputs.
_LM_DIALOGUE_PAIRS_WITH_CATEGORY: list[tuple[str, str, str]] = [
    ("Force push to main now?", "yes do it", "approve"),
    ("Run rm -rf node_modules?", "no, keep them", "reject"),
    ("Install pkg X to fix Y?", "use pkg Z instead", "redirect"),
    ("Run pytest in CI?", "what does the suite cover?", "clarify"),
    ("Branch is rebased and pushed.", "ok thanks", "acknowledge"),
    ("Deploy to staging?", "approved, ship it", "approve"),
    ("Drop user_settings table?", "absolutely not", "reject"),
    ("Use pickle for serialization?", "use json instead", "redirect"),
    ("Run the migration?", "explain what it does first", "clarify"),
    ("All checks green.", "looks good", "approve"),
]
# Backward-compat alias for callers that only need (prompt, reply).
_LM_DIALOGUE_PAIRS: list[tuple[str, str]] = [
    (p, r) for (p, r, _cat) in _LM_DIALOGUE_PAIRS_WITH_CATEGORY
]


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


def _record_lm_dialogue(
    bus: "MessageBus",
    session_id: str,
    *,
    start_idx: int,
    model: str = _LM_DEFAULT_MODEL,
    runner=None,
) -> list[dict]:
    """v1.3 Path-A: drive Learn Mode dialogue pairs through the live
    categorizer and produce ``learn_dialogue`` cassette envelopes.

    For each pair in ``_LM_DIALOGUE_PAIRS``:

      1. Publish a ``desktop_prompt`` envelope and capture its id.
      2. Publish a ``user_reply`` envelope with ``metadata.pair_id``
         pointing at the prompt id (mirrors ``jsonl_tail._maybe_emit_learn_mode``).
      3. Call ``categorize_pair`` directly (no worker thread) so the
         recorded latency is the categorizer hot-path wall-clock only.
      4. Write a ``learn_pattern`` row through ``consolidate_patterns``
         so the cassette + ship-gate runs leave the canonical projection
         in the same shape the live worker would.
      5. Return one cassette row per pair.

    A failed categorize_pair (None result) produces an ``unknown`` row
    with confidence 0.0, matching the live worker's poison-skip path.
    The recorder never crashes on a single bad pair.
    """
    rows: list[dict] = []
    for offset, (prompt_text, reply_text) in enumerate(_LM_DIALOGUE_PAIRS):
        idx = start_idx + offset
        # Synthesize a dialogue chain. Real Desktop turns carry uuid +
        # parent_uuid; the recorder fakes both since there's no JSONL.
        prompt_uuid = f"cassette-prompt-{idx}"
        reply_uuid = f"cassette-reply-{idx}"
        try:
            prompt_env = _BusMsgT.new(
                session_id=session_id,
                type="desktop_prompt",
                direction="inbound",
                content=prompt_text,
                metadata={
                    "desktop_session_id": session_id,
                    "uuid": prompt_uuid,
                    "parent_uuid": "",
                    "ts": time.time(),
                    "synthetic": True,
                },
            )
            bus.publish(prompt_env)
            reply_env = _BusMsgT.new(
                session_id=session_id,
                type="user_reply",
                direction="inbound",
                content=reply_text,
                metadata={
                    "desktop_session_id": session_id,
                    "uuid": reply_uuid,
                    "parent_uuid": prompt_uuid,
                    "pair_id": prompt_env.id,
                    "ts": time.time(),
                    "synthetic": True,
                },
            )
            bus.publish(reply_env)
        except Exception as exc:
            print(
                f"[cassette] LM idx={idx} bus publish failed: {exc!r}",
                file=sys.stderr,
            )
            continue

        t0 = time.perf_counter()
        try:
            result = _lm_categorize_pair(
                prompt_text,
                reply_text,
                model=model,
                runner=runner,
            )
        except Exception as exc:
            print(
                f"[cassette] LM idx={idx} categorize failed: {exc!r}",
                file=sys.stderr,
            )
            result = None
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        if result is None:
            category = "unknown"
            confidence = 0.0
            reasoning = "categorizer returned None"
        else:
            category = result.category
            confidence = max(0.0, min(1.0, float(result.confidence)))
            reasoning = result.reasoning or ""

        # Mirror the live worker side-effect so canonical projection is
        # populated at recorder time too.
        try:
            _lm_consolidate(
                bus,
                _lm_prompt_hash(prompt_text),
                category,
                confidence,
                now_ts=time.time(),
            )
        except Exception:
            # Non-fatal — the cassette row is the artifact of record.
            pass

        rows.append(
            {
                "idx": idx,
                "kind": "learn_dialogue",
                "content": prompt_text,
                "recorded_latency_ms": round(elapsed_ms, 3),
                "decision": {
                    "action": "ALLOW",
                    "confidence": round(confidence, 4),
                    "reasoning": f"category={category}",
                    "matched_hash": "",
                    "model_used": model,
                    "layer": 0,
                },
                "desktop_prompt": prompt_text,
                "user_reply": reply_text,
                "recorded_categorize_latency_ms": round(elapsed_ms, 3),
                "category_result": {
                    "category": category,
                    "confidence": round(confidence, 4),
                    "reasoning": reasoning[:500],
                },
            }
        )
    return rows


def _record_ppp_envelopes(
    bus: MessageBus, session_id: str, start_idx: int,
) -> list[dict]:
    """v2.1 P1+P2 (FR-PPP) Layers 1 & 2: synthesize the full PPP envelope
    set — Layer 1 `audit.probe` + `audit.probe_ack`, then Layer 2
    `audit.canary_emit` + `audit.canary_observed` + `audit.probe_failure`.
    All five HMAC sigs reuse the `desktop_command` secret (issue #128 §A1).
    Canary envelopes ride the same opt-out flag (`--skip-ppp-pump`) per
    v2.1 P2 scope §3 — Layer 2 is part of the PPP pump, not a separate
    cassette section."""
    from stream_manager import desktop_commands
    from stream_manager.message_bus import (
        AuditCanaryEmitEnvelope,
        AuditCanaryObservedEnvelope,
        AuditProbeAckEnvelope,
        AuditProbeCandidate,
        AuditProbeEnvelope,
        AuditProbeFailureEnvelope,
    )
    issued_at = time.time()
    cand = AuditProbeCandidate(
        slug="cassette", jsonl_path="/tmp/cassette.jsonl",
        brain_id=session_id, last_event_ts=issued_at, prompt_hash="",
    )
    env = AuditProbeEnvelope(
        probe_id=f"cassette-probe-{start_idx}",
        candidate_streams=[cand], ttl_seconds=300,
        issued_at=issued_at, hmac_sig="",
    )
    env_payload = env.to_dict()
    env_payload["hmac_sig"] = desktop_commands.sign(
        {k: v for k, v in env_payload.items() if k != "hmac_sig"}
    )
    bus.write_envelope("audit.probe", env_payload)

    ack = AuditProbeAckEnvelope(
        probe_id=env.probe_id, selected_jsonl_path=cand.jsonl_path,
        signed_at=issued_at, expires_at=issued_at + 300.0, hmac_sig="",
    )
    ack_payload = ack.to_dict()
    ack_payload["hmac_sig"] = desktop_commands.sign(
        {k: v for k, v in ack_payload.items() if k != "hmac_sig"}
    )
    bus.write_envelope("audit.probe_ack", ack_payload)

    # v2.1 P2 — Layer 2 canary echo triplet. Three sequential envelopes
    # cover the binding-proof happy path (emit → observed) plus the
    # failure path (probe_failure). Cassette readers disambiguate by
    # `kind`; idx is informational.
    def _sign(p: dict) -> dict:
        p["hmac_sig"] = desktop_commands.sign(
            {k: v for k, v in p.items() if k != "hmac_sig"}
        )
        return p

    nonce = "cassette_nonce_" + str(start_idx).zfill(4)
    emit_payload = _sign(AuditCanaryEmitEnvelope(
        probe_id=env.probe_id, jsonl_path=cand.jsonl_path, nonce=nonce,
        issued_at=issued_at, timeout_s=10, hmac_sig="",
    ).to_dict())
    bus.write_envelope("audit.canary_emit", emit_payload)
    observed_payload = _sign(AuditCanaryObservedEnvelope(
        probe_id=env.probe_id, nonce=nonce,
        observed_at=issued_at + 1.0, jsonl_path=cand.jsonl_path,
        hmac_sig="",
    ).to_dict())
    bus.write_envelope("audit.canary_observed", observed_payload)
    failure_payload = _sign(AuditProbeFailureEnvelope(
        probe_id=env.probe_id + "-neg", reason="canary_timeout",
        failed_at=issued_at + 11.0, hmac_sig="",
    ).to_dict())
    bus.write_envelope("audit.probe_failure", failure_payload)

    # v2.1 P3 — Layer 3 negative-control hallucination envelope. Rides
    # the same `--skip-ppp-pump` opt-out per FR-PPP-14. Cassette also
    # records the decoy registration row so soak replay covers the
    # full Layer-3 surface (register → detect → envelope).
    decoy_rows = _record_decoy_envelopes(bus, start_idx + 5, issued_at)

    return [
        {"idx": start_idx, "kind": "audit_probe", "envelope": env_payload},
        {"idx": start_idx + 1, "kind": "audit_probe_ack",
         "envelope": ack_payload},
        {"idx": start_idx + 2, "kind": "audit_canary_emit",
         "envelope": emit_payload},
        {"idx": start_idx + 3, "kind": "audit_canary_observed",
         "envelope": observed_payload},
        {"idx": start_idx + 4, "kind": "audit_probe_failure",
         "envelope": failure_payload},
    ] + decoy_rows


def _record_decoy_envelopes(
    bus: MessageBus, start_idx: int, issued_at: float,
) -> list[dict]:
    """v2.1 P3 (FR-PPP-12..14) — Layer 3 negative-control cassette
    coverage. Records ONE decoy registration row + ONE
    `audit.hallucination_detected` envelope per cassette run.

    Rides the same `--skip-ppp-pump` opt-out as Layers 1/2 — Layer 3
    is part of the PPP pump, not a separate cassette section.
    """
    from stream_manager import desktop_commands
    from stream_manager.message_bus import (
        AuditHallucinationDetectedEnvelope,
    )
    probe_id = f"cassette-decoy-{start_idx}"
    jsonl_path = f"/tmp/cassette-decoy-{start_idx}.jsonl"
    reg_sig = desktop_commands.sign({
        "probe_id": probe_id, "jsonl_path": jsonl_path,
        "registered_at": float(issued_at),
    })
    _ok, *_ = bus.write_provenance_decoy(
        probe_id=probe_id, jsonl_path=jsonl_path,
        registered_at=issued_at, hmac_sig=reg_sig,
    )
    # cassette discards WAL-row payload; only writes the row
    detected_at = issued_at + 5.0
    halluc = AuditHallucinationDetectedEnvelope(
        probe_id=probe_id, jsonl_path=jsonl_path,
        detected_at=detected_at, hmac_sig="",
    )
    halluc_payload = halluc.to_dict()
    halluc_payload["hmac_sig"] = desktop_commands.sign(
        {k: v for k, v in halluc_payload.items() if k != "hmac_sig"}
    )
    bus.mark_decoy_triggered(probe_id=probe_id, triggered_at=detected_at)
    bus.write_envelope(
        "audit.hallucination_detected", halluc_payload,
    )
    return [
        {"idx": start_idx, "kind": "audit_decoy_register",
         "row": {"probe_id": probe_id, "jsonl_path": jsonl_path,
                 "registered_at": issued_at, "hmac_sig": reg_sig}},
        {"idx": start_idx + 1, "kind": "audit_hallucination_detected",
         "envelope": halluc_payload},
    ]


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
    ap.add_argument(
        "--lm-model",
        default=_LM_DEFAULT_MODEL,
        help=(
            "v1.3 Path-A: model id for the Learn Mode categorizer. "
            f"Defaults to {_LM_DEFAULT_MODEL} per design spec §2.4."
        ),
    )
    ap.add_argument(
        "--skip-lm-pump",
        action="store_true",
        help=(
            "v1.3 Path-A: skip the Learn Mode dialogue pump. Produces a "
            "v1.2-shape cassette (no learn_dialogue envelopes). Useful "
            "for cheap CI runs that only validate engine.evaluate plumbing."
        ),
    )
    ap.add_argument(
        "--skip-ppp-pump",
        action="store_true",
        help=(
            "v2.1 P1 (FR-PPP): skip the PPP pump. Default behaviour records "
            "one `audit.probe` + one `audit.probe_ack` envelope so cassette "
            "replay covers the full Layer 1 pair. Set this for legacy CI."
        ),
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
            # v1.3 Path-A: append Learn Mode dialogue envelopes.
            lm_row_count = 0
            if not args.skip_lm_pump:
                lm_rows = _record_lm_dialogue(
                    bus,
                    session_id,
                    start_idx=len(payloads),
                    model=args.lm_model,
                )
                for row in lm_rows:
                    fp.write(json.dumps(row) + "\n")
                    fp.flush()
                    written += 1
                lm_row_count = len(lm_rows)
                print(
                    f"[cassette] LM dialogue: {lm_row_count} pairs recorded "
                    f"(model={args.lm_model})"
                )

            # v2.1 P1 (FR-PPP) Layer 1: record one `audit.probe` +
            # one `audit.probe_ack` envelope so cassette replay covers
            # the full pair (`feedback_cassette_must_cover_new_envelopes.md`).
            # v2.1 P1a (R-cassette-idx): use actual LM row count, not the
            # magic-50 estimate; cassette readers disambiguate pairs by
            # `kind`, not by `idx`, but accurate idx makes diffs readable.
            if not args.skip_ppp_pump:
                ppp_idx = len(payloads) + lm_row_count
                ppp_rows = _record_ppp_envelopes(bus, session_id, ppp_idx)
                for row in ppp_rows:
                    fp.write(json.dumps(row) + "\n")
                    fp.flush()
                    written += 1
                print(f"[cassette] PPP: {len(ppp_rows)} envelope(s) recorded")
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
