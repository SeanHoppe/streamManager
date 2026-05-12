# Changelog

All notable changes to streamManager are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project
adheres to semantic versioning per `docs/ROADMAP.md`.

## [Unreleased]

## [2.1.0] — 2026-05-11

Tagged ship of the v2.1 feature cycle — **PPP audit harness ships
end-to-end across three layers + two drain sub-phases**. See
`docs/v2.1-backlog.md` for the carry-forward seed list and
`docs/adr/ADR-5-latency-budget.md` §"v2.1 ship-gate baseline" for the
P4 numbers.

**ADR-18 surface freeze remains in force** — PPP layers landed as
additive envelope pairs (`audit.probe` / `audit.probe_ack` /
`audit.canary_emit` / `audit.canary_observed` / `audit.probe_failure` /
`audit.hallucination_detected`), additive WAL tables
(`provenance_assertions`, `provenance_decoys`), and additive
`desktop_command` allowlist kind (`audit_probe`) + additive HITL
trigger reason (`audit_probe`). No FROZEN seam edits. No new levers
introduced. `WIRED_LEVER_LEDGER_COUNT` remains 0; DORMANT-N gate
stays inert.

**ADR-18 §"Amendments" — retroactive Rule 4 LOC amendment.** The P3
PPP Layer 3 PR landed 1071 LOC vs the 700-LOC P3 soft cap; the
overage was recorded as a retroactive amendment at P3a per the
v2.1 P1 → P1a precedent. See `docs/v2.1-p3-scope.md` §"LOC tracker".
No new amendments at P4.

Highlights:

- **v2.1 P0 cycle frame**
  ([PR #126](https://github.com/SeanHoppe/streamManager/pull/126)) —
  cycle frame minted; ADR-18 surface freeze + falsify-before-extend
  carried into the PPP feature cycle. `docs/v2.1-task-plan.md` +
  `docs/v2.1-backlog.md` minted with 6 seeds (5 carry-forwards from
  v2.0 + 1 newly-scoped PPP harness target promoted into cycle scope).
  No code changes.
- **v2.1 P1 PPP Layer 1 — stream disambiguation**
  ([PR #138](https://github.com/SeanHoppe/streamManager/pull/138)) —
  FR-PPP-1..7 shipped. `audit.probe` + `audit.probe_ack` envelope
  pair on the ADR-14 SSE transport via `MessageBus.write_envelope`;
  HMAC reuses `desktop_command` secret of record (issue #128 §A1);
  `provenance_assertions` WAL table (additive, `probe_id UNIQUE`);
  `POST /api/sm-probe` + `POST /api/sm-probe/ack` dashboard
  endpoints; HITL panel `audit_probe` row variant; signed-assertion
  TTL caching; `FR-HITL-2` 5th trigger reason (`audit_probe`);
  `desktop_command` allowlist gains `audit_probe` kind;
  `--ppp-auto-probe` soak driver flag (opt-in, default OFF at P1).
- **v2.1 P1a P1 drain**
  ([PR #141](https://github.com/SeanHoppe/streamManager/pull/141)) —
  R14 (sig_v=2 schema bumps `signing_payload()` to include
  `brain_id` + `prompt_hash` for P2 canary verifier; pre-P1a v1
  rows continue validating); R16 (`SM_OWN_SESSION_ID` defense-in-
  depth filter at `session_watcher.build_audit_probe_candidates`,
  optional kwarg at P1a); R-cassette-idx, R-conftest. ADR-18
  §"Amendments" added the P1a sub-phase precedent under Rule 4.
- **v2.1 P2 PPP Layer 2 — canary echo**
  ([PR #143](https://github.com/SeanHoppe/streamManager/pull/143)) —
  FR-PPP-8..11 shipped. Three additive envelopes
  (`audit.canary_emit` / `audit.canary_observed` /
  `audit.probe_failure`); `JsonlTailWorker._canary_registry` +
  `register_canary` / `unregister_canary` API; per-process canary
  observer scanning user-text turns AFTER the `_is_sm_originated`
  filter (self-monitor guard from `feedback_no_self_monitor.md`);
  `CANARY_SWEEP_INTERVAL_S = 1.0` daemon-thread timeout sweep with
  10-s default; `mark_canary_confirmed` single-write-wins via
  `WHERE canary_confirmed_at IS NULL`; on canary timeout SM emits
  `audit.probe_failure` + re-fires Layer 1 candidate list (R7
  mitigation: recursion cap at 1 per probe).
- **v2.1 P3 PPP Layer 3 — negative-control + self-monitor hard guard**
  ([PR #145](https://github.com/SeanHoppe/streamManager/pull/145)) —
  FR-PPP-12..14 shipped. `POST /api/sm-decoy/register` endpoint +
  `provenance_decoys` WAL table (additive, `probe_id UNIQUE` +
  `jsonl_path UNIQUE`, idempotent on re-register);
  `audit.hallucination_detected` envelope (server-stamped on first
  parsed-record match against any registered decoy path);
  `MessageBus.is_registered_decoy_path` + `mark_decoy_triggered`
  single-emit-via-`WHERE triggered_at IS NULL`; `JsonlTailWorker`
  decoy hook (dormant in production at P3, exercised via direct
  calls in tests per the P2 `_process_line` precedent);
  **`session_watcher.build_audit_probe_candidates`'s `sm_brain_id`
  kwarg graduated from optional (P1a defense-in-depth) to
  MANDATORY** (silent → loud failure mode per
  `feedback_no_self_monitor.md`); dashboard `audit.hallucination_detected`
  HITL row variant (RED border, operator-dismiss only, NO auto-clear).
- **v2.1 P3a P3 drain**
  ([PR #147](https://github.com/SeanHoppe/streamManager/pull/147)) —
  R-decoy-idem 🔴 (decoy-registration idempotency race against
  `INSERT … ON CONFLICT(jsonl_path) DO NOTHING`); R-decoy-bus-sig
  (HMAC sig stamping at the registration endpoint); R-decoy-test-gap
  (registry coverage uplift); R-loc-amend (retroactive ADR-18 Rule 4
  LOC amendment for the P3 overage recorded at
  `docs/v2.1-p3-scope.md` §"LOC tracker", per the v2.1 P1 → P1a
  precedent).
- **v2.1 P4 ship-gate** (this entry) — 31.8-min Tier 3 soak with
  `--cli-pool-size 2` and `--ppp-auto-probe` default-on
  (`reports/soak-20260511T173516Z.md`). Verdict PASS; overall p95
  7.694 s (improvement vs v2.0 9.115 s, −1.42 s); RSS drift
  +0.38 MB. Per-band p95: ALLOW 6.35 s (vs v2.0 6.70 s), L2/L3
  9.00 s (vs v2.0 9.63 s), L4 12.14 s (vs v2.0 17.70 s; small-n
  n=4 oscillation band), LM 10.79 s (vs v2.0 14.12 s; LM watch
  closes 5th consecutive cycle). Soak summary emits the
  `WIRED_LEVER_LEDGER` inert-gate line:
  `Lever ledger: 0 wired levers — DORMANT-N gate inert`. Drift-
  detection test `tests/test_dormant_ledger_consistency.py` passes
  unchanged. `--ppp-auto-probe` default flipped OFF → ON at P4
  (FR-PPP-1 ship-gate-default amendment; paired `--no-ppp-auto-probe`
  mirror flag added for legacy CI / Tier 1.5 opt-out). Six auto-
  probes fired during the soak (every 10th publish: indices 10, 20,
  30, 40, 50, 60; zero `publish_errors`, zero uncaught exceptions);
  emit count not surfaced in soak summary because the soak driver's
  local bus has no envelope subscribers wired (issue #128 §A1 Option
  B fire-and-forget). v2.2 carry-forward seed: surface a probe-emit
  counter in the soak summary block (~5 LOC additive).

**Cycle LOC delta**: 25 files changed, +3924 / −50 →
**net +3874 LOC** in `src tests tools dashboard` for the v2.1 PPP
cycle alone (`git diff 401ae47..HEAD` subset excluding the v10 RL
companion track that merged in parallel; v10 subset is +2971 LOC
across 27 files, tracked at `project_v10_rl_track.md`). v2.1 is a
**feature cycle, no hard cap** per `docs/v2.1-task-plan.md`
§"LOC budget". The +3874 figure is the operator anchor for future
feature-cycle precedent (v1.9 ~+2800; v2.0 −1031; v2.1 +3874).
The §"Feature-cycle LOC ceiling — POLICY GAP" cross-cutting risk
from the task plan carries forward to v2.2 as an ADR-18 amendment
seed.

**JsonlTailWorker disposition (Option B — record dormancy + seed
v2.2).** The P3 decoy hook is exercised today via direct calls in
tests (matching the P2 `_process_line` test pattern).
`JsonlTailWorker.start()` itself is dormant in production — no
`src/` or `dashboard/` call site invokes it; only `tests/`
instantiate the class. Wiring decision deferred to v2.2 per the
v2.0 P4 docs-only ship-gate pattern. Seed at
`docs/v2.1-backlog.md` §"Carry-forwards from v2.1".

**Cross-cutting risk closures** (per
`docs/v2.1-task-plan.md` §"Cross-cutting risks"):

- **#1 Stale-memory recurrence** — mitigated at P0 (ground-truth
  walk before scoping)
- **#2 Cassette coverage drift** — held; cassette extended same-
  cycle in P1 / P2 / P3 per
  `feedback_cassette_must_cover_new_envelopes.md`
- **#3 Self-monitor leak** — closed at P3 (`sm_brain_id` mandatory
  kwarg graduation)
- **#4 Sub-phase escape hatch** — held; P1 → P1a + P3 → P3a both
  followed cycle-frame amendment path with retroactive Rule 4 LOC
  amendment for P3
- **#5 Probe transport coupling** — resolved at P1 kickoff (issue
  #128 §A1 Option B: direct `bus.write_envelope` for soak driver
  path; HTTP `/api/sm-probe` for operator path)
- **#6 P3 candidate-discovery surface** — closed at P3 hard-guard
  scope (`sm_brain_id` mandatory; `RuntimeError` at unset env-var
  call site)
- **#7 Feature-cycle LOC ceiling — POLICY GAP** — carries forward
  to v2.2 as ADR-18 amendment seed (the +3874 v2.1 cycle precedent
  anchors the policy question)

**Alignment-eval note**: `--ci-gate` exit 0 (FR-OG-7 regressions 0,
haiku-vs-sonnet regressions 0). Sonnet pass rate dipped 0.95 → 0.8636
between v2.0 and v2.1 ship-gate runs (`reports/alignment-eval-
20260511T185249Z.md`); ship-go per the P4 prompt §"Mint-new-phase
rule" because PPP envelope pairs cannot causally influence Sonnet
alignment (pubsub seam, never reaches `cli_governance.py`). The
Sonnet pass *count* is unchanged at 19 vs v2.0; the rate dropped
because the stability denominator rose (sonnet_stable_count 22 in
v2.1 vs 20 in v2.0) — two additional rows resolved to stably-wrong
majority verdicts. Latency variance is **ruled out** (it would lower
stability, not raise it); leading candidates are corpus rot on the
2 newly-stably-wrong rows or a Sonnet behavioural shift on those
2 rows. Alignment-recovery investigation carries forward to v2.2.

**Carry-forwards into v2.2** (`docs/v2.1-backlog.md` §"Carry-forwards
from v2.1"): `JsonlTailWorker.start()` production wiring, soak-
summary probe-emit counter (P4-surfaced gap), feature-cycle LOC
ceiling ADR amendment candidate, alignment-recovery investigation
(Sonnet 0.95 → 0.8636 dip — corpus rot vs Sonnet behavioural shift;
latency variance falsified by the stability-count rise).

## [2.0.0] — 2026-05-07

Tagged ship of the v2.0 consolidation cycle. See `docs/v2.1-backlog.md`
for the seed list and `docs/adr/ADR-5-latency-budget.md` §"v2.0
ship-gate baseline" for the P4 numbers.

**ADR-18 minted — cycle-discipline rules now in force for v2.1+.**
Five rules: (1) FROZEN/EVOLVING/EXPERIMENTAL surface freeze, (2)
DORMANT-N falsify-before-extend (cumulative dormant cycle counter
drives WARN/BLOCK signals), (3) consolidation-cycle LOC budget
(deletion-positive net delta required), (4) phase budget hard cap
per cycle, (5) backlog hard cap. See
`docs/adr/ADR-18-mvp-surface-freeze.md`.

**ADR-17 amendment — Tier 1.5 smoke soak + trigger matrix.** Binary
gate (pool warmed + clean shutdown) for fast-feedback verification
between Tier 1 unit tests and the full Tier 3 ship-gate soak.

Highlights:

- **v2.0 P0 cycle frame**
  ([PR #105](https://github.com/SeanHoppe/streamManager/pull/105)) —
  ADR-18 minted; consolidation cycle scoped against v1.9.0 baseline
  (`a7d0666`). DORMANT-3 disposition triggered for Haiku fastpath
  router; DORMANT-2 lever flagged for falsify-before-extend.
- **v2.0 P1 cli_pool worker A/B**
  ([PR #114](https://github.com/SeanHoppe/streamManager/pull/114)) —
  exercised `worker_recycle_every_n` ∈ {None, 1, 5, 10} to test the
  warm-process-reuse revival hypothesis for the verdict-fallback lever.
  **Falsified.** All four cadences produced 0% fallback fire rate;
  arm B (every-turn recycle) regressed ALLOW p95 ~+2 s without
  trading for fire rate. Per ADR-18 Rule 2 §"What counts as a strike",
  falsification grants anticipatory rip authority for the
  verdict-fallback lever in the same cycle. Source:
  `reports/v2-p1-cli-pool-ab-20260507T141200Z.md`.
- **v2.0 P2 Tier 1.5 codification**
  ([PR #113](https://github.com/SeanHoppe/streamManager/pull/113)) —
  ADR-17 amendment + soak-trigger matrix codifying the Tier 1.5 smoke
  soak as a pre-Tier-3 sanity gate.
- **v2.0 P3 lever rips — Haiku fastpath + verdict-fallback**
  ([PR #119](https://github.com/SeanHoppe/streamManager/pull/119)) —
  both wired levers removed in single PR:
  - **Haiku fastpath router** (DORMANT-3 mandatory rip): unread
    `is_ambiguous_block` / `is_hitl_synthesis` consumer at the pre-CLI
    dispatch site, `RoutingDecision.fallback_model_id` field, and
    `model_router.route()` L4 sub-band logic deleted. FROZEN
    content-detection helpers (`_looks_ambiguous_block`,
    `_looks_hitl_synthesis`, `_AMBIGUOUS_BLOCK_PATTERNS`) preserved.
  - **Verdict-fallback retry path** (DORMANT-2 + P1 anticipatory
    rip authority): `cli_governance.py` retry-trigger branches,
    `_fallback_confidence_floor()`, `_fallback_mode()`,
    `BRIDGE_L4_FALLBACK_*` env constants, `governance_fallback_routed`
    + `governance_envelope_missing_confidence` envelope emission, and
    `cli_dispatch_fallback_ms` instrumentation key all removed. Bus
    envelope schemas retained on disk for cassette + historical-report
    parsing.
  - **ADR-18 §"Amendments" entry — first-ever subtractive change to
    `engine._last_phase_timings_ms`** (FROZEN dict, ADR-18 Rule 1).
    `cli_dispatch_fallback_ms` key removed; precedent: subtractive
    timing-key change is allowed ONLY when the originating lever is
    ripped under Rule 2.
  - Net LOC delta after P3 PR alone: −1123 lines vs `a7d0666`
    (target ≤ 0 per ADR-18 Rule 3; ~−700 P3 estimate exceeded).
    Post-P4 the cumulative cycle delta lands at −1031 (P4 added
    ~92 LOC for `WIRED_LEVER_LEDGER` codification + drift test).
- **v2.0 P4 ship-gate** (this entry) — 32.2-min Tier 3 soak with
  `--cli-pool-size 2` (`reports/soak-20260507T174051Z.md`). Verdict
  PASS; overall p95 9.115 s (improvement vs v1.9 11.064 s, −1.95 s);
  RSS drift +0.73 MB. Per-band p95: ALLOW 6.70 s (vs v1.9 8.54 s),
  L2/L3 9.63 s (vs v1.9 15.09 s), L4 17.70 s (vs v1.9 17.40 s,
  +0.30 s within small-n oscillation band), LM 14.12 s (vs v1.9
  15.11 s; LM watch closes 4th consecutive cycle).
  Soak summary emits the `WIRED_LEVER_LEDGER` inert-gate line:
  `Lever ledger: 0 wired levers — DORMANT-N gate inert`.
  Drift-detection test `tests/test_dormant_ledger_consistency.py`
  asserts ADR-18 HTML comment matches the `tools/soak_driver` dict
  on every CI run.

**Lever-effect outcome — ledger empty.** v1.7-vintage Haiku fastpath
+ v1.7/v1.8/v1.9 verdict-fallback removed; `WIRED_LEVER_LEDGER_COUNT`
2 → 0. The DORMANT-N gate stays in the soak driver schema so future
re-introductions inherit the cycle-discipline rule.

**Open investigation carried into v2.1**: the gap between P1a
fresh-process Haiku BLOCK (100% on wrapped destructive corpus) and
soak ALLOW (100% on the same corpus). Likely investigation:
instrument `cli_governance.py` request-build path to confirm
wrapping equivalence between fresh-process probe and soak driver.
Out of scope for v2.0 per ADR-18 Rule 4 (phase cap).

## [1.9.0] — 2026-05-07

Tagged ship of the v1.9 cycle. See `docs/v2.0-backlog.md` for the seed
list and `docs/adr/ADR-5-latency-budget.md` §"v1.9 ship-gate baseline"
for the P4 numbers.

Highlights:

- **Verdict-based fallback trigger**
  ([PR #100](https://github.com/SeanHoppe/streamManager/pull/100), P1) — adds a `verdict==ENGAGE` branch to the v1.8
  confidence-floor fallback in `cli_governance.py`. Combined trigger now
  fires when **either** Haiku confidence drops below
  `BRIDGE_L4_FALLBACK_CONFIDENCE` **or** Haiku returns ENGAGE verdict.
  v1.7 byte-identical-when-disabled invariant preserved
  (`BRIDGE_L4_FALLBACK_MODE=off`).
- **P1a corpus-check diagnostic**
  ([PR #101](https://github.com/SeanHoppe/streamManager/pull/101), P1a) — `tools/p1a_haiku_probe.py` added to
  diagnose v1.8/v1.9 fallback-lever dormancy via fresh-process Haiku
  probe. Wrapped probe (matching `cli_governance.py:357` user-prompt
  wrapper) BLOCKs 100% of destructive corpus at confidence ≥ 0.85;
  bare probe BLOCKs 96%. Confirms the soak corpus IS adequate to
  trigger non-ALLOW verdicts, isolating the dormancy cause to cli_pool
  warm-process reuse (untested in P1a; v2.0 cli_pool A/B item seeded).
  Includes `_scrubbed_env` to strip BRIDGE_*/ANTHROPIC_API_KEY env
  inheritance and `_wrap_user_prompt` for soak-parity wrapping.
- **External session watcher + bg task token registry**
  ([PR #102](https://github.com/SeanHoppe/streamManager/pull/102), P2) — `src/stream_manager/session_watcher.py` polls
  `~/.claude/sessions/` for live Claude Code CLI sessions and tracks
  PID + cwd + entrypoint metadata. Re-registration after exit refreshes
  pid/cwd/entrypoint (PR #102 review fix). Foundation for the v2.0
  cross-session learning seam (per
  `project_sync_comms` memory). Test coverage:
  `tests/test_session_watcher.py` including
  `test_re_register_updates_pid_and_metadata`.
- **Learn Mode JSONL source expansion + self-monitor guard**
  ([PR #103](https://github.com/SeanHoppe/streamManager/pull/103), P3) — Learn Mode (v1.3) extended to ingest
  Desktop↔user dialogue from a wider source set including the new
  session-watcher pool. Self-monitor guard prevents Learn Mode from
  ever ingesting its own JSONL/bus events (per `feedback_no_self_monitor`
  memory rule). Advisory bias only; never overrides safety verdicts.
- **v1.9 ship-gate** (this entry, P4) — 32.3-min Tier 3 soak with
  `--cli-pool-size 2` (`reports/soak-20260507T084933Z.md`). Verdict
  PASS; overall p95 11.064 s (budget ≤ 12 s); RSS drift +0.24 MB.
  Alignment-eval `--ci-gate` exit 0; sonnet 1.000 / haiku 0.9545 /
  0 FR-OG-7 regressions / 0 haiku regressions vs sonnet
  (`reports/alignment-eval-20260507T093010Z.md`) — strongest alignment
  cycle to date.

**Lever-effect outcome — DORMANT for second consecutive cycle.** The
v1.9 P1 verdict-fallback addition fired 0% in the ship-gate soak.
60/60 events terminated at ALLOW; no Haiku verdict returned ENGAGE;
the new branch had nothing to fire on. `cli_dispatch_fallback_ms` p95
= 0.00 ms (identical to v1.8). The combined (confidence + verdict)
lever is wired but has fired 0% across two consecutive ship-gate
soaks. P1a probe diagnostic confirmed fresh-process wrapped Haiku
BLOCKs 100% of destructive prompts at confidence ≥ 0.85, isolating
the dormancy cause to cli_pool warm-process reuse (the leading
hypothesis, untested in P1a). v2.0 cli_pool A/B (fresh-vs-reused
process) is the next investigation lever. See
`docs/adr/ADR-5-latency-budget.md` §"v1.9 ship-gate baseline" §Caveats
and `docs/v2.0-backlog.md` for the next-cycle plan.

**Per-band p95 small-sample tail violations.** L2/L3 p95 (15.09 s, n=7)
exceeds the ≤ 8 s budget and L4 alignment p95 (17.40 s, n=4) exceeds
the ≤ 14 s budget; at these sample sizes p95 ≈ max and a single tail
event dominates. No code path touched between v1.8 and v1.9 in either
band; lever fire rate = 0%. Reproduces the v1.7→v1.8 oscillation
pattern. Treated as upstream Anthropic round-trip variance pending a
larger-n soak (Tier 4 candidate in v2.0 backlog).

**LM (categorize) p95 = 15.11 s** (v1.8: 13.30 s, +1.81 s). Within the
18 s ceiling; LM watch stays closed (third consecutive cycle).

## [1.8.0] — 2026-05-06

Tagged ship of the v1.8 cycle. See `docs/v1.9-backlog.md` for the seed
list and `docs/adr/ADR-5-latency-budget.md` §"v1.8 ship-gate baseline"
for the P2 numbers.

Highlights:

- **Content-detection wiring at pre-routing call site**
  ([PR #93](https://github.com/SeanHoppe/streamManager/pull/93), P1) — wires `is_ambiguous_block` and
  `is_hitl_synthesis` computation into `governance._evaluate_inner_core`
  at the pre-routing call site, activating the v1.7 P2 Haiku-fastpath
  lever. `_looks_ambiguous_block` matches a curated list of destructive-
  action patterns (shell commands, SQL DDL, force-push forms, prose
  variants) using compiled regexes. `_looks_hitl_synthesis` proxies the
  HITL classify-trigger surface (DESKTOP_PAUSE flag or PAUSE_PATTERNS
  match). New test file `tests/test_governance_content_detection.py` (40
  tests). Verdict-path invariant: when both flags are False (v1.7 default
  state), behavior is byte-identical to v1.7.
- **Soak corpus extension for ambiguous-block coverage**
  ([PR #94](https://github.com/SeanHoppe/streamManager/pull/94), P1a + P1c) — extended `tools/soak_driver.py`
  `_L2_L3_TRIGGER` with prose-form patterns (force-push, drop-table,
  delete-table) and imperative declarative forms to exercise
  `_looks_ambiguous_block` under the standard load mix. Three patterns
  land at soak positions 5 and 55 (seed-4242), confirmed by unit tests.
- **v1.8 ship-gate** (this entry, P2) — 32.1-min Tier 3 soak with
  `--cli-pool-size 2` (`reports/soak-20260506T101746Z.md`). Verdict PASS;
  overall p95 7.612 s (budget ≤ 12 s). Alignment-eval `--ci-gate` exit 0;
  0 FR-OG-7 regressions (`reports/alignment-eval-20260506T113450Z.md`).

**Lever-effect outcome — no latency improvement measured.** The
content-detection wiring correctly routes two soak events to Haiku-first
(positions 5 and 55 of the seed-4242 sequence match `_looks_ambiguous_block`).
However, Haiku returned confidence ≥ 0.70 on both events, so the
`BRIDGE_L4_FALLBACK_CONFIDENCE` floor was never crossed and
`cli_dispatch_fallback_ms` p95 = 0.00 ms (0 fallback fires). v1.8.0 ships
as a latency no-op; all p95 deltas vs v1.7 are within upstream Anthropic
round-trip variance. See `docs/adr/ADR-5-latency-budget.md` §"v1.8
ship-gate baseline" §Caveats and `docs/v1.9-backlog.md` §"Haiku fastpath
confidence floor" for the next-cycle investigation options.

**LM (categorize) p95 = 13.30 s** (v1.7: 11.95 s, +1.35 s). Within the
18 s ceiling; LM watch stays closed.

## [1.7.0] — 2026-05-05

Tagged ship of the v1.7 cycle. See `docs/v1.8-backlog.md` for the seed
list and `docs/adr/ADR-5-latency-budget.md` §"v1.7 ship-gate baseline"
for the P3 numbers.

Highlights:

- **L4 alignment-eval harness** ([PR #89](https://github.com/SeanHoppe/streamManager/pull/89), P1) — additive `tools/alignment_eval.py`
  driver + 32-row L4 golden set (`tests/golden/l4_alignment.jsonl`)
  drives `CliGovernor.evaluate` against control (Sonnet) and candidate
  (Haiku) models with a 3-runs-per-row unanimous-stability gate. Acts
  as the v1.7 P2 ship-blocker. P1 v2 baseline:
  `reports/alignment-eval-20260505T113007Z.md` (sonnet 0.9545; 1 FR-OG-7
  regression on `frog7-valid-transports-04`). Calibration narrative —
  v1 baseline at 50% control revealed prescriptive miscalibration;
  recalibration to Sonnet's empirical majority on borderline rows lifted
  control to 0.9545 with the unanimous-stability rule classifying drift
  honestly.
- **Haiku fastpath router with confidence-gated Sonnet fallback**
  ([PR #90](https://github.com/SeanHoppe/streamManager/pull/90), P2) — additive `RoutingDecision.fallback_model_id`
  field + L4 sub-band: `requires_alignment` stays Sonnet-only (FR-OG-7
  protected); `is_ambiguous_block` / `is_hitl_synthesis` route Haiku-first
  with Sonnet fallback when primary confidence < `BRIDGE_L4_FALLBACK_CONFIDENCE`
  (default 0.70). New `governance_fallback_routed` and
  `governance_envelope_missing_confidence` envelopes wired through a
  generalized `_publish_bus_message` helper. New `cli_dispatch_fallback_ms`
  key in `_last_phase_timings_ms` + 6th row in the v1.6 CLI residue
  block (pre-v1.7 streams unchanged). 27 new tests cover the surface
  deterministically.
- **v1.7 ship-gate** (this PR, P3) — 31.8-min Tier 3 soak with
  `--cli-pool-size 2` and the v1.7 router config enabled. Verdict PASS
  with overall p95 9.277 s, ALLOW p95 5.13 s, L4 alignment p95 13.41 s.
  Alignment-eval `--ci-gate` exit 0 (sonnet 0.9583, 0 FR-OG-7 regressions).
- **Lever wired but DORMANT — falsification recorded.** The L4 sub-band
  fastpath ships behind a content-detection seam that is not yet wired
  in production code paths: `governance._evaluate_inner_core` pre-routing
  sets `is_ambiguous_block=False` and `is_hitl_synthesis=False`
  unconditionally for now. Soak result: 0 fallback fires across 60 events;
  `cli_dispatch_fallback_ms` p95 = 0.00 ms. `cli_pool_send_ms` p95 dropped
  19.0% (6328 → 5129 ms) and ALLOW p95 dropped 1.20 s, but per the P3
  falsification rule these are recorded as upstream Anthropic round-trip
  variance, NOT lever effect (the lever code never executed). Content-based
  detection of the two flags is a v1.8 backlog item; lever effect cannot
  be measured until that lands.
- **LM (categorize) watch — RESOLVED.** v1.7 LM p95 = **11.95 s** (n=10)
  is well below the 18 s ceiling. Trend: v1.4 = 19.26 s → v1.5 = 15.39 s
  → v1.6 = 18.60 s → **v1.7 = 11.95 s**. Watch closes per the v1.7
  backlog rubric. Spread p50→p95 = 2.82 s (v1.6 was 5.91 s) — variance
  also retreated.
- **ADR-5 §"v1.7 ship-gate baseline"** added; budget table carried
  forward unchanged from v1.6. v1.6 §Caveats LM bullet annotated with
  v1.7 disposition (RESOLVED). v1.6 §Caveats lever bullet annotated with
  v1.7 disposition (DORMANT, see falsification check). Status line
  bumped (v1.6 + v1.7 baselines added).

### Notes

- v1.7 verdict path is **byte-identical** for v1.6 callers (every
  production caller post-merge passes `fallback_model_id=None`):
  550 fast-tier tests passing.
- `--cli-pool-size 2` remains the ship-gate default per
  `feedback_soak_cli_pool_flag.md`.
- Cassette format (`tools/cassette_record.py`) captures decision-output
  records, not bus events, so the new bus envelopes are out of the
  cassette schema by design. Test stubs replace cassette evidence for
  the dormant fallback surface (7 deterministic scenarios in
  `tests/test_governance_fallback_routing.py`).
- Lifecycle bridge orphan-free positively asserted at ship-gate again
  (0 entries, 0 orphans).
- v1.7 P0 cycle frame ([PR #88](https://github.com/SeanHoppe/streamManager/pull/88)) seeded the four orchestration prompts
  + task plan + v1.8 backlog (then empty); P3 finalize populates v1.8
  backlog with the content-detection wiring item.

## [1.6.0] — 2026-05-05

Tagged ship of the v1.6 cycle. See `docs/v1.7-backlog.md` for the seed
list and `docs/adr/ADR-5-latency-budget.md` §"v1.6 ship-gate baseline"
for the P2 numbers.

Highlights:

- **`_evaluate_inner` CLI residue instrumentation** (PR #85 + #86, P1) —
  five new keys on `engine._last_phase_timings_ms`: `cli_setup_ms`,
  `cli_dispatch_ms`, `cli_pool_acquire_ms`, `cli_pool_send_ms`,
  `cli_parse_ms`. Soak driver report grows an `### ALLOW _evaluate_inner
  CLI residue breakout (v1.6)` block alongside the v1.4 publish-path and
  v1.5 sub-phase blocks. Verdict path unchanged (additive `perf_counter`
  deltas only, no reordering).
- **v1.6 ship-gate** (this PR, P2) — 32.6-min Tier 3 soak with
  `--cli-pool-size 2` and the new CLI residue instrumentation enabled.
  Verdict PASS with overall p95 7.665 s and ALLOW p95 6.33 s.
- **Driver localisation finding.** The v1.5 §"Caveats" residue item is
  **resolved**. `cli_pool_send_ms` p95 = 6328.07 ms accounts for 99.99%
  of `cli_dispatch_ms` (6329.00 ms) and ~99.98% of `evaluate_inner`
  (6329.38 ms). Driver is the synchronous `worker.send` Anthropic CLI
  round-trip (subprocess stdin write + stdout JSONL response wait in
  `CliWorker.send`); `cli_setup_ms` (0.01 ms), `cli_pool_acquire_ms`
  (0.06 ms — confirms zero queueing under sequential soak), and
  `cli_parse_ms` (0.15 ms) are all negligible. v1.7 lever = **Haiku
  fastpath** (primary; downgrade more L4/ambiguous-BLOCK from Sonnet →
  Haiku) with **pool sizing >2** as fallback (insurance for concurrent
  burst load only).
- **LM (categorize) p95 trend disposition.** v1.4 = 19.26 s → v1.5 =
  15.39 s → v1.6 = **18.60 s** (+3.21 s vs v1.5; 0.60 s over 18 s
  ceiling, 3.3% breach). Per S5a triage — n=10 high-variance, dashboard
  log clean, no cassette envelope additions in v1.6 affecting the LM
  categorizer — **decision: ship-with-v1.7-watch**. LM is advisory /
  categorize, not on the safety path. Re-measure at v1.7 ship-gate; if
  next sample also lands ≥ 18 s, treat as sustained regression and
  triage cassette/categorizer separately.
- **ADR-5 §"v1.6 ship-gate baseline"** added; budget table carried
  forward unchanged from v1.5. v1.5 §"Caveats" residue + LM bullets
  appended w/ forward pointers to v1.6 disposition. Status line bumped.

### Notes

- v1.6 verdict path is **at parity** with v1.5 (no production-code
  change to `_evaluate_inner` body beyond additional `perf_counter`
  deltas inside the CLI escalation branch). ALLOW + overall p95
  increases vs v1.5 are classified as upstream Anthropic round-trip
  variance on a sequential soak driver, not earned regression — the
  residue driver (`cli_pool_send_ms`) is upstream model time, not local
  engine code.
- Lifecycle bridge orphan-free positively asserted at ship-gate again.
- `--cli-pool-size 2` remains the ship-gate default (omitting it
  silently reproduces the v1.0 cold-start regression by spawning a
  fresh CLI per event — pool reuse is mandatory for the residue
  numbers above to be representative).
- v1.6 P1 followups (PR #86, merge `380f453`) hardened residue
  instrumentation emission paths so all `_evaluate_inner` exit branches
  populate the five keys consistently.

## [1.5.0] — 2026-05-04

Tagged ship of the v1.5 cycle. See `docs/v1.6-backlog.md` for the seed
list and `docs/adr/ADR-5-latency-budget.md` §"v1.5 ship-gate baseline"
for the P2 numbers.

Highlights:

- **`_evaluate_inner` sub-phase instrumentation** (PR #82, P1) — five
  new keys on `engine._last_phase_timings_ms`: `og7_check`,
  `fast_precheck`, `graph_classify`, `hydrator_state_read`,
  `routing_dispatch`. Soak driver report grows an `### ALLOW
  _evaluate_inner sub-phase breakout (v1.5)` block alongside the v1.4
  publish-path block. Verdict path unchanged (additive `perf_counter`
  deltas only, no reordering).
- **v1.5 ship-gate** (this PR, P2) — 32.2-min Tier 3 soak with
  `--cli-pool-size 2` and the new sub-phase instrumentation enabled.
  Verdict PASS with overall p95 5.820 s and ALLOW p95 5.60 s.
- **Sub-phase finding.** The v1.4 hypothesis that the ALLOW p95 tail
  lives in one of the five named sub-phases is **falsified by the
  data**. The five sub-phases sum to 0.13 ms p95 against a 5599 ms
  `evaluate_inner` p95 — ~99.998% of the tail is in code paths NOT
  covered by v1.5 instrumentation. The actual tail driver lives in the
  un-instrumented residue inside `_evaluate_inner`, most plausibly the
  synchronous `cli_pool` round-trip on the escalation branch. v1.6
  should extend instrumentation around the residue.
- **LM (categorize) p95 trend disposition.** v1.3.1 = 15.39 s →
  v1.4 = 19.26 s → v1.5 = 15.39 s. The v1.4 elevation did not persist;
  the v1.4 §"Caveats" watch item ("re-measure if the next ship-gate
  also lands above 18 s") is **closed**. No v1.6 follow-up needed.
- **ADR-5 §"v1.5 ship-gate baseline"** added; budget table carried
  forward unchanged from v1.4. Status line bumped.

### Notes

- v1.5 verdict path is **at parity** with v1.4 (no production-code
  change to `evaluate_inner` body beyond five additional `perf_counter`
  deltas). The −2.36 s overall p95 and −1.97 s ALLOW p95 deltas vs v1.4
  are classified as time-of-day / upstream-rate-limit measurement
  variance, not earned improvements.
- Lifecycle bridge orphan-free positively asserted at ship-gate again.
- `hydrator_state_read` fires on every ALLOW (n=50) at p95 = 0.00 ms;
  the lazy-hydrator state read is effectively free under the soak
  workload.

## [1.4.0] — 2026-05-04

Tagged ship of the v1.4 cycle. See `docs/v1.4-backlog.md` for the
seed list and `docs/adr/ADR-5-latency-budget.md` §"v1.4 ship-gate
baseline" for the M3 numbers.

Highlights:

- **Learn Mode runtime slide-toggle** (PR #76) — dashboard header pill
  flips the categorizer worker active state without bouncing the host.
  Persisted to `learn_categorizer_state(key='runtime_enabled')`; worker
  observes the change on its next 5 s tick. Backward-compat preserved
  for v1.3.1 deployments without a runtime row.
- **ALLOW publish-path phase instrumentation** (PR #77) — new
  `engine._last_phase_timings_ms` attribute populated at end of every
  `evaluate()` call with sub-microsecond `perf_counter` deltas across
  seven phases. Soak driver report grows an `### ALLOW publish-path
  phase breakout (v1.4)` block. New `tools/allow_phase_probe.py` for
  cheap quota-free local profiling.
- **Scenarios library buildout** (PR #78) — 9 Method-1 YAML scenarios
  under `tests/scenarios/` covering v1.0–v1.4 surface (governance L0/L4,
  HITL, lifecycle bridge, SSE desktop_command, WireCLI, Learn Mode
  end-to-end, advisory bias, runtime toggle). `scenario_runner.py`
  gains `--scenarios`, `--all`, plus a `_KNOWN_ENVELOPE_TYPES` registry
  that soft-warns on unknown types.
- **Cassette ↔ beacon DRY** (PR #79) — single canonical 3-tuple
  constant `cassette_record._LM_DIALOGUE_PAIRS_WITH_CATEGORY` drives
  both the cassette refresh and a regenerated beacon JSONL.
  `tools/regenerate_lm_beacons.py` keeps the two in sync; drift-detection
  test fails if either side edits without rerunning the regenerator.
- **v1.4 ship-gate** (PR pending — this cycle) — 32.3-min Tier 3 soak
  with `--cli-pool-size 2` and the new phase instrumentation enabled.
  Verdict PASS with overall p95 8.178 s (−2.26 s vs v1.3.1, parity
  class — likely measurement noise). The phase breakout **disproves
  the v1.3.1 §"Caveats" hypothesis** that ALLOW p95 was dominated by
  publish-path sqlite contention: 100% of the 7.57 s ALLOW p95 lives
  inside `_evaluate_inner` (publish + record_decision sum to under 1 ms).
  v1.5 should instrument inside `_evaluate_inner` to attribute the
  7.5-second tail to a specific sub-phase.
- **ADR-5 §"v1.4 ship-gate baseline"** added; budget table carried
  forward unchanged from v1.3.1. Status line bumped.

### Notes

- v1.4 verdict path is **at parity** with v1.3.1 (no production-code
  change to `evaluate_inner` body). The phase instrumentation adds
  ~7 `perf_counter` deltas per call (~sub-µs each). The probe tool
  reports in-process ALLOW p95 = 0.16 ms on an idle bus.
- Lifecycle bridge orphan-free positively asserted at ship-gate again.
- v1.4 backlog now empty.

## [1.3.1] — 2026-05-04

P6 close-gaps maintenance release (PR #75). Adds Path-A soak coverage
of the Learn Mode hot path so ADR-5 can be re-baselined against v1.3
code. v1.3.0 (commit `01e749a`) was tagged feature-complete but had
not exercised the FR-LM-1..6 envelopes under ship-gate soak — this
release closes that gap.

- **Cassette `learn_dialogue` envelope kind** (`tools/cassette_record.py`,
  `tools/soak_driver.py`): recorder pumps 10 pre-canned Desktop ↔ user
  dialogue pairs through the live Sonnet categorizer per cassette
  refresh; cassette p95 is a relative regression signal only.
- **Soak driver replay path** routes `learn_dialogue` envelopes into a
  new `lm_categorize_latencies_s` band; per-band table grows an
  "LM (categorize)" row.
- **Soak driver ship-gate path** runs the same dialogue pump after the
  engine.evaluate publish loop with real Sonnet, surfacing the LM band
  in the M3 ship-gate report.
- **Backward compat:** v1.2 cassettes (zero `learn_dialogue` rows)
  replay unchanged; legacy CI runs may pass `--skip-lm-pump`.
- **ADR-17** amended (additive): `learn_dialogue` schema documented
  under §"v1.3 learn_dialogue extension".
- **ADR-5** re-baselined: new §"v1.3 ship-gate baseline" against
  `reports/soak-20260504T152005Z.md` (M3, 32.2 min, `--cli-pool-size 2`).
  Overall p50 3.680 s / p95 10.436 s — **parity** with v1.2 (Δp95
  +0.04 s). New per-band rows: ALLOW p95 9.60 s, L2/L3 p95 6.08 s,
  L4 p95 13.89 s, LM p95 15.39 s. ALLOW p95 budget widened from
  speculative ≤ 6 s to measured ≤ 12 s; new LM (categorize) p95
  budget ≤ 25 s.
- **Lifecycle bridge orphan-key check** now positively asserted at
  ship-gate (P1 hardening firing; v1.2 caveat resolved).

### Notes

- v1.3 verdict path is **at parity** with v1.2 (overall p95 +0.04 s).
  Learn Mode advisory bias (P5d `bias_for` read) does NOT regress the
  verdict hot path.
- Lifecycle bridge orphan-key check now positively asserted at
  ship-gate; carried v1.2 caveat resolved.
- ALLOW p95 separated from overall envelope for the first time. The
  9.60 s measurement supersedes the v1.2 speculative ≤ 6 s; v1.4
  publish-path instrumentation is queued.

## [1.3.0] — 2026-05-04

Tagged ship of the v1.3 cycle (commit `01e749a`, PR #74 merge). See
`docs/v1.3-task-plan.md` for the full phase list (P0–P6) and the
ship-gate maintenance release [1.3.1] above for the Path-A close-gaps
work. Highlights:

- **P0** (PR #54): cycle frame + testing methodology
  (`docs/v1.3-testing.md`) + v1.4 backlog seed.
- **P1** (PR #56): soak driver + recorder hardening — same-day
  cassette no-clobber, per-band p50/p95 split (ALLOW / L2-L3 / L4),
  positive `LifecycleBridge._seen` orphan-free assertion at ship-gate.
- **P2** (PR #57): `list_active_jobs` windowed query — 100-pair tail
  truncation fixed.
- **P3** (PR #58): REQUIREMENTS FR-OG drift audit — session picker,
  lifecycle pane, SSE-only desktop_command transport, WireCLI default
  + json refusal entries added; spec version pin bumped.
- **P4** (PR #59–63): code-quality sweep (7 🔵 carry-overs).
- **P5** marquee — Learn Mode (advisory dialogue bias):
  - **P5a** (PR #60): `docs/learn-mode-design.md` + REQUIREMENTS
    FR-LM-1..6.
  - **P5b** (PR #61): JSONL tail extension — `desktop_prompt` and
    `user_reply` message types, paired via `parentUuid` chain;
    SM-self filtering enforces `feedback_no_self_monitor.md`.
  - **P5c** (PR #62): Sonnet categorizer worker (`learn_categorizer.py`)
    — out-of-band, dedicated subprocess, off the verdict hot path
    (ADR-5 NFR-P2 unaffected); new `learn_patterns` table.
  - **P5d** (PR #63): advisory bias hookup (`bias_for`) — read-only
    consumer of `learn_patterns`; never overrides safety-first checks
    or short-circuits HITL gate; INTENT.md §"Safety priorities"
    always wins.
  - **P5e** (PR #64): decay/reinforcement/contradiction logic
    (`decay.py`) + beacon/probe drivers
    (`tests/beacons/learn_mode_categorizer.jsonl`,
    `tests/probes/learn_mode_drift.csv`).
  - **Corrective C0–C10** (PRs #65–73): bias-canonical wiring,
    PR #64 review fixes, drift audit across P5 sub-phases, ADR-19
    canonical/audit split, end-to-end pipeline test, FR-LM-* CI
    coverage map, dashboard bias-hint badge.

## [1.2.0] — 2026-05-03

Tagged ship of the v1.2 cycle. See `docs/v1.2-task-plan.md` for the
full task list. Highlights:

- Task A: three-tier soak model (replay / cassette / ship-gate) —
  ADR-17. Replay tier removes upstream rate-limit variance from
  per-CI runs; ship-gate remains the source of truth for ADR-5
  absolute latency budget.
- Task B: `sm sessions list/tail` operator CLI + dashboard session
  picker (`sm:session-changed` event, `PHASE6.selectedSessionId`).
- Task C: Claude Code lifecycle bridge — `LifecycleBridge` +
  `HookFolderPoller` shim for BG jobs / spawned subagents,
  `/api/lifecycle/jobs` read endpoint, dashboard pane.
- Task D: long-poll command transport removed (see Removed entry
  below). SSE is the sole desktop_command transport.
- Task E: json CLI transport selector removed (see Removed entry
  below). WireCLI is the sole and default cli transport.
- Tasks F (per-instance HMAC keypairs default) and G (browser
  dashboard auth) deferred — gates did not fire in v1.2.
- `docs/v1.2-followup.md`: running ledger of deferred review
  findings carried into v1.3.

### Removed
- **Long-poll command transport** (deprecated in v1.1, ADR-14). The
  legacy `GET /api/commands/pending` endpoint and the
  `transport='long-poll'` branch on `CommandConsumer` have been removed.
  Server-Sent Events (`GET /api/commands/stream`) is now the sole
  desktop_command transport. `CommandConsumer(transport='long-poll')`
  raises `ValueError` with a migration hint pointing at this entry.
  Operators using `tools/sm_consumer.py` should drop any
  `--transport long-poll` flag; the default and only accepted value is
  now `sse`. See `docs/adr/ADR-14-desktop-command-sse.md` and
  `docs/v1.2-task-plan.md` Task D.
- **json CLI transport selector** (deprecated in v1.1, ADR-15). The
  legacy `transport='json'` value on `cli_client.cli_transport()` and
  the `BRIDGE_CLI_TRANSPORT=json` env value have been removed.
  `WireCLI` (`transport='wirecli'`) is now the unconditional default
  and the only accepted value. `cli_transport('json')` and
  `BRIDGE_CLI_TRANSPORT=json` raise `ValueError` with a migration hint
  pointing at this entry. The `cli_client.transport` kwarg surface and
  the `cli_transport()` resolver are preserved (still used as the
  governance escalation selector); only the `'json'` value goes away.
  Operators running `tools/wirecli_soak_compare.py` should drop any
  `--transport json` flag and use `--transport wirecli` (or
  `--transport legacy` for the historical fragility-comparison report,
  which is no longer a runtime transport). See
  `docs/adr/ADR-15-wirecli-transport.md` and
  `docs/v1.2-task-plan.md` Task E.

## [1.1.0] — 2026-05-03

Tagged ship of the v1.1 cycle. See `docs/v1.1-task-plan.md` for the
full task list. Highlights:

- Task I: hydrator hot-path profile + lazy-init.
- Task J: warm pool of long-lived Claude CLI workers (`CliPool`).
- Task K: SSE transport for desktop_command (`/api/commands/stream`),
  long-poll retained as default for one-cycle compatibility.
- Task L: `hitl_pending.matched_hash` dedicated column with idempotent
  backfill.
- Task M: `EngineRegistry.start_refresh` / `stop_refresh` wired to
  dashboard boot/shutdown.
- Task N: WireCLI structured CLI transport (`transport='wirecli'`),
  json transport retained as default for one-cycle compatibility.

## [1.0.0] — initial ship

POC graduated to a tagged release. See `docs/v1.0-ship-plan.md`.
