You are implementing **Task M1 — Tier 1 replay smoke** from `docs/v1.2-soak-finalize.md`.

## Master plan
Read `docs/v1.2-soak-finalize.md` first. M1 is the cheap pre-flight gate before burning Haiku quota (M2) or default-model quota (M3). Goal: confirm v1.2 plumbing (Tasks C, D, E) does not regress against the committed cassette.

## Branch + base
- Base: `main` (v1.2.0 already tagged at `69965aa`).
- Open PR targeting `main` titled `chore(v1.2): replay smoke pre-shipgate`.
- Single-commit PR, report-only artifact.

## ⚠️ CRITICAL: Do-not-touch guard
M1 is **measurement only**. NO production code edits. Read the do-not-touch table in `docs/v1.2-soak-finalize.md` §"CRITICAL". If replay surfaces a regression in any protected symbol, STOP — file a separate fix PR against `main`, do not bundle into M1.

Pre-flight diff check (catch silent reverts since v1.2.0 — memory: `feedback_subagent_stale_mental_model.md`):
```
git diff v1.2.0..HEAD -- src/stream_manager/cli_pool.py src/stream_manager/governance.py src/stream_manager/wirecli.py src/stream_manager/desktop_command_consumer.py src/stream_manager/cli_replay_pool.py tools/soak_driver.py tools/cassette_record.py
```
Expect empty diff (or only doc changes). If protected symbols moved: STOP and report.

## Task brief

Run the existing committed cassette through `tools/soak_driver.py --cli-replay` and capture report.

### Steps

1. Confirm cassette exists: `tests/fixtures/soak_cassette_2026-05-03.jsonl`.

2. Run replay:
   ```
   python tools/soak_driver.py --cli-replay tests/fixtures/soak_cassette_2026-05-03.jsonl
   ```

3. Driver writes `reports/replay-<UTC-ts>.md`. Report header MUST show:
   - mode: replay
   - cassette: `tests/fixtures/soak_cassette_2026-05-03.jsonl`
   - miss-counter: 0

4. Verification gates (FAIL → file fix PR, do NOT continue M1):
   - Overall PASS
   - miss-counter == 0 (if >0: cassette is stale → M2 must run first)
   - Lifecycle bridge (Task C): `claude_code_*` event types appear in bus log; no orphan start/end keys in `LifecycleBridge._seen`
   - SSE-only consumer (Task D): no long-poll fallback path hit; `_VALID_TRANSPORTS == frozenset({"sse"})`
   - JSON transport (Task E): no `transport=json` envelopes reach engine. (Cassette pre-dates Task E — if any present, ReplayPool returns canned response, OK)
   - p95 within ±5% of cassette recorded p95 (RELATIVE signal — see ADR-17)
   - RSS drift < 50 MB

5. If all gates green: commit only the new `reports/replay-<ts>.md`. Commit msg:
   ```
   chore(v1.2): tier-1 replay smoke pre-shipgate

   Confirms v1.2 plumbing (Tasks C, D, E) does not regress vs cassette
   2026-05-03 baseline. Pre-flight gate before M2 cassette refresh and
   M3 ship-gate soak per docs/v1.2-soak-finalize.md.
   ```

6. Open PR. PR body links the report and notes M2 unblocked.

## Do NOT
- Edit any production code.
- Edit the cassette fixture (M2 owns refresh).
- Run M2 or M3 in this PR.
- Update ADR-5 (M4 owns it).

## DOD
- `reports/replay-<ts>.md` PASS, all gates green
- Single-commit PR merged to `main`
- M2 prompt unblocked
