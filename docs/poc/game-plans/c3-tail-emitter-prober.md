# C3 — `tail-emitter-prober` game plan

**Agent file:** `.claude/agents/tail-emitter-prober.md`
**Role:** Tail-side wire prober.
**Tools:** Read, Grep, Bash.

## Role in fleet

Confirms `JsonlTailWorker` (production wire site `src/stream_manager/jsonl_tail.py:178`, wired at `dashboard/server.py:292-331`) emits `desktop_prompt` / `user_reply` envelopes against the C1-locked target slug. Downstream C4/C5/C9 require this PASS.

## Inputs

- C1's locked triple.
- C2's env-validation PASS row (precondition).
- MessageBus SQLite (default `.claude/gov.db`; URI `?mode=ro`).
- `src/stream_manager/jsonl_tail.py:178` (read-only reference).
- `dashboard/server.py:292-331` (read-only reference).
- Dashboard log (read-only).

## Steps

1. Snapshot `max(envelope_id)` at t0.
2. Wait ≤ 60 s for new rows where `kind ∈ {desktop_prompt, user_reply}` AND `metadata.source_slug == BRIDGE_PROJECT_SLUG`.
3. Verify: target slug counter > 0, SM-slug counter == 0.
4. Grep dashboard log for `polarity-flip-refusal` lines during window; confirm all cite SM slugs only (not the target).

## PASS criteria

- ≥ 1 target envelope in 60 s window.
- 0 SM-slug envelopes (no polarity-flip leak).
- Self-refusal log lines (if any) cite SM slugs only.

## Outputs to coordinator

- `envelope_id` for C4 to trace.
- Per-source-slug counts.
- Self-refusal log evidence.

## Failure modes

- `no-envelopes-in-60s` — operator didn't send a turn in window; recoverable, re-fire after operator turn.
- `sm-slug-envelope-observed` — wire-site refusal bug; HARD FAIL.
- `refusal-citing-target-slug` — wire site is refusing the intended target; HARD FAIL.

## Dependencies

- Hard precondition: C1 PASS + C2 PASS.
- Soft: dashboard running and JsonlTailWorker started.

## Refs

- `src/stream_manager/jsonl_tail.py:178`.
- `dashboard/server.py:292-331`.
- `docs/learn-mode-design.md` §3.1.
- `feedback_no_self_monitor.md`.
