<!--
  AmberActionCard.svelte -- the single highest-severity escalation hero.

  This is the ONE saturated, in-motion surface in the whole product. It renders
  the lone true M2 escalation (desktop_pause / governance_negative_regression /
  static-rule) that EscalationRail has promoted to the foreground. Everything
  else in the still-water monitor stays calm; awe is spent HERE, deliberately,
  on the one signal that has earned the operator's full attention.

  CONTRACT (inviolable MUSTs this leaf carries):

    M4  Paired label+color ALWAYS -- color alone is NEVER a signal. The card
        leads with the literal text "ACTION REQUIRED" rendered as real text
        (never an icon, never a bare color block). The amber identity is the
        SECOND channel layered on top of the text, never instead of it.
        Palette is the frozen M4 ACTION REQUIRED contract: amber #d97706 on
        #fef3c7 with a 2px solid amber, pulsing border. The whole card carries
        title + aria-label = the trigger reason so the meaning is reachable by
        hover AND by assistive tech; the reason is never blank (it falls back
        to a non-empty default).

    M2  This card is rendered ONLY for a foreground-eligible escalation. It is a
        pure presentation leaf: it does NOT itself decide eligibility -- that is
        EscalationRail reading the escalation.js M2 allow-list table. The card
        renders whatever descriptor it is handed. (The S2 render-validator
        asserts the rail never hands it a badge-in-place type.)

    M16 Domain-agnostic. The card hard-codes NO monitored-project vocabulary.
        The governed-target identity (session label) is rendered from the data
        on the descriptor, never from a literal here.

    M17 a11y: role="alert" + aria-live so a newly-promoted escalation is
        announced; the dismiss control is a real <button> with a 2px solid
        #d97706 focus ring + 2px offset; the accessible name is never empty.

    M18 Post-hoc observability: pure view leaf, zero network I/O, never on the
        verdict hot path.

  CRAFT (calm-ambient spine, KingMode): the card is the sole place motion +
  saturation are licensed. Severity is carried by the variable-weight
  typographic scale (the heading sits at the critical weight) reinforced by --
  never replaced by -- the amber chrome. The pulsing border is the live.css /
  Badge.svelte pulse, reduced-motion aware: under prefers-reduced-motion (and
  no operator force-allow) the pulse collapses to a static inset ring so the
  signal survives without movement.

  This component depends only on theme/calm tokens + its props. It is
  file-disjoint from every other unit and consumes no endpoints.
-->
<script>
  import { createEventDispatcher } from 'svelte';

  /**
   * descriptor: the resolved escalation descriptor from escalation.js
   * describe(), shaped:
   *   { type, disposition, foreground, severity, reason, known }
   * `type` is the canonical signal type (desktop_pause / ...);
   * `reason` is the human trigger string surfaced as title + aria-label (M4).
   * REQUIRED -- the card has no meaning without one.
   * @type {{ type:string, reason?:string, foreground?:boolean,
   *          severity?:number, known?:boolean } | null}
   */
  export let descriptor = null;

  /**
   * sessionLabel: the governed-target identity for this escalation, rendered
   * FROM DATA (M16) -- e.g. a session's project_slug or a short session id.
   * Optional; when absent the card simply omits the attribution line rather
   * than inventing a name. NEVER a hard-coded monitored-project literal.
   */
  export let sessionLabel = '';

  /**
   * sessionId: the raw session_id this escalation belongs to. Surfaced on the
   * "focus" action so the shell can scope panes to it. Never displayed raw as
   * the only identity (sessionLabel is the human channel).
   */
  export let sessionId = '';

  /**
   * dismissable: whether to show the operator-dismiss affordance. The hero is
   * acknowledged, not silenced -- dismiss clears THIS card; the underlying
   * governance state is untouched (the card is observability only).
   */
  export let dismissable = true;

  const dispatch = createEventDispatcher();

  // M4: the literal, load-bearing label. A constant -- the card cannot exist
  // without this exact text beside the amber chrome.
  const ACTION_LABEL = 'ACTION REQUIRED';

  // M4 a11y: the accessible name = the trigger reason, never empty. Falls back
  // to a non-empty default so axe never sees an empty aria-label / title.
  $: reasonText = (() => {
    const r = descriptor && typeof descriptor.reason === 'string' ? descriptor.reason.trim() : '';
    return r !== '' ? r : 'Operator action required -- governance escalation';
  })();

  // The canonical signal type, surfaced as a quiet machine-readable chip and as
  // the S2-validator hook (data-escalation-type). Domain-agnostic (M16).
  $: signalType = descriptor && typeof descriptor.type === 'string' ? descriptor.type : '';

  // Full accessible sentence for the card region. Includes the literal label so
  // the announced text leads with the signal, then the reason, then (only when
  // present) the governed-target attribution rendered from data (M16).
  $: ariaSentence = sessionLabel
    ? `${ACTION_LABEL}: ${reasonText} -- ${sessionLabel}`
    : `${ACTION_LABEL}: ${reasonText}`;

  function onFocusSession() {
    // Bubble a request to scope the shell to this escalation's session. The
    // card owns no navigation -- it only emits intent (file-disjoint).
    dispatch('focus', { sessionId, type: signalType });
  }

  function onDismiss() {
    dispatch('dismiss', { sessionId, type: signalType });
  }
</script>

{#if descriptor}
  <article
    class="aac is-escalating"
    role="alert"
    aria-live="assertive"
    aria-atomic="true"
    aria-label={ariaSentence}
    title={reasonText}
    data-escalation-type={signalType}
    data-foreground="true"
  >
    <!-- Asymmetric amber rail: a bespoke left spine, not a template card edge.
         Decorative -- the text label below is the real signal (M4). -->
    <span class="aac__spine" aria-hidden="true"></span>

    <div class="aac__body">
      <header class="aac__head">
        <!-- M4: the literal label, ALWAYS present, at the critical type weight
             (variable-weight severity). The dot is decorative only. -->
        <span class="aac__badge sev-critical">
          <span class="aac__dot" aria-hidden="true"></span>
          <span class="aac__label">{ACTION_LABEL}</span>
        </span>

        {#if signalType}
          <!-- machine-readable signal type; quiet, monospaced, never the sole
               signal. Domain-agnostic (M16): this is a governance signal name,
               not a monitored-project term. -->
          <code class="aac__type" aria-hidden="true">{signalType}</code>
        {/if}
      </header>

      <!-- The trigger reason as real prose -- the operator-facing "why". -->
      <p class="aac__reason">{reasonText}</p>

      {#if sessionLabel}
        <!-- Governed-target attribution rendered FROM DATA (M16). Quiet,
             secondary; the escalation reason leads. -->
        <p class="aac__attr">
          <span class="aac__attr-tag" aria-hidden="true">session</span>
          <span class="aac__attr-val">{sessionLabel}</span>
        </p>
      {/if}

      <div class="aac__actions">
        <button
          type="button"
          class="aac__btn aac__btn--primary"
          on:click={onFocusSession}
          aria-label={`Focus the session for: ${reasonText}`}
        >
          Focus session
        </button>
        {#if dismissable}
          <button
            type="button"
            class="aac__btn aac__btn--ghost"
            on:click={onDismiss}
            aria-label={`Dismiss escalation: ${reasonText}`}
          >
            Dismiss
          </button>
        {/if}
      </div>
    </div>
  </article>
{/if}

<style>
  /* The hero is the ONE saturated, in-motion surface. Amber identity is the
     frozen M4 ACTION REQUIRED contract: #d97706 on #fef3c7, 2px solid amber.
     These literals are theme-invariant (the escalation must read identically in
     obsidian / phosphor / paper -- it is the load-bearing signal), mirroring
     theme.css --badge-ar-* and Badge.svelte exactly. */
  .aac {
    position: relative;
    display: flex;
    gap: 0;
    align-items: stretch;
    background: #fef3c7;
    color: #7c4a02;
    border: 2px solid #d97706;
    border-radius: var(--radius-soft, 4px);
    padding: 0;
    overflow: hidden;
    /* repaint-cheap shadow; the pulse animates the outer ring only (no reflow). */
    box-shadow: 0 1px 2px rgba(217, 119, 6, 0.12);
  }

  /* Asymmetric amber spine -- a bespoke 4px left rail for a non-template
     silhouette. Decorative; the text carries the signal (M4). */
  .aac__spine {
    flex: 0 0 4px;
    background: #d97706;
    align-self: stretch;
  }

  .aac__body {
    flex: 1 1 auto;
    min-width: 0;
    padding: var(--space-5, 14px) var(--space-6, 22px) var(--space-5, 14px) var(--space-5, 14px);
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 6px);
  }

  .aac__head {
    display: flex;
    align-items: center;
    gap: var(--space-4, 10px);
    flex-wrap: wrap;
  }

  /* M4: paired label + color. The dot is decorative; .aac__label is the real
     signal text and can never be hidden. */
  .aac__badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: #d97706;
    line-height: 1;
  }

  .aac__dot {
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: currentColor;
    flex: 0 0 auto;
  }

  /* The label sits at the critical severity weight (variable-weight scale).
     We restate the tuple locally so the component is correct even if calm.css
     is not yet loaded; when it is, .sev-critical reinforces identically. */
  .aac__label {
    font-family: var(--ff-system, var(--font-d, ui-sans-serif, system-ui, sans-serif));
    font-size: var(--fs-badge, 12px);
    font-weight: 750;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #d97706;
  }

  .aac__type {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: var(--fs-chrome, 11px);
    letter-spacing: 0.02em;
    color: #92400e;
    background: rgba(217, 119, 6, 0.12);
    padding: 1px 6px;
    border-radius: var(--radius-sharp, 2px);
    white-space: nowrap;
  }

  /* The "why" as real prose -- highest information density on the card. */
  .aac__reason {
    margin: 0;
    font-family: var(--ff-system, system-ui, sans-serif);
    font-size: var(--fs-body, 14px);
    font-weight: 560;
    line-height: var(--lh-body, 1.5);
    color: #7c4a02;
  }

  .aac__attr {
    margin: 0;
    display: flex;
    align-items: baseline;
    gap: var(--space-3, 6px);
    font-size: var(--fs-meta, 13px);
  }

  .aac__attr-tag {
    font-size: var(--fs-chrome, 11px);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #b45309;
  }

  .aac__attr-val {
    font-family: var(--ff-mono, ui-monospace, monospace);
    color: #7c4a02;
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }

  .aac__actions {
    display: flex;
    gap: var(--space-3, 6px);
    margin-top: var(--space-2, 4px);
  }

  .aac__btn {
    appearance: none;
    font-family: var(--ff-system, system-ui, sans-serif);
    font-size: var(--fs-meta, 13px);
    font-weight: 600;
    line-height: 1;
    padding: 7px 12px;
    border-radius: var(--radius-sharp, 2px);
    cursor: pointer;
    transition: background var(--t-calm, 180ms ease), border-color var(--t-calm, 180ms ease),
      color var(--t-calm, 180ms ease);
  }

  .aac__btn--primary {
    background: #d97706;
    color: #fffbeb;
    border: 1px solid #b45309;
  }
  .aac__btn--primary:hover {
    background: #b45309;
  }

  .aac__btn--ghost {
    background: transparent;
    color: #92400e;
    border: 1px solid rgba(217, 119, 6, 0.5);
  }
  .aac__btn--ghost:hover {
    border-color: #d97706;
    color: #7c4a02;
  }

  /* M17: 2px solid #d97706 focus ring + 2px offset on every interactive el. */
  .aac__btn:focus-visible {
    outline: 2px solid #d97706;
    outline-offset: 2px;
  }

  /* The escalation pulse (the ONLY attention-grabbing motion in the product).
     Animates an outer glow ring -- never layout -- so it is repaint-cheap and
     never reflows (M18). Mirrors calm.css .is-escalating + Badge.svelte. */
  :global(.aac.is-escalating) {
    animation: aac-escalate-pulse var(--motion-pulse, 1.6s) var(--motion-ease, ease-in-out) infinite;
  }

  @keyframes aac-escalate-pulse {
    0%,
    100% {
      box-shadow: 0 0 0 0 rgba(217, 119, 6, 0.55);
    }
    50% {
      box-shadow: 0 0 0 6px rgba(217, 119, 6, 0);
    }
  }

  /* NFR-UI-7 reduced motion: honor the OS preference unless the operator has
     force-allowed motion via the FR-UI-9 override (html[data-motion="allow"]).
     When suppressed, the escalation survives as a STATIC inset ring -- only the
     movement is removed; M4 text + amber color still carry the signal. */
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .aac.is-escalating {
      animation: none;
      box-shadow: 0 0 0 2px #d97706 inset;
    }
  }

  /* Operator force-reduce: kill the pulse unconditionally. */
  :global(html[data-motion='reduce']) .aac.is-escalating {
    animation: none !important;
    box-shadow: 0 0 0 2px #d97706 inset;
  }

  /* Operator force-allow: re-assert the pulse even if the OS reports reduce. */
  :global(html[data-motion='allow']) .aac.is-escalating {
    animation: aac-escalate-pulse var(--motion-pulse, 1.6s) var(--motion-ease, ease-in-out)
      infinite !important;
  }
</style>
