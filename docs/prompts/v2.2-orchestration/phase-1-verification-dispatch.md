# v2.2 P1 — verification dispatch (reviewer subagent brief)

> Fires AFTER the implementation subagent reports back. Reviewer
> agent (`caveman:cavecrew-reviewer`) audits the branch diff against
> the dispatch DOD. Read-only. One line per finding, severity-tagged.

## Branch under review

- Repo: `C:\Users\SeanHoppe\vs\streamManager`.
- Branch: `feat/v2.2-p1-api-timeout-invariant`.
- Base sha: `main` @ `fbd0fb2`.
- Implementation dispatch:
  `docs/prompts/v2.2-orchestration/phase-1-implementation-dispatch.md`.

## Audit checklist (in order; each → severity-tagged finding or PASS)

1. **FROZEN-surface diff is empty.**
   - `git diff fbd0fb2...HEAD -- src/stream_manager/governance.py
     src/stream_manager/message_bus.py
     src/stream_manager/cli_governance.py
     src/stream_manager/model_router.py`
   - Expect: zero output. Any line = ADR-18 Rule 1 violation =
     `🛑 BLOCKING`.

2. **Net LOC ≤ 0 across consolidation buckets.**
   - `git diff --shortstat fbd0fb2...HEAD -- src/ tests/ tools/
     dashboard/`
   - Expect: insertions − deletions ≤ 0. Positive net delta =
     ADR-18 Rule 3 violation = `🛑 BLOCKING`.

3. **`tools/replay_transcript.py` deleted.**
   - `git log fbd0fb2..HEAD --diff-filter=D --name-only` should list
     it. Otherwise the deletion offset claim is unbacked = `🛑 BLOCKING`.

4. **`BRIDGE_FALLBACK_LATENCY_BUDGET_MS` is imported, not literal-pinned.**
   - Grep `tests/test_api_timeout_invariant.py` for literal `35_000`,
     `35000`, or any other ms threshold number. Expect: none. Any hit
     = the test won't auto-track ADR-5 re-baselines = `🛑 BLOCKING`
     per gap-4 spec §"Pin the threshold at promotion".
   - Confirm `from src.stream_manager.latency_budgets import
     BRIDGE_FALLBACK_LATENCY_BUDGET_MS` (or equivalent) is present.

5. **Patch target legitimacy.**
   - Confirm the test patches one of:
     - `src.stream_manager.cli_pool.CliWorker.send` (preferred per
       dispatch), or
     - `CliGovernor._runner` (declared fallback).
   - Any other patch target (e.g. raw `subprocess.Popen`,
     `subprocess.run` at module scope) is brittle per
     `feedback_soak_cli_pool_flag.md` (v1.0 cold-start precedent) =
     `⚠️ WARN`. Surface, do not auto-block.

6. **Both fault classes covered.**
   - Timeout class: at least one test path that raises
     `subprocess.TimeoutExpired` or equivalent.
   - 5xx class: at least one test path covering 500 / 502 / 503
     (parametrize or three explicit tests).
   - Missing either = `🛑 BLOCKING` per gap-4 spec §DOD.

7. **OBSERVE-degrade assertion is correct.**
   - Read `governance.py:42` (`Mode.OBSERVE = 0`) and the bridge-
     level handling of `CliGovernor.evaluate(...) == None`.
   - Confirm the test asserts the bridge-level consequence (e.g.
     `decision.mode == Mode.OBSERVE` or `decision.action == "OBSERVE"`)
     and NOT just `assert cli_governor.evaluate(...) is None`. The
     latter is necessary but not sufficient — the invariant is about
     the bridge's final verdict, not the CLI evaluator's internal
     return.
   - Insufficient assertion = `🛑 BLOCKING`.

8. **Soak-driver line is one line.**
   - Grep `tools/soak_driver.py` diff for the new line. Expect:
     a single `[soak] invariant-degrade canary: PASS/FAIL` print
     in the closing summary block. Multi-line refactor of the
     summary block = scope creep = `⚠️ WARN`.

9. **Ship-gate ledger column landed somewhere.**
   - Grep `git diff fbd0fb2...HEAD` for the string
     `invariant-degrade` outside the test and constants module.
     Expect at least one ledger render site updated.
   - Missing = `🛑 BLOCKING`.

10. **No "deferred to follow-up" notes per
    `feedback_subagent_escape_hatches.md`.**
    - Grep the impl subagent's report message + every new comment
      in the diff for: `deferred`, `follow-up`, `TODO(.*next PR)`,
      `XXX`, `FIXME`.
    - Any hit = `⚠️ WARN`. Surface to operator; not auto-blocking
      because some pre-existing TODOs may be unrelated.

11. **No new abstractions / helper modules beyond the dispatch's
    five files.**
    - `git log fbd0fb2..HEAD --diff-filter=A --name-only` should
      list exactly:
      - `src/stream_manager/latency_budgets.py`
      - `tests/test_api_timeout_invariant.py`
      - (and any docs the operator added pre-impl;
        `docs/v2.2-p1-task-list.md` +
        `docs/prompts/v2.2-orchestration/phase-1-implementation-dispatch.md`
        + `docs/prompts/v2.2-orchestration/phase-1-verification-dispatch.md`)
    - Any other new file = scope creep = `⚠️ WARN`.

12. **Firewall not violated.**
    - Grep `git diff fbd0fb2...HEAD` for `certPortal`. Expect: zero
      hits. Any hit = `🛑 BLOCKING` per project CLAUDE.md §Firewall.

## Output format

Per `caveman:cavecrew-reviewer` default:

```
path:line: <emoji> <severity>: <problem>. <fix>.
```

Plus, at the end, a one-line verdict:

- `READY-TO-MERGE` — all blocking checks PASS; warns are operator
  decision.
- `BLOCKED` — one or more `🛑 BLOCKING` findings; list them.

No praise, no scope creep, no formatting nits unless they change
meaning.
