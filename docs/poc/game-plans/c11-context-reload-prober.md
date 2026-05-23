# C11 — `context-reload-prober` game plan

**Agent file:** `.claude/agents/context-reload-prober.md`
**Role:** Project-context-loading prober (INTENT §"Project context loading").
**Tools:** Read, Write, Grep, Bash.

## Role in fleet

Validates the four INTENT.md §"Project context loading" invariants in one shot:
1. 10 s debounce reload on monitored-file change.
2. 400-token excerpt budget.
3. INTENT > REQUIREMENTS > CLAUDE.md > README rank order.
4. Mid-session refresh delivers new content into next decision's alignment context.

## Inputs

- Operator-pre-approved target `INTENT.md` path under a non-SM, non-firewalled project root (passed by coordinator).
- C1's locked triple.
- `src/stream_manager/project_context.py` (FROZEN; read-only).
- Bus DB / decisions table (read-only).
- INTENT.md §"Project context loading".

## Steps

1. Read project_context.py's rank list; confirm matches INTENT order.
2. Capture target file pre-edit SHA-256.
3. Edit: insert unique marker line + 1–2 sentences distinctive content.
4. Wait 12 s (10 s debounce + 2 s tolerance).
5. Trigger one envelope (cassette OR operator turn via coordinator relay).
6. Query resulting decision's `metadata_json.alignment_context`; confirm marker present.
7. Sum token count of alignment_context excerpts; confirm ≤ 400.
8. Confirm excerpt ordering matches rank list (if all four ranks present in target project).
9. **REVERT** file; verify SHA matches pre-edit.

## PASS criteria

- Rank list in source matches INTENT.
- Marker surfaces in next decision within 12 s.
- Token budget ≤ 400.
- Rank order honored.
- Revert SHA matches pre-edit SHA.

## Hard rules

- NEVER modify SM's own `INTENT.md` (polarity flip).
- NEVER modify any file under `C:\Users\SeanHoppe\VS\certPortal\` (firewall).
- ALWAYS revert at end of probe (even on partial failure).
- Operator must pre-approve target path; otherwise FAIL `no-approved-target`.

## Outputs to coordinator

- §4 INTENT §"Project context loading" row read (PASS/FAIL with which sub-row).

## Failure modes

- `no-approved-target` — operator did not supply path.
- `marker-not-observed` — debounce or refresh failed.
- `budget-exceeded` — alignment_context > 400 tokens.
- `rank-order-violated` — README ranked above INTENT, etc.
- `revert-sha-mismatch` — HARD FAIL; file left in modified state; operator must inspect.

## Refs

- INTENT.md §"Project context loading".
- `src/stream_manager/project_context.py` (FROZEN per ADR-18 + INTENT §"Hot zones").
