You are implementing **Phase P4 — Code-quality sweep batch** from the streamManager v1.3 cycle.

## Branch + base

- Base: `main`.
- PR target: `main`.
- Branch: `chore/v1.3-quality-sweep` (or operator's choice).
- If `main` is unexpectedly behind v1.2 close-out (`7b7dc64`), ABORT and tell the user.

## ⚠️ CRITICAL: Do-not-touch guard

The seven items below are intentionally surface-stable. Protected symbols MUST NOT be reshaped:

| From task | File | Symbols/sections |
|-----------|------|------------------|
| J (v1.1) | `src/stream_manager/cli_pool.py` | `CliPool`, `CliWorker` |
| K (v1.1) | `src/stream_manager/desktop_command_consumer.py` | `_run_sse`, `_consume_sse_stream` |
| K (v1.1) | `dashboard/server.py` | `/api/commands/stream` |
| N (v1.1) | `src/stream_manager/wirecli.py` | `WireProtocolError`/`WireSchemaVersionError`/`WireTransportError` |
| C (v1.2) | `src/stream_manager/lifecycle_bridge.py` | `LifecycleBridge` outer surface |
| C (v1.2) | `dashboard/server.py` | `/api/lifecycle/jobs` |
| A (v1.2) | `tools/soak_driver.py` | `--cli-replay` flag |

Pre-flight grep:

```
grep -nE 'HookFolderPoller|_record_event_type|_conn\.execute|_process_one|_VALID_TRANSPORTS|Literal\["wirecli"\]|wirecli_soak_compare' src/stream_manager/lifecycle_bridge.py src/stream_manager/message_bus.py src/stream_manager/desktop_command_consumer.py src/stream_manager/cli_client.py tools/wirecli_soak_compare.py
```

If any symbol missing, STOP and report.

## Task brief

Seven 🔵 (low) carry-overs from `docs/v1.3-backlog.md` §"Carried 🔵 (low) — quality-of-life". Batched as ONE PR.

1. **HookFolderPoller rotation on Windows** (PR #43): `(st_ino, st_mtime)` is unstable on Windows. Add a content-hash sentinel of the first 64 B alongside the `(st_ino, st_mtime)` tuple, OR add a docstring note "POSIX-only rotation detection; Windows callers should not rely on rotation invalidation." Pick the docstring note unless tests can be added cheaply.

2. **`_record_event_type` heuristic** (PR #43): `tool_result + background=True` may re-order on same-tick start/end pairs. Tighten classifier — prefer explicit `event_subtype` over inference, or fall back to monotonic-counter tie-breaker on equal `ts`.

3. **Tests reach into `bus._conn.execute`** (PR #43): add a public `MessageBus.fetch_rows(query, params)` read-only helper (or `MessageBus.iter_envelopes()` iterator). Migrate three test files: `tests/test_lifecycle_bridge.py`, `tests/test_desktop_command_sse.py`, `tests/test_desktop_commands.py`.

4. **`CommandConsumer._process_one` underscore prefix** (PR #44): rename to public `process_row(...)` (preferred) OR add a comment in the test file. Pick the rename if no other internal call sites depend on the old name.

5. **`_VALID_TRANSPORTS` + `transport == "long-poll"` dual check** (PR #44): fold into a single `_REMOVED_TRANSPORTS = {"long-poll": "removed in v1.2 — use sse"}` lookup. Refactor `desktop_command_consumer.py` to consult once. Behavioral parity required.

6. **`Transport = Literal["wirecli"]` degenerate** (PR #45): keep as a `Literal` contract surface. Add a comment on the Literal definition line: `# Single-value Literal: kept as a contract surface for future transports; do not collapse to str.`

7. **`wirecli_soak_compare.py` output filename rename** (PR #45): document in the script's module docstring that pre-v1.2 reports under `soak-wirecli-json-*.md` are not auto-renamed; operators comparing across the v1.1/v1.2 boundary should grep both stems. Implementing the migration is deferred.

## DOD

- [ ] All seven items addressed in one PR
- [ ] Tests for items 1, 2, 3, 5 added or migrated; existing tests stay green
- [ ] Items 4, 6, 7 documented per scope above
- [ ] No protected-symbol drift (diff stat audit)
- [ ] `pytest -q` passes end-to-end
- [ ] `git --no-pager diff main..HEAD --stat` shows only intentionally added/modified files

## Final verification before opening PR

```
git --no-pager diff origin/main..HEAD --stat
```

Expected files (approximate):
- `src/stream_manager/lifecycle_bridge.py` (modified — items 1, 2)
- `src/stream_manager/message_bus.py` (modified — item 3 helper)
- `src/stream_manager/desktop_command_consumer.py` (modified — items 4, 5)
- `src/stream_manager/cli_client.py` (modified — item 6 comment)
- `tools/wirecli_soak_compare.py` (modified — item 7 docstring)
- `tests/test_lifecycle_bridge.py` (modified — item 3 migration)
- `tests/test_desktop_command_sse.py` (modified — item 3 migration)
- `tests/test_desktop_commands.py` (modified — item 3 migration)

If diff shows ANY change to symbols in the do-not-touch table, STOP and report — likely silent-revert.

Run `pytest -q` end-to-end. Paste tail in PR body.

Report back: PR URL, diff stat, pytest tail.
