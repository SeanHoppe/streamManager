# ADR-20: Operator-UI redesign as an EXPERIMENTAL spike (KingMode)

- **Status**: Accepted (operator-approved 2026-06-10 via /goal sign-off gate). `sm-ui-build` runs with adrApproved=true.
- **Date**: 2026-06-10
- **Related**: ADR-18 (surface freeze), INTENT.md SS"UI / HITL principles" + SS"Intentional non-goals (v1)",
  `docs/KingModePrompt.txt`, `Claude-ResearchFixWorkflow.md`, `.claude/workflows/sm-research-md.js`,
  `.claude/workflows/sm-ui-build.js`, `UI-DESIGN-SPEC.md` (pending)

## Context

The operator directive (2026-06-10 `/goal`) asks to build a flexible, scalable, "awe-inspiring"
operator UI using the `docs/KingModePrompt.txt` Senior-Frontend-Architect persona (anti-generic,
bespoke, asymmetric, intentional-minimalism, WCAG AAA).

Today's UI is a single hand-rolled `dashboard/static/index.html` (~5205 lines, vanilla HTML/CSS/JS)
served by `dashboard/server.py` (FastAPI + SSE). `package.json` is dev-only a11y tooling
(`@axe-core/puppeteer`, `puppeteer`) -- there is **no UI framework** in the repo.

INTENT.md SS"UI / HITL principles" prescribes a specific **monitor-first 3-frame information
architecture** (Interactive REPL / Sub-Agents / Background Jobs) with paired label+color badges and
HITL ON/OFF semantics. KingMode's "asymmetric / bespoke / reject-template" philosophy is in tension
with a *prescribed* frame geometry. The operator chose (AskUserQuestion, 2026-06-10):

1. **Layout authority** = Full redesign -- authority to change the IA itself, **gated on this ADR**.
2. **Stack** = framework + build (e.g. Svelte/React + Tailwind + Vite) -- a new dependency surface.
3. **Deliverable** = wire the two workflows, run research -> `UI-DESIGN-SPEC.md`, **stop for sign-off**
   before any UI code.
4. **Scope** = EXPERIMENTAL spike on a separate path; cannot block ship-gate; unbudgeted by ADR-18 LOC.

Without an ADR, a full-IA redesign would silently contradict INTENT.md SS"UI / HITL principles" and
would have no surface classification under ADR-18 Rule 1.

## Decision

### 1. Authorize a redesigned IA -- but pin an inviolable MUST-floor

The redesign MAY restructure the **frame geometry** (asymmetry, hero zones, density, motion,
typography, theming) away from the literal three-equal-frames layout. The following invariants from
INTENT.md SS"UI / HITL principles" remain **MUST** (a redesign that breaks any of these is rejected,
not merely flagged):

| # | Invariant (verbatim source) | Source |
|---|---|---|
| M1 | **Monitor-first by default**: the human sees activity without being interrupted. | INTENT.md:77 |
| M2 | Only true escalations (`desktop_pause`, negative regression, static-rule fire) may auto-foreground; lower-severity signals flag **in place** via badges. | INTENT.md:79-80 |
| M3 | **HITL ON** = SM proposes a ranked option list from memory; human picks; SM persists the pick. | INTENT.md:81-82 |
| M4 | **HITL OFF** = SM posts its proposed answer read-only; monitor-only by default, per-card opt-in to act. | INTENT.md:83-84 |
| M5 | Actionable vs informational state visible **at a glance via paired label + color badges**. Color alone is not a signal. | INTENT.md:85-86 |
| M6 | The three activity domains -- Interactive REPL, Sub-Agents, Background Jobs -- all remain reachable/visible (their *arrangement* is free; their *presence* is not). | INTENT.md:77-78 |
| M7 | Non-goals hold: no general-purpose IDE / terminal multiplexer; no multi-tenant cloud; does not replace Claude Code's permission model. | INTENT.md:88-93 |
| M8 | Domain-agnostic: the UI hard-codes **no** monitored-project vocabulary; governed-target identity is rendered from data (firewall + zero-contamination). | CLAUDE.md SS"Zero contamination", SS"Firewall" |
| M9 | Polarity-flip: the UI never presents the SM's own session as a governed target (default-exclude self). | CLAUDE.md SS"Session-source exception rule" |

> The 9 rows above (M1-M9 here) are the **governance-level** invariants. The **authoritative,
> finer-grained MUST floor is `UI-DESIGN-SPEC.md` SS3 (M1-M19)**, produced by `sm-research-md`
> (6 cataloguers -> 113 claims -> 60 verified -> 55 survivors; 53 MUST). Where the spec's numbering
> differs, the spec governs the build; this table governs the ADR intent. Research CONFIRMED all 9 rows
> and added detail (5 governance modes, L0-L4 graph, FR-PPP probe/canary UI, the 3 themes, the axe gate).

What is now **free** (was implicitly constrained): frame count/symmetry, visual hierarchy, the hero
treatment of the top live signal, density modes, and the overall aesthetic -- the KingMode surface.

### 2. Surface classification (ADR-18 Rule 1)

The redesign is built to a **new prototype path** (default `dashboard/ui-next/`), classified
**EXPERIMENTAL**:

- Failure here **cannot block ship-gate** (peer to the v10 RL companion track).
- It is **not** counted against the ADR-18 feature-cycle LOC soft target (1500) -- a spike, not a
  cycle phase.
- The live `dashboard/static/index.html` and `dashboard/server.py` are **untouched** by the spike.
  The new UI consumes the **existing** server API/SSE contract unchanged (read-only against the
  governance backend).

**Promotion** of `ui-next/` over the live dashboard is a **separate future decision**: it requires a
formal v2.x cycle frame that sets the LOC anchor, reclassifies the surface EVOLVING, and runs the
normal ship-gate. This ADR authorizes the *spike*, not the *promotion*.

### 3. Dependency decision (framework + build)

Introducing a frontend framework + build step (e.g. Svelte/React + Tailwind + Vite) into an otherwise
build-free Python repo is accepted **only within the EXPERIMENTAL spike dir**. Constraints:

- Build artifacts and `node_modules/` under `dashboard/ui-next/` are git-ignored.
- The existing `npm run axe` WCAG audit (`tools/axe_audit.mjs`) is the accessibility gate for the spike.
- `npm install` / `npm run build` are **main-thread** operations (may exceed the 5-min subagent cap);
  the `sm-ui-build` workflow emits them as a gate, never runs them inside a subagent
  (`feedback_subagent_long_task_abandonment.md`).
- Promotion-time, the framework dependency is re-evaluated against the INTENT non-goal of low
  operational complexity; the spike does not commit the project to shipping a framework.

## Consequences

- **Positive**: unblocks an awe-inspiring redesign without silently violating INTENT; the MUST-floor
  keeps the governance semantics intact; EXPERIMENTAL classification de-risks (no ship-gate coupling);
  the live dashboard keeps working throughout.
- **Negative / cost**: a second UI surface exists during the spike (maintenance duplication until
  promote-or-discard); a framework toolchain enters the repo (contained to `ui-next/`).
- **Reversible**: discarding the spike = delete `dashboard/ui-next/` + this ADR's classification row;
  nothing on the MVP critical path depends on it.

## Status / next step

Accepted 2026-06-10. Operator approved (a) this ADR and (b) `UI-DESIGN-SPEC.md` at the /goal sign-off gate.
`sm-ui-build` is running with `args.adrApproved = true` against the spec's MUST (M1-M19) / SHOULD lists.
