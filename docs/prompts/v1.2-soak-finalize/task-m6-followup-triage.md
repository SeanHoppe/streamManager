You are implementing **Task M6 — Followup ledger triage** from `docs/v1.2-soak-finalize.md`.

## Master plan
Read `docs/v1.2-soak-finalize.md` first. M6 triages `docs/v1.2-followup.md`: moves 🔵 (low) items into a new `docs/v1.3-backlog.md`, keeps 🟡 (medium) items if still open. Parallel-safe with M1–M5 — does NOT block soak finalization.

## Predecessor gate
None. M6 may run any time.

## Branch + base
- Base: `main`.
- PR title: `docs(v1.3): seed backlog from v1.2 followup ledger`.

## ⚠️ CRITICAL
M6 is **documentation only**. NO code, test, or memory edits.

`docs/v1.2-followup.md` convention (see its bottom §"Convention") states the file is a running ledger — do NOT delete history. Cross-link, never excise.

## Task brief

### Steps

1. Read `docs/v1.2-followup.md`. Inventory 🔵 and 🟡 items still open under each PR header.

2. Read `docs/v1.2-task-plan.md` §"Task summary" for v1.3 framing template (mirror the table format).

3. Create `docs/v1.3-backlog.md`. Suggested skeleton:
   ```
   # v1.3 backlog

   Seed list of carry-overs from v1.2. Each item links back to the
   originating PR via `docs/v1.2-followup.md`.

   ## Carried 🟡 (medium) — still open

   - **list_active_jobs LIMIT * 4 overfetch** (PR #43, Task C)
     Replace with windowed query (latest event per `job_id` via
     correlated subquery or window function) or paginate.
     Hot session with >25 lifecycle event pairs silently drops tail.

   ## Carried 🔵 (low) — quality-of-life

   - **HookFolderPoller rotation on Windows** (PR #43, Task C)
     `(st_ino, st_mtime)` is unstable on Windows. Add content-hash
     sentinel of first 64 B or note POSIX-only in docstring.

   - **_record_event_type heuristic** (PR #43, Task C)
     Tighten classifier — `tool_result + background=True` may
     re-order on same-tick start/end pairs.

   - **Test reach into bus._conn.execute** (PR #43, Task C)
     Add public iterator on `MessageBus` or read-only fetch helper.
     Migrate callers:
     - `tests/test_lifecycle_bridge.py`
     - `tests/test_desktop_command_sse.py`
     - `tests/test_desktop_commands.py`

   - **CommandConsumer._process_one underscore prefix** (PR #44, Task D)
     Rename to public `process_row(...)` if call sites grow, or
     add comment in test file.

   - **_VALID_TRANSPORTS + transport==long-poll dual check** (PR #44, Task D)
     Future removals could share a `_REMOVED_TRANSPORTS = {name: msg}`
     lookup. Not load-bearing.

   - **Transport = Literal["wirecli"] degenerate** (PR #45, Task E)
     Single-value Literal. Either keep as contract surface (so v1.3
     re-extensions add to the Literal) or drop to `str`. Document
     decision on the Literal definition line.

   - **wirecli_soak_compare.py output filename rename** (PR #45, Task E)
     Pre-v1.2 reports under old `soak-wirecli-json-*.md` stem are
     not auto-renamed. Operators comparing across v1.1/v1.2 boundary
     should grep both stems. Document or implement migration.

   ## Convention

   Items here are seeded from `docs/v1.2-followup.md`. When picked up
   in a v1.3 task, link the new task ID and the originating ledger
   line.
   ```

4. Update `docs/v1.2-followup.md`:
   - For each carried item, append `→ v1.3 ([docs/v1.3-backlog.md](docs/v1.3-backlog.md))` to the entry line
   - Do NOT delete entries
   - Do NOT change severity emoji (🔵/🟡 stay frozen at original review time per convention)

5. Commit (single PR):
   - `docs/v1.3-backlog.md` (NEW)
   - `docs/v1.2-followup.md` (cross-link annotations)
   Commit msg:
   ```
   docs(v1.3): seed backlog from v1.2 followup ledger

   Cross-links 🔵/🟡 carry-overs from docs/v1.2-followup.md into
   the v1.3 backlog seed file. Preserves the followup ledger as
   running history per its own convention.
   ```

## Do NOT
- Edit production code, tests, or memory.
- Delete any v1.2-followup.md entries.
- Change severity emoji.
- Block on M1–M5 — M6 is parallel-safe.

## DOD
- `docs/v1.3-backlog.md` created with all carried items
- `docs/v1.2-followup.md` carried items annotated with `→ v1.3`
- No items lost across the move
- PR merged to `main`
