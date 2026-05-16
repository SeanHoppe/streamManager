# Gap 1 — Cadence enforcement FR (v2.2 P0 phase candidate)

> Minted from `docs/intent-todo-gap-2026-05-16.md` §Gap 1. Promotion-
> gated on operator declaring v2.2 cycle type = **feature**. If v2.2
> = consolidation, defer to v2.3.

## Why

INTENT.md §"Safety priorities" frame: "SM enforces two things beyond
raw safety: plan alignment and cadence (is the session making forward
progress?)." Plan-alignment has at least one regression-watch row
(PR #161 Sonnet dip audit). **Cadence has zero coverage** — no FR,
no detector, no test, no watch. Any v2.x regression to forward-progress
signalling lands silent.

## Phase shape (3 deliverables — additive)

### 1. FR-cadence-N requirement

Add one or more `FR-cadence-N` rows to `docs/REQUIREMENTS.md`
defining what "forward progress" means. Candidate signals (pick one
or compose):

- Monotone-decreasing open-item count across rolling window.
- Monotone-increasing closed-PR count across rolling window.
- Assistant-turn novelty score (cosine drop of message-embedding
  centroid vs prior N turns) — flags loop-stuck sessions.

Operator at P0 picks one signal definition before P-N opens. Record
the chosen signal definition verbatim in FR row body.

### 2. Detector wired advisory-only

Wire detector into `governance.evaluate` path **advisory-only**
(consistent with ADR-18 Rule 2 — first wiring counts as DORMANT-1;
must falsify-before-extend at next cycle if not promoted).

- New module: `src/stream_manager/cadence_detector.py` (~50–80 LOC).
- Wired at evaluate seam; emits `governance_signal` envelope with
  `kind="cadence_warning"` (NOT a verdict modifier).
- `WIRED_LEVER_LEDGER_COUNT`: 0 → 1 (this counts as a wired lever
  per ADR-18 Rule 2; record at cycle close).

### 3. Regression test

`tests/test_cadence_detector.py`:

- Fixture session = synth N-turn JSONL with no forward progress
  (e.g. assistant repeats same message body 5× consecutive). Assert
  detector fires `cadence_warning`.
- Negative fixture: assistant turns show novelty / open-item count
  decreases. Assert detector silent.

## Cross-refs

- INTENT §"Safety priorities" frame line.
- `docs/REQUIREMENTS.md` — destination for FR-cadence-N rows.
- ADR-18 Rule 2 (DORMANT-N falsify-before-extend) — wiring policy.
- Gap doc §"Gap 1 — Cadence enforcement FR".
- Companion advisory-only precedent: `cli_governance.py` verdict path.

## Promotion criterion (re-stated)

Operator confirms v2.2 cycle type = **feature** at P0 fire. If
consolidation, this prompt sleeps until v2.3 P0.

## DOD

- [ ] One or more `FR-cadence-N` rows in `docs/REQUIREMENTS.md`.
- [ ] `cadence_detector.py` module added + wired advisory-only.
- [ ] `tests/test_cadence_detector.py` covering positive + negative
      fixture.
- [ ] Memory note: `project_v22_cadence_detector.md` (or fold into
      v2.2 cycle-close memory) — declare detector DORMANT-1.
- [ ] Cycle-close LOC ledger column updated for this phase.
- [ ] Gap-tracking doc `docs/intent-todo-gap-2026-05-16.md` §Gap 1
      marked LANDED (or doc deleted entirely if gaps 1–4 all close).

## ADR-18 posture

- New surface: `cadence_detector.py` EXPERIMENTAL on land; ratchet
  to EVOLVING after one falsify cycle.
- Touches FROZEN `governance.py` evaluate seam — additive call site,
  not behavioral modification on existing verdicts. Operator records
  Rule 1 disposition at P0 (additive call ≠ FROZEN break per
  precedent set in v2.0 P1 cli_pool A/B).
- LOC estimate: ~80 src + ~100 tests = ~180 LOC. Counts against
  feature-cycle LOC budget per Amendment A (#130).
