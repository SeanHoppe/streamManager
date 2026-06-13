# Deprecation candidates -- ui-next spike (directive #4)

**Status:** Deprecation analysis. Source: `sm-ux-audit` (109 agents, 2-refuter + adjudicator) +
main-thread reconciliation after the theme-wiring fix. Read-only analysis; no deletions performed.
**ASCII-only (cp1252).** Dash = "--". Full grounding in `reports/UX-AUDIT-REPORT.md`.

---

## The headline (read this first)

The audit flagged 6 components as DEPRECATE and 25 as dead/unmounted. But the 2-refuter pass caught a
distinction that a naive sweep would miss: **most "dead" components are NOT redundant -- they are
built-but-UNWIRED FROZEN contract surfaces.** Several appear under BOTH `DEPRECATE` and `FRICTION` in the
audit precisely because deleting them would drop a frozen REQUIREMENTS contract item (FR-PPP audit/probe/
canary/hallucination, the FR-UI Feed grid, Events panel, Settings drawer, cross-session patterns).

So the real finding is bigger than "delete dead code":

> **The ui-next spike is NOT contract-complete.** It looks finished (3 frames, live decisions, HITL,
> themes) but a large slice of the behavioural contract the live `dashboard/static/index.html` satisfies
> was BUILT in ui-next and never mounted. That is a promotion blocker, not a pile of deletes.

Two tiers below. Apply Tier 1 (safe deletes). Do NOT delete Tier 2 -- wire it or formally drop the
contract item via ADR.

---

## Tier 1 -- SAFE TO REMOVE (redundant / superseded; zero contract loss)

These have a live replacement or no contract role. Removing them is pure hygiene.

| Component | Why safe to remove | Evidence |
|---|---|---|
| `HeaderBar.svelte` | Never mounted; `App.svelte` puts `SessionPicker` in the header slot directly. Its one unique role -- the theme switch + `prefers-color-scheme` -- was just lifted into `stores/theme.js` + `ThemeToggle.svelte` (now mounted in `AppShell` masthead). Fully superseded. | audit: dead, "unused; SessionPicker used instead"; this session moved theme logic to the store |
| `ThroughputLine.svelte` | Imported ONLY by the dead `HeaderBar`. Orphaned once HeaderBar goes. **Caveat:** the ambient decision-rate sparkline has real calm-tech value -- if wanted, RE-MOUNT it in the `AppShell` footer rather than delete; otherwise remove. | audit: "imported by HeaderBar which is unused" |
| `FrameB_SubAgents.svelte` | A Frame-wrapper for Sub-Agents that is never mounted; `App.svelte:311` mounts `AgentRoster` directly into the frameB slot. Redundant wrapper. | audit DEPRECATE MEDIUM; `App.svelte:311` |
| `SessionMirror.svelte` | Unused per REPAIR-LOG; no parent mounts it and no contract surface requires a separate mirror (Frame A already renders the scoped session). Confirm against REQUIREMENTS before deleting. | audit: dead, "unused per REPAIR-LOG" |

**Dormant-by-design -- KEEP, do NOT delete:**
- `TabTitle.svelte` -- intentionally passive (`apply=false`); `AppShell` is the single runtime
  `document.title` writer (M3). It is the documented alternative owner kept dormant on purpose. Audit
  disposition: KEEP. Leave it; do not "clean it up."

---

## Tier 2 -- DEAD BUT CONTRACT-REQUIRED -> WIRE, do NOT delete

Each implements a FROZEN REQUIREMENTS / MUST contract surface that the live dashboard satisfies and
ui-next currently does NOT. Deleting any of these silently drops an MVP contract item. Default action =
WIRE into the composed tree; only drop via an explicit ADR amendment that also removes the requirement.

| Component | Contract it implements | Audit severity | Disposition |
|---|---|---|---|
| `AuditProbeRow.svelte` | M11 FR-PPP audit-probe HITL ack (radio candidate list + none-of-the-above, POST /api/sm-probe/ack) | HIGH | WIRE -- no parent owns audit-probe rows in ui-next |
| `CanaryEchoRow.svelte` | M12 FR-PPP Layer-2 canary echo (nonce + prompt-to-type + countdown) | MEDIUM | WIRE |
| `HallucinationAlert.svelte` | FR-PPP hallucination-detected alert + operator dismiss | KEEP(contract) | WIRE |
| `EventsPanel.svelte` | FR-UI bus-event log, frozen type-color coding (exact type names) | MEDIUM | WIRE |
| `FeedView.svelte` | FR-UI 8-column decision feed grid + ALL/ALLOW/.../BLOCK filters + JSONL export + MAX_ROWS=300 | MEDIUM | WIRE |
| `CrossSessionPatterns.svelte` | Cross-session pattern list + demote action (POST /api/patterns/{hash}/demote) | HIGH | WIRE |
| `SettingsDrawer.svelte` | FR-UI-9 operator settings (HITL mode, confidence floor, sync timeout, pause, audible, activity window, reduced-motion, layout reset) | FRICTION/KEEP | WIRE -- no settings affordance reachable in the live tree |
| `EscalationRail.svelte` + `AmberActionCard.svelte` | M2 escalation foreground surface (the lone-escalation hero) | unknown | INVESTIGATE -- referenced by the dead TabTitle path; confirm whether the M2 foreground is handled elsewhere before wire-or-drop |

**Why this is the important half:** the spike's apparent completeness is misleading. A promotion of
ui-next over `dashboard/static/index.html` is blocked until either (a) these surfaces are wired and pass
their render-validator (S2 in UI-DESIGN-SPEC), or (b) each dropped item gets an ADR that also amends
REQUIREMENTS. This is the single biggest finding of the audit.

---

## Soak-side deprecation / correctness (GAP, directive #2)

The audit surfaced 3 soak findings (see `reports/UX-AUDIT-REPORT.md` + `reports/soak-for-non-sm-sessions.md`):

- **HIGH -- Learn-Mode pattern contamination:** the soak driver's `_run_lm_dialogue_pump()` writes
  synthetic LM dialogue pairs into `learn_patterns_canonical` **unfiltered** -- synthetic soak data
  pollutes the real pattern corpus. This is a correctness defect, not just a UI gap.
- **HIGH -- no tier distinction for LM ingest sources:** `LearnSourceManager` writes external non-SM
  sessions to the SAME unfiltered table; no provenance separation between soak-synthetic and live.
- **MEDIUM -- synthetic-only path:** soak exercises only the synthetic LM pump, never the live
  non-SM-session JSONL tail -- confirming the `#112` gap documented in `soak-for-non-sm-sessions.md`.

These argue for a soak-source provenance column + the live-session soak harness proposed in
`reports/proposals/2026-06-11-soak-1-live-session-shadow-harness.proposal.md`.

---

## Recommended action order

1. **Tier 1 deletes** (`HeaderBar`, `FrameB_SubAgents`, `SessionMirror`; decide `ThroughputLine`
   re-mount vs delete) -- pure hygiene, EXPERIMENTAL surface, low risk.
2. **Tier 2 wiring decisions** -- the real work: wire the FR-PPP + Feed + Events + Settings + patterns
   surfaces (they are built), or ADR-drop each. This is the ui-next promotion gate.
3. **Soak provenance fix** -- separate synthetic/live LM writes (HIGH correctness).

All Tier 1/2 changes are EXPERIMENTAL ui-next scope; none touch a FROZEN runtime surface. A promotion to
replace the live dashboard remains a separate v2.x cycle frame.

---

### Verify

- Tier 1: `grep -rl "FrameB_SubAgents\|HeaderBar\|SessionMirror" dashboard/ui-next/src --include=*.svelte`
  returns only the files themselves (no live importer) before deleting.
- Tier 2: for each, `grep -rl "<ComponentName" dashboard/ui-next/src` shows no mounting parent today;
  the matching FR-* in `REQUIREMENTS.md` shows the contract it owes.
- Soak: `grep -n "_run_lm_dialogue_pump\|learn_patterns_canonical" tools/soak_driver.py src/stream_manager/*`
  confirms the unfiltered synthetic write.
