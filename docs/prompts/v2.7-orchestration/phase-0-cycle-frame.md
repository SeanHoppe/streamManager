# v2.7 P0 — Cycle frame

> Minted ahead-of-fire as a skeleton (PR #191 v2.6-pm-mint precedent
> + PR #178 v2.4-pm-mint precedent). Cycle type **TBD by operator at
> fire time**.
>
> **NO default lean pre-authorized at this PM-mint.** Unlike the
> v2.6 PM-mint preamble, no /goal pre-authorization signal was issued
> at the session that produced this skeleton. Operator picks at P0
> fire from both options surfaced under §"Cycle-type call" below; the
> §"Default lean rationale" paragraph there records BOTH stances
> (feature + consolidation) honestly so the operator weighs them at
> fire time without skeleton bias.
>
> Comparison anchor: `docs/v2.7-next-steps.md` §"P0 frame — operator-
> bound decisions" (drafted alongside this frame in this PM-mint
> bundle per PR #191 precedent).
>
> **Skeleton scope:** this file bounds the v2.7 P0 decision surface
> and surfaces the cap-counted reading + cross-refs. The operator
> fills in decision blocks at fire time. NO operator decision is
> pre-empted by this skeleton.

## Branch + base

- Base: `main` after v2.6.0 (commit `c3a964c`, PR #198 — v2.6 P2
  ship-gate finalize, squash-merged 2026-05-20; tag pushed
  2026-05-21). Verify SHA freshness at fire time.
- Branch: `feat/v2.7-p0-cycle-frame` (feature default; rename to
  `chore/v2.7-p0-cycle-frame` only if operator overrides to
  consolidation at fire time).
- PR target: `main`.

## §Memory pre-flight (Rule 6 — ADR-18 Amendment B)

Verify each load-bearing memory against current repo state before
opening P0 PR. If any cited memory is stale, update it BEFORE
opening P0 PR. Record verification stamp in P0 PR body.

**Minimum re-read list for v2.7 P0** (operator may extend):

- `feedback_certportal_dev_firewall.md` — dev-session firewall against
  `C:\Users\SeanHoppe\VS\certPortal\`; deny rules enforced via
  `.claude/settings.local.json`.
- `feedback_no_self_monitor.md` — polarity-flip rule; SM must never
  govern itself; include-iff `project_slug NOT IN
  STREAM_MANAGER_PROJECT_SLUGS`.
- `project_v26_cycle_close.md` — v2.6 ship at `c3a964c`, PR #198;
  feature cycle; cycle-tip net +147 LOC at soak fire-time (~+670
  post-PR-merge with `tools/ship_gate_runner.py`); lever ledger BUMP
  1 → 2 (production-bucket canonical; first wire since v2.3 Seed 6);
  Seed v2.5-A CLOSED CONTENT-DRIFT at S6.5 pre-execution (PR #197;
  v2.5.1 P1 100%-timeout artefact FALSIFIED at n=6, 1/6 actual);
  NEW Seeds v2.6-A + v2.6-A-T spawned; alignment-eval Sonnet n=6
  0.9412 (escape-hatch from n=3 fired) + Haiku 1.0 +
  regression_rows=[]; Sonnet p99 25.048 s = Seed v2.6-G step (2)
  input; soak overall p95 9.926 s + LM p95 12.64 s recovered + L4
  p95 19.89 s downgrade-toward-close; v10 P4 corpus piggyback 608
  (Run 7; Δ +60 vs v2.5.1).
- `feedback_alignment_eval_stability_window.md` — n=6 mandate near
  FR-OG-7 floor; v2.7 P2 entry condition: prior cycle v2.6 Sonnet
  pass_rate = 0.9412 (n=6 reading) → 0.9412 ≥ 0.85 → default
  `--runs 3` applies UNLESS escape-hatch conditions fire
  (unstable_sonnet > 0.25 × total OR per-row CLI-timeout-rate >
  33%).
- `feedback_soak_cli_pool_flag.md` — `--cli-pool-size 2` still
  required at soak fire.
- `feedback_glob_narrowing_no_op.md` — PR #184 cassette; filename
  glob narrowing without verifying driver write-pattern is no-op.

**Stamp output (P0 PR body):** for each memory above, record
`fresh / updated-in-this-PR / superseded-by-X`. Empty stamp =
non-compliant (Amendment B §"Required output").

## §Cycle-type call

Decision-block (operator picks at P0 fire 2026-05-21):

- [x] **Feature cycle** (≥ 1 lever wired OR Seed v2.6-C Path-D
      synthetic-fixture P5 fires; soft LOC ≤ 1500 per ADR-18
      Amendment A; BLOCK at 1.5× = 2250).
- [ ] **Consolidation cycle** (net LOC ≤ 0 vs P0-merge tip per
      ADR-18 Amendment C).

**Operator pick: FEATURE.** Rationale: Seed v2.6-G step (2) FIRE
candidate is evidence-ready (J2 audit recommends primary cap = 30 s
based on measured Sonnet n=192 p99 = 25.048 s); production-bucket
lever-wire qualifies feature classification on its own. 2-in-a-row
feature (v2.6 was also feature) is permitted by Amendment A
§"Default lean rationale" when a ready FIRE candidate justifies the
choice. Seed v2.6-C Path-D DEFERS another cycle (5th-consecutive;
lever-budget bound) — single-lever fire keeps the LOC envelope tight
and the Path-D ~600 LOC carry remains valid evidence at v2.8 P0.

**Default lean rationale.** Both stances are surfaced honestly so the
operator weighs them at fire time without skeleton bias.

- **(a) Feature stance.** Two cap-counted FIRE candidates are
  evidence-ready entering v2.7: (i) Seed v2.6-G step (2) timeout-
  tighten — J2 evidence audit
  (`docs/seed-v2.6-g-step2-timeout-tighten-audit.md`, this session)
  cites measured Sonnet p99 = 25.048 s from v2.6 P1 instrumentation
  (PR #196) and selects a candidate cap within the 30–45 s band that
  v2.5 P0 J2 audit recommended; the step (2) value-selection is
  no longer measurement-bound. (ii) Seed v2.6-C Path-D synthetic-
  fixture P5 implementation (~600 LOC) carries 4-consecutive-cycle
  deferral pressure (v2.4 + v2.5 + v2.5.1 + v2.6 all skipped) — the
  ADR-18 Amendment A 1500 LOC soft cap accommodates the Path-D
  scope, and the v10 RL chain remains blocked behind it. Either
  trigger qualifies the cycle as feature.
- **(b) Consolidation stance.** ADR-18 Amendment A §"Default lean
  rationale" sequences alternation hygiene: v2.6 was feature
  (lever-wire ledger 1 → 2 production); strict alternation argues
  v2.7 consolidation. Two consecutive feature cycles is permitted
  by Amendment A but not encouraged unless a load-bearing FIRE
  candidate justifies the choice. Operator may also elect
  consolidation if v2.7 P0 fire surfaces a blocker (e.g. v10.3
  stochastic propensities still not in hand, scope uncertainty on
  step (2) cap value, or lever-budget bound on bundling step (2) +
  step (3)).

Operator weighs both at fire time and records the rationale in
`docs/v2.7-task-plan.md` (minted at P0 fire, not this PM-mint).

**Coupling note (binding).** Feature cycle classification requires
at least one of:

- Seed v2.6-G step (2) timeout-tighten — modifies
  `src/stream_manager/cli_governance.py:49` `TIMEOUT_SECONDS`
  (production-bucket LOC delta under Amendment A 3-bucket
  measurement; qualifies as lever-wire on its own).
- Seed v2.6-G step (3) env-split — `BRIDGE_CLI_TIMEOUT` (prod) +
  `BRIDGE_CLI_TIMEOUT_EVAL` (eval override) env-readable; modifies
  `src/stream_manager/cli_governance.py` plus a small loader change
  (production-bucket LOC delta on its own).
- Seed v2.6-C Path-D synthetic-fixture P5 implementation (~600
  LOC; ADR-18 Amendment D §"Acceptance" DEFERRED-v2.5 items —
  bandit `is_ready_for_shadow_v10_1()`, train `promotion_gate`
  envelope additive keys, phase-5 prompt re-mint OR new
  `phase-1-shadow-synthetic.md`, shadow harness `--mode=v10.1`
  suffix, `check_criteria` filter).

If multiple fire same cycle the LOC budget remains under Amendment A
soft cap 1500. Step (2) alone is small (≤ 20 LOC `src/` change);
step (3) bundled adds ≤ 60 LOC; Seed v2.6-C adds the dominant
~600 LOC. Combined feature-cycle LOC envelope is comfortably under
1500.

## §Rule 5 cap-counted reading

Post-v2.6 P2 backlog reading (Seed v2.5-A CLOSED at S6.5; NEW Seeds
v2.6-A + v2.6-A-T spawned; Seeds v2.5-C → v2.6-C + v2.5-G → v2.6-G
renamed; current open seeds = v2.6-A + v2.6-A-T + v2.6-C + v2.4-E +
v2.4-F + v2.6-G + v2.4-I..N).

**Cap-counted: 6**

- Seed v2.6-A (`frog7-wirecli-module-10` Sonnet content drift vs
  golden `expected_verdict=SUGGEST`; NEW at v2.6 P2 S6.5; re-measure
  n=12 candidate v2.7 P2).
- Seed v2.6-A-T (row-10 timeout-boundary watch; NEW at v2.6 P2 S6.5;
  closes when Seed v2.6-G step (2) lands measured-band timeout-
  tighten + row-10 re-measured p99 ≥ 2 s under new cap).
- Seed v2.6-C (Path-D synthetic-fixture P5; renamed from v2.5-C;
  4th-consecutive deferral candidate this cycle).
- Seed v2.4-E (overall p95 watch; v2.6 P2 reading 9.926 s; 2nd
  consecutive cycle ≤ 10 s downgrade band; closure threshold ≤ 8.2 s
  not yet met).
- Seed v2.4-F (L4 half DOWNGRADE-TOWARD-CLOSE at v2.6 P2 = 19.89 s;
  LM half CLOSED RECOVERED at 12.64 s; carries with reduced concern).
- Seed v2.6-G (CLI-timeout instrumentation + tighten + split;
  renamed from v2.5-G; step (1) LANDED v2.6 P1 PR #196; steps (2) +
  (3) FIRE candidates this cycle).

**Amendment E EXEMPT: 6**

- Seed v2.4-I (INTENT-graduated, promotion-criterion-bound).
- Seed v2.4-J (INTENT-graduated, promotion-criterion-bound).
- Seed v2.4-K (INTENT-graduated, promotion-criterion-bound).
- Seed v2.4-L (INTENT-graduated, promotion-criterion-bound).
- Seed v2.4-M (INTENT-graduated, promotion-criterion-bound).
- Seed v2.4-N (Remote-CLI monitoring extension, demand-bound).

Cite: ADR-18 Amendment E §"Self-application" (entry 2026-05-19) +
ADR-18 Amendment E §"Acceptance" final acceptance row (verbatim
external-trigger citations required in `docs/v2.7-next-steps.md` at
P0 fire).

**Operator decision:**

- [x] Accept the **6-cap** reading above (cap-counted 6; exempt 6 per
      Amendment E §"Self-application").
- [ ] Mint a Rule 5 clarification (new amendment) if the reading is
      contested. Specify the contested seed(s) and the proposed
      reclassification:

  Contested seed(s): `n/a`

  Proposed reclassification: `n/a`

**Operator pick: ACCEPT 6-CAP.** Cap-counted 6 = v2.6-A + v2.6-A-T +
v2.6-C + v2.4-E + v2.4-F + v2.6-G. Exempt 6 = v2.4-I..N per
Amendment E §"Self-application". Reading verified against
`docs/v2.6-backlog.md` §"Carry-forwards from v2.6"; no drift. No
Rule 5 clarification amendment minted this cycle.

## §Seed v2.6-G step (2) fire decision

Evidence input: `docs/seed-v2.6-g-step2-timeout-tighten-audit.md`
(J2 output from this session); Sonnet p99 25.048 s measured at v2.6
P2 alignment-eval `reports/alignment-eval-20260520T205842Z.json`;
v2.6 P2 S6.5 single-row p99 24.96 s + max 25.047 s on
`frog7-wirecli-module-10` at
`reports/seed-v2.5-a/alignment-eval-20260520T172054Z.json`.

Decision-block (operator picks at P0 fire 2026-05-21):

- [x] **FIRE step (2) at v2.7 P1** — modifies
      `src/stream_manager/cli_governance.py:49` `TIMEOUT_SECONDS`
      from 25.0 to the J2-recommended cap (production-bucket
      lever-wire under Amendment A 3-bucket; requires §"Cycle-type
      call" = feature).
- [ ] **DEFER another cycle** — Seed v2.6-G step (2) carries to
      v2.7+ (1st deferral since v2.5 P0 promote-confirmation; step
      (2) value-selection evidence has been in hand since v2.6 P2).
      Operator records the rationale (typical: scope uncertainty
      on new cap value, lever-budget bound, prefer bundling with
      step (3) at a later cycle, etc.).

**Operator pick: FIRE step (2) at v2.7 P1 with cap value 30 s** (J2
audit primary recommendation). Rationale: clears measured Sonnet
n=192 p99 = 25.048 s with ~5 s (≈20%) headroom; closes Seed
v2.6-A-T mechanically (5.04 s margin above row-10 single-row p99
24.96 s, well above 2 s close threshold); substantial false-timeout-
NONE reduction expected (row-08/10/13/15 plausibly recover ~50% of
boundary-attributable NONE verdicts); eval-runtime worst-case +16 min
absorbable (realistic Δ near zero); production-path worst-case user
wait moves 25 s → 30 s only on rare tail (degrade_count = 0 across
all post-v2.4 soaks). 30 s is conservative-but-credible end of the
J2 30–45 s band — leaves room for v2.8+ tightening if production
data warrants. Lever ledger BUMP 2 → 3 (production-bucket canonical)
at v2.7 P1 merge; first FROZEN-surface lever ever wired
(`src/stream_manager/cli_governance.py:49`).

**Coupling note.** §"Cycle-type call" = FEATURE — coupling intact;
step (2) production-bucket LOC delta fits feature gate (≤ 20 LOC
`src/` change, well under 1500 soft cap).

## §Seed v2.6-G step (3) env-split fire decision

Step (3) introduces env-readable `BRIDGE_CLI_TIMEOUT` (prod) +
`BRIDGE_CLI_TIMEOUT_EVAL` (eval override) so production and
alignment-eval can carry different cap values. Modifies
`src/stream_manager/cli_governance.py` plus a small loader change
(production-bucket LOC delta).

Decision-block (operator picks at P0 fire 2026-05-21):

- [ ] **BUNDLE same phase as step (2)** — step (2) + step (3) ship
      together at v2.7 P1; valid only if §"Seed v2.6-G step (2)
      fire decision" = FIRE. Bundling keeps the cap change + env-
      split coherent (one PR documents both surfaces).
- [x] **CARRY independently** — step (3) waits for a later cycle
      even if step (2) fires now. Useful if operator wants to land
      the cap change without the env-split surface (smaller scope,
      tighter LOC delta this cycle).
- [ ] **DEFER another cycle** — step (3) carries v2.7+; couples
      with the same cycle as step (2) at the next election.
      Required if §"Seed v2.6-G step (2) fire decision" = DEFER.

**Operator pick: CARRY independently.** J2 audit default given step
(2) cap = 30 s: prod-vs-eval cap divergence at 30 s is only +5 s, so
ops complexity (two env vars, two code paths, two soak readings to
validate) outweighs the user-wait benefit. Step (3) becomes a v2.8+
candidate once step (2)'s effect on stability has settled. Step (3)
is NOT on the v2.7 critical path.

## §Seed v2.6-C deferral/fire decision

Path-D synthetic-fixture P5 implementation (~600 LOC). Bound on
cycle-type per §"Cycle-type call" above. Deferral count entering
v2.7: **4 cycles** (v2.4 + v2.5 + v2.5.1 + v2.6 all skipped).

Decision-block (operator picks at P0 fire 2026-05-21):

- [ ] **FIRE this cycle** — only valid if §"Cycle-type call" =
      feature. Path-D P5 lands as v2.7 P1 OR P1a (sequenced
      alongside Seed v2.6-G step (2) if both fire). Implementation
      scope per ADR-18 Amendment D §"Acceptance" DEFERRED-v2.5
      items (bandit `is_ready_for_shadow_v10_1()`, train
      `promotion_gate` envelope additive keys, phase-5 prompt
      re-mint OR new `phase-1-shadow-synthetic.md`, shadow harness
      `--mode=v10.1` suffix, `check_criteria` filter). Ends the
      4-cycle deferral streak; unblocks v10 chain #112 → #131 →
      #124 + #125.
- [x] **DEFER another cycle** — Seed v2.6-C carries to v2.8 P0
      (5th consecutive deferral; renames Seed v2.7-C at v2.7 P2
      backlog mint). Re-evaluate at next cycle frame. Operator
      records the deferral rationale (typical: scope uncertainty,
      dependency on v10.3 stochastic propensities not yet in
      hand, lever-budget bound).

**Operator pick: DEFER another cycle (5th consecutive).** Rationale:
lever-budget bound — single-lever fire (Seed v2.6-G step (2) cap
30 s) keeps the feature-cycle LOC envelope tight (~20 LOC `src/`
vs ~620 LOC if Path-D bundled). v10.3 stochastic-propensities
dependency still not in hand. Seed v2.6-C carry remains valid
evidence at v2.8 P0; renames **Seed v2.7-C** in `docs/v2.7-backlog.md`
at v2.7 P2 mint. v10 chain #112 → #131 → #124 + #125 stays blocked
on Path-D landing; no v10.x cycle frame mint at v2.7. Re-evaluate at
v2.8 P0 (will be 5th-consecutive entering, 6th if also deferred).

**Cycle-coupling guard.** §"Cycle-type call" = FEATURE; this section
= DEFER. Coupling intact (feature classification justified by Seed
v2.6-G step (2) FIRE alone; Path-D defer does not affect feature
classification).

## §Seed v2.6-A re-measure decision

Evidence input: `docs/seed-v2.6-a-row10-remeasure-protocol.md` (J3
output from this session); v2.6 P2 S6.5 n=6 reading on row 10
`frog7-wirecli-module-10` = sonnet_majority INTERVENE (4/6) vs
golden `expected_verdict=SUGGEST`; sonnet timeout_count = 1/6 (run 6
at 25.047 s); sonnet p50/p95/p99/max = 22.891 / 24.613 / 24.96 /
25.047 s.

Decision-block (operator picks at P0 fire 2026-05-21):

- [x] **FIRE n=12 re-measure at v2.7 P2** — default per J3
      protocol. Re-measure runs inside the v2.7 P2 alignment-eval
      window (single-row fixture; ~3.2 min runtime under Sonnet p50
      16 s × 12 = 192 s). Decision tree: ≥ 9/12 INTERVENE →
      STABLE-CONTENT-DRIFT → golden-update path; 6–8/12 INTERVENE
      → still-unstable → DIP-watch hold; if Seed v2.6-A-T fires
      (re-measured p99 ≥ 2 s under new cap) escalate per coupling.
- [ ] **FIRE n=12 re-measure at v2.7 P1** — alternate placement
      that benefits from any cap-tighten landing same phase as
      Seed v2.6-G step (2) (re-measure runs under the new cap and
      directly informs Seed v2.6-A-T close-out). Valid only if
      §"Seed v2.6-G step (2) fire decision" = FIRE.
- [ ] **DEFER another cycle** — Seed v2.6-A carries to v2.8
      (renames Seed v2.7-A at v2.7 P2 backlog mint). Operator
      records the deferral rationale.

**Operator pick: FIRE n=12 re-measure at v2.7 P2** (J3 protocol
default). Re-measure runs under the **new 30 s cap** since Seed
v2.6-G step (2) lands at v2.7 P1 (operator pick above) — cleaner
read for both Seed v2.6-A content-drift verdict AND Seed v2.6-A-T
boundary-watch close-vote. Single-row n=12 add-on at ~3.2–5 min
fits inside the v2.7 P2 alignment-eval window without extending
Tier-3 soak envelope. Fixture re-uses
`reports/seed-v2.5-a/row10-fixture.jsonl`; output to
`reports/seed-v2.6-a/alignment-eval-<UTC>Z.{md,json}`. Invocation
per `docs/seed-v2.6-a-row10-remeasure-protocol.md` §"Re-measure
design".

## §Seed v2.6-A-T carry-forward

Re-state coupling (no P0-time decision required; logging only):

- **Disposition:** WATCH 🟡; closes iff Seed v2.6-G step (2) lands
  measured-band timeout-tighten + row-10 is re-measured under the
  new cap with p99 ≥ 2 s of margin. v2.6 P2 reading: p99 24.96 s,
  max 25.047 s on `frog7-wirecli-module-10` (50 ms shy of cap; 47 ms
  over cap on a single run).
- **No P0-time action.** Close-out is mechanical at v2.7 P2 if
  step (2) fires AND re-measure protocol fires same cycle. Operator
  records the carry-forward in `docs/v2.7-next-steps.md`
  §"Carry-forwards" + cap-counted reading above (already counted as
  1 of 6).

## §Seed v2.4-E overall-p95 posture

Re-state (no P0-time decision required; logging only):

- **Disposition:** WATCH continues 🟢. v2.6 P2 reading p95 9.926 s
  (Δ +0.270 s vs v2.5.1 9.656 s; within ≤ 10 s downgrade band;
  ≤ regression-flag threshold 10.156 s; > 8.2 s closure threshold
  not met). 2nd consecutive cycle ≤ 10 s.
- **Watch fires at:** v2.7 P2 (ship-gate finalize). Close-vote
  criteria: if v2.7 P2 reading ≤ 8.2 s → close fully; else if ≤
  10 s for the 3rd consecutive cycle → downgrade narrative carry;
  else if > 10.156 s → regression-flag with operator scope decision.
- **No P0-time action.**

## §Seed v2.4-F latency-regression posture

Re-state (no P0-time decision required; logging only):

- **Disposition:** LM half CLOSED RECOVERED at v2.6 P2 (LM p95
  12.64 s back at v2.4-P2 ≤ 15 s band; v2.5.1 P2 25.26 s reading
  reclassed as sample-variance outlier). L4 half ⏸ DOWNGRADE-
  TOWARD-CLOSE at 19.89 s (n=4; v2.5.1 P2 = 21.64 s, Δ −1.75 s
  mild recovery; > 17 s close threshold; < 22 s promote-🔴 line).
- **Watch fires at:** v2.7 P2 (ship-gate finalize). Close-vote
  criteria for L4 half: if v2.7 P2 reading ≤ 17 s → close fully;
  else if ≤ 22 s → carry with reduced concern; else if ≥ 22 s →
  promote 🔴 and operator decides v2.8 latency-lever scope.
- **No P0-time action.**

## §v2.6 carry-forward dispositions (quick-ref table)

| Seed | Description | Current disposition | Cap status |
|---|---|---|---|
| v2.6-A | `frog7-wirecli-module-10` Sonnet content drift vs golden SUGGEST | WATCH 🟡; re-measure n=12 at v2.7 P2 per J3 protocol | Cap-counted |
| v2.6-A-T | row-10 timeout-boundary watch (p99 24.96 s; max 25.047 s) | WATCH 🟡; closes when Seed v2.6-G step (2) lands + re-measure ≥ 2 s margin | Cap-counted |
| v2.6-C (was v2.5-C) | Path-D synthetic-fixture P5 implementation (~600 LOC) | DEFER candidate (4th-consecutive); FIRE iff cycle=feature | Cap-counted |
| v2.4-E | Overall p95 watch (9.926 s at v2.6 P2; 2nd consecutive ≤ 10 s) | WATCH 🟢; v2.7 P2 close-vote (≤ 8.2 s closure threshold) | Cap-counted |
| v2.4-F | L4 + LM small-n latency-regression watch (L4 19.89 s, LM 12.64 s at v2.6 P2) | LM CLOSED RECOVERED; L4 DOWNGRADE-TOWARD-CLOSE; v2.7 P2 close-vote | Cap-counted |
| v2.6-G (was v2.5-G) | CLI-timeout instrumentation + tighten + split (step (1) LANDED v2.6 P1) | Step (2) FIRE candidate (J2 audit evidence); step (3) bundle/carry decision | Cap-counted |
| v2.4-I | INTENT-graduated regression-coverage (promotion-criterion-bound) | EXEMPT per Amendment E | Exempt |
| v2.4-J | INTENT-graduated regression-coverage (promotion-criterion-bound) | EXEMPT per Amendment E | Exempt |
| v2.4-K | INTENT-graduated regression-coverage (promotion-criterion-bound) | EXEMPT per Amendment E | Exempt |
| v2.4-L | INTENT-graduated regression-coverage (promotion-criterion-bound) | EXEMPT per Amendment E | Exempt |
| v2.4-M | INTENT-graduated regression-coverage (promotion-criterion-bound) | EXEMPT per Amendment E | Exempt |
| v2.4-N | Remote-CLI monitoring extension (demand-bound) | EXEMPT per Amendment E | Exempt |

**Totals:** Cap-counted = 6 (v2.6-A + v2.6-A-T + v2.6-C + v2.4-E +
v2.4-F + v2.6-G). Exempt = 6 (v2.4-I..N).

Verify against `docs/v2.6-backlog.md` §"Carry-forwards from v2.6" at
P0 fire — if backlog status has drifted (new seed minted post-v2.6
close, or carry-forward disposition changed), reconcile this table
before P0 PR opens.

## §ADR-18 reference block

One-line summary of each Amendment with file:line cite into
`docs/adr/ADR-18-mvp-surface-freeze.md`:

- **Amendment A** (`ADR-18-mvp-surface-freeze.md:342`) — 2026-05-16 v2.2
  P0: Rule 3 extension — feature-cycle LOC soft target ≤ 1500; BLOCK
  at 1.5× = 2250; 3-bucket measurement (production load-bearing,
  test + docs advisory).
- **Amendment B** (`ADR-18-mvp-surface-freeze.md:403`) — 2026-05-16 v2.2
  P0: Rule 6 (NEW) — memory pre-flight at cycle frame; P0 PR body
  carries verified-memory stamp; empty stamp = non-compliant.
- **Amendment C** (`ADR-18-mvp-surface-freeze.md:437`) — 2026-05-17 v2.2
  P2: Rule 3 anchor clarification — gate measurement anchors at
  P0-merge tip (cycle-discipline); predecessor-tag retained for
  cycle-impact narrative.
- **Amendment D** (`ADR-18-mvp-surface-freeze.md:515`) — 2026-05-18 v2.4
  P0: v10 P5 entry-gate split — v10.1-mode (baseline arm gate,
  infrastructure validation) vs v10.3-mode (original gate, real
  promotion); resolves issue #177.
- **Amendment E** (`ADR-18-mvp-surface-freeze.md:648`) — 2026-05-19 v2.4
  P0: Rule 5 cycle-handoff exemption — promotion-criterion-bound +
  demand-bound seeds with verbatim external-trigger citation are
  exempt from the 2-cycle cap until trigger fires.

No new amendment planned at v2.7 PM-mint. If P0 fire surfaces a
binding rule gap (e.g. step (2) FROZEN-surface modification needs
its own amendment, or a new lever-ledger semantics clarification),
operator drafts the amendment at fire time per the v2.4 Amendment D
/ v2.2 Amendment A precedent.

## §Canonical S2 env block (for downstream P1 / P2 prompts)

Every v2.7 work-phase prompt that fires a Tier-3 soak
(`tools/soak_driver.py`) MUST export this env block before
invocation. Folded into the canonical v2.6 P0 template at v2.6 P0
(3rd recurrence of the `PATHSPEC-UNSET` cassette omission); carries
verbatim into v2.7:

```bash
export BRIDGE_RL_LOGGER_ENABLED=1
export BRIDGE_LOC_PATHSPEC=src/,tests/,tools/,dashboard/
```

- `BRIDGE_RL_LOGGER_ENABLED=1` — v10 P4 corpus piggyback (608
  episodes at v2.6 P2 close; gate cleared with 408-episode margin;
  corpus accretion remains a hygiene-positive side effect).
- `BRIDGE_LOC_PATHSPEC=src/,tests/,tools/,dashboard/` — bucket-scoped
  LOC delta emitter for `tools/soak_driver.py` dual-anchor summary;
  unset → `[soak] cycle-tip LOC delta (Amend C): PATHSPEC-UNSET
  [UNKNOWN]`. P2 ship-gate cannot verify Amendment C cycle-tip gate
  without this.

Soak driver invocation pattern (Tier-3 ship-gate):

```bash
.venv/Scripts/python.exe tools/soak_driver.py \
  --cli-pool-size 2 \
  --ppp-auto-probe \
  --total-seconds 1800 \
  --interval-seconds 20
```

`--cli-pool-size 2` is mandatory per `feedback_soak_cli_pool_flag.md`
(default 0 silently reproduces v1.0 cold-start latency regression).

## §Alignment-eval n=6 stability rule (S5 procedure)

Per `feedback_alignment_eval_stability_window.md`, ship-gate
alignment-eval MUST run at `--runs 6` when the prior cycle's Sonnet
`pass_rate` is within 0.05 of the FR-OG-7 floor (0.80). Branching
rule at S4 entry:

```
prior_sonnet = <read from prior cycle's alignment-eval report>
if prior_sonnet < 0.85:
    runs = 6     # n=6 mandate
else:
    runs = 3     # default
```

**v2.7 P2 entry condition:** prior cycle is v2.6 P2; Sonnet
pass_rate = **0.9412** (n=6 reading at
`reports/alignment-eval-20260520T205842Z.json`); 0.9412 ≥ 0.85 →
default `--runs 3` applies UNLESS:

- `unstable_sonnet` count from any prior-run probe exceeds
  0.25 × total (≥ 8 of 32 rows); refire at doubled n regardless
  of headline pass_rate.
- Row-level CLI-timeout-rate > 33% on any row (matches Seed v2.5-A
  pattern that re-falsified at v2.6); exclude from gate denominator
  on this measurement run.

The v2.7 P2 ship-gate prompt MUST encode this branching rule
explicitly — do not rely on operator memory. Operator shell is
PowerShell per CLAUDE.md; both shell variants below for whichever
the P2 ship-gate prompt mints into.

POSIX / Git Bash:

```bash
prior_sonnet=$(jq -r '.sonnet_pass_rate' \
  reports/alignment-eval-20260520T205842Z.json)
if (( $(echo "$prior_sonnet < 0.85" | bc -l) )); then
  runs=6
else
  runs=3
fi
.venv/Scripts/python.exe tools/alignment_eval.py \
  --runs "$runs" \
  --ci-gate
```

PowerShell (Windows operator-shell):

```powershell
$prior_sonnet = (Get-Content reports/alignment-eval-20260520T205842Z.json `
  | ConvertFrom-Json).sonnet_pass_rate
$runs = if ($prior_sonnet -lt 0.85) { 6 } else { 3 }
.venv\Scripts\python.exe tools\alignment_eval.py `
  --runs $runs `
  --ci-gate
```

## §Phase prompt stubs

Phase prompts to mint after P0 fires (sequencing depends on §"Cycle-
type call" + §"Seed v2.6-G step (2) fire decision" + §"Seed v2.6-G
step (3) env-split fire decision" + §"Seed v2.6-C deferral/fire
decision"):

- **v2.7 P1** — **FIRES per P0 picks above.** Resolved scope:
  - **Seed v2.6-G step (2) timeout-tighten** (operator pick):
    `phase-1-cli-timeout-tighten.md` (TBD mint ahead-of-fire per
    PR #195 / PR #197 precedent). Scope: change
    `src/stream_manager/cli_governance.py:49` `TIMEOUT_SECONDS`
    from 25.0 to **30.0** (J2 audit primary); ≤ 20 LOC `src/`
    change. First FROZEN-surface lever ever wired; lever ledger
    BUMP 2 → 3 (production-bucket canonical).
  - **Seed v2.6-G step (3) env-split**: NOT bundled this cycle
    (CARRY independently per P0 pick; v2.8+ candidate).
  - **Seed v2.6-C Path-D P5**: DEFERRED v2.8 per P0 pick
    (5th-consecutive deferral).
  - **Single work phase** (no P1a): the elected lever fits in one
    PR. LOC budget far under Amendment A soft cap 1500.
- **v2.7 P2** — ship-gate finalize. Follows the v2.4 P2 / v2.5.1 P2
  / v2.6 P2 pattern; mint prompt ahead-of-fire per the PR #182 /
  PR #188 / PR #195 / PR #197 precedent. v2.7 P2 S4 entry condition
  checks `--runs 3` default per §"Alignment-eval n=6 stability rule"
  above (escape-hatch fires only if unstable_sonnet exceeds 0.25 ×
  total OR row-level CLI-timeout-rate > 33%). Seed v2.4-E + v2.4-F
  L4 half close-vote fires at P2. Seed v2.6-A n=12 re-measure fires
  at P2 by default (per §"Seed v2.6-A re-measure decision").

**Skeleton mint scope:** this P0 skeleton does NOT mint P1 or P2
prompts. Subsequent mints happen after P0 fires, per precedent
(PR #182 minted v2.4 P2 ahead-of-fire after v2.4 P0 closed;
PR #188 minted v2.5.1 P1 ahead-of-fire after v2.5 P2 BLOCK;
PR #195 minted v2.6 P1 prompt ahead of P1 fire; PR #197 bundled
v2.6 P2 prompt mint + Seed v2.5-A diagnosis pre-execution).

## DoD

- [x] Branch opened from `main` at `c3a964c` (v2.6.0 ship; verified
      at P0 fire 2026-05-21).
- [x] Memory pre-flight stamp in PR body (Amendment B §"Required
      output"; self-applies to this P0 PR). 6 load-bearing memories
      verified FRESH at `c3a964c`; stamp in `docs/v2.7-task-plan.md`
      §"Memory pre-flight stamp".
- [x] `docs/v2.7-next-steps.md` drafted alongside this frame
      (mirrors `docs/v2.6-next-steps.md` pattern); includes verbatim
      external-trigger citations for every Amendment E exempt seed
      (v2.4-I..N).
- [x] All operator decisions from §"Cycle-type call", §"Rule 5 cap-
      counted reading", §"Seed v2.6-G step (2) fire decision",
      §"Seed v2.6-G step (3) env-split fire decision", §"Seed v2.6-C
      deferral/fire decision", §"Seed v2.6-A re-measure decision"
      recorded in `docs/v2.7-task-plan.md` §"Operator decisions
      recorded at P0 fire (2026-05-21)".
- [x] §"v2.6 carry-forward dispositions" table reconciled against
      `docs/v2.6-backlog.md` ground truth at P0 fire. No drift.
- [x] If cycle = feature: explicit lever-wire commitment recorded —
      Seed v2.6-G step (2) cap value = **30 s** (J2 audit primary);
      first FROZEN-surface lever ever wired
      (`src/stream_manager/cli_governance.py:49` `TIMEOUT_SECONDS`).
      Ledger BUMP 2 → 3 at v2.7 P1 merge.
- [ ] If cycle = consolidation: deletion-offset survey ≥ 0 LOC net
      vs P0-merge tip (per ADR-18 Amendment C cycle-tip anchor).
      `n/a — cycle = feature`
- [x] Cycle-tip LOC anchor cited verbatim in `docs/v2.7-task-plan.md`
      using `<v2.7-P0-merge-SHA>..HEAD` template (per Amendment C).
      Placeholder SHA backfilled in follow-up PR after P0 fire merge
      (v2.5 PR #186 + v2.6 PR #194 precedent).
- [x] Canonical S2 env block (`BRIDGE_LOC_PATHSPEC=src/,tests/,
      tools/,dashboard/`) recorded in this P0 frame §"Canonical S2
      env block" + carried into v2.7 P1 / P2 prompt templates at
      mint.
- [x] Alignment-eval n=6 stability rule encoded in this P0 frame
      §"Alignment-eval n=6 stability rule" for v2.7 P2 prompt
      template S4 entry (do not rely on operator memory).
- [x] Seed v2.6-A + Seed v2.6-A-T coupling logged in
      `docs/v2.7-next-steps.md` §"Seed v2.6-A-T" (closes iff Seed
      v2.6-G step (2) lands + row-10 re-measured p99 ≥ 2 s under
      new cap; with 30 s cap chosen, expected margin = 5.04 s).

## Refs

- `docs/prompts/v2.6-orchestration/phase-0-cycle-frame.md` —
  structural anchor for this skeleton; preserve section headings,
  decision-block style, DoD shape.
- `docs/prompts/v2.4-orchestration/phase-0-cycle-frame.md` —
  PM-mint precedent (PR #178); v2.7 PM-mint follows the same
  skeleton-then-fire pattern.
- `docs/v2.6-next-steps.md` — predecessor next-steps doc; v2.7
  next-steps must mirror its shape + carry forward Amendment E
  external-trigger citations.
- `docs/v2.6-backlog.md` — backlog ground-truth at v2.6 P2 close;
  reconcile §"v2.6 carry-forward dispositions" table against this
  file at P0 fire.
- `docs/seed-v2.6-g-step2-timeout-tighten-audit.md` — J2 evidence
  audit (this session) for Seed v2.6-G step (2) cap value selection.
- `docs/seed-v2.6-a-row10-remeasure-protocol.md` — J3 protocol
  (this session) for Seed v2.6-A n=12 re-measure at v2.7 P2.
- `docs/seed-v2.5-a-row10-diagnosis.md` — v2.6 P2 S6.5 verdict
  (CONTENT-DRIFT); Seed v2.6-A + v2.6-A-T mint origin.
- `docs/adr/ADR-18-mvp-surface-freeze.md` — Amendments A / B / C / D
  / E + Rules 1–6.
- `project_v26_cycle_close.md` — v2.6 close-out facts.
- `feedback_certportal_dev_firewall.md` — SM dev firewall against
  `C:\Users\SeanHoppe\VS\certPortal\`.
- `feedback_no_self_monitor.md` — polarity-flip rule.
- `feedback_alignment_eval_stability_window.md` — n=6 mandate near
  FR-OG-7 floor (minted v2.5.1 P1).
- `feedback_soak_cli_pool_flag.md` — `--cli-pool-size 2` required.
- `feedback_glob_narrowing_no_op.md` — PR #184 cassette.
- Precedent PM-mint PRs: PR #191 (v2.6 PM-mint — P0 frame +
  next-steps bundle); PR #178 (v2.4 PM-mint — P0 frame + next-steps
  + Amendment D draft).
- Precedent ahead-of-fire prompt mints: PR #182 (v2.4 P2 ship-gate
  finalize), PR #188 (v2.5.1 P1 corrective P1 prompt), PR #195
  (v2.6 P1 prompt), PR #197 (v2.6 P2 prompt + S6.5 pre-execution).
