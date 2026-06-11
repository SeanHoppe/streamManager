<!--
  AdvisoryChip.svelte -- M8 Learn-Mode advisory chip. The ABSOLUTE-GATE leaf.

  CONTRACT (inviolable MUST M8):
    - Learn-Mode bias is presented ONLY as a dashed, NON-VERDICT informational
      chip rendered ABOVE the action buttons of a pending HITL row. It is a
      hint, never a decision.
    - Fixed accessible title (frozen string, MUST NOT drift):
        "advisory only -- operator decision still required"
      carried as both title + aria-label so the meaning is reachable by hover
      AND by assistive tech (axe: never an empty accessible name).
    - It NEVER bypasses the HITL gate: it renders no action buttons, emits no
      events, performs no network I/O, and exposes no "apply" affordance. It is
      a pure read-only annotation. (governance.py:902-941 -- bias is advisory.)
    - It NEVER toasts (no transient popup / live-region alert) and NEVER offers
      undo. Those would imply an action was taken; none ever is. role is the
      passive "note", not "alert" -- it must not steal focus or announce
      assertively.

  CRAFT (calm-ambient spine, KingMode): the chip is deliberately the quietest
  surface in the HITL dock. A dashed hairline border (the visual grammar of
  "provisional / not-yet-committed"), low-saturation ink, sev-quiet type. It
  defers entirely to the amber ACTION REQUIRED affordance below it -- the
  operator's eye is drawn to the real decision, the advisory whispers. The
  dashed border is the single structural cue that this is non-binding; it pairs
  with the literal "ADVISORY" label so the non-verdict status is never carried
  by chrome alone (M4 discipline applied even though this is not an M4 badge).

  This component depends only on theme/calm tokens + its props. It is
  file-disjoint and consumes NO endpoints (M18: zero network I/O, pure view).
  M16: domain-agnostic -- the bias text is rendered verbatim from data, never a
  hard-coded monitored-project term.
-->
<script context="module">
  // The fixed M8 advisory title. Frozen as a module constant so the string is
  // a single source of truth and the S2 render-validator can assert it exactly.
  // MUST NOT drift. ASCII-only (cp1252-safe): dash rendered as "--".
  export const ADVISORY_TITLE = 'advisory only -- operator decision still required';

  // The literal, load-bearing label that pairs with the dashed chrome so the
  // non-verdict status is never color/border-only.
  export const ADVISORY_LABEL = 'ADVISORY';
</script>

<script>
  /**
   * bias: the Learn-Mode advisory text rendered FROM DATA (M16). This is the
   * pre-fill hint the bridge surfaced (e.g. a suggested disposition or a short
   * rationale). Rendered verbatim; NEVER a hard-coded monitored-project term.
   * When absent/blank the chip does not render at all -- there is no empty
   * advisory state.
   * @type {string}
   */
  export let bias = '';

  /**
   * confidence: optional advisory confidence (0..1) surfaced as a quiet,
   * secondary readout. Purely informational -- it never gates anything (M8).
   * @type {number|null}
   */
  export let confidence = null;

  // Trim once; a blank bias yields no chip (no empty non-verdict surface).
  $: biasText = typeof bias === 'string' ? bias.trim() : '';
  $: hasBias = biasText !== '';

  // Quiet confidence readout, only when a finite 0..1 value is supplied.
  $: confPct = (() => {
    const n = Number(confidence);
    if (!Number.isFinite(n)) return null;
    const clamped = Math.min(1, Math.max(0, n));
    return Math.round(clamped * 100);
  })();
</script>

{#if hasBias}
  <!-- role="note": passive, non-assertive. NOT role="alert" (M8: never toasts,
       never steals focus). The fixed title + aria-label carry the absolute-gate
       reminder to hover AND assistive tech. -->
  <div
    class="adv-chip"
    role="note"
    title={ADVISORY_TITLE}
    aria-label={`${ADVISORY_TITLE}: ${biasText}`}
    data-advisory="true"
    data-non-verdict="true"
  >
    <!-- The literal non-verdict label, paired with the dashed chrome so the
         "advisory only" status is never carried by border-style alone. -->
    <span class="adv-chip__tag sev-quiet" aria-hidden="true">{ADVISORY_LABEL}</span>

    <!-- The Learn-Mode bias text, rendered verbatim from data (M16). -->
    <span class="adv-chip__bias">{biasText}</span>

    {#if confPct !== null}
      <!-- Quiet confidence readout. Informational only -- gates nothing (M8). -->
      <span class="adv-chip__conf" aria-hidden="true">~{confPct}%</span>
    {/if}
  </div>
{/if}

<style>
  /* The quietest surface in the dock. Dashed hairline = "provisional / not a
     verdict". Low saturation, sev-quiet ink. It defers to the amber action
     affordance below it -- the advisory whispers, the decision shouts. */
  .adv-chip {
    display: flex;
    align-items: baseline;
    gap: var(--space-3, 6px);
    width: 100%;
    box-sizing: border-box;
    /* M8: dashed NON-VERDICT chrome -- the structural cue that this is a hint,
       not a decision. 1px dashed hairline in the dim chrome ink. */
    border: 1px dashed var(--calm-hairline, #cbd5e1);
    border-radius: var(--radius-soft, 4px);
    /* Whisper-quiet wash; never the saturated accent (that is reserved for the
       lone true escalation). */
    background: var(--calm-accent-wash, rgba(148, 163, 184, 0.08));
    padding: var(--space-2, 4px) var(--space-4, 10px);
    /* Sits ABOVE the action buttons (M8): a small bottom gap separates the
       advisory from the real decision affordance. */
    margin: 0 0 var(--space-3, 6px) 0;
  }

  /* The literal "ADVISORY" tag -- the paired text cue (not chrome-only). */
  .adv-chip__tag {
    flex: 0 0 auto;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: var(--fs-chrome, 11px);
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--calm-ink-quiet, #64748b);
  }

  /* The bias text -- the operator-facing hint. Quiet ink, body legibility
     floor (NFR-UI-2). Wraps; never truncated (the operator must read it). */
  .adv-chip__bias {
    flex: 1 1 auto;
    min-width: 0;
    font-family: var(--ff-system, system-ui, sans-serif);
    font-size: var(--fs-meta, 13px);
    font-weight: 400;
    line-height: var(--lh-body, 1.5);
    color: var(--calm-ink-quiet, #64748b);
    font-style: italic;
  }

  /* The confidence readout -- secondary, monospaced, tabular. Informational. */
  .adv-chip__conf {
    flex: 0 0 auto;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: var(--fs-chrome, 11px);
    color: var(--calm-ink-quiet, #64748b);
    font-variant-numeric: tabular-nums;
    opacity: 0.85;
  }
</style>
