<!--
  Badge.svelte -- M4 paired label+color badge primitive.

  CONTRACT (inviolable MUST M4):
    - Paired label + color ALWAYS. Color alone is NEVER a signal. The `label`
      prop is REQUIRED; a missing/blank label throws at construction time so
      there is no color-without-text code path. This is enforced structurally,
      not by convention.
    - Variants (canonical labels, frozen): ACTION REQUIRED / OBSERVING /
      DECIDED / BLOCKED / WARN / TIMEOUT.
    - Every badge carries `title` + `aria-label` = the trigger reason, so the
      meaning is reachable by hover AND by assistive tech. When no explicit
      reason is supplied we fall back to the human label so the a11y name is
      never empty (axe: no empty aria-label).
    - ACTION REQUIRED = amber #d97706 on #fef3c7 with a 2px solid amber pulsing
      border. OBSERVING = slate, no (heavy) border. Palette mirrors the live
      dashboard FR-UI-6 badge contract exactly (index.html .ar-* classes).

  CRAFT (calm-ambient spine, KingMode): the resting state is still water --
  only ACTION REQUIRED pulses, and only via motion that is reduced-motion
  aware. Severity is carried by variable type-weight + a paired dot glyph, not
  by chrome. Tokens are CSS custom properties so the 3 themes
  (obsidian/phosphor/paper) can retint without touching this leaf.

  This component depends only on theme tokens + self-contained styles. It is
  file-disjoint from every logic unit and consumes no endpoints.
-->
<script context="module">
  /**
   * Frozen variant -> {label, defaultReason} table.
   * The label strings are the canonical M4 labels and MUST NOT drift.
   * Encoding M4 as one auditable table (signal-hero graft) keeps the S2
   * render-validator trivial: assert every rendered badge's text is one of
   * these labels and that an aria-label is present.
   */
  export const BADGE_VARIANTS = Object.freeze({
    'action-required': { label: 'ACTION REQUIRED', defaultReason: 'Operator action required' },
    observing:         { label: 'OBSERVING',       defaultReason: 'Observing -- no action required' },
    decided:           { label: 'DECIDED',         defaultReason: 'Decision recorded' },
    blocked:           { label: 'BLOCKED',          defaultReason: 'Message blocked by governance' },
    warn:              { label: 'WARN',             defaultReason: 'Warning -- review advised' },
    timeout:           { label: 'TIMEOUT',          defaultReason: 'HITL window expired' },
  });

  /** Reverse map: canonical label string -> variant key (operator convenience). */
  const LABEL_TO_VARIANT = Object.freeze(
    Object.fromEntries(
      Object.entries(BADGE_VARIANTS).map(([k, v]) => [v.label, k]),
    ),
  );

  /** Resolve a caller-supplied variant OR canonical label into a variant key. */
  function resolveVariant(variant) {
    if (variant == null) return null;
    const v = String(variant).trim();
    if (v in BADGE_VARIANTS) return v;
    if (v in LABEL_TO_VARIANT) return LABEL_TO_VARIANT[v];
    // normalise "ACTION REQUIRED" / "action_required" / "Action-Required"
    const norm = v.toLowerCase().replace(/[\s_]+/g, '-');
    if (norm in BADGE_VARIANTS) return norm;
    return null;
  }
</script>

<script>
  /**
   * variant: one of the BADGE_VARIANTS keys, or a canonical label string.
   * REQUIRED -- there is no default. A missing/unknown variant is a construction
   * error (color-without-text is impossible by construction, M4).
   */
  export let variant;

  /**
   * label: optional override of the canonical variant label. If provided it
   * MUST be non-blank. We still require SOME label text on every badge; passing
   * an empty string is rejected. Defaults to the canonical variant label so the
   * common path needs only `variant`.
   */
  export let label = undefined;

  /**
   * reason: the trigger reason -> title + aria-label. Falls back to the
   * variant's defaultReason (never empty) so the accessible name is always set.
   */
  export let reason = undefined;

  /** count: optional numeric tally appended to the label (e.g. ACTION REQUIRED 3). */
  export let count = undefined;

  /** as: render element. Span by default; callers may use 'button'-like markup separately. */
  export let element = 'span';

  $: resolved = resolveVariant(variant);

  // --- Structural M4 enforcement: no badge without a variant + a text label. ---
  $: if (resolved == null) {
    throw new Error(
      `Badge.svelte (M4): unknown/blank variant "${variant}". ` +
      `Color alone is never a signal -- a known variant (one of ` +
      `${Object.keys(BADGE_VARIANTS).join(', ')}) is required.`,
    );
  }

  $: canonicalLabel = BADGE_VARIANTS[resolved].label;

  $: resolvedLabel = (() => {
    if (label === undefined) return canonicalLabel;
    const t = String(label).trim();
    if (t === '') {
      // Reject the color-without-text path explicitly (M4).
      throw new Error(
        'Badge.svelte (M4): label override must be non-empty -- ' +
        'a badge can never render color without text.',
      );
    }
    return t;
  })();

  $: hasCount = count !== undefined && count !== null && count !== '';
  $: displayText = hasCount ? `${resolvedLabel} ${count}` : resolvedLabel;

  // aria-label / title = trigger reason; never empty (falls back to defaultReason).
  $: accessibleReason = (() => {
    const r = reason === undefined || reason === null ? '' : String(reason).trim();
    return r !== '' ? r : BADGE_VARIANTS[resolved].defaultReason;
  })();
</script>

<svelte:element
  this={element}
  class="ar-badge ar-{resolved}"
  data-variant={resolved}
  title={accessibleReason}
  aria-label={accessibleReason}
  role="status"
>
  <!-- paired dot glyph: decorative; the text label below is the real signal -->
  <span class="ar-dot" aria-hidden="true"></span>
  <span class="ar-text">{displayText}</span>
</svelte:element>

<style>
  /* FR-UI-6 paired actionability badge. Palette mirrors the live dashboard
     .ar-* contract exactly so promotion is a 1:1 form swap. */
  .ar-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    /* variable-weight typographic severity (monitor-first graft): the label
       itself carries severity via weight + tracking, not via extra chrome. */
    font-family: var(--ff-system, var(--font-d, ui-sans-serif, system-ui, sans-serif));
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 3px 8px;
    white-space: nowrap;
    border-radius: 2px;
    line-height: 1;
    vertical-align: middle;
  }

  .ar-dot {
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    flex: 0 0 auto;
  }

  /* The text node is the load-bearing signal -- it can never be hidden. */
  .ar-text {
    display: inline;
  }

  /* ACTION REQUIRED -- amber #d97706 on #fef3c7, 2px solid amber pulsing
     border. Heaviest type weight: this is the one true escalation surface. */
  .ar-action-required {
    /* ACTION REQUIRED text darkened to AA on the theme-invariant #fef3c7 chip
       (was #d97706 = 2.86:1, below AA). Same hue; bg/border/weight/border-color
       and the pulse animation unchanged so the escalation identity is preserved
       -- only the text ink darkens. */
    color: #b45309;
    background: #fef3c7;
    border: 2px solid #d97706;
    font-weight: 800;
    animation: pulseAR 1.6s ease-in-out infinite;
  }

  /* OBSERVING -- slate, calm resting state, no heavy border (still water). */
  .ar-observing {
    color: #475569;
    background: #f1f5f9;
    border: 1px solid #cbd5e1;
    font-weight: 600;
  }

  .ar-decided {
    /* DECIDED text darkened to AA on the theme-invariant #dcfce7 chip (was
       #16a34a = 3.0:1, below AA). Same hue; bg/border/weight unchanged. */
    color: #15803d;
    background: #dcfce7;
    border: 1px solid #86efac;
  }

  .ar-blocked {
    /* BLOCKED text darkened to AA on the theme-invariant #fee2e2 chip (was
       #dc2626 = 3.95:1, below AA). Same hue; bg/border/weight unchanged. */
    color: #b91c1c;
    background: #fee2e2;
    border: 2px solid #dc2626;
    font-weight: 700;
  }

  .ar-warn {
    /* WARN text darkened to AA on the theme-invariant #ffedd5 chip (was #ea580c
       = 3.1:1, below AA). The dashed border keeps the orange accent identity. */
    color: #9a3412;
    background: #ffedd5;
    border: 1px dashed #ea580c;
  }

  .ar-timeout {
    color: #7c3aed;
    background: #ede9fe;
    border: 1px solid #c4b5fd;
  }

  @keyframes pulseAR {
    0%,
    100% {
      box-shadow: 0 0 0 0 rgba(217, 119, 6, 0.55);
    }
    50% {
      box-shadow: 0 0 0 5px rgba(217, 119, 6, 0);
    }
  }

  /* NFR-UI-7 reduced motion: suppress the pulse unless the operator has
     explicitly force-allowed motion via the FR-UI-9 override
     (html[data-motion="allow"]). Mirrors the live dashboard semantics so the
     contract is preserved across the form swap. */
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .ar-action-required {
      animation: none;
      /* keep a static 1px inset ring so the signal survives without motion */
      box-shadow: 0 0 0 1px #d97706 inset;
    }
  }

  /* Operator force-reduce: kill the pulse unconditionally. */
  :global(html[data-motion='reduce']) .ar-action-required {
    animation: none !important;
    box-shadow: 0 0 0 1px #d97706 inset;
  }

  /* Operator force-allow: re-assert the pulse even if the OS reports reduce. */
  :global(html[data-motion='allow']) .ar-action-required {
    animation: pulseAR 1.6s ease-in-out infinite !important;
  }
</style>
