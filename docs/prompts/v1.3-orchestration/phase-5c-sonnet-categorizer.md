You are implementing **Phase P5c — Sonnet categorizer worker** from the streamManager v1.3 cycle (Learn Mode sub-cycle).

## Branch + base

- Base: `ship/v1.3-learn-mode`.
- PR target: `ship/v1.3-learn-mode`.
- Branch: `feat/v1.3-learn-categorizer` off `ship/v1.3-learn-mode` (or operator's choice).
- If `ship/v1.3-learn-mode` does not exist, ABORT — P5a must ship first.

## Dependencies

- P5a: `docs/learn-mode-design.md` merged on `ship/v1.3-learn-mode` — source of truth for categorizer spec.
- P5b: `desktop_prompt` + `user_reply` message types emitted by `src/stream_manager/jsonl_tail.py`.

## ⚠️ CRITICAL: Do-not-touch guard

Protected symbols:

| From task | File | Symbols/sections |
|-----------|------|------------------|
| I (v1.1) | `src/stream_manager/governance.py` | `_install_lazy_hydrator`, `GovernanceEngine.hydrated` — categorizer is OFF the verdict hot path; do not touch hydrator |
| J (v1.1) | `src/stream_manager/cli_pool.py` | `CliPool`, `CliWorker` — categorizer uses its own dedicated subprocess; do not borrow the verdict pool |
| (cross-cutting) | `src/stream_manager/cli_governance.py` | hot path — categorizer must run async/out-of-band; existing entry points untouched |
| M (v1.1) | `src/stream_manager/governance.py` | `EngineRegistry.start_refresh/stop_refresh/refresh_all/refresh_status` — categorizer hooks into lifecycle as a CONSUMER; do not modify these methods |

Pre-flight grep:

```
grep -nE 'CliPool|_install_lazy_hydrator|cli_governance|start_refresh|stop_refresh' src/stream_manager/cli_pool.py src/stream_manager/governance.py src/stream_manager/cli_governance.py
```

If any symbol missing, STOP and report.

## Task brief

New module `src/stream_manager/learn_categorizer.py` — out-of-band worker that pulls paired turns from the `messages` table and categorizes them via Sonnet using the existing subprocess pattern from `cli_governance.py` (memory `feedback_cli_over_sdk.md`).

### Steps

1. New SQLite table `learn_patterns(id, prompt_hash, category, confidence, ladder_step, last_reinforced_ts, contradicted_count)`. Add migration in `MessageBus` init (additive — does not modify existing tables).

2. New module `src/stream_manager/learn_categorizer.py`:
   - Worker pulls `desktop_prompt`/`user_reply` pairs from `messages`.
   - Calls Sonnet via `claude -p` subprocess (mirror the pattern in `src/stream_manager/cli_governance.py`).
   - Writes `learn_patterns` rows.
   - Worker lifecycle: starts/stops with `EngineRegistry.start_refresh` / `stop_refresh` lifecycle hooks (READ-ONLY consumption — do not modify these methods).

3. Worker MUST NOT block the verdict hot path. Run on its own thread/process.

### Tests

- `tests/test_learn_categorizer.py`:
  - Mock the `claude -p` subprocess call.
  - Assert worker writes a `learn_patterns` row per pair.
  - Assert worker does not block governance hot path (synthesize a verdict request mid-categorization; verify hot-path latency unaffected).

## DOD

- [ ] New `learn_categorizer.py` module
- [ ] New `learn_patterns` table created via additive migration in `MessageBus`
- [ ] Worker runs out-of-band (verified by latency test)
- [ ] `pytest -q` passes end-to-end
- [ ] No protected-symbol drift
- [ ] Single PR against `ship/v1.3-learn-mode`

## Final verification before opening PR

```
git --no-pager diff origin/ship/v1.3-learn-mode..HEAD --stat
```

Expected files:
- `src/stream_manager/learn_categorizer.py` (new)
- `src/stream_manager/message_bus.py` (modified — additive table migration only)
- `tests/test_learn_categorizer.py` (new)

If diff shows ANY change to `cli_pool.py`, `governance.py` `_install_lazy_hydrator` / `EngineRegistry.refresh_*`, or `cli_governance.py` hot-path entry points, STOP and report.

Run `pytest -q` end-to-end. Paste tail in PR body.

Report back: PR URL, diff stat, pytest tail.
