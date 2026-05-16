# v2.2 P2 — ship-gate finalize + ADR-5 v2.2 baseline + CHANGELOG + tag

> Minted at v2.2 P0 cycle frame (this PR). Format mirrors
> `docs/prompts/v2.1-orchestration/phase-4-ship-gate-finalize.md`
> compressed for consolidation-cycle scope. Fire when P1 merges.

## Branch + base

- Base: `main` after v2.2 P0 + P1 merged.
- PR target: `main`.
- Branch: `ship/v2.2-shipgate-finalize`.
- ABORT if P0 / P1 not merged.

## Pre-flight

```
git fetch origin
git log --oneline origin/main -5
```

Expected: P0 merge commit + P1 merge commit at HEAD. If divergent,
STOP.

## Context

v2.2 ship-gate validates the consolidation cycle's two guarantees:

1. **Net LOC ≤ 0** across `src/` + `tests/` + `tools/` +
   `dashboard/` vs `8303f38` (v2.1.0 tag). Gap-4 P1 added ~80 LOC
   test/driver — P1 also landed ≥ 80 LOC offsetting deletion.
2. **API-timeout invariant holds.** New invariant-degrade canary
   line in soak summary reads PASS. CLI-timeout + API-500 fault
   classes both produce `OBSERVE` verdict + bounded latency.

ADR-18 surface freeze stays in force. `WIRED_LEVER_LEDGER` empty;
DORMANT-N gate inert.

## References (load before starting)

- `docs/v2.2-task-plan.md` §PHASE P2 — scope sketch.
- `docs/prompts/v2.0-orchestration/phase-4-ship-gate-finalize.md`
  — consolidation-cycle ship-gate predecessor; format template.
- `docs/prompts/v2.1-orchestration/phase-4-ship-gate-finalize.md`
  — immediate predecessor (feature cycle; format reference for
  S1–S12 structure even though our scope is lighter).
- `docs/adr/ADR-5-latency-budget.md` — append §"v2.2 ship-gate
  baseline" section.
- `docs/adr/ADR-17-soak-tiers.md` + `docs/soak-trigger-matrix.md`
  — Tier 3 invocation.
- `reports/soak-20260511T173516Z.md` — v2.1 ship-gate baseline
  (compare against).
- `tools/soak_driver.py` `--ppp-auto-probe` default-on at v2.1
  ship-gate; v2.2 inherits.
- Memory: `project_v21_cycle_close.md` (template for v2.2 close
  memory), `feedback_subagent_long_task_abandonment.md` (soak
  launch discipline), `feedback_monitoring_live_sessions.md`
  (soak monitor template), `feedback_cassette_must_cover_new_
  envelopes.md`.

## ⚠️ CRITICAL: Do-not-touch guard

P2 touches **only**:

- `docs/adr/ADR-5-latency-budget.md` — append v2.2 ship-gate
  baseline section (additive at file tail).
- `docs/v2.2-task-plan.md` — append §"P2 close-out (this PR)"
  subsection; do NOT rewrite earlier sections.
- `docs/v2.2-backlog.md` — append §"Carry-forwards from v2.2"
  subsection ONLY IF surfaced items merit carry-forward. No edits
  to existing 6 seeds (frozen-emoji rule).
- `CHANGELOG.md` — append `## [2.2.0]` section.
- Memory: write `project_v22_cycle_close.md` and add to
  `MEMORY.md`.

**No code edits expected at P2.** Gap-4 P1 already shipped the
test + soak observability line.

## Scope

### S1 — Wipe soak state

Project CLAUDE.md pins the dev shell to PowerShell. Use:

```powershell
Remove-Item -Force .bridge/soak-driver/*, .bridge/cli-pool.pids, reports/soak-*.md -ErrorAction SilentlyContinue
```

(Preserve historical reports under git tracking — only wipe
working-directory artifacts; the v2.1 ship-gate report stays in
git history. `-ErrorAction SilentlyContinue` matches `rm -f`
semantics for missing files.)

### S2 — Fire Tier-3 soak

Per ADR-17 Tier-3 + `feedback_subagent_long_task_abandonment.md`,
launch from main thread with `run_in_background` +
`ScheduleWakeup`:

```powershell
python tools/soak_driver.py `
  --cli-pool-size 2 `
  --ppp-auto-probe `
  --total-seconds 1800 `
  --interval-seconds 20
```

(PowerShell backtick continuation; POSIX `\` does NOT continue
lines in PowerShell. If running under bash, flatten to one line or
swap backticks for `\`.)

Monitor template: `feedback_monitoring_live_sessions.md`. Expected
soak duration ~30 min. Schedule wake-up at 35 min for completion
check.

### S3 — Verify invariant-degrade canary

Soak summary closing block MUST contain
`[soak] invariant-degrade canary: PASS`. FAIL = ship blocked;
root-cause via gap-4 test logs.

### S4 — Alignment-eval

```
python tools/alignment_eval.py --ci-gate
```

Exit 0 required. Compare Sonnet pass rate against v2.1 (0.8636);
record dip status:

- Recovered (≥ 0.90) → log as alignment-recovery seed CLOSED at
  v2.2 ship-gate; update `docs/v2.1-backlog.md` §"Alignment-
  recovery investigation" disposition.
- Stable (~0.8636) → record as "v2.1 dip reproduces on fresh
  control"; promote to 🔴 per v2.1-backlog §"Why 🟡 (not 🟢)"
  rule; carry-forward to v2.3.
- Worse (< 0.8636) → BLOCK ship; root-cause.

### S5 — LOC delta verification

```
git diff 8303f38...HEAD --stat -- src tests tools dashboard
```

Confirm net delta ≤ 0. If > 0, BLOCK ship; demand deletion
reconciliation pre-tag.

### S6 — ADR-5 v2.2 baseline append

Append §"v2.2 ship-gate baseline" section to `docs/adr/ADR-5-
latency-budget.md`. Format mirrors v2.1 baseline section. Include:

- Soak source (`reports/soak-<timestamp>.md`).
- Per-band p50/p95 (ALLOW, L2, L3, L4, LM).
- Delta vs v2.1 ship-gate.
- Caveats section if anything noteworthy.

### S7 — CHANGELOG entry

Append `## [2.2.0]` section per Keep-a-Changelog format. Cover:

- **Added** — gap-4 API-timeout invariant test + Tier-3 soak
  invariant-degrade canary column.
- **Changed** — ADR-18 §"Amendments" gained v2.2 P0 Amendment A
  (feature-cycle LOC soft target ≤ 1500) + Amendment B (Rule 6
  memory pre-flight); INTENT.md gap-10/12 strikes applied.
- **Removed** — deletion-offset items from P1 (list).

### S8 — Tag v2.2.0

After PR review approve + merge to main:

```
git tag -a v2.2.0 -m "v2.2.0 consolidation cycle — gap-4 API-timeout invariant + Amendment A/B"
git push origin v2.2.0
```

### S9 — Mint close memory

Write `memory/project_v22_cycle_close.md` per template
(`project_v21_cycle_close.md`). Cover:

- Tag SHA + PR list.
- LOC delta (final).
- Lever ledger status (expected: unchanged at 0).
- v2.1 alignment-dip disposition recorded at S4.
- Carry-forwards into v2.3 (if any).

Add index entry to `MEMORY.md`.

### S10 — Mark gap-4 LANDED

Edit `docs/prompts/v2.2-orchestration/gap-4-api-timeout-invariant-
test.md` header: `FOLDED v2.2 P1 — LANDED PR #<n>` becomes
`LANDED v2.2.0 ship-gate`.

### S11 — Lifetime cleanup

Delete `docs/intent-todo-gap-2026-05-16.md` per its lifetime rule
(P0 mint + gap-4 land both satisfied at v2.2 ship-gate close).

**Also strike** the corresponding bullet from
`INTENT.md` §"Authoritative status references" — the bullet
points to the deleted file and dangles without this strike. The
bullet text is `- \`docs/intent-todo-gap-2026-05-16.md\` — 12-gap
synthesis pass …`; remove the entire `- ` line.

### S12 — Mint-new-phase rule

If S2-S5 surface any new must-fix item, mint a v2.2.1 patch-cycle
prompt (matches v1.3 / v1.6 / v1.8 corrective-cycle precedent).
Default: no follow-up; ship clean.

## DOD

- [ ] Tier-3 soak PASS verdict.
- [ ] Invariant-degrade canary PASS in soak summary.
- [ ] Alignment-eval `--ci-gate` exit 0; dip disposition
      recorded.
- [ ] LOC delta ≤ 0 verified.
- [ ] ADR-5 v2.2 baseline appended.
- [ ] CHANGELOG `## [2.2.0]` appended.
- [ ] `v2.2.0` tag pushed.
- [ ] `project_v22_cycle_close.md` memory + MEMORY.md index.
- [ ] Gap-4 prompt header stamped LANDED.
- [ ] `docs/intent-todo-gap-2026-05-16.md` deleted.
- [ ] `INTENT.md` §"Authoritative status references" bullet
      pointing to the deleted gap doc removed (same PR).
- [ ] Single PR `ship(v2.2):` against `main`.

Report back when v2.2.0 tag is pushed with: tag SHA, soak report
path, alignment dip disposition, final LOC delta vs `8303f38`.
