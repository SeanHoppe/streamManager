# Phase 0 — Land Uncommitted Changes

**Sequence:** First. No dependencies.
**Estimated time:** < 5 minutes.
**FR refs:** None — git hygiene only.

---

## Context

Two files were edited after the last `pull+merge` (`46d9403`) and are uncommitted:
- `REQUIREMENTS.md` — bumped to v1.6, added FR-OG-7 maturity-ring alignment signals
- `src/stream_manager/agent_profiles.yaml` — spotlight comment updated to include
  `instructions/MVP-100-PLAN.md` and `maturity-dashboard.html`

These must land on `main` before any implementation work begins so the spec
and implementation are never ahead of each other on different branches.

---

## Prompt

```
Commit the two uncommitted files in this worktree and merge them to main.

Files to commit:
  - REQUIREMENTS.md
  - src/stream_manager/agent_profiles.yaml

Commit message (use exactly):
  docs(requirements): v1.6 — FR-OG-7 maturity-ring governance + certPortal spotlight

Steps:
  1. git add REQUIREMENTS.md src/stream_manager/agent_profiles.yaml
  2. git commit with the message above
  3. git push origin HEAD
  4. gh pr create targeting main with title "docs(requirements): v1.6 FR-OG-7 + certPortal spotlight"
  5. gh pr merge --merge --delete-branch (or squash if preferred)
  6. Confirm main is up to date with: git log origin/main --oneline -3

Do not modify any other files. Do not run tests (no code changed).
```

---

## STOP + VERIFY

Before marking Phase 0 complete, confirm **all** of the following:

- [ ] `git status` shows no uncommitted changes in tracked files
- [ ] `git log origin/main --oneline -1` shows the FR-OG-7 commit at HEAD
- [ ] `REQUIREMENTS.md` on `main` contains section `FR-OG-7` and revision `v1.6`
- [ ] `src/stream_manager/agent_profiles.yaml` on `main` contains `MVP-100-PLAN.md` in spotlight comment
- [ ] No other files were modified or committed

**If any check fails:** do not proceed to Phase 1. Fix the git state first.

---

## Definition of Done

`main` branch contains v1.6 REQUIREMENTS.md with FR-OG-7 and the updated
agent_profiles.yaml spotlight comment. Worktree is clean.
