# 2026-05-22 — velocity-gauge running notes

> **Purpose:** Captures interpretive decisions, deviations, tradeoffs, and
> open questions for `docs/2026-05-22-status.md`. Spec source = `/goal`
> directive from this session + repo state at 2026-05-22 ~05:30Z (post
> overnight Tier-3 soak `reports/soak-20260521T235321Z.md`).
>
> **Lifetime:** Discardable once operator acks the status doc.

---

## Design decisions (spec-ambiguous spots)

### DD-1 — "today" boundary

Goal references "where did things land today". Today's date per
`currentDate` is **2026-05-21**, but the latest soak finished at
**2026-05-22T05:04:57Z** and the status doc filename is dated
**2026-05-22**. Interpretation: "today" = the 24h window
**2026-05-21T00:00Z → 2026-05-22T06:00Z UTC** (covers both calendar days
that the operator's local PM-to-AM session spans). Anchored against
`git log --since="2026-05-21 00:00"` (8 merge commits PR #199 → #206).

### DD-2 — "MVP 100%" anchor

Goal phrases "MVP 100%" without naming which artefact bounds it. There
are two live MVP scopes in this repo:

1. **v10 RL companion-track MVP** — `docs/v10-mvp-status.md` is the
   authoritative ledger (last refresh 2026-05-21 at corpus 608 episodes
   / Phase 4 ✅ / Phase 5 🔒 / aggregate ~80%).
2. **v1.x/v2.x main-cycle MVP** — implicit. No single percentage anchor;
   completeness is encoded as cycle-after-cycle ADR-18-disciplined
   shipping with WIRED_LEVER_LEDGER + alignment-eval pass-rate floor +
   Tier-3 soak gates.

Status doc treats `v10-mvp-status.md` as primary MVP-100% anchor and
narrates v2.x main-cycle progress as the production-runtime delivery
vehicle that the v10 track piggybacks on.

### DD-3 — "today's jobs"

Task-list `docs/2026-05-21-task-list.md` minted 4 agent-dispatchable jobs
(J1–J4) + 9 operator-bound items (O1–O9). Per
`docs/2026-05-21-implementation-notes.md` §"Landing log", **all 4 J-jobs
landed first-try** on 2026-05-21 (PM-mint session). Status doc reports
those as DONE and tracks O1–O9 disposition through today's 8 PR merges.

### DD-4 — velocity gauge unit

No spec for the unit. Picked **cycles-per-MVP-quanta** combined with
**deferral pressure** as the gauge dimensions:

- **Cycle cadence** (calendar days between v2.x P2 / P3 ship-gates).
- **Lever-wire rate** (production-bucket WIRED_LEVER_LEDGER bumps per
  cycle).
- **Held-chain depth** (head-of-chain seed + deferral count).
- **Floor margin** (Sonnet pass-rate vs FR-OG-7 floor 0.80).

These dimensions are pre-existing in the project — see
`docs/v10-mvp-status.md` §4 + `project_v26_cycle_close.md` for shape. New
synthesis = projecting time-to-MVP-100 from current rates.

---

## Deviations

### DV-1 — Status doc treats P3 as IN-FLIGHT, not LANDED

Goal asks for today's landing. v2.7 P3 ship-gate has not yet merged at
read-time (only 7 of 8 v2.7 PRs landed; P3 PR is open as the working-tree
edits on `ship/v2.7-p3-ship-gate`). Status doc records P3 as **OPEN /
PRE-FIRE** with the in-flight soak as the gating evidence.

### DV-2 — Latest soak flagged but not adjudicated

`reports/soak-20260521T235321Z.md` reads **Verdict: PASS** at the
top-level invariants (`degrade_count=0`, RSS+0.63 MB, no exceptions),
**but** the latency block shows `LM p95 = 5593.95 s` and lever ledger
`0 wired levers — DORMANT-N gate inert`. Status doc surfaces both as
concerns but does NOT call BLOCK — the operator decides at P3 fire-PR.
Reasoning: status doc is a snapshot, not a ship-gate disposition; calling
BLOCK pre-empts the operator's S4 alignment-eval + S5 LOC delta + S6
ledger reconciliation evidence.

### DV-3 — Discards a clean "X% to 100%" formula

Goal asks for a velocity gauge. The honest read of the project's gating
structure is that **percentage completion is not the load-bearing
metric** — ADR-18 surface-freeze + Rule 5 cap + Amendment-D split mean
the chain is held by a specific seed (v2.6-C Path-D P5) and a specific
classification freeze (`model_router.route`). Gauge instead reports
**"cycles to v10 P5 land"** + **"cycles to first FROZEN-surface
reclassification"** + **"cycles to ship criteria PASS × 3"** as the
load-bearing schedule estimators.

---

## Tradeoffs

### TR-1 — Detail level for REVIEW1 vs REVIEW2 vs velocity

Considered:

- **Heavy per-PR walk for REVIEW1** (verbose; reads like changelog).
- **One-paragraph compressed REVIEW1** (loses the artefact pointers).

Picked **table + one-line annotation per PR** for REVIEW1 — every PR
linkable + the artefact it landed visible at a glance.

REVIEW2 + velocity get prose because the analysis is judgment-dense
(held-chain depth, falsification of J2 audit, cap-clip artefact); a table
would force false precision.

### TR-2 — Whether to include latest soak failure modes

Considered burying the LM p95 = 5593 s reading under "open follow-ups"
to keep status optimistic. Rejected — the soak just finished 25 min
before status-doc write; operator opens P3 fire-PR within hours and
needs the signal in the top half of the doc. Surface in REVIEW1 §"Latest
Tier-3 soak" inline, repeat in velocity §"Risks to schedule".

### TR-3 — Velocity gauge: optimistic vs nominal vs pessimistic bands

Picked **3-band projection** (best / nominal / worst) anchored against
cycle cadence v2.4 → v2.5 → v2.5.1 → v2.6 → v2.7. Single-point estimate
would over-promise; 3-band makes the operator's deferral-cost calculus
visible (each Seed v2.6-C defer adds ≥ 1 cycle to v10 P5 landing).

---

## Open questions

### OQ-1 — What does `Lever ledger: 0 wired levers — DORMANT-N gate inert` actually mean?

Soak driver emits this line; the v2.7 task-plan + close memory both
claim WIRED_LEVER_LEDGER = 3 production after PR #203. Either:

- The soak-side ledger reads a different counter than the docs-side
  ledger (separate accounting paths), OR
- The soak driver's lever-detection isn't picking up the freshly-wired
  Seed v2.6-G step (2) cap-tighten lever (PR #203 merged `28a89c4`).

Status doc flags this as **OQ-1** and notes that S6 of the P3 ship-gate
must reconcile or BLOCK. **Not** a status-doc-side bug to fix.

### OQ-2 — Does the LM p95 = 5593.95 s reading have a root cause known to the operator?

The soak completed at 05:04Z (25 min before status-doc write). No
post-soak triage notes exist in working tree. Status doc reports the
reading verbatim and asks operator at P3 fire whether this is a known
flake, an instrumentation artefact (e.g. dashboard log buffering pulling
one stale entry), or a real regression. Pre-cap (v2.6 P2) LM p95 was
12.64 s; +5581 s would be a 444× regression — implausible as a real
prod-path measurement; almost certainly a single stalled CLI dispatch
that was not killed. Flagged as **OQ-2**.

### OQ-3 — Velocity gauge horizon

How far should the velocity gauge project? Picked 6 cycles forward
(through v3.3) as the projection window — past 6 cycles the cap-clip
artefact + ADR-18 reclassification timing become too uncertain. Operator
may want a longer horizon for a quarterly business view; if so, gauge
section needs a "beyond v3.3" caveat block (not in current draft).

### OQ-4 — Does PR #154 (Robin self-vs-other docs DRAFT) affect velocity?

It's been open as DRAFT since 2026-05-12 (9 days). Status doc treats it
as **non-blocking** for v10 P5 / main-cycle MVP — it's a Robin-agent
hygiene doc, not a held-chain dependency. Operator may disagree; flagged
in §"Operator queue".

---

## Refs

- `docs/2026-05-21-task-list.md` — predecessor task list (4 J-jobs).
- `docs/2026-05-21-implementation-notes.md` — yesterday's notes
  (aspirational shape for this doc).
- `docs/2026-05-22-status.md` — primary deliverable.
- `docs/v10-mvp-status.md` — v10 MVP anchor (DD-2).
- `docs/v2.7-task-plan.md` + `docs/v2.7-next-steps.md` — v2.7 fire ledger.
- `reports/soak-20260521T235321Z.md` — overnight Tier-3 soak (DV-2, OQ-1,
  OQ-2).
- `project_v26_cycle_close.md` — v2.6 baseline (Sonnet 0.9412, LM 12.64s).
