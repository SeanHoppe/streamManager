# Task — Robin capability hooks (#116 + #117): PreToolUse Bash<5min + sqlite3 deny

> Combined low-pri hardening task. Pairs two issues that both target
> robin subagent capability layer. Run when robin is heavily used OR
> as v2.2 standalone hardening PR.

## Why combined

- Both edit `.claude/settings.json` or `.claude/settings.local.json`.
- Both shift soft prompt-rules → hard capability-layer enforcement.
- Both require the same pre-spike (can PreToolUse distinguish robin
  from main?).

## Pre-spike (BLOCKING — answer before implementation)

**Question:** can `.claude` PreToolUse hooks distinguish calling agent
(main thread vs `robin` subagent)?

- If YES → hooks can target `agent: robin` and main keeps long-Bash +
  direct-sqlite3 rights.
- If NO → hook applies repo-wide. Main loses long-Bash (UNACCEPTABLE
  — main owns Tier-3 soaks per `feedback_subagent_long_task_abandonment.md`).
  Fallback: scope deny to specific commands (`soak_driver.py`,
  `pytest -k soak`) and accept partial coverage.

**How to spike:** read `.claude/settings.json` schema docs OR run a
minimal hook that logs `$CLAUDE_AGENT_NAME` (or equivalent env) +
trigger once from main, once via robin. Record finding.

## Part 1 — #116 Bash < 5 min for robin

PowerShell hook `.claude/hooks/robin-bash-timeout.ps1`:

```powershell
# Reject Bash tool calls from robin subagent that have no timeout
# OR timeout > 300000 ms. Soft cap per memory
# feedback_subagent_long_task_abandonment.md.

param([string]$ToolName, [string]$AgentName, [string]$ToolArgsJson)
if ($AgentName -ne 'robin') { exit 0 }
if ($ToolName  -ne 'Bash')  { exit 0 }
$args = $ToolArgsJson | ConvertFrom-Json
if ($null -eq $args.timeout)         { Write-Error 'robin Bash requires timeout'; exit 1 }
if ($args.timeout -gt 300000)        { Write-Error 'robin Bash timeout > 5min'; exit 1 }
exit 0
```

Wire in `.claude/settings.json` PreToolUse handler for `agent: robin`,
`tool: Bash`.

Acceptance:

- Robin Bash with no timeout → rejected.
- Robin Bash `timeout: 600000` → rejected.
- Robin Bash `timeout: 60000` → allowed.
- Main `run_in_background` long soaks → still allowed.

## Part 2 — #117 sqlite3 deny against RL DBs

Add to `permissions.deny` in `.claude/settings.local.json` (or
`.claude/settings.json` — operator choice based on whether the rule is
local-only or repo-shared):

```jsonc
{
  "permissions": {
    "deny": [
      "Bash(sqlite3 *rl_episodes.db*)",
      "Bash(sqlite3 *rl_shadow.db*)"
    ]
  }
}
```

Symmetric: applies to both main and robin. Python `import sqlite3`
remains allowed (deny matches the `sqlite3` CLI binary, not Python
module imports). Helper `tools/rl_test_helper/db_summary.py` opens
DBs read-only via Python module — unaffected.

Acceptance:

- `Bash sqlite3 rl_episodes.db "SELECT 1"` from robin OR main → denied.
- `python -c 'import sqlite3; sqlite3.connect("file:rl_episodes.db?mode=ro", uri=True)'`
  → allowed.
- `python -m tools.rl_test_helper.db_summary ...` → allowed.

Risk audit before merge:

```bash
# Confirm no legit invocation will be caught.
grep -rn 'sqlite3 .*rl_(episodes|shadow)\.db' . --include='*.md' --include='*.py' --include='*.sh' --include='*.ps1'
```

## DOD

- [ ] Pre-spike answered + recorded in PR body.
- [ ] If pre-spike NO: scope-narrowed fallback documented; #116 either
      lands narrow or defers to capability-layer upstream fix.
- [ ] `.claude/hooks/robin-bash-timeout.ps1` lands (or equivalent
      fallback per pre-spike).
- [ ] `.claude/settings.local.json` (or settings.json) deny rules land.
- [ ] Manual test matrix run (5 cases above for both #116 and #117).
- [ ] Risk audit grep clean.
- [ ] Issues #116 + #117 closed on merge.

## ADR-18 posture

Settings + hook scripts; no `src/` touch. LOC ~50 (hook) + ~10 JSON.
No FROZEN seam.

## Cross-references

- Issue #116: `docs/jobs/issue-116.md`.
- Issue #117: `docs/jobs/issue-117.md`.
- Memory `feedback_subagent_long_task_abandonment.md`,
  `project_v10_rl_track.md`.
- Robin agent: `.claude/agents/robin.md`, PR #115, commit `24bc1d6`.
