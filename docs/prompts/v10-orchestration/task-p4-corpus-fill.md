# v10 P4 — Corpus-fill run (unblock `phase-4-bandit-trainer.md`)

> Operational task. Required BEFORE firing
> `docs/prompts/v10-orchestration/phase-4-bandit-trainer.md`. Phase 4
> ABORTS if `rl_episodes.db` has < 200 live episodes (per seed v10.0 →
> v10.1 promotion gate).

## Current state (2026-05-12 baseline)

- `rl_episodes.db` total = 0; live = 0. DB file may be absent.
- Live MessageBus → rl_episodes.db subscriber wired at PR #155 (B'
  branch). Backfill extractor (gov.db → rl_episodes JSONL) at PR #156.
- Q4 hold lifted 2026-05-11 by operator. Hold-lift memory:
  `project_v10_p4_hold_lifted.md`.

## Goal

Populate `rl_episodes.db.episodes` with ≥ 200 rows tagged
`source='live'` (or operator-accepted alternative source mix per
`rl/sources/`) WITHOUT triggering FROZEN-seam edits.

## Two production paths (operator picks at run time)

### Path A — Live subscriber over Tier-3 soak (preferred, exercises PR #155)

1. Verify subscriber wired live: confirm `EpisodeLogger` registered as
   `MessageBus` subscriber at SM startup (grep
   `episode_logger.*subscribe|register` in `src/stream_manager/` +
   `dashboard/server.py`).
2. Run Tier-3 soak with `--cli-pool-size 2` (per memory
   `feedback_soak_cli_pool_flag.md`) for duration sized to
   ≥ 200 governance decisions (~30+ minutes; check ADR-17 + memory
   `project_v21_cycle_close.md` for v2.1 31.8-min soak baseline).
3. After soak completes, verify count:
   ```bash
   sqlite3 rl_episodes.db "SELECT COUNT(*) FROM episodes WHERE source='live';"
   ```
4. If < 200, repeat Tier-3 soak OR fall back to Path B.

### Path B — Backfill from prior gov.db (uses PR #156 extractor)

1. Locate any prior `tmp/soak_gov.db` from a previously run Tier-3
   soak.
2. Run extractor:
   ```bash
   python -m rl.cli.backfill --gov-db tmp/soak_gov.db --out tmp/backfill.jsonl
   python -m rl.episode_logger ingest --source backfill --file tmp/backfill.jsonl
   ```
3. Verify count post-ingest. Mix with Path A if needed.

## Verification gate (BEFORE firing phase-4 prompt)

```bash
sqlite3 rl_episodes.db "SELECT source, COUNT(*) FROM episodes GROUP BY source;"
```

- live ≥ 200 → Path A target met; phase-4 may fire.
- live + backfill ≥ 200, live > 0 → acceptable mix; verify P4 prompt
  AC allows mixed sources.
- Otherwise → re-run.

## Sticking points / risks

- **No shipped helper today** for extracting `governance_decision` from
  the soak-sse ndjson — PR #156 may cover or may need follow-up. Verify
  extractor exists post-merge.
- **`SM_OWN_SESSION_ID` defense-in-depth** (per memory
  `feedback_no_self_monitor.md` + `rl/episode_logger.py:88-90`) — confirm
  not filtering out the soak driver's own session.
- **Tier-3 soak duration** vs episode count: ensure publish cadence
  produces ≥ 200 governance_decision envelopes; tune `--total-seconds`
  and `--interval-seconds` to land ~200+ with margin.
- **ADR-18 surface posture** — corpus-fill is operational; no FROZEN
  edit. Live subscriber + backfill extractor already classified
  EVOLVING under v10 P1/P4 surfaces.

## DOD

- [ ] `rl_episodes.db` count satisfies phase-4 gate.
- [ ] Verification output pasted into operator log / issue #111 thread.
- [ ] If Path A used: soak report path recorded; cli-pool-size flag
      confirmed `2`.
- [ ] `docs/v10-mvp-status.md` §3 "P4" episode-count line updated to
      reflect new ground-truth count.
- [ ] Phase-4 prompt cleared to fire — no edits to that prompt at this
      step.

## Cross-references

- PR #155 (live MessageBus → rl_episodes.db subscriber).
- PR #156 (backfill extractor gov.db → JSONL).
- `docs/prompts/v10-orchestration/phase-4-bandit-trainer.md`.
- `docs/v10-mvp-status.md` §3 "P4".
- Memory `project_v10_p4_hold_lifted.md`,
  `feedback_soak_cli_pool_flag.md`, `feedback_no_self_monitor.md`.
- ADR-17 (Tier 3 vehicle).
