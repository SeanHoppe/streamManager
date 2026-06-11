<!--
  SoakPanel.svelte -- BETA feature "soak-panel" (#16): Frame D -- Live Session
  Soak Control Panel with Polarity Audit.

  WHAT IT DOES
    A glance-first, BETA-gated right-side DRAWER (Frame-D idiom) summoned from a
    quiet footer "SOAK" affordance -- NOT a fourth always-on frame (the 3-frame
    floor is inviolable, ADR-18 M1). The drawer answers one question loudly: "is
    the SM-self-exclusion polarity gate still live?" via a single paired
    label+color POLARITY PASS/FAIL verdict header, computed from a READ over
    gov.db (GET /api/soak/polarity-audit). Below it: a ranked, SELF-EXCLUDED,
    firewall-filtered live NON-SM session selector (GET /api/soak/sessions) with
    a VISIBLE "excluded: N self / M firewalled" footer (self-exclusion is a
    feature, not a silent filter), the last soak run's per-band p50/p95 readout
    (GET /api/soak/status -> soak_runs.report_md), and a clearly-labelled
    NON-functional "Launch from CLI" affordance. The live soak LAUNCH (a
    long-running Tier-4 subprocess) is DEFERRED to the CLI / main thread per
    feedback_subagent_long_task_abandonment -- this panel NEVER spawns a soak
    in-process.

  CONSTRAINED ADDITIVE v1: NO new bus envelope, NO message_bus edit, NO ADR-18
  amendment, NO in-process soak spawn. Only additive read surfaces.

  BETA GATING (default OFF -- load-bearing). The ENTIRE body is wrapped in
  {#if enabled}. While $betaFlags["soak-panel"] is OFF the component renders
  NOTHING and registers NO poller / SSE handler / timer / fetch of its own.
  There is NO background polling: data is fetched on demand only when the
  operator OPENS the drawer. Flag defaults OFF (lib/beta/registry.js); the
  operator flips it in Settings > BETA features ("Live Session Soak control panel").

  POLARITY (G2/M15): the selector fetch goes to GET /api/soak/sessions, which
  excludes SM-self (project_slug NOT IN the SM slug set AND session_id != self)
  AND rejects firewalled (certPortal-cwd) candidates server-side. As
  defense-in-depth this component ALSO re-classifies every candidate
  (SoakPanel-data.classifyCandidate) so a self / firewalled row can never become
  selectable even on the mock path, and the excluded counts are rendered VISIBLE
  in the selector footer. The polarity verdict is a READ proof of zero SM-self
  leakage.

  FIREWALL (G1): no certPortal path is read; a candidate whose cwd contains a
  firewalled fragment is rejected (never selectable) and counted in the footer.

  ADR-18 MUST floor honoured here:
    - M1 3-frame presence: this is a footer affordance + an overlay drawer; it
      adds NO 4th frame and removes none. The three frames are untouched.
    - M2 escalation-only foreground: the soak panel is operator-initiated only.
      The footer affordance raises no escalation, steals no focus, auto-fires
      nothing. A FAIL verdict states (in prose) that the real escalation path is
      the existing Frame A HITL hand-off -- this badge is glanceable context.
    - M4 paired label+color: EVERY state (verdict PASS/FAIL/NONE, run state
      IN PROGRESS / COMPLETE / FAILED, each excluded tag) renders a LITERAL text
      label beside its color; color is NEVER the sole signal.
    - Absolute HITL gate: untouched -- this panel performs no HITL mutation.
    - M16 domain-agnostic: every session identity renders FROM DATA
      (project_slug / session_id / cwd). No monitored-project vocabulary is
      hard-coded (the firewall fragment is configuration in SoakPanel-data).
    - M17 a11y AAA: the footer trigger + drawer are real buttons; role="dialog"
      aria-modal with a focus trap, Escape-to-close, focus restored to the
      trigger on close; the verdict + selection use aria-live; full keyboard
      path; every control carries the global 2px focus ring.
    - M18: presentation-only; on-demand reads, never on the verdict hot path,
      never opens /api/commands/stream.

  When live gov.db data is absent (fresh DB / fetch error) it falls back to
  realistic, domain-agnostic MOCK fixtures (SoakPanel-data) so the feature is
  always testable headless (usedMockData=true, surfaced as a literal text label).

  All selectors are .sp-* scoped so this feature pollutes no shared class.
  Tokens come from theme.css (the calm-* / badge-* / focus-ring / spacing set).
  ASCII-only (cp1252-safe): dash is "--". No smart quotes, no em-dashes.
-->
<script>
  import { onDestroy, tick } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { readOwnSessionId } from '../../api.js';
  // These three read wrappers are additive to api.js (returned as DATA for the
  // main thread to wire). Imported defensively: if api.js has not yet gained
  // them (or a call throws / returns empty) the component degrades to mock.
  import * as api from '../../api.js';
  import {
    rankCandidates,
    classifyCandidate,
    verdictFor,
    stateFor,
    parseBands,
    relRecency,
    fmtNum,
    mockCandidates,
    mockSoakRun,
    mockBands,
    MOCK_OWN_SESSION_ID,
  } from './SoakPanel-data.js';

  const FLAG_KEY = 'soak-panel';

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
  let usedMockData = false;
  /** @type {Array<Record<string, any>>} */
  let candidates = [];
  let excludedSelf = 0;
  let excludedFirewalled = 0;
  let selectedSid = '';
  /** @type {Record<string, any>|null} the most-recent soak run (or mock) */
  let lastRun = null;
  /** @type {{pass:boolean, leak_count:number, checked:number}|null} */
  let audit = null;

  /** @type {HTMLElement|null} */
  let panelEl = null;
  /** @type {Element|null} */
  let lastFocused = null;

  // -- derived: ranked selectable candidates + visible excluded counts --------
  $: ranked = enabled
    ? rankCandidates(candidates, ownId())
    : { sessions: [], excludedSelf: 0, excludedFirewalled: 0, totalSeen: 0 };
  // Prefer server-reported excluded counts (authoritative) when present; else
  // the client-derived counts from the ranking.
  $: selfCount = excludedSelf || ranked.excludedSelf;
  $: fwCount = excludedFirewalled || ranked.excludedFirewalled;

  // -- derived: paired verdict + run-state + per-band table -------------------
  // The polarity VERDICT prefers the dedicated audit read (a fresh gov.db
  // proof); it falls back to the last run's polarity_pass when no audit landed.
  $: verdict = audit
    ? (audit.pass
        ? { variant: 'pass', label: 'POLARITY PASS -- 0 self-leaks' }
        : { variant: 'fail', label: 'POLARITY FAIL -- ' + (Number(audit.leak_count) || 0) + ' self-leaks' })
    : verdictFor(lastRun);
  $: runState = stateFor(lastRun);
  $: bands = (() => {
    if (!lastRun) return [];
    const parsed = parseBands(lastRun.report_md);
    return parsed.length ? parsed : (usedMockData ? mockBands() : []);
  })();
  $: verdictMeta = (() => {
    if (audit) {
      return 'checked ' + fmtNum(audit.checked) + ' rows -- '
        + (Number(audit.leak_count) || 0) + ' SM-self leak(s) past the WHERE-clause.';
    }
    if (lastRun) {
      return 'rejections=' + (Number(lastRun.rejection_count) || 0)
        + '  self_leaks=' + (Number(lastRun.polarity_pass) === 1 ? 0 : (Number(lastRun.rejection_count) || 0));
    }
    return 'Open a soak to populate the self-exclusion audit.';
  })();

  // -- on-demand load (NO background poller). Fetches all three reads in
  // parallel; any failure / empty shape degrades that slice to mock so the
  // drawer is always demonstrable headless. -----------------------------------
  async function loadAll() {
    if (!enabled) return;
    loading = true;
    let mocked = false;
    // 1) ranked self-excluded candidate sessions.
    try {
      const fn = api.getSoakSessions;
      const data = typeof fn === 'function' ? await fn() : null;
      const rows = data && Array.isArray(data.sessions) ? data.sessions : [];
      if (data && data.own_session_id) ownSessionId = data.own_session_id;
      if (rows.length > 0) {
        candidates = rows;
        excludedSelf = Number(data.excluded_self) || 0;
        excludedFirewalled = Number(data.excluded_firewalled) || 0;
      } else {
        mocked = true;
        candidates = mockCandidates();
        if (ownSessionId === null || ownSessionId === '') ownSessionId = MOCK_OWN_SESSION_ID;
        excludedSelf = 0;
        excludedFirewalled = 0;
      }
    } catch {
      mocked = true;
      candidates = mockCandidates();
      if (ownSessionId === null || ownSessionId === '') ownSessionId = MOCK_OWN_SESSION_ID;
      excludedSelf = 0;
      excludedFirewalled = 0;
    }
    // 2) last soak run (status read).
    try {
      const fn = api.getSoakStatus;
      const data = typeof fn === 'function' ? await fn() : null;
      const runs = data && Array.isArray(data.runs) ? data.runs : [];
      lastRun = runs.length ? runs[0] : (mocked ? mockSoakRun() : null);
      if (!runs.length && !mocked && data && data.runs) {
        // live server, genuinely zero runs -> mock the run readout so the
        // per-band table + verdict are still demonstrable (testable headless).
        lastRun = mockSoakRun();
        mocked = true;
      }
    } catch {
      lastRun = mockSoakRun();
      mocked = true;
    }
    // 3) polarity audit (the loud verdict).
    try {
      const fn = api.getSoakPolarityAudit;
      const data = typeof fn === 'function' ? await fn() : null;
      if (data && typeof data.pass === 'boolean') {
        audit = {
          pass: data.pass,
          leak_count: Number(data.leak_count) || 0,
          checked: Number(data.checked) || 0,
        };
      } else {
        audit = mocked ? { pass: true, leak_count: 0, checked: 21065 } : null;
      }
    } catch {
      audit = { pass: true, leak_count: 0, checked: 21065 };
      mocked = true;
    }
    usedMockData = mocked;
    // default-select the top-ranked (busiest + most-recent) selectable row.
    const r = rankCandidates(candidates, ownId());
    selectedSid = r.sessions.length ? (r.sessions[0].session_id || r.sessions[0].id || '') : '';
    loading = false;
  }

  // -- drawer open / close + focus trap ---------------------------------------
  async function openPanel() {
    if (!enabled || open) return;
    lastFocused = typeof document !== 'undefined' ? document.activeElement : null;
    open = true;
    await loadAll();
    await tick();
    const first = panelEl && panelEl.querySelector(
      'button:not([disabled]), [href], input, [tabindex]:not([tabindex="-1"])',
    );
    if (first && first.focus) first.focus();
  }

  function closePanel() {
    if (!open) return;
    open = false;
    if (lastFocused && lastFocused.focus) lastFocused.focus();
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

  // -- selection (single-select listbox of real <button> rows) ----------------
  function selectRow(c) {
    const cls = classifyCandidate(c, ownId());
    if (!cls.selectable) return; // self / firewalled are never selectable
    selectedSid = c.session_id || c.id || '';
  }

  // -- BETA gate teardown: flag OFF (or destroy) closes the drawer. The
  // {#if enabled} block unmounts the DOM; this clears the open flag. ----------
  $: if (!enabled) teardown();
  function teardown() {
    if (open) open = false;
  }
  onDestroy(teardown);
</script>

<!-- GATE: render absolutely nothing while OFF. No trigger, no drawer, no fetch. -->
{#if enabled}
  <!-- The quiet footer SOAK affordance (mirrors the mockup chrome button). It
       opens the Frame-D drawer; it is NOT an always-on frame. -->
  <button
    class="sp-trigger"
    type="button"
    aria-haspopup="dialog"
    aria-label="Open Live Session Soak control panel (Frame D)"
    on:click={openPanel}
  >
    <span class="sp-trigger__dot" aria-hidden="true"></span>
    SOAK
  </button>

  {#if open}
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div
      class="sp-scrim"
      role="presentation"
      on:click={(e) => { if (e.target === e.currentTarget) closePanel(); }}
    ></div>

    <aside
      class="sp-panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="sp-title"
      bind:this={panelEl}
      tabindex="-1"
      on:keydown={onPanelKeydown}
    >
      <!-- aria-live region: announces the loaded verdict + the selection -->
      <div class="sp-sr-only" aria-live="polite">
        {#if loading}Loading soak panel...{:else}Last soak verdict: {verdict.label}. Selected session {selectedSid || 'none'}.{/if}
      </div>

      <header class="sp-head">
        <div class="sp-head__titlewrap">
          <h2 id="sp-title" class="sp-head__title">Frame D -- Live Session Soak</h2>
          <p class="sp-head__sub">Tier-4 real-JSONL soak with polarity audit</p>
          <span class="sp-beta">
            BETA -- default OFF, toggled in Settings &gt; BETA features
            {#if usedMockData}<span class="sp-beta__mock"> -- SAMPLE DATA</span>{:else}<span class="sp-beta__live"> -- LIVE</span>{/if}
          </span>
        </div>
        <button class="sp-close" type="button" aria-label="Close Frame D (Esc)" on:click={closePanel}>
          <span aria-hidden="true">x</span>
        </button>
      </header>

      <div class="sp-body">
        <!-- (1) the LOUD glanceable POLARITY verdict header (M4 paired badge) -->
        <div class="sp-verdict">
          <span class="sp-verdict__caption">Polarity verdict -- SM-self leakage audit</span>
          <span class="sp-vbadge sp-vbadge--{verdict.variant}" role="status">
            <span class="sp-vbadge__dot" aria-hidden="true"></span>
            <span>{verdict.label}</span>
          </span>
          <span class="sp-verdict__meta">{verdictMeta}</span>
        </div>

        <!-- (2) ranked self-excluded session selector ----------------------- -->
        <div class="sp-section">
          <div class="sp-section__label">
            Live session selector
            <span class="sp-section__hint">ranked, self-excluded, firewall-filtered</span>
          </div>
          <p class="sp-section__desc">
            Non-SM sessions only (project_slug NOT IN streamManager AND
            session_id != self). Busiest + most-recent is pre-elevated.
            project_slug is rendered FROM DATA -- domain-agnostic.
          </p>

          {#if loading}
            <p class="sp-state">Loading candidates...</p>
          {:else if ranked.sessions.length === 0}
            <p class="sp-state">No eligible non-SM sessions. Still water.</p>
          {:else}
            <div class="sp-selector" role="listbox" aria-label="Rankable non-SM live sessions">
              {#each ranked.sessions as c (c.session_id || c.id)}
                {@const sid = c.session_id || c.id || ''}
                {@const isSel = sid === selectedSid}
                <button
                  class="sp-srow"
                  class:sp-srow--top={c.top}
                  type="button"
                  role="option"
                  aria-selected={isSel}
                  aria-pressed={isSel}
                  on:click={() => selectRow(c)}
                >
                  <span class="sp-srow__main">
                    <span class="sp-srow__slug">
                      {c.project_slug || sid}
                      {#if c.top}<span class="sp-srow__toptag">top pick</span>{/if}
                    </span>
                    <span class="sp-srow__id">{sid}{#if c.cwd} -- {c.cwd}{/if}</span>
                  </span>
                  <span class="sp-srow__busy">{fmtNum(c.busy != null ? c.busy : c.busy_score)}<small>busy</small></span>
                  <span class="sp-srow__recency">{relRecency(c.recencySecs)}</span>
                </button>
              {/each}
            </div>
          {/if}

          <!-- VISIBLE self-exclude / firewall rejection footer (G1/G2): a
               feature, not a silent filter. Each tag pairs a count + literal
               label (number never alone). -->
          <div class="sp-excluded" aria-label="Sessions excluded by the polarity gate and firewall">
            <span class="sp-excluded__lead">excluded:</span>
            <span class="sp-excluded__tag">{selfCount} self</span>
            <span class="sp-excluded__tag">{fwCount} firewalled</span>
          </div>
        </div>

        <!-- (3) the DEFERRED launch affordance (clearly non-functional) ------ -->
        <div class="sp-section sp-launch">
          <div class="sp-section__label">Launch a live soak</div>
          <button
            class="sp-launch__btn"
            type="button"
            disabled
            aria-disabled="true"
            aria-label="Launch deferred -- run a live soak from the CLI"
            title="Launch from the CLI -- a live soak is a long-running main-thread task"
          >
            Launch from CLI (soak_driver --live-session)
          </button>
          <p class="sp-launch__note">
            <span class="sp-launch__tag">CLI ONLY</span>
            A live 5-min Tier-4 soak is a long-running task -- it is launched from
            the terminal against the selected session, NOT spawned in-process here.
            Run: <code>soak_driver --live-session {selectedSid || '&lt;session_id&gt;'}</code>
          </p>
        </div>

        <!-- (4) the last soak report -- per-band p50/p95 readout ------------ -->
        <div class="sp-section">
          <div class="sp-section__label">
            Last soak report
            {#if lastRun}<span class="sp-section__hint">{lastRun.soak_id || ''}</span>{/if}
          </div>

          {#if !lastRun}
            <p class="sp-state">No soak run on record yet.</p>
          {:else}
            <div class="sp-runstate">
              <span class="sp-statebadge sp-statebadge--{runState.variant}" role="status">
                <span class="sp-statebadge__dot" aria-hidden="true"></span>{runState.label}
              </span>
            </div>

            {#if bands.length}
              <table class="sp-bands">
                <caption>Per-band latency -- p50 / p95 (mirrors soak_driver._render_per_band)</caption>
                <thead>
                  <tr>
                    <th scope="col">Path</th><th scope="col">n</th>
                    <th scope="col">p50 (s)</th><th scope="col">p95 (s)</th>
                  </tr>
                </thead>
                <tbody>
                  {#each bands as b (b.path)}
                    <tr>
                      <td>{b.path}</td><td>{fmtNum(b.n)}</td>
                      <td>{b.p50}</td><td>{b.p95}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            {/if}

            {#if lastRun.report_md}
              <pre class="sp-reportmd">{lastRun.report_md}</pre>
            {/if}

            {#if verdict.variant === 'fail'}
              <!-- FAIL-only escalation surface (M2: routes via the EXISTING Frame
                   A HITL hand-off; this badge is glanceable context, never the
                   silent end of the line). -->
              <div class="sp-escalate" role="note">
                <b>POLARITY FAIL.</b> A self / streamManager session leaked past the
                self-exclude WHERE-clause. Per ADR-18 escalation-only-foreground, a
                real regression foregrounds via the EXISTING Frame A HITL path -- this
                badge is glanceable context. The ship-gate is NOT cleared.
              </div>
            {/if}
          {/if}
        </div>
      </div>
    </aside>
  {/if}
{/if}

<style>
  /* ---- the quiet footer SOAK affordance (mirrors mockup .chrome-btn) ------- */
  .sp-trigger {
    appearance: none;
    display: inline-flex; align-items: center; gap: 6px;
    background: transparent;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: 2px;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    font-family: var(--ff-system);
    font-size: 0.68rem; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase;
    padding: 0.15rem 0.6rem; line-height: 1; cursor: pointer;
    transition: color var(--t-calm, 180ms ease), border-color var(--t-calm, 180ms ease),
                background var(--t-calm, 180ms ease);
  }
  .sp-trigger:hover {
    color: var(--calm-accent, var(--accent, #f59e0b));
    border-color: var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25)));
    background: var(--calm-accent-wash, var(--accent-dim, rgba(245, 158, 11, 0.09)));
  }
  .sp-trigger:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid) var(--focus-ring-color, #d97706);
    outline-offset: var(--focus-ring-offset, 2px);
  }
  .sp-trigger__dot {
    width: 5px; height: 5px; border-radius: 50%;
    background: var(--calm-accent, var(--accent, #f59e0b)); flex: 0 0 auto;
  }

  /* ---- scrim + right-anchored Frame-D drawer (SettingsDrawer dialog idiom) -- */
  .sp-scrim {
    position: fixed; inset: 0; background: rgba(8, 10, 12, 0.55);
    backdrop-filter: blur(1px); z-index: 80;
  }
  .sp-panel {
    position: fixed; top: 0; right: 0; bottom: 0;
    width: min(480px, 94vw); z-index: 81;
    display: flex; flex-direction: column;
    background: var(--calm-surface-raised, var(--bg-card, #0c1118));
    border-left: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25)));
    box-shadow: -18px 0 48px -24px rgba(0, 0, 0, 0.7);
    color: var(--calm-ink, var(--text, #b8b098));
    font-family: var(--ff-system); overflow: hidden;
  }
  :global(html[data-motion='allow']) .sp-panel { animation: spSlide 160ms ease-out; }
  @keyframes spSlide { from { transform: translateX(12px); opacity: 0; } to { transform: none; opacity: 1; } }

  /* ---- header ------------------------------------------------------------- */
  .sp-head {
    flex: 0 0 auto; display: flex; align-items: flex-start; justify-content: space-between;
    gap: var(--space-4, 10px);
    padding: var(--space-5, 14px) var(--space-6, 22px) var(--space-4, 10px);
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
  }
  .sp-head__titlewrap { min-width: 0; }
  .sp-head__title {
    margin: 0; font-family: var(--font-h, var(--ff-system)); font-size: 18px;
    letter-spacing: 0.05em; text-transform: uppercase;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
  }
  .sp-head__sub { margin: 3px 0 0; font-size: 11px; letter-spacing: 0.04em; color: var(--calm-ink-quiet, var(--text-dim, #948870)); }
  .sp-beta {
    display: inline-block; margin-top: 8px;
    font-family: var(--font-d, var(--ff-mono)); font-size: 10px;
    letter-spacing: 0.04em; color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .sp-beta__mock { color: var(--badge-ar-fg, #d97706); font-weight: 700; }
  .sp-beta__live { color: var(--badge-decided-fg, #16a34a); font-weight: 700; }
  .sp-close {
    appearance: none; background: transparent;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-sharp, 2px); color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    width: 28px; height: 28px; line-height: 1; font-size: 14px; cursor: pointer; flex: 0 0 auto;
    display: inline-flex; align-items: center; justify-content: center;
    transition: color var(--t-calm, 180ms ease), border-color var(--t-calm, 180ms ease);
  }
  .sp-close:hover { color: var(--calm-accent, var(--accent, #f59e0b)); border-color: var(--calm-hairline-hi, var(--border-hi)); }

  /* ---- body --------------------------------------------------------------- */
  .sp-body {
    flex: 1 1 auto; overflow-y: auto;
    padding: var(--space-5, 14px) var(--space-6, 22px) var(--space-7, 36px);
    display: flex; flex-direction: column; gap: var(--space-6, 22px);
  }
  .sp-section { display: flex; flex-direction: column; gap: var(--space-3, 6px); }
  .sp-section__label {
    font-size: 13px; font-weight: 600; letter-spacing: 0.02em;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    display: flex; align-items: baseline; justify-content: space-between; gap: 10px;
  }
  .sp-section__hint { font-size: 11px; font-weight: 400; color: var(--calm-ink-quiet, var(--text-dim, #948870)); letter-spacing: 0.02em; }
  .sp-section__desc { margin: 0; font-size: 11px; line-height: var(--lh-body, 1.5); color: var(--calm-ink-quiet, var(--text-dim, #948870)); max-width: 52ch; }
  .sp-state { margin: 4px 0; font-size: 13px; font-style: italic; color: var(--calm-ink-quiet, var(--text-dim, #948870)); }

  /* ---- (1) the LOUD verdict header (M4 paired badge) ---------------------- */
  .sp-verdict {
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-soft, 4px);
    padding: 16px 18px; background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
    display: flex; flex-direction: column; gap: 8px;
  }
  .sp-verdict__caption { font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--calm-ink-quiet, var(--text-dim, #948870)); }
  .sp-vbadge {
    display: inline-flex; align-items: center; gap: 9px; align-self: flex-start;
    font-family: var(--ff-system); font-size: 14px; font-weight: 800; letter-spacing: 0.06em;
    text-transform: uppercase; padding: 8px 14px; border-radius: var(--radius-sharp, 2px); line-height: 1;
  }
  .sp-vbadge__dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; flex: 0 0 auto; }
  .sp-vbadge--pass { color: var(--badge-decided-fg, #16a34a); background: var(--badge-decided-bg, #dcfce7); border: 2px solid var(--badge-decided-border, #86efac); }
  .sp-vbadge--fail { color: var(--badge-blocked-fg, #dc2626); background: var(--badge-blocked-bg, #fee2e2); border: 2px solid var(--badge-blocked-border, #dc2626); }
  .sp-vbadge--none { color: var(--badge-obs-fg, #475569); background: var(--badge-obs-bg, #f1f5f9); border: 1px solid var(--badge-obs-border, #cbd5e1); font-weight: 700; }
  .sp-verdict__meta { font-family: var(--font-d, var(--ff-mono)); font-size: 11px; color: var(--calm-ink-quiet, var(--text-dim, #948870)); font-variant-numeric: tabular-nums; }

  /* ---- (2) ranked self-excluded session selector ------------------------- */
  .sp-selector { display: flex; flex-direction: column; gap: 7px; margin-top: 4px; }
  .sp-srow {
    appearance: none; text-align: left; cursor: pointer; width: 100%;
    display: grid; grid-template-columns: 1fr auto auto; gap: 2px 12px; align-items: center;
    background: var(--calm-surface-row, var(--bg-row, #0e141e));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-left: 3px solid transparent; border-radius: var(--radius-sharp, 2px);
    padding: 9px 12px; color: var(--calm-ink, var(--text, #b8b098)); font-family: var(--ff-system);
    transition: border-color var(--t-calm, 180ms ease), background var(--t-calm, 180ms ease);
  }
  .sp-srow:hover { background: var(--calm-surface-hover, var(--bg-row-hover, #131c2a)); }
  .sp-srow:focus-visible { outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid) var(--focus-ring-color, #d97706); outline-offset: var(--focus-ring-offset, 2px); }
  .sp-srow[aria-pressed='true'] { border-color: var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25))); background: var(--calm-surface-hover, var(--bg-row-hover, #131c2a)); }
  .sp-srow--top { border-left-color: var(--calm-accent, var(--accent, #f59e0b)); }
  .sp-srow__main { min-width: 0; display: flex; flex-direction: column; gap: 2px; grid-column: 1; }
  .sp-srow__slug { font-size: 13px; font-weight: 600; color: var(--calm-ink-loud, var(--text-bright, #e8e0cc)); letter-spacing: 0.01em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .sp-srow__toptag {
    display: inline-block; margin-left: 7px; font-size: 9px; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--calm-accent, var(--accent, #f59e0b));
    border: 1px solid var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25)));
    border-radius: 999px; padding: 1px 6px; vertical-align: middle;
  }
  .sp-srow__id { font-family: var(--font-d, var(--ff-mono)); font-size: 11px; color: var(--calm-ink-quiet, var(--text-dim, #948870)); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .sp-srow__busy { grid-column: 2; font-family: var(--font-d, var(--ff-mono)); font-size: 13px; font-variant-numeric: tabular-nums; color: var(--calm-accent, var(--accent, #f59e0b)); text-align: right; }
  .sp-srow__busy small { display: block; font-size: 9px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--calm-ink-quiet, var(--text-dim, #948870)); font-weight: 600; }
  .sp-srow__recency { grid-column: 3; font-family: var(--font-d, var(--ff-mono)); font-size: 11px; color: var(--calm-ink-quiet, var(--text-dim, #948870)); text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }

  /* visible self-exclude / firewall rejection footer (G1/G2). */
  .sp-excluded {
    margin-top: 9px; font-family: var(--font-d, var(--ff-mono)); font-size: 11px;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    display: flex; align-items: center; gap: 7px; flex-wrap: wrap;
    border-top: 1px dashed var(--calm-hairline, var(--border, #192030)); padding-top: 9px;
  }
  .sp-excluded__lead { letter-spacing: 0.04em; }
  .sp-excluded__tag {
    color: var(--badge-obs-fg, #475569); background: var(--badge-obs-bg, #f1f5f9);
    border: 1px solid var(--badge-obs-border, #cbd5e1); border-radius: 999px;
    padding: 2px 8px; font-size: 10px; letter-spacing: 0.04em; font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  /* ---- (3) the DEFERRED launch affordance (clearly non-functional) -------- */
  .sp-launch {
    border: 1px dashed var(--badge-ar-border, #d97706); border-radius: var(--radius-soft, 4px);
    padding: 12px 14px; background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
  }
  .sp-launch__btn {
    appearance: none; align-self: flex-start; cursor: not-allowed;
    background: transparent; color: var(--calm-ink-quiet, var(--text-dim, #948870));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030)); border-radius: 5px;
    font-family: var(--ff-system); font-size: 13px; font-weight: 600; letter-spacing: 0.02em;
    padding: 10px 16px; line-height: 1; opacity: 0.6;
  }
  .sp-launch__note { margin: 6px 0 0; font-size: 11px; line-height: var(--lh-body, 1.5); color: var(--calm-ink-quiet, var(--text-dim, #948870)); max-width: 52ch; }
  .sp-launch__tag {
    display: inline-block; margin-right: 7px; font-size: 9px; font-weight: 800; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--badge-ar-fg, #d97706);
    border: 1px solid var(--badge-ar-border, #d97706); border-radius: 999px; padding: 2px 7px;
  }
  .sp-launch__note code {
    font-family: var(--font-d, var(--ff-mono)); color: var(--calm-accent, var(--accent, #f59e0b));
    background: var(--calm-surface-row, var(--bg-row, #0e141e)); padding: 1px 5px; border-radius: 2px;
  }

  /* ---- (4) per-band report ----------------------------------------------- */
  .sp-runstate { margin-top: 2px; }
  .sp-statebadge {
    display: inline-flex; align-items: center; gap: 7px;
    font-size: 12px; font-weight: 700; letter-spacing: 0.07em; text-transform: uppercase;
    padding: 4px 10px; border-radius: var(--radius-sharp, 2px); line-height: 1;
  }
  .sp-statebadge__dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
  .sp-statebadge--inprogress { color: var(--badge-ar-fg, #d97706); background: var(--badge-ar-bg, #fef3c7); border: 1px solid var(--badge-ar-border, #d97706); }
  .sp-statebadge--complete { color: var(--badge-decided-fg, #16a34a); background: var(--badge-decided-bg, #dcfce7); border: 1px solid var(--badge-decided-border, #86efac); }
  .sp-statebadge--failed { color: var(--badge-blocked-fg, #dc2626); background: var(--badge-blocked-bg, #fee2e2); border: 2px solid var(--badge-blocked-border, #dc2626); }

  .sp-bands { width: 100%; border-collapse: collapse; font-family: var(--font-d, var(--ff-mono)); font-size: 12px; margin-top: 8px; }
  .sp-bands caption { text-align: left; font-family: var(--ff-system); font-size: 13px; font-weight: 600; color: var(--calm-ink-loud, var(--text-bright, #e8e0cc)); margin-bottom: 6px; }
  .sp-bands th, .sp-bands td { padding: 7px 10px; text-align: right; font-variant-numeric: tabular-nums; border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030)); }
  .sp-bands th { font-family: var(--ff-system); font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--calm-ink-quiet, var(--text-dim, #948870)); font-weight: 600; }
  .sp-bands th:first-child, .sp-bands td:first-child { text-align: left; color: var(--calm-ink-loud, var(--text-bright, #e8e0cc)); }
  .sp-bands tbody tr:nth-child(even) td { background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018)); }

  .sp-reportmd {
    margin-top: 8px; font-family: var(--font-d, var(--ff-mono)); font-size: 11px;
    color: var(--calm-ink-quiet, var(--text-dim, #948870)); line-height: 1.55;
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-sharp, 2px); padding: 10px 12px; white-space: pre-wrap;
    overflow-x: auto;
  }
  .sp-escalate {
    margin-top: 8px; border: 2px solid var(--badge-blocked-border, #dc2626); border-radius: var(--radius-soft, 4px);
    background: var(--badge-blocked-bg, #fee2e2); color: #7f1d1d; padding: 12px 14px; font-size: 12px; line-height: 1.5;
  }
  .sp-escalate b { color: var(--badge-blocked-fg, #dc2626); }

  /* visually-hidden live region for screen readers (M17). */
  .sp-sr-only {
    position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; border: 0;
    clip: rect(0 0 0 0); overflow: hidden; white-space: nowrap;
  }

  /* reduced motion (M17): suppress the slide-in unless force-allowed. */
  :global(html[data-motion='reduce']) .sp-panel,
  :global(html[data-motion='reduce']) .sp-trigger { transition: none; animation: none; }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .sp-panel { animation: none; }
    :global(html:not([data-motion='allow'])) .sp-trigger { transition: none; }
  }
</style>
