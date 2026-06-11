# BETA Proposals Initiative -- plan + cycle frame (2026-06-11)

Operator directive (/goal 2026-06-11): using `Claude-ResearchFixWorkflow.md` as a
Rosetta Stone, build workflows that fully research, understand, and build the
functionality in `reports/proposals/PROPOSALS-INDEX.md` and its UI. All proposals
are **optional BETA, default-OFF, toggleable at the UI level**, promotable to
permanent one day. Per-proposal: (#1a) determine end-user usage; (#1b) design from
the end-user's shoes; (#1c) never veer from `docs/KingModePrompt.txt`. (#2) Provide
`.html` mockups for operator confirmation. (#test) test every feature, backend +
frontend, mock data where live data is unavailable; **no feature goes live without
backend AND Playwright `--headed` frontend test passing**. (#r1) soak non-SM
sessions. (#r2) always use KingModePrompt for design input.

Goal-reviewer verdict on the directive: **FLAG** (11 rows). Operator decisions
(AskUserQuestion 2026-06-11) resolved the load-bearing forks. This doc records the
resolution and is the cycle frame for the work.

ASCII-only.

---

## 1. Operator decisions (binding)

| Fork | Decision | Consequence |
|---|---|---|
| Surface bucket | **Live dashboard + backend** (not EXPERIMENTAL-spike-only) | FROZEN-surface checks + ADR-18 LOC gate ENFORCED. Per-feature FROZEN footprint classified at research time; envelope/governance-core touchers get an ADR amendment before build. |
| Pilot batch | **15 SHIP-PROPOSAL first** | Batch-1 = #4,10,12,14,15,16,18,19,22,25,31,32,34,46,49. CONSTRAIN (27) = batch-2; gap-fill (4) = batch-3; process-only (3) excluded. See `reports/proposals/BETA-DEFERRAL-LEDGER.md`. |
| Mockup gate | **Gate on mockups** | research -> design -> `.html` mockup -> **PAUSE for operator approval** -> build -> backend + Playwright test -> wired BETA. UI is seen before code is written. |

### Assumption flagged for operator correction at the mockup gate

Proposals cite `dashboard/static/index.html` (the LIVE legacy single-file
dashboard). KingMode (#1c/#r2) + the active frontend investment live in
`dashboard/ui-next/` (Svelte). **Resolution taken:** frontend features are built in
**ui-next (Svelte), KingMode-styled**; backend is additive read-APIs in
`dashboard/server.py` (+ additive `src/` where a feature genuinely needs it). The
"live, not throwaway-spike" meaning of the operator's bucket choice = real backend
wiring + flag persistence + production-quality, NOT a static-html-vs-svelte
mandate. If the operator wants features in `static/index.html` instead, redirect at
the mockup gate; the standalone `.html` mockups apply either way.

---

## 2. BETA feature-flag architecture (cross-cutting foundation)

Every shipped feature is gated. Built once, before any feature; all 15 depend on it.

### Backend (`dashboard/server.py`, additive -- EVOLVING surface, not FROZEN)

- New `beta_flags` table in `gov.db` (additive; no FROZEN schema touched):
  `beta_flags(key TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0, updated_at TEXT)`.
- `GET /api/beta/flags` -> `{key: bool, ...}` (merges registry defaults with stored
  overrides; unknown/unset keys default OFF).
- `POST /api/beta/flags/{key}` body `{enabled: bool}` -> upsert + return new state.
- All flags **default OFF**. Absent table / read error degrades to all-OFF (loud:
  logs, never silently flips a flag on).

### Frontend (`dashboard/ui-next/`)

- `src/lib/beta/registry.js` -- single source of truth: `key -> {label,
  description, group, component, defaultEnabled:false}` for the 15. The deferral
  ledger's batch-2/3 entries are commented placeholders.
- `src/lib/stores/beta.js` -- `betaFlags` writable store, hydrated from
  `GET /api/beta/flags` at boot, written through `POST` on toggle. Optimistic UI
  with rollback on POST failure.
- `src/lib/components/BetaToggles.svelte` -- the on/off panel. Lives in
  `SettingsDrawer.svelte` under a "BETA features" section. KingMode-styled: paired
  label+color badge (ON = labelled accent chip, OFF = slate), grouped by feature
  area, WCAG AAA contrast, keyboard-navigable. Each row: label + one-line
  description + toggle + "what it does" affordance.
- Each feature component renders `{#if $betaFlags['<key>']}` ... `{/if}` and is a
  no-op (renders nothing, registers no pollers/SSE handlers) when OFF.

### Promotion path (one day permanent)

Per feature, a later v2.x cycle may: (a) flip `defaultEnabled:true`, then (b)
remove the flag + gate entirely (always-on). Promotion is a deliberate per-feature
decision, never automatic.

---

## 3. Workflow suite (the Rosetta Stone adaptation)

Two workflows under `.claude/workflows/`, mirroring `/report-research` +
`/report-fixes`. Architecture borrowed, inputs rewritten for SM (per the Rosetta
Stone's own "borrow the harness, rewrite the inputs" note). Args-driven: both take
a proposal-key list, so they cover batch-2/3 unchanged.

### `sm-proposal-research.js` (Catalog -> Find -> Verify -> Mockup)

1. **Catalog/Research** (one agent per proposal, `general-purpose`): read the
   proposal file; extract (#1a) end-user usage -- who toggles it ON, what task it
   serves, the glance/click path; (#1b) persona-walk from the operator's shoes
   (when, why, what it replaces); surface footprint classification (UI-only /
   new-read-API / new-table / new-envelope / FROZEN-touch); data needs + a
   mock-data spec (for #test when live data absent); (#1c/#r2) KingMode design
   direction. Structured output.
2. **Verify** (2 isolated refuters per proposal + adjudicator): refute, do not
   agree. Lenses: firewall (no certPortal coupling / contamination), polarity (no
   SM-self monitoring; non-SM target only), ADR-18 FROZEN (does the declared
   footprint actually touch a FROZEN surface? does it need an amendment?),
   feasibility. Adjudicator emits the vetted brief; a FROZEN/envelope toucher is
   flagged `needs_amendment` (not killed).
3. **Mockup**: produce a self-contained KingMode-styled `.html` mockup with inline
   mock data, written to `reports/proposals/mockups/<key>.html`. This is the #2
   operator-confirmation artifact.
4. Output per proposal: design brief + mockup path + footprint + amendment flag.
   **The workflow STOPS here (mockup gate).**

### `sm-proposal-build.js` (Split -> Build -> Refute -> Test)

Runs only on operator-APPROVED proposals after the gate.

1. **Split**: union-find partition by declared files so same-file work is serial,
   file-disjoint work parallel (Rosetta partitioner).
2. **Build** (per partition, `isolation:'worktree'`, `general-purpose`): minimal
   additive edits -- ui-next Svelte component (KingMode) + additive backend
   read-API + `registry.js` entry + mock-data fallback. Confined to declared files
   + their tests. Fixer **returns its worktree diff text** (memory rule below).
3. **Refute** (2 isolated reviewers per partition): review the **returned diff
   text only** -- never the shared tree (worktree-blindness memory rule). Lenses:
   FROZEN breach, polarity flip, certPortal contamination, ADR-18 LOC, root-cause
   vs symptom. Bounded <=2-round repair loop. Partition shippable only if
   unanimous.
4. **Test**: targeted backend pytest for `.py`; Playwright `--headed` for the
   Svelte component (#test). Mock data where live data unavailable. A feature is
   NOT shippable without BOTH green.
5. Return diffs + test results for **main-thread gate re-check** before any PR.

---

## 4. ADR-18 / FROZEN posture

- `dashboard/server.py` + `dashboard/ui-next/` are EVOLVING (only `/api/lifecycle/jobs`
  + lifecycle pane are FROZEN). New read endpoints + new UI panes + the `beta_flags`
  table are **additive** and allowed.
- FROZEN surfaces in play: `governance.py` decision flow, `message_bus` envelope
  schemas, `cli_pool`, `model_router`, `LifecycleBridge`, `wirecli`. Any feature
  whose research footprint touches these is **build-blocked until an ADR-18
  amendment lands** (precedent: `governance_decision` envelope amendment
  2026-05-12 -- additive new envelope, FROZEN, opt-in env-gated).
- New bus envelope kind => same-PR `tools/cassette_record.py` +
  `tools/soak_driver.py` coverage (cassette memory rule). Batch-1's
  highest-envelope-risk items: #16 (soak panel), #31 (event cursor), #32 (health
  digest live push). Research phase confirms whether each truly needs a new
  envelope or can ride existing `governance_decision` / bus rows.
- **LOC gate ENFORCED** (operator chose live path). Cycle-tip anchor per ADR-18
  Amendment C. Production bucket (`src` + `tools` + `dashboard`) binds; soft target
  1500 / BLOCK 2250 (feature cycle, Amendment A). Batch-1 is large; if it trends
  over soft target, record the operator override verbatim in the ship-gate, or
  split batch-1 across two PRs.

---

## 5. Embedded workflow-design memory rules (baked into both scripts)

1. Exec/build stages use `agentType:'general-purpose'`, never Explore
   (`feedback_workflow_exec_agenttype.md`).
2. Fixer returns worktree diff text; refuter reviews THAT, never the shared tree
   (`feedback_workflow_refuter_worktree_blindness.md`).
3. Main thread re-runs EVERY gate (cp1252 scan on added lines, ruff, targeted
   tests, build, axe) before opening any PR -- no CI exists, the main thread IS the
   gate (`feedback_workflow_gate_recheck_main_thread.md`).
4. Any workaround used in one partition is audited across all partitions
   (`feedback_parallel_undisclosed_deviations.md`).
5. Subagent "deferred to a follow-up" language is a BLOCK signal -- demand
   authorization or land it in-PR (`feedback_subagent_escape_hatches.md`).
6. Any soak / live-session test needs a confirmed live non-SM Claude session before
   firing; stale fixtures / self-loop do not satisfy
   (`feedback_soak_needs_live_non_sm_session.md` + #r1).

Plus long-task ownership: any build/test run > 5 min launches from the main thread
via `run_in_background` + `ScheduleWakeup`, never from a subagent
(`feedback_subagent_long_task_abandonment.md`).

---

## 6. Sequence

1. [done] Deferral ledger (`reports/proposals/BETA-DEFERRAL-LEDGER.md`).
2. [this doc] Initiative plan + cycle frame.
3. Author `sm-proposal-research.js` + `sm-proposal-build.js`.
4. Run `sm-proposal-research` on batch-1 (15) -> 15 KingMode `.html` mockups +
   briefs + footprint classification. **PAUSE: operator reviews mockups.**
5. On approval: build the BETA-flag foundation, then run `sm-proposal-build` on
   approved proposals (worktree-isolated, adversarial-refuted).
6. Main-thread gate re-check (build exit 0 + axe PASS + Playwright --headed PASS +
   targeted pytest PASS) -> PR per file-disjoint cluster.
7. Soak any live-session feature (#16 etc.) against a confirmed non-SM session.

## 6b. Held-2 resolution (soak-panel, event-cursor) -- NO FROZEN amendment

The research pass flagged soak-panel + event-cursor NEEDS-AMENDMENT (new FROZEN
bus envelopes). On re-examination of the vetted briefs, BOTH build ADDITIVELY --
no `message_bus.py` edit, no new envelope, no ADR-18 amendment, ADR-18 surface
freeze intact:

- **event-cursor**: its own vetted footprint is `frozenTouch:false` -- a new
  additive read endpoint `GET /api/sessions/{id}/events?since=<cursor>` over the
  existing `messages`/`decisions` tables + a localStorage cursor + ResumeBadge.
  The "amendment" the refuter named was an OPTIONAL doc-classification of
  `message_bus.py`, not a required code change.
- **soak-panel**: built as a CONSTRAINED ADDITIVE v1 -- additive `soak_runs`
  table + read endpoints (`/api/soak/sessions`, `/api/soak/status`,
  `/api/soak/polarity-audit`) + the Frame-D panel. The live soak LAUNCH (spawn a
  Tier-4 subprocess) is DEFERRED to a main-thread/operator op (long-running, needs
  a live non-SM session per #r1 + `feedback_subagent_long_task_abandonment`); v1
  shows a non-functional "launch from CLI" affordance, not an in-process spawn.
  The new `soak_polarity_audit` / `soak_ready_for_ship_gate` BUS envelopes are NOT
  minted -- the polarity audit is a read computation over gov.db, not a bus
  broadcast. If a future v2 wants live bus broadcast, THAT cycle files the
  ADR-18 amendment per the 2026-05-12 `governance_decision` precedent.

Net: the entire batch-1 (15) ships additive-only; the ADR-18 FROZEN surface
freeze is never breached.

## 7. Out of scope / guardrails

- No certPortal repo reads (firewall). No SM-self monitoring (polarity).
- No FROZEN edit without an ADR-18 amendment landing first.
- Process-only proposals (#6/#20/#39) do not enter this pipeline.
- v2.8 cycle stays open in parallel; this initiative does not gate its ship-gate.
