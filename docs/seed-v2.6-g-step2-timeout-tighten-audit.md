# Seed v2.6-G step (2) — CLI governance timeout-tighten audit

- Generated: 2026-05-21
- Cycle: v2.6 P2 close → v2.7 P0 prep (J2 of `docs/2026-05-21-task-list.md`)
- Status: 🔴 (step (1) instrumentation LANDED v2.6 P1 PR #196 `7220b33`;
  step (2) value-selection is this audit's scope)
- Predecessor: `docs/seed-v2.4-g-cli-timeout-audit.md` (v2.5 P0 J2;
  recommended PROMOTE-to-🔴 with measurement-protocol stance + band
  30–45 s; declined to recommend a point value pending n).

This doc is an **evidence audit only**. It does NOT modify
`src/stream_manager/cli_governance.py`. The `TIMEOUT_SECONDS = 25.0`
constant is FROZEN under ADR-18 surface-freeze and remains frozen
through this audit. The purpose of the doc is to bound the operator's
v2.7 P0 decision surface for "fire step (2) timeout-tighten?" with the
evidence currently on hand. The v2.5 P0 audit recommended a band
30–45 s; the v2.6 P1 instrumentation now in hand (n=192 wall-clock
observations) is sufficient to recommend a primary point value plus
two alternates inside that band.

## §Current state

`src/stream_manager/cli_governance.py:49`:

```python
TIMEOUT_SECONDS = 25.0
```

(Cite-only; the line is FROZEN under ADR-18 surface-freeze and is not
edited by this audit.) The value is the wall-clock cap on
`subprocess.run(...)` calls into the local `claude -p` CLI when
escalating L2/L3/L4 content. On `subprocess.TimeoutExpired` the engine
degrades to local-only behaviour and the call returns `(None, False)`,
which downstream consumers treat as a `NONE` verdict in alignment-eval
row sequences. This audit recommends but does not change the value.
Any change lands at v2.7 P1 if the operator promotes step (2) to FIRE
at v2.7 P0.

## §Measured distribution (v2.6 P2 reading)

Source: `reports/alignment-eval-20260520T205842Z.{md,json}` — v2.6 P2
ship-gate alignment-eval, n=6 escape-hatch reading, JSON keys
`summary.sonnet_duration_s_*` and `summary.haiku_duration_s_*`.

The instrumentation surface lives at `tools/alignment_eval.py`
(per-run timing block written at PR #196 `7220b33`; cite-only —
not edited by this audit). Per-run durations are aggregated across
all rows × all runs × both models, then percentiled.

| Model  | n   | p50      | p95      | p99      | max      |
|--------|-----|----------|----------|----------|----------|
| sonnet | 192 | 16.140 s | 25.039 s | 25.048 s | 25.063 s |
| haiku  | 192 | 14.508 s | 23.271 s | 25.035 s | 25.094 s |

Cross-reference (single-row n=6 instrumented S6.5 re-measure of
`frog7-wirecli-module-10`): sonnet p50 = 22.891 s, p95 = 24.613 s,
**p99 = 24.960 s**, max = 25.047 s (1/6 timeout boundary).
Source: `reports/seed-v2.5-a/alignment-eval-20260520T172054Z.{md,json}`.

The full-corpus Sonnet p99 (25.048 s) and the row-10 single-row
Sonnet p99 (24.960 s) are within ~90 ms of each other — both sit
hard against the 25.0 s cap. The full-corpus reading is the canonical
step (2) input; the single-row reading is the Seed v2.6-A-T watch
anchor.

## §Boundary analysis

The current cap is 25.0 s; measured Sonnet p99 across the n=192
sample is 25.048 s, and the max is 25.063 s. The gap between Sonnet
p99 and the cap is **−48 ms** — Sonnet's p99 sits *above* the cap by
roughly 50 ms, which means approximately 1 in 100 escalation calls
exits via the timeout-degrade path under current conditions. Haiku
p99 is 25.035 s — also above the cap, by 35 ms.

The n=6 escape-hatch reading (per `docs/v2.6-backlog.md` §"v2.6 P2
measurement summary") records the following at the boundary:

- **n=3 default first-fire:** Sonnet pass_rate = 0.9444 (17/18 stable
  pass), with **14/32 unstable** Sonnet rows and **3 rows ≥ 50%
  timeout-rate**. The n=3 reading triggered the n=6 escape-hatch
  per `feedback_alignment_eval_stability_window.md`.
- **n=6 escape-hatch read:** Sonnet pass_rate = 0.9412 (16/17 stable
  pass); regression_rows = []. Stability recovered; but 14/32 unstable
  Sonnet rows persist in the n=6 sample and at least four rows
  (row-08, row-10, row-13, row-15 by inspection of the n=6 report)
  carry ≥ 3 NONE in their 6-run sequences.

The implication for content-classification stability at the boundary:
about 1% of escalation calls produce a NONE verdict not because Sonnet
is semantically uncertain but because the CLI subprocess didn't return
inside 25.0 s. NONE then propagates into majority-verdict counting
and reduces sonnet_stable_count for that row. The 14/32 unstable
Sonnet rows in v2.6 P2 are inflated by this boundary noise; some
unknown fraction of those rows would settle into a stable content
verdict if the cap were further from the per-run p99.

**Seed v2.6-A-T coupling.** Row-10 `frog7-wirecli-module-10`
specifically (single-row n=6 p99 = 24.960 s; one of six runs grazed
the boundary at 25.047 s) is the watch anchor. v2.6-A-T closes only
when (a) step (2) lands a new cap value and (b) row-10's re-measured
p99 sits ≥ 2 s below the new cap. With single-row p99 = 24.960 s,
the close threshold is **new cap ≥ 26.960 s**. Any candidate ≥ 30 s
therefore closes v2.6-A-T mechanically; candidates below 27 s do
not.

## §Cap-value selection

Five candidate cap values evaluated. Per-candidate trade-off:

| Cap   | Margin vs p99 25.048 s | Margin %  | Closes v2.6-A-T (≥ 26.96 s)? | Approx. false-timeout-NONE reduction | Eval-runtime worst-case (n=192) | Production-path risk             |
|-------|------------------------|-----------|------------------------------|--------------------------------------|---------------------------------|----------------------------------|
| 28 s  | +2.952 s               | ~11.8 %   | yes (~1.04 s margin)         | partial — clears p99 25.048 s but max 25.063 s still inside band; row-08/10/13/15 plausibly recover ~50% of timeout-NONE | +3 s × 192 calls worst-case = +576 s (+9.6 min) | minimal: +3 s vs 25 s worst case |
| 30 s  | +4.952 s               | ~19.8 %   | yes (~3.04 s margin)         | substantial — clears p99 + max with comfortable headroom; expect ≥3 of 4 timeout-heavy Sonnet rows to recover content verdicts | +5 s × 192 = +960 s (+16.0 min) | low: +5 s worst-case user wait   |
| 35 s  | +9.952 s               | ~39.7 %   | yes (~8.04 s margin)         | near-complete — covers a 5-σ tail; only adversarial prompts plausibly time out | +10 s × 192 = +1920 s (+32.0 min) | moderate: +10 s worst-case user wait; harder to distinguish "Sonnet is thinking" from "Sonnet stuck" |
| 40 s  | +14.952 s              | ~59.7 %   | yes (~13.04 s margin)        | effectively floor-zero false-timeouts under v2.6 P2 distribution | +15 s × 192 = +2880 s (+48.0 min) | elevated: +15 s worst-case; doubles soak-band escalate-path tail |
| 45 s  | +19.952 s              | ~79.7 %   | yes (~18.04 s margin)        | floor-zero false-timeouts; defensively covers a hypothetical worse Sonnet | +20 s × 192 = +3840 s (+64.0 min) | high: +20 s worst-case; 80% bump in tail latency for marginal eval gain |

**Notes on the eval-runtime column.** The worst case is "every row
hits the new cap" — in practice almost no row will hit the cap since
the n=192 max under current 25.0 s is 25.063 s (i.e. the *current*
tail is shaped by the cap). Realistic eval-runtime delta is closer
to **Δp50 × n** = ~0 s (median is far from the cap on all rows), with
the worst-case bound above as the absolute ceiling.

**Notes on the false-timeout reduction column.** The 14/32 unstable
Sonnet rows in v2.6 P2 are a mixture of (i) genuine content-divergent
rows (e.g. row-10 INTERVENE-vs-SUGGEST per Seed v2.6-A) and (ii)
boundary-timeout artefacts. A cap ≥ 30 s should resolve (ii) for
most rows; (i) is unaffected by cap-tighten and is the domain of
Seed v2.6-A re-measure (J3).

**Notes on the production-path column.** The production soak series
(reports/soak-2026051*.md → reports/soak-20260520T180511Z.md) shows
escalate-path max under 19 s across 6+ consecutive soaks with
`degrade_count = 0`. Production traffic is not the constraint — the
constraint is eval traffic. A cap raise hurts user-facing latency
*only on the rare tail* where the CLI was already going to take a
long time; the median user wait is unchanged.

## §Recommendation

**PRIMARY: 30 s.** Justification:

- Clears measured Sonnet n=192 p99 (25.048 s) with ~5 s headroom
  (≈20% margin), which is sufficient under the J2 v2.5 P0 audit's
  recommended band of 30–45 s (30 s = the band's lower edge).
- Closes Seed v2.6-A-T trivially: 30 s − row-10 single-row p99
  24.960 s = 5.04 s margin, well above the 2 s close threshold.
- Substantial false-timeout-NONE reduction expected; the 14/32
  unstable Sonnet rows should shrink to mostly content-divergent
  cases (the domain of J3's row-10 re-measure protocol).
- Eval-runtime worst-case +16 min is absorbable; realistic Δ is
  near zero.
- Production-path worst-case user wait moves from 25 s to 30 s on
  the rare tail; soaks show this tail almost never fires
  (degrade_count = 0 across all post-v2.4 soaks).
- 30 s is the conservative-but-credible end of the band — leaves
  room for v2.8+ tightening (e.g. back toward 28 s) if production
  data warrants, without locking in a defensively-large value.

**ALTERNATE A: 35 s.** Operator may prefer 35 s if (a) they want a
single landing decision that does not need re-litigation in v2.8 or
(b) they observe that the n=192 sample under the current 25.0 s cap
is censored at 25 s, so the *true* uncapped Sonnet p99 may sit
materially above 25.05 s. 35 s gives ~10 s headroom against the
*current censored* p99, which is defensive against this measurement
artefact. Cost: +10 s worst-case user-facing latency vs +5 s for
30 s.

**ALTERNATE B: 28 s.** Operator may prefer 28 s if they want a
minimum-disturbance change — exactly enough to move the cap above
the measured n=192 p99 + max with a thin margin. Cost: 28 s clears
p99 25.048 s by 2.95 s but only clears max 25.063 s by 2.94 s; the
v2.6-A-T close margin is just 1.04 s above the row-10 single-row
p99, which is at the edge of the 2 s close threshold. Not
recommended as primary; viable if the operator wants step (2) to
be a measurable but minimal change.

**Seed v2.6-A-T watch close.** All three candidates (28 s / 30 s /
35 s) and the two more-generous candidates (40 s / 45 s) close
v2.6-A-T mechanically. The only candidate that does NOT close it
is one strictly below 26.96 s, which this audit does not recommend.

## §Step (3) env-split coupling note

Step (3) splits `TIMEOUT_SECONDS` into `BRIDGE_CLI_TIMEOUT`
(production default) and `BRIDGE_CLI_TIMEOUT_EVAL` (eval override),
both readable from env. Bundle decision:

**Recommend BUNDLE step (3) with step (2) at v2.7 P1** if the chosen
cap is ≥ 35 s. Rationale: at 35 s the prod-vs-eval cap divergence
matters more — production traffic sees the same +10 s user-wait
ceiling that eval does, with no production benefit. Splitting at
+10 s recovers the production-side conservative value (≈ 28 s)
while letting eval enjoy the headroom.

**Recommend CARRY step (3) independently to v2.7+** if the chosen
cap is 30 s or lower. Rationale: at 30 s the prod-vs-eval cap
divergence is only +5 s; ops complexity (two env vars, two code
paths, two soak readings to validate) outweighs the user-wait
benefit. Step (3) is then a v2.8+ candidate once step (2)'s effect
on stability has settled.

**Default given the primary recommendation of 30 s: CARRY step (3)
independently.** Step (3) is not on the v2.7 critical path.

## §v2.7 P0 question (verbatim operator decision block)

Paste this block into `docs/prompts/v2.7-orchestration/phase-0-cycle-frame.md`
§"Seed v2.6-G step (2) fire decision" + §"Seed v2.6-G step (3)
env-split fire decision":

> **Seed v2.6-G step (2) — timeout-tighten fire decision (v2.7 P0).**
>
> Evidence: `docs/seed-v2.6-g-step2-timeout-tighten-audit.md`.
> Measured Sonnet n=192 p99 = 25.048 s vs current cap 25.0 s.
> Audit recommends primary cap = 30 s; alternates 35 s (defensive)
> or 28 s (minimum-disturbance).
>
> Operator decision (pick one):
>
> - [ ] **FIRE step (2) at v2.7 P1 with cap value: __________** s
>   (audit primary: 30 s; alternates: 28 s / 35 s).
> - [ ] **DEFER step (2) another cycle** (Seed v2.6-G stays open;
>   `TIMEOUT_SECONDS = 25.0` stays FROZEN; Seed v2.6-A-T stays open).
>
> **Seed v2.6-G step (3) — env-split fire decision (v2.7 P0).**
>
> Evidence: same audit §"Step (3) env-split coupling note".
> Audit recommends BUNDLE if chosen cap ≥ 35 s; CARRY independently
> if chosen cap ≤ 30 s.
>
> Operator decision (pick one):
>
> - [ ] **FIRE step (3) env-split at v2.7 P1, same phase as step (2)**
>   (recommended if step (2) cap ≥ 35 s).
> - [ ] **DEFER step (3) to v2.7+ (carry independently)**
>   (recommended if step (2) cap ≤ 30 s, OR if step (2) deferred).

## §Refs

- `src/stream_manager/cli_governance.py:49` — `TIMEOUT_SECONDS = 25.0`
  (FROZEN under ADR-18 surface-freeze; cite-only, not modified by
  this audit).
- `tools/alignment_eval.py` — per-run timing surface added at PR #196
  `7220b33` (Seed v2.5-G step (1) instrumentation; cite-only, not
  edited by this audit).
- `docs/seed-v2.4-g-cli-timeout-audit.md` — predecessor audit (J2
  from v2.5 P0); recommended band 30–45 s + measurement-protocol
  stance; structural template for this doc.
- `reports/alignment-eval-20260520T205842Z.{md,json}` — v2.6 P2
  full-corpus n=6 reading; canonical Sonnet n=192 p99 = 25.048 s.
- `reports/seed-v2.5-a/alignment-eval-20260520T172054Z.{md,json}` —
  v2.6 P2 S6.5 instrumented n=6 single-row re-measure of
  `frog7-wirecli-module-10`; row-10 single-row p99 = 24.960 s.
- `docs/v2.6-backlog.md` §"v2.6 P2 measurement summary" — backup
  source for the same n=192 numbers; §"Seed v2.6-G" item 5 and
  §"Seed v2.6-A-T" item 7 for the carry-forward framing.
- `docs/seed-v2.5-a-row10-diagnosis.md` §"Latency boundary analysis"
  — Seed v2.6-A-T close-criterion source (new cap ≥ row-10 p99 + 2 s).
- `docs/v2.6-next-steps.md` §"Seed v2.6-G" — disposition narrative.
- `docs/adr/ADR-18-mvp-surface-freeze.md` §"surface-freeze" +
  Amendments A–E — surface-freeze covering
  `src/stream_manager/cli_governance.py`.
- `feedback_alignment_eval_stability_window.md` — n=6 escape-hatch
  mandate when prior cycle Sonnet pass_rate is within 0.05 of floor;
  triggered the n=6 reading that produced the n=192 sample.
- `C:\Users\SeanHoppe\.claude\projects\C--Users-SeanHoppe-vs-streamManager\memory\project_v26_cycle_close.md`
  §"Alignment-eval result" + §"NEW Wall-clock distributions" —
  memory-side confirmation of the canonical numbers.
- v2.6 P1 commit `7220b33` (PR #196) — step (1) wall-clock
  instrumentation source PR; lever ledger BUMP 1 → 2.
