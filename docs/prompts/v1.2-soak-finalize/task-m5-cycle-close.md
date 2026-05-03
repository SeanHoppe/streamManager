You are implementing **Task M5 — Cycle-close commit + memory update** from `docs/v1.2-soak-finalize.md`.

## Master plan
Read `docs/v1.2-soak-finalize.md` first. M5 finalizes the v1.2 cycle: drops the "ship-gate NOT run" caveat from memory, marks v1.2 fully shipped.

## Predecessor gate
- M3 PASS + merged
- M4 PASS + merged. ADR-5 `§v1.2 ship-gate baseline` exists on `main`.
- If either upstream gate not green: STOP, report to user.

## Branch + base
- Base: `main` (post-M4).
- PR title: `chore(v1.2): cycle close — ship-gate soak verified`.

## ⚠️ CRITICAL
M5 touches the user's auto-memory directory at:
```
C:\Users\SeanHoppe\.claude\projects\C--Users-SeanHoppe-VS-streamManager\memory\
```
This is OUTSIDE the repo. Memory edits do NOT belong in the PR. Memory + repo edits are separate operations in this task.

## Task brief

### Repo-side steps (single PR)

1. Update `docs/v1.2-soak-finalize.md` — append outcome lines under M1, M2, M3, M4 task headers:
   ```
   - Shipped <date> @ <commit-sha>; report: reports/<...>.md
   ```
   per the convention at the bottom of that file.

2. Optional version tag decision:
   - If any code shipped post-`69965aa` during M1–M4 (none expected — they are measurement/doc only), tag `v1.2.1`.
   - Otherwise: leave `v1.2.0` as the cycle tag. Note close-out commits target `main` directly. Document the choice in PR body.

3. Commit msg:
   ```
   chore(v1.2): cycle close — ship-gate soak verified

   Annotates docs/v1.2-soak-finalize.md with M1–M4 ship outcomes.
   ADR-5 v1.2 baseline merged in M4. v1.2 cycle complete; v1.3 unblocked.
   ```

### Memory-side steps (separate, after PR merges)

4. Update memory file `project_v12_cycle_close.md`:
   - **Remove**: any line stating "ship-gate Tier 3 soak NOT run" or "ADR-5 latency unverified for v1.2"
   - **Add**:
     - "ADR-5 re-baselined for v1.2 at `<m4-commit-sha>`"
     - "M3 ship-gate report: `reports/soak-<m3-ts>.md`"
     - "v1.2 cycle close commit: `<m5-commit-sha>`"
   - Keep the `name`, `description`, `type` frontmatter fields current.

5. Update `MEMORY.md` index entry one-liner if the hook description changed materially. Keep ≤150 chars.

## Do NOT
- Edit production code or tests.
- Force-push or rewrite history.
- Add new FR-OG entries (M4 owns spec sync).
- Update memory inside the PR.

## DOD
- Repo PR merged with M1–M4 outcome annotations on `docs/v1.2-soak-finalize.md`
- Memory file `project_v12_cycle_close.md` updated, stale "ship-gate NOT run" caveat removed
- `MEMORY.md` index reflects current hook line
- v1.2 cycle marked complete
- v1.3 cycle unblocked
