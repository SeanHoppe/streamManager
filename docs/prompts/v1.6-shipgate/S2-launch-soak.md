# S2 — Launch Tier-3 ship-gate soak

**Goal:** Run 32-min Tier-3 soak on v1.6 (P0+P1+P1-fix) per ADR-17.
Produces `reports/soak-<ts>Z.md` with the v1.6 residue block populated.

## Context

- Ship branch `ship/v1.6-shipgate-finalize` rebased on main (`380f453`).
- `--cli-pool-size 2` mandatory per `feedback_soak_cli_pool_flag.md`.
- Background launch only (per `feedback_subagent_long_task_abandonment.md`):
  main thread `Bash(run_in_background=true)` + `ScheduleWakeup`. NEVER from
  a subagent.

## Steps

1. Confirm S1 done (clean tmp).
2. Verify on ship branch: `git rev-parse --abbrev-ref HEAD` → `ship/v1.6-shipgate-finalize`.
3. Launch in background:
   ```bash
   BRIDGE_API_GOV=1 python tools/soak_driver.py \
       --cli-pool-size 2 \
       --gov-db tmp/v16_soak.db \
       > tmp/v16-shipgate-soak.log 2>&1
   ```
   Use `Bash` w/ `run_in_background: true`. Capture bash shell ID.
4. `ScheduleWakeup` ~1900s (~32 min) w/ prompt referencing this checklist.

## Acceptance

- Background bash task ID returned, status `running`.
- `tmp/v16_soak.db` exists + grows (file size > 0 after first minute).
- Wakeup scheduled.

## On-done ack

`- [~] **S2 — Launch Tier-3 ship-gate soak** (bash task <id>, woke at <ts>)`

State `[~]` until wake fires; flip to `[x]` after S3 confirms artifact landed.

## Mint-new check

- If launch fails (port bound, import error, missing dep), mint `S2a-launch-debug.md`.
- If soak crashes mid-run (check log on wake), mint `S2b-soak-crash-triage.md`.
