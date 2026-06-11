<!--
  HitlDock.svelte -- the HITL decision surface composition root (u-hitl-core).

  RESPONSIBILITY: this is the one place the HITL panes are assembled. It seeds
  the pending list from /api/hitl/pending, keeps it live via the named bus
  events (hitl_sync_queued / hitl_timeout), and renders -- per the active mode --
  either editable pending rows (HITL ON) or read-only rows (HITL OFF). It owns
  the mode toggle and the optimistic-resolve bookkeeping that the rows delegate
  to it.

  MUSTs assembled here (the leaf rows carry the per-row contract; the dock owns
  the seam):

    M5  HitlModeToggle is the SYNC/ASYNC switch (no off). The dock reflects the
        promoted mode and re-renders ON vs OFF rows accordingly. The server
        emits hitl_mode_promoted; the dock requests the switch via the toggle.

    M6  HITL ON -> HitlPendingRow renders APPROVE / OVERRIDE (RankedOptionList) /
        DISMISS; the row persists the pick keyed to message hash. The dock just
        supplies the envelope + session label (FROM DATA) and handles resolve.

    M7  HITL OFF -> HitlReadOnlyRow renders read-only + OBSERVING + Take action.
        The dock listens for `take-action`: it promotes that row to a pending
        ON row (surfacing the ranked list) once the session is flipped to SYNC.

    M8  AdvisoryChip is embedded by the rows (not the dock) ABOVE the actions.

    M9  CountdownBar lives in HitlPendingRow; on `expired` the dock keeps the row
        but the row dims + disables itself.

    M10 Optimistic resolve. On a row's `resolve` the dock filters it IMMEDIATELY
        from the pending list; on `resolve-failed` it silently restores the row
        to its prior position. No toast, no error chrome.

    M15 Self-exclude: the dock filters the SM's own session_id out of the seeded
        + streamed pending rows (defense-in-depth; the server already strips
        self). Empty/missing own id => no filtering (documented skip rule).

    M16 Domain-agnostic: the session label rendered for attribution comes from
        /api/sessions data (project_slug or raw id) via the session store -- the
        dock hard-codes NO monitored-project vocabulary.

    M18 Post-hoc: the dock seeds once via GET and otherwise lives off the SSE
        bus; its only mutations are the operator-initiated resolve / mode POSTs.
        It NEVER opens /api/commands/stream.

  CRAFT (calm-ambient spine, KingMode): the dock is still water with one
  leaning-forward lane. The pending count is a quiet paired badge; the rows
  stack with a tight, deliberate rhythm; the empty state is a calm "all clear",
  not a void. Only a pending ACTION REQUIRED row carries amber -- everything
  else defers.
-->
<script>
  import { onMount, onDestroy, createEventDispatcher } from 'svelte';
  import { get } from 'svelte/store';
  import Badge from './Badge.svelte';
  import HitlModeToggle from './HitlModeToggle.svelte';
  import HitlPendingRow from './HitlPendingRow.svelte';
  import HitlReadOnlyRow from './HitlReadOnlyRow.svelte';
  import { getHitlPending } from '../api.js';
  import { onBusEvent } from '../sse.js';
  import {
    selectedSessionId,
    selectedSession,
    getOwnSessionId,
    scopeParam,
  } from '../stores/session.js';
  import { settings } from '../stores/settings.js';

  /**
   * mode: the active HITL mode for the dock ('sync' | 'async'). Two-way bound so
   * the toggle and the settings store stay in sync. Initialised from the
   * settings store (which coerces to sync|async -- never off, M5).
   * @type {'sync'|'async'}
   */
  export let mode = get(settings).hitlMode;

  /**
   * hitlOn: whether the operator is in the editable HITL ON path. HITL ON is
   * the SYNC mode's holding behavior; ASYNC renders rows read-only until the
   * operator opts in (M7). We treat 'sync' as ON (the holding gate is live) and
   * 'async' as the read-only + opt-in surface. Per-row opt-in (M7) promotes a
   * single row to editable even while the dock is ASYNC.
   * @type {boolean}
   */
  $: hitlOn = mode === 'sync';

  // The default countdown duration (M9) flows from the settings store
  // (syncTimeoutSec), defaulting to 60s.
  let defaultSeconds = get(settings).syncTimeoutSec || 60;

  // -- Pending list state ----------------------------------------------------
  // Each entry is the raw /api/hitl/pending envelope. Self-excluded (M15).
  /** @type {Array<Record<string, any>>} */
  let pending = [];

  // Rows the operator has individually opted into editing while in ASYNC (M7):
  // a set of pending/decision ids promoted to the ON path.
  /** @type {Set<string|number>} */
  let promotedRows = new Set();

  // Snapshot used to silently restore an optimistically-resolved row on POST
  // failure (M10): maps pending_id -> { row, index }.
  /** @type {Map<string|number, { row:Record<string, any>, index:number }>} */
  const resolveBackups = new Map();

  let loading = true;
  let loadError = false;

  // -- Self-exclude (M15) ----------------------------------------------------
  /** @param {Record<string, any>} row */
  function isSelf(row) {
    const own = getOwnSessionId();
    return !!own && row && row.session_id === own;
  }
  /** @param {Array<Record<string, any>>} rows */
  function dropSelf(rows) {
    return (Array.isArray(rows) ? rows : []).filter((r) => !isSelf(r));
  }

  /**
   * Stable identity for a row (de-dupe + keying + M7 promotion set).
   * Repair (u-hitl-core M7 BLOCKER): resolution order MUST match
   * HitlReadOnlyRow's decisionId (id > decision_id > pending_id > message_hash
   * > matched_hash). Otherwise onTakeAction keys promotedRows under one id while
   * isPromoted() looks it up under another, and the per-row opt-in promotion is
   * silently lost. Server rows carry `id` (hp.id / decisions.id), so this is the
   * stable key on every path; the resolve path compares idOf===pendingId where
   * pendingId is likewise id-derived, so reordering is safe.
   */
  function idOf(row) {
    return row?.id ?? row?.decision_id ?? row?.pending_id ?? row?.message_hash ?? row?.matched_hash ?? null;
  }

  // -- Session-scope filter (mirrors the api session_id param) ---------------
  // The dock seeds with the scoped param; the streamed events are filtered to
  // the selected session too so the dock always matches the rest of the panes.
  $: scopedSessionId = $selectedSessionId; // null == ALL governed sessions
  /** @param {Record<string, any>} row */
  function inScope(row) {
    if (scopedSessionId == null) return true; // ALL
    return row && row.session_id === scopedSessionId;
  }

  // The governed-target label for attribution, rendered FROM DATA (M16): the
  // selected session's project_slug, falling back to the raw id. When ALL is
  // selected we resolve per-row below (the dock cannot label across sessions
  // from a single store value), so this is only the single-session convenience.
  $: activeSessionLabel = (() => {
    const s = $selectedSession;
    if (!s) return '';
    const slug = (s.project_slug ?? '').toString().trim();
    return slug !== '' ? slug : (s.id ?? '').toString();
  })();

  /**
   * Resolve a per-row attribution label FROM DATA (M16). When the dock is
   * scoped to a single session we reuse activeSessionLabel; otherwise we fall
   * back to the row's own session_id so attribution is never a hard-coded name.
   * @param {Record<string, any>} row
   */
  function labelFor(row) {
    if (scopedSessionId != null) return activeSessionLabel;
    return (row?.project_slug ?? row?.session_id ?? '').toString();
  }

  // The visible pending list = self-excluded + scope-filtered, newest first
  // (the server returns the envelope order; we trust it and only filter).
  $: visiblePending = pending.filter((r) => !isSelf(r) && inScope(r));

  // M3-at-dock-grain: the live open-ACTION-REQUIRED tally surfaced as a paired
  // count badge (M4). Only the editable (ON / promoted) rows are "action
  // required"; read-only OFF rows are observing, not pending action.
  $: actionCount = visiblePending.filter((r) => rowIsOn(r)).length;

  // M3 (shell-grain): emit the live open-action tally upward so the composing
  // App can thread it into the Frame A header pill + the browser-tab total. The
  // dock owns the HITL surface; the shell owns the aggregate M3 chrome. Emit
  // only on change so the parent never churns.
  const dispatch = createEventDispatcher();
  let _lastEmittedCount = -1;
  $: if (actionCount !== _lastEmittedCount) {
    _lastEmittedCount = actionCount;
    dispatch('actioncount', { frame: 'A', count: actionCount });
  }

  /** Is THIS row on the editable ON path (dock SYNC, or per-row opt-in)? (M7) */
  function rowIsOn(row) {
    if (hitlOn) return true;
    const id = idOf(row);
    return id != null && promotedRows.has(id);
  }
  // re-evaluate rowIsOn reactively when mode / promotions change
  $: _onDeps = [hitlOn, promotedRows];

  // -- Seed (M18: one GET) ---------------------------------------------------
  async function seed() {
    loading = true;
    loadError = false;
    try {
      const rows = await getHitlPending({ session_id: scopeParam() });
      pending = dropSelf(rows);
    } catch {
      // The dock degrades to an empty list rather than throwing; the operator
      // sees the calm "all clear" state, not an error wall.
      pending = [];
      loadError = true;
    } finally {
      loading = false;
    }
  }

  // Re-seed when the operator changes the session scope so the dock matches the
  // rest of the panes.
  let _lastScope = scopedSessionId;
  $: if (scopedSessionId !== _lastScope) {
    _lastScope = scopedSessionId;
    seed();
  }

  // -- Live updates via the named bus events (M18: off the hot path) ---------
  /** @type {Array<()=>void>} */
  let unsubs = [];

  /** A new SYNC-queued pending row arrived -- prepend it (self-excluded). */
  function onSyncQueued(payload) {
    if (!payload || isSelf(payload)) return; // M15
    const id = idOf(payload);
    // De-dupe: if a row with this id already exists, replace it in place.
    if (id != null && pending.some((r) => idOf(r) === id)) {
      pending = pending.map((r) => (idOf(r) === id ? { ...r, ...payload } : r));
    } else {
      pending = [payload, ...pending];
    }
  }

  /** A pending row timed out -- the row's own CountdownBar handles the visual;
   *  the bus event lets us reconcile if the server expires it server-side. We
   *  keep the row (dimmed) so the operator sees the timeout, matching the live
   *  dashboard. If the server signals removal we drop it. */
  function onTimeout(payload) {
    if (!payload) return;
    const id = idOf(payload);
    if (id == null) return;
    // Mark the row expired so the row dims itself (M9). We do not delete it --
    // the operator should see the TIMEOUT, consistent with the live contract.
    pending = pending.map((r) =>
      idOf(r) === id ? { ...r, _expired: true } : r,
    );
  }

  // -- Optimistic resolve plumbing (M10) -------------------------------------
  /** A row committed a resolution -> filter it IMMEDIATELY. */
  function onRowResolve(e) {
    const { pendingId } = e.detail;
    if (pendingId == null) return;
    const index = pending.findIndex((r) => idOf(r) === pendingId);
    if (index === -1) return;
    // Stash for a possible silent restore.
    resolveBackups.set(pendingId, { row: pending[index], index });
    pending = pending.filter((r) => idOf(r) !== pendingId);
    promotedRows.delete(pendingId);
    promotedRows = new Set(promotedRows);
  }

  /** The resolve POST succeeded -> drop the backup (no restore needed). */
  function onRowResolved(e) {
    resolveBackups.delete(e.detail.pendingId);
  }

  /** The resolve POST failed -> silently restore the row to its prior slot. */
  function onRowResolveFailed(e) {
    const { pendingId } = e.detail;
    const backup = resolveBackups.get(pendingId);
    if (!backup) return;
    resolveBackups.delete(pendingId);
    // Re-insert at (approximately) its original index so order is preserved.
    const next = pending.slice();
    const at = Math.min(backup.index, next.length);
    next.splice(at, 0, backup.row);
    pending = next;
  }

  /** A row fired `expired` -> mark it so it stays dimmed/disabled (M9). */
  function onRowExpired(e) {
    const id = e.detail.pendingId;
    if (id == null) return;
    pending = pending.map((r) => (idOf(r) === id ? { ...r, _expired: true } : r));
  }

  // -- M7: promote an OFF read-only row to the editable ON path --------------
  function onTakeAction(e) {
    const id = e.detail.decisionId;
    if (id == null) return;
    // The read-only row already flipped the session to SYNC + emitted
    // hitl_mode_promoted via the server. Reflect the promotion: surface the
    // ranked list for THIS row. If the whole dock is now SYNC we don't need the
    // per-row set, but we add it so the promotion survives a mode flip-back.
    promotedRows.add(id);
    promotedRows = new Set(promotedRows);
    // Mirror the dock mode to SYNC so the toggle + settings reflect the flip.
    mode = 'sync';
    settings.update((s) => ({ ...s, hitlMode: 'sync' }));
  }

  function onTakeActionFailed() {
    // The mode flip POST failed; the read-only row stays read-only. Nothing to
    // restore (we never optimistically promoted). No toast (M7).
  }

  // -- Mode toggle (M5) ------------------------------------------------------
  function onModePromoted(e) {
    // The toggle already POSTed + the server emitted hitl_mode_promoted. Mirror
    // the promoted mode into the settings store so the whole UI agrees.
    mode = e.detail.mode;
    settings.update((s) => ({ ...s, hitlMode: e.detail.mode }));
  }

  // Keep defaultSeconds + mode in sync if the settings panel changes them.
  let settingsUnsub;

  onMount(() => {
    seed();
    unsubs.push(onBusEvent('hitl_sync_queued', onSyncQueued));
    unsubs.push(onBusEvent('hitl_timeout', onTimeout));
    settingsUnsub = settings.subscribe((s) => {
      defaultSeconds = s.syncTimeoutSec || 60;
      // Reflect an external mode change (Settings panel) into the dock without
      // clobbering an in-progress per-row promotion.
      if (s.hitlMode && s.hitlMode !== mode) mode = s.hitlMode;
    });
  });

  onDestroy(() => {
    for (const u of unsubs) {
      try { u(); } catch { /* noop */ }
    }
    unsubs = [];
    settingsUnsub?.();
  });
</script>

<section class="dock" aria-label="HITL decisions" data-hitl-mode={mode}>
  <header class="dock__head">
    <div class="dock__title-wrap">
      <h2 class="dock__title sev-notice">HITL decisions</h2>
      {#if actionCount > 0}
        <!-- M4 paired label+count badge: the live open-ACTION-REQUIRED tally. -->
        <Badge
          variant="action-required"
          count={actionCount}
          reason={`${actionCount} HITL ${actionCount === 1 ? 'decision' : 'decisions'} awaiting operator action`}
        />
      {:else}
        <Badge variant="observing" reason="No HITL decisions awaiting action" />
      {/if}
    </div>

    <!-- M5: the SYNC/ASYNC runtime switch (no off). Bound to the active scope's
         session_id; inert when ALL is selected (cannot promote a mode against
         every session at once). -->
    <HitlModeToggle
      bind:mode
      sessionId={$selectedSessionId}
      on:promoted={onModePromoted}
    />
  </header>

  <div class="dock__body">
    {#if loading}
      <p class="dock__state sev-quiet">Loading HITL decisions...</p>
    {:else if visiblePending.length === 0}
      <!-- Calm "all clear" empty state -- not a void. -->
      <p class="dock__state sev-quiet">
        {loadError
          ? 'HITL feed unavailable -- monitoring continues.'
          : 'No HITL decisions awaiting action. Still water.'}
      </p>
    {:else}
      <ul class="dock__list" role="list">
        {#each visiblePending as row (idOf(row))}
          <li class="dock__row" role="listitem">
            {#if rowIsOn(row)}
              <!-- HITL ON (M6): editable pending row. -->
              <HitlPendingRow
                pending={row}
                sessionLabel={labelFor(row)}
                {defaultSeconds}
                on:resolve={onRowResolve}
                on:resolved={onRowResolved}
                on:resolve-failed={onRowResolveFailed}
                on:expired={onRowExpired}
              />
            {:else}
              <!-- HITL OFF (M7): read-only + OBSERVING + Take action. -->
              <HitlReadOnlyRow
                decision={row}
                sessionLabel={labelFor(row)}
                on:take-action={onTakeAction}
                on:take-action-failed={onTakeActionFailed}
              />
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
  </div>
</section>

<style>
  .dock {
    display: flex;
    flex-direction: column;
    gap: var(--space-4, 10px);
    min-width: 0;
    height: 100%;
    /* The dock is independently scrollable within its frame (M1 spirit at the
       pane grain) -- the body scrolls, the header stays pinned. */
    overflow: hidden;
  }

  .dock__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4, 10px);
    flex-wrap: wrap;
    flex: 0 0 auto;
    padding-bottom: var(--space-3, 6px);
    border-bottom: 1px solid var(--calm-hairline, #cbd5e1);
  }

  .dock__title-wrap {
    display: flex;
    align-items: center;
    gap: var(--space-4, 10px);
    min-width: 0;
  }

  .dock__title {
    margin: 0;
    font-family: var(--font-h, var(--ff-system, system-ui, sans-serif));
    font-size: 15px;
    letter-spacing: 0.04em;
    color: var(--calm-ink-loud, #e8e0cc);
  }

  .dock__body {
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
    /* Independent scroll lane -- a quiet, telemetry-grade scrollbar. */
    scrollbar-width: thin;
  }

  .dock__list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 6px);
  }
  .dock__row {
    min-width: 0;
  }

  .dock__state {
    margin: 0;
    padding: var(--space-5, 14px) var(--space-2, 4px);
    font-size: var(--fs-meta, 13px);
    color: var(--calm-ink-quiet, #64748b);
    font-style: italic;
  }
</style>
