<!--
  RegretMiningOverrideLoop.svelte -- BETA feature "regret-mining-override-loop"
  (#24: Regret Mining -- close the operator-override feedback loop).

  WHAT IT IS (the operator-APPROVED mockup, realised):
    A READ-ONLY, post-hoc regret ledger card. Every operator OVERRIDE (a HITL
    APPROVE-over-a-SUGGEST, a DISMISS-of-an-INTERVENE, a free-text annotate) is
    the richest learning signal the system makes -- the human said "you were
    wrong here". This pane mines the AGGREGATE of those overrides from the
    EXISTING hitl_overrides + decisions tables and ranks the divergence clusters
    (per matched_hash / routing layer) so the operator can fix the worst
    recurring wrong verdict ONCE -- as a copyable advisory-bias proposal STUB --
    instead of re-correcting it by hand forever. Each cluster is a horizontal
    LANE (not a table row): a fat left gutter (paired direction badge + from->to
    flow), an asymmetric middle (oversized override-rate + identity FROM DATA),
    a thin right rail (literal "n/N" + a hairline mini-bar). Expand a lane ->
    the evidence drawer with the underlying overrides + a "Draft as proposal"
    button that composes operator-facing markdown to copy / download.

  ============================ GOVERNANCE FLOOR ============================
  BETA GATE (load-bearing): renders NOTHING and registers NO pollers / SSE
    handlers / timers / window bridges unless
    $betaFlags['regret-mining-override-loop'] is true (default OFF). The only
    network it does is ONE best-effort read-only GET /api/governance/regret on
    mount-while-ON (and on an explicit operator Refresh). It opens no socket and
    starts no interval.

  CONSTRAINED ADDITIVE (vs the original proposal's Learn-Mode bias write):
    NO message_bus.py edit, NO new bus envelope, NO new decisions column, NO
    ADR-18 amendment, NO in-process spawn/cron/subprocess. The regret clusters
    are computed by an ADDITIVE read endpoint over the existing tables. The
    "Draft as proposal" composes markdown CLIENT-SIDE and WRITES NOTHING
    server-side -- it never mutates a decisions row, never edits a rule, never
    bypasses the absolute HITL gate. The actual advisory-bias write-back is
    DEFERRED to a documented operator-facing "from CLI" affordance (the operator
    reviews + applies the drafted stub by hand).

  M2 (ambient-at-rest / never auto-foreground): a calm reflective card. It NEVER
    auto-expands a lane, NEVER steals focus, NEVER rearranges layout. The
    operator clicks a lane to open its evidence.

  M4 / M5 (paired label + color EVERYWHERE): the direction badge, the demo-data
    chip, and the polarity chip ALL carry the literal WORD adjacent to the color
    swatch. Color is never the sole signal. The override rate is ALWAYS paired
    with the literal "n/N overridden" fraction next to the bar (the bar is never
    the only channel).

  M15 / G2 (polarity / self-exclude): the SM-own session is NEVER mined. The
    server endpoint excludes SM-self at the SQL WHERE (project_slug NOT IN the SM
    slug set AND session_id != SM_OWN_SESSION_ID); this component applies a
    second ownSessionId backstop in deriveClusters(), and renders the dropped
    self tally as a visible "excluded N SM-self rows" chip (G2 as a feature).

  M16 (domain-agnostic): cluster identity (matched_hash / routing layer), the
    governed-target slug, the from/to actions, and the override directions all
    render FROM DATA. No monitored-project vocabulary.

  M17 (a11y / WCAG AAA): each lane is a real <button> with aria-expanded +
    aria-controls; roving tabindex across the ledger (Up/Down/Home/End move,
    Enter/Space toggle, Escape collapses). The drafted stub is announced via a
    polite live region. Focused controls show a 2px accent ring + offset.
    Reduced motion honoured.

  M18 (post-hoc): a pure render pass over a single read-only GET. No verdict-
    path work, no bus write, no mutation.

  MOCK FALLBACK: the live hitl_overrides table is frequently EMPTY (overrides
    are rare). When the endpoint returns no clusters the ledger falls back to a
    realistic mock fixture so the feature is testable. usedMock is exposed
    (data-mock) for the harness and shown as a visible DEMO DATA chip.

  FILE-DISJOINT: this component + its RegretMiningOverrideLoop-* helpers own all
    the new code. It dispatches no shell CustomEvent and imports no sibling beta
    component.

  ASCII-only (cp1252-safe): dash is "--". No smart quotes, no em-dashes.
-->
<script>
  import { onMount, onDestroy } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { getOwnSessionId } from '../../stores/session.js';
  import { getRegret } from './RegretMiningOverrideLoop-api.js';
  import {
    deriveClusters,
    evidenceFor,
    rankScore,
    pct,
    mockLedger,
  } from './RegretMiningOverrideLoop-data.js';

  /** The stable BETA flag key this component gates on. */
  const FLAG_KEY = 'regret-mining-override-loop';

  /**
   * allowMock: when the live endpoint has no clusters, fall back to a realistic
   * mock fixture so the ledger is visible/testable. Default true (tests rely on
   * it). Set false to force a true live-only render.
   * @type {boolean}
   */
  export let allowMock = true;

  /**
   * windowDays: the look-back window passed to the read endpoint.
   * @type {number}
   */
  export let windowDays = 30;

  // -- gate (single source of truth: the betaFlags store) --------------------
  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // -- self-exclude (G2 / M15) -----------------------------------------------
  let ownSessionId = '';

  // -- ledger state ----------------------------------------------------------
  let loading = false;
  let usedMock = false;
  /** @type {Array<Record<string, any>>} */
  let clusters = [];
  let meta = {
    window_days: windowDays,
    excluded_self: 0,
    total_overrides: 0,
    own_session_id: null,
  };

  /** @type {string} the cluster_key of the currently-expanded lane ('' = none) */
  let openKey = '';
  /** @type {string} the cluster_key whose draft stub is currently revealed */
  let draftKey = '';
  let liveMsg = '';

  /** roving-tabindex focus index across the lanes. */
  let focusIdx = 0;
  /** @type {HTMLElement} */
  let ledgerEl;

  /**
   * Load the ledger ONCE (mount-while-ON or explicit operator Refresh). This is
   * the ONLY network this component performs -- no poller, no interval, no SSE.
   */
  async function load() {
    if (!enabled) return;
    loading = true;
    let data = null;
    try {
      data = await getRegret({ window_days: windowDays });
    } catch {
      data = null;
    }
    applyData(data);
    loading = false;
  }

  /** @param {Record<string, any>|null} data */
  function applyData(data) {
    const live = data && Array.isArray(data.clusters)
      ? deriveClustersFromServer(data.clusters)
      : [];
    if (live.length > 0) {
      clusters = live;
      meta = {
        window_days: Number(data.window_days) || windowDays,
        excluded_self: Number(data.excluded_self) || 0,
        total_overrides: Number(data.total_overrides) || live.reduce((a, c) => a + (c.n_overridden || 0), 0),
        own_session_id: data.own_session_id || null,
      };
      usedMock = !!data.mock;
      return;
    }
    if (!allowMock) {
      clusters = [];
      usedMock = false;
      meta = { window_days: windowDays, excluded_self: 0, total_overrides: 0, own_session_id: null };
      return;
    }
    // No live clusters -> realistic mock so the ledger is visible + testable.
    const fix = mockLedger();
    clusters = fix.clusters.slice().sort((a, b) => rankScore(b) - rankScore(a));
    meta = {
      window_days: fix.window_days,
      excluded_self: fix.excluded_self,
      total_overrides: fix.total_overrides,
      own_session_id: fix.own_session_id,
    };
    usedMock = true;
  }

  /**
   * The server returns clusters with an embedded `overrides` list. Re-run the
   * pure derivation so the component shares ONE ranking + evidence code path
   * with the mock (and so the ownSessionId backstop applies to live rows too).
   * The server already self-excludes; this is belt-and-suspenders (G2).
   * @param {Array<Record<string, any>>} serverClusters
   * @returns {Array<Record<string, any>>}
   */
  function deriveClustersFromServer(serverClusters) {
    // Flatten server clusters back to override+decision rows, then re-derive,
    // so a single deriveClusters() owns ranking/direction/evidence for both
    // live + mock. Each server override row carries the cluster's shape fields.
    const rows = [];
    const counts = {};
    for (const c of serverClusters) {
      if (!c || typeof c !== 'object') continue;
      const key = c.cluster_key || '';
      if (key) counts[key] = Number(c.n_decisions) || 0;
      const ovs = Array.isArray(c.overrides) ? c.overrides : [];
      for (const o of ovs) {
        rows.push({
          decision_id: o.decision_id,
          session_id: o.session_id,
          project_slug: o.project_slug,
          original_action: o.original_action,
          override_action: o.override_action,
          note: o.note,
          timestamp: o.timestamp,
          // shape keys so deriveClusters re-buckets into the SAME cluster_key:
          matched_hash: c.label_dim === 'matched_hash' ? c.identity : '',
          layer: c.layer,
          content: o.content,
        });
      }
    }
    return deriveClusters(rows, { ownSessionId, decisionCounts: counts });
  }

  // hottest cluster anchor + the cool threshold for de-emphasis.
  $: topScore = clusters.length ? rankScore(clusters[0]) : 0;

  function isHot(c, i) { return i === 0; }
  function isCool(c) { return rankScore(c) < topScore * 0.5; }

  // -- lane expand / collapse ------------------------------------------------
  function toggleLane(key) {
    if (openKey === key) {
      openKey = '';
      draftKey = '';
    } else {
      openKey = key;
      draftKey = '';
    }
  }

  function toggleDraft(key) {
    draftKey = draftKey === key ? '' : key;
  }

  function clusterFor(key) {
    return clusters.find((c) => c.cluster_key === key) || null;
  }

  // -- "Draft as proposal" -- compose markdown CLIENT-SIDE (writes nothing) ---
  function copyDraft(cluster) {
    const ev = evidenceFor(cluster);
    const done = () => announce(cluster, 'copied');
    if (typeof navigator !== 'undefined' && navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(ev.draft_markdown).then(done, done);
    } else {
      done();
    }
  }

  function downloadDraft(cluster) {
    const ev = evidenceFor(cluster);
    try {
      const blob = new Blob([ev.draft_markdown], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `advisory-bias-${String(cluster.cluster_key || 'cluster').replace(/[^a-z0-9]/gi, '-')}.md`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      /* download blocked (sandbox) -- non-fatal; copy path still works */
    }
    announce(cluster, 'downloaded');
  }

  function announce(cluster, verb) {
    liveMsg = `Drafted advisory-bias candidate for cluster ${cluster.identity} -- ${verb}. Nothing was written server-side.`;
  }

  // -- ledger keyboard (roving tabindex across lanes) ------------------------
  function laneButtons() {
    return ledgerEl ? Array.from(ledgerEl.querySelectorAll('.rmo__lane')) : [];
  }

  function focusLane(pos) {
    const btns = laneButtons();
    if (!btns.length) return;
    focusIdx = Math.max(0, Math.min(btns.length - 1, pos));
    btns.forEach((b, i) => b.setAttribute('tabindex', i === focusIdx ? '0' : '-1'));
    btns[focusIdx].focus();
  }

  /** @param {KeyboardEvent} e @param {number} i @param {string} key */
  function onLaneKeydown(e, i, key) {
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        focusLane(i + 1);
        break;
      case 'ArrowUp':
        e.preventDefault();
        focusLane(i - 1);
        break;
      case 'Home':
        e.preventDefault();
        focusLane(0);
        break;
      case 'End':
        e.preventDefault();
        focusLane(laneButtons().length - 1);
        break;
      case 'Enter':
      case ' ':
        e.preventDefault();
        toggleLane(key);
        break;
      case 'Escape':
        if (openKey === key) {
          e.preventDefault();
          openKey = '';
          draftKey = '';
        }
        break;
      default:
        break;
    }
  }

  onMount(() => {
    // Resolve the self-exclude id once. Safe at mount: reads a meta tag / store.
    ownSessionId = getOwnSessionId() || '';
  });

  // Reactive: a flag flip from OFF->ON triggers the ONE-SHOT load (this also
  // fires for a cold mount where the flag is already ON, so onMount does not
  // call load() itself -- avoids a double-load). OFF clears all state + frees
  // every reference so the gated component registers nothing while OFF.
  let _wasEnabled = false;
  $: if (enabled && !_wasEnabled) {
    _wasEnabled = true;
    // defer one microtask so onMount's ownSessionId read lands first
    Promise.resolve().then(() => load());
  } else if (!enabled && _wasEnabled) {
    _wasEnabled = false;
    clusters = [];
    openKey = '';
    draftKey = '';
    usedMock = false;
  }

  onDestroy(() => {
    openKey = '';
    draftKey = '';
  });
</script>

{#if enabled}
  <section
    class="rmo"
    data-testid="regret-mining-override-loop"
    data-mock={usedMock ? 'true' : 'false'}
    aria-labelledby="rmo-title"
  >
    <!-- HEADER: kicker + title + sub + BETA pill -->
    <div class="rmo__head">
      <div class="rmo__titlewrap">
        <p class="rmo__kicker">Operator-override feedback loop</p>
        <h2 class="rmo__title" id="rmo-title">Regret <span class="rmo__grad">Mining</span></h2>
        <p class="rmo__sub">
          Where governance and you keep disagreeing -- ranked, so you can fix the
          worst cluster ONCE as advisory bias instead of re-correcting it forever.
          Post-hoc and read-only; never on the verdict hot path.
        </p>
      </div>
      <div class="rmo__ctrl">
        <span class="rmo__beta-pill">
          <span class="rmo__beta-dot" aria-hidden="true"></span>
          BETA -- default OFF, toggled in Settings &gt; BETA features
        </span>
        <button
          type="button"
          class="rmo__refresh"
          aria-label="Reload the regret ledger"
          on:click={load}
          disabled={loading}
        >{loading ? 'Loading...' : 'Refresh'}</button>
      </div>
    </div>

    <!-- META STRIP: window, overrides total, polarity self-exclusion, demo -->
    <div class="rmo__metastrip">
      <span class="rmo__chip"><span class="rmo__chip-dot" aria-hidden="true"></span>window <b>{meta.window_days}d</b></span>
      <span class="rmo__chip"><span class="rmo__chip-dot" aria-hidden="true"></span>overrides <b>{meta.total_overrides}</b></span>
      <span
        class="rmo__chip rmo__chip--polarity"
        title="Polarity self-exclusion (G2): SM never mines its own session."
      >
        <span class="rmo__chip-dot" aria-hidden="true"></span>excluded <b>{meta.excluded_self}</b> SM-self rows
      </span>
      <span class="rmo__metastrip-spacer"></span>
      {#if usedMock}
        <span
          class="rmo__chip rmo__chip--demo"
          title="The live hitl_overrides table is empty -- showing a sample fixture so the ledger is testable."
        >
          <span class="rmo__chip-dot" aria-hidden="true"></span>DEMO DATA -- mock
        </span>
      {/if}
    </div>

    <!-- standing read-only advisory line (the contract, always visible) -->
    <div class="rmo__advisory" role="note">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </svg>
      <span>
        <b>Advisory only.</b> Drafting a candidate never changes a verdict, never
        writes the decisions table, and never bypasses the HITL gate. The bias
        write-back is deferred to a from-CLI affordance out of this read-only view.
      </span>
    </div>

    <!-- THE REGRET LEDGER -->
    <div class="rmo__ledger" bind:this={ledgerEl}>
      <div class="rmo__caption">
        <h3>Divergence clusters</h3>
        <span class="rmo__rank-hint">ranked by override-rate x volume -- hottest on top</span>
      </div>

      {#if clusters.length === 0}
        <p class="rmo__empty" role="note">
          No operator overrides in the last {meta.window_days} days -- nothing to mine yet.
          Governance and you currently agree.
        </p>
      {:else}
        {#each clusters as c, i (c.cluster_key)}
          {@const open = openKey === c.cluster_key}
          {@const hot = isHot(c, i)}
          {@const cool = isCool(c)}
          {@const fillPct = Math.round((Number(c.override_rate) || 0) * 100)}
          <button
            type="button"
            class="rmo__lane"
            class:rmo__lane--hot={hot}
            class:rmo__lane--cool={cool}
            id={`rmo-lane-${c.cluster_key.replace(/[^a-z0-9]/gi, '')}`}
            aria-expanded={open ? 'true' : 'false'}
            aria-controls={`rmo-drawer-${c.cluster_key.replace(/[^a-z0-9]/gi, '')}`}
            tabindex={i === 0 ? 0 : -1}
            on:click={() => toggleLane(c.cluster_key)}
            on:keydown={(e) => onLaneKeydown(e, i, c.cluster_key)}
          >
            <!-- left gutter: paired direction badge + from->to flow -->
            <span class="rmo__gutter">
              <span
                class="rmo__ar-badge"
                class:rmo__ar--escalated={c.dominant_direction === 'ESCALATED'}
                class:rmo__ar--deescalated={c.dominant_direction !== 'ESCALATED'}
                role="status"
                aria-label={`${c.dominant_direction} override direction`}
              >
                <span class="rmo__ar-dot" aria-hidden="true"></span>
                <span>{c.dominant_direction}</span>
              </span>
              <span class="rmo__flow">
                <span class="rmo__flow-from">{c.from_action}</span>
                <span class="rmo__flow-arr" aria-hidden="true">--&gt;</span>
                <span class="rmo__flow-to">{c.to_action}</span>
              </span>
              <span class="rmo__dirtext">{c.direction_label}</span>
            </span>

            <!-- middle: oversized rate + identity (FROM DATA) -->
            <span class="rmo__mid">
              <span class="rmo__rate">{pct(c.override_rate)}<small>override rate</small></span>
              <span class="rmo__ident">
                <span class="rmo__ident-id">{c.identity}</span>
                <span class="rmo__ident-dim">({c.label_dim} -- layer {c.layer})</span>
                {#if c.sample_content}
                  <span class="rmo__ident-sample">e.g. <span class="rmo__q">"{c.sample_content}"</span></span>
                {/if}
              </span>
            </span>

            <!-- right rail: literal fraction + hairline mini-bar (bar never alone) -->
            <span class="rmo__rail">
              <span class="rmo__frac">{c.n_overridden}/{c.n_decisions} <small>overridden</small></span>
              <span
                class="rmo__minibar"
                role="img"
                aria-label={`${c.n_overridden} of ${c.n_decisions} overridden`}
              >
                <span class="rmo__minibar-fill" style={`width:${fillPct}%`}></span>
              </span>
              <span class="rmo__rail-n">{c.n_decisions} decisions{hot ? ' -- hottest cluster' : ''}</span>
            </span>

            <span class="rmo__chev" class:rmo__chev--open={open} aria-hidden="true">&#9656;</span>
          </button>

          <!-- EVIDENCE DRAWER -->
          {#if open}
            {@const ev = evidenceFor(c)}
            <div
              class="rmo__drawer"
              id={`rmo-drawer-${c.cluster_key.replace(/[^a-z0-9]/gi, '')}`}
              role="region"
              aria-label={`Evidence for cluster ${c.identity}`}
            >
              <div class="rmo__drawer-head">
                <h4>Evidence</h4>
                <span class="rmo__drawer-count">
                  {ev.overrides.length} override{ev.overrides.length === 1 ? '' : 's'} shown -- {c.n_overridden}/{c.n_decisions} total
                </span>
                <span class="rmo__drawer-spacer"></span>
                {#if usedMock}
                  <span class="rmo__ar-badge rmo__ar--escalated" role="status" aria-label="DEMO DATA mock">
                    <span class="rmo__ar-dot" aria-hidden="true"></span><span>DEMO DATA</span>
                  </span>
                {/if}
              </div>

              <div class="rmo__ev">
                {#each ev.overrides as o (o.decision_id + o.timestamp)}
                  <div class="rmo__ev-row">
                    <span class="rmo__ev-ts">{o.timestamp}</span>
                    <span class="rmo__ev-flow">
                      <span class="rmo__flow-from">{o.original_action}</span>
                      <span class="rmo__flow-arr" aria-hidden="true">--&gt;</span>
                      <span class="rmo__flow-to">{o.override_action}</span>
                    </span>
                    <span class="rmo__ev-body">
                      <span class="rmo__ev-content">"{o.content}"</span>
                      {#if o.note}
                        <span class="rmo__ev-note"><span class="rmo__ev-lbl">note:</span> {o.note}</span>
                      {:else}
                        <span class="rmo__ev-note rmo__ev-note--empty">no operator note</span>
                      {/if}
                      <span class="rmo__ev-sess">{o.session_id} -- {o.project_slug} -- {o.decision_id}</span>
                    </span>
                  </div>
                {/each}
              </div>

              <div class="rmo__drawer-foot">
                <span class="rmo__drawer-advisory">
                  <b>Read-only.</b> "Draft as proposal" composes operator-facing markdown
                  you can copy or download. It writes nothing server-side and never changes a verdict.
                </span>
                <button
                  type="button"
                  class="rmo__btn rmo__btn--primary"
                  aria-expanded={draftKey === c.cluster_key ? 'true' : 'false'}
                  on:click={() => toggleDraft(c.cluster_key)}
                >Draft as proposal</button>
              </div>

              {#if draftKey === c.cluster_key}
                <div class="rmo__draft">
                  <div class="rmo__draft-head">
                    advisory-bias proposal stub -- operator-facing markdown
                    <span class="rmo__ar-badge rmo__ar--deescalated" role="status" aria-label="read-only stub">
                      <span class="rmo__ar-dot" aria-hidden="true"></span><span>READ-ONLY STUB</span>
                    </span>
                  </div>
                  <pre class="rmo__draft-pre">{ev.draft_markdown}</pre>
                  <div class="rmo__draft-foot">
                    <button type="button" class="rmo__btn" on:click={() => copyDraft(c)}>Copy markdown</button>
                    <button type="button" class="rmo__btn" on:click={() => downloadDraft(c)}>Download .md</button>
                  </div>
                </div>
              {/if}
            </div>
          {/if}
        {/each}
      {/if}
    </div>

    <!-- polite live region for the read-only draft outcome (assistive tech) -->
    <p class="rmo__sr-only" role="status" aria-live="polite">{liveMsg}</p>
  </section>
{/if}

<style>
  /* Self-contained reflective Frame-A card. Reuses theme.css tokens verbatim --
     no new tokens, no global CSS pollution. */
  .rmo {
    position: relative;
    margin: 0 0 14px;
    background:
      linear-gradient(180deg, rgba(245, 158, 11, 0.05), transparent 120px),
      var(--bg-card, #0c1118);
    border: 1px solid var(--border, #192030);
    border-top: 2px solid var(--accent-glow, rgba(245, 158, 11, 0.35));
    border-radius: 12px;
    overflow: hidden;
  }

  /* ---- header ---- */
  .rmo__head {
    display: grid;
    grid-template-columns: 1fr auto;
    align-items: start;
    gap: 18px;
    padding: 18px 22px 14px;
    border-bottom: 1px solid var(--border, #192030);
  }
  .rmo__titlewrap { min-width: 0; }
  .rmo__kicker {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10px;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--text-ui, #8a8068);
    margin: 0 0 6px;
  }
  .rmo__title {
    margin: 0;
    font-family: var(--font-h, inherit);
    font-size: 23px;
    line-height: 1.05;
    font-weight: 800;
    letter-spacing: -0.01em;
    color: var(--text-bright, #e8e0cc);
  }
  .rmo__grad {
    background: linear-gradient(92deg, var(--accent, #f59e0b), #ffd27a);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
  }
  .rmo__sub {
    margin: 8px 0 0;
    font-size: 12.5px;
    color: var(--text-dim, #94a3b8);
    max-width: 58ch;
    line-height: 1.5;
  }
  .rmo__ctrl {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 10px;
  }
  .rmo__beta-pill {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10.5px;
    letter-spacing: 0.04em;
    color: var(--badge-warn-fg, #ea580c);
    background: rgba(234, 88, 12, 0.10);
    border: 1px dashed var(--badge-warn-border, #ea580c);
    border-radius: 999px;
    padding: 4px 11px;
    white-space: nowrap;
  }
  .rmo__beta-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
  }
  .rmo__refresh {
    appearance: none;
    cursor: pointer;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 11px;
    letter-spacing: 0.04em;
    border: 1px solid var(--border, #192030);
    background: transparent;
    color: var(--text-ui, #8a8068);
    border-radius: 5px;
    padding: 5px 11px;
  }
  .rmo__refresh:hover:not(:disabled) {
    color: var(--text-bright, #e8e0cc);
    border-color: var(--border-hi, rgba(245, 158, 11, 0.25));
  }
  .rmo__refresh:disabled { opacity: 0.6; cursor: default; }
  .rmo__refresh:focus-visible {
    outline: 2px solid var(--accent, #f59e0b);
    outline-offset: 2px;
  }

  /* ---- meta strip ---- */
  .rmo__metastrip {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    padding: 10px 22px;
    border-bottom: 1px solid var(--border, #192030);
    background: var(--bg-row-alt, #0b1018);
    font-size: 11.5px;
    color: var(--text-dim, #94a3b8);
  }
  .rmo__chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10.5px;
    letter-spacing: 0.03em;
    border: 1px solid var(--border, #192030);
    border-radius: 4px;
    padding: 3px 8px;
    color: var(--text-dim, #94a3b8);
  }
  .rmo__chip b { color: var(--text-bright, #e8e0cc); font-weight: 600; }
  .rmo__chip-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--text-ui, #8a8068);
  }
  .rmo__chip--polarity {
    color: var(--accent, #f59e0b);
    border-color: var(--border-hi, rgba(245, 158, 11, 0.25));
  }
  .rmo__chip--polarity .rmo__chip-dot { background: var(--accent, #f59e0b); }
  .rmo__chip--demo {
    color: var(--badge-warn-fg, #ea580c);
    border-color: var(--badge-warn-border, #ea580c);
    border-style: dashed;
  }
  /* Paper theme: the shared --badge-warn token (#ea580c) is sub-AA on the light
     paper surface (#f5f1ea => 3.16:1). Darken this small-text chip to a WCAG-AA
     orange locally (component-scoped; theme.css is operator-owned, untouched). */
  :global([data-theme='paper']) .rmo__chip--demo {
    color: #9a3412;
    border-color: #9a3412;
  }
  .rmo__chip--demo .rmo__chip-dot { background: currentColor; }
  .rmo__metastrip-spacer { flex: 1 1 auto; }

  /* ---- standing advisory line ---- */
  .rmo__advisory {
    display: flex;
    align-items: flex-start;
    gap: 9px;
    padding: 12px 22px;
    border-bottom: 1px solid var(--border, #192030);
    font-size: 12px;
    color: var(--text, #b8b098);
    background: rgba(245, 158, 11, 0.04);
  }
  .rmo__advisory svg {
    width: 15px;
    height: 15px;
    flex: 0 0 auto;
    margin-top: 1px;
    color: var(--accent, #f59e0b);
  }
  .rmo__advisory b { color: var(--text-bright, #e8e0cc); }

  /* ---- the ledger ---- */
  .rmo__ledger { padding: 8px 12px 14px; }
  .rmo__caption {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    padding: 12px 8px 8px;
    gap: 12px;
  }
  .rmo__caption h3 {
    margin: 0;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--text-ui, #8a8068);
  }
  .rmo__rank-hint {
    font-size: 11px;
    color: var(--text-dim, #94a3b8);
    font-style: italic;
  }
  .rmo__empty {
    margin: 8px;
    padding: 18px;
    font-size: 12.5px;
    color: var(--text-dim, #94a3b8);
    font-style: italic;
    border: 1px dashed var(--border, #192030);
    border-radius: 8px;
  }

  /* a lane is a horizontal grid (NOT a table row) */
  .rmo__lane {
    position: relative;
    display: grid;
    grid-template-columns: 220px 1fr 168px;
    align-items: stretch;
    gap: 0;
    width: 100%;
    text-align: left;
    background: var(--bg-row, #0e141e);
    border: 1px solid var(--border, #192030);
    border-radius: 9px;
    margin: 9px 0;
    padding: 0;
    cursor: pointer;
    color: inherit;
    font: inherit;
  }
  .rmo__lane:hover {
    background: var(--bg-row-hover, #131c2a);
    border-color: var(--border-hi, rgba(245, 158, 11, 0.25));
  }
  .rmo__lane:focus-visible {
    outline: 2px solid var(--accent, #f59e0b);
    outline-offset: 2px;
  }
  .rmo__lane--hot {
    border-color: var(--badge-ar-border, #d97706);
    box-shadow: inset 3px 0 0 0 var(--accent, #f59e0b), 0 0 0 1px rgba(245, 158, 11, 0.18);
  }
  .rmo__lane--cool { opacity: 0.86; }

  /* left gutter */
  .rmo__gutter {
    display: flex;
    flex-direction: column;
    gap: 9px;
    justify-content: center;
    padding: 16px 14px 16px 18px;
    border-right: 1px solid var(--border, #192030);
  }
  .rmo__lane--hot .rmo__gutter { border-right-color: rgba(245, 158, 11, 0.22); }

  .rmo__flow {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 12px;
    letter-spacing: 0.02em;
    color: var(--text-bright, #e8e0cc);
  }
  .rmo__flow-arr { color: var(--text-ui, #8a8068); padding: 0 4px; }
  .rmo__flow-to { color: var(--accent, #f59e0b); }

  /* M4 paired label + color badge primitive */
  .rmo__ar-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    align-self: flex-start;
    font-family: inherit;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    padding: 4px 9px;
    white-space: nowrap;
    border-radius: 2px;
    line-height: 1;
  }
  .rmo__ar-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    flex: 0 0 auto;
  }
  /* ESCALATED = operator made it stricter -- WARN variant (amber, dashed). */
  .rmo__ar--escalated {
    color: #9a3412;
    background: var(--badge-warn-bg, #ffedd5);
    border: 1px dashed var(--badge-warn-border, #ea580c);
  }
  /* DE-ESCALATED = operator relaxed it -- OBSERVING variant (slate, solid). */
  .rmo__ar--deescalated {
    color: var(--badge-obs-fg, #475569);
    background: var(--badge-obs-bg, #f1f5f9);
    border: 1px solid var(--badge-obs-border, #cbd5e1);
  }
  .rmo__dirtext { font-size: 11.5px; color: var(--text-dim, #94a3b8); }

  /* middle column */
  .rmo__mid {
    display: flex;
    align-items: center;
    gap: 18px;
    padding: 16px 18px;
    min-width: 0;
  }
  .rmo__rate {
    font-family: var(--font-d, ui-monospace, monospace);
    font-variant-numeric: tabular-nums;
    font-size: 36px;
    line-height: 0.95;
    font-weight: 800;
    letter-spacing: -0.02em;
    color: var(--text-bright, #e8e0cc);
    flex: 0 0 auto;
  }
  .rmo__lane--hot .rmo__rate {
    color: var(--accent, #f59e0b);
    text-shadow: 0 0 22px var(--accent-glow, rgba(245, 158, 11, 0.35));
  }
  .rmo__rate small {
    display: block;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.12em;
    color: var(--text-ui, #8a8068);
    text-transform: uppercase;
    margin-top: 4px;
  }
  .rmo__ident { min-width: 0; }
  .rmo__ident-id {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 13.5px;
    color: var(--text-bright, #e8e0cc);
    letter-spacing: 0.02em;
  }
  .rmo__ident-dim {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10.5px;
    color: var(--text-ui, #8a8068);
  }
  .rmo__ident-sample {
    display: block;
    margin-top: 6px;
    font-size: 12px;
    color: var(--text-dim, #94a3b8);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 40ch;
  }
  .rmo__q { color: var(--text, #b8b098); font-style: italic; }

  /* right rail */
  .rmo__rail {
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 8px;
    padding: 16px 18px;
    border-left: 1px solid var(--border, #192030);
  }
  .rmo__lane--hot .rmo__rail { border-left-color: rgba(245, 158, 11, 0.22); }
  .rmo__frac {
    font-family: var(--font-d, ui-monospace, monospace);
    font-variant-numeric: tabular-nums;
    font-size: 14px;
    color: var(--text-bright, #e8e0cc);
    letter-spacing: 0.02em;
  }
  .rmo__frac small { color: var(--text-ui, #8a8068); font-size: 11px; }
  .rmo__minibar {
    position: relative;
    height: 8px;
    border-radius: 999px;
    background: var(--bg-row-alt, #0b1018);
    border: 1px solid var(--border, #192030);
    overflow: hidden;
    display: block;
  }
  .rmo__minibar-fill {
    position: absolute;
    inset: 0 auto 0 0;
    height: 100%;
    background: linear-gradient(90deg, var(--accent, #f59e0b), #ffce7a);
    border-right: 1px solid rgba(0, 0, 0, 0.4);
  }
  .rmo__lane--cool .rmo__minibar-fill { background: var(--text-ui, #8a8068); }
  .rmo__rail-n { font-size: 10.5px; color: var(--text-dim, #94a3b8); }

  .rmo__chev {
    position: absolute;
    right: 12px;
    top: 12px;
    color: var(--text-ui, #8a8068);
    font-size: 12px;
  }
  .rmo__chev--open { transform: rotate(90deg); color: var(--accent, #f59e0b); }

  /* ---- evidence drawer ---- */
  .rmo__drawer {
    margin: -4px 4px 12px;
    border: 1px solid var(--border-hi, rgba(245, 158, 11, 0.25));
    border-top: 0;
    border-radius: 0 0 9px 9px;
    background: var(--bg-row-alt, #0b1018);
    overflow: hidden;
  }
  .rmo__drawer-head {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    padding: 12px 18px;
    border-bottom: 1px solid var(--border, #192030);
  }
  .rmo__drawer-head h4 {
    margin: 0;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 12px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-ui, #8a8068);
    font-weight: 700;
  }
  .rmo__drawer-count {
    font-size: 11.5px;
    color: var(--text-dim, #94a3b8);
    font-family: var(--font-d, ui-monospace, monospace);
  }
  .rmo__drawer-spacer { flex: 1 1 auto; }

  .rmo__ev { display: flex; flex-direction: column; }
  .rmo__ev-row {
    display: grid;
    grid-template-columns: 150px auto 1fr;
    gap: 12px;
    align-items: baseline;
    padding: 10px 18px;
    border-bottom: 1px solid var(--border, #192030);
  }
  .rmo__ev-row:last-child { border-bottom: 0; }
  .rmo__ev-ts {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 11px;
    color: var(--text-ui, #8a8068);
  }
  .rmo__ev-flow {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 11.5px;
    color: var(--text-bright, #e8e0cc);
    white-space: nowrap;
  }
  .rmo__ev-body { min-width: 0; }
  .rmo__ev-content { display: block; font-size: 12.5px; color: var(--text, #b8b098); }
  .rmo__ev-note { display: block; margin-top: 3px; font-size: 11.5px; color: var(--text-dim, #94a3b8); }
  .rmo__ev-lbl { color: var(--text-ui, #8a8068); font-family: var(--font-d, ui-monospace, monospace); }
  .rmo__ev-note--empty { font-style: italic; color: var(--text-ui, #8a8068); }
  .rmo__ev-sess {
    display: block;
    margin-top: 3px;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10.5px;
    color: var(--text-ui, #8a8068);
  }

  .rmo__drawer-foot {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    padding: 14px 18px;
    background: var(--bg-card, #0c1118);
    border-top: 1px solid var(--border, #192030);
  }
  .rmo__drawer-advisory {
    font-size: 11.5px;
    color: var(--text-dim, #94a3b8);
    flex: 1 1 240px;
    min-width: 200px;
  }
  .rmo__drawer-advisory b { color: var(--text-bright, #e8e0cc); }

  .rmo__btn {
    appearance: none;
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-family: inherit;
    font-size: 12.5px;
    font-weight: 600;
    letter-spacing: 0.02em;
    border-radius: 6px;
    padding: 8px 14px;
    cursor: pointer;
    border: 1px solid var(--border, #192030);
    background: transparent;
    color: var(--text-dim, #94a3b8);
  }
  .rmo__btn:hover {
    color: var(--text-bright, #e8e0cc);
    border-color: var(--border-hi, rgba(245, 158, 11, 0.25));
    background: var(--accent-dim, rgba(245, 158, 11, 0.09));
  }
  .rmo__btn:focus-visible {
    outline: 2px solid var(--accent, #f59e0b);
    outline-offset: 2px;
  }
  .rmo__btn--primary {
    color: #1a1206;
    background: var(--accent, #f59e0b);
    border-color: var(--badge-ar-border, #d97706);
    font-weight: 700;
  }
  .rmo__btn--primary:hover { color: #1a1206; background: #ffb01f; }

  /* draft markdown reveal */
  .rmo__draft {
    margin: 0 18px 16px;
    border: 1px solid var(--border-hi, rgba(245, 158, 11, 0.25));
    border-radius: 8px;
    overflow: hidden;
    background: var(--bg-card, #0c1118);
  }
  .rmo__draft-head {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 14px;
    border-bottom: 1px solid var(--border, #192030);
    background: var(--bg-row, #0e141e);
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 11px;
    color: var(--text-ui, #8a8068);
    letter-spacing: 0.04em;
  }
  .rmo__draft-head .rmo__ar-badge { margin-left: auto; }
  .rmo__draft-pre {
    margin: 0;
    padding: 14px 16px;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 12px;
    line-height: 1.55;
    color: var(--text, #b8b098);
    white-space: pre-wrap;
    word-break: break-word;
  }
  .rmo__draft-foot {
    display: flex;
    gap: 9px;
    padding: 0 16px 14px;
    flex-wrap: wrap;
  }

  .rmo__sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    margin: -1px;
    padding: 0;
    border: 0;
    clip: rect(0 0 0 0);
    overflow: hidden;
    white-space: nowrap;
  }

  /* responsive: collapse the lane grid on narrow viewports */
  @media (max-width: 760px) {
    .rmo__head { grid-template-columns: 1fr; }
    .rmo__ctrl { align-items: flex-start; }
    .rmo__lane { grid-template-columns: 1fr; }
    .rmo__gutter { border-right: 0; border-bottom: 1px solid var(--border, #192030); }
    .rmo__rail { border-left: 0; border-top: 1px solid var(--border, #192030); }
    .rmo__ev-row { grid-template-columns: 1fr; }
  }
</style>
