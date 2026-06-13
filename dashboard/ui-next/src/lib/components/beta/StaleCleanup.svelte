<!--
  StaleCleanup.svelte -- BETA feature "stale-cleanup" (#46):
  Operator-driven soft-delete + restore of stale (ended, quiet) sessions.

  WHAT IT DOES
    Over a multi-week soak the SessionRail accrues dead non-SM lanes -- ended
    sessions, crashed PIDs, one-off probe runs -- that crowd the calm rail and
    dilute the ACTIVE tally. The only cleanup today is a hand-written SQL DELETE
    against gov.db: irreversible and hostile to a glance-first operator. This
    feature reframes cleanup as "archive a drawer you can reopen", not surgery:
    a hairline "Archive stale" trigger in the rail footer opens a right-anchored
    PREVIEW modal that shows exactly what will be archived (paired tally +
    per-session list) BEFORE any commit. The operator drags an "older than"
    slider (the preview re-fetches live, debounced), then presses the one
    saturated CONFIRM ARCHIVE. Each archived row keeps a RESTORE button -- an
    over-cut costs one click. Soft-delete only (sets sessions.deleted_at); never
    a hard DELETE, so audit/forensic replay survives.

  BETA GATING (default OFF -- load-bearing). The ENTIRE body is wrapped in
  {#if enabled}. While $betaFlags["stale-cleanup"] is OFF the component renders
  NOTHING and registers NO poller / SSE handler / timer / fetch of its own. There
  is no background polling AT ALL: the preview is fetched on demand only when the
  operator opens the modal (and re-fetched, debounced, on a slider drag). Flag
  defaults OFF (lib/beta/registry.js); the operator flips it in
  Settings > BETA features ("Stale session cleanup").

  POLARITY (G2/M15): the preview fetch goes to the additive read endpoint
  GET /api/sessions/stale, which excludes SM-self (project_slug NOT IN the SM
  slug set AND id != SM_OWN_SESSION_ID) server-side. As defense-in-depth this
  component ALSO classifies any SM-self row (by project_slug / own session id)
  as state "self" -- never eligible, never counted, rendered as a dim
  "Self -- never governed" badge echoed in the footer. The archive POST refuses
  SM-self server-side (HTTP 400) so a self row can never be soft-deleted.

  ADR-18 MUST floor honoured here:
    - M1 3-frame presence: this is a rail-footer affordance + an overlay modal;
      it adds NO 4th frame and removes none. The three frames are untouched.
    - M2 escalation-only foreground: cleanup is operator-initiated only. The
      trigger raises no escalation, steals no focus, auto-fires nothing.
    - M4 paired label+color: EVERY state (Stale / Protected / Archived / Self)
      renders a LITERAL text label beside its color; the preview tally numbers
      always sit beside their literal unit label; color is never the sole signal.
    - Absolute HITL gate: a session with >=1 open HITL row is "Protected" --
      excluded from the count, cannot be archived, reason shown in prose.
    - M16 domain-agnostic: every session identity renders FROM DATA
      (project_slug / id). No monitored-project vocabulary is hard-coded.
    - M17 a11y AAA: the trigger + modal are real buttons; role="dialog"
      aria-modal with a focus trap, Escape-to-close, focus restored to the
      trigger on close; the tally is an aria-live region; full keyboard path.
    - M18: presentation-only; on-demand reads + operator-action POSTs, never on
      the verdict hot path, never opens /api/commands/stream.

  When live gov.db data is absent (fresh DB / fetch error) it falls back to a
  realistic, domain-agnostic mock fixture (StaleCleanup-data.mockSessions) so the
  feature is always testable headless (usedMockData=true, surfaced as a literal
  text label). On the mock path archive/restore are client-side only (no POST).

  All selectors are .sc-* scoped so this feature pollutes no shared class.
  Tokens come from theme.css (the calm-* / badge-* / focus-ring / spacing set).
  ASCII-only (cp1252-safe): dash is "--". No smart quotes, no em-dashes.
-->
<script>
  import { onDestroy, tick } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { readOwnSessionId } from '../../api.js';
  import { getStaleSessions, archiveSession, restoreSession } from '../../api.js';
  import {
    preview as computePreview,
    badgeFor,
    fmtNum,
    relWhen,
    mockSessions,
  } from './StaleCleanup-data.js';

  const FLAG_KEY = 'stale-cleanup';

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
  let busy = false; // a confirm/restore is in flight
  let windowHours = 24;
  /** @type {Array<Record<string, any>>} */
  let sessions = [];
  /** @type {Record<string, boolean>} id -> true once soft-deleted this pass */
  let archivedMap = {};
  let verb = 'Archive';
  let receipt = '';

  /** @type {HTMLElement|null} */
  let modalEl = null;
  /** @type {Element|null} */
  let lastFocused = null;
  /** @type {ReturnType<typeof setTimeout>|null} */
  let sliderTimer = null;

  // -- derived preview (pure; no DOM / no fetch) ------------------------------
  $: pv = enabled
    ? computePreview(sessions, windowHours, ownId(), archivedMap)
    : { rows: [], sessionCount: 0, messageCount: 0, decisionCount: 0, protectedCount: 0, shownCount: 0 };

  // The rail-footer trigger count: how many lanes are currently archivable. It
  // is also the gate for whether the trigger renders at all (hide when clean).
  $: staleCount = pv.sessionCount;
  $: showTrigger = enabled && (loading ? true : staleCount > 0 || open);

  // One-shot prime: when the feature is enabled, fetch the live stale preview
  // ONCE so the resting rail trigger reflects the real (or mock) count -- without
  // it the trigger can never appear (staleCount stays 0) and the feature is
  // unreachable. This is a single on-enable read, NOT a poller: there is no
  // interval/SSE; the only other fetches are the on-demand modal-open + slider.
  let _primed = false;
  $: if (enabled && !_primed && typeof window !== 'undefined') {
    _primed = true;
    fetchPreview();
  }

  // -- on-demand preview fetch (NO background poller) -------------------------
  // Fetch the live stale-session preview for the current window. Falls back to
  // the mock fixture on empty/error so the feature is always demonstrable.
  async function fetchPreview() {
    if (!enabled) return;
    loading = true;
    try {
      const data = await getStaleSessions({ older_than_hours: windowHours });
      const live = data && Array.isArray(data.sessions) ? data.sessions : [];
      if (data && data.own_session_id) ownSessionId = data.own_session_id;
      if (live.length > 0) {
        sessions = live;
        usedMockData = false;
      } else {
        sessions = mockSessions();
        usedMockData = true;
      }
    } catch {
      // Server down / fresh DB -- degrade to mock so the modal stays testable.
      sessions = mockSessions();
      usedMockData = true;
    } finally {
      loading = false;
    }
  }

  // -- modal open / close + focus trap ----------------------------------------
  async function openModal() {
    if (!enabled || open) return;
    lastFocused = typeof document !== 'undefined' ? document.activeElement : null;
    open = true;
    verb = 'Archive';
    receipt = '';
    archivedMap = {};
    await fetchPreview();
    await tick();
    const first = modalEl && modalEl.querySelector(
      'input, button:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    if (first && first.focus) first.focus();
  }

  function closeModal() {
    if (!open) return;
    open = false;
    busy = false;
    if (sliderTimer) { clearTimeout(sliderTimer); sliderTimer = null; }
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

  // -- slider: live re-preview (debounced like the mockup) --------------------
  function onSliderInput(e) {
    windowHours = Number(e.currentTarget.value) || 1;
    if (sliderTimer) clearTimeout(sliderTimer);
    // Re-fetch from the server (the window changes the eligible set). On the
    // mock path the pure preview already re-filters reactively, so a re-fetch
    // is harmless (it re-returns the mock). 120ms debounce mirrors the mockup.
    sliderTimer = setTimeout(() => { sliderTimer = null; fetchPreview(); }, 120);
  }

  // -- confirm = soft-delete every eligible row -------------------------------
  async function confirmArchive() {
    if (busy) return;
    const ids = pv.rows.filter((r) => r.eligible).map((r) => r.s.id);
    if (!ids.length) return;
    busy = true;
    const okIds = [];
    for (const id of ids) {
      if (usedMockData) {
        // mock path: client-side soft-delete only (no POST).
        okIds.push(id);
        continue;
      }
      try {
        await archiveSession(id);
        okIds.push(id);
      } catch {
        // Leave un-archived rows in place; partial success is honest.
      }
    }
    const next = { ...archivedMap };
    for (const id of okIds) next[id] = true;
    archivedMap = next;
    verb = 'Archived';
    receipt = okIds.length
      ? okIds.length + ' archived -- soft-deleted (deleted_at set); RESTORE retained per row.'
      : 'Nothing archived -- the server refused every row (self / protected).';
    busy = false;
  }

  // -- restore one soft-deleted row -------------------------------------------
  async function restoreOne(id, slug) {
    if (busy) return;
    busy = true;
    let ok = true;
    if (!usedMockData) {
      try { await restoreSession(id); } catch { ok = false; }
    }
    if (ok) {
      const next = { ...archivedMap };
      delete next[id];
      archivedMap = next;
      verb = 'Archive';
      receipt = 'Restored ' + (slug || id) + ' -- deleted_at cleared; lane returns to the rail.';
    } else {
      receipt = 'Restore failed for ' + (slug || id) + ' -- it stays archived.';
    }
    busy = false;
  }

  // -- BETA gate teardown: flag OFF (or destroy) closes the modal + clears the
  // debounce timer so nothing lingers. The {#if enabled} block unmounts the DOM;
  // this clears the side-channels. -------------------------------------------
  $: if (!enabled) teardown();
  function teardown() {
    if (sliderTimer) { clearTimeout(sliderTimer); sliderTimer = null; }
    if (open) { open = false; busy = false; }
  }
  onDestroy(teardown);
</script>

<!-- GATE: render absolutely nothing while OFF. No trigger, no modal, no fetch. -->
{#if enabled}
  <!-- The hairline rail-footer trigger. Mounts beneath the SessionRail in the
       left command-column; only renders while >=1 stale lane is archivable. -->
  {#if showTrigger}
    <div class="sc-foot">
      <span class="sc-self" title="StreamManager's own session is never eligible for cleanup">
        <span class="sc-self__dot" aria-hidden="true"></span>
        self excluded
      </span>
      <span class="sc-foot__spacer"></span>
      <button
        class="sc-trigger"
        type="button"
        aria-haspopup="dialog"
        aria-label={'Preview and archive ' + staleCount + ' stale session' + (staleCount === 1 ? '' : 's')}
        on:click={openModal}
      >
        Archive stale
        {#if !loading}<span class="sc-trigger__count">{staleCount}</span>{/if}
      </button>
    </div>
  {/if}

  {#if open}
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div class="sc-scrim" role="presentation" on:click={(e) => { if (e.target === e.currentTarget) closeModal(); }}></div>
    <div
      class="sc-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="sc-title"
      bind:this={modalEl}
      on:keydown={onModalKeydown}
    >
      <header class="sc-modal__head">
        <div class="sc-modal__head-row">
          <h2 id="sc-title" class="sc-modal__title">Archive stale sessions</h2>
          <button class="sc-modal__close" type="button" aria-label="Close cleanup preview (Esc)" on:click={closeModal}>
            <span aria-hidden="true">&times;</span>
          </button>
        </div>
        <span class="sc-modal__beta">
          BETA -- default OFF, toggled in Settings &gt; BETA features
          {#if usedMockData}<span class="sc-modal__mock"> -- SAMPLE DATA</span>{/if}
        </span>
      </header>

      <div class="sc-modal__body">
        <!-- window control: labelled slider, tabular-nums readout -->
        <div class="sc-field">
          <div class="sc-field__head">
            <label class="sc-field__label" for="sc-hours">Older than</label>
            <span class="sc-field__val"><span>{windowHours}</span> h</span>
          </div>
          <input
            id="sc-hours"
            class="sc-range"
            type="range"
            min="1"
            max="168"
            step="1"
            value={windowHours}
            aria-valuetext={windowHours + ' hours'}
            on:input={onSliderInput}
          />
          <p class="sc-field__desc">
            Sessions whose <code>ended_at</code> is older than this window are
            eligible. Drag to re-preview -- nothing is committed until you confirm.
          </p>
        </div>

        <!-- PREVIEW SUMMARY: one bold paired tally line (number never alone). -->
        <div class="sc-tally" aria-live="polite" data-testid="stale-cleanup-tally">
          <span class="sc-tally__verb">{verb}</span>
          <span class="sc-tally__seg"><span class="sc-tally__num">{pv.sessionCount}</span><span class="sc-tally__lbl">sessions</span></span>
          <span class="sc-tally__seg"><span class="sc-tally__num">{fmtNum(pv.messageCount)}</span><span class="sc-tally__lbl">msgs</span></span>
          <span class="sc-tally__seg"><span class="sc-tally__num">{fmtNum(pv.decisionCount)}</span><span class="sc-tally__lbl">decisions</span></span>
        </div>

        <!-- per-session list -->
        <div class="sc-list">
          <span class="sc-list__head">
            Matching sessions ({pv.shownCount} shown -- {pv.protectedCount} protected)
          </span>
          {#if loading}
            <p class="sc-list__state">Loading preview...</p>
          {:else if pv.rows.length === 0}
            <p class="sc-list__state">No stale sessions in this window. Still water.</p>
          {:else}
            {#each pv.rows as r (r.s.id)}
              {@const b = badgeFor(r.state)}
              <div class="sc-row" class:sc-row--protected={r.state === 'protected'}>
                <div class="sc-row__main">
                  <span class="sc-row__slug">{r.s.project_slug || r.s.id}</span>
                  <span class="sc-row__when">
                    {relWhen(r.s.ended_hours_ago)} // {fmtNum(r.s.message_count)} msgs, {fmtNum(r.s.decision_count)} decisions
                  </span>
                  {#if !r.eligible && r.reason}
                    <span class="sc-row__reason">{r.reason}</span>
                  {/if}
                </div>
                <span class="sc-row__spacer"></span>
                <span class="sc-badge sc-badge--{b.variant}" role="status" aria-label={b.label}>
                  <span class="sc-badge__dot" aria-hidden="true"></span>{b.label}
                </span>
                {#if r.archived}
                  <button
                    class="sc-restore"
                    type="button"
                    disabled={busy}
                    aria-label={'Restore session ' + (r.s.project_slug || r.s.id)}
                    on:click={() => restoreOne(r.s.id, r.s.project_slug)}
                  >Restore</button>
                {/if}
              </div>
            {/each}
          {/if}
        </div>

        {#if receipt}<p class="sc-receipt" role="status">{receipt}</p>{/if}
      </div>

      <footer class="sc-modal__foot">
        <span class="sc-modal__self" title="StreamManager's own session is never eligible for cleanup">
          <span class="sc-badge sc-badge--self"><span class="sc-badge__dot" aria-hidden="true"></span>Self -- never governed</span>
          {#if ownId()}<code>{ownId()}</code>{:else}<span class="sc-modal__self-note">self-filter from project_slug</span>{/if}
        </span>
        <div class="sc-actionbar">
          <span class="sc-actionbar__spacer"></span>
          <button class="sc-btn-cancel" type="button" on:click={closeModal}>Cancel</button>
          <button
            class="sc-btn-confirm"
            type="button"
            disabled={pv.sessionCount === 0 || busy}
            on:click={confirmArchive}
          >{busy ? 'Archiving...' : 'CONFIRM ARCHIVE'}</button>
        </div>
      </footer>
    </div>
  {/if}
{/if}

<style>
  /* ---- rail-footer trigger strip (mirrors SessionRail .rail__foot idiom) ---- */
  .sc-foot {
    display: flex;
    align-items: center;
    gap: var(--space-4, 10px);
    margin-top: var(--space-3, 6px);
    padding: var(--space-3, 6px) var(--space-5, 14px);
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-soft, 4px);
    background: var(--calm-surface, var(--bg, #080a0c));
  }
  .sc-self {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .sc-self__dot {
    width: 5px; height: 5px; border-radius: 50%;
    background: var(--calm-ink-quiet, var(--text-dim, #948870)); opacity: 0.7;
  }
  .sc-foot__spacer { flex: 1 1 auto; }

  .sc-trigger {
    appearance: none;
    display: inline-flex; align-items: center; gap: 6px;
    background: transparent;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase;
    padding: 3px 9px; border-radius: 999px; cursor: pointer;
    transition: color var(--t-calm, 180ms ease), border-color var(--t-calm, 180ms ease),
                background var(--t-calm, 180ms ease);
  }
  .sc-trigger:hover {
    color: var(--calm-accent, var(--accent, #f59e0b));
    border-color: var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25)));
    background: var(--calm-accent-wash, var(--accent-dim, rgba(245, 158, 11, 0.09)));
  }
  .sc-trigger__count {
    font-variant-numeric: tabular-nums;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
  }
  .sc-trigger:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid) var(--focus-ring-color, #d97706);
    outline-offset: var(--focus-ring-offset, 2px);
  }

  /* ---- modal scrim + right-anchored panel (SettingsDrawer dialog idiom) ---- */
  .sc-scrim {
    position: fixed; inset: 0; background: rgba(8, 10, 12, 0.55);
    backdrop-filter: blur(1px); z-index: 80;
  }
  .sc-modal {
    position: fixed; top: 0; right: 0; bottom: 0;
    width: min(460px, 94vw); z-index: 81;
    display: flex; flex-direction: column;
    background: var(--calm-surface-raised, var(--bg-card, #0c1118));
    border-left: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25)));
    box-shadow: -18px 0 48px -24px rgba(0, 0, 0, 0.7);
    color: var(--calm-ink, var(--text, #b8b098));
    font-family: var(--ff-system);
    overflow: hidden;
  }
  :global(html[data-motion='allow']) .sc-modal { animation: scSlide 160ms ease-out; }
  @keyframes scSlide { from { transform: translateX(12px); opacity: 0; } to { transform: none; opacity: 1; } }

  .sc-modal__head {
    flex: 0 0 auto;
    padding: var(--space-5, 14px) var(--space-6, 22px);
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
  }
  .sc-modal__head-row { display: flex; align-items: center; justify-content: space-between; gap: var(--space-4, 10px); }
  .sc-modal__title {
    margin: 0; font-family: var(--font-h, var(--ff-system)); font-size: 18px;
    letter-spacing: 0.04em; text-transform: uppercase;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
  }
  .sc-modal__close {
    appearance: none; background: transparent;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-sharp, 2px); color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    width: 28px; height: 28px; line-height: 1; font-size: 14px; cursor: pointer;
    display: inline-flex; align-items: center; justify-content: center;
    transition: color var(--t-calm, 180ms ease), border-color var(--t-calm, 180ms ease);
  }
  .sc-modal__close:hover { color: var(--calm-accent, var(--accent, #f59e0b)); border-color: var(--calm-hairline-hi, var(--border-hi)); }
  .sc-modal__beta {
    display: inline-block; margin-top: var(--space-3, 6px);
    font-family: var(--font-d, var(--ff-mono)); font-size: 10px;
    letter-spacing: 0.04em; color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .sc-modal__mock { color: var(--badge-ar-fg, #d97706); font-weight: 700; }

  .sc-modal__body {
    flex: 1 1 auto; overflow-y: auto;
    padding: var(--space-5, 14px) var(--space-6, 22px) var(--space-7, 36px);
    display: flex; flex-direction: column; gap: var(--space-6, 22px);
  }

  /* window control (slider) */
  .sc-field { display: flex; flex-direction: column; gap: var(--space-3, 6px); }
  .sc-field__head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--space-4, 10px); }
  .sc-field__label { font-size: 13px; font-weight: 600; letter-spacing: 0.02em; color: var(--calm-ink-loud, var(--text-bright, #e8e0cc)); }
  .sc-field__val { font-family: var(--font-d, var(--ff-mono)); font-size: 13px; font-variant-numeric: tabular-nums; color: var(--calm-accent, var(--accent, #f59e0b)); }
  .sc-range { width: 100%; margin: 4px 0 0; accent-color: var(--calm-accent, var(--accent, #f59e0b)); cursor: pointer; }
  .sc-field__desc { margin: 0; font-size: 11px; line-height: var(--lh-body, 1.5); color: var(--calm-ink-quiet, var(--text-dim, #948870)); max-width: 48ch; }
  .sc-field__desc code { font-family: var(--font-d, var(--ff-mono)); color: var(--calm-accent, var(--accent)); }

  /* preview tally -- one bold paired line (count never alone). */
  .sc-tally {
    display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-4, 10px);
    padding: var(--space-4, 10px) var(--space-5, 14px);
    border: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25)));
    border-radius: var(--radius-soft, 4px);
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
  }
  .sc-tally__verb { font-family: var(--font-d, var(--ff-mono)); font-size: 11px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: var(--calm-ink-loud, var(--text-bright, #e8e0cc)); }
  .sc-tally__seg { display: inline-flex; align-items: baseline; gap: 6px; }
  .sc-tally__num { font-family: var(--font-d, var(--ff-mono)); font-variant-numeric: tabular-nums; font-size: 22px; font-weight: 750; line-height: 1; color: var(--badge-ar-fg, #d97706); }
  .sc-tally__lbl { font-family: var(--font-d, var(--ff-mono)); font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--calm-ink-chrome, var(--text-ui, #8a8068)); }

  /* per-session list */
  .sc-list { display: flex; flex-direction: column; gap: var(--space-3, 6px); }
  .sc-list__head { font-family: var(--font-d, var(--ff-mono)); font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--calm-ink-chrome, var(--text-ui, #8a8068)); }
  .sc-list__state { margin: 4px 0; font-size: 13px; font-style: italic; color: var(--calm-ink-quiet, var(--text-dim, #948870)); }

  .sc-row {
    display: flex; align-items: center; gap: var(--space-3, 6px);
    padding: var(--space-3, 6px) var(--space-4, 10px);
    background: var(--calm-surface-row, var(--bg-row, #0e141e));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-sharp, 2px);
  }
  .sc-row--protected { border-color: var(--badge-ar-border, #d97706); }
  .sc-row__main { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .sc-row__slug { font-family: var(--font-d, var(--ff-mono)); font-size: 13px; color: var(--calm-ink-loud, var(--text-bright, #e8e0cc)); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .sc-row__when { font-family: var(--font-d, var(--ff-mono)); font-size: 10px; color: var(--calm-ink-quiet, var(--text-dim, #948870)); letter-spacing: 0.03em; }
  .sc-row__reason { font-family: var(--font-d, var(--ff-mono)); font-size: 10px; color: var(--badge-ar-fg, #d97706); margin-top: 2px; letter-spacing: 0.02em; }
  .sc-row__spacer { flex: 1 1 auto; }

  /* PAIRED label+color badges (M4) -- color is NEVER the sole signal. */
  .sc-badge {
    display: inline-flex; align-items: center; gap: 5px;
    font-family: var(--font-d, var(--ff-mono)); font-size: 10px; font-weight: 700;
    letter-spacing: 0.06em; text-transform: uppercase;
    padding: 2px 8px; border-radius: 999px; white-space: nowrap;
  }
  .sc-badge__dot { width: 6px; height: 6px; border-radius: 50%; flex: 0 0 auto; background: currentColor; }
  .sc-badge--stale { color: var(--badge-obs-fg, #475569); background: var(--badge-obs-bg, #f1f5f9); border: 1px solid var(--badge-obs-border, #cbd5e1); }
  .sc-badge--protected { color: var(--badge-ar-fg, #d97706); background: var(--badge-ar-bg, #fef3c7); border: 2px solid var(--badge-ar-border, #d97706); }
  .sc-badge--archived { color: var(--badge-decided-fg, #16a34a); background: var(--badge-decided-bg, #dcfce7); border: 1px solid var(--badge-decided-border, #86efac); }
  .sc-badge--self { color: var(--badge-obs-fg, #475569); background: transparent; border: 1px dashed var(--badge-obs-border, #cbd5e1); }
  .sc-badge--self .sc-badge__dot { background: var(--calm-ink-quiet, var(--text-dim, #948870)); opacity: 0.7; }

  .sc-restore {
    appearance: none; background: transparent;
    border: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25)));
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    font-family: var(--font-d, var(--ff-mono)); font-size: 10px; font-weight: 700;
    letter-spacing: 0.08em; text-transform: uppercase;
    padding: 4px 10px; border-radius: var(--radius-sharp, 2px); cursor: pointer;
    transition: color var(--t-calm, 180ms ease), border-color var(--t-calm, 180ms ease), background var(--t-calm, 180ms ease);
  }
  .sc-restore:hover:not(:disabled) {
    color: var(--calm-accent, var(--accent, #f59e0b));
    border-color: var(--calm-accent, var(--accent, #f59e0b));
    background: var(--calm-accent-wash, var(--accent-dim, rgba(245, 158, 11, 0.09)));
  }
  .sc-restore:disabled { opacity: 0.45; cursor: not-allowed; }

  .sc-receipt {
    margin: 0; font-family: var(--font-d, var(--ff-mono)); font-size: 13px;
    color: var(--badge-decided-fg, #16a34a); letter-spacing: 0.02em;
  }

  /* modal footer: self-exclude echo + action bar */
  .sc-modal__foot {
    flex: 0 0 auto;
    border-top: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    padding: var(--space-4, 10px) var(--space-6, 22px);
    display: flex; flex-direction: column; gap: var(--space-4, 10px);
    background: var(--calm-surface, var(--bg, #080a0c));
  }
  .sc-modal__self {
    display: inline-flex; align-items: center; gap: 6px;
    font-family: var(--font-d, var(--ff-mono)); font-size: 10px; letter-spacing: 0.04em;
    text-transform: uppercase; color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .sc-modal__self code { color: var(--calm-ink-quiet, var(--text-dim, #948870)); background: transparent; }
  .sc-modal__self-note { color: var(--calm-ink-quiet, var(--text-dim, #948870)); text-transform: none; letter-spacing: 0; }
  .sc-actionbar { display: flex; align-items: center; gap: var(--space-4, 10px); }
  .sc-actionbar__spacer { flex: 1 1 auto; }

  .sc-btn-cancel {
    appearance: none; background: transparent;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068)); font-family: var(--ff-system);
    font-size: 13px; font-weight: 600; letter-spacing: 0.04em;
    padding: var(--space-3, 6px) var(--space-5, 14px); border-radius: var(--radius-sharp, 2px); cursor: pointer;
    transition: color var(--t-calm, 180ms ease), border-color var(--t-calm, 180ms ease);
  }
  .sc-btn-cancel:hover { color: var(--calm-ink-loud, var(--text-bright, #e8e0cc)); border-color: var(--calm-hairline-hi, var(--border-hi)); }

  /* CONFIRM -- the ONLY saturated control. Deliberate accent, not destructive
     red: soft-delete is reversible, so the language is "archive", not "delete". */
  .sc-btn-confirm {
    appearance: none; background: var(--calm-accent, var(--accent, #f59e0b));
    border: var(--hairline, 1px) solid var(--calm-accent, var(--accent, #f59e0b));
    color: #1a1206; font-family: var(--ff-system);
    font-size: 13px; font-weight: 750; letter-spacing: 0.04em;
    padding: var(--space-3, 6px) var(--space-5, 14px); border-radius: var(--radius-sharp, 2px); cursor: pointer;
    transition: filter var(--t-calm, 180ms ease);
  }
  .sc-btn-confirm:hover:not(:disabled) { filter: brightness(1.08); }
  .sc-btn-confirm:disabled { opacity: 0.4; cursor: not-allowed; }

  /* shared focus-ring contract: 2px solid amber, 2px offset, every control. */
  .sc-range:focus-visible,
  .sc-restore:focus-visible,
  .sc-btn-cancel:focus-visible,
  .sc-btn-confirm:focus-visible,
  .sc-modal__close:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid) var(--focus-ring-color, #d97706);
    outline-offset: var(--focus-ring-offset, 2px);
  }

  /* reduced motion (M17): suppress the slide-in unless force-allowed. */
  :global(html[data-motion='reduce']) .sc-modal,
  :global(html[data-motion='reduce']) .sc-trigger { transition: none; animation: none; }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .sc-modal { animation: none; }
    :global(html:not([data-motion='allow'])) .sc-trigger { transition: none; }
  }
</style>
