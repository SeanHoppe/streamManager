You are implementing **Task M2 — Tier 2 cassette refresh** from `docs/v1.2-soak-finalize.md`.

## Master plan
Read `docs/v1.2-soak-finalize.md` first. M2 refreshes the soak cassette on Haiku so it covers v1.2 surface (Tasks C, D, E). Output: new fixture committed + `latest` pointer repointed.

## Predecessor gate
- M1 must be PASS and merged. Confirm `reports/replay-<m1-ts>.md` exists on `main`.
- If M1 not green: STOP, report to user.

## Branch + base
- Base: `main` (post-M1 merge).
- PR title: `chore(v1.2): refresh soak cassette for Tasks C/D/E surface`.

## ⚠️ CRITICAL: Do-not-touch guard
M2 is **fixture refresh only**. NO production code edits. See do-not-touch table in `docs/v1.2-soak-finalize.md` §"CRITICAL".

Cassette latencies are recorded against **Haiku**, NOT default ship-gate model. They are RELATIVE regression signals only — never compared to ADR-5 absolute targets (see ADR-17 §"Cassette is a *relative* signal").

## Pre-flight

1. `claude` CLI on PATH:
   ```
   claude --version
   ```
2. `BRIDGE_API_GOV=1` viable in env.
3. Quota: ~60 Haiku calls. Cheap (~10x default model), but confirm available.

## Task brief

### Steps

1. Run recorder:
   ```
   python tools/cassette_record.py
   ```
   Wraps `soak_driver.py` with `--cli-pool-size 2 --model claude-haiku-4-5-20251001 --record-cassette tests/fixtures/soak_cassette_<YYYY-MM-DD>.jsonl`.

2. Confirm new fixture path written: `tests/fixtures/soak_cassette_<today>.jsonl`.

3. Repoint `tests/fixtures/soak_cassette_latest.jsonl` to the new file. (Symlink on POSIX, copy or pointer file on Windows — match existing convention in repo. Inspect what's there first.)

4. Sanity replay against new fixture:
   ```
   python tools/soak_driver.py --cli-replay tests/fixtures/soak_cassette_latest.jsonl
   ```
   Output: `reports/replay-<post-refresh-ts>.md`. Must PASS, miss-counter == 0.

5. Run replay regression test:
   ```
   pytest -q tests/test_soak_replay.py
   ```
   Must pass.

6. Verify new cassette content:
   - Includes lifecycle bridge envelopes (Task C `claude_code_*` event types)
   - Zero `transport=json` envelopes (Task E)
   - L2/L3 + L4 trigger fixtures present (mirror v1.1 mix)

7. Commit (single PR):
   - `tests/fixtures/soak_cassette_<date>.jsonl` (NEW)
   - `tests/fixtures/soak_cassette_latest.jsonl` (POINTER)
   - `reports/replay-<post-refresh-ts>.md` (sanity)
   Commit msg:
   ```
   chore(v1.2): refresh soak cassette for Tasks C/D/E surface

   Records 60-event Haiku cassette covering v1.2 lifecycle bridge
   (Task C), SSE-only consumer (Task D), and json transport refusal
   (Task E). Repoints `latest` pointer. Sanity replay PASS.
   Pre-flight for M3 ship-gate soak per docs/v1.2-soak-finalize.md.
   ```

## Do NOT
- Edit any production code.
- Run M3 ship-gate soak in this PR (separate task, default model, big quota).
- Update ADR-5.
- Delete the prior `soak_cassette_2026-05-03.jsonl` — keep history.

## DOD
- New cassette fixture committed
- `latest` pointer repointed
- Sanity replay PASS, pytest replay test green
- M3 prompt unblocked
