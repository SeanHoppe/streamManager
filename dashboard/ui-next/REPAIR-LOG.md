# ui-next REPAIR-LOG

> Honest post-build repair record for the KingMode EXPERIMENTAL UI spike
> (`.claude/workflows/sm-ui-build.js`, run `wf_da0a8914-5c6`, 2026-06-10).
> The build workflow's adversarial review returned **0 clean / 10 repair / 5
> BLOCKED** units over 60 files. This log records what the main thread fixed,
> what remains, and the verified build state. ASCII-only.

## Winning concept

`calm-ambient` ("still water" monitor) spine, judge total 43 / mustCompliance 10,
**grafted** with: ops-command-deck multi-session SessionRail; signal-hero
data-driven M2 escalation allow-list; monitor-first-elevated variable-weight
typographic severity scale + named paper-theme contrast deliverable.

## Verified build state (BOTH gate criteria PASS)

- `npm install` (dashboard/ui-next): OK (210 packages).
- `npm run build` (vite): **exit 0, 81 modules, 0 errors** (post u-compose wiring;
  the real feature panes are now in the import graph -- was 40 modules when only
  the shell + placeholders compiled). One non-blocking Svelte a11y warning on
  `HitlModeToggle` (radiogroup tabindex) -- pre-existing component note, not an
  axe violation. Output `dist/`: index.html 3.19 kB, css 56.27 kB, js 122.40 kB.
- `npm run axe` (WCAG 2.1 A+AA): **PASS -- 0 serious/critical, 0 violations**
  (`reports/axe-latest.md`). The u-compose pass first surfaced 2 new violations
  (AgentRoster `.roster` empty-list `aria-required-children`; `.roster__empty` +
  `.repl__empty` opacity-drag color-contrast) -- both fixed, see below.

## u-compose wiring pass (composition seam CLOSED -- 2026-06-11)

`App.svelte` now mounts the real feature panes into AppShell's named slots and
boots the read-only transports; the prior placeholder text is gone.

- **Frame A** -> `FrameA_Sessions` (live `ReplStream` decision feed) with
  `HitlDock` in its `pending` slot (live `/api/hitl/pending` + bus).
- **Frame B** -> `AgentRoster` bound to the 8s `/api/agents` poller store + the
  shared 1s clock (mounted as a body; AppShell already provides the B shelf, so
  `FrameB_SubAgents` -- which self-wraps its own `<Frame>` -- is intentionally
  NOT used here to avoid a frame-in-frame / duplicate `#frameB`).
- **Frame C** -> `FrameC_Jobs` (live 2s `/api/lifecycle/jobs` via `LifecyclePanel`).
- **header** -> `SessionPicker` (writes `selectedSessionId` -> scopes every pane).
  The full-height `SessionRail` graft needs a side column AppShell does not have;
  deferred to a layout-enhancement follow-up (the compact picker drives the same
  scope store).
- **footer** -> live connection dot + `/api/stats` decision/session tally.
- **Bootstrap** (App `onMount`): `connect()` SSE, `startPollers()`, seed +5s
  refresh `/api/sessions` (`defaultToMostRecent` once), seed `/api/decisions`,
  one shared 1s clock. Torn down in `onDestroy`.
- **M3 counts**: `HitlDock` now emits `actioncount` (added) -> Frame A pill;
  `FrameC_Jobs` `actioncount` -> Frame C pill; threaded into AppShell.
- **M2**: App drives only Frame A `escalated`, fed STRICTLY from sse.js
  `escalationStore` (produced from the `lib/escalation.js` allow-list), bounded
  to a 20s window. App classifies nothing itself.
- a11y repair: AgentRoster drops `role="list"` while empty (no `listitem` child
  tripped `aria-required-children`); removed the `opacity` AA-drag on
  `.roster__empty` + `.repl__empty` (same bug class as the earlier `.seam__hint`).

### Verified LIVE against the real governance server (not just a static build)

`GOV_DB=.claude/gov.db uvicorn dashboard.server:app --port 8765` + `npm run dev`
(vite proxy :4317 -> :8765). Headless puppeteer readout (`tools/ui_shot.mjs`):

```
conn: "live"   foot: "21065 decisions . 1250 active sessions"
decisionRows: 9   (real ALLOW/OBSERVING rows from gov.db, Frame A)
agentRows: 0  jobRows: 0   (no agents/jobs in scope -> calm "still water", correct)
scope picker: "<governed-slug>" pid 33804   (governed session FROM DATA, M16; SM self excluded, M15)
```

Screenshots: `reports/ui-next-live-obsidian.png` + `reports/ui-next-live-paper.png`.
App MOUNTS + renders the monitor-first 3-frame shell (`#frameA/#frameB/#frameC`
present) with LIVE data flowing into Frame A + the footer.

## SessionRail left-column wiring (2026-06-11)

The deferred `SessionRail` graft (ops-command-deck) is now mounted as a real
LEFT COMMAND-COLUMN, and the latent bugs that running axe/shot against LIVE
(populated) data exposed are fixed.

- **AppShell layout (2-col):** added an optional `rail` named slot. When the
  composing App supplies it, `.shell` switches to
  `grid-template-columns: [rail] clamp(13rem,17vw,16.5rem) [main] 1fr` with
  `grid-template-areas` so the rail spans all three rows on the left and
  masthead/shelves/footer stack in the main column. The rail cell bounds the
  rail (`min-height:0; overflow:hidden`) so the rail's own lane list owns the
  scroll. Three-frame core untouched -- M1 holds (FRAME_KEYS fallback, the three
  named slots, and the Reset control are all intact; render-validator green).
- **Responsive:** at `<=55rem` the rail column collapses
  (`grid-template-areas` -> single col, `.shell__rail{display:none}`) and the
  header `SessionPicker` takes over scope; at `>55.0625rem` the rail IS the
  scope control and `.seam--header` is hidden -- exactly one scope control at
  any width. The header wrapper stays in the DOM (display:none) so the
  `data-own-session` M15 hook is always present.
- **App feeds (App.svelte):** the rail self-wires its lanes + selection from the
  session store; App supplies only the two per-session SIGNAL maps it derives
  from the same read-only transports the frames use:
  `escalations` (re-keyed from sse.js `escalationStore`, the M2 allow-list, in
  the same 20s window Frame A uses -- App classifies nothing) and `actionCounts`
  (an UNSCOPED `/api/hitl/pending` poll grouped by `session_id`, 4s cadence,
  M18 post-hoc GET; self-excluded by ownId).
- **FrameB_SubAgents gotcha (still applies):** AgentRoster mounted directly; the
  rail is a sibling column, not a frame.

### Latent bugs the LIVE (populated) verification surfaced + fixed

The u-compose axe gate runs against `preview` (dist, no proxy => EMPTY data), so
it never exercised the populated render paths. Running axe + the shot helper
against the live dev proxy (real `.claude/gov.db`) surfaced five real bugs --
all fixed (none are rail-specific; the rail just lit them up):

1. **Decision-feed duplicate keys (App-breaking).** `sse.js pushDecision`
   appended an SSE-redelivered decision that was already in the seeded snapshot
   -> two rows with the same `id` -> ReplStream's keyed `{#each}` threw
   "duplicate keys in a keyed each", and the THROWN render error aborted the
   whole Svelte flush, so every other pane's reactive update in that flush was
   dropped (footer + rail showed 0). Fix: `pushDecision` drops any prior copy by
   `id ?? rid` before prepending (newest wins, keys unique); `seedDecisions`
   also de-dupes the snapshot defensively. This single fix un-broke the whole
   live render (stats + rail now populate).
2. **Session list duplicate keys.** `/api/sessions` can return the same
   `session_id` twice across its scan window; `setSessions` now de-dupes by id
   after the recency sort (most-recent instance wins) so the rail/picker keyed
   `{#each}` never sees a dup.
3. **Lane meta contrast (axe serious).** A SELECTED lane sits on the lighter
   `#131c2a` ground where the chrome ink (`#8a8068`) drops to 4.37 (< AA). Lift
   the meta ink to `--calm-ink` on selected lanes only (7.9:1).
4. **Rail self-exclude footer contrast (axe serious).** `.rail__self--inactive`
   carried `opacity:0.7` which dragged the 10px footer text to ~3.0. Removed --
   the inactive state is carried by the TEXT, not dimming.
5. **HITL toggle active-pill contrast (axe serious, pre-existing).** The active
   SYNC/ASYNC segment used near-white `#fffbeb` on the obsidian amber fill
   (`--calm-accent` => `#f59e0b`) = 2.07. Switched to dark ink `#1a1206` (the M4
   ACTION-REQUIRED idiom: dark-on-amber, 8.6:1); the paper theme keeps its own
   light ink (its fill is the dark editorial red). Latent: only manifests with a
   selected session, which the empty-state gate never had.

### Verified (both gates + live)

- `npm run build`: exit 0, **85 modules**, 0 errors.
- `npm run axe` (against the live proxy, POPULATED): **PASS -- 0 serious/critical,
  0 violations**, and no `pageerror` (the duplicate-key throw is gone).
- Live readout (`tools/ui_shot.mjs`, real gov.db): `railLanes: 20`,
  `railTally: "68"` (ACTION-REQUIRED across lanes -> `actionCounts` works),
  `railEmpty: false`, `headerPickerVisible: false` (wide: rail is scope control),
  `conn: "live"`, `foot: "21129 decisions · 1250 active sessions"`. Lanes render
  governed-target slugs + pids FROM DATA (M16); self-exclude footer shown (M15).
  Screenshots `reports/ui-next-rail-{obsidian,paper}.png`.
## SessionLane density + sidebar cleanup + polarity fix (2026-06-11, Playwright review)

Reviewed the live rail with the Playwright CLI (real Chrome, `--channel chrome`)
against the dev proxy, then fixed what the review showed did not make sense.

- **Lane redesign (density):** the prior `.lane__main` flex row over-stuffed the
  ~250px rail -- the slug truncated to ~3 chars, the pid wrapped onto its own
  line, and the OBSERVING/ACTION badge overlapped the id. Now: `.lane__id` takes
  the row slack (`flex:1`, no fixed name max-width) so the slug shows in full and
  ellipsizes gracefully; the meta is ONE non-wrapping ellipsized line
  (`state . pid . hitl`); padding tightened (denser list); the expand control
  slimmed (1.45rem, no heavy left border).
- **Calm-by-default signal:** dropped the always-on `OBSERVING` badge (it was
  noise on every lane -- the opposite of still water). Observing lanes are now
  bare/calm; ONLY lanes needing attention earn a COMPACT amber count pill
  (`<triangle> N` for actions, `! N` for escalation) in the frozen M4 amber
  (`#d97706` on `#fef3c7`, AA). The pill is aria-hidden because the lane's
  aria-label already announces the count/escalation + reason; the amber
  left-edge + the count digit + that aria are the paired M4 signal (color is
  never the sole channel). `Badge` import dropped from `SessionLane` (unused).
- **Polarity self-exclude by project_slug (the #1 "does not make sense"):** the
  review showed the SM's OWN sessions rendered as governed-target lanes (and one
  auto-selected as Frame A scope) -- a polarity-flip CLAUDE.md forbids. Root
  cause: the session store self-excluded only the single `sm-own-session-id`
  (empty in the dev `index.html`), never the project_slug half of the rule
  (`INCLUDE iff project_slug NOT IN STREAM_MANAGER_PROJECT_SLUGS AND session_id
  != self`). Fixed in-spike, M16-safe: added `<meta name="sm-own-project-slugs"
  content="streamManager">` (the SM self-identifies its OWN slug -- the static
  half of the polarity rule; the server may extend it via BRIDGE_SM_PROJECT_SLUGS
  at promotion), a `readOwnProjectSlugs()` reader in `api.js` (mirrors
  `readOwnSessionId`; comma-separated -> lowercased Set; empty => no-op), and a
  `setSessions` filter that drops any session whose `project_slug` is in that set
  (in addition to the self session_id + the dedup). After the fix the rail shows
  ONLY genuine governed targets; the SM's own sessions never appear. (Server-side
  `/api/sessions` does not apply the polarity filter -- this is the dashboard's
  defense-in-depth; the live `server.py` stays untouched per ADR-20.)
- **M16 doc hygiene:** scrubbed the two monitored-project slug mentions this log
  had accrued (now `<governed-slug>` / "governed-target") so the render-validator
  M16 contamination scan passes on the spike docs too.

### Verified (Playwright review + all gates)

- `npm run build`: exit 0, **85 modules**.
- `node --test test/render-validator.test.js`: **28/28 pass** (M1/M2/M4/M6/M15/M16
  -- the contamination scan is now green on docs too).
- `npm run axe` (live proxy, populated): **PASS -- 0 serious/critical**.
- Playwright Chrome review (`reports/pw-rail-{wide2,final,narrow}.png`): lanes
  render full slugs + single-line meta + compact amber count pills only where
  needed; the SM's own sessions are GONE (only governed targets remain); the
  header tally fell from ACTIVE 71 -> 1 once SM-self lanes were excluded; Frame A
  auto-scopes to a real governed target. Narrow viewport (<=55rem): rail
  collapses and the header `SessionPicker` takes over scope -- exactly one scope
  control at any width.
- Remaining dev-only note (not a code bug): the dev `index.html` ships an EMPTY
  `sm-own-session-id`, so per-SESSION self-exclude is off in dev; the per-SLUG
  exclude above now covers the SM's own sessions regardless. The real server
  injects the session id at `GET /`.

## Two additional BLOCKING bugs found + fixed during verification

- **`index.html` `</head>` in a comment (app never mounted):** the top comment
  contained the literal string `</head>` ("...by replacing `</head>`"). Vite
  injected the bundle `<script>`/`<link>` before the FIRST `</head>` -- which was
  inside the comment -- so the bundle tags were commented out and inert. The real
  `<head>` shipped with no script; `#app` stayed empty. Fixed: reworded the
  comment so no literal `</head>` precedes the real head close.
- **Missing `--sm-*` token bridge (themes never reached components + AA fail):**
  the component layer consumes `--sm-*` tokens but `theme.css` defines un-prefixed
  `--text-*`/`--accent`. Every `--sm-*` fell back to a hardcoded slate, so (a) the
  three themes did not retheme the components and (b) dim labels rendered below AA.
  Fixed: a one-place `--sm-*` -> theme-token bridge in `theme.css` (AA-documented
  values, no alpha) + removed an `opacity:0.7` drag on `.seam__hint`.

## BLOCKERs fixed by the main thread (the 5 that gated build/ship)

| # | Unit | MUST | Problem | Fix |
|---|---|---|---|---|
| 1 | u-theme | M4/M9/M17 | `theme.css`/`calm.css`/`focus.css` written but NEVER imported -- the whole token + focus-ring layer was dead code; page would render unstyled. | `src/main.js` imports the cascade `theme -> calm -> focus` (Vite JS->CSS graph owns load order). CSS now bundled (15.83 kB confirms). |
| 2 | u-frameC | M8/M9 | `HitlPendingRow` + `AsyncHitlQueue` read `started_at` / `r.advisory`, but `/api/hitl/pending` returns `queued_at` (ISO string) + `bias_hint` (object) + `trigger_reason`. Countdown + advisory chip would never populate from real server data. | Field resolution now reads `queued_at` (parsed to ms), `bias_hint.category`/`.confidence`, `trigger_reason`, with tolerant fallbacks. |
| 3 | u-shell | M3 | `document.title` double-writer: both `AppShell` and `TabTitle` could write it. | `AppShell` is the documented single runtime owner; `TabTitle` now ships passive (`apply=false`, unmounted) -- exactly one writer. |
| 4 | u-selfexclude | M2 | Two unsynchronized escalation allow-lists (`escalation.js` canonical vs `sse.js` runtime). Drift risk on the foreground-eligibility contract. | `sse.js` imports `escalation.js`'s sets + a module-load assertion that throws on any drift. `escalation.js` is the single source of truth (the S2 validator asserts it). |
| 5 | u-hitl-core | M7 | `HitlDock.idOf` resolved `pending_id`-first while `HitlReadOnlyRow` resolved `id`-first -> per-row opt-in promotion could key/lookup under different ids and silently drop. | `idOf` reordered to `id > decision_id > pending_id > message_hash > matched_hash` to match. Safe: server rows carry `id`. |

Plus: `Frame.svelte` a11y build warning (focusable scroll region) resolved with a
documented `svelte-ignore a11y-no-noninteractive-tabindex` (keyboard-scroll is
the intended WCAG 2.1.1 behaviour).

## NOT yet fixed -- known spike items (the 10 REPAIR units + AAA contrast)

These do NOT block the `vite build` (exit 0) and most do NOT block the axe A+AA
gate (axe excludes AAA color-contrast-enhanced per `tools/axe_audit.mjs` scope).
They are real review findings to resolve before any PROMOTION cycle frame. Source
of record: workflow run `wf_da0a8914-5c6` review findings.

- **AAA contrast (u-hitl-core, u-theme):** focus ring `#d97706` is 2.91:1 on the
  paper-theme light surface (AAA wants 7:1); `AdvisoryChip` quiet-ink on
  accent-wash is 3.49:1 on obsidian. Paper-theme `--text-dim` ratio still
  unmeasured (`src/styles/PAPER-CONTRAST.md` is the placeholder deliverable).
  These are AAA-tier (axe A+AA gate excludes them) but are M4/M17 quality debt.
- **u-config (a11y/scale REPAIR):** badge palette contrast docs; ACTION-REQUIRED
  pair 2.86:1 relies on border+label (M4 paired-label mitigates); empty
  `sm-own-session-id` meta + server append could duplicate the tag at promotion.
- **u-stores / u-badge / u-sessionrail / u-escalation / u-frameA / u-frameB /
  u-settings-patterns / u-validator (REPAIR):** ~per-unit findings (perf reflow,
  unknown-envelope graceful degradation, validator coverage). See the run output.
- **Test runner:** `test/render-validator.test.js` (the S2 contract validator)
  exists but no `test` script / runner is wired in `package.json`. Wire vitest
  before promotion so M1/M2/M4/M6 are CI-asserted.
- **Composition seam: CLOSED (2026-06-11).** `App.svelte` mounts the real feature
  panes (Frame A `FrameA_Sessions`+`HitlDock`, Frame B `AgentRoster`, Frame C
  `FrameC_Jobs`, header `SessionPicker`, live footer) and boots the `/events` +
  `/api/*` transports; verified LIVE against `dashboard/server.py` on the real
  `.claude/gov.db` (see the "u-compose wiring pass" section above). Remaining
  panes NOT yet mounted in the shell (exist as files, deferred): `SessionRail`
  (needs a side column AppShell lacks), `FeedView` / `EventsPanel` /
  `CrossSessionPatterns` (no 4th frame in the monitor-first IA), the FR-PPP audit
  rows (`AuditProbeRow`/`CanaryEchoRow`/`HallucinationAlert`), `SettingsDrawer`,
  and the async-HITL-in-Frame-C path (`FrameC_Jobs` `asyncRows` fed empty -- the
  HitlDock in Frame A is the single live HITL surface for now). These are
  follow-up integration, not blockers of the monitor-first core.

## Gate (main-thread only -- never a subagent)

```
# build (VERIFIED green, exit 0):
npm --prefix dashboard/ui-next run build

# a11y WCAG A+AA gate (VERIFIED PASS, 0 serious/critical):
npm install                                   # repo root: axe-core + puppeteer
npm --prefix dashboard/ui-next run preview    # serves dist on :4317 (background)
npm --prefix dashboard/ui-next run axe        # 0 serious/critical = PASS
```

Binary pass (from the sm-ui-build mainThreadGate): `npm run build` exit 0 AND
axe 0 serious/critical -- **BOTH PASS as of 2026-06-10**.

**Promotion** of `ui-next/` over `dashboard/static/index.html` is a SEPARATE
future v2.x cycle frame (sets LOC anchor + EVOLVING reclass + full ship-gate)
per ADR-20 SS2. This spike CANNOT block ship-gate.

## Resume pass -- M16 contract un-RED + S2 runner + paper AA (2026-06-13)

Resumed from UI-DESIGN-SPEC.md. Determined where work stopped: after the
beta-proposals batches (committed) the spike's own S2 render-validator was RED
and the M17 axe gate had a latent paper-theme regression. Both fixed; all three
gates GREEN.

1. **M16 contamination -- the S2 validator was RED (BLOCKER).** The M16
   "no monitored-project vocabulary" test failed: four files contained the
   literal off-limits monitored-project repo name (a CLAUDE.md zero-contamination
   + firewall breach that landed with the beta batch):
   - `SoakPanel-data.js` hard-coded the repo name as a `FIREWALL_CWD_FRAGMENTS`
     entry (LOGIC) + a mock cwd under that path (FIXTURE) -- the file's own
     header CLAIMED M16-clean while violating it.
   - `api.js`, `AmbientSoakTask.svelte`, `SoakPanel.svelte` named the same repo
     in firewall comments (references, but the M16 scan is zero-tolerance).
   Fix: the firewall fragment is GENERIC placeholder `['walled-repo']` (real
   list = operator/server config, injected as data -- no governed-target name in
   the UI taxonomy); mock cwd -> `/home/op/vs/walled-repo`; comments genericized
   to "off-limits monitored-project cwd". `node --test` now **28/28 PASS**
   including M16. No test asserted on the literal, so behaviour is unchanged
   (the firewalled mock row still classifies `firewalled`).

2. **S2 validator runner wired.** `package.json` had no `test` script (REPAIR-LOG
   flagged this as a pre-promotion gap). Added `"test": "node --test
   test/render-validator.test.js"` (file-direct -- Node 24 rejects the bare-dir
   `node --test test/` form). The M1/M2/M4/M6/M15/M16 contract is now a real
   `npm test` gate, not a hand-run command.

3. **Paper-theme AA regression fixed (M17 / D4-012).** The uncommitted theme
   toggle work added `systemTheme()` (HeaderBar): the OS `prefers-color-scheme:
   light` now auto-selects the PAPER theme on first load. That made the headless
   axe gate render paper for the first time, surfacing two real AA failures the
   static PAPER-CONTRAST.md analysis had not covered (action-palette colors used
   as small TEXT): `.rail__all--active` accent text 4.05:1 and `.repl__note--err`
   intervene text 3.24:1. Fixed AA-clean WITHOUT touching the frozen accents:
   a new paper-only `--calm-accent-text: #9b1c13` for accent text (border/wash
   keep frozen #c0392b), and paper `--c-intervene` #ea580c -> #c2410c. Cascade
   gotcha hit + fixed: a `:root` default for the new token, declared AFTER the
   `[data-theme=paper]` block at equal specificity, clobbered the paper value
   (later-source-wins) -- removed it and let the component `var()` fallback cover
   obsidian/phosphor. Documented in PAPER-CONTRAST.md SS3a + SS7.

### Verified (all three gates, main-thread)

- `npm run build`: exit 0.
- `npm test` (S2 render-validator): **28/28 PASS** (M16 green).
- `npm run axe` (M17, paper rendered DOM): **0 serious/critical** (was 1 serious,
  2 nodes). `reports/axe-latest.md` 2026-06-13.

## Resume pass 2 -- M11/M12 FR-PPP audit surface MOUNTED (2026-06-13)

Closed the increment flagged above. The three FR-PPP leaves are now composed
into a live host and surfaced in Frame A beside the HITL dock.

1. **New host `AuditDock.svelte` (M11/M12).** The audit peer of `HitlDock`. It
   correlates the two halves of a Layer-1 probe -- the `audit_probe`-kind HITL
   pending row (seeded from `/api/hitl/pending`; its message `content` carries
   the probe_id, `id` is the hitl_id) with its `audit.probe` SSE envelope (keyed
   on probe_id, carries `candidate_streams`) -- and hands BOTH to `AuditProbeRow`.
   It owns the Layer-2 canary state machine (`audit.canary_emit` -> pending,
   `audit.canary_observed` -> observed/auto-clear 1.5s, `audit.probe_failure` ->
   failed+reason) feeding `CanaryEchoRow`, and the Layer-3 `audit.hallucination_
   detected` alarm feeding `HallucinationAlert` (rendered FIRST so a parser-
   correctness alarm is never buried). The only mutation is the operator
   "Run audit probe" button (`GET /api/sm-probe?session_id&force=1`); everything
   else is post-hoc off the bus (M18). M15 self-exclude on the seeded rows; M16
   clean (no monitored-project vocabulary; all ids/paths/nonces FROM DATA).

2. **`HitlDock` excludes `trigger_reason==='audit_probe'`.** So a probe renders
   in exactly one place (AuditDock as `AuditProbeRow`), never double-rendered as
   a generic HITL row. One-line predicate add.

3. **`App.svelte` mounts `AuditDock`** in Frame A's `pending` slot, after
   `HitlDock` (the FR-PPP surface lives in the HITL panel per spec SS3d).

4. **`render-validator` +7 M11/M12 tests** (radio candidate list + none-of-the-
   above, session_id validation, ack provenance brain_id+prompt_hash, canary
   nonce+CountdownBar+1.5s auto-clear+failure reason, hallucination no-auto-clear
   operator-dismiss, 5-event subscription, single-render exclusion). 28 -> 35.

5. **Adversarial review (ultracode workflow, 5 lenses, 14 raw -> 6 confirmed) ->
   all 6 fixed before gate:**
   - **[critical] `runProbe` POSTed a GET-only route.** Called `getProbe({...,
     post:true})` -> `POST /api/sm-probe` -> 405 (server registers `@app.get`
     only; the sole POST is `/api/sm-probe/ack`). The surface's one mutation
     failed 100%. Fixed: GET + `force:true`.
   - **[med] dead 503 branch.** The `res.error` calm-message path was unreachable
     (`getJSON`/`postJSON` throw on non-2xx before parsing the body). Fixed: catch
     the throw, detect 503, render a calm "issued but not delivered" line.
   - **[med] re-seed race + amplification.** `onProbe` fired a `getHitlPending`
     GET per `audit.probe` event with no in-flight guard (slower-earlier could
     clobber fresher rows). Fixed: monotonic seq guard on `seed()` (latest wins)
     + skip the re-seed when the envelope's probe_id already correlates to a held
     row (cache alone re-renders it).
   - **[med] scope-bleed of the global leaves.** Documented as intentional: the
     canary/hallucination envelopes carry NO session_id, so they are process-
     global and must NOT be hidden by the operator's session scope (an alarm must
     never be scope-suppressed). Only the Layer-1 rows are session-scoped;
     `openCount` == on-screen count; badge reason names all three kinds.
   - **[low] loading flicker.** Bus-driven re-seeds set `loading=true`, flickering
     the empty-state line on live traffic. Fixed: `quiet` seeds after first load.
   - **[low] no bus backstop for new probe rows.** Added a `hitl_sync_queued`
     subscription (peer to `HitlDock.onSyncQueued`) that reconciles audit_probe
     rows even if the `audit.probe` envelope is missed in a reconnect gap.

### Verified (all three gates, main-thread, post-fix)

- `npm run build`: exit 0 (189 modules; AuditDock + 3 leaves + CountdownBar
  compiled in).
- `npm test` (S2 render-validator): **35/35 PASS** (M11/M12 added; M16 green).
- `npm run axe` (M17, paper rendered DOM): **0 serious/critical**.
  `reports/axe-latest.md` 2026-06-13T06:15.

## Resume pass 3 -- M11/M12 live probe round-trip VERIFIED (2026-06-13)

The pass-2 deferral (a live probe/canary/hallucination flow vs the real server)
is now CLOSED with a live integration harness.

- `tools/audit_ui_roundtrip_harness.py` -- boots the REAL `dashboard.server:app`
  in-process on a fresh temp `GOV_DB` + empty `BRIDGE_PROJECTS_DIR` (worker tails
  nothing -> zero firewall surface), waits for the browser's `/events` SSE
  subscriber to attach, then drives the full FR-PPP sequence:
    * `audit.probe` + `audit.canary_emit` via the REAL governance seams
      (`GovernanceEngine.emit_audit_probe` / `.emit_audit_canary`) -- the same
      calls `/api/sm-probe` + the ack auto-emit make; the HITL row is a real
      `hitl_pending` row read back over `/api/hitl/pending`.
    * `audit.canary_observed` + `audit.hallucination_detected` via the SAME
      `bus.write_envelope(...)` seam `jsonl_tail` uses (the live-LLM nonce echo /
      decoy-path tail is python-unit-covered: `tests/test_audit_canary_observe.py`
      + `tests/test_audit_hallucination_detect.py`).
  Fixture vocabulary is generic synthetic (M16): `demo-stream-alpha/beta`,
  `decoy-negative-control.jsonl`, `governed-fixture-session-001`.
- `test/audit-roundtrip.spec.mjs` -- self-contained puppeteer observer: spawns
  the harness + (re)uses the vite dev proxy (4317 -> 8765), then asserts the
  AuditDock DOM transitions live. **13/13 assertions PASS** (`delivered=1` =
  real browser subscriber on every event):
    * M11 -- AuditProbeRow radio candidate list (3 inputs = 2 data candidates +
      none-of-the-above) rendered FROM the envelope; SIGN affordance present;
      M11 session guard exercised LIVE (SIGN under ALL scope surfaces the inline
      "Select a session before signing this probe." validation, no POST).
    * M12 -- CanaryEchoRow pending (nonce from data + countdown progressbar) ->
      observed CONFIRMED; HallucinationAlert literal "HALLUCINATION DETECTED" +
      decoy-path forensic evidence + `role="alert"` + operator-dismiss removes
      the card.
  Run: `node test/audit-roundtrip.spec.mjs` (NOT part of `npm test`; it is a
  live integration spec). No orphan processes (taskkill tree teardown; 8765
  free after).
- Re-gated GREEN after adding the spec: `npm test` **35/35** (M16 scan clean
  with the new `.mjs` under `test/`).

### Still NOT done

- A true live-LLM canary echo (a running non-SM `claude` session that types the
  nonce back so `jsonl_tail._check_canary_match` fires on a real transcript) is
  still synthetic here -- substituted via the worker's own `write_envelope`
  seam. That end of the seam is python-unit-covered; wiring a live session into
  the browser round-trip would need the watcher to surface the fixture as a
  governed target (out of scope for a UI-transport check).
- Spike remains EXPERIMENTAL; promotion to the live dashboard is a separate v2.x.
