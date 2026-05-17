# Gap 4 — API-timeout invariant test (v2.2 P0 phase candidate)

> **LANDED v2.2.0 ship-gate.** P1 PR #168 (`2b4f1b3`) shipped the
> invariant test + Tier-3 invariant-degrade canary; v2.2.0 ship-gate
> soak PASS with canary degrade_count=0 confirmed the canary wire.
> **Disposition 2026-05-16 at v2.2 P0 mint: FOLDED v2.2 P1.**
> v2.2 = consolidation cycle; gap-4 P1 requires mandatory pre-P1
> deletion offset survey ≥ 80 LOC to keep cycle net LOC ≤ 0.
> See `docs/prompts/v2.2-orchestration/phase-1-gap-4-api-timeout-
> invariant.md` for the P1 phase prompt.
>
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
  - **Preferred patch target:** monkey-patch
    `src.stream_manager.cli_governance.CliWorker.send` (or the
    equivalent worker-pool method actually invoked from the
    evaluate seam — grep at promotion to confirm symbol name). The
    worker-pool layer is the deterministic injection site; patching
    bare `subprocess.Popen` is brittle under `CliPool` worker reuse
    per `feedback_soak_cli_pool_flag.md` (v1.0 cold-start regression
    precedent).
  - Fallback if pool semantics still bite: inject a sentinel CLI
    binary path that hangs indefinitely (set via
    `BRIDGE_CLI_PATH` env or pool-config injection at fixture
    setup).
- Simulate API 500 / 502 / 503 fault via similar shim returning
  non-zero exit with stderr error payload.
- Assert two invariants for both fault classes:
  1. Final governance verdict = `OBSERVE` (NOT `INTERVENE`,
     `BLOCK`, or unset).
  2. Bridge forward latency from message-in → forward-out <
     `BRIDGE_FALLBACK_LATENCY_BUDGET_MS`. **Pin the threshold at
     promotion** to the live constant in `governance.py` or
     `model_router.py` (grep at promotion-time; ADR-5 latency
     baseline as of v1.7 cycle-close is ~11s p95, NOT 2 s). Do
     NOT hard-code a literal ms value in this test — fetch from
     the runtime constant so future ADR-5 re-baselines propagate
     automatically. If no such constant exists yet, mint one at
     P-N as part of the deliverable.

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
- ADR-5 latency baseline (~11s p95 per `project_v17_cycle_close.md`).
  `BRIDGE_FALLBACK_LATENCY_BUDGET_MS` resolves to live constant in
  `governance.py` / `model_router.py` at test runtime — do NOT hard-
  code.
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
- LOC estimate: ~70 tests + ~10 driver = ~80 LOC. Negligible vs
  either cycle budget. **Deletion-offset target in
  `phase-1-gap-4-api-timeout-invariant.md` rounds to ≥ 80 LOC**
  to give P1 a single integer threshold (do not split-hair between
  70 vs 80 at P1 review).
- No DORMANT-N implication.
