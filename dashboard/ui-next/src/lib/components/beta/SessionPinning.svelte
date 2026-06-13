<!--
  SessionPinning.svelte -- BETA feature "session-pinning" (#25):
  Session-per-Agent Pinning swim-lane (Frame B).

  WHAT IT DOES
    Frame B's roster defaults to "most-recently-active first". When the operator
    pauses or shifts focus, that ordering shuffles and a watched agent can fall
    below the fold on a 13-inch laptop. This feature lets the operator NAIL an
    observed sub-agent to a PINNED group at row 1, ABOVE the auto "Active in
    window" group, so churn can never bury it. Click the pin glyph on a row (or
    Enter/Space on the focused button) to toggle. Pinned rows keep FULL opacity
    even when idle -- they do not recede. The header carries a "N pinned" count
    chip beside the M3 action count so the two signals read as distinct.

  CLIENT-SIDE ONLY. No backend, no new endpoint, no new bus envelope, no new
  table. It REORDERS the existing roster only: no agent is hidden, no count is
  fabricated, nothing is POSTed. Pin state is a per-session Set persisted in
  localStorage (the session-store key idiom). It reads ONLY the shared, already-
  self-excluded client stores (agentsStore from pollers.js, settings +
  selectedSessionId from the stores) -- it never queries, never opens
  /api/commands/stream, never sits on the verdict hot path (M18).

  BETA GATING (default OFF -- load-bearing). The ENTIRE body is wrapped in
  {#if enabled}. While $betaFlags["session-pinning"] is OFF the component renders
  NOTHING and registers NO poller / SSE handler / timer / store-effect of its
  own (it merely $-subscribes to the shared agentsStore that the live shell
  already runs; flipping OFF unmounts every row + clears the live region). The
  flag defaults OFF (lib/beta/registry.js); the operator flips it in
  Settings > BETA features ("Session-per-agent pinning").

  ADR-18 MUST floor honoured here:
    - M1 3-frame presence: this is a Frame B BODY swap (the same shelf), NEVER a
      4th frame and never a removed one. It is mounted INSIDE the existing
      frameB slot in place of the plain AgentRoster while the flag is ON.
    - M2 escalation-only foreground: pinning NEVER auto-foregrounds. Pinning an
      agent re-sorts it to row 1 of its frame in place; it raises no escalation,
      sets no `escalated`, and steals no focus to the frame.
    - M4 paired label+color: the pinned state renders a LITERAL "PINNED" text
      chip + a group label + a filled glyph (triple signal). The pin hue is a
      desaturated slate-cyan (--sp-pin-*), DELIBERATELY not the FROZEN amber
      action-required identity -- color is never the only signal, and pin can
      never be mistaken for an escalation.
    - M13: one row per observed agent; chronological event chips per agent;
      NO inter-agent blocking edge is shown. Idle agents fade but are never
      dropped. The pinned partition is a strict superset of the FR-UI-1 sort.
    - M15/G2 polarity: the agentsStore it reads is SM-self excluded upstream
      (project_slug NOT IN {streamManager} AND session_id != self). This feature
      adds no query of its own; the localStorage pin key is scoped per (non-self)
      session_id. It cannot surface or pin an SM-self row.
    - M16 domain-agnostic: every agent identity + the pin key render FROM DATA
      (profile_slug / attribution_plugin). The only literals are SM's own UI copy
      and the generic role schema in RoleBadge.
    - M17 a11y AAA: each pin control is a real <button> with aria-pressed + a
      descriptive aria-label; the whole roster is keyboard-operable; focus stays
      on the just-toggled button after the re-sort (pin several without losing
      your place); an aria-live=polite region announces pin/unpin; reduced motion
      honoured via data-motion.
    - M18: presentation-only; no fetch, off the verdict hot path.

  When live gov.db data is absent (fresh DB -- agentsStore empty) it falls back
  to a realistic, domain-agnostic mock roster (SessionPinning-data.mockRoster)
  so the feature is always testable headless (usedMockData=true, surfaced as a
  literal text label).

  All selectors are .sp-* scoped so this feature pollutes no shared class.
  Tokens come from theme.css; the NEW pin tokens (--sp-pin-*) are defined in this
  component's :global([data-theme]) block per theme so the slate-cyan re-themes.

  ASCII-only (cp1252-safe): dash is "--". No smart quotes, no em-dashes.
-->
<script>
  import { onDestroy, tick } from 'svelte';
  import RoleBadge from '../RoleBadge.svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { agentsStore } from '../../pollers.js';
  import { settings } from '../../stores/settings.js';
  import { selectedSessionId } from '../../stores/session.js';
  import {
    pinStorageKey,
    pinSuffix,
    loadPins,
    savePins,
    projectRoster,
    mockRoster,
    relTime,
  } from './SessionPinning-data.js';

  const FLAG_KEY = 'session-pinning';

  /**
   * actionCount: the M3 open-ACTION-REQUIRED count for Frame B, OWNED by the
   * shell and passed in so this body can render the same header count chip the
   * plain Frame B header would (paired with the NEW pin count). /api/agents
   * carries no action verdict, so this body never fabricates a count. Default 0.
   */
  export let actionCount = 0;

  // -- gate: TRUE only while the operator has the BETA flag ON. The entire
  // template + every effect below is conditioned on this. --------------------
  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // -- safe storage handle (private mode / SSR => null => pins are in-memory) --
  const storage = (() => {
    try {
      return typeof localStorage === 'undefined' ? null : localStorage;
    } catch {
      return null;
    }
  })();

  // -- live roster source: the shared 8s /api/agents poller store, already
  // session-scoped + SM-self excluded upstream. When it is empty we fall back
  // to the mock roster so the feature is demonstrable/testable headless. -------
  $: liveAgents = Array.isArray($agentsStore) ? $agentsStore : [];
  $: liveEmpty = liveAgents.length === 0;

  // a stable mock (one instance per mount) so pin toggles persist within a run.
  let _mock = null;
  function getMock() {
    if (!_mock) _mock = mockRoster(Date.now());
    return _mock;
  }

  $: usedMockData = enabled && liveEmpty;
  $: agents = usedMockData ? getMock().agents : liveAgents;
  // the session scope that keys the localStorage pin bucket. With live data we
  // use the operator-selected session; with mock data we use the mock session
  // so a tester's pins persist under a stable, self-contained key.
  $: scopeId = usedMockData ? getMock().sessionId : ($selectedSessionId || null);
  $: activityWindowSec = usedMockData ? getMock().activityWindowSec : $settings.activityWindowSec;

  // -- pin state (per-session Set + earliest-pinned-first order) --------------
  /** @type {Set<string>} */
  let pinnedSet = new Set();
  /** @type {string[]} */
  let pinOrder = [];
  let _loadedKey = null; // the storage key currently loaded (re-load on scope change)

  // (Re)load pins whenever the scope changes OR the feature turns ON. Seed the
  // mock default-pin the FIRST time a mock scope is loaded with no stored pins,
  // so the demo shows the "developer pinned at row 1" story out of the box.
  $: if (enabled) reloadPinsFor(scopeId);

  /** @param {string|null} sid */
  function reloadPinsFor(sid) {
    const key = pinStorageKey(sid);
    if (key === _loadedKey) return; // already loaded this scope
    _loadedKey = key;
    const { set, order } = loadPins(storage, key);
    if (set.size === 0 && usedMockData) {
      // first mock load with nothing stored -> seed the demo default pins.
      const seed = getMock().defaultPins.filter(Boolean);
      pinnedSet = new Set(seed);
      pinOrder = seed.slice();
    } else {
      pinnedSet = set;
      pinOrder = order;
    }
  }

  // -- live clock for the active/idle re-partition. ONE timer for the whole
  // roster, started ONLY while enabled (the gate is load-bearing) and torn down
  // when the flag flips OFF or the component is destroyed. --------------------
  let nowMs = Date.now();
  /** @type {ReturnType<typeof setInterval>|null} */
  let clockTimer = null;

  $: syncClock(enabled);
  function syncClock(on) {
    if (on && !clockTimer) {
      nowMs = Date.now();
      clockTimer = setInterval(() => { nowMs = Date.now(); }, 1000);
    } else if (!on && clockTimer) {
      clearInterval(clockTimer);
      clockTimer = null;
    }
  }

  // -- derived, sorted roster (PINNED -> ACTIVE -> IDLE) ----------------------
  $: rows = enabled
    ? projectRoster(agents, pinnedSet, pinOrder, nowMs, activityWindowSec)
    : [];
  $: pinnedRows = rows.filter((r) => r.pinned);
  $: activeRows = rows.filter((r) => r.isActive);
  $: idleRows = rows.filter((r) => !r.pinned && !r.isActive);
  $: pinnedCount = pinnedRows.length;

  // -- aria-live announcement -------------------------------------------------
  let liveMsg = '';
  function announce(msg) {
    // clear then set so AT re-reads an identical consecutive message.
    liveMsg = '';
    tick().then(() => { liveMsg = msg; });
  }

  // -- toggle (optimistic, synchronous, no network) ---------------------------
  /** @param {string} suffix @param {string} name */
  async function togglePin(suffix, name) {
    if (!suffix) return;
    if (pinnedSet.has(suffix)) {
      pinnedSet.delete(suffix);
      pinOrder = pinOrder.filter((s) => s !== suffix);
      pinnedSet = pinnedSet; // trigger reactivity
      announce(`Unpinned ${name}. It returns to its activity-sorted position.`);
    } else {
      pinnedSet.add(suffix);
      pinOrder = [...pinOrder, suffix];
      pinnedSet = pinnedSet; // trigger reactivity
      announce(`Pinned ${name} to the top. It stays put while others churn.`);
    }
    savePins(storage, _loadedKey || pinStorageKey(scopeId), pinOrder);
    // keep focus on the just-toggled button after the re-sort so the operator
    // can pin several agents without losing their place.
    await tick();
    refocus(suffix);
  }

  /** @type {HTMLElement|null} */
  let rosterEl = null;
  /** @param {string} suffix */
  function refocus(suffix) {
    if (!rosterEl) return;
    const sel = `.sp-pin-btn[data-suffix="${cssAttr(suffix)}"]`;
    const btn = rosterEl.querySelector(sel);
    if (btn && typeof btn.focus === 'function') btn.focus();
  }
  /** @param {string} s @returns {string} */
  function cssAttr(s) {
    return String(s).replace(/["\\]/g, '\\$&');
  }

  // -- BETA gate teardown: when the flag flips OFF (or on destroy), drop the
  // clock + clear the live region so nothing lingers. The {#if enabled} block
  // already unmounts the DOM; this clears the side-channels. -------------------
  $: if (!enabled) teardown();
  function teardown() {
    if (clockTimer) { clearInterval(clockTimer); clockTimer = null; }
    liveMsg = '';
    _loadedKey = null;
  }
  onDestroy(teardown);

  /** @param {number} ms @returns {string} */
  function rel(ms) { return relTime(ms, nowMs); }
</script>

{#if enabled}
  <div class="sp-root" data-testid="session-pinning">
    <!-- HEADER STRIP: BETA marker + the two count chips (M3 action + NEW pinned).
         Side by side ON PURPOSE so the operator sees they are different signals. -->
    <div class="sp-head">
      <span class="sp-beta">BETA</span>
      <span class="sp-head__title">Pinning</span>
      <span class="sp-spacer"></span>
      {#if actionCount > 0}
        <span class="sp-chip sp-chip--action" title="Actions required (M3) -- escalation signal">
          <span class="sp-chip__num">{actionCount}</span> action
        </span>
      {/if}
      <span
        class="sp-chip sp-chip--pinned"
        data-testid="session-pinning-count"
        title="Sticky pins set on this session"
        aria-label={`${pinnedCount} pinned`}
      >
        <span class="sp-chip__num">{pinnedCount}</span> pinned
      </span>
    </div>

    <!-- data-source line: ALWAYS a literal text label (mock vs live) -->
    <p class="sp-source" data-mock={usedMockData}>
      {usedMockData
        ? 'SAMPLE DATA -- no agents observed in gov.db yet; showing a representative roster.'
        : 'LIVE -- observed agents from /api/agents (polarity-filtered, this session).'}
    </p>

    <!-- ROSTER: role=list only when populated (an empty list with no listitem
         child trips axe aria-required-children). -->
    <div
      class="sp-roster"
      role={rows.length === 0 ? undefined : 'list'}
      aria-label="Sub-agent roster (pinning)"
      bind:this={rosterEl}
    >
      {#if rows.length === 0}
        <p class="sp-empty">Still water. No sub-agents observed for this session yet.</p>
      {:else}
        {#if pinnedRows.length}
          <!-- PINNED group divider: paired glyph + label + count (M4). -->
          <div class="sp-group sp-group--pinned" role="presentation">
            <span class="sp-group__glyph" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="11" height="11"><circle cx="12" cy="9" r="6" fill="currentColor"/><path d="M12 15 L12 21" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
            </span>
            <span class="sp-group__label">Pinned</span>
            <span class="sp-group__count">{pinnedRows.length}</span>
          </div>
          {#each pinnedRows as r (r.key)}
            <div
              class="sp-row sp-row--pinned"
              role="listitem"
              aria-label={`Sub-agent ${r.name} (pinned)`}
            >
              <div class="sp-row__lead">
                <RoleBadge role={r.role} sidechain={r.sidechain} />
                <span class="sp-row__name" title={r.name}>{r.name}</span>
                <span class="sp-pinned-chip">
                  <svg viewBox="0 0 24 24" width="11" height="11" aria-hidden="true"><circle cx="12" cy="9" r="6" fill="currentColor"/><path d="M12 15 L12 21" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
                  PINNED
                </span>
                <button
                  class="sp-pin-btn is-pinned"
                  type="button"
                  data-suffix={r.suffix}
                  aria-pressed="true"
                  aria-label={`Unpin ${r.name} from top`}
                  title={`Unpin ${r.name} from top`}
                  on:click={() => togglePin(r.suffix, r.name)}
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle class="sp-fill" cx="12" cy="9" r="6" stroke="currentColor" stroke-width="1.6"/><path d="M12 15 L12 21" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
                </button>
              </div>
              <div class="sp-row__events" aria-label="Activity trail">
                {#if Number.isFinite(r.firstMs)}<span class="sp-event">seen {rel(r.firstMs)}</span>{/if}
                {#if r.skill}<span class="sp-event">{r.skill}</span>{/if}
                {#if r.modeOverride}<span class="sp-event sp-event--mode">mode: {r.modeOverride}</span>{/if}
                {#if Number.isFinite(r.lastMs) && r.lastMs !== r.firstMs}<span class="sp-event sp-event--active">active {rel(r.lastMs)}</span>{/if}
              </div>
            </div>
          {/each}
        {/if}

        {#if activeRows.length}
          <div class="sp-group sp-group--active" role="presentation">
            <span class="sp-group__dot sp-group__dot--live" aria-hidden="true"></span>
            <span class="sp-group__label">Active in window</span>
            <span class="sp-group__count">{activeRows.length}</span>
          </div>
          {#each activeRows as r (r.key)}
            <div class="sp-row sp-row--active" role="listitem" aria-label={`Sub-agent ${r.name} (active)`}>
              <div class="sp-row__lead">
                <RoleBadge role={r.role} sidechain={r.sidechain} />
                <span class="sp-row__name" title={r.name}>{r.name}</span>
                <span class="sp-live"><span class="sp-live__dot" aria-hidden="true"></span>live</span>
                <button
                  class="sp-pin-btn"
                  type="button"
                  data-suffix={r.suffix}
                  aria-pressed="false"
                  aria-label={`Pin ${r.name} to top`}
                  title={`Pin ${r.name} to top`}
                  on:click={() => togglePin(r.suffix, r.name)}
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle class="sp-fill" cx="12" cy="9" r="6" stroke="currentColor" stroke-width="1.6"/><path d="M12 15 L12 21" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
                </button>
              </div>
              <div class="sp-row__events" aria-label="Activity trail">
                {#if Number.isFinite(r.firstMs)}<span class="sp-event">seen {rel(r.firstMs)}</span>{/if}
                {#if r.skill}<span class="sp-event">{r.skill}</span>{/if}
                {#if r.modeOverride}<span class="sp-event sp-event--mode">mode: {r.modeOverride}</span>{/if}
                {#if Number.isFinite(r.lastMs) && r.lastMs !== r.firstMs}<span class="sp-event sp-event--active">active {rel(r.lastMs)}</span>{/if}
              </div>
            </div>
          {/each}
        {/if}

        {#if idleRows.length}
          <div class="sp-group sp-group--idle" role="presentation">
            <span class="sp-group__dot" aria-hidden="true"></span>
            <span class="sp-group__label">Idle</span>
            <span class="sp-group__count">{idleRows.length}</span>
          </div>
          {#each idleRows as r (r.key)}
            <div class="sp-row sp-row--idle" role="listitem" aria-label={`Sub-agent ${r.name} (idle)`}>
              <div class="sp-row__lead">
                <RoleBadge role={r.role} sidechain={r.sidechain} />
                <span class="sp-row__name" title={r.name}>{r.name}</span>
                <button
                  class="sp-pin-btn"
                  type="button"
                  data-suffix={r.suffix}
                  aria-pressed="false"
                  aria-label={`Pin ${r.name} to top`}
                  title={`Pin ${r.name} to top`}
                  on:click={() => togglePin(r.suffix, r.name)}
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle class="sp-fill" cx="12" cy="9" r="6" stroke="currentColor" stroke-width="1.6"/><path d="M12 15 L12 21" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
                </button>
              </div>
              <div class="sp-row__events" aria-label="Activity trail">
                {#if Number.isFinite(r.firstMs)}<span class="sp-event">seen {rel(r.firstMs)}</span>{/if}
                {#if r.skill}<span class="sp-event">{r.skill}</span>{/if}
                {#if r.modeOverride}<span class="sp-event sp-event--mode">mode: {r.modeOverride}</span>{/if}
                {#if Number.isFinite(r.lastMs) && r.lastMs !== r.firstMs}<span class="sp-event sp-event--active">active {rel(r.lastMs)}</span>{/if}
              </div>
            </div>
          {/each}
        {/if}
      {/if}
    </div>

    <!-- aria-live region: announces pin / unpin (polite). -->
    <p class="sp-sr-only" aria-live="polite" data-testid="session-pinning-live">{liveMsg}</p>
  </div>
{/if}

<style>
  /* NEW per-feature pin tokens (slate-cyan). DELIBERATELY not the FROZEN amber
     action-required identity (M4). Defined per theme so the hue re-themes with
     [data-theme]; each value is tuned for AAA contrast on that theme's chip bg.
     :global() so the [data-theme] selector on <html> resolves against this
     scoped component. These tokens are ONLY consumed by .sp-* selectors. */
  :global([data-theme='obsidian']) .sp-root {
    --sp-pin-fg: #67c5d6; --sp-pin-bg: rgba(103, 197, 214, 0.13); --sp-pin-bd: rgba(103, 197, 214, 0.45);
  }
  :global([data-theme='phosphor']) .sp-root {
    --sp-pin-fg: #5fe0ff; --sp-pin-bg: rgba(95, 224, 255, 0.10); --sp-pin-bd: rgba(95, 224, 255, 0.40);
  }
  :global([data-theme='paper']) .sp-root {
    --sp-pin-fg: #0c5563; --sp-pin-bg: #dbeef2; --sp-pin-bd: #0c5563;
  }
  /* Fallback (no/unknown theme): the obsidian values. */
  .sp-root {
    --sp-pin-fg: #67c5d6; --sp-pin-bg: rgba(103, 197, 214, 0.13); --sp-pin-bd: rgba(103, 197, 214, 0.45);
  }

  .sp-root {
    display: flex;
    flex-direction: column;
    gap: 0;
    color: var(--sm-text, var(--text));
    font-family: var(--ff-system);
  }

  /* HEADER STRIP */
  .sp-head {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0 0.1rem 0.5rem;
  }
  .sp-beta {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.56rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: #92400e;
    background: var(--badge-ar-bg);
    border: 1px solid var(--badge-ar-border);
    border-radius: 4px;
    padding: 0.05rem 0.3rem;
  }
  .sp-head__title {
    font-size: 0.66rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--sm-text-dim, var(--text-dim));
  }
  .sp-spacer { flex: 1 1 auto; }

  .sp-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    padding: 0.18rem 0.45rem;
    border-radius: 999px;
    flex: 0 0 auto;
    font-variant-numeric: tabular-nums;
  }
  .sp-chip__num { font-weight: 800; }
  .sp-chip--action {
    color: var(--badge-ar-fg);
    background: var(--badge-ar-bg);
    border: 1px solid var(--badge-ar-border);
  }
  .sp-chip--pinned {
    color: var(--sp-pin-fg);
    background: var(--sp-pin-bg);
    border: 1px solid var(--sp-pin-bd);
  }

  .sp-source {
    margin: 0 0 0.55rem;
    font-size: 0.7rem;
    font-family: var(--font-d, var(--ff-mono));
    letter-spacing: 0.02em;
    color: var(--sm-text-dim, var(--text-dim));
  }
  .sp-source[data-mock='true'] {
    color: var(--badge-warn-fg);
  }
  /* PAPER surface (--bg-card #f8f4ee) is too light for #ea580c at AA; darken the
     WARN ink to #9a3412 on paper only. Dark themes keep the AA base. */
  :global([data-theme='paper']) .sp-source[data-mock='true'] {
    color: #9a3412;
  }

  /* ROSTER */
  .sp-roster {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .sp-empty {
    margin: 0;
    color: var(--sm-text-dim, var(--text-dim));
    font-size: 0.82rem;
    font-style: italic;
  }

  /* GROUP DIVIDERS (paired label + count, never color alone) */
  .sp-group {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    padding: 0.5rem 0.1rem 0.3rem;
    font-size: 0.66rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--sm-text-dim, var(--text-dim));
  }
  .sp-group--active,
  .sp-group--idle {
    margin-top: 0.35rem;
    border-top: 1px dashed var(--sm-border, var(--border));
    padding-top: 0.55rem;
  }
  .sp-group__dot {
    width: 0.42rem;
    height: 0.42rem;
    border-radius: 50%;
    background: var(--sm-text-dim, var(--text-dim));
    flex: 0 0 auto;
    opacity: 0.7;
  }
  .sp-group__dot--live {
    background: var(--c-allow, #22c55e);
    opacity: 1;
  }
  .sp-group__glyph {
    display: inline-flex;
    flex: 0 0 auto;
    color: var(--sp-pin-fg);
  }
  .sp-group__label { flex: 1 1 auto; }
  .sp-group--pinned .sp-group__label { color: var(--sp-pin-fg); }
  .sp-group__count {
    font-variant-numeric: tabular-nums;
    color: var(--sm-text, var(--text-bright));
  }

  /* ROWS */
  .sp-row {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    padding: 0.5rem 0.6rem;
    border-radius: 6px;
    border: 1px solid transparent;
    transition: background-color 0.2s ease, opacity 0.2s ease, border-color 0.2s ease;
  }
  .sp-row:hover,
  .sp-row:focus-within { background: var(--bg-row-hover, rgba(148, 163, 184, 0.07)); }

  .sp-row--active {
    background: var(--bg-row, rgba(148, 163, 184, 0.07));
    border-color: var(--sm-border, var(--border));
    position: relative;
  }
  .sp-row--active::before {
    content: '';
    position: absolute;
    inset: 0.4rem auto 0.4rem 0;
    width: 2px;
    border-radius: 2px;
    background: var(--c-allow, #22c55e);
    opacity: 0.7;
  }
  .sp-row--idle { opacity: 0.62; }

  /* PINNED rows keep FULL opacity even when idle -- the whole point is they do
     not recede. They get a calm slate-cyan left rail (NOT amber). */
  .sp-row--pinned {
    opacity: 1;
    position: relative;
    background: var(--bg-row, rgba(148, 163, 184, 0.07));
    border-color: var(--sp-pin-bd);
  }
  .sp-row--pinned::before {
    content: '';
    position: absolute;
    inset: 0.4rem auto 0.4rem 0;
    width: 2px;
    border-radius: 2px;
    background: var(--sp-pin-fg);
  }

  .sp-row__lead {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    min-width: 0;
  }
  .sp-row__name {
    font-family: var(--sm-font-mono, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.78rem;
    font-weight: 500;
    color: var(--sm-text-dim, var(--text));
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
    flex: 1 1 auto;
  }
  .sp-row--active .sp-row__name,
  .sp-row--pinned .sp-row__name {
    font-weight: 700;
    color: var(--sm-text, var(--text-bright));
  }

  /* live marker (paired text + dot) */
  .sp-live {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    flex: 0 0 auto;
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--c-allow, #16a34a);
  }
  .sp-live__dot {
    width: 0.4rem;
    height: 0.4rem;
    border-radius: 50%;
    background: currentColor;
  }

  /* PINNED text chip -- the load-bearing signal (fill is the SECOND channel). */
  .sp-pinned-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    flex: 0 0 auto;
    font-size: 0.6rem;
    font-weight: 800;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--sp-pin-fg);
    background: var(--sp-pin-bg);
    border: 1px solid var(--sp-pin-bd);
    padding: 0.1rem 0.4rem;
    border-radius: 4px;
  }

  /* the pin button (real <button> so the global focus ring applies) */
  .sp-pin-btn {
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 26px;
    padding: 0;
    margin-left: auto;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    color: var(--sm-text-dim, var(--text-ui));
    cursor: pointer;
    opacity: 0;
    transition: opacity 0.15s ease, background 0.15s ease, color 0.15s ease;
  }
  /* the pin glyph is quiet + only appears on hover/focus when unpinned */
  .sp-row:hover .sp-pin-btn,
  .sp-row:focus-within .sp-pin-btn,
  .sp-pin-btn:focus-visible { opacity: 1; }
  .sp-pin-btn:hover {
    background: var(--bg-row-hover, rgba(148, 163, 184, 0.12));
    color: var(--sm-text, var(--text-bright));
  }
  /* a pinned row's button is ALWAYS visible (filled) -- it is the unpin control */
  .sp-pin-btn.is-pinned {
    opacity: 1;
    color: var(--sp-pin-fg);
  }
  .sp-pin-btn svg { width: 15px; height: 15px; display: block; }
  .sp-pin-btn .sp-fill { fill: none; }
  .sp-pin-btn.is-pinned .sp-fill { fill: var(--sp-pin-fg); }

  /* EVENT CHIPS */
  .sp-row__events {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    padding-left: 0.1rem;
  }
  .sp-event {
    font-family: var(--sm-font-mono, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.66rem;
    line-height: 1;
    padding: 3px 6px;
    border-radius: 3px;
    color: var(--sm-text-dim, var(--text-dim));
    background: var(--bg-row-alt, rgba(148, 163, 184, 0.08));
    border: 1px solid var(--sm-border, var(--border));
    white-space: nowrap;
  }
  .sp-event--active {
    color: var(--c-allow, #16a34a);
    border-color: rgba(34, 197, 94, 0.3);
  }
  /* PAPER row-alt chip (--bg-row-alt #f5f1ea) is too light for the paper #16a34a
     --c-allow at AA inside a pinned row; darken the active-event ink to #15803d
     on paper only. Dark themes keep their AA-compliant --c-allow. */
  :global([data-theme='paper']) .sp-row--pinned .sp-row__events .sp-event--active {
    color: #166534;
  }
  .sp-event--mode {
    color: var(--badge-warn-fg);
    border-color: var(--badge-warn-border);
  }

  /* visually-hidden live region */
  .sp-sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
    border: 0;
  }

  /* A11Y (M17): the global 2px amber focus ring on every interactive element. */
  .sp-pin-btn:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid)
      var(--focus-ring-color, var(--sm-focus, #d97706));
    outline-offset: 2px;
  }

  /* Reduced motion (M17): drop transitions unless the operator force-allows. */
  :global(html[data-motion='reduce']) .sp-row,
  :global(html[data-motion='reduce']) .sp-pin-btn { transition: none; }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .sp-row,
    :global(html:not([data-motion='allow'])) .sp-pin-btn { transition: none; }
  }
</style>
