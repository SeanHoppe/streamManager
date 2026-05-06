You are implementing **Phase P2 — External session registry + background task token registry** from the streamManager v1.9 cycle.

## Branch + base

- Base: `main` with v1.9 P0 (`docs/v1.9-cycle-frame`) merged.
- PR target: `main`.
- Branch: `feat/v1.9-session-watcher` (or operator's choice).
- P2 is independent of P1 and P3 — it may land before, after, or in parallel with them. P0 must be merged first (ensures the task plan is on `main`).

## ⚠️ CRITICAL: Do-not-touch guard

The full v1.1–v1.8 protected-symbol set in `docs/v1.9-task-plan.md` §"CRITICAL: do-not-touch list" applies. P2 must touch ONLY:

- `src/stream_manager/session_watcher.py` (NEW file)
- `dashboard/` — new external-sessions panel + bg-tokens panel only; no changes to existing panels
- `tests/test_session_watcher.py` (NEW file)

NO edits to `governance.py`, `cli_governance.py`, `model_router.py`, `learn_mode.py`, `cli_pool.py`, `tools/soak_driver.py`, `tools/cassette_record.py`, or any existing protected symbol. The new bus envelopes (`external_session_registered`, `external_session_exited`, `bg_task_output_ready`) are **session-lifecycle only** — they do not enter the cassette decision-output path. Verify after implementation:

```
grep -rn 'external_session_registered\|external_session_exited\|bg_task_output_ready' tools/cassette_record.py tools/soak_driver.py
```

Expected: zero matches. If any appear, STOP — the session-lifecycle envelopes must not affect the soak cassette schema.

## Task brief

UC-01 (2026-05-06) documented that an operator spent 7 manual steps to determine whether the certPortal Matt QA agent was healthy. SM had zero visibility into external `claude -p` subprocesses despite their session state being discoverable via `~/.claude/sessions/*.json` and `ps`. The full incident and acceptance criteria are in `docs/use-cases/uc-01-external-session-monitoring.md`.

P2 adds a read-only session observation subsystem. It is passive — it never governs or modifies external sessions, never runs the governance engine on their output, and never self-monitors SM's own sessions (per `feedback_no_self_monitor.md`).

### Deliverables

1. **`src/stream_manager/session_watcher.py`** (NEW):

   - **Poll loop:** check `~/.claude/sessions/` (resolved via `pathlib.Path.home() / ".claude" / "sessions"`) every `SESSION_POLL_INTERVAL_SECONDS` (default 5, configurable via `SESSION_WATCHER_POLL_ENV = "BRIDGE_SESSION_WATCHER_POLL_SECS"`). Runs in a daemon thread; started by the dashboard server startup hook.
   - **Session file discovery:** scan for `*.json` files in the sessions directory. For each file, read `pid`, `sessionId`, `cwd`, `entrypoint` (field names match the Claude Code session JSON schema; skip files missing any of these fields).
   - **Liveness check:** `os.kill(pid, 0)` (equivalent to `kill -0`). On `OSError` → session exited.
   - **Self-monitor guard:** before registering any session, check:
     - `session.cwd == str(pathlib.Path.cwd())` → skip silently (SM's own working directory).
     - `"stream_manager"` in `session.entrypoint` (or equivalent SM-identifying marker) → skip silently.
     - Log a debug-level message when a session is skipped, not a warning (reduces noise).
   - **State tracking:** maintain an in-memory dict `{sessionId: SessionRecord}`. `SessionRecord` stores `pid`, `cwd`, `entrypoint`, `registered_at`, `last_seen`, `state: Literal["active", "exited"]`.
   - **Bus envelope emission:**
     - `external_session_registered` — emitted once per session on first liveness confirmation. Metadata: `{"sessionId": str, "pid": int, "cwd": str, "entrypoint": str, "registered_at": str (ISO-8601)}`.
     - `external_session_exited` — emitted when liveness check fails for a previously active session. Metadata: `{"sessionId": str, "pid": int, "exit_time": str (ISO-8601)}`.
   - **Background task token extraction:** on each poll, for each active session, attempt to read the session JSONL tail (`~/.claude/sessions/<sessionId>.jsonl` if present). Scan for entries containing `backgroundTaskId`. For each new `backgroundTaskId` not yet tracked:
     - Derive output file path from the token (Claude Code stores task output at a known path — use the pattern from memory `feedback_monitoring_live_sessions.md`).
     - Record: `BgTaskRecord{taskId, output_path, originating_session, start_time, last_size_bytes=0}`.
   - **Bg task polling:** every `BG_TASK_POLL_INTERVAL_SECONDS` (default 30), check `output_path` file size for all pending `BgTaskRecord` entries. When size transitions from 0 → non-zero, emit `bg_task_output_ready` bus envelope. Metadata: `{"taskId": str, "output_path": str, "originating_session": str, "start_time": str, "ready_at": str (ISO-8601)}`. Remove from pending set after emission.
   - **Startup / shutdown:** session watcher starts via a `start_session_watcher(bus)` function called at dashboard startup. Stops cleanly on `KeyboardInterrupt` / server shutdown (daemon thread; join with 1 s timeout).

2. **Dashboard panels** — read from `SessionWatcher` state (inject via existing `app.state` or equivalent):
   - **Active external sessions panel:** table rows: sessionId (truncated), cwd (basename), entrypoint (basename), state (🟢 active / 🔴 exited), last-seen (relative time). Refresh every 5 s.
   - **Pending background tokens panel:** table rows: taskId (truncated), output_path (basename), originating_session (truncated), age (from start_time), file size (bytes). Operator can expand row to see full paths. Refresh every 30 s.

3. **Tests** (`tests/test_session_watcher.py` NEW):
   - `test_registers_external_session` — mock sessions dir with one valid JSON file, live PID → `external_session_registered` envelope emitted; session in state dict as `"active"`.
   - `test_emits_exited_on_dead_pid` — session active, then PID dies → `external_session_exited` envelope emitted; state set to `"exited"`.
   - `test_self_monitor_guard_own_cwd` — session with `cwd == os.getcwd()` → NOT registered; no envelope emitted.
   - `test_self_monitor_guard_sm_entrypoint` — session with SM-identifying entrypoint → NOT registered; no envelope emitted.
   - `test_bg_task_ready_on_size_transition` — session JSONL contains `backgroundTaskId`; output file starts at 0 bytes; poll detects non-zero → `bg_task_output_ready` emitted.
   - `test_bg_task_no_emit_while_zero` — output file remains 0 bytes across two polls → no envelope emitted.
   - `test_no_duplicate_registration` — same session polled twice while alive → `external_session_registered` emitted exactly once.
   - `test_missing_fields_skipped` — session JSON file with missing `pid` or `sessionId` → no envelope; no exception.

4. **Cassette + soak neutrality** — verify (by grep, not by running):
   ```
   grep -rn 'external_session_registered\|external_session_exited\|bg_task_output_ready' tools/cassette_record.py tools/soak_driver.py
   ```
   Expected: zero matches. Session-lifecycle envelopes must not appear in the decision-output cassette path.

### Memory feedback applied

- `feedback_no_self_monitor.md` — self-monitor guard in `session_watcher.py`; tested explicitly
- `feedback_monitoring_live_sessions.md` — session discovery via `~/.claude/sessions/`, PID validation, 0-byte task file ≠ hung
- `feedback_cassette_must_cover_new_envelopes.md` — verified: new envelopes are session-lifecycle only; cassette path unchanged; soak driver unaffected
- `feedback_subagent_stale_mental_model.md` — pre-flight grep before any edit to existing files
- `feedback_cross_pr_seam_review.md` — verify: governance hot path (evaluate → cli_governance → decision publish) has zero calls to `session_watcher` (read-only observation; no coupling)

## DOD

- [ ] `src/stream_manager/session_watcher.py` created; poll loop, liveness check, self-monitor guard, bus envelope emission, bg task token extraction all implemented
- [ ] `external_session_registered`, `external_session_exited`, `bg_task_output_ready` envelopes emitted correctly per spec
- [ ] Dashboard: active external sessions panel + pending bg tokens panel added
- [ ] `tests/test_session_watcher.py` created; all 8 scenarios pass
- [ ] `pytest tests/ -m "not slow and not alignment_eval" -q` → all pass (no v1.7/v1.8 regression)
- [ ] `grep -rn 'external_session_registered\|external_session_exited\|bg_task_output_ready' tools/cassette_record.py tools/soak_driver.py` → zero matches
- [ ] No edits to `governance.py`, `cli_governance.py`, `model_router.py`, `learn_mode.py`, `cli_pool.py`, `tools/soak_driver.py`, `tools/cassette_record.py` — verify with `git --no-pager diff origin/main..HEAD --stat -- src/stream_manager/governance.py src/stream_manager/cli_governance.py src/stream_manager/model_router.py src/stream_manager/learn_mode.py tools/soak_driver.py tools/cassette_record.py`
- [ ] `docs/use-cases/uc-01-external-session-monitoring.md` AC-1 and AC-3 both satisfied (document in PR description which AC is verified by which test)
- [ ] Single PR against `main`

## Mint-new-phase rule

After P2 implementation and before ticking DOD:
- If cassette grep shows matches: STOP — the session-lifecycle envelopes have leaked into the soak/cassette path; untangle before merging.
- If any existing fast-tier test regresses: STOP — `session_watcher.py` has a side-effect on the governance hot path; audit imports and startup hooks.
- If dashboard panels fail to render (server startup exception): STOP — debug the `app.state` injection.
- If neither: P2 is unblocked.

Report back when PR is open with: PR URL, diff stat, test count (new + total), cassette grep result (zero matches confirmation), AC-1 + AC-3 verification notes.
