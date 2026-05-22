# Seed v2.7-A-CLIP — corpus-wide cap-clip re-measure protocol

- Generated: 2026-05-22
- Cycle: v2.7 P3 BLOCKED → v2.8 P0 cycle-type decision input (J5 of
  `docs/2026-05-22-task-list.md`)
- Status: 🔴 (Seed v2.7-A-CLIP ELEVATED at v2.7 P3 S4 corpus-wide cap-clip
  confirmation; protocol design-only at this fire-time)
- Predecessor (parent, FALSIFIED): `docs/seed-v2.6-g-step2-timeout-tighten-audit.md`
  (v2.6 J2; cap=30 s recommendation driven by clipped Sonnet n=192
  distribution under old 25 s ceiling).
- Predecessor (structural cousin): `docs/seed-v2.6-a-row10-remeasure-protocol.md`
  (v2.6 J3; row-level re-measure design + decision tree + fire-condition
  template; this doc is the corpus-wide analogue).
- **Lifetime:** Carries through v2.8 P0 cycle-type decision; consumed at
  v2.8 P2 alignment-eval window if the Convergence-cycle frame elects.
  Discardable once v2.8 P2 re-measure report lands.

This doc is a **measurement protocol only**. It does NOT modify
`src/stream_manager/cli_governance.py`, `tools/alignment_eval.py`, the
golden corpus, or any test fixture. `TIMEOUT_SECONDS = 30.0` (installed
at v2.7 P1 PR #203 `28a89c4`) remains FROZEN under ADR-18 surface-
freeze through this protocol's lifetime. Purpose: bound the operator's
**v2.8 P0** decision surface for the Convergence-cycle proposal
(`docs/2026-05-22-status.md` §"Proposal — Convergence cycle"). Does
**not** fire at v2.7.1; see §"Fire conditions" below.

## §Background — the cap-clip artefact

The cap-clip artefact is the consequence of measuring a wall-clock
response distribution under a ceiling that already clips the upper
tail. Causality chain across v2.6 / v2.7:

1. **v2.6 P1 — instrumentation under old 25 s cap (PR #196 `7220b33`).**
   Seed v2.5-G step (1) wired per-run wall-clock timing into
   `tools/alignment_eval.py` with `TIMEOUT_SECONDS = 25.0` frozen.
   n=192 sample (32 rows × n=6 escape-hatch) reported Sonnet p99 =
   **25.048 s**, max = 25.063 s — both sit approximately *at* the
   cap. On `subprocess.TimeoutExpired` the harness records a value
   within ~50 ms of the cap; the percentile-counter cannot see what
   the response would have taken absent the cap. The "p99 = 25.048 s"
   reading was the **cap-clip frequency**, not the true response p99.

2. **v2.7 P0 — J2 audit recommendation (cap = 30 s).**
   `docs/seed-v2.6-g-step2-timeout-tighten-audit.md` evaluated five
   candidate caps (28 / 30 / 35 / 40 / 45 s) against the v2.6 P1
   distribution. Primary recommendation: **30 s** — clears measured
   p99 (25.048 s) with ~5 s headroom (~20% margin). The structural
   blindness: the recommendation was computed against a clipped
   distribution, so the "margin" was a margin against the clip
   frequency, not against the true response tail.

3. **v2.7 P1 — wired cap = 30 s (PR #203 `28a89c4`).** Seed v2.6-G
   step (2) landed `TIMEOUT_SECONDS = 25.0 → 30.0`. First FROZEN-
   surface lever-wire ever shipped; WIRED_LEVER_LEDGER 2 → 3.

4. **v2.7 P2 — row-10 n=12 re-measure (PR #206 `59bee5c`).** Row-10
   (`frog7-wirecli-module-10`) re-measured under the new 30 s cap at
   n=12 per the J3 protocol (`docs/seed-v2.6-a-row10-remeasure-protocol.md`).
   `reports/seed-v2.6-a/alignment-eval-20260521T230415Z.{md,json}`:
   counts NONE=8 / INTERVENE=3 / BLOCK=1; p50 30.062 s / p95 30.086 s
   / **p99 30.092 s** / max 30.094 s; 9/12 timeouts; verdict
   **STILL-100%-TIMEOUT-ESCALATE**; Seed v2.6-A-T margin 30.0 −
   30.092 = **−0.092 s** (NEGATIVE). Cap-clip confirmed at one row.

5. **v2.7 P3 S4 — corpus-wide confirmation (PR #207, BLOCKED).** The
   ship-gate alignment-eval `--runs 6` found the row-10 pattern is
   **not row-specific**: multiple rows show Sonnet p99 at-or-near
   the new 30 s cap. Seed v2.7-A-CLIP elevates from "hypothesised
   at v2.7 P2" to "confirmed corpus-wide at v2.7 P3". See
   `docs/2026-05-22-status.md` §"v2.7 P3 ship-gate verdict (PR #207
   — BLOCKED)" two-front diagnosis (2).

**Inference.** Sonnet's TRUE response distribution extends beyond 30 s
for an unknown subset of rows in the v2.7 golden corpus. The current
30 s cap mechanically clips them, just as the previous 25 s cap
clipped a (likely larger) subset. The v2.6 P1 instrumentation under
the old cap could never have surfaced this — by construction, the cap
shaped the upper tail of its own reading.

## §Why this matters

Without the true Sonnet response distribution, every future cap-
related decision is structurally blind in the same way the J2 audit
was:

- **Cap-tighten candidates** (e.g. v2.8+ "30 → 28 s") cannot be
  evaluated; any tighten lands on a clipped reading and falsifies one
  cycle later.
- **Cap-loosen candidates** (e.g. eval-only widen) cannot be sized
  without knowing the response p99 / max under a ceiling wide enough
  that the cap is not binding.
- **Seed v2.6-A content-drift verdict** is unreachable while re-
  measure runs against a clipped distribution: rows with true p99 >
  current-cap read as NONE-majority (J3 §"Special case"), masking
  content judgement.
- **Seed v2.6-A-T close-vote** is blocked: close criterion "row p99
  ≥ 2 s below the new cap" (per `docs/seed-v2.5-a-row10-diagnosis.md`
  §"Latency boundary analysis") is meaningless against a clipped p99.

The v2.8 Convergence-cycle proposal needs a TRUE response
distribution measurement before cap-related levers fire again. This
protocol is the design for that measurement.

## §Corpus-wide re-measure design

**Fixture.** Full v2.7 alignment-eval golden corpus
`tests/golden/l4_alignment.jsonl` (32 rows per v2.6 P2 reading; cite-
only — FROZEN). All rows, no row filter.

**Per-row n.** Recommended **n = 12** (matches J3 row-10 protocol;
doubles confidence vs n=6 escape-hatch, clean p99 order-statistic).
Acceptable fallback **n = 6** if the v2.8 P2 alignment-eval window
cannot absorb full n=12 wall-clock (see §"Expected runtime").

**Eval-cap.** Widened to **60 s** — 2× the v2.7 P1 30 s cap. Clears
the v2.6 P1 Sonnet n=192 max (25.063 s) by ≥ 2× *and* the v2.7 P2
row-10 p99 (30.092 s) by ≥ 2×. < 50 s is suspect under the cap-clip
hypothesis itself; > 90 s is wasteful.

**Cap-widening mechanism.** Two paths; operator picks at v2.8 P0:

- **Path 1 (recommended): bundle with Seed v2.6-G step (3) env-split.**
  Splits `TIMEOUT_SECONDS` into `BRIDGE_CLI_TIMEOUT` (prod default,
  stays 30 s) and `BRIDGE_CLI_TIMEOUT_EVAL` (eval override, 60 s).
  Prod-path latency tail unaffected. See parent audit §"Step (3) env-
  split coupling note"; promoted from carry-independent (v2.7 P1) to
  cheap dependency for this re-measure.
- **Path 2 (fallback): one-off `TIMEOUT_SECONDS = 60.0` in throwaway
  branch.** No env-split. Prod cap also widens to 60 s for the window;
  +30 s worst-case user-wait on the rare tail; ADR-5 append required.
  Pick only if step (3) ops complexity is unacceptable.

**Runner invocation (Path 1, with step (3) env-split landed at v2.8 P1).**

```powershell
$env:BRIDGE_CLI_TIMEOUT_EVAL = "60"
python -m tools.alignment_eval --golden tests/golden/l4_alignment.jsonl `
  --runs 12 --candidate-only-control --report-only `
  --reports-dir reports/seed-v2.7-a-clip
```

Flag notes: `--candidate-only-control` matches v2.6/v2.7 P2 precedent;
`--report-only` keeps the wide-cap read out of `--ci-gate` (calibration
evidence for v2.9+, not a gate input); `--cli-pool-size 2` recommended
per `feedback_soak_cli_pool_flag.md` (default 0 reproduces v1.0 cold-
start regression and contaminates the cap-clip reading).

**Output.** `reports/seed-v2.7-a-clip/alignment-eval-<UTC>Z.{md,json}`
(new dir; sidecar keys identical to v2.6 P2 / v2.7 P2 patterns).

## §Per-row analysis spec

For each of the 32 rows, extract from the sidecar JSON: `sonnet_runs`,
`sonnet_majority`, `sonnet_stable`, `sonnet_duration_s_{p50,p95,p99,max}`,
`sonnet_timeout_count` (runs ≥ `TIMEOUT_SECONDS − 0.5` = 59.5 s under
the wide cap).

Two derived flags per row:

- **`cap_clip_flag`** — TRUE iff the row would have timed out at the
  prior cap but escapes the new ceiling cleanly:
  `sonnet_p99 ≥ 29.5 s` under the prior 30 s cap reading AND
  `sonnet_p99 < 59.5 s` under this protocol's 60 s reading.
  Prior-cap comparator source: v2.7 P3 S4 ship-gate sidecar; fall back
  to `reports/alignment-eval-20260520T205842Z.json` (v2.6 P2 S6) if
  unavailable.
- **`persistent_timeout_flag`** — TRUE iff `sonnet_p99 ≥ 59.5 s` even
  at the 60 s cap. The row is fundamentally unstable / model-bound,
  not cap-bound; forecloses cap-loosen as a remedy.

**Per-row output table** (in protocol report markdown):

```
| row_id | sonnet_p99 (60s) | cap_clip_flag | persistent_timeout_flag | sonnet_stable | sonnet_majority |
```

32-row table; one row per golden entry.

## §Decision tree (corpus-wide verdict)

Count `cap_clip_flag` and `persistent_timeout_flag` across all 32
rows; apply this gate:

- **Verdict A — cap-clip resolves at 60 s.** ≥ 90% rows (≥ 29/32)
  clear at `sonnet_p99 < 50 s`. Cap-clip confirmed and calibratable.
  v2.8 P2 ship-gate selects a new eval cap at e.g. **55 s** (5 s
  headroom over corpus-wide p95 of p99 readings); step (3) env-split
  keeps prod cap at 30 s. **Seed v2.7-A-CLIP CLOSES.** Seed v2.6-A
  re-measure becomes meaningful; J3 protocol re-fires at v2.9 if
  content-drift verdict still wanted.
- **Verdict B — partial cap-clip.** 50–90% rows (16–28 / 32) clear;
  remainder show `persistent_timeout_flag`. Step (3) env-split ships
  at v2.8 P2 but prod cap stays at 30 s (no calibration available;
  some rows are not cap-bound). Surface unresolved rows as **v2.9
  candidates** (model-routing, prompt-shape, selective row deferral).
  **Seed v2.7-A-CLIP CARRIES to v2.9** scoped to the subset.
- **Verdict C — broad persistent-timeout.** < 50% rows (< 16 / 32)
  clear. Distribution is model-bound, not cap-bound; cap-loosen
  exhausted as remedy. Escalate to a model-routing seed at v2.9
  (route persistent-timeout rows through a faster candidate or a
  non-CLI surrogate). **Seed v2.7-A-CLIP CLOSES** (loosen-falsified;
  artefact real but not binding cause).

## §Expected runtime

Anchors (v2.6 P2 reading; per-row Sonnet p50 ≈ 16.14 s under old 25 s
cap; p50 holds approximately under 60 s cap since p50 is well below
either cap):

- **32 rows × 12 runs × 16.14 s p50** ≈ 6 198 s ≈ **103 min single-
  threaded** (~1.7 h realistic-central).
- **With `--cli-pool-size 2`** per `feedback_soak_cli_pool_flag.md`:
  ≈ **50 min**.
- **Worst case** — 20% of rows (~6) take 60 s every run: ≈ 53 min
  extra; total ≈ **3 h**.

All three fit inside Tier-3 soak envelope (typically 5 h+; v2.7 P3
overnight soak ran 311.6 min). Recommended: **piggyback v2.8 P2 ship-
gate alignment-eval window** — same runner plus env override and
wider `--reports-dir`. No additional soak fire required.

## §v2.8 Convergence-cycle coupling

This protocol's re-measure is one of the three bundled landings in
the v2.8 Convergence-cycle proposal (per `docs/2026-05-22-status.md`
§"v2.8 as a Convergence Cycle (recommended)"). The bundle:

1. **Seed v2.6-C Path-D synthetic-fixture P5** — ~600 LOC under
   `rl/` + tests; unblocks the held v10 chain (#112 → #131 → #124 +
   #125).
2. **Seed v2.6-G step (3) env-split** — ~50 LOC under
   `src/cli_governance.py` + tests; introduces `BRIDGE_CLI_TIMEOUT`
   (prod) vs `BRIDGE_CLI_TIMEOUT_EVAL` (eval) env vars.
3. **Seed v2.7-A-CLIP corpus-wide re-measure** at eval-cap = 60 s —
   reports-only (0 production-bucket LOC); this protocol's invocation.

**Firing order inside v2.8.** The re-measure depends on step (3)
landing first (otherwise the cap-widen has prod-path risk per Path 2
above). Recommended ordering:

- **v2.8 P1** = Seed v2.6-G step (3) env-split land + Seed v2.6-C
  Path-D land. Path-D is the higher-risk item; landing it at P1 gives
  the full cycle's CI exposure.
- **v2.8 P2** = corpus re-measure fires inside the P2 alignment-eval
  window (this protocol's invocation). Output lands in
  `reports/seed-v2.7-a-clip/`. Verdict A/B/C decision recorded in
  v2.8 P2 ship-gate close-out.
- **v2.8 P3** = ship-gate. Re-measure verdict already baked in; P3
  validates that the env-split + Path-D + measurement combination
  ships cleanly.

Step (3) env-split is the **cheap dependency** that makes this re-
measure cheap: eval-only cap widen, no prod-path risk surface. If
step (3) does not land (deferred again), Path 2 (one-off
`TIMEOUT_SECONDS = 60.0` in throwaway branch) is the fallback.

## §Fire conditions (NOT v2.7.1)

**This protocol does NOT fire at v2.7.1.** v2.7.1 scope is corrective
row-05 re-measure only (J3 n=12 re-eval applied to
`frog7-phase-timings-keys-05`, mirroring v2.7 P2's row-10 protocol).
Mixing the corpus-wide cap-clip re-measure into v2.7.1 would (a)
inflate the corrective sub-cycle's LOC + runtime budget beyond the
v2.5.1 precedent, (b) require step (3) env-split to land *inside*
the corrective sub-cycle (out of corrective scope), and (c) confound
the v2.7.1 Hatch A/B/C decision with corpus-wide cap-clip signal.

**Primary fire condition (recommended).** Fires at **v2.8 P2**, INSIDE
the P2 alignment-eval window, ONLY IF Seed v2.6-G step (3) env-split
lands at v2.8 P1 (Path 1 above). Invocation per §"Runner invocation"
with `BRIDGE_CLI_TIMEOUT_EVAL = "60"`.

**Alternate fire path.** Fires at v2.8 P2 via Path 2 (one-off
`TIMEOUT_SECONDS = 60.0` in throwaway branch, no env-split). Operator
may select this if step (3) ops complexity is unacceptable. Risk:
production cap also widens to 60 s during the measurement window;
ADR-5 latency-tail baseline append is required documenting the
deviation. Not recommended unless step (3) is itself deferred.

**Deferral path.** If v2.8 P0 picks a consolidation cycle (Convergence
proposal rejected, Path-D deferred 6th-consecutive), Seed v2.7-A-CLIP
carries to v2.9 in the same shape; this protocol re-fires unchanged
at v2.9 P2.

**Hard non-fire conditions.**

- v2.7.1 ANY phase — out of scope; corrective sub-cycle bounded to
  row-05.
- v2.8 P1 — depends on step (3) env-split (Path 1) or one-off
  throwaway (Path 2); neither lands at P1 by themselves.
- Any cycle where step (3) is NOT landed AND the operator has
  rejected Path 2 — re-measure cannot proceed; this protocol stays
  pending.

## §Carry-forward to v2.8 P0 cycle-type decision

Operator quotes this verbatim block into v2.8 P0 cycle-frame as the
invocation of this protocol:

> **Seed v2.7-A-CLIP — corpus-wide re-measure fire decision (v2.8 P0).**
>
> Evidence: `docs/seed-v2.7-a-clip-corpus-protocol.md`. v2.7 P3 S4
> ship-gate confirmed cap-clip artefact corpus-wide (multiple rows
> p99 at-or-near 30 s cap). Sonnet's true response distribution is
> not measurable under the current cap. Protocol recommends eval-cap
> = 60 s, full corpus n = 12, reports-only.
>
> Operator decision (pick one):
>
> - [ ] **FIRE at v2.8 P2 inside Convergence-cycle bundle** (Path 1:
>   bundled with Seed v2.6-G step (3) env-split at v2.8 P1 + Seed
>   v2.6-C Path-D at v2.8 P1; re-measure piggybacks v2.8 P2 ship-gate
>   alignment-eval window). RECOMMENDED.
> - [ ] **FIRE at v2.8 P2 via Path 2** (one-off `TIMEOUT_SECONDS = 60.0`
>   throwaway branch; step (3) deferred). Production-path latency
>   tail acquires +30 s worst-case for the measurement window; ADR-5
>   append required.
> - [ ] **DEFER to v2.9** (Convergence-cycle rejected at v2.8 P0;
>   Seed v2.7-A-CLIP carries unchanged).

## §Refs

- `docs/seed-v2.6-g-step2-timeout-tighten-audit.md` — **falsified
  parent audit** (v2.6 J2). Recommended cap = 30 s on a clipped Sonnet
  n=192 distribution; the structural blindness this protocol corrects.
- `docs/seed-v2.6-a-row10-remeasure-protocol.md` — **structural cousin
  protocol** (v2.6 J3). Single-row re-measure design + decision tree +
  fire-condition template; this doc is the corpus-wide analogue.
- `docs/2026-05-22-status.md` §"Proposal — Convergence cycle" — v2.8
  cycle frame this re-measure feeds.
- `docs/2026-05-22-status.md` §"v2.7 P2 verdict (PR #206)" + §"v2.7 P3
  ship-gate verdict (PR #207 — BLOCKED)" — row-10 + corpus-wide cap-
  clip confirmations.
- `docs/2026-05-22-task-list.md` §"J5" — this protocol's scope spec.
- `tests/golden/l4_alignment.jsonl` — v2.7 golden corpus (32 rows;
  cite-only; FROZEN).
- `src/stream_manager/cli_governance.py:49` — `TIMEOUT_SECONDS = 30.0`
  (v2.7 P1 PR #203 `28a89c4`; FROZEN under ADR-18; cite-only).
- `tools/alignment_eval.py` — instrumented runner (PR #196 `7220b33`;
  per-run timing + `sonnet_runs`; cite-only).
- `reports/seed-v2.6-a/alignment-eval-20260521T230415Z.{md,json}` —
  v2.7 P2 row-10 n=12 baseline; one-row cap-clip evidence.
- `reports/alignment-eval-20260520T205842Z.{md,json}` — v2.6 P2 n=6
  n=192 clipped distribution the J2 audit relied on.
- `docs/adr/ADR-18-mvp-surface-freeze.md` §"Amendment A" — feature-
  cycle LOC soft target ≤ 1500 (Convergence cycle ~650 LOC = 43%).
- `docs/v2.6-backlog.md` §"Seed v2.6-G" — step (3) env-split backlog
  citation; promoted from carry-independent to cheap dependency.
- `feedback_soak_cli_pool_flag.md` — `--cli-pool-size 2` mandate at
  the runner invocation site.
- `feedback_alignment_eval_stability_window.md` — n=6 escape-hatch
  mandate; n=12 here is one tier above.
- `project_v26_cycle_close.md` (auto-memory) §"Alignment-eval result"
  — memory-side confirmation of the v2.6 P2 n=192 reading.
