# v2.5 P0 — Cycle frame

> Minted ahead-of-fire as a skeleton (v2.4-pm-mint precedent: PR #182
> minted v2.4 P2 ship-gate finalize ahead of fire; PR #181 minted
> Sonnet-DIP investigation ahead of v2.4 P1). Cycle type **TBD by
> operator at fire time**. Default lean: **consolidation** (v2.4 was
> consolidation, cycle-tip bucket-scoped LOC = 0; v2.3 was feature
> +461 LOC; alternation hygiene argues for the *next* feature only if
> Seed v2.4-C Path-D synthetic-fixture P5 is sequenced into this cycle).
>
> Comparison anchor: `docs/v2.5-next-steps.md` §"P0 frame — operator-
> bound decisions" (to be drafted alongside this frame at P0 fire,
> mirroring v2.4 / v2.3 pattern).
>
> **Skeleton scope:** this file bounds the v2.5 P0 decision surface
> and surfaces the cap-counted reading + cross-refs. The operator
> fills in decision blocks at fire time. NO operator decision is
> pre-empted by this skeleton.

## Branch + base

- Base: `main` after v2.4.0 (commit `08eb71d`, PR #183 — v2.4.0 ship-
  gate finalize). Verify SHA freshness at fire time (PR #184 followed
  with Seeds v2.4-O/P resolution at `9ca5226`; rebase target may be
  later).
- Branch: `feat/v2.5-p0-cycle-frame` (feature) or
  `chore/v2.5-p0-cycle-frame` (consolidation) — pick at branch open
  based on §"Cycle-type call" below.
- PR target: `main`.

## §Memory pre-flight (Rule 6 — ADR-18 Amendment B)

Verify each load-bearing memory against current repo state before
opening P0 PR. If any cited memory is stale, update it BEFORE
opening P0 PR. Record verification stamp in P0 PR body.

**Minimum re-read list for v2.5 P0** (operator may extend):

- `feedback_certportal_dev_firewall.md` — dev-session firewall against
  `C:\Users\SeanHoppe\VS\certPortal\`; deny rules enforced via
  `.claude/settings.local.json`.
- `feedback_no_self_monitor.md` — polarity-flip rule; SM must never
  govern itself; include-iff `project_slug NOT IN
  STREAM_MANAGER_PROJECT_SLUGS`.
- `project_v24_cycle_close.md` — v2.4.0 ship at `08eb71d`; cycle-tip
  bucket-scoped LOC = 0; lever ledger HOLD 1 (Seed v2.4-H bound);
  Sonnet 0.8261 STILL DIPPED (FREEZE-on-content; carries as Seed
  v2.4-Q to v2.5 P2); Haiku 1.0 recovered; v10 P4 corpus 240→360;
  Seeds v2.4-O + v2.4-P RESOLVED via PR #184 (`9ca5226`).
- `feedback_glob_narrowing_no_op.md` — PR #184 cassette where filename
  glob narrowing without verifying actual driver write-pattern was a
  no-op; prefer `git clean -df` / tracked-status filters.
- `feedback_cycle_tolerance_masks_bugs.md` — feature cycles' wider LOC
  tolerance can hide off-by-bucket helper bugs that consolidation
  cycles immediately surface; cycle-discipline tooling needs explicit
  unit tests at BOTH tolerances.

**Stamp output (P0 PR body):** for each memory above, record
`fresh / updated-in-this-PR / superseded-by-X`. Empty stamp =
non-compliant (Amendment B §"Required output").

## §Cycle-type call

Decision-block (operator fills at fire time):

- [ ] Feature cycle (≥ 1 lever wired OR Seed v2.4-C Path-D fires;
      soft LOC ≤ 1500 per ADR-18 Amendment A; BLOCK at 1.5× = 2250).
- [ ] Consolidation cycle (net LOC ≤ 0 vs P0-merge tip per
      ADR-18 Amendment C).

**Operator pick:** `_______________`

**Coupling note (binding).** Seed v2.4-C Path-D synthetic-fixture P5
implementation (~600 LOC) requires **feature** classification per
ADR-18 Amendment A (LOC ceiling). If the operator picks
**consolidation**, Seed v2.4-C automatically defers another cycle and
becomes Seed v2.5-C. This is the load-bearing cycle-type vs Seed v2.4-C
coupling; operator must read §"Seed v2.4-C deferral/fire decision"
below before answering this section.

**Default lean rationale:** v2.4 was consolidation; strict alternation
hygiene would call feature. However alternation is not law — operator
electing consolidation a second cycle in a row is permitted if Seed
v2.4-C is not yet ready to fire OR if no other lever-wire candidate is
sequenced. See ADR-18 Rule 3 (LOC budget) and Amendment A (feature-
cycle soft target).

## §Rule 5 cap-counted reading

Post-PR #184 backlog reading (Seeds v2.4-O + v2.4-P resolved via PR
#184 `9ca5226`; current open seeds = v2.4-C / E / F / G / I..N / Q).

**Cap-counted: 5**

- Seed v2.4-Q (Sonnet-DIP FREEZE-on-content; carries to v2.5 P2 watch).
- Seed v2.4-C (Path-D synthetic-fixture P5 implementation; deferral
  candidate this cycle).
- Seed v2.4-E (overall p95 partial-recovery watch).
- Seed v2.4-F (carry-forward seed from v2.4 backlog).
- Seed v2.4-G (CLI timeout audit — see §"Seed v2.4-G promotion
  question" below).

**Amendment E EXEMPT: 6**

- Seed v2.4-I (INTENT-graduated, promotion-criterion-bound).
- Seed v2.4-J (INTENT-graduated, promotion-criterion-bound).
- Seed v2.4-K (INTENT-graduated, promotion-criterion-bound).
- Seed v2.4-L (INTENT-graduated, promotion-criterion-bound).
- Seed v2.4-M (INTENT-graduated, promotion-criterion-bound).
- Seed v2.4-N (Remote-CLI monitoring extension, demand-bound).

Cite: ADR-18 Amendment E §"Self-application" (entry 2026-05-19) +
ADR-18 Amendment E §"Acceptance" final acceptance row (verbatim
external-trigger citations required in `docs/v2.5-next-steps.md` at
P0 mint).

**Operator decision:**

- [ ] Accept the **5-cap** reading above (cap-counted 5; exempt 6 per
      Amendment E §"Self-application").
- [ ] Mint a Rule 5 clarification (new amendment) if the reading is
      contested. Specify the contested seed(s) and the proposed
      reclassification:

  Contested seed(s): `_______________`

  Proposed reclassification: `_______________`

## §Seed v2.4-G promotion question

Evidence input: `docs/seed-v2.4-g-cli-timeout-audit.md` (J2 output —
authored in parallel with this prompt mint; verify presence + ground
truth before answering).

Decision-block (operator fills at fire time; options mirror the audit
doc's three dispositions):

- [ ] **FREEZE** — Seed v2.4-G stays 🟡 WATCH; re-evaluate at next
      cycle. No code action.
- [ ] **PROMOTE TO 🔴** — Seed v2.4-G becomes a numbered phase in v2.5
      (P1 candidate if cycle = feature; otherwise queue for next
      feature cycle).
- [ ] **NO-ACTION** — Seed v2.4-G closed without promotion; root-cause
      not actionable OR demand absent.

**Operator pick:** `_______________`

**Disposition rationale (paste from audit doc summary):**
`_______________`

## §Seed v2.4-C deferral/fire decision

Path-D synthetic-fixture P5 implementation (~600 LOC). Bound on
cycle-type per §"Cycle-type call" above.

Decision-block (operator fills at fire time):

- [ ] **FIRE this cycle** — only valid if §"Cycle-type call" =
      feature. Path-D P5 lands as v2.5 P1 (or designated phase).
      Implementation scope per ADR-18 Amendment D §"Acceptance"
      DEFERRED-v2.5 items (bandit `is_ready_for_shadow_v10_1()`,
      train `promotion_gate` envelope additive keys, phase-5 prompt
      re-mint OR new `phase-1-shadow-synthetic.md`, shadow harness
      `--mode=v10.1` suffix, `check_criteria` filter).
- [ ] **DEFER another cycle** — Seed v2.4-C becomes Seed v2.5-C and
      carries to v2.6 P0. Re-evaluate at next cycle frame.

**Operator pick:** `_______________`

**Cycle-coupling guard:** if §"Cycle-type call" = consolidation AND
this section = FIRE, the choices are inconsistent and the operator
must re-open §"Cycle-type call". The skeleton does not auto-resolve;
operator records the resolution.

## §Seed v2.4-Q carry-forward

Re-state (no P0-time decision required; logging only):

- **Disposition:** FREEZE-on-content. Sonnet alignment 0.8261 still
  dipped below 0.95 threshold at v2.4 ship-gate; root cause not yet
  isolated.
- **Watch fires at:** v2.5 P2 (ship-gate finalize). Re-measure
  alignment; if still dipped, FREEZE renews and Seed re-opens as
  Seed v2.5-Q.
- **No P0-time action.** Operator records the carry-forward in
  `docs/v2.5-next-steps.md` §"Carry-forwards" + cap-counted reading
  above (already counted as 1 of 5).

## §v2.4 carry-forward dispositions (quick-ref table)

| Seed | Description | Current disposition | Cap status |
|---|---|---|---|
| v2.4-C | Path-D synthetic-fixture P5 implementation (~600 LOC) | DEFER candidate; FIRE iff cycle=feature | Cap-counted |
| v2.4-E | Overall p95 partial-recovery watch (+4.54s vs v2.2) | WATCH; re-measure at P2 | Cap-counted |
| v2.4-F | Carry-forward seed (per `docs/v2.4-backlog.md`) | WATCH (default carry) | Cap-counted |
| v2.4-G | CLI timeout audit | TBD per §"Seed v2.4-G promotion question" | Cap-counted |
| v2.4-I | INTENT-graduated regression-coverage (promotion-criterion-bound) | EXEMPT per Amendment E | Exempt |
| v2.4-J | INTENT-graduated regression-coverage (promotion-criterion-bound) | EXEMPT per Amendment E | Exempt |
| v2.4-K | INTENT-graduated regression-coverage (promotion-criterion-bound) | EXEMPT per Amendment E | Exempt |
| v2.4-L | INTENT-graduated regression-coverage (promotion-criterion-bound) | EXEMPT per Amendment E | Exempt |
| v2.4-M | INTENT-graduated regression-coverage (promotion-criterion-bound) | EXEMPT per Amendment E | Exempt |
| v2.4-N | Remote-CLI monitoring extension (demand-bound) | EXEMPT per Amendment E | Exempt |
| v2.4-Q | Sonnet-DIP FREEZE-on-content (0.8261 < 0.95) | FREEZE; watch fires at v2.5 P2 | Cap-counted |

**Totals:** Cap-counted = 5 (v2.4-Q + v2.4-C / E / F / G). Exempt = 6
(v2.4-I..N).

Verify against `docs/v2.4-backlog.md` at P0 fire — if backlog status
has drifted (new seed minted post-v2.4 close, or carry-forward
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

## §Phase prompt stubs

Phase prompts to mint after P0 fires (sequencing depends on §"Cycle-
type call" + §"Seed v2.4-C deferral/fire decision"):

- **v2.5 P1** — only if a v2.5-specific implementation phase emerges
  from operator decisions above. Candidates:
  - Path-D synthetic-fixture P5 implementation (fires iff Seed v2.4-C
    = FIRE AND cycle = feature). Prompt name: TBD by operator (e.g.
    `phase-1-shadow-synthetic.md` per ADR-18 Amendment D §"Acceptance"
    DEFERRED-v2.5 row).
  - Seed v2.4-G promotion (fires iff §"Seed v2.4-G promotion question"
    = PROMOTE TO 🔴 AND cycle permits the LOC delta). Prompt name:
    TBD by operator.
  - Other lever-wire candidate (operator may surface a new candidate
    at fire time; not pre-enumerated here).
- **v2.5 P2** — ship-gate finalize. Follows the v2.4 P2 pattern; mint
  prompt ahead-of-fire per the v2.4 P2 precedent (PR #182). Sonnet-
  DIP re-measure (Seed v2.4-Q watch) fires at P2. Amendment E
  regression-check step on `docs/v2.5-next-steps.md` for exempt-seed
  external-trigger citations.

**Skeleton mint scope:** this P0 skeleton does NOT mint P1 or P2
prompts. Subsequent mints happen after P0 fires, per precedent
(PR #182 minted v2.4 P2 ahead-of-fire after v2.4 P0 closed).

## DoD

- [ ] Branch opened from `main` at `08eb71d` or later (verify SHA at
      fire time).
- [ ] Memory pre-flight stamp in PR body (Amendment B §"Required
      output"; self-applies to this P0 PR).
- [ ] `docs/v2.5-next-steps.md` drafted alongside this frame (mirrors
      `docs/v2.4-next-steps.md` pattern); includes verbatim
      external-trigger citations for every Amendment E exempt seed
      (v2.4-I..N).
- [ ] All operator decisions from §"Cycle-type call", §"Rule 5 cap-
      counted reading", §"Seed v2.4-G promotion question", §"Seed
      v2.4-C deferral/fire decision" recorded in `docs/v2.5-task-
      plan.md` (mint at P0).
- [ ] §"v2.4 carry-forward dispositions" table reconciled against
      `docs/v2.4-backlog.md` ground truth at P0 fire.
- [ ] If cycle = feature: explicit lever-wire commitment recorded
      (Path-D P5 if Seed v2.4-C fires; otherwise operator records
      alternative lever-wire candidate).
- [ ] If cycle = consolidation: deletion-offset survey ≥ 0 LOC net
      vs P0-merge tip (per ADR-18 Amendment C cycle-tip anchor).
- [ ] Cycle-tip LOC anchor cited verbatim in `docs/v2.5-task-plan.md`
      using `<v2.5 P0-merge SHA>..HEAD` template (per Amendment C).
- [ ] Seed v2.4-Q carry-forward logged in `docs/v2.5-next-steps.md`
      §"Carry-forwards" with FREEZE-on-content note + v2.5 P2 watch
      trigger.

## Refs

- `docs/prompts/v2.4-orchestration/phase-0-cycle-frame.md` —
  structural anchor for this skeleton; preserve section headings,
  decision-block style, DoD shape.
- `docs/v2.4-next-steps.md` — predecessor next-steps doc; v2.5
  next-steps must mirror its shape + carry forward Amendment E
  external-trigger citations.
- `docs/v2.4-backlog.md` — backlog ground-truth at v2.4 close;
  reconcile §"v2.4 carry-forward dispositions" table against this
  file at P0 fire.
- `docs/seed-v2.4-g-cli-timeout-audit.md` — J2 output (being authored
  in parallel with this prompt mint); evidence input for §"Seed
  v2.4-G promotion question".
- `docs/adr/ADR-18-mvp-surface-freeze.md` — Amendments A / B / C / D
  / E + Rules 1–6.
- `project_v24_cycle_close.md` — v2.4.0 close-out facts.
- `feedback_certportal_dev_firewall.md` — SM dev firewall against
  `C:\Users\SeanHoppe\VS\certPortal\`.
- `feedback_no_self_monitor.md` — polarity-flip rule.
- `feedback_glob_narrowing_no_op.md` — PR #184 cassette on filename-
  pattern guess failure.
- `feedback_cycle_tolerance_masks_bugs.md` — cycle-type tolerance can
  mask helper bugs.
- Precedent ahead-of-fire prompt mints: PR #182 (v2.4 P2 ship-gate
  finalize), PR #181 (Sonnet-DIP investigation).
