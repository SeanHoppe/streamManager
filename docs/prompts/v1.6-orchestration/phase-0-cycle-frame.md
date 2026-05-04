You are implementing **Phase P0 — Cycle frame** from the streamManager v1.6 cycle.

## Status

This phase is the framing PR itself — the PR that creates `docs/v1.6-task-plan.md`, `docs/v1.7-backlog.md`, and the three `docs/prompts/v1.6-orchestration/phase-*.md` prompts (including this file).

`docs/v1.6-backlog.md` already exists (seeded post-v1.5 ship-gate at HEAD `95ffb83`). This phase wraps that seed in the cycle scaffolding and is otherwise docs-only. If `docs/v1.6-backlog.md` is empty / lacks the v1.5 falsification follow-up seed item (residue localization), append the seed item in this same PR.

After merge, fill the line below with the merge commit SHA so the orchestration directory is a complete record of the cycle:

- Shipped <date> @ <commit-sha>; PR #<n>

## Branch + base

- Base: `main` (v1.5.0 tagged at `95ffb83`).
- PR target: `main`.
- Branch: `docs/v1.6-cycle-frame` (or operator's choice).
- If `main` is unexpectedly behind v1.5.0, ABORT and tell the user.

## ⚠️ CRITICAL: Do-not-touch guard

P0 is **docs only**. Zero code edits. Do not touch anything under `src/`, `tests/`, `tools/`, `dashboard/`. If the diff stat shows ANY non-docs file, STOP — scope creep.

Pre-flight check:

```
git --no-pager diff origin/main..HEAD --stat -- src tests tools dashboard
```

Expect empty output. Any rows: STOP and report.

## Task brief

v1.6 cycle scope is narrow. One backlog seed (residue localization), one engineering phase, one ship-gate phase. Create the framing artifacts:

1. `docs/v1.6-task-plan.md` — mirrors `docs/v1.5-task-plan.md` style. Reference the seeded `docs/v1.6-backlog.md`. Phase summary table:
   | Phase | Title | Effort | Depends on | Prompt |
   |---|---|---|---|---|
   | P0 | Cycle frame (THIS doc) | ¼ session | — | `phase-0-cycle-frame.md` |
   | P1 | `_evaluate_inner` CLI residue instrumentation | 1 session | P0 | `phase-1-cli-residue-instrumentation.md` |
   | P2 | v1.6 ship-gate + ADR-5 v1.6 baseline + driver localization | ½ session | P1 merged | `phase-2-ship-gate-finalize.md` |

2. `docs/v1.7-backlog.md` — empty seed file with the convention block (mirrors `docs/v1.6-backlog.md` structure, no items yet).

3. `docs/prompts/v1.6-orchestration/phase-{0,1,2}-*.md` — three prompt files (THIS file is one of them; verify P1 + P2 prompts are committed alongside).

Reference docs to cite in `docs/v1.6-task-plan.md`:
- `docs/adr/ADR-5-latency-budget.md` — v1.5 ship-gate baseline §"Caveats" (load-bearing for P1 scope; documents the falsification of the v1.4 sub-phase-tail hypothesis)
- `docs/v1.6-backlog.md` — seeded items
- `docs/v1.5-backlog.md` — predecessor (now closed-out)
- `reports/soak-20260504T201714Z.md` — v1.5 ship-gate report (source of the residue-localization scope)
- Memory: `feedback_subagent_stale_mental_model.md`, `feedback_no_self_monitor.md`, `feedback_soak_cli_pool_flag.md`, `feedback_cassette_must_cover_new_envelopes.md`, `feedback_cross_pr_seam_review.md`, `feedback_subagent_long_task_abandonment.md`

## DOD

- [ ] All three artifact groups created (`v1.6-task-plan.md`, `v1.7-backlog.md`, three phase prompts)
- [ ] `docs/v1.6-backlog.md` contains the v1.5 falsification follow-up seed item (residue localization); if empty, append in this PR
- [ ] `git --no-pager diff origin/main..HEAD --stat` shows only `docs/`
- [ ] No protected-symbol drift (no code touched at all)
- [ ] Single PR against `main`

## Final verification before opening PR

```
git --no-pager diff origin/main..HEAD --stat
```

Expected file list:
- `docs/v1.6-backlog.md` (modified — seed item appended IF previously empty)
- `docs/v1.6-task-plan.md` (new)
- `docs/v1.7-backlog.md` (new)
- `docs/prompts/v1.6-orchestration/phase-0-cycle-frame.md` (new)
- `docs/prompts/v1.6-orchestration/phase-1-cli-residue-instrumentation.md` (new)
- `docs/prompts/v1.6-orchestration/phase-2-ship-gate-finalize.md` (new)

If any non-docs file appears, STOP — scope creep.

No pytest run required (docs only).

Report back when PR is open with: PR URL, diff stat.
