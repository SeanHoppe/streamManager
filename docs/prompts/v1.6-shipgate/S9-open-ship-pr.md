# S9 — Open ship PR

**Goal:** Open PR from `ship/v1.6-shipgate-finalize` → `main` with docs-only
diff (ADR-5, CHANGELOG, soak report, optional v1.7-backlog).

## Context

Ship branch already rebased on main `380f453` and contains P0+P1+P1-fix.
S6, S7, S8 commits land on top of that branch. Soak report from S3 commits
to `reports/`.

## Steps

1. `git status` — confirm clean working tree (all S6/S7/S8 changes committed).
2. Stage + commit each phase output if not already:
   ```
   git add docs/adr/ADR-5-latency-budget.md
   git add CHANGELOG.md
   git add reports/soak-<ts>Z.md
   git add docs/v1.7-backlog.md  # if S8 wrote
   git commit -m "ship(v1.6.0): ship-gate baseline + ADR-5 v1.6 + driver finding"
   ```
3. Push: `git push -u origin ship/v1.6-shipgate-finalize`.
4. Open PR via `gh pr create`:
   - Title: `ship(v1.6.0): ship-gate + ADR-5 v1.6 baseline + driver localization`
   - Body: `## Summary` + `## Test plan` per global CLAUDE.md template.
   - Cite soak report path, ADR-5 section, driver finding.

## Acceptance

- PR open, links back to soak report + ADR-5 section.
- CI green (or known-flaky w/ explanation).

## On-done ack

`- [x] PR #<n> **S9 — Open ship PR** (<url>)`

## Mint-new check

- Caveman-review optionally: `/caveman:caveman-review pr <n>` — if findings,
  mint `S9a-ship-pr-fixups.md`.
- If CI fails, mint `S9b-ship-ci-debug.md`.
