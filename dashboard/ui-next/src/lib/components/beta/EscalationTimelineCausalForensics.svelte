<!--
  EscalationTimelineCausalForensics.svelte -- BETA feature
  "escalation-timeline-causal-forensics" (#13: Escalation Timeline -- forensic
  causal-chain visibility for governance decisions).

  WHAT IT IS (the operator-APPROVED mockup, realised):
    At REST it is ONE calm amber paired "N escalations" badge + a gear in the
    Frame C header gutter -- nothing else. Click the badge / gear (or press
    Enter/Space) and a vertical wall-clock SPINE of escalation nodes slides into
    Frame C's RIGHT inset (newest at top). Click a node and a two-column overlay
    scoped INSIDE Frame C opens:
      LEFT  = DecisionDiff   -- matched message content + proposed-action badge +
                                confidence value + proportional bar.
      RIGHT = causal context -- 5 prior + the focus + 3 next compressed decision
                                rows, plus the agents-in-window chips.
    Dismiss acks the node (self-prunes to a struck hairline) and writes the
    additive escalation_dismissals table only -- never a decisions row.

  ============================ GOVERNANCE FLOOR ============================
  BETA GATE (load-bearing): the component renders NOTHING and registers NO
    pollers / SSE handlers / timers / window bridges unless
    $betaFlags['escalation-timeline-causal-forensics'] is true (default OFF). It
    reads the EXISTING decisionsStore (already fed by the ONE shared /events SSE
    in sse.js); it opens no socket and starts no interval of its own. The only
    network it does is a best-effort one-shot dismiss POST on operator action.

  CONSTRAINED ADDITIVE (vs the original proposal/mockup's ADR-18 amendment):
    NO message_bus.py edit, NO new bus envelope, NO new decisions column, NO
    ADR-18 amendment, NO in-process spawn/cron/subprocess. Escalation cards + the
    causal context are DERIVED at READ TIME from the existing decision rows; the
    only persisted state is the dismiss ack in an additive dashboard-side table.
    The richer "agent attribution persisted at decision-write time" + the live
    server-side prior/next JOIN the mockup footnote imagines is DEFERRED to a
    documented "from CLI" affordance; this build derives the same context
    client-side from the already-loaded feed, falling back to the server context
    endpoint when present.

  M2 (escalation-only foreground / ambient-at-rest): the resting footprint is a
    single paired badge with aria-live=polite. It NEVER auto-expands the pane,
    NEVER auto-foregrounds Frame C, NEVER rearranges layout. The operator must
    click the badge / gear to open the spine. Opening a node never happens
    automatically.

  M4 / M5 (paired label + color EVERYWHERE): the count badge, the node event
    badges, the action badges, and the prior/next compressed rows ALL carry the
    literal action / event WORD adjacent to the color swatch. Color is never the
    sole signal. Severity is expressed as TYPOGRAPHIC weight, not chrome.

  M6 (three Frame C domains reachable): the spine opens as a RIGHT inset; it does
    not displace the host Frame C stack. (The host wires it as an extra column.)

  M15 / G2 (polarity / self-exclude): the SM-own session is NEVER shown. The
    server endpoint excludes SM-self at the SQL WHERE (project_slug NOT IN the SM
    slug set AND session_id != SM_OWN_SESSION_ID); this component applies a second
    ownSessionId backstop in the derivation, and when the scoped session is the
    SM-own one it renders an explicit "self -- excluded" note, never a wall of
    nodes.

  M16 (domain-agnostic): no monitored-project vocabulary. Session identity, agent
    ids, reasons, and event labels are rendered FROM DATA.

  M17 (a11y): the spine is a real listbox (role=listbox, roving tabindex,
    Up/Down/Home/End, Enter opens detail, X dismisses); the overlay is a modal
    dialog (role=dialog, aria-modal, Escape closes + returns focus). Focused
    nodes / controls show a 2px accent ring + offset. Reduced motion honoured.

  M18 (post-hoc): pure render pass over already-streamed feed data + a one-shot
    dismiss ack that writes a SEPARATE dismissals table. No verdict-path work.

  MOCK FALLBACK: the live gov.db is frequently ALLOW-only (zero escalations), so
    when the live feed carries none the spine falls back to a realistic mock
    fixture (mockFeed) so the feature is testable. `usedMock` is exposed
    (data-mock) for the harness and shown in the foot note.

  FILE-DISJOINT: this component + its EscalationTimelineCausalForensics-* helper
    own all the new code. It dispatches no shell CustomEvent and imports no
    sibling beta component.

  ASCII-only (cp1252-safe): dash is "--". No smart quotes, no em-dashes.
-->
<script>
  import { onMount, onDestroy, tick } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { decisionsStore } from '../../sse.js';
  import { selectedSessionId, getOwnSessionId } from '../../stores/session.js';
  import { readOwnProjectSlugs } from '../../api.js';
  import {
    deriveEscalations,
    deriveContext,
    evtMeta,
    agentLabel,
    hhmmss,
    pct,
    actionColorVar,
    mockFeed,
    WINDOW_MS,
    WINDOW_CHOICES,
  } from './EscalationTimelineCausalForensics-data.js';

  /** The stable BETA flag key this component gates on. */
  const FLAG_KEY = 'escalation-timeline-causal-forensics';

  /**
   * allowMock: when the live feed has no escalations, fall back to a realistic
   * mock fixture so the spine is visible/testable. Default true (tests rely on
   * it). Set false to force a true live-only render.
   * @type {boolean}
   */
  export let allowMock = true;

  /**
   * now: epoch ms "end of axis" for the mock fixture, injectable for
   * deterministic tests. Defaults to the live clock read once per recompute
   * (NOT a registered timer).
   * @type {number|null}
   */
  export let now = null;

  // -- gate (single source of truth: the betaFlags store) --------------------
  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // -- self-exclude (G2 / M15) -----------------------------------------------
  let ownSessionId = '';
  /** @type {Set<string>} */
  let ownProjectSlugs = new Set();

  $: scopedSessionId = $selectedSessionId || null;
  $: isSelfScope = !!(ownSessionId && scopedSessionId && scopedSessionId === ownSessionId);

  // -- the live feed, scoped + self-excluded ---------------------------------
  // decisionsStore is fed by the SINGLE shared SSE (sse.js). We never open our
  // own stream. When a session is scoped we narrow to its rows.
  $: feedRows = $decisionsStore || [];
  $: scopedRows = scopedSessionId
    ? feedRows.filter((r) => r && r.session_id === scopedSessionId)
    : feedRows;

  // -- pane + overlay state --------------------------------------------------
  let paneOpen = false;
  let usedMock = false;
  /** @type {Array<Record<string, any>>} the rows the derivation runs over */
  let sourceRows = [];
  /** @type {Set<string>} locally-acked dismissals (mirrors the dismiss POST) */
  let dismissedLocal = new Set();
  /** @type {ReturnType<typeof deriveEscalations>} */
  let escalations = [];

  // the open forensic overlay (null = closed). carries the derived context.
  /** @type {null | ReturnType<typeof deriveContext>} */
  let overlay = null;
  let overlayDecisionId = '';
  let windowMs = WINDOW_MS;

  // roving-tabindex spine state
  let focusIdx = -1;
  let spineEl;
  /** @type {HTMLElement|null} node to return focus to when the overlay closes */
  let returnFocusEl = null;

  function recompute() {
    if (!enabled || isSelfScope) {
      sourceRows = [];
      escalations = [];
      usedMock = false;
      return;
    }
    const nowMs = Number.isFinite(now) ? Number(now) : Date.now();
    const live = deriveEscalations(scopedRows, { ownSessionId, dismissed: dismissedLocal });
    if (live.length > 0 || !allowMock) {
      sourceRows = scopedRows;
      escalations = live;
      usedMock = false;
      return;
    }
    // No live escalations -> realistic mock so the spine is visible + testable.
    const fix = mockFeed({ now: nowMs });
    sourceRows = fix.rows;
    // seed the mock's pre-dismissed node once (does not touch the live POST path)
    if (dismissedLocal.size === 0) {
      dismissedLocal = new Set(fix.dismissedIds);
    }
    escalations = deriveEscalations(fix.rows, { ownSessionId, dismissed: dismissedLocal });
    usedMock = true;
  }

  // Reactive RE-RENDER (not a timer): the feed / store / flag / scope drive it.
  $: enabled, isSelfScope, scopedRows, now, allowMock, dismissedLocal, recompute();

  // open (undismissed) escalation count -> the resting badge number (M2).
  $: openCount = escalations.filter((e) => e.dismissed_at == null).length;
  $: newest = escalations.find((e) => e.dismissed_at == null) || null;
  $: badgeLabel = newest
    ? `${openCount} escalation${openCount === 1 ? '' : 's'} awaiting forensic review; newest: ${evtMeta(newest.event_type).reason}. Activate to open the Escalation Timeline.`
    : `${openCount} escalation${openCount === 1 ? '' : 's'} awaiting forensic review. Activate to open the Escalation Timeline.`;

  // -- pane open / close -----------------------------------------------------
  async function setPane(open) {
    paneOpen = !!open;
    if (!paneOpen) {
      closeOverlay(false);
      return;
    }
    await tick();
    // focus the first node (do NOT auto-open a detail -- M2)
    focusIdx = escalations.length ? 0 : -1;
    await tick();
    focusNode(focusIdx, true);
  }

  function togglePane() {
    setPane(!paneOpen);
  }

  // -- spine keyboard listbox (roving tabindex) ------------------------------
  function focusNode(pos, silent) {
    if (!spineEl) return;
    const nodes = Array.from(spineEl.querySelectorAll('.etl__node'));
    if (!nodes.length) {
      if (!silent) spineEl.focus();
      return;
    }
    focusIdx = Math.max(0, Math.min(nodes.length - 1, pos < 0 ? 0 : pos));
    nodes.forEach((n, i) => n.setAttribute('tabindex', i === focusIdx ? '0' : '-1'));
    if (!silent) nodes[focusIdx].focus();
  }

  /** @param {KeyboardEvent} e */
  function onSpineKeydown(e) {
    const nodes = spineEl ? Array.from(spineEl.querySelectorAll('.etl__node')) : [];
    if (!nodes.length) return;
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        focusNode(focusIdx < 0 ? 0 : focusIdx + 1);
        break;
      case 'ArrowUp':
        e.preventDefault();
        focusNode(focusIdx <= 0 ? 0 : focusIdx - 1);
        break;
      case 'Home':
        e.preventDefault();
        focusNode(0);
        break;
      case 'End':
        e.preventDefault();
        focusNode(nodes.length - 1);
        break;
      case 'Enter':
      case ' ':
        e.preventDefault();
        if (focusIdx < 0) focusNode(0);
        else openOverlay(escalations[focusIdx].decision_id, nodes[focusIdx]);
        break;
      case 'x':
      case 'X':
      case 'Backspace':
        e.preventDefault();
        if (focusIdx >= 0) dismiss(escalations[focusIdx].decision_id);
        break;
      default:
        break;
    }
  }

  function onSpineFocus() {
    if (focusIdx < 0 && escalations.length) focusNode(0, true);
  }

  /** @param {number} i @param {Event} ev */
  function onNodeClick(i, ev) {
    focusNode(i, true);
    openOverlay(escalations[i].decision_id, ev && ev.currentTarget);
  }

  // -- the KEY interaction: open the split-view forensic overlay -------------
  async function openOverlay(decisionId, originEl) {
    const ctx = deriveContext(sourceRows, decisionId, { ownSessionId, windowMs });
    if (!ctx) return;
    overlay = ctx;
    overlayDecisionId = decisionId;
    returnFocusEl = originEl || null;
    await tick();
    if (closeBtnEl) closeBtnEl.focus();
  }

  function reopenWindow(ms) {
    windowMs = WINDOW_CHOICES.includes(Number(ms)) ? Number(ms) : WINDOW_MS;
    if (overlayDecisionId) {
      overlay = deriveContext(sourceRows, overlayDecisionId, { ownSessionId, windowMs });
    }
  }

  function closeOverlay(returnFocus) {
    overlay = null;
    overlayDecisionId = '';
    if (returnFocus && returnFocusEl && typeof returnFocusEl.focus === 'function') {
      returnFocusEl.focus();
    }
  }

  /** @param {KeyboardEvent} e */
  function onOverlayKeydown(e) {
    if (e.key === 'Escape') {
      e.preventDefault();
      closeOverlay(true);
    }
  }

  // -- dismiss (POST /api/escalations/{id}/dismiss -> escalation_dismissals) --
  // Optimistic: ack locally first (the node self-prunes), then best-effort POST.
  // A POST failure is non-fatal (the local ack stands for the session); the
  // dismiss is pure observability (M18) and never touches a decisions row.
  async function dismiss(decisionId) {
    const did = String(decisionId || '').trim();
    if (!did || dismissedLocal.has(did)) return;
    dismissedLocal = new Set([...dismissedLocal, did]);
    // close the overlay if it was showing this node, then refocus a node.
    if (overlayDecisionId === did) closeOverlay(false);
    await tick();
    focusNode(0, false);
    // best-effort server ack -- only for real (non-mock) ids
    if (!usedMock) {
      try {
        await fetch(`/api/escalations/${encodeURIComponent(did)}/dismiss`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          cache: 'no-store',
          body: JSON.stringify({ decision_id: did }),
        });
      } catch {
        /* server down -- local ack stands; never flips a verdict */
      }
    }
  }

  /** @type {HTMLButtonElement} */
  let closeBtnEl;

  onMount(() => {
    ownSessionId = getOwnSessionId() || '';
    ownProjectSlugs = readOwnProjectSlugs();
    recompute();
  });

  onDestroy(() => {
    paneOpen = false;
    overlay = null;
  });
</script>

{#if enabled}
  <div
    class="etl"
    class:etl--open={paneOpen}
    data-testid="escalation-timeline-causal-forensics"
    data-mock={usedMock ? 'true' : 'false'}
    data-self={isSelfScope ? 'true' : 'false'}
  >
    <!-- ===== RESTING SIGNATURE: the paired amber count badge + gear (M2/M4) ===== -->
    <div class="etl__gutter">
      {#if isSelfScope}
        <span class="etl__self-badge" role="note">self -- excluded (G2)</span>
      {:else if openCount > 0}
        <button
          type="button"
          class="etl__badge"
          data-open={paneOpen ? 'true' : 'false'}
          aria-label={badgeLabel}
          aria-expanded={paneOpen ? 'true' : 'false'}
          on:click={togglePane}
        >
          <span class="etl__badge-dot" aria-hidden="true"></span>
          <span class="etl__badge-n">{openCount}</span>
          <span class="etl__badge-lab">escalation{openCount === 1 ? '' : 's'}</span>
        </button>
      {:else}
        <!-- calm: no open escalations -> a quiet "0 escalations" pill (still paired) -->
        <span class="etl__badge etl__badge--calm" role="status" aria-label="No escalations awaiting review">
          <span class="etl__badge-n">0</span>
          <span class="etl__badge-lab">escalations</span>
        </span>
      {/if}
      <button
        type="button"
        class="etl__gear"
        aria-label="Open Escalation Timeline pane"
        title="Escalation Timeline"
        on:click={() => setPane(true)}
      >cog</button>
      <!-- aria-live polite announce (M2: never steals focus / never auto-expands) -->
      <span class="sr-only" aria-live="polite">{openCount > 0 ? badgeLabel : ''}</span>
    </div>

    <!-- ===================== THE ESCALATION TIMELINE INSET (spine) ===================== -->
    {#if paneOpen}
      <section class="etl__inset" aria-label="Escalation Timeline">
        <div class="etl__inset-head">
          <h3 class="etl__inset-title">Escalation Timeline</h3>
          <button
            type="button"
            class="etl__inset-close"
            aria-label="Close Escalation Timeline pane"
            on:click={() => setPane(false)}
          >x</button>
        </div>
        <span class="etl__beta">BETA -- default OFF, toggled in Settings</span>

        {#if escalations.length === 0}
          <p class="etl__empty" role="note">No escalations in scope.</p>
        {:else}
          <ul
            class="etl__spine"
            bind:this={spineEl}
            role="listbox"
            tabindex="0"
            aria-label={`Escalation events, newest first. ${escalations.length} node${escalations.length === 1 ? '' : 's'}. Arrow keys move between nodes, Enter opens the forensic detail, X dismisses the focused node.`}
            on:keydown={onSpineKeydown}
            on:focus={onSpineFocus}
          >
            <span class="etl__spine-line" aria-hidden="true"></span>
            {#each escalations as e, i (e.escalation_id)}
              {@const meta = evtMeta(e.event_type)}
              {@const dismissed = e.dismissed_at != null}
              <li
                class="etl__node"
                role="option"
                data-evt={e.event_type}
                data-sev={meta.sev}
                data-dismissed={dismissed ? 'true' : 'false'}
                aria-selected="false"
                tabindex={i === 0 ? 0 : -1}
                aria-label={`${meta.reason} -- proposed ${e.proposed_action} at ${hhmmss(e.triggered_at)}, agent ${e.agent_id}${dismissed ? ' (dismissed)' : ''}`}
                on:click={(ev) => onNodeClick(i, ev)}
              >
                <span class="etl__tick" aria-hidden="true">{hhmmss(e.triggered_at)}</span>
                <span
                  class="etl__pip"
                  aria-hidden="true"
                  style={`--pip:${actionColorVar(meta.action)}`}
                ></span>
                <span class="etl__reason">
                  {meta.reason}<span class="etl__dismissed-tag">dismissed</span>
                </span>
                <span class="etl__node-meta">
                  <span class="etl__evt-badge" style={`--evt:${actionColorVar(meta.action)}`}>
                    <span class="etl__evt-sw" aria-hidden="true"></span>{meta.label}
                  </span>
                  <span class="etl__agent">agent {e.agent_id} -- {e.proposed_action}</span>
                </span>
              </li>
            {/each}
          </ul>
          <div class="etl__foot">
            {#if usedMock}
              <span class="etl__mock" title="Live feed had no escalations -- showing a sample fixture so the spine is testable.">sample data</span>
            {/if}
          </div>
        {/if}
      </section>
    {/if}

    <!-- ===================== SPLIT-VIEW FORENSIC OVERLAY (scoped to this pane) ===================== -->
    {#if overlay}
      {@const m = evtMeta(overlay.event_type)}
      <div
        class="etl__scrim"
        role="presentation"
        on:click={(e) => { if (e.target === e.currentTarget) closeOverlay(true); }}
        on:keydown={onOverlayKeydown}
      >
        <div class="etl__modal" role="dialog" aria-modal="true" aria-label={`${m.label} -- forensic detail`}>
          <div class="etl__modal-head">
            <div>
              <h3 class="etl__modal-title">{m.label} -- forensic detail</h3>
              <span class="etl__modal-when">{hhmmss(overlay.focus.timestamp)} -- decision {overlay.decision_id}</span>
            </div>
            <div class="etl__modal-actions">
              <button
                type="button"
                class="etl__mbtn etl__mbtn--dismiss"
                aria-label="Dismiss / acknowledge this escalation"
                on:click={() => { const d = overlay.decision_id; dismiss(d); }}
              >Dismiss (X)</button>
              <button
                type="button"
                class="etl__mbtn"
                bind:this={closeBtnEl}
                aria-label="Close forensic detail (Esc)"
                on:click={() => closeOverlay(true)}
              >Close (Esc)</button>
            </div>
          </div>

          <div class="etl__cols">
            <!-- LEFT: DecisionDiff -->
            <div class="etl__col">
              <p class="etl__col-label">Decision diff</p>
              <div class="etl__diff-action">
                <span class="etl__action-badge" data-act={overlay.focus.action} style={`--act:${actionColorVar(overlay.focus.action)}`}>
                  <span class="etl__action-sw" aria-hidden="true"></span>{overlay.focus.action}
                </span>
                <span class="etl__agent-chip">agent {overlay.focus.agent_id}</span>
              </div>
              {#if overlay.focus.reasoning}
                <p class="etl__diff-reasoning">{overlay.focus.reasoning}</p>
              {/if}
              <p class="etl__diff-content-label">Matched message content</p>
              <div class="etl__diff-content" tabindex="0" role="group" aria-label="Matched message content, scroll-isolated">{overlay.focus.content || '(no content recorded)'}</div>
              {#if overlay.focus.direction}
                <p class="etl__diff-dir">direction: {overlay.focus.direction}</p>
              {/if}
              <div class="etl__conf">
                <div class="etl__conf-head">
                  <span class="etl__conf-lab">confidence at decision time</span>
                  <span class="etl__conf-val">{pct(overlay.focus.confidence)}</span>
                </div>
                <div class="etl__conf-bar">
                  <div
                    class="etl__conf-fill"
                    style={`width:${pct(overlay.focus.confidence)};background:${actionColorVar(overlay.focus.action)}`}
                  ></div>
                </div>
              </div>
            </div>

            <div class="etl__vline" aria-hidden="true"></div>

            <!-- RIGHT: causal context -->
            <div class="etl__col">
              <p class="etl__col-label">Causal context (+/- {Math.round(overlay.window_ms / 1000)}s window)</p>

              <div class="etl__ctx-group etl__ctx-prior">
                <p class="etl__ctx-h">Lead-up <span class="etl__ct">{overlay.prior.length} prior decision{overlay.prior.length === 1 ? '' : 's'}</span></p>
                {#each overlay.prior as r, i}
                  <div class="etl__ctx-row">
                    <span class="etl__seq">-{overlay.prior.length - i}</span>
                    <span class="etl__act" data-act={r.action} style={`--act:${actionColorVar(r.action)}`}>
                      <span class="etl__act-d" aria-hidden="true"></span>{r.action}
                    </span>
                    <span class="etl__rsn" title={r.reason}>{r.reason}</span>
                    <span class="etl__ag">{r.agent_id}</span>
                  </div>
                {:else}
                  <p class="etl__ctx-none">(no prior decisions in this session window)</p>
                {/each}
              </div>

              <div class="etl__ctx-focus" style={`--evt:${actionColorVar(m.action)}`}>
                <span class="etl__marker" aria-hidden="true">&gt;&gt;</span>
                ESCALATION -- {m.label} at {hhmmss(overlay.focus.timestamp)}
              </div>

              <div class="etl__ctx-group">
                <p class="etl__ctx-h">Aftermath <span class="etl__ct">{overlay.next.length} next decision{overlay.next.length === 1 ? '' : 's'}</span></p>
                {#each overlay.next as r, i}
                  <div class="etl__ctx-row">
                    <span class="etl__seq">+{i + 1}</span>
                    <span class="etl__act" data-act={r.action} style={`--act:${actionColorVar(r.action)}`}>
                      <span class="etl__act-d" aria-hidden="true"></span>{r.action}
                    </span>
                    <span class="etl__rsn" title={r.reason}>{r.reason}</span>
                    <span class="etl__ag">{r.agent_id}</span>
                  </div>
                {:else}
                  <p class="etl__ctx-none">(no aftermath decisions yet)</p>
                {/each}
              </div>

              <div class="etl__agents">
                <p class="etl__ctx-h">Agents active in window <span class="etl__ct">from data</span></p>
                <div class="etl__agents-row">
                  {#each overlay.agents_in_window as a}
                    <span class="etl__agent-window">
                      <span class="etl__agent-window-sw" aria-hidden="true"></span>
                      {a.agent_id}
                      <span class="etl__agent-window-span">{hhmmss(a.active_from)}-{hhmmss(a.active_to)}</span>
                    </span>
                  {/each}
                </div>
                <div class="etl__seg" role="group" aria-label="Context window size">
                  {#each WINDOW_CHOICES as choice}
                    <button
                      type="button"
                      aria-pressed={windowMs === choice ? 'true' : 'false'}
                      on:click={() => reopenWindow(choice)}
                    >+/-{Math.round(choice / 1000)}s</button>
                  {/each}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    {/if}
  </div>
{/if}

<style>
  /* The component is a self-contained Frame-C-scoped inset. It reuses theme.css
     tokens verbatim (the per-theme action palette + chrome) -- no new tokens. */
  .etl {
    position: relative;
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  /* ===================== resting gutter (badge + gear) ===================== */
  .etl__gutter {
    display: inline-flex;
    align-items: center;
    gap: 10px;
  }

  /* paired amber count badge (theme-invariant warn token, paired WORD + color) */
  .etl__badge {
    appearance: none;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 11px;
    letter-spacing: 0.06em;
    font-weight: 700;
    border: 1px solid var(--badge-warn-border, #ea580c);
    border-radius: 999px;
    padding: 4px 11px 4px 9px;
    background: var(--badge-warn-bg, #ffedd5);
    color: var(--badge-warn-fg, #ea580c);
  }
  .etl__badge[data-open='true'] {
    background: var(--badge-warn-fg, #ea580c);
    color: #fff;
  }
  .etl__badge[data-open='true'] .etl__badge-dot {
    background: #fff;
  }
  .etl__badge:focus-visible {
    outline: 2px solid var(--accent, #f59e0b);
    outline-offset: 2px;
  }
  .etl__badge-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--c-intervene, #f97316);
    flex: 0 0 auto;
  }
  .etl__badge-n {
    font-variant-numeric: tabular-nums;
  }
  .etl__badge-lab {
    font-weight: 600;
    letter-spacing: 0.04em;
  }
  /* calm/zero state: a quiet observing pill (not a button -- nothing to open) */
  .etl__badge--calm {
    cursor: default;
    border-color: var(--badge-obs-border, #cbd5e1);
    background: var(--badge-obs-bg, #f1f5f9);
    color: var(--badge-obs-fg, #475569);
    font-weight: 600;
  }
  .etl__self-badge {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10px;
    letter-spacing: 0.06em;
    font-style: italic;
    color: var(--text-dim, #94a3b8);
    border: 1px dashed var(--border, #192030);
    border-radius: 3px;
    padding: 3px 9px;
  }
  .etl__gear {
    appearance: none;
    cursor: pointer;
    background: transparent;
    border: 1px solid var(--border, #192030);
    color: var(--text-ui, #8a8068);
    border-radius: 4px;
    width: 26px;
    height: 26px;
    line-height: 1;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 12px;
  }
  .etl__gear:focus-visible {
    outline: 2px solid var(--accent, #f59e0b);
    outline-offset: 2px;
  }

  /* ===================== the spine inset ===================== */
  .etl__inset {
    display: flex;
    flex-direction: column;
    min-width: 0;
    margin-top: 12px;
    padding: 14px 16px 16px;
    background: var(--bg-card, #0c1118);
    border: 1px solid var(--border, #192030);
    border-radius: 7px;
    max-height: 560px;
    overflow: auto; /* scroll-isolated (M1) */
  }
  .etl__inset-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 4px;
  }
  .etl__inset-title {
    margin: 0;
    font-family: var(--font-h, inherit);
    font-size: 15px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--text-bright, #e8e0cc);
  }
  .etl__inset-close {
    appearance: none;
    cursor: pointer;
    background: transparent;
    border: 1px solid var(--border, #192030);
    color: var(--text-ui, #8a8068);
    border-radius: 4px;
    width: 24px;
    height: 24px;
    line-height: 1;
    font-family: var(--font-d, ui-monospace, monospace);
  }
  .etl__inset-close:focus-visible {
    outline: 2px solid var(--accent, #f59e0b);
    outline-offset: 2px;
  }
  .etl__beta {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 9.5px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--badge-ar-fg, #d97706);
    background: var(--badge-ar-bg, #fef3c7);
    border: 1px solid var(--badge-ar-border, #d97706);
    border-radius: 3px;
    padding: 2px 7px;
    margin: 6px 0 12px;
    display: inline-block;
    align-self: flex-start;
  }
  .etl__empty {
    margin: 8px 0 0;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 12px;
    color: var(--text-dim, #94a3b8);
    font-style: italic;
  }

  /* THE WALL-CLOCK SPINE */
  .etl__spine {
    position: relative;
    list-style: none;
    margin: 0;
    padding: 0 0 0 64px;
    outline: none;
  }
  .etl__spine-line {
    position: absolute;
    top: 6px;
    bottom: 6px;
    left: 54px;
    width: 1px;
    background: var(--border, #192030);
  }
  .etl__node {
    position: relative;
    display: block;
    padding: 9px 4px 11px 16px;
    cursor: pointer;
    border-radius: 5px;
  }
  .etl__node:hover {
    background: var(--bg-row-hover, #131c2a);
  }
  .etl__node:focus-visible {
    outline: 2px solid var(--accent, #f59e0b);
    outline-offset: 2px;
  }
  .etl__tick {
    position: absolute;
    left: -64px;
    top: 11px;
    width: 48px;
    text-align: right;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10px;
    color: var(--text-dim, #94a3b8);
    font-variant-numeric: tabular-nums;
  }
  .etl__pip {
    position: absolute;
    left: -11px;
    top: 13px;
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--pip, var(--c-intervene, #f97316));
    box-shadow: 0 0 0 2px var(--bg-card, #0c1118);
  }
  /* BLOCK-class severity gets a heavier ring -- ink, not only hue (M4). */
  .etl__node[data-sev='3'] .etl__pip {
    box-shadow:
      0 0 0 2px var(--bg-card, #0c1118),
      0 0 0 3.5px var(--pip, var(--c-block, #ef4444));
  }
  .etl__reason {
    display: block;
    color: var(--text-bright, #e8e0cc);
    line-height: 1.25;
  }
  /* severity = TYPOGRAPHIC weight (not chrome) */
  .etl__node[data-sev='3'] .etl__reason {
    font-weight: 750;
    font-size: 14px;
  }
  .etl__node[data-sev='2'] .etl__reason {
    font-weight: 600;
    font-size: 13px;
  }
  .etl__node[data-sev='1'] .etl__reason {
    font-weight: 500;
    font-size: 12.5px;
  }
  .etl__node-meta {
    display: block;
    margin-top: 5px;
  }
  .etl__evt-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10px;
    letter-spacing: 0.05em;
    border: 1px solid var(--evt, var(--border, #192030));
    border-radius: 3px;
    padding: 2px 7px;
    color: var(--text-bright, #e8e0cc);
  }
  .etl__evt-sw {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex: 0 0 auto;
    background: var(--evt, var(--c-intervene, #f97316));
  }
  .etl__agent {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10px;
    color: var(--text-dim, #94a3b8);
    margin-left: 8px;
  }
  /* DISMISSED node: self-prunes to a single struck hairline tick. */
  .etl__node[data-dismissed='true'] {
    padding-top: 4px;
    padding-bottom: 4px;
    opacity: 0.55;
  }
  .etl__node[data-dismissed='true'] .etl__reason {
    font-weight: 500;
    font-size: 11px;
    text-decoration: line-through;
    color: var(--text-dim, #94a3b8);
  }
  .etl__node[data-dismissed='true'] .etl__node-meta {
    display: none;
  }
  .etl__node[data-dismissed='true'] .etl__pip {
    background: var(--text-dim, #94a3b8);
    width: 6px;
    height: 6px;
    top: 9px;
    box-shadow: 0 0 0 2px var(--bg-card, #0c1118);
  }
  .etl__node[data-dismissed='true'] .etl__tick {
    top: 5px;
  }
  .etl__dismissed-tag {
    display: none;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 9px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-dim, #94a3b8);
    margin-left: 8px;
  }
  .etl__node[data-dismissed='true'] .etl__dismissed-tag {
    display: inline;
  }

  .etl__foot {
    margin-top: 10px;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10px;
    color: var(--text-dim, #94a3b8);
  }
  .etl__mock {
    color: var(--badge-ar-fg, #d97706);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  /* ===================== split-view forensic overlay ===================== */
  .etl__scrim {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: stretch;
    justify-content: flex-end;
    background: rgba(0, 0, 0, 0.45);
    z-index: 20;
  }
  .etl__modal {
    width: min(760px, 96%);
    background: var(--bg-card, #0c1118);
    border-left: 1px solid var(--border-hi, rgba(245, 158, 11, 0.25));
    box-shadow: -30px 0 80px -30px rgba(0, 0, 0, 0.85);
    display: grid;
    grid-template-rows: auto 1fr;
    overflow: hidden;
    animation: etl-slidein 0.2s ease;
  }
  @keyframes etl-slidein {
    from {
      transform: translateX(20px);
      opacity: 0.4;
    }
    to {
      transform: none;
      opacity: 1;
    }
  }
  .etl__modal-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border, #192030);
  }
  .etl__modal-title {
    margin: 0;
    font-family: var(--font-h, inherit);
    font-size: 15px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--text-bright, #e8e0cc);
  }
  .etl__modal-when {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 11px;
    color: var(--text-dim, #94a3b8);
  }
  .etl__modal-actions {
    display: inline-flex;
    gap: 8px;
    align-items: center;
  }
  .etl__mbtn {
    appearance: none;
    cursor: pointer;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 11px;
    letter-spacing: 0.04em;
    border: 1px solid var(--border, #192030);
    background: transparent;
    color: var(--text-ui, #8a8068);
    border-radius: 4px;
    padding: 5px 11px;
  }
  .etl__mbtn:focus-visible {
    outline: 2px solid var(--accent, #f59e0b);
    outline-offset: 2px;
  }
  .etl__mbtn--dismiss {
    color: var(--badge-warn-fg, #ea580c);
    border-color: var(--badge-warn-border, #ea580c);
    background: var(--badge-warn-bg, #ffedd5);
    font-weight: 700;
  }
  .etl__cols {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 1px minmax(0, 1fr);
    min-height: 0;
  }
  .etl__vline {
    background: var(--border, #192030);
  }
  .etl__col {
    padding: 14px 16px;
    overflow: auto;
    min-width: 0;
  }
  .etl__col-label {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 9.5px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--text-ui, #8a8068);
    margin: 0 0 10px;
  }

  /* LEFT: DecisionDiff */
  .etl__diff-action {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    margin-bottom: 12px;
  }
  .etl__action-badge {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 12px;
    letter-spacing: 0.06em;
    font-weight: 700;
    border: 1px solid var(--act, var(--border, #192030));
    border-radius: 4px;
    padding: 4px 10px;
    color: var(--text-bright, #e8e0cc);
  }
  .etl__action-sw {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    flex: 0 0 auto;
    background: var(--act, var(--c-intervene, #f97316));
  }
  .etl__action-badge[data-act='BLOCK'] .etl__action-sw {
    box-shadow:
      0 0 0 1px var(--bg-card, #0c1118),
      0 0 0 2px var(--c-block, #ef4444);
  }
  .etl__agent-chip {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10px;
    letter-spacing: 0.04em;
    color: var(--text-ui, #8a8068);
    border: 1px solid var(--border, #192030);
    border-radius: 3px;
    padding: 2px 7px;
  }
  .etl__diff-reasoning {
    font-size: 12.5px;
    color: var(--text, #b8b098);
    line-height: 1.55;
    margin: 0 0 12px;
  }
  .etl__diff-content-label {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 9.5px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-ui, #8a8068);
    margin: 0 0 5px;
  }
  .etl__diff-content {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 12px;
    color: var(--text-bright, #e8e0cc);
    background: var(--bg-row, #0e141e);
    border: 1px solid var(--border, #192030);
    border-left: 3px solid var(--c-block, #ef4444);
    border-radius: 5px;
    padding: 10px 12px;
    white-space: pre-wrap;
    word-break: break-word;
    line-height: 1.5;
    max-height: 160px;
    overflow: auto;
  }
  .etl__diff-content:focus-visible {
    outline: 2px solid var(--accent, #f59e0b);
    outline-offset: 2px;
  }
  .etl__diff-dir {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10px;
    color: var(--text-dim, #94a3b8);
    margin-top: 6px;
  }
  .etl__conf {
    margin-top: 14px;
  }
  .etl__conf-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
  }
  .etl__conf-lab {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 9.5px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-ui, #8a8068);
  }
  .etl__conf-val {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 15px;
    color: var(--text-bright, #e8e0cc);
    font-variant-numeric: tabular-nums;
    font-weight: 700;
  }
  .etl__conf-bar {
    margin-top: 6px;
    height: 6px;
    border-radius: 3px;
    background: var(--bg-row, #0e141e);
    border: 1px solid var(--border, #192030);
    overflow: hidden;
  }
  .etl__conf-fill {
    height: 100%;
    background: var(--c-block, #ef4444);
  }

  /* RIGHT: causal context */
  .etl__ctx-group {
    margin-bottom: 14px;
  }
  .etl__ctx-h {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 9.5px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-ui, #8a8068);
    margin: 0 0 7px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .etl__ct {
    color: var(--text-dim, #94a3b8);
    font-weight: 600;
  }
  .etl__ctx-row {
    display: grid;
    grid-template-columns: 26px 84px 1fr auto;
    gap: 8px;
    align-items: baseline;
    padding: 5px 0;
    font-size: 11.5px;
  }
  .etl__seq {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10px;
    color: var(--text-dim, #94a3b8);
    text-align: right;
  }
  .etl__act {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10.5px;
    letter-spacing: 0.04em;
    color: var(--text-bright, #e8e0cc);
  }
  .etl__act-d {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex: 0 0 auto;
    background: var(--act, var(--c-allow, #22c55e));
  }
  .etl__rsn {
    color: var(--text, #b8b098);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }
  .etl__ag {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10px;
    color: var(--text-dim, #94a3b8);
  }
  .etl__ctx-prior .etl__ctx-row {
    opacity: 0.82;
  }
  .etl__ctx-none {
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 11px;
    color: var(--text-dim, #94a3b8);
    font-style: italic;
    margin: 4px 0;
  }
  .etl__ctx-focus {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 9px 0;
    padding: 7px 10px;
    background: var(--bg-row, #0e141e);
    border: 1px solid var(--border-hi, rgba(245, 158, 11, 0.25));
    border-left: 3px solid var(--evt, var(--c-intervene, #f97316));
    border-radius: 5px;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 11px;
    color: var(--text-bright, #e8e0cc);
  }
  .etl__marker {
    font-weight: 700;
    color: var(--evt, var(--c-intervene, #f97316));
  }
  .etl__agents {
    margin-top: 6px;
  }
  .etl__agents-row {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
    margin-top: 7px;
  }
  .etl__agent-window {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10.5px;
    color: var(--text-bright, #e8e0cc);
    border: 1px solid var(--border, #192030);
    border-radius: 999px;
    padding: 3px 10px;
    background: var(--bg-row, #0e141e);
  }
  .etl__agent-window-sw {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--accent, #f59e0b);
  }
  .etl__agent-window-span {
    color: var(--text-dim, #94a3b8);
  }
  .etl__seg {
    display: inline-flex;
    border: 1px solid var(--border, #192030);
    border-radius: 5px;
    overflow: hidden;
    margin-top: 9px;
  }
  .etl__seg button {
    appearance: none;
    cursor: pointer;
    background: transparent;
    border: none;
    font-family: var(--font-d, ui-monospace, monospace);
    font-size: 10.5px;
    letter-spacing: 0.03em;
    color: var(--text-ui, #8a8068);
    padding: 5px 10px;
    line-height: 1;
  }
  .etl__seg button + button {
    border-left: 1px solid var(--border, #192030);
  }
  .etl__seg button[aria-pressed='true'] {
    background: var(--accent-dim, rgba(245, 158, 11, 0.09));
    color: var(--accent, #f59e0b);
    font-weight: 700;
  }
  .etl__seg button:focus-visible {
    outline: 2px solid var(--accent, #f59e0b);
    outline-offset: -2px;
  }

  @media (max-width: 680px) {
    .etl__cols {
      grid-template-columns: 1fr;
    }
    .etl__vline {
      display: none;
    }
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    margin: -1px;
    padding: 0;
    border: 0;
    clip: rect(0 0 0 0);
    overflow: hidden;
  }

  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .etl__modal {
      animation: none;
    }
  }
  :global(html[data-motion='reduce']) .etl__modal {
    animation: none;
  }
</style>
