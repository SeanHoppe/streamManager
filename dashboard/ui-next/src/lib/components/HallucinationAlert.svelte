<!--
  HallucinationAlert.svelte -- FR-PPP Layer-3 negative-control alarm (M12).

  WHAT THIS IS
    The decoy / negative-control alarm. A decoy is a stream the learn-mode
    parser must NEVER report activity on. If the parser DOES emit a record for a
    registered decoy, it is fabricating data -- a parser-correctness failure. The
    bridge fires audit.hallucination_detected; this leaf renders that alarm.

  CONTRACT (inviolable MUST M12):
    - Render audit.hallucination_detected with an EXPLICIT operator-dismiss.
    - NO auto-clear, NO countdown (unlike the canary). This is a correctness
      alarm, not an attestation prompt -- it stays on screen until the operator
      acknowledges it. Dismiss is UI-only: the underlying WAL audit row is the
      durable record (this leaf is observability, M18), so we never imply the
      dismiss "fixes" anything -- it only clears the surfaced card.

  CRAFT (calm-ambient spine, KingMode):
    This is the one card in the AUDIT surface that legitimately reads loud: a
    parser that fabricates records has broken the product's core trust. BUT it
    is NOT an M2 foreground escalation (that amber-pulse register is reserved
    for desktop_pause / governance_negative_regression / static-rule). So this
    card uses the BLOCKED red register -- a STATIC hard border, NOT the pulsing
    amber motion. Loud via saturation + the heaviest type weight, still without
    spending the foreground-escalation motion budget. The decoy path is rendered
    as quiet forensic evidence beneath the headline.

  M4 (paired label+color): the literal text "HALLUCINATION DETECTED" leads,
    rendered as real words at the critical weight; the red is the second
    channel, never the only one. The dismiss control is a labelled button. No
    color-only signalling anywhere.

  M16 (domain-agnostic): the jsonl_path / probe_id / detected_at are DATA from
    the envelope. No monitored-project vocabulary, no hard-coded stream name --
    the offending path renders verbatim from the alarm payload.

  M17 (a11y): role="alert" + aria-live="assertive" so the alarm is announced
    when it lands; aria-atomic so the whole sentence reads; the accessible name
    is a non-empty data-derived sentence; dismiss is a real <button> with a
    non-empty label + the focus.css amber ring.

  M18 (post-hoc): pure presentation. Zero network I/O. Dismiss emits an intent
    event; the parent owns the cache eviction. Never on the verdict hot path.

  FILE-DISJOINT: owns only itself. Renders from props, emits `dismiss`; performs
  no list mutation, no fetch, no navigation.
-->
<script>
  import { createEventDispatcher } from 'svelte';

  /**
   * alert: the Layer-3 alarm state assembled from audit.hallucination_detected:
   *   { probe_id, jsonl_path?, detected_at? }
   * REQUIRED -- the card has no meaning without a probe_id + the offending path.
   * @type {{ probe_id?:string, jsonl_path?:string, detected_at?:number } | null}
   */
  export let alert = null;

  const dispatch = createEventDispatcher();

  // M4: the literal, load-bearing headline. A constant -- the card cannot exist
  // without this exact text beside the red chrome.
  const HEADLINE = 'HALLUCINATION DETECTED';

  $: probeId = (alert && alert.probe_id) || '';
  $: jsonlPath = (alert && alert.jsonl_path) || '';
  $: detectedAt = alert && alert.detected_at ? Number(alert.detected_at) : null;

  // Human time for the forensic line (data-derived, M16). Best-effort; epoch
  // seconds OR ms both tolerated.
  $: detectedText = (() => {
    if (detectedAt == null) return '';
    const ms = detectedAt > 1e12 ? detectedAt : detectedAt * 1000;
    try {
      return new Date(ms).toLocaleTimeString();
    } catch {
      return '';
    }
  })();

  // M17: a non-empty, data-derived accessible sentence so the alarm announces
  // meaningfully and axe never sees an empty aria-label.
  $: ariaSentence = jsonlPath
    ? `${HEADLINE}. The parser reported activity on a registered decoy stream (${jsonlPath}); it is producing fictional records.`
    : `${HEADLINE}. The parser reported activity on a registered decoy stream; it is producing fictional records.`;

  function dismiss() {
    // UI-only acknowledgement -- the WAL row remains the durable audit record.
    dispatch('dismiss', { probeId });
  }
</script>

{#if alert}
  <article
    class="halluc"
    role="alert"
    aria-live="assertive"
    aria-atomic="true"
    aria-label={ariaSentence}
    data-probe-id={probeId}
  >
    <!-- Static red spine -- a hard alarm edge, NOT the pulsing amber foreground
         rail. Decorative; the headline text carries the signal (M4). -->
    <span class="halluc__spine" aria-hidden="true"></span>

    <div class="halluc__body">
      <header class="halluc__head">
        <!-- M4: literal headline at the critical weight; the dot is decorative,
             the words are the signal. sev-critical = heaviest type step. -->
        <span class="halluc__badge sev-critical">
          <span class="halluc__dot" aria-hidden="true"></span>
          <span class="halluc__label">{HEADLINE}</span>
        </span>
        <span class="halluc__tag">negative-control alarm</span>
      </header>

      <p class="halluc__why">
        The parser reported activity on a registered decoy stream. The parser is
        producing fictional records.
      </p>

      {#if jsonlPath}
        <!-- Forensic evidence: the offending path, verbatim from data (M16). -->
        <p class="halluc__evidence">
          <span class="halluc__evidence-tag" aria-hidden="true">decoy stream</span>
          <code class="halluc__path" title={jsonlPath}>{jsonlPath}</code>
        </p>
      {/if}

      {#if detectedText}
        <p class="halluc__meta">detected {detectedText}</p>
      {/if}

      <div class="halluc__actions">
        <!-- Explicit operator-dismiss (M12). No auto-clear, no countdown. -->
        <button
          type="button"
          class="halluc__dismiss"
          on:click={dismiss}
          aria-label="Dismiss this hallucination alarm (the audit record is retained)"
        >
          Dismiss
        </button>
        <span class="halluc__note" role="note">
          Dismiss clears the card only -- the audit record is retained.
        </span>
      </div>
    </div>
  </article>
{/if}

<style>
  /* BLOCKED red register -- a hard, STATIC alarm. Loud via saturation + weight,
     NOT via the foreground-escalation pulse (that motion budget is reserved for
     the lone M2 escalation). Theme-invariant red so a parser-correctness alarm
     reads identically in obsidian / phosphor / paper. */
  .halluc {
    position: relative;
    display: flex;
    align-items: stretch;
    gap: 0;
    background: var(--badge-blocked-bg, #fee2e2);
    color: #7f1d1d;
    border: 2px solid var(--badge-blocked-border, #dc2626);
    border-radius: var(--radius-soft, 4px);
    overflow: hidden;
    /* repaint-cheap static depth -- NO keyframe animation (motion budget). */
    box-shadow: 0 1px 2px rgba(220, 38, 38, 0.18);
  }

  .halluc__spine {
    flex: 0 0 4px;
    background: var(--badge-blocked-fg, #dc2626);
    align-self: stretch;
  }

  .halluc__body {
    flex: 1 1 auto;
    min-width: 0;
    padding: var(--space-5, 14px) var(--space-6, 22px) var(--space-5, 14px) var(--space-5, 14px);
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 6px);
  }

  .halluc__head {
    display: flex;
    align-items: center;
    gap: var(--space-4, 10px);
    flex-wrap: wrap;
  }

  /* M4: paired headline. The dot is decorative; .halluc__label is the real,
     never-hidden signal text. */
  .halluc__badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: var(--badge-blocked-fg, #dc2626);
    line-height: 1;
  }

  .halluc__dot {
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: currentColor;
    flex: 0 0 auto;
  }

  /* Heaviest type step -- the headline is the load-bearing escalation signal.
     We restate the tuple locally so the card reads correctly even if calm.css
     is not yet in the cascade; .sev-critical reinforces it identically. */
  .halluc__label {
    font-family: var(--ff-system);
    font-size: var(--fs-badge, 12px);
    font-weight: 800;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--badge-blocked-fg, #dc2626);
  }

  .halluc__tag {
    font-family: var(--ff-mono);
    font-size: var(--fs-chrome, 11px);
    letter-spacing: 0.02em;
    color: #991b1b;
    background: rgba(220, 38, 38, 0.12);
    padding: 1px 6px;
    border-radius: var(--radius-sharp, 2px);
    white-space: nowrap;
  }

  .halluc__why {
    margin: 0;
    font-family: var(--ff-system);
    font-size: var(--fs-body, 14px);
    font-weight: 560;
    line-height: var(--lh-body, 1.5);
    color: #7f1d1d;
  }

  .halluc__evidence {
    margin: 0;
    display: flex;
    align-items: baseline;
    gap: var(--space-3, 6px);
    min-width: 0;
  }

  .halluc__evidence-tag {
    flex: 0 0 auto;
    font-size: var(--fs-chrome, 11px);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #991b1b;
  }

  /* The offending path -- forensic, monospaced, truncates rather than wraps.
     Full path on hover + a11y via title. Rendered verbatim from data (M16). */
  .halluc__path {
    font-family: var(--ff-mono);
    font-size: var(--fs-chrome, 11px);
    letter-spacing: 0.01em;
    color: #7f1d1d;
    background: rgba(220, 38, 38, 0.08);
    padding: 1px 6px;
    border-radius: var(--radius-sharp, 2px);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }

  .halluc__meta {
    margin: 0;
    font-family: var(--ff-mono);
    font-size: var(--fs-chrome, 11px);
    letter-spacing: 0.04em;
    color: #991b1b;
    font-variant-numeric: tabular-nums;
  }

  .halluc__actions {
    display: flex;
    align-items: center;
    gap: var(--space-4, 10px);
    margin-top: var(--space-2, 4px);
    flex-wrap: wrap;
  }

  .halluc__dismiss {
    appearance: none;
    font-family: var(--ff-system);
    font-size: var(--fs-meta, 13px);
    font-weight: 650;
    line-height: 1;
    padding: 7px 14px;
    border-radius: var(--radius-sharp, 2px);
    cursor: pointer;
    color: #fef2f2;
    background: var(--badge-blocked-fg, #dc2626);
    border: 1px solid #991b1b;
    transition: background var(--t-calm, 180ms ease);
  }
  .halluc__dismiss:hover {
    background: #b91c1c;
  }

  /* M17: restate the amber focus ring locally (focus.css also enforces it
     globally; the ring color is the constant operator anchor, not red). */
  .halluc__dismiss:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid)
      var(--focus-ring-color, #d97706);
    outline-offset: var(--focus-ring-offset, 2px);
  }

  .halluc__note {
    font-family: var(--ff-system);
    font-size: var(--fs-chrome, 11px);
    letter-spacing: 0.02em;
    color: #991b1b;
  }
</style>
