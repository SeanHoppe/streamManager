<!--
  SessionRail.svelte -- the multi-session GLANCE LAYER (GRAFT: ops-command-deck).

  THE operator-fit core of this unit. The rail is one calm lane per NON-SELF
  governed session, giving the single-operator laptop user glance-readability
  across concurrent sessions (the stated need). It is the spine's calm slate
  rail: still water at rest, lanes warm only on a per-lane ACTION REQUIRED tally
  and the lone true M2 escalation.

  M15 / G2 (self-exclude polarity) -- STRUCTURALLY VISIBLE: the rail renders
  from the `sessions` store, which filters the SM's own session out in
  setSessions() (defense-in-depth atop the server-side strip). The rail NEVER
  constructs a lane for the own session; there is no code path that could. The
  own-session id is shown in the rail FOOTER as an explicit "excluded" readout
  so the polarity is auditable on screen, not just in a comment.

  M16 (domain-agnostic) -- STRUCTURALLY VISIBLE: every lane's identity comes
  from /api/sessions row data (project_slug / id). The rail hard-codes NO
  monitored-project vocabulary. The empty state and the footer speak only in
  the UI's own taxonomy ("sessions", "governed targets"), never a target name.

  CALM-AMBIENT (spine): the rail chrome is whisper-quiet -- a hairline frame, a
  dim header, slate lanes. The only saturated affordances are (a) the per-lane
  amber ACTION-REQUIRED edge/badge and (b) the lone escalation pulse, both
  driven by the data-fed tally/escalation maps -- never by rail-local state.

  DATA: subscribes to the shared session stores (u-stores). The parent shell
  feeds two plain maps keyed by session_id:
    - actionCounts: { [session_id]: number }  -- per-lane open ACTION REQUIRED.
    - escalations:  { [session_id]: { reason } | true } -- M2 allow-list hits,
      computed by u-escalation from the single escalation table (never here).
  The rail owns NO fetch (M18 post-hoc); it only renders + routes selection.

  Endpoints (consumed via the stores, not directly here): GET /api/sessions.
-->
<script>
  import { sessions, selectedSessionId, selectSession, ownSessionId } from '../stores/session.js';
  import SessionLane from './SessionLane.svelte';
  import { betaFlags } from '../stores/beta.js';
  import HealthDigest from './beta/HealthDigest.svelte';

  /**
   * actionCounts: per-session open-ACTION-REQUIRED tallies, keyed by session_id.
   * Fed by the shell from the decisions/hitl store. Missing key => 0 (calm).
   * @type {Record<string, number>}
   */
  export let actionCounts = {};

  /**
   * escalations: per-session M2 allow-list escalation descriptors, keyed by
   * session_id. A truthy value flips a lane to the lone foreground escalation;
   * `{ reason }` supplies the M4 accessible trigger string. Computed upstream
   * by u-escalation from the one escalation table -- the rail only consumes it.
   * @type {Record<string, { reason?: string } | boolean>}
   */
  export let escalations = {};

  /** title: rail heading. UI taxonomy only (M16) -- never a target name. */
  export let title = 'Sessions';

  // ---- self-exclude readout (M15 made visible) ---------------------------
  // The store already excludes self from `sessions`; we ALSO surface the
  // excluded id explicitly so the polarity is on-screen and auditable. Empty
  // meta => null => nothing to exclude (loud-fail-safe per M15).
  $: ownId = $ownSessionId;

  // ---- per-lane helpers (read from the data-fed maps; no local inference) -
  function countFor(id) {
    const n = Number(actionCounts && actionCounts[id]);
    return Number.isFinite(n) && n > 0 ? n : 0;
  }
  function escFor(id) {
    return escalations ? escalations[id] : undefined;
  }
  function escReasonFor(id) {
    const e = escFor(id);
    return e && typeof e === 'object' && typeof e.reason === 'string' ? e.reason : '';
  }

  // Rail-level aggregate tally for the header (sum of per-lane open actions
  // across all visible governed sessions). Paired with the literal "ACTIVE"
  // label below -- the number never stands alone (M4 spirit).
  $: totalOpen = $sessions.reduce((acc, s) => acc + countFor(s.id), 0);

  // Are any lanes escalated? Drives the header's escalation marker (text +
  // edge, never color-alone). Reads only the data-fed map.
  $: anyEscalated = $sessions.some((s) => Boolean(escFor(s.id)));

  function onSelect(e) {
    // SessionLane emits { id }. Route through the store's guarded setter, which
    // refuses to ever resolve to the own session (M15/G2 belt-and-braces).
    selectSession(e.detail.id);
  }

  // "ALL governed sessions" reset -- clears the scope filter (null). The header
  // exposes this so the operator can always escape a single-session scope.
  function selectAll() {
    selectSession(null);
  }
  $: allActive = $selectedSessionId === null;
</script>

<nav class="rail" aria-label="Governed sessions">
  <header class="rail__head">
    <div class="rail__title-wrap">
      <h2 class="rail__title">{title}</h2>
      <!-- header tally: paired label + count (M4 spirit). Calm slate unless
           open actions exist, then it warms via the modifier (color is the
           SECOND channel atop the always-present text). -->
      <span
        class="rail__tally"
        class:rail__tally--active={totalOpen > 0}
        class:rail__tally--esc={anyEscalated}
        title={totalOpen > 0
          ? `${totalOpen} open action${totalOpen === 1 ? '' : 's'} across ${$sessions.length} session${$sessions.length === 1 ? '' : 's'}`
          : `Observing ${$sessions.length} session${$sessions.length === 1 ? '' : 's'} -- no open actions`}
        aria-label={totalOpen > 0
          ? `${totalOpen} open actions across all governed sessions`
          : 'No open actions across governed sessions'}
      >
        <span class="rail__tally-tag">ACTIVE</span>
        <span class="rail__tally-num">{totalOpen}</span>
      </span>
    </div>

    <!-- "ALL" scope control: the deliberate, reachable un-scoped state. -->
    <button
      type="button"
      class="rail__all"
      class:rail__all--active={allActive}
      aria-pressed={allActive}
      title="Show all governed sessions (clear scope filter)"
      aria-label="Select all governed sessions"
      on:click={selectAll}
    >ALL</button>
  </header>

  {#if $betaFlags['health-digest']}
    <!-- BETA #32: multi-session health digest glance widget, above the lanes.
         Reuses the rail's guarded onSelect (G2-safe session select). -->
    <div class="rail__digest">
      <HealthDigest on:select={onSelect} />
    </div>
  {/if}

  <!-- role="list" ONLY when lanes exist: an empty list whose sole child is the
       <p> empty-state has no listitem child and trips aria-required-children
       (axe critical). Dropping the role while empty keeps the calm empty state
       valid; the listitem wrappers below restore it the moment lanes render. -->
  <div class="rail__lanes" role={$sessions.length === 0 ? undefined : 'list'}>
    {#if $sessions.length === 0}
      <!-- Empty state: domain-agnostic, calm. We never invent a target name. -->
      <p class="rail__empty">
        No governed sessions yet. Lanes appear here as non-SM sessions are
        observed.
      </p>
    {:else}
      {#each $sessions as s (s.id)}
        <div role="listitem" class="rail__lane-wrap">
          <SessionLane
            session={s}
            selected={$selectedSessionId === s.id}
            actionCount={countFor(s.id)}
            escalated={Boolean(escFor(s.id))}
            escalationReason={escReasonFor(s.id)}
            on:select={onSelect}
          />
        </div>
      {/each}
    {/if}
  </div>

  <!-- M15 footer: the polarity, on-screen. When the server injected an own
       session id we state it is excluded; when absent we state self-filtering
       is inactive (loud-fail-safe). Never presents self AS a governed lane. -->
  <footer class="rail__foot">
    {#if ownId}
      <span class="rail__self" title={`StreamManager's own session (${ownId}) is never governed`}>
        <span class="rail__self-dot" aria-hidden="true"></span>
        self excluded
      </span>
    {:else}
      <span class="rail__self rail__self--inactive" title="No own-session id injected; self-filtering inactive (showing all)">
        <span class="rail__self-dot" aria-hidden="true"></span>
        self-filter inactive
      </span>
    {/if}
  </footer>
</nav>

<style>
  /* The rail: a calm slate spine. Hairline frame, dim chrome, quiet header.
     Still water -- it must not shimmer with per-decision activity. */
  .rail {
    display: flex;
    flex-direction: column;
    min-height: 0;
    height: 100%;
    background: var(--calm-surface-raised, var(--bg-card, #0c1118));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-soft, 4px);
    overflow: hidden;
  }

  .rail__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4, 10px);
    padding: var(--space-4, 10px) var(--space-5, 14px);
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    background: var(--calm-surface, var(--bg, #080a0c));
  }

  .rail__title-wrap {
    display: inline-flex;
    align-items: baseline;
    gap: var(--space-4, 10px);
    min-width: 0;
  }

  .rail__title {
    margin: 0;
    font-family: var(--font-h, var(--ff-system));
    font-size: var(--fs-body, 14px);
    font-weight: 560;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    white-space: nowrap;
  }

  /* Header tally: paired tag + number. Calm at rest, warms on open actions. */
  .rail__tally {
    display: inline-flex;
    align-items: baseline;
    gap: 5px;
    padding: 2px 7px;
    border-radius: 999px;
    border: var(--hairline, 1px) solid transparent;
    background: var(--calm-accent-wash, rgba(245, 158, 11, 0.09));
    transition: background var(--t-flash, 300ms ease),
                border-color var(--t-flash, 300ms ease);
  }
  .rail__tally-tag {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.13em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .rail__tally-num {
    font-family: var(--font-d, var(--ff-mono));
    font-variant-numeric: tabular-nums;
    font-size: var(--fs-meta, 13px);
    font-weight: 560;
    line-height: 1;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    min-width: 1ch;
    text-align: right;
  }
  /* Active: the amber ACTION-REQUIRED palette as the second channel atop the
     always-present "ACTIVE N" text (M4 -- color never alone). */
  .rail__tally--active {
    background: var(--badge-ar-bg, #fef3c7);
    border-color: var(--badge-ar-border, #d97706);
  }
  .rail__tally--active .rail__tally-tag,
  .rail__tally--active .rail__tally-num { color: var(--badge-ar-fg, #d97706); }
  .rail__tally--active .rail__tally-num { font-weight: 720; }
  /* Escalation present: the one permitted pulse, applied to the header tally so
     the operator sees rail-level escalation at a glance. Reduced-motion aware
     via calm.css .is-escalating fallback rules. */
  .rail__tally--esc { animation: rail-tally-pulse 1.6s ease-in-out infinite; }

  @keyframes rail-tally-pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(217, 119, 6, 0.5); }
    50%      { box-shadow: 0 0 0 4px rgba(217, 119, 6, 0); }
  }

  /* ALL control: clears the scope filter. Calm pill; active = accent edge. */
  .rail__all {
    appearance: none;
    flex: 0 0 auto;
    background: transparent;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    font-weight: 600;
    letter-spacing: 0.1em;
    padding: 3px 9px;
    border-radius: 999px;
    cursor: pointer;
    transition: color var(--t-calm, 180ms ease),
                border-color var(--t-calm, 180ms ease),
                background var(--t-calm, 180ms ease);
  }
  .rail__all:hover {
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    border-color: var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25)));
  }
  .rail__all--active {
    color: var(--calm-accent, var(--accent, #f59e0b));
    border-color: var(--calm-accent, var(--accent, #f59e0b));
    background: var(--calm-accent-wash, rgba(245, 158, 11, 0.09));
  }

  /* M17 focus ring on every interactive element. */
  .rail__all:focus-visible {
    outline: 2px solid var(--badge-ar-border, #d97706);
    outline-offset: 2px;
  }

  /* Independent-scroll lane list (monitor-first-elevated graft: per-frame
     independent scroll discipline). The rail body owns its own scroll; it never
     drags sibling frames. */
  .rail__lanes {
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
    overflow-x: hidden;
    overscroll-behavior: contain;
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 6px);
    padding: var(--space-4, 10px);
    scrollbar-gutter: stable;
  }
  .rail__lane-wrap { display: block; }

  .rail__empty {
    margin: 0;
    padding: var(--space-5, 14px) var(--space-4, 10px);
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    font-size: var(--fs-meta, 13px);
    font-style: italic;
    line-height: var(--lh-body, 1.5);
  }

  /* M15 footer: the self-exclude polarity, on-screen + auditable. */
  .rail__foot {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    padding: var(--space-2, 4px) var(--space-5, 14px);
    border-top: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    background: var(--calm-surface, var(--bg, #080a0c));
  }
  .rail__self {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .rail__self-dot {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--calm-ink-quiet, var(--text-dim, #948870));
    opacity: 0.7;
  }
  /* The inactive state is conveyed by the TEXT ("self-filter inactive"), NOT by
     dimming: an opacity drag on this small footer text pushed --calm-ink-chrome
     under WCAG AA (axe color-contrast ~3.0). The base ink already passes AA, so
     the inactive variant simply keeps it -- no opacity. */

  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .rail__tally,
    :global(html:not([data-motion='allow'])) .rail__all { transition: none; }
    :global(html:not([data-motion='allow'])) .rail__tally--esc { animation: none; box-shadow: 0 0 0 1px #d97706 inset; }
  }
  :global(html[data-motion='reduce']) .rail__tally--esc {
    animation: none !important;
    box-shadow: 0 0 0 1px #d97706 inset;
  }
  :global(html[data-motion='allow']) .rail__tally--esc {
    animation: rail-tally-pulse 1.6s ease-in-out infinite !important;
  }
</style>
