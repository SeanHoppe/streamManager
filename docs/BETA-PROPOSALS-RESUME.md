# BETA Proposals -- RESTART / RESUME doc

**Milestone: 45 / 46 feature proposals shipped (batch-3 closed 2026-06-13).**
**1 HELD: allow-pattern-auto-graduation -- needs a real ADR-18 FROZEN amendment.**
**(Earlier checkpoint: 42 / 46, paused 2026-06-11.)**
**Branch: `feat/beta-proposals`** (commit of the 29-feature working tree; operator
theme-in-flight work -- `theme.css` / `ThemeToggle.svelte` / `theme.js` /
`AppShell.svelte` / `HeaderBar.svelte` -- deliberately EXCLUDED, left in the
working tree on `main`).

This doc is the single entry point to resume. Read it + the project memory
(`~/.claude/projects/C--Users-SeanHoppe-vs-streamManager/memory/project_beta_proposals_initiative.md`).

---

## 1. What this is

`/goal` 2026-06-11: build every proposal in `reports/proposals/PROPOSALS-INDEX.md`
as an **optional BETA feature** -- default-OFF, toggleable at the UI level
(Settings drawer > BETA features), promotable to permanent. KingMode design
(`docs/KingModePrompt.txt`); per-proposal research -> `.html` mockup gate ->
build -> backend + Playwright `--headed` test. Plan/cycle-frame:
`docs/2026-06-11-beta-proposals-initiative.md`.

Two workflows drive it (Rosetta-Stone adaptation of `Claude-ResearchFixWorkflow.md`):
- `.claude/workflows/sm-proposal-research.js` -- proposal -> brief -> 2-refuter
  verify -> writes a KingMode `.html` mockup. STOPS at the mockup gate.
- `.claude/workflows/sm-proposal-build.js` -- approved -> working-tree component
  build (no worktree) -> 2-refuter file review. Returns shared-file edits as DATA
  for the main thread to apply.

---

## 2. Coverage state (46 feature proposals; 3 process-only #6/#20/#39 excluded)

| Batch | Count | Status |
|---|---|---|
| Batch-1 (SHIP-PROPOSAL) | 15 | **DONE** -- built + backend + polarity-verified + axe 0-serious + all 15 `--headed` |
| Batch-2 NEW (CONSTRAIN) | 14 | **DONE** -- built + 21 additive endpoints + axe 0-serious + 13/14 `--headed` |
| Batch-2 overlaps | 13 | **COVERED BY BATCH-1** (no re-build; see `reports/proposals/BETA-DEFERRAL-LEDGER.md`) |
| **Batch-3 (gap-fill)** | **4** | **3 DONE + 1 HELD** (closed 2026-06-13) |

**Batch-3 outcome (2026-06-13):** unanimous 2-refuter verdicts (recovered from the
stopped Jun-11 research run journal -- mockups + verdicts already existed, no
re-run). **3 PASS built + integrated + all gates green:** `policy-preview-chip`
(#21, `GET /api/governance/predict`, chip under the HITL SYNC/ASYNC toggle),
`confidence-calibration-loop` (#8, `GET /api/governance/calibration`, root-sibling
reliability-diagram drawer), `regret-mining-override-loop` (#24,
`GET /api/governance/regret`, Frame-A regret-ledger card). All CONSTRAINED-ADDITIVE
(additive read-only GET, no DDL, no FROZEN, no envelope; polarity dual-key +
`excluded_self`). **1 HELD:** `allow-pattern-auto-graduation` (#1) -- NEEDS-AMENDMENT
(the one batch-3 proposal that genuinely needs a real ADR-18 FROZEN amendment: a
new `pattern_graduated` bus envelope + same-PR cassette/soak coverage + a
verdict-path short-circuit). Artifacts: `reports/_research_b3.json` (verdicts),
`reports/_build_b3.json` (build data), `reports/proposals/mockups/INDEX-batch3.html`
(gate gallery). Gates: build exit 0 (199 mod), npm test 35/35, pytest 13/13
(`tests/test_dashboard_{policy_preview_chip,confidence_calibration,regret_mining}.py`),
axe 0 serious flags-ON, puppeteer smoke 12/12 (`dashboard/ui-next/test/beta-headed/`).
Proposal files:
`reports/proposals/2026-06-11-{allow-pattern-auto-graduation,confidence-calibration-loop,policy-preview-chip,regret-mining-override-loop}.proposal.md`.

**32 BETA features are LIVE** in `dashboard/ui-next/` (default-OFF; 29 + the 3 batch-3 PASS). Component
files: `dashboard/ui-next/src/lib/components/beta/*.svelte`. Registry (the toggle
panel source): `dashboard/ui-next/src/lib/beta/registry.js`. Backend: ~32 additive
read endpoints in `dashboard/server.py` (all polarity-guarded, SM-self excluded).

---

## 3. How to RESUME batch-3 (the 4)

**ALREADY PRE-WIRED (paused mid-setup 2026-06-11):**
- `.claude/workflows/sm-proposal-research.js` -> `ACTIVE_BATCH = 'batch3'` is
  ALREADY SET. Just run the workflow (Workflow tool, scriptPath) -> writes 4
  mockups to `reports/proposals/mockups/` + returns verdicts. (A run was launched
  then stopped per operator request before it finished -- nothing partial to clean
  up; just re-run.)
- `.claude/workflows/sm-proposal-build.js` -> the `BATCH3_NEW` array (the 4, with
  CONSTRAINED-ADDITIVE read-only/advisory buildNotes) is ALREADY BAKED IN and
  `ACTIVE_APPROVED = BATCH3_NEW` is ALREADY SET. Just run it after the gate.
- **GOTCHA still applies:** Workflow `args` does NOT thread via `scriptPath` --
  the `ACTIVE_BATCH` / `ACTIVE_APPROVED` constants are the selectors.

So the resume sequence is just:
1. **Research:** run `sm-proposal-research.js` (scriptPath) -> 4 mockups + verdicts.
2. **Mockup gate:** generate a gallery (see `reports/_gen_index2.cjs` pattern --
   that temp was cleaned, re-create from git history) + present the 4 mockups for
   operator approval (directive #2).
3. **Build:** run `sm-proposal-build.js` (scriptPath; `ACTIVE_APPROVED=BATCH3_NEW`
   already set). Components land in `beta/`; build returns 0 shippable / N
   needsRepair -- **known FALSE-NEGATIVE** (refuter `matchesMockup` flags the
   by-design-unwired state). The components are sound; the "repair" is the
   main-thread wiring.
4. **Integrate (main thread):** recover the build data from the run's
   `journal.jsonl` (the aggregate only forwards full data for `shippable`; parse
   `type:'result'` events -> `reports/_build_b3.json`). Then: extract backend
   endpoints + api helpers to a draft, review (polarity/FROZEN/SQL/ASCII), splice
   into `server.py` (anchor: before `_DEFAULT_TIMEOUT_S = 60.0`) + `api.js`,
   ruff-fix the new region, add registry entries, wire each component into
   `App.svelte` (or the named mount) per its `wireInstruction`.
5. **Gate:** `npm --prefix dashboard/ui-next run build` (exit 0) + `npm run axe`
   (0 serious -- expect paper-theme contrast/ARIA whack-a-mole; see the playbook
   in section 5) + curl the new endpoints + Playwright `--headed`.

---

## 4. How to RUN + TEST the dashboard

```
# backend (temp DB so you don't touch the real gov.db; polarity-safe env):
GOV_DB=reports/_beta_test.db SM_CLI_POOL_SIZE=0 \
  BRIDGE_PROJECT_SLUG=streamManager BRIDGE_SM_PROJECT_SLUGS=streamManager \
  python -m uvicorn dashboard.server:app --host 127.0.0.1 --port 8765

# seed realistic governance data (6 sessions incl. 1 SM-self + 1 stale, ~45
# decisions, 1 hitl_pending) -- recreate the seed via MessageBus + raw inserts
# (the temp seed script was a throwaway; pattern is in the memory + git history).

# frontend (vite preview serves dist/, proxies /api -> 8765):
npm --prefix dashboard/ui-next run build
npm --prefix dashboard/ui-next run preview     # port 4317

# turn a flag ON to render a feature:
curl -X POST -H "Content-Type: application/json" -d '{"enabled":true}' \
  http://127.0.0.1:8765/api/beta/flags/<key>

# axe gate (must be 0 serious with flags ON):
npm --prefix dashboard/ui-next run axe          # -> reports/axe-latest.md

# Playwright --headed: cached chromium at
#   C:\Users\SeanHoppe\AppData\Local\ms-playwright\chromium-1212\chrome-win64\chrome.exe
#   (the npx-cache playwright at $(npm root)/.../_npx/.../node_modules; set NODE_PATH to it).
```

The BETA toggle panel is in **Settings drawer > BETA features** (footer "Settings"
button). Flags hydrate from the backend at app boot (`hydrateBetaFlags()` in
`App.svelte.onMount` -- a known bug-fix; do NOT move it back into the drawer).

---

## 5. Gotchas + playbooks (learned this session)

- **Workflow `args` does NOT thread via `scriptPath`** -> bake `ACTIVE_BATCH` /
  `ACTIVE_APPROVED` module constants. (Cost a wasted 135-agent run.)
- **Build refuters false-negative** every component (0 shippable / N needsRepair)
  because `matchesMockup` checks for being mounted, but wiring is the main
  thread's deferred job. Components are sound; recover their build data from
  `journal.jsonl` `type:'result'` events.
- **Build agents DON'T overwrite** an existing-and-wired component on a re-run --
  manual fixes survive accidental default re-runs.
- **Paper-theme contrast whack-a-mole:** the operator's PAPER theme `--c-*` /
  `--badge-*` palette is sub-AA at small text; more states render -> more axe
  contrast nodes. Fix: base-darken theme-INVARIANT chips (amber #d97706->#92400e
  / #b45309, orange #ea580c->#9a3412, red #dc2626->#b91c1c, green #16a34a->#15803d),
  and `:global([data-theme='paper']) .sel { color: <darker> }` overrides for
  per-theme surfaces. Opacity-dimmed text (`.lane--ended { opacity }`) caps
  achievable contrast -> raise the paper opacity + darken.
- **ARIA grid widgets** (heatmaps) need `grid > row > (rowheader|gridcell)`.
  Build agents emit grid>cell directly -> wrap rows in
  `<div role="row" style="display:contents">` (keeps CSS-grid layout).
- **Polarity (G2):** every backend endpoint MUST exclude SM-self
  (`project_slug NOT IN (sm_slugs)`, env `BRIDGE_SM_PROJECT_SLUGS` default
  `{streamManager}`). Verified vs seeded data: health-digest `excluded_self=1`,
  coverage/story/breach all exclude the seeded `streamManager` session.
- **Constrained-additive ships everything:** NO `message_bus.py` edit, NO new bus
  envelope, NO ADR-18 FROZEN amendment was needed -- soak-panel + the heavy
  forensics/replay/time-machine features all built as additive read endpoints +
  additive tables, with live-spawn/cron/replay-engine parts DEFERRED to documented
  "from CLI" affordances. Surface freeze intact.

---

## 6. Key files / artifacts

- Plan / cycle frame: `docs/2026-06-11-beta-proposals-initiative.md`
- Deferral + overlap ledger: `reports/proposals/BETA-DEFERRAL-LEDGER.md`
- Workflows: `.claude/workflows/sm-proposal-{research,build}.js`
- Mockups + galleries: `reports/proposals/mockups/` (`INDEX.html`, `INDEX-batch2.html`)
- Build data (recovered per batch): `reports/_build13.json`, `_build_held2.json`,
  `_build_b2.json` (batch-3 will be `_build_b3.json`)
- Foundation: `beta_flags` table + `GET/POST /api/beta/flags` in `server.py`;
  `lib/beta/registry.js` + `lib/stores/beta.js` + `lib/components/BetaToggles.svelte`
- Hook fix: `.claude/settings.json` PreToolUse now uses `$CLAUDE_PROJECT_DIR`
  (was relative `tools/hook_evaluate.py` -> broke when cwd left repo root).

---

## 7. Outstanding / known-incomplete

- **Batch-3 (4)** -- DONE 2026-06-13: 3 PASS built + integrated + gated green;
  `allow-pattern-auto-graduation` HELD pending an ADR-18 FROZEN amendment (new
  `pattern_graduated` envelope + cassette/soak + verdict short-circuit). To ship
  the held one, author the amendment first, then build it (not constrained-additive).
- **spatial-session-sidebar** -- built + wired + axe-clean, but its resting root
  element didn't render in the `--headed` smoke (selector `.ssb-spine` count 0);
  confirm its resting affordance renders (may need a session selected / hover).
- **Nothing pushed** -- the branch is local. Push when ready.
- **Real-data soak (#r1)** -- features tested with seeded mock data + an empty
  live gov.db; a true soak against a live non-SM Claude session is still pending
  for the soak-panel / ambient-soak / live features.
