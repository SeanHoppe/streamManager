# S1 — Wipe stale soak state

**Goal:** Clean `tmp/` of partial artifacts from killed v1.6 soak (2026-05-04).
Prevents re-using a half-populated DB or empty log.

## Context

Previous soak was killed mid-flight (Win PID 12808, 5 procs terminated).
Leftover state on disk:
- `tmp/v16_soak.db` + WAL/SHM (partial gov decisions)
- `tmp/v16-shipgate-soak.log` (empty — driver buffered before flush)

## Steps

```bash
rm -f tmp/v16_soak.db tmp/v16_soak.db-shm tmp/v16_soak.db-wal
rm -f tmp/v16-shipgate-soak.log
```

## Acceptance

- `ls tmp/v16*` returns nothing (or only `tmp/v16-shipgate-soak.log` recreated by S2 launch)
- No port 8766 listener (`netstat -ano | grep 8766` empty)

## On-done ack

Update checklist line:
`- [x] <SHA-not-applicable, file-deletion-only> **S1 — Wipe stale soak state** ...`

## Mint-new check

None expected. If ports/processes still bound, mint `S1a-stale-process-cleanup.md`.
