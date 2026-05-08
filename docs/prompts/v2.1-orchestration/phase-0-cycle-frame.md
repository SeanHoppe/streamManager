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
3. Consolidation cycles deletion-positive (net LOC ≤ 0) — does NOT
   apply to v2.1 (feature cycle; see decision below).
4. Phase budget: 4 phases per cycle (P0/P1/P2/P3 + P4 ship-gate)
5. Backlog hard cap (each cycle that opens new items must close or
   graduate at least one seed)

v2.0 closed with `WIRED_LEVER_LEDGER` empty (DORMANT-N gate inert).
Any v2.1 lever introduction bumps the dict + ADR-18 HTML comment in
the same PR. v2.1 P1 (PPP audit harness) is purely additive and
introduces no new wired lever; ledger stays empty.

## Operator decisions recorded at P0

**Cycle type: FEATURE.** Net LOC unbounded. v2.0 was the
deletion-positive consolidation cycle; v2.1 lands a new audit
seam (PPP) and is feature-shaped.

**Primary lever (P1): PPP audit harness — Layer 1 stream
disambiguation.** See `docs/v2.1-task-plan.md` and
`docs/prompts/v2.1-orchestration/phase-1-ppp-stream-disambiguation.md`
for full scope. P2 = Layer 2 canary echo. P3 = Layer 3
negative-control + self-monitor guard. P4 = ship-gate.

### Pivot rationale

The original P0 stub (preserved verbatim in §"Original P0 stub
(superseded)" below) recommended 🟡 corpus-framing parity as the
P1 candidate. At P0 review:

1. **Corpus-framing parity declined.** Per the backlog promotion
   criterion ("only promote to v2.1 P1 if a fresh
   content-detection lever is being designed"), no fresh
   content-detection lever is on deck — verdict-fallback was
   ripped in v2.0 P3 (DORMANT-2 anticipatory authority). The
   parity gap remains a structural curiosity in `docs/v2.1-backlog.md`
   at 🟡; no v2.1 work is queued against it.
2. **Sync-comms v1.0 HITL panel candidate evaluated and found
   SHIPPED.** When the fallback lever (sync-comms HITL panel
   slice) was scoped, ground-truth `src/stream_manager/` walk
   showed Tasks D/E/F/K landed in v1.0–v1.2:
   - `desktop_commands.py` (Task D, commit `e77a823`) — 159 LOC
   - `desktop_command_consumer.py` (Task E, commit `f6cd82d`) —
     428 LOC
   - `cross_session_hydrator.py` (Task F, commit `d7a4210`) — 92
     LOC
   - SSE transport (Task K, commit `b4d3bea`)
   - HITL queue panel + `cross_session_promotion` row variant
     (`dashboard/static/index.html:715`, `governance.py:1221,1231`)
   - `surface_hitl` kind in `desktop_commands.py:45` allowlist
   - `cross_session_flag` HITL trigger reason at `hitl.py:57`
   - `patterns.cross_session` column at `message_bus.py:465,503`
   - REQUIREMENTS NFR-MS-1..3 at lines 107–109

   The `project_sync_comms.md` memory was 5+ days stale and
   described pre-ship state. Memory updated at P0 to reflect
   SHIPPED status.

3. **PPP audit harness blocker cleared.** The 🟢 PPP audit harness
   seed has carried v1.7 → v1.8 → v1.9 → v2.0 → v2.1 backlogs with
   blocker "Depends on sync-comms v1.0 HITL panel landing first".
   With sync-comms v1.0 done, PPP unblocks naturally. No backlog
   emoji edit (frozen-emoji rule per `docs/v1.3-backlog.md`
   convention); cycle ownership recorded in
   `docs/v2.1-task-plan.md` only.

## References

- `docs/v2.1-backlog.md` — seed list (6 items, hard cap)
- `docs/v1.7-backlog.md` §"🟢 PPP audit harness — Provenance Probe
  Protocol" — original PPP scope, three-layer design, envelope
  pair `audit.probe` / `audit.probe_ack`
- `docs/adr/ADR-18-mvp-surface-freeze.md` — cycle-discipline rules
- `docs/adr/ADR-5-latency-budget.md` §"v2.0 ship-gate baseline" —
  current latency baseline; PPP cadence (per-30-min) sparse enough
  not to shift p95
- `docs/adr/ADR-14-desktop-command-sse.md` — SSE transport landed
  Task K; PPP HITL question rides this transport
- `CHANGELOG.md` v2.0.0 entry — cycle outcome summary
- `project_v20_cycle_close.md` memory — cycle-close context
- `project_sync_comms.md` memory (UPDATED at P0) — SHIPPED v1.0–v1.2

## Phase placeholders

- **P0** (this prompt): cycle frame + cycle-type framing decision
  + P1 lever pivot + minted P1 prompt + minted task-plan +
  sync-comms memory update.
- **P1**: PPP Layer 1 stream disambiguation (envelope pair +
  `provenance_assertions` WAL table + HITL panel section + HMAC
  cache + `/sm-probe` endpoint + cassette coverage +
  defense-in-depth self-monitor filter). Output: feature PR.
  Prompt:
  `docs/prompts/v2.1-orchestration/phase-1-ppp-stream-disambiguation.md`.
- **P2**: PPP Layer 2 canary echo (nonce emit + JSONL observation
  + 10 s timeout + re-fire Layer 1 on timeout). Prompt minted at
  P1 close-out.
- **P3**: PPP Layer 3 negative-control fake stream + hardened
  self-monitor brain_id guard. Prompt minted at P2 close-out.
- **P4**: ship-gate (Tier 3 soak `--cli-pool-size 2 --ppp-auto-probe`
  + alignment-eval + ADR-5 v2.1 baseline + CHANGELOG + tag).
  Prompt minted at P3 close-out.

## DOD for P0

- [x] Cycle-type framing decision recorded (FEATURE)
- [x] P1 lever decision recorded (PPP Layer 1)
- [x] Pivot rationale documented (corpus-framing declined +
      sync-comms-shipped finding + PPP unblock)
- [x] `docs/v2.1-task-plan.md` minted with phase rows + do-not-touch
      lists inheriting v2.0's FROZEN-list discipline
- [x] `docs/prompts/v2.1-orchestration/phase-1-ppp-stream-disambiguation.md`
      minted
- [x] ADR-18 confirmed unchanged (no v2.1 P0 amendment expected)
- [x] Backlog hard-cap check: 6 seeds in `docs/v2.1-backlog.md`;
      P0 work does NOT mutate backlog (frozen-emoji rule)
- [x] `project_sync_comms.md` memory updated to SHIPPED v1.0–v1.2

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

---

## Original P0 stub (superseded)

The original v2.1 P0 stub minted at v2.0 P4 ship-gate (commit
`3a2d9f7`) is preserved verbatim below. The "Primary lever
candidate (P1)" section is SUPERSEDED by the operator decision
above. Other content (cycle inheritance + ADR-18 rules + DOD
boxes) is duplicated in the elaborated body and remains accurate.

> ## Primary lever candidate (P1) — SUPERSEDED
>
> **🟡 Corpus-framing parity** (top of `docs/v2.1-backlog.md`):
>
> Investigate the gap between P1a fresh-process Haiku BLOCK (100% on
> wrapped destructive corpus at confidence ≥ 0.85) and soak driver
> ALLOW (100% on the same corpus through cli_pool long-lived workers).
> The verdict-fallback lever was ripped in v2.0 P3, so this gap no
> longer gates anything — but it's a structural curiosity worth
> diagnosing before any future content-detection lever is wired.
>
> Investigation scope:
> - Instrument `cli_governance.py` request-build path. Capture exact
>   stdin payload sent to the CLI subprocess for both:
>   - `tools/p1a_haiku_probe.py` fresh-process probe
>   - Soak driver running the same corpus row
> - Diff payloads byte-by-byte. Confirm `_wrap_user_prompt` parity,
>   system prompt header parity, conversation turn structure parity.
> - Either match the framing in the soak corpus or document the
>   structural divergence in ADR-5 §"v2.0 ship-gate baseline /
>   Caveats".
>
> Decision criterion at P3: if the gap turns out to be reproducible +
> small fix, P3 lands the patch (LOC budget bound by ADR-18 Rule 3 if
> v2.1 is framed as consolidation; if framed as feature cycle, no
> budget). If structural divergence is intentional v1.x harness behavior,
> P3 is a documentation-only ADR amendment.
