"""v1.9 P3 — Learn Mode JSONL source expansion.

Adds a configurable list of *external* JSONL sources to the Learn Mode
ingest pipeline. The default is empty (off; existing v1.3 Desktop session
ingest path in ``jsonl_tail.py`` is unchanged). Each configured source is
tail-watched and its dialogue turns are tagged with a ``source_label``
before being passed to the categoriser, so oversight-agent patterns
(e.g. certPortal Dave/Jen/Jason/Matt/Oliver/Michael) can be attributed
separately from SM-governance patterns.

Design constraints (from ``docs/prompts/v1.9-orchestration/phase-3-learn-mode-sources.md``):

  1. **Additive only.** This module is a new file. The v1.3 advisory bias
     surface (``_consult_learn_mode_bias`` / ``_emit_learn_mode_bias_applied`` /
     ``bias_consult`` timing key / ``bias_hint`` HITL column) is NOT
     touched. P3 only extends the WRITE side of Learn Mode (ingest +
     label tagging + new nullable ``hitl_overrides.source_label`` column).

  2. **Self-monitor guard is non-negotiable** (memory:
     ``feedback_no_self_monitor.md``). Any resolved path that overlaps
     with SM's own session JSONL or contains a ``stream_manager`` path
     segment is REJECTED with a WARNING-level log. The guard never
     raises — other sources in the same config remain unaffected. The
     guard runs at every glob expansion, not just at config load time
     (files may appear later).

  3. **Source isolation.** Each configured source is tail-watched on its
     own thread with an independent envelope queue. The categoriser
     processes one turn at a time regardless of source; ``source_label``
     is metadata-only and never routes/biases categorisation differently.

  4. **No new bus envelopes.** Source turns are emitted as the existing
     ``desktop_prompt`` / ``user_reply`` envelope types, with the new
     ``source_label`` field added to ``metadata``. No new envelope type
     name is introduced (verified by absence of ``"learn_source"`` in
     this module's envelope ``type=`` arguments).

The ``hitl_overrides`` WAL table gains a nullable ``source_label`` column
via :func:`ensure_source_label_column`. The migration is idempotent —
safe to run on a fresh DB *and* on an existing DB with rows. Existing
rows are not touched (``source_label`` is NULL for all of them).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

from stream_manager import message_bus as _msg_bus

if TYPE_CHECKING:
    from stream_manager.message_bus import MessageBus

log = logging.getLogger(__name__)

# Env var carrying a JSON-encoded list of source dicts. Each dict must
# have ``path_glob`` (str) and ``label`` (str). Default: empty list.
LEARN_SOURCES_ENV: str = "BRIDGE_LEARN_SOURCES"

# Tail polling interval. Mirrors ``jsonl_tail.POLL_INTERVAL_S`` (0.5 s)
# so the seam behaviour is consistent across the existing Desktop tailer
# and the new external-source tailer.
POLL_INTERVAL_S: float = 0.5

# Path-segment guard sentinel — any resolved path whose ``parts`` contain
# this segment is treated as SM-internal and rejected. Compared against
# the case-folded path components.
_SELF_MONITOR_SEGMENT: str = "stream_manager"


# ── Config ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SourceConfig:
    """One external Learn Mode JSONL source.

    ``path_glob`` is resolved with :meth:`pathlib.Path.glob`. ``label``
    is the attribution tag attached as ``metadata.source_label`` on each
    emitted ``desktop_prompt`` / ``user_reply`` envelope.
    """

    path_glob: str
    label: str


def load_sources(env: dict[str, str] | None = None) -> list[SourceConfig]:
    """Parse the ``BRIDGE_LEARN_SOURCES`` env var into a list of configs.

    Default: empty list (Learn Mode source expansion is opt-in per
    source). When the env var is unset or empty, returns ``[]`` and the
    existing Desktop session ingest path runs as before — no extra
    threads are started.

    Malformed JSON or entries missing ``path_glob`` / ``label`` are
    logged at WARNING level and skipped. The function never raises on
    bad input — a misconfigured source must not break SM startup.
    """
    src_env = env if env is not None else os.environ
    raw = (src_env.get(LEARN_SOURCES_ENV) or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.warning(
            "learn_sources: malformed JSON in %s; treating as empty",
            LEARN_SOURCES_ENV,
        )
        return []
    if not isinstance(parsed, list):
        log.warning(
            "learn_sources: %s must decode to a list; got %s",
            LEARN_SOURCES_ENV,
            type(parsed).__name__,
        )
        return []
    out: list[SourceConfig] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            log.warning("learn_sources: skipping non-dict entry: %r", entry)
            continue
        path_glob = str(entry.get("path_glob", "") or "").strip()
        label = str(entry.get("label", "") or "").strip()
        if not path_glob or not label:
            log.warning(
                "learn_sources: skipping entry missing path_glob/label: %r",
                entry,
            )
            continue
        out.append(SourceConfig(path_glob=path_glob, label=label))
    return out


# ── Self-monitor guard ──────────────────────────────────────────────


def _sm_session_jsonl_path(sm_own_session_id: str | None = None) -> Path | None:
    """Return the canonical SM-internal session JSONL path, if known.

    Resolves to ``~/.claude/sessions/<SM-session-id>.jsonl``. Returns
    ``None`` when ``SM_OWN_SESSION_ID`` is unset (the no-self-monitor
    invariant degrades to the path-segment check only — see
    ``feedback_no_self_monitor.md``).
    """
    sm_id = (
        sm_own_session_id
        if sm_own_session_id is not None
        else os.environ.get("SM_OWN_SESSION_ID", "")
    ).strip()
    if not sm_id:
        return None
    home = Path.home()
    return home / ".claude" / "sessions" / f"{sm_id}.jsonl"


def is_self_monitor_path(
    path: Path,
    sm_own_session_id: str | None = None,
) -> bool:
    """Return True when ``path`` would trigger an eval feedback loop.

    Two checks (per ``feedback_no_self_monitor.md``):

      1. **Exact-path match** — does ``path`` resolve to the SM-internal
         session JSONL (``~/.claude/sessions/<SM-session-id>.jsonl``)?

      2. **Path-segment match** — does any component of ``path`` (after
         resolution) equal ``stream_manager``? This catches anything
         under SM's working tree, including session-watcher state files
         and project-cwd-style globs.

    The check operates on resolved paths so that symlinks / parent-dir
    relativity (``..``) cannot evade it. Comparison is case-insensitive
    on Windows (``Path.resolve`` normalises drive case but not segment
    case for non-existent intermediate segments, so we case-fold).
    """
    try:
        resolved = path.resolve(strict=False)
    except (OSError, RuntimeError):
        # Path resolution failed — refuse rather than silently allow.
        log.warning("learn_sources: path.resolve failed for %s; rejecting", path)
        return True

    # Exact-path match against SM's own session JSONL.
    sm_path = _sm_session_jsonl_path(sm_own_session_id)
    if sm_path is not None:
        try:
            if resolved == sm_path.resolve(strict=False):
                return True
        except (OSError, RuntimeError):
            pass

    # Path-segment match. Case-fold for cross-platform safety.
    for part in resolved.parts:
        if part.casefold() == _SELF_MONITOR_SEGMENT.casefold():
            return True
    return False


def _filter_self_monitor(
    candidates: Iterable[Path],
    sm_own_session_id: str | None = None,
) -> list[Path]:
    """Drop self-monitor paths from a glob expansion, with WARNING logs.

    Used at every glob expansion (not just at config load time) so a
    file appearing under a watched glob *after* config load is still
    rejected.
    """
    kept: list[Path] = []
    for cand in candidates:
        if is_self_monitor_path(cand, sm_own_session_id=sm_own_session_id):
            log.warning(
                "learn_sources: rejecting path %s — matches SM-internal "
                "session JSONL or contains 'stream_manager' segment; "
                "eval feedback loop prevention",
                cand,
            )
            continue
        kept.append(cand)
    return kept


# ── Migration ───────────────────────────────────────────────────────


def ensure_source_label_column(bus: MessageBus) -> None:
    """Idempotent additive migration: add ``hitl_overrides.source_label``.

    SQLite does not support ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS``
    natively, so we sniff the column list first. Safe to call on a fresh
    DB *and* on an existing DB with rows; existing rows remain unaffected
    (``source_label`` is NULL for all of them).
    """
    rows = bus.fetch_rows("SELECT name FROM pragma_table_info('hitl_overrides')")
    existing = {r[0] for r in rows}
    if "source_label" in existing:
        return
    # Nullable, no default — existing rows get NULL automatically.
    bus.execute_write(
        "ALTER TABLE hitl_overrides ADD COLUMN source_label TEXT"
    )


def record_override_with_source_label(
    bus: MessageBus,
    *,
    decision_id: str,
    original_action: str,
    override_action: str,
    note: str | None,
    mode: str,
    source_label: str | None,
) -> None:
    """Insert a ``hitl_overrides`` row carrying a ``source_label``.

    Helper for callers that have a tagged turn's ``source_label`` (from
    a Learn Mode external source) and want to attribute the override.
    Desktop session turns must call ``MessageBus.annotate_decision``
    directly so ``source_label`` stays NULL — preserves the v1.3 invariant
    that Desktop turns are unlabelled.

    The migration is performed lazily here so callers don't need to
    remember to run it before the first insert.
    """
    ensure_source_label_column(bus)
    import datetime as _dt
    ts = _dt.datetime.now(_dt.UTC).isoformat()
    bus.execute_write(
        "INSERT INTO hitl_overrides (decision_id, original_action, "
        "override_action, note, mode, timestamp, source_label) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            decision_id,
            original_action,
            override_action,
            note,
            mode,
            ts,
            source_label,
        ),
    )


# ── Source ingest worker ────────────────────────────────────────────


@dataclass
class _PerSourceState:
    """Per-source mutable state kept off the manager's hot path."""

    source: SourceConfig
    open_path: Path | None = None
    fh: object | None = None  # File handle (or None when no file open).
    uuid_to_pair: dict[tuple[str, str], str] = field(default_factory=dict)


class LearnSourceWorker:
    """Tail-watch one external JSONL source and emit labelled turns.

    Mirrors :class:`stream_manager.jsonl_tail.JsonlTailWorker` for the
    Learn Mode envelope shape (``desktop_prompt`` / ``user_reply`` paired
    via ``parentUuid``), but:

      * the *path source* is a glob, not a project-slug directory;
      * each emitted envelope carries ``metadata.source_label = <label>``;
      * the self-monitor guard runs at every glob expansion.

    The worker is non-blocking (FR-AR-7): exceptions from JSON parsing,
    file IO, or downstream callbacks are logged and swallowed so a stuck
    JSONL never blocks SM.
    """

    _PAIR_CACHE_MAX = 2048

    def __init__(
        self,
        source: SourceConfig,
        bus: MessageBus,
        *,
        sm_session_id: str = "",
        sm_own_session_id: str | None = None,
        poll_interval_s: float = POLL_INTERVAL_S,
    ) -> None:
        self._source = source
        self._bus = bus
        # The SM-side session id under which the emitted envelopes are
        # filed — same convention as ``JsonlTailWorker._session_id``.
        # Defaults to the source label so envelopes from different
        # sources are queryable separately even when ``session_id`` is
        # the only available filter.
        self._sm_session_id = sm_session_id or f"learn-source:{source.label}"
        self._sm_own_session_id = sm_own_session_id
        self._poll_interval_s = poll_interval_s
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._state = _PerSourceState(source=source)

    @property
    def source(self) -> SourceConfig:
        return self._source

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            log.warning(
                "LearnSourceWorker(%s) already running; ignoring start()",
                self._source.label,
            )
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"learn-source-{self._source.label}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None
        fh = self._state.fh
        if fh is not None:
            with contextlib.suppress(Exception):
                fh.close()  # type: ignore[union-attr]
            self._state.fh = None

    # ── glob + tail ────────────────────────────────────────────────

    def expand_glob(self) -> list[Path]:
        """Resolve the configured ``path_glob`` and apply the guard.

        Public so the manager / tests can drive a single expansion
        without spinning up the tail thread.
        """
        glob_str = self._source.path_glob
        # Split into base + pattern. ``Path.glob`` requires a base dir.
        # We walk parts left-to-right and collect everything before the
        # first segment containing a glob metachar as the base; the
        # remainder is the pattern. Accept both absolute globs
        # (e.g. ``/abs/dir/*.jsonl``) and relative globs (resolved
        # against the cwd).
        candidates = self._glob_candidates(glob_str)
        return _filter_self_monitor(
            candidates, sm_own_session_id=self._sm_own_session_id
        )

    @staticmethod
    def _glob_candidates(glob_str: str) -> list[Path]:
        """Split ``glob_str`` into (base_dir, pattern) and run ``glob``.

        Walks the parts left-to-right; the base is the longest leading
        prefix of parts containing no glob metachar (``*``, ``?``, or
        ``[``). The remainder is the pattern. When the entire string has
        no metachars, it's treated as a single file path.
        """
        p = Path(glob_str)
        parts = p.parts
        meta = ("*", "?", "[")
        split_at: int | None = None
        for idx, part in enumerate(parts):
            if any(ch in part for ch in meta):
                split_at = idx
                break
        if split_at is None:
            # No glob chars — treat as a single explicit path.
            try:
                if p.is_file():
                    return [p]
            except OSError:
                log.exception(
                    "learn_sources: stat failed for %s", glob_str
                )
            return []
        base_parts = parts[:split_at]
        pattern_parts = parts[split_at:]
        if not base_parts:
            # Pure relative glob like ``*.jsonl``.
            base = Path(".")
        else:
            base = Path(*base_parts)
        pattern = "/".join(pattern_parts) if pattern_parts else ""
        if not pattern:
            return []
        try:
            return [c for c in base.glob(pattern) if c.is_file()]
        except OSError:
            log.exception(
                "learn_sources: glob failed for %s", glob_str
            )
            return []

    def _newest_path(self) -> Path | None:
        candidates = self.expand_glob()
        if not candidates:
            return None
        return max(candidates, key=lambda c: c.stat().st_mtime)

    def _run(self) -> None:
        path: Path | None = None
        fh = None
        try:
            while not self._stop_event.is_set():
                newest = self._newest_path()
                if newest is None:
                    if self._stop_event.wait(self._poll_interval_s):
                        break
                    continue
                if newest != path:
                    if fh is not None:
                        with contextlib.suppress(OSError):
                            fh.close()
                    path = newest
                    self._state.open_path = path
                    try:
                        fh = path.open(
                            "r", encoding="utf-8", errors="replace"
                        )
                        fh.seek(0, 2)  # tail: skip existing content
                    except OSError:
                        log.exception(
                            "learn_sources: open failed for %s", path
                        )
                        fh = None
                        if self._stop_event.wait(self._poll_interval_s):
                            break
                        continue
                    self._state.fh = fh
                if fh is None:
                    if self._stop_event.wait(self._poll_interval_s):
                        break
                    continue
                line = fh.readline()
                if not line:
                    if self._stop_event.wait(self._poll_interval_s):
                        break
                    continue
                self.process_line(line)
        finally:
            if fh is not None:
                with contextlib.suppress(OSError):
                    fh.close()

    # ── per-line ingest ─────────────────────────────────────────────

    def process_line(self, line: str) -> None:
        """Parse one JSONL line and emit labelled envelopes.

        Public so tests can drive the worker without spawning a thread.
        Mirrors ``JsonlTailWorker._process_line`` for the Learn Mode
        path; non-Learn-Mode emit paths (agent_identified, desktop_pause)
        are intentionally NOT replayed here — those are the v1.3 Desktop
        tailer's responsibility, not the external-source tailer's.
        """
        line = (line or "").strip()
        if not line:
            return
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            log.debug("learn_sources(%s): bad JSON line; skipping",
                      self._source.label)
            return
        if not isinstance(record, dict):
            return
        session_id_jsonl = str(record.get("sessionId", "") or "")
        try:
            self._maybe_emit(record, session_id_jsonl)
        except Exception:
            log.exception(
                "learn_sources(%s): emit failed",
                self._source.label,
            )

    @staticmethod
    def _extract_text(message: object) -> str:
        """Same shape as ``JsonlTailWorker._extract_text``.

        Desktop-style transcripts emit ``message.content`` either as a
        plain string or a list of typed parts. Learn Mode only ingests
        chat text — tool-use / tool-result parts are skipped.
        """
        if not isinstance(message, dict):
            return ""
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    txt = item.get("text", "")
                    if isinstance(txt, str) and txt:
                        parts.append(txt)
            return "\n".join(parts)
        return ""

    def _remember_pair(
        self, session_id_jsonl: str, uuid: str, pair_id: str
    ) -> None:
        if not uuid or not pair_id:
            return
        key = (session_id_jsonl, uuid)
        cache = self._state.uuid_to_pair
        if len(cache) >= self._PAIR_CACHE_MAX:
            drop = max(1, self._PAIR_CACHE_MAX // 10)
            for k in list(cache.keys())[:drop]:
                cache.pop(k, None)
        cache[key] = pair_id

    def _maybe_emit(self, record: dict, session_id_jsonl: str) -> None:
        record_type = str(record.get("type", "") or "")
        if record_type not in ("assistant", "user"):
            return
        message = record.get("message")
        text = self._extract_text(message)
        if not text:
            return
        uuid = str(record.get("uuid", "") or "")
        parent_uuid = str(record.get("parentUuid", "") or "")
        ts = time.time()
        if record_type == "assistant":
            envelope = _msg_bus.Message.new(
                session_id=self._sm_session_id,
                type="desktop_prompt",
                direction="inbound",
                content=text,
                metadata={
                    "desktop_session_id": session_id_jsonl,
                    "uuid": uuid,
                    "parent_uuid": parent_uuid,
                    "ts": ts,
                    # P3 — attribution tag for the categoriser and the
                    # ``hitl_overrides`` write helper. Carried as plain
                    # metadata; the categoriser is unchanged.
                    "source_label": self._source.label,
                },
            )
            try:
                self._bus.publish(envelope)
            except Exception:
                log.exception(
                    "learn_sources(%s): bus.publish(desktop_prompt) failed",
                    self._source.label,
                )
                return
            self._remember_pair(session_id_jsonl, uuid, envelope.id)
            return
        # record_type == "user"
        pair_id = self._state.uuid_to_pair.get((session_id_jsonl, parent_uuid))
        metadata: dict[str, object] = {
            "desktop_session_id": session_id_jsonl,
            "uuid": uuid,
            "parent_uuid": parent_uuid,
            "ts": ts,
            "source_label": self._source.label,
        }
        if pair_id:
            metadata["pair_id"] = pair_id
        envelope = _msg_bus.Message.new(
            session_id=self._sm_session_id,
            type="user_reply",
            direction="inbound",
            content=text,
            metadata=metadata,
        )
        try:
            self._bus.publish(envelope)
        except Exception:
            log.exception(
                "learn_sources(%s): bus.publish(user_reply) failed",
                self._source.label,
            )


# ── Manager ────────────────────────────────────────────────────────


class LearnSourceManager:
    """Owns N :class:`LearnSourceWorker` — one per configured source.

    Empty config (default) → no workers spun up; the existing v1.3
    Desktop session ingest path runs as before.

    Sources whose ``path_glob`` resolves *only* to self-monitor paths
    are kept registered (so a non-self-monitor file appearing later
    under the same glob still gets ingested) but their initial expansion
    yields zero candidates after the guard runs.
    """

    def __init__(
        self,
        bus: MessageBus,
        sources: list[SourceConfig] | None = None,
        *,
        sm_session_id: str = "",
        sm_own_session_id: str | None = None,
        poll_interval_s: float = POLL_INTERVAL_S,
    ) -> None:
        self._bus = bus
        self._sources = list(sources) if sources is not None else []
        self._sm_session_id = sm_session_id
        self._sm_own_session_id = sm_own_session_id
        self._poll_interval_s = poll_interval_s
        self._workers: list[LearnSourceWorker] = []

    @property
    def sources(self) -> list[SourceConfig]:
        return list(self._sources)

    @property
    def workers(self) -> list[LearnSourceWorker]:
        return list(self._workers)

    def start(self) -> None:
        """Start one tail worker per configured source.

        No-op when ``self._sources`` is empty — preserves the
        ``test_empty_sources_default_unchanged`` invariant: no extra
        threads are spun up when Learn Mode source expansion is off.

        Also runs the idempotent ``hitl_overrides.source_label`` column
        migration so the column exists even if no source ever fires.
        """
        ensure_source_label_column(self._bus)
        if not self._sources:
            return
        for src in self._sources:
            worker = LearnSourceWorker(
                src,
                self._bus,
                sm_session_id=self._sm_session_id,
                sm_own_session_id=self._sm_own_session_id,
                poll_interval_s=self._poll_interval_s,
            )
            worker.start()
            self._workers.append(worker)

    def stop(self) -> None:
        for w in self._workers:
            with contextlib.suppress(Exception):
                w.stop()
        self._workers.clear()


def from_environment(
    bus: MessageBus,
    *,
    sm_session_id: str = "",
    sm_own_session_id: str | None = None,
    env: dict[str, str] | None = None,
) -> LearnSourceManager:
    """Build a :class:`LearnSourceManager` from ``BRIDGE_LEARN_SOURCES``.

    Convenience wrapper for the host process boot path.
    """
    sources = load_sources(env=env)
    return LearnSourceManager(
        bus,
        sources=sources,
        sm_session_id=sm_session_id,
        sm_own_session_id=sm_own_session_id,
    )
