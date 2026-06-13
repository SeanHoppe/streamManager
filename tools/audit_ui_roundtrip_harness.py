#!/usr/bin/env python
"""Live FR-PPP provenance-audit round-trip harness for the KingMode UI spike.

WHAT THIS PROVES
    The render-validator + axe gates exercise the AuditDock surface only at the
    BUILD / static-contract / empty-state level. They never drive a live
    probe / canary / hallucination flow. This harness closes that deferral: it
    boots the REAL dashboard server (`dashboard.server:app`) in-process, waits
    for a live browser SSE subscriber to attach, then drives the full FR-PPP
    envelope sequence through the REAL transport so a puppeteer observer
    (test/audit-roundtrip.spec.mjs) can assert the AuditDock DOM transitions.

    Layer-1  audit.probe                -> AuditProbeRow (radio candidate list)
    Layer-2  audit.canary_emit          -> CanaryEchoRow (nonce + countdown)
             audit.canary_observed      -> CanaryEchoRow flips observed (auto-clear)
    Layer-3  audit.hallucination_detected-> HallucinationAlert (operator-dismiss)

FIDELITY / HONESTY
    * audit.probe + audit.canary_emit are emitted via the REAL governance seams
      (`GovernanceEngine.emit_audit_probe` / `.emit_audit_canary`) -- the same
      calls `/api/sm-probe` + the ack auto-emit make. The HITL pending row is a
      real `hitl_pending` row read back by AuditDock over `/api/hitl/pending`.
    * audit.canary_observed + audit.hallucination_detected are normally emitted
      by `jsonl_tail` when it sees the nonce / a decoy-path record in a tailed
      transcript. Driving a live LLM session to echo a nonce is out of scope for
      a UI-transport check (and is covered by tests/test_audit_canary_observe.py
      + tests/test_audit_hallucination_detect.py). Here they are written via the
      SAME `bus.write_envelope(...)` seam the worker uses (jsonl_tail.py:558 /
      governance.py:1563), with the real envelope dataclasses -- identical wire
      shape, deterministic, no live session required.

ISOLATION (firewall + polarity, CLAUDE.md)
    * GOV_DB + BRIDGE_PROJECTS_DIR are fresh temp dirs -- the worker tails an
      empty fixture project and never reads a real (or firewalled) transcript.
    * BRIDGE_PROJECT_SLUG is a non-SM fixture slug; SM_OWN_SESSION_ID is a dummy
      distinct from the governed fixture session (the registry refuses self).
    * Every fixture identifier (slug / path / brain_id / session id) is generic
      synthetic vocabulary -- no monitored-project names (M16 zero-contamination).

USAGE
    python tools/audit_ui_roundtrip_harness.py
    Env overrides: HARNESS_PORT (8765), HARNESS_HOLD_S (15), HARNESS_WAIT_SUB_S (45).
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

PORT = int(os.environ.get("HARNESS_PORT", "8765"))
HOLD_S = float(os.environ.get("HARNESS_HOLD_S", "15"))
WAIT_SUB_S = float(os.environ.get("HARNESS_WAIT_SUB_S", "45"))

# Generic synthetic fixture vocabulary (M16: no monitored-project names).
FIX_SESSION = "governed-fixture-session-001"
SM_OWN = "sm-self-harness-0000"
FIX_SLUG = "ui-audit-fixture"


def _log(msg: str) -> None:
    print(f"[harness] {msg}", flush=True)


def _set_env(tmp: Path) -> None:
    """Set the isolation env BEFORE importing dashboard.server (it snapshots
    GOV_DB at import time)."""
    (tmp / "projects").mkdir(parents=True, exist_ok=True)
    os.environ["GOV_DB"] = str(tmp / "gov.db")
    os.environ["SM_OWN_SESSION_ID"] = SM_OWN
    os.environ.setdefault("BRIDGE_PROJECT_SLUG", FIX_SLUG)
    os.environ["BRIDGE_PROJECTS_DIR"] = str(tmp / "projects")
    os.environ["SM_CLI_POOL_SIZE"] = "0"  # no `claude` workers spawned
    os.environ.pop("BRIDGE_RL_LOGGER_ENABLED", None)


def _candidate_dict(slug, jsonl_path, brain_id, last_event_ts, prompt_hash):
    # Matches AuditProbeEnvelope candidate_streams[*] wire shape exactly.
    return {
        "slug": slug,
        "jsonl_path": jsonl_path,
        "brain_id": brain_id,
        "last_event_ts": last_event_ts,
        "prompt_hash": prompt_hash,
    }


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="audit-ui-roundtrip-"))
    _set_env(tmp)

    # Import AFTER env is set.
    import uvicorn

    import dashboard.server as srv
    from stream_manager.message_bus import (
        AuditCanaryObservedEnvelope,
        AuditHallucinationDetectedEnvelope,
        AuditProbeCandidate,
    )

    # Boot the real ASGI app in a daemon thread. uvicorn's signal-handler
    # install is a no-op off the main thread, so this is safe.
    config = uvicorn.Config(
        srv.app, host="127.0.0.1", port=PORT, log_level="warning"
    )
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    # Wait for the server to accept connections.
    import http.client

    deadline = time.time() + 30
    up = False
    while time.time() < deadline:
        try:
            c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=2)
            c.request("GET", "/api/hitl/pending")
            r = c.getresponse()
            r.read()
            c.close()
            if r.status < 500:
                up = True
                break
        except Exception:
            time.sleep(0.3)
    if not up:
        _log("FATAL: server did not come up")
        return 2
    _log(f"READY http://127.0.0.1:{PORT}")

    bus = srv._get_bus()
    if bus is None:
        _log("FATAL: bus unavailable")
        return 2

    # Wait for the browser's /events EventSource to register as an envelope
    # subscriber. This is the rendezvous: we never fan a named bus event into
    # the void (named events have NO replay).
    def sub_count() -> int:
        try:
            return int(bus.envelope_subscriber_count())
        except Exception:
            return 0

    deadline = time.time() + WAIT_SUB_S
    while time.time() < deadline and sub_count() < 1:
        time.sleep(0.25)
    n = sub_count()
    if n < 1:
        _log(
            "WARN: no envelope subscriber attached within "
            f"{WAIT_SUB_S}s -- driving anyway (events may be dropped)"
        )
    else:
        _log(f"SUBSCRIBER attached (count={n})")

    # Let AuditDock finish mounting + binding its onBusEvent handlers (the
    # EventSource opens slightly before the component's onMount runs).
    time.sleep(2.0)

    reg = srv._get_engine_registry()
    if reg is None:
        _log("FATAL: engine registry unavailable")
        return 2
    eng = reg.get_or_create(FIX_SESSION)

    now = time.time()
    proj = tmp / "projects"
    cands = [
        AuditProbeCandidate(
            slug="demo-stream-alpha",
            jsonl_path=str(proj / "demo-stream-alpha" / f"{FIX_SESSION}.jsonl"),
            brain_id=FIX_SESSION,
            last_event_ts=now,
            prompt_hash="a1b2c3d4",
        ),
        AuditProbeCandidate(
            slug="demo-stream-beta",
            jsonl_path=str(proj / "demo-stream-beta" / "other-fixture-002.jsonl"),
            brain_id="other-fixture-002",
            last_event_ts=now - 30,
            prompt_hash="e5f6a7b8",
        ),
    ]

    # -- Layer 1: real emit_audit_probe (writes the HITL row + fans audit.probe).
    probe_id, hitl_id, delivered = eng.emit_audit_probe(cands)
    _log(f"PROBE emitted probe_id={probe_id} hitl_id={hitl_id} delivered={delivered}")

    # Re-fan the audit.probe envelope a few times so the cached candidate list
    # lands even if the very first fan raced AuditDock's handler binding. Same
    # probe_id => AuditDock.onProbe re-caches idempotently; the HITL row is
    # already committed for the GET /api/hitl/pending seed regardless.
    probe_dict = {
        "probe_id": probe_id,
        "candidate_streams": [
            _candidate_dict(
                c.slug, c.jsonl_path, c.brain_id, c.last_event_ts, c.prompt_hash
            )
            for c in cands
        ],
        "ttl_seconds": 1800,
        "issued_at": now,
        "hmac_sig": "",
    }
    for _ in range(3):
        time.sleep(1.0)
        bus.write_envelope("audit.probe", probe_dict)
    _log("PROBE re-fan complete")

    # -- Layer 2a: real emit_audit_canary (fans audit.canary_emit).
    time.sleep(2.0)
    nonce, _cenv, cdel = eng.emit_audit_canary(probe_id, cands[0].jsonl_path)
    _log(f"CANARY_EMIT nonce={nonce} delivered={cdel}")

    # -- Layer 2b: canary observed (worker seam: bus.write_envelope).
    time.sleep(3.0)
    observed = AuditCanaryObservedEnvelope(
        probe_id=probe_id,
        nonce=nonce,
        observed_at=time.time(),
        jsonl_path=cands[0].jsonl_path,
        hmac_sig="",
    ).to_dict()
    od = bus.write_envelope("audit.canary_observed", observed)
    _log(f"CANARY_OBSERVED delivered={od}")

    # -- Layer 3: hallucination on a registered-decoy path (negative control).
    time.sleep(3.0)
    decoy_path = str(proj / "decoy-stream" / "decoy-negative-control.jsonl")
    halluc = AuditHallucinationDetectedEnvelope(
        probe_id=probe_id,
        jsonl_path=decoy_path,
        detected_at=time.time(),
        hmac_sig="",
    ).to_dict()
    hd = bus.write_envelope("audit.hallucination_detected", halluc)
    _log(f"HALLUCINATION delivered={hd}")

    # Hold the server up so the observer can finish asserting + dismiss.
    _log(f"HOLD {HOLD_S}s")
    time.sleep(HOLD_S)
    _log("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
