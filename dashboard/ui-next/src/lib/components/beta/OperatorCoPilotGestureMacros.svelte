<!--
  OperatorCoPilotGestureMacros.svelte -- BETA feature
  "operator-co-pilot-gesture-macros" (#17 Operator Co-Pilot: one-tap ranked
  next-action macro palette for a HITL PENDING row). The MULTI-ACTION superset
  of the #18 ConfidenceChip: instead of a single confidence dial it surfaces a
  ranked LADDER of 3-5 next-action macros (APPROVE / TUNE / ESCALATE / SNOOZE),
  each one-tap, each paired with a literal confidence WORD + a BINDING/ADVISORY
  text tag.

  BETA GATE (load-bearing): the whole component is wrapped in
  {#if $betaFlags['operator-co-pilot-gesture-macros']}. When the flag is OFF it
  renders NOTHING and registers NO network call / NO timer / NO SSE handler -- a
  pure no-op. The one read it performs (the lazy suggestions fetch) fires only
  from a reactive block that runs while the gate is ON; flipping OFF tears it
  down. It mounts IN PLACE of the #18 chip (the host shows one OR the other,
  never both -- see the wire instruction).

  ABSOLUTE HITL GATE INTACT (ADR-18 M3/M8): the palette pre-commits NOTHING and
  removes NO host affordance. APPROVE / OVERRIDE / DISMISS in the host row are
  untouched (M6).
    - APPROVE is the ONLY binding macro. One-tap accept routes through the
      EXISTING commit path: the host passes its own commit() in as `onApprove`.
      The palette NEVER calls the network itself and NEVER auto-acts -- a macro
      fires only on an explicit operator gesture (a tap or a key).
    - TUNE pre-stages the host OVERRIDE picker (calls `onTune`, which the host
      maps to toggleOverride) -- no server write.
    - ESCALATE moves focus to the host's escalation / OVERRIDE control
      (`onEscalate`) -- no new disposition, no server write.
    - SNOOZE dims this row client-side for a window (localStorage marker) and
      asks the host to fade it (`onSnooze`) -- no server write.
    - A dimmed (low-confidence) macro NEVER auto-fires; it requires an explicit
      tap or key.

  KEYBOARD (M17): the palette root is focusable. Down/Up move the ranked
  highlight across the full list (headline + ladder), Enter fires the
  highlighted macro, Ctrl/Cmd+Enter fires the top APPROVE directly, Esc collapses
  and hands focus to the host dissent control (`onDissent`) -- dissent one key
  away (M6).

  M4/M5 (paired label+color, never color alone): every action carries a literal
  VERB + a tabular PERCENT + a confidence WORD (high/moderate/low) + a
  BINDING/ADVISORY text tag. Low-confidence (<60%) entries are DIMMED AND carry a
  literal "low confidence" cue -- the dimming emphasises the label, it is never
  the sole signal. The provenance state tag (SAMPLE DATA / FALLBACK RANKING /
  LIVE) is always explicit.

  M16 (domain-agnostic): the action verbs + rationale are generic operator-intent
  taxonomy carried FROM the data module. NO monitored-project vocabulary.

  M18 (post-hoc): the only read is the EXISTING GET
  /api/decisions/{id}/suggestions (via getDecisionSuggestions). The only mutation
  is the host's commit('approve') -- identical to the Approve button. Nothing
  here sits on the verdict hot path.

  M15 / G2 (polarity): self-exclude is upstream -- HitlDock filters the SM's own
  session before any row is constructed, so the palette only ever renders on a
  governed (non-SM) row. It performs no session query of its own.

  ASCII-only (cp1252-safe): dash rendered as "--", no smart quotes, no
  em-dashes, no box-drawing.
-->
<script>
  import { betaFlags } from '../../stores/beta.js';
  import { getDecisionSuggestions } from '../../api.js';
  import {
    toPct,
    confWord,
    envelopeConfidence,
    topActionVerb,
    decisionIdOf,
    rankedFromSuggestions,
    mockRanked,
    persistSnooze,
  } from './OperatorCoPilotGestureMacros-data.js';

  // The stable flag key (matches registry.js + the beta_flags table + the test).
  const FLAG_KEY = 'operator-co-pilot-gesture-macros';

  /**
   * pending: the same /api/hitl/pending envelope the host HitlPendingRow renders
   * (FROM DATA, M16). Used to resolve the decision id (for the suggestions
   * fetch), the headline confidence, and the recommended action verb.
   * @type {Record<string, any>}
   */
  export let pending = {};

  /**
   * onApprove: the host's EXISTING optimistic-resolve commit, bound so the
   * binding APPROVE macro reuses the SAME mutation surface the Approve button
   * calls (M10). Signature mirrors HitlPendingRow.commit:
   * (disposition, resolution) => void. When omitted the APPROVE macro degrades
   * to inert (it still renders; it just cannot fire).
   * @type {((disposition:string, resolution:string)=>any)|null}
   */
  export let onApprove = null;

  /**
   * onTune: pre-stage the host OVERRIDE picker (the host maps this to
   * toggleOverride). Advisory -- no server write. Optional.
   * @type {(()=>any)|null}
   */
  export let onTune = null;

  /**
   * onEscalate: move focus to the host's escalation / OVERRIDE control. Advisory
   * -- no new disposition, no server write. Optional.
   * @type {(()=>any)|null}
   */
  export let onEscalate = null;

  /**
   * onSnooze: ask the host to fade this row for a window (advisory; the palette
   * also writes a client-side localStorage marker). No server write. Optional.
   * @type {(()=>any)|null}
   */
  export let onSnooze = null;

  /**
   * onDissent: hand focus to the host OVERRIDE control on Esc (M6 -- dissent one
   * key away). Best-effort; when omitted the palette simply does nothing on Esc
   * beyond a log-free collapse. Optional.
   * @type {(()=>any)|null}
   */
  export let onDissent = null;

  /**
   * disabled: the host's actionsDisabled (expired row / resolve in flight). When
   * true NO macro fires -- the palette never resolves an expired or in-flight row.
   * @type {boolean}
   */
  export let disabled = false;

  // -- Reactive gate read. $on is the single source of truth for "render?". ---
  $: on = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // -- Ranked view-model. Starts from realistic mock, patches the headline from
  //    the envelope synchronously, then upgrades to the live suggestions blend
  //    when the lazy fetch lands. Falls back to mock when nothing live is
  //    available so the palette is always testable. -------------------------
  /** @type {ReturnType<typeof mockRanked>} */
  let model = mockRanked(pending);
  let usedMock = true;

  // Seed the headline (APPROVE) confidence + verb from the envelope synchronously
  // (no fetch) so the palette shows a real number on first paint.
  $: {
    const envPct = envelopeConfidence(pending);
    const envVerb = topActionVerb(pending);
    if ((envPct != null || envVerb) && Array.isArray(model.actions) && model.actions.length) {
      const next = model.actions.map((a) => ({ ...a }));
      if (envPct != null) next[0].confidence = envPct / 100;
      if (envVerb) next[0].label = envVerb.charAt(0).toUpperCase() + envVerb.slice(1);
      model = { ...model, actions: next };
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
    // Flag flipped OFF: reset so a later ON re-fetches; collapse keyboard state.
    _fetchedFor = null;
    hiIndex = 0;
  }

  /** @param {string} decisionId */
  async function loadSuggestions(decisionId) {
    try {
      const suggestions = await getDecisionSuggestions(decisionId);
      const live = rankedFromSuggestions(suggestions, pending);
      if (live) {
        model = live;
        usedMock = false;
        return;
      }
      usedMock = true; // empty/unusable array -- keep mock-seeded model
    } catch {
      usedMock = true; // server down / 404 / network -- degrade to mock
    }
  }

  // -- Provenance state tag (paired text; never implicit). --------------------
  $: stateTag = usedMock
    ? { txt: 'SAMPLE DATA', cls: '' }
    : model.source === 'live'
      ? { txt: 'LIVE', cls: '' }
      : { txt: 'FALLBACK RANKING', cls: 'cp__state--rank' };

  // -- Derived per-action view rows (pct + word + dim). -----------------------
  $: actions = Array.isArray(model.actions) ? model.actions : [];
  $: topAction = actions[0] || null;
  $: ladder = actions.slice(1);

  /** @param {{confidence:number}} a */
  function pctOf(a) {
    const p = toPct(a?.confidence);
    return p == null ? 0 : p;
  }

  // -- Keyboard highlight across the FULL ranked list (0 = headline APPROVE,
  //    1..n = ladder rows). ---------------------------------------------------
  let hiIndex = 0;
  /** @type {HTMLDivElement|undefined} */
  let rootEl;
  /** @type {HTMLButtonElement[]} */
  let ladderBtns = [];

  // -- Macro routing. Every path is gated on !disabled and an explicit gesture;
  //    nothing auto-fires. APPROVE is the only server-touching path (and only
  //    via the host's existing commit). -----------------------------------
  /** @param {{key:string,label:string,route:string}} action */
  function fireMacro(action) {
    if (disabled || !action) return;
    switch (action.route) {
      case 'commit-approve': {
        if (typeof onApprove !== 'function') return; // inert without the host
        // resolution echoes the recommended verb so the executor applies it
        // (mirrors HitlPendingRow.onApprove, which resolves with the action).
        const resolution = (
          topActionVerb(pending) || (action.label || 'approve')
        )
          .toString();
        onApprove('approve', resolution);
        break;
      }
      case 'prestage-override':
        if (typeof onTune === 'function') onTune();
        break;
      case 'focus-escalate':
        if (typeof onEscalate === 'function') onEscalate();
        else if (typeof onDissent === 'function') onDissent();
        break;
      case 'client-snooze':
        persistSnooze(decisionIdOf(pending), 5);
        if (typeof onSnooze === 'function') onSnooze();
        break;
      default:
        /* unknown route -- no-op (never auto-acts) */
        break;
    }
  }

  function fireHighlighted() {
    fireMacro(actions[hiIndex] || actions[0]);
  }

  /** @param {KeyboardEvent} e */
  function onKeydown(e) {
    if (!on) return; // belt-and-suspenders: no handler effect when OFF
    const n = actions.length;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      hiIndex = Math.min(n - 1, hiIndex + 1);
      focusHi();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      hiIndex = Math.max(0, hiIndex - 1);
      focusHi();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (e.ctrlKey || e.metaKey) fireMacro(actions[0]); // Ctrl/Cmd+Enter = APPROVE
      else fireHighlighted();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      if (typeof onDissent === 'function') onDissent();
    }
  }

  function focusHi() {
    // hiIndex 0 -> the root/headline; 1..n -> ladder buttons.
    if (hiIndex > 0 && ladderBtns[hiIndex - 1]) ladderBtns[hiIndex - 1].focus();
    else rootEl?.focus();
  }

  /** @param {number} i ladder index (0-based) @param {{...}} a */
  function onLadderClick(a) {
    fireMacro(a);
  }
  /** @param {number} rank full-list index (1..n) */
  function onLadderEnter(rank) {
    hiIndex = rank;
  }

  // Top headline aria + paired text.
  $: topPct = topAction ? pctOf(topAction) : null;
  $: topWord = confWord(topPct);
  $: topLabelUpper = (topAction?.label || 'approve').toString().toUpperCase();
  $: approveDisabled = disabled || typeof onApprove !== 'function';
</script>

{#if on}
  <!-- The palette wrapper carries an accessible group name so assistive tech
       reads it as the co-pilot region. The keydown handler hosts the
       Down/Up/Enter/Ctrl+Enter/Esc gestures. role=group + tabindex=0 makes the
       whole palette a single focus target (the headline APPROVE is index 0). -->
  <div
    class="cp"
    role="group"
    tabindex="0"
    bind:this={rootEl}
    aria-label="Operator Co-Pilot -- ranked advisory next-action palette. Advisory only; the operator decision is still required."
    data-beta={FLAG_KEY}
    data-mock={usedMock ? 'true' : 'false'}
    on:keydown={onKeydown}
  >
    <!-- HEAD: bespoke AI glyph + tag + provenance state. -->
    <div class="cp__head">
      <span class="cp__glyph" aria-hidden="true">Co</span>
      <div class="cp__headtxt">
        <div class="cp__tagrow">
          <span class="cp__tag">Co-Pilot -- ranked next actions</span>
          <span class="cp__state {stateTag.cls}" data-state={stateTag.txt}>{stateTag.txt}</span>
        </div>

        <!-- TOP action headline (binding APPROVE, largest type, clickable). -->
        <button
          type="button"
          class="cp__top"
          class:is-hi={hiIndex === 0}
          on:click={() => fireMacro(actions[0])}
          on:mouseenter={() => (hiIndex = 0)}
          disabled={approveDisabled}
          aria-label={topPct == null
            ? `Recommend ${topLabelUpper}, binding. Activate to approve.`
            : `Recommend ${topLabelUpper}, ${topPct} percent, ${topWord} confidence, binding. Activate to approve.`}
        >
          <span class="cp__top-verb">1. recommend <b>{topLabelUpper}</b></span>
          {#if topPct != null}
            <span class="cp__top-pct">{topPct}%</span>
            <span class="act__word act__word--{topWord}">{topWord} confidence</span>
          {/if}
          <span class="act__kind act__kind--binding">binding</span>
        </button>
        {#if topAction?.rationale}
          <p class="cp__top-rationale">
            {topAction.rationale}
            {#if topAction.precedent != null}
              <span class="prec">({topAction.precedent} precedent)</span>
            {/if}
          </p>
        {/if}
      </div>
    </div>

    <!-- RANKED LADDER: ranks 2..n. role=listbox; each macro is an option. -->
    {#if ladder.length}
      <div class="cp__ladder" role="listbox" aria-label="Lower-ranked next actions">
        <div class="cp__ladlab" id="cp-ladlab">Or pick another response</div>
        {#each ladder as a, i (a.key)}
          {@const rank = i + 2}
          {@const pct = pctOf(a)}
          {@const word = confWord(pct)}
          {@const dim = pct < 60}
          <button
            type="button"
            class="act"
            class:is-dim={dim}
            class:is-hi={hiIndex === rank - 1}
            role="option"
            aria-selected={hiIndex === rank - 1}
            bind:this={ladderBtns[i]}
            on:click={() => onLadderClick(a)}
            on:mouseenter={() => onLadderEnter(rank - 1)}
            disabled={disabled}
            aria-label={`${a.label}, ${pct} percent, ${word} confidence, ${a.binding ? 'binding' : 'advisory'}. ${a.rationale}`}
          >
            <span class="act__ord" aria-hidden="true">{rank}.</span>
            <span class="act__main">
              <span class="act__verb">{a.label}</span>
              <span class="act__kind {a.binding ? 'act__kind--binding' : 'act__kind--advisory'}">
                {a.binding ? 'binding' : 'advisory'}
              </span>
              {#if dim}
                <span class="act__kind act__kind--low">low confidence</span>
              {/if}
            </span>
            <span class="act__conf">
              <span class="act__pct">{pct}%</span>
              <span class="act__word act__word--{word}">{word}</span>
            </span>
            <span class="act__rationale">
              {a.rationale}{a.precedent ? `  (${a.precedent} precedent)` : '  (no precedent this session)'}
            </span>
          </button>
        {/each}
      </div>
    {/if}

    <!-- FOOTER: BETA annotation + advisory reminder + keyboard legend. -->
    <div class="cp__foot">
      <span class="cp__beta">BETA -- default OFF, toggled in Settings</span>
      <span class="cp__advis">
        Advisory only. The absolute HITL gate stays intact -- no macro auto-fires,
        and only APPROVE is binding.
      </span>
      <span class="cp__keys">
        <kbd class="kbd">Down</kbd><kbd class="kbd">Up</kbd> move highlight
        &middot; <kbd class="kbd">Enter</kbd> fire highlighted
        &middot; <kbd class="kbd">Ctrl+Enter</kbd> fire APPROVE
        &middot; <kbd class="kbd">Esc</kbd> dissent (Override)
      </span>
    </div>
  </div>
{/if}

<style>
  /* The palette shares the row's amber left-rail grammar -- part of the lean-
     forward spine, not a bolt-on widget. */
  .cp {
    border-left: 3px solid var(--badge-ar-border, #d97706);
    background: var(--calm-accent-wash, rgba(245, 158, 11, 0.09));
    border-radius: var(--radius-soft, 4px);
    padding: var(--space-5, 14px);
    margin-bottom: var(--space-3, 6px);
    box-sizing: border-box;
  }
  .cp:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid)
      var(--focus-ring-color, var(--accent, #f59e0b));
    outline-offset: 2px;
  }

  .cp__head { display: flex; align-items: flex-start; gap: var(--space-4, 10px); }

  /* bespoke AI-shaped glyph -- asymmetric corner, decorative (aria-hidden). */
  .cp__glyph {
    flex: 0 0 auto; width: 34px; height: 34px; margin-top: 2px;
    display: grid; place-items: center;
    border: 1px solid var(--badge-ar-border, #d97706);
    border-radius: 8px 8px 8px 2px;
    background: var(--calm-surface-raised, var(--bg-card, #0c1118));
    color: var(--badge-ar-fg, #d97706);
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-weight: 750; font-size: 15px; letter-spacing: -0.04em;
  }
  .cp__headtxt { flex: 1 1 auto; min-width: 0; }
  .cp__tagrow { display: flex; align-items: baseline; flex-wrap: wrap; gap: var(--space-3, 6px); }
  .cp__tag {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: var(--fs-chrome, 11px); font-weight: 700;
    letter-spacing: 0.16em; text-transform: uppercase;
    color: var(--calm-ink-chrome, #8a8068);
  }
  /* provenance state tag -- paired text, never implicit. */
  .cp__state {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 10px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
    color: var(--badge-ar-fg, #d97706);
    border: 1px solid var(--badge-ar-border, #d97706);
    border-radius: 3px; padding: 1px 6px;
  }
  .cp__state--rank {
    color: var(--badge-timeout-fg, #7c3aed);
    border-color: var(--badge-timeout-border, #c4b5fd);
  }

  /* TOP action headline -- the largest type in the dock (earns the co-pilot
     role). It is a real button so the binding APPROVE is one tap / Enter away. */
  .cp__top {
    appearance: none; cursor: pointer; text-align: left; width: 100%;
    display: flex; align-items: baseline; flex-wrap: wrap; gap: var(--space-3, 6px);
    margin-top: var(--space-2, 4px);
    background: transparent; border: 1px solid transparent;
    border-radius: var(--radius-sharp, 2px);
    padding: var(--space-2, 4px) var(--space-2, 4px);
    transition: background var(--t-calm, 180ms ease), border-color var(--t-calm, 180ms ease);
  }
  .cp__top:hover:not(:disabled) { background: var(--calm-surface-hover, var(--bg-row-hover, #131c2a)); }
  .cp__top.is-hi { border-color: var(--badge-ar-border, #d97706); background: var(--calm-accent-wash, rgba(245, 158, 11, 0.09)); }
  .cp__top:disabled { cursor: default; opacity: 0.5; }
  .cp__top:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid)
      var(--focus-ring-color, var(--accent, #f59e0b));
    outline-offset: 2px;
  }
  .cp__top-verb {
    font-family: var(--ff-system, system-ui, sans-serif);
    font-size: 22px; font-weight: 750; letter-spacing: -0.01em;
    color: var(--calm-ink-loud, #e8e0cc);
  }
  .cp__top-verb b { color: var(--badge-ar-fg, #d97706); }
  .cp__top-pct {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 20px; font-weight: 750; letter-spacing: -0.02em;
    color: var(--calm-ink-loud, #e8e0cc); font-variant-numeric: tabular-nums;
  }
  .cp__top-rationale {
    font-size: var(--fs-meta, 13px); color: var(--calm-ink, #b8b098);
    margin: var(--space-2, 4px) 0 0;
  }
  .cp__top-rationale .prec { color: var(--calm-ink-quiet, #948870); }

  /* RANKED LADDER -- the remaining 2..n macros. */
  .cp__ladder {
    margin-top: var(--space-5, 14px);
    border-top: 1px dashed var(--calm-hairline-hi, rgba(245, 158, 11, 0.25));
    padding-top: var(--space-4, 10px);
    display: flex; flex-direction: column; gap: var(--space-2, 4px);
  }
  .cp__ladlab {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: var(--fs-chrome, 11px); letter-spacing: 0.1em; text-transform: uppercase;
    color: var(--calm-ink-quiet, #948870); margin-bottom: var(--space-2, 4px);
  }

  /* an action button = the full interactive ladder row. */
  .act {
    appearance: none; text-align: left; cursor: pointer; width: 100%;
    display: grid;
    grid-template-columns: 2.2ch minmax(0, 1fr) auto;
    align-items: center;
    column-gap: var(--space-4, 10px); row-gap: 2px;
    background: transparent; border: 1px solid transparent;
    border-radius: var(--radius-sharp, 2px);
    padding: var(--space-3, 6px) var(--space-3, 6px);
    color: inherit;
    transition: background var(--t-calm, 180ms ease), border-color var(--t-calm, 180ms ease);
  }
  .act:hover:not(:disabled) { background: var(--calm-surface-hover, var(--bg-row-hover, #131c2a)); }
  .act.is-hi { border-color: var(--badge-ar-border, #d97706); background: var(--calm-accent-wash, rgba(245, 158, 11, 0.09)); }
  .act:disabled { cursor: default; opacity: 0.5; }
  .act:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid)
      var(--focus-ring-color, var(--accent, #f59e0b));
    outline-offset: 2px;
  }
  .act__ord {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: var(--fs-meta, 13px); font-weight: 600;
    color: var(--calm-ink-quiet, #948870); font-variant-numeric: tabular-nums; text-align: center;
  }
  .act__main { min-width: 0; display: flex; align-items: baseline; gap: var(--space-3, 6px); flex-wrap: wrap; }
  .act__verb {
    font-family: var(--ff-system, system-ui, sans-serif);
    font-size: var(--fs-body, 14px); font-weight: 600;
    color: var(--calm-ink-loud, #e8e0cc);
  }
  /* binding vs advisory paired TEXT tag -- not color alone. */
  .act__kind {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
    padding: 1px 5px; border-radius: 3px; border: 1px solid;
  }
  .act__kind--binding {
    color: var(--badge-ar-fg, #d97706); border-color: var(--badge-ar-border, #d97706);
    background: var(--badge-ar-bg, #fef3c7);
  }
  .act__kind--advisory {
    color: var(--calm-ink-chrome, #8a8068); border-color: var(--calm-hairline, #192030);
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
  }
  /* literal "low confidence" cue -- paired with the dimming (never color-only). */
  .act__kind--low {
    color: var(--badge-blocked-fg, #dc2626); border-color: var(--badge-blocked-border, #dc2626);
    background: var(--badge-blocked-bg, #fee2e2);
  }
  .act__conf {
    display: inline-flex; align-items: baseline; gap: var(--space-2, 4px);
    font-family: var(--ff-mono, ui-monospace, monospace); font-variant-numeric: tabular-nums;
    justify-self: end; white-space: nowrap;
  }
  .act__pct { font-size: var(--fs-body, 14px); font-weight: 700; color: var(--calm-ink-loud, #e8e0cc); }
  /* confidence WORD -- the same number rendered as a word so color is strippable. */
  .act__word {
    font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
    padding: 1px 5px; border-radius: 3px; border: 1px solid;
  }
  .act__word--high     { color: var(--badge-decided-fg, #16a34a); border-color: var(--badge-decided-border, #86efac); background: var(--badge-decided-bg, #dcfce7); }
  .act__word--moderate { color: var(--badge-warn-fg, #ea580c);    border-color: var(--badge-warn-border, #ea580c);    background: var(--badge-warn-bg, #ffedd5); }
  .act__word--low      { color: var(--badge-blocked-fg, #dc2626); border-color: var(--badge-blocked-border, #dc2626); background: var(--badge-blocked-bg, #fee2e2); }
  .act__word--unknown  { color: var(--calm-ink-chrome, #8a8068);  border-color: var(--calm-hairline, #192030);        background: var(--calm-surface-alt, #0b1018); }
  .act__rationale {
    grid-column: 2 / 4;
    font-size: var(--fs-meta, 13px); color: var(--calm-ink-quiet, #948870);
    line-height: var(--lh-tight, 1.25);
  }

  /* low-confidence (<60%) entries: visibly DIMMED + a literal "low confidence"
     cue. The dimming EMPHASISES the label; it is never the signal itself. */
  .act.is-dim { opacity: 0.62; }
  .act.is-dim .act__verb { color: var(--calm-ink, #b8b098); font-weight: 500; }

  /* FOOTER: BETA annotation + advisory reminder + keyboard legend. */
  .cp__foot {
    margin-top: var(--space-5, 14px);
    border-top: 1px solid var(--calm-hairline, #192030);
    padding-top: var(--space-4, 10px);
    display: flex; align-items: center; flex-wrap: wrap; gap: var(--space-4, 10px);
  }
  .cp__beta {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: var(--fs-chrome, 11px); font-weight: 700; letter-spacing: 0.08em;
    color: var(--badge-ar-fg, #d97706);
    border: 1px solid var(--badge-ar-border, #d97706); border-radius: 3px; padding: 2px 7px;
  }
  .cp__advis {
    font-size: var(--fs-meta, 13px); color: var(--calm-ink-quiet, #948870);
    font-style: italic; flex: 1 1 200px; min-width: 0;
  }
  .cp__keys {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: var(--fs-chrome, 11px); color: var(--calm-ink-quiet, #948870);
    letter-spacing: 0.02em; width: 100%;
  }
  .kbd {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 10px; color: var(--calm-ink-chrome, #8a8068);
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
    border: 1px solid var(--calm-hairline, #192030);
    border-radius: 3px; padding: 1px 5px; margin-right: 2px;
  }

  /* Reduced motion: snap transitions (M17). */
  :global(html[data-motion='reduce']) .act,
  :global(html[data-motion='reduce']) .cp__top { transition: none; }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .act,
    :global(html:not([data-motion='allow'])) .cp__top { transition: none; }
  }
</style>
