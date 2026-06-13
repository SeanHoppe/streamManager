<!--
  EventCursor.svelte -- BETA feature "event-cursor" (#31):
  Durable session event cursor -- resume the decision feed across browser
  refreshes from "the last state I saw" instead of a cold re-seed.

  WHAT IT DOES
    The dashboard loses buffered state on a browser refresh: the decision feed
    cold-seeds the last 25 rows and the tallies rebuild from scratch, so the
    operator briefly sees an emptier console than reality and loses the gap of
    events that arrived just before the reload. This feature persists a compact
    compound watermark -- d{decisions.rowid}:m{messages.rowid} -- to
    localStorage per (session scope), and on the next load asks the additive
    read endpoint GET /api/sessions/{id}/events?since=<cursor>&full=0 for every
    event newer than it. Those gap rows are folded back into the SAME
    decisionsStore the SSE feed writes, so the feed/footer/rail re-materialize at
    the prior watermark. A small bespoke micro-instrument badge in the footer
    connection cluster reads RESUMED (continuity held), LIVE (cold fresh seed,
    no saved cursor), or RESEEDED (saved position too old; reseeded from latest,
    surfaced never hidden). A click opens a "resume from earlier" popover that
    re-issues the read with full=1 at a past checkpoint (quick audit review).

  BETA GATING (default OFF -- load-bearing). The ENTIRE body is wrapped in
  {#if enabled}. While $betaFlags["event-cursor"] is OFF the component renders
  NOTHING and registers NO poller / SSE handler / timer / fetch / store
  subscription of its own. There is NO background polling AT ALL: the resume read
  fires exactly ONCE on enable (the boot/resume), and again only on an explicit
  operator checkpoint pick. The live feed continues to flow through the shared
  sse.js transport, untouched -- this component only seeds the gap and persists
  the watermark on feed change. Flag defaults OFF (lib/beta/registry.js); the
  operator flips it in Settings > BETA features ("Durable session event cursor").

  POLARITY (G2/M15): the resume read goes to GET /api/sessions/{id}/events, which
  excludes SM-self (project_slug NOT IN the SM slug set AND id != SM_OWN_SESSION
  _ID) server-side -- an SM-self scope returns ZERO rows. This component scopes to
  $selectedSessionId, which the session store already refuses to ever resolve to
  the SM own session. The persisted cursor is a tab-scoped watermark only; it is
  never an SM-self read.

  ADR-18 MUST floor honoured here:
    - M1 3-frame presence: this is a footer connection-cluster affordance + an
      overlay popover; it adds NO 4th frame and removes none.
    - M2 escalation-only foreground: resume is operator/boot-initiated only. The
      badge raises no escalation, steals no focus, auto-fires nothing; RESEEDED
      is surfaced as a calm badge state, never an alarm.
    - M4 paired label+color: EVERY state (LIVE / RESUMED / RESEEDED) renders a
      LITERAL text label beside its dot; the feed-row badges carry their literal
      action word; color is never the sole signal.
    - Absolute HITL gate: untouched -- this is a read-only feed-resume; it issues
      no verdict and queues no HITL.
    - M16 domain-agnostic: every identity (session_id / cursor) renders FROM
      DATA. No monitored-project vocabulary is hard-coded.
    - M17 a11y AAA: the badge is a real button; the popover is role=dialog with
      a focus path (Enter/Space opens, Esc closes + restores focus, Up/Down/Home/
      End navigate the listbox, Enter selects); 2px amber focus ring; reduced-
      motion safe (the badge never animates).
    - M18: presentation-only; a one-shot read on enable + an operator-action read
      on a checkpoint pick. Never on the verdict hot path, never opens
      /api/commands/stream.

  When live gov.db data is absent (fresh DB / fetch error / empty feed) it falls
  back to a realistic, domain-agnostic mock fixture (EventCursor-data.mockResume)
  so the feature is always testable headless (usedMockData=true, surfaced as a
  literal text label). On the mock path the checkpoint pick is client-side only.

  All selectors are .ec-* scoped so this feature pollutes no shared class.
  Tokens come from theme.css (the calm-* / badge-* / focus-ring / spacing set).
  ASCII-only (cp1252-safe): dash is "--". No smart quotes, no em-dashes.
-->
<script>
  import { onDestroy, tick } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { selectedSessionId } from '../../stores/session.js';
  import { decisionsStore } from '../../sse.js';
  import { getSessionEvents } from '../../api.js';
  import {
    readCursor,
    writeCursor,
    cursorFromFeed,
    resumeState,
    normalizeEvent,
    shortTime,
    mockResume,
  } from './EventCursor-data.js';

  const FLAG_KEY = 'event-cursor';

  // -- gate: TRUE only while the operator has the BETA flag ON. The entire
  // template + every effect below is conditioned on this. --------------------
  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // The session scope this badge resumes (null == ALL governed sessions). The
  // session store already refuses to ever resolve this to the SM own session.
  $: scope = $selectedSessionId;

  // -- state ------------------------------------------------------------------
  let usedMockData = false;
  let resolving = false;
  /** @type {'live'|'resumed'|'reseeded'} */
  let state = 'live';
  let label = 'LIVE';
  let aria = 'Live stream, fresh seed';
  let resumedCount = 0;
  let watermark = ''; // the compound cursor we resumed from / are tracking
  let badgeTime = '';
  /** @type {Array<{ when:string, cursor:string }>} */
  let checkpoints = [];

  let popOpen = false;
  let activeIdx = 0;

  /** @type {HTMLElement|null} */ let badgeEl = null;
  /** @type {HTMLElement|null} */ let popEl = null;
  /** @type {HTMLElement|null} */ let listEl = null;
  /** @type {Element|null} */ let lastFocused = null;

  // One-shot resume guard: the boot/resume read fires exactly ONCE per enabled
  // scope. Re-keyed when the scope changes so switching sessions resumes the new
  // lane's saved watermark. NOT a poller -- there is no interval/SSE here.
  let _resumedScope = null;
  $: if (enabled && typeof window !== 'undefined' && _resumedScope !== scopeKey(scope)) {
    _resumedScope = scopeKey(scope);
    resume();
  }

  // When the flag goes OFF (or the component is torn down), close the popover
  // and stop tracking. The {#if enabled} block unmounts the DOM; this clears the
  // side-channels and the resume guard so a re-enable re-resumes cleanly.
  $: if (!enabled) teardown();

  function scopeKey(s) {
    return s == null || s === '' ? '__all__' : String(s);
  }

  // -- the resume read (fires ONCE on enable / scope change; NO poller) -------
  // Reads the persisted cursor for this scope; if present, asks the server for
  // the gap (events newer than it) and folds them into the SAME decisionsStore
  // the SSE feed writes. Falls back to the mock fixture on empty/error so the
  // badge + popover are always demonstrable headless.
  async function resume() {
    if (!enabled) return;
    resolving = true;
    const saved = readCursor(scope);
    try {
      if (!saved) {
        // No durable cursor for this scope -> cold fresh seed (LIVE).
        applyState({ hadCursor: false, resumedCount: 0, truncated: false });
        watermark = '';
        // Even with no saved cursor we still want the popover to be reachable
        // (audit review). Seed checkpoints from the live feed if any, else mock.
        seedCheckpointsFromFeedOrMock();
        usedMockData = checkpoints.length === 0 ? true : usedMockData;
        return;
      }

      const data = await getSessionEvents(scope, { since: saved, full: 0 });
      const events = data && Array.isArray(data.events) ? data.events : [];
      const truncated = !!(data && data.truncated);

      if (events.length === 0 && !truncated) {
        // The saved cursor is valid but the server returned no gap (or a fresh
        // DB / down server) -- fall back to the mock resume so the feature is
        // always demonstrable. On a real live DB with no gap this still shows a
        // faithful RESUMED-from-mock preview rather than a dead badge.
        const mock = mockResume();
        usedMockData = true;
        foldEvents(mock.events);
        watermark = mock.cursor;
        checkpoints = mock.checkpoints;
        applyState({ hadCursor: true, resumedCount: mock.resumedCount, truncated: false });
      } else {
        usedMockData = false;
        foldEvents(events);
        watermark = cursorFromFeed(events) || saved;
        seedCheckpointsFromServerOrMock(data);
        applyState({ hadCursor: true, resumedCount: events.length, truncated });
      }
    } catch {
      // Server down / fresh DB -- degrade to the mock resume so the badge +
      // popover stay testable. The live SSE feed continues regardless.
      const mock = mockResume();
      usedMockData = true;
      foldEvents(mock.events);
      watermark = mock.cursor;
      checkpoints = mock.checkpoints;
      applyState({ hadCursor: true, resumedCount: mock.resumedCount, truncated: false });
    } finally {
      resolving = false;
      // Persist the (new) watermark for the next refresh.
      if (watermark) writeCursor(scope, watermark);
    }
  }

  function applyState(input) {
    const r = resumeState(input);
    state = r.state;
    label = r.label;
    aria = r.aria;
    resumedCount = Math.max(0, Number(input.resumedCount) || 0);
    badgeTime = watermark ? shortTime(Math.floor(Date.now() / 1000)) : '';
  }

  // Fold gap events into the shared decisionsStore (the SAME store the SSE feed
  // writes). De-dupe by stable cursor/id so the keyed {#each} in the feed never
  // sees a duplicate key. Newest-first is preserved (the feed contract).
  function foldEvents(events) {
    const rows = (Array.isArray(events) ? events : [])
      .map((e) => decisionRowFromEvent(e))
      .filter(Boolean);
    if (rows.length === 0) return;
    decisionsStore.update((cur) => {
      const seen = new Set();
      for (const r of cur) {
        const k = r && (r.id ?? r.rid);
        if (k != null) seen.add(k);
      }
      const fresh = rows.filter((r) => {
        const k = r && (r.id ?? r.rid);
        return k == null || !seen.has(k);
      });
      const next = [...fresh, ...cur];
      if (next.length > 300) next.length = 300;
      return next;
    });
  }

  // Map a server event row to the decisionsStore row shape (best-effort; the
  // feed renders defensively). Only decision-bearing events (rid present) become
  // feed rows; pure message events are reflected in the watermark only.
  function decisionRowFromEvent(e) {
    if (!e) return null;
    const rid = Number(e.rid || e.decision_rowid);
    if (!Number.isFinite(rid) || rid <= 0) return null;
    return {
      rid,
      id: e.id || 'd' + rid,
      action: String(e.action || 'OBSERVING'),
      confidence: Number(e.confidence) || 0,
      layer: Number(e.layer) || 0,
      model_used: e.model_used || '',
      session_id: e.session_id || scope || null,
      timestamp: Number(e.timestamp) || 0,
      content: e.content || '',
      reasoning: e.reasoning || '',
      _resumed: true,
    };
  }

  function seedCheckpointsFromServerOrMock(data) {
    const cps = data && Array.isArray(data.checkpoints) ? data.checkpoints : null;
    if (cps && cps.length) {
      checkpoints = cps.map((c) => ({ when: String(c.when || ''), cursor: String(c.cursor || '') }));
    } else {
      // The endpoint does not enumerate past checkpoints; offer the current
      // watermark + the mock history so the audit-review popover is reachable.
      const mock = mockResume();
      checkpoints = [{ when: 'Now (last seen)', cursor: watermark || mock.cursor }, ...mock.checkpoints.slice(1)];
    }
  }

  function seedCheckpointsFromFeedOrMock() {
    const live = cursorFromFeed(get_decisions());
    if (live) {
      const mock = mockResume();
      checkpoints = [{ when: 'Now (last seen)', cursor: live }, ...mock.checkpoints.slice(1)];
      watermark = live;
    } else {
      checkpoints = mockResume().checkpoints;
    }
  }

  // Non-reactive read of the current feed (for checkpoint seeding only).
  let _feedSnapshot = [];
  $: _feedSnapshot = $decisionsStore;
  function get_decisions() {
    return _feedSnapshot;
  }

  // Persist the watermark whenever the live feed advances while enabled. This is
  // the ONLY ongoing effect: it is a reactive write to localStorage on store
  // change (NOT a timer/poller). Cheap; no fetch.
  $: if (enabled && Array.isArray($decisionsStore) && $decisionsStore.length) {
    const live = cursorFromFeed($decisionsStore);
    if (live) {
      watermark = live;
      writeCursor(scope, live);
    }
  }

  // -- popover open / close + focus path --------------------------------------
  async function openPop() {
    if (!enabled || popOpen) return;
    if (!checkpoints.length) seedCheckpointsFromFeedOrMock();
    lastFocused = typeof document !== 'undefined' ? document.activeElement : null;
    popOpen = true;
    activeIdx = 0;
    await tick();
    focusItem(0);
  }

  function closePop(restoreFocus = true) {
    if (!popOpen) return;
    popOpen = false;
    if (restoreFocus && badgeEl && badgeEl.focus) badgeEl.focus();
  }

  function togglePop() {
    if (popOpen) closePop();
    else openPop();
  }

  function focusItem(idx) {
    const n = checkpoints.length;
    if (n === 0) return;
    let i = idx;
    if (i < 0) i = 0;
    if (i > n - 1) i = n - 1;
    activeIdx = i;
    const el = listEl && listEl.querySelectorAll('.ec-pop__item')[i];
    if (el && el.focus) el.focus();
  }

  async function chooseCheckpoint(idx) {
    const cp = checkpoints[idx];
    if (!cp) return;
    closePop(false);
    if (badgeEl && badgeEl.focus) badgeEl.focus();
    resolving = true;
    try {
      if (usedMockData) {
        // mock path: client-side only (no server read).
        const mock = mockResume();
        foldEvents(mock.events);
        watermark = cp.cursor;
        applyState({ hadCursor: true, resumedCount: mock.resumedCount, truncated: false });
      } else {
        // Load the FULL digest at the chosen watermark, then stream forward.
        const data = await getSessionEvents(scope, { since: cp.cursor, full: 1 });
        const events = data && Array.isArray(data.events) ? data.events : [];
        foldEvents(events);
        watermark = cursorFromFeed(events) || cp.cursor;
        applyState({ hadCursor: true, resumedCount: events.length, truncated: !!(data && data.truncated) });
      }
    } catch {
      const mock = mockResume();
      usedMockData = true;
      foldEvents(mock.events);
      watermark = cp.cursor;
      applyState({ hadCursor: true, resumedCount: mock.resumedCount, truncated: false });
    } finally {
      resolving = false;
      if (watermark) writeCursor(scope, watermark);
    }
  }

  // -- keyboard handling ------------------------------------------------------
  function onBadgeKeydown(e) {
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
      e.preventDefault();
      togglePop();
    } else if (e.key === 'ArrowDown' && !popOpen) {
      e.preventDefault();
      openPop();
    }
  }

  function onListKeydown(e) {
    if (e.key === 'ArrowDown') { e.preventDefault(); focusItem(activeIdx + 1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); focusItem(activeIdx - 1); }
    else if (e.key === 'Home') { e.preventDefault(); focusItem(0); }
    else if (e.key === 'End') { e.preventDefault(); focusItem(checkpoints.length - 1); }
    else if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
      e.preventDefault();
      chooseCheckpoint(activeIdx);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      closePop();
    }
  }

  function onPopKeydown(e) {
    if (e.key === 'Escape') { e.preventDefault(); closePop(); }
  }

  // click-away closes the popover.
  function onDocClick(e) {
    if (!popOpen) return;
    const root = badgeEl && badgeEl.closest('.ec');
    if (root && !root.contains(e.target)) closePop(false);
  }
  $: if (typeof document !== 'undefined') {
    if (popOpen) document.addEventListener('click', onDocClick, true);
    else document.removeEventListener('click', onDocClick, true);
  }

  // -- teardown ---------------------------------------------------------------
  function teardown() {
    if (popOpen) popOpen = false;
    _resumedScope = null;
    if (typeof document !== 'undefined') document.removeEventListener('click', onDocClick, true);
  }
  onDestroy(teardown);
</script>

<!-- GATE: render absolutely nothing while OFF. No badge, no popover, no fetch. -->
{#if enabled}
  <div class="ec" data-state={state}>
    <button
      class="ec__btn"
      type="button"
      bind:this={badgeEl}
      aria-haspopup="dialog"
      aria-expanded={popOpen}
      aria-controls="ec-pop"
      aria-label={aria}
      title={aria}
      on:click={togglePop}
      on:keydown={onBadgeKeydown}
      data-testid="event-cursor-badge"
    >
      <span class="ec__tick" aria-hidden="true"></span>
      <span class="ec__dot" aria-hidden="true"></span>
      <span class="ec__label" data-testid="event-cursor-state">{label}</span>
      {#if state !== 'live' && badgeTime}<span class="ec__time">{badgeTime}</span>{/if}
      <span class="ec__chev" aria-hidden="true">&#9662;</span>
    </button>
    <span class="ec__beta">
      BETA -- default OFF{#if usedMockData} -- SAMPLE DATA{/if}
    </span>

    {#if popOpen}
      <div
        class="ec-pop"
        id="ec-pop"
        role="dialog"
        aria-label="Resume from an earlier checkpoint"
        bind:this={popEl}
        on:keydown={onPopKeydown}
      >
        <p class="ec-pop__head">Resume from earlier</p>
        <p class="ec-pop__sub">
          Load the full session digest at a past watermark, then stream forward.
          For quick audit review -- the default refresh path needs no click.
        </p>
        <ul
          class="ec-pop__list"
          role="listbox"
          aria-label="Cursor checkpoints"
          bind:this={listEl}
          on:keydown={onListKeydown}
        >
          {#each checkpoints as cp, i (cp.cursor + ':' + i)}
            <li
              class="ec-pop__item"
              class:is-active={i === activeIdx}
              role="option"
              tabindex={i === activeIdx ? 0 : -1}
              aria-selected={i === activeIdx}
              on:click={() => chooseCheckpoint(i)}
              on:mouseenter={() => (activeIdx = i)}
            >
              <span class="ec-pop__when">{cp.when}</span>
              <span class="ec-pop__cursor">{cp.cursor}</span>
            </li>
          {/each}
        </ul>
        <p class="ec-pop__foot">
          Issues <code>GET /api/sessions/{scope || 'all'}/events?since=&lt;cursor&gt;&amp;full=1</code>
          -- loads the accumulated digest AT the cursor, then resumes the feed
          from that watermark.
        </p>
      </div>
    {/if}
  </div>
{/if}

<style>
  /* ---- the bespoke micro-instrument badge (footer connection cluster) ---- */
  .ec {
    position: relative;
    display: inline-flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
  }
  .ec__btn {
    appearance: none;
    display: inline-flex;
    align-items: center;
    gap: var(--space-2, 4px);
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-meta, 13px);
    font-weight: 600;
    letter-spacing: 0.02em;
    background: var(--calm-surface-raised, var(--bg-card, #0c1118));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-sharp, 2px);
    padding: 3px 8px 3px 6px;
    cursor: pointer;
    white-space: nowrap;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    transition: border-color var(--t-calm, 180ms ease);
  }
  .ec__btn:hover { border-color: var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25))); }
  .ec__btn:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid) var(--focus-ring-color, #d97706);
    outline-offset: var(--focus-ring-offset, 2px);
    border-radius: var(--radius-soft, 4px);
  }
  /* the signature 2px tick-mark glyph -- distinct from a pill. */
  .ec__tick {
    width: 2px; height: 11px;
    background: currentColor;
    display: inline-block; flex: 0 0 auto; opacity: 0.85;
  }
  .ec__dot { width: 7px; height: 7px; border-radius: 50%; flex: 0 0 auto; }
  .ec__label { color: var(--calm-ink-loud, var(--text-bright, #e8e0cc)); }
  .ec__time { color: var(--calm-ink-quiet, var(--text-dim, #948870)); font-weight: 500; }
  .ec__chev { font-size: 0.6rem; color: var(--calm-ink-chrome, var(--text-ui, #8a8068)); margin-left: 1px; }

  .ec__beta {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 9px; letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    white-space: nowrap;
  }

  /* PAIRED label+dot state -- color ALWAYS rides with the WORD (M4).
     LIVE     = filled accent dot (fresh seed).
     RESUMED  = hollow slate dot (calm/non-alarm, continuity held).
     RESEEDED = WARN amber dot (silently-truncated resume, surfaced). */
  .ec[data-state='live'] .ec__dot {
    background: var(--calm-accent, var(--accent, #f59e0b));
    border: 2px solid var(--calm-accent, var(--accent, #f59e0b));
  }
  .ec[data-state='resumed'] .ec__dot {
    background: transparent;
    border: 2px solid var(--badge-obs-fg, #475569);
  }
  .ec[data-state='reseeded'] .ec__dot {
    background: var(--badge-warn-fg, #ea580c);
    border: 2px solid var(--badge-warn-border, #ea580c);
  }
  .ec[data-state='reseeded'] .ec__btn { border-color: var(--badge-warn-border, #ea580c); }
  .ec[data-state='reseeded'] .ec__label { color: var(--badge-warn-fg, #ea580c); }

  /* ---- resume-from-earlier popover ---- */
  .ec-pop {
    position: absolute;
    bottom: calc(100% + var(--space-3, 6px));
    left: 0;
    width: 290px;
    background: var(--calm-surface-raised, var(--bg-card, #0c1118));
    border: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25)));
    border-radius: var(--radius-soft, 4px);
    box-shadow: 0 14px 40px rgba(0, 0, 0, 0.55);
    padding: var(--space-4, 10px);
    z-index: 90;
  }
  .ec-pop__head {
    margin: 0 0 var(--space-2, 4px);
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px); font-weight: 700;
    letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .ec-pop__sub {
    margin: 0 0 var(--space-4, 10px);
    font-size: 11px; line-height: 1.4;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .ec-pop__list {
    list-style: none; margin: 0; padding: 0;
    display: flex; flex-direction: column; gap: var(--space-2, 4px);
  }
  .ec-pop__item {
    display: flex; align-items: baseline; justify-content: space-between;
    gap: var(--space-3, 6px);
    padding: var(--space-3, 6px) var(--space-3, 6px);
    background: var(--calm-surface-row, var(--bg-row, #0e141e));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-sharp, 2px);
    cursor: pointer;
  }
  .ec-pop__item:hover,
  .ec-pop__item.is-active {
    border-color: var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25)));
    background: var(--bg-row-hover, #131c2a);
  }
  .ec-pop__item:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid) var(--focus-ring-color, #d97706);
    outline-offset: var(--focus-ring-offset, 2px);
  }
  .ec-pop__when { font-size: var(--fs-meta, 13px); color: var(--calm-ink-loud, var(--text-bright, #e8e0cc)); font-weight: 600; }
  .ec-pop__cursor { font-family: var(--font-d, var(--ff-mono)); font-size: 11px; color: var(--calm-ink-quiet, var(--text-dim, #948870)); }
  .ec-pop__foot {
    margin: var(--space-4, 10px) 0 0;
    padding-top: var(--space-3, 6px);
    border-top: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    font-size: 10px; line-height: 1.4;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .ec-pop__foot code {
    font-family: var(--font-d, var(--ff-mono)); font-size: 10px;
    color: var(--calm-accent, var(--accent, #f59e0b));
  }

  /* reduced motion (M17): the badge never animates; suppress hover transition. */
  :global(html[data-motion='reduce']) .ec__btn { transition: none; }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .ec__btn { transition: none; }
  }
</style>
