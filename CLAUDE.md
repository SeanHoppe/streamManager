# streamManager (SM) — Project Instructions

## Firewall: certPortal isolation

**SM dev sessions MUST NOT reach into the certPortal repo.** This is a hard
boundary. Repo location: `C:\Users\SeanHoppe\VS\certPortal\` (sibling of SM
under `C:\Users\SeanHoppe\VS\`).

### Why

SM is a domain-agnostic governance product. certPortal is one **runtime
target** SM governs (via learn-mode JSONL-tail of certPortal's Claude Code
sessions). That coupling lives in SM's product code — it is NOT license for
SM's dev session (this Claude Code session) to operate on certPortal's repo
state. Crossing that boundary contaminates SM's context and routes
operator-personal certPortal queue items (PRs, incidents, JOBs) through
SM agents — which is out of scope.

### What is prohibited

- Reading any file under `**/certPortal/**` or
  `C:\Users\SeanHoppe\VS\certPortal\**`
- Glob / Grep against any certPortal path
- Bash / `gh` operations targeting the certPortal repo
- Spawning sub-agents whose task is to triage / fix certPortal issues, JOBs,
  incidents, or PRs
- Editing SM source/docs to add new certPortal coupling beyond what is
  already designed in (learn-mode source registry, project_context,
  agent_profiles)

These are enforced via `.claude/settings.local.json` `permissions.deny`
patterns. If a deny rule fires, do NOT attempt to work around it. Surface
to the operator.

### What is allowed

- Reading SM's own source/docs that **textually reference** certPortal as a
  test/demo target (e.g. `docs/learn-mode-design.md`,
  `src/stream_manager/project_context.py`). These are SM-internal.
- Modifying SM's certPortal-aware modules when the change is SM-scoped
  (e.g. extending learn-mode parser, refactoring project_context). The
  change must remain SM-side; do not edit anything inside the certPortal
  repo to make SM work.
- SM runtime (production) reading certPortal session JSONL — that is the
  product. The firewall is a **dev-session boundary**, not a runtime one.

### Operator queue separation

Sean's MEMORY.md surfaces certPortal items (PRs, INCs, MASTER JOBs,
JOB-XXXX entries) as **operator awareness context**, NOT as work-targets
for SM dispatch. If asked to act on a certPortal item, refuse and suggest
the operator open a Claude Code session inside the certPortal repo
instead.

## Session-source exception rule (polarity-flip)

SM monitors **NON-SM sessions**, never itself. Default-exclude SM by
project-slug. Concrete rule for any corpus / replay / ingest / OPE / training
code path that reads from `.claude/gov.db` or session transcripts:

```
INCLUDE iff session.project_slug NOT IN (STREAM_MANAGER_PROJECT_SLUGS)
        AND session_id != BRIDGE_SM_SELF_SESSION_ID
```

- Default `STREAM_MANAGER_PROJECT_SLUGS = {"streamManager"}`.
- Override via env `BRIDGE_SM_PROJECT_SLUGS` (comma-separated) for worktree
  slug variants.
- Filter at SQL `WHERE`, not post-hoc Python. Default-exclude makes leakage
  the loud failure path (zero rows surface) rather than silent
  corpus-poisoning.

Cross-ref: `feedback_no_self_monitor.md` §"Polarity flip".

## Zero contamination from monitored repo

SM source/docs/tests/fixtures must NOT contain certPortal-specific (or any
monitored-project-specific) paths, JOB IDs, agent-role names, domain logic,
extracted artifacts, or PR scope. SM is domain-agnostic; the monitored
project is configuration, not vocabulary. Reference is fine; logic that
only works for one target is contamination.

Cross-ref: `feedback_certportal_dev_firewall.md` §"Zero-contamination rule".

## Other project rules

- ADR-18 surface-freeze list is law for v10 / v10.x cycles. See
  `docs/adr/ADR-18-mvp-surface-freeze.md`.
- Long-running tasks (>5 min) launch from main thread via
  `run_in_background` + `ScheduleWakeup`, never from sub-agents
  (`feedback_subagent_long_task_abandonment.md`).
- The `robin` agent owns v10 RL test verification (P1–P5). Engage robin
  for post-soak ingest verdicts, OPE validation roll-ups, ship-gate
  checks. Do NOT use generic agents for v10 RL verification when robin's
  playbook covers the case.
