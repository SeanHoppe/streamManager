"""v1.3 P5c — Learn Mode Sonnet categorizer worker.

Out-of-band worker that drains paired Desktop dialogue turns from the
``messages`` table (emitted by P5b's ``jsonl_tail.py`` extension as
``desktop_prompt`` + ``user_reply`` rows) and produces categorized rows
in the new ``learn_patterns`` table.

Design constraints (locked by ``docs/learn-mode-design.md`` §2.4 and the
P5c orchestration prompt):

  1. **Off the verdict hot path.** The worker runs on its own background
     thread. The governance verdict path never invokes this categorizer
     synchronously — it only ever READS from ``learn_patterns`` (P5d).
     ADR-5 latency budgets (NFR-P2) are unaffected.

  2. **CLI subprocess backend, not the Anthropic SDK.** Per memory note
     ``feedback_cli_over_sdk.md``: invoke ``claude -p ... --model sonnet``
     to extract a category. Mirror the subprocess pattern from
     ``cli_governance.py`` so we share envelope parsing (markdown-fence
     stripping, ``{"type":"result", "result": ...}`` shape).

  3. **Dedicated subprocess.** The categorizer does NOT borrow the
     verdict ``CliPool`` (Task J). A pool worker stuck on a categorizer
     round-trip would starve the verdict path. The categorizer spawns
     its own short-lived ``subprocess.run`` per pair.

  4. **Lifecycle as consumer of EngineRegistry.** ``EngineRegistry``
     itself is not modified. The categorizer is started/stopped by the
     same lifecycle owner that calls ``start_refresh()`` /
     ``stop_refresh()`` on the registry — typically the host process
     (uvicorn boot in production, the test fixture in pytest).

  5. **Pair lookup uses metadata.pair_id.** P5b sets
     ``user_reply.metadata.pair_id`` to the envelope id of the preceding
     ``desktop_prompt``. We pull pairs in lockstep using that link.

  6. **Idempotent.** A ``(prompt_hash, last_reinforced_ts)`` pair could
     repeat across ticks if a `user_reply` row is processed twice. We
     keep ledger state on the consumer side (highest message ``id``
     seen) so each pair is categorized at most once per worker lifetime.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from stream_manager.message_bus import MessageBus

log = logging.getLogger(__name__)

# Sonnet is the categorization model per design spec §2.4.
DEFAULT_MODEL = "claude-sonnet-4-5"
CLI_BIN = "claude"
TIMEOUT_SECONDS = 30.0
DEFAULT_POLL_INTERVAL_S = 5.0

_VALID_CATEGORIES = frozenset(
    {
        "approve",
        "reject",
        "redirect",
        "clarify",
        "acknowledge",
        "unknown",
    }
)

_CATEGORIZER_SYSTEM = (
    "You are a dialogue categorizer for streamManager Learn Mode. Given "
    "a Desktop assistant prompt and the operator's reply, classify the "
    "operator's reply intent into ONE of: approve, reject, redirect, "
    "clarify, acknowledge, unknown.\n\n"
    "Reply with a JSON object only — no prose, no markdown fences:\n"
    "{\"category\": \"<one-of-above>\", \"confidence\": <0.0-1.0>, "
    "\"reasoning\": \"<short>\"}\n"
)


@dataclass(frozen=True)
class CategoryResult:
    category: str
    confidence: float
    reasoning: str


def _normalize_prompt(text: str) -> str:
    """Normalize a desktop_prompt for stable hashing.

    Whitespace-collapsed, lowercased. P5d uses this for similarity
    lookup, so the hash MUST be deterministic across runs.
    """
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip().lower())


def prompt_hash(text: str) -> str:
    """Stable 16-hex-char hash of the normalized desktop_prompt text."""
    norm = _normalize_prompt(text)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def _strip_fence(s: str) -> str:
    s = s.strip()
    m = re.match(r"^```(?:json)?\s*\n", s)
    if m:
        s = s[m.end():]
        if s.endswith("```"):
            s = s[:-3].rstrip()
    return s


def _parse_inner_json(text: str) -> dict | None:
    """Parse a JSON object from the inner result text. Tolerant of fences
    and trailing prose — same idiom as cli_governance._extract_json_object.
    """
    s = _strip_fence(text)
    decoder = json.JSONDecoder()
    try:
        obj, _ = decoder.raw_decode(s)
    except json.JSONDecodeError:
        for idx in range(len(s)):
            if s[idx] != "{":
                continue
            try:
                obj, _ = decoder.raw_decode(s[idx:])
                break
            except json.JSONDecodeError:
                continue
        else:
            return None
    return obj if isinstance(obj, dict) else None


def _parse_envelope(stdout: str) -> CategoryResult | None:
    """Parse a ``claude -p --output-format json`` envelope into a CategoryResult.

    Mirrors cli_governance._parse_envelope's tolerance: outer envelope is
    a JSON object with ``result`` either a dict or a JSON string. Any
    parse failure or category-enum mismatch returns None — the caller
    treats None as a degraded categorization and logs but does not crash.
    """
    try:
        envelope = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(envelope, dict):
        return None
    if envelope.get("is_error"):
        return None
    inner = envelope.get("result")
    data: dict | None
    if isinstance(inner, dict):
        data = inner
    elif isinstance(inner, str) and inner:
        data = _parse_inner_json(inner)
    else:
        return None
    if not data:
        return None
    cat = data.get("category")
    if not isinstance(cat, str) or cat.lower() not in _VALID_CATEGORIES:
        return None
    try:
        conf = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    reasoning = str(data.get("reasoning", ""))[:500]
    return CategoryResult(category=cat.lower(), confidence=conf, reasoning=reasoning)


def categorize_pair(
    desktop_prompt_text: str,
    user_reply_text: str,
    *,
    model: str = DEFAULT_MODEL,
    runner: Callable | None = None,
    timeout: float = TIMEOUT_SECONDS,
) -> CategoryResult | None:
    """Invoke the Sonnet CLI to categorize one (prompt, reply) pair.

    Mirrors the cli_governance subprocess pattern: ``claude -p`` with
    ``--system-prompt``, ``--output-format json``, ``--model``,
    ``--no-session-persistence``, ``--tools ""``. Returns None on any
    failure (CLI missing, timeout, malformed JSON, enum mismatch).

    A test injectable ``runner`` may replace ``subprocess.run`` so unit
    tests can simulate Sonnet latency/output without spawning processes.
    """
    run = runner or subprocess.run
    user_prompt = (
        "Desktop prompt:\n"
        f"{desktop_prompt_text[:4000]}\n\n"
        "Operator reply:\n"
        f"{user_reply_text[:2000]}"
    )
    cmd = [
        CLI_BIN, "-p", user_prompt,
        "--system-prompt", _CATEGORIZER_SYSTEM,
        "--output-format", "json",
        "--model", model,
        "--no-session-persistence",
        "--tools", "",
    ]
    try:
        result = run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        log.warning("learn_categorizer: `%s` CLI not on PATH; degrading", CLI_BIN)
        return None
    except subprocess.TimeoutExpired:
        log.warning(
            "learn_categorizer: subprocess timeout (>%.1fs); degrading", timeout
        )
        return None
    if getattr(result, "returncode", 0) != 0:
        log.warning(
            "learn_categorizer: non-zero exit %d; degrading",
            getattr(result, "returncode", -1),
        )
        return None
    return _parse_envelope(getattr(result, "stdout", "") or "")


class LearnCategorizerWorker:
    """Background worker that drains pairs and writes ``learn_patterns`` rows.

    Lifecycle: ``start()`` spawns a daemon thread that polls the bus
    every ``poll_interval_s`` seconds for new ``user_reply`` rows whose
    ``metadata.pair_id`` resolves to a ``desktop_prompt``. Each pair is
    categorized via ``categorize_pair`` and the result written to the
    ``learn_patterns`` table.

    ``stop()`` signals the loop to exit and joins the thread. Idempotent.

    The worker maintains ``_last_id_seen`` so each pair is categorized at
    most once per process lifetime.

    Off-hot-path guarantee: this worker NEVER calls into the verdict
    path (``CliGovernor.evaluate``, ``CliPool.acquire``, or
    ``GovernanceEngine`` directly). It uses its own
    ``categorize_pair`` subprocess. The verdict path is free to run
    concurrently — verified by ``test_learn_categorizer.py``'s latency
    test.
    """

    def __init__(
        self,
        bus: "MessageBus",
        *,
        model: str = DEFAULT_MODEL,
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
        runner: Callable | None = None,
        timeout: float = TIMEOUT_SECONDS,
    ) -> None:
        self._bus = bus
        self._model = model
        self._poll = float(poll_interval_s)
        self._runner = runner
        self._timeout = float(timeout)
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_id_seen = 0
        self._lock = threading.Lock()

    # ── lifecycle ───────────────────────────────────────────────────

    def start(self) -> None:
        """Begin the polling loop on a daemon thread. Idempotent."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_evt.clear()
            t = threading.Thread(
                target=self._run,
                name="learn-categorizer",
                daemon=True,
            )
            self._thread = t
            t.start()

    def stop(self, join_timeout: float = 2.0) -> None:
        """Signal the worker to exit and join. Idempotent."""
        with self._lock:
            self._stop_evt.set()
            t = self._thread
            self._thread = None
        if t is not None:
            try:
                t.join(timeout=join_timeout)
            except Exception:
                log.exception("learn_categorizer: join failed")

    @property
    def running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    # ── core loop ───────────────────────────────────────────────────

    def _run(self) -> None:
        """Polling loop body. Exits when ``_stop_evt`` is set."""
        while not self._stop_evt.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("learn_categorizer: tick failed")
            # Wait with early-exit on stop.
            if self._stop_evt.wait(timeout=self._poll):
                return

    def tick(self) -> int:
        """Run one drain pass. Returns the number of pairs categorized.

        Public so tests can drive the worker synchronously (without
        relying on the polling thread). The thread loop simply calls
        ``tick`` on every interval.
        """
        pairs = self._fetch_new_pairs()
        if not pairs:
            return 0
        n = 0
        for last_id, prompt_text, reply_text in pairs:
            try:
                self._categorize_and_record(prompt_text, reply_text)
                n += 1
            except Exception:
                log.exception("learn_categorizer: pair categorization failed")
            # Always advance the ledger — a permanent CLI failure on a
            # given pair must not block the worker from making progress.
            self._last_id_seen = max(self._last_id_seen, last_id)
        return n

    # ── DB helpers ──────────────────────────────────────────────────

    def _fetch_new_pairs(self) -> list[tuple[int, str, str]]:
        """Pull new (rowid, desktop_prompt_text, user_reply_text) tuples.

        Uses ``MessageBus.fetch_rows`` (read-only helper) to avoid
        reaching into the bus connection. Pairs are resolved by joining
        the ``user_reply`` row to its preceding ``desktop_prompt`` via
        ``user_reply.metadata.pair_id`` (a JSON-extracted field).
        """
        # SQLite's json_extract is available in stdlib sqlite3 ≥ 3.38; on
        # older builds the join silently returns no rows. We use ROWID
        # for the ledger so the ordering is monotonic regardless of
        # session_id mix.
        rows = self._bus.fetch_rows(
            "SELECT u.rowid, d.content, u.content "
            "FROM messages u "
            "JOIN messages d ON d.id = json_extract(u.metadata, '$.pair_id') "
            "WHERE u.type='user_reply' AND d.type='desktop_prompt' "
            "AND u.rowid > ? "
            "ORDER BY u.rowid ASC",
            (self._last_id_seen,),
        )
        return [(int(r[0]), str(r[1] or ""), str(r[2] or "")) for r in rows]

    def _categorize_and_record(
        self, desktop_prompt_text: str, user_reply_text: str
    ) -> None:
        """Run categorize_pair and write a ``learn_patterns`` row.

        On categorizer failure (None result) we still record a low-
        confidence ``unknown`` row so downstream P5d can see "we tried."
        The decay scheduler (P5e) will let it age out if no
        reinforcement arrives.
        """
        result = categorize_pair(
            desktop_prompt_text,
            user_reply_text,
            model=self._model,
            runner=self._runner,
            timeout=self._timeout,
        )
        h = prompt_hash(desktop_prompt_text)
        now = time.time()
        if result is None:
            category = "unknown"
            confidence = 0.0
        else:
            category = result.category
            confidence = max(0.0, min(1.0, result.confidence))
        self._insert_pattern_row(
            prompt_hash_val=h,
            category=category,
            confidence=confidence,
            now_ts=now,
        )

    def _insert_pattern_row(
        self,
        *,
        prompt_hash_val: str,
        category: str,
        confidence: float,
        now_ts: float,
    ) -> None:
        """INSERT one row into ``learn_patterns``.

        We reach into the bus connection through the public
        ``_conn``/``_lock`` pair the rest of the codebase already uses
        (e.g. ``MessageBus.publish``). The categorizer never participates
        in HITL or governance state, so a dedicated DML helper on the
        bus would be over-engineered; a single INSERT under the bus
        lock matches the codebase's "small write under bus lock" idiom.
        """
        bus = self._bus
        # Use the bus lock so writes serialize cleanly with publish().
        with bus._lock:  # noqa: SLF001 — internal lock per codebase idiom
            bus._conn.execute(
                "INSERT INTO learn_patterns "
                "(prompt_hash, category, confidence, ladder_step, "
                " last_reinforced_ts, contradicted_count, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    prompt_hash_val,
                    category,
                    float(confidence),
                    0,
                    float(now_ts),
                    0,
                    float(now_ts),
                ),
            )


def is_enabled() -> bool:
    """Optional environment gate.

    The categorizer worker is opt-in via ``SM_LEARN_MODE=1`` so existing
    deployments don't suddenly start spawning Sonnet subprocesses on
    every Desktop dialogue turn. The host that owns the EngineRegistry
    lifecycle should check this flag before calling ``start()``.
    """
    return os.environ.get("SM_LEARN_MODE", "").lower() in ("1", "true", "yes")
