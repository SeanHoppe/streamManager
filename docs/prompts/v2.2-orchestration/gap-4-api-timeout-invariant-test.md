# Gap 4 — API-timeout invariant test (v2.2 P0 phase candidate)

> Minted from `docs/intent-todo-gap-2026-05-16.md` §Gap 4. **Either
> cycle type acceptable** — pure additive test + Tier-3 ledger
> column extension. ADR-18-clean.

## Why

INTENT.md safety priority #5 (verbatim): "API timeouts must never
block forwarding. A governance API failure degrades to OBSERVE; it
does not stall the bridge."

todo.md tracks zero regression test for this invariant. v2.x
refactors (worker pool tuning, model router, CLI subprocess wrap)
could silently break the OBSERVE-degrade contract; no canary
catches it pre-ship.

## Deliverable shape (1 test + 1 Tier-3 ledger column)

### 1. Regression test

`tests/test_api_timeout_invariant.py`:

- Simulate `claude -p` subprocess timeout via fake CLI shim that
  blocks > timeout-fallback budget.
  - Strategy: patch `cli_governance` subprocess.Popen to return a
    fake that sleeps past timeout, OR inject a sentinel CLI binary
    path that hangs indefinitely.
- Simulate API 500 / 502 / 503 fault via similar shim returning
  non-zero exit with stderr error payload.
- Assert two invariants for both fault classes:
  1. Final governance verdict = `OBSERVE` (NOT `INTERVENE`,
     `BLOCK`, or unset).
  2. Bridge forward latency from message-in → forward-out <
     `BRIDGE_FALLBACK_LATENCY_BUDGET_MS` (default 2000 ms or
     whatever ADR-5 latency baseline declares; pull from
     `model_router` or `governance` constants).

### 2. Tier-3 ship-gate ledger extension

Ship-gate ledger currently has two columns: latency, alignment.
Add third column **invariant-degrade**:

- Boolean per Tier-3 soak run: did any synthetic timeout fixture
  fire AND produce a non-OBSERVE verdict? → BLOCK ship.
- Implementation site: wherever ship-gate report is rendered
  (likely `tools/soak_driver.py` summary block or
  `docs/SHIP_GATE.md` table).
- Surface: one new line in soak-summary closing print
  `[soak] invariant-degrade canary: PASS/FAIL`.

## Cross-refs

- INTENT safety priority #5 verbatim.
- ADR-5 latency baseline (cross-ref for `BRIDGE_FALLBACK_LATENCY_
  BUDGET_MS` value).
- `src/stream_manager/cli_governance.py` — fault injection site.
- `tools/soak_driver.py` — Tier-3 ledger render site.
- Gap doc §"Gap 4 — API-timeout invariant test".

## Promotion criterion

Either cycle type — pure additive test + observability line. Trivial
LOC impact.

## DOD

- [ ] `tests/test_api_timeout_invariant.py` covers timeout-path AND
      API-500-path; both assert OBSERVE + bounded latency.
- [ ] `tools/soak_driver.py` soak-summary extended with
      invariant-degrade canary line.
- [ ] Ship-gate ledger table (wherever rendered) extended with
      invariant-degrade column.
- [ ] One real Tier-3 soak run shows new canary PASS in summary.
- [ ] Gap doc §Gap 4 LANDED.

## ADR-18 posture

- Test-only + one additive observability line. Zero FROZEN surface
  touched. EXPERIMENTAL on land.
- LOC estimate: ~60 tests + ~10 driver = ~70 LOC. Negligible vs
  either cycle budget.
- No DORMANT-N implication.
