You are implementing **Phase P3a-tighten — pre-merge drain of PR
#147 caveman-review findings** for the streamManager v2.1 cycle
(PPP audit harness, P3a sub-phase). P3a (PR #147) shipped the
R-decoy-idem 🔴 fix + R-decoy-bus-sig signature widen +
R-decoy-test-gap regression test + R-loc-amend retroactive ADR-18
amendment. Pre-merge caveman-review surfaced 2 ❓ defensive-code
risks + 1 🔵 nit that this tightening drains before merge.

P3a-tighten is **NOT** a new sub-phase against the v2.1 phase
budget. It is a pre-merge fixup on the OPEN PR #147 branch — same
pattern as a reviewer-requested change set, just routed through a
fresh-session prompt for context isolation per
`feedback_subagent_stale_mental_model.md`.

## Branch + base

- **Existing branch (do NOT create new):** `feat/v2.1-p3a-ppp-p3-followups`
- **Head SHA at mint time:** `b888ab7`
- **PR:** [#147](https://github.com/SeanHoppe/streamManager/pull/147) — OPEN, MERGEABLE
- Push additional commit(s) to this branch; do NOT open a new PR.
- After your push, GitHub auto-updates #147.

## Reference docs (load before coding)

- `docs/v2.1-p3a-scope.md` — parent scope (P3a items table +
  R-register; load-bearing for context only — P3a-tighten does NOT
  amend it).
- `docs/prompts/v2.1-orchestration/phase-3a-ppp-p3-followups.md` —
  parent phase prompt (the 4 P3a items it specifies are ALREADY
  landed on `feat/v2.1-p3a-ppp-p3-followups`; do NOT re-do them).
- Memory: `feedback_subagent_stale_mental_model.md`,
  `feedback_cross_pr_seam_review.md`.

## ⚠️ CRITICAL: Do-not-touch guard

ADR-18 surface freeze in force. P3a-tighten touches ONLY:

- `src/stream_manager/governance.py` — finding 1 (assertion).
- `src/stream_manager/message_bus.py` — finding 2 (drop unreachable
  branch OR convert to assert).
- `tools/cassette_record.py` — finding 3 (rename `ok` → `_ok`,
  drop `del`).

NO edits to tests (existing P3a tests already cover both seams; if
the asserts trip in CI, that is correct fail-loud behavior). NO
edits to docs (`docs/v2.1-p3a-scope.md` LOC tally stays at 91 — the
3 tightenings are net negative LOC, well under the 100 cap). NO
edits to any other src/ file. NO new envelope dataclasses, no new
WAL tables, no new endpoints.

Pre-flight check after `git checkout feat/v2.1-p3a-ppp-p3-followups
&& git pull`:

```
grep -nE 'write_provenance_decoy|register_decoy_stream' src/ tests/ tools/ dashboard/
```

Hit set MUST match P3a post-merge baseline (governance.py × 2,
message_bus.py × 1, tools/cassette_record.py × 1,
tests/test_audit_decoy_register.py × multiple). P3a-tighten changes
shapes inside 3 of those hits; adds zero hits.

## Task brief

Drain 3 caveman-review findings on PR #147:

### Finding 1 — `governance.py` defensive fall-through

**File:** `src/stream_manager/governance.py` (around L1511 in
`register_decoy_stream`).

**Problem:** The current branch reads:

```python
first_write, wal_probe_id, wal_registered_at, wal_sig = (
    self.bus.write_provenance_decoy(...)
)
if not first_write and wal_probe_id is not None:
    return wal_probe_id, {
        "probe_id": wal_probe_id,
        "jsonl_path": jsonl_path,
        "registered_at": float(wal_registered_at),
        "hmac_sig": wal_sig,
    }, False
return probe_id, {**sig_payload, "hmac_sig": sig}, first_write
```

If `first_write is False` AND `wal_probe_id is None` somehow,
control falls through to the bottom `return`, which silently
re-introduces the original R-decoy-idem bug (returns freshly-minted
probe_id even though the WAL kept a different row). Today this is
unreachable — `write_provenance_decoy` guarantees `wal_probe_id is
not None` when `first_write is False` (it SELECTs from a row that
the ON CONFLICT proved exists). But a future schema migration (e.g.
DELETE path on `provenance_decoys` for ops cleanup) could make it
reachable, and the bug would be silent.

**Fix:** Replace the defensive `wal_probe_id is not None` guard
with an assertion that fail-loud documents the invariant:

```python
first_write, wal_probe_id, wal_registered_at, wal_sig = (
    self.bus.write_provenance_decoy(...)
)
if not first_write:
    assert wal_probe_id is not None, (
        "WAL row vanished after ON CONFLICT — "
        "provenance_decoys integrity violation"
    )
    return wal_probe_id, {
        "probe_id": wal_probe_id,
        "jsonl_path": jsonl_path,
        "registered_at": float(wal_registered_at),
        "hmac_sig": wal_sig,
    }, False
return probe_id, {**sig_payload, "hmac_sig": sig}, first_write
```

Net LOC: roughly −1 (the `and wal_probe_id is not None` clause
moves out of the `if` and becomes a 3-line assert).

### Finding 2 — `message_bus.py` unreachable `row is None`

**File:** `src/stream_manager/message_bus.py` (around L1051 inside
`write_provenance_decoy`).

**Problem:** After `ON CONFLICT(jsonl_path) DO NOTHING` registers a
no-op (cur.rowcount == 0), the conflict path SELECTs the existing
row. Then:

```python
row = cur.fetchone()
if row is None:
    return (False, None, None, None)
return (False, row[0], row[1], row[2])
```

The `row is None` branch is unreachable: `ON CONFLICT(jsonl_path)
DO NOTHING` only fires when a row with that `jsonl_path` already
exists in the table (UNIQUE constraint), so the immediately
following `SELECT ... WHERE jsonl_path = ?` against the same lock
window MUST return a row.

**Fix:** Convert to an assertion that fail-loud documents the
invariant:

```python
row = cur.fetchone()
assert row is not None, (
    "provenance_decoys ON CONFLICT path SELECT returned no row — "
    "WAL integrity violation"
)
return (False, row[0], row[1], row[2])
```

Net LOC: roughly −1 (drop the early-return branch, gain a 3-line
assert).

### Finding 3 — `cassette_record.py` `del` after unpack

**File:** `tools/cassette_record.py:395`.

**Problem:** Current call site reads:

```python
ok, *_ = bus.write_provenance_decoy(...)
del ok
```

The `del ok` is dead code — `ok` is a local that goes out of scope
naturally, and the unpack already discards the trailing tuple
elements. Idiomatic Python uses underscore-prefix to mark an unused
binding.

**Fix:**

```python
_ok, *_ = bus.write_provenance_decoy(...)
```

Net LOC: −1.

## Total LOC delta

Estimate: ≈ −3 net (governance.py −1, message_bus.py −1,
cassette_record.py −1; small positive churn from the assert message
strings). P3a tally drops from 91 → ~88, still under the 100 cap.

## Threat model continuity

P3a-tighten does NOT alter the threat model (FR-PPP-2 lock
2026-05-10). The asserts STRENGTHEN integrity: a corrupted WAL
state that would have silently returned a wrong probe_id now raises
loud at the seam, surfacing the corruption to oncall instead of
poisoning downstream correlation.

## Deliverables

Single additional commit (or 2-3 small ones) on the EXISTING
branch `feat/v2.1-p3a-ppp-p3-followups`. Push to update PR #147.

Conventional commit prefix: `fix(ppp):` (same family as the parent
P3a commit). Suggested subject:

```
fix(ppp): v2.1 P3a tighten — drain PR #147 review ❓ + 🔵
```

PR #147 body: append a "Pre-merge tightenings" section
cross-referencing the 3 review findings drained. Do NOT mint a
new PR; do NOT open a P3b scope doc — these are pre-merge fixups
on review findings, not a new sub-phase.

## DOD

- [ ] Pulled latest `feat/v2.1-p3a-ppp-p3-followups` before editing
- [ ] Finding 1 landed: `assert wal_probe_id is not None` with
      integrity-violation message; no defensive fall-through path
      to R-decoy-idem bug
- [ ] Finding 2 landed: `assert row is not None` with WAL
      integrity-violation message; no unreachable early-return
- [ ] Finding 3 landed: `_ok, *_ = ...`; `del ok` line gone
- [ ] `pytest -m "not slow and not alignment_eval"` — 721 passed
      (unchanged from P3a baseline; asserts must NOT trip in any
      existing test)
- [ ] LOC tally for the full PR #147 still ≤ 100 net add (was 91;
      should land ~88)
- [ ] FROZEN-seam diff guard: still ONE disclosed non-additive
      hunk (`message_bus.py:write_provenance_decoy` return widening
      from the parent P3a commit); the assert tightening on the
      same function is additive in shape (no new return path
      introduced)
- [ ] Cross-seam check: `register_decoy_stream` callers and
      cassette caller unchanged in observable behavior (asserts
      only trip on invariant violation; happy path identical)
- [ ] PR #147 body amended with "Pre-merge tightenings" section
      paste-citing the 3 review findings
- [ ] NO edits outside the 3 listed files
- [ ] NO new tests (existing P3a tests still cover both seams)
- [ ] NO scope-doc edits (`docs/v2.1-p3a-scope.md` unchanged)
- [ ] Sub-cycle close-out diff: PR #147 head vs `main` confirms
      ONLY the 5 files from P3a + this tightening's 3 files (which
      overlap) — net 5 files touched, no surprise additions per
      `feedback_subagent_stale_mental_model.md`

## After this phase

P3a (PR #147) merges. P4 ship-gate prompt mints per the
just-in-time pattern in `docs/v2.1-task-plan.md`:
- Tier 3 soak with PPP auto-probe default-on (flip from P1's
  opt-in).
- Alignment-eval `--ci-gate`.
- ADR-5 v2.1 baseline append.
- CHANGELOG v2.1.0.
- Tag v2.1.0.
- Mint `project_v21_cycle_close.md`.
- Decide on dormant `JsonlTailWorker.start()` (wire OR record
  dormancy with v2.2 backlog seed).

P3a-tighten does NOT cover any of the above. Out of scope.
