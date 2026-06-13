<!--
  ConfidenceCalibrationLoop.svelte -- BETA feature "confidence-calibration-loop"
  (#8): make the confidence number mean something.

  WHAT IT IS
    A read-only CALIBRATION view (observability, NOT a Frame). It buckets the
    existing governed decisions by predicted confidence (deciles) and, for each
    decile, computes realized operator-agreement = 1 - override_rate against
    hitl_overrides. It renders a square reliability diagram (the perfect-
    calibration diagonal + the measured curve) plus a decile rail + per-decile
    detail tray, so the operator can SEE where "0.95 confidence" actually means
    ~82% agreement. An OPT-IN advisory transform toggle (DEFAULT OFF) is offered
    that, when ON, only annotates ADVISORY presentation surfaces -- it NEVER
    changes the verdict or writes decisions.confidence.

  BETA GATE (load-bearing)
    The ENTIRE component is wrapped in {#if $betaFlags['confidence-calibration-
    loop']}. When the flag is OFF it renders NOTHING and registers NO fetch /
    poller / SSE / timer -- zero runtime cost. The flag defaults OFF
    (lib/beta/registry.js); the operator flips it in Settings > BETA features.
    There is NO SSE and NO poller here at all: calibration is read once per
    drawer-open via a single post-hoc GET (M18). It is a DRAWER reached from a
    quiet launcher chip, never a fourth Frame, and NEVER auto-foregrounds.

  DATA
    Reads GET /api/governance/calibration?days=&buckets=. The server aggregates
    decisions x hitl_overrides, polarity-filtered (project_slug NOT IN
    {streamManager} AND session_id != self) so SM-self is never measured against
    itself (G2). When the endpoint is absent or returns an empty/zero set (fresh
    DB, no decisions, server down), the view falls back to a deterministic mock
    fixture (ConfidenceCalibrationLoop-data.js) so it is always inspectable; the
    mock state is labelled with a "Sample data" chip.

  TEST BRIDGE
    A documented window event `confidence-calibration-loop:open` opens the
    drawer (used by the Playwright spec so it is independent of live gov.db
    state). The event is a no-op when the flag is OFF (component not mounted ->
    no listener), which the spec asserts.

  ADR-18 MUST floor honoured here:
    - M2: never auto-foregrounds; the chip + drawer are operator-invoked only;
      a still reliability field, no pulse/motion.
    - M4 (paired label+color): every decile carries the SIGN word (OVER / UNDER
      / CALIBRATED / LOW N) + the literal gap in points + a node SHAPE (filled
      square = over, hollow = under, dot = calibrated, dashed = low sample). The
      band tint is a reinforcing channel only; a desaturated render still reads.
    - M13/M8 (advisory-only): the opt-in transform is DEFAULT OFF and scoped to
      advisory DISPLAY; it never touches the verdict or decisions.confidence.
    - M16 (domain-agnostic): no monitored-project vocabulary; the governed-target
      identity (scope) is rendered FROM DATA.
    - M17 (a11y): chip is a real <button> with aria-haspopup; the drawer is
      role=dialog aria-modal with a labelled heading, Escape-to-close, focus
      moved in on open + restored on close, focus trap. The decile RAIL is the
      focusable control (roving tabindex, Up/Down/Home/End, Enter opens the
      tray, Escape closes + restores focus). The diagram is role=img with a
      headline aria-label. Reduced motion honoured via the data-motion attr.
    - M18: pure post-hoc GET; never on the verdict hot path; no bus envelope.
    - G2 (polarity): SM-self is excluded server-side; excluded_self is shown.

  ASCII-only (cp1252-safe): dash rendered as "--". No smart quotes / em-dash.
-->
<script>
  import { tick, onDestroy } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { getCalibration } from '../../api.js';
  import {
    MIN_N,
    mockCalibration,
    pct,
    fmtN,
    gapPoints,
    shapeFor,
    transformFor,
    worstGap,
    signWords,
    railGapText,
    isUsableLive,
  } from './ConfidenceCalibrationLoop-data.js';

  const FLAG_KEY = 'confidence-calibration-loop';
  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // ---- drawer open/close + focus contract (mirrors CoverageAnalyzer) --------
  let open = false;
  /** @type {HTMLDivElement|null} */
  let panelEl = null;
  /** @type {HTMLButtonElement|null} */
  let chipEl = null;
  /** @type {Element|null} */
  let prevFocus = null;

  // ---- data state -----------------------------------------------------------
  let loading = false;
  let usedMockData = false;
  /** @type {Record<string, any>|null} */
  let data = null;

  /** @type {number|null} the active decile idx (tray open), or null */
  let activeIdx = null;
  /** the opt-in advisory-transform display toggle (DEFAULT OFF, advisory-only) */
  let optinOn = false;

  /**
   * Load calibration once (drawer-open only -- NO poller). Best-effort: any
   * failure or empty result degrades to the deterministic mock so the view is
   * always inspectable. Never throws to the render path.
   */
  async function load() {
    loading = true;
    let payload = null;
    try {
      payload = await getCalibration({ days: 30, buckets: 10 });
    } catch {
      payload = null;
    }
    if (isUsableLive(payload)) {
      data = payload;
      usedMockData = false;
    } else {
      data = mockCalibration();
      usedMockData = true;
    }
    loading = false;
  }

  // ---- derived view model ----------------------------------------------------
  $: buckets = (data && Array.isArray(data.buckets)) ? data.buckets : [];
  $: worst = worstGap(buckets);
  $: worstLabel = worst
    ? gapPoints(worst.gap) + ' pts ' + (worst.sign === 'OVER' ? 'over' : worst.sign === 'UNDER' ? 'under' : 'ok')
    : 'n/a';
  $: maxN = buckets.reduce((m, b) => Math.max(m, Number(b.n) || 0), 0) || 1;
  $: activeBucket = activeIdx == null ? null : buckets.find((b) => b.idx === activeIdx) || null;
  $: activeTransform = activeBucket ? transformFor(data && data.transform, activeBucket.predicted) : null;

  // SVG plot coords: X = predicted (0..1 -> 0..100); Y = realized agreement
  // (0..1 -> 100..0 so higher agreement sits HIGHER on the square field).
  const px = (p) => (Number(p) || 0) * 100;
  const py = (r) => 100 - (Number(r) || 0) * 100;

  /** curve polyline points "x,y x,y ..." across the deciles. */
  $: curvePoints = buckets.map((b) => px(b.predicted) + ',' + py(b.realized)).join(' ');

  /** node half-extent scaled by sqrt(n) (visual weight), matching the mockup. */
  function nodeSize(n) {
    return 2.2 + 3.8 * Math.sqrt((Number(n) || 0) / maxN);
  }

  // ---- drawer lifecycle ------------------------------------------------------
  async function openDrawer() {
    if (!enabled || open) return;
    prevFocus = (typeof document !== 'undefined' && document.activeElement) || null;
    open = true;
    if (!data) await load();
    await tick();
    // focus the first decile row (the primary control) if present, else panel.
    const firstRow = panelEl && panelEl.querySelector('.rrow[tabindex="0"]');
    if (firstRow && typeof firstRow.focus === 'function') firstRow.focus();
    else if (panelEl) panelEl.focus();
  }

  function closeDrawer() {
    if (!open) return;
    open = false;
    activeIdx = null;
    if (prevFocus && typeof prevFocus.focus === 'function') prevFocus.focus();
    else if (chipEl) chipEl.focus();
    prevFocus = null;
  }

  // ---- decile selection (tray) ----------------------------------------------
  function selectDecile(idx, focusRow) {
    if (!buckets.some((b) => b.idx === idx)) return;
    activeIdx = idx;
    if (focusRow) {
      tick().then(() => {
        const row = panelEl && panelEl.querySelector('.rrow[data-idx="' + idx + '"]');
        if (row && typeof row.focus === 'function') row.focus();
      });
    }
  }

  function closeTray(restoreFocus) {
    const prev = activeIdx;
    activeIdx = null;
    if (restoreFocus && prev != null) {
      tick().then(() => {
        const row = panelEl && panelEl.querySelector('.rrow[data-idx="' + prev + '"]');
        if (row && typeof row.focus === 'function') row.focus();
      });
    }
  }

  // ---- M17 rail keyboard path (roving tabindex; Up/Down/Home/End/Enter/Esc) --
  function railKeydown(e) {
    const rows = panelEl ? Array.from(panelEl.querySelectorAll('.rrow')) : [];
    if (rows.length === 0) return;
    const pos = rows.indexOf(document.activeElement);
    if (e.key === 'ArrowDown') {
      const next = rows[pos < 0 ? 0 : Math.min(rows.length - 1, pos + 1)];
      next.focus();
      e.preventDefault();
    } else if (e.key === 'ArrowUp') {
      const prev = rows[pos < 0 ? 0 : Math.max(0, pos - 1)];
      prev.focus();
      e.preventDefault();
    } else if (e.key === 'Home') {
      rows[0].focus();
      e.preventDefault();
    } else if (e.key === 'End') {
      rows[rows.length - 1].focus();
      e.preventDefault();
    } else if (e.key === 'Enter' || e.key === ' ') {
      if (pos > -1) {
        selectDecile(parseInt(rows[pos].getAttribute('data-idx'), 10), false);
        e.preventDefault();
      }
    } else if (e.key === 'Escape') {
      if (activeIdx != null) {
        closeTray(true);
        e.stopPropagation();
        e.preventDefault();
      }
    }
  }

  // ---- drawer-level focus trap + Escape -------------------------------------
  function onDrawerKeydown(e) {
    if (e.key === 'Escape') {
      if (activeIdx != null) {
        closeTray(false);
      } else {
        closeDrawer();
      }
      e.preventDefault();
      return;
    }
    if (e.key !== 'Tab' || !panelEl) return;
    const focusables = panelEl.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    if (focusables.length === 0) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      last.focus();
      e.preventDefault();
    } else if (!e.shiftKey && document.activeElement === last) {
      first.focus();
      e.preventDefault();
    }
  }

  // ---- documented test/open bridge ------------------------------------------
  // `confidence-calibration-loop:open` window CustomEvent opens the drawer (used
  // by the Playwright spec so it is independent of live gov.db state). The
  // listener is registered ONLY while ENABLED and torn down the moment the flag
  // flips OFF (load-bearing gate: when OFF there is NO listener, so the event is
  // a no-op -- the spec asserts this). Mirrors DecisionOracle's window bridge.
  const OPEN_EVENT = 'confidence-calibration-loop:open';
  let _bridgeBound = false;
  function onOpenBridge() {
    openDrawer();
  }
  function bindBridge() {
    if (_bridgeBound || typeof window === 'undefined') return;
    window.addEventListener(OPEN_EVENT, onOpenBridge);
    _bridgeBound = true;
  }
  function unbindBridge() {
    if (!_bridgeBound || typeof window === 'undefined') return;
    window.removeEventListener(OPEN_EVENT, onOpenBridge);
    _bridgeBound = false;
    // Tearing the bridge down also closes any open drawer so OFF means gone.
    if (open) {
      open = false;
      activeIdx = null;
    }
  }
  // Reactively bind/unbind purely on the gate. When OFF: no listener, no fetch,
  // no timer -- zero runtime cost (BETA gate is load-bearing).
  $: if (enabled) bindBridge();
  $: if (!enabled) unbindBridge();
  onDestroy(unbindBridge);
</script>

{#if enabled}
  <!-- The quiet launcher chip (operator-invoked; M2 -- never auto-opens). -->
  <button
    type="button"
    class="ccl-chip"
    bind:this={chipEl}
    aria-haspopup="dialog"
    aria-expanded={open}
    on:click={openDrawer}
  >
    <span class="ccl-chip__glyph" aria-hidden="true"></span>
    <span class="ccl-chip__label">Confidence calibration</span>
    <span class="ccl-chip__beta">BETA</span>
  </button>

  {#if open}
    <!-- scrim -->
    <div
      class="ccl-scrim"
      on:click={closeDrawer}
      aria-hidden="true"
    ></div>

    <!-- the drawer / dialog -->
    <div
      class="ccl"
      bind:this={panelEl}
      role="dialog"
      aria-modal="true"
      aria-label="Confidence calibration (BETA)"
      tabindex="-1"
      on:keydown={onDrawerKeydown}
    >
      <div class="ccl__head">
        <div class="ccl__titlewrap">
          <div class="ccl__titlerow">
            <h2 class="ccl__title">Confidence calibration</h2>
            <span class="ccl__beta">BETA -- default OFF, toggled in Settings</span>
          </div>
          {#if data}
            <p class="ccl__sub">
              predicted confidence vs realized operator-agreement (1 - override rate) --
              last {data.days || 30} days, {data.bucket_count || 10} deciles --
              scope <span class="ccl__scope">{data.scope || 'all governed sessions'}</span> --
              self excluded (G2): <span>{data.excluded_self || 0}</span> sessions
            </p>
          {/if}
        </div>
        <button
          type="button"
          class="ccl__close"
          aria-label="Close confidence calibration (Escape)"
          on:click={closeDrawer}
        >Close (Esc)</button>
      </div>

      {#if loading && !data}
        <p class="ccl__off">Loading calibration...</p>
      {:else if data}
        <div class="ccl__body">
          <!-- headline stats -->
          <div class="ccl__stats">
            <div class="stat">
              <span class="stat__v">{pct(data.overall_agreement)}</span>
              <span class="stat__k">overall agreement</span>
            </div>
            <div class="stat">
              <span class="stat__v">{Number(data.brier || 0).toFixed(3)}</span>
              <span class="stat__k">Brier score</span>
            </div>
            <div class="stat">
              <span class="stat__v worst">{worstLabel}</span>
              <span class="stat__k">worst gap{worst ? ' (' + Number(worst.lo).toFixed(1) + '-' + Number(worst.hi).toFixed(1) + ' band)' : ''}</span>
            </div>
            <div class="stat">
              <span class="stat__v">{fmtN(data.total_decisions)}</span>
              <span class="stat__k">decisions / {fmtN(data.total_overrides)} overrides</span>
            </div>
            {#if usedMockData}
              <span
                class="samplechip"
                title="The live GET /api/governance/calibration endpoint was empty or unavailable, so a deterministic sample fixture is shown."
              >Sample data</span>
            {/if}
          </div>

          <div class="ccl__split">
            <!-- the square reliability FIELD (role=img; headline aria) -->
            <div class="field">
              <div class="field__svgwrap">
                <span class="axis-y" aria-hidden="true">realized agreement -- up</span>
                <span class="axis-x" aria-hidden="true">predicted confidence -- right</span>
                <svg
                  viewBox="0 0 100 100"
                  role="img"
                  aria-label={'Calibration curve. Overall operator-agreement ' + pct(data.overall_agreement) + ', Brier score ' + Number(data.brier || 0).toFixed(3) + '. ' + (worst ? 'Worst gap is ' + worstLabel + ' in the ' + Number(worst.lo).toFixed(1) + ' to ' + Number(worst.hi).toFixed(1) + ' band.' : '')}
                >
                  <g aria-hidden="true">
                    <line class="gridline" x1="0" y1="25" x2="100" y2="25" />
                    <line class="gridline" x1="0" y1="50" x2="100" y2="50" />
                    <line class="gridline" x1="0" y1="75" x2="100" y2="75" />
                    <line class="gridline" x1="25" y1="0" x2="25" y2="100" />
                    <line class="gridline" x1="50" y1="0" x2="50" y2="100" />
                    <line class="gridline" x1="75" y1="0" x2="75" y2="100" />
                    <text class="tick-text" x="1.5" y="99">0</text>
                    <text class="tick-text" x="89" y="99">1.0</text>
                    <text class="tick-text" x="1.5" y="6">1.0</text>
                  </g>
                  <!-- the perfect-calibration diagonal (predicted = actual) -->
                  <line class="diag" x1="0" y1="100" x2="100" y2="0" />
                  <text class="diag-label" x="52" y="44" transform="rotate(-45 52 44)">perfect calibration</text>

                  <!-- drop-lines: node -> diagonal (the literal miscalibration gap) -->
                  <g aria-hidden="true">
                    {#each buckets as b (b.idx)}
                      <line
                        class={'dropline drop-' + b.band}
                        x1={px(b.predicted)} y1={py(b.realized)}
                        x2={px(b.predicted)} y2={py(b.predicted)}
                      />
                    {/each}
                  </g>

                  <!-- the measured curve -->
                  <polyline class="curve" points={curvePoints} aria-hidden="true"></polyline>

                  <!-- nodes: shape carries the sign (M4); size by sqrt(n) -->
                  <g>
                    {#each buckets as b (b.idx)}
                      {@const sz = nodeSize(b.n)}
                      {@const cx = px(b.predicted)}
                      {@const cy = py(b.realized)}
                      {@const shape = shapeFor(b)}
                      <rect
                        class="node-ring"
                        class:is-active={activeIdx === b.idx}
                        x={cx - sz - 2} y={cy - sz - 2}
                        width={sz * 2 + 4} height={sz * 2 + 4}
                        rx="1.5" aria-hidden="true"
                      />
                      {#if shape === 'cal'}
                        <circle
                          class={'node band-' + b.band + ' node--cal'}
                          class:is-active={activeIdx === b.idx}
                          cx={cx} cy={cy} r={sz * 0.85}
                          role="presentation"
                          on:click={() => selectDecile(b.idx, true)}
                        />
                      {:else}
                        <rect
                          class={'node band-' + b.band + ' node--' + shape + (shape === 'low' ? ' node--lowsample' : shape === 'under' ? ' node--under' : '')}
                          class:is-active={activeIdx === b.idx}
                          x={cx - sz} y={cy - sz}
                          width={sz * 2} height={sz * 2}
                          role="presentation"
                          on:click={() => selectDecile(b.idx, true)}
                        />
                      {/if}
                    {/each}
                  </g>
                </svg>
              </div>
            </div>

            <!-- the decile RAIL (focusable; the whole story survives here) -->
            <div
              class="rail"
              role="group"
              aria-label="Calibration deciles -- use Up and Down arrows to move, Enter to open a bucket, Escape to close"
              on:keydown={railKeydown}
            >
              <div class="rail__cap">
                <span>decile</span>
                <span>predicted / actual / gap</span>
              </div>
              <div class="rail__rows">
                {#each buckets as b, i (b.idx)}
                  {@const low = (Number(b.n) || 0) < MIN_N}
                  {@const shape = shapeFor(b)}
                  {@const gp = gapPoints(b.gap)}
                  <button
                    type="button"
                    class="rrow"
                    class:is-active={activeIdx === b.idx}
                    data-band={b.band}
                    data-idx={b.idx}
                    tabindex={activeIdx == null ? (i === 0 ? 0 : -1) : (activeIdx === b.idx ? 0 : -1)}
                    aria-label={Number(b.lo).toFixed(1) + ' to ' + Number(b.hi).toFixed(1) + ' band. n ' + b.n + ' decisions, ' + b.overrides + ' overrides. predicted ' + pct(b.predicted) + ', realized agreement ' + pct(b.realized) + '. ' + (low ? 'low sample, below the floor.' : b.sign + ', gap ' + gp + ' points. Activate to open detail.')}
                    on:click={() => selectDecile(b.idx, false)}
                  >
                    <span class="rrow__decile">{Number(b.lo).toFixed(1)}-{Number(b.hi).toFixed(1)}</span>
                    <span class="rrow__nums">n={fmtN(b.n)} | pred <b>{pct(b.predicted)}</b> | actual <b>{pct(b.realized)}</b></span>
                    <span class="sign" data-sign={low ? 'LOWSAMPLE' : b.sign}>
                      <span class="sign__glyph" data-shape={shape} aria-hidden="true"></span>
                      <span>{low ? 'LOW N' : b.sign}</span>
                      <span class="sign__gap">{railGapText(b)}</span>
                    </span>
                  </button>
                {/each}
              </div>
            </div>
          </div>

          <!-- the calm inline tray (one decile expanded) -->
          {#if activeBucket}
            <div class="tray" role="region" aria-label="Selected decile detail">
              <div class="tray__head">
                <span class="tray__title">{Number(activeBucket.lo).toFixed(1)} -- {Number(activeBucket.hi).toFixed(1)} band</span>
                <button
                  type="button"
                  class="tray__close"
                  aria-label="Close decile detail (Escape)"
                  on:click={() => closeTray(true)}
                >Close (Esc)</button>
              </div>
              <div class="tray__body">
                <div class="tfact"><span class="tfact__k">decisions (n)</span><span class="tfact__v">{fmtN(activeBucket.n)}</span></div>
                <div class="tfact"><span class="tfact__k">overrides</span><span class="tfact__v">{fmtN(activeBucket.overrides)}</span></div>
                <div class="tfact"><span class="tfact__k">predicted</span><span class="tfact__v">{pct(activeBucket.predicted)}</span></div>
                <div class="tfact"><span class="tfact__k">realized agreement</span><span class="tfact__v">{pct(activeBucket.realized)}</span></div>
                <p class="tray__words">
                  <b>{(Number(activeBucket.n) || 0) < MIN_N ? 'LOW SAMPLE' : activeBucket.sign}</b> -- {signWords(activeBucket)}{#if activeTransform} Fitted advisory transform for this band: {Number(activeBucket.predicted).toFixed(2)} maps to {Number(activeTransform.to).toFixed(2)} (used only by the opt-in display toggle).{/if}
                </p>
              </div>
            </div>
          {/if}

          <!-- OPT-IN advisory transform (DEFAULT OFF, advisory-only, M13/M8) -->
          <div class="optin">
            <div class="optin__row">
              <div class="optin__copy">
                <p class="optin__title">Apply calibration to advisory presentation</p>
                <p class="optin__desc">
                  When ON, the calibrated value is shown alongside the raw confidence on
                  ADVISORY surfaces only -- the ConfidenceChip dial and the floor read.
                  <b>It never changes the verdict and never writes decisions.confidence.</b>
                  Display-layer only.
                </p>
              </div>
              <div class="optin__control">
                <span class="optin__state" data-on={optinOn}>{optinOn ? 'ON' : 'OFF'}</span>
                <button
                  type="button"
                  class="switch"
                  role="switch"
                  aria-checked={optinOn}
                  aria-label="Apply calibration to advisory presentation. Default OFF. Advisory display only -- never alters the verdict or decisions.confidence."
                  on:click={() => (optinOn = !optinOn)}
                ></button>
              </div>
            </div>
            {#if optinOn}
              <div class="optin__scope">
                ON -- advisory display only. Example: a raw 0.95 in the 0.9 band now shows
                "0.95 raw -- 0.82 calibrated" on the chip dial. The verdict and the stored
                decisions.confidence are untouched (M13 / ADR-18 FROZEN governance path).
              </div>
            {/if}
          </div>

          <div class="ccl__foot">
            <span class="legend" aria-label="Node-shape legend (shape carries the sign; color reinforces)">
              <span class="lk"><span class="lk__shape" data-shape="over" aria-hidden="true"></span>filled square = OVER-confident</span>
              <span class="lk"><span class="lk__shape" data-shape="under" aria-hidden="true"></span>hollow square = UNDER-confident</span>
              <span class="lk"><span class="lk__shape" data-shape="cal" aria-hidden="true"></span>dot = CALIBRATED</span>
              <span class="lk"><span class="lk__shape" data-shape="low" aria-hidden="true"></span>dashed = low sample (n &lt; {MIN_N})</span>
            </span>
          </div>
        </div>
      {/if}
    </div>
  {/if}
{/if}

<style>
  /* ===========================================================================
     Tokens are inherited from styles/theme.css (the calm-* / --c-* / --text* /
     --accent / badge tokens). NO new color token is invented; the action ramp
     (--c-allow / --c-suggest / --c-intervene / --c-block) is reused as the
     calibration BAND tint exactly as the heat-map pane reuses it. Spacing falls
     back to literal px where a --space-* token is not guaranteed in scope.
  =========================================================================== */

  /* ---- the quiet launcher chip --------------------------------------------- */
  .ccl-chip {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 11px;
    letter-spacing: 0.04em;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    background: var(--calm-surface-row, var(--bg-row, #0e141e));
    border: 1px solid var(--calm-hairline, var(--border, #192030));
    border-radius: 4px;
    padding: 5px 10px;
    cursor: pointer;
  }
  .ccl-chip:hover { background: var(--calm-surface-hover, var(--bg-row-hover, #131c2a)); }
  .ccl-chip:focus-visible { outline: 2px solid var(--calm-accent, var(--accent, #f59e0b)); outline-offset: 2px; }
  .ccl-chip__glyph {
    width: 9px; height: 9px; flex: 0 0 auto;
    border: 1.5px solid var(--calm-accent, var(--accent, #f59e0b));
    transform: rotate(45deg);
  }
  .ccl-chip__label { color: var(--calm-ink, var(--text, #b8b098)); }
  .ccl-chip__beta {
    font-size: 9px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--badge-obs-fg, #475569);
    background: var(--badge-obs-bg, #f1f5f9);
    border: 1px solid var(--badge-obs-border, #cbd5e1);
    border-radius: 3px;
    padding: 1px 5px;
  }

  /* ---- scrim + drawer ------------------------------------------------------- */
  .ccl-scrim {
    position: fixed; inset: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 80;
  }
  .ccl {
    position: fixed;
    z-index: 81;
    top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    width: min(920px, calc(100vw - 32px));
    max-height: calc(100vh - 48px);
    overflow: auto;
    background: var(--calm-surface-raised, var(--bg-card, #0c1118));
    border: 1px solid var(--calm-hairline, var(--border, #192030));
    border-radius: 8px;
    padding: 22px;
    color: var(--calm-ink, var(--text, #b8b098));
  }
  .ccl:focus-visible { outline: 2px solid var(--calm-accent, var(--accent, #f59e0b)); outline-offset: 2px; }

  .ccl__head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 14px;
    flex-wrap: wrap;
    margin-bottom: 14px;
  }
  .ccl__titlewrap { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .ccl__titlerow { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .ccl__title {
    margin: 0;
    font-family: var(--font-h, var(--ff-system, sans-serif));
    font-size: 18px;
    letter-spacing: 0.04em;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    font-weight: 650;
  }
  .ccl__beta {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 10px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--badge-obs-fg, #475569);
    background: var(--badge-obs-bg, #f1f5f9);
    border: 1px solid var(--badge-obs-border, #cbd5e1);
    border-radius: 3px;
    padding: 2px 8px;
    white-space: nowrap;
  }
  .ccl__sub {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 11px;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    letter-spacing: 0.02em;
    margin: 0;
  }
  .ccl__sub .ccl__scope { color: var(--calm-ink, var(--text, #b8b098)); }
  .ccl__close {
    appearance: none;
    background: transparent;
    border: 1px solid var(--calm-hairline, var(--border, #192030));
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    border-radius: 4px;
    font-size: 11px;
    padding: 4px 10px;
    cursor: pointer;
    font-family: var(--ff-mono, ui-monospace, monospace);
    letter-spacing: 0.04em;
    white-space: nowrap;
  }
  .ccl__close:focus-visible { outline: 2px solid var(--calm-accent, var(--accent, #f59e0b)); outline-offset: 2px; }

  .ccl__off {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 12px;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    font-style: italic;
    padding: 14px 0;
  }

  /* ---- headline stat block -------------------------------------------------- */
  .ccl__stats {
    display: flex;
    align-items: baseline;
    gap: 22px;
    flex-wrap: wrap;
    font-family: var(--ff-mono, ui-monospace, monospace);
    margin-bottom: 14px;
  }
  .stat { display: flex; flex-direction: column; gap: 2px; }
  .stat__v {
    font-size: 22px;
    font-weight: 700;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    font-variant-numeric: tabular-nums;
    line-height: 1;
  }
  .stat__k {
    font-size: 9px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .stat__v.worst { color: var(--badge-ar-fg, #d97706); }

  .samplechip {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 9px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--badge-ar-fg, #d97706);
    border: 1px solid var(--badge-ar-border, #d97706);
    background: rgba(217, 119, 6, 0.1);
    border-radius: 3px;
    padding: 2px 7px;
    align-self: center;
  }

  /* ---- chart field (left) + decile rail (right) ---------------------------- */
  .ccl__split {
    display: grid;
    grid-template-columns: minmax(280px, 320px) 1fr;
    gap: 22px;
    align-items: start;
  }
  @media (max-width: 720px) {
    .ccl__split { grid-template-columns: 1fr; }
  }

  .field { position: relative; width: 100%; max-width: 320px; }
  .field__svgwrap { position: relative; padding: 6px 6px 26px 34px; }
  .field svg { display: block; width: 100%; height: auto; }
  .axis-x, .axis-y {
    position: absolute;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 9px;
    letter-spacing: 0.04em;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    text-transform: uppercase;
  }
  .axis-x { bottom: 4px; left: 34px; right: 6px; text-align: center; }
  .axis-y {
    left: -2px; top: 6px; bottom: 26px;
    writing-mode: vertical-rl;
    transform: rotate(180deg);
    display: flex; align-items: center; justify-content: center;
  }

  /* SVG element styling in CSS so it re-themes (SVG attrs would freeze color). */
  .diag {
    stroke: var(--calm-hairline, var(--border, #192030));
    stroke-width: 1; stroke-dasharray: 4 3; fill: none;
  }
  .diag-label {
    fill: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 7px; letter-spacing: 0.04em;
  }
  .gridline { stroke: var(--calm-hairline, var(--border, #192030)); stroke-width: 0.5; opacity: 0.5; }
  .tick-text {
    fill: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 6.5px;
  }
  .curve {
    fill: none;
    stroke: var(--calm-accent, var(--accent, #f59e0b));
    stroke-width: 1.5; stroke-linejoin: round;
  }
  .dropline { stroke-width: 1; stroke-dasharray: 1.5 1.5; opacity: 0.75; }

  .node { cursor: pointer; stroke-width: 1.25; }
  .node--under { fill: var(--calm-surface-raised, var(--bg-card, #0c1118)) !important; }
  .node--lowsample {
    fill: var(--calm-surface-alt, var(--bg-row-alt, #0b1018)) !important;
    stroke: var(--calm-ink-chrome, var(--text-ui, #8a8068)) !important;
    stroke-dasharray: 2 1.5;
  }
  .node-ring {
    fill: none;
    stroke: var(--calm-accent, var(--accent, #f59e0b));
    stroke-width: 1.5; opacity: 0;
  }
  .node-ring.is-active { opacity: 1; }

  .band-LOW { fill: var(--c-block, #ef4444); stroke: var(--c-block, #ef4444); }
  .band-WATCH { fill: var(--c-intervene, #f97316); stroke: var(--c-intervene, #f97316); }
  .band-OK { fill: var(--c-suggest, #84cc16); stroke: var(--c-suggest, #84cc16); }
  .band-HIGH { fill: var(--c-allow, #22c55e); stroke: var(--c-allow, #22c55e); }
  .drop-LOW { stroke: var(--c-block, #ef4444); }
  .drop-WATCH { stroke: var(--c-intervene, #f97316); }
  .drop-OK { stroke: var(--c-suggest, #84cc16); }
  .drop-HIGH { stroke: var(--c-allow, #22c55e); }

  /* ---- the decile RAIL ------------------------------------------------------ */
  .rail {
    border: 1px solid var(--calm-hairline, var(--border, #192030));
    border-radius: 6px;
    overflow: hidden;
    background: var(--calm-surface-row, var(--bg-row, #0e141e));
  }
  .rail__cap {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 10px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    padding: 8px 12px;
    border-bottom: 1px solid var(--calm-hairline, var(--border, #192030));
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
    display: flex; justify-content: space-between; gap: 10px;
  }
  .rrow {
    display: grid;
    grid-template-columns: 78px 1fr auto;
    gap: 10px;
    align-items: center;
    width: 100%;
    text-align: left;
    border: 0;
    border-top: 1px solid var(--calm-hairline, var(--border, #192030));
    border-left: 3px solid transparent;
    background: transparent;
    color: inherit;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 12px;
    padding: 9px 12px;
    cursor: pointer;
  }
  .rrow:first-child { border-top: 0; }
  .rrow:hover { background: var(--calm-surface-hover, var(--bg-row-hover, #131c2a)); }
  .rrow:focus-visible {
    outline: 2px solid var(--calm-accent, var(--accent, #f59e0b));
    outline-offset: -2px;
  }
  .rrow.is-active {
    background: var(--calm-surface-hover, var(--bg-row-hover, #131c2a));
    border-left-color: var(--calm-accent, var(--accent, #f59e0b));
  }
  .rrow[data-band="LOW"] { border-left-color: var(--c-block, #ef4444); }
  .rrow[data-band="WATCH"] { border-left-color: var(--c-intervene, #f97316); }
  .rrow[data-band="OK"] { border-left-color: var(--c-suggest, #84cc16); }
  .rrow[data-band="HIGH"] { border-left-color: var(--c-allow, #22c55e); }
  .rrow.is-active[data-band] { border-left-color: var(--calm-accent, var(--accent, #f59e0b)); }

  .rrow__decile {
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    font-variant-numeric: tabular-nums;
    font-weight: 600;
    letter-spacing: 0.02em;
  }
  .rrow__nums { color: var(--calm-ink-quiet, var(--text-dim, #948870)); font-variant-numeric: tabular-nums; }
  .rrow__nums b { color: var(--calm-ink, var(--text, #b8b098)); font-weight: 600; }

  .sign {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 10px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    border: 1px solid var(--calm-hairline, var(--border, #192030));
    border-radius: 3px;
    padding: 2px 7px;
    white-space: nowrap;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
  }
  .sign__glyph { width: 9px; height: 9px; flex: 0 0 auto; display: inline-block; }
  .sign__glyph[data-shape="over"] { background: currentColor; }
  .sign__glyph[data-shape="under"] { background: transparent; border: 1.5px solid currentColor; }
  .sign__glyph[data-shape="cal"] { background: currentColor; border-radius: 50%; width: 8px; height: 8px; }
  .sign__glyph[data-shape="low"] { background: transparent; border: 1.5px dashed currentColor; }
  .sign[data-sign="OVER"] { color: var(--c-allow, #22c55e); border-color: var(--c-allow, #22c55e); }
  .sign[data-sign="UNDER"] { color: var(--c-intervene, #f97316); border-color: var(--c-intervene, #f97316); }
  .sign[data-sign="CALIBRATED"] { color: var(--calm-ink, var(--text, #b8b098)); border-color: var(--calm-hairline, var(--border, #192030)); }
  .sign[data-sign="LOWSAMPLE"] { color: var(--calm-ink-chrome, var(--text-ui, #8a8068)); border-color: var(--calm-ink-chrome, var(--text-ui, #8a8068)); }
  .sign__gap { color: inherit; }

  /* ---- the calm inline tray ------------------------------------------------- */
  .tray {
    margin-top: 14px;
    border: 1px solid var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25)));
    border-radius: 6px;
    background: var(--calm-surface-row, var(--bg-row, #0e141e));
    overflow: hidden;
  }
  .tray__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 9px 13px;
    border-bottom: 1px solid var(--calm-hairline, var(--border, #192030));
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
  }
  .tray__title { font-family: var(--ff-mono, ui-monospace, monospace); font-size: 12px; color: var(--calm-ink-loud, var(--text-bright, #e8e0cc)); }
  .tray__close {
    appearance: none;
    background: transparent;
    border: 1px solid var(--calm-hairline, var(--border, #192030));
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    border-radius: 4px;
    font-size: 11px;
    padding: 3px 9px;
    cursor: pointer;
    font-family: var(--ff-mono, ui-monospace, monospace);
    letter-spacing: 0.04em;
  }
  .tray__close:focus-visible { outline: 2px solid var(--calm-accent, var(--accent, #f59e0b)); outline-offset: 2px; }
  .tray__body {
    padding: 12px 13px;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 12px 22px;
    font-family: var(--ff-mono, ui-monospace, monospace);
  }
  .tfact { display: flex; flex-direction: column; gap: 3px; }
  .tfact__k { font-size: 9px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--calm-ink-chrome, var(--text-ui, #8a8068)); }
  .tfact__v { font-size: 13px; color: var(--calm-ink-loud, var(--text-bright, #e8e0cc)); font-variant-numeric: tabular-nums; }
  .tray__words {
    grid-column: 1 / -1;
    font-size: 12px;
    color: var(--calm-ink, var(--text, #b8b098));
    line-height: 1.6;
    border-top: 1px solid var(--calm-hairline, var(--border, #192030));
    padding-top: 10px;
    margin: 0;
  }
  .tray__words b { color: var(--calm-ink-loud, var(--text-bright, #e8e0cc)); }

  /* ---- OPT-IN advisory transform control ------------------------------------ */
  .optin {
    margin-top: 22px;
    border: 1px solid var(--calm-hairline, var(--border, #192030));
    border-radius: 6px;
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
    padding: 10px 14px;
  }
  .optin__row {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    justify-content: space-between;
    flex-wrap: wrap;
  }
  .optin__copy { min-width: 0; max-width: 560px; }
  .optin__title {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 12px;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    letter-spacing: 0.02em;
    margin: 0 0 4px;
  }
  .optin__desc {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 11px;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    line-height: 1.6;
    margin: 0;
  }
  .optin__desc b { color: var(--calm-ink, var(--text, #b8b098)); }
  .optin__control { display: flex; align-items: center; gap: 9px; }
  .optin__state {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .optin__state[data-on="true"] { color: var(--calm-accent, var(--accent, #f59e0b)); }
  .optin__state[data-on="false"] { color: var(--calm-ink-chrome, var(--text-ui, #8a8068)); }
  .optin__scope {
    margin-top: 10px;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 10px;
    letter-spacing: 0.03em;
    color: var(--badge-ar-fg, #d97706);
    border-top: 1px dashed var(--calm-hairline, var(--border, #192030));
    padding-top: 8px;
  }

  /* the opt-in switch (advisory-only). Default OFF; M17 focus ring. */
  .switch {
    position: relative;
    width: 42px;
    height: 22px;
    border-radius: 12px;
    border: 1px solid var(--calm-hairline, var(--border, #192030));
    background: var(--calm-surface-row, var(--bg-row, #0e141e));
    cursor: pointer;
    padding: 0;
    flex: 0 0 auto;
    transition: background 0.15s ease, border-color 0.15s ease;
  }
  .switch[aria-checked="true"] {
    background: var(--calm-accent-wash, var(--accent-dim, rgba(245, 158, 11, 0.09)));
    border-color: var(--accent, #f59e0b);
  }
  .switch::after {
    content: "";
    position: absolute;
    top: 2px; left: 2px;
    width: 16px; height: 16px;
    border-radius: 50%;
    background: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    transition: transform 0.15s ease, background 0.15s ease;
  }
  .switch[aria-checked="true"]::after {
    transform: translateX(20px);
    background: var(--accent, #f59e0b);
  }
  .switch:focus-visible { outline: 2px solid var(--calm-accent, var(--accent, #f59e0b)); outline-offset: 2px; }

  /* ---- legend --------------------------------------------------------------- */
  .ccl__foot {
    margin-top: 22px;
    display: flex; gap: 22px; flex-wrap: wrap; align-items: center;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 11px;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .legend { display: inline-flex; align-items: center; gap: 14px; flex-wrap: wrap; }
  .lk { display: inline-flex; align-items: center; gap: 7px; }
  .lk__shape { width: 10px; height: 10px; flex: 0 0 auto; display: inline-block; }
  .lk__shape[data-shape="over"] { background: var(--c-allow, #22c55e); }
  .lk__shape[data-shape="under"] { background: transparent; border: 1.5px solid var(--c-intervene, #f97316); }
  .lk__shape[data-shape="cal"] { background: var(--calm-ink, var(--text, #b8b098)); border-radius: 50%; width: 9px; height: 9px; }
  .lk__shape[data-shape="low"] { background: transparent; border: 1.5px dashed var(--calm-ink-chrome, var(--text-ui, #8a8068)); }

  /* M17 reduced-motion: kill the switch transition when the user prefers it. */
  @media (prefers-reduced-motion: reduce) {
    .switch, .switch::after { transition: none; }
  }
  :global(html[data-motion="reduce"]) .switch,
  :global(html[data-motion="reduce"]) .switch::after { transition: none; }
</style>
