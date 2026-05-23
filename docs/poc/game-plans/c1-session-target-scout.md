# C1 — `session-target-scout` game plan

**Agent file:** `.claude/agents/session-target-scout.md`
**Role:** Session-locator. Returns the locked `{pid, sessionId, cwd, projectSlug}` triple.
**Tools:** Read, Glob, Bash.

## Role in fleet

First in fire order. Without a locked non-SM target, nothing downstream is valid. Also captures observed Desktop sub-agent topology so C4 + C10 can ground their role-binding probes.

## Inputs

- `~/.claude/sessions/` (Glob enumeration).
- `~/.claude/projects/` (Glob; project-slug enumeration only — does NOT read transcript content).
- Env: `BRIDGE_SM_PROJECT_SLUGS`, `BRIDGE_SM_SELF_SESSION_ID`.
- `feedback_session_monitor_target.md` (binding rule for ranking + exclusion).

## Steps

1. Enumerate session records under `~/.claude/sessions/`.
2. Extract `{pid, sessionId, cwd, projectSlug, updatedAt, status}` per record.
3. Filter: exclude SM slugs, exclude self sessionId, exclude `cwd` under `C:\Users\SeanHoppe\VS\certPortal\`, exclude dead PIDs.
4. Rank: `status == "busy"` first, then `updatedAt` desc.
5. Lock top candidate.
6. Record observed Desktop sub-agent roles (Prompt Constructor / Developer / Code Reviewer / Tester / Other) from recent envelopes.

## PASS criteria

- A single triple emitted, all four fields non-empty.
- `projectSlug` not in `BRIDGE_SM_PROJECT_SLUGS`.
- `cwd` not under certPortal repo source.
- PID alive.

## Outputs to coordinator

- Locked triple → C2, C3, C4, C5, C7, C9, C11 all bind to this target.
- Observed topology → C4, C10 use for role-binding probes.

## Failure modes

- `NO-TARGET no-live-sessions` — no live non-SM session at scout time.
- `NO-TARGET all-excluded` — every observed session is SM-self or firewalled.

## Refs

- `feedback_session_monitor_target.md`.
- `feedback_no_self_monitor.md`.
- `feedback_certportal_dev_firewall.md`.
- INTENT.md §"What this project is" + §"Sub-agent governance principles".
