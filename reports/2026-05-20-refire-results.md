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

### S1 — Wipe soak state ✅ PASS

Executed: `rm -rf .bridge/soak-driver/* .bridge/cli-pool.pids ; git clean -df reports/`
(POSIX equivalent; spec showed PowerShell syntax. Bash tool routes
through POSIX shell — see Deviation DV1 below.)

### S1.1 — Post-wipe assert ✅ PASS

Initial fire flagged staged scaffold as drift (the running-results file
itself was staged but not yet committed). Resolved by committing scaffold
as `f1c7ef6` ("ship(v2.5.1): seed running refire results scaffold") — see
Deviation DV2 below. Re-fire returned clean.

### S2 — Tier-3 soak ⏳ IN PROGRESS (background `b5fo97xeh`, ~30 min wall)

Fired with env triple:
- `BRIDGE_API_GOV=1`
- `BRIDGE_RL_LOGGER_ENABLED=1` (v10 P4 corpus Run N+1 piggyback)
- `BRIDGE_CYCLE_TIP_SHA=634e9d1d982a3b6071bfe78c369c4995419e2d44`
- `BRIDGE_PREDECESSOR_TAG_SHA=08eb71d`
- `BRIDGE_CYCLE_TYPE=consolidation`

Command: `python tools/soak_driver.py --cli-pool-size 2 --ppp-auto-probe --total-seconds 1800 --interval-seconds 20`. Monitor armed on `tmp/soak-stdout-v251p2.log` with progress + terminal-state grep alternation.

### S3 — Invariant-degrade canary verify (target: post-S2)

Will grep soak summary for `[soak] invariant-degrade canary: PASS`.

### S4 — Alignment-eval (path-1 — cite n=6 P1 evidence) ✅ PRE-VERIFIED

n=6 evidence already on disk at `reports/alignment-eval-20260520T092222Z.{md,json}`:
- Sonnet `pass_rate=0.9375` (15 pass / 16 stable) ✅ ≥ 0.80 floor
- Haiku `pass_rate=1.0` (15/15) ✅ ≥ 0.85 floor
- `regression_rows=[]`, `frog7_regression_rows=0`
- Per `feedback_alignment_eval_stability_window.md`: this is the
  mandated n=6 reading (prior cycle 0.7895 within 0.05 of 0.80 floor).

**Seed v2.4-Q disposition (per spec):** 0.9375 ≥ 0.90 → RECOVERED band
→ Seed v2.4-Q CLOSES at v2.5.1 P2.

**5-cycle Sonnet trajectory (n=6 reading):**
`v2.1 → v2.2 → v2.3 → v2.4 → v2.5` =
`0.8636 → 0.9474 → 0.8182 → 0.8261 → 0.9375`
(n=3 reading 0.7895 superseded; both noted in narrative).

**4-cycle Haiku trajectory:** `0.85 → 0.9412 → 1.0 → 1.0`.

### S5 — LOC delta verify (cycle-tip anchor `634e9d1`) ✅ PASS

```
$ git diff 634e9d1d982a3b6071bfe78c369c4995419e2d44..HEAD --stat \
    -- src tests tools dashboard
(empty)
```

**Cycle-tip production-bucket delta = 0 / 0 / 0 → consolidation gate PASS.**

Narrative anchor:
```
$ git diff 08eb71d..HEAD --stat -- src tests tools dashboard
tests/test_soak_summary_loc_anchors.py +334 / -...
tools/soak_driver.py                  +57 / -...
2 files changed, 383 insertions(+), 8 deletions(-)
```
Predecessor-tag delta = +383 / -8 (from PR #184 Seeds v2.4-O + v2.4-P
fix; narrative only under Amendment A — not gating).

Cross-check at S3: will verify Seed 4 dual-anchor block in soak summary
matches this byte-for-byte.

### S6 — Lever-ledger HOLD ✅ RECORDED

- Production scope (Seed v2.4-H binding): count = **1** (v2.3 Seed 6
  JsonlTailWorker wire unchanged).
- Soak-scope `WIRED_LEVER_LEDGER: dict = {}` in `tools/soak_driver.py`
  — internal artefact, len 0.
- No wire/rip this cycle. **HOLD** verdict.
- No ADR-18 amendment required.

### S6.5 — Seed v2.4-G promotion re-confirm ✅ RECORDED

- Promotion 🔴 (landed v2.5 P0 PR #185, recorded `9ca5226` lineage).
- v2.5.1 P2 confirms stance unchanged.
- Implementation defers v2.6 (consolidation gate binds; ~30 LOC
  instrumentation incompatible with net ≤ 0).
- `src/stream_manager/cli_governance.py:49` `TIMEOUT_SECONDS = 25.0`
  STAYS FROZEN through v2.5.1.
- Cross-ref: Seed v2.5-A (`frog7-wirecli-module-10` 100% timeout
  opacity) = fresh empirical evidence for promotion stance; carries
  to v2.6 alongside Seed v2.4-G instrumentation.
- Seed v2.4-G renames to **Seed v2.5-G** in v2.5-backlog.md (this PR).

### S7 — ADR-5 v2.5 baseline ⏳ PENDING (default SKIP, re-evaluate post-S2)

Default per v2.4 P2 precedent: consolidation cycle + LOC delta = 0 +
no latency lever wired → **SKIP append**. Rationale recorded in P2 PR
body.

Re-evaluate if S2 surfaces p95 swing > 0.5s vs v2.4 P2 baseline
(10.518 s).

### S8 — CHANGELOG `## [2.5.1]` ⏳ DRAFTING

Will cover (per spec):
- Header: v2.5.0 BLOCKED → v2.5.1 P1 corrective re-measure → verdict A.
- Changed: alignment-eval n=6 mandate when prior-cycle within 0.05 of
  floor.
- Closed: Seed v2.4-Q RECOVERED (n=6 0.9375).
- Deferred / carry: Seed v2.5-A (NEW), Seed v2.5-C, Seed v2.5-G,
  Seeds v2.4-I..N exempts, Seed v2.4-E/F watches (per S2 data).

### S9 — Tag `v2.5.1` ⏳ POST-MERGE

Tag command (post-PR-merge):
`git tag -a v2.5.1 -m "..." <merge-SHA>` + `git push origin v2.5.1`.

### S10 — Compare-back `docs/v2.5-next-steps.md` ⏳ POST-S2

Row-by-row TBD table at L319. Pre-known:
- Seed v2.4-C → DEFERRED v2.6 (renames v2.5-C)
- Seed v2.4-E → re-measure post-S2
- Seed v2.4-F → re-measure post-S2
- Seed v2.4-G → promotion landed P0; impl defers v2.6 (renames v2.5-G)
- Seed v2.4-Q → **CLOSED RECOVERED** (n=6 0.9375)
- Seed v2.4-I..M → NOT FIRED; carry v2.6
- Seed v2.4-N → NOT FIRED; carry v2.6
- NEW Seed v2.5-A → wirecli-module-10 100% timeout opacity; carry v2.6

### S11 — Mint `project_v25_cycle_close.md` ⏳ DRAFTING

Single close memory covering: v2.5 P0 (#185, `634e9d1`) + v2.5 P2 BLOCK
(`2e49102`-prep + ship-gate work-PR never opened) + v2.5.1 P1 (#188 prompt
mint, #189 investigation `c14a9c6`) + v2.5.1 P2 (this PR).

### S12 — Lifetime cleanup ✅ DEFAULT

Per v2.0–v2.4 pattern: prompts persist as historical record. No retire
action this cycle.

### S13 — Mint v2.6 P0 prompt ⏳ POST-TAG

`docs/prompts/v2.6-orchestration/phase-0-cycle-frame.md` —
consolidation-or-feature pick at operator-call time. Planned v2.6
levers per spec: Seed v2.4-G CLI-timeout instrumentation (also resolves
v2.5-A wirecli-module-10 opacity), Seed v2.4-C Path-D P5 RL track, plus
v2.5.1 ship-gate carry-forwards.

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

### DV1 — S1 wipe uses POSIX equivalents, not PowerShell

Spec shows PowerShell syntax (`Remove-Item -Force`). Bash tool routes
through POSIX shell, not PowerShell. Used `rm -rf .bridge/soak-driver/*`
+ `rm -f .bridge/cli-pool.pids` instead. Semantically equivalent;
preserves intent of S1 wipe. Same `git clean -df reports/` call.

### DV2 — Scaffold committed pre-S1.1 (not in original S1 order)

S1.1 spec asserts `git status --short --untracked-files=no reports/`
returns clean. My pre-S2 setup staged the running-results scaffold file
which registered as drift even though the scaffold is legitimate
work-in-progress for this PR. Resolution: committed the scaffold
(`f1c7ef6`) before re-firing S1.1, which then PASS'd. Trade-off: adds
one bonus commit to the ship PR before S2 fires, but preserves the
running-log artefact (which would otherwise be wiped by S1's
`git clean -df`).

### DV3 — S2 env block extended with `BRIDGE_LOC_PATHSPEC`

**Forced deviation.** Spec phase-2 §S2 says "Fire as written in v2.5 P2
S2." but the v2.5 P2 §S2 env block omits `BRIDGE_LOC_PATHSPEC` — and
that omission was the precise failure mode at the v2.5 P2 first soak
(see `docs/v2.5-task-plan.md` §"P2 ship-gate BLOCK" → "Open carry-forwards":
*"Resolution: v2.5.1 P2 (or later) ship-gate prompt must include
`BRIDGE_LOC_PATHSPEC=src/,tests/,tools/,dashboard/` in the env block.
Single-line fix."*). The v2.5.1 P2 phase-2 prompt didn't fold the fix
into its inherited S2 block, so a strict-spec fire would repeat the
`PATHSPEC-UNSET [UNKNOWN]` outcome.

**My fix:** added `export BRIDGE_LOC_PATHSPEC=src/,tests/,tools/,dashboard/`
to the S2 env block on the refire (after I caught the omission and
stopped the first soak fire). Re-fired soak ID `b2vzwg5z6` with the
env var present.

**Trade-off considered:** strict spec compliance → repeat the BLOCK
condition → BLOCK record loops. Operator clearly wanted the env-block
fix per the task-plan note, just didn't fold it into the phase-2 prompt
text. Picking operator-intent over spec-letter.

**Open question:** confirm intent for v2.6 P0 — fold the env var into
the phase-2 prompt template directly, so future P2 fires don't depend
on the operator catching it? See Q3 below.

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

### Q3. Seed v2.5-A naming conflict (TWO conflicting definitions on main)

Two docs on `main` already define a different "Seed v2.5-A":

- **`docs/v2.5-task-plan.md` §"Open carry-forwards (entering v2.5.1)"**
  (commit `634e9d1` lineage + later) — *"NEW Seed v2.5-A — P2 prompt
  S2 env block missing `BRIDGE_LOC_PATHSPEC`. Single-line fix."*
- **`docs/prompts/v2.5.1-corrective/phase-2-shipgate-refire.md` §S4**
  (commit `c14a9c6`) — *"Seed v2.5-A (`frog7-wirecli-module-10` 100%
  timeout opacity) carries forward to v2.6."*

**Resolved by default (subject to operator override):**

- **Phase-2 prompt's definition wins** (newer mint, explicit seed-row
  language): `Seed v2.5-A = frog7-wirecli-module-10 100% timeout
  opacity` → carries to v2.6 alongside Seed v2.4-G instrumentation.
- **Task-plan's v2.5-A (env-block omission)** is folded into v2.5.1
  P2 operator execution as **DV3 above** — no separate seed identifier
  needed. Recorded in close memory as historical note.

**Why pick this default:** the env-block omission is a single-line
prompt-template bug already resolved by the operator's execution-time
fix (DV3). Promoting it to a tracked seed identifier on the v2.5.1 P2
ship-gate PR would mean either (a) reusing v2.5-A and confusing the
two, or (b) inventing a v2.5-A1/v2.5-A2 split — both worse than just
recording the env-block fix as an operator fold under the existing
Seed v2.5-A (wirecli-module-10) entry.

**Open question for operator:** confirm phase-2 prompt's definition
of Seed v2.5-A is the canonical one? If you want the env-block fix
to carry as its own tracked seed (e.g. Seed v2.5-Z or Seed v2.5-X),
say so before the ship PR opens.

### Q4. Fold `BRIDGE_LOC_PATHSPEC` into v2.6 phase-0 + phase-2 templates?

DV3 above is the third time this env-block omission has appeared in
the v2.x ship-gate lineage (v2.4 P2 latent, v2.5 P2 surfaced at S2,
v2.5.1 P2 inherited unchanged). v2.6 phase-0/phase-2 templates should
fold `BRIDGE_LOC_PATHSPEC=src/,tests/,tools/,dashboard/` into the
canonical S2 env block. Confirm before S13 mints v2.6 P0?

## Scenarios exercised this session

Each S-step recorded as a test scenario (Scenario ID, inputs, expected,
actual, verdict). Populated as S-steps execute.

| Scenario | Step | Expected | Actual | Verdict |
|---|---|---|---|---|
| SC-S1 | wipe `reports/` untracked | tracked files preserved | tracked preserved (POSIX path); `git clean -df reports/` clean | ✅ PASS |
| SC-S1.1 | git status clean post-wipe | empty drift | clean after scaffold commit `f1c7ef6` (DV2) | ✅ PASS |
| SC-S2 | Tier-3 soak PASS | verdict PASS, canary PASS | _running bg `b2vzwg5z6` (post-DV3 refire)_ | _pending_ |
| SC-S3 | invariant-degrade canary | `canary: PASS` line in summary | _post-S2_ | _pending_ |
| SC-S4 | n=6 alignment-eval cite | Sonnet ≥ 0.80, Haiku ≥ 0.85 | Sonnet 0.9375 (15/16), Haiku 1.0 (15/15), regression=[]| ✅ PASS (path-1) |
| SC-S5 | cycle-tip LOC delta | net ≤ 0 production bucket | 0 / 0 / 0 (empty diff vs 634e9d1 -- src tests tools dashboard) | ✅ PASS |
| SC-S6 | lever-ledger HOLD | production=1, soak={} | recorded (this PR body) | ✅ PASS |
| SC-S6.5 | Seed v2.4-G stance | 🔴 + v2.6 defer + renames v2.5-G | recorded (this PR body + v2.5-backlog mint) | ✅ PASS |
| SC-S7 | ADR-5 append (cond) | SKIP rationale OR append | default SKIP, re-evaluate post-S2 p95 | _pending_ |
| SC-S8 | CHANGELOG `[2.5.1]` | entry committed | drafted; commits post-S3 verify | _pending_ |
| SC-S9 | tag v2.5.1 | tag pushed post-merge | _POST-MERGE_ | _pending_ |
| SC-S10 | compare-back next-steps | row-by-row marks | drafted; finalises post-S2 (E/F bands) | _pending_ |
| SC-S11 | project_v25_cycle_close.md | minted + indexed | drafted; finalises post-S2 | _pending_ |
| SC-S12 | lifetime cleanup | prompts persist (default) | default applied | ✅ PASS |
| SC-S13 | v2.6 P0 mint | new prompt file | _POST-TAG_ | _pending_ |
