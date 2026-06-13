<!--
  HitlPendingRow.svelte -- the HITL-ON pending decision row.

  CONTRACT (inviolable MUSTs this row carries):

    M6  HITL ON = ranked options. A pending row renders three operator
        affordances: APPROVE / OVERRIDE / DISMISS. OVERRIDE expands a
        RankedOptionList (FR-UI-5 ranked list | free text). The operator's pick
        is persisted KEYED TO THE MESSAGE HASH for reinforcement -- so a
        recurring message pre-fills the prior choice. Persistence is best-effort
        localStorage (private-mode safe).

    M9  Countdown. The row embeds CountdownBar (u-badge), default 60s, 1s tick.
        On expiry the WHOLE row gets opacity .35 + grayscale (the live
        `.hitl-item.expired` treatment) and the action buttons disable -- an
        expired window can no longer be resolved from this row.

    M10 Optimistic resolve. On commit the row asks the parent to filter it out
        IMMEDIATELY (dispatch `resolve`), then POSTs /api/hitl/resolve
        {pending_id, resolution}. On error it asks the parent to silently
        restore the prior state (dispatch `resolve-failed`) -- no toast, no
        error chrome beyond restoring the row.

    M8  Advisory. When the envelope carries a Learn-Mode bias, AdvisoryChip
        renders it as a dashed NON-VERDICT chip ABOVE the action buttons. It is
        a hint only -- it pre-fills NOTHING that bypasses the gate, never toasts,
        never offers undo.

    M4  Every status indicator is a paired label+color Badge -- color alone is
        never a signal. The pending row carries an ACTION REQUIRED badge whose
        aria-label = the trigger reason.

    M15 Self-exclude is upstream (HitlDock filters the SM's own session before a
        row is ever constructed). This row renders governed-target identity
        (session label) FROM DATA only (M16) -- no hard-coded vocabulary.

    M18 Post-hoc: the only network call is the operator-initiated resolve POST.

  CRAFT (calm-ambient spine, KingMode): a pending row is the one place the
  monitor leans toward the operator. The ACTION REQUIRED badge + amber primary
  affordance draw the eye; everything else (metadata, advisory, countdown) stays
  whisper-quiet. The OVERRIDE expansion is a calm height reveal, not a flash.
-->
<script>
  import { createEventDispatcher } from 'svelte';
  import Badge from './Badge.svelte';
  import CountdownBar from './CountdownBar.svelte';
  import AdvisoryChip from './AdvisoryChip.svelte';
  import RankedOptionList, { FREE_TEXT_VALUE } from './RankedOptionList.svelte';
  import { postHitlResolve } from '../api.js';
  import { betaFlags } from '../stores/beta.js';
  import ConfidenceChip from './beta/ConfidenceChip.svelte';
  import OperatorCoPilotGestureMacros from './beta/OperatorCoPilotGestureMacros.svelte';

  /**
   * pending: one /api/hitl/pending envelope (rendered FROM DATA -- M16). Shape
   * (server-driven; fields tolerated as optional):
   *   { pending_id, message_hash|matched_hash, session_id, reason|reasoning,
   *     options|suggestions, advisory|learn_mode_bias, advisory_confidence,
   *     seconds|timeout_sec, started_at, action, layer, confidence }
   * @type {Record<string, any>}
   */
  export let pending = {};

  /**
   * sessionLabel: governed-target identity for attribution, rendered FROM DATA
   * (M16). Optional; absent => no attribution line (never an invented name).
   * @type {string}
   */
  export let sessionLabel = '';

  /**
   * defaultSeconds: countdown duration fallback when the envelope omits one.
   * Default 60s (M9). The settings unit's syncTimeoutSec flows in via the parent.
   * @type {number}
   */
  export let defaultSeconds = 60;

  const dispatch = createEventDispatcher();

  // -- Envelope field resolution (tolerant; domain-agnostic, M16) ------------
  $: pendingId = pending?.pending_id ?? pending?.id ?? null;
  // The message hash is the reinforcement key (M6). Accept either field name.
  $: messageHash =
    (pending?.message_hash ?? pending?.matched_hash ?? pending?.message_id ?? '')
      .toString()
      .trim();
  // Server /api/hitl/pending returns trigger_reason (not reason/reasoning).
  $: reasonText = (() => {
    const r = (pending?.trigger_reason ?? pending?.reason ?? pending?.reasoning ?? '')
      .toString().trim();
    return r !== '' ? r : 'Operator action required';
  })();
  // Repair (u-frameC BLOCKER): server returns bias_hint as a decoded OBJECT
  // ({category, confidence, ladder_step_suggestion, ...}), not a string field
  // named advisory. Read bias_hint.category first so the M8 advisory chip
  // actually populates; keep tolerant fallbacks for cassette/test shapes.
  $: advisoryBias = (
    pending?.bias_hint?.category ?? pending?.advisory ?? pending?.learn_mode_bias ?? pending?.bias ?? ''
  ).toString();
  $: advisoryConfidence =
    pending?.bias_hint?.confidence ?? pending?.advisory_confidence ?? pending?.bias_confidence ?? null;
  $: rankedOptions = Array.isArray(pending?.options)
    ? pending.options
    : Array.isArray(pending?.suggestions)
      ? pending.suggestions
      : [];
  $: seconds = Number(pending?.seconds ?? pending?.timeout_sec ?? defaultSeconds) || defaultSeconds;
  // Repair (u-frameC BLOCKER): server returns queued_at (ISO-8601 string), not
  // an epoch started_at. Parse it to ms so the M9 countdown anchors correctly.
  $: startedAt = (() => {
    if (pending?.started_at != null) {
      const n = Number(pending.started_at);
      return Number.isNaN(n) ? undefined : (n < 1e12 ? n * 1000 : n);
    }
    if (pending?.queued_at != null) {
      const t = Date.parse(pending.queued_at);
      return Number.isNaN(t) ? undefined : t;
    }
    return undefined;
  })();

  // Per-row radio group name so multiple expanded rows don't cross-bind.
  $: groupName = `sm-ranked-${pendingId ?? messageHash ?? 'row'}`;

  // -- Reinforcement persistence (M6): pick keyed to message hash -------------
  const LS_PICK_PREFIX = 'sm.next.hitlPick.';

  /** @param {string} hash */
  function loadPersistedPick(hash) {
    if (!hash || typeof localStorage === 'undefined') return null;
    try {
      const raw = localStorage.getItem(LS_PICK_PREFIX + hash);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }
  /** @param {string} hash @param {{mode:string, selected:string|null, freeText:string}} pick */
  function persistPick(hash, pick) {
    if (!hash || typeof localStorage === 'undefined') return;
    try {
      localStorage.setItem(LS_PICK_PREFIX + hash, JSON.stringify(pick));
    } catch {
      /* private-mode / quota -- non-fatal; reinforcement just won't persist */
    }
  }

  // Override picker state (two-way bound into RankedOptionList).
  let overrideOpen = false;
  let selectedOption = null;
  let freeText = '';
  let resolving = false; // in-flight guard for the resolve POST (M10)
  let expired = false;

  // Pre-fill from the persisted reinforcement pick when the hash resolves (M6).
  // Re-runs when the row is re-keyed to a different pending envelope.
  let _hydratedHash = null;
  $: if (messageHash && messageHash !== _hydratedHash) {
    _hydratedHash = messageHash;
    const prior = loadPersistedPick(messageHash);
    if (prior && prior.mode === 'override') {
      overrideOpen = true;
      selectedOption = prior.selected ?? null;
      freeText = typeof prior.freeText === 'string' ? prior.freeText : '';
    } else {
      overrideOpen = false;
      selectedOption = null;
      freeText = '';
    }
  }

  // The effective override resolution string the operator has assembled.
  $: overrideResolution =
    selectedOption === FREE_TEXT_VALUE ? freeText.trim() : (selectedOption ?? '');
  $: overrideComplete =
    selectedOption != null &&
    (selectedOption !== FREE_TEXT_VALUE || freeText.trim() !== '');

  // Actions disable once the window has expired (M9) or a resolve is in flight.
  $: actionsDisabled = expired || resolving || pendingId == null;

  function onExpired() {
    expired = true;
    // Tell the parent so it may dim/cull the row consistently with the live
    // `.hitl-item.expired` contract (the row also dims itself below, M9).
    dispatch('expired', { pendingId, sessionId: pending?.session_id ?? null });
  }

  function toggleOverride() {
    overrideOpen = !overrideOpen;
    if (overrideOpen && selectedOption == null) {
      // Default to the top-ranked option if any, so OVERRIDE is one click away.
      selectedOption = rankedOptions.length ? null : FREE_TEXT_VALUE;
    }
  }

  /**
   * Commit a resolution (M10 optimistic). disposition is the canonical
   * operator verdict ('approve' | 'override' | 'dismiss'); resolution is the
   * effective payload string (for override, the ranked pick / free text).
   * @param {'approve'|'override'|'dismiss'} disposition
   * @param {string} resolution
   */
  async function commit(disposition, resolution) {
    if (actionsDisabled) return;
    resolving = true;

    // Persist the operator's pick keyed to the message hash for reinforcement
    // (M6) BEFORE the optimistic cull, so the choice survives even if the row
    // is removed from the DOM the next instant.
    persistPick(messageHash, {
      mode: disposition,
      selected: selectedOption,
      freeText,
    });

    // M10: filter the row IMMEDIATELY. The parent removes it from the pending
    // list; we hand back enough to restore it on error.
    dispatch('resolve', { pendingId, disposition, resolution, pending });

    try {
      await postHitlResolve({
        pending_id: pendingId,
        resolution,
        // extra context the server tolerates; keeps the verdict attributable.
        disposition,
        message_hash: messageHash || undefined,
        session_id: pending?.session_id ?? undefined,
      });
      dispatch('resolved', { pendingId, disposition, resolution });
    } catch (err) {
      // M10: silently restore prior state. No toast, no error chrome -- the
      // parent re-inserts the row; we just clear the in-flight guard.
      dispatch('resolve-failed', { pendingId, disposition, resolution, pending, error: err });
    } finally {
      resolving = false;
    }
  }

  function onApprove() {
    // APPROVE = accept the governance verdict as-is. resolution echoes the
    // envelope's own action so the executor applies the original disposition.
    commit('approve', (pending?.action ?? 'approve').toString());
  }
  function onOverride() {
    if (!overrideComplete) {
      // Surface the picker if the operator hit OVERRIDE before choosing.
      overrideOpen = true;
      return;
    }
    commit('override', overrideResolution);
  }
  function onDismiss() {
    commit('dismiss', 'dismiss');
  }

  function onRankChange(e) {
    // Keep local bindings in sync (RankedOptionList is controlled).
    selectedOption = e.detail.selected;
  }
</script>

<article
  class="hpr"
  class:hpr--expired={expired}
  data-pending-id={pendingId ?? ''}
  data-hitl-mode="on"
>
  <!-- HEADER: paired ACTION REQUIRED badge (M4) + governed-target attribution
       rendered FROM DATA (M16). The badge's aria-label = the trigger reason. -->
  <header class="hpr__head">
    <Badge variant="action-required" reason={reasonText} />
    {#if sessionLabel}
      <span class="hpr__attr" title={sessionLabel}>
        <span class="hpr__attr-tag" aria-hidden="true">session</span>
        <span class="hpr__attr-val">{sessionLabel}</span>
      </span>
    {/if}
  </header>

  <!-- The trigger reason as real prose -- the operator-facing "why". -->
  <p class="hpr__reason sev-base">{reasonText}</p>

  <!-- M9: the countdown bar. On expiry it fires `expired`; the whole row dims
       via .hpr--expired (opacity .35 + grayscale). -->
  <div class="hpr__countdown">
    <CountdownBar
      {seconds}
      {startedAt}
      running={!expired && !resolving}
      dim={false}
      showReadout={true}
      label={`HITL countdown -- ${reasonText}`}
      on:expired={onExpired}
    />
  </div>

  <!-- M8: Learn-Mode advisory chip ABOVE the action buttons. Non-verdict,
       dashed, never bypasses the gate. Renders only when a bias is present. -->
  <AdvisoryChip bias={advisoryBias} confidence={advisoryConfidence} />

  {#if $betaFlags['operator-co-pilot-gesture-macros']}
    <!-- BETA #17: ranked one-tap macro palette. APPROVE routes the row's
         EXISTING commit path; TUNE/ESCALATE pre-stage the OVERRIDE picker;
         SNOOZE dims client-side. Never opens the network, never auto-acts.
         Renders IN PLACE of the #18 ConfidenceChip (never both at once). -->
    <OperatorCoPilotGestureMacros
      {pending}
      disabled={actionsDisabled}
      onApprove={commit}
      onTune={() => { if (!overrideOpen) toggleOverride(); }}
      onEscalate={() => { if (!overrideOpen) toggleOverride(); }}
      onSnooze={() => { dispatch('expired', { pendingId, sessionId: pending?.session_id ?? null }); }}
      onDissent={() => { if (!overrideOpen) toggleOverride(); }}
    />
  {:else if $betaFlags['confidence-chip']}
    <!-- BETA #18: advisory co-pilot confidence chip. Reuses the row's existing
         commit/override path; never opens the network, never auto-acts. -->
    <ConfidenceChip
      {pending}
      disabled={actionsDisabled}
      onAccept={commit}
      onDissent={() => { if (!overrideOpen) toggleOverride(); }}
    />
  {/if}

  <!-- M6: OVERRIDE ranked picker (revealed). FR-UI-5 ranked list | free text. -->
  {#if overrideOpen}
    <div class="hpr__override">
      <RankedOptionList
        options={rankedOptions}
        bind:selected={selectedOption}
        bind:freeText
        {groupName}
        disabled={actionsDisabled}
        on:change={onRankChange}
      />
    </div>
  {/if}

  <!-- M6: APPROVE / OVERRIDE / DISMISS. The amber primary is the calm spine's
       one leaning-forward affordance; override + dismiss stay quiet. -->
  <div class="hpr__actions" role="group" aria-label="HITL decision">
    <button
      type="button"
      class="hpr__btn hpr__btn--approve"
      on:click={onApprove}
      disabled={actionsDisabled}
      aria-label={`Approve: ${reasonText}`}
    >
      Approve
    </button>

    <button
      type="button"
      class="hpr__btn hpr__btn--override"
      class:is-open={overrideOpen}
      on:click={overrideOpen ? onOverride : toggleOverride}
      disabled={actionsDisabled}
      aria-expanded={overrideOpen}
      aria-label={overrideOpen ? `Commit override: ${reasonText}` : `Override: ${reasonText}`}
    >
      {overrideOpen ? 'Commit override' : 'Override'}
    </button>

    {#if overrideOpen}
      <button
        type="button"
        class="hpr__btn hpr__btn--ghost"
        on:click={toggleOverride}
        disabled={actionsDisabled}
        aria-label="Cancel override"
      >
        Cancel
      </button>
    {/if}

    <button
      type="button"
      class="hpr__btn hpr__btn--ghost"
      on:click={onDismiss}
      disabled={actionsDisabled}
      aria-label={`Dismiss: ${reasonText}`}
    >
      Dismiss
    </button>
  </div>
</article>

<style>
  .hpr {
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 6px);
    padding: var(--space-4, 10px) var(--space-5, 14px);
    background: var(--calm-surface-row, #0e141e);
    border: 1px solid var(--calm-hairline, #cbd5e1);
    /* Asymmetric amber left rail: the one place the monitor leans toward the
       operator. Decorative reinforcement; the ACTION REQUIRED text is the real
       signal (M4). */
    border-left: 3px solid var(--badge-ar-border, #d97706);
    border-radius: var(--radius-soft, 4px);
  }

  /* M9 expiry: opacity .35 + grayscale on the WHOLE row. Mirrors the live
     `.hitl-item.expired` rule. A calm fade, not a snap. */
  .hpr--expired {
    opacity: 0.35;
    filter: grayscale(0.6);
    transition: opacity var(--t-calm, 180ms ease), filter var(--t-calm, 180ms ease);
  }

  .hpr__head {
    display: flex;
    align-items: center;
    gap: var(--space-4, 10px);
    flex-wrap: wrap;
    min-width: 0;
  }

  .hpr__attr {
    display: inline-flex;
    align-items: baseline;
    gap: var(--space-2, 4px);
    min-width: 0;
  }
  .hpr__attr-tag {
    font-size: var(--fs-chrome, 11px);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--calm-ink-quiet, #64748b);
  }
  .hpr__attr-val {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: var(--fs-chrome, 11px);
    color: var(--calm-ink-chrome, #8a8068);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 24ch;
  }

  .hpr__reason {
    margin: 0;
    font-family: var(--ff-system, system-ui, sans-serif);
    font-size: var(--fs-body, 14px);
    line-height: var(--lh-body, 1.5);
    color: var(--calm-ink, #b8b098);
    overflow-wrap: anywhere;
  }

  .hpr__countdown {
    width: 100%;
  }

  .hpr__override {
    width: 100%;
  }

  .hpr__actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3, 6px);
    margin-top: var(--space-1, 2px);
  }

  .hpr__btn {
    appearance: none;
    font-family: var(--ff-system, system-ui, sans-serif);
    font-size: var(--fs-meta, 13px);
    font-weight: 600;
    line-height: 1;
    padding: 7px 14px;
    border-radius: var(--radius-sharp, 2px);
    cursor: pointer;
    transition: background var(--t-calm, 180ms ease), border-color var(--t-calm, 180ms ease),
      color var(--t-calm, 180ms ease);
  }
  .hpr__btn:disabled {
    cursor: default;
    opacity: 0.5;
  }

  /* APPROVE -- the amber primary affordance (the one leaning-forward surface). */
  .hpr__btn--approve {
    background: var(--badge-ar-border, #d97706);
    color: #fffbeb;
    border: 1px solid #b45309;
  }
  .hpr__btn--approve:hover:not(:disabled) {
    background: #b45309;
  }

  /* OVERRIDE -- quiet outline; gains an accent edge when its picker is open. */
  .hpr__btn--override {
    background: transparent;
    color: var(--calm-ink, #b8b098);
    border: 1px solid var(--calm-hairline, #cbd5e1);
  }
  .hpr__btn--override:hover:not(:disabled) {
    border-color: var(--calm-accent, #d97706);
    color: var(--calm-ink-loud, #e8e0cc);
  }
  .hpr__btn--override.is-open {
    border-color: var(--calm-accent, #d97706);
    color: var(--calm-accent, #d97706);
    font-weight: 700;
  }

  /* DISMISS / Cancel -- the quietest affordances. */
  .hpr__btn--ghost {
    background: transparent;
    color: var(--calm-ink-quiet, #64748b);
    border: 1px solid transparent;
  }
  .hpr__btn--ghost:hover:not(:disabled) {
    color: var(--calm-ink, #b8b098);
    border-color: var(--calm-hairline, #cbd5e1);
  }
</style>
