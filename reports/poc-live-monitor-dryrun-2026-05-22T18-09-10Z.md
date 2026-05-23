# POC live-monitor — DRY-RUN verdict — 2026-05-22T18:09:10Z

> **Dispatch mode:** poc-coordinator paper exercise. NO live subagent dispatch;
> NO live-fire of C1..C11. Prerequisite-state audit + fire-readiness matrix only.
> Coordinator running under `general-purpose` fallback (per F-POC-1 item 1 in
> `docs/poc/next-steps.md`: "If Agent tool doesn't auto-load fresh agent files
> mid-session, restart Claude Code OR dispatch via general-purpose agent with
> poc-coordinator's mission text inlined").

## 1. Inputs

Paths read this session:

- `C:\Users\SeanHoppe\vs\streamManager\docs\2026-05-22-task-list.md`
  - Anchor quote (§3 design principles, row 1): "One coordinator owns the verdict. Subagents return artefacts + PASS/FAIL rows; the coordinator gates ship/no-ship."
- `C:\Users\SeanHoppe\vs\streamManager\docs\poc\next-steps.md`
  - Anchor quote (§"Fleet roster"): "Minted 2026-05-22 alongside `.claude/agents/poc-coordinator.md` + 10 subagent files + 12 game plans under `docs/poc/game-plans/`."
- `C:\Users\SeanHoppe\vs\streamManager\.claude\agents\poc-coordinator.md`
  - Anchor quote (§"Mission"): "Ship a verdict report proving SM can monitor a non-SM Claude CLI session end-to-end and surface real-time governance data + suggestions, within latency budget, while honoring INTENT.md product-shape requirements."
- `C:\Users\SeanHoppe\vs\streamManager\INTENT.md`
  - Anchor quote (§"Safety priorities" #5): "API timeouts must never block forwarding. A governance API failure degrades to OBSERVE; it does not stall the bridge."
- `C:\Users\SeanHoppe\vs\streamManager\docs\v10-mvp-status.md`
  - Anchor quote (§2 aggregate read): "v10 MVP completeness: ~80% (track ships at v10.0; P5 implementation deferred to v2.7 via Seed v2.6-C — 4th consecutive cycle deferred; v10.1+ is post-MVP refinement)."

Glob/state inspections (no certPortal repo paths touched; firewall honored):

- `.claude/agents/*.md` — 12 files present (poc-coordinator + 10 + robin).
- `docs/poc/game-plans/*.md` — 12 files present (c0..c11).
- `tests/cassettes/safety/*.json` — 0 files (NOT recorded).
- `reports/poc-*` — 0 files (no prior POC verdict report).
- `rl/shadow.py` + `rl/stop_conditions.py` — present in working tree (per `git status`; v2.8 P1 Path-D drafts).
- `dashboard.log` — NOT present in repo root.
- `$env:BRIDGE_PROJECT_SLUG / BRIDGE_SM_PROJECT_SLUGS / BRIDGE_SM_SELF_SESSION_ID / BRIDGE_PROJECTS_DIR` — ALL UNSET in this shell.
- `~/.claude/sessions/` — 8 session JSON entries (`18108`, `20124`, `20476`, `24036`, `27464`, `27984`, `4916`, `7924`); PID `27984` matches task-list snapshot as `self`; PID `4916` cwd is firewalled (`certPortal\oversight`). No attachment performed (dry-run).
- `gh pr list` — only PR #154 OPEN (unrelated docs PR); no v2.8 P1 Path-D PR yet open (Path-D currently working-tree only on branch `feat/v2.8-p1-path-d`).

## 2. Prerequisite state table

Source: `docs/poc/next-steps.md` §"Itemized prerequisites — operator-bound" (5 items, OP-1..OP-5) and §"Itemized prerequisites — main-thread-bound" (4 items, MT-1..MT-4). Anchor quote: "Before F-POC-2 fires, the operator MUST decide and supply".

| ID | Source row | Description | Status | Evidence |
|---|---|---|---|---|
| OP-1 | operator-bound 1 | Locked target = live non-SM, non-certPortal-repo-cwd Claude CLI session, ideally running Desktop sub-agent orchestration | NOT-MET | Only non-self busy session at task-list snapshot is PID 4916 (certPortal-oversight cwd, firewalled). No admissible non-SM non-firewalled live session enumerated in `~/.claude/sessions/`. |
| OP-2a | operator-bound 2 | `BRIDGE_PROJECT_SLUG` set to encoded non-SM dir | NOT-MET | Env var UNSET in this shell. |
| OP-2b | operator-bound 2 | `BRIDGE_SM_PROJECT_SLUGS` set (streamManager ∪ 12 encoded SM dirs) | NOT-MET | Env var UNSET. |
| OP-2c | operator-bound 2 | `BRIDGE_SM_SELF_SESSION_ID` set to current SM sessionId | NOT-MET | Env var UNSET. |
| OP-2d | operator-bound 2 | `BRIDGE_PROJECTS_DIR` set | NOT-MET | Env var UNSET. |
| OP-3 | operator-bound 3 | `dashboard/server.py` running with JsonlTailWorker active; log path supplied | NOT-MET | `dashboard.log` not present at repo root; no running dashboard process verified (dry-run cannot probe). |
| OP-4 | operator-bound 4 | `tests/cassettes/safety/p{1..5}-*.json` recorded OR operator pre-approved record path OR live-injection approval | NOT-MET | Glob `tests/cassettes/safety/*.json` returned 0 files. |
| OP-5 | operator-bound 5 | C11 target `INTENT.md` (or other `*.md`) path supplied | NOT-MET | No path supplied in dispatch context. |
| MT-1 | main-thread-bound 1 | Tier-3 soak fire for Path-D verification (main thread owns; subagents forbidden `>5min` Bash) | UNKNOWN | Not required for §3 PASS; v2.8 P1 still in-flight (working-tree only; no PR open). |
| MT-2 | main-thread-bound 2 | Operator-turn relay capability at C9 (`AskUserQuestion`) | UNKNOWN | Capability exists in main-thread harness; not exercised in dry-run. |
| MT-3 | main-thread-bound 3 | C8 abort-signal handler (cancel in-flight subagents on firewall HARD-FAIL) | UNKNOWN | Main-thread responsibility; not invoked in dry-run. |
| MT-4 | main-thread-bound 4 | Path-D PR merge timing (`feat/v2.8-p1-path-d` landed or local checkout) | NOT-MET (partial) | Branch checked out (current branch); files `rl/shadow.py` + `rl/stop_conditions.py` present per `git status`; no PR opened yet; not merged. §3 pipeline does not block on this per next-steps. |

**Summary:** 8 NOT-MET (operator-bound), 0 MET, 4 UNKNOWN (main-thread-bound, deferred to fire-time).

## 3. §3 pipeline row table

Source: `docs/2026-05-22-task-list.md` §3 "Fleet roster" + DoD checklist. Anchor quote: "Coordinator pick: option chosen = NEW `poc-coordinator` subagent (not extending robin)."

Expected output path convention: `reports/poc-live-monitor-<UTC>.md` (per `.claude/agents/poc-coordinator.md` §"Workflow" step 9).

| # | Subagent | Fire-readiness | Blocking prerequisites | Expected output path |
|---|---|---|---|---|
| C1 | `session-target-scout` | BLOCKED | OP-1 (no admissible non-SM non-firewalled live session). Per escalation table: "C1 NO-TARGET → HALT POC; operator starts a non-SM session and re-fires." | Lock-in record `{pid, sessionId, cwd, projectSlug}` written into the verdict-report row C1 cell. |
| C2 | `env-bootstrap-validator` | BLOCKED | OP-2a, OP-2b, OP-2c, OP-2d (all four `BRIDGE_*` env vars UNSET); also OP-3 (dashboard log line required for env-cross-check). |  Bootstrap PASS/FAIL row + env snapshot in verdict report. |
| C3 | `tail-emitter-prober` | BLOCKED | C1 (gated), C2 (gated), OP-1, OP-3 (need live envelopes from JsonlTailWorker reading target slug). | Envelope-emission PASS/FAIL + per-source-slug counts in verdict report. |
| C4 | `governance-trace-verifier` | BLOCKED | C3 PASS (gated). | Trace PASS/FAIL + decision_id in verdict report. |
| C5 | `dashboard-surface-prober` | BLOCKED | C4 PASS (gated); OP-3 (dashboard running). | Surface PASS/FAIL + tail-to-surface p95 latency reading in verdict report. |
| C6 | `robin` (reuse for shadow side) | DEFERRED | MT-4 (Path-D PR not merged; can still run against working-tree drafts but C6 game plan calls for shipped artefact). Per task-list §3 "Coupling with v2.8 cycle": "Once Path-D lands, C6 robin re-runs with the shipped `rl/shadow.py` against the synthetic corpus." | Shadow-side PASS/FAIL verdict + invariant readings. |
| C7 | `learn-mode-bias-prober` | BLOCKED | C3 PASS (needs ≥ 1 desktop_prompt / user_reply pair from target session for patterns-table write). | Bias-applied PASS/FAIL + pattern_id in verdict report. |
| C8 | `firewall-auditor` | READY | None (parallel-audit role; runs continuous from coordinator-start). Per coordinator workflow step 4: "Dispatch C8 firewall-auditor in parallel with all subsequent agents." | Firewall PASS/FAIL audit row in verdict report. |
| C9 | `e2e-smoke-runner` | BLOCKED | C3/C4/C5 PASS (gated; runs them in sequence with timing instrumentation); MT-2 (operator-turn relay required); OP-1; OP-3. | E2E latency reading p50/p95 + per-stage breakdown in verdict report. |

**Tally:** READY = 1 (C8) / BLOCKED = 7 (C1, C2, C3, C4, C5, C7, C9) / DEFERRED = 1 (C6).

## 4. §4 INTENT conformance row table

Source: `docs/2026-05-22-task-list.md` §4 "INTENT.md → POC DoD mapping" (8 rows) + §"New subagents (C10 + C11)" + §"Revised POC DoD (additive)" (8 additive items). Anchor quote: "`INTENT.md` is the load-bearing 'what is SM' doc and the authoritative anchor for what MVP 100% must demonstrate."

INTENT-anchor quotes (verbatim from `INTENT.md`):
- §"What this project is" L9-11: "SM is the project manager layer ... reads the full set of `*.md` files from the governed project, discovers the Desktop's sub-agent topology ... and governs each agent independently per its role scope."
- §"Safety priorities" #5 L33-34: "API timeouts must never block forwarding. A governance API failure degrades to OBSERVE; it does not stall the bridge."
- §"Sub-agent governance principles" L53-58: "Each sub-agent is governed independently by its role profile."
- §"Project context loading" L62-65: "Rank order: INTENT > REQUIREMENTS > CLAUDE.md > README > others. Context refreshes mid-session (10 s debounce) ... 400-token budget."
- §"UI / HITL principles" L77-86: "Default dashboard is monitor-first: three frames (Interactive REPL, Sub-Agents, Background Jobs) ... paired label + color badges."

| # | INTENT section | Owner subagent | Fire-readiness | Blocking prerequisites |
|---|---|---|---|---|
| I1 | §"What this project is" — Desktop sub-agent topology discovered + role-bound governance | C1 (extend) | BLOCKED | OP-1 (target must run Desktop sub-agent orchestration; absent live session, no topology to record). Per next-steps "without sub-agent orchestration ... §4 row will mark `partial-evidence-single-role`". |
| I2 | §"Plan alignment + cadence" — alignment_score + cadence band surfaced on decision row | C4 (extend) | BLOCKED | C4 BLOCKED (chain). Cannot extend an unfired probe. |
| I3 | §"Safety priorities" #1 (destructive shell BLOCK) | C10 | BLOCKED | OP-4 (cassette pack `tests/cassettes/safety/p1-*.json` not recorded; no live-injection approval). |
| I4 | §"Safety priorities" #2 (force-push protected branches INTERVENE) | C10 | BLOCKED | OP-4 (cassette pack `tests/cassettes/safety/p2-*.json` not recorded). |
| I5 | §"Safety priorities" #3 (eval(/exec( INTERVENE) | C10 | BLOCKED | OP-4 (cassette pack `tests/cassettes/safety/p3-*.json` not recorded). |
| I6 | §"Safety priorities" #4 (credential shapes BLOCK) | C10 | BLOCKED | OP-4 (cassette pack `tests/cassettes/safety/p4-*.json` not recorded; synthetic-only shape required). |
| I7 | §"Safety priorities" #5 (API timeout → OBSERVE, not stall; latency p95 ≤ `BRIDGE_FALLBACK_LATENCY_BUDGET_MS = 45_000` ms) | C10 | BLOCKED | OP-4 (cassette pack `tests/cassettes/safety/p5-*.json` not recorded; timeout-simulation invocation required). |
| I8 | §"Sub-agent governance principles" — role-bound divergence (reviewer-vs-developer same prompt → different verdicts) | C4 + C10 | BLOCKED | C4 BLOCKED (chain) AND C10 BLOCKED (cassette pack). Compound block. |
| I9 | §"Project context loading" — 10 s debounce reload + 400-token budget + INTENT > REQUIREMENTS > CLAUDE.md > README rank order | C11 | BLOCKED | OP-5 (no C11 target path supplied); also C5 PASS gate (dashboard reload signal observability). |
| I10 | §"UI / HITL principles" — 3-frame monitor-first dashboard + paired label+color badges + HITL ranked-option list rendering | C5 (extend) | BLOCKED | C5 BLOCKED (chain); OP-3 (dashboard must be running). |
| I11 | §"Out of scope" — no `transport/` writes, no plaintext session-token persistence, no SQLite-bus exfil | C8 (extend) | READY | None (C8 audits subagent tool-log; runs continuous). Same READY posture as §3 C8 row. |

**Tally:** READY = 1 (I11) / BLOCKED = 10 (I1, I2, I3, I4, I5, I6, I7, I8, I9, I10) / DEFERRED = 0.

(Note: §4 row counts 11 — matches the "11 rows" total in the dispatch instructions: "9 §3 + 11 §4-or-add" → total 20.)

## 5. Dry-run verdict line

`DRY-RUN 2 READY / 17 BLOCKED / 1 DEFERRED` (out of 20 total rows: 9 §3 + 11 §4).

Per `.claude/agents/poc-coordinator.md` §"Per-stage gate logic": "C1 FAIL → halt; no point firing anything else." Under live-fire today, coordinator would halt at C1 with verdict `NO-SHIP no-target-locked` (escalation-table entry 1).

## 6. Open items for main thread

Concrete relay tasks the main thread must own (per `docs/poc/next-steps.md` §"Itemized prerequisites — main-thread-bound" + §"Escalation table"):

1. **Relay AskUserQuestion at C9 fire-time.** Per next-steps MT-2: "C9 emits a request; main thread fires `AskUserQuestion` (`What time did you send the test turn?` + envelope kind); relays back to C9." Cannot pre-fire; binds on C1..C5 PASS first.
2. **Own Tier-3 soak fire if Path-D verification requested.** Per next-steps MT-1 + `feedback_subagent_long_task_abandonment.md`: any `>5min` Bash must launch from main thread via `run_in_background` + `ScheduleWakeup`. Robin (C6) ingests reports the main thread produces.
3. **Honor C8 abort signal.** Per next-steps MT-3: "If C8 mid-run HARD-FAILs, main thread cancels in-flight subagent dispatches and forces coordinator to write `NO-SHIP firewall-breach`." Dry-run: C8 abort path not exercised.
4. **Decide POC dispatch path.** Per `docs/poc/next-steps.md` §"What's next for the team" item 1: agent files `.claude/agents/*.md` are present on disk but Claude Code's `Agent` tool resolves `subagent_type` at session start. Either (a) restart Claude Code to pick up `poc-coordinator` definition + dispatch via `Agent` tool, OR (b) continue dispatching via `general-purpose` fallback with inlined mission text (current path, used for this dry-run).
5. **Mint C10 cassette pack (or pre-approve operator-driven record).** Per next-steps item 6: "If `tests/cassettes/safety/p{1..5}-*.json` not present, record via `tools/cassette_record.py` against the safety priority prompts. Use synthetic credentials only." Item explicitly tagged "NOT a subagent — too touchy for delegation"; main thread or operator must drive.
6. **Resync against operator parallel state before any live POC fire.** Per `feedback_parallel_operator_state.md` (Sean MEMORY.md): "before any docs-mint subagent dispatch, run `git fetch` + `gh pr list` to check whether the operator has opened a PR in the namespace I'm about to mint into; v2.7.1 collision 2026-05-22 cost 5 subagent runs." Dry-run baseline: only PR #154 open (unrelated docs); no v2.8 P1 Path-D PR yet.

## 7. Open items for operator

Numbered by `docs/poc/next-steps.md` §"What's next for the team" (items 1-10):

1. **Item 1 — Verify agent discovery.** Decide whether to restart Claude Code so the `Agent` tool picks up `poc-coordinator` + 10 minted subagent files. Alternative: continue dispatching coordinator via `general-purpose` fallback. (Status: NOT-DONE.)
2. **Item 2 — F-POC-1 land agent files.** Open single docs-only PR adding 11 agent files + 12 game plans + next-steps + task-list amendment. Outside v2.8 P1 scope per `do-not-touch guard`. (Status: NOT-DONE; files staged in working tree but no PR open.)
3. **Item 3 — F-POC-2 coordinator fire.** Depends on item 1; not actionable yet. (Status: BLOCKED on item 1.)
4. **Item 4 — Operator session + env.** Start a non-SM Claude CLI session in a non-firewalled cwd (NOT under `C:\Users\SeanHoppe\VS\certPortal\`); set the four `BRIDGE_*` env vars (OP-2a..OP-2d above); start dashboard with JsonlTailWorker active (OP-3). All currently UNSET; this is the single largest set of blockers (4 of 8 operator-bound prerequisites). (Status: NOT-DONE.)
5. **Item 5 — Path-D PR land.** `feat/v2.8-p1-path-d` complete + merged for C6 robin's shadow-side verification. Orthogonal to §3 PASS; C6 stays DEFERRED until this lands. (Status: PARTIAL — working-tree drafts present; no PR opened.)
6. **Item 6 — C10 cassette pack record.** Record `tests/cassettes/safety/p{1..5}-*.json` via `tools/cassette_record.py` using synthetic credentials only. Blocks I3..I7 (5 of 11 §4 rows). (Status: NOT-DONE.)
7. **Item 7 — C11 target path decision.** Pick a non-SM, non-firewalled project whose `INTENT.md` (or other `*.md`) C11 may temporarily edit + revert. Blocks I9. (Status: NOT-DONE.)
8. **Item 8 — F-POC-3 verdict review.** Depends on item 3; not actionable yet. (Status: BLOCKED on item 3.)
9. **Item 9 — F-POC-4 MVP-gauge update.** Update `docs/v10-mvp-status.md` gauge from ~80% → ~95% on combined POC ship + Path-D land. (Status: BLOCKED on items 5 + 8.)
10. **Item 10 — (Stretch) n>1 distribution.** Re-fire C9 K times to capture latency distribution beyond n=1. (Status: BLOCKED on item 3 PASS.)

---

## Closing posture

Dry-run confirms the §3 + §4 fleet is **structurally minted but operationally unfireable** today. All 10 operator-bound prerequisites listed in `docs/poc/next-steps.md` are unmet; only the 2 audit-style readiness rows (C8 / I11 — same subagent, two scope hats) can fire without operator setup. The next concrete unblock is operator item 4 (live non-SM session + `BRIDGE_*` env + dashboard) — that single action would unblock C1, C2, C3, C4, C5, C7, C9 (7 of 9 §3 rows) and I1, I2, I8, I10 (4 of 11 §4 rows). Item 6 (cassette pack) unblocks I3..I7 (5 more §4 rows). Item 7 (C11 path) unblocks I9. Item 5 (Path-D land) un-defers C6.

Firewall holds throughout this dry-run: no read attempted against `C:\Users\SeanHoppe\VS\certPortal\**` repo paths; PID 4916 (certPortal-oversight cwd) noted as firewalled and excluded from candidate-session enumeration.

Per `.claude/agents/poc-coordinator.md` §"Sanity self-check" — verdict line is a single token bracket per row-class: `DRY-RUN 2 READY / 17 BLOCKED / 1 DEFERRED`. No `deferred-to-follow-up` / `out-of-scope` escape-hatch language used (Hard boundary #6 honored).

C:\Users\SeanHoppe\vs\streamManager\reports\poc-live-monitor-dryrun-2026-05-22T18-09-10Z.md
