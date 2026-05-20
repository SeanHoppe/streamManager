# v2.6 P0 — Cycle frame

> Minted ahead-of-fire as a skeleton (v2.4-pm-mint precedent: PR #178
> minted v2.4 P0 frame + next-steps + Amendment D draft ahead of P0
> fire PR #179). Cycle type **TBD by operator at fire time**.
>
> **Default lean: feature.** Three load-bearing carry-forwards from
> v2.5.1 P2 ship (`c1e9070`, PR #190) sequence a feature cycle as the
> dominant fit:
>
> 1. Seed v2.5-G (renamed from v2.4-G) — 🔴 CLI-timeout instrumentation
>    measurement-protocol step (1): per-run wall-clock in alignment-eval
>    row runner (~30 LOC tooling; production-bucket LOC delta breaks
>    consolidation-cycle net ≤ 0 gate). Also resolves Seed v2.5-A
>    `frog7-wirecli-module-10` 100% Sonnet timeout opacity (2-for-1
>    measurement value). Strongest v2.5.1 P1 single-row signal yet.
> 2. Seed v2.5-C (renamed from v2.4-C) — Path-D synthetic-fixture P5
>    implementation (~600 LOC; requires feature classification per
>    Amendment A). Deferral count: 2 cycles (v2.4 + v2.5). Phase-5
>    prompt re-mint to reflect Amendment D gate-split (v10.1-mode vs
>    v10.3-mode) packages with implementation.
> 3. Seed v2.4-F 🟡 L4/LM small-n regression-flag — needs n > 4 re-fire
>    to decide 🔴 promotion vs sample-variance dismissal. Re-measure
>    fires at v2.6 P2 ship-gate regardless of cycle type; the seed is
>    not a P1 work driver but informs cycle posture.
>
> **Pre-authorized operator signal (2026-05-20 /goal directive):**
> feature cycle confirmed at PM-mint time; Seed v2.5-G + Seed v2.5-A
> 2-for-1 cited as clear lever-wire candidate. Final cycle-type call
> still recorded at fire time per the skeleton's decision-block
> contract — the operator may downgrade to consolidation if v2.6 P0
> fire reveals a blocker, but the default lean and the planned-lever
> recording reflect the pre-authorization.
>
> Comparison anchor: `docs/v2.6-next-steps.md` §"P0 frame — operator-
> bound decisions" (drafted alongside this frame in this PM-mint).
>
> **Skeleton scope:** this file bounds the v2.6 P0 decision surface
> and surfaces the cap-counted reading + cross-refs. The operator
> fills in decision blocks at fire time. NO operator decision is
> pre-empted by this skeleton.

## Branch + base

- Base: `main` after v2.5.1 (commit `c1e9070`, PR #190 — v2.5.1 P2
  ship-gate finalize). Verify SHA freshness at fire time.
- Branch: `feat/v2.6-p0-cycle-frame` (feature default; rename to
  `chore/v2.6-p0-cycle-frame` only if operator overrides to
  consolidation at fire time).
- PR target: `main`.

## §Memory pre-flight (Rule 6 — ADR-18 Amendment B)

Verify each load-bearing memory against current repo state before
opening P0 PR. If any cited memory is stale, update it BEFORE
opening P0 PR. Record verification stamp in P0 PR body.

**Minimum re-read list for v2.6 P0** (operator may extend):

- `feedback_certportal_dev_firewall.md` — dev-session firewall against
  `C:\Users\SeanHoppe\VS\certPortal\`; deny rules enforced via
  `.claude/settings.local.json`.
- `feedback_no_self_monitor.md` — polarity-flip rule; SM must never
  govern itself; include-iff `project_slug NOT IN
  STREAM_MANAGER_PROJECT_SLUGS`.
- `project_v25_cycle_close.md` — v2.5.1 ship at `c1e9070`, PR #190;
  cycle-tip bucket-scoped LOC = 0 (consolidation cycle held across
  P0 + P2 BLOCK + v2.5.1 P1 + v2.5.1 P2); lever ledger HOLD 1
  production / 0 soak; Seed v2.4-Q CLOSED RECOVERED at n=6 0.9375;
  Seed v2.5-A `frog7-wirecli-module-10` 100% timeout opacity carries
  v2.6; v10 P4 corpus 548 episodes (gate cleared 2.74×).
- `feedback_alignment_eval_stability_window.md` — minted v2.5.1 P1;
  mandates `--runs 6` when prior cycle Sonnet pass_rate < 0.85 (within
  0.05 of 0.80 FR-OG-7 floor). v2.5.1 P2 n=6 Sonnet = 0.9375 → v2.6
  S4 may default to `--runs 3` IF the rule's prior-cycle threshold
  is met; verify at S4 entry.
- `feedback_soak_cli_pool_flag.md` — `--cli-pool-size 2` still
  required at soak fire.
- `feedback_glob_narrowing_no_op.md` — PR #184 cassette; filename
  glob narrowing without verifying driver write-pattern is no-op.

**Stamp output (P0 PR body):** for each memory above, record
`fresh / updated-in-this-PR / superseded-by-X`. Empty stamp =
non-compliant (Amendment B §"Required output").

## §Cycle-type call

Decision-block (operator fills at fire time):

- [x] **Feature cycle** (≥ 1 lever wired OR Seed v2.5-C Path-D
      synthetic-fixture P5 fires; soft LOC ≤ 1500 per ADR-18
      Amendment A; BLOCK at 1.5× = 2250). **Default lean per
      preamble.**
- [ ] Consolidation cycle (net LOC ≤ 0 vs P0-merge tip per
      ADR-18 Amendment C). **Override path** — requires operator
      rationale; defers Seed v2.5-G implementation a 3rd cycle and
      Seed v2.5-A diagnosis remains blocked.

**Operator pick:** `feature` (2026-05-20 fire; pre-authorized at PM-mint
preamble; Seed v2.5-G step (1) instrumentation wires lever +1 production-
bucket per Amendment A 3-bucket; resolves Seed v2.5-A diagnosis blocker
2-for-1; alternation hygiene argues feature after 3 of last 4 cycles
consolidation).

**Coupling note (binding).** Feature cycle classification requires
at least one of:

- Seed v2.5-G measurement-protocol step (1) — instrumentation
  (~30 LOC tooling; production-bucket addition under Amendment A
  3-bucket measurement, qualifies as lever-wire on its own).
  Env-readable `BRIDGE_CLI_TIMEOUT` / `BRIDGE_CLI_TIMEOUT_EVAL`
  split (step 3) is bonus same-phase scope, NOT required for
  lever-wire status. See §"Seed v2.5-G fire decision" below.
- Seed v2.5-C Path-D synthetic-fixture P5 implementation (~600 LOC).
  See §"Seed v2.5-C fire decision" below.

If both fire same cycle the LOC budget is dominated by Seed v2.5-C
(~600) + Seed v2.5-G (~30); well under Amendment A soft cap 1500.

**Default lean rationale.** v2.5 (corrective v2.5.1 included) was
consolidation; consolidation streak now at 3 of last 4 cycles
(v2.2 / v2.4 / v2.5 = consolidation; v2.3 = feature +461 LOC).
Strict alternation hygiene argues feature; carry-forward composition
also argues feature (Seed v2.5-G 🔴 stayed dormant 1 cycle on
consolidation gate; Seed v2.5-C 🟡 deferred 2 cycles). Operator may
still elect consolidation a 4th time if v2.6 P0 fire surfaces a
blocker — record the rationale in `docs/v2.6-task-plan.md`.

## §Rule 5 cap-counted reading

Post-v2.5.1 P2 backlog reading (Seed v2.4-Q CLOSED RECOVERED; Seed
v2.5-A NEW; current open seeds = v2.5-A + v2.5-C + v2.4-E + v2.4-F
+ v2.5-G + v2.4-I..N).

**Cap-counted: 5**

- Seed v2.5-A (`frog7-wirecli-module-10` 100% timeout opacity; NEW at
  v2.5.1 P1). Resolves when Seed v2.5-G instrumentation lands.
- Seed v2.5-C (Path-D synthetic-fixture P5; renamed from v2.4-C;
  deferral candidate this cycle).
- Seed v2.4-E (overall p95 partial-recovery watch; v2.5.1 P2 reading
  9.656 s Δ −0.862 s vs v2.4; downgrade candidate).
- Seed v2.4-F (L4 + LM categorize p95 small-n watch; v2.5.1 P2
  reading L4 21.64 s / LM 25.26 s regression-flag at small n).
- Seed v2.5-G (CLI-timeout instrumentation 🔴; renamed from v2.4-G;
  measurement-protocol step (1) fire candidate this cycle).

**Amendment E EXEMPT: 6**

- Seed v2.4-I (INTENT-graduated, promotion-criterion-bound).
- Seed v2.4-J (INTENT-graduated, promotion-criterion-bound).
- Seed v2.4-K (INTENT-graduated, promotion-criterion-bound).
- Seed v2.4-L (INTENT-graduated, promotion-criterion-bound).
- Seed v2.4-M (INTENT-graduated, promotion-criterion-bound).
- Seed v2.4-N (Remote-CLI monitoring extension, demand-bound).

Cite: ADR-18 Amendment E §"Self-application" (entry 2026-05-19) +
ADR-18 Amendment E §"Acceptance" final acceptance row (verbatim
external-trigger citations required in `docs/v2.6-next-steps.md` at
P0 fire).

**Operator decision:**

- [x] Accept the **5-cap** reading above (cap-counted 5; exempt 6 per
      Amendment E §"Self-application").
- [ ] Mint a Rule 5 clarification (new amendment) if the reading is
      contested. Specify the contested seed(s) and the proposed
      reclassification:

  Contested seed(s): `none`

  Proposed reclassification: `none`

## §Seed v2.5-G fire decision

Evidence input: `docs/seed-v2.4-g-cli-timeout-audit.md` (J2 output
from v2.5 P0); v2.5.1 P1 row-level dispositions in
`docs/v2.5.1-sonnet-floor-investigation.md`; Seed v2.5-A row-10
evidence in `docs/v2.5-backlog.md` §"Seed v2.5-A".

Decision-block (operator fills at fire time):

- [x] **FIRE step (1) this cycle** — instrumentation lands as v2.6
      P1. Scope: per-run wall-clock timing in alignment-eval row
      runner (~30 LOC tooling); env-readable `BRIDGE_CLI_TIMEOUT`
      + `BRIDGE_CLI_TIMEOUT_EVAL` split optional same phase. No
      FROZEN-surface touch; `src/stream_manager/cli_governance.py:49`
      `TIMEOUT_SECONDS = 25.0` stays frozen until step (2) at a
      later cycle. Resolves Seed v2.5-A diagnosis blocker.
- [ ] **DEFER another cycle** — Seed v2.5-G carries to v2.7 P0. 2nd
      consecutive deferral; Seed v2.5-A also defers in lockstep.
      Operator records why measurement-protocol stance still holds
      without the instrumentation lever.

**Operator pick:** `FIRE step (1)` (2026-05-20 fire; default-lean
accepted; ~30 LOC tooling addition to `tools/` qualifies as lever-wire
under Amendment A 3-bucket production-bucket; step (2) timeout-tighten
defers to v2.7+ pending measured eval p99 from step (1); step (3)
env-split is operator-elective at v2.6 P1 mint — MAY bundle same phase
as step (1) OR defer to v2.7+, NOT gated on p99; resolves Seed v2.5-A
row-10 100% timeout opacity in lockstep).

**Coupling note.** If §"Cycle-type call" = consolidation AND this
section = FIRE, the choices are inconsistent (instrumentation tooling
adds production-bucket LOC). Operator must re-open §"Cycle-type
call" OR move instrumentation to a `tools/` path that does not count
toward consolidation gate — there is no such path; consolidation
gate measures `src/ + tests/ + tools/ + dashboard/`. Skeleton does
not auto-resolve; operator records the resolution.

## §Seed v2.5-C fire decision

Path-D synthetic-fixture P5 implementation (~600 LOC). Bound on
cycle-type per §"Cycle-type call" above. Deferral count entering
v2.6: **2 cycles** (v2.4 + v2.5).

Decision-block (operator fills at fire time):

- [ ] **FIRE this cycle** — only valid if §"Cycle-type call" =
      feature. Path-D P5 lands as v2.6 P1 OR P1a (sequenced
      alongside Seed v2.5-G P1 if both fire). Implementation scope
      per ADR-18 Amendment D §"Acceptance" DEFERRED-v2.5 items
      (bandit `is_ready_for_shadow_v10_1()`, train `promotion_gate`
      envelope additive keys, phase-5 prompt re-mint OR new
      `phase-1-shadow-synthetic.md`, shadow harness `--mode=v10.1`
      suffix, `check_criteria` filter).
- [x] **DEFER another cycle** — Seed v2.5-C carries to v2.7 P0
      (3rd consecutive deferral). Re-evaluate at next cycle frame.
      Operator records the deferral rationale (typical: scope
      uncertainty, dependency on v10.3 stochastic propensities,
      lever-budget bound).

**Operator pick:** `DEFER` (2026-05-20 fire; lever-budget bound — Seed
v2.5-G P1 is the single-lever fire this cycle to keep feature-cycle LOC
envelope tight (~30 LOC tooling vs ~600 LOC if bundled); pre-auth signal
cited Seed v2.5-G + Seed v2.5-A 2-for-1 as the lever-wire candidate,
NOT both work phases; Seed v2.5-C carries as v2.6-C to v2.7 — 3rd
consecutive deferral noted, re-evaluate at v2.7 P0 with v10.3
stochastic-propensities status in hand).

**Cycle-coupling guard:** if §"Cycle-type call" = consolidation AND
this section = FIRE, the choices are inconsistent and the operator
must re-open §"Cycle-type call". The skeleton does not auto-resolve;
operator records the resolution.

## §Seed v2.4-F latency-regression posture

Re-state (no P0-time decision required; logging only):

- **Disposition:** WATCH continues 🟡 with regression-flag from
  v2.5.1 P2 (L4 p95 21.64 s at n=4 vs v2.4 P2 15.36 s, Δ +6.28 s;
  LM p95 25.26 s at n=10 vs v2.4 13.60 s, Δ +11.66 s). Small-n
  variance plausibly drives the readings (L4 max-of-4 ≈ p95;
  single outlier anchors).
- **Watch fires at:** v2.6 P2 (ship-gate finalize). Re-measure
  L4 + LM p95 at v2.6 Tier-3 soak; verdict criteria:
  - If v2.6 reading returns to v2.4 P2 band (L4 ≤ 17 s, LM ≤ 15 s),
    retroactively mark v2.5.1 P2 as sample-variance outlier; downgrade
    Seed v2.4-F to 🟢 or close.
  - If v2.6 reading holds at the v2.5.1 P2 elevated band, **promote
    Seed v2.4-F → 🔴** and operator decides v2.7 latency-lever scope.
- **No P0-time action.** Operator records the carry-forward in
  `docs/v2.6-next-steps.md` §"Carry-forwards" + cap-counted reading
  above (already counted as 1 of 5).

## §Seed v2.4-E overall-p95 posture

Re-state (no P0-time decision required; logging only):

- **Disposition:** WATCH continues 🟢. v2.5.1 P2 reading p95 9.656 s
  Δ −0.862 s improvement vs v2.4 P2 10.518 s; also Δ −3.501 s vs
  v2.5 P2 first-soak 13.157 s (which now reads as transient variance
  outlier per `docs/v2.5-backlog.md` §"Seed v2.4-E"). NOT ≤ 8.2 s
  closure threshold yet; downgrade candidate carries.
- **Watch fires at:** v2.6 P2 (ship-gate finalize). If one more cycle
  holds ≤ 10 s, close fully OR retain as 🟢 narrative carry.
- **No P0-time action.**

## §Seed v2.5-A carry-forward

Re-state (no P0-time decision required; logging only):

- **Disposition:** WATCH 🟡; resolves when Seed v2.5-G instrumentation
  lands. v2.5.1 P1 n=6 measurement: row `frog7-wirecli-module-10`
  100% Sonnet timeout (6/6 runs `cli governance timeout (>25.0s);
  degrading`). The row's "stable NONE" Sonnet majority is therefore
  100% timeout-degradation artefact, NOT content drift. Single-row
  evidence drove v2.5.1 P1 verdict-A classification.
- **Close-out path:** instrumented row-runner re-measures row 10 in
  v2.6; verdict = content-drift OR timeout-attributable. If
  §"Seed v2.5-G fire decision" = FIRE, this resolves same cycle.
- **No P0-time action.** Operator records the carry-forward in
  `docs/v2.6-next-steps.md` §"Carry-forwards" + cap-counted reading
  above (already counted as 1 of 5).

## §v2.5 carry-forward dispositions (quick-ref table)

| Seed | Description | Current disposition | Cap status |
|---|---|---|---|
| v2.5-A | `frog7-wirecli-module-10` 100% Sonnet timeout opacity | WATCH 🟡; resolves via Seed v2.5-G fire | Cap-counted |
| v2.5-C (was v2.4-C) | Path-D synthetic-fixture P5 implementation (~600 LOC) | DEFER candidate; FIRE iff cycle=feature | Cap-counted |
| v2.4-E | Overall p95 partial-recovery watch (9.656 s at v2.5.1 P2; Δ −0.862 s vs v2.4) | WATCH 🟢 (improvement); re-measure at v2.6 P2 | Cap-counted |
| v2.4-F | L4 + LM categorize p95 small-n regression-flag (L4 21.64 s / LM 25.26 s at v2.5.1 P2) | WATCH 🟡 regression-flag; v2.6 P2 re-measure decides 🔴 vs variance | Cap-counted |
| v2.5-G (was v2.4-G) | CLI-timeout instrumentation 🔴 | FIRE candidate; PROMOTE confirmed at v2.5 P0 + v2.5.1 P2 | Cap-counted |
| v2.4-I | INTENT-graduated regression-coverage (promotion-criterion-bound) | EXEMPT per Amendment E | Exempt |
| v2.4-J | INTENT-graduated regression-coverage (promotion-criterion-bound) | EXEMPT per Amendment E | Exempt |
| v2.4-K | INTENT-graduated regression-coverage (promotion-criterion-bound) | EXEMPT per Amendment E | Exempt |
| v2.4-L | INTENT-graduated regression-coverage (promotion-criterion-bound) | EXEMPT per Amendment E | Exempt |
| v2.4-M | INTENT-graduated regression-coverage (promotion-criterion-bound) | EXEMPT per Amendment E | Exempt |
| v2.4-N | Remote-CLI monitoring extension (demand-bound) | EXEMPT per Amendment E | Exempt |

**Totals:** Cap-counted = 5 (v2.5-A + v2.5-C + v2.4-E + v2.4-F +
v2.5-G). Exempt = 6 (v2.4-I..N).

Verify against `docs/v2.5-backlog.md` at P0 fire — if backlog status
has drifted (new seed minted post-v2.5.1 close, or carry-forward
disposition changed), reconcile this table before P0 PR opens.

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

No new amendment planned at v2.6 PM-mint. If P0 fire surfaces a
binding rule gap (e.g. lever-ledger semantics for tooling-only
wires, or a new bucket-scope clarification), operator drafts the
amendment at fire time per the v2.4 Amendment D / v2.2 Amendment A
precedent.

## §Canonical S2 env block (for downstream P1 / P2 prompts)

Every v2.6 work-phase prompt that fires a Tier-3 soak (`tools/
soak_driver.py`) MUST export this env block before invocation. This
canonical block folds the `BRIDGE_LOC_PATHSPEC` fix from the v2.5 P2
first-soak `PATHSPEC-UNSET` cassette (Seed v2.5-A's namesake env-block
omission was the 3rd recurrence; canonical fold-in this cycle):

```bash
export BRIDGE_RL_LOGGER_ENABLED=1
export BRIDGE_LOC_PATHSPEC=src/,tests/,tools/,dashboard/
```

- `BRIDGE_RL_LOGGER_ENABLED=1` — v10 P4 corpus piggyback (548
  episodes at v2.5.1 close; gate cleared 2.74×, but corpus accretion
  remains a hygiene-positive side effect).
- `BRIDGE_LOC_PATHSPEC=src/,tests/,tools/,dashboard/` — bucket-scoped
  LOC delta emitter for `tools/soak_driver.py` dual-anchor summary;
  unset → `[soak] cycle-tip LOC delta (Amend C): PATHSPEC-UNSET
  [UNKNOWN]`. P2 ship-gate cannot verify Amendment C cycle-tip gate
  without this. **3rd recurrence of the omission fix — operator
  Q4 (2026-05-20 /goal) folded into canonical template this cycle.**

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

**v2.6 P2 entry condition:** prior cycle is v2.5.1 P2; Sonnet
pass_rate = **0.9375** (n=6 reading); 0.9375 ≥ 0.85 → default
`--runs 3` applies UNLESS:

- `unstable_sonnet` count from any prior-run probe exceeds
  0.25 × total (≥ 8 of 32 rows); refire at doubled n regardless
  of headline pass_rate.
- Row-level CLI-timeout-rate > 33% on any row (matches Seed v2.5-A
  pattern); exclude from gate denominator on this measurement run.

The v2.6 P2 ship-gate prompt MUST encode this branching rule
explicitly — do not rely on operator memory. Operator shell is
PowerShell per CLAUDE.md; both shell variants below for whichever
the P2 ship-gate prompt mints into.

POSIX / Git Bash:

```bash
prior_sonnet=$(jq -r '.sonnet_pass_rate' \
  reports/alignment-eval-20260520T092222Z.json)
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
$prior_sonnet = (Get-Content reports/alignment-eval-20260520T092222Z.json `
  | ConvertFrom-Json).sonnet_pass_rate
$runs = if ($prior_sonnet -lt 0.85) { 6 } else { 3 }
.venv\Scripts\python.exe tools\alignment_eval.py `
  --runs $runs `
  --ci-gate
```

## §Phase prompt stubs

Phase prompts to mint after P0 fires (sequencing depends on §"Cycle-
type call" + §"Seed v2.5-G fire decision" + §"Seed v2.5-C fire
decision"):

- **v2.6 P1** — fires iff §"Cycle-type call" = feature AND at least
  one of §"Seed v2.5-G fire decision" / §"Seed v2.5-C fire decision"
  = FIRE. Candidate scope (operator picks):
  - **Seed v2.5-G instrumentation** (default if only one P1 fires):
    `phase-1-cli-timeout-instrumentation.md`. Scope: per-run wall-
    clock timing in alignment-eval row runner; env-readable
    `BRIDGE_CLI_TIMEOUT` / `BRIDGE_CLI_TIMEOUT_EVAL` split.
    ~30 LOC tooling. No FROZEN-surface touch.
  - **Seed v2.5-C Path-D P5**: `phase-1-shadow-synthetic.md` per
    ADR-18 Amendment D §"Acceptance" DEFERRED-v2.5 row. ~600 LOC.
  - **Both same cycle** (sequenced P1 + P1a): P1 = Seed v2.5-G
    instrumentation (lighter scope, lands first); P1a = Seed v2.5-C
    Path-D P5 (heavier, lands second). LOC budget = ~630 well under
    Amendment A soft cap 1500.
- **v2.6 P2** — ship-gate finalize. Follows the v2.4 P2 / v2.5.1 P2
  pattern; mint prompt ahead-of-fire per the v2.4 P2 / v2.5.1 P2
  precedent (PR #182 / PR #188). v2.6 P2 S4 entry condition checks
  `--runs 6` mandate per §"Alignment-eval n=6 stability rule" above.
  Seed v2.4-F latency-regression re-measure fires at P2 (decides
  🔴 vs variance dismissal).

**Skeleton mint scope:** this P0 skeleton does NOT mint P1 or P2
prompts. Subsequent mints happen after P0 fires, per precedent
(PR #182 minted v2.4 P2 ahead-of-fire after v2.4 P0 closed;
PR #188 minted v2.5.1 P1 ahead-of-fire after v2.5 P2 BLOCK).

## DoD

- [ ] Branch opened from `main` at `c1e9070` or later (verify SHA at
      fire time).
- [ ] Memory pre-flight stamp in PR body (Amendment B §"Required
      output"; self-applies to this P0 PR).
- [ ] `docs/v2.6-next-steps.md` drafted alongside this frame (mirrors
      `docs/v2.5-next-steps.md` pattern); includes verbatim
      external-trigger citations for every Amendment E exempt seed
      (v2.4-I..N).
- [ ] All operator decisions from §"Cycle-type call", §"Rule 5 cap-
      counted reading", §"Seed v2.5-G fire decision", §"Seed v2.5-C
      fire decision" recorded in `docs/v2.6-task-plan.md` (mint at P0).
- [ ] §"v2.5 carry-forward dispositions" table reconciled against
      `docs/v2.5-backlog.md` ground truth at P0 fire.
- [ ] If cycle = feature: explicit lever-wire commitment recorded
      (Seed v2.5-G step-(1) if fired; Seed v2.5-C Path-D P5 if fired;
      OR operator records alternative lever-wire candidate).
- [ ] If cycle = consolidation: deletion-offset survey ≥ 0 LOC net
      vs P0-merge tip (per ADR-18 Amendment C cycle-tip anchor).
- [ ] Cycle-tip LOC anchor cited verbatim in `docs/v2.6-task-plan.md`
      using `<v2.6 P0-merge SHA>..HEAD` template (per Amendment C).
      Placeholder SHA backfilled in follow-up PR after P0 fire merge
      (v2.5 PR #186 precedent).
- [ ] Canonical S2 env block (`BRIDGE_LOC_PATHSPEC=src/,tests/,tools/,
      dashboard/`) recorded in this P0 frame § "Canonical S2 env
      block" + carried into v2.6 P1 / P2 prompt templates at mint.
- [ ] Alignment-eval n=6 stability rule encoded in v2.6 P2 prompt
      template S4 entry (do not rely on operator memory).
- [ ] Seed v2.5-A + Seed v2.5-G coupling logged in
      `docs/v2.6-next-steps.md` §"Carry-forwards" (Seed v2.5-A
      resolves when Seed v2.5-G fires).

## Refs

- `docs/prompts/v2.5-orchestration/phase-0-cycle-frame.md` —
  structural anchor for this skeleton; preserve section headings,
  decision-block style, DoD shape.
- `docs/prompts/v2.4-orchestration/phase-0-cycle-frame.md` —
  PM-mint precedent (PR #178); v2.6 PM-mint follows the same
  skeleton-then-fire pattern.
- `docs/v2.5-next-steps.md` — predecessor next-steps doc; v2.6
  next-steps must mirror its shape + carry forward Amendment E
  external-trigger citations.
- `docs/v2.5-backlog.md` — backlog ground-truth at v2.5.1 close;
  reconcile §"v2.5 carry-forward dispositions" table against this
  file at P0 fire.
- `docs/seed-v2.4-g-cli-timeout-audit.md` — J2 evidence audit (v2.5
  P0) for Seed v2.5-G (renamed from v2.4-G) measurement-protocol
  stance.
- `docs/v2.5.1-sonnet-floor-investigation.md` — v2.5.1 P1 verdict-A
  investigation; row-level dispositions including Seed v2.5-A
  100% timeout row-10 evidence.
- `docs/adr/ADR-18-mvp-surface-freeze.md` — Amendments A / B / C / D
  / E + Rules 1–6.
- `project_v25_cycle_close.md` — v2.5.1 close-out facts.
- `feedback_certportal_dev_firewall.md` — SM dev firewall against
  `C:\Users\SeanHoppe\VS\certPortal\`.
- `feedback_no_self_monitor.md` — polarity-flip rule.
- `feedback_alignment_eval_stability_window.md` — n=6 mandate near
  FR-OG-7 floor (minted v2.5.1 P1).
- `feedback_soak_cli_pool_flag.md` — `--cli-pool-size 2` required.
- `feedback_glob_narrowing_no_op.md` — PR #184 cassette.
- Precedent PM-mint PR: PR #178 (v2.4 PM-mint — P0 frame +
  next-steps + Amendment D draft).
- Precedent ahead-of-fire prompt mints: PR #182 (v2.4 P2 ship-gate
  finalize), PR #188 (v2.5.1 P1 corrective P1 prompt).
