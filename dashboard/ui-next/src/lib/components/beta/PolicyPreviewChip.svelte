<!--
  PolicyPreviewChip.svelte -- BETA feature "policy-preview-chip" (#21 -- "what
  governance will do, read from the corpus"). The QUIETEST element at its site:
  an advisory chip that, for the SELECTED session, shows the likely verdict from
  the historical decision corpus -- rendered at the SYNC/ASYNC decision point so
  the operator can decide with the corpus's memory in view.

  BETA GATE (load-bearing): the whole component is wrapped in
  {#if $betaFlags['policy-preview-chip']}. When the flag is OFF it renders
  NOTHING and registers NO network call / NO timer / NO SSE handler -- a pure
  no-op. The single read (the corpus-prediction fetch) is fired lazily from a
  reactive block that only runs while the gate is ON; flipping OFF tears it down.

  READ-ONLY PREVIEW (the absolute HITL gate + M18 are intact):
    - The chip NEVER calls governance.evaluate / the live engine. Its one read is
      the additive, post-hoc GET /api/governance/predict (a retrieval over the
      EXISTING decision corpus). Nothing here sits on the verdict hot path (M18).
    - It pre-selects NOTHING: it emits no selection event, removes no affordance,
      and the SYNC/ASYNC toggle is untouched. The operator's mode choice never
      alters this readout, and this readout never alters the mode.

  POLARITY (G2): the corpus is polarity-filtered SERVER-SIDE (project_slug NOT IN
  the SM slug set AND session_id != SM-self). The dropped-self tally is rendered
  as a VISIBLE feature (the "SM-self excluded N" readout) so suppression is
  legible, never silent.

  M4 (paired label+color, never color alone): the dominant action VERB word +
  the share fraction (14/15) + n carry ALL meaning; the band only drives a
  decorative left-edge tint that REINFORCES the literal text. A colorblind
  operator reads the number and the word. Strip the tint -- the signal survives.

  M16 (domain-agnostic): the action verb, shape hash, layer label, and session id
  are rendered FROM DATA. NO monitored-project vocabulary is baked in.

  ACCESSIBILITY: the root is role="note" (passive -- never "alert", it is a
  preview not an alarm). The ONLY interactive node is the expand <button> (a real
  button in tab order, Enter/Space toggles the histogram, Esc collapses). The
  global 2px focus ring applies. Honors prefers-reduced-motion (the reveal snaps
  instead of sliding).

  CRAFT (KingMode): mirrors AdvisoryChip's M8 dashed NON-VERDICT grammar (1px
  dashed hairline, low-saturation calm wash, italic quiet ink) and
  ConfidenceChip's SAMPLE-DATA degrade idiom -- it is the calmest element at the
  dock header, a preview, not a verdict.

  ASCII-only (cp1252-safe): dash rendered as "--", no smart quotes, no
  em-dashes, no box-drawing.
-->
<script>
  import { betaFlags } from '../../stores/beta.js';
  import { getGovernancePredict } from '../../api.js';
  import {
    ACTION_ORDER,
    normalizePrediction,
    readFor,
    matchLabel,
    ariaFor,
    mockPrediction,
    mockColdPrediction,
  } from './PolicyPreviewChip-data.js';

  // The stable flag key (matches registry.js + the beta_flags table + the test).
  const FLAG_KEY = 'policy-preview-chip';

  /**
   * sessionId: the selected session whose recent command-shapes the preview is
   * bound to (FROM DATA, M16). When null/empty (ALL governed sessions, or a test
   * mount with no scope) the chip falls back to its deterministic mock fixture so
   * it is always paintable. The preview is bound to the SESSION, never to the
   * operator's SYNC/ASYNC choice -- toggling mode never re-renders the chip.
   * @type {string|null}
   */
  export let sessionId = null;

  /**
   * sessionLabel: a domain-agnostic attribution label (project_slug or raw id)
   * the host already resolved FROM DATA. Display-only.
   * @type {string}
   */
  export let sessionLabel = '';

  /**
   * coldOverride: a test/seed hook to force the cold ("no history") fixture when
   * falling back to mock (e.g. to exercise the novel-shape path). Default false.
   * @type {boolean}
   */
  export let coldOverride = false;

  // -- Reactive gate read. `on` is the single source of truth for "render?". ---
  $: on = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // -- View-model. Starts from a realistic mock so the chip paints on first
  //    frame; upgrades to the live corpus prediction when the lazy fetch lands,
  //    and falls back to mock on any error so it is never empty/broken. --------
  let model = normalizePrediction(mockPrediction());
  let usedMock = true;

  // -- Expand (histogram reveal) state. The ONLY interactive affordance. -------
  let open = false;
  /** @type {HTMLButtonElement|undefined} */
  let expandEl;

  // -- Lazy corpus-prediction fetch (GATED: only fires while the flag is ON).
  //    One fetch per session scope; re-keys when the selected session changes.
  //    OFF => no fetch, reveal torn down. -------------------------------------
  let _fetchedFor = null;
  $: if (on) {
    const key = sessionId == null ? '' : String(sessionId);
    if (key !== _fetchedFor) {
      _fetchedFor = key;
      loadPrediction(sessionId);
    }
  } else {
    // Flag flipped OFF: reset so a later ON re-fetches; tear down the reveal.
    _fetchedFor = null;
    open = false;
  }

  /**
   * Fetch the corpus prediction for the selected session, then normalize it.
   * Degrades to the deterministic mock fixture on any error / empty corpus (the
   * server returns mock:true OR n:0 -> the chip paints SAMPLE DATA / NO HISTORY,
   * never a broken or misleadingly-live chip).
   * @param {string|null} sid
   */
  async function loadPrediction(sid) {
    try {
      const raw = await getGovernancePredict({ session_id: sid });
      // A usable live payload has a numeric n (>= 0) and an action_hist object.
      const looksLive =
        raw && typeof raw === 'object' && raw.mock !== true && raw.action_hist != null;
      if (looksLive) {
        model = normalizePrediction(raw);
        // n === 0 with match none is a real "cold" live read -- still live data.
        usedMock = false;
        return;
      }
      // Server degraded (mock:true) or unusable -> deterministic mock.
      model = normalizePrediction(
        coldOverride ? mockColdPrediction(sid || '') : mockPrediction(sid || ''),
      );
      usedMock = true;
    } catch {
      // Server down / network -> deterministic mock (never blocks the dock).
      model = normalizePrediction(
        coldOverride ? mockColdPrediction(sid || '') : mockPrediction(sid || ''),
      );
      usedMock = true;
    }
  }

  // -- Derived view tells. ----------------------------------------------------
  $: isCold = model.n === 0;
  $: read = readFor(model.band);
  $: meanText = model.mean_conf == null ? '--' : model.mean_conf.toFixed(2);
  $: layerText = model.dominant_layer || '--';
  $: ariaLabel = ariaFor(model);

  // -- Expand toggle (Enter/Space via native button; click too). --------------
  function toggle() {
    open = !open;
  }
  function collapse() {
    open = false;
  }

  // Esc collapses the reveal from anywhere inside the chip (M6/M8 idiom).
  /** @param {KeyboardEvent} e */
  function onKeydown(e) {
    if (!on) return; // belt-and-suspenders: no handler effect when OFF
    if (e.key === 'Escape' && open) {
      collapse();
      e.preventDefault();
      // Return focus to the expand control so keyboard context is preserved.
      if (expandEl) expandEl.focus();
    }
  }
</script>

{#if on}
  <!-- role="note": a passive advisory preview, NEVER an alert. The keydown
       handler hosts the Esc-collapse gesture. data-mock surfaces the SAMPLE
       DATA state for the test + assistive tech. -->
  <div
    class="ppc"
    role="note"
    data-beta="policy-preview-chip"
    data-band={model.band}
    data-mock={usedMock ? 'true' : 'false'}
    aria-label={ariaLabel}
    on:keydown={onKeydown}
  >
    <!-- TAG ROW: CORPUS PREVIEW + ADVISORY paired text + (SAMPLE DATA degraded) -->
    <div class="ppc__tagrow">
      <span class="ppc__tag">corpus preview</span>
      <span class="ppc__advisory">ADVISORY -- your decision stands</span>
      {#if usedMock}
        <!-- paired text state: the operator must KNOW this is sample data. -->
        <span class="ppc__mock" title="Server unavailable -- showing sample data, not live">SAMPLE DATA</span>
      {/if}
      {#if sessionLabel}
        <span class="ppc__scope" title="preview scope (rendered from data)">{sessionLabel}</span>
      {/if}
    </div>

    <!-- HEADLINE: a literal sentence carrying ALL meaning (M4). -->
    {#if isCold}
      <div class="ppc__headline">
        <span class="ppc__key">NO HISTORY</span>
        <span class="ppc__sep">--</span>
        <span class="ppc__read">novel shape, earns attention.</span>
        No precedent in the corpus for this command-shape; do not assume routine.
      </div>
    {:else}
      <div class="ppc__headline">
        <span class="ppc__key">CORPUS:</span>
        <span class="ppc__num">{model.dominant_count}/{model.n}</span>
        <span class="ppc__verb" data-action={model.dominant_action}>{model.dominant_action}</span>
        <span class="ppc__sep">--</span>
        mean <span class="ppc__num">{meanText}</span>
        <span class="ppc__sep">--</span>
        <span class="ppc__num">{layerText}</span>
      </div>
      <div class="ppc__meta">
        <span class="ppc__metaitem"><b>{read}</b></span>
      </div>
    {/if}

    <!-- META LINE: n + match kind + the polarity (self-exclusion) readout +
         the optional expand toggle (the only interactive node). -->
    <div class="ppc__meta">
      <span class="ppc__metaitem">n <b>{model.n}</b></span>
      <span class="ppc__metaitem">{matchLabel(model.match_kind)}</span>
      <!-- Polarity made visible (G2): the dropped SM-self count is always shown,
           so suppression is a legible feature, never silent. -->
      <span class="ppc__metaitem">SM-self excluded <b>{model.excluded_self}</b></span>
      {#if !isCold}
        <button
          bind:this={expandEl}
          type="button"
          class="ppc__expand"
          aria-expanded={open}
          aria-controls="ppc-hist"
          on:click={toggle}
        >
          {open ? 'hide histogram' : 'show histogram'}
        </button>
      {/if}
    </div>

    <!-- HISTOGRAM reveal: passive role=note, calm height reveal. Each bar pairs a
         literal action label + count + percent (never color only). -->
    {#if !isCold}
      <div
        id="ppc-hist"
        class="ppc__hist"
        class:is-open={open}
        role="note"
        aria-label="Per-action history -- each bar is a literal label, count, and percent"
      >
        <div class="ppc__hist-head">action histogram -- {model.n} matched decisions</div>
        {#each ACTION_ORDER as act (act)}
          {@const cnt = model.action_hist[act] || 0}
          {@const share = model.n ? Math.round((cnt / model.n) * 100) : 0}
          <div class="ppc__bar">
            <span class="ppc__bar-label">{act}</span>
            <span class="ppc__bar-track">
              <span class="ppc__bar-fill" data-action={act} style={`width:${share}%`}></span>
            </span>
            <span class="ppc__bar-num">{cnt} / {share}%</span>
          </div>
        {/each}
        <p class="ppc__hist-foot">
          {usedMock
            ? 'Sample data (server unavailable). Advisory only -- this reads the corpus, it does not pre-decide your mode.'
            : 'Read from the decision corpus, polarity-filtered. Advisory only -- this does not pre-decide your mode. Esc collapses.'}
        </p>
      </div>
    {/if}
  </div>
{/if}

<style>
  /* The chip mirrors AdvisoryChip's M8 dashed NON-VERDICT grammar: 1px dashed
     hairline, low-saturation calm wash, italic quiet ink. The QUIETEST element
     at its site -- a preview, not a verdict. */
  .ppc {
    display: block;
    width: 100%;
    box-sizing: border-box;
    border: 1px dashed var(--calm-hairline-hi, rgba(245, 158, 11, 0.25));
    border-radius: var(--radius-soft, 4px);
    background: var(--calm-accent-wash, rgba(245, 158, 11, 0.09));
    padding: var(--space-4, 10px) var(--space-5, 14px);
  }
  /* Decorative left-edge tint -- REINFORCES the literal verb (M4). The literal
     text always carries the meaning; the edge is decorative.
       calm  = routine (ALLOW-dominant)  -> green
       mixed = neutral (no clear winner) -> chrome ink
       block = BLOCK/INTERVENE history   -> amber edge (earns a look)
       cold  = no history                -> dashed neutral hairline */
  .ppc[data-band='calm'] { border-left: 3px solid var(--c-allow, #22c55e); }
  .ppc[data-band='mixed'] { border-left: 3px solid var(--calm-ink-chrome, #8a8068); }
  .ppc[data-band='block'] { border-left: 3px solid var(--badge-ar-border, #d97706); }
  .ppc[data-band='cold'] { border-left: 3px dashed var(--calm-hairline, #192030); }

  .ppc__tagrow {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-3, 6px);
    margin-bottom: var(--space-2, 4px);
  }
  .ppc__tag {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, #8a8068);
  }
  /* "ADVISORY -- your decision stands" paired text (AdvisoryChip idiom). */
  .ppc__advisory {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--calm-ink-quiet, #948870);
    border: 1px dashed var(--calm-hairline-hi, rgba(245, 158, 11, 0.25));
    border-radius: 3px;
    padding: 1px 6px;
  }
  /* "SAMPLE DATA" paired-text tag (ConfidenceChip usedMock idiom). */
  .ppc__mock {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--badge-ar-fg, #d97706);
    border: 1px solid var(--badge-ar-border, #d97706);
    border-radius: 3px;
    padding: 0 5px;
  }
  /* domain-agnostic scope label (project_slug / id) -- rendered FROM DATA. */
  .ppc__scope {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 10px;
    letter-spacing: 0.04em;
    color: var(--calm-ink-quiet, #948870);
    margin-left: auto;
    max-width: 24ch;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* HEADLINE -- a literal sentence carrying ALL meaning (M4). */
  .ppc__headline {
    font-family: var(--ff-system, system-ui, sans-serif);
    font-size: 15px;
    line-height: 1.45;
    color: var(--calm-ink-loud, #e8e0cc);
    font-style: italic;
  }
  .ppc__key {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-style: normal;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: var(--calm-ink-chrome, #8a8068);
    font-size: 12px;
    margin-right: 2px;
  }
  /* the dominant verb -- the paired text signal. Color REINFORCES; the word
     itself carries meaning if color is stripped (M4). */
  .ppc__verb {
    font-style: normal;
    font-weight: 800;
    letter-spacing: 0.02em;
  }
  .ppc__verb[data-action='ALLOW'] { color: var(--c-allow, #22c55e); }
  .ppc__verb[data-action='SUGGEST'] { color: var(--c-suggest, #84cc16); }
  .ppc__verb[data-action='GUIDE'] { color: var(--c-guide, #eab308); }
  .ppc__verb[data-action='INTERVENE'] { color: var(--c-intervene, #f97316); }
  .ppc__verb[data-action='BLOCK'] { color: var(--c-block, #ef4444); }
  .ppc__num {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-style: normal;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    color: var(--calm-ink-loud, #e8e0cc);
  }
  .ppc__sep {
    color: var(--calm-ink-quiet, #948870);
    font-style: normal;
    padding: 0 4px;
  }
  .ppc__read {
    font-style: normal;
    color: var(--calm-ink, #b8b098);
    font-weight: 600;
  }

  /* secondary line(s): the plain-English read + n + match + polarity readout. */
  .ppc__meta {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-4, 10px);
    margin-top: var(--space-3, 6px);
  }
  .ppc__metaitem {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 11px;
    letter-spacing: 0.02em;
    color: var(--calm-ink-quiet, #948870);
    font-variant-numeric: tabular-nums;
  }
  .ppc__metaitem b {
    color: var(--calm-ink, #b8b098);
    font-weight: 700;
  }

  /* the optional EXPAND toggle -- the ONLY interactive element. A real <button>
     in tab order with the global 2px focus ring. */
  .ppc__expand {
    appearance: none;
    cursor: pointer;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 11px;
    letter-spacing: 0.04em;
    color: var(--calm-ink-chrome, #8a8068);
    background: transparent;
    border: 1px solid var(--calm-hairline, #192030);
    border-radius: var(--radius-sharp, 2px);
    padding: 3px 9px;
    transition: background var(--t-calm, 180ms ease), border-color var(--t-calm, 180ms ease);
  }
  .ppc__expand:hover { background: var(--calm-surface-hover, #131c2a); }
  .ppc__expand:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid)
      var(--focus-ring-color, var(--accent, #f59e0b));
    outline-offset: 2px;
  }

  /* HISTOGRAM reveal -- calm height reveal (mirrors ConfidenceChip breakdown). */
  .ppc__hist {
    overflow: hidden;
    max-height: 0;
    opacity: 0;
    transition: max-height var(--t-calm, 180ms ease), opacity var(--t-calm, 180ms ease),
      margin var(--t-calm, 180ms ease);
    border-left: 1px dashed var(--calm-hairline-hi, rgba(245, 158, 11, 0.25));
    margin: 0 0 0 var(--space-1, 2px);
    padding-left: 0;
  }
  .ppc__hist.is-open {
    max-height: 360px;
    opacity: 1;
    margin: var(--space-4, 10px) 0 var(--space-1, 2px) var(--space-1, 2px);
    padding-left: var(--space-5, 14px);
  }
  .ppc__hist-head {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 10px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--calm-ink-quiet, #948870);
    margin-bottom: var(--space-3, 6px);
  }
  .ppc__bar {
    display: grid;
    grid-template-columns: 11ch 1fr 7ch;
    align-items: center;
    gap: var(--space-3, 6px);
    margin-bottom: var(--space-3, 6px);
  }
  .ppc__bar-label {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.04em;
    color: var(--calm-ink, #b8b098);
  }
  .ppc__bar-track {
    height: 8px;
    background: var(--calm-surface-alt, #0b1018);
    border-radius: 2px;
    overflow: hidden;
  }
  .ppc__bar-fill {
    display: block;
    height: 100%;
    border-radius: 2px;
    background: var(--calm-ink-chrome, #8a8068);
  }
  .ppc__bar-fill[data-action='ALLOW'] { background: var(--c-allow, #22c55e); }
  .ppc__bar-fill[data-action='SUGGEST'] { background: var(--c-suggest, #84cc16); }
  .ppc__bar-fill[data-action='GUIDE'] { background: var(--c-guide, #eab308); }
  .ppc__bar-fill[data-action='INTERVENE'] { background: var(--c-intervene, #f97316); }
  .ppc__bar-fill[data-action='BLOCK'] { background: var(--c-block, #ef4444); }
  .ppc__bar-num {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 12px;
    font-weight: 700;
    color: var(--calm-ink-loud, #e8e0cc);
    font-variant-numeric: tabular-nums;
    text-align: right;
  }
  .ppc__hist-foot {
    font-family: var(--ff-system, system-ui, sans-serif);
    font-size: 12px;
    font-style: italic;
    color: var(--calm-ink-quiet, #948870);
    margin: var(--space-3, 6px) 0 0;
  }

  /* Reduced motion: the reveal snaps instead of sliding (M17). */
  :global(html[data-motion='reduce']) .ppc__hist { transition: none; }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .ppc__hist { transition: none; }
  }
</style>
