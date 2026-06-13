<!--
  ConfidenceChip.svelte -- BETA feature "confidence-chip" (#18 Operator
  Co-Pilot Confidence Chip). The ADVISORY co-pilot chip that renders on a HITL
  PENDING row, ABOVE the action buttons, proposing the engine's top-ranked next
  action with a confidence dial -- so a routine SYNC approval collapses to a
  single Ctrl+Enter while OVERRIDE stays exactly as available as today.

  BETA GATE (load-bearing): the whole component is wrapped in
  {#if $betaFlags['confidence-chip']}. When the flag is OFF it renders NOTHING
  and registers NO network call / NO timer / NO SSE handler -- a pure no-op. The
  one read it performs (the breakdown suggestions fetch) is fired lazily from a
  reactive block that only runs while the gate is ON; flipping OFF tears it down.

  ADVISORY-ONLY (the absolute HITL gate is intact):
    - The chip pre-commits NOTHING and removes NO affordance. APPROVE / OVERRIDE
      / DISMISS in the host row are untouched (M6).
    - One-tap accept routes through the EXISTING commit path: the host passes its
      own `commit('approve', ...)` function in as the `onAccept` prop. The chip
      NEVER calls the network itself and NEVER auto-acts -- accept fires only on
      an explicit operator gesture (the Accept button or Ctrl+Enter).
    - Ctrl+Enter = accept (same path as the row's Approve button, M10).
      Esc = collapse the breakdown and hand focus to OVERRIDE (dissent is one key
      away, M6).

  M4 (paired label+color, never color alone): the dial carries the literal
  percent number + the literal verb "recommend <ACTION>"; amber only reinforces.
  Each breakdown bar carries its literal source label + percent. A colorblind
  operator reads the number and the verb.

  M16 (domain-agnostic): the action verb + source keys are rendered FROM DATA /
  from the FROZEN SuggestionWeights enum. NO monitored-project vocabulary.

  M18 (post-hoc): the only read is the existing GET
  /api/decisions/{id}/suggestions (via getDecisionSuggestions). The only
  mutation is the host's commit('approve') -- identical to the Approve button.
  Nothing here sits on the verdict hot path.

  CRAFT (KingMode): the chip shares the row's amber left-rail spine -- it is part
  of the lean-forward grammar, not a bolt-on. The dial is the largest dock
  element (it earns the co-pilot role); everything else stays whisper-quiet. The
  breakdown is a calm height reveal, mirroring the OVERRIDE reveal.

  ASCII-only (cp1252-safe): dash rendered as "--", no smart quotes, no
  em-dashes, no box-drawing.
-->
<script>
  import { betaFlags } from '../../stores/beta.js';
  import { getDecisionSuggestions } from '../../api.js';
  import {
    decisionIdOf,
    envelopeConfidence,
    topActionVerb,
    breakdownFromSuggestions,
    mockBreakdown,
  } from './ConfidenceChip-data.js';

  // The stable flag key (matches registry.js + the beta_flags table + the test).
  const FLAG_KEY = 'confidence-chip';

  /**
   * pending: the same /api/hitl/pending envelope the host HitlPendingRow renders
   * (FROM DATA, M16). Used to resolve the decision id (for the suggestions
   * fetch), the headline confidence, and the recommended action verb.
   * @type {Record<string, any>}
   */
  export let pending = {};

  /**
   * onAccept: the host's EXISTING optimistic-resolve commit, bound so one-tap
   * accept reuses the SAME mutation surface the Approve button calls (M10). The
   * chip NEVER opens the network itself. Signature mirrors
   * HitlPendingRow.commit: (disposition, resolution) => void. When omitted (e.g.
   * a standalone test mount) the chip degrades to an inert button -- it still
   * renders, it just cannot fire accept.
   * @type {((disposition:string, resolution:string)=>any)|null}
   */
  export let onAccept = null;

  /**
   * onDissent: optional hook so the host can move focus to OVERRIDE when the
   * operator presses Esc (M6 -- dissent one key away). Best-effort; when omitted
   * the chip simply collapses the breakdown.
   * @type {(()=>any)|null}
   */
  export let onDissent = null;

  /**
   * disabled: the host's actionsDisabled (expired row / resolve in flight).
   * When true the accept affordance is inert -- the chip never resolves an
   * expired or in-flight row.
   * @type {boolean}
   */
  export let disabled = false;

  // -- Reactive gate read. $on is the single source of truth for "render?". ---
  $: on = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // -- Breakdown view-model. Starts from a synchronous best-effort (envelope
  //    confidence + verb), then upgrades to the live suggestions blend when the
  //    lazy fetch lands. Falls back to realistic mock data when nothing live is
  //    available so the chip is always testable. -----------------------------
  /** @type {ReturnType<typeof mockBreakdown>} */
  let model = mockBreakdown();
  let usedMock = true;

  // Seed the headline from the envelope synchronously (no fetch) so the dial
  // shows a real number on first paint even before suggestions resolve.
  $: {
    const envPct = envelopeConfidence(pending);
    const envVerb = topActionVerb(pending);
    if (envPct != null || envVerb) {
      // Patch the headline only; keep whatever bars we have (mock until live).
      model = {
        ...model,
        confidencePct: envPct != null ? envPct : model.confidencePct,
        verb: envVerb || model.verb,
      };
    }
  }

  // -- Lazy suggestions fetch (GATED: only fires while the flag is ON). One
  //    fetch per decision id; re-keys when the row changes. OFF => no fetch. ---
  let _fetchedFor = null;
  $: if (on) {
    const did = decisionIdOf(pending);
    if (did && did !== _fetchedFor) {
      _fetchedFor = did;
      loadSuggestions(did);
    }
  } else {
    // Flag flipped OFF: reset so a later ON re-fetches; tear down open reveal.
    _fetchedFor = null;
    open = false;
  }

  /** @param {string} decisionId */
  async function loadSuggestions(decisionId) {
    try {
      const suggestions = await getDecisionSuggestions(decisionId);
      const live = breakdownFromSuggestions(suggestions);
      if (live) {
        model = live;
        usedMock = false;
        return;
      }
      // Empty/unusable array -- keep the mock-seeded model.
      usedMock = true;
    } catch {
      // Server down / 404 / network -- degrade to mock (never blocks the row).
      usedMock = true;
    }
  }

  // -- Breakdown reveal state (mirrors the OVERRIDE reveal). ------------------
  let open = false;
  /** @type {HTMLButtonElement|undefined} */
  let dialEl;

  function toggle() {
    open = !open;
  }
  function collapse() {
    open = false;
  }

  // -- Accept (one-tap). Routes through the host's EXISTING commit; NEVER the
  //    network here, NEVER auto-acts -- fires only on explicit gesture. -------
  $: acceptDisabled = disabled || typeof onAccept !== 'function';

  function accept() {
    if (acceptDisabled) return;
    // resolution echoes the recommended verb so the executor applies it (this
    // mirrors HitlPendingRow.onApprove, which resolves with the envelope action).
    const resolution = (model.verb || topActionVerb(pending) || 'approve').toString();
    onAccept('approve', resolution);
  }

  // -- Keyboard: Ctrl/Cmd+Enter = accept; Esc = collapse + dissent (focus
  //    OVERRIDE). Bound on the chip root so the gestures work from the dial or
  //    the body. The host row may also bind Ctrl+Enter; both reach the same
  //    commit, so a double-bind is harmless (accept is idempotent at the gate
  //    -- the row culls on the first resolve). ---------------------------------
  /** @param {KeyboardEvent} e */
  function onKeydown(e) {
    if (!on) return; // belt-and-suspenders: no handler effect when OFF
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      accept();
      return;
    }
    if (e.key === 'Escape') {
      // Esc always means "dissent": collapse the reveal, then hand off to
      // OVERRIDE. Even with the breakdown closed, Esc routes to dissent (M6).
      const wasOpen = open;
      if (wasOpen) {
        collapse();
        e.preventDefault();
      }
      if (typeof onDissent === 'function') {
        onDissent();
        e.preventDefault();
      }
    }
  }

  // dial role=button: Enter/Space toggle the breakdown reveal.
  /** @param {KeyboardEvent} e */
  function onDialKeydown(e) {
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
      e.preventDefault();
      toggle();
    }
  }

  // -- SVG arc geometry (the partial 270deg dial -- bespoke, not a full donut).
  //    Total arc length of the 270deg sweep at r=48 is ~226px. We paint
  //    confidencePct of that, capped, with the remainder transparent. ---------
  const ARC_LEN = 226;
  $: pct = Number.isFinite(Number(model.confidencePct))
    ? Math.min(100, Math.max(0, Math.round(Number(model.confidencePct))))
    : null;
  $: dashArray = pct == null ? `0 ${ARC_LEN}` : `${(pct / 100) * ARC_LEN} ${ARC_LEN}`;

  // Upper-cased verb for the paired text signal (the literal carries the
  // meaning; amber only reinforces -- M4).
  $: verbUpper = (model.verb || 'approve').toString().toUpperCase();

  // A literal confidence-state word so the signal survives with color stripped
  // (paired label, M4): high / moderate / low, derived from the same number.
  $: confWord =
    pct == null ? 'unknown' : pct >= 75 ? 'high' : pct >= 50 ? 'moderate' : 'low';

  // Full aria-label for the dial (button): number + verb + affordance hint.
  $: dialAria =
    pct == null
      ? `Confidence unavailable, recommend ${verbUpper}; activate for source breakdown`
      : `Confidence ${pct} percent (${confWord}), recommend ${verbUpper}; activate for source breakdown`;

  // Heading for the breakdown reveal.
  $: breakdownHead =
    pct == null ? 'Blended source weights' : `Why ${pct}% -- blended source weights`;
</script>

{#if on}
  <!-- The chip wrapper carries an accessible group name so assistive tech reads
       it as the co-pilot recommendation region. The keydown handler hosts the
       Ctrl+Enter / Esc gestures. -->
  <div
    class="cc"
    role="group"
    aria-label="Co-Pilot recommendation -- advisory only, the operator decision is still required"
    data-beta="confidence-chip"
    data-mock={usedMock ? 'true' : 'false'}
    on:keydown={onKeydown}
  >
    <div class="cc__chip">
      <!-- DIAL column: role=button reveals the breakdown. Partial 270deg arc. -->
      <div class="cc__dialwrap">
        <button
          bind:this={dialEl}
          type="button"
          class="cc__dial"
          aria-expanded={open}
          aria-controls="cc-breakdown"
          aria-label={dialAria}
          on:click={toggle}
          on:keydown={onDialKeydown}
        >
          <svg width="124" height="124" viewBox="0 0 124 124" aria-hidden="true" focusable="false">
            <!-- track arc: 270deg, gap toward lower-left (bespoke ring) -->
            <path
              d="M 27.7 96.3 A 48 48 0 1 1 96.3 96.3"
              fill="none"
              stroke="var(--calm-hairline, #192030)"
              stroke-width="11"
              stroke-linecap="round"
            />
            <!-- value arc: pct of the 270deg sweep, rich amber -->
            <path
              d="M 27.7 96.3 A 48 48 0 1 1 96.3 96.3"
              fill="none"
              stroke="var(--badge-ar-border, #d97706)"
              stroke-width="11"
              stroke-linecap="round"
              stroke-dasharray={dashArray}
            />
            <!-- the literal percent number (paired text -- carries the signal) -->
            {#if pct == null}
              <text x="62" y="64" text-anchor="middle" class="cc__pct" font-size="20">--</text>
            {:else}
              <text x="62" y="60" text-anchor="middle" class="cc__pct" font-size="30">{pct}</text>
              <text x="62" y="60" text-anchor="middle" class="cc__pctsign" font-size="30" dx="22">%</text>
            {/if}
            <text x="62" y="82" text-anchor="middle" class="cc__pctlabel" font-size="9">CONFIDENCE</text>
          </svg>
        </button>
      </div>

      <!-- RECOMMENDATION column -->
      <div class="cc__body">
        <div class="cc__tagrow">
          <span class="cc__tag">Co-Pilot recommends</span>
          {#if usedMock}
            <!-- paired text state: the operator must KNOW this is sample data -->
            <span class="cc__mock" title="No live suggestions for this row -- showing sample data">SAMPLE DATA</span>
          {/if}
        </div>

        <!-- PAIRED text signal: the literal verb carries meaning without color -->
        <div class="cc__verb">
          recommend <span class="cc__verb-action">{verbUpper}</span>
        </div>

        {#if model.rationale}
          <div class="cc__prose">{model.rationale}</div>
        {/if}
        {#if Number.isFinite(Number(model.precedent))}
          <div class="cc__prose cc__prose--quiet">matches {model.precedent} prior approvals on this pattern</div>
        {/if}

        <!-- one-tap accept (routes through the host's commit; never the network
             here, never auto-acts). Always paired with the keyboard hint. -->
        <div class="cc__actions">
          <button
            type="button"
            class="cc__accept"
            on:click={accept}
            disabled={acceptDisabled}
            aria-label={`Accept recommendation: ${verbUpper}`}
          >
            Accept {verbUpper}
          </button>
          <span class="cc__hint">
            <kbd class="cc__kbd">Ctrl+Enter</kbd> accept
            &middot; <kbd class="cc__kbd">Enter</kbd> on dial = why
            &middot; <kbd class="cc__kbd">Esc</kbd> dissent (OVERRIDE)
          </span>
        </div>
      </div>
    </div>

    <!-- BREAKDOWN reveal: passive role=note (AdvisoryChip precedent), height
         reveal. Each bar pairs a literal source label + percent (never color
         only). Advisory -- it pre-commits NOTHING. -->
    <div
      id="cc-breakdown"
      class="cc__breakdown"
      class:is-open={open}
      role="note"
      aria-label="Confidence source breakdown -- blended from the frozen source weights"
    >
      <div class="cc__bk-head">{breakdownHead}</div>

      {#each model.bars as bar (bar.key)}
        <div class="cc__bar">
          <span class="cc__bar-label">{bar.key}</span>
          <span class="cc__bar-track">
            <span class="cc__bar-fill" style={`width:${bar.pct}%`}></span>
          </span>
          <span class="cc__bar-pct">{bar.pct}%</span>
        </div>
      {/each}

      <p class="cc__bk-foot">
        {usedMock
          ? 'Sample weights (no live suggestions for this row). Advisory only -- this does not pre-commit the gate.'
          : 'Frozen SuggestionWeights blend. Advisory only -- this does not pre-commit the gate. Esc collapses and returns focus to OVERRIDE.'}
      </p>
    </div>
  </div>
{/if}

<style>
  /* The chip shares the row's amber left-rail grammar -- part of the lean-
     forward spine, not a bolt-on widget. */
  .cc {
    display: flex;
    flex-direction: column;
    width: 100%;
    box-sizing: border-box;
  }

  .cc__chip {
    display: flex;
    align-items: stretch;
    gap: var(--space-5, 14px);
    border-left: 3px solid var(--badge-ar-border, #d97706);
    background: var(--calm-accent-wash, rgba(245, 158, 11, 0.09));
    border-radius: var(--radius-soft, 4px);
    padding: var(--space-4, 10px) var(--space-5, 14px);
    margin-bottom: var(--space-3, 6px);
  }

  /* DIAL -- left-anchored, the largest dock element (earns the co-pilot role). */
  .cc__dialwrap { flex: 0 0 auto; }
  .cc__dial {
    appearance: none;
    display: block;
    background: transparent;
    border: 0;
    padding: 0;
    cursor: pointer;
    border-radius: 50%;
  }
  .cc__dial:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid)
      var(--focus-ring-color, var(--accent, #f59e0b));
    outline-offset: 4px;
  }
  .cc__dial svg { display: block; }
  .cc__pct {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-weight: 750;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.02em;
    fill: var(--calm-ink-loud, #e8e0cc);
  }
  .cc__pctsign {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-weight: 600;
    fill: var(--calm-ink-chrome, #8a8068);
  }
  .cc__pctlabel {
    font-family: var(--ff-mono, ui-monospace, monospace);
    fill: var(--calm-ink-chrome, #8a8068);
    letter-spacing: 0.16em;
  }

  /* RECOMMENDATION column */
  .cc__body {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: var(--space-2, 4px);
  }
  .cc__tagrow { display: flex; align-items: baseline; gap: var(--space-3, 6px); flex-wrap: wrap; }
  .cc__tag {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: var(--fs-chrome, 11px);
    font-weight: 700;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, #8a8068);
  }
  /* SAMPLE DATA tag -- paired text so the mock state is never implicit. */
  .cc__mock {
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

  /* the literal recommend verb -- paired text, carries the signal w/o color */
  .cc__verb {
    font-family: var(--ff-system, system-ui, sans-serif);
    font-size: 17px;
    font-weight: 700;
    color: var(--calm-ink-loud, #e8e0cc);
    letter-spacing: 0.01em;
  }
  .cc__verb-action { color: var(--badge-ar-fg, #d97706); }
  .cc__prose {
    font-size: var(--fs-meta, 13px);
    color: var(--calm-ink, #b8b098);
  }
  .cc__prose--quiet { color: var(--calm-ink-quiet, #948870); }

  .cc__actions {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-3, 6px);
    margin-top: var(--space-2, 4px);
  }
  /* the one-tap accept -- amber primary, mirrors the row's Approve affordance. */
  .cc__accept {
    appearance: none;
    font-family: var(--ff-system, system-ui, sans-serif);
    font-size: var(--fs-meta, 13px);
    font-weight: 600;
    line-height: 1;
    padding: 7px 14px;
    border-radius: var(--radius-sharp, 2px);
    cursor: pointer;
    background: var(--badge-ar-border, #d97706);
    color: #fffbeb;
    border: 1px solid #b45309;
    transition: background var(--t-calm, 180ms ease), border-color var(--t-calm, 180ms ease);
  }
  .cc__accept:hover:not(:disabled) { background: #b45309; }
  .cc__accept:disabled { cursor: default; opacity: 0.5; }
  .cc__accept:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid)
      var(--focus-ring-color, var(--accent, #f59e0b));
    outline-offset: 2px;
  }
  .cc__hint {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: var(--fs-chrome, 11px);
    color: var(--calm-ink-quiet, #948870);
    letter-spacing: 0.02em;
  }
  .cc__kbd {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 10px;
    color: var(--calm-ink-chrome, #8a8068);
    background: var(--calm-surface-alt, #0b1018);
    border: 1px solid var(--calm-hairline, #192030);
    border-radius: 3px;
    padding: 1px 5px;
  }

  /* BREAKDOWN -- calm height reveal (mirrors the OVERRIDE reveal). */
  .cc__breakdown {
    overflow: hidden;
    max-height: 0;
    opacity: 0;
    transition: max-height var(--t-calm, 180ms ease), opacity var(--t-calm, 180ms ease),
      margin var(--t-calm, 180ms ease);
    border-left: 1px dashed var(--calm-hairline-hi, rgba(245, 158, 11, 0.25));
    margin: 0 0 0 var(--space-2, 4px);
    padding-left: 0;
  }
  .cc__breakdown.is-open {
    max-height: 320px;
    opacity: 1;
    margin: var(--space-3, 6px) 0 var(--space-1, 2px) var(--space-2, 4px);
    padding-left: var(--space-5, 14px);
  }
  .cc__bk-head {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: var(--fs-chrome, 11px);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--calm-ink-quiet, #948870);
    margin-bottom: var(--space-3, 6px);
  }
  .cc__bar {
    display: grid;
    grid-template-columns: 14ch 1fr 4ch;
    align-items: center;
    gap: var(--space-3, 6px);
    margin-bottom: var(--space-3, 6px);
  }
  .cc__bar-label {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: var(--fs-meta, 13px);
    color: var(--calm-ink, #b8b098);
  }
  .cc__bar-track {
    height: 8px;
    background: var(--calm-surface-alt, #0b1018);
    border-radius: 2px;
    overflow: hidden;
  }
  .cc__bar-fill {
    display: block;
    height: 100%;
    background: var(--badge-ar-border, #d97706);
    border-radius: 2px;
  }
  .cc__bar-pct {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: var(--fs-meta, 13px);
    font-weight: 700;
    color: var(--calm-ink-loud, #e8e0cc);
    font-variant-numeric: tabular-nums;
    text-align: right;
  }
  .cc__bk-foot {
    font-size: var(--fs-chrome, 11px);
    color: var(--calm-ink-quiet, #948870);
    font-style: italic;
    margin: var(--space-2, 4px) 0 0;
  }

  /* Reduced motion: the reveal snaps instead of sliding (M17). */
  :global(html[data-motion='reduce']) .cc__breakdown { transition: none; }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .cc__breakdown { transition: none; }
  }
</style>
