<!--
  EscalationHeatmap.svelte -- BETA feature "escalation-heatmap" (#14).

  A 12px-wide vertical heatmap GUTTER pinned to the left margin of the Monitor
  frame (Frame A), parallel to the decision stream. One dot per 30s wall-clock
  bucket; color = peak severity in that bucket; size + opacity = density; quiet
  buckets are transparent. Glance => bursty-vs-steady + exactly-WHEN in ~500ms.
  Click / keyboard a bucket => scope the feed to that 30s window via a DOM
  CustomEvent (the shell DIMS out-of-window rows, never hides them).

  This is the Svelte realisation of the operator-APPROVED mockup
  (reports/proposals/mockups/escalation-heatmap.html). It reuses theme.css
  tokens verbatim (the per-theme --c-guide / --c-intervene / --c-block severity
  palette + --calm-* / --accent / --border chrome) -- no new color tokens.

  ============================ GOVERNANCE FLOOR ============================
  BETA GATE: the component renders NOTHING and registers NO pollers / SSE
    handlers / timers unless $betaFlags['escalation-heatmap'] is true (default
    OFF). It reads the EXISTING decisionsStore (already fed by the one shared
    /events SSE in sse.js); it opens no socket and starts no interval of its own.
    The single store subscription is created on mount and torn down on destroy,
    and only when the flag is ON.

  M2 (escalation-only foreground): this gutter is ambient at rest -- a hairline
    of dots, no motion, no layout-steal (its 12px slot is reserved by the host
    grid). It NEVER auto-foregrounds a frame; tapping a bucket only scopes the
    feed. Foreground policy stays solely with the escalation.js allow-list.

  M4 (paired label + color, never color alone): every dot carries a data-built
    text title + aria-label naming the literal severity state in WORDS; severity
    is ALSO encoded as size (BLOCK ring) + opacity, so color is never the only
    channel. A text legend pairs each swatch with its written action name.

  M15 / G2 (polarity / self-exclude): the SM-own session is never bucketed. The
    gutter reads decisionsStore (already self-excluded in sse.js) and applies a
    second ownSessionId backstop in bucketize(); when the scoped session is the
    SM-own one the gutter renders an explicit "self -- excluded" note, never dots.

  M16 (domain-agnostic): no monitored-project vocabulary. Session identity and
    bucket text are rendered FROM DATA.

  M17 (a11y): the gutter is a real listbox (role=listbox, arrow-key roving
    tabindex, Enter/Space apply, Escape clear); the focused bucket shows a 2px
    solid accent ring + 2px offset. Reduced motion honoured.

  M18 (post-hoc): pure render pass over already-streamed feed data. No
    verdict-path work, no writes.

  MOCK FALLBACK: the live gov.db is frequently ALLOW-only (zero escalations), so
    when the live feed carries no escalation rows the gutter falls back to a
    realistic mock fixture (mockEscalationRows) so the feature is testable. The
    `usedMock` flag is exposed for the test harness and shown in the foot note.

  FILE-DISJOINT: this component + its EscalationHeatmap-* helper own all the new
    code. It dispatches the DOM CustomEvent 'sm:filter-timewindow' (mirrors
    EscalationRail's 'sm:focus-session'); the shell listens and scopes the feed.

  ASCII-only (cp1252-safe): dash is "--".
-->
<script>
  import { onMount, onDestroy } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { decisionsStore } from '../../sse.js';
  import { selectedSessionId, getOwnSessionId } from '../../stores/session.js';
  import { readOwnProjectSlugs } from '../../api.js';
  import {
    bucketize,
    bucketText,
    mockEscalationRows,
    hhmm,
    hhmmss,
    BUCKET_MS,
  } from './EscalationHeatmap-data.js';

  /** The stable BETA flag key this component gates on. */
  const FLAG_KEY = 'escalation-heatmap';

  /**
   * bucketMs: window width. 30s per the proposal; overridable for tests.
   * @type {number}
   */
  export let bucketMs = BUCKET_MS;

  /**
   * allowMock: when the live feed has no escalations, fall back to a realistic
   * mock fixture so the gutter is visible/testable. Default true (tests rely on
   * it). Set false to force a true live-only render.
   * @type {boolean}
   */
  export let allowMock = true;

  /**
   * now: epoch ms "end of axis", injectable for deterministic tests. Defaults to
   * the live clock read once per recompute (NOT a registered timer -- the
   * existing app clock already drives re-render cadence elsewhere).
   * @type {number|null}
   */
  export let now = null;

  // -- gate (single source of truth: the betaFlags store) --------------------
  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // -- self-exclude (G2 / M15) -----------------------------------------------
  // Resolve the SM-own session id + own project slugs once. Used as a cheap
  // backstop inside bucketize() and to render the explicit "self -- excluded"
  // state when the operator scopes to the SM-own session.
  let ownSessionId = '';
  /** @type {Set<string>} */
  let ownProjectSlugs = new Set();

  // The session whose identity the scope picker shows. The gutter aggregates the
  // ALREADY self-excluded decisionsStore; when the operator has explicitly
  // scoped to a session we narrow to that session_id.
  $: scopedSessionId = $selectedSessionId || null;

  // Is the scoped session the SM-own one? (Belt-and-suspenders: selectedSession
  // can never resolve to ownSessionId per session.js, but guard anyway so the
  // gutter shows the calm self note instead of silently empty if it ever did.)
  $: isSelfScope = !!(ownSessionId && scopedSessionId && scopedSessionId === ownSessionId);

  // -- the live feed, scoped + self-excluded ---------------------------------
  // decisionsStore is fed by the SINGLE shared SSE (sse.js). We do NOT open our
  // own stream. When a session is scoped we narrow to its rows; otherwise all
  // governed (already self-excluded) rows feed the gutter.
  $: feedRows = $decisionsStore || [];
  $: scopedRows = scopedSessionId
    ? feedRows.filter((r) => r && r.session_id === scopedSessionId)
    : feedRows;

  // -- aggregate (mock fallback when the live scope has no escalations) -------
  let usedMock = false;
  /** @type {ReturnType<typeof bucketize>} */
  let agg = { buckets: [], max: 1, bucketMs, escalationCount: 0 };

  function recompute() {
    if (!enabled || isSelfScope) {
      agg = { buckets: [], max: 1, bucketMs, escalationCount: 0 };
      usedMock = false;
      return;
    }
    const nowMs = Number.isFinite(now) ? Number(now) : Date.now();
    const live = bucketize(scopedRows, { bucketMs, ownSessionId, now: nowMs });
    if (live.escalationCount > 0 || !allowMock) {
      agg = live;
      usedMock = false;
      return;
    }
    // No live escalations -> realistic mock so the gutter is visible + testable.
    const rows = mockEscalationRows({ now: nowMs, bucketMs });
    agg = bucketize(rows, { bucketMs, ownSessionId, now: nowMs });
    usedMock = true;
  }

  // Recompute on any input change. This is a reactive RE-RENDER, not a timer:
  // the feed/store/flag/scope drive it; no setInterval is ever registered here.
  $: enabled, isSelfScope, scopedRows, bucketMs, now, allowMock, recompute();

  // newest at TOP: render the contiguous (ascending) buckets reversed.
  $: renderBuckets = agg.buckets.slice().reverse();
  // the indexes (into renderBuckets) of buckets that actually have escalations;
  // keyboard nav + click only land on these (quiet buckets are inert).
  $: navIdx = renderBuckets
    .map((b, i) => (b.total > 0 ? i : -1))
    .filter((i) => i >= 0);

  // -- the active time-window filter (selected bucket) -----------------------
  /** @type {{ t0:number, t1:number, label:string }|null} */
  let activeWindow = null;
  let focusPos = -1; // index INTO navIdx of the keyboard-focused bucket

  function isSelected(b) {
    return !!(activeWindow && b.t === activeWindow.t0);
  }

  /**
   * Apply (or toggle off) the time-window for the bucket at renderBuckets[i].
   * Emits the DOM CustomEvent the shell listens for. Pure observability (M18).
   * @param {number} i index into renderBuckets
   */
  function applyWindow(i) {
    const b = renderBuckets[i];
    if (!b || b.total === 0) return;
    const t0 = b.t;
    const t1 = b.t + agg.bucketMs;
    if (activeWindow && activeWindow.t0 === t0) {
      clearWindow();
      return;
    }
    activeWindow = { t0, t1, label: `${hhmm(t0)} -- ${hhmmss(t1)}` };
    dispatchWindow(t0, t1);
  }

  function clearWindow() {
    activeWindow = null;
    dispatchWindow(null, null);
  }

  /**
   * Dispatch the scope CustomEvent (file-disjoint, mirrors EscalationRail's
   * 'sm:focus-session'). Carries the scoped session_id + the window bounds in
   * epoch MS. t0/t1 null => clear. Domain-agnostic (M16): ids/timestamps only.
   * @param {number|null} t0 @param {number|null} t1
   */
  function dispatchWindow(t0, t1) {
    if (typeof window === 'undefined' || typeof CustomEvent === 'undefined') return;
    window.dispatchEvent(
      new CustomEvent('sm:filter-timewindow', {
        detail: { sessionId: scopedSessionId, t0, t1 },
      }),
    );
  }

  // -- keyboard listbox (roving tabindex) ------------------------------------
  function focusBucket(pos) {
    if (!navIdx.length) return;
    focusPos = Math.max(0, Math.min(navIdx.length - 1, pos));
    const renderI = navIdx[focusPos];
    const el = listEl && listEl.querySelector(`[data-render-i="${renderI}"]`);
    if (el && typeof el.focus === 'function') el.focus();
  }

  /** @param {KeyboardEvent} e */
  function onListKeydown(e) {
    if (!navIdx.length) return;
    switch (e.key) {
      case 'ArrowUp':
        e.preventDefault();
        focusBucket(focusPos <= 0 ? 0 : focusPos - 1);
        break;
      case 'ArrowDown':
        e.preventDefault();
        focusBucket(focusPos < 0 ? 0 : focusPos + 1);
        break;
      case 'Home':
        e.preventDefault();
        focusBucket(0);
        break;
      case 'End':
        e.preventDefault();
        focusBucket(navIdx.length - 1);
        break;
      case 'Enter':
      case ' ':
        e.preventDefault();
        if (focusPos < 0) focusBucket(0);
        else applyWindow(navIdx[focusPos]);
        break;
      case 'Escape':
        e.preventDefault();
        clearWindow();
        break;
      default:
        break;
    }
  }

  function onListFocus() {
    if (focusPos < 0 && navIdx.length) focusBucket(0);
  }

  /** @param {number} i */
  function onBucketClick(i) {
    applyWindow(i);
  }

  // -- lifecycle: the ONLY subscription, created on mount, gated on the flag ---
  // We subscribe to nothing imperatively here -- the $-store autosubscriptions
  // above are torn down by Svelte on destroy. We only resolve the self-exclude
  // identity once at DOM-ready (the meta is server-injected into <head>).
  let listEl;
  let mounted = false;

  onMount(() => {
    ownSessionId = getOwnSessionId() || '';
    ownProjectSlugs = readOwnProjectSlugs();
    mounted = true;
    recompute();
  });

  onDestroy(() => {
    mounted = false;
    activeWindow = null;
  });
</script>

{#if enabled}
  <nav class="ehm" aria-label="Escalation timeline heatmap (BETA)">
    <span class="ehm__spine" aria-hidden="true"></span>

    {#if isSelfScope}
      <!-- G2 / M15: the SM-own session is never governed by SM. No dots. -->
      <p class="ehm__self" role="note">self -- excluded (G2)</p>
    {:else if navIdx.length === 0}
      <!-- Calm/empty: a scoped session with zero escalations. Slot reserved. -->
      <p class="ehm__empty" role="note">No escalations in span</p>
    {:else}
      <ul
        class="ehm__list"
        bind:this={listEl}
        role="listbox"
        tabindex="0"
        aria-label={`Escalation timeline, newest first. ${navIdx.length} bucket${navIdx.length === 1 ? '' : 's'} with escalations. Arrow keys move between them, Enter applies a time-window filter, Escape clears it.`}
        on:keydown={onListKeydown}
        on:focus={onListFocus}
      >
        {#each renderBuckets as b, i (b.t)}
          {@const active = b.total > 0}
          {@const dens = active ? b.total / agg.max : 0}
          {@const opacity = active ? (0.55 + 0.45 * dens).toFixed(2) : '0'}
          {@const txt = bucketText(b)}
          {@const selected = isSelected(b)}
          <li
            class="ehm__bucket"
            data-render-i={i}
            data-active={active ? 'true' : 'false'}
            data-peak={b.peak || ''}
            data-selected={selected ? 'true' : 'false'}
            role="option"
            aria-selected={selected ? 'true' : 'false'}
            tabindex={active ? -1 : undefined}
            aria-hidden={active ? undefined : 'true'}
            title={active ? txt : undefined}
            aria-label={active ? txt : undefined}
            on:click={active ? () => onBucketClick(i) : undefined}
          >
            <span class="ehm__dot" aria-hidden="true" style={`opacity:${opacity}`}></span>
            {#if active}
              <span class="ehm__flyout" aria-hidden="true">
                <span class="ehm__swatch" data-peak={b.peak || ''}></span>
                <span class="ehm__flytext">{txt}</span>
              </span>
            {/if}
          </li>
        {/each}
      </ul>

      <div class="ehm__foot">
        <span class="ehm__legend" aria-label="Severity legend (paired label and color)">
          <span class="ehm__k"><span class="ehm__sw g" aria-hidden="true"></span>GUIDE</span>
          <span class="ehm__k"><span class="ehm__sw i" aria-hidden="true"></span>INTERVENE</span>
          <span class="ehm__k"><span class="ehm__sw b" aria-hidden="true"></span>BLOCK</span>
        </span>
        {#if activeWindow}
          <span class="ehm__win" role="status">
            window {activeWindow.label}
            <button type="button" class="ehm__clear" on:click={clearWindow}>Clear</button>
          </span>
        {/if}
        {#if usedMock}
          <span class="ehm__mock" title="Live feed had no escalations -- showing a sample fixture so the gutter is testable.">sample data</span>
        {/if}
      </div>
    {/if}
  </nav>
{/if}

<style>
  /* The gutter holds a stable narrow column so toggling never reflows the feed
     (M2 no-layout-steal). Ambient at rest: a hairline spine + quiet dots. */
  .ehm {
    position: relative;
    width: 100%;
    min-width: 12px;
    display: flex;
    flex-direction: column;
    align-items: stretch;
  }

  /* faint baseline ("tide line") the dots sit on. */
  .ehm__spine {
    position: absolute;
    top: 0;
    bottom: 0;
    left: 6px;
    width: 1px;
    background: var(--calm-hairline, var(--border, #192030));
  }

  .ehm__list {
    position: relative;
    z-index: 1;
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    outline: none;
  }

  .ehm__bucket {
    position: relative;
    height: 8px;
    display: flex;
    align-items: center;
    justify-content: flex-start;
    padding-left: 2px;
    cursor: default;
  }
  .ehm__bucket[data-active='true'] {
    cursor: pointer;
  }

  /* the dot: color = peak severity; size + opacity = density. */
  .ehm__dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: transparent; /* quiet buckets stay transparent */
    transition: box-shadow 0.15s ease;
  }
  .ehm__bucket[data-peak='GUIDE'] .ehm__dot {
    background: var(--c-guide, #eab308);
  }
  .ehm__bucket[data-peak='INTERVENE'] .ehm__dot {
    background: var(--c-intervene, #f97316);
  }
  /* BLOCK: +1px radius + an outer ring so the heaviest signal is heavier in INK,
     not only in hue (M4 -- color is never the sole channel). */
  .ehm__bucket[data-peak='BLOCK'] .ehm__dot {
    background: var(--c-block, #ef4444);
    width: 8px;
    height: 8px;
    box-shadow:
      0 0 0 1.5px var(--calm-surface, var(--bg-card, #0c1118)),
      0 0 0 2.5px var(--c-block, #ef4444);
  }

  /* selected window: 2px accent ring + offset (M17). */
  .ehm__bucket[data-selected='true']::after {
    content: '';
    position: absolute;
    inset: -3px -4px -3px -2px;
    border: 2px solid var(--calm-accent, var(--accent, #f59e0b));
    border-radius: 4px;
    pointer-events: none;
  }
  /* keyboard focus reuses the same accent ring (M17). */
  .ehm__bucket:focus-visible {
    outline: 2px solid var(--calm-accent, var(--accent, #f59e0b));
    outline-offset: 2px;
    border-radius: 3px;
  }
  .ehm__list:focus-visible {
    outline: none;
  }

  /* hover/focus flyout chip: the SAME state in WORDS next to a colored swatch
     (M4 paired). Appears beside the gutter; never shifts the layout. */
  .ehm__flyout {
    position: absolute;
    left: 16px;
    top: 50%;
    transform: translateY(-50%);
    z-index: 5;
    white-space: nowrap;
    display: none;
    align-items: center;
    gap: 8px;
    background: var(--calm-surface-row, var(--bg-row, #0e141e));
    border: 1px solid var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25)));
    border-radius: 5px;
    padding: 5px 9px;
    box-shadow: 0 8px 24px -10px rgba(0, 0, 0, 0.7);
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 11px;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
  }
  .ehm__bucket[data-active='true']:hover .ehm__flyout,
  .ehm__bucket:focus-visible .ehm__flyout {
    display: inline-flex;
  }
  .ehm__swatch {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    flex: 0 0 auto;
    background: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .ehm__swatch[data-peak='GUIDE'] {
    background: var(--c-guide, #eab308);
  }
  .ehm__swatch[data-peak='INTERVENE'] {
    background: var(--c-intervene, #f97316);
  }
  .ehm__swatch[data-peak='BLOCK'] {
    background: var(--c-block, #ef4444);
    box-shadow:
      0 0 0 1.5px var(--calm-surface-row, var(--bg-row, #0e141e)),
      0 0 0 2.5px var(--c-block, #ef4444);
  }

  /* the self-exclude + empty notes: calm, vertical, never a wall of dots. */
  .ehm__self,
  .ehm__empty {
    margin: 8px 0 0;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10px;
    letter-spacing: 0.06em;
    color: var(--calm-ink-quiet, var(--text-dim, #94a3b8));
    writing-mode: vertical-rl;
    transform: rotate(180deg);
    font-style: italic;
  }

  /* foot: paired legend + the active-window readout + the mock marker. */
  .ehm__foot {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-top: 8px;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10px;
    color: var(--calm-ink-quiet, var(--text-dim, #94a3b8));
  }
  .ehm__legend {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .ehm__k {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    white-space: nowrap;
  }
  .ehm__sw {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex: 0 0 auto;
  }
  .ehm__sw.g {
    background: var(--c-guide, #eab308);
  }
  .ehm__sw.i {
    background: var(--c-intervene, #f97316);
  }
  .ehm__sw.b {
    background: var(--c-block, #ef4444);
    box-shadow:
      0 0 0 1px var(--calm-surface, var(--bg-card, #0c1118)),
      0 0 0 2px var(--c-block, #ef4444);
    width: 9px;
    height: 9px;
  }
  .ehm__win {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
  }
  .ehm__clear {
    appearance: none;
    background: transparent;
    border: 1px solid var(--calm-hairline, var(--border, #192030));
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    border-radius: 3px;
    font-size: 10px;
    padding: 1px 6px;
    cursor: pointer;
    letter-spacing: 0.04em;
  }
  .ehm__clear:focus-visible {
    outline: 2px solid var(--calm-accent, var(--accent, #f59e0b));
    outline-offset: 2px;
  }
  .ehm__mock {
    color: var(--badge-ar-fg, #d97706);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .ehm__dot {
      transition: none;
    }
  }
  :global(html[data-motion='reduce']) .ehm__dot {
    transition: none;
  }
</style>
