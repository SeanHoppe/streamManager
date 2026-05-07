You are implementing **Phase P1 — cli_pool worker A/B (per-turn isolation lever revival)** for the streamManager v2.0 cycle.

## Branch + base

- Base: `main` (after v2.0 P0 is merged — ADR-18 + task plan must
  exist before this phase opens).
- PR target: `main`.
- Branch: `feat/v2-p1-cli-pool-ab` (or operator's choice).
- If ADR-18 does not exist on `main`, ABORT and run P0 first.

## Context (load-bearing — read before coding)

v1.9 P1a falsified the corpus-weakness hypothesis: a fresh-process
Haiku BLOCKs 100% of wrapped destructive prompts at confidence ≥ 0.85.
v1.9 ship-gate still measured `cli_dispatch_fallback_ms` p95 = 0.00 ms
(DORMANT-2). Remaining hypothesis: cli_pool's long-lived stream-json
workers, reused across ~30 turns per soak, bias Haiku toward
conversational ALLOW on later destructive prompts despite per-turn
`session_id` rotation.

v2.0 P1 tests this directly via worker-recycle cadence A/B.

## References

- `docs/v2.0-backlog.md` §"🟡 v1.9 P1b — cli_pool worker per-turn
  isolation A/B" — full investigation scope
- `docs/adr/ADR-18-mvp-surface-freeze.md` Rule 1 (cli_pool FROZEN —
  additive only) + Rule 2 (DORMANT-N counter)
- `src/stream_manager/cli_pool.py` — `CliPool`, `CliWorker` lifecycle
- `src/stream_manager/cli_governance.py` — UNCHANGED in P1
- `tools/soak_driver.py` — adds `--worker-recycle-every-n` pass-through
- `tools/p1a_haiku_probe.py` — `_scrubbed_env`, `_wrap_user_prompt`
  helpers reused for fresh-process control arm
- `reports/p1a-corpus-haiku-verdicts-20260507T083813Z.md` — 100% BLOCK
  fresh-process baseline
- `reports/soak-20260507T084933Z.md` — v1.9 ship-gate baseline (status
  quo Arm A reference numbers)

## Do-not-touch guard

`CliPool.__init__` extends with `worker_recycle_every_n: int | None
= None` (default `None` = byte-identical v1.9 behaviour). Any other
signature change to `CliPool`, `CliWorker`, `CliWorker.send`, or
`.bridge/cli-pool.pids` → STOP. Bus envelope schemas UNCHANGED.

Verify before commit:

```
git --no-pager diff origin/main..HEAD -- src/stream_manager/cli_pool.py | head -120
```

Should show only additive changes inside `__init__` and a recycle-check
helper. The recycle decision lives in `CliPool` (worker pool manager),
NOT inside `CliWorker.send`.

## Scope

1. **`CliPool.__init__` kwarg**: add
   `worker_recycle_every_n: int | None = None`. Store on the pool
   instance. When `None`, recycle never fires (status quo).
2. **Recycle implementation**: track per-worker turn counter inside
   the pool. After each successful `send`, if counter ≥ N, kill the
   worker (existing teardown path) and respawn fresh. Counter resets
   on respawn. Implementation must be inside `CliPool` only;
   `CliWorker.send` signature unchanged.
3. **`tools/soak_driver.py --worker-recycle-every-n`**: forward to
   `CliPool` constructor. Default unset.
4. **Tests**:
   - `tests/test_cli_pool.py`: extend with `test_recycle_none_is_status_quo`
     (asserts no respawn at any send count when kwarg is `None`) +
     `test_recycle_every_n_respawns_after_n_sends` (parametrised over
     N ∈ {1, 5}).
   - DO NOT modify any existing test in `test_cli_pool.py`.
5. **A/B soak runs** (60 events, `--cli-pool-size 2`):
   - Arm A: `--worker-recycle-every-n` UNSET (control / status quo)
   - Arm B: `--worker-recycle-every-n 1`
   - Arm C: `--worker-recycle-every-n 5`
   - Arm D: `--worker-recycle-every-n 10`
   - Per-arm metrics: `cli_dispatch_fallback_ms` p95 + fire rate,
     `cli_pool_send_ms` p95, spawn-overhead delta vs Arm A, overall
     p95, ALLOW p95, L2/L3 verdict distribution on `_L2_L3_TRIGGER`
     prompts.
   - **Total wall-clock: ~128 min (4 arms × ~32 min)**. Launch each
     arm via `run_in_background` + `ScheduleWakeup` per
     `feedback_subagent_long_task_abandonment.md`. Do NOT chain four
     soaks in a single Bash call (subagent abandonment + 5-min cache
     window cost). Sequential launches from the main thread; each
     arm's wakeup re-enters at PID-exit detection.
6. **Report**: author `reports/v2-p1-cli-pool-ab-<UTC-timestamp>.md`.
   Sections:
   - Setup (commit SHA, soak parameters, four-arm matrix)
   - Per-arm results table
   - Fire-rate outcome (any arm > 0%? which arm?)
   - Recommendation: keep status quo / promote one cadence to default
     / rip fallback path
   - Cite `reports/p1a-corpus-haiku-verdicts-20260507T083813Z.md` as
     fresh-process control baseline
7. **ADR-5 update**: append v2.0 P1 row to lever-effect ledger with
   per-arm fire rates.

## Decision criteria (binding for P3)

- **Any arm > 0% fire rate**: P1 outcome = "fallback revived". P3
  keeps fallback path. ADR-18 counter resets immediately on probe
  fire (per ADR-18 Rule 2 §"What counts as a strike"). The arm with
  best (fire-rate × lowest spawn overhead) is recorded as the
  recommended cadence in ADR-5 lever-effect ledger and forwarded by
  `tools/soak_driver.py --worker-recycle-every-n` at ship-gate.
  `CliPool.__init__` default stays `None` permanently — no FROZEN
  signature default flip (ADR-18 Rule 1).
- **All arms = 0% fire rate**: P1 outcome = "warm-process hypothesis
  falsified". Lever stays DORMANT-2 by counter (A/B is not a Tier 3
  strike) but P3 invokes *anticipatory rip authority* (ADR-18 Rule 2
  §"What counts as a strike") and rips both. ADR-5 records the
  falsification.

**Arm-differentiation note.** Arm B (recycle-every-1) ≈ fresh-process
control — fire there confirms fresh-process matters but does not
differentiate cli_pool warm-process bias from generic Claude
variance. Differentiation comes from Arm C / D fire (partial pool
reuse). Report MUST call out which arms fired separately; "any arm
fired" is the binding revival criterion but the recommended cadence
should weight C/D over B-only fire when interpreting causation.

## DOD

- [ ] `CliPool.__init__` accepts `worker_recycle_every_n` kwarg;
      `None` default preserves byte-identical v1.9 behaviour
- [ ] `tools/soak_driver.py --worker-recycle-every-n` flag forwards
      to pool
- [ ] Two new tests (default-no-respawn + recycle-every-N-respawns)
- [ ] Four-arm soak run; per-arm reports under `reports/`
- [ ] `reports/v2-p1-cli-pool-ab-<timestamp>.md` consolidated report
      authored
- [ ] ADR-5 lever-effect ledger updated
- [ ] PR LOC delta ≤ 100 net add in `src/` + `tests/` + `tools/`
- [ ] Alignment-eval `--ci-gate` exit 0 (no regression from kwarg
      addition)
- [ ] Single PR against `main`

## Subagent abandonment guard

Soak runs are 32+ minutes wall-clock. Per
`feedback_subagent_long_task_abandonment.md`: launch the soak from
the main thread with `run_in_background` + `ScheduleWakeup`, NOT from
a subagent. Subagents abandon long-running Bash > 5 min.

Use the Monitor template from `feedback_monitoring_live_sessions.md`
to detect PASS / FAIL / panic / PID-exit during the soak.

## Mint-new-phase rule

If during P1 implementation a fifth A/B arm seems necessary (e.g.
recycle-every-2, every-20), STOP — phase budget is at cap (3 work
phases per ADR-18 Rule 4). Run only the four codified arms; new
investigation lever lands in v2.1 backlog.

If `cli_pool_send_ms` p95 in any non-control arm exceeds 12 s
(ADR-5 budget), do NOT propose tightening the budget — record the
trade-off in the report and let P3 weigh it.

Report back when PR is open with: PR URL, diff stat, file list,
`reports/v2-p1-cli-pool-ab-<timestamp>.md` path, and the binding
fire-rate outcome (revival or falsification).
