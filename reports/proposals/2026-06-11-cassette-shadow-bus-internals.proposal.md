# Proposal: replace `run_shadow`'s direct `bus._conn` poke with a test-only insert helper

- **Finding:** F1 (cavecrew review, 2026-06-11) — `tools/cassette_replay.py` `run_shadow` reaches into `bus._lock` + `bus._conn` and hand-`INSERT`s into the FROZEN `messages` table, bypassing `publish()` validation. Severity 🟡.
- **Disposition:** ~~PROPOSAL (deferred — fix edits FROZEN surface)~~ → ~~REVISE: APPLY-NOW~~ → **DONE (`eb52689`).** Applied the `tools/`-only seam-swap: `run_shadow` now uses public `bus.fetch_rows` + `bus.execute_write` instead of `bus._lock`/`bus._conn`. E2E shadow run green (5/5 recorded, exit 0). The DEFER premise was falsified by verified research (workflow `w7npngehj`, 2026-06-11) — the bus already exposes the public seams; no FROZEN edit, no ADR-18 amendment. See **Verified-research update** at the bottom.

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
- `message_bus.py:707` — the fan-out `governance_decision` envelope carries `message_id` (the stable key `run_shadow` relies on). NB: the envelope is *built* at `record_decision` `message_bus.py:703-724`; `message_id` is the field at `:707`, not the build line (corrected per research).

---

## Verified-research update (2026-06-11, workflow `w7npngehj`, adversarially verified)

**Verdict: REVISE — flip DEFER → APPLY-NOW with a cheaper, FROZEN-free fix.** The original disposition rested on a false dilemma ("only fix = new method on FROZEN `message_bus.py`"). It is wrong.

**Verified facts (file:line, independently re-confirmed):**
- `MessageBus` already exposes two public, lock-managed seams added in **v1.3** specifically to migrate callers off `bus._conn`:
  - `MessageBus.fetch_rows(query, params)` — guarded read-only (SELECT/WITH), holds `self._lock` internally — `message_bus.py:1461-1487`.
  - `MessageBus.execute_write(query, params)` — guarded non-SELECT, holds `self._lock` internally — `message_bus.py:1489-1514`.
- The flagged block (`tools/cassette_replay.py` `run_shadow`, the `SELECT COALESCE(MAX(sequence))` + `INSERT INTO messages`) maps 1:1 onto `fetch_rows` (the MAX query) + `execute_write` (the INSERT). Production already uses this idiom: `decay.py:160,183,195`, plus `learn_mode.py`, `learn_categorizer.py` (**17 production occurrences across 3 files** — *not* "30+", which only holds counting tests).
- `cassette_replay.py` is a **`tools/` harness, not `src/`** — NOT on the ADR-18 freeze list nor the v2.8 "zero touch to FROZEN files" list (`docs/v2.8-task-plan.md:140-142`, which names `message_bus.py`). The swap touches **no FROZEN surface** → admissible this cycle, **no ADR-18 amendment, no deferral**.
- The "bus `Message` model differs from `messages.py` `Message`" rationale is TRUE but only rules out `bus.publish()` (which also fires `bus._subscribers` + `json.dumps(context/metadata)` vs the hardcoded `'{}'`, changing the row encoding/determinism). It does NOT justify poking `_conn` when `execute_write` exists.

**Recommended change (replaces the deferred `_testonly_insert_message` idea) — `tools/`-only, behaviour-identical:**
```python
seq = (bus.fetch_rows(
    "SELECT COALESCE(MAX(sequence), 0) FROM messages WHERE session_id=?",
    (sid,))[0][0] or 0) + 1
bus.execute_write(
    "INSERT INTO messages (id, session_id, sequence, type, direction, "
    "content, context, metadata, timestamp) VALUES (?,?,?,?,?,?,?,?,?)",
    (message_id, sid, seq, "user", "inbound",
     str(env.get("prompt", "")), "{}", "{}", ts))
```
Same SQL, same columns, same `'{}'`, same lock held internally (`message_bus.py:1486,1513`) → no concurrency/determinism change. Removes the `_lock`/`_conn` reach F1 flagged. **DISCARD** the on-bus `_testonly_insert_message` new-method recommendation (it would add a caller path to FROZEN `message_bus.py` for what two existing methods already do).

**Residual (separate, lower severity, NOT F1):** the 9-column `INSERT` list still lives in the harness after the swap. Only centralize it bus-side (a shared `_insert_message_row` that `publish()` also calls) if/when the freeze lifts AND a second harness needs it; otherwise put any shared seed helper in `tools/`/`tests/`, not on the bus class.

**Open question for operator:** retro-migrate the ~12 existing `tests/` files that poke `bus._conn.execute` (with divergent partial column lists) onto `fetch_rows`/`execute_write`? Out of F1 scope, but it is the real "multiple consumers" signal that would justify a shared `tests/_bus_fixtures.py` seam.
