<!--
  SessionPicker.svelte -- the header session SCOPE control (writes the store
  that scopes every pane).

  CONTRACT: writes `selectedSessionId` (u-stores). That store is localStorage-
  persisted and defaults to the most-recently-active non-self session
  (defaultToMostRecent(), called once by the shell after the first
  setSessions()). Selecting a session here filters every pane by that
  session_id; selecting "All governed" clears the scope (null) -- a deliberate,
  reachable un-scoped state.

  M15 / G2 polarity: the picker's options are the `sessions` store, which is
  already self-excluded (the SM's own session can NEVER appear as an option),
  and the store setter refuses to resolve to the own id even if asked. The
  operator therefore cannot scope the dashboard TO the SM's own session.

  M16 domain-agnostic: option labels render from /api/sessions row data
  (project_slug / id) -- never a hard-coded monitored-project name.

  CALM-AMBIENT (spine): a quiet native <select> styled to the still-water
  chrome. Native control = full keyboard + screen-reader + mobile support for
  free, and zero custom-listbox a11y risk against the M17 axe gate. The picker
  does not animate, glow, or pulse -- scope selection is a calm, deliberate act.

  M18: presentation + store write only. No fetch (the shell owns the
  /api/sessions poll feeding the store). Off the verdict hot path.

  File-disjoint: theme tokens + the shared session store only.
-->
<script>
  import { sessions, selectedSessionId, selectSession } from '../stores/session.js';

  /** id used to wire the visually-hidden <label> to the <select> (a11y). */
  export let id = 'sm-session-picker';

  /** label text for the control. UI taxonomy only (M16). */
  export let label = 'Scope';

  // The native select binds to a string; we map ''/sentinel <-> null (ALL).
  const ALL = '__all__';

  // Render a stable, human option label from row DATA only (M16). Prefer the
  // project_slug; fall back to a shortened id so an option is always nameable
  // WITHOUT inventing a target name.
  function optionLabel(s) {
    const slug =
      s && typeof s.project_slug === 'string' && s.project_slug.trim()
        ? s.project_slug.trim()
        : '';
    const id = s && s.id != null ? String(s.id) : '';
    const name = slug || (id ? shortId(id) : 'unnamed');
    const ended = s && s.ended_at !== null && s.ended_at !== undefined;
    return ended ? `${name} (ended)` : name;
  }
  function shortId(v) {
    return v.length <= 14 ? v : `${v.slice(0, 8)}…${v.slice(-4)}`;
  }

  // The <select>'s current value mirrors the store (ALL sentinel when null).
  $: currentValue = $selectedSessionId === null ? ALL : $selectedSessionId;

  function onChange(e) {
    const v = e.currentTarget.value;
    selectSession(v === ALL ? null : v);
  }

  // Accessible status describing the active scope, for the control's title.
  $: scopeTitle = (() => {
    if ($selectedSessionId === null) {
      return `Scope: all governed sessions (${$sessions.length})`;
    }
    const sel = $sessions.find((s) => s.id === $selectedSessionId);
    return sel
      ? `Scope: ${optionLabel(sel)}`
      : 'Scope: a session no longer listed';
  })();
</script>

<div class="picker" title={scopeTitle}>
  <label class="picker__label" for={id}>{label}</label>

  <div class="picker__field">
    <select
      {id}
      class="picker__select"
      value={currentValue}
      on:change={onChange}
      aria-label={`${label} -- filter all panes by session`}
    >
      <!-- ALL: the deliberate un-scoped state. Domain-agnostic wording. -->
      <option value={ALL}>All governed sessions</option>

      {#if $sessions.length}
        <optgroup label="Sessions">
          {#each $sessions as s (s.id)}
            <option value={s.id}>{optionLabel(s)}</option>
          {/each}
        </optgroup>
      {/if}
    </select>

    <!-- decorative chevron; the native control still drives interaction -->
    <span class="picker__chev" aria-hidden="true">&#9662;</span>
  </div>
</div>

<style>
  .picker {
    display: inline-flex;
    align-items: center;
    gap: var(--space-3, 6px);
    min-width: 0;
  }

  /* Label: quiet chrome caption, paired with the control (never a bare icon). */
  .picker__label {
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    white-space: nowrap;
  }

  .picker__field {
    position: relative;
    display: inline-flex;
    align-items: center;
    min-width: 0;
  }

  /* The native <select>, styled to the still-water chrome. Native = a11y +
     keyboard + mobile for free; no custom-listbox risk against the axe gate. */
  .picker__select {
    appearance: none;
    -webkit-appearance: none;
    -moz-appearance: none;
    max-width: 24ch;
    min-width: 9rem;
    background: var(--calm-surface-raised, var(--bg-card, #0c1118));
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-soft, 4px);
    font-family: var(--font-h, var(--ff-system));
    font-size: var(--fs-meta, 13px);
    font-weight: 480;
    letter-spacing: 0.01em;
    line-height: 1.2;
    padding: 5px 1.7rem 5px 9px; /* room for the chevron */
    cursor: pointer;
    text-overflow: ellipsis;
    transition: border-color var(--t-calm, 180ms ease),
                background var(--t-calm, 180ms ease);
  }
  .picker__select:hover {
    border-color: var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25)));
  }

  /* M17: 2px solid amber focus ring + 2px offset on the interactive control. */
  .picker__select:focus-visible {
    outline: 2px solid var(--badge-ar-border, #d97706);
    outline-offset: 2px;
    border-color: var(--calm-accent, var(--accent, #f59e0b));
  }

  /* The option list renders with the browser's native popup; we still hint the
     surface colors so dark themes do not flash a white menu where supported. */
  .picker__select option,
  .picker__select optgroup {
    background: var(--calm-surface-raised, var(--bg-card, #0c1118));
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
  }

  .picker__chev {
    position: absolute;
    right: 8px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 0.7rem;
    line-height: 1;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    pointer-events: none; /* clicks pass through to the native select */
  }

  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .picker__select { transition: none; }
  }
</style>
