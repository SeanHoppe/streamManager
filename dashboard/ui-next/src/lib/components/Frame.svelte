<script>
  // Frame.svelte -- a generic, scroll-ISOLATED still-water shelf (MUST M1).
  //
  // One of these hosts each of the three guaranteed frames. Responsibilities:
  //  - M1 independent scroll: the body is its own scroll container
  //    (overflow:auto + min-height:0 inside a flex/grid column), so one
  //    frame's overflow never drags the others. Per-frame scroll offset is
  //    restored from / saved to the layout store, keyed per session.
  //  - M3: hosts FrameHeader, forwarding the live open-ACTION-REQUIRED count.
  //  - M2 in-place flagging: a frame can be `flagged` (badge-in-place) WITHOUT
  //    being foregrounded. Only the escalation allow-list (u-escalation) sets
  //    `escalated`, which is the sole trigger for the auto-foreground affordance
  //    here. This component encodes the distinction structurally; it never
  //    invents an escalation of its own.
  //
  // Content is injected by sibling units via the default slot (Frame A REPL,
  // Frame B agent timeline, Frame C lifecycle). This file owns ONLY the shelf.

  import { tick } from 'svelte';
  import FrameHeader from './FrameHeader.svelte';
  import { layoutStore } from '../stores/layout.js';

  export let frameKey = '';
  export let title = '';
  export let hint = '';
  export let count = 0;            // M3 live open-action count (from parent store)
  export let controls = false;     // reorder/reset affordances in header
  export let flagged = false;      // M2 in-place flag (badge only; NOT foreground)
  export let flagLabel = '';       // accessible reason for the in-place flag
  export let escalated = false;    // M2 allow-list foreground (set by u-escalation only)

  let bodyEl;
  let restoredScroll = 0;

  // Pull this frame's remembered scroll offset from the layout store.
  $: restoredScroll = $layoutStore.layout.scroll[frameKey] ?? 0;

  // After the session's layout loads (or changes), restore scrollTop once the
  // body has rendered. M1 per-session scroll persistence.
  let lastAppliedSession = Symbol('init');
  $: maybeRestore($layoutStore.sessionId, restoredScroll, bodyEl);
  async function maybeRestore(sessionId, top, el) {
    if (!el) return;
    if (sessionId === lastAppliedSession) return;
    lastAppliedSession = sessionId;
    await tick();
    el.scrollTop = top;
  }

  // Persist scroll offset, debounced via rAF so fast scrolling never thrashes
  // localStorage. Client-only; off the verdict hot path (M18).
  let scrollRaf = null;
  function onScroll() {
    if (scrollRaf != null) return;
    scrollRaf = requestAnimationFrame(() => {
      scrollRaf = null;
      if (bodyEl) layoutStore.setScroll(frameKey, bodyEl.scrollTop);
    });
  }

  // M2: an escalated frame may be brought into view. This is the ONLY
  // foreground path this component exposes, and the parent only flips
  // `escalated` for the data-driven allow-list members. new_pattern /
  // low_confidence / variance flag via `flagged` and stay put.
  export function bringIntoView() {
    if (!escalated) return; // structural guard: no foreground without escalation
    const node = bodyEl?.closest('.frame');
    if (node) node.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
  $: if (escalated) queueMicrotask(() => bringIntoView());
</script>

<section
  id={`frame${frameKey}`}
  class="frame"
  class:frame--flagged={flagged}
  class:frame--escalated={escalated}
  data-frame={frameKey}
  aria-label={title}
>
  <FrameHeader
    {frameKey}
    {title}
    {hint}
    {count}
    {controls}
    on:move
  />

  {#if flagged}
    <!-- M2: badge-in-place. Paired text label + color, with the trigger
         reason as the accessible name (M4). Presence of this strip does NOT
         move the frame; it is the explicit "flag here, do not foreground"
         channel. -->
    <div class="frame__flag" role="status" aria-label={flagLabel || `${title} flagged`}>
      <span class="frame__flag-dot" aria-hidden="true"></span>
      <span class="frame__flag-text">WATCH</span>
      <span class="frame__flag-reason">{flagLabel || 'in-place flag'}</span>
    </div>
  {/if}

  <!-- Independent scroll container: the load-bearing M1 isolation boundary.
       tabindex="0" is intentional: a scrollable region MUST be keyboard-focusable
       so keyboard-only operators can scroll the lane (WCAG 2.1.1). The Svelte
       a11y rule flags tabindex on a noninteractive role; the focusable-scroll
       pattern is the documented exception. -->
  <!-- svelte-ignore a11y-no-noninteractive-tabindex -->
  <div
    class="frame__body"
    bind:this={bodyEl}
    on:scroll={onScroll}
    tabindex="0"
    role="region"
    aria-label={`${title} content`}
  >
    <slot>
      <p class="frame__empty">Still water. No activity in this lane yet.</p>
    </slot>
  </div>
</section>

<style>
  .frame {
    display: flex;
    flex-direction: column;
    min-height: 0;            /* allow the body to own the scroll, not the frame */
    height: 100%;
    background: var(--sm-frame-bg, rgba(15, 23, 42, 0.35));
    border: 1px solid var(--sm-border, rgba(148, 163, 184, 0.16));
    border-radius: var(--sm-radius, 10px);
    overflow: hidden;        /* clip rounded corners; body scrolls internally */
    position: relative;
    scroll-margin: 1rem;     /* graceful target for bringIntoView() */
    transition: border-color 0.25s ease, box-shadow 0.25s ease;
  }

  /* M2 in-place flag: a quiet left edge accent. NOT a foreground; the frame
     stays exactly where it is in the stack. */
  .frame--flagged {
    border-color: var(--sm-warn-fg, #ca8a04);
  }
  .frame--flagged::before {
    content: '';
    position: absolute;
    inset: 0 auto 0 0;
    width: 2px;
    background: var(--sm-warn-fg, #ca8a04);
  }

  /* M2 escalation: reserved, louder treatment for the genuine allow-list
     escalations (desktop_pause / governance_negative_regression / static-rule).
     Calm-ambient thesis: saturation + the only insistent ring are spent here,
     nowhere else. */
  .frame--escalated {
    border-color: var(--sm-action-fg, #d97706);
    box-shadow: 0 0 0 2px var(--sm-action-fg, #d97706),
                0 8px 30px -12px var(--sm-action-glow, rgba(217, 119, 6, 0.45));
  }

  .frame__flag {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    padding: 0.3rem 0.85rem;
    font-size: 0.68rem;
    letter-spacing: 0.04em;
    color: var(--sm-warn-fg, #ca8a04);
    background: var(--sm-warn-bg, rgba(202, 138, 4, 0.08));
    border-bottom: 1px solid var(--sm-border, rgba(148, 163, 184, 0.16));
  }
  .frame__flag-dot {
    width: 0.5rem; height: 0.5rem; border-radius: 50%;
    background: currentColor; flex: 0 0 auto;
  }
  .frame__flag-text { font-weight: 700; text-transform: uppercase; }
  .frame__flag-reason { color: var(--sm-text-dim, #94a3b8); }

  /* THE scroll-isolation boundary (M1). overflow:auto + flex:1 + min-height:0
     keeps each frame's scroll private. */
  .frame__body {
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
    overflow-x: hidden;
    overscroll-behavior: contain;  /* don't chain scroll to the page/siblings */
    padding: 0.85rem 1rem 1.1rem;
    scrollbar-gutter: stable;
  }

  .frame__body:focus-visible {
    outline: 2px solid var(--sm-focus, #d97706);
    outline-offset: -2px;          /* inset so the ring stays inside the clip */
  }

  .frame__empty {
    margin: 0;
    color: var(--sm-text-dim, #94a3b8);
    font-size: 0.82rem;
    font-style: italic;
    opacity: 0.85;
  }

  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .frame { transition: none; }
  }
</style>
