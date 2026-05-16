# Gap 1 — Cadence enforcement FR (v2.2 P0 phase candidate)

> Minted from `docs/intent-todo-gap-2026-05-16.md` §Gap 1. **TWO gates**
> before promotion: (a) v2.2 cycle type = **feature** AND (b) ADR-18
> Rule 1 carve-out for FROZEN `governance.py` evaluate seam. Operator
> records both decisions at P0. If v2.2 = consolidation, defer to v2.3.
> Same seam as gap-2; carve-out wording should be shared verbatim.

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
- Counts as a wired lever per ADR-18 Rule 2; record at cycle
  close. **Do NOT assert a numeric `WIRED_LEVER_LEDGER_COUNT`
  delta here** — gap-11 is the canonical inventory site (see
  §"ADR-18 posture" below).

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

## Promotion criteria (BOTH must hold)

1. Operator confirms v2.2 cycle type = **feature**.
2. Operator records ADR-18 Rule 1 carve-out for `governance.py`
   evaluate-seam touch at P0 PR body (same seam as gap-2 — shared
   carve-out wording recommended). "Additive call site ≠ FROZEN
   break" is NOT auto-policy; each prompt that touches the seam
   requires its own explicit operator OK until/unless codified in
   ADR-18 as a general rule.

## DOD

- [ ] One or more `FR-cadence-N` rows in `docs/REQUIREMENTS.md`.
- [ ] `cadence_detector.py` module added + wired advisory-only.
- [ ] `tests/test_cadence_detector.py` covering positive + negative
      fixture.
- [ ] ADR-18 Rule 1 carve-out text in v2.2 P0 PR body verbatim
      (shared with gap-2 if both promote).
- [ ] Memory note: `project_v22_cadence_detector.md` (or fold into
      v2.2 cycle-close memory) — declare detector DORMANT-1.
- [ ] Cycle-close LOC ledger column updated for this phase.
- [ ] Gap-tracking doc `docs/intent-todo-gap-2026-05-16.md` §Gap 1
      marked LANDED (or doc deleted entirely if gaps 1–4 all close).

## ADR-18 posture

- New surface: `cadence_detector.py` EXPERIMENTAL on land; ratchet
  to EVOLVING after one falsify cycle.
- Touches FROZEN `governance.py` evaluate seam. **Hard gate** —
  operator must carve out at P0 explicitly. No silent FROZEN edit.
- Lever-bump delta recorded at P0 per gap-11 (canonical inventory
  site). This prompt does NOT assert a numeric counter delta — see
  gap-11 for the single source of truth.
- LOC estimate: ~80 src + ~100 tests = ~180 LOC. Counts against
  feature-cycle LOC soft target per ADR-18 Amendment A (#130,
  queued — soft target value TBD at P0 mint).
