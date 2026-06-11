<!--
  CountdownBar.svelte -- M9 HITL countdown primitive.

  CONTRACT (inviolable MUST M9):
    - Each pending row shows a 1s-tick countdown, default 60s.
    - On expiry the row gets opacity .35 + grayscale. This component owns the
      bar + (optionally, via the `expired` event + `dim` prop) the dimming of
      its own wrapper; the parent row also reacts to the `expired` event to dim
      the whole HITL item, matching the live dashboard `.hitl-item.expired`
      rule (opacity:.35; filter:grayscale(.6)).
    - 1s linear tick: the fill width transitions over 1s linear, ticked once a
      second, mirroring the live dashboard `.hitl-bar-fill { transition: width
      1s linear }` + `setInterval(..., 1000)` contract.

  CRAFT (calm-ambient spine, KingMode): at rest the bar is a thin, quiet lane
  in the `--accent` (paper theme retints to ink). It does not pulse, flash, or
  change hue as time runs out -- calm tech: the passage of time is the signal,
  not alarm chrome. Severity (near-expiry) is encoded as a subtle type/opacity
  shift on the optional readout, never as a saturation spike.

  REDUCED MOTION (NFR-UI-7): when the operator has not force-allowed motion and
  the OS reports prefers-reduced-motion, the width transition is dropped so the
  bar steps rather than glides -- the countdown remains fully functional.

  This component depends only on theme tokens + an internal interval. It is
  file-disjoint from every logic unit and consumes no endpoints. The driving
  clock is self-contained so the bar is correct even when rendered standalone;
  parents MAY instead pass a `startedAt` epoch to resume an in-flight countdown
  across re-renders (matches HITL.startedAt resume semantics).
-->
<script>
  import { onDestroy, createEventDispatcher } from 'svelte';

  /** Total countdown duration in seconds. Default 60s (M9). */
  export let seconds = 60;

  /**
   * startedAt: optional epoch-ms the countdown began. When supplied the bar
   * resumes from elapsed-since-startedAt (so re-mounts/re-renders don't reset
   * the clock) -- mirrors the live dashboard HITL.startedAt resume contract.
   * When omitted we stamp "now" on first mount.
   */
  export let startedAt = undefined;

  /**
   * running: set false to freeze the bar (e.g. row already resolved). A frozen
   * bar keeps its current width and stops ticking; it does not fire `expired`.
   */
  export let running = true;

  /**
   * dim: when true, apply the expired dimming (opacity .35 + grayscale) to this
   * component's own wrapper. Parents that dim the whole row themselves on the
   * `expired` event can leave this false. Defaults to true so the primitive is
   * correct standalone.
   */
  export let dim = true;

  /** showReadout: render a small MM:SS / Ns remaining readout under the bar. */
  export let showReadout = false;

  /** label: accessible name for the progress bar. */
  export let label = 'HITL countdown';

  const dispatch = createEventDispatcher();

  const total = Math.max(1, Number(seconds) || 60);

  // Resolve the start epoch once. If a parent passes startedAt we honor it
  // (resume); otherwise we stamp mount time.
  let start = startedAt != null ? Number(startedAt) : Date.now();
  $: if (startedAt != null && Number(startedAt) !== start) {
    // Parent re-keyed the countdown to a new origin; re-sync.
    start = Number(startedAt);
    expiredFired = false;
  }

  let remaining = total;
  let expired = false;
  let expiredFired = false;
  let timer = null;

  function compute() {
    const elapsed = (Date.now() - start) / 1000;
    remaining = Math.max(0, total - elapsed);
    if (remaining <= 0) {
      remaining = 0;
      if (!expired) {
        expired = true;
        if (!expiredFired) {
          expiredFired = true;
          // Notify the parent so it can dim the full HITL item row (M9).
          dispatch('expired');
        }
      }
      stop();
    }
  }

  function tick() {
    compute();
  }

  function stop() {
    if (timer != null) {
      clearInterval(timer);
      timer = null;
    }
  }

  function startTimer() {
    stop();
    compute(); // immediate paint so we never show a stale full bar for ~1s
    if (!expired && running) {
      timer = setInterval(tick, 1000);
    }
  }

  // (Re)start whenever running flips on or the origin changes.
  $: if (running && !expired) {
    startTimer();
  } else if (!running) {
    stop();
  }

  onDestroy(stop);

  // remaining -> fill percentage (100% at start, 0% at expiry).
  $: pct = Math.max(0, Math.min(100, (remaining / total) * 100));

  // Quiet, calm-tech readout. Sub-10s shows whole seconds with a subtle
  // emphasis via the .is-low class (type weight, not hue alarm).
  $: secsLeft = Math.ceil(remaining);
  $: isLow = remaining > 0 && remaining <= 10;
</script>

<div
  class="cb-wrap"
  class:expired={expired && dim}
  data-expired={expired ? 'true' : 'false'}
>
  <div
    class="cb-track"
    role="progressbar"
    aria-label={label}
    aria-valuemin="0"
    aria-valuemax={total}
    aria-valuenow={secsLeft}
    aria-valuetext={expired ? 'expired' : `${secsLeft}s remaining`}
  >
    <div class="cb-fill" style="width:{pct}%"></div>
  </div>

  {#if showReadout}
    <div class="cb-readout" class:is-low={isLow} aria-hidden="true">
      {#if expired}
        <span class="cb-expired-text">expired</span>
      {:else}
        {secsLeft}s
      {/if}
    </div>
  {/if}
</div>

<style>
  .cb-wrap {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    /* M9 expiry transition is itself calm -- a slow fade into the dimmed
       resting state, not a snap. */
    transition: opacity 0.3s ease;
  }

  /* M9 expiry: opacity .35 + grayscale. Mirrors live `.hitl-item.expired`. */
  .cb-wrap.expired {
    opacity: 0.35;
    filter: grayscale(0.6);
  }

  .cb-track {
    flex: 1 1 auto;
    height: 4px;
    background: var(--border, #cbd5e1);
    border-radius: 2px;
    overflow: hidden;
  }

  .cb-fill {
    height: 100%;
    width: 100%;
    background: var(--accent, #d97706);
    /* 1s linear tick (M9): the fill glides one second's worth per tick. */
    transition: width 1s linear;
  }

  /* Paper theme retints the fill to ink, matching the live dashboard override
     so the countdown stays legible on the warm paper ground. */
  :global([data-theme='paper']) .cb-fill {
    background: #2a2018;
  }

  .cb-readout {
    flex: 0 0 auto;
    min-width: 3ch;
    text-align: right;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.04em;
    color: var(--text-dim, #64748b);
    font-variant-numeric: tabular-nums;
  }

  /* Near-expiry emphasis via type weight, not a hue alarm (calm tech). */
  .cb-readout.is-low {
    font-weight: 700;
    color: var(--text, #1e293b);
  }

  .cb-expired-text {
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  /* NFR-UI-7 reduced motion: drop the gliding fill + expiry fade so the bar
     steps discretely. The countdown stays fully functional; only the motion is
     removed. Suppressed when the operator has force-allowed motion. */
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .cb-fill {
      transition: none;
    }
    :global(html:not([data-motion='allow'])) .cb-wrap {
      transition: none;
    }
  }

  /* Operator force-reduce: kill motion unconditionally. */
  :global(html[data-motion='reduce']) .cb-fill,
  :global(html[data-motion='reduce']) .cb-wrap {
    transition: none !important;
  }

  /* Operator force-allow: re-assert the gliding fill. */
  :global(html[data-motion='allow']) .cb-fill {
    transition: width 1s linear !important;
  }
</style>
