<script>
  // FrameHeader.svelte -- still-water frame header (MUST M3).
  //
  // Renders a frame's calm title row plus a LIVE open-ACTION-REQUIRED count.
  // The count is the per-frame half of M3 (the browser-tab total is the
  // co-owned u-tabtitle half, fed from the same source of truth). This
  // component is presentation-only: it receives `count` reactively and never
  // pulls data itself -- post-hoc observability, never on the verdict hot
  // path (M18).
  //
  // Variable-weight typographic severity (graft: monitor-first-elevated):
  // severity is encoded in TYPE EMPHASIS (weight + tracking + a tabular
  // numeral), not in chrome. At rest the header is whisper-quiet slate; a
  // non-zero action count lifts the numeral's weight and ink. The count
  // pill is ALWAYS a paired label+number ("ACTION" + N) -- color is never the
  // sole signal (the M4 paired-signal discipline applied to the header).
  //
  // KingMode craft: an asymmetric hairline "tide mark" under the title whose
  // ink tracks severity, and a hanging frame-key glyph in the left gutter for
  // a bespoke, non-template silhouette.

  export let frameKey = '';      // 'A' | 'B' | 'C' -- UI taxonomy, not domain vocab (M16)
  export let title = '';         // domain-agnostic frame title from layout meta
  export let hint = '';          // optional sub-label
  export let count = 0;          // live open-ACTION-REQUIRED count (M3)
  export let controls = false;   // show reorder/reset affordances (owned by parent)

  // Reorder + reset intents bubble to AppShell, which owns the layout store.
  import { createEventDispatcher } from 'svelte';
  const dispatch = createEventDispatcher();

  $: active = count > 0;
  // Stable, accessible status sentence. Read by SR users and exposed as the
  // count pill's title so the trigger meaning is never color-only (M4 spirit).
  $: countLabel = active
    ? `${count} action${count === 1 ? '' : 's'} required in ${title}`
    : `No action required in ${title}; observing`;
</script>

<header class="fh" class:fh--active={active} aria-label={title}>
  <span class="fh__glyph" aria-hidden="true">{frameKey}</span>

  <div class="fh__id">
    <h2 class="fh__title">{title}</h2>
    {#if hint}<p class="fh__hint">{hint}</p>{/if}
  </div>

  <div class="fh__actions">
    {#if controls}
      <div class="fh__reorder" role="group" aria-label={`Reorder ${title}`}>
        <button
          type="button"
          class="fh__btn"
          title={`Move ${title} up`}
          aria-label={`Move ${title} up`}
          on:click={() => dispatch('move', { frameKey, delta: -1 })}
        >&uarr;</button>
        <button
          type="button"
          class="fh__btn"
          title={`Move ${title} down`}
          aria-label={`Move ${title} down`}
          on:click={() => dispatch('move', { frameKey, delta: 1 })}
        >&darr;</button>
      </div>
    {/if}

    <!-- M3: live count. Paired label+number; never color-alone. The data-count
         attribute lets the render-validator (S2) assert presence + value. -->
    <span
      class="fh__count"
      class:fh__count--active={active}
      data-count={count}
      data-frame={frameKey}
      title={countLabel}
      aria-label={countLabel}
    >
      <span class="fh__count-tag">ACTION</span>
      <span class="fh__count-num">{count}</span>
    </span>
  </div>

  <span class="fh__tide" aria-hidden="true"></span>
</header>

<style>
  /* All color via CSS custom properties so the three themes (obsidian /
     phosphor / paper) stay swappable through the u-theme layer. Defaults
     here are inert fallbacks, not a 4th theme. */
  .fh {
    display: grid;
    grid-template-columns: auto 1fr auto;
    grid-template-rows: auto auto;
    align-items: baseline;
    column-gap: 0.85rem;
    padding: 0.7rem 1rem 0.55rem;
    position: relative;
    border-bottom: 1px solid var(--sm-border, rgba(148, 163, 184, 0.18));
    background: var(--sm-frame-head-bg, transparent);
  }

  /* Hanging frame-key glyph -- asymmetric left gutter, intentionally quiet. */
  .fh__glyph {
    grid-row: 1 / span 2;
    align-self: center;
    font-family: var(--sm-font-mono, ui-monospace, monospace);
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    line-height: 1;
    color: var(--sm-text-faint, rgba(148, 163, 184, 0.55));
    width: 1.1rem;
    text-align: center;
    user-select: none;
  }

  .fh__id { grid-column: 2; grid-row: 1; min-width: 0; }

  .fh__title {
    margin: 0;
    font-family: var(--sm-font-display, var(--sm-font-sans, system-ui, sans-serif));
    /* Variable-weight severity: resting title is calm regular weight. */
    font-weight: 460;
    font-size: 0.96rem;
    letter-spacing: 0.005em;
    line-height: 1.15;
    color: var(--sm-text, #e2e8f0);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .fh__hint {
    grid-column: 2;
    grid-row: 2;
    margin: 0.1rem 0 0;
    font-size: 0.7rem;
    letter-spacing: 0.02em;
    color: var(--sm-text-dim, #94a3b8);
  }

  .fh__actions {
    grid-column: 3;
    grid-row: 1 / span 2;
    align-self: center;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
  }

  .fh__reorder { display: inline-flex; gap: 0.15rem; }

  .fh__btn {
    appearance: none;
    border: 1px solid var(--sm-border, rgba(148, 163, 184, 0.25));
    background: transparent;
    color: var(--sm-text-dim, #94a3b8);
    font-size: 0.72rem;
    line-height: 1;
    width: 1.55rem;
    height: 1.55rem;
    border-radius: 5px;
    cursor: pointer;
    transition: color 0.18s ease, border-color 0.18s ease, background 0.18s ease;
  }
  .fh__btn:hover { color: var(--sm-text, #e2e8f0); border-color: var(--sm-text-dim, #94a3b8); }

  /* M17: 2px solid amber focus ring + 2px offset on every interactive el. */
  .fh__btn:focus-visible,
  .fh__count:focus-visible {
    outline: 2px solid var(--sm-focus, #d97706);
    outline-offset: 2px;
  }

  /* M3 / M4 spirit: the count is a paired label ("ACTION") + tabular number.
     Color shifts only as a SECOND channel on top of the always-present text. */
  .fh__count {
    display: inline-flex;
    align-items: baseline;
    gap: 0.35rem;
    padding: 0.18rem 0.5rem;
    border-radius: 999px;
    border: 1px solid transparent;
    background: var(--sm-count-bg, rgba(148, 163, 184, 0.1));
    transition: background 0.22s ease, border-color 0.22s ease, color 0.22s ease;
  }

  .fh__count-tag {
    font-size: 0.6rem;
    font-weight: 600;
    letter-spacing: 0.13em;
    text-transform: uppercase;
    color: var(--sm-text-faint, rgba(148, 163, 184, 0.7));
  }

  .fh__count-num {
    font-family: var(--sm-font-mono, ui-monospace, monospace);
    font-variant-numeric: tabular-nums;
    font-size: 0.86rem;
    font-weight: 520;
    line-height: 1;
    color: var(--sm-text-dim, #94a3b8);
    min-width: 0.9ch;
    text-align: right;
  }

  /* ACTIVE state: severity rises through TYPE first (weight + ink), with the
     amber paired-badge palette as the supporting channel. Never color-alone. */
  .fh--active .fh__title { font-weight: 600; letter-spacing: 0.012em; color: var(--sm-text, #f8fafc); }
  .fh__count--active {
    background: var(--sm-action-bg, #fef3c7);
    border-color: var(--sm-action-fg, #d97706);
  }
  .fh__count--active .fh__count-tag { color: var(--sm-action-fg, #b45309); }
  .fh__count--active .fh__count-num { color: var(--sm-action-fg, #b45309); font-weight: 680; }

  /* Asymmetric "tide mark": a short hairline under the title gutter that
     deepens its ink when the frame holds open actions. Decorative only. */
  .fh__tide {
    grid-column: 2 / 3;
    grid-row: 2;
    align-self: end;
    justify-self: start;
    margin-top: 0.35rem;
    height: 1px;
    width: 2.25rem;
    background: var(--sm-text-faint, rgba(148, 163, 184, 0.35));
    transition: width 0.3s ease, background 0.3s ease;
  }
  .fh--active .fh__tide { width: 3.5rem; background: var(--sm-action-fg, #d97706); }

  @media (prefers-reduced-motion: reduce) {
    /* Honor the OS preference unless the operator force-allows motion via the
       FR-UI-9 override on <html data-motion="allow">. */
    :global(html:not([data-motion='allow'])) .fh,
    :global(html:not([data-motion='allow'])) .fh__count,
    :global(html:not([data-motion='allow'])) .fh__tide,
    :global(html:not([data-motion='allow'])) .fh__btn { transition: none; }
  }
</style>
