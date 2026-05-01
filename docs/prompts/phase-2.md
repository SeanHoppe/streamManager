# Phase 2 — HITL Core Loop

**Sequence:** Third. Requires Phase 1 complete.
**Estimated time:** 2 sessions.
**FR refs:** FR-HITL §4.9, ADR-9.

**Dependency:** Phase 1 agent identity (`desktop_pause` event from `jsonl_tail.py`)
feeds into Trigger 3 of the HITL sync gate. Phase 1 must be complete first.

---

## Context

The governance engine has no human-in-the-loop mechanism. Every decision
is either acted on immediately (sync gate missing) or logged after the fact
(async annotation missing). The HITL spec in REQUIREMENTS.md §4.9 defines:

- **Sync mode:** hold the decision in `hitl_pending`, wait up to N seconds for
  human override before forwarding. Timeout → original decision proceeds.
- **Async mode:** forward immediately, emit `hitl_async_flagged` event, allow
  retroactive annotation via `hitl_overrides` table.
- **Feedback loop:** HITL override adjusts confidence for matching `matched_hash`
  on future encounters; free-text note injected as ≤50-token prefix.

Three triggers fire the sync gate:
1. `new_pattern` — `source == "default"` (no graph match found)
2. `low_confidence` — `confidence < session.hitl_floor` (default 0.60)
3. `desktop_pause` — message ends with `?` / contains "should I" / "please confirm"
   / OR `stopReason=end_turn` received from JSONL tail

---

## Deliverables

### New files

| File | Purpose |
|------|---------|
| `src/stream_manager/hitl.py` | `HitlQueue` class; sync/async routing; feedback loop |

### Modified files

| File | Changes |
|------|---------|
| `src/stream_manager/message_bus.py` | Add `hitl_pending` + `hitl_overrides` tables; `sessions` table gets `hitl_mode` + `hitl_floor` columns |
| `src/stream_manager/governance.py` | Wire `HitlQueue` into `evaluate()`; route through sync/async path |
| `dashboard/server.py` | Add `GET /api/hitl/pending`, `POST /api/hitl/resolve`, `POST /api/hitl/annotate` endpoints |

---

## Prompt

```
Implement Phase 2 of the StreamManager viable product roadmap.
Reference: REQUIREMENTS.md §4.9 FR-HITL, ADR-9.
Phase 1 (agent_registry.py, jsonl_tail.py) must already exist.

### 1. WAL schema additions

In message_bus.py _SCHEMA, add after existing tables:

    CREATE TABLE IF NOT EXISTS hitl_pending (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id TEXT NOT NULL REFERENCES messages(id),
        proposed_action TEXT NOT NULL,
        proposed_confidence REAL NOT NULL,
        trigger_reason TEXT NOT NULL,    -- "new_pattern" | "low_confidence" | "desktop_pause"
        queued_at TEXT NOT NULL,         -- ISO-8601 UTC
        resolved_at TEXT,                -- NULL until resolved
        resolution TEXT                  -- "approved" | "overridden:{ACTION}" | "timeout"
    );

    CREATE TABLE IF NOT EXISTS hitl_overrides (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        decision_id TEXT NOT NULL REFERENCES decisions(id),
        original_action TEXT NOT NULL,
        override_action TEXT NOT NULL,
        note TEXT,
        mode TEXT NOT NULL,              -- "sync" | "async"
        timestamp TEXT NOT NULL          -- ISO-8601 UTC
    );

Also add to sessions table (ALTER TABLE pattern — handle IF NOT EXISTS):
    hitl_mode TEXT NOT NULL DEFAULT 'async'    -- "sync" | "async"
    hitl_floor REAL NOT NULL DEFAULT 0.60

Add to MessageBus class:
    def queue_hitl(self, message_id: str, proposed_action: str,
                   proposed_confidence: float, trigger_reason: str) -> int
        Returns hitl_pending.id

    def resolve_hitl(self, pending_id: int, resolution: str) -> None
        Sets resolved_at + resolution on hitl_pending row

    def annotate_decision(self, decision_id: str, original_action: str,
                          override_action: str, note: str | None, mode: str) -> None
        Inserts into hitl_overrides

    def get_pending_hitl(self, session_id: str) -> list[dict]
        Returns unresolved hitl_pending rows for session

    def get_hitl_mode(self, session_id: str) -> tuple[str, float]
        Returns (hitl_mode, hitl_floor) from sessions row

    def set_hitl_mode(self, session_id: str, mode: str, floor: float) -> None

### 2. hitl.py

Create src/stream_manager/hitl.py with:

PAUSE_PATTERNS = re.compile(
    r"(\?$|should\s+i\b|please\s+confirm\b)", re.IGNORECASE
)

class TriggerReason(str, Enum):
    NEW_PATTERN   = "new_pattern"
    LOW_CONFIDENCE = "low_confidence"
    DESKTOP_PAUSE  = "desktop_pause"

class HitlQueue:
    def __init__(self, bus: MessageBus, timeout_seconds: float = 60.0):
        ...

    def classify_trigger(self, decision: GovDecision, message_content: str,
                          desktop_pause_active: bool) -> TriggerReason | None:
        # Returns trigger reason if HITL should fire, else None
        # new_pattern: decision.source == "default"
        # low_confidence: decision.confidence < floor (floor from session)
        # desktop_pause: PAUSE_PATTERNS.search(message_content) or desktop_pause_active

    def route(self, decision: GovDecision, message_id: str,
              message_content: str, session_id: str,
              desktop_pause_active: bool) -> GovDecision:
        # Returns (possibly overridden) GovDecision
        # If mode == "sync":
        #   queue in hitl_pending, block up to self.timeout_seconds
        #   poll hitl_pending.resolution every 0.5s
        #   on "approved" → return original decision
        #   on "overridden:{ACTION}" → return decision with action replaced
        #   on timeout → emit hitl_timeout bus event, return original decision
        # If mode == "async":
        #   emit hitl_async_flagged bus event
        #   return original decision unchanged

    def apply_feedback(self, decision_id: str, override_action: str,
                       note: str | None, mode: str) -> None:
        # Store override in hitl_overrides
        # If matched_hash exists on decision, update graph confidence:
        #   approved → +0.05 (cap 1.0)
        #   overridden → -0.10 (floor 0.0)
        # Store note text for future injection (cap N=5 per hash)

    def get_active_notes(self, matched_hash: str) -> list[str]:
        # Returns up to 5 most recent notes for hash; each ≤50 tokens

### 3. Wire HitlQueue into GovernanceEngine

Modify src/stream_manager/governance.py:

    @dataclass
    class GovernanceEngine:
        ...
        hitl: HitlQueue | None = None          # add
        _desktop_pause_active: bool = False     # add; set by jsonl_tail event

In evaluate() (outer method, after _evaluate_inner returns):
    if self.hitl is not None and bus_msg is not None:
        trigger = self.hitl.classify_trigger(decision, msg.content,
                                             self._desktop_pause_active)
        if trigger is not None:
            decision = self.hitl.route(decision, bus_msg.id, msg.content,
                                       self.session_id, self._desktop_pause_active)
        self._desktop_pause_active = False   # consume the pause signal

Add method:
    def signal_desktop_pause(self) -> None:
        self._desktop_pause_active = True

Also inject active HITL notes into CLI context when calling cli_governance:
    notes = self.hitl.get_active_notes(match.hash) if self.hitl and match else []
    # Prepend notes as ≤50-token context to CLI prompt (truncate to fit)

### 4. Dashboard API endpoints

In dashboard/server.py add:

    GET  /api/hitl/pending
         Query: ?session_id=...
         Returns: list of unresolved hitl_pending rows

    POST /api/hitl/resolve
         Body: {"pending_id": int, "resolution": str}
         resolution values: "approved" | "overridden:ALLOW" | "overridden:GUIDE" |
                            "overridden:INTERVENE" | "overridden:BLOCK"
         Writes to hitl_pending.resolution; HitlQueue.route() picks it up

    POST /api/hitl/annotate
         Body: {"decision_id": str, "override_action": str, "note": str | null}
         Calls hitl.apply_feedback(); stores override + adjusts graph confidence

    GET  /api/hitl/settings
         Returns: {"hitl_mode": str, "hitl_floor": float, "timeout_seconds": float}

    POST /api/hitl/settings
         Body: {"hitl_mode": str, "hitl_floor": float, "timeout_seconds": float}
         Updates session hitl_mode + hitl_floor in WAL

SSE stream: add "hitl_sync_queued" and "hitl_async_flagged" event types so
the dashboard updates the queue panel in real time.

### 5. Tests

Add tests/test_hitl.py covering:
    - classify_trigger() returns NEW_PATTERN when source=="default"
    - classify_trigger() returns LOW_CONFIDENCE when confidence < floor
    - classify_trigger() returns DESKTOP_PAUSE when message ends with "?"
    - classify_trigger() returns None when no trigger fires
    - route() in async mode returns original decision unchanged
    - route() in sync mode times out and returns original decision after timeout
    - apply_feedback() increases graph confidence on approved override
    - apply_feedback() decreases graph confidence on action override

Run: pytest tests/test_hitl.py -v
All tests must pass.
```

---

## STOP + VERIFY

Before marking Phase 2 complete, confirm **all** of the following:

**WAL schema**
- [ ] `hitl_pending` table exists in `_SCHEMA` with all 7 columns
- [ ] `hitl_overrides` table exists in `_SCHEMA` with all 6 columns
- [ ] `sessions` table gains `hitl_mode` + `hitl_floor` (migration-safe)
- [ ] `queue_hitl()`, `resolve_hitl()`, `annotate_decision()`, `get_pending_hitl()`, `get_hitl_mode()`, `set_hitl_mode()` all on `MessageBus`

**hitl.py**
- [ ] File exists at `src/stream_manager/hitl.py`
- [ ] `PAUSE_PATTERNS` regex covers `?` ending, "should i", "please confirm"
- [ ] `classify_trigger()` returns `None` when no trigger matches
- [ ] `route()` sync path polls `hitl_pending.resolution` at 0.5s interval
- [ ] `route()` sync path respects timeout (does not block indefinitely)
- [ ] `apply_feedback()` updates graph confidence via `DecisionGraph`
- [ ] Note cap is N=5 per hash; each note truncated to ≤50 tokens before storage

**governance.py**
- [ ] `hitl: HitlQueue | None` field on `GovernanceEngine`
- [ ] `_desktop_pause_active` flag; consumed (reset to False) after each evaluate
- [ ] `signal_desktop_pause()` method
- [ ] HITL routing happens in outer `evaluate()` not `_evaluate_inner()`
- [ ] `hitl=None` → no behavior change (backward compatible)

**dashboard API**
- [ ] `GET /api/hitl/pending` returns unresolved rows
- [ ] `POST /api/hitl/resolve` accepts all valid resolution strings
- [ ] `POST /api/hitl/annotate` stores override + triggers feedback
- [ ] `GET/POST /api/hitl/settings` round-trips hitl_mode + floor
- [ ] SSE emits `hitl_sync_queued` + `hitl_async_flagged` event types

**tests**
- [ ] `tests/test_hitl.py` exists with all 8 test cases
- [ ] `pytest tests/test_hitl.py -v` passes with zero failures
- [ ] `ruff check src/` passes
- [ ] `mypy src/stream_manager/` passes (or pre-existing errors only)

**If any check fails:** do not proceed to Phase 3. Fix first.

---

## Definition of Done

`GovernanceEngine.evaluate()` routes decisions through HITL when triggered.
Sync mode blocks and waits for human resolution. Async mode passes and flags.
Both modes feed back into the decision graph via confidence adjustments.
REST endpoints exist for dashboard to drive HITL interactions.

Commit message:
```
feat(hitl): FR-HITL §4.9 — sync/async queue, WAL tables, feedback loop
```
