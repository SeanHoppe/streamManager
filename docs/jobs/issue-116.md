# #116 — robin: enforce Bash < 5 min via PreToolUse hook (capability constraint)

**Status:** OPEN — low pri. Run when robin heavily used.
**Bucket:** robin side track.
**GH:** https://github.com/SeanHoppe/streamManager/issues/116

## Why

`robin` subagent system prompt has rule "NEVER launch any Bash command expected to run > 5 min" =
soft (prompt-only). No per-tool timeout cap in subagent format. Memory
`feedback_subagent_long_task_abandonment.md`: long-running Bash from subagent = abandonment risk
(orphaned processes). Capability-layer hook = belt-and-suspenders.

## Scope

- PreToolUse hook in `.claude/settings.json` (or `.claude/settings.local.json`) keyed on `agent: robin`.
- PowerShell hook (e.g. `.claude/hooks/robin-bash-timeout.ps1`) inspects proposed Bash invocation:
  - Reject if no `timeout` param.
  - Reject if `timeout > 300000` (ms).
- **Spike first:** confirm PreToolUse can distinguish calling agent (main vs robin). If not, hook
  applies repo-wide → main loses long-Bash right (unacceptable; main owns Tier 3 soaks). In that
  case, look for per-agent settings or scope deny to specific commands (`soak_driver.py`, `pytest -k soak`).

## Acceptance

- Robin Bash with no timeout → hook rejects.
- Robin Bash `timeout: 600000` → hook rejects.
- Robin `Bash python -m pytest tests/test_rl_test_helper.py` `timeout: 60000` → allowed.
- Main `run_in_background` long soaks still allowed.

## Refs

- PR #115.
- `feedback_subagent_long_task_abandonment.md`.
- `feedback_monitoring_live_sessions.md`.
