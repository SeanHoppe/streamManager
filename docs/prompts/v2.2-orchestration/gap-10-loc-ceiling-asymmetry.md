# Gap 10 — Feature-cycle LOC ceiling carry-forward asymmetry (bookkeeping)

> Minted from `docs/intent-todo-gap-2026-05-16.md` §Gap 10. Bookkeeping
> drift. Refresh at v2.2 P0 INTENT pre-flight pass per ADR-18 Rule 6
> (#133).

## Why

INTENT.md §"Current cycle posture" lists 4 v2.2 carry-forwards:

1. dormant `JsonlTailWorker.start()` production wiring
2. soak-summary probe-emit counter
3. Sonnet 0.95 → 0.8636 alignment dip (🟡)
4. feature-cycle LOC ceiling

todo.md folds #4 (LOC ceiling) into #130 ADR-18 amendment, paired
with the cycle-gate item. **Tracking is correct, just asymmetric**
between INTENT (4-bullet list) and todo (3-bullet list + paired
into cycle-gate). One source of truth, two presentations.

## Action (operator decision at P0 mint — record either A or B)

### Option A — Re-add feature-cycle LOC ceiling as its own todo row

Add a fourth bullet to todo.md §"Carry-forwards from v2.1":

```
- [ ] **Feature-cycle LOC ceiling.** Tracked at #130; paired with
      v2.2 P0 cycle-gate item. ADR-18 Amendment A in v2.2 P0 PR
      body.
```

Result: INTENT and todo both show 4 bullets; symmetry restored.

### Option B — Trim the INTENT bullet to pointer

Edit INTENT.md §"Current cycle posture" v2.x main cycle paragraph:

```
... feature-cycle LOC ceiling.
```

becomes:

```
... feature-cycle LOC ceiling (see #130).
```

Result: INTENT presents 3 carry-forwards + 1 pointer; todo also 3
+ paired-into-cycle-gate; symmetry restored via cross-link.

## Recommended option

**Option B** — pointer to #130 is leaner; LOC ceiling is itself
the ADR-18 Amendment A subject, which is structurally a cycle-gate
artifact, not a carry-forward feature item. Promoting it to a
top-level carry-forward list inflates the slate. Operator confirms
at P0.

## Cross-refs

- INTENT.md §"Current cycle posture" — line subject to edit.
- todo.md §"Non-v10 (v2.x main cycle)" §"🟡 Carry-forwards" —
  destination if Option A.
- ADR-18 Amendment A in v2.2 P0 phase-0 prompt — the actual closure
  for feature-cycle LOC ceiling work.
- Issue #130 — ADR-18 Rule 3 LOC ceiling.
- ADR-18 Rule 6 (#133) — INTENT-refresh pass at cycle frame.
- Gap doc §"Gap 10 — Feature-cycle LOC ceiling carry-forward
  asymmetry".

## DOD (at v2.2 P0 INTENT-refresh pass)

- [ ] Operator picks A or B; records choice in P0 PR body.
- [ ] Edit applied to INTENT.md (Option B) OR todo.md (Option A) —
      not both.
- [ ] Gap doc §Gap 10 marked LANDED.

## ADR-18 posture

- Pure documentation. Zero src / test touch. No FROZEN surface.
- No LOC count of consequence.
- No DORMANT-N implication.
