<!--
  SessionLane.svelte -- ONE calm lane for ONE non-self governed session.

  GRAFT (ops-command-deck): the SessionRail is the operator's glance layer
  across concurrent sessions. Each lane is a single non-self governed session,
  rendered ENTIRELY from /api/sessions data (M16 domain-agnostic): the lane's
  human identity is the session's `project_slug` (or the raw id when the slug
  is absent) -- NEVER a hard-coded monitored-project name. A SessionLane is
  never constructed for the SM's own session: the parent rail draws from the
  `sessions` store, which structurally self-excludes (M15 / G2 polarity).

  CALM-AMBIENT (winning spine): at rest the lane is slate-quiet -- a hairline
  edge, dim ink, no border, no glow. It earns visual weight ONLY in two ways,
  both contract-driven:
    1. a per-lane LIVE ACTION REQUIRED tally (M3 spirit at the session grain)
       rendered as a paired label+count badge (M4 -- color is never alone);
    2. the lone true M2 escalation: when `escalated` is set by the data-driven
       escalation allow-list (u-escalation), and ONLY then, the lane gains the
       amber escalation edge + the single permitted pulse. new_pattern /
       low_confidence / variance NEVER reach this flag -- they badge in place.

  S1: the session cwd is surfaced on expand (not auto-rejected): the operator
  manually verifies cwd is non-SM + non-firewalled before attaching. The lane
  exposes cwd prominently when expanded; it does not police it.

  M18: presentation-only. The lane fetches nothing; the rail/stores feed it the
  session row + tally. Off the verdict hot path.

  File-disjoint: theme tokens + Badge.svelte (the shared M4 primitive) only.
-->
<script>
  import { createEventDispatcher } from 'svelte';

  /**
   * session: a /api/sessions row. Carries id, project_slug, pid, started_at,
   * ended_at, hitl_mode, hitl_floor, and (when the watcher supplies it) cwd.
   * The ONLY identity source -- M16. Required.
   * @type {{ id:string, project_slug?:string|null, pid?:number|null,
   *   started_at?:number|null, ended_at?:number|null, hitl_mode?:string|null,
   *   hitl_floor?:number|null, cwd?:string|null }}
   */
  export let session;

  /** selected: is this lane the active scope filter? Drives the active edge. */
  export let selected = false;

  /**
   * actionCount: per-lane LIVE open-ACTION-REQUIRED tally for this session_id.
   * Supplied by the parent (derived from the decisions / hitl store scoped to
   * this session). 0 => calm resting lane. (M3 at session grain.)
   */
  export let actionCount = 0;

  /**
   * escalated: TRUE iff a genuine M2 allow-list escalation
   * (desktop_pause / governance_negative_regression / static-rule) is open for
   * THIS session. Set by u-escalation reading the one escalation table -- never
   * inferred locally. This is the SOLE trigger for the amber escalation edge +
   * pulse. Defaults false: calm.
   */
  export let escalated = false;

  /**
   * escalationReason: human trigger string for the escalated state, surfaced as
   * the accessible name of the escalation badge (M4 paired signal). Falls back
   * to a safe generic reason so the a11y name is never empty.
   */
  export let escalationReason = '';

  const dispatch = createEventDispatcher();

  // ---- identity, rendered from data only (M16) ---------------------------
  // Prefer the human project_slug; fall back to the raw session id so a lane is
  // always nameable WITHOUT inventing a label. We never hard-code a target name.
  $: rawId = session && session.id != null ? String(session.id) : '';
  $: slug =
    session && typeof session.project_slug === 'string' && session.project_slug.trim()
      ? session.project_slug.trim()
      : '';
  $: displayName = slug || (rawId ? shortId(rawId) : 'unnamed session');

  // A short, stable id fragment for the secondary line (tabular, monospace).
  function shortId(id) {
    if (id.length <= 12) return id;
    return `${id.slice(0, 6)}…${id.slice(-4)}`; // 6 + ellipsis + last 4
  }

  $: ended = session && (session.ended_at !== null && session.ended_at !== undefined);
  $: live = !ended;

  $: pid =
    session && session.pid !== null && session.pid !== undefined
      ? String(session.pid)
      : '';

  // S1: cwd surfaced on expand. Present only when the server/watcher attached it.
  $: cwd =
    session && typeof session.cwd === 'string' && session.cwd.trim()
      ? session.cwd.trim()
      : '';

  $: hitlMode =
    session && typeof session.hitl_mode === 'string' && session.hitl_mode.trim()
      ? session.hitl_mode.trim().toUpperCase()
      : '';

  $: hasActions = Number(actionCount) > 0;
  $: actionN = hasActions ? Number(actionCount) : 0;

  // ---- expand state (S1 cwd reveal) --------------------------------------
  let expanded = false;
  function toggleExpand(e) {
    // The expand toggle must not also fire the lane-select; stop bubbling.
    e.stopPropagation();
    expanded = !expanded;
  }

  // ---- selection -> parent (the rail writes selectedSessionId) -----------
  function selectLane() {
    dispatch('select', { id: rawId });
  }
  function onKey(e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      selectLane();
    }
  }

  // The lane's accessible name folds in every glanceable fact so a screen-
  // reader user gets the same "at a glance" read a sighted operator does.
  $: laneAria = (() => {
    const parts = [`Session ${displayName}`];
    parts.push(live ? 'live' : 'ended');
    if (hasActions) parts.push(`${actionN} action${actionN === 1 ? '' : 's'} required`);
    else parts.push('observing, no action required');
    if (escalated) parts.push('escalation -- foreground required');
    if (selected) parts.push('selected scope');
    return parts.join(', ');
  })();

  $: escReason =
    escalationReason && String(escalationReason).trim()
      ? String(escalationReason).trim()
      : 'Escalation open for this session -- operator attention required';
</script>

<div
  class="lane"
  class:lane--selected={selected}
  class:lane--live={live}
  class:lane--ended={ended}
  class:lane--actions={hasActions}
  class:lane--escalated={escalated}
  class:is-escalating={escalated}
  data-session-id={rawId}
  data-action-count={actionN}
  data-escalated={escalated ? 'true' : 'false'}
>
  <!-- The lane body is the selectable scope control. A button role + keyboard
       handler make it operable; the visible label + badges carry the signal. -->
  <div
    class="lane__main"
    role="button"
    tabindex="0"
    aria-pressed={selected}
    aria-label={laneAria}
    on:click={selectLane}
    on:keydown={onKey}
  >
    <!-- liveness pip: paired with the live/ended text below; never color-alone.
         Slate at rest; it does NOT carry escalation (the edge + badge do). -->
    <span
      class="lane__pip"
      class:lane__pip--live={live}
      class:calm-live-dot={live}
      aria-hidden="true"
    ></span>

    <span class="lane__id">
      <span class="lane__name" title={slug || rawId}>{displayName}</span>
      <!-- One compact, non-wrapping meta line (state . pid . hitl); it ellipsizes
           rather than wrapping so a lane never grows tall or collides with the
           signal pill at the narrow rail width. -->
      <span class="lane__meta">{live ? 'live' : 'ended'}{#if pid} <span class="lane__sep" aria-hidden="true">&middot;</span> pid {pid}{/if}{#if hitlMode} <span class="lane__sep" aria-hidden="true">&middot;</span> {hitlMode}{/if}</span>
    </span>

    <!-- Compact glance signal. OBSERVING lanes stay CALM (no pill) -- still water;
         only lanes that need attention earn the amber count pill, so the few that
         matter pop against the quiet rest. The amber left-edge + the count digit
         + the lane's aria-label (which states the full reason) are the paired M4
         signal -- color is never the sole channel. The pill is aria-hidden because
         laneAria already announces the count/escalation. -->
    {#if escalated}
      <span class="lane__flag lane__flag--esc" title={escReason} aria-hidden="true">!{actionN > 0 ? ` ${actionN}` : ''}</span>
    {:else if hasActions}
      <span
        class="lane__flag lane__flag--ar"
        title={`${actionN} action${actionN === 1 ? '' : 's'} required in ${displayName}`}
        aria-hidden="true"
      >&#9650;&nbsp;{actionN}</span>
    {/if}
  </div>

  <!-- S1 expand affordance: reveals cwd for the operator's manual non-SM /
       non-firewalled check. Separate control so it doesn't hijack selection. -->
  <button
    type="button"
    class="lane__expand"
    aria-expanded={expanded}
    aria-controls={`lane-detail-${rawId}`}
    title={expanded ? 'Hide session detail' : 'Show session detail (cwd)'}
    aria-label={expanded ? `Hide detail for ${displayName}` : `Show detail for ${displayName}`}
    on:click={toggleExpand}
  >
    <span class="lane__chev" class:lane__chev--open={expanded} aria-hidden="true">&rsaquo;</span>
  </button>

  {#if expanded}
    <div class="lane__detail" id={`lane-detail-${rawId}`} role="region" aria-label={`${displayName} detail`}>
      <dl class="lane__dl">
        <div class="lane__row">
          <dt>session</dt>
          <dd class="lane__mono">{rawId || '--'}</dd>
        </div>
        <div class="lane__row">
          <dt>cwd</dt>
          <dd class="lane__mono lane__cwd">
            {#if cwd}{cwd}{:else}<span class="lane__unknown">not reported -- verify manually before attaching</span>{/if}
          </dd>
        </div>
        {#if hitlMode}
          <div class="lane__row">
            <dt>hitl</dt>
            <dd class="lane__mono">{hitlMode}</dd>
          </div>
        {/if}
      </dl>
      <!-- S1 reminder, plain text: the UI surfaces cwd; the operator verifies. -->
      <p class="lane__s1">Verify cwd is non-SM and non-firewalled before attaching.</p>
    </div>
  {/if}
</div>

<style>
  /* THE calm lane. At rest: a hairline-edged shelf, low ink, no glow. It is the
     still-water resting state -- the rail must not shimmer with activity. */
  .lane {
    position: relative;
    display: grid;
    grid-template-columns: 1fr auto;
    grid-template-rows: auto auto;
    align-items: stretch;
    background: var(--calm-lane-bg, var(--bg-card, #0c1118));
    border: var(--hairline, 1px) solid var(--calm-lane-edge, var(--border, #192030));
    border-radius: var(--radius-soft, 4px);
    /* asymmetric left accent gutter is the only "edge" treatment at rest, and
       it is transparent until the lane has actions / escalates. */
    border-left-width: 2px;
    border-left-color: transparent;
    transition: border-color var(--t-calm, 180ms ease),
                background var(--t-calm, 180ms ease),
                box-shadow var(--t-flash, 300ms ease);
  }

  /* Selected: a quiet accent edge marks the active scope. Calm, not loud. */
  .lane--selected {
    border-left-color: var(--calm-accent, var(--accent, #f59e0b));
    background: var(--calm-surface-hover, var(--bg-row-hover, #131c2a));
  }

  /* Ended sessions recede further -- they are history, not live targets. */
  .lane--ended { opacity: 0.62; }

  /* Has-actions: the left gutter warms to the ACTION-REQUIRED amber. The paired
     badge inside still carries the literal text -- this edge is the SECOND
     channel only (M4: color is never alone). */
  .lane--actions {
    border-left-color: var(--badge-ar-border, #d97706);
  }

  /* THE lone true M2 escalation: amber edge + the one permitted pulse (the
     .is-escalating utility from calm.css). All saturation/motion budget is
     spent here, nowhere else in the rail. */
  .lane--escalated {
    border-color: var(--badge-ar-border, #d97706);
    border-left-color: var(--badge-ar-border, #d97706);
    background: var(--bg-row-flash, rgba(245, 158, 11, 0.09));
  }

  .lane__main {
    grid-column: 1;
    grid-row: 1;
    display: flex;
    align-items: center;
    gap: var(--space-3, 8px);
    min-width: 0;
    /* Tighter vertical rhythm: a denser, scannable list. */
    padding: 7px var(--space-4, 10px);
    cursor: pointer;
    text-align: left;
    border-radius: var(--radius-soft, 4px) 0 0 var(--radius-soft, 4px);
  }
  .lane__main:hover { background: var(--calm-surface-hover, var(--bg-row-hover, #131c2a)); }

  /* M17: 2px solid amber focus ring + 2px offset on every interactive element. */
  .lane__main:focus-visible,
  .lane__expand:focus-visible {
    outline: 2px solid var(--badge-ar-border, #d97706);
    outline-offset: 2px;
    border-radius: var(--radius-soft, 4px);
  }

  /* Liveness pip: slate at rest, breathes only while live (calm-live-dot from
     calm.css). It NEVER turns amber -- escalation lives on the edge + badge. */
  .lane__pip {
    flex: 0 0 auto;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--calm-ink-quiet, var(--text-dim, #948870));
    opacity: 0.6;
  }
  .lane__pip--live {
    background: var(--calm-accent, var(--accent, #f59e0b));
    opacity: 0.85;
  }

  .lane__id {
    display: flex;
    flex-direction: column;
    gap: 1px;
    min-width: 0;
    /* Take the row's slack so the name has real room (the pill + expand are
       flex:0) -- this is what stops the slug truncating to 3 chars. */
    flex: 1 1 auto;
  }

  /* The session name: rendered from data (M16). Variable-weight: calm regular
     weight at rest; the active scope and actions lift it via the modifiers. */
  .lane__name {
    font-family: var(--font-h, var(--ff-system));
    font-size: var(--fs-meta, 13px);
    font-weight: 460;
    letter-spacing: 0.01em;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    line-height: var(--lh-tight, 1.25);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    /* No fixed max-width: flex:1 on .lane__id + this ellipsis govern the room,
       so the name shows as much of the slug as the lane allows. */
  }
  .lane--selected .lane__name { font-weight: 620; }
  .lane--actions .lane__name { font-weight: 600; }

  /* A selected lane sits on the lighter --calm-surface-hover ground (#131c2a),
     on which the chrome ink (#8a8068) drops to 4.37 -- under WCAG AA for this
     11px meta text. Lift the meta ink to --calm-ink on selected lanes only
     (7.9:1). The unselected lanes keep the quieter chrome (5.1:1, passes).
     axe color-contrast. */
  .lane--selected .lane__meta { color: var(--calm-ink, var(--text, #b8b098)); }

  /* One line, ellipsized -- never wraps (wrapping was what made lanes grow tall
     and collide with the signal pill). */
  .lane__meta {
    display: block;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    font-variant-numeric: tabular-nums;
  }
  .lane__sep { opacity: 0.5; }

  /* Compact glance signal pill -- the frozen M4 amber (AA-documented), shown
     ONLY on lanes that need attention. flex:0 so it never squeezes the name. */
  .lane__flag {
    flex: 0 0 auto;
    align-self: center;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    letter-spacing: 0.02em;
    line-height: 1.4;
    padding: 1px 7px;
    border-radius: 999px;
    white-space: nowrap;
    color: var(--badge-ar-fg, #d97706);
    background: var(--badge-ar-bg, #fef3c7);
    border: 1px solid var(--badge-ar-border, #d97706);
  }
  /* Escalation reuses the amber pill; the lone permitted motion is the lane
     edge pulse (.is-escalating on .lane), so the pill itself stays still. */
  .lane__flag--esc { font-weight: 800; }

  /* Expand control (S1 cwd reveal). Quiet chrome glyph; full a11y name. Slimmer
     and border-less so it stops eating ~13% of every lane's width. */
  .lane__expand {
    grid-column: 2;
    grid-row: 1;
    align-self: stretch;
    appearance: none;
    background: transparent;
    border: none;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    width: 1.45rem;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: color var(--t-calm, 180ms ease), background var(--t-calm, 180ms ease);
  }
  .lane__expand:hover {
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    background: var(--calm-surface-hover, var(--bg-row-hover, #131c2a));
  }
  .lane__chev {
    display: inline-block;
    font-size: 1rem;
    line-height: 1;
    transition: transform var(--t-calm, 180ms ease);
  }
  .lane__chev--open { transform: rotate(90deg); }

  /* S1 detail panel: cwd + ids, monospace, calm. */
  .lane__detail {
    grid-column: 1 / -1;
    grid-row: 2;
    padding: var(--space-3, 6px) var(--space-4, 10px) var(--space-4, 10px);
    border-top: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
    border-radius: 0 0 var(--radius-soft, 4px) var(--radius-soft, 4px);
  }
  .lane__dl { margin: 0; }
  .lane__row {
    display: grid;
    grid-template-columns: 4.5rem 1fr;
    gap: var(--space-4, 10px);
    padding: 2px 0;
  }
  .lane__row dt {
    margin: 0;
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .lane__row dd { margin: 0; min-width: 0; }
  .lane__mono {
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    color: var(--calm-ink, var(--text, #b8b098));
    word-break: break-all;
  }
  .lane__cwd { line-height: var(--lh-body, 1.5); }
  .lane__unknown {
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    font-style: italic;
  }
  .lane__s1 {
    margin: var(--space-3, 6px) 0 0;
    font-size: var(--fs-chrome, 11px);
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    letter-spacing: 0.01em;
  }

  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .lane,
    :global(html:not([data-motion='allow'])) .lane__main,
    :global(html:not([data-motion='allow'])) .lane__expand,
    :global(html:not([data-motion='allow'])) .lane__chev { transition: none; }
  }

  /* PAPER (light) theme color-contrast (WCAG AA): on an ended lane the
     .lane--ended { opacity: 0.62 } recede dims the id text below AA on the
     paper --bg-card (#f8f4ee) cream surface (was 3.26:1). Opacity caps the
     achievable contrast, so a color override alone cannot reach AA -- raise the
     paper ended-lane opacity (recede preserved, just lighter) AND darken the id
     ink so the blended result clears 4.5:1. Paper + ended modifier ONLY; the
     dark obsidian/phosphor themes pass and stay untouched. */
  :global([data-theme='paper']) .lane--ended { opacity: 0.9; }
  :global([data-theme='paper']) .lane--ended .lane__id { color: #3a2c1e; }
</style>
