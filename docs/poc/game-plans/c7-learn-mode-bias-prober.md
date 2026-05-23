# C7 — `learn-mode-bias-prober` game plan

**Agent file:** `.claude/agents/learn-mode-bias-prober.md`
**Role:** Learn-mode + bias-provenance prober.
**Tools:** Read, Grep, Bash.

## Role in fleet

Validates the out-of-band Sonnet categorizer writes patterns to `patterns` table from the C1-locked target session, bias threads through to a downstream decision via `decision_suggestions`, HITL gate is never auto-bypassed, AND the target project's INTENT-derived "routine" command class graduates to ALLOW patterns within the POC window.

## Inputs

- C1's locked triple.
- POC window start timestamp.
- Bus DB / `patterns` + `decision_suggestions` tables (read-only).
- `docs/learn-mode-design.md` §2.3 (HITL non-bypass), §3.1 (data flow), §7 (learn_sources config).
- `src/stream_manager/learn_mode.py` + `learn_categorizer.py` (read-only).
- INTENT.md §"What governance should learn from this project".

## Steps

1. Query `patterns` for `source_session_id == C1.sessionId` AND `created_at >= POC window start`.
2. Pick one `pattern_id`.
3. Query `decision_suggestions` for `pattern_id`; confirm ≥ 1 attached decision.
4. For each attached decision row, confirm `bypass_hitl != 1`.
5. Look for `kind == "routine"` patterns from the target project; record decay-clock state if POC window too short.

## PASS criteria

- ≥ 1 categorizer write in window.
- ≥ 1 bias attached to a downstream decision.
- 0 HITL bypasses.
- (Soft) Routine commands graduated OR decay state documented.

## Outputs to coordinator

- `pattern_id` evidence.
- §4 INTENT §"What governance should learn" row read.

## Failure modes

- `no-categorizer-writes` — Learn Mode wire is broken or no qualifying turns in window; FAIL.
- `hitl-bypass-detected` — HARD FAIL on a Learn-Mode design-doc invariant.

## Refs

- `docs/learn-mode-design.md` §2.3, §3.1, §7.
- `src/stream_manager/learn_mode.py`, `learn_categorizer.py`.
- INTENT.md §"What governance should learn from this project".
- `feedback_cassette_must_cover_new_envelopes.md`.
