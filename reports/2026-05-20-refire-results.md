# 2026-05-20 v2.5.1 P2 ship-gate refire — running results

> Live operator log for the v2.5.1 P2 ship-gate refire. Captures design
> decisions, deviations from spec, tradeoffs, open questions as work
> proceeds. Per operator goal directive (2026-05-20).
>
> **Spec source:** `docs/prompts/v2.5.1-corrective/phase-2-shipgate-refire.md`
> (merged 2026-05-20 at `c14a9c6`). Inherits S-steps from
> `docs/prompts/v2.5-orchestration/phase-2-ship-gate-finalize.md` (merged
> 2026-05-19 at `2e49102`).
>
> **Path choice at S4: path-1 (default — cite n=6 P1 evidence).**

## Branch + base

- Branch: `ship/v2.5.1-shipgate-finalize` (created from `main` at `c14a9c6`).
- Base: `main` post `c14a9c6` (v2.5.1 P1 corrective merge).
- Lineage: `634e9d1` (v2.5 P0 cycle-tip) reachable in HEAD history. ✅

## Pre-flight (Amendment B — memory pre-flight)

Verified FRESH for rule content (2026-05-20):

| Memory | Status |
|---|---|
| `project_v24_cycle_close.md` | FRESH (minted 2026-05-19) |
| `feedback_glob_narrowing_no_op.md` | FRESH |
| `feedback_cycle_tolerance_masks_bugs.md` | FRESH |
| `feedback_subagent_long_task_abandonment.md` | 15-day-old; rule unchanged |
| `feedback_monitoring_live_sessions.md` | 13-day-old; pattern unchanged |
| `feedback_soak_cli_pool_flag.md` | 17-day-old; rule confirmed (verified `--cli-pool-size` default=0 still at `tools/soak_driver.py:1567`) |
| `feedback_alignment_eval_stability_window.md` | FRESH (minted 2026-05-20 at v2.5.1 P1) |

Code-state verify:
- `tools/soak_driver.py:1567` `--cli-pool-size default=0` → must pass `2` at S2.
- `src/stream_manager/cli_governance.py:49` `TIMEOUT_SECONDS = 25.0` FROZEN through v2.5 (Seed v2.4-G defers to v2.6 per spec).

## Cycle-tip anchor

`634e9d1d982a3b6071bfe78c369c4995419e2d44` (v2.5 P0 merge SHA) STAYS.
v2.5.1 P1 corrective PR #189 added docs+reports+memory ONLY → production-
bucket delta vs cycle-tip should remain 0 going into S2.

## Path choice — S4

**Default path-1 selected.** Cite `reports/alignment-eval-20260520T092222Z.{md,json}`
n=6 evidence in P2 PR body. Sonnet `pass_rate=0.9375`, Haiku 1.0,
regression_rows=[], frog7_regression_rows=0. No fresh n=6 fire at P2 to
avoid duplicate ~80-min wall.

**Rationale:** spec default; n=6 evidence already on disk and consistent
with current HEAD (no production code drift between P1 close and P2 fire);
duplicate fire would burn cycle time + further CLI-timeout pressure with
zero information gain.

**Open question (will surface to operator):** if reviewer wants path-2
(fresh n=6 at v2.5.1 head), I'll re-fire — but doing so adds ~80 min wall
and the n=6 reading at `c14a9c6` already represents the same code state
as the upcoming v2.5.1 tag (since no production-bucket touches between
P1 merge and P2 ship PR).

## S-step execution log

### S1 — Wipe soak state (target: pending)
### S1.1 — Post-wipe assert (target: pending)
### S2 — Tier-3 soak (target: pending; ~30 min wall)
### S3 — Invariant-degrade canary verify (target: post-S2)
### S4 — Alignment-eval (path-1: cite n=6 P1 evidence) (target: post-S3)
### S5 — LOC delta verify (cycle-tip anchor `634e9d1`) (target: post-S2)
### S6 — Lever-ledger HOLD record (target: drafting)
### S6.5 — Seed v2.4-G promotion re-confirm (target: drafting)
### S7 — ADR-5 v2.5 baseline (default SKIP per consolidation + LOC≈0) (target: post-S2 verdict)
### S8 — CHANGELOG `## [2.5.1]` append (target: drafting)
### S9 — Tag v2.5.1 (POST-MERGE) (target: post-PR-merge)
### S10 — Compare-back `docs/v2.5-next-steps.md` (target: post-S2)
### S11 — Mint `project_v25_cycle_close.md` (target: post-all-S)
### S12 — Lifetime cleanup (prompts persist; default) (target: post-tag)
### S13 — Mint-new-phase rule (v2.6 P0 if clean ship) (target: post-tag)

## Design decisions (running)

### D1. Running results file location: `reports/2026-05-20-refire-results.md`

Operator goal said "maintain a running 2026-05-20-refire-results.md file".
Path not specified. Chose `reports/` because (a) other live artifacts
(soak reports, alignment-eval reports) live there, (b) `reports/` is in
the docs bucket per Amendment C — no production-LOC penalty, (c) per S1
wipe pattern (`git clean -df reports/`), this file must be **tracked**
(`git add` after creation) so the wipe doesn't delete it.

### D2. "Create test scenarios" interpretation

Operator goal text reads "phase-2 ship-gate refire → v2.5.1 tag.. Create
test scenarios". Two possible readings:

- **(a)** create *new* test scenarios (golden-set additions, soak driver
  scenarios) — would violate ADR-18 surface freeze + Amendment C net ≤ 0
  binding. Off-limits at v2.5.1 P2.
- **(b)** log the test scenarios I'm executing (each S-step is a test
  scenario being exercised against the codebase) into this running file
  — surfaces what passes/fails as we go.

Picked **(b)** by default. Each S-step gets a "Scenario" entry below
with inputs / expected / actual / verdict. If operator meant (a), would
need explicit operator break-FREEZE decision.

**Open question for operator:** confirm (b) interpretation? If you meant
(a), specify which surface gets new scenarios so I can re-scope.

### D3. Default path-1 at S4

Selected per spec default. See "Path choice" above. Tradeoff vs path-2
documented.

### D4. ADR-5 v2.5 baseline append (default SKIP)

Per v2.5 P2 §S7 + v2.4 P2 precedent: consolidation cycle + LOC ≈ 0 +
no latency lever wired → MAY skip. Default SKIP unless S2 surfaces
latency-relevant data (e.g., p95 swing > 0.5s vs v2.4). Will re-evaluate
post-S2.

## Deviations from spec (running)

(none yet)

## Tradeoffs considered (running)

### T1. Path-1 vs Path-2 at S4

- **Path-1 (chosen):** cite existing n=6 evidence from P1.
  - Pros: zero new wall-clock; preserves n=6 reading as the canonical
    artefact for verdict A; avoids further CLI-timeout pressure.
  - Cons: technically measures `c14a9c6` (P1 merge state), not P2 HEAD.
    Cycle-tip lineage identical; production-bucket diff between P1
    merge and v2.5.1 tag = expected 0.
- **Path-2:** fresh n=6 at current HEAD.
  - Pros: clean evidentiary chain at tag SHA.
  - Cons: ~80 min wall; same production-state ⇒ same expected result;
    further CLI-timeout pressure could destabilize a row that was stable
    at the P1 reading.

Verdict: path-1. If reviewer demands path-2, re-evaluate.

## Open questions (running)

### Q1. Test scenarios — interpretation (see D2)
### Q2. Path-1 vs Path-2 at S4 (see T1; spec defaults to path-1)

## Scenarios exercised this session

Each S-step recorded as a test scenario (Scenario ID, inputs, expected,
actual, verdict). Populated as S-steps execute.

| Scenario | Step | Expected | Actual | Verdict |
|---|---|---|---|---|
| SC-S1 | wipe `reports/` untracked | tracked files preserved | _pending_ | _pending_ |
| SC-S1.1 | git status clean post-wipe | empty drift | _pending_ | _pending_ |
| SC-S2 | Tier-3 soak PASS | verdict PASS, canary PASS, p95 ≤ 13.7s | _pending_ | _pending_ |
| SC-S3 | invariant-degrade canary | `canary: PASS` line in summary | _pending_ | _pending_ |
| SC-S4 | n=6 alignment-eval cite | Sonnet 0.9375, Haiku 1.0, regression=[] | _pending_ | _pending_ |
| SC-S5 | cycle-tip LOC delta | net ≤ 0 production bucket | _pending_ | _pending_ |
| SC-S6 | lever-ledger HOLD | production=1, soak={} | _pending_ | _pending_ |
| SC-S6.5 | Seed v2.4-G stance | 🔴 + v2.6 defer | _pending_ | _pending_ |
| SC-S7 | ADR-5 append (cond) | SKIP rationale OR append | _pending_ | _pending_ |
| SC-S8 | CHANGELOG `[2.5.1]` | entry committed | _pending_ | _pending_ |
| SC-S9 | tag v2.5.1 | tag pushed post-merge | _pending_ | _pending_ |
| SC-S10 | compare-back next-steps | row-by-row marks | _pending_ | _pending_ |
| SC-S11 | project_v25_cycle_close.md | minted + indexed | _pending_ | _pending_ |
| SC-S12 | lifetime cleanup | prompts persist (default) | _pending_ | _pending_ |
| SC-S13 | v2.6 P0 mint | new prompt file | _pending_ | _pending_ |
