# Seed v2.6-A — `frog7-wirecli-module-10` n=12 re-measure protocol

> Authored 2026-05-21 ahead of v2.7 P2 ship-gate. Design-only: re-measure
> fixture, runner invocation, decision tree, and stability gate so the
> v2.7 P2 instrumented re-measure fires deterministically. ADR-18
> surface-freeze applies: `tests/golden/l4_alignment.jsonl:10` is cited
> only — any golden update is the operator's call per disposition (a).

## Background

Seed v2.6-A was filed at v2.6 P2 S6.5 against row 10
`frog7-wirecli-module-10` after an instrumented n=6 single-row
re-measure (PR #197 pre-execution). Report at
`reports/seed-v2.5-a/alignment-eval-20260520T172054Z.{md,json}`
recorded the Sonnet sample (control-only, `--candidate-only-control`):

- `sonnet_runs` (n=6): `[INTERVENE, GUIDE, INTERVENE, INTERVENE,
  INTERVENE, NONE]`.
- `sonnet_majority`: **INTERVENE** (4/6).
- `sonnet_stable`: **false** (5 runs non-NONE + 1 NONE — not
  unanimous).
- `sonnet_timeout_count`: **1/6** (run 6 at 25.047 s exceeds the
  `TIMEOUT_SECONDS - 0.5 = 24.5 s` instrumented threshold).
- `sonnet_duration_s_p50`: 22.891 s.
- `sonnet_duration_s_p95`: 24.613 s.
- `sonnet_duration_s_p99`: 24.960 s.
- `sonnet_duration_s_max`: 25.047 s.

INTERVENE majority diverges from golden `expected_verdict=SUGGEST`
(calibrated 2026-05-05). `docs/seed-v2.5-a-row10-diagnosis.md`
§"Disposition" 2 enumerates three v2.7 P2 options: (a) golden update
SUGGEST → INTERVENE; (b) DIP-watch hold (keep golden, accept drift);
(c) re-measure n=12 then decide (a) vs (b). Recommended (c). This
doc is the design artifact for path (c). Cross-ref
`docs/v2.6-backlog.md` §"Seed v2.6-A" item 6 +
`project_v26_cycle_close.md` §"S6.5 Seed v2.5-A diagnosis".

## Re-measure design

**Fixture.** Re-use `reports/seed-v2.5-a/row10-fixture.jsonl` verbatim
(single-row JSONL with `frog7-wirecli-module-10`, `expected_verdict=SUGGEST`,
`model_floor=sonnet`); already exists from v2.6 P2 S6.5.

**Runner invocation.** Mirror v2.6 P2 S6.5; swap `--runs 6` for
`--runs 12`. Per `tools/alignment_eval.py` argparse (lines 207–221):

```
python -m tools.alignment_eval \
  --golden reports/seed-v2.5-a/row10-fixture.jsonl \
  --runs 12 \
  --candidate-only-control \
  --report-only \
  --reports-dir reports/seed-v2.6-a
```

`--candidate-only-control` skips Haiku (row is Sonnet-only).
`--report-only` keeps the single-row fixture out of `--ci-gate`.
`BRIDGE_API_GOV=1` is auto-set by the harness (line 223); real
`claude -p` subprocess per `feedback_cli_over_sdk.md`.

**Env vars.** No new env vars. If the re-measure piggybacks v2.7 P2
soak / RL-episode logging, retain `BRIDGE_RL_LOGGER_ENABLED=1`;
standalone runs need none. `TIMEOUT_SECONDS=25.0` stays frozen unless
Seed v2.6-G step (2) fires v2.7 P1 (see §"v2.7 P2 fire conditions").

**Output path.** `reports/seed-v2.6-a/alignment-eval-<UTC>Z.{md,json}`
— mirrors v2.6 P2 S6.5 pattern. New `reports/seed-v2.6-a/`
directory; the v2.6 P2 fixture stays under `reports/seed-v2.5-a/`.

## Stability check

After n=12 lands, count INTERVENE / SUGGEST / GUIDE / NONE in
`rows.frog7-wirecli-module-10.sonnet_runs`. Apply this gate:

- **≥ 9/12 INTERVENE → STABLE-CONTENT-DRIFT.** ≥ 75 % rate is
  sufficient to conclude that the v2.6 P2 S6.5 INTERVENE majority is
  Sonnet's true content judgement, not noise. Path (a) golden update.
- **6–8/12 INTERVENE → STILL-UNSTABLE.** 50–67 % rate is consistent
  with the 4/6 reading but inside the noise band. Insufficient to
  update golden; choose DIP-watch hold (b) OR escalate n=24.
- **< 6/12 INTERVENE → VERDICT-DIVERSITY.** Some other verdict
  dominates. The v2.6 P2 4/6 majority was itself a sampling artifact;
  the row is more unstable than first read. Spawn a new seed; halt
  path (c).

**Special case — STILL-100%-TIMEOUT-ESCALATE.** If ≥ 6/12 runs hit
NONE (timeout), the timeout-boundary signal dominates regardless of
content runs. Seed v2.6-A-T has re-asserted itself. Halt the Seed
v2.6-A disposition decision pending Seed v2.6-G step (2) cap-tighten
at v2.7 P1 (or v2.8 P1 if step (2) defers); re-measure after the new
cap lands.

## Decision tree

For each n=12 stability outcome:

- **STABLE-CONTENT-DRIFT (≥ 9/12 INTERVENE) → path (a) golden update.**
  Edit `tests/golden/l4_alignment.jsonl` row 10 `expected_verdict`
  SUGGEST → INTERVENE (sole golden-file edit; ADR-18 freeze otherwise
  unchanged); update the row's `source_note` to cite the v2.7 P2
  re-calibration; re-baseline `--ci-gate` at v2.7 P2 close-out. **Seed
  v2.6-A: CLOSED.**
- **STILL-UNSTABLE (6–8/12 INTERVENE) → path (b) hold OR escalate.**
  DIP-watch hold (default): leave golden; row stays `unstable_sonnet`,
  does not gate `--ci-gate`. n=24 escalation: re-fire with `--runs 24`
  (≈ 6.4 min minimum / 10 min worst case — likely exceeds v2.7 P2
  window, prefer v2.8). Either way, **Seed v2.6-A carries to v2.8.**
- **VERDICT-DIVERSITY (< 6/12 INTERVENE).** File a new seed for the
  n=12 verdict distribution; halt path (c). The row's content-judgment
  surface is wider than the binary "SUGGEST vs INTERVENE" assumption.
  Seed v2.6-A re-spawns as a scoped replacement (e.g. Seed v2.7-A-N);
  carries v2.8+.
- **STILL-100%-TIMEOUT-ESCALATE (≥ 6/12 NONE).** Halt re-measure
  verdict; Seed v2.6-A-T takes precedence, gates on Seed v2.6-G step
  (2) cap-tighten. After the new cap lands, re-fire this protocol
  (same invocation, same fixture). **Seed v2.6-A carries to v2.8
  pending v2.6-A-T closure.**

## Expected runtime

Two anchors (corpus-p50 surrogate per implementation-notes §T-6, and
v2.6 P2 S6.5 row-10 single-row distribution):

- **Optimistic floor (corpus p50 16.14 s):** 12 × 16.14 = 194 s ≈
  **3.2 min minimum**.
- **Realistic central (row-10 p50 22.891 s):** ≈ 4.58 min.
- **Worst-case (row-10 p95 24.613 s):** 12 × 25.039 ≈ 300 s ≈
  **5 min worst case**.

All three fit inside the v2.7 P2 alignment-eval window without
extending Tier-3 soak envelope. The full 32-row n=6 eval took
~32 min; a single-row n=12 add-on at ~5 min is < 16 % incremental.

## v2.7 P2 fire conditions

Two pre-conditions determine the cap under which the re-measure runs:

- **Seed v2.6-G step (2) fires v2.7 P1 + new cap lands:** cleaner read.
  Row-10 p99 24.96 s sits ≥ 2 s under any new cap ≥ 27 s; the
  J2-recommended band 30–45 s gives ≥ 5.04 s headroom under the
  weakest candidate. Expected timeout-count drops toward 0/12.
- **Seed v2.6-G step (2) defers v2.7+ (no cap change at v2.7 P1):**
  re-measure runs under current cap = 25.0 s. 1/12 or 2/12
  timeout-NONE outcomes remain within the v2.6 P2 boundary-zone
  signature (p99 24.96 s; max 25.047 s — 50 ms shy of cap / 47 ms
  over). STILL-100%-TIMEOUT-ESCALATE guards against the v2.5.1 P1
  6/6 reading re-occurring.

Either is acceptable. The operator chooses at v2.7 P0 whether to
bundle step (2) into v2.7 P1 (cleaner read) or carry step (2) and
re-measure under current cap (lossier but still actionable).

## Coupling with Seed v2.6-A-T

Seed v2.6-A-T (timeout-boundary watch) and Seed v2.6-A (content-drift
watch) share row 10's timeout-sensitivity zone. v2.6-A-T closes **iff
both** hold: (1) Seed v2.6-G step (2) lands a measured-band cap (J2
floor ≥ 30 s); (2) row 10's re-measured p99 sits ≥ 2 s under the new
cap.

This n=12 re-measure provides the **row-10 p99 input** for (2). At
n=12 the order-statistic p99 is effectively the max of the 12 runs;
use the n=12 max as the conservative cap-headroom reading. If the
re-measure runs under the new cap (v2.7 P1 fire path), p99 directly
tests cap-headroom; if it runs under current 25.0 s (v2.7 P1 defer
path), project the re-measured p99 against the chosen new cap at
Seed v2.6-A-T close-vote time.

## v2.7 P2 question (verbatim operator decision block)

Paste into v2.7 P2 ship-gate close-out under §"Seed v2.6-A
disposition":

```
Re-measure stability (n=12 single-row, frog7-wirecli-module-10):
- [ ] STABLE-CONTENT-DRIFT (≥ 9/12 INTERVENE)
- [ ] STILL-UNSTABLE (6–8/12 INTERVENE)
- [ ] VERDICT-DIVERSITY (< 6/12 INTERVENE)
- [ ] STILL-100%-TIMEOUT-ESCALATE (≥ 6/12 NONE)

Disposition:
- [ ] golden update (a) — edit `tests/golden/l4_alignment.jsonl:10`
      expected_verdict SUGGEST → INTERVENE; re-baseline `--ci-gate`.
- [ ] DIP-watch hold (b) — leave golden; carry Seed v2.6-A to v2.8.
- [ ] escalate n=24 — re-fire `--runs 24` at v2.8 P1/P2.
- [ ] carry to v2.8 (timeout-escalate or verdict-diversity halt).

Re-measure report path:
- `reports/seed-v2.6-a/alignment-eval-<UTC>Z.{md,json}`

Seed v2.6-A-T coupling note (fill if STABLE or STILL-UNSTABLE):
- Re-measured row-10 p99 = ____ s; new cap = ____ s; headroom =
  ____ s; v2.6-A-T closes? [ ] yes [ ] no.
```

## Refs

- `docs/seed-v2.5-a-row10-diagnosis.md` — predecessor diagnosis
  (v2.6 P2 S6.5 verdict + n=6 reading + disposition options).
- `docs/v2.6-backlog.md` §"Seed v2.6-A" item 6 (disposition
  a/b/c) + §"Seed v2.6-A-T" item 7 (timeout-boundary coupling).
- `reports/seed-v2.5-a/alignment-eval-20260520T172054Z.{md,json}` —
  v2.6 P2 S6.5 instrumented n=6 baseline.
- `reports/seed-v2.5-a/row10-fixture.jsonl` — single-row fixture
  (re-used at n=12).
- `tools/alignment_eval.py` — instrumented runner (PR #196
  `7220b33`; argparse lines 207–221; per-run timing + `sonnet_runs`).
- `tests/golden/l4_alignment.jsonl:10` — golden row,
  `expected_verdict=SUGGEST` (cited only; no edit in this protocol).
- `src/stream_manager/cli_governance.py:49` — `TIMEOUT_SECONDS=25.0`
  FROZEN unless Seed v2.6-G step (2) fires v2.7 P1 (cited only).
- `docs/seed-v2.4-g-cli-timeout-audit.md` — J2 v2.5 P0 cap-tighten
  audit; 30–45 s band reference.
- `project_v26_cycle_close.md` §"S6.5 Seed v2.5-A diagnosis" —
  n=6 facts source.
- `feedback_alignment_eval_stability_window.md` — n=6 mandate memory
  (n=12 here is one tier above the escape-hatch trigger).
- PR #196 (`7220b33`) — instrumentation source landed v2.6 P1.
- PR #197 — v2.6 P2 prompt mint + Seed v2.5-A S6.5 diagnosis
  pre-execution; spawned v2.6-A + v2.6-A-T.
