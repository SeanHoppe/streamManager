# Proposal: replace `run_shadow`'s direct `bus._conn` poke with a test-only insert helper

- **Finding:** F1 (cavecrew review, 2026-06-11) — `tools/cassette_replay.py` `run_shadow` reaches into `bus._lock` + `bus._conn` and hand-`INSERT`s into the FROZEN `messages` table, bypassing `publish()` validation. Severity 🟡.
- **Disposition:** PROPOSAL (no code change this cycle). The recommended fix edits a FROZEN surface and is therefore deferred, not applied.

## Problem

`run_shadow` (cassette-shadow mode) needs a `messages` row to exist so that `bus.record_decision`'s `messages -> sessions` JOIN resolves `session_id` + `project_slug` for the fanned envelope. It does this by acquiring `bus._lock` and executing a raw `INSERT INTO messages (...)` against `bus._conn` directly:

```python
with bus._lock:
    seq_row = bus._conn.execute(
        "SELECT COALESCE(MAX(sequence), 0) FROM messages WHERE session_id=?", (sid,)
    ).fetchone()
    sequence = (seq_row[0] or 0) + 1
    bus._conn.execute(
        "INSERT INTO messages (id, session_id, sequence, type, direction, "
        "content, context, metadata, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (message_id, sid, sequence, "user", "inbound", str(env.get("prompt", "")), "{}", "{}", ts),
    )
```

This couples the offline harness to two private bus internals (`_lock`, `_conn`) **and** to the exact column list of the FROZEN `messages` table. Any private-schema change to `MessageBus` (column add/rename, lock-strategy change) breaks the harness silently — no type error, just a runtime `sqlite3.OperationalError` at replay time.

## Root cause

`run_shadow` bypasses `bus.publish()` deliberately, and for a real reason documented in-code:

> We bypass `bus.publish()` because the bus `Message` model differs from `messages.py` `Message`; a direct row keeps it deterministic.

So the coupling is not an oversight — it is the cheapest way to seed a JOIN-resolvable row without dragging the full `publish()` envelope-validation path (and its differing `Message` model) into an offline, synthetic replay. The mitigation today is real: the path is **offline-only** (never runs in production), and the `messages` table is **FROZEN** (ADR-18), so the private schema it pokes is stable for the v10 / v10.x window.

## Recommended change (deferred)

Add a **test-only insert helper** to `MessageBus` so the harness stops reaching past the public surface:

```python
# stream_manager/message_bus.py  (FROZEN — requires an ADR-18 freeze exception)
def _testonly_insert_message(self, *, message_id, session_id, content, ts) -> int:
    """Seed a minimal inbound `messages` row for offline replay harnesses.
    Returns the assigned sequence. NOT for production use."""
    with self._lock:
        seq = (self._conn.execute(
            "SELECT COALESCE(MAX(sequence), 0) FROM messages WHERE session_id=?",
            (session_id,)).fetchone()[0] or 0) + 1
        self._conn.execute(
            "INSERT INTO messages (id, session_id, sequence, type, direction, "
            "content, context, metadata, timestamp) VALUES (?,?,?,?,?,?,?,?,?)",
            (message_id, session_id, seq, "user", "inbound", content, "{}", "{}", ts))
        return seq
```

`run_shadow` then calls `seq = bus._testonly_insert_message(...)` and never touches `_lock` / `_conn`. The schema knowledge lives in **one** place (the bus), so a future column change updates the helper, not every harness.

## Why deferred (not applied now)

- `stream_manager/message_bus.py` is on the **ADR-18 surface-freeze list** for the v10 / v10.x cycle. Adding a method — even a test-only one — is a FROZEN-surface edit and is out of scope for this review's bounded, file-confined fixes.
- The reviewer's own routing was explicit: *"Offline-only + FROZEN-stable mitigates — but **if this grows**, add a test-only insert helper on the bus instead of poking `_conn`."* The condition ("if this grows") has not been met: `run_shadow` is the single consumer and the schema is frozen.

## Trigger to apply

Apply the helper when **any** of the following becomes true:
1. A second harness needs to seed `messages` rows (the coupling would then be duplicated).
2. The ADR-18 freeze on `message_bus.py` lifts (e.g. a v11 cycle), at which point the helper costs nothing and removes the private-internal reach.
3. The `messages` schema is changed for any reason — fold the helper in as part of that change so the harness moves with the schema.

## Evidence

- `tools/cassette_replay.py` — `run_shadow`, the `with bus._lock:` / `bus._conn.execute(...)` block.
- In-code rationale comment directly above the block ("We bypass `bus.publish()` ...").
- ADR-18 surface-freeze list (`docs/adr/ADR-18-mvp-surface-freeze.md`) — `message_bus.py` FROZEN.
- `message_bus.py:707` — FROZEN fan-out envelope carries `message_id` (the stable key `run_shadow` relies on), confirmed in the source review.
