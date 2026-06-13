<!--
  SpatialSessionSidebar.svelte -- BETA feature "spatial-session-sidebar" (#45).

  WHAT IT IS
    A collapsible RIGHT-edge rail: the spatial counterpart to the existing left
    command-deck rail. Each governed NON-SM session is a CHIP-NODE positioned by
    recency, ringed by its governance mode, carrying a last-10 latency sparkline,
    and linked to any session that shares a learned cross-session pattern (a
    labelled "xN" edge). On hover/focus a tooltip-card surfaces open-HITL count,
    the active agent slug, and a one-click Focus button that switches the main
    frame scope to that session (the SAME guarded selectSession() the left rail
    uses -- structurally refuses SM-self). The field reprojects to a 1D timeline
    strip on narrow viewports / by toggle.

    It is NOT a 4th frame and NOT a frame replacement -- Frames A/B/C and the left
    rail are untouched (ADR-18 M1, read-only augmentation). Mounted at the App
    composition root as a position:fixed right-edge panel, sibling to AwayMode /
    DecisionOracle. It matches the operator-approved mockup
    (reports/proposals/mockups/spatial-session-sidebar.html).

  BETA GATE (load-bearing)
    The ENTIRE component is wrapped in {#if $betaFlags['spatial-session-sidebar']}.
    When the flag is OFF it renders NOTHING and registers NO fetch / poller / SSE
    / timer / wheel listener -- zero runtime cost. The flag defaults OFF
    (lib/beta/registry.js); the operator flips it in Settings > BETA features. The
    poll loop starts ONLY while enabled and is torn down the instant the flag
    flips OFF (the reactive block + onDestroy both clear the interval).

  DATA
    Reads GET /api/sessions/spatial-overview (nodes + shared-pattern edges) on a
    calm cadence. The server aggregates per-session mode / recency / latency /
    hitl over gov.db, polarity-filtered (project_slug NOT IN {streamManager} AND
    session_id != self). When the endpoint is absent or returns an empty set
    (fresh DB, no governed sessions) the sidebar falls back to realistic MOCK data
    (SpatialSessionSidebar-data.js) so it is always inspectable; the mock state is
    labelled in the source line and the footer.

  ADR-18 MUST floor honoured here:
    - M1: Frames A/B/C + the left rail never move -- this panel is a fixed
      right-edge overlay that coexists, never displaces.
    - M2: the escalation pulse is an OUTLINE animation (no color-only state) and
      respects prefers-reduced-motion + the FR-UI-9 data-motion override. This
      panel auto-foregrounds NOTHING; the lone permitted M2 foreground stays with
      the real escalation stream owned elsewhere.
    - M4 (paired label+color): every node renders its LITERAL mode WORD
      (OBSERVE/SUGGEST/GUIDE/INTERVENE/BLOCK), the open-HITL chip is "ACTION N"
      (word + count), and the alert chip is the literal M2 word -- color is never
      the sole signal. Edge thickness is paired with an "xN" count label; the
      count is the signal, the line is secondary.
    - M15 / G2 (polarity): the server excludes SM-self by project_slug; the panel
      footer surfaces excluded_self. Focus routes through selectSession(), which
      can never resolve to the SM own session.
    - M16 (domain-agnostic): NO monitored-project vocabulary; every node identity
      is rendered FROM DATA (project_slug).
    - M17 (a11y): each node is a real <button> in recency (Tab) order; Arrow keys
      move selection, Enter/Space Focus the scope, Escape collapses; the 2px amber
      focus ring applies throughout.
    - M18: pure post-hoc GET on a calm cadence; never on the verdict hot path.

  ASCII-only (cp1252-safe): dash rendered as "--". No smart quotes / em-dash.
-->
<script>
  import { onDestroy, tick } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { selectSession } from '../../stores/session.js';
  import { getSpatialOverview } from './SpatialSessionSidebar-api.js';
  import {
    mockOverview,
    normalizeOverview,
    modeLabel,
    modeClass,
    escLabel,
    sparklinePath,
    nodeCenter,
    ago,
    byRecency,
    nodeAria,
  } from './SpatialSessionSidebar-data.js';

  const FLAG_KEY = 'spatial-session-sidebar';
  const LS_COLLAPSED = 'sm.next.spatial-sidebar.collapsed';

  /** Poll cadence: calm glance data, not a hot-path signal. */
  const REFRESH_MS = 5000;
  /** The 2D field geometry (matches the mockup field box). */
  const FIELD_W = 320;
  const FIELD_H = 392;

  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // ---- data state -----------------------------------------------------------
  let loaded = false;
  let usedMockData = false;
  let now = Math.floor(Date.now() / 1000);
  /** @type {import('./SpatialSessionSidebar-data.js').SpatialNode[]} */
  let nodes = [];
  /** @type {import('./SpatialSessionSidebar-data.js').SpatialEdge[]} */
  let edges = [];
  let excludedSelf = 0;

  // ---- view state -----------------------------------------------------------
  let collapsed = readCollapsed();
  let is1d = false;
  let zoom = 100;
  let selectedIdx = 0;
  /** the session_id the tooltip-card is currently anchored to, or null. */
  let tipId = null;
  /** {x,y} screen-space anchor for the tooltip-card within the field. */
  let tipPos = { x: 8, y: 8 };
  let liveStatus = '';

  /** recency-ordered nodes (DOM == Tab order). */
  $: ordered = byRecency(nodes);
  /** session_id -> recency rank, for edge endpoint placement. */
  $: rankById = ordered.reduce((m, n, i) => { m[n.session_id] = i; return m; }, /** @type {Record<string,number>} */ ({}));
  $: tipNode = tipId ? ordered.find((n) => n.session_id === tipId) || null : null;

  function readCollapsed() {
    if (typeof localStorage === 'undefined') return false;
    try { return localStorage.getItem(LS_COLLAPSED) === '1'; } catch { return false; }
  }
  function persistCollapsed(v) {
    if (typeof localStorage === 'undefined') return;
    try { localStorage.setItem(LS_COLLAPSED, v ? '1' : '0'); } catch { /* quota */ }
  }

  // ---- center placement (2D) ------------------------------------------------
  function center(n) {
    const c = nodeCenter(rankById[n.session_id] ?? 0, ordered.length, FIELD_W, FIELD_H);
    return c;
  }

  // ---- load (best-effort; degrade to mock) ----------------------------------
  async function load() {
    let payload = null;
    try {
      payload = await getSpatialOverview();
    } catch {
      payload = null;
    }
    const norm = normalizeOverview(payload);
    if (norm) {
      nodes = norm.nodes;
      edges = norm.edges;
      now = norm.now;
      excludedSelf = norm.excluded_self;
      usedMockData = false;
    } else {
      const m = mockOverview();
      nodes = m.nodes;
      edges = m.edges;
      now = m.now;
      excludedSelf = m.excluded_self;
      usedMockData = true;
    }
    if (selectedIdx >= ordered.length) selectedIdx = 0;
    loaded = true;
  }

  // ---- poll lifecycle, gated strictly on `enabled` --------------------------
  /** @type {ReturnType<typeof setInterval>|null} */
  let _timer = null;
  function startPolling() {
    if (_timer || typeof setInterval === 'undefined') return;
    load();
    _timer = setInterval(load, REFRESH_MS);
  }
  function stopPolling() {
    if (_timer) { clearInterval(_timer); _timer = null; }
  }
  $: if (enabled) startPolling();
  else {
    stopPolling();
    // OFF holds zero state; a re-enable re-fetches fresh.
    loaded = false;
    nodes = [];
    edges = [];
    tipId = null;
    liveStatus = '';
  }
  onDestroy(stopPolling);

  // ---- interactions ---------------------------------------------------------
  function setCollapsed(v) {
    collapsed = v;
    persistCollapsed(v);
    if (v) { tipId = null; liveStatus = 'Spatial map collapsed to the rail spine.'; }
    else { liveStatus = 'Spatial map expanded.'; }
  }

  /**
   * Focus: switch the main frame scope to this session via the SAME guarded
   * store setter the left rail uses (refuses SM-self structurally). The panes
   * follow; the layout does not move (M1).
   */
  function focusScope(n) {
    selectSession(n.session_id);
    tipId = n.session_id;
    liveStatus = `Focus -- scope switched to ${n.project_slug}. Frames A/B/C follow; the layout does not move.`;
  }

  function setProjection(one) {
    is1d = one;
    tipId = null;
    liveStatus = one
      ? '1D timeline strip -- same nodes ordered by recency, edges dropped, badges unchanged.'
      : '2D constellation field -- nodes positioned by recency, shared-pattern edges shown.';
  }

  async function selectIdx(i) {
    if (i < 0 || i >= ordered.length) return;
    selectedIdx = i;
    await tick();
    const els = nodeButtons();
    if (els[i]) els[i].focus();
  }

  function nodeButtons() {
    if (!_field) return [];
    return Array.prototype.slice.call(_field.querySelectorAll('.ssb-node'));
  }
  /** @type {HTMLElement|null} */
  let _field = null;

  function showTip(n, anchorEl) {
    tipId = n.session_id;
    if (is1d || !anchorEl || !_field) {
      tipPos = { x: 8, y: 8 };
      return;
    }
    const fieldRect = _field.getBoundingClientRect();
    const aRect = anchorEl.getBoundingClientRect();
    let left = aRect.left - fieldRect.left + aRect.width + 8;
    let top = aRect.top - fieldRect.top;
    if (left + 224 > fieldRect.width) left = aRect.left - fieldRect.left - 224 - 8;
    if (left < 4) left = 4;
    if (top + 184 > fieldRect.height) top = Math.max(4, fieldRect.height - 188);
    tipPos = { x: left, y: top };
  }

  function onNodeClick(n, i, ev) {
    selectedIdx = i;
    showTip(n, ev && ev.currentTarget);
    focusScope(n);
  }
  function onNodeFocus(n, i, ev) {
    selectedIdx = i;
    showTip(n, ev && ev.currentTarget);
  }

  // field-level keyboard: Arrow move, Escape collapse (Enter/Space handled by
  // the focused node button itself).
  function onFieldKey(e) {
    const n = ordered.length;
    if (n === 0) return;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      selectIdx((selectedIdx + 1) % n);
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      selectIdx((selectedIdx - 1 + n) % n);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      setCollapsed(true);
    }
  }

  function onWheel(e) {
    if (is1d) return;
    e.preventDefault();
    zoom = Math.max(60, Math.min(180, zoom + (e.deltaY < 0 ? 10 : -10)));
  }

  $: zoomFactor = zoom / 100;
  $: sourceLine = usedMockData
    ? 'SAMPLE DATA -- no governed sessions in gov.db yet; representative shape.'
    : 'LIVE -- gov.db, polarity-filtered (SM-self excluded).';
</script>

{#if enabled}
  {#if collapsed}
    <!-- collapsed: a thin right-edge spine (paired chevron + "MAP" word). -->
    <button
      type="button"
      class="ssb-spine"
      aria-expanded="false"
      aria-label="Expand spatial session overview"
      on:click={() => setCollapsed(false)}
    >
      <span class="ssb-spine__chev" aria-hidden="true">&lsaquo;</span>
      <span class="ssb-spine__label">MAP</span>
    </button>
  {:else}
    <nav class="ssb" aria-label="Spatial session overview">
      <header class="ssb__head">
        <h2 class="ssb__title">Spatial map</h2>
        <span class="ssb__beta">BETA</span>
        <button
          type="button"
          class="ssb__collapse"
          aria-expanded="true"
          aria-label="Collapse spatial session overview"
          on:click={() => setCollapsed(true)}
        >
          <span aria-hidden="true">&rsaquo;</span> MAP
        </button>
      </header>

      <!-- data-source line: ALWAYS a literal text label (mock vs live). -->
      <p class="ssb__source" data-mock={usedMockData}>{sourceLine}</p>

      <div class="ssb__controls">
        <div class="ssb-proj" role="group" aria-label="Field projection">
          <button type="button" aria-pressed={!is1d} on:click={() => setProjection(false)}>2D field</button>
          <button type="button" aria-pressed={is1d} on:click={() => setProjection(true)}>1D strip</button>
        </div>
        {#if !is1d}
          <span class="ssb-zoom" aria-label={`zoom ${zoom} percent; scroll to zoom, drag to pan`}>zoom {zoom}%</span>
        {/if}
      </div>

      {#if !loaded}
        <p class="ssb__loading">Loading spatial map...</p>
      {:else if ordered.length === 0}
        <p class="ssb__empty">No governed sessions to map. Nodes appear as non-SM sessions are observed.</p>
      {:else}
        <!-- the field: 2D constellation or 1D strip. role=application so Arrow
             keys are owned here; the descriptive label spells out the controls. -->
        <div
          class="ssb-field"
          class:is-1d={is1d}
          bind:this={_field}
          role="application"
          aria-label="Session constellation -- nodes are buttons in recency order; Arrow keys move selection, Enter focuses scope, Escape collapses"
          on:keydown={onFieldKey}
          on:wheel={onWheel}
        >
          {#if !is1d}
            <!-- edges: shared-pattern flows. The line is secondary; the xN count
                 chip is the load-bearing signal (M4). aria-hidden (the count is
                 also surfaced in each node's tooltip). -->
            <svg class="ssb-field__svg" viewBox={`0 0 ${FIELD_W} ${FIELD_H}`} preserveAspectRatio="none" aria-hidden="true">
              {#each edges as e (e.from_session_id + '>' + e.to_session_id)}
                {@const a = nodeCenter(rankById[e.from_session_id] ?? 0, ordered.length, FIELD_W, FIELD_H)}
                {@const b = nodeCenter(rankById[e.to_session_id] ?? 0, ordered.length, FIELD_W, FIELD_H)}
                {@const mx = (a.x + b.x) / 2}
                {@const my = (a.y + b.y) / 2}
                {@const label = 'x' + e.pattern_count}
                <path class="ssb-edge" d={`M${a.x},${a.y} L${b.x},${b.y}`} stroke-width={0.8 + e.pattern_count * 0.9} />
                <rect class="ssb-edge-chip" x={mx - (10 + label.length * 7) / 2} y={my - 9} width={10 + label.length * 7} height="16" rx="4" />
                <text class="ssb-edge-txt" x={mx} y={my + 3} text-anchor="middle">{label}</text>
              {/each}
            </svg>
          {/if}

          {#each ordered as n, i (n.session_id)}
            {@const c = center(n)}
            <button
              type="button"
              class="ssb-node {modeClass(n.governance_mode)}"
              class:is-selected={i === selectedIdx}
              class:node--alert={!!n.alert}
              data-session-id={n.session_id}
              aria-label={nodeAria(n, now)}
              style={is1d ? '' : `left:${c.x}px; top:${c.y}px; transform: translate(-50%, -50%) scale(${zoomFactor});`}
              on:click={(ev) => onNodeClick(n, i, ev)}
              on:focus={(ev) => onNodeFocus(n, i, ev)}
              on:mouseenter={(ev) => showTip(n, ev.currentTarget)}
            >
              <span class="ssb-node__ring" aria-hidden="true"></span>
              <span class="ssb-node__top">
                <span class="ssb-node__slug" title={n.project_slug}>{n.project_slug}</span>
                <span class="ssb-node__ago tabular">{ago(n.last_activity_ts, now)}</span>
              </span>
              <span class="ssb-node__badges">
                <span class="ssb-mode"><span class="ssb-mode__dot" aria-hidden="true"></span>{modeLabel(n.governance_mode)}</span>
                {#if n.open_hitl > 0}
                  <span class="ssb-action">ACTION {n.open_hitl}</span>
                {/if}
                {#if n.alert}
                  <span class="ssb-alert">{escLabel(n.alert)}</span>
                {/if}
              </span>
              <svg class="ssb-node__spark" viewBox="0 0 120 22" preserveAspectRatio="none" aria-hidden="true">
                <line class="ssb-spark-base" x1="0" y1="21" x2="120" y2="21"></line>
                <path class="ssb-spark-line" d={sparklinePath(n.latency_sparkline, 120, 22)}></path>
              </svg>
            </button>
          {/each}

          {#if tipNode}
            <!-- the hover/focus tooltip-card. role=dialog with a label; the Focus
                 button routes through the guarded selectSession(). -->
            <div
              class="ssb-tip"
              role="dialog"
              aria-label={`${tipNode.project_slug} session detail`}
              style={is1d ? '' : `left:${tipPos.x}px; top:${tipPos.y}px;`}
            >
              <div class="ssb-tip__slug">{tipNode.project_slug}</div>
              <div class="ssb-tip__mode">
                <span class="ssb-mode {modeClass(tipNode.governance_mode)}"><span class="ssb-mode__dot" aria-hidden="true"></span>{modeLabel(tipNode.governance_mode)}</span>
              </div>
              <dl class="ssb-tip__dl">
                <dt>open hitl</dt>
                <dd class="tabular">{tipNode.open_hitl > 0 ? `ACTION ${tipNode.open_hitl}` : '0 (none)'}</dd>
                <dt>agent</dt>
                <dd>{tipNode.agent_slug || 'no active agent'}</dd>
                <dt>last seen</dt>
                <dd class="tabular">{ago(tipNode.last_activity_ts, now)}</dd>
                <dt>latency</dt>
                <dd class="tabular">{tipNode.latency_sparkline.length ? `${tipNode.latency_sparkline[tipNode.latency_sparkline.length - 1]} ms (last of ${tipNode.latency_sparkline.length})` : 'n/a'}</dd>
                {#if tipNode.alert}
                  <dt>alert</dt>
                  <dd>{escLabel(tipNode.alert)}</dd>
                {/if}
              </dl>
              <button type="button" class="ssb-tip__focus" on:click={() => focusScope(tipNode)}>Focus this session</button>
            </div>
          {/if}
        </div>

        <!-- M15 polarity readout: the self-exclude, on-screen + auditable. -->
        <footer class="ssb__foot">
          <span class="ssb__self-dot" aria-hidden="true"></span>
          <span>{excludedSelf} self row{excludedSelf === 1 ? '' : 's'} excluded (polarity filter)</span>
        </footer>
      {/if}
    </nav>
  {/if}

  <!-- screen-reader live region for projection / focus / collapse announcements -->
  <p class="ssb-sr" aria-live="polite">{liveStatus}</p>
{/if}

<style>
  /* The panel is a fixed right-edge rail, sibling to AwayMode / DecisionOracle.
     It coexists with Frames A/B/C + the left rail (M1) -- never displaces them. */
  .ssb {
    position: fixed;
    top: 4rem;
    right: 0.75rem;
    z-index: 40;
    width: min(348px, calc(100vw - 1.5rem));
    max-height: calc(100vh - 6rem);
    display: flex;
    flex-direction: column;
    background: var(--calm-surface, var(--bg-card, #0c1118));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-card, 6px);
    overflow: hidden;
    font-family: var(--ff-system);
    box-shadow: 0 10px 36px rgba(0, 0, 0, 0.5);
  }

  /* collapsed: a thin right-edge spine with a paired chevron + vertical "MAP". */
  .ssb-spine {
    position: fixed;
    top: 4rem;
    right: 0.75rem;
    z-index: 40;
    width: 30px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    padding: 10px 0;
    appearance: none;
    background: var(--calm-surface, var(--bg-card, #0c1118));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-card, 6px);
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    cursor: pointer;
  }
  .ssb-spine:hover { color: var(--calm-ink-loud, var(--text-bright, #e8e0cc)); border-color: var(--border-hi, rgba(245, 158, 11, 0.25)); }
  .ssb-spine:focus-visible { outline: 2px solid var(--sm-focus, var(--badge-ar-border, #d97706)); outline-offset: 2px; }
  .ssb-spine__chev { font-size: 14px; }
  .ssb-spine__label {
    writing-mode: vertical-rl;
    text-orientation: mixed;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    letter-spacing: 0.22em;
    text-transform: uppercase;
  }

  /* ---- header ------------------------------------------------------------- */
  .ssb__head {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    padding: 9px 12px;
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    background: var(--calm-surface-deep, var(--bg, #080a0c));
  }
  .ssb__title {
    margin: 0;
    font-size: 13px;
    font-weight: 560;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    white-space: nowrap;
  }
  .ssb__beta {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: #92400e;
    background: var(--badge-ar-bg, #fef3c7);
    border: 1px solid var(--badge-ar-border, #d97706);
    border-radius: 4px;
    padding: 0 5px;
  }
  .ssb__collapse {
    margin-left: auto;
    appearance: none;
    background: transparent;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.1em;
    padding: 3px 8px;
    border-radius: 999px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 5px;
  }
  .ssb__collapse:hover { color: var(--calm-ink-loud, var(--text-bright, #e8e0cc)); border-color: var(--border-hi, rgba(245, 158, 11, 0.25)); }
  .ssb__collapse:focus-visible { outline: 2px solid var(--sm-focus, var(--badge-ar-border, #d97706)); outline-offset: 2px; }

  .ssb__source {
    margin: 0;
    padding: 5px 12px;
    font-size: 10.5px;
    font-family: var(--font-d, var(--ff-mono));
    letter-spacing: 0.02em;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
  }
  .ssb__source[data-mock='true'] { color: var(--badge-warn-fg, #ea580c); }
  :global([data-theme='paper']) .ssb__source[data-mock='true'] { color: #9a3412; }

  /* ---- controls: projection toggle + zoom readout ------------------------- */
  .ssb__controls {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    padding: 7px 12px;
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    background: var(--calm-surface-deep, var(--bg, #080a0c));
  }
  .ssb-proj {
    display: inline-flex;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: 999px;
    overflow: hidden;
  }
  .ssb-proj button {
    appearance: none;
    background: transparent;
    border: 0;
    cursor: pointer;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 3px 9px;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .ssb-proj button[aria-pressed='true'] { background: var(--accent-dim, rgba(245, 158, 11, 0.09)); color: var(--calm-accent, var(--accent, #f59e0b)); }
  /* paper accent (#c0392b) on the paper accent-dim control surface (#eadcd2)
     reads 4.05 -- darken the pressed-projection text on paper to clear AA. */
  :global([data-theme='paper']) .ssb-proj button[aria-pressed='true'] { color: #9a2018; }
  .ssb-proj button:focus-visible { outline: 2px solid var(--sm-focus, var(--badge-ar-border, #d97706)); outline-offset: -2px; }
  .ssb-zoom {
    margin-left: auto;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    letter-spacing: 0.06em;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }

  .ssb__loading,
  .ssb__empty {
    margin: 0;
    padding: 14px 12px;
    font-size: 11px;
    font-style: italic;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }

  /* ---- the field ---------------------------------------------------------- */
  .ssb-field {
    position: relative;
    height: 392px;
    overflow: hidden;
    background:
      radial-gradient(circle at 70% 22%, var(--accent-dim, rgba(245, 158, 11, 0.05)), transparent 60%),
      var(--calm-surface-deep, var(--bg, #080a0c));
    cursor: grab;
  }
  .ssb-field.is-1d {
    height: auto;
    max-height: calc(100vh - 16rem);
    cursor: default;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 8px;
  }
  .ssb-field__svg { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
  .ssb-edge { stroke: var(--calm-ink-chrome, var(--text-ui, #8a8068)); fill: none; opacity: 0.55; }
  .ssb-edge-chip { fill: var(--calm-surface-alt, var(--bg-row-alt, #0b1018)); stroke: var(--calm-hairline, var(--border, #192030)); }
  .ssb-edge-txt {
    fill: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.02em;
  }

  /* ---- the chip-node ------------------------------------------------------ */
  .ssb-node {
    position: absolute;
    width: 142px;
    background: var(--calm-surface, var(--bg-card, #0c1118));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-left: 2px solid transparent;
    border-radius: var(--radius-card, 6px);
    padding: 7px 9px 5px 11px;
    cursor: pointer;
    text-align: left;
    color: inherit;
    font: inherit;
    transition: border-color 160ms ease, box-shadow 160ms ease, background 160ms ease;
  }
  .ssb-field.is-1d .ssb-node { position: relative; left: auto !important; top: auto !important; transform: none !important; width: 100%; }
  .ssb-node:hover { background: var(--calm-surface-hover, var(--bg-row-hover, #131c2a)); box-shadow: 0 0 0 1px var(--border-hi, rgba(245, 158, 11, 0.25)); }
  .ssb-node:focus-visible { outline: 2px solid var(--sm-focus, var(--badge-ar-border, #d97706)); outline-offset: 2px; }
  .ssb-node.is-selected { border-color: var(--calm-accent, var(--accent, #f59e0b)); box-shadow: 0 0 0 1px var(--accent-glow, rgba(245, 158, 11, 0.35)); }

  /* the MODE RING: a 2px band-color arc down the chip's left edge. Color is the
     SECOND channel only -- the mode WORD is always printed in the badge below. */
  .ssb-node__ring { position: absolute; left: -2px; top: 8px; bottom: 8px; width: 2px; border-radius: 2px; }
  .node--observe .ssb-node__ring { background: var(--c-allow, #22c55e); }
  .node--suggest .ssb-node__ring { background: var(--c-suggest, #84cc16); }
  .node--guide .ssb-node__ring { background: var(--c-guide, #eab308); }
  .node--intervene .ssb-node__ring { background: var(--c-intervene, #f97316); }
  .node--block .ssb-node__ring { background: var(--c-block, #ef4444); }

  .ssb-node__top { display: flex; align-items: baseline; justify-content: space-between; gap: 6px; }
  .ssb-node__slug {
    font-size: 11px;
    font-weight: 460;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-width: 0;
  }
  .ssb-node__ago { font-family: var(--font-d, var(--ff-mono)); font-size: 9px; color: var(--calm-ink-chrome, var(--text-ui, #8a8068)); flex: 0 0 auto; }

  .ssb-node__badges { display: flex; align-items: center; gap: 5px; flex-wrap: wrap; margin: 3px 0 4px; }
  /* paired MODE badge: literal WORD always present; the color is the small dot. */
  .ssb-mode {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    border: 1px solid var(--calm-hairline, var(--border, #192030));
    border-radius: 999px;
    padding: 0 6px;
    line-height: 1.5;
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
  }
  .ssb-mode__dot { width: 6px; height: 6px; border-radius: 50%; flex: 0 0 auto; background: var(--c-allow, #22c55e); }
  .node--observe .ssb-mode__dot { background: var(--c-allow, #22c55e); }
  .node--suggest .ssb-mode__dot { background: var(--c-suggest, #84cc16); }
  .node--guide .ssb-mode__dot { background: var(--c-guide, #eab308); }
  .node--intervene .ssb-mode__dot { background: var(--c-intervene, #f97316); }
  .node--block .ssb-mode__dot { background: var(--c-block, #ef4444); }

  /* open-HITL amber "ACTION N" chip (rail convention) -- word + count. */
  .ssb-action {
    display: inline-flex;
    align-items: center;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 9px;
    font-weight: 800;
    letter-spacing: 0.04em;
    color: #b45309;
    background: var(--badge-ar-bg, #fef3c7);
    border: 1px solid var(--badge-ar-border, #d97706);
    border-radius: 999px;
    padding: 0 5px;
    line-height: 1.5;
  }
  /* alert chip: the literal M2 word + a pulsing OUTLINE (second channel). */
  .ssb-alert {
    display: inline-flex;
    align-items: center;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 9px;
    font-weight: 800;
    letter-spacing: 0.04em;
    color: #b91c1c;
    background: var(--badge-blocked-bg, #fee2e2);
    border: 1px solid var(--badge-blocked-border, #dc2626);
    border-radius: 999px;
    padding: 0 5px;
    line-height: 1.5;
  }
  .node--alert { animation: ssb-pulse 1.6s ease-in-out infinite; }
  @keyframes ssb-pulse {
    0%, 100% { box-shadow: 0 0 0 1px var(--border-hi, rgba(245, 158, 11, 0.25)); }
    50% { box-shadow: 0 0 0 3px var(--accent-glow, rgba(245, 158, 11, 0.35)); }
  }

  /* the 10-point latency SPARKLINE filling the chip's lower third. Shape-only. */
  .ssb-node__spark { display: block; width: 100%; height: 22px; margin-top: 2px; }
  .ssb-spark-line { fill: none; stroke: var(--calm-ink-chrome, var(--text-ui, #8a8068)); stroke-width: 1.4; }
  .node--block .ssb-spark-line,
  .node--intervene .ssb-spark-line { stroke: var(--calm-accent, var(--accent, #f59e0b)); }
  .ssb-spark-base { stroke: var(--calm-hairline, var(--border, #192030)); stroke-width: 1; }

  /* ---- tooltip-card ------------------------------------------------------- */
  .ssb-tip {
    position: absolute;
    z-index: 20;
    width: 224px;
    background: var(--calm-surface, var(--bg-card, #0c1118));
    border: var(--hairline, 1px) solid var(--border-hi, rgba(245, 158, 11, 0.25));
    border-radius: var(--radius-card, 6px);
    padding: 10px 12px;
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.5);
  }
  .ssb-field.is-1d .ssb-tip { position: static; width: 100%; margin-top: 4px; }
  .ssb-tip__slug { font-size: 12px; font-weight: 600; color: var(--calm-ink-loud, var(--text-bright, #e8e0cc)); letter-spacing: 0.04em; }
  .ssb-tip__mode { margin: 4px 0 8px; }
  .ssb-tip__dl { display: grid; grid-template-columns: auto 1fr; gap: 2px 10px; margin: 0 0 10px; }
  .ssb-tip__dl dt { font-family: var(--font-d, var(--ff-mono)); font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--calm-ink-chrome, var(--text-ui, #8a8068)); margin: 0; }
  .ssb-tip__dl dd { margin: 0; font-family: var(--font-d, var(--ff-mono)); font-size: 11px; color: var(--calm-ink, var(--text, #b8b098)); }
  .ssb-tip__focus {
    appearance: none;
    width: 100%;
    cursor: pointer;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--calm-accent, var(--accent, #f59e0b));
    background: var(--accent-dim, rgba(245, 158, 11, 0.09));
    border: 1px solid var(--calm-accent, var(--accent, #f59e0b));
    border-radius: 4px;
    padding: 5px 0;
  }
  .ssb-tip__focus:hover { background: var(--calm-surface-hover, var(--bg-row-hover, #131c2a)); }
  .ssb-tip__focus:focus-visible { outline: 2px solid var(--sm-focus, var(--badge-ar-border, #d97706)); outline-offset: 2px; }

  /* ---- footer: polarity self-exclude readout ------------------------------ */
  .ssb__foot {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    padding: 5px 12px;
    border-top: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    background: var(--calm-surface-deep, var(--bg, #080a0c));
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .ssb__self-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--calm-ink-quiet, var(--text-dim, #948870)); opacity: 0.7; }

  .tabular { font-variant-numeric: tabular-nums; font-family: var(--font-d, var(--ff-mono)); }

  .ssb-sr { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }

  /* M17 reduced motion: suppress the escalation pulse + node transitions. */
  :global(html[data-motion='reduce']) .node--alert,
  :global(html[data-motion='reduce']) .ssb-node { animation: none; transition: none; }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .node--alert { animation: none; }
    :global(html:not([data-motion='allow'])) .ssb-node { transition: none; }
  }
</style>
