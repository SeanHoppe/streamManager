<!--
  ConfidenceHeatmapPane.svelte -- BETA feature "confidence-heatmap-pane" (#9).

  A still, calm role x time-bucket grid mounted INSIDE Frame B (Sub-Agents),
  BELOW the AgentRoster. Y = agent roles (sorted by current count-weighted mean
  confidence DESC, highest at top); X = 12 contiguous 5-min buckets over a
  rolling 60 min, oldest-left newest-right. Glance a ROW left-to-right => one
  role's confidence trajectory; scan a COLUMN top-to-bottom => which roles were
  shaky in the same window. Hover/focus a cell => a tooltip; click/Enter a cell
  => an inline mini-tray of the decisions behind it (filtered from the EXISTING
  feed, no tray endpoint). Observation-only -- it NEVER gates or blocks an agent
  (M13).

  This is the Svelte realisation of the operator-APPROVED mockup
  (reports/proposals/mockups/confidence-heatmap-pane.html). It reuses theme.css
  tokens verbatim (the per-theme action palette --c-allow / --c-suggest /
  --c-intervene / --c-block reused as the confidence-band RAMP, plus the
  --calm-* / --accent / --border chrome). No new color tokens.

  ============================ GOVERNANCE FLOOR ============================
  BETA GATE: the component renders NOTHING and registers NO pollers / SSE
    handlers / timers unless $betaFlags['confidence-heatmap-pane'] is true
    (default OFF). It reads the EXISTING decisionsStore (already fed by the one
    shared /events SSE in sse.js); it opens no socket, fetches nothing, and
    starts no interval of its own. The single store autosubscription is created
    by Svelte only while the {#if enabled} block is rendered, and torn down on
    destroy. Live updates ride that store (NO new envelope, NO new SSE channel)
    and the in-place recompute is COALESCED 1/500ms so a decision burst never
    re-renders the grid more than twice a second (M18).

  M2 (calm at rest / escalation-only foreground): a still grid inside Frame B --
    no pulse, no motion, no Frame escalation; it never auto-foregrounds. Only the
    rightmost ("now") column earns a single 1px accent underline.

  M4 (paired label+color, never color alone): every cell carries THREE
    simultaneous encodings -- (1) a band fill color, (2) the literal mean % text
    IN the tile, (3) a one-letter band glyph H/O/W/L. An EMPTY cell is NOT
    colored -- a calm --border hairline gap (absence reads as quiet). The % +
    glyph + aria text survive a fully-desaturated render. A text legend pairs
    each swatch with its written band name + range.

  M13 (observation-only): no agent is gated/blocked; the pane is a read surface.

  M15 / G2 (polarity / self-exclude): the SM-own session is never gridded. The
    pane reads decisionsStore (already self-excluded in sse.js), narrows to the
    operator-scoped session, and applies a second ownSessionId backstop in
    aggregateGrid(); when the scoped session is the SM-own one the pane renders
    an explicit "self -- excluded (G2)" note, never a wall of cells.

  M16 (domain-agnostic): no monitored-project vocabulary. Roles + cell text are
    rendered FROM DATA (the decision rows' role field).

  M17 (a11y): the grid is a real role=grid with a roving 2D tabindex (Arrow keys
    move cell-to-cell, Home/End jump to row ends, Enter/Space open the tray,
    Escape closes it and returns focus); the focused cell shows a 2px solid
    accent ring + 2px offset. Reduced motion honoured.

  M18 (post-hoc): a pure render pass over already-streamed feed data. No
    verdict-path work, no writes, no extra network.

  MOCK FALLBACK: when the live (scoped, self-excluded) feed carries no decisions
    in the rolling 60-min window the grid falls back to a realistic mock fixture
    (mockHeatmapRows) so the feature is visible + testable. The `usedMock` flag
    is exposed for the test harness and shown in the foot note.

  FILE-DISJOINT: this component + its ConfidenceHeatmapPane-data.js helper own
    all the new code. A tray-row click dispatches the EXISTING DOM CustomEvent
    'sm:focus-session' (mirrors EscalationRail) to scope the main feed.

  ASCII-only (cp1252-safe): dash is "--".
-->
<script>
  import { onMount, onDestroy, tick } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { decisionsStore } from '../../sse.js';
  import { selectedSessionId, getOwnSessionId } from '../../stores/session.js';
  import { readOwnProjectSlugs } from '../../api.js';
  import {
    aggregateGrid,
    indexGrid,
    mockHeatmapRows,
    cellAria,
    cellTooltip,
    hhmm,
    hhmmss,
    BAND_GLYPH,
    BAND_NAME,
    BUCKET_MS,
    NCOLS,
    ACTIONS,
  } from './ConfidenceHeatmapPane-data.js';

  /** The stable BETA flag key this component gates on. */
  const FLAG_KEY = 'confidence-heatmap-pane';

  /**
   * bucketMs: window width. 5 min per the proposal; overridable for tests.
   * @type {number}
   */
  export let bucketMs = BUCKET_MS;

  /**
   * allowMock: when the live feed has no in-window decisions, fall back to a
   * realistic mock fixture so the grid is visible/testable. Default true (tests
   * rely on it). Set false to force a true live-only render.
   * @type {boolean}
   */
  export let allowMock = true;

  /**
   * now: epoch ms "right edge" of the X axis, injectable for deterministic
   * tests. null => the live clock read once per recompute (NOT a registered
   * timer -- the existing feed cadence drives re-render).
   * @type {number|null}
   */
  export let now = null;

  // -- gate (single source of truth: the betaFlags store) --------------------
  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // -- self-exclude (G2 / M15) -----------------------------------------------
  let ownSessionId = '';
  /** @type {Set<string>} */
  let ownProjectSlugs = new Set();

  // The operator-scoped session (the pane aggregates the ALREADY self-excluded
  // decisionsStore; when a session is scoped we narrow to its rows).
  $: scopedSessionId = $selectedSessionId || null;

  // Belt-and-suspenders: selectedSessionId can never resolve to ownSessionId
  // (session.js), but guard anyway so we show the calm self note, never empty.
  $: isSelfScope = !!(ownSessionId && scopedSessionId && scopedSessionId === ownSessionId);

  // -- the live feed, scoped + self-excluded ---------------------------------
  $: feedRows = $decisionsStore || [];
  $: scopedRows = scopedSessionId
    ? feedRows.filter((r) => r && r.session_id === scopedSessionId)
    : feedRows;

  // -- aggregate (mock fallback when the live scope has no in-window rows) ----
  let usedMock = false;
  /** @type {ReturnType<typeof aggregateGrid>} */
  let payload = { now_ms: 0, bucket_min: 5, minutes: 60, excluded_self: 0, roles: [], buckets: [], cells: [] };
  /** @type {string[]} */
  let roles = [];
  /** @type {Array<Array<any>>} */
  let grid = [];
  /** @type {Array<{idx:number,t_ms:number,label:string}>} */
  let buckets = [];

  function computeNow() {
    const nowMs = Number.isFinite(now) ? Number(now) : Date.now();
    if (!enabled || isSelfScope) {
      payload = { now_ms: nowMs, bucket_min: Math.round(bucketMs / 60000), minutes: 60, excluded_self: isSelfScope ? 1 : 0, roles: [], buckets: [], cells: [] };
      usedMock = false;
    } else {
      const live = aggregateGrid(scopedRows, { bucketMs, ownSessionId, now: nowMs });
      if (live.cells.length > 0 || !allowMock) {
        payload = live;
        usedMock = false;
      } else {
        const rows = mockHeatmapRows({ now: nowMs, bucketMs });
        payload = aggregateGrid(rows, { bucketMs, ownSessionId, now: nowMs });
        usedMock = true;
      }
    }
    const idx = indexGrid(payload);
    roles = idx.roles;
    grid = idx.grid;
    buckets = payload.buckets;
    reconcileFocus();
  }

  // -- M18 coalesce: a decision BURST must not re-render the grid more than
  //    once per 500ms. The reactive trigger schedules a recompute; if one is
  //    already pending it is a no-op (the trailing edge picks up the freshest
  //    feed). This is the ONLY timer the component ever arms, and only while
  //    enabled + when work is pending -- it is not a poller.
  const COALESCE_MS = 500;
  /** @type {ReturnType<typeof setTimeout>|null} */
  let coalesceTimer = null;
  let dirty = false;

  function scheduleRecompute() {
    if (!enabled) return;
    dirty = true;
    if (coalesceTimer) return;
    coalesceTimer = setTimeout(() => {
      coalesceTimer = null;
      if (dirty) {
        dirty = false;
        computeNow();
      }
    }, COALESCE_MS);
  }

  // Recompute on any input change. The store/scope/flag drive it; scheduleR..
  // coalesces bursts. enabling the flag computes immediately (no 500ms blank).
  let lastEnabled = false;
  $: {
    // touch the reactive deps so Svelte tracks them.
    void enabled;
    void isSelfScope;
    void scopedRows;
    void bucketMs;
    void now;
    void allowMock;
    if (enabled && !lastEnabled) {
      lastEnabled = true;
      computeNow();
    } else if (!enabled && lastEnabled) {
      lastEnabled = false;
      // gated OFF mid-session: drop any pending work + clear state.
      if (coalesceTimer) {
        clearTimeout(coalesceTimer);
        coalesceTimer = null;
      }
      dirty = false;
      roles = [];
      grid = [];
      closeTray();
    } else if (enabled) {
      scheduleRecompute();
    }
  }

  // -- the 2D roving-tabindex grid (M17) -------------------------------------
  let focusR = 0;
  let focusC = NCOLS - 1; // start on the newest col of the top role
  /** @type {{r:number,c:number}|null} */
  let selected = null;
  let gridEl;

  function cellAt(r, c) {
    return grid[r] && grid[r][c] ? grid[r][c] : null;
  }

  function clampFocus(r, c) {
    const rr = Math.max(0, Math.min(roles.length - 1, r));
    const cc = Math.max(0, Math.min(NCOLS - 1, c));
    return { r: rr, c: cc };
  }

  // Keep focus + selection valid across a re-render (roles can reorder / vanish).
  function reconcileFocus() {
    if (!roles.length) {
      selected = null;
      return;
    }
    const p = clampFocus(focusR, focusC);
    focusR = p.r;
    focusC = p.c;
    if (selected && !cellAt(selected.r, selected.c)) selected = null;
  }

  async function focusCell(r, c) {
    const p = clampFocus(r, c);
    focusR = p.r;
    focusC = p.c;
    await tick();
    const el = gridEl && gridEl.querySelector(`.chm__cell[data-r="${p.r}"][data-c="${p.c}"]`);
    if (el && typeof el.focus === 'function') el.focus();
  }

  function isFocus(r, c) {
    return r === focusR && c === focusC;
  }

  // -- the CLICK mini-tray: the decisions behind one cell --------------------
  /** @type {Array<Record<string, any>>} */
  let trayRows = [];
  /** @type {{role:string, label:string, count:number, mean:number, band:string}|null} */
  let trayMeta = null;

  function bucketWindow(c) {
    const b = buckets[c];
    if (!b) return null;
    return { t0: b.t_ms, t1: b.t_ms + bucketMs, label: b.label };
  }

  // The decisions comprising a (role, bucket) cell: filter the EXISTING scoped
  // feed by role + the bucket's wall-clock window (no tray endpoint). When the
  // grid is showing MOCK data the live feed is empty for this window, so we
  // synthesize a representative set from the cell's action_breakdown instead.
  function decisionsForCell(role, c, cell) {
    const win = bucketWindow(c);
    if (!win) return [];
    if (!usedMock) {
      const rows = scopedRows.filter((r) => {
        if (!r) return false;
        const rr =
          (r.agent_profile_slug != null && String(r.agent_profile_slug).trim() !== ''
            ? r.agent_profile_slug
            : r.profile_slug) || 'unknown';
        if (String(rr).trim() !== role) return false;
        const tsMs = Number(r.timestamp) < 1e12 ? Number(r.timestamp) * 1000 : Number(r.timestamp);
        return Number.isFinite(tsMs) && tsMs >= win.t0 && tsMs < win.t1;
      });
      rows.sort((a, b) => Number(a.timestamp) - Number(b.timestamp));
      return rows.map((r, i) => ({
        id: r.id != null ? r.id : r.rid != null ? r.rid : `${role}-${c}-${i}`,
        action: (r.action || 'ALLOW').toString().toUpperCase(),
        confidence: Number(r.confidence) || 0,
        timestamp: Number(r.timestamp) < 1e12 ? Number(r.timestamp) * 1000 : Number(r.timestamp),
        reasoning: (r.reasoning || r.content || 'governance decision recorded').toString(),
        session_id: r.session_id || scopedSessionId || null,
      }));
    }
    // MOCK path: synthesize 5-10 rows from the cell's action_breakdown.
    return synthTrayRows(role, win, cell);
  }

  function synthTrayRows(role, win, cell) {
    const bd = (cell && cell.action_breakdown) || {};
    const order = ['BLOCK', 'INTERVENE', 'GUIDE', 'SUGGEST', 'ALLOW'];
    const total = ACTIONS.reduce((s, a) => s + (bd[a] || 0), 0) || 1;
    const reasons = {
      code_reviewer: ['flagged an unverified claim', 'could not reproduce the cited test', 'guided toward re-running the failing case', 'review approved a change with no test coverage', 'sign-off on an unscoped destructive edit'],
      frontend_architect: ['approved a token-only style change', 'suggested reusing an existing component', 'guided toward an accessible focus-ring', 'approved an additive pane behind a beta gate'],
      developer: ['approved a scoped edit to a single module', 'suggested a smaller diff', 'guided toward an idempotent migration step'],
      tester: ['approved a read-only assertion', 'guided toward a deterministic fixture', 'intervened on a flaky timing assertion'],
      researcher: ['approved a read-only context gather', 'suggested narrowing the search scope'],
    };
    const rs = reasons[role] || ['governance decision recorded'];
    const out = [];
    let k = 0;
    for (const act of order) {
      const n = bd[act] || 0;
      for (let j = 0; j < n; j++) {
        const t = win.t0 + Math.floor(((k + 1) / (total + 1)) * bucketMs);
        const jitter = act === 'BLOCK' ? -0.1 : act === 'INTERVENE' ? -0.05 : act === 'GUIDE' ? -0.01 : 0.02;
        let conf = Number(cell.mean_confidence) + jitter;
        conf = conf < 0.05 ? 0.05 : conf > 0.98 ? 0.98 : conf;
        out.push({
          id: `mock-${role}-${win.t0}-${k}`,
          action: act,
          confidence: conf,
          timestamp: t,
          reasoning: rs[k % rs.length],
          session_id: 'mock-governed-session',
        });
        k++;
      }
    }
    out.sort((a, b) => a.timestamp - b.timestamp);
    return out;
  }

  function openTray(r, c) {
    const cell = cellAt(r, c);
    if (!cell) {
      closeTray();
      return;
    }
    selected = { r, c };
    const role = roles[r];
    const b = buckets[c];
    trayMeta = {
      role,
      label: b ? b.label : '',
      count: cell.count,
      mean: Math.round(Number(cell.mean_confidence) * 100),
      band: BAND_NAME[cell.band] || cell.band,
    };
    trayRows = decisionsForCell(role, c, cell);
  }

  function closeTray() {
    selected = null;
    trayMeta = null;
    trayRows = [];
  }

  function onCellClick(r, c) {
    focusR = r;
    focusC = c;
    if (!cellAt(r, c)) {
      closeTray();
      return;
    }
    if (selected && selected.r === r && selected.c === c) {
      closeTray();
      return;
    }
    openTray(r, c);
  }

  /** @param {KeyboardEvent} e */
  function onGridKeydown(e) {
    if (!roles.length) return;
    let handled = true;
    if (e.key === 'ArrowRight') focusCell(focusR, focusC + 1);
    else if (e.key === 'ArrowLeft') focusCell(focusR, focusC - 1);
    else if (e.key === 'ArrowDown') focusCell(focusR + 1, focusC);
    else if (e.key === 'ArrowUp') focusCell(focusR - 1, focusC);
    else if (e.key === 'Home') focusCell(focusR, 0);
    else if (e.key === 'End') focusCell(focusR, NCOLS - 1);
    else if (e.key === 'Enter' || e.key === ' ') {
      if (selected && selected.r === focusR && selected.c === focusC) closeTray();
      else openTray(focusR, focusC);
    } else if (e.key === 'Escape') {
      const had = !!selected;
      const rr = selected ? selected.r : focusR;
      const cc = selected ? selected.c : focusC;
      closeTray();
      if (had) focusCell(rr, cc);
    } else handled = false;
    if (handled) e.preventDefault();
  }

  function onTrayRowActivate(d) {
    if (typeof window === 'undefined' || typeof CustomEvent === 'undefined') return;
    // Scope the main feed via the EXISTING CustomEvent (mirrors EscalationRail).
    window.dispatchEvent(
      new CustomEvent('sm:focus-session', {
        detail: { sessionId: d.session_id || scopedSessionId || null, decisionId: d.id },
      }),
    );
  }

  // -- lifecycle: resolve self-exclude identity once; arm NOTHING extra -------
  onMount(() => {
    ownSessionId = getOwnSessionId() || '';
    ownProjectSlugs = readOwnProjectSlugs();
    if (enabled) {
      lastEnabled = true;
      computeNow();
    }
  });

  onDestroy(() => {
    if (coalesceTimer) {
      clearTimeout(coalesceTimer);
      coalesceTimer = null;
    }
    dirty = false;
    closeTray();
  });

  // derived display bits
  $: nowColIdx = NCOLS - 1;
  $: rowMeanPct = (role) => {
    let wSum = 0;
    let n = 0;
    for (const cell of payload.cells) {
      if (cell.role !== role) continue;
      wSum += Number(cell.mean_confidence) * Number(cell.count);
      n += Number(cell.count);
    }
    return n ? Math.round((wSum / n) * 100) : 0;
  };
  function roleTone(role) {
    if (role === 'health_monitor') return 'watch';
    if (role === 'sub_agent' || role === 'unknown') return 'muted';
    return 'calm';
  }
</script>

{#if enabled}
  <section
    class="chm"
    aria-label="Confidence heat map, role by time (BETA)"
    aria-live="off"
  >
    <div class="chm__head">
      <div class="chm__title">
        <h3>Confidence Heat Map</h3>
        <span class="chm__beta">BETA -- default OFF</span>
      </div>
      <div class="chm__win">
        rolling 60 min -- 12 x 5-min buckets -- <span class="chm__live">live</span>
      </div>
    </div>

    {#if isSelfScope}
      <!-- G2 / M15: the SM-own session is never governed by SM. No grid. -->
      <p class="chm__self" role="note">
        self -- excluded (G2 polarity). SM never governs its own session, so the
        heat map is empty by design.
      </p>
    {:else if !roles.length}
      <!-- Calm/empty: a scoped session with zero in-window decisions. -->
      <p class="chm__empty" role="note">
        No agent decisions in the last 60 minutes -- the grid is calm.
      </p>
    {:else}
      <!-- the grid: [role rail] [12 buckets]. role=grid + roving 2D tabindex. -->
      <div
        class="chm__grid"
        bind:this={gridEl}
        role="grid"
        tabindex="-1"
        aria-readonly="true"
        aria-label="Confidence heat map, agent role by 5-minute time bucket, oldest left, newest right. Arrow keys move between cells, Enter opens the decisions behind a cell, Escape closes it."
        on:keydown={onGridKeydown}
      >
        <!-- header row: corner spacer + X-axis ticks -->
        <div class="chm__spacer" aria-hidden="true"></div>
        <div class="chm__xaxis" role="row" aria-hidden="true">
          {#each buckets as b, c (b.t_ms)}
            {@const isNow = c === nowColIdx}
            <span class="chm__tick" class:chm__tick--now={isNow}>
              {isNow ? 'now' : c % 2 === 0 ? b.label : ''}
            </span>
          {/each}
        </div>

        {#each roles as role, r (role)}
          {@const tone = roleTone(role)}
          <!-- one ARIA row per role: grid > row > (rowheader | gridcell). Both
               wrappers are display:contents so the rolecell + 12 cells flow as
               DIRECT grid items into cols 1 + 2-13 (no visual change). -->
          <div class="chm__row" role="row" style="display:contents">
          <div class="chm__rolecell" role="rowheader">
            <span class="chm__rolemean">{rowMeanPct(role)}%</span>
            <span class="chm__rolebadge chm__rolebadge--{tone}">
              <span class="chm__roledot" aria-hidden="true"></span>{role}
            </span>
          </div>
          <div class="chm__cells" style="display:contents">
            {#each buckets as b, c (b.t_ms)}
              {@const cell = grid[r] ? grid[r][c] : null}
              {@const isNow = c === nowColIdx}
              {#if cell}
                {@const pct = Math.round(Number(cell.mean_confidence) * 100)}
                {@const tip = cellTooltip(role, b, cell)}
                <button
                  type="button"
                  class="chm__cell"
                  data-band={cell.band}
                  data-r={r}
                  data-c={c}
                  data-now={isNow ? 'true' : undefined}
                  data-selected={selected && selected.r === r && selected.c === c ? 'true' : undefined}
                  role="gridcell"
                  aria-readonly="true"
                  tabindex={isFocus(r, c) ? 0 : -1}
                  aria-label={cellAria(role, b, cell, isNow)}
                  on:click={() => onCellClick(r, c)}
                >
                  <span class="chm__glyph" aria-hidden="true">{BAND_GLYPH[cell.band]}</span>
                  <span class="chm__pct">{pct}%</span>
                  <span class="chm__tip" role="tooltip" aria-hidden="true">
                    <span class="chm__tipl1">{tip.line1}</span>
                    <span class="chm__tipl2">{tip.line2}</span>
                  </span>
                </button>
              {:else}
                <!-- EMPTY cell: uncolored hairline gap (absence reads as quiet, M4) -->
                <div
                  class="chm__cell"
                  data-band="EMPTY"
                  data-r={r}
                  data-c={c}
                  data-now={isNow ? 'true' : undefined}
                  role="gridcell"
                  aria-readonly="true"
                  tabindex={isFocus(r, c) ? 0 : -1}
                  aria-label={`${role}, ${b.label} window${isNow ? ' (now)' : ''}, no decisions`}
                >
                  <span class="chm__pct chm__pct--empty" aria-hidden="true">--</span>
                </div>
              {/if}
            {/each}
          </div>
          </div>
        {/each}
      </div>

      <div class="chm__foot">
        <span class="chm__legend" aria-label="Confidence band legend (paired label and color)">
          <span class="chm__k"><span class="chm__sw high" aria-hidden="true">H</span>HIGH &gt;=75%</span>
          <span class="chm__k"><span class="chm__sw ok" aria-hidden="true">O</span>OK 60-75%</span>
          <span class="chm__k"><span class="chm__sw watch" aria-hidden="true">W</span>WATCH 45-60%</span>
          <span class="chm__k"><span class="chm__sw low" aria-hidden="true">L</span>LOW &lt;45%</span>
          <span class="chm__k"><span class="chm__sw empty" aria-hidden="true"></span>(empty) no decisions</span>
        </span>
        {#if usedMock}
          <span class="chm__mock" title="Live feed had no in-window decisions -- showing a sample fixture so the grid is testable.">sample data</span>
        {/if}
      </div>

      <!-- the CLICK mini-tray: the decisions behind the selected cell -->
      {#if trayMeta}
        <div class="chm__tray" role="region" aria-label="Decisions behind the selected cell">
          <div class="chm__tray-head">
            <span class="chm__tray-title">
              {trayMeta.role}
              <span class="chm__tray-meta"
                >-- {trayMeta.label} window, {trayMeta.count} decision{trayMeta.count === 1 ? '' : 's'}, mean {trayMeta.mean}%, band {trayMeta.band}</span
              >
            </span>
            <button type="button" class="chm__tray-close" aria-label="Close decision tray (Escape)" on:click={closeTray}>Close (Esc)</button>
          </div>
          <div class="chm__tray-rows">
            {#each trayRows as d (d.id)}
              <button
                type="button"
                class="chm__drow"
                aria-label={`Decision ${d.action}, confidence ${Math.round(d.confidence * 100)} percent, ${d.reasoning}. Activate to scope the main feed to this decision.`}
                on:click={() => onTrayRowActivate(d)}
              >
                <span class="chm__ts">{hhmmss(d.timestamp)}</span>
                <span class="chm__badge" data-act={d.action}>
                  <span class="chm__swatch" aria-hidden="true"></span>{d.action}
                </span>
                <span class="chm__conf">{Math.round(d.confidence * 100)}%</span>
                <span class="chm__msg" title={d.reasoning}>{d.reasoning}</span>
              </button>
            {/each}
          </div>
        </div>
      {/if}
    {/if}
  </section>
{/if}

<style>
  /* The pane is a still shelf inside Frame B, below the roster. Calm at rest. */
  .chm {
    margin-top: 0.75rem;
    padding-top: 0.75rem;
    border-top: 1px solid var(--calm-hairline, var(--border, #192030));
    min-width: 0;
    /* Per-band IN-TILE ink, chosen for AAA (>=7:1) on each band fill. theme.css
       does NOT define these (they are local to this pane), so they are declared
       here and overridden per-theme below -- no global token is polluted. Dark
       themes => near-black ink on the bright fills; the paper (light) theme
       darkens the fills (as RoleBadge does) so a near-WHITE ink clears AAA. */
    --chm-ink-high: #06210f;
    --chm-ink-ok: #1c2606;
    --chm-ink-watch: #2a1404;
    --chm-ink-low: #2a0606;
  }
  /* phosphor (green-on-black): the re-tuned action fills still take dark ink. */
  :global([data-theme='phosphor']) .chm {
    --chm-ink-high: #001a00;
    --chm-ink-ok: #0a1a00;
    --chm-ink-watch: #2a1a00;
    --chm-ink-low: #2a0000;
  }
  /* paper (light): the action fills darken => near-white ink clears AAA. */
  :global([data-theme='paper']) .chm {
    --chm-ink-high: #ffffff;
    --chm-ink-ok: #ffffff;
    --chm-ink-watch: #ffffff;
    --chm-ink-low: #ffffff;
  }

  .chm__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
    padding-bottom: 10px;
  }
  .chm__title {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }
  .chm__title h3 {
    margin: 0;
    font-family: var(--font-h, inherit);
    font-size: 15px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
  }
  .chm__beta {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--badge-obs-fg, #475569);
    background: var(--badge-obs-bg, #f1f5f9);
    border: 1px solid var(--badge-obs-border, #cbd5e1);
    border-radius: 3px;
    padding: 2px 8px;
    white-space: nowrap;
  }
  .chm__win {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 11px;
    color: var(--calm-ink-quiet, var(--text-dim, #94a3b8));
    letter-spacing: 0.04em;
  }
  .chm__live {
    color: var(--calm-accent, var(--accent, #f59e0b));
  }

  /* self / empty calm notes -- never a wall of cells. */
  .chm__self,
  .chm__empty {
    margin: 8px 0 0;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 12px;
    line-height: 1.5;
    color: var(--calm-ink-quiet, var(--text-dim, #94a3b8));
    font-style: italic;
  }

  /* the grid: [role-rail] [12 buckets]. A single flat 13-column grid so the
     ARIA tree is grid > row(display:contents) > [rowheader, gridcell x12].
     The rolecell takes col 1; the 12 cells fill cols 2-13 by source order. */
  .chm__grid {
    display: grid;
    grid-template-columns: minmax(132px, max-content) repeat(12, 1fr);
    /* row-gap keeps the 8px between role rows; column-gap is the 3px the cells
       used to carry internally. The rail->first-bucket gap (was an 8px
       column-gap) is restored by +5px on .chm__rolecell padding-right below
       (4px -> 9px), so the visual is unchanged after the flatten. */
    row-gap: 8px;
    column-gap: 3px;
    align-items: start;
    outline: none;
  }
  .chm__spacer {
    grid-column: 1;
  }
  .chm__xaxis {
    grid-column: 2 / -1;
    display: grid;
    grid-template-columns: repeat(12, 1fr);
    gap: 3px;
    padding-bottom: 4px;
    border-bottom: 1px solid var(--calm-hairline, var(--border, #192030));
  }
  .chm__tick {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 9px;
    color: var(--calm-ink-quiet, var(--text-dim, #94a3b8));
    text-align: center;
    letter-spacing: 0.02em;
    white-space: nowrap;
    min-width: 0;
    overflow: hidden;
  }
  .chm__tick--now {
    color: var(--calm-accent, var(--accent, #f59e0b));
    font-weight: 700;
  }

  .chm__rolecell {
    grid-column: 1;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 7px;
    height: 34px;
    /* 9px (was 4px) restores the rail->first-bucket gap: the old 8px grid
       column-gap collapsed to 3px under the flat grid, so +5px here keeps the
       effective rolecell->cell distance identical (4+8 == 9+3 == 12px). */
    padding-right: 9px;
  }
  .chm__rolemean {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10px;
    color: var(--calm-ink-quiet, var(--text-dim, #94a3b8));
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  /* RoleBadge facsimile: dot decorative / text load-bearing (M4/M16). */
  .chm__rolebadge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-family: var(--font-d, ui-monospace, monospace);
    font-weight: 600;
    letter-spacing: 0.02em;
    line-height: 1;
    border-radius: 2px;
    border: 1px solid var(--calm-hairline, var(--border, #192030));
    background: var(--calm-surface-row-alt, var(--bg-row-alt, #0b1018));
    color: var(--calm-ink, var(--text, #b8b098));
    white-space: nowrap;
    font-size: 11px;
    padding: 3px 8px;
  }
  .chm__roledot {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: currentColor;
    flex: 0 0 auto;
    opacity: 0.85;
  }
  .chm__rolebadge--watch {
    color: #c9a227;
    border-color: rgba(202, 138, 4, 0.4);
    background: rgba(202, 138, 4, 0.1);
    font-weight: 700;
  }
  .chm__rolebadge--muted {
    color: var(--calm-ink-quiet, var(--text-dim, #94a3b8));
    font-weight: 500;
  }

  /* row body: display:contents so the 12 cells become DIRECT grid items of
     .chm__grid (cols 2-13). No box of its own; no role (the parent .chm__row
     carries role="row"). */
  .chm__cells {
    display: contents;
  }

  /* HeatCell -- THREE simultaneous encodings (M4): band fill + literal % + glyph. */
  .chm__cell {
    position: relative;
    height: 34px;
    border: 0;
    border-radius: 2px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1px;
    cursor: pointer;
    padding: 0;
    background: transparent;
    font-family: var(--font-d, ui-monospace, monospace);
    color: inherit;
    transition: filter 0.15s ease;
  }
  .chm__cell:hover {
    filter: brightness(1.06);
  }
  .chm__pct {
    font-size: 12px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1;
  }
  .chm__pct--empty {
    font-size: 11px;
    font-weight: 600;
    opacity: 0.6;
  }
  .chm__glyph {
    position: absolute;
    top: 2px;
    right: 3px;
    font-size: 8px;
    font-weight: 700;
    letter-spacing: 0.02em;
    line-height: 1;
    opacity: 0.92;
  }
  /* band fills reuse the action-palette tokens as the confidence ramp; the
     in-tile ink per band clears AAA on each fill (tokens from theme.css). */
  .chm__cell[data-band='HIGH'] {
    background: var(--c-allow, #22c55e);
    color: var(--chm-ink-high);
  }
  .chm__cell[data-band='OK'] {
    background: var(--c-suggest, #84cc16);
    color: var(--chm-ink-ok);
  }
  .chm__cell[data-band='WATCH'] {
    background: var(--c-intervene, #f97316);
    color: var(--chm-ink-watch);
  }
  .chm__cell[data-band='LOW'] {
    background: var(--c-block, #ef4444);
    color: var(--chm-ink-low);
  }
  /* an EMPTY cell is NOT colored -- a calm hairline gap (absence = quiet). */
  .chm__cell[data-band='EMPTY'] {
    background: transparent;
    border: 1px solid var(--calm-hairline, var(--border, #192030));
    color: var(--calm-ink-quiet, var(--text-dim, #94a3b8));
    cursor: default;
  }
  .chm__cell[data-band='EMPTY']:hover {
    filter: none;
  }
  /* the rightmost ("now") column: a 1px accent underline -- the one emphasis. */
  .chm__cell[data-now='true']::after {
    content: '';
    position: absolute;
    left: 0;
    right: 0;
    bottom: -2px;
    height: 1px;
    background: var(--calm-accent, var(--accent, #f59e0b));
  }
  /* M17 keyboard focus ring on a gridcell: 2px solid accent + offset. */
  .chm__cell:focus-visible {
    outline: 2px solid var(--calm-accent, var(--accent, #f59e0b));
    outline-offset: 2px;
    border-radius: 3px;
  }
  .chm__cell[data-selected='true']::before {
    content: '';
    position: absolute;
    inset: -3px;
    border: 2px solid var(--calm-accent, var(--accent, #f59e0b));
    border-radius: 4px;
    pointer-events: none;
  }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .chm__cell {
      transition: none;
    }
  }
  :global(html[data-motion='reduce']) .chm__cell {
    transition: none;
  }

  /* hover/focus tooltip -- the SAME signal IN WORDS. */
  .chm__tip {
    position: absolute;
    left: 50%;
    bottom: calc(100% + 7px);
    transform: translateX(-50%);
    z-index: 6;
    white-space: nowrap;
    display: none;
    background: var(--calm-surface-row, var(--bg-row, #0e141e));
    border: 1px solid var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25)));
    border-radius: 5px;
    padding: 7px 10px;
    box-shadow: 0 8px 24px -10px rgba(0, 0, 0, 0.7);
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 11px;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    line-height: 1.4;
    text-align: left;
    flex-direction: column;
  }
  .chm__cell[data-band]:not([data-band='EMPTY']):hover .chm__tip,
  .chm__cell:focus-visible .chm__tip {
    display: flex;
  }
  .chm__tipl1 {
    display: block;
  }
  .chm__tipl2 {
    display: block;
    color: var(--calm-ink-quiet, var(--text-dim, #94a3b8));
    margin-top: 2px;
  }

  /* foot: paired band legend + the mock marker. */
  .chm__foot {
    display: flex;
    align-items: center;
    gap: 18px;
    flex-wrap: wrap;
    margin-top: 14px;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 11px;
    color: var(--calm-ink-quiet, var(--text-dim, #94a3b8));
  }
  .chm__legend {
    display: inline-flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
  }
  .chm__k {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .chm__sw {
    width: 13px;
    height: 13px;
    border-radius: 2px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 8px;
    font-weight: 700;
    flex: 0 0 auto;
  }
  .chm__sw.high {
    background: var(--c-allow, #22c55e);
    color: var(--chm-ink-high);
  }
  .chm__sw.ok {
    background: var(--c-suggest, #84cc16);
    color: var(--chm-ink-ok);
  }
  .chm__sw.watch {
    background: var(--c-intervene, #f97316);
    color: var(--chm-ink-watch);
  }
  .chm__sw.low {
    background: var(--c-block, #ef4444);
    color: var(--chm-ink-low);
  }
  .chm__sw.empty {
    background: transparent;
    border: 1px solid var(--calm-hairline, var(--border, #192030));
  }
  .chm__mock {
    color: var(--badge-ar-fg, #d97706);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  /* the CLICK mini-tray (slides open below the grid; never covers it). */
  .chm__tray {
    margin-top: 14px;
    border: 1px solid var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25)));
    border-radius: 6px;
    background: var(--calm-surface-row, var(--bg-row, #0e141e));
    overflow: hidden;
  }
  .chm__tray-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 9px 13px;
    border-bottom: 1px solid var(--calm-hairline, var(--border, #192030));
    background: var(--calm-surface-row-alt, var(--bg-row-alt, #0b1018));
  }
  .chm__tray-title {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 12px;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
  }
  .chm__tray-meta {
    color: var(--calm-ink-quiet, var(--text-dim, #94a3b8));
  }
  .chm__tray-close {
    appearance: none;
    background: transparent;
    border: 1px solid var(--calm-hairline, var(--border, #192030));
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    border-radius: 4px;
    font-size: 11px;
    padding: 3px 9px;
    cursor: pointer;
    font-family: var(--font-d, ui-monospace, monospace);
    letter-spacing: 0.04em;
  }
  .chm__tray-close:focus-visible {
    outline: 2px solid var(--calm-accent, var(--accent, #f59e0b));
    outline-offset: 2px;
  }
  .chm__tray-rows {
    padding: 4px 0;
    max-height: 260px;
    overflow: auto;
  }
  .chm__drow {
    display: grid;
    grid-template-columns: 72px 104px 56px 1fr;
    gap: 10px;
    align-items: center;
    padding: 7px 13px;
    border-top: 1px solid var(--calm-hairline, var(--border, #192030));
    font-size: 12px;
    cursor: pointer;
    width: 100%;
    text-align: left;
    background: transparent;
    border-left: 0;
    border-right: 0;
    color: inherit;
    font-family: inherit;
  }
  .chm__drow:first-child {
    border-top: 0;
  }
  .chm__drow:hover {
    background: var(--calm-surface-row-hover, var(--bg-row-hover, #131c2a));
  }
  .chm__drow:focus-visible {
    outline: 2px solid var(--calm-accent, var(--accent, #f59e0b));
    outline-offset: -2px;
  }
  .chm__ts {
    font-family: var(--font-d, ui-monospace, monospace);
    color: var(--calm-ink-quiet, var(--text-dim, #94a3b8));
    font-variant-numeric: tabular-nums;
  }
  .chm__conf {
    font-family: var(--font-d, ui-monospace, monospace);
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    font-variant-numeric: tabular-nums;
    text-align: right;
  }
  .chm__msg {
    color: var(--calm-ink, var(--text, #b8b098));
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }
  /* paired action badge -- the text label is ALWAYS present; color is 2nd channel. */
  .chm__badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    justify-self: start;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    border: 1px solid var(--calm-hairline, var(--border, #192030));
    border-radius: 3px;
    padding: 2px 7px;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
  }
  .chm__swatch {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .chm__badge[data-act='ALLOW'] {
    border-color: var(--c-allow, #22c55e);
  }
  .chm__badge[data-act='ALLOW'] .chm__swatch {
    background: var(--c-allow, #22c55e);
  }
  .chm__badge[data-act='SUGGEST'] {
    border-color: var(--c-suggest, #84cc16);
  }
  .chm__badge[data-act='SUGGEST'] .chm__swatch {
    background: var(--c-suggest, #84cc16);
  }
  .chm__badge[data-act='GUIDE'] {
    border-color: var(--c-guide, #eab308);
  }
  .chm__badge[data-act='GUIDE'] .chm__swatch {
    background: var(--c-guide, #eab308);
  }
  .chm__badge[data-act='INTERVENE'] {
    border-color: var(--c-intervene, #f97316);
  }
  .chm__badge[data-act='INTERVENE'] .chm__swatch {
    background: var(--c-intervene, #f97316);
  }
  .chm__badge[data-act='BLOCK'] {
    border-color: var(--c-block, #ef4444);
  }
  .chm__badge[data-act='BLOCK'] .chm__swatch {
    background: var(--c-block, #ef4444);
  }
</style>
