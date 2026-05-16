# Gap 11 — WIRED_LEVER_LEDGER_COUNT surface (bookkeeping conditional watch)

> Minted from `docs/intent-todo-gap-2026-05-16.md` §Gap 11. Bookkeeping
> drift, **conditional** — only fires if v2.2 wires a new lever
> (counter bumps 0 → ≥ 1).

## Why

INTENT.md §"ADR-18 governance regime" records:

> `WIRED_LEVER_LEDGER_COUNT` = 0; DORMANT-N gate inert.

This is a **plan-alignment surface** — it tells future cycles
whether DORMANT-N falsify-before-extend pressure applies. todo.md
does NOT carry a plan-alignment-watch row reflecting this state.

If v2.2 wires a lever (e.g. gap-1 cadence detector OR gap-2
escalation hook), counter bumps `0 → ≥1` and the DORMANT-N gate
becomes live. todo should flag the bump so a future cycle does NOT
forget to falsify within ≤ 2 cycles.

## Action (conditional — only fires if counter bumps)

### Step 1 — Mint check at v2.2 P0

At cycle frame fire, evaluate planned P1–P4 deliverables. Count
new wired levers:

- Gap-1 cadence detector wired advisory-only: counts as 1 (DORMANT-1
  by INTENT, but already adds to wired-lever ledger).
- Gap-2 escalation hook wired active: counts as 1.
- Other new levers? Inventory at P0.

If `delta_lever_count > 0`: trigger Step 2.
If `delta_lever_count == 0`: no-op; gap doc §Gap 11 marks NO-OP
LANDED.

### Step 2 — Add watch row to todo §"Sticking points"

Append one line under todo.md §"Sticking points / blockers":

```
N. **WIRED_LEVER_LEDGER_COUNT bumped 0 → K at v2.2.** DORMANT-N
   gate now live. Falsify or extend evidence before v2.4 P0 mint
   (≤ 2 cycle horizon per ADR-18 Rule 2).
```

Where `K` = new counter value, `N` = next sticking-point ordinal.

### Step 3 — Update INTENT.md counter line

INTENT.md §"ADR-18 governance regime":

```
- `WIRED_LEVER_LEDGER_COUNT` = 0; DORMANT-N gate inert.
```

becomes:

```
- `WIRED_LEVER_LEDGER_COUNT` = K; DORMANT-N gate LIVE — falsify by
  v2.4 P0.
```

## Cross-refs

- INTENT §"ADR-18 governance regime" — counter line.
- ADR-18 Rule 2 — DORMANT-N falsify-before-extend cumulative
  semantics.
- Gap doc §"Gap 11 — `WIRED_LEVER_LEDGER_COUNT` = 0 surface".
- Companion: gap-1 + gap-2 prompts (potential lever-bump sources).

## DOD (at v2.2 P0 mint)

- [ ] Lever-count delta inventoried at P0.
- [ ] If delta > 0: Step 2 + Step 3 applied in same PR as P0 cycle
      frame.
- [ ] If delta = 0: documented as no-op in P0 PR body.
- [ ] Gap doc §Gap 11 LANDED (either path).

## ADR-18 posture

- Pure documentation. Plan-alignment-watch surface.
- Zero LOC src/test impact.
- Conditional on lever wiring decisions in P0.
