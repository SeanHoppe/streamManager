<!--
  HitlBulkDismiss.svelte -- BETA feature #15 "hitl-bulk-dismiss".

  A focus-trapped triage modal that batch-resolves a backed-up async HITL queue
  in one sweep instead of row-by-row. It is the Svelte form of the operator-
  APPROVED KingMode mockup (reports/proposals/mockups/hitl-bulk-dismiss.html):
  a low-emphasis gear affordance in the HITL dock header, an Alt+D hotkey, three
  selection presets (all / older-than-N & below-confidence / by trigger reason),
  a confidence slider + age field, per-row checkboxes with a VISIBLE checked
  state, a standing DESTRUCTIVE warning (paired BLOCKED badge + literal prose),
  and an explicit CONFIRM that loops the EXISTING POST /api/hitl/resolve once per
  operator-selected row (resolution "dismissed").

  GATING (BETA, default OFF): the component renders NOTHING and registers NO
  pollers / SSE handlers / timers unless $betaFlags["hitl-bulk-dismiss"] is true.
  When OFF the gear vanishes, the global Alt+D listener is detached, and no fetch
  is ever issued. There is no background polling at all -- the pending list is
  fetched on demand only when the operator opens the modal.

  POLARITY (G2/M15): the on-demand fetch goes to the additive read endpoint
  GET /api/hitl/pending/triage, which excludes SM-self (project_slug NOT IN the
  SM slug set AND session_id != SM_OWN_SESSION_ID) server-side. The modal scopes
  to the operator-selected session_id; rows are NEVER implicitly select-all
  without a visible checked state on each row.

  SAFETY (ADR-18 MUST floor):
    - M4 paired label+color: every state (the destructive warning, the per-row
      action/trigger chips, the dock count, the committed toast) renders the
      LITERAL text state; color is never the sole signal.
    - Absolute HITL gate: no row is ever auto-dismissed. Every sweep needs an
      explicit CONFIRM press; Esc / Cancel close WITHOUT dismissing.
    - Domain-agnostic (M16): session label + trigger reasons render FROM DATA;
      no monitored-project vocabulary is hard-coded.
    - a11y (M17): role="dialog" aria-modal, focus trap, focus restore, a polite
      live region for the committed result, AAA-contrast tokens, full keyboard
      operability. ASCII-only (cp1252-safe): dash is "--".

  When live gov.db data is absent (empty endpoint / fetch error) the modal falls
  back to a small realistic mock set so the feature is always testable.
-->
<script>
  import { onMount, onDestroy, tick, createEventDispatcher } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { getHitlTriagePending, postHitlResolve } from '../../api.js';
  import { selectedSessionId, selectedSession } from '../../stores/session.js';

  const FLAG_KEY = 'hitl-bulk-dismiss';

  // The parent (the HITL dock host) can pass the count it is already showing so
  // the residual math is exact; absent that we derive a residual from the rows
  // we fetched. usedMockData is surfaced for the test harness.
  /** @type {number|null} */
  export let dockCount = null;

  const dispatch = createEventDispatcher();

  // -- gate (default OFF) -----------------------------------------------------
  // Reactive flag read. Everything below is a no-op while OFF: the gear is not
  // rendered, the Alt+D listener is detached, and no fetch/timer ever runs.
  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // -- state ------------------------------------------------------------------
  /** @type {Array<Record<string, any>>} */
  let rows = [];
  /** @type {Record<string|number, boolean>} */
  let checked = {};
  let open = false;
  let loading = false;
  let usedMockData = false;
  let busy = false; // a confirm sweep is in flight
  let liveStatus = '';

  // preset model (mirrors the approved mockup)
  let preset = 'age-conf'; // 'all' | 'age-conf' | 'reason'
  let confThreshold = 0.55;
  let ageSeconds = 120;
  /** @type {Record<string, boolean>} */
  let reasonOn = { low_confidence: false, desktop_pause: false, cross_session_flag: false };

  /** @type {HTMLElement|null} */
  let modalEl = null;
  /** @type {Element|null} */
  let lastFocused = null;

  // A fixed "now" captured when the modal opens so row ages are stable across a
  // single triage pass (no ticking timer -- still water, no background cost).
  let nowMs = Date.now();

  // -- realistic mock fallback (vetted mockDataSpec; mirrors the pending shape) -
  function mockRows() {
    const base = Date.parse('2026-06-11T09:16:42Z');
    nowMs = base;
    return [
      { id: 4101, proposed_action: 'BLOCK', proposed_confidence: 0.31, trigger_reason: 'low_confidence', queued_at: '2026-06-11T09:14:02Z', content: 'run the migration against prod now', session_id: 'sess-demo-7f3a', project_slug: 'demo-target' },
      { id: 4102, proposed_action: 'INTERVENE', proposed_confidence: 0.42, trigger_reason: 'desktop_pause', queued_at: '2026-06-11T09:14:48Z', content: 'force-push to the shared branch', session_id: 'sess-demo-7f3a', project_slug: 'demo-target' },
      { id: 4103, proposed_action: 'GUIDE', proposed_confidence: 0.27, trigger_reason: 'low_confidence', queued_at: '2026-06-11T09:15:10Z', content: 'rm -rf the build cache', session_id: 'sess-demo-7f3a', project_slug: 'demo-target' },
      { id: 4104, proposed_action: 'SUGGEST', proposed_confidence: 0.68, trigger_reason: 'cross_session_flag', queued_at: '2026-06-11T09:16:33Z', content: 'reuse the prior credential pattern', session_id: 'sess-demo-7f3a', project_slug: 'demo-target' },
    ];
  }

  // -- derived ----------------------------------------------------------------
  function ageSec(row) {
    const t = Date.parse(row && row.queued_at);
    if (!Number.isFinite(t)) return 0;
    return Math.max(0, Math.round((nowMs - t) / 1000));
  }
  function idOf(row) {
    return row && (row.id != null ? row.id : row.message_id != null ? row.message_id : null);
  }
  function conf(row) {
    const n = Number(row && row.proposed_confidence);
    return Number.isFinite(n) ? n : 0;
  }

  // trigger_reason -> paired badge variant + literal label (color never alone).
  function reasonBadge(r) {
    switch (r) {
      case 'low_confidence': return { variant: 'warn', label: 'WARN low confidence' };
      case 'desktop_pause': return { variant: 'observing', label: 'OBSERVING desktop pause' };
      case 'cross_session_flag': return { variant: 'warn', label: 'WARN cross-session flag' };
      case 'audit_probe': return { variant: 'observing', label: 'OBSERVING audit probe' };
      default: return { variant: 'observing', label: 'OBSERVING ' + String(r || 'pending') };
    }
  }
  function actionBadge(a) {
    if (a === 'BLOCK') return { variant: 'blocked', label: 'BLOCK' };
    if (a === 'INTERVENE') return { variant: 'warn', label: 'INTERVENE' };
    return { variant: 'observing', label: String(a || 'OBSERVE') };
  }

  // The scope label rendered FROM DATA (M16): the selected session's
  // project_slug, falling back to its id; "all sessions" when unscoped.
  $: scopeLabel = (() => {
    const s = $selectedSession;
    if (!s) return $selectedSessionId || 'all sessions';
    const slug = (s.project_slug || '').toString().trim();
    return slug !== '' ? slug : (s.id || '').toString();
  })();

  $: selectedIds = rows.filter((r) => checked[idOf(r)]).map((r) => idOf(r));
  $: selectedCount = selectedIds.length;
  // residual = the count the dock shows (live tally when supplied) minus the
  // rows this sweep will dismiss; falls back to the fetched-row count.
  $: visibleTotal = (dockCount != null && dockCount >= rows.length) ? dockCount : rows.length;
  $: residual = Math.max(0, visibleTotal - selectedCount);

  // The gear is only meaningful when there is a queue to triage. We learn the
  // queue depth from the dock count the parent threads down (no extra fetch);
  // when the parent supplies nothing we still show it (the modal self-fetches).
  $: hasQueue = dockCount == null ? true : dockCount > 0;

  // -- preset application -----------------------------------------------------
  // Recompute the checked set from the active preset. NEVER an implicit
  // select-all without a visible checked state: every checkbox reflects this map
  // and the operator can override any row by hand.
  function applyPreset() {
    const next = {};
    for (const r of rows) {
      const id = idOf(r);
      if (id == null) continue;
      let keep;
      if (preset === 'all') keep = true;
      else if (preset === 'reason') keep = !!reasonOn[r.trigger_reason];
      else keep = conf(r) < confThreshold && ageSec(r) > ageSeconds; // age-conf
      next[id] = keep;
    }
    checked = next;
  }
  $: presetLabel = preset === 'all' ? 'all pending' : preset === 'reason' ? 'by trigger reason' : 'older & low-confidence';

  function onPresetChange(value) {
    preset = value;
    applyPreset();
  }
  function onConfInput(e) {
    confThreshold = Number(e.currentTarget.value);
    if (preset === 'age-conf') applyPreset();
  }
  function onAgeInput(e) {
    ageSeconds = Number(e.currentTarget.value);
    if (preset === 'age-conf') applyPreset();
  }
  function onReasonToggle(key, e) {
    reasonOn = { ...reasonOn, [key]: !!e.currentTarget.checked };
    if (preset === 'reason') applyPreset();
  }
  function onRowToggle(id, e) {
    checked = { ...checked, [id]: !!e.currentTarget.checked };
  }

  // -- fetch (on demand only -- no background poller) -------------------------
  async function loadRows() {
    loading = true;
    usedMockData = false;
    try {
      const live = await getHitlTriagePending({ session_id: $selectedSessionId });
      if (Array.isArray(live) && live.length > 0) {
        rows = live;
        nowMs = Date.now();
      } else {
        rows = mockRows();
        usedMockData = true;
      }
    } catch {
      // Server down / empty DB -- degrade to mock so the modal stays testable.
      rows = mockRows();
      usedMockData = true;
    } finally {
      loading = false;
      applyPreset();
    }
  }

  // -- modal open / close + focus trap ----------------------------------------
  async function openModal() {
    if (!enabled) return; // gated: never opens while OFF
    if (open) return;
    lastFocused = typeof document !== 'undefined' ? document.activeElement : null;
    open = true;
    await loadRows();
    await tick();
    // focus the first interactive control (first row checkbox, else CONFIRM)
    const first = modalEl && modalEl.querySelector('input, button, [tabindex]:not([tabindex="-1"])');
    if (first && first.focus) first.focus();
  }
  function closeModal() {
    if (!open) return;
    open = false;
    busy = false;
    if (lastFocused && lastFocused.focus) lastFocused.focus();
  }
  function focusables() {
    if (!modalEl) return [];
    return Array.prototype.slice
      .call(modalEl.querySelectorAll('button, input, [tabindex]:not([tabindex="-1"])'))
      .filter((el) => !el.disabled && el.offsetParent !== null);
  }
  function onModalKeydown(e) {
    if (e.key === 'Escape') { e.preventDefault(); closeModal(); return; }
    if (e.key === 'Tab') {
      const f = focusables();
      if (!f.length) return;
      const firstEl = f[0];
      const lastEl = f[f.length - 1];
      if (e.shiftKey && document.activeElement === firstEl) { e.preventDefault(); lastEl.focus(); }
      else if (!e.shiftKey && document.activeElement === lastEl) { e.preventDefault(); firstEl.focus(); }
    }
  }

  // -- confirm = batch resolve (loop the EXISTING /api/hitl/resolve) ----------
  async function confirmSweep() {
    const ids = selectedIds.slice();
    if (!ids.length || busy) return;
    busy = true;
    const okIds = [];
    for (const id of ids) {
      // resolution "dismissed" is an existing _VALID_RESOLUTIONS member; the
      // server endpoint re-checks the row and dispatches via dispatch_resolution
      // (already polarity-safe). One POST per operator-selected row -- no new
      // endpoint, no new bus envelope, no FROZEN surface touched.
      try {
        await postHitlResolve({ pending_id: typeof id === 'number' ? id : Number(id), resolution: 'dismissed' });
        okIds.push(id);
      } catch {
        // Leave un-dismissed rows in place; partial success is honest.
      }
    }
    // Optimistic dock cull: drop the rows that resolved from our local list and
    // notify the parent so it can prune its own pending list + count.
    const sweptSet = new Set(okIds);
    rows = rows.filter((r) => !sweptSet.has(idOf(r)));
    const nextChecked = {};
    for (const r of rows) nextChecked[idOf(r)] = !!checked[idOf(r)];
    checked = nextChecked;
    dispatch('culled', { dismissedIds: okIds, count: okIds.length });
    liveStatus = 'Dismissed ' + okIds.length + ' row' + (okIds.length === 1 ? '' : 's') + '. ' + Math.max(0, visibleTotal - okIds.length) + ' remain.';
    busy = false;
    closeModal();
  }

  // -- global Alt+D (registered only while ON) --------------------------------
  function onGlobalKeydown(e) {
    if (!enabled) return; // gated
    if (e.altKey && (e.key === 'd' || e.key === 'D')) {
      e.preventDefault();
      if (open) closeModal(); else openModal();
    }
  }

  // Register the global hotkey only while ON; tear it down when OFF or unmounted
  // so an OFF flag leaves zero listeners (no runtime cost, BETA-gate contract).
  let _keyBound = false;
  function bindKey() {
    if (_keyBound || typeof window === 'undefined') return;
    window.addEventListener('keydown', onGlobalKeydown);
    _keyBound = true;
  }
  function unbindKey() {
    if (!_keyBound || typeof window === 'undefined') return;
    window.removeEventListener('keydown', onGlobalKeydown);
    _keyBound = false;
  }
  $: if (enabled) bindKey(); else { unbindKey(); if (open) closeModal(); }

  onMount(() => { if (enabled) bindKey(); });
  onDestroy(() => unbindKey());
</script>

<!-- GATE: render absolutely nothing while OFF. No gear, no modal, no listener. -->
{#if enabled}
  {#if hasQueue}
    <button
      class="bulk-btn"
      type="button"
      aria-haspopup="dialog"
      aria-label="Bulk dismiss pending HITL decisions (Alt plus D)"
      on:click={openModal}
    >
      <svg class="gear" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <circle cx="12" cy="12" r="3"></circle>
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
      </svg>
      Bulk dismiss
      <span class="bulk-btn__kbd" aria-hidden="true">Alt+D</span>
    </button>
  {/if}

  {#if open}
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div class="scrim" role="presentation" on:click={(e) => { if (e.target === e.currentTarget) closeModal(); }}>
      <div
        class="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="hbd-title"
        aria-describedby="hbd-warn"
        bind:this={modalEl}
        on:keydown={onModalKeydown}
      >
        <div class="modal__head">
          <div class="head-row">
            <h2 id="hbd-title" class="modal__title">Bulk-dismiss pending decisions</h2>
            <button class="modal__x" type="button" aria-label="Close without dismissing (Esc)" on:click={closeModal}>&times;</button>
          </div>
          <span class="modal__beta">
            BETA -- default OFF, toggled in Settings &gt; BETA features
            &nbsp; -- &nbsp; scope <span class="modal__scope">{scopeLabel}</span>
            {#if usedMockData}<span class="modal__mock"> -- DEMO DATA</span>{/if}
          </span>
        </div>

        <!-- standing DESTRUCTIVE warning: BLOCKED badge + literal prose (M4/M5). -->
        <div id="hbd-warn" class="warnline">
          <span class="ar-badge ar-blocked" role="status" title="Destructive action" aria-label="Destructive action">
            <span class="ar-dot" aria-hidden="true"></span><span>BLOCKED</span>
          </span>
          <span class="warnline__text">
            DESTRUCTIVE -- selected rows revert to decided / annotate-only. This
            cannot be undone by re-opening the dock.
          </span>
        </div>

        <div class="modal__body">
          <!-- LEFT RAIL: selectable rows -->
          <div class="rail">
            <div class="rail__head">
              <span class="rail__count"><b>{selectedCount}</b> of {rows.length} rows selected</span>
              <span class="rail__count">preset: <span class="rail__preset">{presetLabel}</span></span>
            </div>

            {#if loading}
              <p class="rail__state">Loading pending decisions...</p>
            {:else if rows.length === 0}
              <p class="rail__state">No pending decisions to triage. Still water.</p>
            {:else}
              <div class="rail__rows">
                {#each rows as row (idOf(row))}
                  {@const id = idOf(row)}
                  {@const rb = reasonBadge(row.trigger_reason)}
                  {@const ab = actionBadge(row.proposed_action)}
                  {@const on = !!checked[id]}
                  <div class="trow" class:is-unchecked={!on}>
                    <div class="trow__check">
                      <input
                        type="checkbox"
                        checked={on}
                        aria-label={'Select row ' + id + ': ' + (row.content || '')}
                        on:change={(e) => onRowToggle(id, e)}
                      />
                    </div>
                    <div class="trow__conf" title={'confidence ' + conf(row).toFixed(2)}>{conf(row).toFixed(2)}</div>
                    <div class="trow__main">
                      <div class="trow__line1">
                        <span class="ar-badge ar-{rb.variant}" role="status" title={rb.label} aria-label={rb.label}>
                          <span class="ar-dot" aria-hidden="true"></span><span>{rb.label}</span>
                        </span>
                        <span class="ar-badge ar-{ab.variant}" role="status" title={'proposed ' + ab.label} aria-label={'proposed ' + ab.label}>
                          <span class="ar-dot" aria-hidden="true"></span><span>{ab.label}</span>
                        </span>
                        <span class="trow__age">age {ageSec(row)}s -- id {id}</span>
                      </div>
                      <div class="trow__content" title={row.content || ''}>{row.content || ''}</div>
                    </div>
                  </div>
                {/each}
              </div>
            {/if}
          </div>

          <!-- RIGHT: preset column -->
          <div class="presets">
            <div class="presets__group" role="radiogroup" aria-label="Selection preset">
              <h3 class="presets__h">Preset</h3>
              <label class="radio">
                <input type="radio" name="hbd-preset" value="all" checked={preset === 'all'} on:change={() => onPresetChange('all')} />
                <span>All pending<small>check every visible row</small></span>
              </label>
              <label class="radio">
                <input type="radio" name="hbd-preset" value="age-conf" checked={preset === 'age-conf'} on:change={() => onPresetChange('age-conf')} />
                <span>Older-than-N &amp; below confidence<small>the cool-down sweep (default)</small></span>
              </label>
              <label class="radio">
                <input type="radio" name="hbd-preset" value="reason" checked={preset === 'reason'} on:change={() => onPresetChange('reason')} />
                <span>By trigger reason<small>pick reasons from the set below</small></span>
              </label>

              <div class="slider-wrap">
                <label for="hbd-conf">Confidence below <span class="slider-val">{confThreshold.toFixed(2)}</span></label>
                <input
                  id="hbd-conf"
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  value={confThreshold}
                  disabled={preset !== 'age-conf'}
                  aria-valuetext={'confidence ' + confThreshold.toFixed(2)}
                  on:input={onConfInput}
                />
              </div>
              <div class="age-wrap">
                <label for="hbd-age">Older than (seconds)</label>
                <input
                  id="hbd-age"
                  type="number"
                  min="0"
                  step="10"
                  value={ageSeconds}
                  disabled={preset !== 'age-conf'}
                  aria-label="Older than, seconds"
                  on:input={onAgeInput}
                />
              </div>
            </div>

            <div class="presets__group" aria-label="Trigger reasons" class:is-dim={preset !== 'reason'}>
              <h3 class="presets__h">Trigger reasons</h3>
              <label class="checkrow">
                <input type="checkbox" checked={reasonOn.low_confidence} disabled={preset !== 'reason'} on:change={(e) => onReasonToggle('low_confidence', e)} />
                low_confidence
              </label>
              <label class="checkrow">
                <input type="checkbox" checked={reasonOn.desktop_pause} disabled={preset !== 'reason'} on:change={(e) => onReasonToggle('desktop_pause', e)} />
                desktop_pause
              </label>
              <label class="checkrow">
                <input type="checkbox" checked={reasonOn.cross_session_flag} disabled={preset !== 'reason'} on:change={(e) => onReasonToggle('cross_session_flag', e)} />
                cross_session_flag
              </label>
            </div>
          </div>
        </div>

        <div class="modal__foot">
          <span class="modal__foot-info">
            <b>{selectedCount}</b> row{selectedCount === 1 ? '' : 's'} will be dismissed -- {residual} remain in the dock.
          </span>
          <span class="modal__foot-spacer"></span>
          <button class="modal__btn modal__btn--cancel" type="button" on:click={closeModal}>Cancel</button>
          <button
            class="modal__btn modal__btn--confirm"
            type="button"
            disabled={selectedCount === 0 || busy}
            on:click={confirmSweep}
          >
            {busy ? 'Dismissing...' : 'Confirm dismiss (' + selectedCount + ')'}
          </button>
        </div>
      </div>
    </div>
  {/if}

  <!-- polite live region: the committed result, reachable by assistive tech. -->
  <p class="sr-only" role="status" aria-live="polite">{liveStatus}</p>
{/if}

<style>
  /* gear "Bulk dismiss" affordance -- low emphasis (theme tokens only). */
  .bulk-btn {
    display: inline-flex; align-items: center; gap: 7px;
    font-family: var(--ff-system, system-ui, sans-serif);
    font-size: 12px; font-weight: 600; letter-spacing: 0.02em;
    color: var(--calm-ink-quiet, var(--text-dim)); background: transparent;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: 5px; padding: 6px 10px; cursor: pointer;
    transition: color var(--t-calm, 0.18s), border-color var(--t-calm, 0.18s), background var(--t-calm, 0.18s);
  }
  .bulk-btn:hover {
    color: var(--calm-ink-loud, var(--text-bright));
    border-color: var(--calm-hairline-hi, var(--border-hi));
    background: var(--calm-accent-wash, var(--accent-dim));
  }
  .bulk-btn:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid) var(--focus-ring-color, #d97706);
    outline-offset: var(--focus-ring-offset, 2px);
  }
  .bulk-btn__kbd {
    font-family: var(--font-d, var(--ff-mono)); font-size: 10.5px;
    color: var(--calm-ink-chrome, var(--text-ui));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: 3px; padding: 1px 5px; margin-left: 2px;
  }
  .gear { width: 14px; height: 14px; flex: 0 0 auto; }

  /* ---- modal scrim + shell ---- */
  .scrim {
    position: fixed; inset: 0; background: rgba(4, 6, 9, 0.72);
    display: flex; align-items: center; justify-content: center;
    padding: 24px; z-index: 50;
  }
  .modal {
    width: min(880px, 100%); max-height: calc(100vh - 48px); overflow: hidden;
    background: var(--calm-surface-card, var(--bg-card));
    border: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi));
    border-radius: 10px; box-shadow: 0 24px 64px rgba(0, 0, 0, 0.55);
    display: flex; flex-direction: column;
  }
  :global(html[data-motion='allow']) .modal { animation: hbdRise 140ms ease-out; }
  @keyframes hbdRise { from { transform: translateY(8px); opacity: 0; } to { transform: none; opacity: 1; } }

  .modal__head { padding: 18px 22px 14px; border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border)); }
  .head-row { display: flex; align-items: center; gap: 12px; }
  .modal__title { margin: 0; font-size: 16px; font-weight: 700; letter-spacing: 0.01em; color: var(--calm-ink-loud, var(--text-bright)); }
  .modal__beta { display: inline-block; margin-top: 6px; font-size: 11px; color: var(--calm-ink-quiet, var(--text-dim)); }
  .modal__scope { font-family: var(--font-d, var(--ff-mono)); color: var(--calm-accent, var(--accent)); }
  .modal__mock { font-family: var(--font-d, var(--ff-mono)); color: var(--badge-warn-fg, #ea580c); }
  .modal__x {
    margin-left: auto; background: transparent;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    color: var(--calm-ink-quiet, var(--text-dim));
    border-radius: 5px; width: 28px; height: 28px; cursor: pointer; font-size: 15px; line-height: 1;
  }

  .warnline {
    display: flex; align-items: center; gap: 11px; margin: 14px 22px 0; padding: 10px 12px;
    border: 2px solid var(--badge-blocked-border, #dc2626); border-radius: 6px;
    background: rgba(220, 38, 38, 0.06);
  }
  .warnline__text { font-size: 12.5px; color: var(--calm-ink-loud, var(--text-bright)); }

  .modal__body {
    display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(220px, 1fr);
    overflow: hidden; flex: 1 1 auto; min-height: 0;
  }
  @media (max-width: 720px) { .modal__body { grid-template-columns: 1fr; } }

  /* left rail */
  .rail { padding: 14px 18px 16px; overflow-y: auto; min-height: 0; }
  .rail__head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
  .rail__count { font-size: 12px; color: var(--calm-ink-quiet, var(--text-dim)); }
  .rail__count b { color: var(--calm-accent, var(--accent)); font-variant-numeric: tabular-nums; }
  .rail__preset { color: var(--calm-ink-loud, var(--text-bright)); }
  .rail__state { margin: 8px 0; font-size: 12.5px; font-style: italic; color: var(--calm-ink-quiet, var(--text-dim)); }
  .rail__rows { display: flex; flex-direction: column; }

  .trow {
    display: grid; grid-template-columns: auto auto 1fr; align-items: start; gap: 10px;
    padding: 10px 8px; border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
  }
  .trow:last-child { border-bottom: 0; }
  .trow__check { margin-top: 2px; }
  .trow__conf {
    font-family: var(--font-d, var(--ff-mono)); font-variant-numeric: tabular-nums;
    font-size: 13px; color: var(--calm-ink-loud, var(--text-bright)); min-width: 38px;
  }
  .trow__main { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
  .trow__line1 { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .trow__age {
    font-family: var(--font-d, var(--ff-mono)); font-size: 11px;
    color: var(--calm-ink-quiet, var(--text-dim)); font-variant-numeric: tabular-nums;
  }
  .trow__content {
    font-size: 13px; color: var(--calm-ink, var(--text));
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%;
  }
  .trow.is-unchecked { opacity: 0.55; }
  .trow.is-unchecked .trow__content { text-decoration: line-through; }

  /* right preset column */
  .presets {
    padding: 14px 18px 16px; border-left: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    background: var(--calm-surface-row-alt, var(--bg-row-alt)); overflow-y: auto; min-height: 0;
    display: flex; flex-direction: column; gap: 16px;
  }
  .presets__group.is-dim { opacity: 0.5; }
  .presets__h { margin: 0 0 8px; font-size: 10.5px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--calm-ink-chrome, var(--text-ui)); font-weight: 700; }
  .radio, .checkrow {
    display: flex; align-items: flex-start; gap: 8px; padding: 5px 0; cursor: pointer;
    font-size: 12.5px; color: var(--calm-ink, var(--text));
  }
  .radio input, .checkrow input, .trow__check input { accent-color: var(--calm-accent, var(--accent)); }
  .radio small { display: block; color: var(--calm-ink-quiet, var(--text-dim)); font-size: 11px; }
  .slider-wrap { margin-top: 10px; }
  .slider-wrap label, .age-wrap label { display: block; font-size: 11px; color: var(--calm-ink-quiet, var(--text-dim)); margin-bottom: 6px; }
  .slider-val { font-family: var(--font-d, var(--ff-mono)); color: var(--calm-ink-loud, var(--text-bright)); font-variant-numeric: tabular-nums; }
  input[type='range'] { width: 100%; accent-color: var(--calm-accent, var(--accent)); }
  .age-wrap { margin-top: 12px; }
  .age-wrap input[type='number'] {
    width: 86px; font-family: var(--font-d, var(--ff-mono));
    background: var(--calm-surface-row, var(--bg-row)); color: var(--calm-ink-loud, var(--text-bright));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border)); border-radius: 4px; padding: 4px 7px;
  }

  /* shared focus ring contract: 2px solid amber, 2px offset. */
  .trow__check input:focus-visible,
  .radio input:focus-visible,
  .checkrow input:focus-visible,
  input[type='range']:focus-visible,
  input[type='number']:focus-visible,
  .modal__btn:focus-visible,
  .modal__x:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid) var(--focus-ring-color, #d97706);
    outline-offset: var(--focus-ring-offset, 2px);
  }

  .modal__foot {
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    padding: 14px 22px; border-top: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
  }
  .modal__foot-info { color: var(--calm-ink-quiet, var(--text-dim)); font-size: 12px; }
  .modal__foot-info b { color: var(--calm-accent, var(--accent)); font-variant-numeric: tabular-nums; }
  .modal__foot-spacer { flex: 1 1 auto; }
  .modal__btn {
    font-size: 13px; font-weight: 600; letter-spacing: 0.02em; border-radius: 5px;
    padding: 8px 16px; cursor: pointer;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    background: transparent; color: var(--calm-ink-quiet, var(--text-dim));
  }
  .modal__btn--cancel:hover { color: var(--calm-ink-loud, var(--text-bright)); border-color: var(--calm-hairline-hi, var(--border-hi)); }
  .modal__btn--confirm {
    color: #1a1206; background: var(--calm-accent, var(--accent));
    border-color: var(--badge-ar-border, #d97706); font-weight: 700;
  }
  .modal__btn--confirm:hover:not(:disabled) { background: var(--calm-accent-hi, #ffb01f); }
  .modal__btn--confirm:disabled {
    background: var(--calm-surface-row-alt, var(--bg-row-alt)); color: var(--calm-ink-chrome, var(--text-ui));
    border-color: var(--calm-hairline, var(--border)); cursor: not-allowed;
  }

  /* ---- shared Badge primitive (mirrors Badge.svelte .ar-* classes) ---- */
  .ar-badge {
    display: inline-flex; align-items: center; gap: 5px;
    font-family: var(--ff-system, system-ui, sans-serif); font-size: 11px; font-weight: 600;
    letter-spacing: 0.08em; text-transform: uppercase; padding: 3px 8px;
    white-space: nowrap; border-radius: 2px; line-height: 1; vertical-align: middle;
  }
  .ar-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex: 0 0 auto; }
  .ar-blocked { color: var(--badge-blocked-fg, #dc2626); background: var(--badge-blocked-bg, #fee2e2); border: 2px solid var(--badge-blocked-border, #dc2626); font-weight: 700; }
  .ar-warn { color: #9a3412; background: var(--badge-warn-bg, #ffedd5); border: 1px dashed var(--badge-warn-border, #ea580c); }
  .ar-observing { color: var(--badge-obs-fg, #475569); background: var(--badge-obs-bg, #f1f5f9); border: 1px solid var(--badge-obs-border, #cbd5e1); }

  .sr-only {
    position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
    overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;
  }

  :global(html[data-motion='reduce']) .bulk-btn { transition: none; }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .modal { animation: none; }
    :global(html:not([data-motion='allow'])) .bulk-btn { transition: none; }
  }
</style>
