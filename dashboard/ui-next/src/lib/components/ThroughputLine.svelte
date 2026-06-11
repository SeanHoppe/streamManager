<!--
  ThroughputLine.svelte -- the ambient "is-it-alive" sparkline (calm-tech).

  GRAFT: this is the calm-ambient still-water heartbeat. It breathes with the
  DECISION RATE ONLY. It is deliberately, structurally NOT an urgency signal:
    - It never changes hue, never pulses red/amber, never grows a border.
    - Higher throughput = a taller, denser line; lower = flatter. That is the
      ENTIRE vocabulary. Severity / escalation is the exclusive job of the M2
      allow-list + M4 badges elsewhere -- never of this sparkline.
  Calm-tech thesis (winning concept): the one ambient motion in the resting
  product is "the monitor is alive", expressed in the single resting accent at
  low saturation. This keeps the lone true M2 escalation truly alone.

  DATA (M16 domain-agnostic): the only input is an aggregate decision counter
  from GET /api/stats (total_decisions). No governed-target identity is read,
  named, or rendered here. The component derives a rate from successive total
  readings sampled by the parent (the u-stores stats poller, 5s cadence), so it
  never sits on the verdict hot path (M18 -- post-hoc observability only).

  M18: pure presentation over an already-polled aggregate. No fetch of its own;
  no per-decision latency dependency. The parent feeds `total` (or a ready-made
  `series`); this leaf only renders.

  REDUCED MOTION (NFR-UI-7): the only motion is the sweep of the live dot along
  the most-recent sample. Under prefers-reduced-motion (and no force-allow) the
  sweep transition is dropped; the sparkline itself is static SVG either way.

  File-disjoint: depends only on theme tokens + props. Consumes no endpoints
  directly (the parent owns the /api/stats poll).
-->
<script>
  import { onDestroy } from 'svelte';

  /**
   * total: the latest GET /api/stats `total_decisions` aggregate. Monotonic
   * non-decreasing counter. Each new value the parent pushes is differenced
   * against the previous to derive a per-interval decision RATE sample. When
   * the parent prefers to own the math it may pass `series` directly instead.
   * @type {number|null|undefined}
   */
  export let total = undefined;

  /**
   * series: optional pre-computed rate samples (oldest -> newest). When given,
   * this is rendered verbatim and `total` differencing is bypassed. Lets a
   * test or a smarter parent supply an exact waveform.
   * @type {number[]|undefined}
   */
  export let series = undefined;

  /** points: how many samples the sparkline retains (its width in samples). */
  export let points = 32;

  /** width/height: intrinsic SVG viewBox. Scales fluidly via CSS. */
  export let width = 132;
  export let height = 22;

  /** label: accessible name. Domain-agnostic; never a governed-target name. */
  export let label = 'Decision throughput -- ambient liveness';

  // ---- internal rolling buffer of derived rate samples -------------------
  /** @type {number[]} */
  let buf = [];
  let lastTotal = null;

  // Difference successive totals into a rate sample. A counter reset (total
  // drops, e.g. server restart) is treated as a 0 sample rather than a negative
  // spike, so a restart never reads as a throughput cliff.
  function pushTotal(t) {
    const n = Number(t);
    if (!Number.isFinite(n)) return;
    if (lastTotal === null) {
      lastTotal = n;
      // seed one zero so the line has a baseline before the first delta
      buf = [0];
      return;
    }
    const delta = n - lastTotal;
    lastTotal = n;
    const sample = delta > 0 ? delta : 0;
    buf = [...buf, sample].slice(-points);
  }

  // React to parent-pushed `total` updates (the 5s stats poll cadence).
  $: if (series === undefined && total !== undefined && total !== null) {
    pushTotal(total);
  }

  // Effective sample set: explicit series wins; else our differenced buffer.
  $: samples = (series && series.length ? series : buf).slice(-points);

  // Is anything moving at all? Used only to drive the calm liveness dot's
  // breathing -- NOT a severity cue.
  $: alive = samples.length > 0 && samples.some((s) => s > 0);

  // ---- geometry: map samples -> a smooth-ish polyline in the viewBox ------
  // Normalise to the running max so the line "breathes" with relative rate.
  // A floor of 1 avoids div-by-zero on an all-zero (quiet) buffer.
  $: peak = Math.max(1, ...samples);

  $: coords = (() => {
    const n = samples.length;
    if (n === 0) return [];
    const innerW = width - 2; // 1px inset each side so strokes are not clipped
    const innerH = height - 2;
    const stepX = n > 1 ? innerW / (n - 1) : 0;
    return samples.map((s, i) => {
      const x = 1 + i * stepX;
      // invert Y (SVG origin top-left); keep a 1px floor so a 0 still draws.
      const norm = Math.max(0, Math.min(1, s / peak));
      const y = 1 + (innerH - innerH * norm);
      return [x, y];
    });
  })();

  $: linePath = coords.length
    ? 'M ' + coords.map(([x, y]) => `${x.toFixed(2)} ${y.toFixed(2)}`).join(' L ')
    : '';

  // Area path (line down to the baseline and back) for the faint wash fill.
  $: areaPath = coords.length
    ? `${linePath} L ${coords[coords.length - 1][0].toFixed(2)} ${height - 1} ` +
      `L ${coords[0][0].toFixed(2)} ${height - 1} Z`
    : '';

  // The live dot rides the most-recent sample.
  $: head = coords.length ? coords[coords.length - 1] : null;

  // Accessible summary: a single quiet sentence, no numbers that imply urgency.
  $: srText = alive
    ? 'Decision throughput active -- monitor live.'
    : 'No decisions in the recent window -- monitor idle, still live.';

  onDestroy(() => {
    buf = [];
    lastTotal = null;
  });
</script>

<div
  class="tl"
  class:tl--idle={!alive}
  role="img"
  aria-label={label}
  title={label}
>
  <svg
    class="tl__svg"
    viewBox={`0 0 ${width} ${height}`}
    preserveAspectRatio="none"
    aria-hidden="true"
    focusable="false"
  >
    {#if areaPath}
      <path class="tl__area" d={areaPath} />
    {/if}
    {#if linePath}
      <path class="tl__line" d={linePath} />
    {/if}
    {#if head}
      <circle class="tl__dot" cx={head[0]} cy={head[1]} r="1.6" />
    {/if}
  </svg>

  <!-- The text channel: the line is decorative; this sentence carries meaning
       for assistive tech so liveness is never a color/shape-only signal. -->
  <span class="tl__sr">{srText}</span>
</div>

<style>
  .tl {
    display: inline-flex;
    align-items: center;
    height: 100%;
    min-width: 0;
    /* the sparkline rides quietly in the header chrome; it must never out-shout
       a badge, so its container has no border, no background, no glow. */
  }

  .tl__svg {
    display: block;
    width: 100%;
    height: 100%;
    /* the only animation here is the head-dot breathing; nothing reflows. */
  }

  /* The line: a single hairline in the resting accent at LOW saturation. This
     is the one ambient liveness affordance the calm-ambient spine permits. */
  .tl__line {
    fill: none;
    stroke: var(--calm-accent, var(--accent, #f59e0b));
    stroke-width: 1.25;
    stroke-linejoin: round;
    stroke-linecap: round;
    /* keep it whisper-quiet: the accent is dimmed so it reads as ambient, not
       as a signal competing with the ACTION REQUIRED amber. */
    opacity: 0.55;
  }

  /* The wash beneath the line -- the faintest possible fill so the waveform has
     body without weight. Uses the accent wash token (already low-alpha). */
  .tl__area {
    fill: var(--calm-accent-wash, var(--accent-dim, rgba(245, 158, 11, 0.09)));
    stroke: none;
  }

  /* The live head dot: the "is-it-alive" heartbeat. Breathes via opacity only
     (composited, repaint-cheap -- M18) and NEVER changes hue. */
  .tl__dot {
    fill: var(--calm-accent, var(--accent, #f59e0b));
    animation: tl-breath 2.6s ease-in-out infinite;
  }

  /* Idle: flatten the affordance further so quiet truly looks quiet. */
  .tl--idle .tl__line { opacity: 0.3; }
  .tl--idle .tl__dot { animation-duration: 4s; opacity: 0.5; }

  @keyframes tl-breath {
    0%, 100% { opacity: 1; }
    50%      { opacity: 0.35; }
  }

  /* Visually-hidden accessible text (the meaning channel). */
  .tl__sr {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }

  /* NFR-UI-7 reduced motion: still the heartbeat (the SVG stays drawn; only the
     breathing stops) unless the operator force-allows motion. */
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .tl__dot { animation: none; }
  }
  :global(html[data-motion='reduce']) .tl__dot { animation: none !important; }
  :global(html[data-motion='allow']) .tl__dot {
    animation: tl-breath 2.6s ease-in-out infinite !important;
  }
</style>
