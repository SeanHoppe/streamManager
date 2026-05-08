# Master jobs list

Cross-cycle issue tracker. Per-issue detail in `docs/jobs/issue-NNN.md`.
Daily task lists in `reports/YYYY-MM-DD.md`.

Status legend: `OPEN` / `IN-PROGRESS` / `LANDED` / `HELD` / `BLOCKED`.

---

## NOW — unblocks v2.1 current cycle

| # | Title | Status | Job |
|---|---|---|---|
| #128 | v2.1 P1 PPP transport (HTTP vs MessageBus) → mint P1 prompt | DECIDED 2026-05-08 (Option B); GH OPEN til P1 PR lands | [issue-128.md](issue-128.md) |
| #118 | rl_test_helper schema-parity vs `rl/schema.sql` (parallel-safe; no v2.1 dep) | UNBLOCKED 2026-05-08 (#108 bundle-merged via #121); ready to land | [issue-118.md](issue-118.md) |

## Post v2.1 P1 land

| # | Title | Status | Job |
|---|---|---|---|
| #132 | Cassette CI guard — needs P1 envelopes as bootstrap baseline | OPEN | [issue-132.md](issue-132.md) |

## Pre v2.1 P3 prompt mint

| # | Title | Status | Job |
|---|---|---|---|
| #129 | v2.1 P3 candidate-discovery surface enum | OPEN | [issue-129.md](issue-129.md) |

## v2.2 P0 — paired ADR-18 §Amendments mint

| # | Title | Status | Job |
|---|---|---|---|
| #130 | ADR-18 feature-cycle LOC soft target (Rule 3 extension) | OPEN | [issue-130.md](issue-130.md) |
| #133 | ADR-18 Rule 6 memory pre-flight + DOD checklist | OPEN | [issue-133.md](issue-133.md) |

## v10 chain — held

`#111 → #112 → #131 → #124 + #125`. No move til #111 unholds (Q4 hold).

| # | Title | Status | Job |
|---|---|---|---|
| #111 | v10 P4 — Bandit trainer (Thompson + CMDP + promotion gate) | HELD (Q4) | [issue-111.md](issue-111.md) |
| #112 | v10 P5 — Shadow A/B + ship criteria | BLOCKED on #111 | [issue-112.md](issue-112.md) |
| #131 | v10.x cycle frame — mint trigger for #124 + #125 freeze-lift | BLOCKED on #112 | [issue-131.md](issue-131.md) |
| #124 | v10.x — wire `BRIDGE_L4_FALLBACK_CONFIDENCE` + promote `_stage_1_golden` | BLOCKED on #131 | [issue-124.md](issue-124.md) |
| #125 | v10.x — restore Ridge-Q DR estimator | BLOCKED on #131 | [issue-125.md](issue-125.md) |

## robin side track — low pri

Run when robin heavily used.

| # | Title | Status | Job |
|---|---|---|---|
| #116 | robin: PreToolUse hook enforce Bash < 5min | OPEN (low pri) | [issue-116.md](issue-116.md) |
| #117 | robin: deny direct `sqlite3` against RL DBs | OPEN (low pri) | [issue-117.md](issue-117.md) |

---

## Update protocol

- Daily list (`reports/YYYY-MM-DD.md`) carries today's targeted slice.
- This file is master roll-up. Update status column AS items land.
- Per-issue job md (`issue-NNN.md`) carries full context + acceptance.
- LANDED rows stay until next cycle close, then graduate to cycle-close memory.
