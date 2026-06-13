<!--
  AmbientSoakTask.svelte -- BETA feature "ambient-soak-task" (#2): a calm AMBIENT
  OK/WARN polarity badge anchored in the AppShell footer's soak corner + a
  read-only history drawer (a cadence strip + a newest-first ledger of recent
  ambient soak runs).

  WHAT IT DOES
    A glance-first, BETA-gated footer CHIP -- the quietest persistent polarity
    instrument -- companioned by a right-side read-only DRAWER (NOT a fourth
    always-on frame; the 3-frame floor is inviolable, ADR-18 M1). A background
    Cron job (operator/main-thread, out-of-process) periodically soaks the
    most-recent NON-SM session and appends a tiny verdict record to the additive
    ambient_runs table. The chip reads the freshest verdict as a paired
    label+color badge (AMBIENT OK / POLARITY CHECK); one click opens the drawer,
    which reads the rolling history into a typographic ledger. WARN never pulses
    and never auto-foregrounds (M2) -- still water.

  CONSTRAINED ADDITIVE: NO message_bus edit, NO new bus envelope, NO ADR-18
  amendment, NO in-process spawn/cron/subprocess. The polarity verdict is a READ
  attribute of each ambient_runs row (the original proposal's
  ambient_soak_coverage_gap envelope is REMOVED -- the soak-panel precedent). Two
  additive read endpoints back this:
    GET /api/ambient/soak-status   -- latest verdict + cadence meta
    GET /api/ambient/soak-history  -- the newest-first ledger rows
  Both polarity-filter SM-self server-side. The Cron scheduler + the live soak
  run are DEFERRED to a clearly-labelled non-functional "from CLI" affordance --
  this pane NEVER spawns a soak in-process (the long-task rule).

  BETA GATING (default OFF -- load-bearing). The ENTIRE template + every fetch is
  wrapped in {#if enabled}. While $betaFlags["ambient-soak-task"] is OFF the
  component renders NOTHING and registers NO poller / SSE handler / timer / fetch
  of its own. There is NO background polling: data is read on demand only when
  the operator OPENS the drawer. Flag defaults OFF (lib/beta/registry.js); the
  operator flips it in Settings > BETA features.

  POLARITY (G2/M15): the reads go to /api/ambient/soak-status + /soak-history,
  which exclude SM-self (project_slug NOT IN the SM slug set AND session_id !=
  SM_OWN_SESSION_ID) server-side. As defense-in-depth this component ALSO drops
  any self row from the ledger (AmbientSoakTask-data.isSelfRun) and surfaces the
  excluded_self tally as a VISIBLE meta tag -- self-exclusion is a feature, not a
  silent filter.

  FIREWALL (G1): no firewalled monitored-project path is read; identity renders FROM DATA.

  ADR-18 MUST floor honoured here:
    - M1 3-frame presence: this is a footer chip + an overlay drawer; it adds NO
      4th frame and removes none.
    - M2 escalation-only foreground: operator-invoked only. The WARN state is a
      BADGE-IN-PLACE -- it never pulses, never steals focus, never auto-fires.
    - M4 paired label+color: EVERY state (AMBIENT OK / POLARITY CHECK / PASS /
      FAIL, each coverage chip, the data-source label) renders a LITERAL text
      word beside its color; color is NEVER the sole signal.
    - Absolute HITL gate: untouched -- this pane performs no HITL mutation.
    - M16 domain-agnostic: every session identity (project_slug / session_id)
      renders FROM DATA. No monitored-project vocabulary is hard-coded.
    - M17 a11y AAA: the chip + drawer are real buttons; role=dialog aria-modal
      with a focus trap, Escape-to-close, focus restored to the chip on close;
      each ledger row is a keyboard-operable <button> accordion; the global 2px
      focus ring on every control; reduced-motion honoured.
    - M18: presentation-only; on-demand reads, never on the verdict hot path,
      never opens /api/commands/stream.

  When the live ambient_runs table is absent / empty (fresh DB / fetch error) it
  falls back to realistic domain-agnostic MOCK fixtures (AmbientSoakTask-data) so
  the feature is always testable headless (usedMockData=true, surfaced as a
  literal text label).

  All selectors are .ast-* scoped so this feature pollutes no shared class.
  Tokens come from theme.css (the calm-* / badge-* / focus-ring / spacing set).
  ASCII-only (cp1252-safe): dash is "--". No smart quotes, no em-dashes.
-->
<script>
  import { onDestroy, tick } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { readOwnSessionId } from '../../api.js';
  // The two read wrappers are additive to api.js (returned as DATA for the main
  // thread to wire). Imported defensively via the * namespace: if api.js has not
  // yet gained them (or a call throws / returns empty) the component degrades to
  // mock so it is always demonstrable headless.
  import * as api from '../../api.js';
  import {
    isSelfRun,
    isFlagged,
    isPass,
    coverageGaps,
    latestVerdict,
    cadenceSentence,
    fmtNum,
    fmtClock,
    ago,
    mockStatus,
    mockHistory,
    MOCK_OWN_SESSION_ID,
  } from './AmbientSoakTask-data.js';

  const FLAG_KEY = 'ambient-soak-task';

  // -- gate: TRUE only while the operator has the BETA flag ON. The entire
  // template + every effect below is conditioned on this. --------------------
  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // SM-own session id (defense-in-depth self-exclude). Read once, lazily.
  let ownSessionId = null;
  function ownId() {
    if (ownSessionId === null) ownSessionId = readOwnSessionId();
    return ownSessionId;
  }

  // -- state ------------------------------------------------------------------
  let open = false;
  let loading = false;
  let loaded = false;
  let usedMockData = false;
  /** @type {Record<string, any>|null} the latest-run summary + cadence meta */
  let status = null;
  /** @type {Array<Record<string, any>>} the newest-first ledger rows */
  let history = [];
  let excludedSelf = 0;
  /** the currently expanded ledger row id (accordion), or null. */
  let openRow = null;

  /** @type {HTMLElement|null} */
  let panelEl = null;
  /** @type {HTMLButtonElement|null} */
  let chipEl = null;
  /** @type {Element|null} */
  let lastFocused = null;

  // -- derived: the paired latest verdict (footer chip + drawer strip) --------
  // latest = the freshest history row (or the status verdict when history is
  // empty but status carries one). The WORD is the load-bearing signal (M4).
  $: latestRun = history.length ? history[0] : null;
  $: verdict = (() => {
    if (latestRun) return latestVerdict(latestRun);
    // No history rows but the status may carry a coarse verdict word.
    const v = status && String(status.verdict || '').toUpperCase();
    if (v === 'WARN' || v === 'FLAGGED') return { variant: 'warn', word: 'POLARITY CHECK', count: 1 };
    if (v === 'OK') return { variant: 'ok', word: 'AMBIENT OK', count: 0 };
    return { variant: 'none', word: 'NO RUNS YET', count: 0 };
  })();
  $: intervalMinutes = (status && Number(status.interval_minutes)) || 30;
  $: lastRunAgoSec = status && status.last_run_ago_s != null ? Number(status.last_run_ago_s) : null;
  $: ageLabel = lastRunAgoSec == null ? '--' : ago(lastRunAgoSec);
  $: cadence = cadenceSentence(verdict, intervalMinutes, lastRunAgoSec);
  $: historyCount = history.length || (status && Number(status.history_count)) || 0;

  // -- the resting chip aria-label (full sentence; never color alone) ---------
  $: chipAria = verdict.variant === 'warn'
    ? ('Ambient polarity check flagged ' + verdict.count + ' in the latest run. '
       + 'Open history. WARN -- not action-required, does not foreground.')
    : verdict.variant === 'none'
      ? 'Ambient soak: no runs on record yet. Open history.'
      : ('Ambient polarity check: AMBIENT OK, last check ' + ageLabel + ' ago. Open history.');

  // -- on-demand load (NO background poller). Reads both endpoints in parallel;
  // any failure / empty shape degrades to mock so the drawer is always
  // demonstrable headless. Never throws to the render path. --------------------
  async function loadAll() {
    if (!enabled) return;
    loading = true;
    let mocked = false;
    let nextStatus = null;
    let nextHistory = [];
    let nextExcluded = 0;

    // 1) the latest-run status + cadence meta.
    try {
      const fn = api.getAmbientSoakStatus;
      const data = typeof fn === 'function' ? await fn() : null;
      if (data && typeof data === 'object' && (data.last_run_at != null || data.verdict != null)) {
        nextStatus = data;
        if (data.own_session_id) ownSessionId = data.own_session_id;
        if (Number.isFinite(Number(data.excluded_self))) nextExcluded = Number(data.excluded_self);
      } else {
        mocked = true;
      }
    } catch {
      mocked = true;
    }

    // 2) the newest-first ledger rows.
    try {
      const fn = api.getAmbientSoakHistory;
      const data = typeof fn === 'function' ? await fn({ limit: 10 }) : null;
      const rows = data && Array.isArray(data.runs) ? data.runs : [];
      if (data && data.own_session_id) ownSessionId = data.own_session_id;
      if (data && Number.isFinite(Number(data.excluded_self))) {
        nextExcluded = Math.max(nextExcluded, Number(data.excluded_self));
      }
      if (rows.length > 0) {
        // Defense-in-depth: drop any SM-self row that slipped the server filter.
        nextHistory = rows.filter((r) => !isSelfRun(r, ownId()));
      } else {
        mocked = true;
      }
    } catch {
      mocked = true;
    }

    if (mocked) {
      if (ownSessionId === null || ownSessionId === '') ownSessionId = MOCK_OWN_SESSION_ID;
      nextStatus = nextStatus && (nextStatus.last_run_at != null || nextStatus.verdict != null)
        ? nextStatus : mockStatus();
      nextHistory = mockHistory().filter((r) => !isSelfRun(r, ownId()));
      nextExcluded = nextExcluded || Number(mockStatus().excluded_self) || 0;
    }

    status = nextStatus;
    history = nextHistory;
    excludedSelf = nextExcluded;
    usedMockData = mocked;
    loaded = true;
    loading = false;
  }

  // -- drawer open / close + focus trap ---------------------------------------
  async function openPanel() {
    if (!enabled || open) return;
    lastFocused = typeof document !== 'undefined' ? document.activeElement : null;
    open = true;
    if (!loaded) await loadAll();
    await tick();
    const first = panelEl && panelEl.querySelector(
      'button:not([disabled]), [href], input, [tabindex]:not([tabindex="-1"])',
    );
    if (first && first.focus) first.focus();
  }

  function closePanel() {
    if (!open) return;
    open = false;
    const target = lastFocused && /** @type {any} */ (lastFocused).focus ? lastFocused : chipEl;
    /** @type {HTMLElement|null} */ (target)?.focus?.();
    lastFocused = null;
  }

  function focusables() {
    if (!panelEl) return [];
    return Array.prototype.slice
      .call(panelEl.querySelectorAll('button, input, [href], [tabindex]:not([tabindex="-1"])'))
      .filter((el) => !el.disabled && el.offsetParent !== null);
  }

  function onPanelKeydown(e) {
    if (e.key === 'Escape') { e.preventDefault(); closePanel(); return; }
    if (e.key === 'Tab') {
      const f = focusables();
      if (!f.length) return;
      const firstEl = f[0];
      const lastEl = f[f.length - 1];
      if (e.shiftKey && document.activeElement === firstEl) { e.preventDefault(); lastEl.focus(); }
      else if (!e.shiftKey && document.activeElement === lastEl) { e.preventDefault(); firstEl.focus(); }
    }
  }

  // -- ledger row accordion ---------------------------------------------------
  function toggleRow(id) {
    openRow = openRow === id ? null : id;
  }

  // -- BETA gate teardown: flag OFF (or destroy) closes the drawer. The
  // {#if enabled} block unmounts the DOM; this clears the open flag. ----------
  $: if (!enabled && open) open = false;
  onDestroy(() => { if (open) open = false; });
</script>

<!-- GATE: render absolutely nothing while OFF. No chip, no drawer, no fetch. -->
{#if enabled}
  <!-- The calm AMBIENT badge -- a real <button>; the WORD is the signal (M4).
       It is the quietest thing in the footer at rest. It does NOT pulse and does
       NOT auto-foreground -- still water. -->
  <button
    bind:this={chipEl}
    class="ast-chip ast-chip--{verdict.variant}"
    type="button"
    aria-haspopup="dialog"
    aria-expanded={open}
    aria-controls="ast-panel"
    aria-label={chipAria}
    on:click={openPanel}
  >
    <span class="ast-chip__dot" aria-hidden="true"></span>
    <span class="ast-chip__word">{verdict.word}</span>
    {#if verdict.variant === 'warn'}
      <span class="ast-chip__age">{verdict.count}</span>
    {:else if verdict.variant !== 'none'}
      <span class="ast-chip__age">{ageLabel}</span>
    {/if}
  </button>

  {#if open}
    <!-- SCRIM: click-out closes. Not a focus target. -->
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div
      class="ast-scrim"
      role="presentation"
      on:click={(e) => { if (e.target === e.currentTarget) closePanel(); }}
    ></div>

    <!-- DRAWER: role=dialog aria-modal; labelled heading; Escape + focus trap. -->
    <aside
      id="ast-panel"
      class="ast-panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="ast-title"
      bind:this={panelEl}
      tabindex="-1"
      on:keydown={onPanelKeydown}
    >
      <!-- aria-live region: announces the verdict + row expansion (M17 a11y) -->
      <div class="ast-sr-only" aria-live="polite">
        {#if loading}Loading ambient soak history...{:else}Ambient latest verdict: {verdict.word}{#if verdict.variant === 'warn'} flagged {verdict.count}{/if}. {historyCount} run{historyCount === 1 ? '' : 's'} in history.{/if}
      </div>

      <header class="ast-head">
        <div class="ast-head__titlewrap">
          <h2 id="ast-title" class="ast-head__title">Ambient Soak -- polarity history</h2>
          <p class="ast-head__sub">Read-only -- newest first. Runs land from Cron, not here.</p>
          <span class="ast-beta">
            BETA -- default OFF, toggled in Settings &gt; BETA features
            {#if usedMockData}<span class="ast-beta__mock"> -- SAMPLE DATA</span>{:else}<span class="ast-beta__live"> -- LIVE</span>{/if}
          </span>
        </div>
        <button class="ast-close" type="button" aria-label="Close ambient soak history (Esc)" on:click={closePanel}>
          <span aria-hidden="true">x</span>
        </button>
      </header>

      <div class="ast-body">
        {#if loading && !loaded}
          <p class="ast-state">Loading ambient soak history...</p>
        {:else}
          <!-- (1) the muted top strip: latest verdict + live cadence sentence -->
          <div class="ast-cadence">
            <div class="ast-cadence__verdict">
              <span class="ast-vbadge ast-vbadge--{verdict.variant}" role="status">
                <span class="ast-vbadge__dot" aria-hidden="true"></span>
                <span>{verdict.word}{#if verdict.variant === 'warn'} {verdict.count}{/if}</span>
              </span>
              <span class="ast-cadence__sentence">{cadence}</span>
            </div>
            <div class="ast-cadence__meta">
              <span class="ast-tag">interval {intervalMinutes}m</span>
              <span class="ast-tag">{historyCount} run{historyCount === 1 ? '' : 's'} in history</span>
              <!-- G2: self-exclusion surfaced VISIBLE, not a silent filter -->
              <span class="ast-tag">excluded_self {excludedSelf}</span>
              {#if usedMockData}
                <span class="ast-tag ast-tag--mock">MOCK DATA -- no ambient history yet</span>
              {/if}
            </div>
          </div>

          <!-- passive affordance: the pane never spawns a soak in-process ----- -->
          <div class="ast-passive" role="note">
            <span class="ast-passive__label">passive</span>
            <span>
              Ambient runs are launched by the operator/main-thread Cron job
              (long-task rule), not from this pane. This drawer is a READ over the
              additive <code>ambient_runs</code> table -- it never spawns a subprocess.
            </span>
          </div>

          <!-- (2) the DEFERRED Cron affordance (clearly non-functional) ------- -->
          <div class="ast-section ast-launch">
            <div class="ast-section__label">Schedule the ambient cadence</div>
            <button
              class="ast-launch__btn"
              type="button"
              disabled
              aria-disabled="true"
              aria-label="Cron scheduling deferred -- run the ambient soak loop from the CLI"
              title="Schedule from the CLI -- the ambient Cron loop is an out-of-process long-task op"
            >
              Schedule from CLI (ambient cadence)
            </button>
            <p class="ast-launch__note">
              <span class="ast-launch__tag">CLI ONLY</span>
              The ~{intervalMinutes}m Cron loop is an out-of-process long-running task --
              it is launched + scheduled from the terminal, NOT spawned in-process
              here. Run: <code>soak_driver --live-session &lt;session_id&gt; --mode ambient</code>
            </p>
          </div>

          <!-- (3) the newest-first typographic ledger ------------------------- -->
          <div class="ast-section__label ast-ledger-head">
            Recent ambient runs
            <span class="ast-section__hint">tick = covered (slate) / flagged (amber)</span>
          </div>

          {#if history.length === 0}
            <p class="ast-state">No ambient runs on record yet. Still water.</p>
          {:else}
            <div class="ast-ledger" role="list" aria-label="Ambient soak runs, newest first">
              {#each history as r (r.id || r.ts)}
                {@const rowId = String(r.id || r.ts)}
                {@const pass = isPass(r)}
                {@const flagged = isFlagged(r)}
                {@const gaps = coverageGaps(r)}
                {@const expanded = openRow === rowId}
                <button
                  class="ast-lrow"
                  class:ast-lrow--flagged={flagged}
                  type="button"
                  role="listitem"
                  aria-expanded={expanded}
                  aria-controls="ast-det-{rowId}"
                  aria-label="Run {fmtClock(r.ts)}, target {r.project_slug || r.session_id}, polarity {pass ? 'PASS' : 'FAIL'}. Activate to expand coverage detail."
                  on:click={() => toggleRow(rowId)}
                >
                  <span class="ast-lrow__tick" aria-hidden="true"></span>
                  <span class="ast-lrow__main">
                    <span class="ast-lrow__ts">{fmtClock(r.ts)}</span>
                    <span class="ast-lrow__target">
                      <span class="ast-lrow__slug">{r.project_slug || r.session_id}</span>
                      <span class="ast-lrow__sid">{r.session_id}</span>
                    </span>
                    <span class="ast-lword ast-lword--{pass ? 'pass' : 'fail'}">
                      <span class="ast-lword__dot" aria-hidden="true"></span>{pass ? 'PASS' : 'FAIL'}
                    </span>
                  </span>
                </button>
                {#if expanded}
                  <div class="ast-ldetail" id="ast-det-{rowId}" role="region" aria-label="Run detail">
                    <dl>
                      <dt>target</dt>
                      <dd>{r.project_slug || '--'} / {r.session_id} (rendered from data)</dd>
                      <dt>polarity</dt>
                      <dd>{pass ? 'PASS -- 0 self-leaks' : 'FAIL -- self/SM leak detected'}</dd>
                      <dt>coverage</dt>
                      <dd>
                        <span class="ast-gapchips">
                          {#if gaps.length === 0}
                            <span class="ast-gapchips__none">no gaps -- full coverage</span>
                          {:else}
                            {#each gaps as g}
                              <span class="ast-gapchip">{g}</span>
                            {/each}
                          {/if}
                        </span>
                      </dd>
                      <dt>duration</dt>
                      <dd>{fmtNum(r.duration_s)}s</dd>
                      <dt>messages</dt>
                      <dd>{fmtNum(r.messages_seen)} seen</dd>
                    </dl>
                  </div>
                {/if}
              {/each}
            </div>
          {/if}
        {/if}
      </div>

      <footer class="ast-foot">
        <span class="ast-foot__pill">BETA</span>
        <span>
          Read-only. Default OFF, toggled in Settings &gt; BETA features. Never
          auto-foregrounds; never a fourth frame.
        </span>
      </footer>
    </aside>
  {/if}
{/if}

<style>
  /* ===== the calm AMBIENT chip -- the quietest thing in the footer at rest.
     A hairline-bordered chip reading a monospace age. The DOT is decorative; the
     WORD is the signal (M4). It does NOT pulse and does NOT auto-foreground. === */
  .ast-chip {
    appearance: none; cursor: pointer; text-align: left;
    display: inline-flex; align-items: center; gap: 9px;
    border-radius: var(--radius-sharp, 2px); padding: 0.3rem 0.65rem; line-height: 1.1;
    font-family: var(--ff-system);
    transition: border-color var(--t-calm, 180ms ease), background var(--t-calm, 180ms ease),
                color var(--t-calm, 180ms ease);
  }
  .ast-chip:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid) var(--focus-ring-color, #d97706);
    outline-offset: var(--focus-ring-offset, 2px);
  }
  .ast-chip__dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex: 0 0 auto; }
  .ast-chip__word { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
  .ast-chip__age {
    font-family: var(--font-d, var(--ff-mono)); font-size: 0.72rem; letter-spacing: 0.02em;
    color: var(--calm-ink-quiet, var(--text-dim, #948870)); font-variant-numeric: tabular-nums;
  }
  /* OK (healthy / idle) -- slate, hairline border, no motion (still water). */
  .ast-chip--ok {
    color: var(--badge-obs-fg, #475569); background: var(--badge-obs-bg, #f1f5f9);
    border: 1px solid var(--badge-obs-border, #cbd5e1);
  }
  .ast-chip--ok:hover { border-color: var(--calm-accent, var(--accent, #f59e0b)); }
  /* NONE (no runs yet) -- same calm slate, distinct WORD. */
  .ast-chip--none {
    color: var(--badge-obs-fg, #475569); background: var(--badge-obs-bg, #f1f5f9);
    border: 1px dashed var(--badge-obs-border, #cbd5e1);
  }
  .ast-chip--none:hover { border-color: var(--calm-accent, var(--accent, #f59e0b)); }
  /* WARN (a polarity_violation OR coverage_gap in the latest run) -- amber-orange,
     dashed border. WARN, NOT ACTION REQUIRED: it must NOT pulse (M2). */
  .ast-chip--warn {
    color: var(--badge-warn-fg, #9a3412); background: var(--badge-warn-bg, #ffedd5);
    border: 1px dashed var(--badge-warn-border, #ea580c);
  }
  .ast-chip--warn:hover { border-color: var(--badge-warn-fg, #9a3412); }
  .ast-chip--warn .ast-chip__age { color: var(--badge-warn-fg, #9a3412); }

  /* ---- scrim + right-anchored drawer (SettingsDrawer dialog idiom) --------- */
  .ast-scrim {
    position: fixed; inset: 0; background: rgba(8, 10, 12, 0.55);
    backdrop-filter: blur(1px); z-index: 80;
  }
  .ast-panel {
    position: fixed; top: 0; right: 0; bottom: 0;
    width: min(520px, 96vw); z-index: 81;
    display: flex; flex-direction: column;
    background: var(--calm-surface-raised, var(--bg-card, #0c1118));
    border-left: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25)));
    box-shadow: -18px 0 48px -24px rgba(0, 0, 0, 0.7);
    color: var(--calm-ink, var(--text, #b8b098));
    font-family: var(--ff-system); overflow: hidden;
  }
  :global(html[data-motion='allow']) .ast-panel { animation: astSlide 160ms ease-out; }
  @keyframes astSlide { from { transform: translateX(12px); opacity: 0; } to { transform: none; opacity: 1; } }

  /* ---- header ------------------------------------------------------------- */
  .ast-head {
    flex: 0 0 auto; display: flex; align-items: flex-start; justify-content: space-between;
    gap: var(--space-4, 10px);
    padding: var(--space-5, 14px) var(--space-6, 22px) var(--space-4, 10px);
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
  }
  .ast-head__titlewrap { min-width: 0; }
  .ast-head__title {
    margin: 0; font-family: var(--font-h, var(--ff-system)); font-size: 18px;
    letter-spacing: 0.05em; text-transform: uppercase;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
  }
  .ast-head__sub { margin: 3px 0 0; font-size: 11px; letter-spacing: 0.04em; color: var(--calm-ink-quiet, var(--text-dim, #948870)); }
  .ast-beta {
    display: inline-block; margin-top: 8px;
    font-family: var(--font-d, var(--ff-mono)); font-size: 10px;
    letter-spacing: 0.04em; color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .ast-beta__mock { color: var(--badge-warn-fg, #9a3412); font-weight: 700; }
  .ast-beta__live { color: var(--badge-decided-fg, #15803d); font-weight: 700; }
  .ast-close {
    appearance: none; background: transparent;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-sharp, 2px); color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    width: 28px; height: 28px; line-height: 1; font-size: 14px; cursor: pointer; flex: 0 0 auto;
    display: inline-flex; align-items: center; justify-content: center;
    transition: color var(--t-calm, 180ms ease), border-color var(--t-calm, 180ms ease);
  }
  .ast-close:hover { color: var(--calm-accent, var(--accent, #f59e0b)); border-color: var(--calm-hairline-hi, var(--border-hi)); }
  .ast-close:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid) var(--focus-ring-color, #d97706);
    outline-offset: var(--focus-ring-offset, 2px);
  }

  /* ---- body --------------------------------------------------------------- */
  .ast-body {
    flex: 1 1 auto; overflow-y: auto;
    padding: var(--space-5, 14px) var(--space-6, 22px) var(--space-7, 36px);
    display: flex; flex-direction: column; gap: var(--space-5, 14px);
  }
  .ast-state { margin: 4px 0; font-size: 13px; font-style: italic; color: var(--calm-ink-quiet, var(--text-dim, #948870)); }
  .ast-section { display: flex; flex-direction: column; gap: var(--space-3, 6px); }
  .ast-section__label {
    font-size: 13px; font-weight: 600; letter-spacing: 0.02em;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    display: flex; align-items: baseline; justify-content: space-between; gap: 10px;
  }
  .ast-section__hint { font-size: 11px; font-weight: 400; color: var(--calm-ink-quiet, var(--text-dim, #948870)); letter-spacing: 0.02em; }

  /* ---- (1) the muted cadence strip ---------------------------------------- */
  .ast-cadence {
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-soft, 4px);
    padding: 13px 15px; background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
    display: flex; flex-direction: column; gap: 8px;
  }
  .ast-cadence__verdict { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .ast-vbadge {
    display: inline-flex; align-items: center; gap: 8px;
    font-family: var(--ff-system); font-size: 13px; font-weight: 800; letter-spacing: 0.06em;
    text-transform: uppercase; padding: 6px 12px; border-radius: var(--radius-sharp, 2px); line-height: 1;
  }
  .ast-vbadge__dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; flex: 0 0 auto; }
  .ast-vbadge--ok { color: var(--badge-obs-fg, #475569); background: var(--badge-obs-bg, #f1f5f9); border: 1px solid var(--badge-obs-border, #cbd5e1); font-weight: 700; }
  .ast-vbadge--none { color: var(--badge-obs-fg, #475569); background: var(--badge-obs-bg, #f1f5f9); border: 1px dashed var(--badge-obs-border, #cbd5e1); font-weight: 700; }
  .ast-vbadge--warn { color: var(--badge-warn-fg, #9a3412); background: var(--badge-warn-bg, #ffedd5); border: 1px dashed var(--badge-warn-border, #ea580c); }
  .ast-cadence__sentence {
    font-family: var(--font-d, var(--ff-mono)); font-size: 11px; color: var(--calm-ink-quiet, var(--text-dim, #948870));
    line-height: 1.55; font-variant-numeric: tabular-nums;
  }
  .ast-cadence__meta {
    font-family: var(--font-d, var(--ff-mono)); font-size: 10px; color: var(--calm-ink-quiet, var(--text-dim, #948870));
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
    border-top: 1px dashed var(--calm-hairline, var(--border, #192030)); padding-top: 8px; font-variant-numeric: tabular-nums;
  }
  .ast-tag {
    color: var(--badge-obs-fg, #475569); background: var(--badge-obs-bg, #f1f5f9); border: 1px solid var(--badge-obs-border, #cbd5e1);
    border-radius: 999px; padding: 2px 8px; font-size: 10px; letter-spacing: 0.04em; font-weight: 600;
  }
  .ast-tag--mock {
    color: var(--badge-warn-fg, #9a3412); background: var(--badge-warn-bg, #ffedd5); border: 1px dashed var(--badge-warn-border, #ea580c);
  }

  /* ---- passive note ------------------------------------------------------- */
  .ast-passive {
    display: flex; gap: 9px; align-items: flex-start;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030)); border-radius: var(--radius-soft, 4px);
    background: var(--calm-surface-row, var(--bg-row, #0e141e)); color: var(--calm-ink-quiet, var(--text-dim, #948870));
    padding: 10px 13px; font-size: 11px; line-height: 1.5;
  }
  .ast-passive__label {
    flex: 0 0 auto; font-size: 9px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068)); border: 1px solid var(--calm-hairline, var(--border, #192030));
    border-radius: 999px; padding: 2px 7px; margin-top: 1px;
  }
  .ast-passive code, .ast-launch__note code {
    font-family: var(--font-d, var(--ff-mono)); color: var(--calm-accent, var(--accent, #f59e0b));
    background: var(--calm-surface-row, var(--bg-row, #0e141e)); padding: 1px 5px; border-radius: 2px;
  }

  /* ---- (2) the DEFERRED Cron affordance (clearly non-functional) ---------- */
  .ast-launch {
    border: 1px dashed var(--badge-ar-border, #d97706); border-radius: var(--radius-soft, 4px);
    padding: 12px 14px; background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
  }
  .ast-launch__btn {
    appearance: none; align-self: flex-start; cursor: not-allowed;
    background: transparent; color: var(--calm-ink-quiet, var(--text-dim, #948870));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030)); border-radius: 5px;
    font-family: var(--ff-system); font-size: 13px; font-weight: 600; letter-spacing: 0.02em;
    padding: 10px 16px; line-height: 1; opacity: 0.6;
  }
  .ast-launch__note { margin: 6px 0 0; font-size: 11px; line-height: 1.5; color: var(--calm-ink-quiet, var(--text-dim, #948870)); max-width: 52ch; }
  .ast-launch__tag {
    display: inline-block; margin-right: 7px; font-size: 9px; font-weight: 800; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--badge-ar-fg, #d97706);
    border: 1px solid var(--badge-ar-border, #d97706); border-radius: 999px; padding: 2px 7px;
  }

  /* ---- (3) the newest-first typographic ledger ---------------------------- */
  .ast-ledger-head { margin-top: 2px; }
  .ast-ledger { display: flex; flex-direction: column; gap: 0; margin-top: 2px; }
  /* each run is a single keyboard-operable button row. No card chrome -- a
     typographic ledger. A thin left vertical tick carries severity (calm =
     covered, amber = flagged) ALONGSIDE the PASS/FAIL word (never alone). */
  .ast-lrow {
    appearance: none; cursor: pointer; text-align: left; width: 100%;
    display: grid; grid-template-columns: 3px 1fr; gap: 0 12px; align-items: stretch;
    background: transparent; border: none; border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    padding: 0; color: var(--calm-ink, var(--text, #b8b098)); font-family: var(--ff-system);
  }
  .ast-lrow:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid) var(--focus-ring-color, #d97706);
    outline-offset: -2px;
  }
  .ast-lrow:hover .ast-lrow__main { background: var(--calm-surface-hover, var(--bg-row-hover, #131c2a)); }
  .ast-lrow__tick { width: 3px; align-self: stretch; background: var(--badge-obs-border, #cbd5e1); }
  .ast-lrow--flagged .ast-lrow__tick { background: var(--badge-warn-border, #ea580c); }
  .ast-lrow__main {
    display: grid; grid-template-columns: auto 1fr auto; gap: 2px 14px;
    align-items: center; padding: 11px 12px; transition: background var(--t-calm, 180ms ease);
  }
  .ast-lrow__ts {
    font-family: var(--font-d, var(--ff-mono)); font-size: 12px; color: var(--calm-ink-quiet, var(--text-dim, #948870));
    font-variant-numeric: tabular-nums; white-space: nowrap;
  }
  .ast-lrow__target { min-width: 0; }
  .ast-lrow__slug { font-size: 13px; font-weight: 600; color: var(--calm-ink-loud, var(--text-bright, #e8e0cc)); letter-spacing: 0.01em; }
  .ast-lrow__sid { font-family: var(--font-d, var(--ff-mono)); font-size: 10px; color: var(--calm-ink-quiet, var(--text-dim, #948870)); margin-left: 7px; }
  /* the verdict WORD column -- the verdict leads, the rest is quiet meta. PASS =
     DECIDED green word, FAIL = BLOCKED red word. */
  .ast-lword {
    display: inline-flex; align-items: center; gap: 7px; justify-self: end;
    font-size: 12px; font-weight: 800; letter-spacing: 0.07em; text-transform: uppercase;
    padding: 4px 10px; border-radius: var(--radius-sharp, 2px); line-height: 1; white-space: nowrap;
  }
  .ast-lword__dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex: 0 0 auto; }
  .ast-lword--pass { color: var(--badge-decided-fg, #15803d); background: var(--badge-decided-bg, #dcfce7); border: 1px solid var(--badge-decided-border, #86efac); }
  .ast-lword--fail { color: var(--badge-blocked-fg, #b91c1c); background: var(--badge-blocked-bg, #fee2e2); border: 2px solid var(--badge-blocked-border, #dc2626); }

  /* the expandable detail (coverage_gaps list + meta) -- accordion. */
  .ast-ldetail {
    padding: 0 12px 13px 27px;
    font-family: var(--font-d, var(--ff-mono)); font-size: 11px; color: var(--calm-ink-quiet, var(--text-dim, #948870)); line-height: 1.6;
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
  }
  .ast-ldetail dl { margin: 0; display: grid; grid-template-columns: auto 1fr; gap: 3px 14px; }
  .ast-ldetail dt { color: var(--calm-ink-chrome, var(--text-ui, #8a8068)); text-transform: uppercase; letter-spacing: 0.06em; font-size: 9px; }
  .ast-ldetail dd { margin: 0; color: var(--calm-ink, var(--text, #b8b098)); font-variant-numeric: tabular-nums; }
  /* coverage gap chips -- each carries its literal text (never color alone). */
  .ast-gapchips { display: inline-flex; gap: 6px; flex-wrap: wrap; }
  .ast-gapchip {
    color: var(--badge-warn-fg, #9a3412); background: var(--badge-warn-bg, #ffedd5); border: 1px dashed var(--badge-warn-border, #ea580c);
    border-radius: 999px; padding: 1px 8px; font-size: 10px; letter-spacing: 0.03em; font-weight: 600; text-transform: none;
  }
  .ast-gapchips__none { color: var(--badge-decided-fg, #15803d); }

  /* ---- footer ------------------------------------------------------------- */
  .ast-foot {
    flex: 0 0 auto; padding: 0.55rem 1.15rem;
    border-top: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    display: flex; align-items: center; gap: 0.5rem;
    font-size: 0.68rem; color: var(--calm-ink-quiet, var(--text-dim, #948870));
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
  }
  .ast-foot__pill {
    font-size: 0.6rem; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase;
    padding: 0.16rem 0.45rem; border-radius: 6px;
    color: var(--badge-ar-fg, #d97706); background: var(--badge-ar-bg, #fef3c7); border: 1px solid var(--badge-ar-border, #d97706);
  }

  /* visually-hidden live region for screen readers (M17). */
  .ast-sr-only {
    position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; border: 0;
    clip: rect(0 0 0 0); overflow: hidden; white-space: nowrap;
  }

  /* reduced motion (M17): suppress the slide-in + transitions unless allowed. */
  :global(html[data-motion='reduce']) .ast-panel,
  :global(html[data-motion='reduce']) .ast-chip,
  :global(html[data-motion='reduce']) .ast-lrow__main { transition: none; animation: none; }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .ast-panel { animation: none; }
    :global(html:not([data-motion='allow'])) .ast-chip,
    :global(html:not([data-motion='allow'])) .ast-lrow__main { transition: none; }
  }
</style>
