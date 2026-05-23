# POC live-monitor — next steps for the team

> Minted 2026-05-22 alongside `.claude/agents/poc-coordinator.md` + 10 subagent files + 12 game plans under `docs/poc/game-plans/`.
>
> Goal: ship a POC verdict report proving SM can monitor a non-SM Claude CLI session and surface real-time governance data + suggestions, end-to-end, within latency budget, while honoring INTENT.md product-shape requirements.

## Fleet roster — minted this session

| # | Agent | File | Game plan |
|---|---|---|---|
| C0 | `poc-coordinator` | `.claude/agents/poc-coordinator.md` | `docs/poc/game-plans/c0-poc-coordinator.md` |
| C1 | `session-target-scout` | `.claude/agents/session-target-scout.md` | `docs/poc/game-plans/c1-session-target-scout.md` |
| C2 | `env-bootstrap-validator` | `.claude/agents/env-bootstrap-validator.md` | `docs/poc/game-plans/c2-env-bootstrap-validator.md` |
| C3 | `tail-emitter-prober` | `.claude/agents/tail-emitter-prober.md` | `docs/poc/game-plans/c3-tail-emitter-prober.md` |
| C4 | `governance-trace-verifier` | `.claude/agents/governance-trace-verifier.md` | `docs/poc/game-plans/c4-governance-trace-verifier.md` |
| C5 | `dashboard-surface-prober` | `.claude/agents/dashboard-surface-prober.md` | `docs/poc/game-plans/c5-dashboard-surface-prober.md` |
| C6 | `robin` (existing) | `.claude/agents/robin.md` (unchanged) | `docs/poc/game-plans/c6-robin.md` (reuse plan) |
| C7 | `learn-mode-bias-prober` | `.claude/agents/learn-mode-bias-prober.md` | `docs/poc/game-plans/c7-learn-mode-bias-prober.md` |
| C8 | `firewall-auditor` | `.claude/agents/firewall-auditor.md` | `docs/poc/game-plans/c8-firewall-auditor.md` |
| C9 | `e2e-smoke-runner` | `.claude/agents/e2e-smoke-runner.md` | `docs/poc/game-plans/c9-e2e-smoke-runner.md` |
| C10 | `safety-priority-injector` | `.claude/agents/safety-priority-injector.md` | `docs/poc/game-plans/c10-safety-priority-injector.md` |
| C11 | `context-reload-prober` | `.claude/agents/context-reload-prober.md` | `docs/poc/game-plans/c11-context-reload-prober.md` |

## Fire order — F-POC-0..F-POC-4

Mirrors `docs/2026-05-22-task-list.md` §3 fire-order block. Updated 2026-05-22 to reflect that agents + game plans are already minted (F-POC-0 done).

| # | Step | Owner | Status |
|---|---|---|---|
| **F-POC-0** | Mint `.claude/agents/poc-coordinator.md` + 10 subagent files + 12 game plans. | main thread | **DONE 2026-05-22** |
| **F-POC-1** | Land agent files as a single docs-only PR (or operator confirms session-local use). Confirm Claude Code's `Agent` tool discovers each by name. | operator | TODO |
| **F-POC-2** | Dispatch `poc-coordinator` with task-list path + goal sentence as context. Coordinator sequences C1..C11 per §"Workflow" in its agent file. | operator OR main thread | TODO |
| **F-POC-3** | Coordinator emits `reports/poc-live-monitor-<UTC>.md`. Operator reviews; ships POC tag (e.g. `poc-live-monitor-v0.1`) on PASS. | operator | TODO |
| **F-POC-4** | POC ship feeds back into v10 MVP gauge: confirms end-to-end pipeline works against the surface that v10 P5 shadow recorder rides; closes G1–G7 from task-list §2 gap map. | operator | TODO |

## Itemized prerequisites — operator-bound

Before F-POC-2 fires, the operator MUST decide and supply:

1. **Locked target session.** Operator starts (or already runs) a live Claude CLI session in a non-SM, non-certPortal-repo cwd. The session must run Desktop sub-agent orchestration (INTENT.md §"What this project is") if §4 row C4 role-binding evidence is required. (Coordinator can still run a §3-only PASS without sub-agent orchestration — but §4 row will mark `partial-evidence-single-role` and rely on C10 negative-tests to seal role divergence.)

2. **Env mandate.** Operator sets:
   - `BRIDGE_PROJECT_SLUG` = encoded dir form of the target session's project (e.g. `C--Users-SeanHoppe-VS-certPortal` — note: certPortal **project transcript** slug is admissible; certPortal **repo source** is firewalled).
   - `BRIDGE_SM_PROJECT_SLUGS` = comma list of `streamManager` ∪ 12 encoded SM project dirs.
   - `BRIDGE_SM_SELF_SESSION_ID` = current SM session's sessionId.
   - `BRIDGE_PROJECTS_DIR` = `~/.claude/projects` (or absolute equivalent).

3. **Dashboard running.** `dashboard/server.py` started with JsonlTailWorker active. Log file path supplied to coordinator (default `dashboard.log` at repo root).

4. **C10 cassette pack.** Either `tests/cassettes/safety/p{1..5}-*.json` already recorded, OR operator pre-approves coordinator-driven recording, OR operator explicitly approves live injection at the bus boundary (NOT at the filesystem). If none of the three, C10 reports `cassette-pack-required` and coordinator emits `NO-SHIP cassette-pack-required` (recoverable).

5. **C11 target path.** Operator supplies path to a non-SM, non-firewalled project's `INTENT.md` (or other `*.md` under the rank list) that C11 may temporarily edit + revert.

## Itemized prerequisites — main-thread-bound

Main thread (this Claude Code session) owns:

1. **Tier-3 soak fire** for Path-D verification, if requested (per `feedback_subagent_long_task_abandonment.md`; subagents are forbidden `>5min` Bash). Robin (C6) ingests reports the main thread produces.
2. **Operator-turn relay** at C9. C9 emits a request; main thread fires `AskUserQuestion` (`What time did you send the test turn?` + envelope kind); relays back to C9.
3. **C8 abort signal.** If C8 mid-run HARD-FAILs, main thread cancels in-flight subagent dispatches and forces coordinator to write `NO-SHIP firewall-breach`.
4. **Path-D PR merge timing.** v2.8 P1 Path-D is in flight on `feat/v2.8-p1-path-d`. C6 robin requires Path-D landed (or local branch checked out). POC §3 pipeline does NOT require Path-D land; coordinator can ship §3 PASS while §4 C6 row pends.

## What's next for the team (itemized)

| # | Item | Action | Owner | Blocker |
|---|---|---|---|---|
| 1 | Verify agent discovery | Coordinator dispatch via Agent tool with `subagent_type=poc-coordinator`. If `Agent` tool doesn't auto-load fresh agent files mid-session, restart Claude Code OR dispatch via `general-purpose` agent with poc-coordinator's mission text inlined. | operator OR main thread | — |
| 2 | F-POC-1 land agent files | Open single docs-only PR adding 11 agent files + 12 game plans + next-steps + task-list amendment. Outside v2.8 P1 scope per `do-not-touch guard`. | operator | — |
| 3 | F-POC-2 coordinator fire | After agent discovery confirmed, dispatch `poc-coordinator` with `docs/2026-05-22-task-list.md` + this `docs/poc/next-steps.md` as context. Run in background. | main thread | item 1 |
| 4 | Operator session + env | Start a non-SM Claude CLI session; set the four `BRIDGE_*` env vars; start dashboard. | operator | — |
| 5 | Path-D PR land | `feat/v2.8-p1-path-d` complete + merged for C6 robin's shadow-side verification. (Orthogonal to §3 PASS.) | operator | per v2.8 P1 prompt |
| 6 | C10 cassette pack record | If `tests/cassettes/safety/p{1..5}-*.json` not present, record via `tools/cassette_record.py` against the safety priority prompts. **Use synthetic credentials only.** | operator OR main thread (NOT a subagent — too touchy for delegation) | — |
| 7 | C11 target path decision | Operator picks a non-SM, non-firewalled project whose `INTENT.md` (or other `*.md`) C11 may temporarily edit. | operator | — |
| 8 | F-POC-3 verdict review | Read `reports/poc-live-monitor-<UTC>.md`; tag `poc-live-monitor-v0.1` on PASS. | operator | item 3 |
| 9 | F-POC-4 MVP-gauge update | Update `docs/v10-mvp-status.md` gauge from ~80% → ~95% on combined POC ship + Path-D land. | operator OR main thread (gauge update is doc-only) | items 5 + 8 |
| 10 | (Stretch) n>1 distribution | Operator re-fires C9 K times to capture latency distribution beyond n=1. | operator | item 3 PASS |

## Coupling with v2.8 cycle (carry-forward)

- **POC does NOT block v2.8 P1 Path-D fire.** Path-D synthetic-fixture P5 is offline.
- **POC runs orthogonal to v2.8 P1.** Once Path-D lands, C6 robin re-runs with shipped `rl/shadow.py` against synthetic corpus.
- **POC validates the v10 production-runtime delivery vehicle.** v10 MVP 100% binds on this pipeline working; POC ship demonstrates SM achieves the product intent even with #112+#131+#124+#125 still blocked.

## Escalation table

| Trigger | Action |
|---|---|
| C1 NO-TARGET | HALT POC; operator starts a non-SM session and re-fires. |
| C2 polarity-flip-violation | HALT POC; operator fixes env vars and re-fires. |
| C3 no-envelopes-in-60s | Operator sends a turn in the locked session; re-fire C3. |
| C8 HARD-FAIL | ABORT POC; verdict `NO-SHIP firewall-breach`; operator investigates the breach location. |
| C10 cassette-pack-required | Operator records pack OR approves live-injection at bus boundary. |
| C11 revert-sha-mismatch | HARD FAIL; file left modified; operator inspects + manually reverts. |
| Path-D not landed at coordinator fire | §3-only PASS possible; §4 C6 row pends. Coordinator notes in verdict. |
| Agent file not discoverable by Agent tool | Restart Claude Code OR fall back to `general-purpose` agent dispatch with poc-coordinator mission inlined. |

## Refs

- `docs/2026-05-22-task-list.md` §3 (POC fleet) + §4 (INTENT conformance) — binding spec.
- `INTENT.md` — product-shape anchor.
- `docs/v10-mvp-status.md` §2 — phase ledger / MVP gauge.
- `docs/v2.8-task-plan.md` + `docs/prompts/v2.8-orchestration/phase-1-seed-v2.6-c-path-d.md` — Path-D in-flight.
- `docs/learn-mode-design.md` §3.1 + §7.2.1 — production wiring + env contract.
- `.claude/agents/robin.md` — C6 reuse anchor.
- `feedback_subagent_long_task_abandonment.md`, `feedback_certportal_dev_firewall.md`, `feedback_no_self_monitor.md`, `feedback_session_monitor_target.md` — binding constraints.
- `src/stream_manager/jsonl_tail.py:178`, `dashboard/server.py:292-331` — wire site.
- `src/stream_manager/latency_budgets.py` — `BRIDGE_FALLBACK_LATENCY_BUDGET_MS = 45_000`.
- `src/stream_manager/project_context.py`, `agent_registry.py` — INTENT hot zones (FROZEN; read-only).
- ADR-5 §"NFR-P2" — latency budget.
- ADR-18 surface freeze regime.
- ADR-9 HITL semantics.
