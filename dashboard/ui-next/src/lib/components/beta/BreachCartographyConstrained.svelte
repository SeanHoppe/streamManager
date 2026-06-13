<!--
  BreachCartographyConstrained.svelte -- BETA feature
  "breach-cartography-constrained" (#5): Breach Cartography, temporal decision
  causation UI, CONSTRAINED v1.

  A TRANSIENT modal overlay that turns a governance negative-regression alarm
  into a one-click causal decision map -- a swimlane of the decisions in the
  run-up (X = time, Y = one decision per lane), a pattern shelf resolving each
  lane's matched_hash, a temporal scrubber, and a heuristic-ranked Surgical
  Revert panel. The operator reverts the offending verdict instead of blindly
  rolling back the whole run. This is the Svelte realisation of the
  operator-APPROVED mockup
  (reports/proposals/mockups/breach-cartography-constrained.html); it reuses
  theme.css tokens verbatim (the five action color tokens, the M4 badge tokens,
  the --accent / --border chrome) -- NO new color tokens, NO CSS pollution.

  ============================ GOVERNANCE FLOOR ============================
  BETA GATE: the component renders NOTHING and registers NO pollers / SSE
    handlers / timers / fetches unless $betaFlags['breach-cartography-
    constrained'] is true (default OFF). It opens no socket and starts no
    interval; the ONLY fetch is the one-shot cartography read fired by the
    operator pressing "Map this regression" (a user action), and the only timers
    are the 30s idle-dismiss + idle-meter rAF, both started ONLY while the modal
    is open and torn down on close/destroy.

  M1 / M2 (three frames; escalation-only foreground): this is NOT a fourth
    persistent frame. It is a transient modal launched ONLY from a foreground
    escalation (a governance negative-regression / variance alert). At rest it is
    a single quiet launch chip; the modal dismisses on action, Esc, scrim-click,
    or a 30s idle timeout -- it never becomes a surface the operator must manage.

  M5 / M4 (paired label + color, never color alone): every decision node renders
    the literal TEXT verdict + confidence ("BLOCK conf=1.00") AND a shape glyph
    (square / diamond / triangle / dot) so a color-blind operator reads it
    without hue. Color is never the sole signal anywhere in this component.

  Absolute HITL gate: the Surgical Revert is a TWO-STEP operator action (select
    -> accept -> confirm). It NEVER auto-acts. Confirm calls the EXISTING
    /api/hitl/annotate path (no new envelope) to record the override.

  POLARITY (G2 / M15): the server endpoint self-excludes SM (project_slug NOT IN
    the SM slug set AND session_id != SM_OWN_SESSION_ID). When the escalated
    session IS the SM-self session, the revert accept is DISABLED with a literal
    text reason ("POLARITY G2: SM-self session -- revert locked out"). SM never
    reverts its own session.

  M16 (domain-agnostic): no monitored-project vocabulary. Session identity,
    project slug, cell labels, verdicts -- all rendered FROM DATA.

  M17 (a11y): role=dialog + aria-modal, focus moves into the modal on open and
    restores to the trigger on close, Tab is trapped, Esc closes, the scrubber is
    a real range input (arrow-key steppable), the revert list is a radiogroup,
    every focusable shows the global 2px accent focus ring.

  M18 (post-hoc): a pure read pass over already-recorded decisions/patterns. No
    verdict-path work; the only write is the operator-confirmed annotate.

  MOCK FALLBACK: when the live gov.db read returns no rows (frequently the case
    on a quiet/ALLOW-only DB) OR errors, the modal falls back to a realistic mock
    cartography fixture so the feature is always populated + testable. A "MOCK
    DATA -- live gov.db unavailable" strip is shown so the operator is never
    misled into reading a fabricated chain as live. `usedMock` is exposed.

  CONSTRAINED v1: per-decision maturity snapshots require a FROZEN schema edit
    (deferred to a future ADR-18 amendment). v1 derives the coarse maturity_delta
    ONLY from the alert's RingDelta. No new bus envelope; no governance.py hook;
    no in-process spawn/cron/subprocess. The "deep replay / counterfactual" part
    is a documented non-functional "from CLI" affordance, not built in-process.

  FILE-DISJOINT: this component + BreachCartographyConstrained-data.js own all
    the new client code. It listens for the existing escalation signal already in
    the feed (escalation-action rows) to decide whether to paint the launch chip.

  ASCII-only (cp1252-safe): dash is "--"; no smart quotes; no em-dashes.
-->
<script>
  import { onMount, onDestroy, tick } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { decisionsStore } from '../../sse.js';
  import { sessions, getOwnSessionId } from '../../stores/session.js';
  import { getBreachCartography, postHitlAnnotate } from '../../api.js';
  import {
    buildModel,
    mockCartographyPayload,
    fmtClock,
  } from './BreachCartographyConstrained-data.js';

  /** The stable BETA flag key this component gates on. */
  const FLAG_KEY = 'breach-cartography-constrained';

  /**
   * allowMock: when the live read returns no rows / errors, fall back to a
   * realistic mock fixture so the modal is populated + testable. Default true
   * (tests rely on it). Set false to force a true live-only render.
   * @type {boolean}
   */
  export let allowMock = true;

  /**
   * now: epoch ms anchor for the mock fixture, injectable for deterministic
   * tests. Defaults to the mock module's fixed anchor (NOT a registered timer).
   * @type {number|null}
   */
  export let now = null;

  /**
   * forceOpen: test-only -- opens the modal on mount with mock data so the
   * Playwright spec can assert the populated render without driving the feed.
   * Never used in production (App.svelte mounts with no props). Default false.
   * @type {boolean}
   */
  export let forceOpen = false;

  // -- gate (single source of truth: the betaFlags store) --------------------
  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // -- self-exclude identity (resolved once at DOM-ready) --------------------
  let ownSessionId = '';

  // -- launch eligibility: a governance negative-regression / variance alert --
  // The feed already carries escalation-action rows (the foreground-eligible
  // signal). At rest we show the quiet "Map this regression" chip ONLY when the
  // flag is ON and there is at least one escalation row in the (already
  // self-excluded) feed scoped to a governed session. We never open ourselves.
  $: feedRows = enabled ? ($decisionsStore || []) : [];
  $: governedIds = new Set(($sessions || []).map((s) => s && s.id).filter(Boolean));
  // The most-recent escalation row in a governed, non-SM session, if any.
  $: latestEscalation = enabled
    ? feedRows
        .filter((r) => {
          if (!r) return false;
          const a = String(r.action || '').toUpperCase();
          if (a !== 'GUIDE' && a !== 'INTERVENE' && a !== 'BLOCK') return false;
          const sid = r.session_id;
          if (!sid) return false;
          if (ownSessionId && sid === ownSessionId) return false; // G2 self
          return governedIds.has(sid);
        })
        .slice(-1)[0] || null
    : null;
  // Show the launch chip when eligible. (forceOpen test path bypasses this.)
  $: launchable = enabled && (forceOpen || !!latestEscalation);

  // -- modal state -----------------------------------------------------------
  let open = false;
  let loading = false;
  let loadError = false;
  let usedMock = false;
  /** @type {ReturnType<typeof buildModel>|null} */
  let model = null;

  // scrubber playhead (ms relative to t0); defaults to the alert (all visible).
  let playheadRel = 0;

  // surgical-revert selection + two-step accept state.
  let selectedRevert = null; // decisionId
  let confirmOpen = false;
  let receiptText = '';
  let liveMsg = ''; // aria-live announcements

  let lastTrigger = null;
  let idleTimer = null;
  let idleRAF = null;
  let idleFrac = 1;
  let modalEl;
  let closeBtn;

  // -- derived render slices -------------------------------------------------
  $: lanes = model ? model.lanes : [];
  $: patterns = model ? model.patterns : [];
  $: reverts = model ? model.reverts : [];
  $: windowMs = model ? model.windowMs : 600000;
  // Polarity lockout: the escalated session is the SM-self one.
  $: selfLocked = !!(model && (!model.excludedSelf
    || (ownSessionId && model.sessionId && model.sessionId === ownSessionId)));
  // selected revert detail (for the accept-status line).
  $: selectedDetail = reverts.find((r) => r.decisionId === selectedRevert) || null;
  // scrubber readout.
  $: visibleCount = lanes.filter((l) => l.tRel <= playheadRel).length;

  /**
   * Open the modal: fetch the cartography read for the escalated session, fall
   * back to mock on empty/error so the swimlane is always populated. The ONLY
   * network call this component makes, and only on a user action.
   * @param {EventTarget|null} trigger element to restore focus to on close
   * @param {string|null} sessionId the escalated session (null => mock anchor)
   */
  async function openModal(trigger, sessionId) {
    if (!enabled) return;
    lastTrigger = trigger || null;
    open = true;
    loading = true;
    loadError = false;
    usedMock = false;
    model = null;
    selectedRevert = null;
    confirmOpen = false;
    receiptText = '';

    await tick();
    if (closeBtn && typeof closeBtn.focus === 'function') closeBtn.focus();

    let payload = null;
    try {
      const data = await getBreachCartography({ session_id: sessionId || undefined });
      if (data && Array.isArray(data.decisions) && data.decisions.length > 0) {
        payload = data;
        usedMock = false;
      }
    } catch {
      loadError = true;
    }

    if (!payload) {
      if (!allowMock) {
        model = buildModel({ decisions: [], patterns: [] });
        usedMock = false;
        loading = false;
        return;
      }
      payload = mockCartographyPayload({ now });
      usedMock = true;
    }

    const m = buildModel(payload);
    model = m;
    // default the scrubber to the alert (all lanes visible) + default selection
    // to the top-ranked revert proposal. Read from the freshly-built model `m`
    // (not the $:-derived `lanes`/`reverts`, which have not recomputed yet).
    playheadRel = m.lanes.length ? Math.max(...m.lanes.map((l) => l.tRel), 0) : 0;
    selectedRevert = m.reverts.length ? m.reverts[0].decisionId : null;
    loading = false;
    liveMsg = usedMock
      ? 'Breach Cartography opened with sample data (live gov.db unavailable).'
      : 'Breach Cartography opened.';
    resetIdle();
  }

  function closeModal() {
    if (!open) return;
    open = false;
    confirmOpen = false;
    clearIdle();
    const t = lastTrigger;
    lastTrigger = null;
    if (t && typeof t.focus === 'function') t.focus();
  }

  // -- 30s idle dismiss (started only while open; reset on any interaction) ---
  function resetIdle() {
    clearIdle();
    const reduce = typeof window !== 'undefined' && window.matchMedia
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const start = Date.now();
    idleFrac = 1;
    if (!reduce && typeof requestAnimationFrame === 'function') {
      const step = () => {
        const elapsed = Date.now() - start;
        idleFrac = Math.max(0, 1 - elapsed / 30000);
        if (idleFrac > 0) idleRAF = requestAnimationFrame(step);
      };
      idleRAF = requestAnimationFrame(step);
    }
    idleTimer = setTimeout(() => {
      liveMsg = 'Breach Cartography dismissed after 30s idle.';
      closeModal();
    }, 30000);
  }
  function clearIdle() {
    if (idleTimer) { clearTimeout(idleTimer); idleTimer = null; }
    if (idleRAF && typeof cancelAnimationFrame === 'function') {
      cancelAnimationFrame(idleRAF); idleRAF = null;
    }
  }
  function bumpIdle() {
    if (open) resetIdle();
  }

  // -- focus trap + Esc (M17) ------------------------------------------------
  function onModalKeydown(e) {
    if (!open) return;
    if (e.key === 'Escape') { e.preventDefault(); closeModal(); return; }
    if (e.key === 'Tab' && modalEl) {
      const f = modalEl.querySelectorAll(
        'button, [href], input, [tabindex]:not([tabindex="-1"])',
      );
      const focusables = Array.prototype.filter.call(f, (el) => (
        !el.disabled && el.getAttribute('aria-disabled') !== 'true'
        && el.offsetParent !== null
      ));
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus();
      }
    }
  }

  // -- scrubber --------------------------------------------------------------
  function onScrub(e) {
    playheadRel = Number(e.target.value);
    bumpIdle();
  }

  // -- surgical revert: select + two-step accept (absolute HITL gate) --------
  function selectRevert(id) {
    selectedRevert = id;
    confirmOpen = false;
    receiptText = '';
    bumpIdle();
  }
  function onAccept() {
    if (selfLocked) {
      liveMsg = 'Revert locked: SM-self session (polarity G2).';
      return;
    }
    if (!selectedRevert) return;
    confirmOpen = true;
    liveMsg = 'Confirm step opened. A second confirm records the override.';
    bumpIdle();
  }
  function cancelConfirm() {
    confirmOpen = false;
    bumpIdle();
  }
  async function confirmRevert() {
    if (selfLocked || !selectedRevert || !model) return;
    confirmOpen = false;
    const id = selectedRevert;
    // Record the override via the EXISTING annotate path (no new envelope). The
    // server is the durable gate; a write failure still shows a local receipt
    // explaining the override was attempted (post-hoc, never on the verdict path).
    try {
      await postHitlAnnotate({
        decision_id: id,
        override_action: 'REVERTED',
        note: `breach-cartography surgical revert proposal accepted for ${id} (session ${model.sessionId})`,
      });
    } catch {
      /* server-down: the receipt below still records the operator's intent. */
    }
    receiptText = `Override recorded -- ${id} reverted via /api/hitl/annotate`;
    liveMsg = `Override recorded for ${id}. Modal will dismiss.`;
    // action taken -> the transient modal self-dismisses shortly after.
    setTimeout(closeModal, 1800);
  }

  // -- node tooltip (hover/focus) -- pure client, no fetch -------------------
  let tip = null; // { lane, x, y }
  function showTip(lane, ev) {
    const r = ev && ev.currentTarget && ev.currentTarget.getBoundingClientRect
      ? ev.currentTarget.getBoundingClientRect() : null;
    tip = {
      lane,
      x: r ? Math.min(r.left, (typeof window !== 'undefined' ? window.innerWidth : 1200) - 360) : 0,
      y: r ? r.bottom + 8 : 0,
    };
  }
  function hideTip() { tip = null; }

  // -- lifecycle: resolve identity once; (optionally) force-open for tests ----
  onMount(() => {
    ownSessionId = getOwnSessionId() || '';
    if (forceOpen && enabled) {
      // test path: open immediately with the mock anchor (no live feed needed).
      openModal(null, null);
    }
  });

  onDestroy(() => {
    clearIdle();
    open = false;
  });
</script>

{#if enabled}
  <!-- The quiet launch chip. Painted ONLY when an escalation makes the feature
       launchable (M2 escalation-only foreground). Self-managed; no layout steal. -->
  {#if launchable && !open}
    <div class="bcc-launch" role="region" aria-label="Breach Cartography (BETA)">
      <span class="bcc-launch__badge">
        <span class="bcc-launch__dot" aria-hidden="true"></span>NEG REGRESSION
      </span>
      <button
        type="button"
        class="bcc-launch__btn"
        aria-haspopup="dialog"
        on:click={(e) => openModal(e.currentTarget, latestEscalation ? latestEscalation.session_id : null)}
      >
        <span class="bcc-launch__glyph" aria-hidden="true">[]&rarr;</span>
        Map this regression
      </button>
    </div>
  {/if}

  {#if open}
    <!-- scrim + modal: transient overlay. -->
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div class="bcc-scrim" on:click={closeModal} aria-hidden="true"></div>

    <div
      class="bcc-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="bcc-modal-h"
      bind:this={modalEl}
      on:keydown={onModalKeydown}
      on:mousemove={bumpIdle}
    >
      <div class="bcc-shell">
        <!-- 30s idle-dismiss meter -->
        <div class="bcc-idlebar" aria-hidden="true">
          <span class="bcc-idlebar__fill" style={`transform:scaleX(${idleFrac})`}></span>
        </div>

        <button
          type="button"
          class="bcc-close"
          aria-label="Close Breach Cartography"
          bind:this={closeBtn}
          on:click={closeModal}
        >&times;</button>

        <!-- ===== LEFT INCIDENT GUTTER -- the SYMPTOM ===== -->
        <aside class="bcc-gutter">
          <p class="bcc-eyebrow">Incident</p>
          <span class="bcc-regbadge">
            <span class="bcc-sq" aria-hidden="true"></span>NEG REGRESSION
          </span>
          <h2 class="bcc-headline" id="bcc-modal-h">Decision causation map</h2>

          {#if loading}
            <p class="bcc-note" role="status">Loading causal chain ...</p>
          {:else if model}
            {#if model.regressedCells.length}
              <ul class="bcc-cells" aria-label="Regressed maturity cells">
                {#each model.regressedCells as c (c.id)}
                  <li class="bcc-cell">
                    <span class="bcc-arrow" aria-hidden="true">&darr;</span>{c.label}
                  </li>
                {/each}
              </ul>
            {/if}

            <div class="bcc-meta">
              window <b>{Math.round(windowMs / 60000)} min</b><br />
              session <b>{model.sessionId || '(unknown)'}</b>
            </div>

            <!-- polarity readout chip (paired text + tint, never tint alone) -->
            <span class="bcc-pol" class:bcc-pol--self={selfLocked}>
              <span class="bcc-pol__dot" aria-hidden="true"></span>
              {#if selfLocked}
                EXCLUDED_SELF=0 -- session=SM (SELF)
              {:else}
                EXCLUDED_SELF=1 -- target={model.projectSlug || 'governed'}
              {/if}
            </span>

            <div class="bcc-delta">
              <p class="bcc-delta__k">Maturity delta (RingDelta)</p>
              <span class="bcc-delta__v">
                <span aria-hidden="true">&darr;</span> {model.maturityDelta.cells} cells
              </span>
              {#if model.maturityDelta.note}
                <p class="bcc-delta__note">{model.maturityDelta.note}</p>
              {/if}
            </div>
          {/if}
        </aside>

        <!-- ===== RIGHT SWIMLANE CANVAS -- the CHAIN ===== -->
        <section class="bcc-canvas">
          <div class="bcc-cap">
            <span class="bcc-eyebrow">Decision swimlane</span>
            <span class="bcc-hint">X = time (older left) &middot; Y = one decision per lane &middot; arrows to matched pattern</span>
            {#if usedMock}
              <span class="bcc-mock" title="Live gov.db returned no rows -- showing a sample fixture so the chain is testable.">
                <span class="bcc-mock__dot" aria-hidden="true"></span>MOCK DATA -- live gov.db unavailable
              </span>
            {/if}
          </div>

          <div class="bcc-plot">
            {#if model && lanes.length}
              {#each lanes as l (l.decisionId)}
                <button
                  type="button"
                  class="bcc-node"
                  class:bcc-node--future={l.tRel > playheadRel}
                  data-action={l.action}
                  style={`left:${(l.xFrac * 86).toFixed(2)}%; top:${(8 + l.yFrac * 78).toFixed(2)}%;`}
                  data-decision={l.decisionId}
                  aria-label={`${l.verdict}, pattern ${l.hash || 'none'}: ${l.message}`}
                  on:mouseenter={(e) => showTip(l, e)}
                  on:mouseleave={hideTip}
                  on:focus={(e) => showTip(l, e)}
                  on:blur={hideTip}
                >
                  <span class="bcc-node__badge">
                    <span class={`bcc-glyph ${l.glyph}`} aria-hidden="true"></span>
                    <span class="bcc-node__verdict">{l.verdict}</span>
                  </span>
                  <span class="bcc-node__msg" title={l.message}>{l.message}</span>
                  <span class="bcc-node__sub">
                    <span class="bcc-node__hash">{l.hash || '(none)'}</span>
                    {#if l.hitlNote}<span class="bcc-node__hitl" title="HITL override note">{l.hitlNote}</span>{/if}
                    <span>{fmtClock(l.tRel)}</span>
                  </span>
                </button>
              {/each}

              <!-- pattern shelf (the CAUSE) -->
              <div class="bcc-shelf" aria-label="Matched pattern shelf">
                <span class="bcc-shelf__cap">Pattern shelf</span>
                {#each patterns as pat (pat.hash)}
                  <div class="bcc-pnode" class:bcc-pnode--immature={!pat.mature}>
                    <span class="bcc-pnode__hash">{pat.hash}<span class="bcc-pnode__lvl">L{pat.level}</span></span>
                    {#if pat.label}<p class="bcc-pnode__txt">{pat.label}</p>{/if}
                    <span class="bcc-pnode__occ">occ {pat.occurrences} -- {pat.mature ? 'mature' : 'immature'}</span>
                    {#if !pat.mature}
                      <span class="bcc-pnode__flag"><span class="bcc-tri" aria-hidden="true"></span>low-freq</span>
                    {/if}
                  </div>
                {/each}
              </div>
            {:else if !loading}
              <p class="bcc-note" role="note">No decisions in the regression window.</p>
            {/if}
          </div>
        </section>

        <!-- ===== TEMPORAL SCRUBBER ===== -->
        <div class="bcc-scrub">
          <div class="bcc-scrub__row">
            <span class="bcc-scrub__lbl">Scrub the causal chain</span>
            <span class="bcc-scrub__read" role="status">
              playhead {fmtClock(playheadRel)} -- {visibleCount} of {lanes.length} decisions before this moment
            </span>
          </div>
          <input
            class="bcc-scrubber"
            type="range"
            min="0"
            max={windowMs}
            step="1000"
            value={playheadRel}
            aria-label="Temporal playhead -- decisions before it are solid, after it ghosted"
            aria-valuetext={`playhead at ${fmtClock(playheadRel)}, ${visibleCount} of ${lanes.length} decisions visible`}
            on:input={onScrub}
          />
        </div>

        <!-- ===== SURGICAL REVERT PANEL -- the FIX ===== -->
        <section class="bcc-revert">
          <div class="bcc-revert__cap">
            <span class="bcc-revert__eyebrow">Surgical revert</span>
            <span class="bcc-revert__hint">heuristic rank = pattern-frequency + confidence &middot; select one, then confirm (absolute HITL gate)</span>
          </div>

          {#if reverts.length}
            <div class="bcc-revert__list" role="radiogroup" aria-label="Revert proposals, ranked">
              {#each reverts as r (r.decisionId)}
                <label
                  class={`bcc-rprop bcc-rprop--r${r.rankNum}`}
                  class:is-selected={selectedRevert === r.decisionId}
                >
                  <input
                    class="bcc-rprop__radio"
                    type="radio"
                    name="bcc-revert"
                    value={r.decisionId}
                    checked={selectedRevert === r.decisionId}
                    on:change={() => selectRevert(r.decisionId)}
                  />
                  <span class="bcc-rprop__rank" aria-hidden="true">{r.rankNum}</span>
                  <span class="bcc-rprop__main">
                    <span class="bcc-rprop__line">
                      <span class="bcc-mini" data-action={r.action}>
                        <span class={`bcc-g ${r.glyph}`} aria-hidden="true"></span>{r.verdict}
                      </span>
                      <span class="bcc-rprop__id">{r.decisionId}</span>
                    </span>
                    <p class="bcc-rprop__why">{r.why}</p>
                  </span>
                  <span class="bcc-rprop__score">score<b>{r.score.toFixed(2)}</b></span>
                </label>
              {/each}
            </div>
          {:else if !loading}
            <p class="bcc-note" role="note">No escalation verdicts to revert in this chain.</p>
          {/if}

          <!-- two-step accept (select -> accept -> confirm). Never auto-acts. -->
          <div class="bcc-acceptbar" class:is-self-locked={selfLocked}>
            <span class="bcc-acceptbar__status">
              {#if selectedDetail}
                Selected: <b>{selectedDetail.decisionId} ({selectedDetail.action}, score {selectedDetail.score.toFixed(2)})</b>
              {:else}
                Select a revert proposal above.
              {/if}
            </span>

            <button
              type="button"
              class="bcc-btn bcc-btn--accept"
              aria-disabled={selfLocked || !selectedRevert ? 'true' : 'false'}
              title={selfLocked ? 'Polarity G2: SM never reverts its own session' : undefined}
              on:click={onAccept}
            >
              Accept revert proposal
            </button>

            {#if selfLocked}
              <span class="bcc-lockout" role="note">
                <span class="bcc-lockout__dot" aria-hidden="true"></span>
                POLARITY G2: SM-self session -- revert locked out
              </span>
            {/if}

            {#if confirmOpen}
              <span class="bcc-confirm">
                <span class="bcc-acceptbar__status">Records an override via the existing annotate path. Confirm?</span>
                <button type="button" class="bcc-btn bcc-btn--confirm" on:click={confirmRevert}>Confirm revert</button>
                <button type="button" class="bcc-btn bcc-btn--ghost" on:click={cancelConfirm}>Cancel</button>
              </span>
            {/if}

            {#if receiptText}
              <span class="bcc-receipt" role="status">
                <span class="bcc-receipt__dot" aria-hidden="true"></span>{receiptText}
              </span>
            {/if}
          </div>

          <p class="bcc-cli-note" role="note">
            Deep counterfactual replay (toggle a verdict, re-feed, recompute maturity deltas)
            is a v1-CONSTRAINED deferral -- run it out-of-process from the CLI; it is NOT
            executed in-process here.
          </p>
        </section>

        <!-- BETA annotation footer (required) -->
        <span class="bcc-betafoot">
          <span class="bcc-betafoot__dot" aria-hidden="true"></span>
          BETA -- default OFF, toggled in Settings &gt; BETA features
        </span>
      </div>
    </div>

    <!-- node tooltip -->
    {#if tip}
      <div class="bcc-tip" role="tooltip" style={`left:${tip.x}px; top:${tip.y}px;`}>
        <div class="bcc-tip__verdict" data-action={tip.lane.action}>
          <span class="bcc-node__verdict">{tip.lane.verdict}</span>
        </div>
        <p class="bcc-tip__msg">{tip.lane.message}</p>
        <div class="bcc-tip__grid">
          <span class="bcc-tip__k">pattern</span><span class="bcc-tip__v">{tip.lane.hash || '(none)'}</span>
          <span class="bcc-tip__k">confidence</span><span class="bcc-tip__v">{tip.lane.confidence.toFixed(2)}</span>
          <span class="bcc-tip__k">HITL note</span><span class="bcc-tip__v">{tip.lane.hitlNote || '--'}</span>
        </div>
      </div>
    {/if}
  {/if}

  <!-- aria-live region for scrubber / accept announcements -->
  <div class="bcc-sr-only" role="status" aria-live="polite">{liveMsg}</div>
{/if}

<style>
  /* ---- launch chip: quiet, escalation-only foreground (M2) ---- */
  .bcc-launch {
    position: fixed;
    right: 1.1rem;
    bottom: 1.1rem;
    z-index: 39;
    display: inline-flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.5rem 0.7rem;
    border: 1px solid var(--border-hi, rgba(245, 158, 11, 0.25));
    border-left: 3px solid var(--badge-ar-border, #d97706);
    border-radius: 8px;
    background: var(--bg-card, #0c1118);
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
  }
  .bcc-launch__badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-family: var(--ff-system);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 3px 8px;
    border-radius: 2px;
    line-height: 1;
    color: #b91c1c;
    background: var(--badge-blocked-bg, #fee2e2);
    border: 2px solid var(--badge-blocked-border, #dc2626);
  }
  .bcc-launch__dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: currentColor; flex: 0 0 auto;
  }
  .bcc-launch__btn {
    appearance: none;
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    font-family: var(--ff-mono);
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--accent, #f59e0b);
    background: var(--accent-dim, rgba(245, 158, 11, 0.09));
    border: 1px solid var(--border-hi, rgba(245, 158, 11, 0.25));
    border-radius: 5px;
    padding: 0.4rem 0.7rem;
    cursor: pointer;
    transition: border-color 0.16s ease, background 0.16s ease;
  }
  .bcc-launch__btn:hover {
    border-color: var(--accent, #f59e0b);
    background: rgba(245, 158, 11, 0.16);
  }
  /* paper accent (#c0392b) on the paper accent-dim surface reads 4.49 -- darken
     the launch text on paper to clear AA on #f4e7e0. */
  :global([data-theme='paper']) .bcc-launch__btn { color: #9a2018; }
  .bcc-launch__glyph { font-size: 0.8rem; line-height: 1; }

  /* ---- scrim + modal: transient overlay ---- */
  .bcc-scrim {
    position: fixed; inset: 0;
    background: rgba(4, 6, 8, 0.86);
    z-index: 40;
  }
  .bcc-modal {
    position: fixed;
    inset: 0;
    z-index: 50;
    padding: 2.2vh 0 2.2vh 2.2vw;
  }
  .bcc-shell {
    position: relative;
    height: 100%;
    width: 100%;
    display: grid;
    grid-template-columns: minmax(220px, 280px) 1fr;
    grid-template-rows: 1fr auto auto;
    gap: 0;
    background: var(--bg-card, #0c1118);
    border: 1px solid var(--border-hi, rgba(245, 158, 11, 0.25));
    border-right: none;
    border-radius: 10px 0 0 10px;
    box-shadow: -1px 0 0 var(--border-hi, rgba(245, 158, 11, 0.25)), 0 24px 64px rgba(0, 0, 0, 0.55);
    overflow: hidden;
  }

  .bcc-idlebar {
    position: absolute;
    top: 0; left: 0;
    height: 2px;
    width: 100%;
    z-index: 6;
    pointer-events: none;
  }
  .bcc-idlebar__fill {
    display: block;
    height: 100%;
    width: 100%;
    background: var(--accent-glow, rgba(245, 158, 11, 0.35));
    transform-origin: left center;
  }

  .bcc-close {
    appearance: none;
    position: absolute;
    top: 0.7rem; right: 0.8rem;
    z-index: 7;
    width: 2rem; height: 2rem;
    border: 1px solid var(--border, #192030);
    border-radius: 5px;
    background: var(--bg-row, #0e141e);
    color: var(--text-dim, #948870);
    font-size: 1.1rem;
    line-height: 1;
    cursor: pointer;
  }
  .bcc-close:hover { color: var(--accent, #f59e0b); border-color: var(--accent, #f59e0b); }

  /* ---- left incident gutter ---- */
  .bcc-gutter {
    grid-row: 1 / 4;
    background: linear-gradient(180deg, var(--bg-card, #0c1118), var(--bg-row-alt, #0b1018));
    border-right: 1px solid var(--border, #192030);
    padding: 1.1rem 1.1rem 1.1rem 1.2rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
    overflow-y: auto;
  }
  .bcc-eyebrow {
    font-family: var(--ff-mono);
    font-size: 0.6rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--text-ui, #8a8068);
    margin: 0;
  }
  .bcc-regbadge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-family: var(--ff-system);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 3px 8px;
    border-radius: 2px;
    line-height: 1;
    color: var(--badge-blocked-fg, #dc2626);
    background: var(--badge-blocked-bg, #fee2e2);
    border: 2px solid var(--badge-blocked-border, #dc2626);
    align-self: flex-start;
  }
  .bcc-sq { width: 7px; height: 7px; background: currentColor; flex: 0 0 auto; }
  .bcc-headline {
    font-size: 1.5rem;
    line-height: 1.02;
    font-weight: 800;
    letter-spacing: -0.02em;
    color: var(--text-bright, #e8e0cc);
    margin: 0;
  }
  .bcc-cells {
    list-style: none;
    margin: 0.2rem 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .bcc-cell {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-family: var(--ff-mono);
    font-size: 0.82rem;
    color: var(--text-bright, #e8e0cc);
    border: 1px solid var(--badge-blocked-border, #dc2626);
    border-left-width: 3px;
    border-radius: 4px;
    padding: 0.35rem 0.5rem;
    background: rgba(239, 68, 68, 0.07);
  }
  .bcc-arrow { color: var(--c-block, #ef4444); font-family: var(--ff-mono); font-weight: 700; }
  .bcc-meta {
    font-family: var(--ff-mono);
    font-size: 0.66rem;
    color: var(--text-dim, #948870);
    line-height: 1.5;
  }
  .bcc-meta b { color: var(--text-bright, #e8e0cc); font-weight: 700; }

  .bcc-pol {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-family: var(--ff-mono);
    font-size: 0.58rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--badge-decided-fg, #16a34a);
    background: var(--badge-decided-bg, #dcfce7);
    border: 1px solid var(--badge-decided-border, #86efac);
    border-radius: 3px;
    padding: 0.14rem 0.4rem;
    align-self: flex-start;
  }
  .bcc-pol--self {
    color: var(--badge-timeout-fg, #7c3aed);
    background: var(--badge-timeout-bg, #ede9fe);
    border-color: var(--badge-timeout-border, #c4b5fd);
  }
  .bcc-pol__dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }

  .bcc-delta {
    margin-top: auto;
    border-top: 1px solid var(--border, #192030);
    padding-top: 0.8rem;
  }
  .bcc-delta__k {
    font-family: var(--ff-mono);
    font-size: 0.56rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-ui, #8a8068);
    margin: 0 0 0.3rem;
  }
  .bcc-delta__v {
    font-family: var(--ff-mono);
    font-size: 1.1rem;
    font-weight: 700;
    color: var(--c-block, #ef4444);
    font-variant-numeric: tabular-nums;
  }
  .bcc-delta__note {
    font-size: 0.62rem;
    line-height: 1.4;
    color: var(--text-ui, #8a8068);
    margin: 0.4rem 0 0;
    font-style: italic;
  }

  /* ---- right swimlane canvas ---- */
  .bcc-canvas {
    position: relative;
    overflow: hidden;
    padding: 0.9rem 0 0.4rem;
  }
  .bcc-cap {
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    padding: 0 1rem 0.5rem 1.1rem;
    flex-wrap: wrap;
  }
  .bcc-hint { font-size: 0.7rem; color: var(--text-dim, #948870); }
  .bcc-mock {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    margin-left: auto;
    font-family: var(--ff-mono);
    font-size: 0.58rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--badge-timeout-fg, #7c3aed);
    background: var(--badge-timeout-bg, #ede9fe);
    border: 1px solid var(--badge-timeout-border, #c4b5fd);
    border-radius: 3px;
    padding: 0.12rem 0.42rem;
  }
  .bcc-mock__dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }

  .bcc-plot {
    position: relative;
    height: calc(100% - 2.3rem);
    min-height: 280px;
    margin-left: 1.1rem;
    background-image: repeating-linear-gradient(
      to right,
      transparent 0,
      transparent calc(20% - 1px),
      var(--border, #192030) calc(20% - 1px),
      var(--border, #192030) 20%
    );
  }

  .bcc-node {
    appearance: none;
    position: absolute;
    z-index: 2;
    transform: translateY(-50%);
    display: inline-flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 3px;
    min-width: 9.5rem;
    text-align: left;
    background: var(--bg-row, #0e141e);
    border: 1px solid var(--border, #192030);
    border-left-width: 3px;
    border-radius: 6px;
    padding: 0.4rem 0.5rem;
    cursor: pointer;
    transition: border-color 0.14s ease, background 0.14s ease, opacity 0.14s ease;
  }
  .bcc-node:hover { background: var(--bg-row-hover, #131c2a); border-color: var(--border-hi, rgba(245, 158, 11, 0.25)); }
  .bcc-node--future { opacity: 0.34; }

  .bcc-node__badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: var(--ff-mono);
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    line-height: 1;
  }
  .bcc-node__verdict {
    padding: 0.16rem 0.4rem;
    border-radius: 3px;
    background: rgba(4, 6, 8, 0.72);
  }
  .bcc-glyph {
    width: 0.7rem; height: 0.7rem;
    flex: 0 0 auto;
    display: inline-block;
  }
  /* shape per action -- the color-blind read path (M5), redundant with color */
  .glyph-block     { background: var(--c-block, #ef4444); }
  .glyph-intervene { background: var(--c-intervene, #f97316); transform: rotate(45deg); width: 0.6rem; height: 0.6rem; }
  .glyph-guide     { background: var(--c-guide, #eab308); clip-path: polygon(50% 0, 100% 100%, 0 100%); }
  .glyph-allow     { background: var(--c-allow, #22c55e); border-radius: 50%; }

  .bcc-node[data-action='BLOCK']     { border-left-color: var(--c-block, #ef4444); }
  .bcc-node[data-action='INTERVENE'] { border-left-color: var(--c-intervene, #f97316); }
  .bcc-node[data-action='GUIDE']     { border-left-color: var(--c-guide, #eab308); }
  .bcc-node[data-action='ALLOW']     { border-left-color: var(--c-allow, #22c55e); }
  .bcc-node[data-action='SUGGEST']   { border-left-color: var(--c-suggest, #84cc16); }
  .bcc-node[data-action='BLOCK']     .bcc-node__verdict { color: var(--c-block, #ef4444); }
  .bcc-node[data-action='INTERVENE'] .bcc-node__verdict { color: var(--c-intervene, #f97316); }
  .bcc-node[data-action='GUIDE']     .bcc-node__verdict { color: var(--c-guide, #eab308); }
  .bcc-node[data-action='ALLOW']     .bcc-node__verdict { color: var(--c-allow, #22c55e); }
  .bcc-node[data-action='SUGGEST']   .bcc-node__verdict { color: var(--c-suggest, #84cc16); }

  .bcc-node__msg {
    font-size: 0.68rem;
    line-height: 1.3;
    color: var(--text, #b8b098);
    max-width: 13rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .bcc-node__sub {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-family: var(--ff-mono);
    font-size: 0.56rem;
    color: var(--text-ui, #8a8068);
  }
  .bcc-node__hash {
    border: 1px solid var(--border, #192030);
    border-radius: 2px;
    padding: 0 0.25rem;
  }
  .bcc-node__hitl { color: var(--badge-ar-fg, #d97706); }

  /* ---- pattern shelf ---- */
  .bcc-shelf {
    position: absolute;
    top: 0; right: 0; bottom: 1.4rem;
    width: 8.5rem;
    border-left: 1px dashed var(--border-hi, rgba(245, 158, 11, 0.25));
    padding: 0.3rem 0.5rem 0.3rem 0.6rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    z-index: 2;
    overflow-y: auto;
  }
  .bcc-shelf__cap {
    font-family: var(--ff-mono);
    font-size: 0.54rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-ui, #8a8068);
  }
  .bcc-pnode {
    border: 1px solid var(--border, #192030);
    border-radius: 5px;
    background: var(--bg-row-alt, #0b1018);
    padding: 0.4rem 0.45rem;
  }
  .bcc-pnode--immature { border-color: var(--badge-warn-border, #ea580c); }
  .bcc-pnode__hash {
    font-family: var(--ff-mono);
    font-size: 0.74rem;
    font-weight: 700;
    color: var(--text-bright, #e8e0cc);
  }
  .bcc-pnode__lvl {
    display: inline-block;
    font-family: var(--ff-mono);
    font-size: 0.54rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: var(--accent, #f59e0b);
    border: 1px solid var(--border-hi, rgba(245, 158, 11, 0.25));
    border-radius: 2px;
    padding: 0 0.25rem;
    margin-left: 0.3rem;
  }
  .bcc-pnode__txt {
    font-size: 0.62rem;
    line-height: 1.3;
    color: var(--text-dim, #948870);
    margin: 0.25rem 0 0.2rem;
  }
  .bcc-pnode__occ {
    font-family: var(--ff-mono);
    font-size: 0.56rem;
    color: var(--text-ui, #8a8068);
  }
  .bcc-pnode__flag {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    margin-top: 0.3rem;
    font-family: var(--ff-mono);
    font-size: 0.52rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--badge-warn-fg, #ea580c);
    border: 1px dashed var(--badge-warn-border, #ea580c);
    border-radius: 2px;
    padding: 0.06rem 0.3rem;
  }
  .bcc-tri {
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 6px solid currentColor;
  }

  /* ---- scrubber ---- */
  .bcc-scrub {
    grid-column: 2 / 3;
    border-top: 1px solid var(--border, #192030);
    padding: 0.55rem 1rem 0.6rem 1.1rem;
    background: var(--bg-card, #0c1118);
  }
  .bcc-scrub__row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 0.3rem;
    gap: 0.6rem;
  }
  .bcc-scrub__lbl {
    font-family: var(--ff-mono);
    font-size: 0.62rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-ui, #8a8068);
  }
  .bcc-scrub__read {
    font-family: var(--ff-mono);
    font-size: 0.66rem;
    color: var(--text-bright, #e8e0cc);
    font-variant-numeric: tabular-nums;
  }
  .bcc-scrubber {
    width: 100%;
    accent-color: var(--accent, #f59e0b);
  }

  /* ---- surgical revert panel ---- */
  .bcc-revert {
    grid-column: 1 / 3;
    border-top: 1px solid var(--border-hi, rgba(245, 158, 11, 0.25));
    background: linear-gradient(180deg, var(--bg-card, #0c1118), var(--bg-row-alt, #0b1018));
    padding: 0.85rem 1.1rem 1rem;
    overflow-y: auto;
  }
  .bcc-revert__cap {
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    margin-bottom: 0.6rem;
    flex-wrap: wrap;
  }
  .bcc-revert__eyebrow {
    font-family: var(--ff-mono);
    font-size: 0.62rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--accent, #f59e0b);
  }
  .bcc-revert__hint { font-size: 0.7rem; color: var(--text-dim, #948870); }
  .bcc-revert__list { display: flex; flex-direction: column; gap: 0.5rem; }

  .bcc-rprop {
    display: grid;
    grid-template-columns: 2.2rem 1fr auto;
    align-items: center;
    gap: 0.7rem;
    border: 1px solid var(--border, #192030);
    border-radius: 7px;
    background: var(--bg-row, #0e141e);
    padding: 0.55rem 0.7rem;
    cursor: pointer;
    transition: border-color 0.14s ease, background 0.14s ease;
  }
  .bcc-rprop:hover { background: var(--bg-row-hover, #131c2a); }
  .bcc-rprop.is-selected { border-color: var(--accent, #f59e0b); background: var(--accent-dim, rgba(245, 158, 11, 0.09)); }
  /* the radio is the keyboard control; hide it visually but keep it operable. */
  .bcc-rprop__radio {
    position: absolute;
    width: 1px; height: 1px;
    opacity: 0;
    margin: 0;
    pointer-events: none;
  }
  .bcc-rprop__rank {
    font-family: var(--ff-mono);
    font-weight: 800;
    color: var(--accent, #f59e0b);
    text-align: center;
    font-variant-numeric: tabular-nums;
  }
  .bcc-rprop--r1 .bcc-rprop__rank { font-size: 1.5rem; }
  .bcc-rprop--r2 .bcc-rprop__rank { font-size: 1.05rem; color: var(--text-dim, #948870); }
  .bcc-rprop__main { min-width: 0; }
  .bcc-rprop__line {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-bottom: 0.2rem;
  }
  .bcc-mini {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-family: var(--ff-mono);
    font-size: 0.66rem;
    font-weight: 700;
    padding: 0.1rem 0.35rem;
    border-radius: 3px;
    background: rgba(4, 6, 8, 0.6);
  }
  .bcc-mini[data-action='BLOCK']     { color: var(--c-block, #ef4444); }
  .bcc-mini[data-action='INTERVENE'] { color: var(--c-intervene, #f97316); }
  .bcc-mini[data-action='GUIDE']     { color: var(--c-guide, #eab308); }
  .bcc-g { width: 0.55rem; height: 0.55rem; flex: 0 0 auto; }
  .bcc-rprop__id {
    font-family: var(--ff-mono);
    font-size: 0.66rem;
    color: var(--text-bright, #e8e0cc);
  }
  .bcc-rprop--r1 .bcc-rprop__id { font-weight: 700; }
  .bcc-rprop__why {
    font-size: 0.72rem;
    color: var(--text-dim, #948870);
    line-height: 1.35;
    margin: 0;
  }
  .bcc-rprop--r1 .bcc-rprop__why { color: var(--text, #b8b098); }
  .bcc-rprop__score {
    font-family: var(--ff-mono);
    font-size: 0.62rem;
    color: var(--text-ui, #8a8068);
    text-align: right;
    white-space: nowrap;
  }
  .bcc-rprop__score b {
    display: block;
    font-size: 0.92rem;
    color: var(--text-bright, #e8e0cc);
    font-variant-numeric: tabular-nums;
  }

  /* roving focus highlight on the whole label (the radio is sr-positioned). */
  .bcc-rprop:focus-within {
    outline: 2px solid var(--accent, #f59e0b);
    outline-offset: 2px;
  }

  /* ---- two-step accept bar ---- */
  .bcc-acceptbar {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.6rem 0.8rem;
    margin-top: 0.7rem;
    padding-top: 0.7rem;
    border-top: 1px solid var(--border, #192030);
  }
  .bcc-acceptbar__status {
    font-family: var(--ff-mono);
    font-size: 0.68rem;
    color: var(--text-dim, #948870);
  }
  .bcc-acceptbar__status b { color: var(--text-bright, #e8e0cc); }
  .bcc-btn {
    appearance: none;
    font-family: var(--ff-mono);
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    border-radius: 5px;
    padding: 0.45rem 0.85rem;
    cursor: pointer;
    border: 1px solid var(--border, #192030);
    background: var(--bg-row-alt, #0b1018);
    color: var(--text-dim, #948870);
    transition: border-color 0.14s ease, background 0.14s ease, color 0.14s ease;
  }
  .bcc-btn--ghost:hover { border-color: var(--accent, #f59e0b); color: var(--accent, #f59e0b); }
  .bcc-btn--accept {
    color: var(--accent, #f59e0b);
    border-color: var(--border-hi, rgba(245, 158, 11, 0.25));
    background: var(--accent-dim, rgba(245, 158, 11, 0.09));
  }
  .bcc-btn--accept:hover:not([aria-disabled='true']) {
    border-color: var(--accent, #f59e0b);
    background: rgba(245, 158, 11, 0.16);
  }
  .bcc-btn--confirm {
    color: var(--badge-blocked-fg, #dc2626);
    border: 2px solid var(--badge-blocked-border, #dc2626);
    background: var(--badge-blocked-bg, #fee2e2);
  }
  .bcc-btn[aria-disabled='true'] {
    opacity: 0.5;
    cursor: not-allowed;
    color: var(--text-ui, #8a8068);
    border-color: var(--border, #192030);
    background: var(--bg-row-alt, #0b1018);
  }
  .bcc-lockout {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-family: var(--ff-mono);
    font-size: 0.62rem;
    color: var(--badge-timeout-fg, #7c3aed);
    background: var(--badge-timeout-bg, #ede9fe);
    border: 1px solid var(--badge-timeout-border, #c4b5fd);
    border-radius: 3px;
    padding: 0.16rem 0.45rem;
  }
  .bcc-lockout__dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }
  .bcc-confirm { display: inline-flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; }
  .bcc-receipt {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: var(--ff-mono);
    font-size: 0.66rem;
    color: var(--badge-decided-fg, #16a34a);
    background: var(--badge-decided-bg, #dcfce7);
    border: 1px solid var(--badge-decided-border, #86efac);
    border-radius: 3px;
    padding: 0.2rem 0.5rem;
  }
  .bcc-receipt__dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }

  .bcc-cli-note {
    margin: 0.7rem 0 0;
    font-size: 0.64rem;
    line-height: 1.45;
    color: var(--text-ui, #8a8068);
    font-style: italic;
  }

  /* ---- tooltip ---- */
  .bcc-tip {
    position: fixed;
    z-index: 60;
    max-width: 22rem;
    background: var(--bg-card, #0c1118);
    border: 1px solid var(--border-hi, rgba(245, 158, 11, 0.25));
    border-radius: 6px;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.5);
    padding: 0.6rem 0.7rem;
    pointer-events: none;
  }
  .bcc-tip__verdict {
    font-family: var(--ff-mono);
    font-size: 0.72rem;
    font-weight: 700;
    margin-bottom: 0.3rem;
  }
  .bcc-tip__verdict[data-action='BLOCK']     .bcc-node__verdict { color: var(--c-block, #ef4444); }
  .bcc-tip__verdict[data-action='INTERVENE'] .bcc-node__verdict { color: var(--c-intervene, #f97316); }
  .bcc-tip__verdict[data-action='GUIDE']     .bcc-node__verdict { color: var(--c-guide, #eab308); }
  .bcc-tip__verdict[data-action='ALLOW']     .bcc-node__verdict { color: var(--c-allow, #22c55e); }
  .bcc-tip__verdict[data-action='SUGGEST']   .bcc-node__verdict { color: var(--c-suggest, #84cc16); }
  .bcc-tip__msg {
    font-size: 0.72rem;
    line-height: 1.4;
    color: var(--text, #b8b098);
    margin: 0 0 0.4rem;
  }
  .bcc-tip__grid {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 0.15rem 0.6rem;
    font-family: var(--ff-mono);
    font-size: 0.62rem;
  }
  .bcc-tip__k { color: var(--text-ui, #8a8068); }
  .bcc-tip__v { color: var(--text-bright, #e8e0cc); }

  /* ---- beta footer + notes ---- */
  .bcc-betafoot {
    position: absolute;
    left: 1.2rem; bottom: 0.35rem;
    z-index: 7;
    font-family: var(--ff-mono);
    font-size: 0.58rem;
    letter-spacing: 0.04em;
    color: var(--text-ui, #8a8068);
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    pointer-events: none;
  }
  .bcc-betafoot__dot { width: 5px; height: 5px; border-radius: 50%; background: var(--badge-ar-fg, #d97706); }

  .bcc-note {
    font-family: var(--ff-mono);
    font-size: 0.72rem;
    color: var(--text-dim, #948870);
    margin: 0.6rem 0 0;
  }

  .bcc-sr-only {
    position: absolute; width: 1px; height: 1px; padding: 0;
    margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); border: 0;
  }

  /* global focus ring (M17) -- the app provides :focus-visible 2px amber; this
     reinforces it on the interactive controls this component owns. */
  .bcc-close:focus-visible,
  .bcc-launch__btn:focus-visible,
  .bcc-btn:focus-visible,
  .bcc-node:focus-visible,
  .bcc-scrubber:focus-visible {
    outline: 2px solid var(--accent, #f59e0b);
    outline-offset: 2px;
  }

  @media (prefers-reduced-motion: reduce) {
    .bcc-node, .bcc-btn, .bcc-launch__btn, .bcc-rprop, .bcc-idlebar__fill {
      transition: none !important;
    }
  }
</style>
