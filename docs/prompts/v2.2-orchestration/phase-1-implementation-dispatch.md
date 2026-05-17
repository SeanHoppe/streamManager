# v2.2 P1 — implementation dispatch (coder subagent brief)

> Self-contained brief for the coder subagent. Hand verbatim to a fresh
> Claude Code session or subagent. Inherits the gap-4 spec and the
> phase-1 deletion-offset addendum without re-stating their body.
> Deletion target already picked. LOC budget already accounted.

## Branch + base

- Repo: `C:\Users\SeanHoppe\vs\streamManager`.
- Base sha: `main` @ `fbd0fb2` (v2.2 P0 cycle frame merge).
- Branch: `feat/v2.2-p1-api-timeout-invariant` (already created;
  scaffolding commit already on it).
- ABORT if `git rev-parse HEAD` does not descend from `fbd0fb2`.

## ADR-18 boundaries (binding)

FROZEN modules (Rule 1) — do NOT edit:

- `src/stream_manager/governance.py`
- `src/stream_manager/message_bus.py`
- `src/stream_manager/cli_governance.py`
- `src/stream_manager/model_router.py`

Read access for IMPORT and PATCH TARGET resolution is fine. Editing is
the violation; importing from these in a test file is not.

Consolidation cycle (Rule 3) — net LOC ≤ 0 across `src/` + `tests/` +
`tools/` + `dashboard/`. Accounting in `docs/v2.2-p1-task-list.md`
§"LOC accounting". Pre-review estimate was ≈ −33; actual landed at
−7 (tests heavier than budget but still under the ceiling).

Firewall (project CLAUDE.md) — do NOT read anything under
`**/certPortal/**`. If a deny rule fires, surface immediately, do NOT
work around.

## Deliverables (5 files; 1 NEW, 2 MODIFY, 1 DELETE, plus optional ship-gate doc)

### 1. NEW — `src/stream_manager/latency_budgets.py`

Single-export module hosting the runtime constant required by the
gap-4 test. Lives here (NOT in `governance.py` / `model_router.py`)
because both spec-suggested homes are FROZEN per ADR-18 Rule 1.

```python
"""Latency budgets consumed by governance-bridge regression tests.

Single source of truth for any threshold a test pins to a "live"
constant. Re-baselining ADR-5 means editing this file only.
"""

# Bridge forward latency must stay below this even when the CLI
# governance API times out. Value = cli_governance.TIMEOUT_SECONDS
# (25.0) * 1.4 rounded up to the nearest 5_000 ms, giving headroom
# for the timeout + fallback path + downstream forward step.
BRIDGE_FALLBACK_LATENCY_BUDGET_MS = 35_000
```

Keep the file under 10 LOC of executable code (docstring + constant +
comment is fine). No imports from FROZEN modules at module top
level — leave the linkage to the test's runtime read so future
re-baselines have a single edit site.

### 2. NEW — `tests/test_api_timeout_invariant.py`

Two test functions, both asserting INTENT §"Safety priorities" #5:
"API timeouts must never block forwarding. A governance API failure
degrades to OBSERVE; it does not stall the bridge."

Patch target: `src.stream_manager.cli_pool.CliWorker.send`. (Note:
the gap-4 spec mentions `src.stream_manager.cli_governance.CliWorker.send`
but `CliWorker` actually lives in `cli_pool.py` — confirmed via
`src/stream_manager/cli_governance.py:257` which does
`worker.send(pool_prompt, timeout=TIMEOUT_SECONDS)` against a worker
acquired from `self._pool`.)

Fallback patch target if the pool path can't be exercised cleanly in
the test harness: monkey-patch `CliGovernor._runner` (set at
`cli_governance.py` `__init__`) with a callable that raises
`subprocess.TimeoutExpired` (timeout case) or returns a `subprocess.
CompletedProcess` with non-zero `returncode` and a 5xx-shaped stderr
payload (5xx case). The spawn path at `cli_governance.py:317`
`self._runner(cmd, ...)` is the injection site.

Tests (acceptance criteria, NOT prescriptive code):

- `test_cli_timeout_degrades_to_observe_under_budget`:
  - Construct a minimal governance session OR call
    `CliGovernor.evaluate(content)` directly (whichever exercises
    the degrade path with the least scaffolding).
  - Patched `CliWorker.send` / `_runner` raises
    `subprocess.TimeoutExpired` after `TIMEOUT_SECONDS`-equivalent
    wait (in test, use a much shorter sleep + manually raise so the
    test runs in ≤ 1s wall-clock).
  - Assert the final governance decision degrades — pool path
    returns `None` from `_evaluate_once`; verify the bridge-level
    consequence is `Mode.OBSERVE` or the verdict's `action` field
    is `"OBSERVE"`. Read `governance.py` carefully to pick the
    correct top-level assertion shape.
  - Assert wall-clock `(end - start) * 1000 < BRIDGE_FALLBACK_LATENCY_BUDGET_MS`
    where the constant is imported from
    `src.stream_manager.latency_budgets` (NOT literal-pinned).

- `test_cli_5xx_error_degrades_to_observe_under_budget`:
  - Same shape, but patched call returns a fake
    `subprocess.CompletedProcess(returncode=1, stdout=b"",
    stderr=b"...500 Internal Server Error...")` OR equivalent for
    the pool path (raise `RuntimeError("upstream 502")`).
  - Loop the three codes `500 / 502 / 503` via `pytest.mark.parametrize`
    to keep coverage explicit.
  - Same OBSERVE + bounded-latency assertions.

Total file size target ≤ 80 LOC. If scaffolding genuinely needs more,
surface in PR body — do NOT pad with helper layers.

### 3. MODIFY — `tools/soak_driver.py`

Add **one** invariant-degrade canary line to the closing summary
block (the block that already prints `[soak] ...` summary lines at
end of run). Surface a `PASS` if zero synthetic-timeout-equivalent
events were observed during the soak that produced a non-OBSERVE
verdict, `FAIL` otherwise.

For v2.2 P1 there is no real synthetic-timeout fixture firing in
soak yet — the canary line should default to `PASS` (no observations
means nothing degraded) with a code comment noting that the v2.2 P2
ship-gate is where the canary first gains real signal once the
fixture-driven probe lands.

Implementation envelope: at most 10 LOC of added Python.

### 4. MODIFY — ship-gate ledger render site

Find the ledger render site by greping for the existing latency +
alignment columns. Likely `docs/SHIP_GATE.md` (markdown table) or
`tools/soak_driver.py`'s summary table render. Add an
`invariant-degrade` column with the canary value.

If the ledger turns out to be split across multiple render sites,
update them all — but keep the cumulative addition under 10 LOC.

### 5. DELETE — `tools/replay_transcript.py` (121 LOC offset)

Single-file `git rm`. Investigator confirmed zero references in
`tests/`, `src/`, `pyproject.toml`, `.github/workflows/`, or any
imports across the repo. Already accounted as the deletion offset
in `docs/v2.2-p1-task-list.md`.

Before `git rm`, do a confirmation pass: ripgrep `replay_transcript`
across the whole repo (exclude `.git/`). If you find ANY reference
other than this dispatch doc / task-list / changelog entries, STOP
and surface to operator.

## Out of scope (DO NOT do)

- DO NOT edit any FROZEN module.
- DO NOT add a new envelope kind to the bus.
- DO NOT add new soak-driver flags / CLI surface.
- DO NOT add new ADR entries.
- DO NOT touch the dashboard.
- DO NOT add helper libraries / utility classes / abstractions
  beyond the four deliverables. The test should be flat, the
  driver line should be one line, the constants module is one
  constant.
- DO NOT add "deferred to follow-up" notes per
  `feedback_subagent_escape_hatches.md`. If a deliverable cannot
  land in this PR, STOP and surface for operator decision — do NOT
  ship partial.

## Pre-implementation verification (run first, before any edit)

1. `git rev-parse HEAD` — confirm descends from `fbd0fb2`.
2. `git status` — confirm clean working tree apart from the
   scaffolding commit that minted this dispatch doc.
3. Confirm `CliWorker` lives in `src/stream_manager/cli_pool.py`
   (grep `class CliWorker`); confirm `worker.send(...)` call site
   in `cli_governance.py:257`.
4. Confirm `Mode.OBSERVE` is the degrade verdict — read
   `governance.py:42` (enum definition) and the bridge-level path
   that handles `CliGovernor.evaluate(...) == None`.
5. Confirm `BRIDGE_FALLBACK_LATENCY_BUDGET_MS` does NOT already
   exist (`rg BRIDGE_FALLBACK_LATENCY_BUDGET_MS src/ tests/ tools/`
   should be empty before your edit).

## DOD (mirror v2.2-p1-task-list.md)

- [ ] `src/stream_manager/latency_budgets.py` exists w/ single
      `BRIDGE_FALLBACK_LATENCY_BUDGET_MS` export.
- [ ] `tests/test_api_timeout_invariant.py` has both test functions,
      both assert OBSERVE-degrade + bounded latency under the LIVE
      constant.
- [ ] `pytest tests/test_api_timeout_invariant.py -v` passes locally
      in ≤ 5 seconds wall-clock total.
- [ ] `tools/soak_driver.py` summary block has one new line
      `[soak] invariant-degrade canary: PASS/FAIL` printing the
      canary value.
- [ ] Ship-gate ledger render site has new `invariant-degrade`
      column.
- [ ] `tools/replay_transcript.py` deleted.
- [ ] `git diff --shortstat fbd0fb2...HEAD -- src/ tests/ tools/
      dashboard/` shows net ≤ 0 LOC.
- [ ] `git diff fbd0fb2...HEAD -- src/stream_manager/governance.py
      src/stream_manager/message_bus.py
      src/stream_manager/cli_governance.py
      src/stream_manager/model_router.py` returns empty (FROZEN
      surfaces untouched).
- [ ] Commit on `feat/v2.2-p1-api-timeout-invariant` with a single
      well-scoped message; no force-push, no rebase, no amend.

## Report back

Reply with:

- Commit sha(s) added to the branch.
- Output of `git diff --shortstat fbd0fb2...HEAD -- src/ tests/
  tools/ dashboard/`.
- Output of `pytest tests/test_api_timeout_invariant.py -v` tail.
- One-line statement of which patch target you used (pool vs spawn)
  and why.
- Any DOD item you could NOT meet (STOP + surface, do NOT ship
  partial).
