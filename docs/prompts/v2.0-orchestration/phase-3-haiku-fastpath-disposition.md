You are implementing **Phase P3 — Haiku fastpath rip + verdict-fallback rip** for the streamManager v2.0 cycle.

## Branch + base

- Base: `main` (after v2.0 P1 merged at `8b34ce2`).
- PR target: `main`.
- Branch: `feat/v2-p3-fastpath-fallback-rip` (or operator's choice).

## Decision locked: rip both levers

P1 A/B (`reports/v2-p1-cli-pool-ab-20260507T141200Z.md`) measured **0%
fallback fire rate at all four cli_pool worker-recycle cadences**
(unset / N=1 / N=5 / N=10). Warm-process-reuse revival hypothesis
**falsified**. Per ADR-18 Rule 2 §"What counts as a strike", A/B
falsification grants **anticipatory rip authority** for the
verdict-fallback lever in the same cycle without waiting for the next
Tier 3 ship-gate strike.

Two levers ripped in P3:

1. **Haiku fastpath router** (DORMANT-3 entering v2.0; mandatory rip
   per ADR-18 Rule 2).
2. **Confidence + verdict-based fallback retry path** (DORMANT-2 +
   P1 falsification → anticipatory rip authority).

No A/B branching in this prompt; both rips land in the same PR.

## References

- `docs/adr/ADR-18-mvp-surface-freeze.md` Rule 1 (FROZEN list) +
  Rule 2 (DORMANT-N + anticipatory rip authority) + lever ledger
- `reports/v2-p1-cli-pool-ab-20260507T141200Z.md` — REQUIRED CITATION
- `src/stream_manager/governance.py` — `_evaluate_inner_core`;
  pre-CLI dispatch site (Haiku fastpath consumer)
- `src/stream_manager/cli_governance.py` — verdict-fallback retry
  branch; `BRIDGE_L4_FALLBACK_*` constants; envelope emission sites
- `src/stream_manager/model_router.py` — `RoutingDecision.fallback_model_id`
- `src/stream_manager/governance.py` — `_last_phase_timings_ms` dict (sole owner; setdefault sites at `_zero_cli_residue_keys` + `_maybe_cli_evaluate` early-return)
- `src/stream_manager/cli_pool.py` — UNCHANGED in P3
- `tools/soak_driver.py` — `_ALLOW_PHASE_ORDER` if it lists
  `cli_dispatch_fallback_ms`
- `docs/adr/ADR-5-latency-budget.md` — lever-effect ledger
- v1.7 / v1.8 / v1.9 task plan do-not-touch lists — annotate ripped
  symbols, do not delete history rows

## Do-not-touch guard

ADR-18 Rule 2 grants rip authority for both levers. Specific
allowances + restrictions:

- **Haiku fastpath rip**: delete the unread `route()` kwarg consumer
  at the pre-CLI dispatch site. Content-detection helpers
  (`_looks_ambiguous_block`, `is_ambiguous_block` /
  `is_hitl_synthesis` flag computation) STAY — FROZEN per v1.8 P1,
  may be reused by future work; only the unread route()-kwarg
  consumer disappears.
- **Fallback rip**: delete `cli_governance.py` verdict-based +
  confidence-floor retry trigger logic, `_fallback_confidence_floor()`
  helper, `BRIDGE_L4_FALLBACK_*` env constants,
  `governance_fallback_routed` and `governance_envelope_missing_confidence`
  envelope emission sites, `cli_dispatch_fallback_ms` instrumentation
  key. The bus envelope **schemas** stay on disk (append-only
  history); just stop emitting in code.
- **`cli_dispatch_fallback_ms` removal is the FIRST subtractive
  change to `engine._last_phase_timings_ms`.** ADR-18 Rule 1 makes
  this dict FROZEN. Removing the key requires explicit ADR-18
  amendment authorising subtractive change to a FROZEN list. Add
  the amendment in the same PR (text below in §"ADR-18 amendment").
- `cli_pool` UNCHANGED. Bus envelope schemas UNCHANGED (no
  removals).
- `model_router.RoutingDecision.fallback_model_id` deletes ONLY if
  no caller reads it after fastpath rip — `git grep
  fallback_model_id` across `src/`, `tests/`, `tools/` before
  deleting.

## Scope

### Step 1 — Haiku fastpath rip

1. Delete the unread fastpath consumer at the pre-CLI dispatch site
   in `governance._evaluate_inner_core`. `git grep
   'is_ambiguous_block='` and `git grep 'is_hitl_synthesis='`
   locate consumer kwargs at `route()` call sites.
2. `RoutingDecision.fallback_model_id` — `git grep
   fallback_model_id` across `src/`, `tests/`, `tools/`. If only the
   ripped consumer reads it, delete the field. If anything else
   reads it (besides fallback rip in Step 2), keep it.
3. Tests: remove tests that exercise the fastpath consumer ONLY
   (search `tests/test_routing*.py`, `tests/test_governance*.py`
   for `is_ambiguous_block` / `fastpath` references). Keep tests
   for the content-detection helpers themselves.

### Step 2 — Verdict-fallback rip

1. `src/stream_manager/cli_governance.py` — delete:
   - Verdict-based retry trigger branch (v1.9 P1)
   - Confidence-floor retry trigger branch (v1.7 P2)
   - `_fallback_confidence_floor()` helper
   - `BRIDGE_L4_FALLBACK_CONFIDENCE`, `BRIDGE_L4_FALLBACK_MODE` env
     constants
   - `governance_fallback_routed` envelope emission
   - `governance_envelope_missing_confidence` envelope emission
2. `src/stream_manager/governance.py` — remove `cli_dispatch_fallback_ms`
   key from `_last_phase_timings_ms` setdefault sites
   (`_zero_cli_residue_keys` and the `_maybe_cli_evaluate` early-return
   path). Update `tools/soak_driver.py` `_ALLOW_PHASE_ORDER` if it
   lists the key.
3. Bus envelope schemas — keep on disk (append-only history). Stop
   emitting in code only.
4. Tests: remove fallback-specific tests
   (`tests/test_governance_fallback_routing.py` if dedicated;
   prune fallback assertions from shared files).

### Step 3 — ADR-18 amendment (co-located in same PR)

Append a new §"Amendments" subsection to
`docs/adr/ADR-18-mvp-surface-freeze.md`:

> **2026-05-XX — v2.0 P3: subtractive change to
> `engine._last_phase_timings_ms`.** First-ever removal from this
> FROZEN dict (`cli_dispatch_fallback_ms` key) authorised under Rule
> 2 anticipatory rip authority (P1 A/B falsification at
> `reports/v2-p1-cli-pool-ab-20260507T141200Z.md`). Precedent:
> subtractive timing-key change is allowed ONLY when the originating
> lever is ripped under Rule 2; never for keys belonging to active
> levers. Future subtractive changes require their own amendment.

### Step 4 — Lever ledger updates

1. ADR-18 §"Initial classification": move both Haiku fastpath +
   confidence-floor/verdict fallback rows from "FROZEN" to a new
   §"Decommissioned" subsection with rip-date + rip-PR.
2. **Decrement** the `<!-- WIRED_LEVER_LEDGER_COUNT: 2 -->` HTML
   comment to `<!-- WIRED_LEVER_LEDGER_COUNT: 0 -->`. P4 ship-gate
   test asserts equality with `len(WIRED_LEVER_LEDGER)` in
   `tools/soak_driver.py`.
3. ADR-5 lever-effect ledger: append v2.0 P3 entries —
   - Haiku fastpath ripped at v2.0 P3 (DORMANT-3 mandatory
     disposition).
   - Verdict-fallback retry path ripped at v2.0 P3 (DORMANT-2 +
     P1 A/B falsification → anticipatory rip authority). Cite
     P1 report path.

### Step 5 — Search-and-update history references

`git grep` v1.7 / v1.8 / v1.9 task plan + phase prompt
do-not-touch references that name `is_ambiguous_block`,
`fallback_model_id`, `BRIDGE_L4_FALLBACK_*`,
`cli_dispatch_fallback_ms`, `governance_fallback_routed`. Annotate
each row as "ripped at v2.0 P3 — see ADR-18 §Decommissioned" rather
than deleting (preserves history). Active task plan
(`docs/v2.0-task-plan.md`) §P3 row gets updated to reflect both
rips landed (drop Branch A/B conditional language).

## DOD

- [ ] `reports/v2-p1-cli-pool-ab-20260507T141200Z.md` cited in PR
      description with verbatim quote of "anticipatory rip
      authority" sentence.
- [ ] All ripped symbols removed from code + tests; `git grep`
      clean for: `is_ambiguous_block=` (kwarg consumer site only),
      `BRIDGE_L4_FALLBACK_CONFIDENCE`, `BRIDGE_L4_FALLBACK_MODE`,
      `_fallback_confidence_floor`, `cli_dispatch_fallback_ms`,
      `governance_fallback_routed`,
      `governance_envelope_missing_confidence`.
- [ ] ADR-18 §"Decommissioned" subsection added with both rip rows.
- [ ] ADR-18 `WIRED_LEVER_LEDGER_COUNT` HTML comment is `0`.
- [ ] ADR-18 §"Amendments" entry authorising subtractive
      `_last_phase_timings_ms` change.
- [ ] ADR-5 lever-effect ledger appended (both rip events).
- [ ] `docs/v2.0-task-plan.md` §P3 row reflects both rips landed.
- [ ] Net LOC delta in `src/` + `tests/` + `tools/` strongly
      negative; target ~−700 LOC (P1 report estimate). Record
      exact `git diff --stat` figure in PR description.
- [ ] Alignment-eval `--ci-gate` exit 0: sonnet ≥ 0.95, haiku
      ≥ 0.85, 0 FR-OG-7 regressions, 0 haiku regressions vs sonnet.
- [ ] Tier 1.5 smoke soak passes (per ADR-17 amendment from P2).
- [ ] No FROZEN-list non-additive change beyond the authorised
      `_last_phase_timings_ms` key removal.

## Mint-new-phase rule

If during rip a third dormant lever surfaces (i.e. some other
v1.x-wired code path that is ALSO never read), STOP — phase budget
at cap. Document the discovery in
`reports/v2-p3-rip-<timestamp>.md` and seed v2.1 backlog. Do NOT
expand P3 scope mid-phase.

If `alignment-eval --ci-gate` regresses on FR-OG-7 rows after
fastpath rip, ABORT the rip; the `route()` kwarg consumer was
load-bearing in some unmeasured way. Document the failure mode and
revert the fastpath consumer deletion. Lever ledger then records
"rip attempted, reverted" instead of DORMANT-3 disposition. Fallback
rip stands either way (its falsification is independent).

If `cli_dispatch_fallback_ms` removal breaks the v1.6 CLI-residue
breakout in soak driver output formatter, fix the formatter
additively (skip absent keys) — do NOT roll back the rip.

If LOC delta lands materially short of −700 (e.g. only −300), audit
whether helper-method removal opportunities were missed
(`_fallback_confidence_floor`, dedicated test files for ripped
paths). Do not pad with unrelated cleanups; just record the actual
delta.

Report back when PR is open with: PR URL, `git diff --stat` total,
file list, citation of P1 report, alignment-eval result, ADR-18
amendment text, lever-ledger count drop (2→0), Tier 1.5 smoke
soak result.
