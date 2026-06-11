<!--
  TimeMachineGovernanceReplay.svelte -- BETA feature #48
  "time-machine-governance-replay".

  The Svelte realisation of the operator-APPROVED KingMode mockup
  (reports/proposals/mockups/time-machine-governance-replay.html): a gated
  sub-panel mounted at the TOP of the Settings drawer body, just above the
  existing Confidence-floor / HITL-mode controls (the QuickFilters precedent).
  It is NOT a fourth frame and NEVER auto-foregrounds (M1/M2 still-water) -- it
  exists only while the operator has the drawer open AND the flag is ON.

  WHAT IT DOES (v1 -- read-only re-derivation)
    Counterfactual governance replay over ALREADY-STORED decisions. The operator
    picks a window + a trial config delta (confidence floor; HITL mode is shown
    but the re-derivation lever in v1 is the floor), clicks "Replay window", and
    one POST /api/time-machine/replay returns the diff matrix + a +N/-N tally.
    Replay RE-DERIVES the deterministic post-engine confidence-floor overlay
    (governance.py _cap_action + the confidence_floor block) under the trial
    floor -- it does NOT re-call the model and NOTHING is persisted. The "live
    counterfactual engine" (re-running the full pipeline) is DEFERRED and
    surfaced as a read-only "from CLI" affordance, never built in-process.

  ============================ GOVERNANCE FLOOR ============================
  CONSTRAINED ADDITIVE: NO message_bus.py edit, NO new bus envelope, NO ADR-18
    amendment, NO in-process spawn/cron/subprocess. One additive READ endpoint
    over existing gov.db (server EXCLUDES SM-self by project_slug + session_id).

  BETA GATE (default OFF): the component renders NOTHING and registers NO
    pollers / SSE handlers / timers unless $betaFlags['time-machine-governance-
    replay'] is true. There is no interval/socket here AT ALL -- replay is a
    single explicit operator-clicked POST off the verdict hot path (M18). Flag
    OFF => zero runtime cost.

  M2 (escalation-only foreground): ambient settings chrome; never auto-replays
    on drag (an explicit "Replay window" click is required) and never
    foregrounds a frame.

  M4 (paired label+color, never color alone): every diff state renders its
    LITERAL text token (CHANGED / SAME / N/A; "now escalates" / "now releases")
    beside any color chip. The tally + source line are literal text. A
    desaturated render reads every state from text alone.

  M5 (HITL gate): the trial HITL-mode segment is a presentation control only --
    it never bypasses or mutates the live HITL gate (no session is governed by
    this panel).

  M15 / G2 (polarity / self-exclude): the panel issues NO session query of its
    own beyond the one read endpoint, which EXCLUDES SM-self server-side
    (project_slug NOT IN the SM slug set AND session_id != SM_OWN_SESSION_ID).
    The dropped self-row count is surfaced on screen as a visible feature.

  M16 (domain-agnostic): no monitored-project vocabulary. Project + session
    identity is rendered FROM DATA (the mock uses generic demo-project-a/b).

  M17 (a11y AAA): native range/buttons so the global 2px amber focus ring
    applies; the window + HITL-mode + floor controls are labelled; the matrix is
    a keyboard-operable group of expandable rows (Enter/Space toggles the
    reasoning delta, aria-expanded); a polite live region announces the tally
    after a replay. Reduced motion honoured.

  M18 (latency): pure post-hoc inspection; one explicit POST, off the hot path.

  MOCK FALLBACK: when gov.db has no governed (non-SM) decisions in the window
    the endpoint degrades to an empty shape and the component falls back to a
    realistic mock fixture (usedMockData=true) so the panel is always testable.

  ASCII-only (cp1252-safe): dash is "--".
-->
<script>
  import { betaFlags } from '../../stores/beta.js';
  import { settings } from '../../stores/settings.js';
  import { getTimeMachineReplay } from '../../api.js';
  import {
    normalizeReplay,
    rederive,
    summarize,
    classifyRow,
    buildExportMarkdown,
    fmtTime,
    fmtFloor,
    fmtConf,
  } from './TimeMachineGovernanceReplay-data.js';

  const FLAG_KEY = 'time-machine-governance-replay';

  /**
   * usedMockData: surfaced for the test harness (true when the panel fell back
   * to the mock fixture because the server returned no governed rows).
   * @type {boolean}
   */
  export let usedMockData = false;

  /**
   * replayFn: injectable POST hook (OPTIONAL). Defaults to the api.js helper.
   * Injectable so the panel is testable in isolation without a live server.
   * @type {(body: Record<string, any>) => Promise<any>}
   */
  export let replayFn = getTimeMachineReplay;

  // -- gate (single source of truth: the betaFlags store) --------------------
  // Everything below is a no-op while OFF: nothing renders, no fetch fires.
  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // -- window selection (coarse span; default last 1h) -----------------------
  const SPANS = [
    { id: '1h', label: 'Last 1h', ms: 60 * 60 * 1000 },
    { id: '6h', label: '6h', ms: 6 * 60 * 60 * 1000 },
    { id: '24h', label: '24h', ms: 24 * 60 * 60 * 1000 },
  ];
  let spanId = '1h';
  $: spanMs = (SPANS.find((s) => s.id === spanId) || SPANS[0]).ms;

  // -- config delta: pre-filled FROM the live operator settings --------------
  // The "from" floor is the operator's current confidence floor; the trial "to"
  // floor is what the operator nudges. HITL mode is shown but the v1
  // re-derivation lever is the floor (the panel states this read-only).
  $: liveFloor = Number(($settings && $settings.confidenceFloor) ?? 0.6);
  $: liveMode = ($settings && $settings.hitlMode) === 'sync' ? 'SYNC' : 'ASYNC';

  let trialFloor = null; // null => mirror liveFloor until the operator nudges
  let trialMode = null; // null => mirror liveMode until the operator nudges
  $: effFloor = trialFloor == null ? liveFloor : trialFloor;
  $: effMode = trialMode == null ? liveMode : trialMode;

  // -- replay state ----------------------------------------------------------
  /** @type {Record<string, any>|null} the normalized replay payload */
  let data = null;
  let dirty = true; // true => config changed since last replay (replay enabled)
  let busy = false;
  let liveMsg = '';
  /** @type {Set<string>} which rows are expanded (by decision_id) */
  let openRows = new Set();

  function markDirty() {
    dirty = true;
  }
  // Any knob change marks the replay dirty (no auto-replay-on-drag -- M18/M2).
  function onSpan(id) {
    spanId = id;
    markDirty();
  }
  function onFloorInput(e) {
    trialFloor = Number(/** @type {HTMLInputElement} */ (e.currentTarget).value);
    markDirty();
  }
  function onMode(mode) {
    trialMode = mode;
    markDirty();
  }

  // -- the KEY INTERACTION: explicit, bounded replay POST --------------------
  async function replay() {
    if (!enabled || busy) return;
    busy = true;
    const now = Date.now();
    const start = now - spanMs;
    let payload = null;
    try {
      payload = await replayFn({
        time_range_start: start,
        time_range_end: now,
        confidence_floor: effFloor,
        hitl_mode: effMode.toLowerCase(),
      });
    } catch {
      payload = null; // degrade to mock below
    }
    const norm = normalizeReplay(payload, {
      now,
      origFloor: liveFloor,
      trialFloor: effFloor,
    });
    // If the server returned live rows, re-derive them under the exact trial
    // floor so the matrix matches the operator's nudge deterministically (the
    // server applies the same overlay; this keeps client + server in lock-step
    // even if the operator nudged after the round-trip).
    if (!norm.usedMock) {
      const rows = rederive(norm.data.rows, effFloor, liveFloor);
      norm.data = {
        ...norm.data,
        rows,
        summary: { ...summarize(rows, effFloor), mock: false },
        config_delta: {
          confidence_floor: { from: liveFloor, to: effFloor },
          hitl_mode: trialMode ? effMode : null,
        },
        window: { start_ms: start, end_ms: now, label: spanLabel() },
      };
    } else {
      norm.data.window = { start_ms: start, end_ms: now, label: spanLabel() };
      norm.data.config_delta = {
        confidence_floor: { from: liveFloor, to: effFloor },
        hitl_mode: trialMode ? effMode : null,
      };
    }
    data = norm.data;
    usedMockData = norm.usedMock;
    openRows = new Set();
    dirty = false;
    busy = false;
    announceTally();
  }

  function spanLabel() {
    const s = SPANS.find((x) => x.id === spanId) || SPANS[0];
    return s.label.toLowerCase().replace('last ', 'last ');
  }

  function announceTally() {
    if (!data) return;
    const s = data.summary || {};
    const msg =
      `${s.changed || 0} of ${s.checked || 0} decisions change: ` +
      `${s.escalated || 0} now escalate, ${s.released || 0} now release.`;
    liveMsg = '';
    setTimeout(() => {
      liveMsg = msg;
    }, 30);
  }

  // -- expandable reasoning delta (accordion) --------------------------------
  /** @param {string} id */
  function toggleRow(id) {
    const next = new Set(openRows);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    openRows = next;
  }
  /** @param {KeyboardEvent} e @param {string} id */
  function onRowKey(e, id) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      toggleRow(id);
    }
  }

  // -- export (client-side Blob, no server write) ----------------------------
  function exportMarkdown() {
    if (!data || typeof document === 'undefined') return;
    const md = buildExportMarkdown(data);
    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'time-machine-replay.md';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 0);
    liveMsg = '';
    setTimeout(() => {
      liveMsg = 'Diff exported as time-machine-replay.md';
    }, 30);
  }

  // -- mount: NO timer / NO socket / NO fetch. The panel is inert until the
  //    operator clicks "Replay window" -- an explicit, bounded action off the
  //    verdict hot path (M18). onMount/tick are imported for parity with the
  //    drawer idiom but register nothing.

  // Derived display strings (M4: state is always text).
  $: floorChanged = trialFloor != null && Number(trialFloor) !== Number(liveFloor);
  $: modeChanged = trialMode != null && trialMode !== liveMode;
</script>

{#if enabled}
  <section class="tm" aria-labelledby="tm-title">
    <!-- HEADER: title + BETA pill -->
    <div class="tm-head">
      <div class="tm-head__grow">
        <div class="tm-eyebrow">
          <span class="tm-pill">BETA</span>
          <span class="tm-pill__note">default OFF, toggled in Settings &gt; BETA features</span>
        </div>
        <h3 id="tm-title" class="tm-title">Time Machine -- counterfactual replay</h3>
        <p class="tm-sub">
          Re-derive past decisions under a trial config, read-only. Nothing live
          is touched; nothing is persisted.
        </p>
      </div>
    </div>

    <!-- read-only re-derivation note -->
    <p class="tm-readonly">
      Replay is a <b>read-only re-derivation</b> of the deterministic post-engine
      config overlay (confidence-floor capping) over already-stored decisions. It
      does <b>not</b> re-call the model -- the LLM verdict itself is never recomputed.
    </p>

    <!-- ZONE 1: WINDOW -->
    <div class="tm-zone">
      <div class="tm-zone__h"><span class="tm-zone__n">1</span> Window</div>
      <div class="tm-seg" role="radiogroup" aria-label="Replay window span">
        {#each SPANS as sp (sp.id)}
          <button
            type="button"
            class="tm-seg__btn"
            class:is-active={spanId === sp.id}
            role="radio"
            aria-checked={spanId === sp.id}
            tabindex={spanId === sp.id ? 0 : -1}
            on:click={() => onSpan(sp.id)}
          >{sp.label}</button>
        {/each}
      </div>
      <p class="tm-zone__hint">
        The replay scans the most recent governed (non-SM) decisions in this span.
      </p>
    </div>

    <!-- ZONE 2: CONFIG DELTA -->
    <div class="tm-zone">
      <div class="tm-zone__h"><span class="tm-zone__n">2</span> Config delta</div>
      <p class="tm-zone__hint">
        Pre-filled from your current settings. The v1 re-derivation lever is the
        confidence floor; HITL mode is shown for context.
      </p>
      <div class="tm-delta">
        <div class="tm-knob">
          <span class="tm-knob__name">Confidence floor</span>
          <span class="tm-knob__fromto">
            <span class="tm-knob__from">{fmtFloor(liveFloor)}</span>
            <span class="tm-knob__arrow">-&gt;</span>
            <span class="tm-knob__to" class:is-changed={floorChanged}>{fmtFloor(effFloor)}</span>
          </span>
          <input
            class="tm-range"
            type="range"
            min="0"
            max="1"
            step="0.01"
            value={effFloor}
            aria-label="Trial confidence floor"
            aria-valuetext={`${fmtFloor(effFloor)} (from ${fmtFloor(liveFloor)})`}
            on:input={onFloorInput}
          />
        </div>
        <div class="tm-knob">
          <span class="tm-knob__name">HITL mode</span>
          <span class="tm-knob__fromto">
            <span class="tm-knob__from">{liveMode}</span>
            <span class="tm-knob__arrow">-&gt;</span>
            <span class="tm-knob__to" class:is-changed={modeChanged}>{effMode}</span>
          </span>
          <div class="tm-seg tm-knob__seg" role="radiogroup" aria-label="Trial HITL mode">
            {#each ['SYNC', 'ASYNC'] as m (m)}
              <button
                type="button"
                class="tm-seg__btn"
                class:is-active={effMode === m}
                role="radio"
                aria-checked={effMode === m}
                tabindex={effMode === m ? 0 : -1}
                on:click={() => onMode(m)}
              >{m}</button>
            {/each}
          </div>
        </div>
      </div>
    </div>

    <!-- ACTIONS: Replay + Export -->
    <div class="tm-actions">
      <button
        type="button"
        class="tm-btn tm-btn--primary"
        disabled={!dirty || busy}
        on:click={replay}
      >{busy ? 'Replaying...' : 'Replay window'}</button>
      <button
        type="button"
        class="tm-btn tm-btn--ghost"
        disabled={!data}
        on:click={exportMarkdown}
      >Export diff (.md)</button>
      {#if dirty && data}
        <span class="tm-dirty">config changed -- replay to refresh</span>
      {/if}
      <span class="tm-actions__note">POST /api/time-machine/replay</span>
    </div>

    <!-- ZONE 3: DIFF MATRIX + TALLY -->
    {#if data}
      <div class="tm-zone">
        <div class="tm-zone__h"><span class="tm-zone__n">3</span> Diff matrix</div>

        <div class="tm-tally" role="status" aria-live="polite">
          <span class="tm-tally__lead">
            <b>{data.summary.changed}</b> / {data.summary.checked} change
          </span>
          <span class="tm-tally__chip esc">
            <span class="dot" aria-hidden="true"></span>+{data.summary.escalated} escalate
          </span>
          <span class="tm-tally__chip rel">
            <span class="dot" aria-hidden="true"></span>-{data.summary.released} release
          </span>
          <span class="sr-only">{liveMsg}</span>
        </div>

        <p class="tm-source" data-mock={usedMockData ? 'true' : 'false'}>
          {#if usedMockData}
            SAMPLE DATA -- no live governed decisions in gov.db for this window;
            showing a representative shape. (summary.mock = true)
          {:else}
            LIVE -- re-derived from gov.db decisions (polarity-filtered).
          {/if}
        </p>

        <div class="tm-colhead" aria-hidden="true">
          <span>time</span><span>decision</span><span>conf</span>
          <span>orig -&gt; replay</span><span>state</span>
        </div>

        <div class="tm-matrix" role="group" aria-label="Counterfactual diff matrix, newest first">
          {#each data.rows.slice().sort((a, b) => b.timestamp_ms - a.timestamp_ms) as row (row.decision_id)}
            {@const cls = classifyRow(row)}
            {@const isOpen = openRows.has(row.decision_id)}
            <button
              type="button"
              class="tm-row"
              class:is-open={isOpen}
              aria-expanded={isOpen}
              aria-label={`${row.decision_id} at ${fmtTime(row.timestamp_ms)}, confidence ${fmtConf(row.confidence)}, original ${row.original_action} then replay ${row.replay_action}, ${cls.label}${cls.polarity ? ' -- ' + cls.polarity.text : ''}. Activate to expand the reasoning delta.`}
              on:click={() => toggleRow(row.decision_id)}
              on:keydown={(e) => onRowKey(e, row.decision_id)}
            >
              <span class="tm-row__grid">
                <span class="tm-cell time">{fmtTime(row.timestamp_ms)}</span>
                <span class="tm-cell id">{row.decision_id}</span>
                <span class="tm-cell conf">{fmtConf(row.confidence)}</span>
                <span class="tm-cell flow">
                  {row.original_action}
                  <span class="arrow">-&gt;</span>
                  <span class:to-changed={cls.state === 'changed'}>{row.replay_action}</span>
                </span>
                <span class="tm-badge {cls.state}">
                  <span class="dot" aria-hidden="true"></span>{cls.label}
                </span>
              </span>
              {#if cls.polarity}
                <span class="tm-polarity {cls.polarity.cls}">{cls.polarity.text}</span>
              {/if}
              {#if isOpen}
                <span class="tm-detail">
                  <span class="tm-quote original">
                    <span class="tm-quote__lbl">Original cap reason</span>
                    <span class="tm-quote__body">{row.original_reason}</span>
                  </span>
                  <span class="tm-quote replay">
                    <span class="tm-quote__lbl">Counterfactual (floor {fmtFloor(effFloor)}) reason</span>
                    <span class="tm-quote__body">{row.replay_reason}</span>
                  </span>
                  <span class="tm-detail__meta">
                    message {row.message_id} -- project {row.project_slug} -- session {row.session_id}
                  </span>
                </span>
              {/if}
            </button>
          {/each}
        </div>

        <p class="tm-exclude">
          {data.excluded_self} SM-self rows excluded server-side (polarity filter:
          project_slug NOT IN streamManager AND session_id != self).
        </p>
      </div>
    {/if}

    <!-- DEFERRED live-engine affordance (read-only "from CLI") -->
    <div class="tm-gatenote" role="note">
      <span class="tm-gatenote__badge">v1 scope</span>
      <span>
        <b>v1 replays the deterministic floor overlay only.</b>
        The full <i>live</i> counterfactual engine (re-running the entire pipeline
        under a config delta) is deferred to a from-CLI tool -- it is NOT run
        in-process. This panel adds NO new bus envelope and edits NO frozen
        surface.
      </span>
    </div>
  </section>
{/if}

<style>
  .tm {
    display: flex;
    flex-direction: column;
    gap: var(--space-5, 14px);
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: var(--radius-soft, 4px);
    padding: var(--space-5, 14px);
    background:
      linear-gradient(180deg, rgba(245, 158, 11, 0.04), transparent 38%),
      var(--bg-card, #0c1118);
  }

  /* header strip */
  .tm-head { display: flex; align-items: flex-start; gap: var(--space-4, 10px); }
  .tm-head__grow { flex: 1 1 auto; min-width: 0; }
  .tm-eyebrow {
    display: flex; align-items: center; gap: var(--space-3, 6px);
    flex-wrap: wrap; margin-bottom: var(--space-2, 4px);
  }
  .tm-title {
    margin: 0; font-size: 15px; font-weight: 700; letter-spacing: 0.01em;
    color: var(--calm-ink-loud, var(--text-bright));
  }
  .tm-sub {
    margin: var(--space-2, 4px) 0 0; font-size: var(--fs-chrome, 11px);
    color: var(--calm-ink-quiet, var(--text-dim)); max-width: 46ch;
  }
  .tm-pill {
    display: inline-flex; align-items: center;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
    padding: 2px 6px; border-radius: var(--radius-soft, 4px);
    color: var(--badge-ar-fg, #d97706); background: var(--badge-ar-bg, #fef3c7);
    border: 1px solid var(--badge-ar-border, #d97706);
  }
  .tm-pill__note {
    font-size: 10px; letter-spacing: 0.02em; color: var(--calm-ink-quiet, var(--text-dim));
  }

  .tm-readonly {
    margin: 0; font-size: 11px; color: var(--calm-ink-quiet, var(--text-dim));
    border-left: 2px solid var(--calm-hairline, var(--border));
    padding-left: var(--space-3, 6px);
  }
  .tm-readonly b { color: var(--calm-ink-loud, var(--text-bright)); font-weight: 600; }

  /* zones */
  .tm-zone { display: flex; flex-direction: column; gap: var(--space-3, 6px); }
  .tm-zone__h {
    display: flex; align-items: baseline; gap: var(--space-3, 6px);
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui)); font-weight: 700;
  }
  .tm-zone__n { color: var(--calm-accent, var(--accent)); font-weight: 700; }
  .tm-zone__hint {
    margin: 0; font-size: var(--fs-chrome, 11px);
    color: var(--calm-ink-quiet, var(--text-dim)); max-width: 50ch;
  }

  /* segmented control */
  .tm-seg {
    display: inline-flex; align-self: flex-start;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: var(--radius-soft, 4px); overflow: hidden;
  }
  .tm-seg__btn {
    appearance: none; background: transparent; border: none;
    color: var(--calm-ink-chrome, var(--text-ui));
    font-family: var(--ff-system); font-size: var(--fs-badge, 12px);
    font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase;
    padding: var(--space-2, 4px) var(--space-4, 10px); cursor: pointer; line-height: 1;
    transition: background var(--t-calm, 0.18s), color var(--t-calm, 0.18s);
  }
  .tm-seg__btn + .tm-seg__btn {
    border-left: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
  }
  .tm-seg__btn:hover { background: var(--calm-surface-hover, var(--bg-row-hover)); }
  .tm-seg__btn.is-active {
    background: var(--calm-accent, var(--accent)); color: #1a1206; font-weight: 750;
  }
  :global([data-theme='paper']) .tm-seg__btn.is-active { color: #fffefb; }

  /* config delta knobs */
  .tm-delta { display: flex; flex-direction: column; gap: var(--space-4, 10px); }
  .tm-knob {
    display: grid; grid-template-columns: 1fr auto; align-items: center;
    gap: var(--space-4, 10px);
  }
  .tm-knob__name {
    font-size: var(--fs-meta, 13px); font-weight: 600;
    color: var(--calm-ink-loud, var(--text-bright));
  }
  .tm-knob__fromto {
    display: inline-flex; align-items: center; gap: var(--space-3, 6px);
    font-family: var(--font-d, var(--ff-mono));
    font-variant-numeric: tabular-nums; font-size: var(--fs-meta, 13px);
  }
  .tm-knob__from { color: var(--calm-ink-quiet, var(--text-dim)); }
  .tm-knob__arrow { color: var(--calm-ink-chrome, var(--text-ui)); }
  .tm-knob__to { color: var(--calm-ink, var(--text)); font-weight: 600; }
  .tm-knob__to.is-changed { color: var(--calm-accent, var(--accent)); font-weight: 700; }
  .tm-range {
    grid-column: 1 / -1; width: 100%; margin: 0;
    accent-color: var(--calm-accent, var(--accent)); cursor: pointer;
  }
  .tm-knob__seg { grid-column: 1 / -1; }

  /* actions */
  .tm-actions {
    display: flex; align-items: center; gap: var(--space-3, 6px);
    flex-wrap: wrap; padding-top: var(--space-2, 4px);
  }
  .tm-btn {
    appearance: none; font: inherit; font-size: var(--fs-meta, 13px);
    font-weight: 600; letter-spacing: 0.03em;
    padding: var(--space-3, 6px) var(--space-5, 14px);
    border-radius: var(--radius-sharp, 2px); cursor: pointer;
    transition: background var(--t-calm, 0.18s), color var(--t-calm, 0.18s), border-color var(--t-calm, 0.18s);
  }
  .tm-btn--primary {
    color: #1a1206; background: var(--accent, #f59e0b);
    border: var(--hairline, 1px) solid var(--accent, #f59e0b);
  }
  :global([data-theme='paper']) .tm-btn--primary { color: #fffefb; }
  .tm-btn--primary:hover { filter: brightness(1.06); }
  .tm-btn--primary[disabled] {
    background: transparent; color: var(--calm-ink-quiet, var(--text-dim));
    border-color: var(--calm-hairline, var(--border)); cursor: not-allowed; filter: none;
  }
  .tm-btn--ghost {
    background: transparent; color: var(--calm-ink-loud, var(--text-bright));
    border: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi));
  }
  .tm-btn--ghost:hover {
    background: var(--calm-accent-wash, var(--accent-dim));
    border-color: var(--calm-accent, var(--accent)); color: var(--calm-accent, var(--accent));
  }
  .tm-btn--ghost[disabled] {
    color: var(--calm-ink-quiet, var(--text-dim));
    border-color: var(--calm-hairline, var(--border)); cursor: not-allowed;
  }
  .tm-actions__note {
    margin-left: auto; font-size: 11px;
    color: var(--calm-ink-quiet, var(--text-dim)); font-family: var(--font-d, var(--ff-mono));
  }
  .tm-dirty {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px; letter-spacing: 0.04em; text-transform: uppercase;
    color: var(--badge-warn-fg, #ea580c);
  }

  /* tally */
  .tm-tally {
    display: flex; align-items: center; gap: var(--space-4, 10px); flex-wrap: wrap;
    padding: var(--space-3, 6px) var(--space-4, 10px);
    border: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi));
    border-radius: var(--radius-soft, 4px); background: var(--bg-card, #0c1118);
  }
  .tm-tally__lead {
    font-family: var(--font-d, var(--ff-mono)); font-variant-numeric: tabular-nums;
    font-size: var(--fs-meta, 13px); font-weight: 700;
    color: var(--calm-ink-loud, var(--text-bright));
  }
  .tm-tally__lead b { color: var(--calm-accent, var(--accent)); }
  .tm-tally__chip {
    display: inline-flex; align-items: center; gap: var(--space-2, 4px);
    font-family: var(--font-d, var(--ff-mono));
    font-size: 11px; font-weight: 700; letter-spacing: 0.04em;
    font-variant-numeric: tabular-nums; padding: 2px 8px; border-radius: var(--radius-soft, 4px);
  }
  .tm-tally__chip .dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
  .tm-tally__chip.esc { color: var(--badge-blocked-fg, #dc2626); background: rgba(220, 38, 38, 0.12); }
  .tm-tally__chip.rel { color: var(--badge-decided-fg, #16a34a); background: rgba(22, 163, 74, 0.12); }

  .tm-source {
    margin: 0; font-size: 11px; font-family: var(--font-d, var(--ff-mono));
    letter-spacing: 0.02em; color: var(--calm-ink-quiet, var(--text-dim));
  }
  .tm-source[data-mock='true'] { color: var(--badge-warn-fg, #ea580c); }

  /* matrix */
  .tm-matrix { display: flex; flex-direction: column; gap: var(--space-1, 2px); }
  .tm-colhead {
    display: grid; grid-template-columns: 5.2em 6em 3em 1fr 6.4em;
    gap: var(--space-3, 6px); padding: 0 var(--space-3, 6px) var(--space-2, 4px);
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px; letter-spacing: 0.06em; text-transform: uppercase;
    color: var(--calm-ink-quiet, var(--text-dim));
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
  }
  .tm-colhead span:nth-child(3) { text-align: right; }

  .tm-row {
    width: 100%; text-align: left; font: inherit; color: inherit; background: transparent;
    border: var(--hairline, 1px) solid transparent; border-radius: var(--radius-soft, 4px);
    padding: var(--space-3, 6px); cursor: pointer; display: block;
    transition: background var(--t-calm, 0.18s), border-color var(--t-calm, 0.18s);
  }
  .tm-row:hover { background: var(--bg-row-hover, #131c2a); }
  .tm-row.is-open {
    background: var(--bg-row-hover, #131c2a); border-color: var(--calm-hairline, var(--border));
  }
  .tm-row__grid {
    display: grid; grid-template-columns: 5.2em 6em 3em 1fr 6.4em;
    gap: var(--space-3, 6px); align-items: center;
  }
  .tm-cell { font-family: var(--font-d, var(--ff-mono)); font-size: 12px; font-variant-numeric: tabular-nums; }
  .tm-cell.time { color: var(--calm-ink-quiet, var(--text-dim)); }
  .tm-cell.id { color: var(--calm-ink-chrome, var(--text-ui)); }
  .tm-cell.conf { color: var(--calm-ink, var(--text)); text-align: right; }
  .tm-cell.flow { color: var(--calm-ink-loud, var(--text-bright)); }
  .tm-cell.flow .arrow { color: var(--calm-ink-chrome, var(--text-ui)); }
  .tm-cell.flow .to-changed { color: var(--badge-ar-fg, #d97706); font-weight: 700; }

  /* paired label+color state badge (M4) -- the TEXT token is always present */
  .tm-badge {
    display: inline-flex; align-items: center; gap: var(--space-2, 4px); justify-self: end;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase;
    padding: 2px 7px; border-radius: var(--radius-soft, 4px); border: 1px solid;
  }
  .tm-badge .dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; flex: 0 0 auto; }
  .tm-badge.changed {
    color: var(--badge-blocked-fg, #dc2626); background: var(--badge-blocked-bg, #fee2e2);
    border-color: var(--badge-blocked-border, #dc2626);
  }
  .tm-badge.same {
    color: var(--badge-decided-fg, #16a34a); background: var(--badge-decided-bg, #dcfce7);
    border-color: var(--badge-decided-border, #86efac);
  }
  .tm-badge.na { color: #475569; background: #f1f5f9; border-color: #cbd5e1; }

  .tm-polarity {
    display: block; margin-top: var(--space-2, 4px);
    font-family: var(--font-d, var(--ff-mono)); font-size: 10px; letter-spacing: 0.04em;
  }
  .tm-polarity.escalated { color: var(--badge-blocked-fg, #dc2626); }
  .tm-polarity.released { color: var(--badge-decided-fg, #16a34a); }

  /* expanded reasoning delta */
  .tm-detail {
    display: flex; flex-direction: column; gap: var(--space-3, 6px);
    margin: var(--space-3, 6px) 0 0; padding-top: var(--space-3, 6px);
    border-top: var(--hairline, 1px) dashed var(--calm-hairline, var(--border));
  }
  .tm-quote { display: flex; flex-direction: column; gap: var(--space-1, 2px); }
  .tm-quote__lbl {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px; letter-spacing: 0.06em; text-transform: uppercase;
    color: var(--calm-ink-quiet, var(--text-dim));
  }
  .tm-quote__body {
    margin: 0; padding: var(--space-3, 6px) var(--space-4, 10px);
    background: var(--bg-row-alt, #0b1018);
    border-left: 2px solid var(--calm-hairline, var(--border));
    border-radius: var(--radius-soft, 4px); font-size: 12px; color: var(--calm-ink, var(--text));
  }
  .tm-quote.original .tm-quote__body { border-left-color: var(--calm-ink-chrome, var(--text-ui)); }
  .tm-quote.replay .tm-quote__body { border-left-color: var(--badge-ar-fg, #d97706); }
  .tm-detail__meta {
    font-family: var(--font-d, var(--ff-mono)); font-size: 11px;
    color: var(--calm-ink-quiet, var(--text-dim)); font-variant-numeric: tabular-nums;
  }

  .tm-exclude {
    margin: var(--space-3, 6px) 0 0; font-family: var(--font-d, var(--ff-mono));
    font-size: 11px; color: var(--calm-ink-quiet, var(--text-dim)); font-variant-numeric: tabular-nums;
  }

  /* v1-scope deferred-engine note */
  .tm-gatenote {
    display: flex; align-items: flex-start; gap: var(--space-3, 6px);
    padding: var(--space-3, 6px) var(--space-4, 10px);
    border: var(--hairline, 1px) solid var(--badge-warn-border, #ea580c);
    border-left-width: 3px; border-radius: var(--radius-soft, 4px);
    background: rgba(234, 88, 12, 0.07); font-size: 11px; line-height: 1.45;
    color: var(--calm-ink, var(--text));
  }
  .tm-gatenote__badge {
    flex: 0 0 auto; font-family: var(--font-d, var(--ff-mono));
    font-size: 10px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase;
    color: var(--badge-warn-fg, #ea580c); background: var(--badge-warn-bg, #ffedd5);
    border: 1px solid var(--badge-warn-border, #ea580c);
    border-radius: var(--radius-soft, 4px); padding: 2px 6px; margin-top: 1px;
  }
  .tm-gatenote b { color: var(--calm-ink-loud, var(--text-bright)); }
  .tm-gatenote i { font-style: italic; }

  .sr-only {
    position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0;
    border: 0; clip: rect(0 0 0 0); overflow: hidden; white-space: nowrap;
  }

  /* shared focus ring: 2px solid amber, 2px offset (focus.css contract). */
  .tm-seg__btn:focus-visible,
  .tm-range:focus-visible,
  .tm-btn:focus-visible,
  .tm-row:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid) var(--focus-ring-color, #d97706);
    outline-offset: var(--focus-ring-offset, 2px);
  }

  /* reduced motion (M17) */
  :global(html[data-motion='reduce']) .tm-row,
  :global(html[data-motion='reduce']) .tm-btn,
  :global(html[data-motion='reduce']) .tm-seg__btn { transition: none; }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .tm-row,
    :global(html:not([data-motion='allow'])) .tm-btn,
    :global(html:not([data-motion='allow'])) .tm-seg__btn { transition: none; }
  }
</style>
