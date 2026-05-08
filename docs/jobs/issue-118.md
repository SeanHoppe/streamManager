# #118 — rl_test_helper schema-parity vs `rl/schema.sql`

**Status:** UNBLOCKED 2026-05-08 — #108 bundle-merged via PR #121 (2026-05-07). `rl/schema.sql` confirmed present in tree.
Ready to land. Parallel-safe with v2.1 P1 work.
**Bucket:** NOW.
**GH:** https://github.com/SeanHoppe/streamManager/issues/118

## Summary

`tests/test_rl_test_helper.py` builds toy 6-col `episodes` fixture; real P1 schema ~14 cols.
Helper SELECT clauses (`verdict`, `source`, `action_propensity`) silently break under rename.
PR #115 R7. Parity test catches drift before merge.

## Scope

Add `tests/test_rl_test_helper_schema_parity.py`:
1. Build in-mem SQLite by exec `rl/schema.sql`.
2. Insert synthetic row matching real schema.
3. Call `summarise_episodes(db_path, sm_self_session_id=None)` + `summarise_shadow(...)`.
4. Assert no `OperationalError`; expected fields populated.

Alt: parse expected col list from P1 prompt DOD; assert helper SELECT matches.

## Acceptance

- [ ] Parity test in CI.
- [ ] P1 col rename → parity test fails before merge.
- [ ] Test imports `rl/schema.sql` directly (no copy-paste).

## Gating

Cannot land til #108 (v10 P1 episode logging) merges + `rl/schema.sql` exists.
Tag: `gated:P1-merge`.

## Refs

- PR #115 (robin agent + helpers).
- #108 (v10 P1).
- Memory `project_v10_rl_track.md`.
