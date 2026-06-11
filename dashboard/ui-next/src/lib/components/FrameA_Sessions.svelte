<script>
  // FrameA_Sessions.svelte -- the Frame A body: Interactive REPL / Sessions.
  //
  // Frame A is one of the three guaranteed shelves (M1 presence is owned by
  // u-shell's AppShell; this file fills A's body slot). It composes the calm
  // decision/REPL stream (ReplStream -> DecisionRow) and provides the named
  // mount seam where u-hitl-core injects the live pending-action interaction
  // (ranked list / countdown / resolve). This file owns the FORM of Frame A;
  // the HITL interaction itself is a sibling unit, mounted via a slot so the
  // partition stays file-disjoint.
  //
  // CONTRACT:
  //  - M1: this is Frame A's body. It is independently scrollable because its
  //    host (Frame.svelte) is the scroll boundary; this component just lays out
  //    content top-to-bottom and never grabs the page scroll.
  //  - M2: Frame A is the foreground target for the three allow-list
  //    escalations (handled by u-shell). This body renders calm at rest and
  //    does not invent any foreground of its own.
  //  - M7: the read-only/opt-in HITL OFF behaviour lives in DecisionRow; the
  //    `takeaction` intent bubbles up here and onward to u-hitl-core via the
  //    `takeaction` event so it can promote the session to HITL ON SYNC.
  //  - M15/M16: scoping + self-exclude are enforced inside ReplStream from the
  //    session store. No governed-target vocabulary is hard-coded here.
  //  - M18: post-hoc only; no verdict-path work.
  //
  // CRAFT (calm-ambient): a quiet two-region body -- the pending-action seam
  // sits ABOVE the ambient stream so a genuine ACTION REQUIRED is reachable
  // without scrolling, while the still-water stream flows below.

  import { createEventDispatcher } from 'svelte';
  import ReplStream from './ReplStream.svelte';
  import { selectedSession } from '../stores/session.js';

  const dispatch = createEventDispatcher();

  /**
   * hitlOn: whether the selected session is in HITL ON. Threaded to ReplStream
   * so rows render read-only + opt-in (OFF) vs decided (ON). Default OFF.
   */
  export let hitlOn = false;

  /**
   * advisoryByDecisionId: Learn-Mode advisory pre-fills keyed by decisionId
   * (M8), threaded straight through to ReplStream. Informational only.
   * @type {Record<string|number, any>}
   */
  export let advisoryByDecisionId = {};

  // The selected session's identity, rendered from DATA (M16) for the body's
  // quiet sub-header. null => ALL governed sessions.
  $: sess = $selectedSession;
  $: sessLabel = sess
    ? sess.project_slug || (sess.id ? String(sess.id).slice(0, 8) : 'session')
    : 'all governed sessions';
  $: sessPid = sess && sess.pid != null ? `pid ${sess.pid}` : '';

  function onTakeAction(e) { dispatch('takeaction', e.detail); }
</script>

<div class="fa" data-frame-body="A">
  <!-- Quiet body sub-header: domain-agnostic, data-rendered session identity.
       This is NOT the frame header (that is M3, owned by FrameHeader). -->
  <div class="fa__ctx">
    <span class="fa__ctx-label">scope</span>
    <span class="fa__ctx-name" title={sess ? sess.id : 'all sessions'}>{sessLabel}</span>
    {#if sessPid}<span class="fa__ctx-pid">{sessPid}</span>{/if}
  </div>

  <!-- M7 / HITL interaction seam: u-hitl-core mounts the live pending-action
       UI (ranked APPROVE/OVERRIDE/DISMISS list, countdown bars, advisory chip,
       resolve). Placed ABOVE the ambient stream so an ACTION REQUIRED is
       reachable without scrolling. Empty until that unit mounts. -->
  <div class="fa__pending" aria-label="Pending operator actions">
    <slot name="pending" />
  </div>

  <!-- Ambient still-water decision stream. -->
  <div class="fa__stream">
    <ReplStream {hitlOn} {advisoryByDecisionId} on:takeaction={onTakeAction} />
  </div>
</div>

<style>
  .fa {
    display: flex;
    flex-direction: column;
    gap: 0.65rem;
    min-width: 0;
  }

  .fa__ctx {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    font-size: 0.68rem;
    color: var(--text-dim, #94a3b8);
    letter-spacing: 0.03em;
  }
  .fa__ctx-label {
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.6rem;
    color: var(--text-ui, #8a8068);
  }
  .fa__ctx-name {
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    color: var(--text, #e2e8f0);
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
    max-width: 24ch;
  }
  .fa__ctx-pid {
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    color: var(--text-dim, #94a3b8);
  }

  /* The pending seam collapses to nothing when u-hitl-core has no rows (the
     slot is empty), so the calm stream sits flush at rest. */
  .fa__pending:empty { display: none; }

  .fa__stream { min-width: 0; }
</style>
