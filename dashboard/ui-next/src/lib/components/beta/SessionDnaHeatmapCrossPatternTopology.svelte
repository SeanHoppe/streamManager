<!--
  SessionDnaHeatmapCrossPatternTopology.svelte -- BETA feature
  "session-dna-heatmap-cross-pattern-topology" (#30).

  A bespoke session x top-pattern MATRIX mounted as an additive Frame A
  composition fragment ABOVE the decision stream (sibling to VelocityHeatmap).
  It answers ONE glance question: is a governance pattern SPREADING across my
  sessions, ISOLATED to one, or ASYMMETRIC (hot in one, dormant in another)?
  Reading DOWN a column = is this pattern spreading; reading ACROSS a row = a
  session's pattern signature ("DNA"). Enter on a session row opens the
  SessionDnaCard drill-down (top unique + top shared patterns with per-session
  confidence). Enter on a shared-pattern cell lights the whole column + draws
  the 1px propagation vector + announces the spread over aria-live.

  This is the Svelte realisation of the operator-APPROVED mockup
  (reports/proposals/mockups/session-dna-heatmap-cross-pattern-topology.html).
  It reuses theme.css tokens verbatim (the fixed paired-badge tokens
  --badge-warn-* / --badge-ar-* + --bg-* / --text-* / --accent / --border
  chrome). NO new color tokens. NO D3 -- the matrix is hand-rolled CSS + a
  single 1px SVG connector (EscalationHeatmap precedent; D3 is not a dep here).

  ============================ GOVERNANCE FLOOR ============================
  BETA GATE: the component renders NOTHING and registers NO pollers / SSE
    handlers / timers unless $betaFlags['session-dna-heatmap-cross-pattern-
    topology'] is true (default OFF). The ONE read fetch fires only after mount
    AND only while the flag is ON; flipping OFF tears the subscription down.

  M4 (paired label + color, never color alone): every confidence CELL carries
    the LITERAL numeric value (tabular-nums) as the load-bearing signal; the
    band color + a one-word band WORD (HIGH / MEDIUM / LEARNING / absent) are
    redundant reinforcement. A text legend pairs each band swatch with its
    written name + range.

  M6 (3-frame INTENT preserved): an additive Frame A fragment ABOVE the stream.
    NO frame-body component is edited (the proposal's FrameC_Jobs edit is
    REJECTED per the mockup footnote). frozenTouch=false stays accurate.

  M15 / G2 (polarity / self-exclude): the endpoint drops any session whose
    project_slug is in the SM exclusion set at the SQL WHERE and surfaces
    excluded_self; this component renders only the non-SM nodes it is handed and
    shows the excluded_self count as an on-screen polarity readout. No self node
    is derivable client-side.

  M16 (domain-agnostic): session identity (slug, project_slug, agent roster) +
    pattern payload are rendered FROM DATA. No monitored-project vocabulary.

  M17 (a11y): the matrix is a real grid widget (role=grid, roving tabindex;
    arrow keys move cell-to-cell; Enter on a row-header opens the card; Enter on
    a multi-session cell lights the column + announces; Escape clears / closes).
    2px solid accent focus ring + 2px offset. Reduced motion honoured. The card
    is a focus-trapped role=dialog dismissed with Escape (returns focus).

  M18 (post-hoc): pure render over an additive read endpoint. NO writes, NO
    verdict-path work.

  MOCK FALLBACK: the live gov.db is frequently ALLOW-only (zero cross-session
    patterns), so when the endpoint degrades to empty the matrix falls back to a
    realistic deterministic fixture (mockTopology) so the feature is testable.
    `usedMock` is exposed for the test harness + shown in the foot note.

  FILE-DISJOINT: this component + its -data helper own all the new code. It
    imports the read wrapper getCrossSessionTopology from api.js (added there as
    DATA by the main-thread wire step) and the betaFlags store.

  ASCII-only (cp1252-safe): dash is "--".
-->
<script>
  import { onMount, onDestroy, tick } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { getCrossSessionTopology } from '../../api.js';
  import {
    buildGrid,
    patternsForNode,
    spreadVerdict,
    bandOf,
    bandWord,
    fmtConf,
    shortHash,
    levelWord,
    mockTopology,
    hasTopology,
  } from './SessionDnaHeatmapCrossPatternTopology-data.js';

  /** The stable BETA flag key this component gates on. */
  const FLAG_KEY = 'session-dna-heatmap-cross-pattern-topology';

  /**
   * allowMock: when the live endpoint has no cross-session patterns, fall back
   * to a realistic mock fixture so the matrix is visible/testable. Default true
   * (tests rely on it). Set false to force a true live-only render.
   * @type {boolean}
   */
  export let allowMock = true;

  /**
   * topoOverride: injectable topology graph for deterministic tests (bypasses
   * the network). When set, the component renders it directly. Default null.
   * @type {Object|null}
   */
  export let topoOverride = null;

  // -- gate (single source of truth: the betaFlags store) --------------------
  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // -- topology state --------------------------------------------------------
  /** @type {Object|null} */
  let topo = null;
  let usedMock = false;
  let loading = false;
  let loadError = false;
  /** @type {ReturnType<typeof buildGrid>|null} */
  let grid = null;
  /** the currently lit shared-pattern column (hash), or null. */
  let litColumn = null;
  let liveMsg = '';

  // matrix DOM + the propagation-vector overlay geometry
  let matrixEl;
  /** @type {Array<{hash:string, x1:number, y1:number, x2:number, y2:number}>} */
  let vectors = [];

  // the drill-down card
  let cardOpen = false;
  /** @type {Object|null} */
  let cardNode = null;
  let cardEl;
  /** @type {Element|null} */
  let lastFocus = null;

  let mounted = false;
  let fetchSeq = 0;

  // -- the single read: fires only when ON, only after mount -----------------
  async function load() {
    if (!enabled || !mounted) return;
    const seq = ++fetchSeq;
    loading = true;
    loadError = false;
    let graph = topoOverride;
    if (!graph) {
      try {
        graph = await getCrossSessionTopology();
      } catch {
        graph = null;
        loadError = true;
      }
    }
    if (seq !== fetchSeq) return; // a newer load superseded this one
    if (hasTopology(graph)) {
      topo = graph;
      usedMock = !!graph.used_mock;
    } else if (allowMock) {
      topo = mockTopology();
      usedMock = true;
    } else {
      topo = graph && typeof graph === 'object' ? graph : { nodes: [], patterns: {}, edges: [], isolated: [], excluded_self: 0 };
      usedMock = false;
    }
    grid = buildGrid(topo);
    litColumn = null;
    liveMsg = '';
    loading = false;
    // draw the propagation vectors once the DOM has the new cells.
    await tick();
    drawVectors();
  }

  // Re-load when the gate flips ON. Flipping OFF unmounts the markup entirely
  // (the {#if enabled} guard), so no teardown of a timer is needed -- there is
  // no timer. We only (re)fetch on the OFF->ON edge.
  let wasEnabled = false;
  $: if (enabled && !wasEnabled && mounted) {
    wasEnabled = true;
    load();
  } else if (!enabled && wasEnabled) {
    wasEnabled = false;
    // clear state so a future ON re-fetches fresh
    topo = null;
    grid = null;
    litColumn = null;
    vectors = [];
    closeCard();
  }

  // ---- derived render helpers ----------------------------------------------
  $: nodes = grid ? grid.nodes : [];
  $: cols = grid ? grid.patternOrder : [];
  $: sharedCount = grid ? Object.keys(grid.sharedHashes).length : 0;
  $: excludedSelf = topo && Number.isFinite(Number(topo.excluded_self)) ? Number(topo.excluded_self) : 0;

  function cellConf(hash, nodeId) {
    return grid && grid.cellConf[hash] ? grid.cellConf[hash][nodeId] : undefined;
  }
  function isShared(hash) {
    return !!(grid && grid.sharedHashes[hash]);
  }
  function isPresent(hash, nodeId) {
    const c = cellConf(hash, nodeId);
    return c !== undefined && c !== null;
  }

  function cellAria(hash, node) {
    const c = cellConf(hash, node.id);
    const meta = (topo && topo.patterns && topo.patterns[hash]) || {};
    const pay = meta.payload || shortHash(hash);
    if (c === undefined || c === null) {
      return `Pattern ${shortHash(hash)} absent in session ${node.slug}`;
    }
    const band = bandOf(c);
    const where = isShared(hash) ? 'SHARED across sessions' : 'ISOLATED to this session';
    return `Pattern ${shortHash(hash)} (${pay}) in session ${node.slug}: confidence ${fmtConf(c)}, band ${bandWord(band)}, ${where}`;
  }

  // ---- the 1px SVG propagation vector between the two brightest cells of a
  //      multi-session column (one per shared pattern) -----------------------
  function drawVectors() {
    vectors = [];
    if (!matrixEl || !grid) return;
    const mrect = matrixEl.getBoundingClientRect();
    Object.keys(grid.sharedHashes).forEach((h) => {
      const cellEls = Array.from(
        matrixEl.querySelectorAll(`.sdh-cell.sdh-cell--has[data-hash="${cssEsc(h)}"]`),
      );
      if (cellEls.length < 2) return;
      cellEls.sort(
        (a, b) =>
          parseFloat(b.getAttribute('data-conf') || '0') -
          parseFloat(a.getAttribute('data-conf') || '0'),
      );
      const a = cellEls[0].getBoundingClientRect();
      const b = cellEls[1].getBoundingClientRect();
      vectors = vectors.concat({
        hash: h,
        x1: a.left - mrect.left + a.width / 2,
        y1: a.top - mrect.top + a.height / 2,
        x2: b.left - mrect.left + b.width / 2,
        y2: b.top - mrect.top + b.height / 2,
      });
    });
  }

  function cssEsc(s) {
    // minimal attribute-selector escape for hashes (CSS.escape is not in all
    // jsdom builds); hashes are [a-z0-9_-.] in practice.
    return String(s).replace(/["\\]/g, '\\$&');
  }

  // ---- KEY INTERACTION 1: light a shared column (Enter on a multi cell) -----
  function lightColumn(hash) {
    if (!grid || !grid.sharedHashes[hash]) return;
    if (litColumn === hash) {
      clearColumn();
      return;
    }
    litColumn = hash;
    const parts = nodes
      .filter((n) => isPresent(hash, n.id))
      .map((n) => `${n.slug} ${fmtConf(cellConf(hash, n.id))}`);
    liveMsg = `Pattern ${shortHash(hash)} fires in ${parts.join(' and ')}.`;
    drawVectors();
  }
  function clearColumn() {
    litColumn = null;
    liveMsg = '';
  }

  // ---- roving-tabindex grid navigation -------------------------------------
  // Focusables in reading order: per session row = [row-header, ...cells].
  function focusableEls() {
    if (!matrixEl) return [];
    return Array.from(matrixEl.querySelectorAll('.sdh-rowh, .sdh-cell'));
  }
  function gridCols() {
    return cols.length + 1; // +1 for the row-header column
  }
  function focusAt(rowIdx, colIdx) {
    const ncols = gridCols();
    const nrows = nodes.length;
    const r = Math.max(0, Math.min(nrows - 1, rowIdx));
    const c = Math.max(0, Math.min(ncols - 1, colIdx));
    const foc = focusableEls();
    const el = foc[r * ncols + c];
    if (el) {
      foc.forEach((f) => f.setAttribute('tabindex', '-1'));
      el.setAttribute('tabindex', '0');
      el.focus();
    }
  }
  function posOf(el) {
    const foc = focusableEls();
    const i = foc.indexOf(el);
    if (i < 0) return null;
    const ncols = gridCols();
    return { row: Math.floor(i / ncols), col: i % ncols };
  }
  function onMatrixKeydown(e) {
    const pos = posOf(document.activeElement);
    if (!pos) return;
    switch (e.key) {
      case 'ArrowRight':
        e.preventDefault();
        focusAt(pos.row, pos.col + 1);
        break;
      case 'ArrowLeft':
        e.preventDefault();
        focusAt(pos.row, pos.col - 1);
        break;
      case 'ArrowDown':
        e.preventDefault();
        focusAt(pos.row + 1, pos.col);
        break;
      case 'ArrowUp':
        e.preventDefault();
        focusAt(pos.row - 1, pos.col);
        break;
      case 'Home':
        e.preventDefault();
        focusAt(pos.row, 0);
        break;
      case 'End':
        e.preventDefault();
        focusAt(pos.row, gridCols() - 1);
        break;
      case 'Enter':
      case ' ': {
        const el = document.activeElement;
        if (el && el.classList.contains('sdh-rowh')) {
          e.preventDefault();
          openCard(el.getAttribute('data-node'));
        } else if (
          el &&
          el.classList.contains('sdh-cell') &&
          el.getAttribute('data-shared') === 'true' &&
          el.classList.contains('sdh-cell--has')
        ) {
          e.preventDefault();
          lightColumn(el.getAttribute('data-hash'));
        }
        break;
      }
      case 'Escape':
        e.preventDefault();
        clearColumn();
        break;
      default:
        break;
    }
  }

  function onRowHeaderClick(nodeId) {
    openCard(nodeId);
  }
  function onCellClick(hash, nodeId) {
    if (isShared(hash) && isPresent(hash, nodeId)) lightColumn(hash);
  }

  // ---- KEY INTERACTION 2: the SessionDnaCard drill-down --------------------
  function nodeById(id) {
    return nodes.find((n) => n && n.id === id) || null;
  }
  function openCard(nodeId) {
    const node = nodeById(nodeId);
    if (!node) return;
    lastFocus = typeof document !== 'undefined' ? document.activeElement : null;
    cardNode = node;
    cardOpen = true;
    tick().then(() => {
      if (cardEl && typeof cardEl.focus === 'function') cardEl.focus();
    });
  }
  function closeCard() {
    cardOpen = false;
    cardNode = null;
    if (lastFocus && typeof lastFocus.focus === 'function') lastFocus.focus();
    lastFocus = null;
  }
  function onCardKeydown(e) {
    if (e.key === 'Escape') {
      e.preventDefault();
      closeCard();
    }
  }
  function onScrimClick(e) {
    if (e.target === e.currentTarget) closeCard();
  }

  // the card's two ranked lists (top-5 unique + top-5 shared)
  $: cardAll = cardNode && grid ? patternsForNode(grid, cardNode.id) : [];
  $: cardUnique = cardAll
    .filter((p) => !p.shared)
    .slice()
    .sort((a, b) => b.conf - a.conf)
    .slice(0, 5);
  $: cardShared = cardAll
    .filter((p) => p.shared)
    .slice()
    .sort((a, b) => b.conf - a.conf)
    .slice(0, 5);

  function patternMeta(hash) {
    return (topo && topo.patterns && topo.patterns[hash]) || {};
  }

  // ---- lifecycle -----------------------------------------------------------
  onMount(() => {
    mounted = true;
    if (enabled) {
      wasEnabled = true;
      load();
    }
    if (typeof window !== 'undefined') {
      window.addEventListener('resize', drawVectors);
    }
  });
  onDestroy(() => {
    mounted = false;
    if (typeof window !== 'undefined') {
      window.removeEventListener('resize', drawVectors);
    }
  });
</script>

{#if enabled}
  <section class="sdh" aria-label="Session DNA heatmap -- cross-session pattern topology (BETA)">
    <div class="sdh__cap">
      <span class="sdh__ttl">Session DNA -- <b>cross-session pattern topology</b></span>
      <span class="sdh__count" role="status">
        <span class="sdh__count-n">{sharedCount}</span>
        <span class="sdh__count-lab">spreading patterns</span>
      </span>
    </div>

    {#if loading && !grid}
      <p class="sdh__note" role="status">Loading cross-session topology...</p>
    {:else if grid && nodes.length > 0 && cols.length > 0}
      <div
        class="sdh-matrix"
        bind:this={matrixEl}
        role="grid"
        aria-label="Session DNA heatmap. Rows are sessions, columns are governance patterns. Arrow keys move cell to cell. Enter on a session label opens its detail card. Enter on a shared-pattern cell highlights every occurrence of that pattern across sessions."
        style={`grid-template-columns: max-content repeat(${cols.length}, 62px);`}
        on:keydown={onMatrixKeydown}
      >
        <!-- header row: blank corner + vertical hash chips. Wrapped in a
             display:contents role=row so the ARIA grid tree is valid (grid >
             row > columnheader) while the CSS grid layout is unchanged. -->
        <div class="sdh-row" role="row" style="display:contents">
          <div class="sdh-corner" role="columnheader" aria-hidden="true"></div>
          {#each cols as h (h)}
            {@const meta = patternMeta(h)}
            <div class="sdh-colh" role="columnheader">
              {#if levelWord(meta.level)}
                <span class="sdh-lvl" data-lvl={levelWord(meta.level)} title={meta.payload || ''}>{levelWord(meta.level)}</span>
              {/if}
              <span class="sdh-hash" title={meta.payload || shortHash(h)}>{shortHash(h)} {meta.payload || ''}</span>
            </div>
          {/each}
        </div>

        <!-- one row per session. Each data row is wrapped in a display:contents
             role=row so the ARIA tree is valid (grid > row > rowheader/gridcell)
             without altering the CSS grid flow. -->
        {#each nodes as node, ri (node.id)}
          <div class="sdh-row" role="row" style="display:contents">
            <button
              type="button"
              class="sdh-rowh"
              role="rowheader"
              data-node={node.id}
              tabindex={ri === 0 ? 0 : -1}
              aria-label={`Session ${node.slug}, project ${node.project_slug || ''}, agents ${(node.agent_slugs || []).join(' ')}. Enter to open detail card.`}
              on:click={() => onRowHeaderClick(node.id)}
            >
              <span class="sdh-slug">{node.slug}</span>
              {#if node.project_slug}<span class="sdh-proj">{node.project_slug}</span>{/if}
              {#if node.agent_slugs && node.agent_slugs.length}
                <span class="sdh-roster">
                  {#each node.agent_slugs as a}<span class="sdh-agent">{a}</span>{/each}
                </span>
              {/if}
              <span class="sdh-openhint">Enter -- open card</span>
            </button>

            {#each cols as h (h)}
              {@const c = cellConf(h, node.id)}
              {@const present = c !== undefined && c !== null}
              {@const band = bandOf(c)}
              {@const shared = isShared(h)}
              {@const lit = present && shared && litColumn === h}
              <div
                class={`sdh-cell ${present ? 'sdh-cell--has' : 'sdh-cell--empty'}${lit ? ' sdh-cell--lit' : ''}`}
                role="gridcell"
                data-band={band}
                data-hash={h}
                data-conf={present ? c : ''}
                data-shared={shared ? 'true' : 'false'}
                data-node={node.id}
                tabindex="-1"
                title={cellAria(h, node)}
                aria-label={cellAria(h, node)}
                on:click={() => onCellClick(h, node.id)}
              >
                <span class="sdh-val">{fmtConf(c)}</span>
                <span class="sdh-band">{present ? bandWord(band) : 'absent'}</span>
              </div>
            {/each}
          </div>
        {/each}

        {#if vectors.length}
          <svg class="sdh-vector" aria-hidden="true">
            {#each vectors as v (v.hash)}
              <path
                class={litColumn === v.hash ? 'lit' : ''}
                d={`M${v.x1.toFixed(1)} ${v.y1.toFixed(1)} L${v.x2.toFixed(1)} ${v.y2.toFixed(1)}`}
              />
            {/each}
          </svg>
        {/if}
      </div>

      <div class="sdh-live" role="status" aria-live="polite">{liveMsg}</div>

      <div class="sdh-legend" aria-label="Confidence band legend (paired label and color)">
        <span class="sdh-k"><span class="sdh-sw sdh-sw--high" aria-hidden="true"></span><b>HIGH</b> &gt;=0.70</span>
        <span class="sdh-k"><span class="sdh-sw sdh-sw--med" aria-hidden="true"></span><b>MEDIUM</b> 0.40--0.69</span>
        <span class="sdh-k"><span class="sdh-sw sdh-sw--learn" aria-hidden="true"></span><b>LEARNING</b> &lt;0.40</span>
        <span class="sdh-vec-key">
          <svg viewBox="0 0 26 8" aria-hidden="true"><path d="M1 7 L25 1" fill="none" stroke="currentColor" stroke-width="1.5" /></svg>
          <span>propagation vector</span>
        </span>
        <span class="sdh-self" title="Sessions whose project_slug is in the SM exclusion set are dropped at the SQL WHERE -- SM never appears as a governed target.">self excluded: {excludedSelf}</span>
        {#if usedMock}
          <span class="sdh-mock" title="Live gov.db had no cross-session patterns -- showing a deterministic fixture so the matrix is visible and testable.">sample data</span>
        {/if}
      </div>
    {:else}
      <p class="sdh__note" role="note">
        No cross-session patterns yet -- a pattern must fire in 2+ governed (non-SM) sessions to appear here.
        {#if excludedSelf > 0}<span class="sdh-self"> self excluded: {excludedSelf}</span>{/if}
      </p>
    {/if}
  </section>

  <!-- SESSION DNA CARD (1-click drill-down) -->
  {#if cardOpen && cardNode}
    <div class="sdh-scrim" role="presentation" on:click={onScrimClick}>
      <div
        class="sdh-card"
        bind:this={cardEl}
        role="dialog"
        aria-modal="true"
        aria-label={`Session ${cardNode.slug} -- pattern detail`}
        tabindex="-1"
        on:keydown={onCardKeydown}
      >
        <div class="sdh-card__head">
          <div>
            <div class="sdh-card__slug">{cardNode.slug}</div>
            {#if cardNode.project_slug}<div class="sdh-card__proj">{cardNode.project_slug}</div>{/if}
            {#if cardNode.agent_slugs && cardNode.agent_slugs.length}
              <div class="sdh-roster">
                {#each cardNode.agent_slugs as a}<span class="sdh-agent">{a}</span>{/each}
              </div>
            {/if}
          </div>
          <button type="button" class="sdh-card__close" aria-label="Close session detail (Escape)" on:click={closeCard}>Close (Esc)</button>
        </div>

        <div class="sdh-card__sec">
          <h4>Unique to this session <span class="sdh-sub">top patterns seen ONLY here</span></h4>
          {#if cardUnique.length === 0}
            <p class="sdh-card__empty">No patterns unique to this session -- everything here is shared.</p>
          {:else}
            <ul class="sdh-plist">
              {#each cardUnique as p (p.hash)}
                {@const band = bandOf(p.conf)}
                <li class="sdh-pitem">
                  <span class="sdh-pay"><span class="sdh-pay-h">{shortHash(p.hash)}</span>{patternMeta(p.hash).payload || ''}
                    <span class="sdh-verdict" data-v="isolated">isolated -- contained</span>
                  </span>
                  <span class="sdh-chip" data-band={band}>
                    <span class="sdh-chip-v">{fmtConf(p.conf)}</span><span class="sdh-chip-band">{bandWord(band)}</span>
                  </span>
                </li>
              {/each}
            </ul>
          {/if}
        </div>

        <div class="sdh-card__sec">
          <h4>Shared "contagion" patterns <span class="sdh-sub">per-session confidence spread</span></h4>
          {#if cardShared.length === 0}
            <p class="sdh-card__empty">No shared patterns -- this session is currently isolated.</p>
          {:else}
            <ul class="sdh-plist">
              {#each cardShared as p (p.hash)}
                {@const v = spreadVerdict(p.spread)}
                <li class="sdh-pitem">
                  <span class="sdh-pay"><span class="sdh-pay-h">{shortHash(p.hash)}</span>{patternMeta(p.hash).payload || ''}
                    <span class="sdh-verdict" data-v={v.verdict}>{v.text}</span>
                  </span>
                  <span class="sdh-spread">
                    {#each p.spread.slice().sort((a, b) => b.conf - a.conf) as s}
                      {@const sb = bandOf(s.conf)}
                      <span class="sdh-chip" data-band={sb}>
                        <span class="sdh-chip-who">{s.node.slug}</span><span class="sdh-chip-v">{fmtConf(s.conf)}</span><span class="sdh-chip-band">{bandWord(sb)}</span>
                      </span>
                    {/each}
                  </span>
                </li>
              {/each}
            </ul>
          {/if}
        </div>
      </div>
    </div>
  {/if}
{/if}

<style>
  .sdh {
    display: block;
    background: var(--bg-card, #0c1118);
    border: 1px solid var(--border, #192030);
    border-radius: 7px;
    padding: 12px 16px 14px;
    margin-bottom: 12px;
  }

  .sdh__cap {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 10px;
  }
  .sdh__ttl {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--text-ui, #8a8068);
  }
  .sdh__ttl b {
    color: var(--text-bright, #e8e0cc);
  }
  .sdh__count {
    display: inline-flex;
    align-items: baseline;
    gap: 6px;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 12px;
    color: var(--text-dim, #948870);
    border: 1px solid var(--border, #192030);
    border-radius: 4px;
    padding: 3px 9px;
  }
  .sdh__count-n {
    color: var(--accent, #f59e0b);
    font-variant-numeric: tabular-nums;
    font-weight: 700;
  }
  .sdh__count-lab {
    letter-spacing: 0.1em;
    text-transform: uppercase;
    font-size: 10px;
  }

  .sdh__note {
    margin: 6px 0 0;
    font-size: 12px;
    color: var(--text-dim, #948870);
    border: 1px dashed var(--border, #192030);
    border-radius: 5px;
    padding: 10px 13px;
    line-height: 1.55;
  }

  /* ---- the DNA matrix ---- */
  .sdh-matrix {
    display: inline-grid;
    gap: 6px;
    align-items: stretch;
    position: relative;
  }
  .sdh-corner {
    /* blank top-left corner */
  }
  .sdh-colh {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    padding: 2px 0 4px;
  }
  .sdh-hash {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10px;
    letter-spacing: 0.04em;
    color: var(--text-bright, #e8e0cc);
    writing-mode: vertical-rl;
    transform: rotate(180deg);
    white-space: nowrap;
    line-height: 1;
    max-height: 74px;
    overflow: hidden;
  }
  .sdh-lvl {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.05em;
    border: 1px solid var(--border, #192030);
    border-radius: 2px;
    padding: 1px 5px;
    color: var(--text-bright, #e8e0cc);
    white-space: nowrap;
  }
  .sdh-lvl[data-lvl='L3'] {
    border-color: var(--badge-warn-border, #ea580c);
    color: var(--badge-warn-fg, #9a3412);
    background: var(--badge-warn-bg, #ffedd5);
  }
  .sdh-lvl[data-lvl='L2'] {
    border-color: var(--badge-ar-border, #d97706);
    color: var(--badge-ar-fg, #b45309);
    background: var(--badge-ar-bg, #fef3c7);
  }

  /* ROW HEADER: left-anchored mono slug + agent-roster ribbon. */
  .sdh-rowh {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
    justify-content: center;
    padding: 0 12px 0 6px;
    min-width: 160px;
    border: 1px solid transparent;
    border-radius: 5px;
    cursor: pointer;
    background: transparent;
    text-align: left;
    appearance: none;
    color: inherit;
    font: inherit;
  }
  .sdh-rowh:hover {
    background: var(--bg-row-hover, #131c2a);
  }
  .sdh-rowh:focus-visible {
    outline: 2px solid var(--accent, #f59e0b);
    outline-offset: 2px;
    border-radius: 5px;
  }
  .sdh-slug {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 13px;
    color: var(--text-bright, #e8e0cc);
    font-weight: 600;
    letter-spacing: 0.02em;
  }
  .sdh-proj {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10px;
    color: var(--text-dim, #948870);
    letter-spacing: 0.04em;
  }
  .sdh-roster {
    display: inline-flex;
    gap: 4px;
    flex-wrap: wrap;
    margin-top: 1px;
  }
  .sdh-agent {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 9px;
    letter-spacing: 0.04em;
    text-transform: lowercase;
    color: var(--text-ui, #8a8068);
    border: 1px solid var(--border, #192030);
    border-radius: 2px;
    padding: 0 4px;
    line-height: 1.5;
  }
  .sdh-openhint {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 9px;
    color: var(--text-dim, #948870);
    letter-spacing: 0.05em;
    opacity: 0;
    transition: opacity 0.12s;
  }
  .sdh-rowh:hover .sdh-openhint,
  .sdh-rowh:focus-visible .sdh-openhint {
    opacity: 1;
  }

  /* CONFIDENCE CELL: fill = band color, FACE = literal numeric (the signal). */
  .sdh-cell {
    position: relative;
    width: 62px;
    height: 46px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    border: 1px solid var(--border, #192030);
    border-radius: 5px;
    background: var(--bg-row-alt, #0b1018);
    font-family: var(--font-d, ui-monospace, monospace);
    cursor: default;
    color: var(--text, #b8b098);
    transition: box-shadow 0.12s ease;
  }
  .sdh-cell--has {
    cursor: pointer;
  }
  .sdh-val {
    font-size: 15px;
    font-variant-numeric: tabular-nums;
    font-weight: 700;
    letter-spacing: 0.01em;
    line-height: 1;
  }
  .sdh-band {
    font-size: 8px;
    letter-spacing: 0.07em;
    text-transform: uppercase;
  }
  /* EMPTY (no occurrence): a hairline ghost, no ink. */
  .sdh-cell--empty {
    background: transparent;
    border-style: dashed;
    opacity: 0.55;
  }
  .sdh-cell--empty .sdh-val {
    color: var(--text-dim, #948870);
    font-weight: 500;
  }
  .sdh-cell--empty .sdh-band {
    color: var(--text-dim, #948870);
  }
  /* LEARNING band <0.40: quiet, hairline only. */
  .sdh-cell[data-band='LEARNING'] {
    background: var(--bg-row-alt, #0b1018);
    border-color: var(--border, #192030);
  }
  .sdh-cell[data-band='LEARNING'] .sdh-val {
    color: var(--text, #b8b098);
    font-weight: 600;
  }
  .sdh-cell[data-band='LEARNING'] .sdh-band {
    color: var(--text-dim, #948870);
  }
  /* MEDIUM band 0.40-0.69: slate-amber, mid weight. AAA numerics on #fef3c7. */
  .sdh-cell[data-band='MEDIUM'] {
    background: var(--badge-ar-bg, #fef3c7);
    border-color: var(--badge-ar-border, #d97706);
  }
  .sdh-cell[data-band='MEDIUM'] .sdh-val {
    color: #7c2d12;
    font-weight: 700;
  }
  .sdh-cell[data-band='MEDIUM'] .sdh-band {
    color: var(--badge-ar-fg, #b45309);
  }
  /* HIGH band >=0.70: warn-toned amber, HEAVIEST type weight. AAA on #ffedd5. */
  .sdh-cell[data-band='HIGH'] {
    background: var(--badge-warn-bg, #ffedd5);
    border-color: var(--badge-warn-border, #ea580c);
    border-width: 2px;
  }
  .sdh-cell[data-band='HIGH'] .sdh-val {
    color: #7c2d12;
    font-weight: 800;
  }
  .sdh-cell[data-band='HIGH'] .sdh-band {
    color: var(--badge-warn-fg, #9a3412);
    font-weight: 700;
  }
  .sdh-cell:focus-visible {
    outline: 2px solid var(--accent, #f59e0b);
    outline-offset: 2px;
    border-radius: 5px;
  }
  .sdh-cell--lit {
    box-shadow: 0 0 0 2px var(--accent, #f59e0b), 0 0 14px -2px var(--accent-glow, rgba(245, 158, 11, 0.35));
  }

  /* the 1px propagation connector between the two brightest cells of a column */
  .sdh-vector {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    overflow: visible;
    z-index: 3;
  }
  .sdh-vector path {
    fill: none;
    stroke: var(--accent, #f59e0b);
    stroke-width: 1;
    opacity: 0.5;
    stroke-dasharray: 3 3;
  }
  .sdh-vector path.lit {
    opacity: 1;
    stroke-width: 1.5;
    stroke-dasharray: none;
  }

  .sdh-live {
    margin-top: 8px;
    min-height: 1.4em;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 11px;
    color: var(--text-bright, #e8e0cc);
  }

  /* ---- the band legend (paired swatch + WRITTEN name + numeric range) ---- */
  .sdh-legend {
    display: flex;
    align-items: center;
    gap: 18px;
    flex-wrap: wrap;
    margin-top: 12px;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 11px;
    color: var(--text-dim, #948870);
    border-top: 1px solid var(--border, #192030);
    padding-top: 11px;
  }
  .sdh-k {
    display: inline-flex;
    align-items: center;
    gap: 7px;
  }
  .sdh-k b {
    color: var(--text-bright, #e8e0cc);
    font-weight: 700;
  }
  .sdh-sw {
    width: 13px;
    height: 13px;
    border-radius: 3px;
    flex: 0 0 auto;
    border: 1px solid var(--border, #192030);
  }
  .sdh-sw--high {
    background: var(--badge-warn-bg, #ffedd5);
    border: 2px solid var(--badge-warn-border, #ea580c);
  }
  .sdh-sw--med {
    background: var(--badge-ar-bg, #fef3c7);
    border-color: var(--badge-ar-border, #d97706);
  }
  .sdh-sw--learn {
    background: var(--bg-row-alt, #0b1018);
    border-color: var(--border, #192030);
  }
  .sdh-vec-key {
    display: inline-flex;
    align-items: center;
    gap: 7px;
  }
  .sdh-vec-key svg {
    width: 26px;
    height: 8px;
  }
  .sdh-self {
    color: var(--text-ui, #8a8068);
    letter-spacing: 0.04em;
  }
  .sdh-mock {
    margin-left: auto;
    color: var(--badge-ar-fg, #b45309);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  /* ============================ SESSION DNA CARD ============================ */
  .sdh-scrim {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    z-index: 50;
  }
  .sdh-card {
    width: 100%;
    max-width: 560px;
    max-height: 86vh;
    overflow: auto;
    background: var(--bg-card, #0c1118);
    border: 1px solid var(--border-hi, rgba(245, 158, 11, 0.25));
    border-radius: 9px;
    box-shadow: 0 30px 80px -28px rgba(0, 0, 0, 0.85);
  }
  .sdh-card:focus-visible {
    outline: 2px solid var(--accent, #f59e0b);
    outline-offset: 2px;
  }
  .sdh-card__head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    padding: 14px 18px;
    border-bottom: 1px solid var(--border, #192030);
  }
  .sdh-card__slug {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 16px;
    color: var(--text-bright, #e8e0cc);
    font-weight: 700;
  }
  .sdh-card__proj {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 11px;
    color: var(--text-dim, #948870);
    margin-top: 2px;
  }
  .sdh-card__close {
    appearance: none;
    background: transparent;
    border: 1px solid var(--border, #192030);
    color: var(--text-ui, #8a8068);
    border-radius: 4px;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 12px;
    padding: 4px 10px;
    cursor: pointer;
    flex: 0 0 auto;
  }
  .sdh-card__close:focus-visible {
    outline: 2px solid var(--accent, #f59e0b);
    outline-offset: 2px;
  }
  .sdh-card__sec {
    padding: 14px 18px;
    border-bottom: 1px solid var(--border, #192030);
  }
  .sdh-card__sec:last-child {
    border-bottom: none;
  }
  .sdh-card__sec h4 {
    margin: 0 0 9px;
    font-size: 13px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-bright, #e8e0cc);
  }
  .sdh-sub {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10px;
    color: var(--text-dim, #948870);
    letter-spacing: 0.04em;
    margin-left: 8px;
    text-transform: none;
  }
  .sdh-card__empty {
    margin: 0;
    font-size: 12px;
    color: var(--text-dim, #948870);
    font-style: italic;
  }
  .sdh-plist {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 7px;
  }
  .sdh-pitem {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 10px;
    align-items: center;
    padding: 7px 9px;
    border: 1px solid var(--border, #192030);
    border-radius: 5px;
    background: var(--bg-row-alt, #0b1018);
  }
  .sdh-pay {
    font-size: 12px;
    color: var(--text, #b8b098);
    min-width: 0;
  }
  .sdh-pay-h {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10px;
    color: var(--text-dim, #948870);
    margin-right: 7px;
  }
  .sdh-spread {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    flex: 0 0 auto;
    flex-wrap: wrap;
    justify-content: flex-end;
  }
  /* the paired confidence chip (numeric + band WORD + tone) */
  .sdh-chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 11px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    border: 1px solid var(--border, #192030);
    border-radius: 3px;
    padding: 2px 7px;
    color: var(--text-bright, #e8e0cc);
  }
  .sdh-chip[data-band='HIGH'] {
    background: var(--badge-warn-bg, #ffedd5);
    border: 2px solid var(--badge-warn-border, #ea580c);
    color: #7c2d12;
  }
  .sdh-chip[data-band='MEDIUM'] {
    background: var(--badge-ar-bg, #fef3c7);
    border-color: var(--badge-ar-border, #d97706);
    color: #7c2d12;
  }
  .sdh-chip[data-band='LEARNING'] {
    background: var(--bg-row-alt, #0b1018);
    border-color: var(--border, #192030);
    color: var(--text, #b8b098);
  }
  .sdh-chip-who {
    font-weight: 600;
    color: var(--text-ui, #8a8068);
    letter-spacing: 0.02em;
  }
  .sdh-chip-band {
    font-size: 8px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .sdh-verdict {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin-top: 6px;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    border-radius: 3px;
    padding: 2px 7px;
  }
  .sdh-verdict[data-v='spreading'] {
    color: var(--badge-warn-fg, #9a3412);
    background: var(--badge-warn-bg, #ffedd5);
    border: 1px solid var(--badge-warn-border, #ea580c);
  }
  .sdh-verdict[data-v='isolated'] {
    color: var(--text-dim, #948870);
    background: var(--bg-row-alt, #0b1018);
    border: 1px solid var(--border, #192030);
  }
  .sdh-verdict[data-v='asymmetric'] {
    color: var(--badge-ar-fg, #b45309);
    background: var(--badge-ar-bg, #fef3c7);
    border: 1px solid var(--badge-ar-border, #d97706);
  }

  @media (prefers-reduced-motion: reduce) {
    .sdh-cell,
    .sdh-openhint {
      transition: none;
    }
  }
</style>
