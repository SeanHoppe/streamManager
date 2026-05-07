You are implementing **Phase P3 — Haiku fastpath disposition + conditional fallback rip** for the streamManager v2.0 cycle.

## Branch + base

- Base: `main` (after v2.0 P1 is merged — P3 cannot start until P1's
  fire-rate outcome is known).
- PR target: `main`.
- Branch: `feat/v2-p3-fastpath-rip` (or operator's choice).
- If `reports/v2-p1-cli-pool-ab-*.md` does not exist on `main`, ABORT
  and complete P1 first.

## Context (load-bearing)

ADR-18 Rule 2 mandates rip-or-revive at DORMANT-3. Two levers in scope:

1. **Haiku fastpath router** — DORMANT-3 entering v2.0 (wired in v1.7
   P2; `is_ambiguous_block` / `is_hitl_synthesis` flags are computed
   in `governance._evaluate_inner_core` but the pre-CLI dispatch site
   never reads them). Rips unconditionally in P3.
2. **Confidence + verdict-based fallback** — DORMANT-2 entering
   v2.0; v2.0 P1 outcome is the third soak that determines DORMANT-3
   status. **Branching:**
   - P1 produced > 0% fire rate at any arm → fallback revived,
     counter resets, P3 keeps fallback path.
   - P1 produced 0% fire rate at all four arms → fallback joins
     DORMANT-3, P3 rips it.

Read `reports/v2-p1-cli-pool-ab-<timestamp>.md` first. Choose Branch
A or Branch B based on the report's binding fire-rate outcome.

## References

- `docs/adr/ADR-18-mvp-surface-freeze.md` Rule 2 + lever ledger
- `reports/v2-p1-cli-pool-ab-<timestamp>.md` — REQUIRED INPUT
- `src/stream_manager/governance.py` — `_evaluate_inner_core`;
  pre-CLI dispatch site (Haiku fastpath consumer)
- `src/stream_manager/cli_governance.py` — fallback retry path
- `src/stream_manager/model_router.py` — `RoutingDecision.fallback_model_id`
- `src/stream_manager/cli_pool.py` — UNCHANGED in P3
- `docs/adr/ADR-5-latency-budget.md` — lever-effect ledger
- v1.7 / v1.8 / v1.9 task plan do-not-touch lists — search-and-update
  references in any active doc

## Do-not-touch guard

ADR-18 Rule 2 grants rip authority for DORMANT-3 levers. Specific
allowances:

- **Haiku fastpath rip (always in P3)**: delete the unread `route()`
  kwarg consumer at the pre-CLI dispatch site. Content-detection
  helpers (`_looks_ambiguous_block`, `is_ambiguous_block` /
  `is_hitl_synthesis` flag computation) STAY — they're FROZEN per
  v1.8 P1 and may be reused by future work; only the unread route()-
  kwarg consumer disappears.
- **Fallback rip (Branch B only)**: delete `cli_governance.py` retry
  trigger logic, `BRIDGE_L4_FALLBACK_*` constants, fallback envelope
  emission, `cli_dispatch_fallback_ms` instrumentation key. The
  envelope **schemas** stay (append-only); just stop emitting.

The `cli_dispatch_fallback_ms` removal is the FIRST removal from
`engine._last_phase_timings_ms`. ADR-18 Rule 1 makes this dict FROZEN.
Removing the key requires explicit ADR-18 amendment authorising
subtractive change to a FROZEN list. Add the amendment in the same
PR.

`cli_pool` UNCHANGED. Bus envelope schemas UNCHANGED (no removals).
`model_router.RoutingDecision.fallback_model_id` deletes ONLY if no
caller reads it after fastpath rip — grep all callers before deleting.

## Scope

### Step 0: read v2.0 P1 report; choose branch

Open `reports/v2-p1-cli-pool-ab-<timestamp>.md`. Cite the fire-rate
outcome in your PR description.

- Any arm > 0% → Branch A (Haiku fastpath rip only).
- All arms 0% → Branch B (both rips).

### Branch A — Haiku fastpath rip only

1. **Delete the unread fastpath consumer** at the pre-CLI dispatch
   site in `governance._evaluate_inner_core` (or the file the v1.7 P2
   PR touched — grep for `is_ambiguous_block=` and
   `is_hitl_synthesis=` kwargs at `route()` call sites).
2. **`RoutingDecision.fallback_model_id`** — grep all callers across
   `src/`, `tests/`, `tools/`. If only the ripped consumer reads it,
   delete the field. If anything else reads it, keep it.
3. **Tests**: remove tests that exercise the fastpath consumer ONLY
   (search `tests/test_routing*.py`, `tests/test_governance*.py` for
   `is_ambiguous_block` / `fastpath` references). Keep tests for the
   content-detection helpers themselves.
4. **ADR-18 §"Initial classification"**: move the Haiku fastpath row
   from "FROZEN" to a new §"Decommissioned" subsection with rip-date
   + rip-PR.
5. **ADR-5 lever-effect ledger**: append v2.0 P3 entry — Haiku
   fastpath ripped at v2.0 P3 (DORMANT-3 trigger). Fallback retained
   (P1 revival).
6. **Search-and-update** v1.7 / v1.8 / v1.9 task plan do-not-touch
   references that name `is_ambiguous_block` route()-kwarg consumer
   — annotate as "ripped at v2.0 P3" rather than deleting the rows
   (preserves history).
7. **Net deletion target**: 150-200 LOC.

### Branch B — Haiku fastpath rip + fallback rip

Everything in Branch A, PLUS:

1. **`cli_governance.py`** — delete:
   - Verdict-based retry trigger branch (v1.9 P1)
   - Confidence-floor retry trigger branch (v1.7 P2)
   - `_fallback_confidence_floor()` helper
   - `BRIDGE_L4_FALLBACK_CONFIDENCE`, `BRIDGE_L4_FALLBACK_MODE` env
     constants
   - Fallback envelope emission sites (`governance_fallback_routed`,
     `governance_envelope_missing_confidence`)
2. **`engine._last_phase_timings_ms`** — remove `cli_dispatch_fallback_ms`
   key. Update `tools/soak_driver.py` `_ALLOW_PHASE_ORDER` if it
   includes the key.
3. **ADR-18 amendment** (in same PR): authorise subtractive change to
   `_last_phase_timings_ms` for `cli_dispatch_fallback_ms`. Document
   the precedent: subtractive timing-key change is allowed ONLY for
   ripped DORMANT-3 levers; never for active levers.
4. **Bus envelope schemas** — keep on disk (append-only). Stop
   emitting in code.
5. **Tests** — remove fallback-specific tests
   (`tests/test_governance_fallback_routing.py` if dedicated; partial
   in shared files).
6. **ADR-18 §"Decommissioned"** — add fallback row.
7. **ADR-5 lever-effect ledger** — append v2.0 P3 entry; record
   warm-process hypothesis falsification.
8. **Net deletion target**: 300-400 LOC.

## DOD

- [ ] Branch chosen based on `reports/v2-p1-cli-pool-ab-<timestamp>.md`
      fire-rate outcome (cite report in PR description)
- [ ] Ripped symbols removed from code + tests (no orphan references;
      `git grep` clean for ripped names)
- [ ] ADR-18 §"Decommissioned" updated with rip rows
- [ ] ADR-5 lever-effect ledger updated
- [ ] (Branch B only) ADR-18 amendment for subtractive timing-key
      change
- [ ] Net LOC delta strongly negative (-150 minimum, -300 expected
      Branch B)
- [ ] Alignment-eval `--ci-gate` exit 0 (rips must not regress
      alignment): sonnet ≥ 0.95, haiku ≥ 0.85, 0 FR-OG-7 regressions,
      0 haiku regressions vs sonnet
- [ ] Tier 1.5 smoke soak passes (per ADR-17 amendment from P2 if
      merged; else operator-driven Tier 3 on a feature branch is
      acceptable)
- [ ] No FROZEN-list non-additive change without explicit ADR-18
      amendment

## Mint-new-phase rule

If during rip a third dormant lever surfaces (i.e. some other
v1.x-wired code path that is ALSO never read), STOP — phase budget
is at cap. Document the discovery in `reports/v2-p3-rip-<timestamp>.md`
and seed v2.1 backlog. Do NOT expand P3 scope mid-phase.

If the alignment-eval `--ci-gate` regresses on FR-OG-7 rows after rip,
ABORT the rip; the `route()` kwarg consumer was load-bearing in some
unmeasured way. Document the failure mode and revert the consumer
deletion. Lever ledger then records "rip attempted, reverted" rather
than DORMANT-3 disposition.

If `cli_dispatch_fallback_ms` removal breaks the v1.6 CLI residue
breakout in soak driver output formatter, fix the formatter
additively (skip absent keys) — do NOT roll back the rip.

Report back when PR is open with: PR URL, diff stat, file list,
chosen branch (A or B), citation of P1 report, alignment-eval result,
total LOC delta in `src/` + `tests/` + `tools/`.
