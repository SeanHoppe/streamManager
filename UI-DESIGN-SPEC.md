# UI-DESIGN-SPEC.md -- StreamManager operator UI (KingMode redesign, EXPERIMENTAL spike)

> Input contract for `.claude/workflows/sm-ui-build.js`. Produced by `.claude/workflows/sm-research-md.js`
> (catalog -> synthesize -> 2-reviewer adversarial refute -> adjudicate). ASCII-only (cp1252).
>
> **Denominator (pin -- do not silently re-baseline):** 6 cataloguers over 42 md/code files -> 113 claims
> -> 60 adversarially verified -> **55 survivors** (53 MUST, 2 SHOULD). 53 claims DEFERRED past the
> verify cap (re-run `sm-research-md` to cover them). Every line below cites a real `file:line`; a
> design choice with no cite is out of scope for this spec.
>
> **Status:** DRAFT pending operator sign-off. Pairs with `docs/adr/ADR-20-ui-redesign-experimental-spike.md`.

---

## 0. What changed vs the original assumption

The existing UI is **not** a thin dashboard -- it is already feature-complete. `dashboard/static/index.html`
(~5205 lines, vanilla) ships: a sidebar (Agents / Monitor / Feed / Events), the INTENT 3-frame layout, an
HITL panel with countdown bars, the full FR-PPP audit-probe / canary / hallucination UI, a settings panel,
**three themes** (obsidian / phosphor / paper), focus rings, and an axe-core WCAG AA gate
(D4-006..D4-014). There is also a formal `REQUIREMENTS.md` with `FR-UI-1..FR-UI-9`, `FR-HITL-*`, `FR-AR-*`,
`FR-OG-*` (D1/D2/D3 grounding).

**Therefore this is a re-architecture, not a greenfield build.** The KingMode redesign must *preserve the
behavioural contract* (every endpoint, SSE event, badge semantic, setting, and a11y gate below) while
restructuring the *form* (frame geometry, hierarchy, motion, density, typography) into something
awe-inspiring. Awe is in the craft layer; the contract layer is frozen.

---

## 1. Product intent the UI serves (product-intent dim, 14 survivors)

- SM is a **governance + adaptive-learning bridge** between Claude Desktop orchestration and a Claude CLI
  executor -- the "project manager layer". It enforces **plan-alignment** and **cadence**, governs
  **messages not transitions**, and never gates one agent on another's state. (D1-1: README.md:3,
  INTENT.md:9-19; D1-15, D2-5.)
- Governance has **5 modes** (OBSERVE/SUGGEST/GUIDE/INTERVENE/BLOCK) with rolling-accuracy auto-promotion
  (D1-5: REQUIREMENTS.md:147-151, governance.py:41-46). Bottom-up **L0-L4 decision graph** learning
  (D1-6: decision_graph.py:20-28,131-138). The Feed already renders an `layer-badge` per decision
  (D1-6: index.html:2891).
- **HITL** is sync (hold) or async (decide+annotate); human overrides become reinforcement signals
  (D1-8: hitl.py:378-446). **Learn Mode** biases as **pre-fill only**, never overriding a HITL gate or the
  safety floor (D1-14, D2-4: governance.py:902-941, learn-mode-design.md:38-40).
- **Lifecycle bridge** surfaces Claude Code background jobs + subagent spawns into frame C (D1-9:
  lifecycle_bridge.py:128-180, server.py:688-717).
- Companion tracks the UI must not break: **v10 RL** off-policy track (EXPERIMENTAL, audit via DB/logs not
  UI -- D1-13) and the **FR-PPP** provenance probe/canary/decoy workflow (already wired in the HITL panel --
  D3-11, D3-12, D4-005).

## 2. Operator profile (operator-profile dim, 10 survivors)

- Single-user, single-operator; **no multi-user / team-sharing surfaces** (D2-9: learn-mode-design.md:61-62,
  REQUIREMENTS.md:507). Sean runs governance on a laptop via `claude -p`.
- Needs **glance-readability** across concurrent sessions without terminal context-switching; a header
  **session picker** filters every pane by `session_id`, persisted to `localStorage`, defaulting to
  most-recently-active (D2-2: REQUIREMENTS.md:290-297, INTENT.md:77-80).
- Wants **monitor-first calm**: see activity without being interrupted; opt in to action per-card (D2-3,
  D2-6). Must distinguish **monitor-only vs action-required at a glance** via paired label+color badges
  (D2-6: INTENT.md:85-86).
- Audit-first: full trail of HITL approvals/overrides/timeouts with timestamps; settings changes emit
  `dashboard_settings_changed` to WAL (D2-10: REQUIREMENTS.md:374,462).

---

## 3. MUST constraint floor (inviolable -- a redesign breaking any of these is rejected)

> These are the binding constraints. `sm-ui-build` receives them as `mustConstraints[]`. Each is grounded.

### 3a. Layout + monitor-first (ui-hitl dim)

- **M1 -- 3-frame presence.** Frame A Interactive REPL/Sessions, Frame B Sub-Agents, Frame C Background
  Jobs all present at page load, each independently scrollable, layout persisted per-session in
  localStorage with a Reset control. *Arrangement is free; presence is not.* (D3-1, D4-006:
  INTENT.md:77-78, REQUIREMENTS.md:378-386, index.html:2301-2392.)
- **M2 -- escalation-only foreground.** Only `desktop_pause`, `governance_negative_regression`, and
  static-rule fire auto-foreground a frame. `new_pattern` / `low_confidence` / `governance_variance_alert`
  flag **in place** via badges only (D3-2: INTENT.md:79-80, REQUIREMENTS.md:390-399).
- **M3 -- frame + tab action counts.** Each frame header shows a live open-`ACTION REQUIRED` count; the
  browser tab title shows `(N) StreamManager` total, SSE-driven with ~100ms debounce (D3-7:
  REQUIREMENTS.md:445, index.html:4706,2308).

### 3b. Badges + actionability (the load-bearing accessibility rule)

- **M4 -- paired label+color, always.** Every visual signal pairs a **text label** with color; color alone
  is never a signal. Labels: `ACTION REQUIRED`, `OBSERVING`, `DECIDED`, `BLOCKED`, `WARN`, `TIMEOUT`. Each
  badge carries `title`/`aria-label` = trigger reason. Reject any color-without-text CSS rule. (D2-6, D3-6:
  INTENT.md:85-86, REQUIREMENTS.md:432-443.)
  - `ACTION REQUIRED` = amber `#d97706` on `#fef3c7`, 2px solid amber pulsing border (HITL ON).
  - `OBSERVING` = slate, no border (HITL OFF).

### 3c. HITL semantics (ui-hitl dim)

- **M5 -- two modes.** SYNC (hold pending until human) and ASYNC (decide now, annotate after), switchable
  at runtime; switch emits `hitl_mode_promoted` for audit. UI exposes SYNC/ASYNC only (backend `off` is not
  operator-selectable) (D3-3: REQUIREMENTS.md:314-316, server.py:2000-2118).
- **M6 -- HITL ON = ranked options.** Pending rows render APPROVE / OVERRIDE (ranked FR-UI-5 list or free
  text) / DISMISS; selection persisted keyed to message hash for next-time reinforcement (D3-4, D2-3:
  INTENT.md:81-82, REQUIREMENTS.md:403-430).
- **M7 -- HITL OFF = read-only + opt-in.** OFF decisions render read-only with `OBSERVING` badge + explicit
  **Take action** affordance; activating it flips the session to HITL ON SYNC, surfaces the ranked list,
  persists, emits `hitl_mode_promoted` (D3-5, D2-3: INTENT.md:83-84, REQUIREMENTS.md:401-404).
- **M8 -- HITL gate is absolute.** Learn-Mode bias only **pre-fills** (a dashed, non-verdict informational
  chip above the action buttons, title "advisory only -- operator decision still required"); it never
  bypasses the gate, never toasts, never offers undo (D3-9, D1-14, D2-4: index.html:3286-3307,
  governance.py:902-941).
- **M9 -- countdown bars.** Each pending row shows a 1s-tick countdown (default 60s); on expiry the row gets
  `expired` (opacity .35 + grayscale) (D3-8: index.html:3339-3361).
- **M10 -- optimistic resolve.** Resolve filters the row immediately, POSTs `/api/hitl/resolve`
  {pending_id, resolution}; on error silently restores prior state (D3-10: index.html:3380-3426).

### 3d. Provenance / FR-PPP (already wired -- preserve)

- **M11 -- audit-probe ack.** Render probe rows with radio candidate list + "none of the above"; validate
  `session_id` set; POST `/api/sm-probe/ack` with brain_id+prompt_hash extracted from the envelope (D3-11,
  D4-005: index.html:3428-3469).
- **M12 -- canary echo.** Render nonce + prompt-to-type with countdown; pending->observed (auto-clear 1.5s)
  / pending->failed (reason). Hallucination alerts render with operator-dismiss (D3-12, D4-005:
  index.html:3240-3279,4415-4488).

### 3e. Sub-Agents + lifecycle (product-intent / frontend dims)

- **M13 -- per-agent role badges, independent.** Frame B renders per-agent role badges
  (prompt_constructor, developer, code_reviewer, tester, frontend_architect, researcher,
  strategic_advisor, health_monitor, sub_agent, unknown), active-in-last-window pinned to top, chronological
  event chips; **no inter-agent blocking shown or enforced** (D1-3, D2-5, D4-006: REQUIREMENTS.md:230,383).
- **M14 -- frame C lifecycle.** Render job/agent name, id/PID, status (running/exited), elapsed, exit code;
  poll `/api/lifecycle/jobs` every 2s, filter by selected session (D1-9, D4-003: server.py:688-705,
  index.html:3057-3087).

### 3f. Self-monitoring firewall (governance integrity)

- **M15 -- exclude SM self.** Read `<meta name="sm-own-session-id">` at DOM-ready and filter that
  `session_id` from every decision row + mirror (defense-in-depth atop the server-side strip). Empty/missing
  meta -> skip filtering (D4-009: server.py:547-562, index.html:5003-5077). *(Polarity-flip; CLAUDE.md.)*
- **M16 -- domain-agnostic.** No monitored-project vocabulary hard-coded anywhere in the UI; governed-target
  identity renders from data only. *(Firewall + zero-contamination; CLAUDE.md.)*

### 3g. Performance + accessibility (NFR)

- **M17 -- a11y gate.** UI must pass `npm run axe` (axe-core + puppeteer, WCAG 2.1 A+AA); deployment blocks
  on serious/critical (AAA color-contrast-enhanced excluded per existing scope) (D4-014:
  axe_audit.mjs:137-160). Focus rings 2px solid `#d97706` + 2px offset on all interactive elements (D4-013).
- **M18 -- latency budget respected.** UI is post-hoc observability; it must NOT add to the verdict hot path
  or require per-decision live latency reads as a hard dependency. Respect ADR-5 (p50<=7s, p95<=15s). The
  Learn-Mode categorizer runs out-of-band (D2-11, D1-10: learn-mode-design.md:45, REQUIREMENTS.md:494,556).
- **M19 -- non-goals hold.** No general-purpose IDE / terminal multiplexer; no multi-tenant; does not
  replace Claude Code's permission model (INTENT.md:88-93).

---

## 4. Endpoint + SSE contract (preserve exactly; UI consumes, server is untouched)

> `sm-ui-build` receives this as `endpoints[]`. The spike reads the existing `dashboard/server.py` API
> unchanged -- it does NOT modify the server.

| Surface | Method | Cadence / trigger | Source |
|---|---|---|---|
| `/` (injects `sm-own-session-id` meta) | GET | page load | server.py:547-562 |
| `/events` (decisions + named bus events) | SSE | persistent, 3s fixed reconnect | index.html:3096-3121 |
| `/api/stats` | GET | poll 5s | index.html:2981-2989 |
| `/api/decisions?limit&session_id` | GET | seed before SSE | server.py:588-615 |
| `/api/decisions/export` | GET | on demand (JSONL) | index.html:4175-4197 |
| `/api/decisions/{id}/suggestions` | GET | tray open | D1-6 |
| `/api/agents?limit&session_id` | GET | poll 8s | index.html:3024-3046 |
| `/api/sessions` | GET | session selector | server.py:720-758 |
| `/api/sessions/external`, `/api/sessions/bg-tasks` | GET | watcher panels | server.py:763-805 |
| `/api/lifecycle/jobs?session_id` | GET | poll 2s | server.py:688-717 |
| `/api/registry/active` | GET | on demand | server.py:661-685 |
| `/api/hitl/pending?session_id` | GET | seed + on SSE hitl event | server.py:877-919 |
| `/api/hitl/resolve`, `/api/hitl/annotate` | POST | operator action | server.py:933-1019 |
| `/api/sm-probe?session_id&force=1`, `/api/sm-probe/ack` | GET/POST | FR-PPP | server.py:1025-1248 |
| `/api/sm-canary/emit`, `/api/sm-decoy/register` | POST | FR-PPP | server.py:1255-1423 |
| `/api/patterns/cross_session`, `/api/patterns/{hash}/demote` | GET/POST | Task F | server.py:1429-1467 |

**Named SSE events the client must handle:** `hitl_sync_queued`, `hitl_timeout`, `audit.probe`,
`audit.probe_ack`, `audit.canary_emit`, `audit.canary_observed`, `audit.probe_failure`,
`audit.hallucination_detected`, `governance_negative_regression`, `governance_variance_alert`,
`nfr_model_routing_alert` (D4-005, D4-010). **Do not** confuse `/events` (dashboard state) with
`/api/commands/stream` (consumer-only; not a dashboard transport) (D3-14: ADR-14:59-65).

---

## 5. Existing UI behaviours to keep (frontend-code-reality dim, 16 survivors)

- Sidebar: Agents / Monitor / Feed / Events; Monitor nav badge = HITL pending count; footer live-connection
  dot (D4-007).
- Feed: 8-column grid (time, action, source, layer, agent, confidence, content+reason, session); action
  filters ALL/ALLOW/SUGGEST/GUIDE/INTERVENE/BLOCK; `MAX_ROWS=300`; JSONL export (D4-008).
- Events: collapsible, type-color-coded (use exact type names, e.g. `governance_variance_alert`), pause/clear
  (D4-010).
- Settings (FR-UI-9): HITL mode, confidence floor slider, sync timeout, pause detection, audible cue,
  sub-agents activity window, reduced-motion override, layout reset; persist no-reload + emit
  `dashboard_settings_changed` (D3-15, D4-011, D2-10).
- Three themes via CSS custom properties: obsidian (dark/amber `#f59e0b`), phosphor (CRT-green `#39ff14`),
  paper (editorial-red `#c0392b`). Keep AA contrast >= the documented ratios; **measure + document the paper
  theme `--text-dim` ratio before production** (open item) (D4-012).

---

## 6. Design direction (KingMode, reconciled with the MUST floor)

KingMode (`docs/KingModePrompt.txt`): anti-generic, bespoke, asymmetry, intentional minimalism, WCAG AAA,
micro-interactions. **Reconciliation:** the awe lives in *craft* (typography scale, spacing rhythm, motion,
density, a signal-hero treatment of the top live escalation, theme polish) layered over the *fixed contract*
(M1-M19). Concretely the build workflow's judge-panel weighs these angles, none of which may score >0 on
must-compliance while breaking a MUST:

1. **monitor-first-elevated** -- the 3-frame IA with bespoke density/motion/type (lowest risk; default).
2. **signal-hero-asymmetric** -- asymmetric shell; the highest-severity live signal owns a hero zone; frames
   reflow around it (still satisfies M1 presence + M2 escalation rules).
3. **ops-command-deck** -- dense multi-session command deck for at-a-glance governance.
4. **calm-ambient** -- stays quiet until a true escalation; maximizes M1 monitor-first calm.

## 7. SHOULD / MAY (2 SHOULD survivors + craft latitude)

- **S1 (SHOULD)** -- Operator manually verifies session cwd is non-SM + non-firewalled before attaching; the
  UI MAY surface cwd prominently but no auto surface-and-reject is mandated (D2-8).
- **S2 (SHOULD)** -- The 3-frame + badge + ranked-list + escalation-foreground principles are the canonical
  validator contract for any dashboard regression suite (D3-13). A redesign SHOULD ship with a render-validator
  asserting M1/M4/M6/M2.
- **MAY** -- project-context panel (which `*.md` ranked/loaded), decision-graph drill-down / L-level ancestry
  (today's tray shows action+confidence+override count only, no graph view -- D1-6), latency sparkline pane,
  per-agent current-scope display (not in schema today -- D1-15). All grounded as *not currently required*;
  treat as KingMode value-adds, not contract.

## 8. Stack + scope (operator-locked 2026-06-10)

- **Stack:** framework + build (default Svelte + Tailwind + Vite). Contained to the spike dir; build
  artifacts + `node_modules/` git-ignored. (ADR-20 SS3.)
- **Scope:** EXPERIMENTAL spike at `dashboard/ui-next/`. Live `dashboard/static/index.html` + `server.py`
  **untouched**. Cannot block ship-gate. Not counted against ADR-18 LOC cap. Promotion is a separate future
  v2.x cycle frame. (ADR-20 SS2.)
- **a11y/build gate:** `npm install && npm run build && npm run axe` -- **main-thread only** (may exceed the
  5-min subagent cap); `sm-ui-build` emits it as a gate, never runs it in a subagent.

## 9. Deferred (do not read as covered)

53 of 113 claims fell past the verify cap (mostly `design-constraints` + `scale-flex-needs` dims, which show
0 survivors only because they queued behind the 60-cap -- NOT because they were refuted). Re-run
`sm-research-md` to verify them before relying on scale/flex/constraint specifics. Known open items: paper-theme
contrast ratio (D4-012), `last_log_line` rendered-but-unpopulated in frame C (D1-9), agent current-scope absent
from schema (D1-15).

---

## 10. Hand-off payload for sm-ui-build

```
Workflow('sm-ui-build', {
  adrApproved: <true ONLY after ADR-20 merges>,
  stack: 'Svelte + Tailwind + Vite',
  targetDir: 'dashboard/ui-next/',
  concepts: 4,
  mustConstraints: [ M1..M19 from SS3 above, verbatim ],
  shouldConstraints: [ S1, S2 from SS7 ],
  endpoints: [ table in SS4 + named SSE events ],
  spec: <this file>,
})
```
