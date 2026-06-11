<!--
  FrameB_SubAgents.svelte -- Frame B (Sub-Agents). MUST M13 + M16.

  ROLE IN THE SHELL:
    This is the Frame B presence guarantee (M1: Frame C/B/A all present at load)
    -- the still-water shelf hosting the per-agent roster. It owns ONLY the
    Frame B view: it wires the already-session-scoped /api/agents poller store
    (u-stores) + the operator activity-window setting (u-settings) into the
    AgentRoster, inside the shared Frame shelf (independent scroll, M1; live
    header count, M3, driven by the parent).

  CONTRACT (MUST M13):
    - Renders per-agent RoleBadge chips for the FIXED generic role schema
      (prompt_constructor, developer, code_reviewer, tester, frontend_architect,
      researcher, strategic_advisor, health_monitor, sub_agent, unknown).
    - ACTIVE-IN-WINDOW agents pinned to top; chronological event chips per agent.
    - NO inter-agent blocking is shown or enforced (also M19 non-goal: this is
      not a terminal multiplexer / IDE).

  CONTRACT (MUST M16 -- domain-agnostic):
    - NO monitored-project vocabulary anywhere. Every governed-agent identity is
      rendered from /api/agents data only; the only literals are the generic
      role schema (RoleBadge) and SM's own UI copy.

  CONTRACT (MUST M2 -- escalation discipline):
    - Frame B NEVER auto-foregrounds itself. Sub-agent activity (new agent,
      activity spike) is NOT on the M2 foreground allow-list. If the shell ever
      needs to flag Frame B in place, it does so via the `flagged` pass-through
      to Frame (badge-in-place only) -- this component never sets `escalated`.

  CONTRACT (MUST M3 -- header count):
    - The frame header's open-ACTION-REQUIRED count is OWNED BY THE SHELL and
      passed in via `actionCount`. /api/agents carries no action verdict, so
      Frame B never fabricates a count from agent data (it would double-count or
      invent actionability). Default 0 = calm.

  CONTRACT (MUST M15 / G2 -- polarity):
    - This view never presents SM's own session. Self-exclusion happens upstream
      (the poller scopes to the operator-selected NON-self session; the sessions
      store structurally drops own-session). This component renders only what
      the store already filtered -- defense-in-depth by construction.

  M18: presentation-only. The 1s clock here drives the active/idle re-partition
  (a cosmetic re-pin), NOT any fetch; the poller (u-stores) owns the network.
  Off the verdict hot path.

  File-disjoint: Frame.svelte + AgentRoster.svelte + the u-stores poller store +
  the u-settings store. Owns no other file.
-->
<script>
  import { onMount, onDestroy } from 'svelte';
  import Frame from './Frame.svelte';
  import AgentRoster from './AgentRoster.svelte';
  import { agentsStore } from '../pollers.js';
  import { settings } from '../stores/settings.js';

  /**
   * actionCount: M3 live open-ACTION-REQUIRED count for Frame B, OWNED by the
   * shell (escalation / hitl store), passed down. Frame B never computes its
   * own (agents are observed, not actioned in this surface). Default 0.
   */
  export let actionCount = 0;

  /**
   * flagged / flagLabel: M2 in-place flag pass-through. The shell may flag
   * Frame B (badge-in-place, NOT foreground) -- e.g. an in-place variance note.
   * Defaults to unflagged. This component never escalates on its own.
   */
  export let flagged = false;
  export let flagLabel = '';

  /**
   * controls: surface the header reorder/reset affordances (M1 layout control).
   * Owned by the shell; defaults off so a standalone mount is calm.
   */
  export let controls = false;

  // --- Live clock for the active-in-window re-partition (M13). One timer for
  // the whole roster (rows don't each own a timer). ~1s tick mirrors the live
  // dashboard swim-lane re-pin cadence. Cleaned up on destroy. ---
  let nowMs = Date.now();
  /** @type {ReturnType<typeof setInterval>|null} */
  let clockTimer = null;

  onMount(() => {
    clockTimer = setInterval(() => {
      nowMs = Date.now();
    }, 1000);
  });
  onDestroy(() => {
    if (clockTimer) clearInterval(clockTimer);
    clockTimer = null;
  });

  // Activity window (FR-UI-9). AgentRoster re-clamps defensively, but we read it
  // here so the prop is reactive to operator settings changes.
  $: activityWindowSec = $settings.activityWindowSec;

  // The session-scoped agent rows from the 8s /api/agents poller (u-stores).
  // Already filtered to the selected NON-self session (M15 upstream).
  $: agents = $agentsStore;
</script>

<Frame
  frameKey="B"
  title="Sub-Agents"
  hint="Observed agents -- monitor only, no inter-agent gating"
  count={actionCount}
  {flagged}
  {flagLabel}
  {controls}
  on:move
>
  <AgentRoster {agents} {activityWindowSec} {nowMs} />
</Frame>
