You are implementing **Phase P0 — Cycle frame** from the streamManager v1.5 cycle.

## Status

This phase is the framing PR itself — the PR that creates `docs/v1.5-task-plan.md`, `docs/v1.6-backlog.md`, and the three `docs/prompts/v1.5-orchestration/phase-*.md` prompts (including this file).

`docs/v1.5-backlog.md` already exists (seeded post-v1.4 ship-gate at HEAD `8b50f47`). This phase wraps that seed in the cycle scaffolding and is otherwise docs-only.

After merge, fill the line below with the merge commit SHA so the orchestration directory is a complete record of the cycle:

- Shipped <date> @ <commit-sha>; PR #<n>

## Branch + base

- Base: `main` (v1.4.0 tagged at `8b50f47`).
- PR target: `main`.
- Branch: `docs/v1.5-cycle-frame` (or operator's choice).
- If `main` is unexpectedly behind v1.4.0, ABORT and tell the user.

## ⚠️ CRITICAL: Do-not-touch guard

P0 is **docs only**. Zero code edits. Do not touch anything under `src/`, `tests/`, `tools/`, `dashboard/`. If the diff stat shows ANY non-docs file, STOP — scope creep.

Pre-flight check:

```
git --no-pager diff origin/main..HEAD --stat -- src tests tools dashboard
```

Expect empty output. Any rows: STOP and report.

## Task brief

v1.5 cycle scope is narrow. Two backlog items, one engineering phase, one ship-gate phase. Create the framing artifacts:

1. `docs/v1.5-task-plan.md` — mirrors `docs/v1.3-task-plan.md` style. Reference the seeded `docs/v1.5-backlog.md`. Phase summary table:
   | Phase | Title | Effort | Depends on | Prompt |
   |---|---|---|---|---|
   | P0 | Cycle frame (THIS doc) | ¼ session | — | `phase-0-cycle-frame.md` |
   | P1 | `_evaluate_inner` sub-phase instrumentation | 1 session | P0 | `phase-1-evaluate-inner-instrumentation.md` |
   | P2 | v1.5 ship-gate + ADR-5 v1.5 baseline + LM trend re-check | ½ session | P1 merged | `phase-2-ship-gate-finalize.md` |

2. `docs/v1.6-backlog.md` — empty seed file with the convention block (mirrors `docs/v1.5-backlog.md` structure, no items yet).

3. `docs/prompts/v1.5-orchestration/phase-{0,1,2}-*.md` — three prompt files (THIS file is one of them; verify P1 + P2 prompts are committed alongside).

Reference docs to cite in `docs/v1.5-task-plan.md`:
- `docs/adr/ADR-5-latency-budget.md` — v1.4 ship-gate baseline §"Caveats" (load-bearing for P1 scope)
- `docs/v1.5-backlog.md` — seeded items
- `docs/v1.4-backlog.md` — predecessor (now closed-out)
- Memory: `feedback_subagent_stale_mental_model.md`, `feedback_no_self_monitor.md`, `feedback_soak_cli_pool_flag.md`, `feedback_cassette_must_cover_new_envelopes.md`, `feedback_cross_pr_seam_review.md`

## DOD

- [ ] All three artifact groups created (`v1.5-task-plan.md`, `v1.6-backlog.md`, three phase prompts)
- [ ] `git --no-pager diff origin/main..HEAD --stat` shows only `docs/`
- [ ] No protected-symbol drift (no code touched at all)
- [ ] Single PR against `main`

## Final verification before opening PR

```
git --no-pager diff origin/main..HEAD --stat
```

Expected file list:
- `docs/v1.5-backlog.md` (already on branch from prior commit; may or may not be in this PR's diff depending on operator choice)
- `docs/v1.5-task-plan.md` (new)
- `docs/v1.6-backlog.md` (new)
- `docs/prompts/v1.5-orchestration/phase-0-cycle-frame.md` (new)
- `docs/prompts/v1.5-orchestration/phase-1-evaluate-inner-instrumentation.md` (new)
- `docs/prompts/v1.5-orchestration/phase-2-ship-gate-finalize.md` (new)

If any non-docs file appears, STOP — scope creep.

No pytest run required (docs only).

Report back when PR is open with: PR URL, diff stat.
