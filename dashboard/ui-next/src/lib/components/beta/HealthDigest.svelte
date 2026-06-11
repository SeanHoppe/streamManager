<!--
  HealthDigest.svelte -- BETA feature "health-digest" (#32).

  WHAT IT IS
    A small GLANCE WIDGET that mounts INSIDE the SessionRail header. It reads one
    server-side digest per governed NON-SM session (GET /api/sessions/health-
    digest, a single aggregated read that collapses the 4 prior per-session
    fetches into a pre-computed health verdict) and renders:
      - a header DIGEST source readout (paired label, only while the flag is ON),
      - a paired SessionHealthBadge list (QUIET / VARIANCE / ACTION N) so the
        operator sees which background session needs attention at a glance, and
      - an expandable per-session digest detail (uptime / decisions / latest
        decision / agents / jobs / hitl / latest escalation).
    It matches the operator-approved mockup (reports/proposals/mockups/health-
    digest.html): the SessionHealthBadge atom + the rich digest detail.

  BETA GATE (load-bearing)
    The ENTIRE component is wrapped in {#if $betaFlags['health-digest']}. When the
    flag is OFF it renders NOTHING and registers NO fetch / poller / SSE / timer
    -- zero runtime cost. The flag defaults OFF (lib/beta/registry.js); the
    operator flips it in Settings > BETA features. The poll loop is started ONLY
    while enabled and torn down the instant the flag flips OFF (the reactive
    block + onDestroy both clear the interval).

  DATA
    Reads GET /api/sessions/health-digest. The server aggregates per-session
    confidence / throughput / escalation / hitl counts over gov.db, polarity-
    filtered (project_slug NOT IN {streamManager} AND session_id != self). When
    the endpoint is absent or returns an empty set (fresh DB, no governed
    sessions) the widget falls back to realistic MOCK data (HealthDigest.data.js)
    so it is always inspectable; the mock state is labelled in the source line.

  ADR-18 MUST floor honoured here:
    - M2: the digest badge NEVER pulses or auto-foregrounds -- a quiet / variance
      state is badge-in-place only. The lone permitted M2 foreground stays
      reserved for the real escalation stream (owned elsewhere). This widget
      classifies NOTHING as a foreground escalation.
    - M4 (paired label+color): every health state renders its LITERAL WORD
      (QUIET / VARIANCE / ACTION N) beside any color; color is never the sole
      signal. The row aria-label carries the same verdict for screen-readers.
    - M15 / G2 (polarity): the server excludes SM-self by project_slug; the
      widget shows an explicit "self excluded" footer readout. No SM-own row is
      ever constructed here.
    - M16 (domain-agnostic): NO monitored-project vocabulary; every lane identity
      is rendered FROM DATA (project_slug).
    - M17 (a11y): each row is a real <button> (select) + a separate expand
      <button> (aria-expanded / aria-controls); the 2px amber focus ring applies;
      reduced motion honoured via the data-motion attribute.
    - M18: pure post-hoc GET on a calm cadence; never on the verdict hot path.

  ASCII-only (cp1252-safe): dash rendered as "--". No smart quotes / em-dash.
-->
<script>
  import { onDestroy, createEventDispatcher } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { getSessionsHealthDigest } from '../../api.js';
  import {
    mockDigests,
    normalizePayload,
    verdict,
    totalOpenActions,
    fmtUptime,
    ago,
    actionClass,
  } from './HealthDigest.data.js';

  const FLAG_KEY = 'health-digest';
  const dispatch = createEventDispatcher();

  /** Poll cadence: calm glance data, not a hot-path signal. */
  const REFRESH_MS = 5000;

  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // ---- data state -----------------------------------------------------------
  let loaded = false;
  let usedMockData = false;
  let now = Math.floor(Date.now() / 1000);
  /** @type {import('./HealthDigest.data.js').Digest[]} */
  let sessions = [];
  let excludedSelf = 0;
  /** the currently expanded session_id (accordion), or null. */
  let openId = null;

  $: totalOpen = totalOpenActions(sessions);

  /**
   * Load the digest once. Best-effort: any failure or empty result degrades to
   * the realistic mock fallback so the widget is always inspectable. Never
   * throws to the render path.
   */
  async function load() {
    let payload = null;
    try {
      payload = await getSessionsHealthDigest();
    } catch {
      payload = null;
    }
    const norm = normalizePayload(payload);
    if (norm) {
      sessions = norm.sessions;
      now = norm.now;
      excludedSelf = norm.excluded_self;
      usedMockData = false;
    } else {
      const m = mockDigests();
      sessions = m.sessions;
      now = m.now;
      excludedSelf = m.excluded_self;
      usedMockData = true;
    }
    loaded = true;
  }

  // ---- poll lifecycle, gated strictly on `enabled` --------------------------
  // The interval exists ONLY while the flag is ON. Flipping OFF clears it and
  // resets state so nothing lingers (no-op gate). This reactive block is the
  // single owner of the timer; onDestroy is the backstop.
  /** @type {ReturnType<typeof setInterval>|null} */
  let _timer = null;
  function startPolling() {
    if (_timer || typeof setInterval === 'undefined') return;
    load();
    _timer = setInterval(load, REFRESH_MS);
  }
  function stopPolling() {
    if (_timer) {
      clearInterval(_timer);
      _timer = null;
    }
  }
  $: if (enabled) startPolling();
  else {
    stopPolling();
    // reset so a re-enable re-fetches fresh, and OFF holds zero state
    loaded = false;
    sessions = [];
    openId = null;
  }

  onDestroy(stopPolling);

  // ---- interactions ---------------------------------------------------------
  function toggleExpand(id) {
    openId = openId === id ? null : id;
  }
  function selectSession(id) {
    // The real rail owns selection; the widget surfaces an intent the parent
    // can route. Emitting is side-effect-free if no parent listens.
    dispatch('select', { id });
  }
  function onRowKey(e, id) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      selectSession(id);
    }
  }

  function rowAria(d, v) {
    const parts = [`Session ${d.project_slug}`, 'live', v.aria];
    return parts.join(', ');
  }
</script>

{#if enabled}
  <!-- The widget is a self-contained block inside the rail header. Present only
       while the flag is ON (the {#if enabled} guard). -->
  <section class="hd" aria-label="Session health digest">
    <!-- DIGEST source readout: a paired label so the operator knows the richer
         server-side source is live. Calm slate; never a bare icon. -->
    <div class="hd__head">
      <span class="hd__tag" title="Health digest source live (server-side glance)">
        <span class="hd__tag-dot" aria-hidden="true"></span>DIGEST
      </span>
      <span class="hd__beta">BETA</span>
      <span
        class="hd__tally"
        class:hd__tally--active={totalOpen > 0}
        aria-label={totalOpen > 0
          ? `${totalOpen} open action${totalOpen === 1 ? '' : 's'} across governed sessions`
          : 'No open actions across governed sessions'}
      >
        <span class="hd__tally-tag">ACTIVE</span>
        <span class="hd__tally-num tabular">{totalOpen}</span>
      </span>
    </div>

    <!-- data-source line: ALWAYS a literal text label (mock vs live) -->
    <p class="hd__source" data-mock={usedMockData}>
      {usedMockData
        ? 'SAMPLE DATA -- no governed-session digests in gov.db yet; showing a representative shape.'
        : 'LIVE -- aggregated from gov.db (polarity-filtered, SM-self excluded).'}
    </p>

    {#if !loaded}
      <p class="hd__loading">Loading digest...</p>
    {:else if sessions.length === 0}
      <p class="hd__empty">
        No governed sessions to summarize. Digests appear as non-SM sessions are
        observed.
      </p>
    {:else}
      <div class="hd__list" role="list">
        {#each sessions as d (d.session_id)}
          {@const v = verdict(d)}
          {@const isOpen = openId === d.session_id}
          <div
            class="hd-lane hd-lane--{v.state}"
            class:is-open={isOpen}
            role="listitem"
            data-session-id={d.session_id}
            data-health-state={v.state}
          >
            <button
              type="button"
              class="hd-lane__main"
              aria-label={rowAria(d, v)}
              on:click={() => selectSession(d.session_id)}
              on:keydown={(e) => onRowKey(e, d.session_id)}
            >
              <span class="hd-lane__pip" aria-hidden="true"></span>
              <span class="hd-lane__id">
                <span class="hd-lane__name" title={d.project_slug}>{d.project_slug}</span>
                <span class="hd-lane__meta tabular">live <span class="hd-sep" aria-hidden="true">&middot;</span> {d.decision_count} dec <span class="hd-sep" aria-hidden="true">&middot;</span> {d.hitl_mode}</span>
              </span>
              <!-- SessionHealthBadge: aria-hidden (the row aria-label carries
                   the verdict). The WORD is always present; color is second. -->
              <span class="hd-badge hd-badge--{v.state}" aria-hidden="true" title={v.aria}>
                <span class="hd-badge__dot" aria-hidden="true"></span>{v.word}
              </span>
            </button>

            <button
              type="button"
              class="hd-lane__expand"
              aria-expanded={isOpen}
              aria-controls={`hd-detail-${d.session_id}`}
              aria-label={isOpen
                ? `Hide digest detail for ${d.project_slug}`
                : `Show digest detail for ${d.project_slug}`}
              on:click={() => toggleExpand(d.session_id)}
            >
              <span class="hd-chev" class:hd-chev--open={isOpen} aria-hidden="true">&rsaquo;</span>
            </button>

            {#if isOpen}
              <div
                class="hd-detail"
                id={`hd-detail-${d.session_id}`}
                role="region"
                aria-label={`${d.project_slug} digest detail`}
              >
                <dl class="hd-dl">
                  <div class="hd-dl__row"><dt>uptime</dt><dd class="tabular">{fmtUptime(d.uptime_seconds)}</dd></div>
                  <div class="hd-dl__row"><dt>decisions</dt><dd class="tabular"><b>{d.decision_count}</b></dd></div>
                  <div class="hd-dl__row">
                    <dt>latest decision</dt>
                    <dd class="tabular">
                      {#if d.latest_decision}
                        <span class="hd-act hd-act--{actionClass(d.latest_decision.action)}">
                          <span class="hd-act__dot" aria-hidden="true"></span>{d.latest_decision.action}
                        </span>
                        conf {d.latest_decision.confidence.toFixed(2)}
                        <span class="hd-sep" aria-hidden="true">&middot;</span> {d.latest_decision.agent_id}
                        <span class="hd-sep" aria-hidden="true">&middot;</span> {ago(d.latest_decision.timestamp, now)}
                      {:else}
                        none yet
                      {/if}
                    </dd>
                  </div>
                  <div class="hd-dl__row"><dt>active agents</dt><dd class="tabular">{d.active_agent_count}</dd></div>
                  <div class="hd-dl__row"><dt>active jobs</dt><dd class="tabular">{d.active_job_count}</dd></div>
                  <div class="hd-dl__row"><dt>hitl pending</dt><dd class="tabular">{d.hitl_pending_count} <span class="hd-sep" aria-hidden="true">&middot;</span> mode {d.hitl_mode}</dd></div>
                  <div class="hd-dl__row">
                    <dt>latest escalation</dt>
                    <dd class="tabular">
                      {#if d.latest_escalation}
                        {d.latest_escalation.type} ({d.latest_escalation.severity}, {ago(d.latest_escalation.timestamp, now)})
                      {:else}
                        none
                      {/if}
                    </dd>
                  </div>
                </dl>
              </div>
            {/if}
          </div>
        {/each}
      </div>

      <!-- M15 polarity readout: the self-exclude, on-screen + auditable. -->
      <footer class="hd__foot">
        <span class="hd__self-dot" aria-hidden="true"></span>
        {excludedSelf} self row{excludedSelf === 1 ? '' : 's'} excluded (polarity filter)
      </footer>
    {/if}
  </section>
{/if}

<style>
  .hd {
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 6px);
    width: 100%;
    min-width: 0;
    padding: var(--space-3, 6px) 0 0;
    font-family: var(--ff-system);
  }

  /* ---- header: DIGEST tag + BETA + ACTIVE tally --------------------------- */
  .hd__head {
    display: flex;
    align-items: center;
    gap: var(--space-3, 6px);
    flex-wrap: wrap;
  }
  .hd__tag {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.13em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    padding: 2px 7px;
    border-radius: 999px;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
  }
  .hd__tag-dot {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--badge-decided-fg, #16a34a);
    opacity: 0.85;
  }
  .hd__beta {
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
  .hd__tally {
    margin-left: auto;
    display: inline-flex;
    align-items: baseline;
    gap: 5px;
    padding: 2px 7px;
    border-radius: 999px;
    border: var(--hairline, 1px) solid transparent;
    background: var(--calm-accent-wash, rgba(245, 158, 11, 0.09));
  }
  .hd__tally--active {
    background: var(--badge-ar-bg, #fef3c7);
    border-color: var(--badge-ar-border, #d97706);
  }
  .hd__tally-tag {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.13em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .hd__tally--active .hd__tally-tag,
  .hd__tally--active .hd__tally-num { color: #92400e; }
  .hd__tally-num {
    font-size: 13px;
    font-weight: 560;
    line-height: 1;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .hd__tally--active .hd__tally-num { font-weight: 720; }

  .hd__source {
    margin: 0;
    font-size: var(--fs-chrome, 11px);
    font-family: var(--font-d, var(--ff-mono));
    letter-spacing: 0.02em;
    line-height: var(--lh-body, 1.5);
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  /* mock source uses the WARN ink (paired text already says SAMPLE DATA). */
  .hd__source[data-mock='true'] { color: var(--badge-warn-fg, #ea580c); }
  /* PAPER surface (--bg-card #f8f4ee) is too light for #ea580c at AA; darken the
     WARN ink to #9a3412 on paper only. Dark themes keep the AA base. */
  :global([data-theme='paper']) .hd__source[data-mock='true'] { color: #9a3412; }

  .hd__loading,
  .hd__empty {
    margin: 0;
    padding: var(--space-3, 6px) 0;
    font-size: var(--fs-chrome, 11px);
    font-style: italic;
    line-height: var(--lh-body, 1.5);
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }

  /* ---- the lane list ------------------------------------------------------ */
  .hd__list {
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 6px);
  }

  .hd-lane {
    position: relative;
    display: grid;
    grid-template-columns: 1fr auto;
    grid-template-rows: auto auto;
    background: var(--calm-lane-bg, var(--bg-card, #0c1118));
    border: var(--hairline, 1px) solid var(--calm-lane-edge, var(--border, #192030));
    border-left-width: 2px;
    border-left-color: transparent;
    border-radius: var(--radius-soft, 4px);
    transition: border-color var(--t-calm, 180ms ease), background var(--t-calm, 180ms ease);
  }
  /* RED ACTION lane: hitl_pending_count > 0. Left gutter warms to BLOCKED red as
     the SECOND channel; the ACTION chip text + row aria-label carry the verdict. */
  .hd-lane--action { border-left-color: var(--badge-blocked-border, #dc2626); }
  /* AMBER VARIANCE lane: governance_variance_alert. Left gutter warms to the
     ACTION-REQUIRED amber. Badge-in-place; NEVER pulses / foregrounds. */
  .hd-lane--variance { border-left-color: var(--badge-ar-border, #d97706); }

  .hd-lane__main {
    grid-column: 1;
    grid-row: 1;
    display: flex;
    align-items: center;
    gap: var(--space-3, 8px);
    min-width: 0;
    padding: 7px var(--space-4, 10px);
    cursor: pointer;
    text-align: left;
    background: transparent;
    border: 0;
    width: 100%;
    color: inherit;
    font: inherit;
    border-radius: var(--radius-soft, 4px) 0 0 var(--radius-soft, 4px);
  }
  .hd-lane__main:hover { background: var(--calm-surface-hover, var(--bg-row-hover, #131c2a)); }
  .hd-lane__main:focus-visible,
  .hd-lane__expand:focus-visible {
    outline: 2px solid var(--badge-ar-border, #d97706);
    outline-offset: 2px;
    border-radius: var(--radius-soft, 4px);
  }

  .hd-lane__pip {
    flex: 0 0 auto;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--calm-accent, var(--accent, #f59e0b));
    opacity: 0.85;
  }

  .hd-lane__id {
    display: flex;
    flex-direction: column;
    gap: 1px;
    min-width: 0;
    flex: 1 1 auto;
  }
  .hd-lane__name {
    font-size: var(--fs-meta, 13px);
    font-weight: 460;
    letter-spacing: 0.01em;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    line-height: var(--lh-tight, 1.25);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .hd-lane--action .hd-lane__name,
  .hd-lane--variance .hd-lane__name { font-weight: 600; }
  .hd-lane__meta {
    display: block;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: var(--fs-chrome, 11px);
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .hd-sep { opacity: 0.5; }

  /* ---- SessionHealthBadge: paired word-chip on its own light bg ----------- */
  .hd-badge {
    flex: 0 0 auto;
    align-self: center;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    letter-spacing: 0.04em;
    line-height: 1.4;
    padding: 1px 8px;
    border-radius: 999px;
    white-space: nowrap;
    display: inline-flex;
    align-items: center;
    gap: 5px;
  }
  .hd-badge__dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex: 0 0 auto; }
  .hd-badge--quiet {
    color: #15803d;
    background: var(--badge-decided-bg, #dcfce7);
    border: 1px solid var(--badge-decided-border, #86efac);
  }
  .hd-badge--variance {
    color: #92400e;
    background: var(--badge-ar-bg, #fef3c7);
    border: 1px solid var(--badge-ar-border, #d97706);
  }
  .hd-badge--action {
    color: #b91c1c;
    background: var(--badge-blocked-bg, #fee2e2);
    border: 2px solid var(--badge-blocked-border, #dc2626);
    font-weight: 800;
  }

  /* ---- expand control ----------------------------------------------------- */
  .hd-lane__expand {
    grid-column: 2;
    grid-row: 1;
    align-self: stretch;
    appearance: none;
    background: transparent;
    border: none;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    width: 1.45rem;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: color var(--t-calm, 180ms ease), background var(--t-calm, 180ms ease);
  }
  .hd-lane__expand:hover {
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    background: var(--calm-surface-hover, var(--bg-row-hover, #131c2a));
  }
  .hd-chev { display: inline-block; font-size: 1rem; line-height: 1; transition: transform var(--t-calm, 180ms ease); }
  .hd-chev--open { transform: rotate(90deg); }

  /* ---- digest detail ------------------------------------------------------ */
  .hd-detail {
    grid-column: 1 / -1;
    grid-row: 2;
    padding: 8px var(--space-4, 10px) 10px;
    border-top: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
    border-radius: 0 0 var(--radius-soft, 4px) var(--radius-soft, 4px);
  }
  .hd-dl { margin: 0; }
  .hd-dl__row {
    display: grid;
    grid-template-columns: 8.5rem 1fr;
    gap: var(--space-4, 10px);
    padding: 2px 0;
  }
  .hd-dl__row dt {
    margin: 0;
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .hd-dl__row dd {
    margin: 0;
    min-width: 0;
    font-size: var(--fs-chrome, 11px);
    color: var(--calm-ink, var(--text, #b8b098));
    word-break: break-word;
  }
  .hd-dl__row dd b { color: var(--calm-ink-loud, var(--text-bright, #e8e0cc)); font-weight: 700; }

  /* latest-decision action chip -- paired text + color */
  .hd-act {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.04em;
    padding: 0 6px;
    border-radius: 3px;
    line-height: 1.5;
  }
  .hd-act__dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }
  .hd-act--allow {
    color: var(--badge-decided-fg, #16a34a);
    background: var(--badge-decided-bg, #dcfce7);
    border: 1px solid var(--badge-decided-border, #86efac);
  }
  .hd-act--block,
  .hd-act--l4 {
    color: var(--badge-blocked-fg, #dc2626);
    background: var(--badge-blocked-bg, #fee2e2);
    border: 1px solid var(--badge-blocked-border, #dc2626);
  }
  .hd-act--l2,
  .hd-act--l3 {
    color: var(--badge-ar-fg, #d97706);
    background: var(--badge-ar-bg, #fef3c7);
    border: 1px solid var(--badge-ar-border, #d97706);
  }

  /* ---- footer: self-exclude readout --------------------------------------- */
  .hd__foot {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: var(--space-2, 4px) 0 0;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .hd__self-dot {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--calm-ink-quiet, var(--text-dim, #948870));
    opacity: 0.7;
  }

  .tabular { font-variant-numeric: tabular-nums; font-family: var(--font-d, var(--ff-mono)); }

  /* M17 reduced motion: suppress the chevron + lane transitions. */
  :global(html[data-motion='reduce']) .hd-chev,
  :global(html[data-motion='reduce']) .hd-lane,
  :global(html[data-motion='reduce']) .hd-lane__main,
  :global(html[data-motion='reduce']) .hd-lane__expand { transition: none; }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .hd-chev,
    :global(html:not([data-motion='allow'])) .hd-lane,
    :global(html:not([data-motion='allow'])) .hd-lane__main,
    :global(html:not([data-motion='allow'])) .hd-lane__expand { transition: none; }
  }
</style>
