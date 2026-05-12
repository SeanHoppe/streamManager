"""v10 P4 B' — live ``governance_decision`` -> ``rl_episodes.db`` subscriber.

Closes the structural gap noted at ``docs/v10-mvp-status.md`` L94: prior
to B' there was no in-process path from the live SM bus to the v10
episode store. Historic backfill via ``tools/extract_gov_to_jsonl.py``
remains useful for one-time seeding; this module is the routine path.

**Activation is opt-in.** ``attach(bus, db_path)`` returns a no-op when
``BRIDGE_RL_LOGGER_ENABLED`` is unset, so the v10 P4 ship-gate's
"logging overhead measurable on demand" invariant holds. Operators
enable per-environment; the dashboard server and the PreToolUse hook
both call ``attach`` at startup. Each process gets at most one
attached subscriber.

**Polarity filter** (per ``feedback_no_self_monitor.md`` §"Polarity
flip"): ``EpisodeLogger.record_decision`` refuses on either SM session
id (``BRIDGE_SM_SELF_SESSION_ID``) or SM project slug
(``BRIDGE_SM_PROJECT_SLUGS``); this adapter catches the refusal and
silently drops the row so SM-self leakage never propagates to
``rl_episodes.db``.

**Single-writer invariant.** ``EpisodeLogger`` uses SQLite WAL with a
single connection per process. ``attach`` MUST be called at most once
per process; calling it from multiple processes against the same
``rl_episodes.db`` is unsupported (writes serialise but p95 spikes are
likely). The hook is short-lived (per Bash call) so the per-process
constraint holds naturally; the dashboard is long-lived and attaches
once at startup.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from rl.episode_logger import EpisodeLogger, SelfMonitorRefusal

log = logging.getLogger(__name__)

_ENV_FLAG = "BRIDGE_RL_LOGGER_ENABLED"


def _is_enabled() -> bool:
    return os.environ.get(_ENV_FLAG, "").strip() == "1"


def attach(bus: Any, db_path: Path | str) -> Callable[[], None]:
    """Attach an episode-logging subscriber to ``bus`` if the env flag
    is set; otherwise return a no-op close-fn.

    Returns a callable that detaches the subscriber and closes the
    underlying ``EpisodeLogger`` connection. Callers SHOULD invoke the
    returned fn when tearing down the bus so the WAL handle releases.

    The subscriber callback is defensive: ``SelfMonitorRefusal`` and
    ``sqlite3.IntegrityError`` (duplicate ``(session_id, trace_id)``)
    are silently dropped; any other exception is logged but does not
    propagate (the bus already catches at fan-out per
    ``MessageBus.record_decision`` NFR-R6 try/except, but defending
    here keeps the bus log clean of expected refusals).
    """
    if not _is_enabled():
        return _noop_close

    logger = EpisodeLogger(Path(db_path))

    def _on_decision(envelope: Mapping[str, Any]) -> None:
        try:
            logger.record_decision(envelope, source="live")
        except SelfMonitorRefusal:
            # Expected for SM-self traffic; polarity-filter is doing
            # its job. Silent drop, no warn-spam in the live bus log.
            return
        except sqlite3.IntegrityError:
            # Duplicate (session_id, trace_id). Cassette replay or
            # bus restart can produce these; not an error.
            return
        except Exception:
            # All other failures: log + swallow. We never crash the
            # bus on logger faults (NFR-R6 + B' design constraint).
            log.exception("rl.bus_subscriber: record_decision failed")

    bus.subscribe_decision(_on_decision)

    def _close() -> None:
        try:
            bus.unsubscribe_decision(_on_decision)
        except Exception:
            log.exception("rl.bus_subscriber: unsubscribe failed")
        try:
            logger.close()
        except Exception:
            log.exception("rl.bus_subscriber: logger close failed")

    return _close


def _noop_close() -> None:
    return None


__all__ = ["attach"]
