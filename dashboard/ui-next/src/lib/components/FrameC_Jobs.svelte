<!--
  FrameC_Jobs.svelte -- the Frame C body (Background Jobs lifecycle + ASYNC HITL).

  Frame C is one of the three guaranteed frames (M1). Its PRESENCE + independent
  scroll isolation are owned by the AppShell/Frame shelf (this body mounts in
  AppShell's `frameC` named slot). This component composes the two surfaces the
  decomposition assigns to Frame C:

    1. LifecyclePanel  -- M14 background-jobs lifecycle (running/exited jobs +
       spawned sub-agents, polled every 2s session-scoped).
    2. AsyncHitlQueue  -- the ASYNC-mode decide+annotate host (M5 ASYNC half).

  M3 (co-owned with u-shell): Frame C reports its LIVE open-ACTION-REQUIRED count
  upward so the frame header pill + the browser-tab total reflect it. For Frame C
  the open-action count is the number of UNDECIDED async HITL rows in scope
  (lifecycle jobs are observational, not actionable -- they do not contribute to
  the action count). The count is emitted on an `actioncount` event AND mirrored
  to a `data-frame-c-action-count` attribute so the S2 render-validator can read
  it without a Svelte subscription. The parent (App) threads this into the
  frameViewStore that drives AppShell's M3 surfaces.

  M2: Frame C never auto-foregrounds. It carries NO escalation policy -- the
  allow-list (desktop_pause / governance_negative_regression / static-rule) is
  owned by u-escalation. Async HITL backlog flags IN PLACE via the count badge
  only; it never moves the frame. (This component never sets `escalated`.)

  M15/M16/M18 hold transitively: the child panels render governed identity FROM
  DATA, self-exclude the SM session, and sit off the verdict hot path.

  This file is the THIN composition seam for Frame C. The heavy lifting lives in
  the two child panels (also owned by this unit). It imports only its own unit's
  files + shared stores -- file-disjoint from every sibling unit.
-->
<script>
  import { createEventDispatcher } from 'svelte';
  import LifecyclePanel from './LifecyclePanel.svelte';
  import AsyncHitlQueue from './AsyncHitlQueue.svelte';
  import { settings } from '../stores/settings.js';
  import { ownSessionId } from '../stores/session.js';

  /**
   * jobs: OPTIONAL lifecycle rows override forwarded to LifecyclePanel. When
   * omitted the panel reads the u-stores lifecycleJobsStore (the wired path).
   * @type {Array<Record<string, any>>|null}
   */
  export let jobs = null;

  /**
   * asyncRows: the ASYNC pending HITL rows in scope (from u-hitl-core's pending
   * seed / SSE, scoped to the selected session). Empty by default.
   * @type {Array<Record<string, any>>}
   */
  export let asyncRows = [];

  /**
   * hitlRowComponent: OPTIONAL injected u-hitl-core row component (the ranked
   * APPROVE / OVERRIDE / DISMISS action UI, M6). Forwarded to AsyncHitlQueue.
   * Absent => the queue renders its self-contained fallback annotate form.
   * @type {import('svelte').ComponentType|null}
   */
  export let hitlRowComponent = null;

  const dispatch = createEventDispatcher();

  // ---- M3 open-ACTION-REQUIRED count for Frame C ---------------------------
  // Actionable == undecided async HITL rows in the active HITL mode. Lifecycle
  // jobs are observational (no operator action) and do NOT count. In SYNC mode
  // the ASYNC queue yields, so Frame C's async action count is zero (the SYNC
  // surface owns those rows). Self-exclude defensively (M15).
  $: own = $ownSessionId;
  $: scopedAsync = (Array.isArray(asyncRows) ? asyncRows : []).filter(
    (r) => r && (!own || String(r.session_id) !== String(own)),
  );
  // A row is "open action required" until it has been decided. We treat the
  // presence of a row as open; the queue marks decided rows locally, but the
  // authoritative open-set is the upstream pending list (decided rows drop out
  // of the seed on the next refresh). M5: only ASYNC mode contributes here.
  $: actionCount = $settings.hitlMode === 'async' ? scopedAsync.length : 0;

  // Emit upward whenever the count changes so App can thread it into the
  // frameViewStore that drives AppShell's M3 header pill + tab-title total.
  let _lastEmitted = -1;
  $: if (actionCount !== _lastEmitted) {
    _lastEmitted = actionCount;
    dispatch('actioncount', { frame: 'C', count: actionCount });
  }
</script>

<!-- The S2 render-validator can read the Frame C action count from this
     attribute without a Svelte subscription (mirrors the M3 contract). -->
<div class="fc" data-frame="C" data-frame-c-action-count={actionCount}>
  <!-- M14: background-jobs lifecycle. Observational; never contributes to the
       action count. -->
  <div class="fc__section">
    <LifecyclePanel {jobs} />
  </div>

  <!-- Hairline divider between the observational lifecycle list and the
       actionable async queue -- a quiet, intentional density break. -->
  <hr class="fc__divider" aria-hidden="true" />

  <!-- M5 ASYNC host. Self-hides in SYNC mode (the sibling SYNC surface owns
       those rows); the divider + section stay so the frame geometry is stable.
       M8 advisory chip + M9 countdown live inside the queue. -->
  <div class="fc__section">
    <AsyncHitlQueue
      rows={asyncRows}
      rowComponent={hitlRowComponent}
      on:annotated
    />
  </div>
</div>

<style>
  /* Frame C body. Independent scroll (M1) is the parent Frame shelf's job; this
     body just stacks its two sections with a calm rhythm. */
  .fc {
    display: flex;
    flex-direction: column;
    gap: var(--space-5, 14px);
    min-width: 0;
  }

  .fc__section { min-width: 0; }

  .fc__divider {
    border: none;
    border-top: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    margin: 0;
    height: 0;
  }
</style>
