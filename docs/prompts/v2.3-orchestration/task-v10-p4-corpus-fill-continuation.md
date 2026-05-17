# Task — v10 P4 corpus-fill continuation (🔴 Seed 5)

> Minted 2026-05-17 as part of v2.3-pm-mint PR. Comparison anchor:
> `docs/v2.3-next-steps.md` §"Seed 5 — 🔴 v10 P4 corpus-fill at 60 / 200
> (30 %)".
>
> **OPERATOR-BOUND PATH CHOICE.** Path A default; Path B alternative.

## Why

v2.2 ship-gate soak with `BRIDGE_RL_LOGGER_ENABLED=1` piggyback
produced **60 live episodes** in `tmp/rl_episodes.db` (per
`docs/v10-mvp-status.md` §P4). v10 P4 bandit trainer remains BLOCKED
on the 200-row gate (`project_v10_p4_hold_lifted.md`); 30 % is
insufficient to lift the data-side blocker even though the policy-side
blocker was lifted 2026-05-11 (issue #111).

## Path A — Continuation Tier-3 soak (default, recommended)

Fire two more Tier-3 soak runs identical in shape to the v2.2 ship-
gate soak. Each yields ~60 episodes; two runs lift count to 180,
three runs to 240 (clears the gate with margin).

### Invocation

```powershell
$env:BRIDGE_API_GOV = "1"
$env:BRIDGE_RL_LOGGER_ENABLED = "1"
$env:PYTHONPATH = "."   # required until Seed 3 lands
python -m tools.soak_driver `
  --cli-pool-size 2 `
  --ppp-auto-probe `
  --total-seconds 1800 `
  --interval-seconds 20
```

### Run 1 (this prompt fires)

- Pre-flight: capture `sqlite3 tmp/rl_episodes.db "SELECT COUNT(*)
  FROM episodes"` → expected 60.
- Fire soak.
- Post-flight: re-count → expected ~ 120.

### Run 2 (next prompt fire OR same session if Run 1 PASS)

- Pre-flight: re-count → expected ~ 120.
- Fire soak.
- Post-flight: re-count → expected ~ 180 (gate-passing).

### Optional Run 3

If episode count after Run 2 < 200, fire a third soak. ADR-5
overhead budget per soak: `tmp/rl_episodes.db` grows ~ 8 MB per
1800s soak with current envelope mix.

### Pros / Cons

- Pros: cleanest data; in-distribution; matches v2.2 ship-gate
  shape; trains on actual live envelopes.
- Cons: each soak = 30 min wall-clock; needs 2-3 fires. Costs ~ 1.5
  hr operator presence (or background-shell + monitor).

## Path B — Backfill from `tmp/soak_gov.db` via PR #156 extractor

PR #156 (`e64806e`) shipped `tools/extract_gov_to_jsonl.py`. It reads
`.claude/gov.db` (or `tmp/soak_gov.db`) and emits JSONL episode
records with the SM-self polarity-flip filter applied at SQL level.

### Invocation

```powershell
python -m tools.extract_gov_to_jsonl `
  --gov-db tmp/soak_gov.db `
  --output tmp/rl_episodes_backfill.jsonl
```

Then load the JSONL into `tmp/rl_episodes.db` via the EpisodeLogger
ingest path (verify the path exists; if not, mint a tiny loader as
part of this task).

### Pros / Cons

- Pros: faster — minutes vs hours. Uses already-captured corpus.
- Cons: depends on `tmp/soak_gov.db` retention from prior cycles
  (v2.2 ship-gate soak DB may have been rotated). Quality risk:
  governance.db rows include synthetic-load-mix patterns from
  `tools/soak_driver.py` §"synthetic load mix" which are NOT
  representative of operator-driven envelopes. The bandit trainer
  may overfit to the soak distribution.

## Recommendation

**Path A.** Cleanliness of training data wins over wall-clock time
for a research/training corpus. v10 P4 bandit policy will be live in
production; in-distribution training data lifts ship confidence.

Path B is the fallback if operator-presence for two more 30-min
soaks is not available within the v2.3 cycle window.

## Dependencies

- Seed 3 (`task-soak-driver-pythonpath-fix.md`) is a **soft
  prerequisite** — without the fix, every soak invocation needs
  `PYTHONPATH=.`. If Seed 3 lands first, drop the env line.
- Bus envelope kinds + EpisodeLogger schema unchanged from v2.2;
  no envelope-shape risk.

## Fire mode

**Background**, per CLAUDE.md §"Long-running tasks (>5 min) launch
from main thread via `run_in_background` + `ScheduleWakeup`, never
from sub-agents." Operator (or main-thread coordinator) fires;
sub-agents do not own this dispatch.

## DoD

- [ ] Run 1 fired + completed. `tmp/rl_episodes.db` episode count
      recorded in PR body / commit message.
- [ ] Run 2 fired + completed. Episode count post-Run-2 ≥ 200 OR
      Run 3 queued.
- [ ] `docs/v10-mvp-status.md` §P4 episode count line updated with
      post-fire value.
- [ ] `docs/v2.3-next-steps.md` Seed 5 row updated:
      `[x] Seed 5 — episode count post-fire = ___ / 200`.
- [ ] `docs/v2.2-backlog.md` §"Carry-forwards from v2.2" #5 row
      annotated `RESOLVED v2.3 (n/200 episodes via Path A|B)`.
- [ ] If episode count clears 200: v10 phase-4 bandit trainer
      unblocked → cross-link to `docs/prompts/v10-orchestration/
      phase-4-bandit-trainer.md` as next dispatchable.

## Refs

- `tools/soak_driver.py` (Path A driver).
- `tools/extract_gov_to_jsonl.py` (Path B extractor, PR #156).
- `docs/v10-mvp-status.md` §P4.
- `project_v10_p4_hold_lifted.md`.
- `project_v22_cycle_close.md` §"v10 P4 piggyback — useful but
  insufficient".
- `docs/prompts/v10-orchestration/task-p4-corpus-fill.md` (existing
  v10 P4 prompt — this task is its v2.3 sequel).
