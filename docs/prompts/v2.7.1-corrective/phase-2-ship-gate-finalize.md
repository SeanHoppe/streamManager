# v2.7.1 P2 — ship-gate finalize + v2.7.1 tag (corrective sub-cycle)

> **STUB minted post-v2.7-P3-BLOCK 2026-05-22** (operator-authorised
> chain after PR #207 BLOCK at v2.7 P3 S4 alignment-eval gate). v2.7.1
> is the corrective sub-cycle that absorbs the row-05
> Haiku-stabilisation regression surfaced at v2.7 P3 S4 plus the
> corpus-wide cap-clip artefact confirmation. Full fold post-P1
> verdict per goal cadence: the n=12 single-row re-eval of
> `frog7-phase-timings-keys-05` at v2.7.1 P1 dictates this prompt's
> Hatch A/B/C path, `--runs` flag, golden-flip decision, and row
> exclusion list.
>
> **Precedent.** v2.5 → v2.5.1 corrective sub-cycle (PR #188 BLOCK
> record + PR #189 corrective P1 + PR #190 ship-gate refire
> verdict-A). v1.3 → v1.3.1 precedent (BLOCKED parent tag is skipped;
> sub-cycle tag carries). v2.7.1 follows the same shape: parent v2.7.0
> is NEVER tagged; v2.7.1 is the carry tag.
>
> **What this stub locks now:**
>
> 1. **Cycle-tip anchor: RETAIN `4902cca440b33c14fddd9357116923ae5fe1
>    fa4b`.** Sub-cycle inherits parent cycle-tip per ADR-18
>    Amendment C + v2.5.1 precedent (v2.5.1 P2 kept v2.5 P0 cycle-tip
>    `634e9d1` unchanged). No new cycle-tip mint; v2.7.1 P0 does not
>    exist. The corrective sub-cycle inherits v2.7 P0's frame
>    decisions verbatim.
> 2. Procedure skeleton (S1–S13) — mirror of v2.7 P3 stub
>    (`docs/prompts/v2.7-orchestration/phase-3-ship-gate.md`) and v2.6
>    P2 full template
>    (`docs/prompts/v2.6-orchestration/phase-2-ship-gate-finalize.md`).
> 3. Alignment-eval `--runs` pre-binding driven by v2.7.1 P1 verdict
>    via §"P1 → P2 verdict-bridge" Hatch A/B/C table. Stability-window
>    hatch (3) is already bound (v2.6 P2 unstable_sonnet 15/32 = 47% >
>    25% threshold persists; v2.7 P3 reaffirmed). Baseline `--runs 6`
>    cannot down-shift.
> 4. Seed v2.4-E + Seed v2.4-F close-vote anchors carried unchanged
>    from v2.7 P3 stub.
> 5. Memory pre-flight: 6 load-bearing memories carried from v2.7 P0;
>    light re-verify at P2 fire — no full pre-flight at this stub PR.
>
> **What stays TBD pending v2.7.1 P1 verdict (folded at P2 fire-PR):**
>
> - Hatch A / B / C / STILL-100%-TIMEOUT-ESCALATE selection (driven by
>   J1 protocol stability-check on row-05).
> - `--runs` final value at S4 (`6` for Hatch A/B baseline; `12` if
>   Hatch C escalation requires further evidence; ABORT-before-S5 if
>   STILL-100%-TIMEOUT-ESCALATE fires).
> - Golden-fixture flip flag — `tests/golden/l4_alignment.jsonl`
>   row-05 update (Hatch A only; Hatch B/C: NO flip).
> - Row exclusion list at S4 alignment-eval — `frog7-phase-timings-
>   keys-05` excluded from gate denominator under Hatch B per
>   `feedback_alignment_eval_stability_window.md` hatch (4).
> - v2.7.1 P1 merge SHA (filled into S2 / S3 / S5 expectation blocks).
> - Cumulative cycle-tip LOC tally — v2.7 P1 (+8 / −6 production)
>   + v2.7.1 P1 corrective (expected 0 production; docs + reports
>   only unless Hatch A golden flip touches `tests/golden/`) + v2.7.1
>   P2 (0 production).
> - ADR-5 baseline append disposition (operator pick at fire — default
>   APPEND because the v2.7 P1 latency-surface lever still ships in
>   v2.7.1).
>
> **Cycle-classification carry.** v2.7 was registered FEATURE at P0
> (PR #200 `4902cca`). v2.7.1 inherits FEATURE classification; soft
> LOC ≤ 1500 / BLOCK 2250 vs cycle-tip `4902cca`. Cumulative cycle
> delta entering P2 (P1 v2.7 + P1 v2.7.1): production-bucket +8 / −6
> LOC. Well under soft target.
>
> **Lifetime.** This file persists as historical record (matches v2.5
> → v2.5.1 retention pattern; v2.5.1 prompts still live under
> `docs/prompts/v2.5.1-corrective/`).

## What this stub locks now

- Cycle-tip anchor decision: **RETAIN
  `4902cca440b33c14fddd9357116923ae5fe1fa4b`**.
- Procedure skeleton: S1–S13 mirror of v2.6 P2 / v2.7 P3.
- `--runs` flag: pre-bound to `6` baseline; v2.7.1 P1 verdict can
  escalate to `12` (Hatch C-likely) but cannot down-shift.
- Tag target: **v2.7.1** (NOT v2.7.0). Parent v2.7.0 never tagged
  per v1.3.1 / v2.5.1 precedent.
- Branch: `ship/v2.7.1-p2-ship-gate`.
- ADR-18 surface-freeze in force; no new amendment minted this
  sub-cycle.

## P1 → P2 verdict-bridge (folded at P2 fire-PR)

The v2.7.1 P1 n=12 row-05 re-eval verdict (per J1 protocol
`docs/seed-v2.7-b-row05-haiku-protocol.md`) drives four P2
parameters: `--runs` flag at S4, golden-fixture flip, row-05
exclusion list, and v2.7.1 vs v2.8-carry tag pick.

**Baseline `--runs 6` is bound at P2 via stability-window
escape-hatch (3)** — v2.6 P2 unstable_sonnet 15/32 = 47% > 25%
threshold persists through v2.7 P3 and into v2.7.1. The P1 verdict
can only ESCALATE further (to `--runs 12` or ABORT), never
down-shift.

| P1 verdict (Haiku stability on row-05)        | `--runs` at S4    | Golden flip? (`l4_alignment.jsonl` row-05) | Row-05 exclusion at S4? | Tag (this cycle vs v2.8 carry) |
|------------------------------------------------|-------------------|---------------------------------------------|--------------------------|--------------------------------|
| **Hatch A** — ≥ 9/12 Haiku stable (golden re-baseline) | `--runs 6` baseline; re-fire after golden update | YES — flip `expected_verdict` to P1 n=12 majority | NO — row stays in denominator | **v2.7.1** ships; v2.8 P0 mint at S13 |
| **Hatch B** — 6–8/12 stable (per-row exclusion) | `--runs 6` baseline; row-05 dropped from gate denominator | NO | YES — apply hatch (4) exclusion | **v2.7.1** ships; v2.8 P0 mint at S13 |
| **Hatch C** — < 6/12 stable (corpus-wide escalation) | Consider `--runs 12` at S4 IF budget permits; otherwise `--runs 6` with both row-05 + cap-clip flagged rows excluded | NO | YES — row-05 excluded + Seed v2.7-A-CLIP rows excluded per cap-clip presence | **ABORT-before-S5**; do NOT tag v2.7.1; carry to v2.8 Convergence-cycle (per `docs/2026-05-22-status.md` §"Proposal") |
| **STILL-100%-TIMEOUT-ESCALATE** — ≥ 6/12 NONE under cap | n/a — do not re-fire S4 | NO | n/a | **ABORT-before-S5**; same v2.7 P2 escalation pattern; v2.7.1 ship gate cannot close until step (3) env-split lands; carry full corrective scope to v2.8 |

Default expectation at this stub mint: **Hatch A or B most likely**.
v2.7 P3 S4 reading was a single-cycle Haiku instability surface; the
n=12 re-eval is the standard protocol disposition (v2.6 P2 row-10
precedent applied to row-05). STILL-100%-TIMEOUT-ESCALATE only fires
if row-05 is hitting the 30 s cap consistently — different failure
mode from the v2.7 P3 reading.

Hatch C → ABORT path is the bridge into the v2.8 Convergence-cycle
proposal (Path-D + step (3) env-split + Seed v2.7-A-CLIP corpus
re-measure bundled).

## Branch + base

- Base: `main` after v2.7.1 P1 corrective PR merged (per J2 P1
  prompt `docs/prompts/v2.7.1-corrective/phase-1-row05-remeasure
  .md`).
- PR target: `main`.
- Branch: `ship/v2.7.1-p2-ship-gate`.
- ABORT if v2.7.1 P1 not merged at HEAD lineage. Verify via:

  ```
  git fetch origin
  git log --oneline origin/main -10
  ```

  Expected top-of-main lineage includes the v2.7.1 P1 merge SHA
  (filled at P2 fire-PR open). If divergent, STOP.

## Pre-flight

Memory pre-flight at v2.7.1 P2 — light re-verify (v2.7 P0
Amendment B pre-flight covers 6 load-bearing memories; v2.7.1 P1
already re-verified at corrective-cycle entry; this ship-gate phase
adds no new memory-loading risk):

- `project_v26_cycle_close.md` — v2.6 ship reference; v2.7.1 cycle
  closes by appending a new `project_v271_cycle_close.md` memory
  (note slug-safety: use `project_v271_cycle_close.md`, NOT
  `project_v27_1_cycle_close.md` — see S11).
- `feedback_cli_over_sdk.md` — `claude -p` subprocess path unchanged.
- `feedback_soak_cli_pool_flag.md` — `--cli-pool-size 2` mandatory
  for S2 Tier-3 soak.
- `feedback_glob_narrowing_no_op.md` — S1 wipe uses `git clean -df
  reports/` (not glob narrowing).
- `feedback_alignment_eval_stability_window.md` — `--runs` decision
  (see §"P1 → P2 verdict-bridge"); hatch (3) bound; hatch (4) used
  under Hatch B / C.
- `feedback_certportal_dev_firewall.md` + `feedback_no_self_monitor.
  md` — unchanged scope; no certPortal coupling, no self-monitor
  surface added.
- `feedback_subagent_long_task_abandonment.md` — S2 Tier-3 soak
  launches from main thread via `run_in_background`, never from a
  subagent.

If any memory stale, update IN A SEPARATE PRE-P2 PR or at top of P2
PR body per Amendment B precedent.

## ⚠️ CRITICAL: Do-not-touch guard

ADR-18 surface-freeze applies. v2.7.1 P2 MUST touch ONLY:

- **CHANGELOG.md** — append v2.7.1 ship entry (NOT v2.7.0).
- **`docs/v2.7.1-task-plan.md` §"P2 close-out"** — fill the
  operator-decision blocks (minted by J4 in PM-mint bundle).
- **`docs/v2.7.1-next-steps.md`** §"Fire-order" + compare-back rows
  — flip `[ ]` → `[x] ✅ LANDED` row-by-row.
- **`docs/v2.7.1-backlog.md`** (NEW; carry-forwards to v2.8). Mirror
  v2.6-backlog.md / v2.5-backlog.md format.
- **`docs/adr/ADR-5-latency-budgets.md`** — operator decides APPEND
  vs hold; default APPEND because the v2.7 P1 latency-surface lever
  (Seed v2.6-G step (2) `TIMEOUT_SECONDS` cap 25 → 30) still ships
  in v2.7.1.
- **Memory mint:** `~/.claude/projects/.../memory/project_v271_cycle
  _close.md` + MEMORY.md index entry.

**Conditional surface (Hatch A only):**
- `tests/golden/l4_alignment.jsonl` row-05 — `expected_verdict` flip
  IF Hatch A path. NO touches under Hatch B / C / STILL-100%-
  TIMEOUT-ESCALATE.

NO edits to `src/`, `tools/`, `dashboard/`, FROZEN bus envelope
schema, governance HITL surfaces. NO deletions; NO renames.

**Specifically do NOT touch:**

- `src/stream_manager/cli_governance.py:49` — `TIMEOUT_SECONDS =
  30.0` from v2.7 P1; do NOT revert or further adjust at v2.7.1.
  (Cap-tighten value disposition belongs to v2.8 Convergence-cycle
  step (3) env-split, NOT this sub-cycle.)
- `src/stream_manager/latency_budgets.py` —
  `BRIDGE_FALLBACK_LATENCY_BUDGET_MS = 45_000` from v2.7 P1; do NOT
  revert.
- `tools/alignment_eval.py` — instrumentation surface from v2.6 P1;
  no touches at v2.7.1 P2.
- Any other golden fixture row (only row-05 under Hatch A).

## Scope (S1–S13)

Procedure mirrors v2.6 P2 + v2.7 P3 ship-gate skeleton; the row-05
re-measure landed at v2.7.1 P1 (separate phase). v2.7.1 P2 is
soak + alignment-eval + invariants + tag.

### S1 — wipe reports

```
git clean -df reports/
```

Per `feedback_glob_narrowing_no_op.md`: tracked-status filter, not
filename pattern guess. The soak driver writes `reports/soak-
{iso_ts}.md` with no `tmp-` prefix; `git clean -df` removes ONLY
untracked under `reports/` while tracked baseline reports stay
intact.

**S1.1 assertion:**

```powershell
$drift = git status --short --untracked-files=no reports/
if ($drift) {
  Write-Error "S1 wipe left tracked reports/ in drift state:`n$drift"
  exit 1
}
```

Must return clean before S2.

### S2 — Tier-3 soak (cycle-tip anchor binding)

Per ADR-17 Tier-3 + `feedback_subagent_long_task_abandonment.md`,
launch from main thread with `run_in_background` + `ScheduleWakeup`.
**NEVER from a subagent.**

```powershell
# Canonical S2 env block (per v2.7 P0 skeleton §"Canonical S2 env block")
$env:BRIDGE_API_GOV = "1"
$env:BRIDGE_RL_LOGGER_ENABLED = "1"
$env:BRIDGE_CYCLE_TIP_SHA = "4902cca440b33c14fddd9357116923ae5fe1fa4b"
$env:BRIDGE_PREDECESSOR_TAG_SHA = "c3a964c"
$env:BRIDGE_CYCLE_TYPE = "feature"
$env:BRIDGE_LOC_PATHSPEC = "src/,tests/,tools/,dashboard/"

python -m tools.soak_driver `
  --tier 3 `
  --cli-pool-size 2 `
  --ppp-auto-probe `
  --total-seconds 1800 `
  --interval-seconds 20
```

`--cli-pool-size 2` is **MANDATORY** per `feedback_soak_cli_pool_
flag.md`. Soak runs with the new `TIMEOUT_SECONDS = 30.0` (v2.7 P1
production path under elevated cap; expect `degrade_count = 0`).

Monitor template: `feedback_monitoring_live_sessions.md`. Expected
duration ~30 min. Schedule wake-up at 35 min for completion check.

**OQ-2 risk note (carry-over from v2.7 P3 overnight soak).** v2.7 P3
S2 soak surfaced LM p95 = 5593.95 s (n=10, max 6974.358 s) suggesting
a single stalled CLI dispatch. v2.7.1 P2 S2 must inspect the LM
band per-event distribution; if a single outlier dominates,
document exclusion per hatch (4) precedent in P2 PR body. If
multiple LM events stall, **STOP and escalate** — that is a real
regression and the v2.7.1 corrective sub-cycle is no longer
sufficient.

### S3 — invariant + dual-anchor

```
python -m tools.invariant_check --anchor cycle-tip
python -m tools.cycle_loc_dual_anchor `
  --cycle-tip 4902cca440b33c14fddd9357116923ae5fe1fa4b `
  --predecessor-tag c3a964c
```

Cycle-tip is the gating LOC anchor (Amendment C); predecessor-tag
narrative diff `c3a964c..HEAD` is reported alongside but does not
gate (Amendment C §"Bucket-scoped narrative").

Soak summary closing block MUST contain
`[soak] invariant-degrade canary: PASS`. FAIL = ship blocked.

Verify dual-anchor block in soak report:
- `cycle-tip (4902cca..HEAD): +X / -Y / +Z [PASS|BLOCK]`
- `predecessor-tag (c3a964c..HEAD): +X / -Y / +Z [narrative]`

Cycle-tip line MUST show **net ≤ 1500 LOC** for feature PASS;
BLOCK at 2250.

### S4 — alignment-eval

`--runs` flag per §"P1 → P2 verdict-bridge". **Baseline `--runs 6`**
is bound by stability-window hatch (3); the v2.7.1 P1 verdict may
ESCALATE to `--runs 12` under Hatch C if budget permits.

```
python -m tools.alignment_eval `
  --runs <P1-verdict-driven; default 6> `
  --ci-gate `
  [<row-exclusion flags per Hatch path>]
```

**Per-row exclusion (Hatch B / C path):**

If Hatch B: exclude `frog7-phase-timings-keys-05` from gate
denominator. Mechanism: `tools/alignment_eval.py --exclude-row
frog7-phase-timings-keys-05` (verify flag exists; if not, fall back
to fixture surgery in a separate Hatch-B-only fold step or document
in P2 PR body as manual disposition).

If Hatch C: exclude row-05 + Seed v2.7-A-CLIP cap-clip flagged rows
(per v2.7 P3 P2 reading; list pinned at P2 fire-PR open).

If `--ci-gate` exit ≠ 0 → BLOCK; fold corrective sub-sub-phase per
v2.5.1 precedent (PR #190 verdict-A) — but at this depth, escalate
to v2.8 Convergence-cycle instead per Hatch C path.

Record per-band disposition:
- **Sonnet:** ≥ 0.80 FR-OG-7 floor.
- **Haiku:** ≥ 0.85 floor.

Capture wall-clock distributions (v2.6 P1 instrumentation surface):
- `summary.sonnet_duration_s_{p50,p95,p99,max,n}`.
- `summary.haiku_duration_s_{p50,p95,p99,max,n}`.

Record **7-cycle Sonnet trajectory** and **6-cycle Haiku trajectory**
in P2 PR body — cycle ledger now reads `v2.1 → v2.2 → v2.3 → v2.4 →
v2.5.1 → v2.6 → v2.7.1` (parent v2.7 itself never tagged).

### S5 — cycle-tip LOC delta verify (Amendment C)

```
git diff 4902cca440b33c14fddd9357116923ae5fe1fa4b..HEAD --stat -- src tests tools dashboard
```

Cumulative cycle delta entering P2:
- v2.7 P1 (PR #203 `28a89c4`): production-bucket +8 / −6 LOC.
- v2.7.1 P1 (J2 P1 prompt; merge SHA TBD): expected 0 production
  bucket unless Hatch A golden flip touches `tests/golden/`
  (counts in tests bucket; ≤ 5 LOC expected).
- v2.7.1 P2 (this PR): 0 production bucket; docs + memory + ADR-5
  + CHANGELOG only.

Expected cumulative cycle-tip net: +8 / −6 LOC production (+0–5 LOC
tests under Hatch A). Well under soft ≤ 1500 target.

Predecessor-tag narrative diff `c3a964c..HEAD` reported alongside
(does NOT gate; cycle-impact context only).

### S6 — lever-ledger confirm

WIRED_LEVER_LEDGER posture: **3 production / 0 soak unchanged**.

- v2.7 P1 bumped 2 → 3 (Seed v2.6-G step (2) `TIMEOUT_SECONDS` cap).
- v2.7 P2 added no production lever (re-measure is measurement, not
  wire).
- v2.7 P3 added no lever (was BLOCKED before reaching S7).
- v2.7.1 P1 adds no production lever (row-05 re-measure is
  measurement, not wire; Hatch A golden flip is a fixture
  re-baseline, not a production-bucket wire).
- v2.7.1 P2 adds no production lever (ship-gate is closure, not
  wire).

| Cycle | Wire                                                            | Bucket    |
|-------|-----------------------------------------------------------------|-----------|
| v2.3  | Seed 6 — JsonlTailWorker production wiring                      | src       |
| v2.6  | Seed v2.5-G step (1) — alignment-eval wall-clock instrumentation | tools/src |
| v2.7  | Seed v2.6-G step (2) — `TIMEOUT_SECONDS` cap                    | src       |

P2 PR body records HOLD verdict: 3 production / 0 soak posture.

### S7 — ADR-5 baseline append

Operator decides at P2 fire: APPEND new baseline row with
`TIMEOUT_SECONDS = 30.0` measurement, or hold.

**Default APPEND.** The v2.7 P1 latency-surface lever (Seed v2.6-G
step (2)) still ships in v2.7.1; ADR-5 cadence prefers append over
re-baseline. Append §"v2.7.1 ship-gate baseline" with:

- Source soak report path (S2 output).
- Per-band p50/p95 (ALLOW, L2, L3, L4, LM).
- Delta vs v2.6 P2 ship-gate baseline (Seed v2.4-E p95 + Seed v2.4-F
  L4/LM watches).
- Delta vs v2.7 P3 overnight soak (the BLOCKED measurement;
  particularly OQ-2 LM band post-exclusion).
- Lever ledger row (HOLD at 3 production / 0 soak).
- Alignment-eval gate verdict + per-model rates + eval wall-clock
  distributions p50/p95/p99 per model.
- v10 P4 corpus piggyback delta (Run 9 expected; 608 + Δ).
- Caveats — particularly the Hatch path selected and any row
  exclusions.

Operator overrides default at P2 fire if Hatch C escalation defers
ADR-5 append into v2.8 Convergence-cycle.

### S8 — CHANGELOG append

Append `## [2.7.1]` entry to `CHANGELOG.md` per Keep-a-Changelog
format. **NOT v2.7.0** — parent v2.7.0 never tagged per v1.3.1 /
v2.5.1 precedent.

Cover:
- **Carried from v2.7 P1 (`28a89c4`):** Seed v2.6-G step (2) timeout-
  tighten — `cli_governance.TIMEOUT_SECONDS` 25.0 → 30.0 (first
  FROZEN-surface lever ever wired; J2-audit-aware framing).
- **Corrective (v2.7.1 P1):** Seed v2.7-B row-05 re-eval
  diagnosis verdict (Hatch A / B / C string from §"P1 → P2 verdict-
  bridge" outcome).
- **Calibration (conditional — Hatch A only):** golden row-05
  `expected_verdict` flip to P1 n=12 majority.
- **Closed seeds:** Seed v2.4-E + Seed v2.4-F close-vote outcomes
  (per §"Close-vote rows"). Seed v2.7-B disposition (CLOSE
  under Hatch A; CARRY-WITH-EXCLUSION under Hatch B; CARRY-TO-v2.8-
  CONVERGENCE under Hatch C).
- **Carry-forwards:** see `docs/v2.7.1-backlog.md` — Seed v2.6-A,
  Seed v2.6-A-T, Seed v2.6-G step (3), Seed v2.6-C Path-D
  (6th-consecutive deferral if v2.8 elects consolidation; closed
  by v2.8 Convergence-cycle if elected), Seed v2.7-A-CLIP.
- **Removed:** none.

### S9 — tag v2.7.1

```
git tag -a v2.7.1 -m "v2.7.1 — corrective sub-cycle (v2.7 P3 BLOCKED at row-05 Haiku-stabilisation; Hatch <A/B/C> disposition)" <merge-SHA>
git push origin v2.7.1
```

**Tag value: v2.7.1 (NOT v2.7.0).** Per v1.3 → v1.3.1 precedent
(v1.3.0 was feature-complete but never soaked; `ad372d7` was the
v1.3.1 ship-gate-validated tag) and v2.5 → v2.5.1 precedent (v2.5.0
never tagged; PR #190 verdict-A shipped v2.5.1). v2.7.0 stays
untagged; v2.7.1 is the carry tag.

Fill the `<A/B/C>` placeholder from §"P1 → P2 verdict-bridge"
outcome.

### S10 — compare-back

Walk `docs/v2.7.1-next-steps.md` row-by-row. Every `[ ]` should now
read `[x] ✅ LANDED PR #__ (<SHA>)`, OR `[ ] DEFERRED v2.8 — <one-
line rationale>`, OR `[ ] DROPPED — <one-line rationale>`. Any
leftover `[ ]` BLOCKS ship; fold disposition into §"P2 close-out"
or carry to v2.8.

Append §"v2.7.1 P2 ship-gate close-out" outcome at the end of
`docs/v2.7.1-next-steps.md` with the row-by-row outcome.

### S11 — close memory

Mint `~/.claude/projects/C--Users-SeanHoppe-vs-streamManager/memory/
project_v271_cycle_close.md` (slug-safe filename — no dot between
`v27` and `1`, mirroring `project_v22_cycle_close.md` /
`project_v25_cycle_close.md` shape; v2.5.1 close-memory followed the
`project_v25_cycle_close.md` convention with sub-cycle content
folded in).

Cover:
- v2.7.1 ship SHA + date.
- v2.7 P3 BLOCK record (PR #207 disposition) — fold-as-corrective
  or merge-as-block-record path chosen at F1.
- v2.7.1 P1 verdict: row-05 Hatch A / B / C disposition.
- v2.7.1 P2 verdict: ship-gate PASS at chosen Hatch path.
- Alignment-eval Sonnet pass-rate post-corrective (track vs 0.9412
  v2.6 baseline; 7-cycle trajectory).
- Haiku pass-rate (6-cycle trajectory).
- Soak p95 / Haiku floor / regression rows.
- OQ-2 LM band disposition (single-outlier exclusion vs
  real-regression escalation).
- v10 P4 corpus delta (Run 9).
- Cycle-tip LOC delta (cumulative v2.7 P1 + v2.7.1 P1 + v2.7.1 P2)
  + WIRED_LEVER_LEDGER final (3 production / 0 soak).
- Carry-forwards to v2.8: Seed v2.6-A (carries per v2.7 P2
  STILL-100%-TIMEOUT-ESCALATE), Seed v2.6-A-T, Seed v2.6-G step (3),
  Seed v2.6-C Path-D, Seed v2.7-A-CLIP, plus any NEW v2.7.1 seeds.

Update MEMORY.md index with one-line hook entry.

### S12 — lifetime

Default: prompts persist as historical record (mirror v2.0–v2.6
lifetime decision; v2.5.1 corrective prompts also persist under
`docs/prompts/v2.5.1-corrective/`).

### S13 — mint v2.8 P0 frame

Per PM-mint precedent (PR #178 / PR #191 / PR #199), mint the v2.8
P0 frame ahead-of-fire. **Recommended frame: Convergence-cycle** per
`docs/2026-05-22-status.md` §"Proposal — Convergence cycle":

- Cycle type: FEATURE (3-in-a-row; Amendment A §"Default lean
  rationale" permits when ready FIRE candidates exist).
- Three bundled landings:
  1. Seed v2.6-C Path-D synthetic-fixture P5 (~600 LOC; `rl/` +
     tests).
  2. Seed v2.6-G step (3) env-split (`BRIDGE_CLI_TIMEOUT` prod /
     `BRIDGE_CLI_TIMEOUT_EVAL` eval; ~50 LOC; `src/cli_governance.
     py` + tests).
  3. Seed v2.7-A-CLIP corpus-wide re-measure at eval cap = 60 s
     (0 production LOC; reports only).
- Expected backlog deflation: 7 cap-counted → 2 cap-counted at v2.8
  close.
- Velocity gauge: v10 MVP 100% timeline collapses from 4 cycles
  (nominal) to 2 cycles under Convergence-cycle landing.

Mint:
- `docs/prompts/v2.8-orchestration/phase-0-cycle-frame.md` skeleton.
- `docs/v2.8-task-plan.md` skeleton.
- `docs/v2.8-next-steps.md` skeleton with carry-forwards from
  `docs/v2.7.1-backlog.md`.

Operator chooses cycle-type default-lean (Convergence vs alternation-
hygiene consolidation) at v2.8 P0 fire. If Hatch C fired at v2.7.1
P2, Convergence-cycle is the natural fallthrough.

### Close-vote rows

- **Seed v2.4-E (overall p95):** close ≤ 8.2 s; carry ≤ 10 s (would
  be 4th consecutive sub-10 reading if it holds at v2.7.1 P2);
  regression-flag > 10.156 s. **OQ-2 caveat:** the v2.7 P3 overnight
  soak reading of 13.957 s is dominated by the LM outlier; v2.7.1
  P2 S2 reading post-LM-exclusion is the binding measurement.
- **Seed v2.4-F (L4 half):** close ≤ 17 s; carry ≤ 22 s (reduced
  concern); promote 🔴 if ≥ 22 s. v2.7 P3 overnight reading
  recovered to 12.66 s under cap-tighten; expected to hold.
- **v10 P4 corpus piggyback (Run 9):** if `BRIDGE_RL_LOGGER_ENABLED=
  1`, record Δ episodes; ≥ 60 → CLEARED, < 60 → CARRY. Expected
  Run 9 total ≈ 668 (608 + 60).

## DoD

### Step (P2) mandatory

- [ ] S1 wipe + S1.1 assertion clean.
- [ ] S2 Tier-3 soak completed; `degrade_count = 0`; canonical env
      block exported; OQ-2 LM-band post-event distribution
      inspected.
- [ ] S3 invariant check exit 0; dual-anchor LOC matrix produced.
- [ ] S4 alignment-eval `--runs <P1-verdict-driven>` `--ci-gate`
      exit 0 under chosen Hatch path; per-row exclusion list
      documented.
- [ ] S5 cycle-tip LOC verified ≤ 1500 (soft); production-bucket
      breakdown documented (cumulative v2.7 P1 + v2.7.1 P1 + v2.7.1
      P2).
- [ ] S6 WIRED_LEVER_LEDGER posture verified **3 production / 0
      soak**.
- [ ] S7 ADR-5 baseline disposition recorded (APPEND default; hold
      under Hatch C if escalating to v2.8).
- [ ] S8 CHANGELOG `## [2.7.1]` entry appended.
- [ ] S9 tag v2.7.1 created + pushed.
- [ ] S10 compare-back walk complete; no leftover `[ ]`.
- [ ] S11 `project_v271_cycle_close.md` minted + MEMORY.md index
      entry added.
- [ ] S12 lifetime decision recorded.
- [ ] S13 v2.8 P0 skeleton minted (Convergence-cycle frame
      recommended).
- [ ] Close-vote rows recorded (Seed v2.4-E, v2.4-F, v10 P4
      piggyback).

### Cycle-discipline

- [ ] LOC budget: production-bucket cumulative cycle-tip delta
      documented; inside soft ≤ 1500 / BLOCK 2250.
- [ ] WIRED_LEVER_LEDGER unchanged at P2 (P2 is closure, not wire).
- [ ] Sub-cycle close-out diff guard per
      `feedback_subagent_stale_mental_model.md`: confirm P2 touched
      only the documented surface (CHANGELOG + docs + ADR-5 +
      memory; conditional Hatch-A golden flip only).
- [ ] Single PR against `main` (`ship(v2.7.1):` conventional
      commits prefix).
- [ ] No re-fire of v2.7 P1 edits (cap stays 30.0; latency budget
      stays 45_000).
- [ ] No re-fire of v2.7.1 P1 edits beyond the Hatch-A conditional
      fixture flip already landed at P1.

### ADR-18 surface-classification

- [ ] PR body documents: v2.7.1 P2 fires no new lever wire. v2.7 P1's
      FROZEN-surface lever (Seed v2.6-G step (2)) ships **as part of**
      v2.7.1 — the J2-audit framing already documented at v2.7 P1
      fire (PR #203) is cited verbatim in
      `project_v271_cycle_close.md`.
- [ ] PR body cites: v2.7 P1 PR #203 (`28a89c4`), v2.7 P2 PR #206
      (`59bee5c`), v2.7 P3 BLOCK PR #207, v2.7.1 P1 PR #___
      (`<v2.7.1-P1-merge-SHA>`), J1 protocol
      (`docs/seed-v2.7-b-row05-haiku-protocol.md`), J2 audit
      (`docs/seed-v2.6-g-step2-timeout-tighten-audit.md` — falsified
      at v2.7 P2 but lever ships anyway).

### Memory + docs

- [ ] `project_v271_cycle_close.md` minted with all verdict cites
      filled.
- [ ] MEMORY.md index updated.
- [ ] No new FR row in `REQUIREMENTS.md` (P2 is ship, not contract
      delta).
- [ ] No new ADR-18 amendment minted in v2.7.1 (sub-cycle inherits
      Amendments A–E).

## Cross-refs

- `docs/prompts/v2.7-orchestration/phase-3-ship-gate.md` — v2.7 P3
  stub; structural ancestor of this v2.7.1 P2 stub. BLOCKED at
  S4 CI gate FAIL; v2.7.1 absorbs the corrective scope.
- `docs/prompts/v2.6-orchestration/phase-2-ship-gate-finalize.md` —
  v2.6 P2 full S1–S13 procedure template (the most thorough
  ship-gate template; v2.7 P3 and v2.7.1 P2 both mirror this shape).
- `docs/prompts/v2.5.1-corrective/phase-2-shipgate-refire.md` —
  v2.5.1 P2 ship-gate refire precedent (verdict-A path; minimum-
  diff re-fire of v2.5 P2 prompt). v2.7.1 P2 inherits the
  minimum-diff-of-parent-ship-gate pattern.
- `docs/prompts/v2.7.1-corrective/phase-1-row-05-haiku-investigation.md` —
  J2 P1 prompt (sibling artefact; minted in same PM-mint bundle).
- `docs/seed-v2.7-b-row05-haiku-protocol.md` — J1 protocol
  (sibling artefact; consumed by v2.7.1 P1; cited at §"P1 → P2
  verdict-bridge").
- `docs/v2.7.1-task-plan.md` §"PHASE P2" — ledger destination
  (minted by J4 in PM-mint bundle).
- `docs/v2.7.1-next-steps.md` §"Fire-order" + close-vote rows —
  compare-back markers (minted by J4).
- `docs/2026-05-22-task-list.md` §"J3" — this prompt's own scope
  spec.
- `docs/2026-05-22-status.md` §"Proposal — Convergence cycle" — v2.8
  P0 frame source for S13.
- `feedback_alignment_eval_stability_window.md` — n=6 escape-hatch
  rule (hatch (3) bound; hatch (4) used under Hatch B / C).
- `feedback_soak_cli_pool_flag.md` — `--cli-pool-size 2` mandatory.
- `feedback_glob_narrowing_no_op.md` — S1 wipe pattern.
- `feedback_subagent_stale_mental_model.md` — sub-cycle close-out
  diff guard.
- `feedback_subagent_long_task_abandonment.md` — S2 Tier-3 launch
  from main thread only.
- `feedback_monitoring_live_sessions.md` — S2 soak Monitor
  template.
- `feedback_cli_over_sdk.md` — `claude -p` subprocess path.
- `feedback_certportal_dev_firewall.md` — firewall in force; no
  certPortal coupling introduced.
- `feedback_no_self_monitor.md` — no SM self-monitor surface added.
- ADR-18 Rule 1 (surface freeze) — v2.7.1 P2 touches no FROZEN
  surface (conditional Hatch-A golden flip is fixture, not
  production).
- ADR-18 Amendment A (3-bucket LOC) — v2.7.1 P2 docs-bucket only;
  conditional tests-bucket micro-delta under Hatch A.
- ADR-18 Amendment B (memory pre-flight) — light re-verify at P2.
- ADR-18 Amendment C (cycle-tip anchor) —
  `4902cca440b33c14fddd9357116923ae5fe1fa4b` RETAINED; v2.5.1
  precedent applied.
- ADR-18 Amendment D (v10 P5 gate split) — unchanged scope; v2.7.1
  does not touch v10 P5.
- ADR-18 Amendment E (Rule 5 cycle-handoff exemption) — unchanged
  scope.
- Precedent sub-cycle ships:
  - v1.3 → v1.3.1 at `ad372d7` (PR #75 Path-A; v1.3.0 never
    ship-gate-validated; v1.3.1 is the carry tag).
  - v2.5 → v2.5.1 at PR #190 verdict-A (v2.5.0 never tagged; v2.5.1
    is the carry tag).

## Stub → final fold task list (at v2.7.1 P2 fire-PR open)

When opening the v2.7.1 P2 fire-PR, the operator (or this prompt's
finalisation step) replaces the TBD blocks listed in the header
with verbatim values pulled from v2.7.1 P1 LANDED:

1. **Hatch decision** (A / B / C / STILL-100%-TIMEOUT-ESCALATE) —
   pin into §"P1 → P2 verdict-bridge" table row + §S11 close-memory
   bullet + §S9 tag message.
2. **v2.7.1 P1 merge SHA** — fill `<v2.7.1-P1-merge-SHA>` and
   `<P1 PR #___>` placeholders (multiple sites: S2 / S3 / S5 / DoD
   citation).
3. **`--runs` final value** — fill §S4 invocation block (6 baseline
   under Hatch A/B; consider 12 under Hatch C).
4. **Golden flip flag** — Hatch A only; record fixture-flip line
   count in §S5 expected LOC tally.
5. **Row-05 exclusion list** — record exclusion flag/value in §S4
   invocation block + §"Close-vote rows" caveat.
6. **Cumulative cycle-tip LOC tally** — fill §S5 expectation block
   (v2.7 P1 +8 / −6 + v2.7.1 P1 +0–5 tests + v2.7.1 P2 0).
7. **ADR-5 baseline disposition** — APPEND (default) vs hold under
   Hatch C escalation; record in §S7.
8. **OQ-2 LM disposition** — single-outlier exclusion vs real-
   regression escalation (record in §S2 OQ-2 risk note + §S7 ADR-5
   delta + §S11 close-memory).
9. **v2.8 P0 frame choice** — Convergence-cycle (recommended) vs
   alternation-hygiene consolidation; record in §S13 mint.

This stub does NOT autonomously fire. It is the structure-and-
parameter holder; the v2.7.1 P2 fire-PR fold turns it into an
executable script.

## Report back

When v2.7.1 P2 fire-PR opens, report back with:

1. **PR URL.**
2. **Final-fold delta** (this stub → fire-PR final form; the 9 TBD
   slots filled per §"Stub → final fold task list").
3. **v2.7.1 tag SHA + push confirmation.** (Or ABORT-before-S9
   record under Hatch C / STILL-100%-TIMEOUT-ESCALATE path —
   document in PR body and the v2.7.1 close-memory.)
4. **`project_v271_cycle_close.md` paste** — full close-memory body.
5. **Full cycle-discipline LOC matrix** — cumulative cycle-tip
   delta (v2.7 P1 + v2.7.1 P1 + v2.7.1 P2) with per-bucket
   breakdown.
6. **WIRED_LEVER_LEDGER posture** — confirm 3 production / 0 soak
   unchanged.
7. **Hatch path selected** + verdict matrix outcome from §"P1 → P2
   verdict-bridge".
8. **OQ-2 LM band disposition** — single-outlier vs real-
   regression call.
9. **v2.8 P0 frame mint** — Convergence-cycle frame skeleton paths
   if S13 fired.
