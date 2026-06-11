<script>
  // AppShell.svelte -- the still-water scaffold (MUST M1, co-owns M3).
  //
  // The calm "still water" spine: a vertical calm-shelf that GUARANTEES the
  // three frames are present at page load (M1), renders them in the
  // per-session persisted order with a Reset control, and isolates each
  // frame's scroll. Header + ambient footer are slots the sibling units fill
  // (header session picker = u-sessionrail; footer connection dot = u-config).
  //
  // This file owns ONLY the scaffold. It does not fetch data, does not decide
  // verdicts, and does not encode any escalation policy of its own:
  //  - M2: the escalation allow-list lives in u-escalation; AppShell just
  //    forwards each frame's `escalated` / `flagged` flags from the `frames`
  //    prop. It NEVER foregrounds a frame for new_pattern/low_confidence/
  //    variance -- those arrive only as `flagged` and stay in place.
  //  - M3: AppShell holds the per-frame open-ACTION-REQUIRED counts and the
  //    debounced browser-tab total ("(N) StreamManager"), the shared half of
  //    M3 the decomposition assigns to u-shell.
  //  - M15/M16: AppShell renders frame identity from the domain-agnostic
  //    layout taxonomy only; governed-target names come from data via child
  //    units. No monitored-project vocabulary appears here.
  //  - M18: zero network I/O; pure view scaffold off the verdict hot path.
  //  - M19: no terminal multiplexer / IDE surface; just three observation
  //    shelves.
  //
  // Motion: respects prefers-reduced-motion UNLESS the FR-UI-9 settings
  // override force-allows it (mirrored onto <html data-motion="allow"> by the
  // settings unit). AppShell reflects `reducedMotion` defensively so its own
  // ambient motion is also gated.

  import { onMount, onDestroy } from 'svelte';
  import Frame from './Frame.svelte';
  import { layoutStore, FRAME_META, FRAME_KEYS } from '../stores/layout.js';

  // Per-frame view state, supplied by the composing App (which wires the
  // sibling-unit stores). Shape per key:
  //   { count, flagged, flagLabel, escalated }
  // Defaults keep the shell renderable in isolation and, crucially, keep all
  // three frames PRESENT even if a sibling store is empty -- M1.
  export let frames = {};

  // Active session id (from the header session picker / u-sessionrail). null
  // before a session is chosen; the shell still renders all three frames.
  export let sessionId = null;

  // App title text for the masthead (domain-agnostic product name only).
  export let productName = 'StreamManager';

  // Operator's FR-UI-9 reduced-motion override. When true we additionally
  // suppress ambient motion regardless of the OS media query.
  export let reducedMotionOverride = false;

  // Whether to expose the per-frame reorder + global Reset controls (M1).
  export let layoutControls = true;

  // Keep the layout store pointed at the active session so the persisted
  // arrangement + scroll follow the header picker. PRESENCE is preserved
  // across the switch because the store heals every load.
  $: layoutStore.useSession(sessionId);

  // Resolve a per-frame view-state with safe, presence-preserving defaults.
  function viewFor(key) {
    const f = frames && frames[key] ? frames[key] : {};
    return {
      count: Number.isFinite(f.count) ? f.count : 0,
      flagged: !!f.flagged,
      flagLabel: f.flagLabel || '',
      escalated: !!f.escalated,
    };
  }

  // Ordered, PRESENCE-GUARANTEED frame list. We iterate the persisted order
  // but fall back to the canonical key set, so a malformed store can never
  // shrink the rendered set below {A,B,C} -- M1.
  $: order = ($layoutStore.layout.order && $layoutStore.layout.order.length === FRAME_KEYS.length)
    ? $layoutStore.layout.order
    : [...FRAME_KEYS];

  // -- M3 (single runtime owner): browser-tab total open-action count --------
  // AppShell is the SOLE writer of document.title at runtime (u-shell M3
  // repair). TabTitle.svelte is the alternative owner but ships passive
  // (apply=false) and is not mounted, so there is exactly one writer.
  // Sum the per-frame counts and reflect into document.title with ~100ms
  // debounce, only flushing when the total actually changes. Matches the
  // frozen behavioural contract: "(N) StreamManager" when N>0 else bare name.
  let _titleLastTotal = -1;
  let _titleTimer = null;
  $: scheduleTitle(totalActions(frames));

  function totalActions(f) {
    let t = 0;
    for (const k of FRAME_KEYS) {
      const c = f && f[k] ? Number(f[k].count) : 0;
      if (Number.isFinite(c) && c > 0) t += c;
    }
    return t;
  }

  function scheduleTitle(total) {
    if (typeof document === 'undefined') return;
    if (_titleTimer != null) return; // coalesce bursts into one ~100ms flush
    _titleTimer = setTimeout(() => {
      _titleTimer = null;
      if (total === _titleLastTotal) return;
      _titleLastTotal = total;
      document.title = total > 0 ? `(${total}) ${productName}` : productName;
    }, 100);
  }

  // -- M1 Reset control ------------------------------------------------------
  // Restore canonical order + zero scroll for the active session, then
  // imperatively zero each frame body's scrollTop so the view matches state.
  function resetLayout() {
    layoutStore.reset();
    if (typeof document !== 'undefined') {
      requestAnimationFrame(() => {
        document.querySelectorAll('.frame__body').forEach((el) => { el.scrollTop = 0; });
      });
    }
  }

  function onFrameMove(e) {
    const { frameKey, delta } = e.detail || {};
    if (frameKey) layoutStore.move(frameKey, delta);
  }

  onDestroy(() => { if (_titleTimer != null) clearTimeout(_titleTimer); });
  onMount(() => {
    // Defensive initial flush so the tab title is correct on first paint.
    scheduleTitle(totalActions(frames));
  });
</script>

<div
  class="shell"
  class:shell--calm={!reducedMotionOverride}
  class:shell--has-rail={$$slots.rail}
  data-reduced-motion={reducedMotionOverride ? 'on' : 'off'}
>
  <!-- Optional left command-column: the multi-session SessionRail (graft:
       ops-command-deck). Rendered ONLY when the composing App supplies a `rail`
       slot, so AppShell stays renderable in isolation (no empty gutter) and the
       three-frame core is never gated on the rail's presence (M1). The rail
       owns its OWN internal scroll; this cell only bounds its height. The cell
       is data-agnostic scaffold -- governed-session identity is data-rendered
       inside the slotted content (M16). On narrow viewports the column collapses
       (see the media query) and the header session picker takes over scope. -->
  {#if $$slots.rail}
    <aside class="shell__rail" aria-label="Governed sessions">
      <slot name="rail" />
    </aside>
  {/if}

  <!-- Masthead: header slot (session picker / SessionRail injects here). The
       product name is rendered domain-agnostically; governed-target identity
       is data-rendered inside the slotted content (M16). -->
  <header class="shell__masthead">
    <div class="shell__brand">
      <span class="shell__mark" aria-hidden="true"></span>
      <span class="shell__name">{productName}</span>
    </div>
    <div class="shell__header-slot">
      <slot name="header" />
    </div>
    {#if layoutControls}
      <button
        type="button"
        class="shell__reset"
        on:click={resetLayout}
        title="Reset frame layout for this session"
        aria-label="Reset frame layout for this session"
      >Reset layout</button>
    {/if}
  </header>

  <!-- The three guaranteed shelves. Rendered from the persisted order, but the
       SET is always {A,B,C}. Each Frame owns its own scroll (M1). -->
  <main class="shell__shelves" aria-label="Governance observation frames">
    {#each order as key (key)}
      {@const meta = FRAME_META[key]}
      {@const v = viewFor(key)}
      <Frame
        frameKey={key}
        title={meta.title}
        hint={meta.hint}
        count={v.count}
        flagged={v.flagged}
        flagLabel={v.flagLabel}
        escalated={v.escalated}
        controls={layoutControls}
        on:move={onFrameMove}
      >
        <!-- Per-frame content slot. Sibling units inject A/B/C bodies. Named
             slots keep the wiring explicit and file-disjoint. -->
        {#if key === 'A'}<slot name="frameA" />{/if}
        {#if key === 'B'}<slot name="frameB" />{/if}
        {#if key === 'C'}<slot name="frameC" />{/if}
      </Frame>
    {/each}
  </main>

  <!-- Ambient footer: connection dot + status injected by u-config. -->
  <footer class="shell__footer">
    <slot name="footer">
      <span class="shell__footer-fallback">post-hoc observability -- {productName}</span>
    </slot>
  </footer>
</div>

<style>
  /* Vertical calm-shelf scaffold. The viewport is the only outer scroll
     surface for the masthead/footer chrome; the shelves region clamps its
     height so each Frame body scrolls INDEPENDENTLY (M1). */
  .shell {
    display: grid;
    grid-template-rows: auto 1fr auto;
    min-height: 100vh;
    height: 100vh;
    box-sizing: border-box;
    gap: 0.85rem;
    padding: 0.9rem clamp(0.85rem, 3vw, 2rem) 0.7rem;
    background: var(--sm-bg, #0b1120);
    color: var(--sm-text, #e2e8f0);
    font-family: var(--sm-font-sans, system-ui, -apple-system, 'Segoe UI', sans-serif);
  }

  /* WITH a left rail: a two-column command-deck. The rail spans all three rows
     on the left; masthead / shelves / footer stack in the main column. The rail
     track is a calm fixed-ish width (clamped to the viewport so it never starves
     the frames). Areas keep child source-order irrelevant. */
  .shell--has-rail {
    grid-template-columns: [rail] clamp(13rem, 17vw, 16.5rem) [main] minmax(0, 1fr);
    grid-template-areas:
      'rail masthead'
      'rail shelves'
      'rail footer';
    column-gap: clamp(0.7rem, 1.6vw, 1.1rem);
  }
  .shell--has-rail .shell__masthead { grid-area: masthead; }
  .shell--has-rail .shell__shelves { grid-area: shelves; }
  .shell--has-rail .shell__footer { grid-area: footer; }

  /* The rail cell: spans the full column height and BOUNDS the rail so its own
     internal lane list owns the scroll (min-height:0 lets the bounded child
     scroll instead of pushing the page). The SessionRail paints all chrome. */
  .shell__rail {
    grid-area: rail;
    min-height: 0;
    min-width: 0;
    overflow: hidden;
  }

  .shell__masthead {
    display: flex;
    align-items: center;
    gap: clamp(0.75rem, 2vw, 1.5rem);
    padding-bottom: 0.2rem;
    border-bottom: 1px solid var(--sm-border, rgba(148, 163, 184, 0.16));
  }

  .shell__brand {
    display: inline-flex;
    align-items: center;
    gap: 0.55rem;
    flex: 0 0 auto;
  }

  /* Bespoke mark: a still-water ripple, not a generic logo box. Quiet at rest. */
  .shell__mark {
    width: 0.85rem;
    height: 0.85rem;
    border-radius: 50%;
    border: 1.5px solid var(--sm-accent, #38bdf8);
    box-shadow: 0 0 0 3px var(--sm-accent-ring, rgba(56, 189, 248, 0.12));
  }

  .shell__name {
    font-family: var(--sm-font-display, var(--sm-font-sans, system-ui, sans-serif));
    /* Distinctive masthead voice: low-weight, wide tracking, small caps feel. */
    font-weight: 360;
    font-size: 1.02rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--sm-text, #e2e8f0);
  }

  .shell__header-slot { flex: 1 1 auto; min-width: 0; }

  .shell__reset {
    appearance: none;
    flex: 0 0 auto;
    border: 1px solid var(--sm-border, rgba(148, 163, 184, 0.25));
    background: transparent;
    color: var(--sm-text-dim, #94a3b8);
    font-size: 0.72rem;
    letter-spacing: 0.03em;
    padding: 0.35rem 0.7rem;
    border-radius: 6px;
    cursor: pointer;
    transition: color 0.18s ease, border-color 0.18s ease;
  }
  .shell__reset:hover { color: var(--sm-text, #e2e8f0); border-color: var(--sm-text-dim, #94a3b8); }

  /* M17: amber 2px focus ring + 2px offset on every interactive element. */
  .shell__reset:focus-visible {
    outline: 2px solid var(--sm-focus, #d97706);
    outline-offset: 2px;
  }

  /* The shelves region is the ONLY flexible row; it clamps to available
     height (min-height:0) so its children scroll internally, not the page. */
  .shell__shelves {
    min-height: 0;
    display: grid;
    grid-auto-rows: minmax(0, 1fr);
    gap: 0.85rem;
    overflow: hidden; /* children (.frame__body) own the scroll -- M1 */
  }

  .shell__footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding-top: 0.35rem;
    border-top: 1px solid var(--sm-border, rgba(148, 163, 184, 0.16));
    font-size: 0.72rem;
    color: var(--sm-text-dim, #94a3b8);
    letter-spacing: 0.02em;
  }
  .shell__footer-fallback { opacity: 0.8; }

  /* Narrow viewports: the left command-column would starve the frames, so it
     collapses and the main column reclaims the full width. Scope control falls
     back to the header session picker (which the composing App reveals at the
     same breakpoint). The three-frame core is untouched -- M1 holds. */
  @media (max-width: 55rem) {
    .shell--has-rail {
      grid-template-columns: minmax(0, 1fr);
      grid-template-areas:
        'masthead'
        'shelves'
        'footer';
    }
    .shell--has-rail .shell__rail { display: none; }
  }

  /* On taller viewports the calm vertical stack reads best; on very short
     viewports let the page scroll rather than crushing the frames flat. */
  @media (max-height: 560px) {
    .shell { height: auto; min-height: 100vh; }
    .shell__shelves { grid-auto-rows: minmax(180px, auto); overflow: visible; }
  }

  /* Reduced-motion: gate the only ambient motion (the brand mark ring pulse)
     behind BOTH the OS query and the absence of the force-allow override. */
  .shell--calm .shell__mark {
    animation: sm-ripple 6s ease-in-out infinite;
  }
  @keyframes sm-ripple {
    0%, 100% { box-shadow: 0 0 0 3px var(--sm-accent-ring, rgba(56, 189, 248, 0.12)); }
    50%      { box-shadow: 0 0 0 5px var(--sm-accent-ring, rgba(56, 189, 248, 0.06)); }
  }
  /* Operator FR-UI-9 override (data-reduced-motion="on") always wins. */
  .shell[data-reduced-motion='on'] .shell__mark { animation: none; }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .shell__mark { animation: none; }
    :global(html:not([data-motion='allow'])) .shell__reset { transition: none; }
  }
</style>
