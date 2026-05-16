# StreamManager — Intent

> This file is intentionally short. It exists so that StreamManager's own
> governance engine can dogfood project-context loading on its own repo.
> If the file is missing, governance falls back to README/CONTRIBUTING/manifests.

## What this project is

A governance and adaptive-learning bridge between Claude Desktop sub-agent
orchestration and a Claude CLI executor. SM is the **project manager layer**:
it reads the full set of `*.md` files from the governed project, discovers the
Desktop's sub-agent topology (Prompt Constructor, Developer, Code Reviewer,
Tester, and others) via hybrid metadata + pattern inference, and governs each
agent independently per its role scope.

SM enforces two things beyond raw safety: **plan alignment** (does this
orchestration prompt move toward stated requirements?) and **cadence**
(is the session making forward progress?). Pipeline ordering remains with
Desktop orchestration. SM governs messages, not transitions.

## Safety priorities (highest first)

1. **No silent forwarding of destructive shell** — `rm -rf /`, `rm -rf ~`,
   `dd if=… of=/dev/…`, `DROP DATABASE/TABLE` must always block, regardless
   of mode.
2. **No force-push to protected branches** — `git push --force` (or `-f`)
   targeting `main` / `master` / `production` is an INTERVENE.
3. **No code-injection patterns** — `eval(`, `exec(` in untrusted message
   bodies are an INTERVENE.
4. **No credential exfiltration** — content matching obvious token / API-key
   shapes is BLOCK.
5. **API timeouts must never block forwarding.** A governance API failure
   degrades to OBSERVE; it does not stall the bridge.

## Out of scope (do not auto-allow these without scrutiny)

- Network-side modifications to `transport/` (GPL-isolated; not present here
  but stated for posterity).
- Session-token storage in plaintext anywhere on disk.
- Any operation that exfiltrates the SQLite bus DB outside the local host.

## Hot zones

- `src/stream_manager/governance.py` — the decision engine. Changes here
  affect every message.
- `src/stream_manager/message_bus.py` — the WAL bus. Schema changes need
  a migration story.
- `src/stream_manager/project_context.py` — defines what "intent" means
  for governed repos.

## Sub-agent governance principles

- Each sub-agent is governed **independently** by its role profile.
- SM MUST NOT gate one agent based on another's completion state.
- Reviewer agents: SUGGEST scope only; direct CLI execution from a reviewer → BLOCK.
- Developer agents near protected files (auth, bus schema, governance core): GUIDE → INTERVENE.
- Unknown agents: treated as `unknown` role under standard engine rules until pattern inference resolves their profile.
- Agent profiles that repeatedly exceed scope MUST escalate governance mode for that agent specifically.

## Project context loading

- All `*.md` files in the governed project root are loaded, ranked by governance relevance.
- Rank order: INTENT > REQUIREMENTS > CLAUDE.md > README > others.
- Context refreshes mid-session (10 s debounce) when any monitored file changes.
- The 400-token budget for alignment checks is consumed by ranked excerpts, not full file dumps.

## What governance should learn from this project

- `pip install -e ".[dev]"`, `pytest`, `ruff check`, and `mypy` are routine
  development commands and should promote to ALLOW patterns quickly.
- File edits under `src/stream_manager/**` are routine.
- File edits under `spikes/**` are throwaway and lower-stakes.
- Commits to feature branches are routine; force-push to `main` is not.

## UI / HITL principles

- Default dashboard is **monitor-first**: three frames (Interactive REPL, Sub-Agents,
  Background Jobs) so the human sees activity without being interrupted.
- Only true escalations (`desktop_pause`, negative regression, static-rule fire)
  may auto-foreground a frame. Lower-severity signals flag in place via badges.
- When HITL is ON, SM proposes a ranked option list from its memory; the human
  picks; SM persists the pick for next time.
- When HITL is OFF, SM posts its proposed answer to the UI as read-only;
  monitor-only by default, with a per-card opt-in to take action.
- Actionable vs informational state must be visible at a glance via paired
  label + color badges. Color alone is not a signal.

## Intentional non-goals (v1)

- Multi-tenant cloud deployment.
- Replacing Claude Code's own permission model.
- Acting as a general-purpose IDE or terminal multiplexer.
- Supporting non-Claude CLI tools (architecture allows but v1 doesn't).

---

## Current cycle posture (as of 2026-05-16)

### Shipped lineage

`v1.0 (POC) → v1.1 (cli_pool) → v1.2 (orchestration ship) → v1.3 (Learn Mode) → v1.5 (sub-phase instrumentation) → v1.6 (cli_dispatch localisation) → v1.7 (Haiku fastpath wired, DORMANT) → v1.8 (content-detection seam) → v1.9 (verdict-fallback + session watcher) → v2.0 (ADR-18 minted; Haiku + verdict-fallback ripped) → v2.1.0 (PPP audit harness ship-gate, 2026-05-11, tag 8303f38)`.

### Two parallel tracks

1. **v2.x main cycle** — governance feature stream. **v2.1.0 SHIPPED.** v2.2 cycle frame **NOT yet minted**. Two ADR-18 §"Amendments" entries queued for v2.2 P0 (feature-cycle LOC ceiling [#130]; memory pre-flight Rule 6 [#133]). Carry-forwards from v2.1 P4: dormant `JsonlTailWorker.start()` production wiring, soak-summary probe-emit counter, Sonnet 0.95 → 0.8636 alignment dip (🟡), feature-cycle LOC ceiling.
2. **v10 RL companion track** — deterministic-Python contextual bandit over L4 confidence threshold. **P0–P3 SHIPPED** (5/7 phases; ~60% MVP). P4 Q4 hold **LIFTED 2026-05-11**; real blocker is now **corpus-fill** (`rl_episodes.db` < 200 live episodes; currently 0). Live subscriber (PR #155) + backfill extractor (PR #156) just landed to enable corpus-fill paths.

### ADR-18 governance regime (in force)

- Rule 1: Surface freeze (FROZEN / EVOLVING / EXPERIMENTAL).
- Rule 2: DORMANT-N falsify-before-extend (cumulative).
- Rule 3: Consolidation cycles net LOC ≤ 0; feature cycles uncapped (amendment pending at #130).
- Rule 4: Phase budget with retroactive sub-phase amendments.
- Rule 5: Backlog hard cap.
- `WIRED_LEVER_LEDGER_COUNT` = 0; DORMANT-N gate inert.

### Held chain (v10)

`#111 (P4) READY corpus-gated → #112 (P5) BLOCKED → #131 (v10.x cycle frame) BLOCKED → #124 + #125 (ADR-18 freeze-lift deliverables) BLOCKED`.

### Hot zones (current)

- `src/stream_manager/governance.py`, `message_bus.py`, `cli_governance.py`, `model_router.py` — FROZEN pre-CLI seam until #131 cycle frame fires.
- `rl/` — v10 RL track surfaces; EVOLVING per ADR-18.
- `dashboard/server.py`, `dashboard/static/index.html` — actively touched per cycle.
- `tools/soak_driver.py`, `tools/cassette_record.py` — EVOLVING; cassette CI guard pending (#132).

### Authoritative status references

- `docs/v10-mvp-status.md` — v10 track ledger (post-hold-lift).
- `docs/v2.2-backlog.md` — v2.2 seed list (1 item: remote-CLI monitoring).
- `docs/v2.1-backlog.md` §"Carry-forwards from v2.1" — 4 v2.2 cycle-handoff items.
- `docs/jobs/MASTER.md` — cross-cycle issue tracker (note: still rows-stale on #111 hold-lift; update pending).
- `CHANGELOG.md` — Keep-a-Changelog tagged ship history.
- `docs/intent-todo-gap-2026-05-16.md` — 12-gap synthesis pass; per-gap prompts under `docs/prompts/v2.2-orchestration/`. Operator dispositions all 12 at v2.2 P0 fire (table at `docs/prompts/operator-decisions-2026-05-16.md`).
