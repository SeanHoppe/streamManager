# Master jobs list

Cross-cycle issue tracker. Per-issue detail in `docs/jobs/issue-NNN.md`.
Daily task lists in `reports/YYYY-MM-DD.md`.

Status legend: `OPEN` / `IN-PROGRESS` / `LANDED` / `HELD` / `BLOCKED` / `READY` (gated on data/non-policy condition).

---

## LANDED (post-v2.1 sweep 2026-05-16)

| # | Title | Status | Job |
|---|---|---|---|
| #128 | v2.1 P1 PPP transport (HTTP vs MessageBus) | LANDED PR #138 (graduates next cycle close) | [issue-128.md](issue-128.md) |
| #129 | v2.1 P3 candidate-discovery surface enum | LANDED PR #145 (graduates next cycle close) | [issue-129.md](issue-129.md) |
| #107 | v10 P0 formal design | LANDED PR #121 | [issue-107.md](issue-107.md) |
| #108 | v10 P1 episode logging | LANDED PR #121 | [issue-108.md](issue-108.md) |
| #109 | v10 P2 corpus augmentation | LANDED PR #122 | [issue-109.md](issue-109.md) |

## NOW — parallel-safe items

| # | Title | Status | Job |
|---|---|---|---|
| #118 | rl_test_helper schema-parity vs `rl/schema.sql` | UNBLOCKED 2026-05-08; ready to land | [issue-118.md](issue-118.md) |
| #132 | Cassette CI guard — bootstrap baseline available (v2.1 P1–P3 envelopes shipped) | OPEN | [issue-132.md](issue-132.md) |

## v2.2 P0 — paired ADR-18 §Amendments mint

| # | Title | Status | Job |
|---|---|---|---|
| #130 | ADR-18 feature-cycle LOC soft target (Rule 3 extension) | OPEN | [issue-130.md](issue-130.md) |
| #133 | ADR-18 Rule 6 memory pre-flight + DOD checklist | OPEN | [issue-133.md](issue-133.md) |

## v10 chain — corpus-gated

`#111 → #112 → #131 → #124 + #125`. v10 P4 Q4 hold **LIFTED 2026-05-11**. Real blocker = corpus-fill (`rl_episodes.db` ≥ 200 live episodes; baseline 0 at 2026-05-12).

| # | Title | Status | Job |
|---|---|---|---|
| #111 | v10 P4 — Bandit trainer (Thompson + CMDP + promotion gate) | READY (corpus-gated, ≥200 ep) | [issue-111.md](issue-111.md) |
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
