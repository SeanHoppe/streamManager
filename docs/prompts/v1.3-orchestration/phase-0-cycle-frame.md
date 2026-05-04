You are implementing **Phase P0 — Cycle frame + testing methodology** from the streamManager v1.3 cycle.

## Status

This phase is the framing PR itself — the PR that creates `docs/v1.3-task-plan.md`, `docs/v1.3-testing.md`, `docs/v1.4-backlog.md`, and the ten `docs/prompts/v1.3-orchestration/phase-*.md` prompts (including this file).

After merge, fill the line below with the merge commit SHA so the orchestration directory is a complete record of the cycle:

- Shipped <date> @ <commit-sha>; PR #<n>

This file is kept on disk so that the orchestration directory is complete and self-referential. There is no further work for P0 once the framing PR merges.

## Branch + base

- Base: `main`.
- PR target: `main`.
- Branch: `docs/v1.3-cycle-frame` (or successor if the framing PR is rebased).

## ⚠️ CRITICAL: Do-not-touch guard

P0 is **docs only**. Zero code edits. Do not touch anything under `src/`, `tests/`, `tools/`, `dashboard/`. If the diff stat shows ANY non-docs file, STOP — scope creep.

Pre-flight check:

```
git --no-pager diff origin/main..HEAD --stat -- src tests tools dashboard
```

Expect empty output. Any rows: STOP and report.

## Task brief

Create the four framing artifacts:

1. `docs/v1.3-task-plan.md` — mirrors `docs/v1.2-task-plan.md` style
2. `docs/v1.3-testing.md` — three operator-in-the-loop test methods
3. `docs/v1.4-backlog.md` — seed file with two items
4. `docs/prompts/v1.3-orchestration/phase-{0..5e}-*.md` — ten prompt files

Reference: `docs/prompts/v1.2-orchestration/task-a-soak-cassette.md` for prompt format.

## DOD

- [ ] All four artifact groups created
- [ ] `git --no-pager diff origin/main..HEAD --stat` shows only `docs/`
- [ ] No protected-symbol drift (no code touched at all)
- [ ] Single PR against `main`

## Final verification before opening PR

```
git --no-pager diff origin/main..HEAD --stat
```

Expected file list:
- `docs/v1.3-task-plan.md`
- `docs/v1.3-testing.md`
- `docs/v1.4-backlog.md`
- `docs/prompts/v1.3-orchestration/phase-0-cycle-frame.md`
- `docs/prompts/v1.3-orchestration/phase-1-driver-recorder-hardening.md`
- `docs/prompts/v1.3-orchestration/phase-2-list-active-jobs-windowed.md`
- `docs/prompts/v1.3-orchestration/phase-3-requirements-fr-og-audit.md`
- `docs/prompts/v1.3-orchestration/phase-4-code-quality-sweep.md`
- `docs/prompts/v1.3-orchestration/phase-5a-learn-mode-design.md`
- `docs/prompts/v1.3-orchestration/phase-5b-jsonl-tail-extension.md`
- `docs/prompts/v1.3-orchestration/phase-5c-sonnet-categorizer.md`
- `docs/prompts/v1.3-orchestration/phase-5d-advisory-bias.md`
- `docs/prompts/v1.3-orchestration/phase-5e-tests-decay.md`

If any non-docs file appears, STOP — scope creep.

No pytest run required (docs only).

Report back when PR is open with: PR URL, diff stat.
