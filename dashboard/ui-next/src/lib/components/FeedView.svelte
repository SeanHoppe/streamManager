<script context="module">
  // FeedView.svelte -- the FROZEN 8-column decision feed grid.
  //
  // BEHAVIOURAL CONTRACT (preserved 1:1 from the live dashboard feed):
  //  - 8 columns, exactly: Time | Action | Source | Layer | Agent |
  //    Confidence | Content / Reasoning | Session.
  //  - Filter bar: ALL / ALLOW / SUGGEST / GUIDE / INTERVENE / BLOCK (ALL is
  //    the default-on filter). Filtering is by the row's `action`.
  //  - MAX_ROWS = 300 ceiling on rendered rows (mirrors live feed cap).
  //  - JSONL export: GET /api/decisions/export (NDJSON), scoped to the
  //    selected session, offered as a file download. The raw body is streamed
  //    to the file untouched (no re-serialize).
  //
  // M15 (self-exclude): rows are filtered to drop the SM's own session_id
  // (defense-in-depth alongside the server strip + the store-level strip).
  // M16 (domain-agnostic): source/agent/session are derived from row DATA;
  // no monitored-project vocabulary is hard-coded. M18: post-hoc only; the
  // ONLY network call is the export GET (operator-initiated).
  //
  // The grid FORM is re-architected (calm density, hairline rows, tabular
  // numerals, severity-as-type-weight) but the column SET, order, names,
  // filters, cap, and export endpoint are frozen.

  /** Canonical filter set + order (frozen). ALL first, then action verdicts. */
  export const FEED_FILTERS = Object.freeze([
    'ALL',
    'ALLOW',
    'SUGGEST',
    'GUIDE',
    'INTERVENE',
    'BLOCK',
  ]);

  /** Frozen 8-column header set (order is contract). */
  export const FEED_COLUMNS = Object.freeze([
    'Time',
    'Action',
    'Source',
    'Layer',
    'Agent',
    'Confidence',
    'Content / Reasoning',
    'Session',
  ]);

  /** Hard render cap (mirrors the live feed MAX_ROWS). */
  export const MAX_ROWS = 300;

  /**
   * Infer the verdict SOURCE lane from a decision row. Mirrors the live feed's
   * inferSrc() exactly so the Source column reads identically. Domain-agnostic:
   * keyed on governance signals (matched_hash, reasoning phrasing, confidence
   * band), never on any governed-target name.
   * @param {Record<string, any>} row
   * @returns {'graph'|'default'|'rate-limit'|'precheck'|'cli'}
   */
  export function inferSource(row) {
    if (row.matched_hash) return 'graph';
    const r = (row.reasoning || '').toLowerCase();
    if (r.includes('default allow') || r.includes('no rules')) return 'default';
    if (r.includes('rate-limited')) return 'rate-limit';
    if (
      r.includes('meta-content') ||
      r.includes('destructive') ||
      r.includes('no-actionable') ||
      r.includes('conversational') ||
      r.includes('caveman') ||
      r.includes('thinking')
    )
      return 'precheck';
    const c = Number(row.confidence) || 0;
    if (c >= 0.9) return 'precheck';
    if (c <= 0.12) return 'default';
    return 'cli';
  }
</script>

<script>
  import { decisionsStore } from '../sse.js';
  import { getDecisionsExport } from '../api.js';
  import { selectedSessionId, getOwnSessionId, scopeParam } from '../stores/session.js';
  import { makeSelfExcludeFilter } from '../selfExclude.js';

  /** Active filter (one of FEED_FILTERS). Default ALL. */
  let activeFilter = 'ALL';

  let exporting = false;
  let exportError = '';

  // M15 self-exclude predicate, bound to the resolved own id.
  $: selfFilter = makeSelfExcludeFilter(getOwnSessionId() || '');

  // Scope by selected session (M16). null => ALL governed sessions.
  $: scopeId = $selectedSessionId;

  // Visible rows: self-excluded, session-scoped, action-filtered, capped.
  $: rows = $decisionsStore
    .filter(selfFilter)
    .filter((r) => scopeId == null || r.session_id === scopeId)
    .filter((r) => activeFilter === 'ALL' || String(r.action || '').toUpperCase() === activeFilter)
    .slice(0, MAX_ROWS);

  // Per-filter live counts for the toolbar (paired label+number; the count is
  // never the sole signal -- the button text is always present).
  $: scopedRows = $decisionsStore
    .filter(selfFilter)
    .filter((r) => scopeId == null || r.session_id === scopeId);
  $: filterCounts = (() => {
    const c = { ALL: scopedRows.length, ALLOW: 0, SUGGEST: 0, GUIDE: 0, INTERVENE: 0, BLOCK: 0 };
    for (const r of scopedRows) {
      const a = String(r.action || '').toUpperCase();
      if (a in c) c[a] += 1;
    }
    return c;
  })();

  function setFilter(f) { activeFilter = f; }

  // -- JSONL (NDJSON) export -- GET /api/decisions/export, scoped ------------
  async function exportJsonl() {
    exporting = true;
    exportError = '';
    try {
      const ndjson = await getDecisionsExport({ session_id: scopeParam() });
      const blob = new Blob([ndjson], { type: 'application/x-ndjson' });
      const url = URL.createObjectURL(blob);
      const stamp = new Date().toISOString().replace(/[:.]/g, '-');
      const scopeTag = scopeId ? `-${String(scopeId).slice(0, 8)}` : '';
      const a = document.createElement('a');
      a.href = url;
      a.download = `sm-decisions${scopeTag}-${stamp}.jsonl`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Revoke on the next tick so the download has a chance to start.
      setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (e) {
      exportError = 'Export failed -- the server may be unreachable.';
    } finally {
      exporting = false;
    }
  }

  // -- Per-row display helpers (M16: all from DATA) --------------------------
  function fmtTs(t) {
    if (!t) return '-';
    const d = new Date(Number(t) * 1000);
    if (Number.isNaN(d.getTime())) return '-';
    const pad = (n) => String(n).padStart(2, '0');
    const ms = String(d.getMilliseconds()).padStart(3, '0');
    return { hms: `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`, ms };
  }
  function clip(s, n = 96) {
    if (!s) return '';
    const c = String(s).replace(/\s+/g, ' ').trim();
    return c.length > n ? `${c.slice(0, n)}...` : c;
  }
  function agentOf(row) {
    const slug = row.profile_slug || row.agent_profile_slug || '';
    const plugin = row.attribution_plugin || '';
    return {
      label: slug || '-',
      title: plugin ? `${plugin} (${slug || 'unknown'})` : slug || 'no profile',
      unknown: !slug || slug === 'unknown',
    };
  }
  function layerOf(row) {
    const n = row.layer == null ? 0 : Number(row.layer);
    const label = `L${Number.isFinite(n) ? n : 0}`;
    const tip = n <= 1 ? 'no LLM' : row.model_used || 'no LLM';
    return { label, tip };
  }
  function confOf(row) {
    return Math.round((Number(row.confidence) || 0) * 100);
  }
</script>

<section class="feed" aria-label="Decision feed">
  <!-- FILTER + EXPORT TOOLBAR (frozen filter set + JSONL export) -->
  <div class="feed__toolbar">
    <div class="feed__filters" role="group" aria-label="Filter decisions by action">
      {#each FEED_FILTERS as f, i}
        {#if i === 1}<span class="feed__filter-sep" aria-hidden="true"></span>{/if}
        <button
          type="button"
          class="feed__fbtn"
          class:feed__fbtn--on={activeFilter === f}
          aria-pressed={activeFilter === f}
          on:click={() => setFilter(f)}
          title={`Show ${f === 'ALL' ? 'all actions' : f} (${filterCounts[f] ?? 0})`}
        >
          <span class="feed__fbtn-label">{f}</span>
          <span class="feed__fbtn-count">{filterCounts[f] ?? 0}</span>
        </button>
      {/each}
    </div>

    <button
      type="button"
      class="feed__export"
      on:click={exportJsonl}
      disabled={exporting}
      title="Export the current decisions as NDJSON (JSONL)"
      aria-label="Export decisions as JSONL"
    >{exporting ? 'Exporting...' : 'Export JSONL'}</button>
  </div>

  {#if exportError}
    <p class="feed__err" role="status">{exportError}</p>
  {/if}

  <!-- Frozen 8-col grid. role=grid/row/columnheader/gridcell so the structure
       survives the form change for assistive tech (M17). -->
  <div class="feed__grid" role="grid" aria-label="Decisions, newest first">
    <div class="feed__head feed__cols" role="row">
      {#each FEED_COLUMNS as col}
        <div class="feed__hcol" role="columnheader">{col}</div>
      {/each}
    </div>

    {#if rows.length === 0}
      <p class="feed__empty" role="status">
        No decisions{activeFilter !== 'ALL' ? ` for ${activeFilter}` : ''} in scope yet.
      </p>
    {:else}
      <div class="feed__rows">
        {#each rows as row (row.id ?? row.rid ?? `${row.message_id ?? ''}:${row.timestamp ?? ''}`)}
          {@const action = String(row.action || '?').toUpperCase()}
          {@const src = inferSource(row)}
          {@const t = fmtTs(row.timestamp)}
          {@const agent = agentOf(row)}
          {@const layer = layerOf(row)}
          {@const conf = confOf(row)}
          <div
            class="feed__row feed__cols"
            role="row"
            data-action={action}
            data-source={src}
          >
            <div class="feed__c feed__c--ts" role="gridcell">
              {#if typeof t === 'object'}
                <span class="feed__hms">{t.hms}</span><span class="feed__ms">.{t.ms}</span>
              {:else}{t}{/if}
            </div>
            <div class="feed__c feed__c--action" role="gridcell">
              <!-- M4 spirit: action is TEXT (never color-only); color is a
                   second channel on the always-present label. -->
              <span class="feed__action feed__action--{action}">{action}</span>
            </div>
            <div class="feed__c feed__c--src" role="gridcell">
              <span class="feed__src feed__src--{src}" title={`source: ${src}`}>{src}</span>
            </div>
            <div class="feed__c feed__c--layer" role="gridcell">
              <span class="feed__layer" title={layer.tip}>{layer.label}</span>
            </div>
            <div class="feed__c feed__c--agent" role="gridcell" title={agent.title}>
              <span class="feed__agent" class:feed__agent--unknown={agent.unknown}>{agent.label}</span>
            </div>
            <div class="feed__c feed__c--conf" role="gridcell" title={`${conf}% confidence`}>
              <span class="feed__conf-bar" aria-hidden="true">
                <span class="feed__conf-fill" style={`width:${conf}%`}></span>
              </span>
              <span class="feed__conf-num">{conf}%</span>
            </div>
            <div class="feed__c feed__c--content" role="gridcell">
              <p class="feed__content" title={row.content || ''}>{clip(row.content) || '-'}</p>
              {#if row.reasoning}
                <p class="feed__reason" title={row.reasoning}>{clip(row.reasoning, 72)}</p>
              {/if}
            </div>
            <div class="feed__c feed__c--sess" role="gridcell" title={row.session_id || ''}>
              {(row.session_id || '').slice(0, 8) || '-'}
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </div>
</section>

<style>
  .feed { display: flex; flex-direction: column; gap: 0.55rem; min-width: 0; }

  /* -- toolbar -- */
  .feed__toolbar {
    display: flex;
    align-items: center;
    gap: 0.85rem;
    flex-wrap: wrap;
  }
  .feed__filters { display: inline-flex; align-items: center; gap: 0.3rem; flex-wrap: wrap; }
  .feed__filter-sep {
    width: 1px; height: 1rem; background: var(--border, rgba(148, 163, 184, 0.3));
    margin: 0 0.2rem;
  }

  .feed__fbtn {
    appearance: none;
    display: inline-flex;
    align-items: baseline;
    gap: 0.35rem;
    border: 1px solid var(--border, rgba(148, 163, 184, 0.25));
    background: transparent;
    color: var(--text-dim, #94a3b8);
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.66rem;
    letter-spacing: 0.06em;
    padding: 0.2rem 0.5rem;
    border-radius: 5px;
    cursor: pointer;
    transition: color 0.16s ease, border-color 0.16s ease, background 0.16s ease;
  }
  .feed__fbtn:hover { color: var(--text, #e2e8f0); border-color: var(--text-dim, #94a3b8); }
  .feed__fbtn--on {
    color: var(--text-bright, #f8fafc);
    border-color: var(--accent, #38bdf8);
    background: var(--accent-dim, rgba(56, 189, 248, 0.1));
  }
  .feed__fbtn-label { text-transform: uppercase; }
  .feed__fbtn-count {
    font-variant-numeric: tabular-nums;
    font-size: 0.6rem;
    color: var(--text-ui, #8a8068);
    opacity: 0.85;
  }
  /* M17 focus ring */
  .feed__fbtn:focus-visible,
  .feed__export:focus-visible {
    outline: 2px solid #d97706;
    outline-offset: 2px;
  }

  .feed__export {
    appearance: none;
    margin-left: auto;
    border: 1px solid var(--border, rgba(148, 163, 184, 0.3));
    background: transparent;
    color: var(--text-dim, #94a3b8);
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.66rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    padding: 0.25rem 0.65rem;
    border-radius: 5px;
    cursor: pointer;
    transition: color 0.16s ease, border-color 0.16s ease;
  }
  .feed__export:hover:not(:disabled) { color: var(--accent, #38bdf8); border-color: var(--accent, #38bdf8); }
  .feed__export:disabled { opacity: 0.55; cursor: progress; }

  .feed__err {
    margin: 0;
    font-size: 0.72rem;
    color: var(--c-intervene, #f97316);
    border: 1px dashed var(--c-intervene, #f97316);
    border-radius: 5px;
    padding: 0.3rem 0.5rem;
  }

  /* -- frozen 8-col grid -- */
  .feed__cols {
    display: grid;
    grid-template-columns:
      86px      /* Time */
      82px      /* Action */
      72px      /* Source */
      44px      /* Layer */
      minmax(70px, 110px)  /* Agent */
      96px      /* Confidence */
      minmax(180px, 1fr)   /* Content / Reasoning */
      80px;     /* Session */
    gap: 0.65rem;
    align-items: center;
  }

  .feed__head {
    padding: 0.3rem 0.5rem;
    border-bottom: 1px solid var(--border, rgba(148, 163, 184, 0.2));
  }
  .feed__hcol {
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.6rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-ui, #8a8068);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .feed__rows { display: flex; flex-direction: column; }
  .feed__row {
    padding: 0.4rem 0.5rem;
    border-bottom: 1px solid var(--border, rgba(148, 163, 184, 0.1));
    font-size: 0.74rem;
    color: var(--text, #e2e8f0);
    transition: background 0.14s ease;
  }
  .feed__row:hover { background: var(--bg-row-hover, rgba(19, 28, 42, 0.6)); }

  .feed__c { min-width: 0; }
  .feed__c--ts {
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-variant-numeric: tabular-nums;
    color: var(--text-dim, #94a3b8);
    white-space: nowrap;
  }
  .feed__ms { color: var(--text-dim, #94a3b8); opacity: 0.6; }

  /* M4 spirit: action is TEXT + a second color channel; severity-as-weight. */
  .feed__action {
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .feed__action--ALLOW     { color: var(--c-allow, #22c55e); font-weight: 500; }
  .feed__action--SUGGEST   { color: var(--c-suggest, #84cc16); font-weight: 500; }
  .feed__action--GUIDE     { color: var(--c-guide, #eab308); font-weight: 600; }
  .feed__action--INTERVENE { color: var(--c-intervene, #f97316); font-weight: 700; }
  .feed__action--BLOCK     { color: var(--c-block, #ef4444); font-weight: 700; }

  .feed__src {
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.66rem;
    color: var(--text-dim, #94a3b8);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    display: inline-block;
    max-width: 100%;
  }
  .feed__src--graph { color: #60a5fa; }
  .feed__src--cli { color: #c084fc; }
  .feed__src--default { color: var(--text-dim, #94a3b8); }
  .feed__src--precheck { color: var(--c-suggest, #84cc16); }
  .feed__src--rate-limit { color: var(--c-guide, #eab308); }

  .feed__layer {
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.62rem;
    color: var(--text-ui, #8a8068);
    border: 1px solid var(--border, rgba(148, 163, 184, 0.25));
    border-radius: 3px;
    padding: 0.02rem 0.25rem;
  }

  .feed__agent {
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.66rem;
    color: var(--text-ui, #8a8068);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    display: inline-block;
    max-width: 100%;
  }
  .feed__agent--unknown { opacity: 0.6; font-style: italic; }

  .feed__c--conf { display: inline-flex; align-items: center; gap: 0.35rem; }
  .feed__conf-bar {
    width: 2.6rem; height: 0.28rem; border-radius: 999px;
    background: var(--border, rgba(148, 163, 184, 0.25)); overflow: hidden;
  }
  .feed__conf-fill { display: block; height: 100%; background: var(--accent, #38bdf8); }
  .feed__conf-num {
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-variant-numeric: tabular-nums;
    font-size: 0.64rem;
    color: var(--text-dim, #94a3b8);
    min-width: 2.4ch;
    text-align: right;
  }

  .feed__content { margin: 0; line-height: 1.3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .feed__reason {
    margin: 0.1rem 0 0;
    font-size: 0.66rem;
    color: var(--text-dim, #94a3b8);
    line-height: 1.25;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .feed__c--sess {
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.66rem;
    color: var(--text-dim, #94a3b8);
    white-space: nowrap;
  }

  .feed__empty {
    margin: 0.5rem 0;
    color: var(--text-dim, #94a3b8);
    font-size: 0.8rem;
    font-style: italic;
    opacity: 0.85;
  }

  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .feed__row,
    :global(html:not([data-motion='allow'])) .feed__fbtn,
    :global(html:not([data-motion='allow'])) .feed__export { transition: none; }
  }
</style>
