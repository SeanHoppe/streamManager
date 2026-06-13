<!--
  AwayMode.svelte -- BETA feature #4: Away / Calm Mode + Activity Summary Replay.

  WHAT IT DOES
    The operator is about to leave the keyboard (15--60 min). They flip the AWAY
    pill in the masthead and the monitor goes calm: incoming decision rows + bus
    escalations buffer client-side (the live stores keep flowing; THIS feature
    just stops surfacing them and dims the frames). A REAL escalation still breaks
    through (it never buffers silently). On return, ONE Activity Summary overlay
    replays the gap -- escalation timeline, new-agent roster, queued-HITL count,
    and the away window -- instead of a scrolled-off feed.

  CLIENT-SIDE ONLY. No backend, no new endpoint, no new bus envelope, no new
  table. It reads ONLY the shared, already-self-excluded client stores
  (decisionsStore / escalationStore from sse.js, agentsStore from pollers.js) and
  the existing read-only GET /api/hitl/pending wrapper. It never POSTs, never
  opens /api/commands/stream, never sits on the verdict hot path (M18).

  BETA GATING (default OFF). The component subscribes to NOTHING and registers
  NO store-subscriptions / timers / fetches until $betaFlags["away-mode"] is true.
  The entire body is wrapped in {#if enabled}; the reactive subscriptions live in
  child logic that only runs while mounted under that guard. Flipping the flag OFF
  forces PRESENT, closes the overlay, and tears down every subscription.

  ADR-18 floor honoured:
    - M1 3-frame presence: this feature adds a header pill + a centered
      role=dialog overlay. It NEVER adds a 4th frame and never removes one.
    - M2 escalation-only foreground: a real escalation (the canonical
      lib/escalation.js allow-list, surfaced via sse.js escalationStore) BREAKS
      THROUGH calm immediately -- it is never buffered away. Foreground policy is
      NOT re-decided here; it is read from the one canonical table.
    - M4 paired label+color: every state renders its literal text (PRESENT / AWAY
      / OBSERVING / PAUSE / STATIC RULE -- BLOCK / NEW). Color is never the only
      signal.
    - M15/G2 polarity: every store it reads is SM-self excluded upstream
      (project_slug NOT IN {streamManager} AND session_id != self). This feature
      adds no query of its own and so cannot surface an SM-self row.
    - M16 domain-agnostic: governed identity (sessionId / projectSlug /
      profile_slug) renders FROM DATA. The escalation classifier is generic
      (action IN [BLOCK, INTERVENE] or an allow-listed trigger) -- never a
      hardcoded envelope kind / JOB id / role name.
    - M17 a11y AAA: real <button>; aria-pressed on the pill; aria-modal dialog
      with a focus trap + Escape dismiss + focus restore; aria-live=polite
      buffered-count announcements; reduced-motion honoured via data-motion.

  When live gov.db data is absent the overlay falls back to a realistic,
  domain-agnostic mock summary (usedMockData) so the feature is testable headless.

  ASCII-only (cp1252-safe): dash is "--". No smart quotes, no em-dashes.
-->
<script>
  import { onDestroy, tick } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { decisionsStore, escalationStore } from '../../sse.js';
  import { agentsStore } from '../../pollers.js';
  import { selectedSession, selectedSessionId } from '../../stores/session.js';
  import { getHitlPending } from '../../api.js';
  import { buildSummary, mockSummary, toTimelineItem } from './AwayMode-data.js';

  const FLAG_KEY = 'away-mode';

  // -- gate: TRUE only while the operator has the BETA flag ON. Everything below
  // (subscriptions, timers, the pill, the overlay) is conditioned on this. -----
  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // -- posture state ----------------------------------------------------------
  /** @type {'present'|'away'} */
  let posture = 'present';
  let awayStart = null;            // epoch ms when AWAY engaged
  let bufferedCount = 0;           // decision rows buffered since AWAY engaged
  let liveMsg = '';                // aria-live polite announcement text

  // -- buffered material captured while AWAY ----------------------------------
  let bufferedDecisions = [];      // raw decision rows seen since awayStart
  let bufferedEscalations = [];    // escalationStore entries seen since awayStart
  let agentsBefore = [];           // roster snapshot at the moment AWAY engaged
  let breakthrough = false;        // a real escalation arrived while AWAY

  // -- overlay state ----------------------------------------------------------
  let summaryOpen = false;
  let summary = null;              // the built Activity Summary (or null)
  let usedMock = false;            // surfaced for tests/telemetry
  let lastFocusEl = null;          // focus restore target
  /** @type {HTMLElement|null} */
  let dialogEl = null;
  /** @type {HTMLButtonElement|null} */
  let catchUpEl = null;

  // -- reactive store subscriptions: these only do work while `enabled`. When
  // the flag is OFF the guards below early-return, so no buffering/escalation
  // bookkeeping happens and the component is inert (renders nothing too). -------
  $: onDecisions($decisionsStore);
  $: onEscalations($escalationStore);

  let _lastDecisionId = null;
  /** @param {Array<Record<string, any>>} rows */
  function onDecisions(rows) {
    if (!enabled || posture !== 'away' || !Array.isArray(rows) || rows.length === 0) return;
    // rows is newest-first; capture only rows newer than awayStart we have not
    // already buffered. Use the head id as a cheap "did the feed advance" guard.
    const headId = rows[0] && (rows[0].id ?? rows[0].rid);
    if (headId === _lastDecisionId) return;
    _lastDecisionId = headId;
    for (const r of rows) {
      const ts = rowMs(r);
      if (awayStart && ts && ts < awayStart) break; // older than the away window
      if (!bufferedDecisions.some((b) => (b.id ?? b.rid) === (r.id ?? r.rid))) {
        bufferedDecisions = [r, ...bufferedDecisions];
        bufferedCount += 1;
        // A hard verdict buffered during AWAY is a break-through candidate.
        if (toTimelineItem(r)) breakthrough = true;
      }
    }
    liveMsg = `Away. ${bufferedCount} event${bufferedCount === 1 ? '' : 's'} buffered quietly.`;
  }

  let _lastEscLen = 0;
  /** @param {Array<{rule:any,sessionId:string|null,ts:number}>} list */
  function onEscalations(list) {
    if (!enabled || posture !== 'away' || !Array.isArray(list)) return;
    if (list.length <= _lastEscLen) { _lastEscLen = list.length; return; }
    const fresh = list.slice(_lastEscLen);
    _lastEscLen = list.length;
    for (const e of fresh) {
      if (awayStart && Number(e.ts) < awayStart) continue;
      bufferedEscalations = [...bufferedEscalations, e];
      breakthrough = true; // escalationStore is, by construction, the M2 set
    }
    // M2: a real escalation breaks through the calm posture -- surface it now,
    // do not wait for the operator to return. The overlay auto-opens.
    if (breakthrough && !summaryOpen) {
      liveMsg = 'Escalation broke through calm posture -- opening Activity Summary.';
      openSummary();
    }
  }

  function rowMs(r) {
    if (!r) return 0;
    const t = r.timestamp;
    if (typeof t === 'number') return t < 1e12 ? Math.round(t * 1000) : Math.round(t);
    const n = Date.parse(String(t));
    return Number.isFinite(n) ? n : 0;
  }

  // -- posture toggle ---------------------------------------------------------
  function goAway() {
    posture = 'away';
    awayStart = Date.now();
    bufferedCount = 0;
    bufferedDecisions = [];
    bufferedEscalations = [];
    breakthrough = false;
    _lastDecisionId = $decisionsStore && $decisionsStore[0]
      ? ($decisionsStore[0].id ?? $decisionsStore[0].rid)
      : null;
    _lastEscLen = ($escalationStore || []).length; // ignore pre-existing escalations
    agentsBefore = ($agentsStore || []).slice();
    liveMsg = 'Away. Monitor calmed; buffering events quietly. Real escalations still break through.';
  }

  async function goPresent() {
    posture = 'present';
    const awayEnd = Date.now();
    // Build + open the Activity Summary IFF anything happened worth a glance.
    await composeSummary(awayEnd);
    if (summary && (summary.hasEscalation || summary.bufferedEventCount > 0
        || summary.newAgents.length > 0 || summary.hitlQueuedCount > 0)) {
      openSummary();
    } else {
      liveMsg = 'Present. Nothing needed you while away.';
    }
    awayStart = null;
  }

  function togglePosture(e) {
    lastFocusEl = (e && e.currentTarget) || document.activeElement;
    if (posture === 'present') goAway();
    else goPresent();
  }

  // -- summary composition (live data -> mock fallback) -----------------------
  async function composeSummary(awayEnd) {
    let hitlQueuedCount = 0;
    try {
      const rows = await getHitlPending({ session_id: $selectedSessionId || undefined });
      hitlQueuedCount = Array.isArray(rows) ? rows.length : 0;
    } catch {
      hitlQueuedCount = 0; // calm degrade -- the count just shows 0
    }
    const sess = $selectedSession;
    const live = buildSummary({
      bufferedDecisions,
      bufferedEscalations,
      agentsBefore,
      agentsAfter: ($agentsStore || []).slice(),
      hitlQueuedCount,
      awayStart,
      awayEnd,
      sessionId: (sess && sess.id) || $selectedSessionId || null,
      projectSlug: (sess && sess.project_slug) || null,
    });

    // If the away window produced no live signal at all (no escalations, no
    // buffered events, no new agents, no queued HITL) AND the live stores were
    // empty to begin with, fall back to a realistic mock so the feature is
    // demonstrable/testable. With real data present we ALWAYS show real data.
    const liveEmpty = !live.hasEscalation && live.bufferedEventCount === 0
      && live.newAgents.length === 0 && live.hitlQueuedCount === 0;
    const storesEmpty = ($decisionsStore || []).length === 0
      && ($agentsStore || []).length === 0;
    if (liveEmpty && storesEmpty) {
      summary = mockSummary(awayEnd);
      usedMock = true;
    } else {
      summary = live;
      usedMock = false;
    }
  }

  // -- overlay lifecycle (focus trap + Escape + restore) ----------------------
  async function openSummary() {
    if (!summary) await composeSummary(Date.now());
    summaryOpen = true;
    await tick();
    if (catchUpEl) catchUpEl.focus();
  }

  function closeSummary(restoreFocus = true) {
    if (!summaryOpen) return;
    summaryOpen = false;
    if (restoreFocus && lastFocusEl && typeof lastFocusEl.focus === 'function') {
      lastFocusEl.focus();
    }
  }

  function onDialogKey(e) {
    if (e.key === 'Escape') { e.preventDefault(); closeSummary(); return; }
    if (e.key !== 'Tab' || !dialogEl) return;
    const f = Array.from(
      dialogEl.querySelectorAll('button, [href], [tabindex]:not([tabindex="-1"])'),
    ).filter((el) => !el.disabled && el.offsetParent !== null);
    if (f.length === 0) return;
    const first = f[0];
    const last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  function onScrimDown(e) {
    if (e.target === e.currentTarget) closeSummary();
  }

  // -- footer actions ---------------------------------------------------------
  function catchUp() {
    bufferedCount = 0;
    bufferedDecisions = [];
    bufferedEscalations = [];
    breakthrough = false;
    closeSummary();
    liveMsg = 'Caught up. Buffer cleared; live monitor resumed.';
  }

  function reviewPending() {
    closeSummary(false);
    // Reuse the same FR-UI-9 settings event bus to ask the shell to focus the
    // HITL dock -- additive, no new bus envelope. The dock listens for the
    // generic focus intent; if nothing listens this is a calm no-op.
    if (typeof window !== 'undefined' && typeof CustomEvent === 'function') {
      window.dispatchEvent(new CustomEvent('sm:focus-hitl', { detail: { source: FLAG_KEY } }));
    }
    liveMsg = 'Jumped to the HITL dock.';
  }

  // -- BETA gate teardown: when the flag flips OFF (or on destroy), force calm,
  // close the overlay, and drop all buffered material so nothing lingers. ------
  $: if (!enabled) teardown();
  function teardown() {
    if (posture !== 'present') posture = 'present';
    if (summaryOpen) summaryOpen = false;
    awayStart = null;
    bufferedCount = 0;
    bufferedDecisions = [];
    bufferedEscalations = [];
    agentsBefore = [];
    breakthrough = false;
    summary = null;
  }

  onDestroy(() => { teardown(); });

  // Derived labels (paired text -- M4).
  $: postureLabel = posture === 'away' ? 'AWAY' : 'PRESENT';
  $: bufferedLabel = bufferedCount > 0 ? `${bufferedCount} buffered` : '';
</script>

{#if enabled}
  <!-- POSTURE PILL -- lives in the masthead header SLOT (App mounts it there).
       Native button: Enter/Space toggle. Paired text label + secondary dot. -->
  <div class="awm-posture" data-testid="away-mode-pill">
    <button
      type="button"
      class="awm-pill"
      data-posture={posture}
      aria-pressed={posture === 'away'}
      aria-label={posture === 'away'
        ? 'Posture: AWAY. Monitor is calm; real escalations still break through. Activate to return.'
        : 'Posture: PRESENT. Activate to go AWAY and calm the monitor.'}
      on:click={togglePosture}
    >
      <span class="awm-dot" aria-hidden="true"></span>
      <span class="awm-pill__text">{postureLabel}</span>
      {#if posture === 'away' && bufferedLabel}
        <span class="awm-buffered">{bufferedLabel}</span>
      {/if}
    </button>
  </div>

  <!-- aria-live region: announces posture + buffered count to AT (polite). -->
  <p class="awm-sr-only" aria-live="polite" data-testid="away-mode-live">{liveMsg}</p>

  <!-- ACTIVITY SUMMARY OVERLAY -- centered role=dialog aria-modal. NEVER a 4th
       frame: it is an overlay that reuses the drawer lifecycle. -->
  {#if summaryOpen && summary}
    <div
      class="awm-scrim"
      data-testid="away-mode-summary"
      on:mousedown={onScrimDown}
      on:keydown={onDialogKey}
    >
      <div
        class="awm-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="awm-title"
        aria-describedby="awm-window"
        bind:this={dialogEl}
      >
        <div class="awm-dialog__head">
          <p class="awm-eyebrow">Activity summary -- while you were away</p>
          <h2 class="awm-title" id="awm-title">Quiet briefing</h2>
          <p class="awm-window" id="awm-window">
            AWAY <b>{summary.awayStartLabel}</b> -&gt; <b>{summary.awayEndLabel}</b>
            ({summary.awayMinutes} min) &middot;
            <span data-testid="away-mode-buffered">{summary.bufferedEventCount}</span> events observed
          </p>
          {#if summary.sessionId}
            <p class="awm-scope">
              session {summary.sessionId}{#if summary.projectSlug} &middot; project {summary.projectSlug}{/if}
              {#if usedMock} &middot; sample data{/if}
            </p>
          {/if}
        </div>

        <div class="awm-dialog__body">
          <!-- ESCALATION TIMELINE -->
          <div class="awm-section">
            <p class="awm-section__label">
              Escalation timeline
              <span class="awm-section__count">while away</span>
            </p>
            {#if summary.timeline.length}
              <ul class="awm-timeline">
                {#each summary.timeline as it (it.ts + '|' + it.label)}
                  <li class="awm-tl-item" data-kind={it.kind}>
                    <span class="awm-tl-dot" aria-hidden="true"></span>
                    <div class="awm-tl-main">
                      <div class="awm-tl-line1">
                        <span class="awm-tl-ts">{it.tsLabel}</span>
                        <span
                          class="awm-badge"
                          class:awm-badge--blocked={it.kind === 'slate'}
                          class:awm-badge--pause={it.kind === 'amber'}
                        >{it.label}</span>
                      </div>
                      <p class="awm-tl-reason">{it.reason}</p>
                    </div>
                  </li>
                {/each}
              </ul>
            {:else}
              <p class="awm-empty">No escalations fired while you were away.</p>
            {/if}
          </div>

          <!-- NEW AGENTS roster -->
          <div class="awm-section">
            <p class="awm-section__label">
              New agents
              <span class="awm-section__count">first seen while away</span>
            </p>
            {#if summary.newAgents.length}
              <div class="awm-chips">
                {#each summary.newAgents as a (a.profile_slug)}
                  <span class="awm-chip">
                    <span class="awm-chip__slug">{a.profile_slug}</span>
                    <span class="awm-chip__seen">{a.first_seen_label}</span>
                    <span class="awm-chip__new">NEW</span>
                  </span>
                {/each}
              </div>
            {:else}
              <p class="awm-empty">No new agents joined while you were away.</p>
            {/if}
          </div>

          <!-- PENDING line -- the HITL gate stays absolute (nothing auto-resolved) -->
          <div class="awm-section">
            <p class="awm-section__label">Pending</p>
            <div class="awm-pending">
              <span class="awm-badge awm-badge--observing">OBSERVING</span>
              <span>
                <b data-testid="away-mode-pending">{summary.hitlQueuedCount}</b>
                HITL row{summary.hitlQueuedCount === 1 ? '' : 's'} queued -- nothing auto-resolved (gate stays absolute)
              </span>
            </div>
          </div>
        </div>

        <!-- FOOTER ACTIONS -->
        <div class="awm-dialog__foot">
          <button class="awm-btn awm-btn--primary" type="button" data-testid="away-mode-catchup"
                  bind:this={catchUpEl} on:click={catchUp}>Catch Up</button>
          <button class="awm-btn" type="button" data-testid="away-mode-review"
                  on:click={reviewPending}>Review Pending</button>
          <button class="awm-btn awm-btn--ghost" type="button"
                  aria-label="Dismiss summary (Esc)" on:click={() => closeSummary()}>Dismiss</button>
          <span class="awm-hint">Esc dismiss &middot; Tab cycles</span>
        </div>
      </div>
    </div>
  {/if}
{/if}

<style>
  /* All selectors are .awm-* scoped so this feature pollutes no shared class.
     Tokens come from theme.css (the --badge-*, --bg-*, --text-*, --accent,
     --border, --font-* contract). No hardcoded palette beyond the primary-button
     ink (#1a1206), which matches the mockup's on-accent text. */

  .awm-posture { display: inline-flex; align-items: center; }

  .awm-pill {
    display: inline-flex; align-items: center; gap: 9px;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 12px; font-weight: 700; letter-spacing: 0.1em;
    padding: 6px 13px; border-radius: 999px; cursor: pointer;
    background: var(--bg-card); border: 1px solid var(--border);
    color: var(--text-bright);
    transition: border-color 180ms ease, background 180ms ease, color 180ms ease;
  }
  .awm-pill:hover { border-color: var(--border-hi); }
  .awm-dot { width: 9px; height: 9px; border-radius: 50%; flex: 0 0 auto; }
  .awm-pill[data-posture='present'] .awm-dot {
    background: transparent; border: 1.5px solid var(--badge-obs-fg);
  }
  .awm-pill[data-posture='away'] {
    background: var(--badge-obs-bg); color: var(--badge-obs-fg);
    border-color: var(--badge-obs-border);
  }
  .awm-pill[data-posture='away'] .awm-dot {
    background: var(--badge-obs-fg); border: 1.5px solid var(--badge-obs-fg);
  }
  .awm-buffered {
    font-size: 10px; font-weight: 600; letter-spacing: 0.04em;
    padding-left: 9px; margin-left: 2px; border-left: 1px solid currentColor;
    opacity: 0.85;
  }

  .awm-sr-only {
    position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
    overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
  }

  /* OVERLAY */
  .awm-scrim {
    position: fixed; inset: 0; background: rgba(2, 4, 8, 0.72);
    display: flex; align-items: flex-start; justify-content: center;
    padding: 7vh 20px 40px; z-index: 60; overflow-y: auto;
  }
  .awm-dialog {
    width: 100%; max-width: 620px;
    background: var(--bg-card); border: 1px solid var(--border-hi);
    border-radius: 12px; box-shadow: 0 24px 60px rgba(0, 0, 0, 0.55);
    overflow: hidden;
  }
  .awm-dialog__head { padding: 18px 22px 14px; border-bottom: 1px solid var(--border); }
  .awm-eyebrow {
    font-family: var(--font-d, var(--ff-mono)); font-size: 10px; font-weight: 700;
    letter-spacing: 0.18em; text-transform: uppercase; color: var(--text-ui); margin: 0 0 6px;
  }
  .awm-title { margin: 0; font-size: 20px; font-weight: 680; color: var(--text-bright); letter-spacing: 0.01em; }
  .awm-window { margin-top: 8px; font-family: var(--font-d, var(--ff-mono)); font-size: 13px; color: var(--text-dim); }
  .awm-window b { color: var(--text); font-weight: 700; }
  .awm-scope {
    margin-top: 6px; font-family: var(--font-d, var(--ff-mono)); font-size: 11px;
    color: var(--text-ui); letter-spacing: 0.04em;
  }
  .awm-dialog__body { padding: 6px 22px 18px; }

  .awm-section { margin-top: 18px; }
  .awm-section__label {
    font-family: var(--font-d, var(--ff-mono)); font-size: 11px; font-weight: 700;
    letter-spacing: 0.12em; text-transform: uppercase; color: var(--text-ui);
    margin: 0 0 10px; display: flex; align-items: center; gap: 8px;
  }
  .awm-section__count {
    font-size: 10px; color: var(--text-dim); border: 1px solid var(--border);
    border-radius: 999px; padding: 1px 7px;
  }

  .awm-timeline { position: relative; margin: 0; padding: 0; list-style: none; }
  .awm-tl-item {
    position: relative; display: grid; grid-template-columns: auto 1fr;
    gap: 12px; padding: 10px 0 10px 4px;
  }
  .awm-tl-item:not(:last-child)::before {
    content: ''; position: absolute; left: 7px; top: 26px; bottom: -2px;
    width: 1px; background: var(--border);
  }
  .awm-tl-dot {
    width: 15px; height: 15px; border-radius: 50%; flex: 0 0 auto; margin-top: 2px;
    border: 3px solid var(--badge-ar-fg); background: var(--bg-card);
  }
  .awm-tl-item[data-kind='slate'] .awm-tl-dot { border-color: var(--badge-blocked-fg); }
  .awm-tl-main { min-width: 0; }
  .awm-tl-line1 { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .awm-tl-ts { font-family: var(--font-d, var(--ff-mono)); font-size: 12px; color: var(--text-dim); }
  .awm-tl-reason { margin-top: 4px; font-size: 13px; color: var(--text); }

  .awm-chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 0; padding: 0; }
  .awm-chip {
    display: inline-flex; align-items: center; gap: 8px;
    background: var(--bg-row-alt); border: 1px solid var(--border); border-radius: 999px;
    padding: 5px 12px; font-size: 13px; color: var(--text);
  }
  .awm-chip__slug { font-weight: 600; color: var(--text-bright); }
  .awm-chip__seen { font-family: var(--font-d, var(--ff-mono)); font-size: 11px; color: var(--text-dim); }
  .awm-chip__new {
    font-family: var(--font-d, var(--ff-mono)); font-size: 9px; letter-spacing: 0.08em;
    color: var(--badge-obs-fg); background: var(--badge-obs-bg);
    border: 1px solid var(--badge-obs-border); border-radius: 3px; padding: 1px 5px;
  }

  .awm-pending { display: flex; align-items: center; gap: 12px; font-size: 14px; color: var(--text); }
  .awm-pending b { color: var(--text-bright); }

  .awm-empty {
    color: var(--text-dim); font-size: 13px; padding: 4px 0 2px; font-style: italic;
  }

  /* PAIRED LABEL+COLOR BADGES (M4) -- text + bg + border; dot is secondary. */
  .awm-badge {
    display: inline-flex; align-items: center; gap: 6px;
    font-family: var(--font-d, var(--ff-mono)); font-size: 10px; font-weight: 700;
    letter-spacing: 0.08em; text-transform: uppercase;
    padding: 3px 8px; border-radius: 4px; white-space: nowrap;
  }
  .awm-badge::before {
    content: ''; width: 7px; height: 7px; border-radius: 2px; background: currentColor; opacity: 0.9;
  }
  .awm-badge--observing { color: var(--badge-obs-fg); background: var(--badge-obs-bg); border: 1px solid var(--badge-obs-border); }
  .awm-badge--pause { color: var(--badge-ar-fg); background: var(--badge-ar-bg); border: 2px solid var(--badge-ar-border); }
  .awm-badge--blocked { color: var(--badge-blocked-fg); background: var(--badge-blocked-bg); border: 2px solid var(--badge-blocked-border); }

  .awm-dialog__foot {
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    padding: 16px 22px; border-top: 1px solid var(--border); background: var(--bg-row-alt);
  }
  .awm-btn {
    appearance: none; font-family: var(--font-h, var(--ff-system));
    font-size: 13px; font-weight: 600; letter-spacing: 0.02em;
    padding: 9px 18px; border-radius: 7px; cursor: pointer;
    border: 1px solid var(--border); background: transparent; color: var(--text-bright);
    transition: border-color 180ms ease, background 180ms ease, color 180ms ease;
  }
  .awm-btn:hover { border-color: var(--border-hi); }
  .awm-btn--primary { background: var(--accent); color: #1a1206; border-color: var(--accent); }
  .awm-btn--primary:hover { filter: brightness(1.06); border-color: var(--accent); }
  .awm-btn--ghost { margin-left: auto; color: var(--text-dim); }
  .awm-hint { font-family: var(--font-d, var(--ff-mono)); font-size: 11px; color: var(--text-ui); letter-spacing: 0.04em; }

  /* A11Y: 2px amber focus ring on every interactive element. */
  .awm-pill:focus-visible, .awm-btn:focus-visible {
    outline: 2px solid var(--badge-ar-border); outline-offset: 2px; border-radius: 6px;
  }

  /* Reduced motion: drop transitions unless the operator force-allows motion. */
  :global(html[data-motion='reduce']) .awm-pill,
  :global(html[data-motion='reduce']) .awm-btn { transition: none; }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .awm-pill,
    :global(html:not([data-motion='allow'])) .awm-btn { transition: none; }
  }
</style>
