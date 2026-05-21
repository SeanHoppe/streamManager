# v2.7 P0 — Cycle frame

> Minted ahead-of-fire as a skeleton (v2.4-pm-mint precedent: PR #178
> minted v2.4 P0 frame + next-steps + Amendment D draft ahead of P0
> fire PR #179; v2.6 PR #191 minted v2.6 P0 frame + next-steps ahead
> of fire PR #193). Cycle type **TBD by operator at fire time**.
>
> **Default lean: OPERATOR-BOUND (Path-F or Path-C).** Two candidate
> headline scopes are pre-staged for v2.7; operator picks at fire time
> per `docs/v2.7-next-steps.md` §"Two candidate headline scopes":
>
> - **Path-F (feature).** Fire Seed v2.6-G step (2) timeout-tighten
>   at v2.7 P1 with **ADR-18 Amendment F (freeze-lift on
>   `TIMEOUT_SECONDS`)** co-minted at v2.7 P0. Measured eval p99 =
>   25.048 s now in hand (v2.6 P1 instrumentation). J2 audit band
>   30–45 s; new-cap floor ≥ 30 s. Closes Seed v2.6-A-T when row-10
>   re-measured p99 ≥ 2 s under new cap. Ledger BUMP 2 → 3.
> - **Path-C (consolidation).** Hold Seed v2.6-G step (2). Narrow-
>   corrective cycle: Seed v2.6-A n=12 re-measure (tooling-only, zero
>   production LOC), Seed v2.4-E + Seed v2.4-F (L4 half) watch roll-
>   ups. Net production-bucket LOC ≤ 0 vs cycle-tip per Amendment C.
>   Ledger HOLD 2. Alternation hygiene argues this path after v2.6
>   feature.
>
> Comparison anchor: `docs/v2.7-next-steps.md` §"P0 frame — operator-
> bound decisions" (drafted alongside this frame in this PM-mint).
>
> **Skeleton scope:** this file bounds the v2.7 P0 decision surface
> and surfaces the cap-counted reading + cross-refs. The operator
> fills in decision blocks at fire time. NO operator decision is
> pre-empted by this skeleton.

## Branch + base

- Base: `main` after v2.6.0 (commit `c3a964c`, PR #198 — v2.6 P2
  ship-gate finalize; tag `v2.6.0` pushed 2026-05-21). Verify SHA
  freshness at fire time.
- Branch: `feat/v2.7-p0-cycle-frame` (feature default if Path-F
  selected; rename to `chore/v2.7-p0-cycle-frame` if Path-C selected).
- PR target: `main`.

## §Memory pre-flight (Rule 6 — ADR-18 Amendment B)

Verify each load-bearing memory against current repo state before
opening P0 PR. If any cited memory is stale, update it BEFORE
opening P0 PR. Record verification stamp in P0 PR body.

**Minimum re-read list for v2.7 P0** (operator may extend; Path-F
adds 1 entry):

- `feedback_certportal_dev_firewall.md` — dev-session firewall against
  `C:\Users\SeanHoppe\VS\certPortal\`; deny rules enforced via
  `.claude/settings.local.json`.
- `feedback_no_self_monitor.md` — polarity-flip rule; SM must never
  govern itself; include-iff `project_slug NOT IN
  STREAM_MANAGER_PROJECT_SLUGS`.
- `project_v26_cycle_close.md` — v2.6 ship at `c3a964c`, PR #198 (tag
  pushed 2026-05-21); cycle-tip +147 LOC at soak fire-time (~+670
  post-PR-merge); lever ledger BUMP 1 → 2 production / 0 soak (Seed
  v2.5-G step (1) wire NEW; first wire since v2.3); Seed v2.5-A
  CLOSED CONTENT-DRIFT at S6.5; NEW Seed v2.6-A + v2.6-A-T spawned;
  v10 P4 corpus 608 episodes (Δ +60; gate cleared 3.04×).
- `feedback_alignment_eval_stability_window.md` — n=6 mandate trigger;
  v2.6 P2 n=3 default first-fire triggered escape-hatch (14/32
  unstable + 3 rows ≥ 50% timeout-rate); n=6 re-fire Sonnet 0.9412 /
  Haiku 1.0. v2.7 P2 S4 default `--runs 3` IF Sonnet 0.9412 ≥ floor
  + 0.05 = 0.85 holds (currently holds; verify at S4 entry).
- `feedback_soak_cli_pool_flag.md` — `--cli-pool-size 2` still
  required at soak fire.
- `feedback_glob_narrowing_no_op.md` — S1 wipe + S1.1 pattern;
  `git clean -df` form unchanged.
- **Path-F only:** `feedback_cli_over_sdk.md` — real `claude -p`
  subprocess path exercised by Seed v2.6-G step (2) change at
  `src/stream_manager/cli_governance.py:49`.

**Stamp output (P0 PR body):** for each memory above, record
`fresh / updated-in-this-PR / superseded-by-X`. Empty stamp =
non-compliant (Amendment B §"Required output").

## §Cycle-type call

Decision-block (operator fills at fire time):

- [ ] **Path-F (feature cycle)** — Seed v2.6-G step (2) timeout-
      tighten at v2.7 P1 + Amendment F freeze-lift at v2.7 P0; soft
      LOC ≤ 1500 per ADR-18 Amendment A; BLOCK at 1.5× = 2250.
- [ ] **Path-C (consolidation cycle)** — net LOC ≤ 0 vs P0-merge tip
      per ADR-18 Amendment C; Seed v2.6-G step (2) holds to v2.8.
- [ ] **Maximal feature override** — Path-F + Seed v2.6-C Path-D P5
      at v2.7 P1a (5th-deferral break; rare; requires v10.3 stochastic-
      propensities dependency status).

**Operator pick:** `<TBD at fire time>` (rationale + memory cite).

**Coupling note (binding).** Path-F classification requires:

- Seed v2.6-G step (2) timeout-tighten — change
  `src/stream_manager/cli_governance.py:49` `TIMEOUT_SECONDS = 25.0`
  to measured-band value (≥ 30 s per J2 audit + v2.6 P1 p99 reading).
- **ADR-18 Amendment F** — minted in same P0 PR OR separate ADR-18
  update PR ahead of P1 fire. Amendment F text lifts
  `TIMEOUT_SECONDS` from the FROZEN surface list with measured-band
  rationale (J2 evidence audit + v2.6 P1 instrumentation p99).
- Optional Seed v2.6-G step (3) env-split (`BRIDGE_CLI_TIMEOUT` /
  `BRIDGE_CLI_TIMEOUT_EVAL`) — ~30 LOC tooling. MAY bundle same
  phase (v2.7 P1) OR defer to v2.8 (operator decides at P1 mint).

If maximal feature override: + Seed v2.6-C Path-D synthetic-fixture
P5 (~600 LOC) at v2.7 P1a. LOC budget then dominated by Seed v2.6-C;
still well under Amendment A soft cap 1500.

**Default lean rationale.** v2.6 was feature (Seed v2.5-G step (1)
wire); v2.5 + v2.5.1 + v2.4 were consolidation. Alternation hygiene
argues Path-C consolidation after v2.6 feature. BUT Seed v2.6-G step
(2) input now in hand (measured eval p99 = 25.048 s from v2.6 P1)
removes the last blocker for Path-F. Operator judges at P0 fire which
takes priority: alternation hygiene (Path-C) vs measurement-protocol
follow-through (Path-F).

## §`WIRED_LEVER_LEDGER_COUNT` posture

Entering v2.7 P0: **2 production / 0 soak**. Production-scope
canonical per Seed v2.4-H binding. Lever wires:

1. v2.3 Seed 6 JsonlTailWorker production wiring (unchanged since
   v2.3.0 `8303f38`).
2. v2.6 P1 Seed v2.5-G step (1) alignment-eval wall-clock
   instrumentation (NEW v2.6.0 `c3a964c`).

Decision-block:

- [ ] **Target end posture (Path-F):** 3 production / 0 soak (Seed
      v2.6-G step (2) timeout-tighten + optional step (3) env-split
      same wire-count; step (3) is configuration not a new lever).
- [ ] **Target end posture (Path-C):** HOLD 2 production / 0 soak.
- [ ] **Target end posture (maximal feature):** 3 production / 0 soak
      (Seed v2.6-C ships harness without lever-wire bump; Seed v2.6-G
      step (2) is the only ledger-counted wire).

## §Rule 5 cap-counted reading (Amendment E)

Entering v2.7 P0: **6 cap-counted** (Seeds v2.6-A + v2.6-A-T + v2.6-C
+ v2.4-E + v2.4-F + v2.6-G) + **6 EXEMPT** (v2.4-I..N) = **12 open**.
Δ +1 vs v2.6 P0 entry (5 cap-counted).

v2.4 P0 Amendment E cap = 5. v2.6 P0 accepted 5-cap reading. v2.7 P0
MUST address the cap-bump explicitly:

Decision-block:

- [ ] **Option (i)** — Accept cap-bump 5 → 6 explicitly per precedent
      (v2.2 1 → 6, v2.3 6 → 11). Recorded rationale lives in
      `docs/v2.7-task-plan.md` §"Operator decisions".
- [ ] **Option (ii)** — Mint additional Amendment E EXEMPT citation
      for Seed v2.6-A-T (natural candidate: promotion-criterion-bound
      on Seed v2.6-G step (2) landing; closes when measured-band cap
      lands + row-10 re-measured p99 ≥ 2 s under). Keeps cap-counted
      reading at 5.

Reconciliation against `docs/v2.6-backlog.md` §"ADR-18 Rule 5 —
backlog hard cap (Amendment E reading at v2.7 P0)" — verified at P0
fire; no drift.

## §Seed v2.6-G fire decision

Decision-block:

- [ ] **Path-F: FIRE step (2)** at v2.7 P1 — change `TIMEOUT_SECONDS`
      to measured-band value (≥ 30 s per J2 + v2.6 P1 p99 25.048 s).
      Requires Amendment F freeze-lift (see §"Amendment F freeze-lift
      decision" below).
- [ ] **Path-F bundle: FIRE step (2) + step (3) same phase** —
      `BRIDGE_CLI_TIMEOUT` + `BRIDGE_CLI_TIMEOUT_EVAL` env-readable;
      ~30 LOC tooling addition.
- [ ] **Path-C: HOLD step (2)** to v2.8. Seed v2.6-G renames Seed
      v2.7-G in v2.7-backlog. Step (3) env-split also carries.

**Default lean** per `docs/v2.7-next-steps.md` §"Two candidate
headline scopes": operator-bound; both Path-F and Path-C are
legitimate choices.

## §Amendment F freeze-lift decision (Path-F only)

If Path-F selected, ADR-18 Amendment F MUST be minted to lift
`src/stream_manager/cli_governance.py:49` `TIMEOUT_SECONDS` from
FROZEN surface list. Amendment F text recipe:

```
## Amendment F (v2.7 P0 mint) — measured-band freeze-lift on TIMEOUT_SECONDS

Per the J2 evidence audit (`docs/seed-v2.4-g-cli-timeout-audit.md`)
and v2.6 P1 alignment-eval wall-clock instrumentation (PR #196,
measured Sonnet p99 = 25.048 s, n=192), `src/stream_manager/
cli_governance.py:49` `TIMEOUT_SECONDS = 25.0` saturates the current
cap. Audit recommends band 30–45 s; new-cap floor ≥ 30 s.

`TIMEOUT_SECONDS` is hereby LIFTED from FROZEN list for v2.7 cycle
duration ONLY. Lift scope: change the literal `TIMEOUT_SECONDS = 25.0`
to a value in [30, 45]. Any other change to `cli_governance.py:49`
remains under Rule 1 surface freeze.

Lift conditions for re-freeze at v2.8:
- v2.7 P2 ship-gate confirms latency surface absorbs the cap-bump
  without overall p95 regression (Seed v2.4-E watch must close OR
  hold ≤ 10 s downgrade band).
- Seed v2.6-A-T closes (row-10 p99 ≥ 2 s under new cap).
- v2.7 P2 close memory records the chosen cap value as the new
  FROZEN literal for v2.8+.
```

Decision-block:

- [ ] **Amendment F minted at v2.7 P0** (this PR; co-mint with frame).
- [ ] **Amendment F deferred to separate ADR-18 update PR** ahead of
      v2.7 P1 fire.
- [ ] **Path-C selected — Amendment F NOT minted this cycle**.

## §Seed v2.6-C fire decision

Decision-block:

- [ ] **Default DEFER** (5th consecutive deferral). Lever-budget bound.
      Becomes Seed v2.7-C in v2.7-backlog. Phase-5 prompt re-mint per
      Amendment D gate-split also defers to v2.8 P0.
- [ ] **Maximal feature override FIRE** at v2.7 P1a — operator decides
      v10.3 stochastic-propensities dependency status (issue #112) is
      ready; ~600 LOC Path-D synthetic-fixture P5 implementation.

## §Seed v2.6-A carry-forward

Decision-block:

- [ ] **Resolves at v2.7 P2 ship-gate** via instrumented n=12 re-
      measure (zero production LOC; tooling-only). Verdict (a) golden-
      update (SUGGEST → INTERVENE in `tests/golden/l4_alignment.jsonl:10`),
      (b) hold golden + accept drift watch, or (c) further re-measure
      at v2.8. **Default-lean (c)**.

## §Amendment C cycle-tip anchor

Per ADR-18 Amendment C, cycle-discipline LOC gate at v2.7 P2 binds at
the v2.7 P0-merge tip. Anchor SHA recorded post-merge of this P0 fire
PR in a follow-up backfill commit per v2.5 PR #186 / v2.6 PR #194
precedent.

Decision-block (filled post-merge):

- [ ] **v2.7 cycle-tip anchor:** `<TBD-merge-SHA>`. Predecessor tag
      `c3a964c` (v2.6.0) is narrative comparator only.
- [ ] **Diff command:**
      ```
      git diff <v2.7-P0-merge-SHA>..HEAD --stat -- src tests tools dashboard
      ```

## §Cycle-discipline guardrails

- **LOC budget (Amendment A + Amendment C).** Anchor = cycle-tip
  (v2.7 P0-merge SHA, backfilled post-merge). Gate:
  - **Path-F:** soft ≤ 1500 / BLOCK at 1.5× = 2250.
  - **Path-C:** net ≤ 0 production-bucket LOC vs cycle-tip.
  - **Maximal feature:** soft ≤ 1500 (Seed v2.6-C ~600 LOC + Seed
    v2.6-G step (2) ~5 LOC + step (3) ~30 LOC = ~635 LOC dominant).

- **Production-bucket commitment.** v2.7 P0 (this fire PR) carries
  zero production-bucket delta (docs-only frame). P1 lever-wire
  commitment depends on path selected.

- **Rule 5 backlog cap.** See §"Rule 5 cap-counted reading" above.

- **Rule 6 memory pre-flight.** See §"Memory pre-flight" above.

- **Surface freeze.** ADR-18 Rule 1 in force. `TIMEOUT_SECONDS = 25.0`
  STAYS FROZEN unless Amendment F minted (Path-F only).

## §v10.x slot

Per #131 trigger cond 2, v10.x cycle blocked while v2.x is in P0–P3
numbered phases. v2.7 numbered-phase span = P0 → P2. v10.x slot also
blocked on #112 (v10 P5) which remains blocked at the
implementation side (Seed v2.6-C deferred again — 5th cycle if Path-F
or Path-C selected; breaks if maximal feature override fires).
#131 remains gated.

#177 CLOSED at v2.4 (Amendment D landed PR #179). #112 OPEN; blocked
on Path-D implementation, NOT on #177.

## DoD (v2.7 P0 fire PR)

- [ ] `docs/v2.7-task-plan.md` minted with all operator decisions
      recorded (cycle type / ledger posture / cap reading / Seed
      v2.6-G + Amendment F + v2.6-C + v2.6-A decisions / Amendment C
      anchor / memory pre-flight).
- [ ] `docs/v2.7-next-steps.md` decision blocks ticked per operator
      picks (pre-minted at this PM-mint as the comparison anchor).
- [ ] `docs/prompts/v2.7-orchestration/phase-0-cycle-frame.md`
      decision-block ticks + operator-pick rationale lines filled
      (this skeleton).
- [ ] `docs/v2.6-backlog.md` reconciled (no drift vs P0 frame §"v2.6
      carry-forward dispositions" table).
- [ ] Memory pre-flight stamp included.
- [ ] Cycle-tip anchor template recorded; SHA populated post-merge
      in follow-up commit per v2.5 PR #186 / v2.6 PR #194 precedent.
- [ ] Path-F only: `docs/adr/ADR-18-mvp-surface-freeze.md` Amendment F
      appended (or scheduled to land in a separate ADR-18 update PR
      ahead of v2.7 P1).
- [ ] Single PR `chore(v2.7-p0):` OR `feat(v2.7-p0):` against `main`
      depending on path selected (trivially true at merge).

## §Refs

- `docs/v2.7-next-steps.md` (the comparison anchor; pre-minted this
  PM-mint).
- `docs/v2.6-backlog.md` (v2.6 P2 close-out backlog ground truth;
  `docs/v2.7-next-steps.md` §"Seeds" mirrors row contents).
- `docs/v2.6-task-plan.md` (predecessor cycle task plan).
- `docs/v2.6-next-steps.md` (predecessor cycle anchor).
- `docs/seed-v2.4-g-cli-timeout-audit.md` (J2 evidence audit; Seed
  v2.6-G measurement-protocol stance, renamed v2.4-G → v2.5-G →
  v2.6-G).
- `docs/seed-v2.5-a-row10-diagnosis.md` (Seed v2.5-A verdict
  CONTENT-DRIFT; Seed v2.6-A + v2.6-A-T mint origin).
- `docs/adr/ADR-18-mvp-surface-freeze.md` Amendments A / B / C / D /
  E (current); Amendment F TBD Path-F-only.
- `project_v26_cycle_close.md` (v2.6 cycle close memory).
- `feedback_alignment_eval_stability_window.md` (n=6 mandate memory).
- `feedback_certportal_dev_firewall.md` (dev firewall).
- `feedback_no_self_monitor.md` (polarity-flip rule).
- `feedback_soak_cli_pool_flag.md` (`--cli-pool-size 2` required).
- `feedback_glob_narrowing_no_op.md` (S1 wipe + S1.1 pattern).
- `feedback_cli_over_sdk.md` (CLI subprocess path; Path-F-only).
- Precedent PM-mint PRs: PR #178 (v2.4 PM-mint), PR #191 (v2.6 PM-mint).
- Precedent ahead-of-fire prompt mints: PR #182 (v2.4 P2 ship-gate),
  PR #188 (v2.5.1 P1 corrective), PR #195 (v2.6 P1), PR #197 (v2.6 P2).
