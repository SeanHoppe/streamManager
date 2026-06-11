<!--
  VelocityHeatmap.svelte -- BETA feature "velocity-heatmap" (#19).

  An ambient L0..L4 x 30-minute LEARNING-DYNAMICS heatmap strip that lives INSIDE
  Frame A, between the scope sub-header (.fa__ctx) and the HITL pending seam
  (.fa__pending). One glance answers: is governance MATURING (mass climbing toward
  L4), STALLED (parked on the L1/L2 mid-band) or RESETTING (a bright L0 row)?

  This is the Svelte realisation of the operator-APPROVED mockup
  (reports/proposals/mockups/velocity-heatmap.html). It reuses theme.css tokens
  verbatim (the per-theme --c-allow / --c-guide / --c-block hue family + the fixed
  --badge-* state palette + --accent / --border chrome). No new color tokens.

  ============================ GOVERNANCE FLOOR ============================
  BETA GATE: the component renders NOTHING and registers NO pollers / SSE
    handlers / timers unless $betaFlags['velocity-heatmap'] is true (default OFF,
    lib/beta/registry.js). It reads the EXISTING decisionsStore (already fed by
    the one shared /events SSE in sse.js); it opens no socket and starts no
    interval of its own. The $-store autosubscription is the only subscription,
    and Svelte tears it down on destroy.

  M1 (monitor-first) / M2 (escalation-only foreground): this strip is AMBIENT.
    It NEVER auto-foregrounds a frame; it alarms quietly in place via the derived
    STATE badge. Tapping a cell only SCOPES the feed (a DOM CustomEvent the shell
    listens for); foreground policy stays solely with escalation.js.

  M4 (paired label + color, never color alone): the load-bearing signal is the
    gutter level labels (L0..L4, always visible), the in-cell COUNT digit (>=2),
    and the derived STATE BADGE (LEARNING / STALLED / RESETTING / CALM) built on
    the frozen Badge variant palette. Remove ALL hue and a fully sufficient
    monochrome signal remains. A text legend pairs every swatch with a word.

  M15 / G2 (polarity / self-exclude): the SM-own session is never bucketed. The
    strip reads decisionsStore (already self-excluded in sse.js) and applies a
    second ownSessionId backstop in bucketize(); when the operator scopes to the
    SM-own session it renders an explicit "self -- excluded" note, never cells.

  M16 (domain-agnostic): no monitored-project vocabulary. Levels are the
    canonical governance L0..L4; hashes + texts are rendered FROM DATA.

  M17 (a11y): the grid is a real 2-D roving-tabindex grid (role=grid; arrows move,
    Enter/Space filter, Escape clears); the focused cell shows the focus.css
    contract ring (2px solid accent, inset). AAA text on the card surface.

  M18 (post-hoc): pure render pass over already-streamed feed data. No
    verdict-path work, no writes.

  MOCK FALLBACK: the live gov.db is frequently ALLOW-only / sparse, so when the
    live feed carries no layered decisions in the window the strip falls back to a
    realistic mock fixture (mockHeatmap) so the feature is testable. The `usedMock`
    flag is exposed (data-used-mock) + shown as a "sample data" marker.

  FILE-DISJOINT: this component + its VelocityHeatmap-data.js helper own all the
    new code. It dispatches the DOM CustomEvent 'sm:filter-pattern-hashes' (mirrors
    EscalationHeatmap's 'sm:filter-timewindow'); the shell listens + scopes/dims
    the feed. It mints NO new bus envelope and touches NO FROZEN surface.

  ASCII-only (cp1252-safe): dash is "--".
-->
<script>
  import { onMount, onDestroy } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { decisionsStore } from '../../sse.js';
  import { selectedSessionId, getOwnSessionId } from '../../stores/session.js';
  import { readOwnProjectSlugs } from '../../api.js';
  import Badge from '../Badge.svelte';
  import {
    bucketize,
    deriveState,
    levelHueVar,
    alphaFor,
    cellLabel,
    mockHeatmap,
    LEVELS_TOP_DOWN,
    LEVEL_WORD,
    MINUTES,
    BUCKET_MS,
  } from './VelocityHeatmap-data.js';

  /** The stable BETA flag key this component gates on. */
  const FLAG_KEY = 'velocity-heatmap';

  /**
   * bucketMs: time-bucket width. 60s per the proposal; overridable for tests.
   * @type {number}
   */
  export let bucketMs = BUCKET_MS;

  /**
   * allowMock: when the live feed has no layered decisions in the window, fall
   * back to a realistic mock fixture so the strip is visible/testable. Default
   * true (tests rely on it). Set false to force a true live-only render.
   * @type {boolean}
   */
  export let allowMock = true;

  /**
   * now: epoch ms "right edge" of the axis, injectable for deterministic tests.
   * Defaults to the live clock read once per recompute (NOT a registered timer).
   * @type {number|null}
   */
  export let now = null;

  // -- gate (single source of truth: the betaFlags store) --------------------
  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // -- self-exclude (G2 / M15) -----------------------------------------------
  let ownSessionId = '';
  /** @type {Set<string>} */
  let ownProjectSlugs = new Set();

  // The session the scope picker shows. We aggregate the ALREADY self-excluded
  // decisionsStore; when a session is scoped we narrow to its rows.
  $: scopedSessionId = $selectedSessionId || null;
  $: isSelfScope = !!(ownSessionId && scopedSessionId && scopedSessionId === ownSessionId);

  // -- the live feed, scoped + self-excluded ---------------------------------
  $: feedRows = $decisionsStore || [];
  $: scopedRows = scopedSessionId
    ? feedRows.filter((r) => r && r.session_id === scopedSessionId)
    : feedRows;

  // -- aggregate (mock fallback when the live scope has no layered decisions) -
  let usedMock = false;
  /** @type {ReturnType<typeof bucketize>} */
  let agg = { buckets: [], byKey: {}, max: 1, total: 0 };
  /** @type {ReturnType<typeof deriveState>} */
  let state = deriveState(agg);

  function recompute() {
    if (!enabled || isSelfScope) {
      agg = { buckets: [], byKey: {}, max: 1, total: 0 };
      state = deriveState(agg);
      usedMock = false;
      clearFilter();
      return;
    }
    const nowMs = Number.isFinite(now) ? Number(now) : Date.now();
    const live = bucketize(scopedRows, {
      bucketMs, minutes: MINUTES, ownSessionId, now: nowMs,
    });
    if (live.total > 0 || !allowMock) {
      agg = live;
      usedMock = false;
    } else {
      agg = mockHeatmap();
      usedMock = true;
    }
    state = deriveState(agg);
  }

  // Reactive RE-RENDER (not a timer): the feed/store/flag/scope drive it; no
  // setInterval is ever registered.
  $: enabled, isSelfScope, scopedRows, bucketMs, now, allowMock, recompute();

  // ------------------------------------------------------------------------
  // Cell helpers -- a flat row-major (L4..L0) x (oldest..now) cell descriptor
  // list so the keyboard roving-tabindex + render stay trivial.
  // ------------------------------------------------------------------------

  /** @returns {Array<{level:number, minute:number, cell:any}>} a single row's cells, oldest->now. */
  function rowCells(level) {
    const out = [];
    for (let m = MINUTES - 1; m >= 0; m -= 1) {
      out.push({ level, minute: m, cell: agg.byKey[`${level}:${m}`] || null });
    }
    return out;
  }

  $: gridRows = LEVELS_TOP_DOWN.map((level) => ({ level, cells: rowCells(level) }));

  // The single tab-stop (roving): the first LIT cell, else the top-left cell.
  $: firstLitKey = (() => {
    for (const row of gridRows) {
      for (const c of row.cells) {
        if (c.cell) return `${c.level}:${c.minute}`;
      }
    }
    return gridRows.length && gridRows[0].cells.length
      ? `${gridRows[0].cells[0].level}:${gridRows[0].cells[0].minute}`
      : '';
  })();

  function hueFor(level) {
    return `var(${levelHueVar(level)})`;
  }
  function cellStyle(level, count) {
    return `background:${cssAlpha(levelHueVar(level), alphaFor(count, agg.max))};`;
  }
  /** Read a theme custom-property and apply alpha via color-mix (theme-safe). */
  function cssAlpha(varName, a) {
    // color-mix keeps us on the live theme token (obsidian/phosphor/paper) and
    // needs no hex parsing; transparent is the second mix term.
    const pct = Math.round(a * 100);
    return `color-mix(in srgb, var(${varName}) ${pct}%, transparent)`;
  }

  // ------------------------------------------------------------------------
  // Popover (hover / focus detail) -- a single shared node positioned at the
  // focused/hovered cell. Pure presentation; no network.
  // ------------------------------------------------------------------------
  /** @type {{level:number, minute:number, cell:any, top:number, left:number}|null} */
  let pop = null;

  function showPop(level, minute, el) {
    const cell = agg.byKey[`${level}:${minute}`];
    if (!cell || !el || typeof el.getBoundingClientRect !== 'function') {
      pop = null;
      return;
    }
    const r = el.getBoundingClientRect();
    const left = Math.max(8, Math.min(r.left, (typeof window !== 'undefined' ? window.innerWidth : 1024) - 340));
    pop = { level, minute, cell, top: r.bottom + 8, left };
  }
  function hidePop() { pop = null; }

  // ------------------------------------------------------------------------
  // Click -> scope the feed to a cell's pattern hashes (M18 observability).
  // Emits a DOM CustomEvent the shell listens for; toggles off on re-select.
  // ------------------------------------------------------------------------
  /** @type {string} the active cell key ("level:minute") or '' */
  let activeKey = '';
  /** @type {{level:number, minute:number, count:number, hashes:string[]}|null} */
  let activeFilter = null;

  function applyFilter(level, minute) {
    const cell = agg.byKey[`${level}:${minute}`];
    if (!cell) return;
    const key = `${level}:${minute}`;
    if (activeKey === key) { clearFilter(); return; }
    activeKey = key;
    const hashes = uniq(cell.hashes);
    activeFilter = { level, minute, count: cell.count, hashes };
    dispatchFilter(hashes, level, minute);
  }
  function clearFilter() {
    if (!activeKey && !activeFilter) return;
    activeKey = '';
    activeFilter = null;
    dispatchFilter(null, null, null);
  }
  function uniq(arr) {
    const seen = {};
    const out = [];
    for (const x of (Array.isArray(arr) ? arr : [])) {
      if (!seen[x]) { seen[x] = 1; out.push(x); }
    }
    return out;
  }

  /**
   * Dispatch the scope CustomEvent (file-disjoint; mirrors EscalationHeatmap's
   * 'sm:filter-timewindow'). Carries the scoped session_id + the pattern hashes
   * the cell covers. hashes null => clear. Domain-agnostic (M16): ids only.
   * @param {string[]|null} hashes @param {number|null} level @param {number|null} minute
   */
  function dispatchFilter(hashes, level, minute) {
    if (typeof window === 'undefined' || typeof CustomEvent === 'undefined') return;
    window.dispatchEvent(
      new CustomEvent('sm:filter-pattern-hashes', {
        detail: { sessionId: scopedSessionId, hashes, level, minute },
      }),
    );
  }

  // ------------------------------------------------------------------------
  // Keyboard: 2-D roving tabindex over the grid. Arrows move; Right == newer
  // (lower minute), Left == older. Up/Down change level. Enter/Space filter;
  // Escape clears. focusKey is the currently-focused cell key.
  // ------------------------------------------------------------------------
  let focusKey = '';
  let gridEl;

  function focusCell(level, minute) {
    const key = `${level}:${minute}`;
    focusKey = key;
    const el = gridEl && gridEl.querySelector(`[data-cell-key="${key}"]`);
    if (el && typeof el.focus === 'function') el.focus();
  }

  function moveBy(level, minute, dCol, dRow) {
    const rowIdx = LEVELS_TOP_DOWN.indexOf(level);
    let newMinute = minute - dCol; // Right (dCol +1) => newer => lower minute
    let newRowIdx = rowIdx + dRow;
    if (newMinute < 0) newMinute = 0;
    if (newMinute > MINUTES - 1) newMinute = MINUTES - 1;
    if (newRowIdx < 0) newRowIdx = 0;
    if (newRowIdx > LEVELS_TOP_DOWN.length - 1) newRowIdx = LEVELS_TOP_DOWN.length - 1;
    focusCell(LEVELS_TOP_DOWN[newRowIdx], newMinute);
  }

  /** @param {KeyboardEvent} e @param {number} level @param {number} minute */
  function onCellKeydown(e, level, minute) {
    switch (e.key) {
      case 'ArrowRight': e.preventDefault(); moveBy(level, minute, 1, 0); break;
      case 'ArrowLeft': e.preventDefault(); moveBy(level, minute, -1, 0); break;
      case 'ArrowUp': e.preventDefault(); moveBy(level, minute, 0, -1); break;
      case 'ArrowDown': e.preventDefault(); moveBy(level, minute, 0, 1); break;
      case 'Enter':
      case ' ':
        e.preventDefault();
        applyFilter(level, minute);
        break;
      case 'Escape':
        e.preventDefault();
        clearFilter();
        hidePop();
        break;
      default: break;
    }
  }

  // ------------------------------------------------------------------------
  // Collapse to a quiet dominant-level sparkline (ambient resting form).
  // ------------------------------------------------------------------------
  let collapsed = false;
  $: spark = (() => {
    const bars = [];
    for (let m = MINUTES - 1; m >= 0; m -= 1) {
      let best = null;
      for (const level of LEVELS_TOP_DOWN) {
        const c = agg.byKey[`${level}:${m}`];
        if (c && (!best || c.count > best.count)) best = c;
      }
      bars.push(best);
    }
    return bars;
  })();
  function toggleCollapse() {
    collapsed = !collapsed;
    if (collapsed) { clearFilter(); hidePop(); }
  }

  // -- lifecycle: resolve self-exclude identity once at DOM-ready ------------
  onMount(() => {
    ownSessionId = getOwnSessionId() || '';
    ownProjectSlugs = readOwnProjectSlugs();
    recompute();
    if (typeof window !== 'undefined') {
      window.addEventListener('scroll', hidePop, true);
      window.addEventListener('resize', hidePop);
    }
  });

  onDestroy(() => {
    clearFilter();
    pop = null;
    if (typeof window !== 'undefined') {
      window.removeEventListener('scroll', hidePop, true);
      window.removeEventListener('resize', hidePop);
    }
  });
</script>

{#if enabled}
  <section
    class="pvh"
    aria-label="Pattern velocity heatmap -- ambient learning-dynamics signal (BETA)"
    data-used-mock={usedMock ? 'true' : 'false'}
    data-self-scope={isSelfScope ? 'true' : 'false'}
  >
    <div class="pvh__bar">
      <button
        type="button"
        class="pvh__collapse"
        aria-expanded={!collapsed}
        on:click={toggleCollapse}
      >
        <span class="caret" aria-hidden="true">{collapsed ? '>' : 'v'}</span>
        {collapsed ? 'Expand heatmap' : 'Collapse to sparkline'}
      </button>
      <span class="pvh__title">Pattern velocity -- last 30 min</span>
      <span class="pvh__beta">BETA</span>
    </div>

    {#if isSelfScope}
      <p class="pvh__self" role="note">self -- excluded (G2)</p>
    {:else}
      <!-- M4 derived STATE BADGE (paired label + color) + plain-language read -->
      <div class="pvh__statebadge-row">
        <Badge variant={state.variant} label={state.label} reason={state.reason} />
        <span class="pvh__state-help">{state.help}</span>
      </div>

      {#if !collapsed}
        <!-- EXPANDED: gutter + 5x30 grid -->
        <div class="pvh__plot">
          <div class="pvh__gutter" aria-hidden="true">
            {#each LEVELS_TOP_DOWN as level (level)}
              <div class="pvh__gutter-cell">
                L{level}<span class="lvl-word">{LEVEL_WORD[level]}</span>
              </div>
            {/each}
          </div>

          <div
            class="pvh__rows"
            role="grid"
            bind:this={gridEl}
            aria-label="Pattern velocity grid: 5 governance levels by 30 one-minute buckets. Arrow keys move, Enter filters the feed to a cell's decisions, Escape clears."
          >
            {#each gridRows as row (row.level)}
              <div class="pvh__row" class:is-mid-anchor={row.level === 2} role="row">
                {#each row.cells as c (c.minute)}
                  {@const key = `${c.level}:${c.minute}`}
                  {@const lit = !!c.cell}
                  {@const minAgo = c.minute === 0 ? 'now' : `${c.minute} min ago`}
                  <button
                    type="button"
                    class="pvh__cell"
                    class:is-lit={lit}
                    class:is-active={activeKey === key}
                    role="gridcell"
                    data-cell-key={key}
                    tabindex={key === (focusKey || firstLitKey) ? 0 : -1}
                    style={lit ? cellStyle(c.level, c.cell.count) : ''}
                    aria-label={lit
                      ? `${cellLabel(c.cell)}. Press Enter to filter the feed.`
                      : `Level ${c.level}, ${minAgo}: no decisions.`}
                    on:mouseenter={lit ? (e) => showPop(c.level, c.minute, e.currentTarget) : undefined}
                    on:mouseleave={hidePop}
                    on:focus={lit ? (e) => showPop(c.level, c.minute, e.currentTarget) : hidePop}
                    on:blur={hidePop}
                    on:click={lit ? () => applyFilter(c.level, c.minute) : undefined}
                    on:keydown={(e) => onCellKeydown(e, c.level, c.minute)}
                  >
                    {#if lit && c.cell.count >= 2}
                      <span class="cnt" aria-hidden="true">{c.cell.count}</span>
                    {/if}
                  </button>
                {/each}
              </div>
            {/each}
          </div>
        </div>

        <div class="pvh__axis" aria-hidden="true">
          <span>30 min ago</span>
          <span>15 min</span>
          <span>now</span>
        </div>

        <!-- legend: hue reinforcement -- every swatch paired with a word -->
        <div class="pvh__legend">
          <span class="pvh__legend-item">
            <span class="pvh__legend-sw" style="background:var(--c-allow)" aria-hidden="true"></span>
            L3/L4 maturing (precedent deepening)
          </span>
          <span class="pvh__legend-item">
            <span class="pvh__legend-sw" style="background:var(--c-guide)" aria-hidden="true"></span>
            L1/L2 dwell (mid-level, watch)
          </span>
          <span class="pvh__legend-item">
            <span class="pvh__legend-sw" style="background:var(--c-block)" aria-hidden="true"></span>
            L0 reset / auto-demote
          </span>
          <span class="pvh__legend-item">
            <span class="pvh__legend-sw pvh__legend-sw--empty" aria-hidden="true"></span>
            empty bucket
          </span>
          {#if usedMock}
            <span class="pvh__mock" title="Live feed had no layered decisions in this window -- showing a sample fixture so the strip is testable.">sample data</span>
          {/if}
        </div>
      {:else}
        <!-- COLLAPSED: dominant-level sparkline (ambient resting form) -->
        <div class="pvh__spark" aria-hidden="true">
          {#each spark as best, i (i)}
            <span
              class="pvh__spark-bar"
              style={best
                ? `height:${Math.max(3, (best.count / Math.max(1, agg.max)) * 24)}px;background:${cssAlpha(levelHueVar(best.level), alphaFor(best.count, agg.max))};`
                : 'height:1px;'}
            ></span>
          {/each}
        </div>
        <p class="pvh__spark-cap">
          Dominant-level trace, last 30 min. The state badge above carries the read.
        </p>
      {/if}

      <!-- filter banner (shown after a cell scopes the feed) -->
      {#if activeFilter}
        <div class="pvh__filter" role="status">
          <span>Feed scoped to
            <code>L{activeFilter.level} @ {activeFilter.minute === 0 ? 'now' : `${activeFilter.minute} min ago`}</code>
            -- {activeFilter.count} decision{activeFilter.count === 1 ? '' : 's'} across {activeFilter.hashes.length} pattern{activeFilter.hashes.length === 1 ? '' : 's'}</span>
          <button type="button" class="pvh__filter-clear" on:click={clearFilter}>Clear (Esc)</button>
        </div>
      {/if}
    {/if}
  </section>

  <!-- shared popover (hover / focus detail) -->
  {#if pop}
    <div
      class="pvh__pop"
      role="dialog"
      aria-label="Bucket detail"
      style={`top:${pop.top}px;left:${pop.left}px;`}
    >
      <h4>
        <span class="pop-lvl">L{pop.level}</span>
        {pop.minute === 0 ? 'now' : `${pop.minute} min ago`} -- {pop.cell.count} decision{pop.cell.count === 1 ? '' : 's'}
      </h4>
      <ul>
        {#each pop.cell.hashes as h, i (i)}
          <li><code>{h}</code><span class="pop-text">{pop.cell.texts[i] || ''}</span></li>
        {/each}
      </ul>
      <div class="pop-hint">Enter / click to scope the feed to these hashes. Esc clears.</div>
    </div>
  {/if}
{/if}

<style>
  .pvh {
    margin-top: 0.5rem;
    min-width: 0;
  }

  .pvh__bar {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    flex-wrap: wrap;
  }
  .pvh__collapse {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    background: var(--bg-row, #0e141e);
    border: 1px solid var(--border, #192030);
    border-radius: 3px;
    color: var(--text-bright, #e8e0cc);
    font-family: var(--ff-system, system-ui, sans-serif);
    font-size: 0.62rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 4px 8px;
    cursor: pointer;
  }
  .pvh__collapse .caret {
    font-family: var(--font-d, ui-monospace, monospace);
    color: var(--accent, #f59e0b);
    font-weight: 700;
  }
  .pvh__collapse:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid) var(--focus-ring-color, #d97706);
    outline-offset: var(--focus-ring-offset, 2px);
  }
  .pvh__title {
    font-size: 0.62rem;
    letter-spacing: 0.13em;
    text-transform: uppercase;
    color: var(--text-ui, #8a8068);
    font-weight: 700;
  }
  .pvh__beta {
    font-size: 0.55rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--badge-timeout-fg, #7c3aed);
    border: 1px solid var(--badge-timeout-border, #c4b5fd);
    background: var(--badge-timeout-bg, #ede9fe);
    border-radius: 2px;
    padding: 2px 6px;
    margin-left: auto;
    white-space: nowrap;
  }

  .pvh__statebadge-row {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    margin: 0.75rem 0 0.55rem;
    flex-wrap: wrap;
  }
  .pvh__state-help {
    font-size: 0.66rem;
    color: var(--text-bright, #e8e0cc);
    letter-spacing: 0.01em;
  }

  .pvh__self {
    margin: 0.6rem 0 0.2rem;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 0.66rem;
    letter-spacing: 0.06em;
    color: var(--text-dim, #948870);
    font-style: italic;
  }

  /* ---- gutter + 5x30 grid ---- */
  .pvh__plot {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 0.4rem;
    align-items: stretch;
    margin-top: 0.3rem;
  }
  .pvh__gutter {
    display: grid;
    grid-template-rows: repeat(5, 14px);
    row-gap: 3px;
    align-content: start;
  }
  .pvh__gutter-cell {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    color: var(--text-bright, #e8e0cc); /* AAA -- load-bearing, never dim */
    padding-right: 0.45rem;
    white-space: nowrap;
  }
  .pvh__gutter-cell .lvl-word {
    font-family: var(--ff-system, system-ui, sans-serif);
    font-weight: 600;
    font-size: 0.5rem;
    letter-spacing: 0.04em;
    color: var(--text-dim, #948870);
    margin-left: 0.35rem;
    text-transform: uppercase;
  }

  .pvh__rows {
    display: grid;
    grid-template-rows: repeat(5, 14px);
    row-gap: 3px;
    min-width: 0;
  }
  .pvh__row {
    display: grid;
    grid-template-columns: repeat(30, 1fr);
    column-gap: 2px;
    position: relative;
  }
  .pvh__row.is-mid-anchor::after {
    content: '';
    position: absolute;
    left: 0; right: 0; bottom: -2px;
    height: 1px;
    background: var(--border-hi, rgba(245, 158, 11, 0.25));
  }

  .pvh__cell {
    height: 14px;
    border-radius: 1px;
    background: var(--bg-row, #0e141e); /* empty bucket = bare hairline */
    border: 1px solid transparent;
    position: relative;
    cursor: default;
    padding: 0;
    margin: 0;
    font: inherit;
    color: var(--text-bright, #e8e0cc);
    display: block;
  }
  .pvh__cell.is-lit {
    cursor: pointer;
    border-color: rgba(255, 255, 255, 0.06);
  }
  .pvh__cell .cnt {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 9px;
    font-weight: 700;
    line-height: 1;
    color: var(--text-bright, #e8e0cc);
    pointer-events: none;
  }
  .pvh__cell.is-active {
    box-shadow: 0 0 0 2px var(--accent, #f59e0b) inset;
  }
  .pvh__cell:focus-visible {
    outline: none;
    box-shadow: 0 0 0 var(--focus-ring-width, 2px) var(--focus-ring-color, #d97706) inset;
    z-index: 2;
  }
  .pvh__cell.is-active:focus-visible {
    box-shadow: 0 0 0 2px var(--accent, #f59e0b) inset,
      0 0 0 var(--focus-ring-width, 2px) var(--focus-ring-color, #d97706);
  }

  .pvh__axis {
    display: flex;
    justify-content: space-between;
    margin: 0.35rem 0 0;
    padding-left: calc(2.6rem);
    font-size: 0.55rem;
    color: var(--text-dim, #948870);
    letter-spacing: 0.04em;
  }

  .pvh__legend {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.4rem 0.9rem;
    margin-top: 0.7rem;
    font-size: 0.6rem;
    color: var(--text-bright, #e8e0cc);
    letter-spacing: 0.02em;
  }
  .pvh__legend-item { display: inline-flex; align-items: center; gap: 0.4rem; }
  .pvh__legend-sw {
    width: 11px; height: 11px; border-radius: 2px; flex: 0 0 auto;
    border: 1px solid rgba(255, 255, 255, 0.12);
  }
  .pvh__legend-sw--empty { background: var(--bg-row, #0e141e); }
  .pvh__mock {
    color: var(--badge-ar-fg, #d97706);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    font-size: 0.55rem;
  }

  /* ---- collapsed sparkline ---- */
  .pvh__spark {
    display: flex;
    align-items: flex-end;
    gap: 2px;
    height: 30px;
    margin-top: 0.6rem;
    padding: 0.3rem 0.4rem;
    background: var(--bg-row, #0e141e);
    border: 1px solid var(--border, #192030);
    border-radius: 3px;
  }
  .pvh__spark-bar {
    flex: 1 1 0;
    min-width: 0;
    background: var(--accent-glow, rgba(245, 158, 11, 0.35));
    border-radius: 1px 1px 0 0;
  }
  .pvh__spark-cap {
    font-size: 0.55rem;
    color: var(--text-dim, #948870);
    letter-spacing: 0.06em;
    margin: 0.35rem 0 0;
  }

  /* ---- filter banner ---- */
  .pvh__filter {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-top: 0.7rem;
    padding: 0.45rem 0.6rem;
    background: var(--accent-dim, rgba(245, 158, 11, 0.09));
    border: 1px solid var(--border-hi, rgba(245, 158, 11, 0.25));
    border-radius: 3px;
    font-size: 0.66rem;
    color: var(--text-bright, #e8e0cc);
  }
  .pvh__filter code {
    font-family: var(--font-d, ui-monospace, monospace);
    color: var(--accent, #f59e0b);
  }
  .pvh__filter-clear {
    margin-left: auto;
    background: var(--bg-row, #0e141e);
    border: 1px solid var(--border, #192030);
    border-radius: 3px;
    color: var(--text-bright, #e8e0cc);
    font-size: 0.6rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 3px 8px;
    cursor: pointer;
  }
  .pvh__filter-clear:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid) var(--focus-ring-color, #d97706);
    outline-offset: var(--focus-ring-offset, 2px);
  }

  /* ---- popover ---- */
  .pvh__pop {
    position: fixed;
    z-index: 50;
    max-width: 320px;
    background: var(--bg-card, #0c1118);
    border: 1px solid var(--border-hi, rgba(245, 158, 11, 0.25));
    border-radius: 5px;
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.55);
    padding: 0.7rem 0.8rem;
    font-size: 0.7rem;
    color: var(--text-bright, #e8e0cc);
    pointer-events: none;
  }
  .pvh__pop h4 {
    margin: 0 0 0.4rem;
    font-size: 0.66rem;
    letter-spacing: 0.04em;
    color: var(--text-bright, #e8e0cc);
    display: flex; align-items: baseline; gap: 0.5rem;
  }
  .pvh__pop .pop-lvl {
    font-family: var(--font-d, ui-monospace, monospace);
    color: var(--accent, #f59e0b);
    font-weight: 700;
  }
  .pvh__pop ul { margin: 0; padding: 0; list-style: none; }
  .pvh__pop li {
    display: flex;
    gap: 0.5rem;
    padding: 2px 0;
    border-top: 1px solid var(--border, #192030);
  }
  .pvh__pop li:first-child { border-top: none; }
  .pvh__pop code {
    font-family: var(--font-d, ui-monospace, monospace);
    color: var(--text-bright, #e8e0cc);
    background: var(--bg-row-alt, #0b1018);
    border-radius: 2px;
    padding: 0 4px;
    flex: 0 0 auto;
  }
  .pvh__pop .pop-text { color: var(--text, #b8b098); }
  .pvh__pop .pop-hint {
    margin-top: 0.45rem;
    font-size: 0.58rem;
    color: var(--text-dim, #948870);
    letter-spacing: 0.03em;
  }
</style>
