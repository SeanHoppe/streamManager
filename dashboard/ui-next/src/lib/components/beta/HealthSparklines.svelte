<!--
  HealthSparklines.svelte -- BETA feature "health-sparklines" (#34).

  WHAT IT IS
    A whisper-quiet ~132x18px health strip per NON-SELF governed session: a
    rolling WINDOW-decision mean-confidence trace (the load-bearing solid line)
    over a faint throughput floor wash (the dotted secondary trace). Each strip
    carries a PAIRED text read ("healthy conf 0.91 -- steady") so the state is
    never color-alone (M4). Hover or keyboard-activate a strip to open an
    observational drawer with the last ~100 decisions + a trigger_reason
    breakdown. The drawer NEVER auto-foregrounds (M2).

    It mounts as a calm block beneath the SessionRail header, drawing ONE strip
    per session in the same order as the rail lanes, so the operator reads each
    lane's trend in line with the lane it belongs to.

  BETA GATE (load-bearing)
    The ENTIRE component is wrapped in {#if enabled} where enabled is
    $betaFlags['health-sparklines']. When the flag is OFF it renders NOTHING and
    registers NO store subscriptions beyond the cheap flag read, NO poller, NO
    SSE handler, NO timer. The flag defaults OFF (lib/beta/registry.js); the
    operator flips it in Settings > BETA features.

  DATA (M18 post-hoc -- no new transport, no new envelope, no FROZEN edit)
    Live strips are derived 100% CLIENT-SIDE from the ALREADY-OPEN decision feed
    (decisionsStore from lib/sse.js) bucketed by session_id -- there is no new
    poller and no new SSE channel. The drawer's "last 100" detail loads once on
    open via an additive read GET /api/sessions/{session_id}/sparkline-data; when
    that endpoint is absent or returns nothing (fresh gov.db) the component falls
    back to realistic deterministic MOCK data so it is always inspectable
    (usedMockData=true, labelled in the UI).

  POLARITY (G2/M15)
    Strips are drawn from the `sessions` store, which structurally self-excludes
    the SM's own session + own project_slug(s) in setSessions(). There is no code
    path that draws a strip for SM-self.

  DOMAIN-AGNOSTIC (M16): session identity is rendered from data (project_slug /
  short id). No monitored-project / JOB / role vocabulary. The trigger_reason
  breakdown is a generic governance enum only.

  ASCII-only (cp1252-safe): dash is "--". No smart quotes / em-dash.
-->
<script>
  import { tick, onDestroy } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { sessions } from '../../stores/session.js';
  import { decisionsStore } from '../../sse.js';
  import { getSparklineData } from '../../api.js';
  import {
    buildView,
    confPath,
    thruPaths,
    stateLabel,
    mockRows,
    mockBandFor,
    reasonBreakdown,
    POINTS,
    FLOOR,
  } from './HealthSparklines.data.js';

  const FLAG_KEY = 'health-sparklines';
  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // ---- live decision buckets (client-side, from the open feed) --------------
  // Only ever read $decisionsStore + $sessions while ENABLED. When OFF the
  // {#if enabled} block below is unmounted, so these reactive reads do not run
  // and no extra work happens -- the gate is load-bearing.
  $: laneSessions = enabled ? $sessions : [];
  $: feed = enabled ? $decisionsStore : [];

  /**
   * Bucket the open decision feed by session_id, newest-first within each
   * bucket (the feed is already newest-first). Pure derive -- no fetch.
   * @type {Record<string, Array<Record<string, any>>>}
   */
  $: bySession = (() => {
    /** @type {Record<string, Array<Record<string, any>>>} */
    const out = {};
    for (const r of feed) {
      const sid = r && r.session_id;
      if (!sid) continue;
      (out[sid] || (out[sid] = [])).push(r);
    }
    return out;
  })();

  /**
   * Per-session strip view-models. For each governed session we use the live
   * rows when present; otherwise (no live rows in the open window) we fall back
   * to deterministic mock so the strip is always inspectable. The fallback is
   * flagged per-strip so the UI can mark it.
   */
  $: strips = laneSessions.map((s) => {
    const sid = String(s.id);
    const live = bySession[sid] || [];
    const usingMock = live.length === 0;
    const rows = usingMock ? mockRows(sid, mockBandFor(sid), POINTS) : live;
    const view = buildView(rows);
    const ended = s.ended_at !== null && s.ended_at !== undefined;
    const slug =
      typeof s.project_slug === 'string' && s.project_slug.trim() ? s.project_slug.trim() : '';
    const name = slug || shortId(sid);
    const cp = confPath(view.conf);
    const tp = thruPaths(view.thru);
    return {
      sid,
      name,
      ended,
      usingMock,
      view,
      confD: cp,
      thruLineD: tp.line,
      thruAreaD: tp.area,
      aria: stripAria(name, view, ended),
      readWord: view.label,
      readLine: `conf ${view.meanConf.toFixed(2)} -- ${view.suffix}`,
    };
  });

  // Any strip on mock data => the whole block is showing sample data; surface it
  // once in the footer (M4: a literal text label, never an implicit signal).
  $: usedMockData = strips.some((st) => st.usingMock);

  function shortId(id) {
    const s = String(id);
    return s.length <= 10 ? s : `${s.slice(0, 6)}..${s.slice(-3)}`;
  }

  function stripAria(name, view, ended) {
    const lvl = `confidence ${view.meanConf.toFixed(2)}`;
    const dir = view.trend === 'falling' ? 'falling' : view.trend === 'rising' ? 'rising' : 'steady';
    const st =
      view.state === 'breach'
        ? 'confidence-floor breached'
        : view.state === 'drift'
          ? 'confidence drifting -- review advised'
          : 'healthy';
    const tail = ended ? ' at session end' : '';
    return `${name} ${lvl}, ${dir}${tail}. ${st}. Activate to open the last decisions detail.`;
  }

  // ---- drawer (observational; opens on hover-dwell OR keyboard intent) -------
  let open = false;
  /** @type {string|null} */
  let openSid = null;
  let openName = '';
  let drawerState = 'healthy';
  let loading = false;
  let drawerMock = false;
  /** @type {Array<Record<string, any>>} */
  let detailRows = [];
  /** @type {HTMLDivElement|null} */
  let panelEl = null;
  /** @type {Element|null} */
  let prevFocus = null;
  /** @type {ReturnType<typeof setTimeout>|null} */
  let hoverTimer = null;

  /** Load the last ~100 decisions for the drawer once per open. Best-effort. */
  async function loadDetail(sid) {
    loading = true;
    let payload = null;
    try {
      payload = await getSparklineData(sid, { limit: 100 });
    } catch {
      payload = null;
    }
    const rows = payload && Array.isArray(payload.rows) ? payload.rows : [];
    if (rows.length === 0) {
      // fresh gov.db / endpoint absent -- representative mock so it is testable.
      detailRows = mockRows(sid, mockBandFor(sid), 100);
      drawerMock = true;
    } else {
      detailRows = rows;
      drawerMock = false;
    }
    loading = false;
  }

  $: detailReasons = open ? reasonBreakdown(detailRows) : [];

  function clamp01n(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return 0;
    return Math.max(0, Math.min(1, n));
  }

  // ---- larger drawer chart geometry (420 x 96), reusing the pure mappers ----
  // confidence for the big chart is the FULL detail set oldest-first.
  $: bigConf =
    open && detailRows.length
      ? detailRows.slice().reverse().map((r) => clamp01n(r.confidence))
      : [];
  $: bigConfD = confPath(bigConf, 420, 96);

  function detailRowsThroughput(rows) {
    // normalize the per-row throughput count to 0..1 for the floor wash.
    const arr = rows.slice().reverse().map((r) => Number(r && r.throughput));
    const max = Math.max(1, ...arr.filter(Number.isFinite));
    return arr.map((t) => (Number.isFinite(t) ? t / max : 0));
  }
  $: bigThru = open ? thruPaths(detailRowsThroughput(detailRows), 420, 96) : { line: '', area: '' };

  async function openDrawer(strip) {
    if (!enabled) return;
    prevFocus = typeof document !== 'undefined' ? document.activeElement : null;
    openSid = strip.sid;
    openName = strip.name;
    drawerState = strip.view.state;
    open = true;
    await loadDetail(strip.sid);
    await tick();
    panelEl?.focus();
  }

  function closeDrawer() {
    open = false;
    openSid = null;
    const target = prevFocus && /** @type {any} */ (prevFocus).focus ? prevFocus : null;
    /** @type {HTMLElement|null} */ (target)?.focus?.();
    prevFocus = null;
  }

  function onStripEnter(strip) {
    if (!enabled) return;
    if (hoverTimer) clearTimeout(hoverTimer);
    // short dwell so a casual sweep does not pop the drawer (M2 spirit).
    hoverTimer = setTimeout(() => openDrawer(strip), 260);
  }
  function onStripLeave() {
    if (hoverTimer) {
      clearTimeout(hoverTimer);
      hoverTimer = null;
    }
  }
  function onStripKey(e, strip) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      e.stopPropagation();
      openDrawer(strip);
    }
  }

  function onPanelKeydown(e) {
    if (!open) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      closeDrawer();
      return;
    }
    if (e.key === 'Tab' && panelEl) {
      const f = Array.from(
        panelEl.querySelectorAll(
          'button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((n) => /** @type {HTMLElement} */ (n).offsetParent !== null);
      if (!f.length) return;
      const first = /** @type {HTMLElement} */ (f[0]);
      const last = /** @type {HTMLElement} */ (f[f.length - 1]);
      const active = document.activeElement;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  // If the flag flips OFF while the drawer is open, close it (defense-in-depth;
  // the {#if enabled} unmount handles the rest).
  $: if (!enabled && open) closeDrawer();

  onDestroy(() => {
    if (hoverTimer) clearTimeout(hoverTimer);
  });
</script>

<svelte:window on:keydown={onPanelKeydown} />

{#if enabled}
  <section class="hs" aria-label="Per-session health sparklines">
    <header class="hs__head">
      <span class="hs__title">Session health</span>
      <span class="hs__beta">BETA</span>
    </header>

    {#if strips.length === 0}
      <p class="hs__empty">
        No governed sessions yet -- strips appear here as non-SM sessions are
        observed.
      </p>
    {:else}
      <ul class="hs__list" role="list">
        {#each strips as st (st.sid)}
          <li class="hs__row" class:hs__row--ended={st.ended}>
            <span class="hs__name" title={st.name}>{st.name}</span>

            <span
              class="hs__spark hs__spark--{st.view.state}"
              role="button"
              tabindex="0"
              aria-haspopup="dialog"
              aria-label={st.aria}
              data-session-id={st.sid}
              data-state={st.view.state}
              on:mouseenter={() => onStripEnter(st)}
              on:mouseleave={onStripLeave}
              on:focus={onStripLeave}
              on:blur={onStripLeave}
              on:keydown={(e) => onStripKey(e, st)}
              on:click|stopPropagation={() => openDrawer(st)}
            >
              <svg viewBox="0 0 132 18" preserveAspectRatio="none" aria-hidden="true" focusable="false">
                {#if st.thruAreaD}<path class="hs__thru-area" d={st.thruAreaD} />{/if}
                {#if st.thruLineD}<path class="hs__thru-line" d={st.thruLineD} />{/if}
                {#if st.confD}<path class="hs__conf" d={st.confD} />{/if}
              </svg>
            </span>

            <!-- the always-present TEXT read (M4: the strip state is never
                 color-only at a glance). The state WORD is the literal label. -->
            <span class="hs__read">
              <b class="hs__read-state">{st.readWord}</b>
              <span class="hs__read-line">{st.readLine}</span>
            </span>
          </li>
        {/each}
      </ul>
    {/if}

    <footer class="hs__foot">
      <span class="hs__foot-pill">BETA -- default OFF, toggled in Settings</span>
      {#if usedMockData}
        <span class="hs__foot-mock">SAMPLE DATA -- no live decisions in scope yet</span>
      {/if}
    </footer>
  </section>

  {#if open}
    <!-- SCRIM: click-out closes. Not a focus target. -->
    <div class="hs-scrim" on:click={closeDrawer} aria-hidden="true"></div>

    <!-- DRAWER: role=dialog aria-modal; labelled; Escape + focus trap. M2: it
         is opened ONLY by operator hover-dwell / keyboard intent above. -->
    <div
      class="hs-drawer"
      role="dialog"
      aria-modal="true"
      aria-labelledby="hs-drawer-title"
      tabindex="-1"
      bind:this={panelEl}
    >
      <header class="hs-drawer__head">
        <div class="hs-drawer__grow">
          <h2 id="hs-drawer-title" class="hs-drawer__title">{openName || 'Session detail'}</h2>
          <p class="hs-drawer__sub">
            last {detailRows.length} decisions
            <span class="hs-drawer__state hs-drawer__state--{drawerState}">{stateLabel(drawerState)}</span>
          </p>
        </div>
        <button
          class="hs-drawer__close"
          type="button"
          aria-label="Close session detail (Esc)"
          on:click={closeDrawer}
        >
          <span aria-hidden="true">x</span>
        </button>
      </header>

      <div class="hs-drawer__body">
        {#if loading}
          <p class="hs-drawer__loading">Loading detail...</p>
        {:else}
          <p class="hs-drawer__source" data-mock={drawerMock}>
            {drawerMock
              ? 'SAMPLE DATA -- no live decisions for this session yet; showing a representative shape.'
              : 'LIVE -- aggregated from gov.db decisions for this session.'}
          </p>

          <p class="hs-drawer__label">Confidence + throughput -- last {detailRows.length} decisions</p>
          <div class="hs-drawer__chart">
            <svg
              viewBox="0 0 420 96"
              preserveAspectRatio="none"
              role="img"
              aria-label="Line chart of confidence and throughput over the last {detailRows.length} decisions. A data table follows for assistive technology."
            >
              <!-- confidence floor reference line (the breach threshold) -->
              <line class="hs-dc-floor" x1="0" y1="62" x2="420" y2="62" />
              {#if bigThru.area}<path class="hs-dc-thru" d={bigThru.area} />{/if}
              {#if bigConfD}<path class="hs-dc-conf" d={bigConfD} />{/if}
              <line class="hs-dc-axis" x1="0" y1="95" x2="420" y2="95" />
            </svg>
          </div>
          <div class="hs-drawer__legend" aria-hidden="true">
            <span class="hs-lk"><span class="hs-sw hs-sw--conf"></span> confidence</span>
            <span class="hs-lk"><span class="hs-sw hs-sw--floor"></span> floor {FLOOR.toFixed(2)}</span>
            <span class="hs-lk"><span class="hs-sw hs-sw--thru"></span> throughput</span>
          </div>

          <!-- a11y data-table fallback (every ~10th interval to stay scannable) -->
          <table class="hs-sr-only">
            <caption>Confidence and throughput per decision interval, oldest first</caption>
            <thead><tr><th>interval</th><th>confidence</th><th>throughput</th></tr></thead>
            <tbody>
              {#each detailRows.slice().reverse() as r, i}
                {#if i % 10 === 0 || i === detailRows.length - 1}
                  <tr>
                    <td>{i}</td>
                    <td>{Number(r.confidence).toFixed(2)}</td>
                    <td>{r.throughput ?? '--'}</td>
                  </tr>
                {/if}
              {/each}
            </tbody>
          </table>

          <p class="hs-drawer__label">trigger_reason breakdown</p>
          <ul class="hs-reasons">
            {#each detailReasons as r (r.key)}
              <li class="hs-reason hs-reason--{r.key}">
                <span class="hs-reason__swatch" aria-hidden="true"></span>
                <span class="hs-reason__name">{r.label}</span>
                <span class="hs-reason__count">{r.count}</span>
              </li>
            {/each}
          </ul>

          <p class="hs-drawer__obs">
            Observational view -- this drawer does not foreground itself and does
            not attach to the session. Confirm the dip is real, then attach from
            Frame B if warranted.
          </p>
        {/if}
      </div>

      <footer class="hs-drawer__foot">
        <span class="hs-drawer__foot-pill">BETA</span>
        <span>Read-only. Default OFF, toggled in Settings &gt; BETA features. Never auto-foregrounds.</span>
      </footer>
    </div>
  {/if}
{/if}

<style>
  /* ---- the strip block -- a calm slate panel beneath the rail header ------- */
  .hs {
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 6px);
    padding: var(--space-4, 10px);
    background: var(--calm-surface-raised, var(--bg-card, #0c1118));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-soft, 4px);
    font-family: var(--ff-system);
  }
  .hs__head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-4, 10px);
    padding-bottom: var(--space-2, 4px);
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
  }
  .hs__title {
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .hs__beta {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--badge-ar-fg, #d97706);
    background: var(--badge-ar-bg, #fef3c7);
    border: 1px solid var(--badge-ar-border, #d97706);
    border-radius: 4px;
    padding: 1px 5px;
  }

  .hs__empty {
    margin: 0;
    padding: var(--space-3, 6px) var(--space-2, 4px);
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    font-size: var(--fs-meta, 13px);
    font-style: italic;
    line-height: var(--lh-body, 1.5);
  }

  .hs__list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 6px);
  }
  .hs__row {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas: 'name' 'spark' 'read';
    gap: 2px;
  }
  .hs__row--ended { opacity: 0.62; }

  .hs__name {
    grid-area: name;
    font-size: var(--fs-meta, 13px);
    font-weight: 460;
    letter-spacing: 0.01em;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    line-height: var(--lh-tight, 1.25);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* the focusable sparkline element: role=img, tabindex 0. The quietest thing
     in the block -- no border, no background, no glow until focus/hover. */
  .hs__spark {
    grid-area: spark;
    position: relative;
    display: block;
    width: 132px;
    height: 18px;
    cursor: pointer;
    border-radius: var(--radius-sharp, 2px);
  }
  .hs__spark:focus-visible,
  .hs__spark:hover {
    outline: 1px solid var(--badge-ar-border, #d97706);
    outline-offset: 2px;
  }
  .hs__spark svg { display: block; width: 132px; height: 18px; }

  /* confidence = the load-bearing solid 1.25px trace (top 70% of the band) */
  .hs__conf {
    fill: none;
    stroke-width: 1.25;
    stroke-linejoin: round;
    stroke-linecap: round;
    opacity: 0.85;
  }
  /* throughput = a dotted, low-opacity baseline-anchored floor wash beneath */
  .hs__thru-area { stroke: none; fill: var(--spark-floor, rgba(148, 163, 184, 0.16)); }
  .hs__thru-line {
    fill: none;
    stroke: var(--calm-ink-quiet, var(--text-dim, #948870));
    stroke-width: 1;
    stroke-dasharray: 1 2;
    opacity: 0.5;
  }

  /* tri-state confidence ink -- the M4 SECOND channel; the read WORD + aria
     carry the literal read. Tokens land via theme.css; fallbacks match it. */
  .hs__spark--healthy .hs__conf { stroke: var(--spark-healthy, #94a3b8); }
  .hs__spark--drift .hs__conf { stroke: var(--spark-drift, #f59e0b); }
  .hs__spark--breach .hs__conf { stroke: var(--spark-breach, #f87171); }

  .hs__read {
    grid-area: read;
    display: inline-flex;
    align-items: baseline;
    gap: 5px;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    letter-spacing: 0.02em;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-width: 0;
  }
  .hs__read-state { font-weight: 700; }
  .hs__spark--healthy ~ .hs__read .hs__read-state { color: var(--spark-healthy, #94a3b8); }
  .hs__spark--drift ~ .hs__read .hs__read-state { color: var(--spark-drift, #f59e0b); }
  .hs__spark--breach ~ .hs__read .hs__read-state { color: var(--spark-breach, #f87171); }
  .hs__read-line { color: var(--calm-ink-quiet, var(--text-dim, #948870)); }

  .hs__foot {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-3, 6px);
    margin-top: var(--space-2, 4px);
    padding-top: var(--space-3, 6px);
    border-top: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
  }
  .hs__foot-pill {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    letter-spacing: 0.04em;
    color: var(--badge-obs-fg, #475569);
    background: var(--badge-obs-bg, #f1f5f9);
    border: 1px solid var(--badge-obs-border, #cbd5e1);
    border-radius: 999px;
    padding: 2px 9px;
  }
  .hs__foot-mock {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    letter-spacing: 0.02em;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }

  /* ---- drawer ------------------------------------------------------------- */
  .hs-scrim {
    position: fixed;
    inset: 0;
    z-index: 80;
    background: rgba(8, 10, 12, 0.55);
  }
  .hs-drawer {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    z-index: 81;
    width: min(460px, 96vw);
    display: flex;
    flex-direction: column;
    background: var(--calm-surface-raised, var(--bg-card, #0c1118));
    border-left: 3px solid var(--calm-accent, var(--accent, #f59e0b));
    box-shadow: -18px 0 48px -24px rgba(0, 0, 0, 0.7);
    color: var(--calm-ink, var(--text, #b8b098));
    font-family: var(--ff-system);
    overflow: hidden;
  }
  .hs-drawer__head {
    flex: 0 0 auto;
    display: flex;
    align-items: flex-start;
    gap: var(--space-4, 10px);
    padding: var(--space-4, 10px) var(--space-5, 14px);
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
  }
  .hs-drawer__grow { flex: 1 1 auto; min-width: 0; }
  .hs-drawer__title {
    margin: 0;
    font-size: var(--fs-body, 14px);
    font-weight: 620;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    line-height: var(--lh-tight, 1.25);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .hs-drawer__sub {
    margin: var(--space-2, 4px) 0 0;
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    font-variant-numeric: tabular-nums;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .hs-drawer__state {
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 0 5px;
    border-radius: 3px;
  }
  .hs-drawer__state--healthy { color: var(--spark-healthy, #94a3b8); }
  .hs-drawer__state--drift { color: var(--spark-drift, #f59e0b); }
  .hs-drawer__state--breach { color: var(--spark-breach, #f87171); }

  .hs-drawer__close {
    flex: 0 0 auto;
    font: inherit;
    line-height: 1;
    font-size: 1rem;
    background: transparent;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-sharp, 2px);
    width: 28px;
    height: 28px;
    cursor: pointer;
  }
  .hs-drawer__close:hover { color: var(--calm-ink-loud, var(--text-bright, #e8e0cc)); }

  .hs-drawer__body {
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
    padding: var(--space-5, 14px);
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 6px);
  }
  .hs-drawer__loading {
    padding: var(--space-6, 22px) 0;
    text-align: center;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    font-style: italic;
  }
  .hs-drawer__source {
    margin: 0;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    letter-spacing: 0.02em;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .hs-drawer__source[data-mock='true'] { color: var(--spark-drift, #f59e0b); }

  .hs-drawer__label {
    margin: var(--space-3, 6px) 0 0;
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }

  .hs-drawer__chart {
    width: 100%;
    height: 96px;
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-sharp, 2px);
  }
  .hs-drawer__chart svg { display: block; width: 100%; height: 96px; }
  .hs-dc-conf { fill: none; stroke: var(--calm-accent, var(--accent, #f59e0b)); stroke-width: 1.5; opacity: 0.9; }
  .hs-dc-floor { stroke: var(--spark-breach, #f87171); stroke-width: 1; stroke-dasharray: 3 3; opacity: 0.7; }
  .hs-dc-thru { fill: var(--spark-floor, rgba(148, 163, 184, 0.16)); stroke: none; }
  .hs-dc-axis { stroke: var(--calm-hairline, var(--border, #192030)); stroke-width: 1; }

  .hs-drawer__legend {
    display: flex;
    gap: var(--space-5, 14px);
    flex-wrap: wrap;
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .hs-lk { display: inline-flex; align-items: center; gap: var(--space-2, 4px); }
  .hs-sw { width: 18px; height: 0; border-top-width: 2px; border-top-style: solid; }
  .hs-sw--conf { border-top-color: var(--calm-accent, var(--accent, #f59e0b)); }
  .hs-sw--floor { border-top-color: var(--spark-breach, #f87171); border-top-style: dashed; }
  .hs-sw--thru { border-top: 0; height: 8px; background: var(--spark-floor, rgba(148, 163, 184, 0.16)); }

  .hs-reasons {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-2, 4px);
  }
  .hs-reason {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: var(--space-3, 6px);
    padding: var(--space-2, 4px) var(--space-3, 6px);
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-sharp, 2px);
  }
  .hs-reason__swatch { width: 8px; height: 8px; border-radius: 2px; flex: 0 0 auto; background: var(--calm-ink-quiet, var(--text-dim, #948870)); }
  .hs-reason--new_pattern .hs-reason__swatch { background: #7c3aed; }
  .hs-reason--low_confidence .hs-reason__swatch { background: var(--spark-drift, #f59e0b); }
  .hs-reason--governance_variance_alert .hs-reason__swatch { background: var(--spark-breach, #f87171); }
  .hs-reason__name {
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    color: var(--calm-ink, var(--text, #b8b098));
  }
  .hs-reason__count {
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    font-weight: 700;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    font-variant-numeric: tabular-nums;
  }

  .hs-drawer__obs {
    margin: var(--space-3, 6px) 0 0;
    padding-top: var(--space-3, 6px);
    border-top: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    font-size: var(--fs-chrome, 11px);
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    line-height: var(--lh-body, 1.5);
  }

  .hs-drawer__foot {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    gap: var(--space-3, 6px);
    padding: var(--space-3, 6px) var(--space-5, 14px);
    border-top: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
    font-size: 10px;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .hs-drawer__foot-pill {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: var(--badge-ar-fg, #d97706);
    background: var(--badge-ar-bg, #fef3c7);
    border: 1px solid var(--badge-ar-border, #d97706);
    border-radius: 4px;
    padding: 1px 5px;
  }

  /* visually-hidden a11y data table */
  .hs-sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }

  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .hs,
    :global(html:not([data-motion='allow'])) .hs__spark { transition: none; }
  }
</style>
