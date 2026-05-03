# Changelog

All notable changes to streamManager are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project
adheres to semantic versioning per `docs/ROADMAP.md`.

## [Unreleased]

Targets v1.2.

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
