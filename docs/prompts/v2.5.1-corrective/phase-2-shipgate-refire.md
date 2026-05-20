# v2.5.1 P2 — Ship-gate refire (verdict-A path)

> Minted 2026-05-20 at v2.5.1 P1 close. Verdict-A path per
> `docs/v2.5.1-sonnet-floor-investigation.md` §"Root-cause verdict":
> the v2.5 P2 BLOCK at S4 was a **measurement artefact** (3-run
> unanimous-agreement window too narrow under CLI-timeout pressure
> near FR-OG-7 floor). n=6 re-measure cleared the floor at
> `pass_rate=0.9375` (15/16). v2.5.0 may ship; target tag becomes
> **v2.5.1** per v1.3 → v1.3.1 precedent (P1 prompt §"Mint-new-phase
> rule").
>
> Format: **minimum-diff re-fire of**
> `docs/prompts/v2.5-orchestration/phase-2-ship-gate-finalize.md`.
> All clauses in that prompt remain in force unless explicitly
> overridden below. Operator runs S1–S13 from the v2.5 P2 prompt with
> the deltas in §"Deltas vs v2.5 P2" applied.

## Branch + base

- Base: `main` after the v2.5.1 P1 corrective PR (which lands this
  prompt + the investigation doc + n=6 reports + stability-window
  memory) merges.
- PR target: `main`.
- Branch: `ship/v2.5.1-shipgate-finalize` (replaces
  `ship/v2.5-shipgate-finalize` from the v2.5 P2 attempt — that
  work-PR was never opened per `docs/v2.5-task-plan.md` §"P2 ship-gate
  BLOCK").
- ABORT if v2.5.1 P1 PR not merged at HEAD, or if HEAD has drifted
  from v2.5 P0 cycle-tip lineage `634e9d1`.

## Pre-flight

Run the v2.5 P2 pre-flight (Amendment B memory pre-flight) as
written, with one addition:

- `feedback_alignment_eval_stability_window.md` — verify FRESH
  (minted 2026-05-20 at v2.5.1 P1). The S4 step below CITES this
  rule.

## ⚠️ Cycle-tip anchor (unchanged)

ADR-18 Amendment C cycle-tip anchor stays at
`634e9d1d982a3b6071bfe78c369c4995419e2d44` (v2.5 P0 merge SHA). The
v2.5.1 P1 corrective PR adds docs + reports + memory ONLY — it does
NOT bump the cycle-tip and does NOT alter production-bucket LOC
delta. Net production LOC ≤ 0 vs `634e9d1` still binds at v2.5.1 P2.

## Deltas vs v2.5 P2 prompt

### S4 — Alignment-eval (REPLACE)

Replace the v2.5 P2 S4 block in full with:

> **S4 has two paths. Operator picks at S4-fire based on time budget.**
>
> **S4-path-1 (default — cite n=6 evidence):** Skip the local fire.
> S4 PASS evidence is the v2.5.1 P1 re-measure already on disk:
> `reports/alignment-eval-20260520T092222Z.{md,json}` — Sonnet
> `pass_rate=0.9375` (15/16 stable+pass), Haiku 1.0 (15/15),
> `regression_rows=[]`, `frog7_regression_rows=0`. Document in P2 PR
> body that S4 ran at n=6 in the P1 corrective phase and was not
> re-fired at P2 to avoid duplicate ~80-min wall.
>
> **S4-path-2 (operator choice — fresh n=6 fire):** Re-fire fresh
> against current `main` HEAD post-P1-merge:
>
> ```
> python tools/alignment_eval.py --runs 6 --ci-gate
> ```
>
> ≥ 0.80 FR-OG-7 floor required (Sonnet + Haiku). Per
> `feedback_alignment_eval_stability_window.md`, n=6 is the
> mandated sample size when prior cycle Sonnet `pass_rate` was within
> 0.05 of floor — v2.5 P2 ran at default `--runs 3` and that is what
> drove the BLOCK; v2.5.1 P2 MUST run at n=6 if firing fresh.
>
> **Either path:** record the 5-cycle Sonnet trajectory in the P2 PR
> body as `v2.1 → v2.2 → v2.3 → v2.4 → v2.5` =
> `0.8636 → 0.9474 → 0.8182 → 0.8261 → 0.9375` (n=6 reading; n=3
> reading 0.7895 superseded — note both in narrative). Haiku
> trajectory `v2.2 → v2.3 → v2.4 → v2.5` =
> `0.85 → 0.9412 → 1.0 → 1.0`.
>
> Seed v2.4-Q (Sonnet-DIP FREEZE-on-content) at v2.5.1 P2: the n=6
> 0.9375 reading lands in the **RECOVERED** band (≥ 0.90 per v2.5 P2
> S4 disposition table). Close Seed v2.4-Q at v2.5.1 P2 ship-gate
> per that table.
>
> Seed v2.5-A (`frog7-wirecli-module-10` 100% timeout opacity)
> carries forward to v2.6 — it is a measurement-blind spot, not a
> content drift; resolves when Seed v2.4-G timeout-instrumentation
> lands. Record in `docs/v2.5-backlog.md` at S10/S11.

### S2 — Tier-3 soak (NO CHANGE)

Fire as written in v2.5 P2 S2. The soak does NOT need a refire for
this corrective cycle (no production-bucket code change since the
v2.5 P2 BLOCK). However, S2 still fires per cycle protocol to
re-confirm canary + dual-anchor LOC at the post-corrective HEAD.

### S5 — LOC delta verification (NO CHANGE)

Cycle-tip anchor `634e9d1` still binds. v2.5.1 P1 PR is docs+reports
+memory only → production-bucket net delta stays 0 vs cycle-tip.
Cross-check the dual-anchor block in the S2 soak summary.

### S8 — CHANGELOG entry (MODIFY)

Replace `## [2.5.0]` with `## [2.5.1]`. Include in the entry:

- Header note: "v2.5.0 BLOCKED at S4 alignment-eval on 2026-05-19
  (Sonnet `pass_rate=0.7895 < 0.80` FR-OG-7 floor at n=3); v2.5.1
  P1 corrective phase re-measured at n=6 → `pass_rate=0.9375`,
  verdict A (measurement artefact). See
  `docs/v2.5.1-sonnet-floor-investigation.md`."
- New entry: "Mandated n=6 alignment-eval sample size at ship-gate
  when prior cycle Sonnet `pass_rate` is within 0.05 of FR-OG-7
  floor. See `feedback_alignment_eval_stability_window.md`."
- Seeds closed: Seed v2.4-Q (Sonnet-DIP FREEZE-on-content,
  RECOVERED at n=6).
- Seeds carried: Seed v2.5-A (wirecli-module-10 100% timeout
  opacity); all other v2.5 carries unchanged.

### S9 — Tag (MODIFY)

Tag **v2.5.1** (not v2.5.0). Precedent: v1.3 → v1.3.1 (PR #75 Path-A,
`ad372d7`). v2.5.0 is the consensus cycle-frame state at P0
(`634e9d1`); v2.5.1 is the first ship-gate-validated tag for the
v2.5 cycle.

### S10 — Compare-back (MODIFY)

In addition to the v2.5 P2 compare-back rows, mark:

- Seed v2.4-Q row → CLOSED at v2.5.1 P2 (n=6 RECOVERED).
- NEW row: Seed v2.5-A — `frog7-wirecli-module-10` 100% timeout
  opacity → carry to v2.6 alongside Seed v2.4-G instrumentation.

### S11 — Close memory (MODIFY)

Mint `project_v25_cycle_close.md` covering BOTH v2.5 P0 + v2.5 P2
BLOCK + v2.5.1 P1 corrective + v2.5.1 P2 ship. Single close memory
for the cycle; do not split.

## Everything else: re-use v2.5 P2 verbatim

S1 (wipe), S1.1 (post-wipe assertion), S2 (Tier-3 soak with
`BRIDGE_CYCLE_TIP_SHA=634e9d1d982a3b6071bfe78c369c4995419e2d44`), S3
(invariant-degrade canary), S6 (lever-ledger HOLD), S6.5 (Seed v2.4-G
promotion re-confirm), S7 (ADR-5 baseline append — conditional), S12
(lifetime cleanup), S13 (mint-new-phase rule) all carry over from
`docs/prompts/v2.5-orchestration/phase-2-ship-gate-finalize.md`
unmodified.

## DoD

- [ ] S2 soak PASS at post-corrective HEAD, canary PASS, dual-anchor
      LOC block matches manual computation.
- [ ] S4 evidence: cite n=6 P1 report (path-1) OR fresh n=6 refire
      with ≥ 0.80 floor (path-2). Record path choice in PR body.
- [ ] S8 CHANGELOG `## [2.5.1]` entry as above.
- [ ] S9 `v2.5.1` tag pushed.
- [ ] S10 compare-back marks Seed v2.4-Q CLOSED + Seed v2.5-A NEW.
- [ ] S11 `project_v25_cycle_close.md` minted + indexed in
      `MEMORY.md`.
- [ ] Single PR `ship(v2.5.1):` against `main`.

## Mint-new-phase rule (this phase ships)

After v2.5.1 tag fires:

- Mint `docs/prompts/v2.6-orchestration/phase-0-cycle-frame.md`
  (consolidation-or-feature pick at operator-call time).
- v2.6 planned levers (per v2.5 carry-forwards + new Seed v2.5-A):
  Seed v2.4-G CLI-timeout instrumentation (now also resolves
  wirecli-module-10 opacity), Seed v2.4-C Path-D P5 RL track, plus
  whatever v2.5.1 ship-gate seeds emerge.

If v2.5.1 P2 itself blocks (it should not — re-measure already
cleared the floor) mint `phase-3-<blocker>.md` per v2.5.1 P1
precedent.
