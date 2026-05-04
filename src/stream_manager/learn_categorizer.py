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
    # Truncated to 16 hex chars (64 bits); birthday collision at ~2^32 patterns. Acceptable for v1.3 cardinality.
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def _strip_fence(s: str) -> str:
    s = s.strip()
    # The optional newline lets us strip both
    #   ```json\n{...}\n```
    # and the single-line variant
    #   ```json{...}```
    m = re.match(r"^```(?:json)?\s*", s)
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
    prompt_len = len(desktop_prompt_text or "")
    reply_len = len(user_reply_text or "")
    if prompt_len > 4000 or reply_len > 2000:
        log.warning(
            "learn_categorizer: input truncated (prompt=%d→4000, reply=%d→2000)",
            prompt_len,
            reply_len,
        )
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

    # Maximum consecutive failures on a single pair before we give up
    # and advance the ledger past it. Keeps a poison record from
    # permanently stalling the worker (Fix B).
    _POISON_RETRY_BUDGET = 3

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
        # Per-rowid retry ledger for poison-record detection (Fix B).
        self._retry_counts: dict[int, int] = {}
        self._lock = threading.Lock()
        self._stopping = False
        # Hot-path read of the in-memory ledger; the durable mirror in
        # learn_categorizer_state is loaded lazily on start() (Fix A).
        self._last_id_seen = self._load_last_id_seen()

    # ── lifecycle ───────────────────────────────────────────────────

    def start(self) -> None:
        """Begin the polling loop on a daemon thread. Idempotent.

        Fix D: gates on ``is_enabled()``. When ``SM_LEARN_MODE`` is
        unset the worker logs once and returns without spawning a
        thread. Caller-side checks remain valid as belt-and-suspenders.
        """
        if not is_enabled():
            log.info(
                "learn_categorizer: SM_LEARN_MODE not set; worker not starting"
            )
            return
        with self._lock:
            if self._stopping:
                # A stop() is in flight; do not race a new thread on top
                # of an unjoined predecessor (Fix C).
                return
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_evt.clear()
            # Refresh ledger from durable mirror in case a previous
            # process advanced it after our __init__ snapshot.
            self._last_id_seen = self._load_last_id_seen()
            t = threading.Thread(
                target=self._run,
                name="learn-categorizer",
                daemon=True,
            )
            self._thread = t
            t.start()

    def stop(self, join_timeout: float = 2.0) -> None:
        """Signal the worker to exit and join. Idempotent.

        Fix C: sets a ``_stopping`` flag under the lock so a concurrent
        ``start()`` cannot spawn a second thread on top of the
        not-yet-joined predecessor. Joins outside the lock to avoid
        blocking concurrent ``running`` checks.
        """
        with self._lock:
            if self._stopping:
                t = self._thread
            else:
                self._stopping = True
                self._stop_evt.set()
                t = self._thread
        if t is not None:
            try:
                t.join(timeout=join_timeout)
            except Exception:
                log.exception("learn_categorizer: join failed")
        with self._lock:
            self._thread = None
            self._stopping = False

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

        Fix B semantics: an exception during ``_categorize_and_record``
        does NOT advance the ledger for that pair — we stop draining
        for this tick and retry on the next one. After
        ``_POISON_RETRY_BUDGET`` consecutive failures on the same row
        we log a warning and skip past it so a poison record cannot
        permanently stall progress.
        """
        pairs = self._fetch_new_pairs()
        if not pairs:
            return 0
        n = 0
        for last_id, prompt_text, reply_text in pairs:
            try:
                self._categorize_and_record(prompt_text, reply_text)
            except Exception:
                count = self._retry_counts.get(last_id, 0) + 1
                self._retry_counts[last_id] = count
                if count >= self._POISON_RETRY_BUDGET:
                    log.warning(
                        "learn_categorizer: poison-skip rowid=%d after %d "
                        "failures; advancing ledger",
                        last_id,
                        count,
                    )
                    self._retry_counts.pop(last_id, None)
                    self._advance_ledger(last_id)
                    # Do NOT count as success.
                    continue
                log.exception(
                    "learn_categorizer: pair categorization failed (rowid=%d, attempt=%d)",
                    last_id,
                    count,
                )
                # Bail out of this tick without advancing — the same
                # pair is retried on the next poll interval.
                return n
            else:
                n += 1
                self._retry_counts.pop(last_id, None)
                self._advance_ledger(last_id)
        return n

    # ── ledger persistence (Fix A) ──────────────────────────────────

    def _load_last_id_seen(self) -> int:
        """Load durable ``last_id_seen`` from ``learn_categorizer_state``.

        Returns 0 if no row exists or the value is malformed. The
        in-memory ``self._last_id_seen`` mirrors this for hot-path
        reads; ``_advance_ledger`` keeps the two in sync.
        """
        try:
            rows = self._bus.fetch_rows(
                "SELECT value FROM learn_categorizer_state WHERE key=?",
                ("last_id_seen",),
            )
        except Exception:
            log.exception("learn_categorizer: failed to load ledger; defaulting to 0")
            return 0
        if not rows:
            return 0
        try:
            return int(rows[0][0])
        except (TypeError, ValueError):
            return 0

    def _advance_ledger(self, new_id: int) -> None:
        """Advance ``_last_id_seen`` and persist to the durable mirror."""
        if new_id <= self._last_id_seen:
            return
        self._last_id_seen = new_id
        try:
            self._bus.execute_write(
                "INSERT OR REPLACE INTO learn_categorizer_state(key, value) "
                "VALUES ('last_id_seen', ?)",
                (str(new_id),),
            )
        except Exception:
            # Persistence failure is non-fatal: the in-memory ledger
            # still advances for this process. Worst case is one
            # restart re-categorizes the most recent pair.
            log.exception("learn_categorizer: failed to persist ledger")

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

        Append-only by design; P5e (decay/reinforcement) is responsible
        for consolidation. Multiple rows per ``prompt_hash`` are
        expected within and across process lifetimes — the table
        deliberately has no UNIQUE constraint on ``prompt_hash``.

        Uses the symmetric ``bus.execute_write`` helper (Fix H) so we
        do not reach into private bus state.
        """
        self._bus.execute_write(
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


# ── v1.3 P5d: advisory bias hookup ──────────────────────────────────
#
# Read-only consumer of ``learn_patterns``. The verdict path consults
# ``bias_for(prompt)`` at decision time to optionally pre-fill the HITL
# prompt with a suggested action. The bias is ADVISORY only:
#
#   * It NEVER auto-allows a request.
#   * It NEVER short-circuits the HITL gate — even at confidence=1.0,
#     the operator still sees and confirms the HITL prompt.
#   * INTENT.md §"Safety priorities" ALWAYS WIN. Destructive shell,
#     force-push to protected branches, eval/exec injection, and
#     credential exfiltration are short-circuited by the verdict path
#     BEFORE bias is consulted (and the bias-application site re-checks
#     the safety regexes belt-and-suspenders).
#
# Design (locked by ``docs/learn-mode-design.md`` §3.2 "Bias reader"):
#
#   * Lookup key: exact ``prompt_hash(prompt)`` match. Similarity-based
#     fuzzy matching is deferred to v1.4+.
#   * Ordering when multiple rows match: ``last_reinforced_ts DESC``,
#     then ``confidence DESC``. Decay (P5e) reinforces by bumping
#     ``last_reinforced_ts``, so freshest reinforcement wins; ties
#     break on confidence.
#   * ``MIN_BIAS_CONFIDENCE`` floor: rows with ``confidence`` below
#     this threshold do not produce a hint.
#   * Categories ``unknown`` / ``clarify`` / ``acknowledge`` / ``redirect``
#     are not actionable as ladder hints in v1.3 — bias is returned ONLY
#     for ``approve`` and ``reject``.

MIN_BIAS_CONFIDENCE = 0.6

# Categories that produce an actionable ladder hint in v1.3. Other
# categories (clarify / acknowledge / redirect / unknown) are recorded
# by the categorizer but do not bias the verdict.
_BIAS_ACTIONABLE_CATEGORIES = frozenset({"approve", "reject"})


@dataclass(frozen=True)
class BiasHint:
    """Advisory bias offered to the verdict path at decision time.

    The hint pre-fills the HITL prompt with a suggested action. The
    operator still confirms — bias never auto-allows, never short-
    circuits the gate.

    Attributes
    ----------
    category : str
        Categorizer-assigned category. v1.3 actionable values are
        ``"approve"`` and ``"reject"``.
    confidence : float
        Confidence in the category, 0.0-1.0. Always >= ``MIN_BIAS_CONFIDENCE``
        when this hint is returned.
    ladder_step_suggestion : int
        Suggested ladder rung (L1-L4) the pattern has earned via the
        decay/reinforcement scheduler. v1.3 uses the raw ``ladder_step``
        column from ``learn_patterns``; P5e populates it.
    pattern_id : int
        ``learn_patterns.id`` of the row that produced this hint. Used
        in the audit envelope so operators can trace back to the
        originating row.
    last_reinforced_ts : float
        Epoch seconds of the most recent reinforcement. Surfaced in the
        audit envelope to aid debugging stale-pattern issues.
    """

    category: str
    confidence: float
    ladder_step_suggestion: int
    pattern_id: int
    last_reinforced_ts: float


def bias_for(
    prompt: str,
    bus: "MessageBus",
    *,
    min_confidence: float = MIN_BIAS_CONFIDENCE,
) -> "BiasHint | None":
    """Look up an advisory bias hint for ``prompt`` in ``learn_patterns``.

    Returns the highest-priority matching row as a ``BiasHint``, or
    ``None`` when no actionable row exists. ``None`` outcomes:

      * No row matches the exact ``prompt_hash(prompt)``.
      * Best matching row has ``confidence < min_confidence``.
      * Best matching row's category is not in
        ``_BIAS_ACTIONABLE_CATEGORIES`` (``unknown``/``clarify``/
        ``acknowledge``/``redirect`` are silent — no hint).
      * Empty / falsy ``prompt``.
      * Bus read fails (logged; non-fatal).

    The lookup is read-only and goes through the public
    ``MessageBus.fetch_rows`` helper. The bus lock is held only for the
    SELECT — same envelope as every other governance read path.

    Parameters
    ----------
    prompt : str
        The message content the verdict path is about to evaluate. Same
        text passed to ``prompt_hash`` for stable lookup.
    bus : MessageBus
        Bus owning the ``learn_patterns`` table.
    min_confidence : float, optional
        Confidence floor; defaults to ``MIN_BIAS_CONFIDENCE`` (0.6).
        Exposed so tests can pin a different threshold.
    """
    if not prompt:
        return None
    h = prompt_hash(prompt)
    try:
        rows = bus.fetch_rows(
            "SELECT id, category, confidence, ladder_step, "
            "last_reinforced_ts "
            "FROM learn_patterns "
            "WHERE prompt_hash = ? "
            "ORDER BY last_reinforced_ts DESC, confidence DESC "
            "LIMIT 1",
            (h,),
        )
    except Exception:
        log.exception("learn_categorizer.bias_for: fetch_rows failed")
        return None
    if not rows:
        return None
    row = rows[0]
    try:
        pattern_id = int(row[0])
        category = str(row[1] or "")
        confidence = float(row[2] or 0.0)
        ladder_step = int(row[3] or 0)
        last_reinforced_ts = float(row[4] or 0.0)
    except (TypeError, ValueError):
        return None
    if category not in _BIAS_ACTIONABLE_CATEGORIES:
        return None
    if confidence < min_confidence:
        return None
    return BiasHint(
        category=category,
        confidence=confidence,
        ladder_step_suggestion=ladder_step,
        pattern_id=pattern_id,
        last_reinforced_ts=last_reinforced_ts,
    )
