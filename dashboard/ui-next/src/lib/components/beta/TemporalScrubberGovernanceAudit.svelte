<!--
  TemporalScrubberGovernanceAudit.svelte -- BETA feature
  "temporal-scrubber-governance-audit" (#47): Temporal Scrubber -- governance
  policy archaeology via replay diff.

  WHAT IT IS
    A focus-trapped MODAL (M2 escalation-foreground pattern -- a transient
    overlay, NEVER a fourth persistent frame) that does policy archaeology by
    REPLAY DIFF. The operator opens it from a low-emphasis "Replay window"
    launcher affordance (the component's own resting chip -- collision-free, no
    edit to Frame A), then:
      Step 1  picks ONE governed (NON-SM) session (a polarity-locked picker --
              SM-self is never listed; the picker shows an "excluded N self"
              tally so self-exclusion is a VISIBLE feature, G2).
      Step 2  brackets two points on the decision timeline with a two-handle
              scrubber rail (window A "then" vs window B "now").
      Step 3  reads ONE replay-diff (a single post-hoc GET, M18) and paints two
              mirrored panes sharing a center confidence-delta HEAT-SPINE; each
              spine segment is tinted by |delta| AND carries the literal signed
              numeral + a VERDICT CHANGED / same-verdict text (M4 -- color is
              never the sole signal).

  v1 SCOPE (CONSTRAINED ADDITIVE)
    v1 DIFFS THE STORED DECISION STREAM. The two window columns are read from the
    additive GET /api/decisions/replay-diff endpoint over EXISTING recorded
    gov.db decisions+messages (polarity-filtered, SM-self excluded server-side).
    The LIVE policy-version store (a policy_snapshots table + a governance.py
    config-mutation hook) is DEFERRED to a documented "from CLI" affordance (the
    amber Build-gated footnote in the modal foot). This component spawns NOTHING,
    re-evaluates NOTHING, mints NO bus envelope, and touches NO FROZEN surface.

  BETA GATE (load-bearing)
    The ENTIRE component is wrapped in
    {#if $betaFlags['temporal-scrubber-governance-audit']}. When the flag is OFF
    it renders NOTHING and registers NO fetch / poller / SSE / timer -- zero
    runtime cost. The flag defaults OFF (lib/beta/registry.js); the operator
    flips it in Settings > BETA features. There is no SSE / poller here at all:
    the diff is read once per Run press via a single post-hoc GET (M18). The
    session picker is fetched on demand only when the modal opens.

  POLARITY (G2/M15): the on-demand reads go to additive endpoints that exclude
    SM-self server-side (project_slug NOT IN the SM slug set AND session_id !=
    SM_OWN_SESSION_ID). The picker NEVER lists SM-self and renders the dropped
    self tally. When the endpoints are absent or empty (fresh DB) the modal falls
    back to realistic mock data (TemporalScrubberGovernanceAudit.data.js) so it
    is always inspectable; the mock state is labelled in the source line.

  ADR-18 MUST floor honoured here:
    - M2/M3: never auto-foregrounds; the launcher chip + modal are operator-
      invoked only; a transient modal, never a fourth frame. Closing returns
      focus to the launcher (Frame A presence is never regressed).
    - M4 (paired label+color): every verdict renders its LITERAL text beside any
      color; the heat-spine writes the literal signed numeral + VERDICT CHANGED /
      same-verdict; the static-rule flag writes "STATIC RULE"; color is never the
      sole signal.
    - M16 (domain-agnostic): no monitored-project vocabulary; verdict + layer +
      model band + pattern hash are governance taxonomy; project identity arrives
      from server data.
    - M17 (a11y): launcher is a real <button> with aria-haspopup; the modal is
      role=dialog aria-modal with a labelled heading, Escape-to-close, focus
      moved in on open + restored on close, a focus trap, a polite aria-live
      summary, the two-handle scrubber is arrow-key nudgeable, and the 2px amber
      focus ring applies. Reduced motion honoured.
    - M18: pure post-hoc GET; never on the verdict hot path.

  ASCII-only (cp1252-safe): dash rendered as "--". No smart quotes / em-dash.
-->
<script>
  import { onMount, tick } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import {
    verdictBadge,
    layerStr,
    confStr,
    signedConf,
    normalizeReplayDiff,
    normalizeSessions,
    mockSessions,
    mockReplayDiff,
    windowLabel,
  } from './TemporalScrubberGovernanceAudit.data.js';

  const FLAG_KEY = 'temporal-scrubber-governance-audit';

  // -- gate (default OFF) -----------------------------------------------------
  // Reactive flag read. Everything below is a no-op while OFF: nothing is
  // rendered (the {#if enabled} guard), no fetch / poller / SSE / timer runs.
  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // -- modal lifecycle + focus contract ---------------------------------------
  let open = false;
  /** @type {HTMLDivElement|null} */
  let modalEl = null;
  /** @type {HTMLButtonElement|null} */
  let launchEl = null;
  /** @type {Element|null} */
  let prevFocus = null;

  // -- step state (1: pick, 2: bracket, 3: diff) ------------------------------
  let scopeConfirmed = false;
  let selectedSessionId = '';
  let ranDiff = false;
  let loadingDiff = false;
  let usedMockData = false;

  /** @type {ReturnType<typeof normalizeSessions>} */
  let sessions = [];
  let excludedSelf = 0;

  /** @type {ReturnType<typeof mockReplayDiff>|null} */
  let diff = null;

  // two-handle scrubber positions (0..100 across an 08:00-15:00 span).
  let handleA = 8;
  let handleB = 70;

  // -- derived ----------------------------------------------------------------
  $: lo = Math.min(handleA, handleB);
  $: hi = Math.max(handleA, handleB);
  $: bandLeft = lo;
  $: bandWidth = Math.max(0, hi - lo);
  $: labelA = windowLabel(handleA);
  $: labelB = windowLabel(handleB);

  $: rows = diff && Array.isArray(diff.rows) ? diff.rows : [];
  $: changedCount = diff ? diff.changed_count : 0;
  $: rowCount = diff ? diff.row_count : 0;

  $: scopeLabel = (() => {
    const s = sessions.find((x) => x.session_id === selectedSessionId);
    if (!s) return selectedSessionId || '--';
    const slug = (s.project_slug || '').trim();
    return (slug !== '' ? slug + ' / ' : '') + s.session_id;
  })();

  $: summaryText = ranDiff
    ? `Replay diff: ${changedCount} verdict${changedCount === 1 ? '' : 's'} changed of ${rowCount} row${rowCount === 1 ? '' : 's'} compared. Confidence movement is on the center spine (signed numeral plus tint).`
    : '';

  // -- network (self-contained; degrades to mock so the modal is testable) ----
  // These reads are intentionally local fetches (mirroring the api.js degrade
  // idiom) so the component is buildable + testable WITHOUT a shared-file edit.
  // The canonical api.js helper sources are returned as DATA for promotion.
  async function fetchJSON(url) {
    try {
      const res = await fetch(url, {
        method: 'GET',
        headers: { Accept: 'application/json' },
        cache: 'no-store',
      });
      if (!res.ok) return null;
      const data = await res.json();
      return data && typeof data === 'object' ? data : null;
    } catch {
      return null;
    }
  }

  /**
   * Load the polarity-filtered NON-SM session picker list (once per modal open).
   * Best-effort: any failure / empty result degrades to the mock picker rows so
   * the modal is always usable. The picker NEVER lists SM-self (server-excluded).
   */
  async function loadSessions() {
    const raw = await fetchJSON('/api/decisions/replay-diff/sessions');
    const norm = normalizeSessions(raw);
    if (norm.length) {
      sessions = norm;
      excludedSelf = Number(raw && raw.excluded_self) || 0;
    } else {
      const m = mockSessions();
      sessions = m.sessions;
      excludedSelf = m.excluded_self;
    }
  }

  /**
   * Run ONE replay-diff read for the confirmed scope + bracketed windows. A
   * single post-hoc GET (M18). Degrades to the realistic mock so the corridor is
   * always paintable; the mock state is labelled (never silent).
   */
  async function runDiff() {
    if (!scopeConfirmed || loadingDiff) return;
    loadingDiff = true;
    ranDiff = true;
    const url =
      '/api/decisions/replay-diff' +
      `?session_id=${encodeURIComponent(selectedSessionId)}` +
      `&a=${encodeURIComponent(String(lo))}` +
      `&b=${encodeURIComponent(String(hi))}`;
    const raw = await fetchJSON(url);
    const norm = normalizeReplayDiff(raw);
    if (norm) {
      diff = norm;
      usedMockData = false;
    } else {
      diff = mockReplayDiff(selectedSessionId, labelA, labelB);
      usedMockData = true;
    }
    loadingDiff = false;
    await tick();
    // scroll the freshly painted corridor into view for keyboard + sighted use.
    const corridor = modalEl && modalEl.querySelector('.tsg-corridor');
    if (corridor && corridor.scrollIntoView) corridor.scrollIntoView({ block: 'nearest' });
  }

  // -- step 1: picker ---------------------------------------------------------
  async function confirmScope() {
    if (!selectedSessionId) return;
    scopeConfirmed = true;
    // reset any prior result so the operator brackets + runs afresh.
    ranDiff = false;
    diff = null;
    await tick();
    const h = modalEl && modalEl.querySelector('#tsg-handle-a');
    if (h && h.focus) h.focus();
  }

  // -- step 2: scrubber (no fetch while dragging -- a Run press is explicit) ---
  function onHandleA(e) {
    handleA = Number(e.currentTarget.value);
  }
  function onHandleB(e) {
    handleB = Number(e.currentTarget.value);
  }

  // -- modal open / close + focus trap ----------------------------------------
  async function openModal() {
    if (!enabled || open) return;
    prevFocus = typeof document !== 'undefined' ? document.activeElement : null;
    open = true;
    // reset to step 1 each open (the polarity gate is re-armed every time).
    scopeConfirmed = false;
    selectedSessionId = '';
    ranDiff = false;
    diff = null;
    usedMockData = false;
    await loadSessions();
    await tick();
    const sel = modalEl && modalEl.querySelector('#tsg-session-select');
    if (sel && sel.focus) sel.focus();
  }
  function closeModal() {
    if (!open) return;
    open = false;
    const target = prevFocus && /** @type {any} */ (prevFocus).focus ? prevFocus : launchEl;
    /** @type {HTMLElement|null} */ (target)?.focus?.();
    prevFocus = null;
  }
  function focusables() {
    if (!modalEl) return [];
    return Array.prototype.slice
      .call(
        modalEl.querySelectorAll(
          'button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      )
      .filter((el) => el.offsetParent !== null);
  }
  function onModalKeydown(e) {
    if (e.key === 'Escape') {
      e.preventDefault();
      closeModal();
      return;
    }
    if (e.key === 'Tab') {
      const f = focusables();
      if (!f.length) return;
      const first = f[0];
      const last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  // Defense-in-depth: if the flag flips OFF while the modal is open, close it so
  // nothing lingers (the {#if enabled} guard already unmounts everything).
  $: if (!enabled && open) open = false;

  // The window bridge ("temporal-scrubber:open") lets the real composition drive
  // the modal WITHOUT editing Frame A (mirrors the DecisionOracle precedent + the
  // approved mockup's documented bridge). The +keydown trap is wired the same
  // way. Both are registered ONLY while the flag is ON: the component is
  // {#if $betaFlags[...]}-gated at its App.svelte mount, so onMount runs (and
  // these listeners attach) only when ON; the OFF flag leaves ZERO listeners /
  // timers / fetches (the BETA-gate contract). Event-driven, never a poller.
  function onBridgeOpen() {
    if (!enabled) return;
    openModal();
  }
  function onWindowKeydown(e) {
    if (open) onModalKeydown(e);
  }
  onMount(() => {
    if (typeof window === 'undefined') return;
    window.addEventListener('temporal-scrubber:open', onBridgeOpen);
    window.addEventListener('keydown', onWindowKeydown);
    return () => {
      window.removeEventListener('temporal-scrubber:open', onBridgeOpen);
      window.removeEventListener('keydown', onWindowKeydown);
    };
  });
</script>

{#if enabled}
  <!-- LAUNCHER: the only resting affordance. A real <button>; opens the modal.
       Present only while the flag is ON (the {#if enabled} guard). Low emphasis,
       theme tokens only -- collision-free (no edit to Frame A). -->
  <button
    bind:this={launchEl}
    class="tsg-launch"
    type="button"
    aria-haspopup="dialog"
    aria-expanded={open}
    aria-controls="tsg-modal"
    on:click={openModal}
  >
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" class="tsg-launch__glyph">
      <circle cx="12" cy="12" r="9"></circle>
      <path d="M12 7v5l3 2"></path>
    </svg>
    Replay window
    <span class="tsg-launch__beta">BETA</span>
  </button>

  {#if open}
    <!-- SCRIM: click-out closes. Not a focus target. -->
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div
      class="tsg-scrim"
      role="presentation"
      on:click={(e) => {
        if (e.target === e.currentTarget) closeModal();
      }}
    >
      <!-- MODAL: role=dialog aria-modal; labelled heading; Escape + focus trap. -->
      <div
        id="tsg-modal"
        class="tsg-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="tsg-title"
        aria-describedby="tsg-beta"
        bind:this={modalEl}
      >
        <div class="tsg-head">
          <div class="tsg-head__row">
            <h2 id="tsg-title" class="tsg-title">
              <span class="tsg-title__glyph" aria-hidden="true">&#9201;</span>
              Temporal Scrubber -- replay-diff
            </h2>
            <button
              class="tsg-x"
              type="button"
              aria-label="Close without running (Esc)"
              on:click={closeModal}
            >&times;</button>
          </div>
          <span class="tsg-beta" id="tsg-beta">
            <span class="tsg-beta__pill">BETA -- default OFF, toggled in Settings &gt; BETA features</span>
            &nbsp;--&nbsp; reads existing decisions + messages tables (v1 Phase 1)
            {#if usedMockData}<span class="tsg-beta__mock"> -- DEMO DATA (live gov.db unavailable)</span>{/if}
          </span>
        </div>

        <!-- STEP 1: polarity-locked session picker (MANDATED before anything). -->
        <div class="tsg-picker" class:is-locked={scopeConfirmed}>
          <div class="tsg-picker__head">
            <h3 class="tsg-picker__h">Step 1 -- pick a governed session</h3>
            <span class="tsg-poltag" title="Self-exclusion is a visible feature, not invisible plumbing">
              <span class="tsg-poltag__dot" aria-hidden="true"></span>
              polarity-locked -- excluded <b>{excludedSelf}</b> self
            </span>
          </div>

          {#if !scopeConfirmed}
            <div class="tsg-picker__row">
              <label class="tsg-sr-only" for="tsg-session-select">Governed session to inspect (non-SM only)</label>
              <select
                id="tsg-session-select"
                class="tsg-select"
                aria-describedby="tsg-pick-hint"
                bind:value={selectedSessionId}
              >
                <option value="">-- choose a non-SM session --</option>
                {#each sessions as s (s.session_id)}
                  <option value={s.session_id}>{s.label}</option>
                {/each}
              </select>
              <button
                class="tsg-confirm"
                type="button"
                disabled={selectedSessionId === ''}
                on:click={confirmScope}
              >Confirm scope</button>
              <span class="tsg-pick-hint" id="tsg-pick-hint">
                SM-self is never listed -- the tool refuses to show you a mirror.
              </span>
            </div>
          {:else}
            <div class="tsg-locked-note">
              <span class="ar-badge ar-observing" role="status" title="scope locked" aria-label="scope locked">
                <span class="ar-dot" aria-hidden="true"></span><span>SCOPE LOCKED</span>
              </span>
              target <b class="tsg-locked-target">{scopeLabel}</b> -- the scrubber below is now active.
            </div>
          {/if}
        </div>

        <!-- STEP 2: the signature two-handle temporal scrubber rail. -->
        <div class="tsg-scrub" class:is-active={scopeConfirmed} aria-label="Step 2 -- bracket two time windows">
          <div class="tsg-scrub__head">
            <span class="tsg-scrub__h">Step 2 -- bracket window A and window B</span>
            <span class="tsg-scrub__readout">
              <span class="tsg-htag">A</span> <b>{labelA}</b>
              &nbsp;vs&nbsp;
              <span class="tsg-htag">B</span> <b>{labelB}</b>
            </span>
          </div>
          <div class="tsg-rail-wrap">
            <div class="tsg-rail">
              <div class="tsg-band" style={`left:${bandLeft}%; width:${bandWidth}%;`}></div>
            </div>
            <input
              id="tsg-handle-a"
              class="tsg-handle"
              type="range"
              min="0"
              max="100"
              value={handleA}
              disabled={!scopeConfirmed}
              aria-label="Window A bracket"
              aria-valuetext={`Window A near ${labelA}`}
              on:input={onHandleA}
            />
            <input
              id="tsg-handle-b"
              class="tsg-handle"
              type="range"
              min="0"
              max="100"
              value={handleB}
              disabled={!scopeConfirmed}
              aria-label="Window B bracket"
              aria-valuetext={`Window B near ${labelB}`}
              on:input={onHandleB}
            />
            <div class="tsg-bounds">
              <span class="tsg-bound">08:00Z (session start)</span>
              <span class="tsg-bound">15:00Z (now)</span>
            </div>
          </div>
          <button
            class="tsg-run"
            type="button"
            disabled={!scopeConfirmed || loadingDiff}
            on:click={runDiff}
          >{loadingDiff ? 'Running...' : 'Run replay-diff (one read)'}</button>
        </div>

        <!-- STEP 3: the two mirrored panes + center confidence-delta heat-spine. -->
        {#if ranDiff && diff}
          <div class="tsg-corridor" aria-label="Step 3 -- replay-diff result">
            <div class="tsg-summary" role="status" aria-live="polite">{summaryText}</div>

            <div class="tsg-cols">
              <div class="tsg-pane-head">Window A -- {diff.window_a_label}</div>
              <div class="tsg-spine-head">conf delta</div>
              <div class="tsg-pane-head right">Window B -- {diff.window_b_label}</div>

              {#each rows as row (row.key)}
                {@const ba = verdictBadge(row.window_a.action)}
                {@const bb = verdictBadge(row.window_b.action)}
                {@const aStatic = row.window_a.matched_hash.indexOf('static:') === 0}
                {@const bStatic = row.window_b.matched_hash.indexOf('static:') === 0}
                <div class="tsg-row" class:is-changed={row.delta.verdict_changed}>
                  <!-- LEFT: window A (then) -->
                  <div class="tsg-cell">
                    <div class="tsg-cell__line">
                      <span class="ar-badge ar-{ba.variant}" role="status" title={'window A verdict ' + ba.label} aria-label={'window A verdict ' + ba.label}>
                        <span class="ar-dot" aria-hidden="true"></span><span>{ba.label}</span>
                      </span>
                      {#if aStatic}
                        <span class="ar-badge ar-static" role="status" title="static rule" aria-label="static rule">
                          <span class="ar-dot" aria-hidden="true"></span><span>STATIC RULE</span>
                        </span>
                      {/if}
                    </div>
                    <span class="tsg-cell__content" title={row.window_a.content}>{row.window_a.content}</span>
                    <span class="tsg-cell__meta">
                      {layerStr(row.window_a.layer)}{row.window_a.model ? ' -- model ' + row.window_a.model : ''} --
                      <span class="tsg-cell__conf">conf {confStr(row.window_a.confidence)}</span>
                      {row.window_a.ts ? ' -- ' + row.window_a.ts : ''}
                    </span>
                  </div>

                  <!-- CENTER: the heat-spine (tint + LITERAL signed numeral, M4) -->
                  <div class="tsg-spine {row.delta.band}" title={'confidence delta ' + signedConf(row.delta.confidence_delta) + (row.delta.verdict_changed ? '; verdict changed' : '')}>
                    <span class="tsg-spine__num">{signedConf(row.delta.confidence_delta)}</span>
                    {#if row.delta.verdict_changed}
                      <span class="tsg-spine__chg">
                        <span class="tsg-spine__bracket" aria-hidden="true">[ ]</span> VERDICT CHANGED
                      </span>
                    {:else}
                      <span class="tsg-spine__same">same verdict</span>
                    {/if}
                  </div>

                  <!-- RIGHT: window B (now) -->
                  <div class="tsg-cell right">
                    <div class="tsg-cell__line">
                      <span class="ar-badge ar-{bb.variant}" role="status" title={'window B verdict ' + bb.label} aria-label={'window B verdict ' + bb.label}>
                        <span class="ar-dot" aria-hidden="true"></span><span>{bb.label}</span>
                      </span>
                      {#if bStatic}
                        <span class="ar-badge ar-static" role="status" title="static rule" aria-label="static rule">
                          <span class="ar-dot" aria-hidden="true"></span><span>STATIC RULE</span>
                        </span>
                      {/if}
                    </div>
                    <span class="tsg-cell__content" title={row.window_b.content}>{row.window_b.content}</span>
                    <span class="tsg-cell__meta">
                      {layerStr(row.window_b.layer)}{row.window_b.model ? ' -- model ' + row.window_b.model : ''} --
                      <span class="tsg-cell__conf">conf {confStr(row.window_b.confidence)}</span>
                      {row.window_b.ts ? ' -- ' + row.window_b.ts : ''}
                    </span>
                  </div>
                </div>
              {/each}
            </div>

            <!-- source label: ALWAYS a literal text label (mock vs live, M4). -->
            <p class="tsg-source" data-mock={usedMockData}>
              {usedMockData
                ? 'SAMPLE DATA -- no governed decisions in gov.db for this scope/window; rendering a deterministic representative diff.'
                : 'LIVE -- diffed from recorded gov.db decisions (polarity-filtered, SM-self excluded).'}
            </p>
          </div>
        {/if}

        <!-- FOOTER: scope recap + the deferred-policy-store "from CLI" footnote. -->
        <div class="tsg-foot">
          <span class="tsg-foot__info">
            {#if !scopeConfirmed}
              Scope <b>not yet confirmed</b> -- pick a governed session to enable the scrubber.
            {:else if !ranDiff}
              Scope <b>{scopeLabel}</b> confirmed -- bracket A and B, then run the diff.
            {:else}
              Replay-diff painted -- <b>{changedCount}</b> verdict{changedCount === 1 ? '' : 's'} changed of {rowCount}. One read fired (M18 post-hoc).
            {/if}
          </span>
          <span class="tsg-foot__spacer"></span>
          <button class="tsg-btn" type="button" on:click={closeModal}>Close</button>
        </div>

        <!-- the standing amber "policy-version store deferred" footnote. -->
        <div class="tsg-gatenote" role="note">
          <span class="ar-badge ar-warn" role="status" title="policy store deferred" aria-label="policy-version store deferred to CLI">
            <span class="ar-dot" aria-hidden="true"></span><span>WARN</span>
          </span>
          <span class="tsg-gatenote__text">
            <b>Policy-version store deferred.</b> v1 diffs the <b>stored decision
            stream</b> read-only (additive endpoint over existing tables; no new
            table, no governance.py hook, no FROZEN-surface touch). The live
            policy-mutation timeline (a policy_snapshots table populated on a
            config-change hook) runs <b>from the CLI</b>, not in this dashboard,
            and remains behind a future ADR-18 amendment.
          </span>
        </div>
      </div>
    </div>
  {/if}
{/if}

<style>
  /* ---- launcher chip (low emphasis, theme tokens only) -------------------- */
  .tsg-launch {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-family: var(--ff-system, system-ui, sans-serif);
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.02em;
    color: var(--calm-ink-quiet, var(--text-dim));
    background: transparent;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: 5px;
    padding: 6px 11px;
    cursor: pointer;
    transition: color 0.18s, border-color 0.18s, background 0.18s;
  }
  .tsg-launch:hover {
    color: var(--calm-ink-loud, var(--text-bright));
    border-color: var(--calm-hairline-hi, var(--border-hi));
    background: var(--calm-accent-wash, var(--accent-dim));
  }
  .tsg-launch__glyph { width: 14px; height: 14px; flex: 0 0 auto; }
  .tsg-launch__beta {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: #92400e;
    background: var(--badge-ar-bg, #fef3c7);
    border: 1px solid var(--badge-ar-border, #d97706);
    border-radius: 4px;
    padding: 0 5px;
  }

  /* ---- scrim + modal shell ------------------------------------------------ */
  .tsg-scrim {
    position: fixed;
    inset: 0;
    background: rgba(4, 6, 9, 0.74);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 22px;
    z-index: 60;
  }
  .tsg-modal {
    width: min(1020px, 100%);
    max-height: calc(100vh - 44px);
    overflow-y: auto;
    background: var(--calm-surface-card, var(--bg-card));
    border: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi));
    border-radius: 12px;
    box-shadow: 0 24px 64px rgba(0, 0, 0, 0.6);
    display: flex;
    flex-direction: column;
    color: var(--calm-ink, var(--text));
    font-family: var(--ff-system, system-ui, sans-serif);
  }
  :global(html[data-motion='allow']) .tsg-modal { animation: tsgRise 140ms ease-out; }
  @keyframes tsgRise { from { transform: translateY(8px); opacity: 0; } to { transform: none; opacity: 1; } }

  .tsg-head {
    padding: 16px 22px 13px;
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
  }
  .tsg-head__row { display: flex; align-items: center; gap: 12px; }
  .tsg-title {
    margin: 0;
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 0.01em;
    color: var(--calm-ink-loud, var(--text-bright));
  }
  .tsg-title__glyph { color: var(--calm-accent, var(--accent)); }
  .tsg-x {
    margin-left: auto;
    background: transparent;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    color: var(--calm-ink-quiet, var(--text-dim));
    border-radius: 5px;
    width: 28px;
    height: 28px;
    cursor: pointer;
    font-size: 15px;
    line-height: 1;
  }
  .tsg-beta { display: block; margin-top: 7px; font-size: 11px; color: var(--calm-ink-quiet, var(--text-dim)); }
  .tsg-beta__pill { color: #9a3412; font-weight: 700; letter-spacing: 0.04em; }
  .tsg-beta__mock { font-family: var(--font-d, var(--ff-mono)); color: var(--badge-warn-fg, #ea580c); }

  /* ---- step 1: polarity-locked picker ------------------------------------- */
  .tsg-picker {
    margin: 14px 22px 0;
    padding: 12px 14px;
    border: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi));
    border-radius: 8px;
    background: var(--calm-surface-row-alt, var(--bg-row-alt));
  }
  .tsg-picker__head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 9px; }
  .tsg-picker__h {
    margin: 0;
    font-size: 10.5px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui));
    font-weight: 700;
  }
  .tsg-poltag {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10.5px;
    color: var(--calm-ink-quiet, var(--text-dim));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: 3px;
    padding: 2px 7px;
  }
  .tsg-poltag b { color: var(--calm-accent, var(--accent)); font-weight: 700; }
  .tsg-poltag__dot { width: 6px; height: 6px; border-radius: 50%; background: var(--calm-accent, var(--accent)); flex: 0 0 auto; }
  .tsg-picker__row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .tsg-select {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 12.5px;
    color: var(--calm-ink-loud, var(--text-bright));
    background: var(--calm-surface-row, var(--bg-row));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: 5px;
    padding: 7px 10px;
    min-width: 240px;
    cursor: pointer;
  }
  .tsg-pick-hint { font-size: 11.5px; color: var(--calm-ink-quiet, var(--text-dim)); font-style: italic; }
  .tsg-confirm {
    font-size: 12.5px;
    font-weight: 700;
    letter-spacing: 0.02em;
    color: #1a1206;
    background: var(--calm-accent, var(--accent));
    border: var(--hairline, 1px) solid var(--badge-ar-border, #d97706);
    border-radius: 5px;
    padding: 7px 14px;
    cursor: pointer;
  }
  .tsg-confirm:disabled {
    background: var(--calm-surface-row-alt, var(--bg-row-alt));
    color: var(--calm-ink-chrome, var(--text-ui));
    border-color: var(--calm-hairline, var(--border));
    cursor: not-allowed;
  }
  .tsg-locked-note { display: flex; align-items: center; gap: 8px; font-size: 11.5px; color: var(--calm-ink-quiet, var(--text-dim)); }
  .tsg-locked-target { color: var(--calm-accent, var(--accent)); font-family: var(--font-d, var(--ff-mono)); }

  /* ---- step 2: scrubber rail ---------------------------------------------- */
  .tsg-scrub {
    margin: 14px 22px 0;
    opacity: 0.45;
    pointer-events: none;
    transition: opacity 0.2s;
  }
  .tsg-scrub.is-active { opacity: 1; pointer-events: auto; }
  .tsg-scrub__head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; margin-bottom: 8px; }
  .tsg-scrub__h {
    font-size: 10.5px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui));
    font-weight: 700;
  }
  .tsg-scrub__readout { font-family: var(--font-d, var(--ff-mono)); font-size: 11.5px; color: var(--calm-ink-quiet, var(--text-dim)); }
  .tsg-scrub__readout b { color: var(--calm-ink-loud, var(--text-bright)); }
  .tsg-htag {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    font-weight: 700;
    color: #1a1206;
    background: var(--calm-accent, var(--accent));
    border-radius: 3px;
    padding: 1px 5px;
  }
  .tsg-rail-wrap { position: relative; padding: 18px 4px 6px; }
  .tsg-rail {
    position: relative;
    height: 4px;
    border-radius: 2px;
    background: linear-gradient(90deg, var(--calm-hairline, var(--border)), var(--calm-hairline-hi, var(--border-hi)), var(--calm-hairline, var(--border)));
  }
  .tsg-band {
    position: absolute;
    top: 0;
    bottom: 0;
    background: var(--calm-accent-wash, var(--accent-dim));
    border-left: 2px solid var(--calm-accent, var(--accent));
    border-right: 2px solid var(--calm-accent, var(--accent));
  }
  .tsg-handle {
    position: absolute;
    left: 0;
    right: 0;
    top: 8px;
    width: 100%;
    margin: 0;
    background: transparent;
    pointer-events: none;
    -webkit-appearance: none;
    appearance: none;
  }
  .tsg-handle::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 16px;
    height: 22px;
    border-radius: 3px;
    background: var(--calm-accent, var(--accent));
    border: 1px solid #1a1206;
    cursor: ew-resize;
    pointer-events: auto;
  }
  .tsg-handle::-moz-range-thumb {
    width: 16px;
    height: 22px;
    border-radius: 3px;
    background: var(--calm-accent, var(--accent));
    border: 1px solid #1a1206;
    cursor: ew-resize;
    pointer-events: auto;
  }
  .tsg-bounds { display: flex; justify-content: space-between; margin-top: 10px; }
  .tsg-bound { font-family: var(--font-d, var(--ff-mono)); font-size: 10px; color: var(--calm-ink-chrome, var(--text-ui)); }
  .tsg-run {
    margin-top: 12px;
    font-size: 12.5px;
    font-weight: 700;
    letter-spacing: 0.02em;
    color: #1a1206;
    background: var(--calm-accent, var(--accent));
    border: var(--hairline, 1px) solid var(--badge-ar-border, #d97706);
    border-radius: 5px;
    padding: 7px 16px;
    cursor: pointer;
  }
  .tsg-run:disabled {
    background: var(--calm-surface-row-alt, var(--bg-row-alt));
    color: var(--calm-ink-chrome, var(--text-ui));
    border-color: var(--calm-hairline, var(--border));
    cursor: not-allowed;
  }

  /* ---- step 3: the corridor (two panes + center heat-spine) --------------- */
  .tsg-corridor { margin: 16px 22px 0; border-top: var(--hairline, 1px) solid var(--calm-hairline, var(--border)); padding-top: 14px; }
  .tsg-summary {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    margin-bottom: 12px;
    padding: 9px 12px;
    border: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi));
    border-radius: 6px;
    background: var(--calm-accent-wash, var(--accent-dim));
    font-size: 12.5px;
    color: var(--calm-ink-loud, var(--text-bright));
  }
  .tsg-cols { display: grid; grid-template-columns: 1fr 116px 1fr; gap: 0; align-items: stretch; }
  .tsg-pane-head {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 11px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui));
    padding: 0 6px 8px;
  }
  .tsg-pane-head.right { text-align: right; }
  .tsg-spine-head {
    text-align: center;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui));
    padding: 0 0 8px;
  }
  .tsg-row {
    display: grid;
    grid-template-columns: subgrid;
    grid-column: 1 / 4;
    align-items: stretch;
    border-top: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
  }
  .tsg-row:last-child { border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border)); }
  .tsg-row.is-changed { background: rgba(245, 158, 11, 0.04); }

  .tsg-cell { padding: 11px 8px; display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .tsg-cell.right { align-items: flex-end; text-align: right; }
  .tsg-cell__line { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .tsg-cell.right .tsg-cell__line { justify-content: flex-end; }
  .tsg-cell__content {
    font-size: 12.5px;
    color: var(--calm-ink, var(--text));
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 100%;
  }
  .tsg-cell__meta {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10.5px;
    color: var(--calm-ink-quiet, var(--text-dim));
    font-variant-numeric: tabular-nums;
  }
  .tsg-cell__conf { color: var(--calm-ink-loud, var(--text-bright)); font-weight: 600; }

  /* center spine: tint by |delta| band AND carry the signed numeral (M4). The
     heat ramp is component-scoped (no theme.css pollution); a single-hue amber
     ramp, each segment paired with the literal numeral so the signal survives
     total color loss. */
  .tsg-spine {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 5px;
    border-left: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-right: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    padding: 8px 4px;
  }
  .tsg-spine.d0 { background: #11161f; }
  .tsg-spine.d1 { background: #2a2410; }
  .tsg-spine.d2 { background: #4a3a0e; }
  .tsg-spine.d3 { background: #7a5a10; }
  .tsg-spine.d4 { background: #b07712; }
  .tsg-spine__num {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 13px;
    font-weight: 700;
    color: var(--text-bright, #e8e0cc);
    font-variant-numeric: tabular-nums;
    letter-spacing: 0.02em;
  }
  .tsg-spine__chg {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: #1a1206;
    background: var(--calm-accent, var(--accent));
    border-radius: 3px;
    padding: 2px 6px;
    text-align: center;
    line-height: 1.2;
  }
  .tsg-spine__same { font-family: var(--font-d, var(--ff-mono)); font-size: 9px; letter-spacing: 0.06em; color: var(--text-bright, #e8e0cc); }
  .tsg-spine__bracket { font-weight: 700; }

  .tsg-source {
    margin: 12px 0 0;
    font-size: 11px;
    font-family: var(--font-d, var(--ff-mono));
    letter-spacing: 0.02em;
    color: var(--calm-ink-quiet, var(--text-dim));
  }
  .tsg-source[data-mock='true'] { color: var(--badge-warn-fg, #ea580c); }

  /* ---- footer + deferred-policy footnote ---------------------------------- */
  .tsg-foot {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    padding: 14px 22px;
    margin-top: 14px;
    border-top: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
  }
  .tsg-foot__info { font-size: 12px; color: var(--calm-ink-quiet, var(--text-dim)); }
  .tsg-foot__info b { color: var(--calm-ink-loud, var(--text-bright)); }
  .tsg-foot__spacer { flex: 1 1 auto; }
  .tsg-btn {
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.02em;
    border-radius: 5px;
    padding: 8px 16px;
    cursor: pointer;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    background: transparent;
    color: var(--calm-ink-quiet, var(--text-dim));
  }
  .tsg-btn:hover { color: var(--calm-ink-loud, var(--text-bright)); border-color: var(--calm-hairline-hi, var(--border-hi)); }

  .tsg-gatenote {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    margin: 0 22px 18px;
    padding: 11px 14px;
    border: var(--hairline, 1px) dashed var(--badge-warn-border, #ea580c);
    border-radius: 7px;
    background: rgba(234, 88, 12, 0.07);
  }
  .tsg-gatenote__text { font-size: 12px; color: var(--calm-ink, var(--text)); line-height: 1.5; max-width: 86ch; }
  .tsg-gatenote__text b { color: #c2410c; }

  /* ---- shared Badge primitive (mirrors Badge.svelte .ar-* classes) -------- */
  .ar-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-family: var(--ff-system, system-ui, sans-serif);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 3px 8px;
    white-space: nowrap;
    border-radius: 2px;
    line-height: 1;
    vertical-align: middle;
  }
  .ar-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex: 0 0 auto; }
  .ar-blocked { color: var(--badge-blocked-fg, #dc2626); background: var(--badge-blocked-bg, #fee2e2); border: 2px solid var(--badge-blocked-border, #dc2626); font-weight: 700; }
  .ar-warn { color: #9a3412; background: var(--badge-warn-bg, #ffedd5); border: 1px dashed var(--badge-warn-border, #ea580c); }
  .ar-observing { color: var(--badge-obs-fg, #475569); background: var(--badge-obs-bg, #f1f5f9); border: 1px solid var(--badge-obs-border, #cbd5e1); }
  .ar-static { color: #5b21b6; background: #ede9fe; border: 1px solid #c4b5fd; font-weight: 600; }

  .tsg-sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }

  /* ---- focus ring (M17): the global 2px amber ring on every interactive el - */
  .tsg-launch:focus-visible,
  .tsg-x:focus-visible,
  .tsg-select:focus-visible,
  .tsg-confirm:focus-visible,
  .tsg-handle:focus-visible,
  .tsg-run:focus-visible,
  .tsg-btn:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid) var(--focus-ring-color, #d97706);
    outline-offset: var(--focus-ring-offset, 2px);
  }
  .tsg-handle:focus-visible::-webkit-slider-thumb {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid) var(--focus-ring-color, #d97706);
    outline-offset: 2px;
  }

  /* ---- reduced motion (M17) ----------------------------------------------- */
  :global(html[data-motion='reduce']) .tsg-launch,
  :global(html[data-motion='reduce']) .tsg-scrub { transition: none; }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .tsg-modal { animation: none; }
    .tsg-launch, .tsg-scrub { transition: none; }
  }

  /* ---- narrow viewport: the corridor stacks ------------------------------- */
  @media (max-width: 640px) {
    .tsg-cols { grid-template-columns: 1fr; }
    .tsg-row { grid-template-columns: 1fr; }
    .tsg-cell.right { align-items: flex-start; text-align: left; }
    .tsg-cell.right .tsg-cell__line { justify-content: flex-start; }
    .tsg-pane-head.right { text-align: left; }
  }
</style>
