You are implementing **Phase P0 — Cycle frame** from the streamManager v1.7 cycle.

## Status

This phase is the framing PR itself — the PR that creates `docs/v1.7-task-plan.md`, `docs/v1.8-backlog.md`, and the four `docs/prompts/v1.7-orchestration/phase-*.md` prompts (including this file).

`docs/v1.7-backlog.md` already exists (seeded post-v1.6 ship-gate at HEAD `6866dad` via the v1.6 P2 S8 phase). This phase wraps that seed in the cycle scaffolding and is otherwise docs-only. Do NOT mutate `docs/v1.7-backlog.md` — backlog hygiene only (rule: emoji frozen at landing time).

After merge, fill the line below with the merge commit SHA so the orchestration directory is a complete record of the cycle:

- Shipped <DATE> @ <SHA>; PR #<n>

## Branch + base

- Base: `main` (v1.6.0 tagged at `6866dad`).
- PR target: `main`.
- Branch: `docs/v1.7-cycle-frame` (or operator's choice).
- If `main` is unexpectedly behind v1.6.0, ABORT and tell the user.

## ⚠️ CRITICAL: Do-not-touch guard

P0 is **docs only**. Zero code edits. Do not touch anything under `src/`, `tests/`, `tools/`, `dashboard/`. If the diff stat shows ANY non-docs file, STOP — scope creep.

Pre-flight check:

```
git --no-pager diff origin/main..HEAD --stat -- src tests tools dashboard
```

Expect empty output. Any rows: STOP and report.

## Task brief

v1.7 cycle scope is narrow. Three engineering phases plus a ship-gate. Lever is data-driven from v1.6 ship-gate (driver = `cli_pool_send_ms` → Haiku fastpath primary; pool sizing >2 fallback). Create the framing artifacts:

1. `docs/v1.7-task-plan.md` — mirrors `docs/v1.6-task-plan.md` style. Reference the seeded `docs/v1.7-backlog.md`. Phase summary table:
   | Phase | Title | Effort | Depends on | Prompt |
   |---|---|---|---|---|
   | P0 | Cycle frame (THIS doc) | ¼ session | — | `phase-0-cycle-frame.md` |
   | P1 | L4 alignment eval harness (golden-set verdicts, ship-gate gate) | 1 session | P0 | `phase-1-alignment-eval-harness.md` |
   | P2 | Haiku fastpath router (widen Haiku surface for L4 / ambiguous-BLOCK) | 1 session | P1 merged + green | `phase-2-haiku-fastpath-router.md` |
   | P3 | v1.7 ship-gate + ADR-5 v1.7 baseline + LM watch resolution | ½ session | P2 merged | `phase-3-ship-gate-finalize.md` |

2. `docs/v1.8-backlog.md` — empty seed file with the convention block (mirrors `docs/v1.7-backlog.md` structure, no items yet — only carry-forward candidates noted).

3. `docs/prompts/v1.7-orchestration/phase-{0,1,2,3}-*.md` — four prompt files (THIS file is one of them; verify P1 + P2 + P3 prompts are committed alongside).

Reference docs to cite in `docs/v1.7-task-plan.md`:
- `docs/adr/ADR-5-latency-budget.md` — v1.6 ship-gate baseline §"Caveats" (load-bearing for P2 scope; documents driver localisation to `cli_pool_send_ms` and names Haiku fastpath as the primary v1.7 lever)
- `docs/v1.7-backlog.md` — seeded items (4: Haiku fastpath, CLI pool sizing >2, LM categorize watch, PPP audit harness)
- `docs/v1.6-backlog.md` — predecessor (now closed-out)
- `reports/soak-20260505T073943Z.md` — v1.6 ship-gate report (source of the lever pick + LM watch)
- `src/stream_manager/model_router.py` — current band → model mapping (read, do not edit in P0)
- Memory: `feedback_subagent_stale_mental_model.md`, `feedback_no_self_monitor.md`, `feedback_soak_cli_pool_flag.md`, `feedback_cassette_must_cover_new_envelopes.md`, `feedback_cross_pr_seam_review.md`, `feedback_subagent_long_task_abandonment.md`

## DOD

- [ ] All three artifact groups created (`v1.7-task-plan.md`, `v1.8-backlog.md`, four phase prompts)
- [ ] `docs/v1.7-backlog.md` left UNCHANGED (frozen-emoji rule)
- [ ] `git --no-pager diff origin/main..HEAD --stat` shows only `docs/`
- [ ] No protected-symbol drift (no code touched at all)
- [ ] Single PR against `main`

## Final verification before opening PR

```
git --no-pager diff origin/main..HEAD --stat
```

Expected file list:
- `docs/v1.7-task-plan.md` (new)
- `docs/v1.8-backlog.md` (new)
- `docs/prompts/v1.7-orchestration/phase-0-cycle-frame.md` (new)
- `docs/prompts/v1.7-orchestration/phase-1-alignment-eval-harness.md` (new)
- `docs/prompts/v1.7-orchestration/phase-2-haiku-fastpath-router.md` (new)
- `docs/prompts/v1.7-orchestration/phase-3-ship-gate-finalize.md` (new)

If any non-docs file appears, STOP — scope creep.

No pytest run required (docs only).

Report back when PR is open with: PR URL, diff stat.
