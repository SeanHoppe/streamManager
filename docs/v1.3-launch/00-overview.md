# v1.3 launch — overview

Walks the path from current state (P0–P5 merged on `main`, last commit `01e749a`) to v1.3.0 tagged + ADR-5 re-baselined.

## Current state

- P0 framing — merged
- P1 driver/recorder hardening — merged
- P2 `list_active_jobs` windowed query — merged
- P3 REQUIREMENTS FR-OG audit — merged
- P4 code-quality sweep — merged
- P5 Learn Mode (5a–5e + corrective C0–C10) — merged via PR #74 (`ship/v1.3-learn-mode` → `main` at `01e749a`, 2026-05-04)
- **P6 ship-gate finalize (M1–M5) — NOT STARTED**

ADR-5 latency budget still pinned to v1.2 baseline (`docs/adr/ADR-5-latency-budget.md` §"v1.2 ship-gate baseline"). v1.3 surface (Learn Mode JSONL types `desktop_prompt` / `user_reply`, `learn_categorizer` worker, `bias_for` advisory hook, `learn_patterns_canonical` + `learn_patterns_audit` tables) not yet exercised under ship-gate soak.

## The four-step flow

1. **Start** — `01-start.md` — bring up dashboard + bus + governance hook. Verifies the v1.3 surface answers requests at all.
2. **Test** — `02-test.md` — run replay smoke (M1) and the three operator-in-the-loop methodologies from `docs/v1.3-testing.md` (scripted scenarios, expectation beacons, adversarial drift probes). Cheap before burning model quota.
3. **Monitor** — `03-monitor.md` — `tools/monitor.py` tail of WAL bus + dashboard live session pane. This is what you watch while M1/M2/M3 run.
4. **Go-live** — `04-go-live.md` — M2 cassette refresh on Haiku, M3 ship-gate soak (default model, `--cli-pool-size 2`), M4 ADR-5 v1.3 re-baseline, M5 cycle-close commit + tag `v1.3.0`.

Strict order: Start → Test → Monitor (concurrent w/ Test/Go-live) → Go-live. Do not skip M1; it is the cheap gate before burning Haiku quota on M2 or default-model quota on M3.

## Reference docs

- `docs/v1.3-task-plan.md` — phases P0–P6 (P6 deferred section is the seed for go-live)
- `docs/v1.3-testing.md` — operator-in-the-loop methodologies
- `docs/v1.2-soak-finalize.md` — template for P6 (M1–M5 task wording)
- `docs/adr/ADR-5-latency-budget.md` — current pin (v1.2); will receive v1.3 §
- `docs/adr/ADR-17-soak-tiers.md` — three-tier replay/cassette/ship-gate model

## Memory load-bearing for this work

- `feedback_soak_cli_pool_flag.md` — **always pass `--cli-pool-size 2` to soak_driver**; default 0 silently reproduces v1.0 cold-start regression
- `feedback_subagent_stale_mental_model.md` — diff PR head vs base on hot files before merge
- `feedback_no_self_monitor.md` — never run SM governance on its own JSONL/bus
