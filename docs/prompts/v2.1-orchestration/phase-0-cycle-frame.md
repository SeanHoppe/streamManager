You are framing **Phase P0 — v2.1 cycle frame** for the streamManager
v2.1 cycle.

## Branch + base

- Base: `main` after v2.0.0 ship (tag `v2.0.0` at `401ae47`).
- PR target: `main`.
- Branch: `feat/v2.1-cycle-frame` (or operator's choice).

## Cycle inheritance

v2.1 inherits **ADR-18 cycle-discipline rules in full force**:

1. Surface freeze (FROZEN / EVOLVING / EXPERIMENTAL classifications)
2. DORMANT-N falsify-before-extend (cumulative dormant counter drives
   WARN/BLOCK; `WIRED_LEVER_LEDGER_COUNT` HTML comment ↔
   `tools/soak_driver.WIRED_LEVER_LEDGER` dict, drift-detection test
   `tests/test_dormant_ledger_consistency.py`)
3. Consolidation cycles deletion-positive (net LOC ≤ 0)
4. Phase budget: 4 phases per cycle (P0/P1/P2/P3 + P4 ship-gate)
5. Backlog hard cap (each cycle that opens new items must close or
   graduate at least one seed)

v2.0 closed with `WIRED_LEVER_LEDGER` empty (DORMANT-N gate inert).
Any v2.1 lever introduction bumps the dict + ADR-18 HTML comment in
the same PR.

## References

- `docs/v2.1-backlog.md` — seed list (6 items)
- `docs/adr/ADR-18-mvp-surface-freeze.md` — cycle-discipline rules
- `docs/adr/ADR-5-latency-budget.md` §"v2.0 ship-gate baseline" —
  current latency baseline
- `CHANGELOG.md` v2.0.0 entry — cycle outcome summary
- `project_v20_cycle_close.md` memory — cycle-close context

## Primary lever candidate (P1)

**🟡 Corpus-framing parity** (top of `docs/v2.1-backlog.md`):

Investigate the gap between P1a fresh-process Haiku BLOCK (100% on
wrapped destructive corpus at confidence ≥ 0.85) and soak driver
ALLOW (100% on the same corpus through cli_pool long-lived workers).
The verdict-fallback lever was ripped in v2.0 P3, so this gap no
longer gates anything — but it's a structural curiosity worth
diagnosing before any future content-detection lever is wired.

Investigation scope:
- Instrument `cli_governance.py` request-build path. Capture exact
  stdin payload sent to the CLI subprocess for both:
  - `tools/p1a_haiku_probe.py` fresh-process probe
  - Soak driver running the same corpus row
- Diff payloads byte-by-byte. Confirm `_wrap_user_prompt` parity,
  system prompt header parity, conversation turn structure parity.
- Either match the framing in the soak corpus or document the
  structural divergence in ADR-5 §"v2.0 ship-gate baseline /
  Caveats".

Decision criterion at P3: if the gap turns out to be reproducible +
small fix, P3 lands the patch (LOC budget bound by ADR-18 Rule 3 if
v2.1 is framed as consolidation; if framed as feature cycle, no
budget). If structural divergence is intentional v1.x harness behavior,
P3 is a documentation-only ADR amendment.

## Cycle-type framing decision

**Operator decision at P0**: is v2.1 a feature cycle or another
consolidation cycle?

- **Feature cycle**: net LOC unbounded. Permits new seam introduction
  (e.g. sync-comms HITL panel from v2.0 carry-forward, PPP audit
  harness if sync-comms unblocks).
- **Consolidation cycle**: net LOC ≤ 0 vs `401ae47`. Suitable if the
  P1 corpus-framing investigation surfaces a stale code path worth
  ripping.

Default recommendation: **feature cycle**, since v2.0 was the
deletion-positive cycle and v2.1 has no DORMANT-3 lever queued. P1
investigation outcome may flip this at P3 if a rip surfaces.

## Phase placeholders (to be elaborated post-P0)

- **P0** (this prompt): cycle frame + cycle-type framing decision.
  ADR review (no edits expected); v2.0-ship-state acknowledgement.
- **P1**: corpus-framing parity investigation (instrumentation +
  diff). Output: `reports/v2-1-corpus-framing-<timestamp>.md`.
- **P2**: TBD pending P1 outcome. Candidates from v2.1 backlog:
  `--total-events` flag drift disposition, Tier 1.5 CI gate
  promotion, sync-comms v1.0 HITL panel (if unblocked).
- **P3**: TBD pending P1 outcome. Either (a) corpus-framing fix or
  ADR doc amendment, or (b) a new lever from P1's findings, or
  (c) a v2.0 carry-forward seed elaborated to feature.
- **P4**: ship-gate (Tier 3 soak `--cli-pool-size 2` + alignment-eval
  + ADR-5 v2.1 baseline + CHANGELOG + tag).

## DOD for P0

- [ ] `docs/v2.1-task-plan.md` minted with phase rows + do-not-touch
      lists inheriting v2.0's FROZEN-list discipline
- [ ] Cycle-type framing decision recorded (feature vs consolidation)
- [ ] v2.1 P1 phase prompt outline drafted (`docs/prompts/v2.1-orchestration/phase-1-corpus-framing-parity.md`)
- [ ] ADR-18 confirmed unchanged (no v2.1 P0 amendment expected)
- [ ] Backlog hard-cap check: 6 seeds in `docs/v2.1-backlog.md`;
      P0 work should not add new ones (or close one if it does)

## Mint-new-phase rule

If P0 review surfaces an ADR-18 amendment opportunity (e.g. a sixth
cycle-discipline rule), defer to a separate ADR-18 §"Amendments"
entry rather than expanding P0 scope. ADR-18 amendments are
single-PR transactions.

If during P0 review the v2.0 ship-gate report surfaces a regression
that escaped the gate (e.g. a phase timing key inadvertently dropped
or a soak verdict marginal), open a ship-gate fixup branch
(`ship/v2.0-shipgate-fixups`) — do NOT expand v2.1 P0 to absorb.

Report back when P0 PR is open with: PR URL, cycle-type framing
decision, v2.1 P1 prompt outline path, v2.1 task-plan path.
