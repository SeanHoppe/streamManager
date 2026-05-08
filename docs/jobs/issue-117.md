# #117 — robin: deny direct `sqlite3` mutation against `rl_episodes.db` / `rl_shadow.db`

**Status:** OPEN — low pri. Run when robin heavily used.
**Bucket:** robin side track.
**GH:** https://github.com/SeanHoppe/streamManager/issues/117

## Why

robin has Bash. Helper `tools/rl_test_helper/db_summary.py` opens `mode=ro` URI = code-level RO.
Robin could bypass helper + run `sqlite3 rl_episodes.db "INSERT ..."` direct via Bash. PR #115 R3:
prompt rule "NEVER write to rl_episodes.db" = soft; capability = hard. Two-agent split rejected as
over-engineered (memory `project_v10_rl_track.md`). Right fix = settings-layer deny.

## Scope

Add to `.claude/settings.local.json` (or `.claude/settings.json`) `permissions.deny`:

```
"Bash(sqlite3 *rl_episodes.db*)"
"Bash(sqlite3 *rl_shadow.db*)"
```

Robin (and main, by symmetry) cannot run `sqlite3` against either RL DB. Helper still works
because it imports `sqlite3` as Python module — deny rule only blocks the CLI binary.

## Acceptance

- `Bash sqlite3 rl_episodes.db "SELECT 1"` from robin or main → denied.
- `python -c 'import sqlite3; sqlite3.connect("file:rl_episodes.db?mode=ro", uri=True)'` → allowed.
- `python -m tools.rl_test_helper.db_summary ...` → allowed.

## Risks

Pattern-match denial may catch unintended invocations. Audit with
`Grep "sqlite3 .*rl_(episodes|shadow)\.db"` before merging.

## Refs

- PR #115.
- `project_v10_rl_track.md` (split rejected; this = alternate protection).
