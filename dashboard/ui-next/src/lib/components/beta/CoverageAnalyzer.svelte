<!--
  CoverageAnalyzer.svelte -- BETA feature "coverage-analyzer" (#10).

  WHAT IT IS
    A read-only DRAWER that compares the soak CASSETTE band distribution against
    the LIVE non-SM session band distribution (and an optional uploaded fixture)
    so the operator can see where soak coverage has drifted from production. The
    four bands are governance routing layers: ALLOW (layer 0), L2/L3 (layer 2),
    L4 (layer 4), LEARN (layer 0, learn-dialogue). When the cassette under- or
    over-represents a band past +/-10%, the drawer surfaces a paired WATCH/DRIFT
    warning so a green soak is not silently trusted.

  BETA GATE (load-bearing)
    The ENTIRE component is wrapped in {#if $betaFlags['coverage-analyzer']}. When
    the flag is OFF it renders NOTHING and registers NO fetch / poller / SSE /
    timer -- zero runtime cost. The flag defaults OFF (lib/beta/registry.js); the
    operator flips it in Settings > BETA features. There is no SSE here at all:
    coverage is read once per drawer-open via a single post-hoc GET (M18). It is
    a DRAWER, never a fourth frame, and NEVER auto-foregrounds (ADR-18 MUST).

  DATA
    Reads GET /api/coverage/bands?window=&fixture_id=. The server aggregates
    decisions by layer, polarity-filtered (project_slug NOT IN {streamManager}
    AND session_id != self) for the live + fixture columns. When the endpoint is
    absent or returns an empty/zero set (fresh DB, no decisions), the drawer
    falls back to realistic mock data (CoverageAnalyzer.data.js) so it is always
    inspectable; the mock state is labelled in the meta line.

  ADR-18 MUST floor honoured here:
    - M2: never auto-foregrounds; the chip + drawer are operator-invoked only.
    - M4 (paired label+color): every severity renders its LITERAL text
      (OK / WATCH / DRIFT) beside any color; color is never the sole signal.
    - M16 (domain-agnostic): no monitored-project vocabulary; band identity is
      a governance-layer taxonomy, project identity is rendered from server data.
    - M17 (a11y): chip is a real <button> with aria-haspopup; the drawer is
      role=dialog aria-modal with a labelled heading, Escape-to-close, focus
      moved in on open + restored on close, and a focus trap. Each band is a
      keyboard-operable <button> that expands counts + remediation. Reduced
      motion honoured via the data-motion attribute.
    - M18: pure post-hoc GET; never on the verdict hot path.

  ASCII-only (cp1252-safe): dash rendered as "--". No smart quotes / em-dash.
-->
<script>
  import { tick } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { getCoverageBands } from '../../api.js';
  import {
    THRESHOLD,
    mockCassette,
    mockLive,
    mockFixture,
    normalizeSet,
    buildDrift,
    worstDrift,
    sevLabel,
    signedPct,
    remediationFor,
  } from './CoverageAnalyzer.data.js';

  const FLAG_KEY = 'coverage-analyzer';
  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // ---- drawer open/close + focus contract (mirrors SettingsDrawer) ----------
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
  /** @type {ReturnType<typeof normalizeSet>} */
  let cassette = null;
  /** @type {ReturnType<typeof normalizeSet>} */
  let live = null;
  /** @type {ReturnType<typeof normalizeSet>} */
  let fixture = null;

  /** 'live' | 'fixture' -- which column the cassette is compared against. */
  let compareMode = 'live';
  /** the currently expanded band key (accordion), or null. */
  let openBand = null;

  /** A set is "empty" if the server gave us no rows at all (fresh DB). */
  function isEmptySet(set) {
    return !set || !Array.isArray(set.bands) || (Number(set.total) || 0) === 0;
  }

  /**
   * Load coverage once (called on drawer-open only -- no poller). Best-effort:
   * any failure or empty result degrades to the realistic mock fallbacks so the
   * drawer is always inspectable. Never throws to the render path.
   */
  async function load() {
    loading = true;
    let payload = null;
    try {
      payload = await getCoverageBands({ window: 1000 });
    } catch {
      payload = null;
    }
    const c = normalizeSet(payload && payload.cassette, 'cassette');
    const l = normalizeSet(payload && payload.live, 'live');
    const f = normalizeSet(payload && payload.fixture, 'fixture');

    if (isEmptySet(c) || isEmptySet(l)) {
      // No usable live/cassette data -- fall back to mock so the feature is
      // testable and the operator sees the shape it will take once data lands.
      cassette = mockCassette();
      live = mockLive();
      fixture = mockFixture();
      usedMockData = true;
    } else {
      cassette = c;
      live = l;
      fixture = !isEmptySet(f) ? f : mockFixture();
      usedMockData = false;
    }
    loading = false;
  }

  // ---- derived view ---------------------------------------------------------
  $: reference = compareMode === 'fixture' ? fixture : live;
  $: refLabel =
    compareMode === 'fixture'
      ? `fixture ${(fixture && fixture.fixture_id) || ''}`.trim()
      : 'live';
  $: drift = cassette && reference ? buildDrift(cassette, reference) : [];
  $: worst = worstDrift(drift);
  $: verdictSev = worst ? worst.severity : 'notice';
  $: flagged = drift.filter((r) => r.severity !== 'notice');
  $: excludedSelf =
    reference && Number.isFinite(Number(reference.excluded_self_rows))
      ? Number(reference.excluded_self_rows)
      : 0;
  $: metaLine = (() => {
    if (!cassette || !reference) return '';
    if (compareMode === 'fixture') {
      return `cassette ${cassette.total} -- fixture ${reference.total} (${
        (fixture && fixture.fixture_id) || 'fixture'
      })`;
    }
    const win = Number(live && live.window) || 1000;
    return `cassette ${cassette.total} -- live ${reference.total} (window ${win})`;
  })();
  $: verdictText = (() => {
    if (!worst) return '';
    if (verdictSev === 'notice') {
      return `Coverage aligned -- all bands within +/-${THRESHOLD}% of ${refLabel}. Soak green is trustworthy.`;
    }
    const path = worst.key === 'l2_l3' ? 'escalation path' : `${worst.label} path`;
    return `${worst.label} drift ${signedPct(worst.delta_pct)} over the ${THRESHOLD}% threshold -- Tier-1 replay may under-test the ${path}.`;
  })();

  // ---- chart scaling (repaint-only widths; the bar length is decorative, the
  // percentage TEXT is the real signal -- never color/length alone) -----------
  $: maxPct = drift.reduce((m, r) => Math.max(m, r.cassettePct, r.refPct), 0);
  $: scale = maxPct > 0 ? 96 / maxPct : 0;
  function barWidth(pct) {
    return `${Math.max(2, (Number(pct) || 0) * scale)}%`;
  }

  // ---- interactions ---------------------------------------------------------
  function toggleBand(key) {
    openBand = openBand === key ? null : key;
  }
  function setMode(m) {
    compareMode = m;
    openBand = null;
  }

  async function openDrawer() {
    if (!enabled) return;
    prevFocus = typeof document !== 'undefined' ? document.activeElement : null;
    open = true;
    if (cassette === null) load();
    await tick();
    panelEl?.focus();
  }
  function closeDrawer() {
    open = false;
    const target = prevFocus && /** @type {any} */ (prevFocus).focus ? prevFocus : chipEl;
    /** @type {HTMLElement|null} */ (target)?.focus?.();
    prevFocus = null;
  }

  function onKeydown(e) {
    if (!open) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      closeDrawer();
      return;
    }
    if (e.key === 'Tab' && panelEl) {
      const f = Array.from(
        panelEl.querySelectorAll(
          'button:not([disabled]), [href], input:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((n) => /** @type {HTMLElement} */ (n).offsetParent !== null);
      if (!f.length) return;
      const first = /** @type {HTMLElement} */ (f[0]);
      const last = /** @type {HTMLElement} */ (f[f.length - 1]);
      const active = document.activeElement;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  // When the flag flips OFF while the drawer is open, close it so nothing
  // lingers (defense-in-depth -- the {#if} below already unmounts everything).
  $: if (!enabled && open) open = false;
</script>

<svelte:window on:keydown={onKeydown} />

{#if enabled}
  <!-- HEADER CHIP: the only resting affordance. A real button; opens the
       drawer. Present only while the flag is ON (the {#if enabled} guard). -->
  <button
    bind:this={chipEl}
    class="ca-chip"
    type="button"
    aria-haspopup="dialog"
    aria-expanded={open}
    aria-controls="ca-panel"
    on:click={openDrawer}
  >
    <span class="ca-chip__dot" aria-hidden="true"></span>
    Coverage
    <span class="ca-chip__beta">BETA</span>
  </button>

  {#if open}
    <!-- SCRIM: click-out closes. Not a focus target. -->
    <div class="ca-scrim" on:click={closeDrawer} aria-hidden="true"></div>

    <!-- DRAWER: role=dialog aria-modal; labelled heading; Escape + focus trap. -->
    <div
      id="ca-panel"
      class="ca-panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="ca-title"
      tabindex="-1"
      bind:this={panelEl}
    >
      <header class="ca-head">
        <div class="ca-head__grow">
          <h2 id="ca-title" class="ca-title">Coverage Analyzer</h2>
          <p class="ca-sub">cassette-vs-live band distribution &middot; drift inspection</p>
        </div>
        <button
          class="ca-close"
          type="button"
          aria-label="Close coverage analyzer"
          on:click={closeDrawer}
        >
          <span aria-hidden="true">x</span>
        </button>
      </header>

      <div class="ca-body">
        <!-- BETA strip -->
        <div class="ca-betastrip">
          <span class="ca-pill">BETA</span>
          <span class="ca-pill__note">
            default OFF -- toggled in Settings &gt; BETA features. Reads are
            post-hoc GET on open; no poller, no SSE.
          </span>
        </div>

        {#if loading && cassette === null}
          <p class="ca-loading">Loading coverage...</p>
        {:else if cassette && reference}
          <!-- data-source line: ALWAYS a literal text label (mock vs live) -->
          <p class="ca-source" data-mock={usedMockData}>
            {usedMockData
              ? 'SAMPLE DATA -- no live decisions in gov.db yet; showing a representative shape.'
              : 'LIVE -- aggregated from gov.db decisions (polarity-filtered).'}
          </p>

          <!-- TOP VERDICT (paired label+color; color is never the sole signal) -->
          <div class="ca-verdict" data-sev={verdictSev}>
            <span class="ca-verdict__dot" aria-hidden="true"></span>
            <span class="ca-verdict__label">{sevLabel(verdictSev)}</span>
            <span class="ca-verdict__text">{verdictText}</span>
          </div>

          <!-- COMPARISON CHART -->
          <div class="ca-section-h">
            <h3>Band distribution</h3>
            <span class="ca-meta tabular">{metaLine}</span>
          </div>
          <div class="ca-legend" aria-hidden="true">
            <span class="ca-legend__item">
              <span class="ca-legend__swatch live"></span>{compareMode === 'fixture'
                ? 'fixture'
                : 'live'} -- ground truth
            </span>
            <span class="ca-legend__item">
              <span class="ca-legend__swatch cassette"></span>cassette -- under judgment
            </span>
          </div>

          <div
            class="ca-chart"
            role="group"
            aria-label="Cassette versus {compareMode === 'fixture'
              ? 'fixture'
              : 'live'} band distribution, four bands"
          >
            {#each drift as r (r.key)}
              <button
                class="ca-band"
                class:is-open={openBand === r.key}
                type="button"
                aria-expanded={openBand === r.key}
                aria-label={`${r.label} band. cassette ${r.cassettePct} percent, ${refLabel} ${r.refPct} percent, delta ${signedPct(
                  r.delta_pct,
                )}, ${sevLabel(r.severity)}. Activate to expand counts and remediation.`}
                on:click={() => toggleBand(r.key)}
              >
                <div class="ca-band__head">
                  <span class="ca-band__name">{r.label}</span>
                  <span class="ca-band__sev" data-sev={r.severity}>
                    <span class="ca-sevdot" aria-hidden="true"></span>{sevLabel(r.severity)}
                  </span>
                  <span class="ca-band__delta" data-sev={r.severity}>{signedPct(r.delta_pct)}</span>
                </div>

                <div class="ca-barwrap">
                  <div class="ca-barline">
                    <span class="ca-barline__tag">cassette</span>
                    <span class="ca-bar">
                      <span class="ca-bar__fill cassette" style="width:{barWidth(r.cassettePct)}"></span>
                    </span>
                    <span class="ca-barline__pct tabular">{r.cassettePct.toFixed(1)}%</span>
                  </div>
                  <div class="ca-barline">
                    <span class="ca-barline__tag">{compareMode === 'fixture' ? 'fixture' : 'live'}</span>
                    <span class="ca-bar">
                      <span class="ca-bar__fill live" style="width:{barWidth(r.refPct)}"></span>
                    </span>
                    <span class="ca-barline__pct tabular">{r.refPct.toFixed(1)}%</span>
                  </div>
                </div>

                {#if openBand === r.key}
                  <dl class="ca-detail">
                    <dt>cassette count</dt>
                    <dd class="tabular">{r.cassetteCount} / {cassette.total} ({r.cassettePct}%)</dd>
                    <dt>{refLabel} count</dt>
                    <dd class="tabular">{r.refCount} / {reference.total} ({r.refPct}%)</dd>
                    <dt>layer bin</dt>
                    <dd class="tabular">layer {r.layer}</dd>
                    <dt>signed drift</dt>
                    <dd class="tabular">{signedPct(r.delta_pct)} ({sevLabel(r.severity)})</dd>
                    <p class="ca-remediation" class:is-notice={r.severity === 'notice'}>
                      {remediationFor(r, refLabel)}
                    </p>
                  </dl>
                {/if}
              </button>
            {/each}
          </div>

          <!-- CONTROLS: compare live window vs an uploaded fixture -->
          <div class="ca-controls">
            <button
              class="ca-btn"
              class:is-active={compareMode === 'live'}
              type="button"
              aria-pressed={compareMode === 'live'}
              on:click={() => setMode('live')}
            >
              Live window
            </button>
            <button
              class="ca-btn"
              class:is-active={compareMode === 'fixture'}
              type="button"
              aria-pressed={compareMode === 'fixture'}
              on:click={() => setMode('fixture')}
            >
              Compare fixture
            </button>
            <span class="ca-controls__note">
              {excludedSelf} SM-self row{excludedSelf === 1 ? '' : 's'} excluded (polarity filter)
            </span>
          </div>

          <!-- WARNINGS: one strip per band over threshold (paired label+color) -->
          <div class="ca-section-h ca-section-h--warns">
            <h3>Drift warnings</h3>
            <span class="ca-meta">threshold +/-{THRESHOLD}%</span>
          </div>
          <div class="ca-warns" role="status" aria-live="polite">
            {#if flagged.length === 0}
              <div class="ca-warn" data-sev="ok">
                <span class="ca-warn__badge ok">
                  <span class="ca-sevdot" aria-hidden="true"></span>OK
                </span>
                <span class="ca-warn__text">
                  No band drifts past the +/-{THRESHOLD}% threshold. Cassette is
                  representative of {refLabel}.
                </span>
              </div>
            {:else}
              {#each flagged as r (r.key)}
                <div class="ca-warn" data-sev={r.severity}>
                  <span class="ca-warn__badge">
                    <span class="ca-sevdot" aria-hidden="true"></span>{sevLabel(r.severity)}
                    {signedPct(r.delta_pct)}
                  </span>
                  <span class="ca-warn__text">
                    <strong>{r.label}</strong> -- {remediationFor(r, refLabel)}
                  </span>
                </div>
              {/each}
            {/if}
          </div>
        {:else}
          <p class="ca-loading">No coverage data available.</p>
        {/if}
      </div>

      <footer class="ca-foot">
        <span class="ca-pill ca-pill--sm">BETA</span>
        <span>
          Read-only. Default OFF, toggled in Settings &gt; BETA features. Never
          auto-foregrounds; never a fourth frame.
        </span>
      </footer>
    </div>
  {/if}
{/if}

<style>
  /* ---- header chip --------------------------------------------------------- */
  .ca-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    font: inherit;
    font-size: 0.72rem;
    letter-spacing: 0.03em;
    padding: 0.3rem 0.65rem;
    background: var(--calm-accent-wash, var(--accent-dim));
    color: var(--calm-ink-loud, var(--text-bright));
    border: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi));
    border-radius: 999px;
    cursor: pointer;
  }
  .ca-chip:hover {
    border-color: var(--calm-accent, var(--accent));
  }
  .ca-chip__dot {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 50%;
    background: var(--calm-accent, var(--accent));
    flex: 0 0 auto;
  }
  .ca-chip__beta {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.56rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: #92400e;
    background: var(--badge-ar-bg);
    border: 1px solid var(--badge-ar-border);
    border-radius: 4px;
    padding: 0 0.3rem;
  }

  /* ---- scrim + drawer ------------------------------------------------------ */
  .ca-scrim {
    position: fixed;
    inset: 0;
    z-index: 80;
    background: rgba(8, 10, 12, 0.55);
    backdrop-filter: blur(1px);
  }
  .ca-panel {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    z-index: 81;
    width: min(560px, 96vw);
    display: flex;
    flex-direction: column;
    background: var(--calm-surface-raised, var(--bg-card));
    border-left: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi));
    box-shadow: -18px 0 48px -24px rgba(0, 0, 0, 0.7);
    color: var(--calm-ink, var(--text));
    font-family: var(--ff-system);
    overflow: hidden;
  }

  .ca-head {
    flex: 0 0 auto;
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    padding: 1rem 1.15rem 0.85rem;
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
  }
  .ca-head__grow {
    flex: 1 1 auto;
    min-width: 0;
  }
  .ca-title {
    margin: 0;
    font-size: 1.02rem;
    letter-spacing: 0.01em;
    color: var(--calm-ink-loud, var(--text-bright));
    font-weight: 700;
    line-height: 1.25;
  }
  .ca-sub {
    margin: 0.2rem 0 0;
    font-size: 0.76rem;
    color: var(--calm-ink-quiet, var(--text-dim));
    font-family: var(--font-d, var(--ff-mono));
  }
  .ca-close {
    flex: 0 0 auto;
    font: inherit;
    line-height: 1;
    font-size: 1rem;
    background: transparent;
    color: var(--calm-ink-quiet, var(--text-dim));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: 8px;
    width: 2rem;
    height: 2rem;
    cursor: pointer;
  }
  .ca-close:hover {
    color: var(--calm-ink-loud, var(--text-bright));
  }

  .ca-body {
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
    padding: 1rem 1.15rem 1.4rem;
    overscroll-behavior: contain;
  }

  .ca-betastrip {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    flex-wrap: wrap;
    padding: 0.55rem 0.7rem;
    margin-bottom: 1rem;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: 8px;
    background: var(--bg-row-alt);
  }
  .ca-pill {
    display: inline-flex;
    align-items: center;
    font-size: 0.66rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    font-weight: 700;
    padding: 0.22rem 0.55rem;
    border-radius: 6px;
    color: var(--badge-ar-fg);
    background: var(--badge-ar-bg);
    border: 2px solid var(--badge-ar-border);
  }
  .ca-pill--sm {
    font-size: 0.6rem;
    padding: 0.16rem 0.45rem;
    border-width: 1px;
  }
  .ca-pill__note {
    flex: 1 1 auto;
    font-size: 0.72rem;
    color: var(--calm-ink-quiet, var(--text-dim));
  }

  .ca-loading {
    padding: 1.2rem 0.4rem;
    text-align: center;
    color: var(--calm-ink-quiet, var(--text-dim));
    font-size: 0.82rem;
    font-style: italic;
  }

  .ca-source {
    margin: 0 0 0.85rem;
    font-size: 0.7rem;
    font-family: var(--font-d, var(--ff-mono));
    letter-spacing: 0.02em;
    color: var(--calm-ink-quiet, var(--text-dim));
  }
  .ca-source[data-mock='true'] {
    color: var(--sm-warn-fg, var(--badge-warn-fg));
  }

  /* ---- top verdict (paired label+color) ------------------------------------ */
  .ca-verdict {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    flex-wrap: wrap;
    padding: 0.6rem 0.75rem;
    margin-bottom: 0.95rem;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: 8px;
    background: var(--bg-card);
  }
  .ca-verdict__dot {
    width: 0.6rem;
    height: 0.6rem;
    border-radius: 50%;
    flex: 0 0 auto;
    background: var(--calm-ink-quiet, var(--text-dim));
  }
  .ca-verdict__label {
    font-family: var(--font-d, var(--ff-mono));
    font-weight: 700;
    font-size: 0.72rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--calm-ink-quiet, var(--text-dim));
  }
  .ca-verdict__text {
    font-size: 0.83rem;
    color: var(--calm-ink, var(--text));
    flex: 1 1 12rem;
  }
  .ca-verdict[data-sev='warn'] {
    border-color: var(--sm-warn-fg, var(--badge-warn-fg));
  }
  .ca-verdict[data-sev='warn'] .ca-verdict__dot,
  .ca-verdict[data-sev='warn'] .ca-verdict__label {
    background: var(--sm-warn-fg, var(--badge-warn-fg));
  }
  .ca-verdict[data-sev='warn'] .ca-verdict__label {
    background: transparent;
    color: var(--sm-warn-fg, var(--badge-warn-fg));
  }
  .ca-verdict[data-sev='alert'] {
    border-color: var(--badge-blocked-border);
  }
  .ca-verdict[data-sev='alert'] .ca-verdict__dot {
    background: var(--badge-blocked-fg);
  }
  .ca-verdict[data-sev='alert'] .ca-verdict__label {
    color: var(--badge-blocked-fg);
  }

  /* ---- section heads + legend ---------------------------------------------- */
  .ca-section-h {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.6rem;
    margin: 0.3rem 0 0.55rem;
  }
  .ca-section-h--warns {
    margin-top: 1.25rem;
  }
  .ca-section-h h3 {
    margin: 0;
    font-size: 0.7rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui));
    font-weight: 700;
  }
  .ca-meta {
    font-size: 0.7rem;
    color: var(--calm-ink-quiet, var(--text-dim));
  }
  .tabular {
    font-variant-numeric: tabular-nums;
    font-family: var(--font-d, var(--ff-mono));
  }

  .ca-legend {
    display: flex;
    gap: 0.9rem;
    font-size: 0.68rem;
    color: var(--calm-ink-quiet, var(--text-dim));
    margin-bottom: 0.7rem;
  }
  .ca-legend__item {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
  }
  .ca-legend__swatch {
    width: 1.3rem;
    height: 0.55rem;
    border-radius: 2px;
    flex: 0 0 auto;
  }
  .ca-legend__swatch.live {
    background: var(--calm-accent, var(--accent));
  }
  .ca-legend__swatch.cassette {
    background: transparent;
    border: 1px solid var(--calm-accent, var(--accent));
  }

  /* ---- chart: one expandable band button per row --------------------------- */
  .ca-chart {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }
  .ca-band {
    width: 100%;
    text-align: left;
    font: inherit;
    background: transparent;
    border: var(--hairline, 1px) solid transparent;
    border-radius: 8px;
    padding: 0.5rem 0.55rem;
    cursor: pointer;
    display: block;
    color: inherit;
  }
  .ca-band:hover {
    background: var(--bg-row-hover);
  }
  .ca-band.is-open {
    background: var(--bg-row-hover);
    border-color: var(--calm-hairline, var(--border));
  }

  .ca-band__head {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.35rem;
  }
  .ca-band__name {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.74rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    color: var(--calm-ink-loud, var(--text-bright));
    min-width: 4.6em;
  }
  .ca-band__delta {
    margin-left: auto;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.74rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }
  .ca-band__sev {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    padding: 0.08rem 0.4rem;
    border-radius: 5px;
    text-transform: uppercase;
  }
  .ca-sevdot {
    width: 0.4rem;
    height: 0.4rem;
    border-radius: 50%;
    background: currentColor;
    flex: 0 0 auto;
  }
  .ca-band__sev[data-sev='notice'] {
    color: var(--calm-ink-quiet, var(--text-dim));
    background: var(--bg-row-alt);
  }
  .ca-band__sev[data-sev='warn'] {
    color: var(--sm-warn-fg, var(--badge-warn-fg));
    background: rgba(202, 138, 4, 0.1);
  }
  .ca-band__sev[data-sev='alert'] {
    color: var(--badge-blocked-fg);
    background: rgba(220, 38, 38, 0.1);
  }
  .ca-band__delta[data-sev='notice'] {
    color: var(--calm-ink-quiet, var(--text-dim));
  }
  .ca-band__delta[data-sev='warn'] {
    color: var(--sm-warn-fg, var(--badge-warn-fg));
  }
  .ca-band__delta[data-sev='alert'] {
    color: var(--badge-blocked-fg);
  }

  .ca-barwrap {
    display: flex;
    flex-direction: column;
    gap: 0.28rem;
  }
  .ca-barline {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .ca-barline__tag {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.58rem;
    letter-spacing: 0.06em;
    color: var(--calm-ink-quiet, var(--text-dim));
    min-width: 4.3em;
    text-transform: uppercase;
  }
  .ca-bar {
    position: relative;
    flex: 1 1 auto;
    height: 0.85rem;
    background: var(--bg-row);
    border-radius: 3px;
    overflow: hidden;
  }
  .ca-bar__fill {
    position: absolute;
    inset: 0 auto 0 0;
    height: 100%;
    border-radius: 3px;
    transition: width 0.45s ease; /* WIDTH ONLY -- repaint discipline */
  }
  .ca-bar__fill.live {
    background: var(--calm-accent, var(--accent));
    border: 1px solid var(--calm-accent, var(--accent));
  }
  .ca-bar__fill.cassette {
    background: var(--calm-accent-wash, var(--accent-dim));
    border: 1px solid var(--calm-accent, var(--accent));
  }
  .ca-barline__pct {
    font-size: 0.66rem;
    color: var(--calm-ink-quiet, var(--text-dim));
    min-width: 3.3em;
    text-align: right;
  }

  /* ---- band detail (expanded) ---------------------------------------------- */
  .ca-detail {
    margin: 0.55rem 0 0;
    padding-top: 0.55rem;
    border-top: var(--hairline, 1px) dashed var(--calm-hairline, var(--border));
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.4rem 1rem;
    font-size: 0.74rem;
  }
  .ca-detail dt {
    color: var(--calm-ink-quiet, var(--text-dim));
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.66rem;
    letter-spacing: 0.03em;
  }
  .ca-detail dd {
    margin: 0 0 0.35rem;
    color: var(--calm-ink, var(--text));
    font-variant-numeric: tabular-nums;
  }
  .ca-remediation {
    grid-column: 1 / -1;
    margin: 0.25rem 0 0;
    padding: 0.45rem 0.55rem;
    background: var(--bg-row-alt);
    border-radius: 6px;
    color: var(--calm-ink-quiet, var(--text-dim));
    font-size: 0.72rem;
    border-left: 2px solid var(--sm-warn-fg, var(--badge-warn-fg));
  }
  .ca-remediation.is-notice {
    border-left-color: var(--calm-hairline, var(--border));
  }

  /* ---- controls ------------------------------------------------------------ */
  .ca-controls {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    flex-wrap: wrap;
    margin-top: 1.1rem;
  }
  .ca-btn {
    font: inherit;
    font-size: 0.74rem;
    padding: 0.4rem 0.7rem;
    background: var(--bg-row-alt);
    color: var(--calm-ink-loud, var(--text-bright));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: 7px;
    cursor: pointer;
  }
  .ca-btn:hover {
    border-color: var(--calm-hairline-hi, var(--border-hi));
  }
  .ca-btn.is-active {
    color: var(--calm-accent, var(--accent));
    border-color: var(--calm-hairline-hi, var(--border-hi));
    background: var(--calm-accent-wash, var(--accent-dim));
  }
  .ca-controls__note {
    font-size: 0.7rem;
    color: var(--calm-ink-quiet, var(--text-dim));
    margin-left: auto;
  }

  /* ---- warnings ------------------------------------------------------------ */
  .ca-warns {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .ca-warn {
    display: flex;
    align-items: flex-start;
    gap: 0.55rem;
    padding: 0.55rem 0.65rem;
    border-radius: 8px;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    background: var(--bg-card);
    font-size: 0.78rem;
    line-height: 1.4;
  }
  .ca-warn__badge {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    flex: 0 0 auto;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    padding: 0.16rem 0.45rem;
    border-radius: 5px;
    text-transform: uppercase;
    margin-top: 0.05rem;
  }
  .ca-warn__badge.ok {
    color: var(--calm-ink-quiet, var(--text-dim));
    background: var(--bg-row-alt);
  }
  .ca-warn[data-sev='warn'] {
    border-color: var(--sm-warn-fg, var(--badge-warn-fg));
  }
  .ca-warn[data-sev='warn'] .ca-warn__badge {
    color: var(--sm-warn-fg, var(--badge-warn-fg));
    background: rgba(202, 138, 4, 0.1);
  }
  .ca-warn[data-sev='alert'] {
    border-color: var(--badge-blocked-border);
  }
  .ca-warn[data-sev='alert'] .ca-warn__badge {
    color: var(--badge-blocked-fg);
    background: rgba(220, 38, 38, 0.1);
  }
  .ca-warn__text strong {
    color: var(--calm-ink-loud, var(--text-bright));
    font-weight: 700;
  }

  /* ---- footer -------------------------------------------------------------- */
  .ca-foot {
    flex: 0 0 auto;
    padding: 0.55rem 1.15rem;
    border-top: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.68rem;
    color: var(--calm-ink-quiet, var(--text-dim));
    background: var(--bg-row-alt);
  }

  /* ---- focus ring (M17): the global 2px amber ring on every interactive el -- */
  .ca-chip:focus-visible,
  .ca-close:focus-visible,
  .ca-band:focus-visible,
  .ca-btn:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid)
      var(--focus-ring-color, var(--sm-focus, #d97706));
    outline-offset: 2px;
  }

  /* ---- reduced motion (M17): suppress the bar width transition -------------- */
  :global(html[data-motion='reduce']) .ca-bar__fill {
    transition: none;
  }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .ca-bar__fill {
      transition: none;
    }
  }
</style>
