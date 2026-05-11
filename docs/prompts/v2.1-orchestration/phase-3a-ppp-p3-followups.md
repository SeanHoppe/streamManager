You are implementing **Phase P3a — PPP Layer 3 follow-ups
(PR #145 review drain + ADR-18 Rule 4 retroactive amendment)** for
the streamManager v2.1 cycle (PPP audit harness). P3 (PR #145)
shipped Layer 3 negative-control + self-monitor hard guard;
caveman-style code review surfaced 1 🔴 bug + 2 🟡 risks +
1 LOC-amendment item that this sub-phase drains.

## Branch + base

- Base: `main` after v2.1 P3 (PR #145) merged.
- PR target: `main`.
- Branch: `feat/v2.1-p3a-ppp-p3-followups`.

## Reference docs (load before coding)

- `docs/v2.1-p3a-scope.md` — **load-bearing** scope + items table
  + LOC tracker + R-register. Authority for every decision below.
- `docs/v2.1-p3-scope.md` — parent scope (P3 inheritance).
- `docs/v2.1-p1a-scope.md` — sub-phase template P3a mirrors.
- `docs/v2.1-task-plan.md` — cycle frame.
- `REQUIREMENTS.md` §4.13 FR-PPP-12..14 (P3-minted spec; P3a does
  not append new FR lines — bug-fix sub-phase only).
- Memory: `feedback_subagent_stale_mental_model.md`,
  `feedback_cross_pr_seam_review.md`,
  `feedback_cassette_must_cover_new_envelopes.md`,
  `feedback_subagent_escape_hatches.md`,
  `feedback_parallel_undisclosed_deviations.md`.

## ⚠️ CRITICAL: Do-not-touch guard

ADR-18 surface freeze in force. P3a touches ONLY:

- `src/stream_manager/governance.py` — fix
  `register_decoy_stream` to return the WAL's authentic
  `(probe_id, registered_at, hmac_sig)` tuple on re-register
  conflict. Currently the method silently returns the freshly
  minted probe_id even when `write_provenance_decoy` rejected the
  insert via `ON CONFLICT(jsonl_path) DO NOTHING`. PR #145 body
  claims "responds with the existing row's metadata in that case"
  — implementation does not. Item R-decoy-idem.
- `src/stream_manager/message_bus.py` — widen
  `write_provenance_decoy` return from `bool` to
  `tuple[bool, str | None, float | None, str | None]`
  (`first_write, probe_id, registered_at, hmac_sig`). On
  `first_write=False`, the trailing 3 elements carry the existing
  WAL row so callers can return authentic data without a second
  SELECT round-trip. Item R-decoy-bus-sig. **This is the ONE
  disclosed non-additive hunk in P3a — return-type widening.**
- `tools/cassette_record.py` — update the `write_provenance_decoy`
  call site at line 395 to unpack the new tuple. Cassette does not
  need the existing row (cassette always writes fresh), so the
  unpack discards the trailing elements (`first_write, *_ = ...`).
  Item R-decoy-bus-sig (call-site fix-up).
- `tests/test_audit_decoy_register.py` — (a) strengthen existing
  `test_register_decoy_stream_via_engine` to assert
  `probe_id2 == probe_id` + `reg2 == reg` on re-register;
  (b) update 5 `write_provenance_decoy` direct calls to unpack
  the new tuple shape; (c) add ONE new test
  `test_register_decoy_stream_conflict_returns_wal_row` that
  proves the bug-fix end-to-end at the governance layer (not
  just bus layer). Item R-decoy-test-gap + R-decoy-idem coverage.
- `docs/v2.1-p3-scope.md` — append retroactive ADR-18 Rule 4
  amendment to §LOC tracker recording 1071 actual / 700 cap /
  371 over. Mirror entry style from `docs/v2.1-p1-scope.md`
  §LOC tracker post-P1. Item R-loc-amend.

NO edits to `dashboard/`, `cli_pool.py`, `cli_governance.py`,
`model_router.py`, `session_watcher.py`, `jsonl_tail.py`, any
other src/ file, `REQUIREMENTS.md`, or any test file outside
`tests/test_audit_decoy_register.py`. NO new envelope dataclasses;
NO new WAL tables; NO new endpoints; NO new dashboard variants.

Pre-flight grep:

```
grep -nE 'write_provenance_decoy|register_decoy_stream' src/ tests/ tools/ dashboard/
```

Before P3a edits: hits in P3 scope only. Confirm count matches
`docs/v2.1-p3a-scope.md` §4 baseline before any edit lands.
After P3a edits: SAME set of hit locations (no new files, no new
call sites); only the shapes change.

## Task brief

Per `docs/v2.1-p3a-scope.md` §2 items table, drain the 3 PR #145
review findings + the LOC amendment:

1. **Fix `register_decoy_stream` idempotent-return** —
   `governance.py:1488`. On `first_write=False` from
   `write_provenance_decoy`, return the WAL's existing
   `(probe_id, registered_at, hmac_sig)` instead of the freshly
   minted values. After item 2 lands, this becomes a 1-line
   change (unpack the tuple). Before item 2, would require a
   separate SELECT; do item 2 first to avoid that path.

2. **Widen `write_provenance_decoy` signature** —
   `message_bus.py:1009`. Inside the existing `with self._lock:`
   block, after the INSERT ON CONFLICT, check `cur.rowcount`:
   - If `> 0` (first write): return `(True, probe_id,
     registered_at, hmac_sig)` (echo input).
   - Else (conflict): `SELECT probe_id, registered_at, hmac_sig
     FROM provenance_decoys WHERE jsonl_path = ?` and return
     `(False, *row)`.
   Keep the SELECT inside the same lock block — the row is
   guaranteed to exist (just lost the insert race).

3. **Strengthen re-register tests** —
   `tests/test_audit_decoy_register.py`. Existing test at L87-111
   gets two new assertions on re-register:
   `assert probe_id2 == probe_id` and `assert reg2 == reg`. The
   5 direct `write_provenance_decoy` calls (L32, L46, L50, L62,
   L71) unpack the new tuple — most can ignore the trailing
   elements via `ok, *_ = bus.write_provenance_decoy(...)`.
   New test:
   ```
   def test_register_decoy_stream_conflict_returns_wal_row(bus, tmp_path):
       """Bug regression: governance must surface WAL probe_id on conflict,
       not the freshly-minted one."""
       ...
       p1, reg1, first1 = engine.register_decoy_stream(jsonl_path=path)
       assert first1 is True
       p2, reg2, first2 = engine.register_decoy_stream(jsonl_path=path)
       assert first2 is False
       assert p2 == p1
       assert reg2["registered_at"] == reg1["registered_at"]
       assert reg2["hmac_sig"] == reg1["hmac_sig"]
   ```
   This test would have caught the bug.

4. **Retroactive ADR-18 Rule 4 amendment** —
   `docs/v2.1-p3-scope.md` §LOC tracker. Append entry recording
   1071 / 700 / 371-over with the same retroactive-amendment
   phrasing used in `docs/v2.1-p1-scope.md` §LOC tracker. Note
   driver: 594 LOC test floor across 5 test files.

### Threat model continuity (FR-PPP-2 lock 2026-05-10)

P3a does NOT alter the threat model. The endpoint-integrity HMAC
sig on `provenance_decoys` rows is server-stamped at register time
in `register_decoy_stream`; the bug-fix surfaces the WAL row's
authentic sig instead of a fresh sig that never reached the WAL.
This STRENGTHENS the integrity guarantee — operators correlating
decoy registration responses with `audit.hallucination_detected`
envelopes will now see matching probe_id + sig pairs.

### Deliverables

Single PR. Conventional commit prefix `fix(ppp):` (not `feat` —
P3a is a bug-fix sub-phase, not a feature surface). PR body:
- Cross-reference each R-register entry resolved.
- Disclose the ONE non-additive hunk (`message_bus.py` return
  widening) in a dedicated section.
- Cite caveman-review pass on PR #145 as the source of findings
  1/2/3 (paste the 3 review comments verbatim under "Review
  findings drained").
- LOC tally vs the 100-LOC P3a ceiling.

## DOD

- [ ] All 4 items landed in one PR
- [ ] `pytest -m "not slow and not alignment_eval"` — 721 passed
      (720 P3 baseline + 1 new regression test)
- [ ] `assert probe_id2 == probe_id` + `assert reg2 == reg`
      present in re-register test
- [ ] `test_register_decoy_stream_conflict_returns_wal_row` added
      and passing
- [ ] `write_provenance_decoy` tuple return; 3 call-site classes
      (governance, cassette, tests) all updated atomically — no
      partial migrations
- [ ] `docs/v2.1-p3-scope.md` §LOC tracker amended with
      retroactive 1071/700 entry
- [ ] FROZEN-seam diff guard: ONE disclosed non-additive hunk
      (`message_bus.py:write_provenance_decoy` return widening);
      zero hunks elsewhere
- [ ] LOC ≤ 100 net add; if exceeded, file P3b (do NOT spill into
      P4 ship-gate)
- [ ] Conventional commit prefix `fix(ppp):`
- [ ] Single PR against `main`
- [ ] Cross-PR seam review: writer↔readers verified atomically
      per `feedback_cross_pr_seam_review.md`
- [ ] Sub-cycle close-out diff PR head vs base on touched files
      per `feedback_subagent_stale_mental_model.md` (governance.py,
      message_bus.py — confirm only the 2 disclosed hunks landed)

## After this phase

P3a close-out mints
`docs/prompts/v2.1-orchestration/phase-4-ship-gate-finalize.md`
(v2.1 ship-gate). P4 inherits two carry-forward items from P3
that P3a explicitly does NOT touch:

1. **Dormant `JsonlTailWorker.start()`** — still not wired into
   dashboard startup (carried from PR #143 + #145). P4 either
   wires it OR records the dormancy in
   `project_v21_cycle_close.md` with a v2.2 backlog seed.
2. **Tier 3 soak with PPP auto-probe default-on** — flip from
   P1's opt-in to default-on at ship-gate; alignment-eval
   `--ci-gate`; ADR-5 v2.1 baseline append; CHANGELOG v2.1.0;
   tag v2.1.0; mint `project_v21_cycle_close.md`.

P3a does NOT cover either. Out of scope.
