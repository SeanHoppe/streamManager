You are implementing **Phase P2 — `list_active_jobs` windowed query** from the streamManager v1.3 cycle.

## Branch + base

- Base: `main`.
- PR target: `main`.
- Branch: `fix/v1.3-list-active-jobs-windowed` (or operator's choice).
- If `main` is unexpectedly behind v1.2 close-out (`7b7dc64`), ABORT and tell the user.

## ⚠️ CRITICAL: Do-not-touch guard

Protected symbols — `LifecycleBridge` outer surface MUST NOT change. The fix is in the SQL query layer ONLY. Do not change method signatures, return-tuple shapes, envelope schema, or the `/api/lifecycle/jobs` payload contract.

| From task | File | Symbols/sections |
|-----------|------|------------------|
| C (v1.2) | `src/stream_manager/lifecycle_bridge.py` | `LifecycleBridge` outer surface; `_seen` dict shape |
| C (v1.2) | `dashboard/server.py` | `/api/lifecycle/jobs` endpoint payload contract |
| (cross-cutting) | `src/stream_manager/message_bus.py` | `MessageBus` envelope schema (additive only — P2 should not need to touch) |

Pre-flight grep:

```
grep -nE 'list_active_jobs|/api/lifecycle/jobs|LifecycleBridge|_seen' src/stream_manager/lifecycle_bridge.py dashboard/server.py
```

If `list_active_jobs` is missing or its signature has drifted from v1.2.0, STOP and report.

## Task brief

🟡 carry-over from PR #43 (Task C). `list_active_jobs` uses `LIMIT * 4` overfetch on the lifecycle events table. Hot session with >25 lifecycle event pairs (default `limit=100`, 2 rows per pair) silently drops open jobs at the tail.

Replace `LIMIT * 4` with one of:
1. **Windowed query** (preferred) — latest event per `job_id` via correlated subquery `WHERE ts = (SELECT MAX(ts) FROM lifecycle_events WHERE job_id = outer.job_id)`, OR `ROW_NUMBER() OVER (PARTITION BY job_id ORDER BY ts DESC) = 1` if SQLite version pinned in the repo supports window functions.
2. **Paginated cursor** (fallback if windowed query is infeasible) — paginate by `(ts, job_id)` cursor with explicit terminator. Document choice in the PR body.

New test `tests/test_list_active_jobs_windowed.py`: synthesize 100 lifecycle event pairs (200 rows), assert `list_active_jobs(limit=100)` returns all 100 open jobs without tail truncation.

Optional: scenario-replay artifact under `tests/scenarios/list_active_jobs_overflow.yaml` per `docs/v1.3-testing.md` §Method 1 — Scripted Scenario Replay (operator-in-the-loop verification).

## DOD

- [ ] Windowed query (or paginated cursor) replaces `LIMIT * 4`
- [ ] No tail truncation at 25+ pairs (test asserts)
- [ ] `LifecycleBridge` outer surface unchanged (`dashboard/server.py` shows zero edits)
- [ ] `pytest -q` passes end-to-end
- [ ] `git --no-pager diff main..HEAD --stat` shows only intentionally added/modified files
- [ ] No protected-symbol drift

## Final verification before opening PR

```
git --no-pager diff origin/main..HEAD --stat
```

Expected files:
- `src/stream_manager/lifecycle_bridge.py` (modified — query layer only)
- `tests/test_list_active_jobs_windowed.py` (new)
- (optional) `tests/scenarios/list_active_jobs_overflow.yaml` (new)

If diff shows ANY edit to `dashboard/server.py` or to the `LifecycleBridge` outer surface (method signatures, `_seen` shape, envelope schema), STOP and report.

Run `pytest -q` end-to-end. Paste tail in PR body.

Report back: PR URL, diff stat, pytest tail.
