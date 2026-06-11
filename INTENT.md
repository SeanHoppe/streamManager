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

## Current cycle posture (as of 2026-05-22; v2.8 Convergence cycle open)

### Shipped lineage

`v1.0 (POC) -> v1.1 (cli_pool) -> v1.2 (orchestration ship) -> v1.3 (Learn Mode) -> v1.5 (sub-phase instrumentation) -> v1.6 (cli_dispatch localisation) -> v1.7 (Haiku fastpath wired, DORMANT) -> v1.8 (content-detection seam) -> v1.9 (verdict-fallback + session watcher) -> v2.0 (ADR-18 minted; Haiku + verdict-fallback ripped) -> v2.1.0 (PPP audit harness ship-gate, 2026-05-11) -> v2.2.0 (consolidation; gap-4 API-timeout invariant + Amendment C, 2026-05-17) -> v2.3.0 (JsonlTailWorker production wiring; lever ledger 0->1, 2026-05-17) -> v2.4.0 (consolidation; Amendments D/E + #111 close, 2026-05-19) -> v2.5.1 (consolidation + corrective; n=6 alignment-eval mandate, 2026-05-20; v2.5.0 never tagged) -> v2.6.0 (feature; wall-clock instrumentation, ledger 1->2, 2026-05-20) -> v2.7.1 (corrective sub-cycle; Hatch B per-row exclusion + cli_governance timeout-tighten, ledger 2->3, 2026-05-22; v2.7.0 never tagged)`.

### Two parallel tracks

1. **v2.x main cycle** -- governance feature stream. **Latest shipped tag: v2.7.1 (2026-05-22).** v2.8 P0 Convergence-cycle frame **MINTED 2026-05-22** (feature classification recommended; operator picks at P0 fire). Cycle-tip anchor `70e23e5` (v2.8 P0 merge of PR #211; predecessor tag v2.7.1). v2.8 bundle: Path-D synthetic-fixture v10 P5 implementation (P1 landed at PR #214), step (3) env-split (expected to bump lever ledger 3 -> 4), and Seed v2.7-A-CLIP corpus measure. Carry-forward watch seeds into v2.8: Seed v2.4-E (overall p95 regression-flag 10.156s) + Seed v2.4-F (L4 promote-red 22s).
2. **v10 RL companion track** -- deterministic-Python contextual bandit over L4 confidence threshold. **P0-P3 SHIPPED**; P4 corpus gate CLEARED (200-row threshold passed at v2.3; corpus ~777 episodes at v2.7.1 Run 9). P5 entry-gate found structurally unreachable under deterministic v10.1 policy (filed #177); resolution path = ADR-18 Amendment D (v10.1-mode vs v10.3-mode gate split, landed v2.4) + parallel synthetic-fixture P5 implementation (Path-D, landing across v2.8 P1). True MVP blocker remains an empirical shadow soak closing #112 -> #131 -> #124 / #125.

### ADR-18 governance regime (in force)

- Rule 1: Surface freeze (FROZEN / EVOLVING / EXPERIMENTAL).
- Rule 2: DORMANT-N falsify-before-extend (cumulative).
- Rule 3: Consolidation cycles net LOC <= 0; feature cycles target <= 1500 LOC (soft per Amendment A; BLOCK at 1.5x); cycle-tip-anchored LOC measure per Amendment C.
- Rule 4: Phase budget with retroactive sub-phase amendments.
- Rule 5: Backlog hard cap, with Amendment E cycle-handoff exemption.
- Rule 6 (v2.2 P0): Memory pre-flight at cycle frame (INTENT.md in scope).
- Amendment D (v2.4): v10 P5 entry-gate split (v10.1-mode vs v10.3-mode).
- `WIRED_LEVER_LEDGER_COUNT` = 3 production / 0 soak entering v2.8 (first wire since v2.3; bumps at v2.6, v2.7 P1).

### Held chain (v10)

`#112 (P5) BLOCKED -> #131 (v10.x cycle frame) BLOCKED -> #124 + #125 (ADR-18 freeze-lift deliverables) BLOCKED`. (`#111` P4 CLOSED at v2.4; gate is now empirical-soak, not policy.)

### Hot zones (current)

- `src/stream_manager/governance.py`, `message_bus.py`, `cli_governance.py`, `model_router.py`, `cli_pool.py` -- FROZEN pre-CLI seam; new caller edges re-route to a #131-style freeze-lift proposal.
- `rl/` -- v10 RL track surfaces; EVOLVING per ADR-18.
- `dashboard/server.py`, `dashboard/static/index.html` -- actively touched per cycle.
- `tools/soak_driver.py`, `tools/cassette_record.py`, `tools/ship_gate_runner.py` -- EVOLVING; new bus envelope kinds require same-PR cassette + soak coverage.

### Authoritative status references

- `docs/v10-mvp-status.md` -- v10 track ledger.
- `docs/v2.8-task-plan.md` + `docs/v2.8-next-steps.md` -- current cycle task plan + carry-forwards.
- `docs/jobs/MASTER.md` -- cross-cycle issue tracker.
- `CHANGELOG.md` -- Keep-a-Changelog tagged ship history (current latest [2.7.1]).
