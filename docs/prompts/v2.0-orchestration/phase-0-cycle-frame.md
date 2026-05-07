You are implementing **Phase P0 — Cycle frame** for the streamManager v2.0 cycle.

## Branch + base

- Base: `main` (v1.9.0 tagged at `a7d0666`).
- PR target: `main`.
- Branch: `docs/v2.0-cycle-frame` (or operator's choice).
- If `main` is unexpectedly behind v1.9.0, ABORT and tell the user.

## Do-not-touch guard

P0 is **docs only**. Verify before commit:

```
git --no-pager diff origin/main..HEAD --stat -- src tests tools dashboard
```

Expected: empty. Any code hunk → STOP.

Do NOT edit `docs/v2.0-backlog.md` (frozen-emoji convention; the file
was pre-seeded in v1.9 P0 with the carry-forward stubs and
post-v1.9 items P1b cli_pool A/B + Tier 1.5).

## Task brief

Author the v2.0 cycle-frame artifacts. v2.0 is framed as a
**consolidation cycle**: zero new modules, deletion-positive net LOC,
two outstanding levers disposed (revive-or-rip).

Mirror the v1.9 P0 layout (`docs/prompts/v1.9-orchestration/phase-0-cycle-frame.md`)
but with the new ADR-18 obligation.

### Deliverables

1. **`docs/adr/ADR-18-mvp-surface-freeze.md`** — new ADR. Required
   sections:
   - Status: Proposed (v2.0 P0)
   - Context: pattern of dormant levers + LOC drift across v1.7-v1.9
     (see `project_v19_cycle_close.md`, `project_v18_cycle_close.md`,
     `project_v17_cycle_close.md` memory + ADR-5 lever-effect entries).
   - Decision: five rules.
     - **Rule 1 — MVP surface freeze**: classify every load-bearing
       module into FROZEN / EVOLVING / EXPERIMENTAL. Initial
       classification table covers every row currently on the v1.9
       do-not-touch list.
     - **Rule 2 — falsify-before-extend**: DORMANT-2 = WARN,
       DORMANT-3 = BLOCK at ship-gate. Lever ledger with current
       counts: Haiku fastpath = DORMANT-3; fallback (confidence +
       verdict) = DORMANT-2.
     - **Rule 3 — cycle LOC budget**: default ≤ 500 net add in
       `src/` + `tests/` + `tools/` + `dashboard/`. v2.0 declared
       consolidation: ≤ 0.
     - **Rule 4 — phase budget**: max 3 work phases per cycle
       (excluding P0 + ship-gate).
     - **Rule 5 — backlog hard cap**: 🟢 items expire after 2
       carry-forward cycles; must graduate, ADR-dispose, or delete.
   - Consequences (positive + costs + reversibility).
   - Migration: how v2.0 lands under the new rules.
   - Open questions.
2. **`docs/v2.0-task-plan.md`** — phase ledger covering P0 / P1 / P2 /
   P3 / P4. Reference ADR-18 as load-bearing for every other phase.
   Declare LOC budget ≤ 0 net. Declare phase budget = 3 work phases.
3. **`docs/prompts/v2.0-orchestration/phase-{0,1,2,3,4}-*.md`** — five
   orchestration prompts:
   - `phase-0-cycle-frame.md` (THIS file)
   - `phase-1-cli-pool-ab.md`
   - `phase-2-tier-15-codify.md`
   - `phase-3-haiku-fastpath-disposition.md`
   - `phase-4-ship-gate-finalize.md`
4. Confirm `docs/v2.0-backlog.md` already exists with:
   - 🟢 CLI pool sizing >2 (carry-forward — note that ADR-18 Rule 5
     graduates this to ADR disposition under v2.0)
   - 🟢 PPP audit harness (carry-forward)
   - 🟡 v1.9 P1b cli_pool A/B
   - 🟡 Tier 1.5 smoke soak codification
   Do NOT mutate it.

### Format invariant

Each phase block in the task plan stands alone — copy-pasteable
verbatim into a fresh Claude Code session via the matching action
prompt. References to memory files use absolute names (no scrollback
assumed).

ADR-18 is referenced from the v2.0 task plan do-not-touch list rather
than re-stating the FROZEN classification per cycle. Future cycles'
task plans inherit the FROZEN list as a read.

## DOD

- [ ] `docs/adr/ADR-18-mvp-surface-freeze.md` created with all five
      rules + initial classification table covering the v1.9
      do-not-touch list rows
- [ ] `docs/v2.0-task-plan.md` created with P0 / P1 / P2 / P3 / P4
      phase blocks + LOC + phase budget declarations
- [ ] `docs/prompts/v2.0-orchestration/phase-{0,1,2,3,4}-*.md` created
      (5 files)
- [ ] `docs/v2.0-backlog.md` UNCHANGED (frozen-emoji rule)
- [ ] PR scope is docs-only — `git --no-pager diff origin/main..HEAD --stat -- src tests tools dashboard` empty
- [ ] Single PR against `main`

## Mint-new-phase rule

P0 is mechanical; no phase mints expected. If `docs/v2.0-backlog.md`
is missing the four expected items (i.e. v1.9 P0 + cycle-close did not
seed correctly), STOP and patch v1.9 retrospectively before opening
v2.0 P0.

If during ADR-18 drafting a sixth rule emerges from the
v1.7-v1.9 retrospective that does not fit the five-rule structure,
flag to the user before merging — do not silently expand the rule
set.

Report back when PR is open with: PR URL, diff stat, file list.
