"""v10 P5 — Shadow recorder for ghost-path candidate execution.

Records (production, candidate, state, ground-truth) into a dedicated
``rl_shadow.db`` so a candidate from a ``rl_proposals/*.json`` manifest
can be A/B-evaluated against the live production decision without
affecting the production decision flow.

Non-invasion invariant (ADR-5 §"v10 shadow overhead"):
``on_governance_decision`` is wall-clock-bounded at 50 ms p95; drops
the row + emits ``rl_shadow_dropped`` envelope on overrun. Production
NEVER waits on shadow. Polarity filter
(``feedback_no_self_monitor.md``) drops SM-self envelopes.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from rl.validate import Candidate

log = logging.getLogger(__name__)

NON_INVASION_BUDGET_MS = 50.0
_DEFAULT_SM_SLUGS = "streamManager"

SHADOW_SCHEMA = """
CREATE TABLE IF NOT EXISTS shadow_episodes (
    shadow_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc               TEXT NOT NULL,
    session_id           TEXT NOT NULL,
    trace_id             TEXT NOT NULL,
    state_features_json  TEXT NOT NULL,
    production_action    REAL NOT NULL,
    production_verdict   TEXT NOT NULL,
    candidate_action     REAL NOT NULL,
    candidate_verdict    TEXT NOT NULL,
    agree                INTEGER NOT NULL,
    ground_truth_known   INTEGER NOT NULL,
    ground_truth_verdict TEXT,
    soak_run_id          TEXT NOT NULL,
    UNIQUE(session_id, trace_id, soak_run_id)
);
CREATE INDEX IF NOT EXISTS idx_shadow_ts       ON shadow_episodes(ts_utc);
CREATE INDEX IF NOT EXISTS idx_shadow_soak_run ON shadow_episodes(soak_run_id);
"""


class SelfMonitorRefusal(ValueError):
    pass


def _sm_slug_set() -> frozenset[str]:
    raw = os.environ.get("BRIDGE_SM_PROJECT_SLUGS", _DEFAULT_SM_SLUGS)
    return frozenset(s.strip() for s in raw.split(",") if s.strip())


def _is_sm_self(env: Mapping[str, Any]) -> bool:
    sm_self = os.environ.get("BRIDGE_SM_SELF_SESSION_ID", "").strip()
    if sm_self and str(env.get("session_id", "")).strip() == sm_self:
        return True
    slug = str(env.get("project_slug", "")).strip()
    return bool(slug) and slug in _sm_slug_set()


def candidate_decision(
    candidate: Candidate, envelope: Mapping[str, Any]
) -> tuple[float, str]:
    """Offline (no live `claude -p` call) candidate decision. v10.1
    action space = constant L4 threshold; the candidate's verdict
    matches production when actions equal, else flips to ALLOW when
    the envelope confidence clears the candidate threshold."""
    cand_a = candidate.l4_threshold()
    prod_a = float(envelope.get("action_taken", envelope.get("threshold", cand_a)))
    prod_v = str(envelope.get("verdict", "ALLOW"))
    if abs(prod_a - cand_a) < 1e-9:
        return cand_a, prod_v
    conf = float(envelope.get("confidence", 0.0))
    return cand_a, ("ALLOW" if conf + 1e-9 >= cand_a else prod_v)


class ShadowRecorder:
    def __init__(
        self,
        candidate: Candidate,
        db_path: Path,
        *,
        soak_run_id: str,
        bus_emit: Callable[[Mapping[str, Any]], None] | None = None,
        non_invasion_budget_ms: float = NON_INVASION_BUDGET_MS,
    ) -> None:
        self.candidate = candidate
        self.db_path = Path(db_path)
        self.soak_run_id = str(soak_run_id)
        self._bus_emit = bus_emit
        self._budget_ms = float(non_invasion_budget_ms)
        self._dropped = 0
        self._recorded = 0
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(SHADOW_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> ShadowRecorder:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @property
    def recorded(self) -> int:
        return self._recorded

    @property
    def dropped(self) -> int:
        return self._dropped

    def on_governance_decision(self, envelope: Mapping[str, Any]) -> None:
        if _is_sm_self(envelope):
            return
        start_ns = time.perf_counter_ns()
        try:
            features = envelope.get("state_features") or envelope.get("state") or {}
            features_json = json.dumps(features, sort_keys=True)
            prod_a = float(envelope.get(
                "action_taken",
                envelope.get("threshold", self.candidate.l4_threshold()),
            ))
            prod_v = str(envelope.get("verdict", "ALLOW"))
            cand_a, cand_v = candidate_decision(self.candidate, envelope)
            gt = envelope.get("ground_truth_verdict")
            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1e6
            if elapsed_ms > self._budget_ms:
                self._drop(envelope, "candidate_eval_overrun", elapsed_ms)
                return
            try:
                self._conn.execute(
                    "INSERT INTO shadow_episodes (ts_utc, session_id, trace_id,"
                    " state_features_json, production_action, production_verdict,"
                    " candidate_action, candidate_verdict, agree,"
                    " ground_truth_known, ground_truth_verdict, soak_run_id)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(envelope.get("ts_utc") or _now_iso()),
                        str(envelope["session_id"]),
                        str(envelope["trace_id"]),
                        features_json, prod_a, prod_v, cand_a, cand_v,
                        1 if prod_v == cand_v else 0,
                        1 if gt is not None else 0,
                        str(gt) if gt is not None else None,
                        self.soak_run_id,
                    ),
                )
                self._recorded += 1
            except sqlite3.IntegrityError:
                return
        except Exception as exc:
            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1e6
            log.exception("rl.shadow: on_governance_decision failed (%s)", exc)
            self._drop(envelope, "shadow_exception", elapsed_ms)

    def _drop(self, env: Mapping[str, Any], reason: str, elapsed_ms: float) -> None:
        self._dropped += 1
        if self._bus_emit is None:
            return
        try:
            self._bus_emit({
                "envelope": "rl_shadow_dropped",
                "reason": reason,
                "elapsed_ms": float(elapsed_ms),
                "budget_ms": self._budget_ms,
                "session_id": env.get("session_id"),
                "trace_id": env.get("trace_id"),
                "soak_run_id": self.soak_run_id,
            })
        except Exception:
            log.exception("rl.shadow: bus_emit on drop failed")


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
