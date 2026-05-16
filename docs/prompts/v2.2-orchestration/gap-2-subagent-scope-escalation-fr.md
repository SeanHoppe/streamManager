# Gap 2 — Sub-agent scope-escalation FR (v2.2 P0 phase candidate)

> Minted from `docs/intent-todo-gap-2026-05-16.md` §Gap 2. **TWO
> gates** before promotion: (a) v2.2 cycle type = feature AND (b)
> ADR-18 Rule 1 carve-out for FROZEN `governance.py`. Operator
> records both decisions at P0.

## Why

INTENT.md §"Sub-agent governance principles" enumerates three
escalation paths that today have ZERO enforcement code or test
coverage:

1. "Agent profiles that repeatedly exceed scope MUST escalate
   governance mode for that agent specifically."
2. "Reviewer agents: SUGGEST scope only; direct CLI execution from
   a reviewer → BLOCK."
3. "Developer agents near protected files: GUIDE → INTERVENE."

PR #154 (robin self-vs-other monitoring) is **monitoring**, not
scope-escalation enforcement. Different problem.

## Phase shape (3 deliverables)

### 1. FR-sub-agent-scope-N requirement

Add `FR-sub-agent-scope-N` row(s) to `docs/REQUIREMENTS.md`:

- Define "repeatedly exceed scope" — count threshold + rolling
  window per `agent_type`.
- Define escalation graduation table: which mode bumps trigger at
  what count.
- Pin (2) + (3) as static rules (no count threshold — first offense
  triggers).

Suggested defaults (operator finalizes at P0):

- Reviewer + CLI execution = BLOCK on first offense (static rule).
- Developer + protected-file pattern = GUIDE → INTERVENE on first
  offense (static rule).
- General scope-overrun = ≥ 3 offenses in 24-hour rolling window
  → mode bump (`OBSERVE → GUIDE`, `GUIDE → INTERVENE`).

### 2. Escalation hook + agent_profiles persistence

- New column on `agent_profiles` table: `escalated_mode TEXT`
  (NULL = use default; non-NULL = governance.evaluate uses
  escalated value for this agent_type).
- Migration: standard `bus.upgrade_schema_if_needed` shape.
- Hook: in `governance.evaluate`, after baseline verdict computed,
  if `agent_type` row has `escalated_mode`, override mode field.
- Decay: optional auto-reset after N idle days (operator decides
  at P0 — recommend defer to v2.3).

### 3. Regression tests

`tests/test_subagent_scope_escalation.py`:

- Fixture: synthesise reviewer-agent JSONL with direct `bash`
  CLI fire pattern → assert governance verdict = BLOCK.
- Fixture: developer-agent edit pattern against `governance.py` /
  `message_bus.py` (per INTENT §"Hot zones") → assert mode bumps
  GUIDE → INTERVENE.
- Fixture: 3 scope-overruns in window → assert `escalated_mode`
  persisted; 4th overrun observed at escalated tier.

## Cross-refs

- INTENT §"Sub-agent governance principles" — all 3 rules verbatim.
- `src/stream_manager/governance.py` — FROZEN surface (Rule 1
  carve-out required).
- `src/stream_manager/agent_profiles.py` (if module exists) OR
  `message_bus.py` schema migration site.
- PR #154 (robin monitoring) — adjacent feature; NOT a substitute.
- Gap doc §"Gap 2 — Sub-agent scope-escalation FR".

## Promotion criteria (BOTH must hold)

1. Operator confirms v2.2 cycle type = **feature**.
2. Operator records ADR-18 Rule 1 carve-out for `governance.py`
   touch at P0 PR body (precedent: any structural edit to evaluate
   path needs explicit operator OK).

## DOD

- [ ] `FR-sub-agent-scope-N` rows in `docs/REQUIREMENTS.md`.
- [ ] `agent_profiles.escalated_mode` column + migration shipped.
- [ ] `governance.evaluate` escalation hook landed.
- [ ] Three regression tests landed (reviewer-CLI, dev-protected,
      count-threshold).
- [ ] ADR-18 Rule 1 carve-out text in v2.2 P0 PR body verbatim.
- [ ] Memory: `project_v22_subagent_scope_escalation.md` or fold-in.
- [ ] Gap doc §Gap 2 marked LANDED.

## ADR-18 posture

- Touches FROZEN `governance.py`. **Hard gate** — operator must
  carve out at P0 explicitly. No silent FROZEN edit.
- New column on `agent_profiles` = EVOLVING surface change. Schema
  migration well-trodden (precedent: v2.1 P1 `provenance_assertions`).
- LOC estimate: ~120 src + ~150 tests = ~270 LOC. Material slice of
  feature-cycle LOC budget per Amendment A (#130 1500 soft target).
- DORMANT-N: at ship, mode-override hook starts wired-active (not
  DORMANT) since tests demand fire on first reviewer-CLI offense.
  `WIRED_LEVER_LEDGER_COUNT`: 0 → 1 (or 0 → 2 if combined with
  gap-1 detector).
