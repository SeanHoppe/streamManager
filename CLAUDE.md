# streamManager (SM) — Project Instructions

## Firewall: certPortal isolation

**SM dev sessions MUST NOT reach into the certPortal repo.** Hard boundary. Repo location: `C:\Users\SeanHoppe\VS\certPortal\` (sibling of SM under `C:\Users\SeanHoppe\VS\`).

### Why

SM = domain-agnostic governance product. certPortal = one **runtime target** SM governs (via learn-mode JSONL-tail of certPortal Claude Code sessions). Coupling lives in SM product code — NOT license for SM dev session (this Claude Code session) to operate on certPortal repo state. Crossing boundary contaminates SM context, routes operator-personal certPortal queue items (PRs, incidents, JOBs) through SM agents — out of scope.

### What is prohibited

- Reading any file under `**/certPortal/**` or `C:\Users\SeanHoppe\VS\certPortal\**`
- Glob / Grep against any certPortal path
- Bash / `gh` operations targeting certPortal repo
- Spawning sub-agents to triage / fix certPortal issues, JOBs, incidents, PRs
- Editing SM source/docs to add new certPortal coupling beyond already-designed (learn-mode source registry, project_context, agent_profiles)

Enforced via `.claude/settings.local.json` `permissions.deny` patterns. Deny rule fires → do NOT work around. Surface to operator.

### What is allowed

- Reading SM source/docs that **textually reference** certPortal as test/demo target (e.g. `docs/learn-mode-design.md`, `src/stream_manager/project_context.py`). SM-internal.
- Modifying SM certPortal-aware modules when change is SM-scoped (e.g. extending learn-mode parser, refactoring project_context). Change stay SM-side; do not edit anything inside certPortal repo to make SM work.
- SM runtime (production) reading certPortal session JSONL — product. Firewall = **dev-session boundary**, not runtime.

### Operator queue separation

Sean MEMORY.md surfaces certPortal items (PRs, INCs, MASTER JOBs, JOB-XXXX entries) as **operator awareness context**, NOT work-targets for SM dispatch. Asked to act on certPortal item → refuse, suggest operator open Claude Code session inside certPortal repo.

## Session-source exception rule (polarity-flip)

SM monitors **NON-SM sessions**, never itself. Default-exclude SM by project-slug. Concrete rule for any corpus / replay / ingest / OPE / training code path reading from `.claude/gov.db` or session transcripts:

```
INCLUDE iff session.project_slug NOT IN (STREAM_MANAGER_PROJECT_SLUGS)
        AND session_id != BRIDGE_SM_SELF_SESSION_ID
```

- Default `STREAM_MANAGER_PROJECT_SLUGS = {"streamManager"}`.
- Override via env `BRIDGE_SM_PROJECT_SLUGS` (comma-separated) for worktree slug variants.
- Filter at SQL `WHERE`, not post-hoc Python. Default-exclude makes leakage loud failure path (zero rows surface) instead of silent corpus-poisoning.
- **Enforcement split by time, not duplicated at read.** `session_id != BRIDGE_SM_SELF_SESSION_ID` half = WRITE-time gate (`episode_logger` raises `SelfMonitorRefusal`); that env var names *current* session, meaningless vs historical rows → NOT in read-side `WHERE`. `project_slug NOT IN (STREAM_MANAGER_PROJECT_SLUGS)` half = durable read-side key, the only term in the read-side SQL `WHERE`. "Filter at SQL `WHERE`" governs the project_slug half; the session_id half is the write-time gate. Adding session_id to the read `WHERE` is inert-to-harmful — do NOT.

Cross-ref: `feedback_no_self_monitor.md` §"Polarity flip"; rationale in `reports/proposals/2026-06-11-polarity-dual-key-read-write-split.proposal.md`.

## Zero contamination from monitored repo

SM source/docs/tests/fixtures must NOT contain certPortal-specific (or any monitored-project-specific) paths, JOB IDs, agent-role names, domain logic, extracted artifacts, PR scope. SM = domain-agnostic; monitored project = configuration, not vocabulary. Reference fine; logic that only works for one target = contamination.

Cross-ref: `feedback_certportal_dev_firewall.md` §"Zero-contamination rule".

## Other project rules

- ADR-18 surface-freeze list = law for v10 / v10.x cycles. See `docs/adr/ADR-18-mvp-surface-freeze.md`.
- Long-running tasks (>5 min) launch from main thread via `run_in_background` + `ScheduleWakeup`, never from sub-agents (`feedback_subagent_long_task_abandonment.md`).
- `robin` agent owns v10 RL test verification (P1–P5). Engage robin for post-soak ingest verdicts, OPE validation roll-ups, ship-gate checks. Do NOT use generic agents for v10 RL verification when robin playbook covers case.

## Coding-nuance memory

Sean persistent coding style, approach nuances, do-not-do rules live in `./MEMORY.md` (checked in, project-root). **Read at session start, update whenever Sean teaches new preference.** Distinct from auto-memory store under `C:\Users\SeanHoppe\.claude\projects\C--Users-SeanHoppe-vs-streamManager\memory\` (per-topic, machine-managed, not checked in).