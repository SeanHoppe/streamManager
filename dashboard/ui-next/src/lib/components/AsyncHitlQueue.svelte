<!--
  AsyncHitlQueue.svelte -- the ASYNC-mode HITL host inside Frame C.

  M5 names TWO HITL modes: SYNC (hold) and ASYNC (decide + annotate). This unit
  hosts the ASYNC half: the operator records a decision + annotation on a
  pending row WITHOUT holding the verdict. (The SYNC hold queue is a sibling
  surface; this queue is the async decide-and-annotate lane, mirroring the live
  dashboard #asyncHitlSection contract.)

  Ownership boundary (decomposition): this is a HOST. The actual per-row action
  UI (ranked APPROVE / OVERRIDE / DISMISS controls -- M6) is owned by
  u-hitl-core's row component. To stay file-disjoint AND build standalone, the
  row component is INJECTED via the `rowComponent` prop. When u-hitl-core is
  wired it passes its row component in; when this unit is built / tested in
  isolation a self-contained fallback annotate form is rendered that honors the
  exact POST /api/hitl/annotate contract. Either way the annotate transport is
  the single shared api.js wrapper.

  MUSTs this host carries / preserves:

    M5   ASYNC mode is one of exactly two modes. This queue renders ONLY in
         ASYNC mode (read from the settings store, never an "off" third state).
         In SYNC mode the queue host yields (the sibling SYNC surface owns the
         rows). Mode is switchable at runtime; this host reacts reactively.

    M8   The HITL gate is absolute. Learn-Mode bias renders ONLY as a dashed,
         NON-verdict informational chip ABOVE the action controls, titled
         "advisory only -- operator decision still required". It never bypasses
         the gate, never toasts, never offers undo. This host renders the chip
         slot; it never lets an advisory pre-select or auto-submit a decision.

    M9   Each pending row shows a 1s-tick countdown (default from the settings
         syncTimeoutSec, fallback 60s); on expiry the row dims (opacity .35 +
         grayscale) via the shared CountdownBar primitive. An expired row stays
         actionable in ASYNC (decide+annotate is post-hoc) but reads as lapsed.

    M4   Every status marker is a PAIRED label+color badge (OBSERVING while
         pending, DECIDED once annotated, TIMEOUT once the window lapses) --
         color is never the sole signal.

    M15/G2  Rows are scoped to the selected non-self session by the seed/SSE
         feed upstream; as defense-in-depth this host also drops any row whose
         session_id matches the SM own-session id when that id is known.

    M16  Domain-agnostic: every governed identifier (session_id, decision_id,
         action, content) is rendered FROM DATA. No monitored-project term is
         hard-coded; the override options are governance verdict names only.

    M18  Post-hoc observability. The annotate POST is an operator action, not a
         verdict on the hot path; nothing here gates a live decision.

  CALM-AMBIENT (winning spine): the queue is still water -- pending rows are
  calm slate with a quiet countdown lane. No row pulses (ASYNC is deliberate,
  not an alarm). Severity is type-weight, reinforced by the paired badge text.

  File-disjoint: depends only on theme/calm tokens, Badge.svelte + CountdownBar
  (shared primitives), the settings + session stores, and the api.js annotate
  wrapper. The row action UI is INJECTED, not imported, so no sibling file is
  referenced at module scope.
-->
<script>
  import { createEventDispatcher } from 'svelte';
  import Badge from './Badge.svelte';
  import CountdownBar from './CountdownBar.svelte';
  import { settings } from '../stores/settings.js';
  import { ownSessionId } from '../stores/session.js';
  import { postHitlAnnotate } from '../api.js';

  /**
   * rows: ASYNC pending rows (from u-hitl-core's pending seed / SSE, scoped to
   * the selected session). Each row carries at least:
   *   { pending_id|id, decision_id, session_id, action, content|message,
   *     confidence, reasoning, started_at, advisory? }
   * Rendered FROM DATA (M16). Empty by default so the host is calm standalone.
   * @type {Array<Record<string, any>>}
   */
  export let rows = [];

  /**
   * rowComponent: OPTIONAL injected u-hitl-core row component that renders the
   * ranked APPROVE / OVERRIDE / DISMISS action UI (M6). When provided we mount
   * it per row and forward the row data + an `annotate` event hook. When absent
   * we render the self-contained fallback annotate form below so this host is
   * functional in isolation. Dependency injection keeps us file-disjoint from
   * u-hitl-core.
   * @type {import('svelte').ComponentType|null}
   */
  export let rowComponent = null;

  /**
   * overrideOptions: the governance verdict names offered as override actions.
   * These are SM governance modes (M16: governance vocabulary, NOT
   * monitored-project terms). Mirrors the live dashboard async annotate tray.
   */
  export let overrideOptions = ['ALLOW', 'GUIDE', 'SUGGEST', 'INTERVENE', 'BLOCK'];

  const dispatch = createEventDispatcher();

  // ---- M5: render ONLY in ASYNC mode --------------------------------------
  // The settings store holds hitlMode 'sync' | 'async' (never 'off' -- coerced
  // upstream). In SYNC mode this host yields entirely; the sibling SYNC surface
  // owns the rows. Reactive => a runtime mode switch re-evaluates immediately.
  $: isAsync = $settings.hitlMode === 'async';

  // ---- M9: countdown duration from settings (fallback 60s) ----------------
  $: countdownSecs =
    Number.isFinite($settings.syncTimeoutSec) && $settings.syncTimeoutSec > 0
      ? $settings.syncTimeoutSec
      : 60;

  // ---- M15 defense-in-depth: drop SM own-session rows ----------------------
  $: own = $ownSessionId;
  $: visibleRows = (Array.isArray(rows) ? rows : []).filter(
    (r) => r && (!own || String(r.session_id) !== String(own)),
  );

  // ---- per-row local UI state ---------------------------------------------
  // Keyed by the row's stable id. Tracks the annotated/expired status WITHOUT
  // mutating the upstream row (the host is presentation + an operator action).
  /** @type {Record<string, { annotated?: boolean, expired?: boolean }>} */
  let rowState = {};

  function rid(r) {
    return String(r.pending_id ?? r.id ?? r.decision_id ?? '');
  }

  function statusOf(r) {
    const st = rowState[rid(r)] || {};
    if (st.annotated) return 'decided';
    if (st.expired) return 'timeout';
    return 'observing';
  }

  function markExpired(r) {
    const k = rid(r);
    rowState = { ...rowState, [k]: { ...(rowState[k] || {}), expired: true } };
  }

  // ---- M8: advisory chip text (dashed, NON-verdict, informational only) ----
  // The chip surfaces the Learn-Mode bias verbatim FROM DATA. It NEVER
  // pre-selects an override, never auto-submits, never toasts, never undoes.
  function advisoryOf(r) {
    if (!r) return '';
    // Repair (u-frameC BLOCKER): server returns bias_hint as a decoded object
    // ({category, confidence, ...}); read its category first so the M8 chip
    // populates. Keep string fallbacks for cassette/test shapes.
    const a = r.bias_hint?.category ?? r.advisory ?? r.learn_mode_advisory ?? r.advisory_hint ?? '';
    return typeof a === 'string' ? a.trim() : '';
  }

  // Repair (u-frameC BLOCKER): server /api/hitl/pending returns queued_at
  // (ISO-8601 string), not an epoch started_at. Normalize both to ms so the
  // M9 countdown anchors to the real queue time.
  function startedAtMs(r) {
    if (!r) return undefined;
    if (r.started_at != null) {
      const n = Number(r.started_at);
      return Number.isNaN(n) ? undefined : (n < 1e12 ? n * 1000 : n);
    }
    if (r.queued_at != null) {
      const t = Date.parse(r.queued_at);
      return Number.isNaN(t) ? undefined : t;
    }
    return undefined;
  }

  // ---- annotate transport (shared api.js; M16 governed ids from data) ------
  // Contract (server.py /api/hitl/annotate): { decision_id, override_action,
  // note }. decision_id + override_action are required non-empty strings; note
  // is string|null (server truncates to <=50 tokens). We surface failure to the
  // operator inline rather than swallowing it -- the gate is absolute (M8), so a
  // failed annotate must NOT read as a recorded decision.
  /** @type {Record<string, { busy?: boolean, error?: string }>} */
  let postState = {};

  async function submitAnnotate(r, overrideAction, note) {
    const k = rid(r);
    const decisionId = r.decision_id ?? r.id ?? '';
    if (!decisionId || !overrideAction) {
      postState = { ...postState, [k]: { error: 'decision id + action required' } };
      return;
    }
    postState = { ...postState, [k]: { busy: true } };
    try {
      await postHitlAnnotate({
        decision_id: String(decisionId),
        override_action: String(overrideAction),
        note: note && String(note).trim() ? String(note).trim() : null,
      });
      postState = { ...postState, [k]: {} };
      rowState = { ...rowState, [k]: { ...(rowState[k] || {}), annotated: true } };
      // Notify any parent (e.g. to refresh the pending seed) -- post-hoc only.
      dispatch('annotated', { decisionId: String(decisionId), overrideAction });
    } catch (err) {
      // M8: a failed annotate is NOT a decision. Surface the error; do not mark
      // the row decided, do not optimistically clear it.
      postState = {
        ...postState,
        [k]: { error: err && err.message ? err.message : 'annotate failed' },
      };
    }
  }

  // The fallback form's local field state (only used when rowComponent is null).
  /** @type {Record<string, { override?: string, note?: string }>} */
  let formState = {};
  function setOverride(r, v) {
    const k = rid(r);
    formState = { ...formState, [k]: { ...(formState[k] || {}), override: v } };
  }
  function setNote(r, v) {
    const k = rid(r);
    formState = { ...formState, [k]: { ...(formState[k] || {}), note: v } };
  }
  function onFallbackSubmit(r) {
    const k = rid(r);
    const fs = formState[k] || {};
    // Default the override to the original action when the operator keeps it.
    const override = fs.override || String(r.action || 'ALLOW');
    submitAnnotate(r, override, fs.note || '');
  }

  // Display name for a row's governed target, FROM DATA (M16).
  function rowLabel(r) {
    const sid = r && r.session_id != null ? String(r.session_id) : '';
    return sid ? shortId(sid) : 'session';
  }
  function shortId(id) {
    if (id.length <= 14) return id;
    return `${id.slice(0, 7)}...${id.slice(-4)}`;
  }
  function contentOf(r) {
    const c = r && (r.content ?? r.message ?? r.reasoning ?? '');
    return typeof c === 'string' ? c : '';
  }
</script>

{#if isAsync}
  <section class="aq" aria-label="Async HITL decide and annotate queue">
    <header class="aq__head">
      <h3 class="aq__title sev-base">Async HITL</h3>
      <span
        class="aq__count"
        data-count={visibleRows.length}
        title={`${visibleRows.length} async row${visibleRows.length === 1 ? '' : 's'} to decide and annotate`}
      >
        <span class="aq__count-tag">QUEUE</span>
        <span class="aq__count-num">{visibleRows.length}</span>
      </span>
    </header>

    {#if visibleRows.length === 0}
      <p class="aq__empty">Still water. No async decisions awaiting annotation.</p>
    {:else}
      <ul class="aq__list" role="list">
        {#each visibleRows as r (rid(r))}
          {@const status = statusOf(r)}
          {@const advisory = advisoryOf(r)}
          {@const ps = postState[rid(r)] || {}}
          <li
            class="aq__row"
            class:aq__row--decided={status === 'decided'}
            data-pending-id={rid(r)}
            data-session-id={r.session_id || ''}
            data-status={status}
          >
            <div class="aq__row-top">
              <div class="aq__id">
                <span class="aq__action sev-notice" title={`original verdict: ${r.action || '?'}`}>
                  {r.action || '?'}
                </span>
                <span class="aq__session sev-quiet" title={`session ${r.session_id || ''}`}>
                  {rowLabel(r)}
                </span>
              </div>

              <!-- M4 paired status badge: OBSERVING (pending) / DECIDED
                   (annotated) / TIMEOUT (window lapsed). Color is never alone. -->
              {#if status === 'decided'}
                <Badge variant="decided" reason="Decision annotated and recorded" />
              {:else if status === 'timeout'}
                <Badge variant="timeout" reason="HITL window lapsed -- annotate still permitted (async)" />
              {:else}
                <Badge variant="observing" reason="Awaiting operator decision -- async annotate" />
              {/if}
            </div>

            <!-- The message/content under review, FROM DATA (M16). -->
            {#if contentOf(r)}
              <p class="aq__content sev-base">{contentOf(r)}</p>
            {/if}

            <!-- M9: 1s-tick countdown; on expiry the row dims (opacity .35 +
                 grayscale handled by CountdownBar) and we flip the status to
                 TIMEOUT. dim=false here so the row stays operable in ASYNC; we
                 dim the row body ourselves only after expiry. -->
            <div class="aq__countdown" class:aq__countdown--expired={status === 'timeout'}>
              <CountdownBar
                seconds={countdownSecs}
                startedAt={startedAtMs(r)}
                running={status === 'observing'}
                dim={false}
                showReadout={true}
                label={`HITL window for ${rowLabel(r)}`}
                on:expired={() => markExpired(r)}
              />
            </div>

            <!-- M8: advisory chip ABOVE the action controls. Dashed, NON-verdict,
                 informational only. Renders ONLY when the row carries a
                 Learn-Mode bias; never pre-selects or auto-submits. -->
            {#if advisory}
              <div
                class="aq__advisory"
                role="note"
                title="advisory only -- operator decision still required"
                aria-label={`advisory only -- operator decision still required: ${advisory}`}
              >
                <span class="aq__advisory-tag" aria-hidden="true">advisory</span>
                <span class="aq__advisory-text">{advisory}</span>
              </div>
            {/if}

            <!-- Action UI: the INJECTED u-hitl-core row component (M6 ranked
                 APPROVE / OVERRIDE / DISMISS) when wired; else the
                 self-contained fallback annotate form. -->
            {#if rowComponent}
              <svelte:component
                this={rowComponent}
                row={r}
                {overrideOptions}
                on:annotate={(e) => submitAnnotate(r, e.detail?.overrideAction, e.detail?.note)}
              />
            {:else}
              <form
                class="aq__form"
                on:submit|preventDefault={() => onFallbackSubmit(r)}
                aria-label={`Annotate decision for ${rowLabel(r)}`}
              >
                <label class="aq__field">
                  <span class="aq__field-label">Override verdict</span>
                  <select
                    class="aq__select"
                    on:change={(e) => setOverride(r, e.currentTarget.value)}
                  >
                    <option value="">Keep {r.action || 'original'}</option>
                    {#each overrideOptions as opt}
                      <option value={opt}>{opt}</option>
                    {/each}
                  </select>
                </label>

                <label class="aq__field aq__field--note">
                  <span class="aq__field-label">Note (&le;50 tokens stored)</span>
                  <textarea
                    class="aq__note"
                    rows="2"
                    placeholder="Why this decision?"
                    on:input={(e) => setNote(r, e.currentTarget.value)}
                  ></textarea>
                </label>

                <div class="aq__form-actions">
                  <button
                    type="submit"
                    class="aq__btn aq__btn--primary"
                    disabled={ps.busy || status === 'decided'}
                    aria-label={`Record and annotate decision for ${rowLabel(r)}`}
                  >
                    {ps.busy ? 'Recording...' : status === 'decided' ? 'Annotated' : 'Decide + annotate'}
                  </button>
                </div>

                {#if ps.error}
                  <!-- M8: a failed annotate is surfaced, never silently treated
                       as a recorded decision. -->
                  <p class="aq__error" role="alert">Not recorded: {ps.error}</p>
                {/if}
              </form>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
  </section>
{/if}

<style>
  .aq {
    display: flex;
    flex-direction: column;
    gap: var(--space-4, 10px);
  }

  .aq__head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-4, 10px);
  }

  .aq__title {
    margin: 0;
    font-family: var(--font-h, var(--ff-system));
    font-size: var(--fs-body, 14px);
    letter-spacing: 0.02em;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
  }

  .aq__count {
    display: inline-flex;
    align-items: baseline;
    gap: var(--space-3, 6px);
    padding: var(--space-1, 2px) var(--space-4, 10px);
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: 999px;
    background: var(--calm-surface-raised, var(--bg-card, #0c1118));
  }
  .aq__count-tag {
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    letter-spacing: 0.13em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .aq__count-num {
    font-family: var(--font-d, var(--ff-mono));
    font-variant-numeric: tabular-nums;
    font-size: var(--fs-meta, 13px);
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
  }

  .aq__empty {
    margin: 0;
    padding: var(--space-5, 14px) var(--space-4, 10px);
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    font-size: var(--fs-meta, 13px);
    font-style: italic;
  }

  .aq__list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-4, 10px);
  }

  /* A calm pending card. Hairline edge, asymmetric left gutter (the bespoke
     non-template silhouette), still water at rest -- no pulse in ASYNC. */
  .aq__row {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 6px);
    padding: var(--space-4, 10px);
    background: var(--calm-surface-raised, var(--bg-card, #0c1118));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-left: 2px solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-soft, 4px);
    transition: opacity var(--t-calm, 180ms ease), border-color var(--t-calm, 180ms ease);
  }
  /* Once decided, the row settles: a quiet green-leaning left edge + recede. */
  .aq__row--decided {
    border-left-color: var(--c-allow, #22c55e);
    opacity: 0.85;
  }

  .aq__row-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4, 10px);
  }

  .aq__id {
    display: inline-flex;
    align-items: baseline;
    gap: var(--space-4, 10px);
    min-width: 0;
  }
  .aq__action {
    font-family: var(--font-d, var(--ff-mono));
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
  }
  .aq__session {
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .aq__content {
    margin: 0;
    color: var(--calm-ink, var(--text, #b8b098));
    line-height: var(--lh-body, 1.5);
    /* keep dense rows readable without dominating the card */
    display: -webkit-box;
    -webkit-line-clamp: 4;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .aq__countdown { width: 100%; }
  .aq__countdown--expired { /* the row reads lapsed; CountdownBar shows expired */ }

  /* M8 advisory chip: DASHED, non-verdict, informational. Visually distinct
     from any actionable control so it can never be mistaken for a decision. */
  .aq__advisory {
    display: flex;
    align-items: baseline;
    gap: var(--space-3, 6px);
    padding: var(--space-3, 6px) var(--space-4, 10px);
    border: 1px dashed var(--calm-accent, var(--accent, #f59e0b));
    border-radius: var(--radius-sharp, 2px);
    background: var(--calm-accent-wash, var(--accent-dim, rgba(245,158,11,0.09)));
  }
  .aq__advisory-tag {
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--calm-accent, var(--accent, #f59e0b));
    flex: 0 0 auto;
  }
  .aq__advisory-text {
    font-size: var(--fs-meta, 13px);
    color: var(--calm-ink, var(--text, #b8b098));
    font-style: italic;
  }

  /* Fallback annotate form (only when no u-hitl-core row component injected). */
  .aq__form {
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 6px);
  }
  .aq__field {
    display: flex;
    flex-direction: column;
    gap: var(--space-2, 4px);
  }
  .aq__field-label {
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .aq__select,
  .aq__note {
    font-family: var(--ff-system, system-ui, sans-serif);
    font-size: var(--fs-meta, 13px);
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    background: var(--calm-surface, var(--bg, #0b1120));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-sharp, 2px);
    padding: var(--space-3, 6px) var(--space-4, 10px);
  }
  .aq__note { resize: vertical; min-height: 2.4rem; line-height: var(--lh-body, 1.5); }

  .aq__form-actions {
    display: flex;
    gap: var(--space-3, 6px);
  }
  .aq__btn {
    appearance: none;
    font-family: var(--ff-system, system-ui, sans-serif);
    font-size: var(--fs-meta, 13px);
    font-weight: 600;
    line-height: 1;
    padding: 7px 12px;
    border-radius: var(--radius-sharp, 2px);
    cursor: pointer;
    transition: background var(--t-calm, 180ms ease), border-color var(--t-calm, 180ms ease),
      color var(--t-calm, 180ms ease);
  }
  .aq__btn--primary {
    background: var(--calm-accent, var(--accent, #f59e0b));
    color: #1a1206;
    border: 1px solid var(--calm-accent, var(--accent, #f59e0b));
  }
  .aq__btn--primary:hover:not(:disabled) { filter: brightness(1.08); }
  .aq__btn:disabled { opacity: 0.55; cursor: not-allowed; }

  .aq__error {
    margin: 0;
    font-size: var(--fs-chrome, 11px);
    color: var(--c-block, #ef4444);
    letter-spacing: 0.02em;
  }

  /* M17: 2px solid amber focus ring + 2px offset on every interactive element. */
  .aq__select:focus-visible,
  .aq__note:focus-visible,
  .aq__btn:focus-visible {
    outline: 2px solid var(--badge-ar-border, #d97706);
    outline-offset: 2px;
  }

  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .aq__row,
    :global(html:not([data-motion='allow'])) .aq__btn { transition: none; }
  }
</style>
