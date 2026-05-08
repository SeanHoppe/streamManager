# #132 — Cassette CI guard: enforce same-PR coverage for new envelope kinds

**Status:** OPEN — bootstrap after v2.1 P1 lands (need P1 envelopes as known-good baseline).
**Bucket:** Post v2.1 P1.
**GH:** https://github.com/SeanHoppe/streamManager/issues/132

## Summary

`feedback_cassette_must_cover_new_envelopes.md` rule = convention-only today.
v1.3 nearly tagged without LM coverage. Probability of recurrence → 1 over enough cycles.
Add CI guard.

## Options

- **A.** Grep diff check — `git diff origin/main..HEAD` for new envelope strings, verify cassette + soak driver reference same kind. Fragile under squash-merge.
- **B.** Source-of-truth allowlist (`src/stream_manager/envelope_kinds.py`) + sentinel test iterates allowlist, asserts each kind in cassette + soak recorder.

**Recommend B.**

## Acceptance

- [ ] A vs B decision recorded.
- [ ] Implementation PR adds guard.
- [ ] Backfill: existing kinds in `desktop_commands.py:45` allowlist verified (or marked exempt).
- [ ] `feedback_cassette_must_cover_new_envelopes.md` updated → enforced rule.
- [ ] Failure-path test: deliberately broken PR fails the guard locally.

## Timing

After v2.1 P1 lands (bootstraps against `audit.probe` + `audit.probe_ack` baseline).
Mint as v2.2 P0 task or standalone hardening PR — no full cycle frame needed.

## Refs

- Memory `feedback_cassette_must_cover_new_envelopes.md`.
- Allowlist source: `src/stream_manager/desktop_commands.py:45`.
- Cassette: `tools/cassette_record.py`, `tools/soak_driver.py`.
- Triggering incident: `project_v13_corrective.md`.
