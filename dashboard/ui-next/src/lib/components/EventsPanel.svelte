<script context="module">
  // EventsPanel.svelte -- the collapsible bus-event log, type-color-coded by
  // the EXACT named-event type names (FROZEN contract).
  //
  // BEHAVIOURAL CONTRACT (preserved from the live evlog):
  //  - Collapsible panel (SHOW/HIDE), with PAUSE (freeze ingestion) and CLEAR
  //    controls. Mirrors the live evlog-toggle / mirror-pause / clear surface.
  //  - Each row is color-coded by its EXACT event_type, via a frozen class
  //    map. Unknown types fall back to a neutral "default" class. The type
  //    name is ALWAYS rendered as TEXT (M4 spirit: color is never the sole
  //    signal -- the exact type string is the load-bearing label).
  //  - The recognized type set is the union of the live `_KNOWN_EVT_CLASSES`
  //    and the spec's named SSE event list, so every contract event has a
  //    deterministic color.
  //
  // M16 (domain-agnostic): event type names are the SM bus vocabulary (the
  // governance product's own taxonomy), NOT monitored-project vocabulary;
  // content is rendered from DATA. M15: rows are self-excluded by session_id
  // (defense-in-depth). M18: post-hoc; consumes the shared eventsStore only,
  // no own transport.
  //
  // CRAFT (calm-ambient): a quiet ledger, hairline rows, tabular timestamps,
  // and severity carried by type-weight on the exact-name token.

  /**
   * Frozen exact event_type -> color-class map. The KEY is the exact event
   * type string the server emits; the value is the CSS class suffix. Severity
   * intent is encoded per-type (block/intervene/guide families + named hues),
   * mirroring the live `.evt-*` rules so the form swap is 1:1.
   *
   * Union of:
   *   - live `_KNOWN_EVT_CLASSES` (governance_*, hitl_sync_queued,
   *     hitl_async_flagged, agent_identified, desktop_pause, governance_call,
   *     learn_mode_bias_applied, nfr_model_routing_alert)
   *   - spec "Named SSE events" (audit.*, hitl_timeout, ...)
   */
  export const EVENT_TYPE_CLASS = Object.freeze({
    // -- governance signals --
    governance_negative_regression: 'neg',
    governance_variance_alert: 'variance',
    governance_call: 'call',
    nfr_model_routing_alert: 'routing',
    // -- HITL lifecycle --
    hitl_sync_queued: 'hitl-sync',
    hitl_async_flagged: 'hitl-async',
    hitl_timeout: 'hitl-timeout',
    hitl_mode_promoted: 'hitl-promoted',
    // -- audit-probe / canary / hallucination (FR-PPP) --
    'audit.probe': 'probe',
    'audit.probe_ack': 'probe-ack',
    'audit.probe_failure': 'probe-fail',
    'audit.canary_emit': 'canary',
    'audit.canary_observed': 'canary-ok',
    'audit.hallucination_detected': 'halluc',
    // -- identity / learn-mode --
    agent_identified: 'agent',
    desktop_pause: 'pause',
    learn_mode_bias_applied: 'learn',
  });

  /** The recognized-type set (derived once). Used to pick the class or fallback. */
  export const KNOWN_EVENT_TYPES = Object.freeze(new Set(Object.keys(EVENT_TYPE_CLASS)));

  /**
   * Resolve the color class suffix for an event type. Unknown => 'default'.
   * The exact type string is ALWAYS shown as text by the caller, so this only
   * decides the SECOND (color) channel (M4: color is never the sole signal).
   * @param {string} type
   * @returns {string}
   */
  export function classForType(type) {
    const t = String(type || '');
    return EVENT_TYPE_CLASS[t] || 'default';
  }
</script>

<script>
  import { eventsStore } from '../sse.js';
  import { selectedSessionId, getOwnSessionId } from '../stores/session.js';
  import { makeSelfExcludeFilter } from '../selfExclude.js';

  /** Collapsed by default (matches the live evlog default: aria-expanded=false). */
  export let open = false;

  /** Ring-buffer cap on rendered event rows (mirrors live EVLOG.MAX). */
  const RENDER_CAP = 500;

  let paused = false;
  /** Frozen snapshot held while paused so ingestion is visually frozen. */
  let frozenRows = null;
  /** Operator-cleared cutoff: hide events at/under this length on clear. */
  let clearedSet = new Set();

  // M15 self-exclude predicate.
  $: selfFilter = makeSelfExcludeFilter(getOwnSessionId() || '');
  $: scopeId = $selectedSessionId;

  // Live, self-excluded, session-scoped, cleared-aware, capped event rows.
  $: liveRows = $eventsStore
    .filter(selfFilter)
    .filter((r) => scopeId == null || r.session_id === scopeId)
    .filter((r) => !clearedSet.has(rowKey(r)))
    .slice(0, RENDER_CAP);

  // When paused, render the frozen snapshot; otherwise the live rows.
  $: rows = paused && frozenRows ? frozenRows : liveRows;

  function rowKey(r) {
    return `${r.event_type || r.type || ''}:${r.timestamp ?? ''}:${(r.content || '').slice(0, 24)}`;
  }

  function togglePanel() { open = !open; }

  function togglePause() {
    paused = !paused;
    // Freeze the currently-visible set on pause; release on resume.
    frozenRows = paused ? liveRows.slice() : null;
  }

  function clearAll() {
    // Mark every currently-known event key as cleared so they drop out; new
    // events still arrive. (We do not mutate the shared store -- other panes
    // may still want it; clearing is a per-panel view operation.)
    const next = new Set(clearedSet);
    for (const r of $eventsStore) next.add(rowKey(r));
    clearedSet = next;
    if (paused) frozenRows = [];
  }

  function fmtTs(t) {
    if (t == null) return '--:--:--.---';
    const d = typeof t === 'number' ? new Date(t * 1000) : new Date(t);
    if (Number.isNaN(d.getTime())) return '--:--:--.---';
    const pad = (n) => String(n).padStart(2, '0');
    const ms = String(d.getMilliseconds()).padStart(3, '0');
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${ms}`;
  }
  function clip(s, n = 120) {
    const c = String(s || '');
    return c.length > n ? `${c.slice(0, n)}...` : c;
  }
</script>

<section class="ev" class:ev--open={open} aria-label="Event log">
  <header class="ev__head">
    <button
      type="button"
      class="ev__toggle"
      aria-expanded={open}
      on:click={togglePanel}
      title={open ? 'Hide the event log' : 'Show the event log'}
    >
      <span class="ev__chevron" aria-hidden="true">{open ? 'v' : '>'}</span>
      <span class="ev__toggle-text">Event log</span>
      <span class="ev__count" aria-hidden="true">{rows.length}</span>
    </button>

    {#if open}
      <div class="ev__controls" role="group" aria-label="Event log controls">
        <button
          type="button"
          class="ev__btn"
          class:ev__btn--on={paused}
          aria-pressed={paused}
          on:click={togglePause}
          title={paused ? 'Resume event ingestion' : 'Pause event ingestion'}
        >{paused ? 'Paused' : 'Pause'}</button>
        <button
          type="button"
          class="ev__btn"
          on:click={clearAll}
          title="Clear all shown events"
        >Clear</button>
      </div>
    {/if}
  </header>

  {#if open}
    <div class="ev__body" role="log" aria-live="polite" aria-label="Bus events, newest first">
      {#if rows.length === 0}
        <p class="ev__empty" role="status">No events yet.</p>
      {:else}
        {#each rows as ev (rowKey(ev))}
          {@const type = String(ev.event_type || ev.type || 'unknown')}
          {@const cls = classForType(type)}
          <div class="ev__row" data-event-type={type}>
            <span class="ev__ts">{fmtTs(ev.timestamp)}</span>
            <!-- M4 spirit: the EXACT type string is the load-bearing label;
                 the color class is a second channel only. -->
            <span class="ev__type ev__type--{cls}" title={type}>{type}</span>
            {#if ev.content}
              <span class="ev__content" title={ev.content}>{clip(ev.content)}</span>
            {/if}
          </div>
        {/each}
      {/if}
    </div>
  {/if}
</section>

<style>
  .ev {
    border: 1px solid var(--border, rgba(148, 163, 184, 0.18));
    border-radius: 8px;
    background: var(--bg-card, rgba(15, 23, 42, 0.4));
    overflow: hidden;
  }

  .ev__head {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.35rem 0.5rem;
  }

  .ev__toggle {
    appearance: none;
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    border: none;
    background: transparent;
    color: var(--text-ui, #8a8068);
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.66rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    cursor: pointer;
    padding: 0.15rem 0.25rem;
    border-radius: 4px;
  }
  .ev__toggle:hover { color: var(--text, #e2e8f0); }
  .ev__chevron { font-size: 0.7rem; }
  .ev__count {
    font-variant-numeric: tabular-nums;
    font-size: 0.6rem;
    color: var(--text-dim, #94a3b8);
    background: var(--border, rgba(148, 163, 184, 0.15));
    border-radius: 999px;
    padding: 0.02rem 0.4rem;
  }

  .ev__controls { display: inline-flex; gap: 0.3rem; margin-left: auto; }
  .ev__btn {
    appearance: none;
    border: 1px solid var(--border, rgba(148, 163, 184, 0.3));
    background: transparent;
    color: var(--text-dim, #94a3b8);
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.62rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    padding: 0.18rem 0.5rem;
    border-radius: 4px;
    cursor: pointer;
    transition: color 0.16s ease, border-color 0.16s ease;
  }
  .ev__btn:hover { color: var(--text, #e2e8f0); border-color: var(--text-dim, #94a3b8); }
  .ev__btn--on {
    color: var(--c-guide, #eab308);
    border-color: var(--c-guide, #eab308);
  }

  /* M17 amber focus ring on every interactive element. */
  .ev__toggle:focus-visible,
  .ev__btn:focus-visible {
    outline: 2px solid #d97706;
    outline-offset: 2px;
  }

  .ev__body {
    max-height: 16rem;
    overflow-y: auto;
    overscroll-behavior: contain;
    border-top: 1px solid var(--border, rgba(148, 163, 184, 0.15));
    padding: 0.25rem 0.5rem 0.4rem;
  }
  .ev__body:focus-visible { outline: 2px solid #d97706; outline-offset: -2px; }

  .ev__row {
    display: grid;
    grid-template-columns: auto auto 1fr;
    align-items: baseline;
    gap: 0.55rem;
    padding: 0.18rem 0;
    border-bottom: 1px solid var(--border, rgba(148, 163, 184, 0.08));
    font-size: 0.7rem;
  }
  .ev__row:last-child { border-bottom: none; }

  .ev__ts {
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-variant-numeric: tabular-nums;
    font-size: 0.64rem;
    color: var(--text-dim, #94a3b8);
    white-space: nowrap;
  }

  /* The exact event_type string. Always TEXT; color is the second channel. */
  .ev__type {
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.64rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 22ch;
  }

  /* Exact-type color map. Mirrors the live `.evt-*` palette; theme-token
     driven so the three themes retint together. Higher-severity families use
     heavier weight (severity-as-type). */
  .ev__type--neg          { color: var(--c-block, #ef4444); font-weight: 700; }
  .ev__type--variance     { color: var(--c-intervene, #f97316); }
  .ev__type--routing      { color: var(--c-guide, #eab308); }
  .ev__type--call         { color: var(--text-ui, #8a8068); }
  .ev__type--hitl-sync    { color: #60a5fa; }
  .ev__type--hitl-async   { color: #14b8a6; }
  .ev__type--hitl-timeout { color: #a78bfa; }
  .ev__type--hitl-promoted{ color: #38bdf8; }
  .ev__type--probe        { color: #818cf8; }
  .ev__type--probe-ack    { color: var(--c-allow, #22c55e); }
  .ev__type--probe-fail   { color: var(--c-block, #ef4444); font-weight: 700; }
  .ev__type--canary       { color: #c084fc; }
  .ev__type--canary-ok    { color: var(--c-allow, #22c55e); }
  .ev__type--halluc       { color: var(--c-block, #ef4444); font-weight: 700; }
  .ev__type--agent        { color: var(--text-ui, #8a8068); }
  .ev__type--pause        { color: var(--text-bright, #e8e0cc); font-weight: 700; }
  .ev__type--learn        { color: var(--text-ui, #8a8068); }
  .ev__type--default      { color: var(--text-dim, #94a3b8); }

  .ev__content {
    color: var(--text-dim, #94a3b8);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }

  .ev__empty {
    margin: 0.4rem 0;
    color: var(--text-dim, #94a3b8);
    font-size: 0.74rem;
    font-style: italic;
    text-align: center;
    opacity: 0.85;
  }

  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .ev__btn { transition: none; }
  }
</style>
