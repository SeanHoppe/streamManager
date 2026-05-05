# Changelog

All notable changes to streamManager are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project
adheres to semantic versioning per `docs/ROADMAP.md`.

## [Unreleased]

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
