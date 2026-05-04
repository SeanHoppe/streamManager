# Changelog

All notable changes to streamManager are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project
adheres to semantic versioning per `docs/ROADMAP.md`.

## [Unreleased]

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
