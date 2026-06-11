<!--
  HeaderBar.svelte -- the calm masthead (GRAFT: ops-command-deck header).

  Composes the always-present operator chrome:
    - WORDMARK: a bespoke, domain-agnostic StreamManager mark (M16 -- it names
      the product, never a governed target). Variable-weight display type.
    - SessionPicker: the scope control that filters every pane by session_id
      (writes selectedSessionId; localStorage-persisted, default most-recent).
    - CWD READOUT: the selected session's working directory surfaced
      prominently (S1) so the operator can eyeball non-SM / non-firewalled
      before attaching. The UI surfaces; it does NOT auto-reject (S1 is MAY).
    - ThroughputLine: the ambient "is-it-alive" sparkline (decision-rate ONLY,
      never an urgency signal -- calm-tech liveness).
    - THEME SWITCH: obsidian / phosphor / paper, via <html data-theme>. Paired
      label+control, full keyboard a11y, persisted to localStorage.

  CALM-AMBIENT (spine): the header is still water -- a hairline base rule, dim
  chrome ink, no glow. The only motion is the throughput heartbeat. Escalation
  is NEVER rendered here; the header stays calm so the lone M2 escalation in the
  frames/rail truly stands alone (M2/M4 discipline).

  M16: no monitored-project vocabulary. The cwd + session name render from
  /api/sessions data via the selected-session store.

  M18: presentation + a store read (selectedSession) + a /api/stats `total`
  prop fed by the shell. No fetch of its own. Off the verdict hot path.

  File-disjoint: theme tokens + SessionPicker + ThroughputLine + the shared
  selectedSession store only.
-->
<script>
  import { onMount } from 'svelte';
  import SessionPicker from './SessionPicker.svelte';
  import ThroughputLine from './ThroughputLine.svelte';
  import { selectedSession } from '../stores/session.js';

  /**
   * total: latest GET /api/stats `total_decisions` aggregate, fed by the shell's
   * 5s stats poller, handed to the ThroughputLine to derive the calm rate.
   * @type {number|null|undefined}
   */
  export let total = undefined;

  /** product wordmark text. Domain-agnostic product identity (M16). */
  export let wordmark = 'StreamManager';

  // ---- theme switch (obsidian / phosphor / paper) ------------------------
  // The three themes are driven by <html data-theme>. The token VALUES are the
  // frozen theme.css contract; this control only flips the attribute + persists.
  const THEMES = Object.freeze([
    { id: 'obsidian', label: 'Obsidian' },
    { id: 'phosphor', label: 'Phosphor' },
    { id: 'paper', label: 'Paper' },
  ]);
  const LS_THEME = 'sm.next.theme';
  const VALID = new Set(THEMES.map((t) => t.id));

  let theme = 'obsidian';

  function applyTheme(next) {
    const t = VALID.has(next) ? next : 'obsidian';
    theme = t;
    if (typeof document !== 'undefined' && document.documentElement) {
      document.documentElement.setAttribute('data-theme', t);
    }
    try {
      if (typeof localStorage !== 'undefined') localStorage.setItem(LS_THEME, t);
    } catch (_e) {
      /* private mode / quota -- theme just won't persist, non-fatal */
    }
  }

  onMount(() => {
    // Resolve initial theme: persisted -> existing DOM attr -> default.
    let initial = 'obsidian';
    try {
      const saved = typeof localStorage !== 'undefined' ? localStorage.getItem(LS_THEME) : null;
      if (saved && VALID.has(saved)) initial = saved;
      else {
        const attr =
          typeof document !== 'undefined'
            ? document.documentElement.getAttribute('data-theme')
            : null;
        if (attr && VALID.has(attr)) initial = attr;
      }
    } catch (_e) {
      /* ignore -- fall back to default */
    }
    applyTheme(initial);
  });

  function onThemeChange(e) {
    applyTheme(e.currentTarget.value);
  }

  // ---- selected-session cwd readout (S1) ---------------------------------
  // Render the active scope's cwd prominently for the operator's manual non-SM
  // / non-firewalled check. Identity + cwd come from /api/sessions data (M16).
  $: sel = $selectedSession; // null => ALL governed sessions (no single cwd)
  $: cwd =
    sel && typeof sel.cwd === 'string' && sel.cwd.trim() ? sel.cwd.trim() : '';
  $: sessionName = (() => {
    if (!sel) return '';
    const slug =
      typeof sel.project_slug === 'string' && sel.project_slug.trim()
        ? sel.project_slug.trim()
        : '';
    return slug || (sel.id != null ? String(sel.id) : '');
  })();
</script>

<header class="hb" role="banner">
  <!-- WORDMARK: product identity (M16 -- product, not a governed target). -->
  <a class="hb__brand" href="/" aria-label={`${wordmark} -- operator console`}>
    <span class="hb__mark" aria-hidden="true"></span>
    <span class="hb__word">
      <span class="hb__word-strong">Stream</span><span class="hb__word-soft">Manager</span>
    </span>
  </a>

  <!-- SCOPE: the session picker filters every pane. -->
  <div class="hb__scope">
    <SessionPicker />
  </div>

  <!-- S1 CWD READOUT: the active scope's working directory, surfaced for the
       operator's manual verification. Calm chrome -- never an alarm. -->
  <div class="hb__cwd" aria-live="polite">
    {#if sel}
      <span class="hb__cwd-tag">CWD</span>
      {#if cwd}
        <span class="hb__cwd-path" title={`${sessionName} working directory: ${cwd}`}>{cwd}</span>
      {:else}
        <span class="hb__cwd-none" title="No cwd reported for this session -- verify manually before attaching">
          not reported
        </span>
      {/if}
    {:else}
      <span class="hb__cwd-tag">SCOPE</span>
      <span class="hb__cwd-none" title="All governed sessions in view">all governed sessions</span>
    {/if}
  </div>

  <!-- AMBIENT LIVENESS: the throughput heartbeat. Decision-rate ONLY; never an
       urgency signal (calm-tech). -->
  <div class="hb__pulse" aria-hidden="false">
    <ThroughputLine {total} />
  </div>

  <!-- THEME SWITCH: obsidian / phosphor / paper, paired label+control. -->
  <div class="hb__theme">
    <label class="hb__theme-label" for="sm-theme-switch">Theme</label>
    <div class="hb__theme-field">
      <select
        id="sm-theme-switch"
        class="hb__theme-select"
        value={theme}
        on:change={onThemeChange}
        aria-label="Color theme"
      >
        {#each THEMES as t (t.id)}
          <option value={t.id}>{t.label}</option>
        {/each}
      </select>
      <span class="hb__theme-chev" aria-hidden="true">&#9662;</span>
    </div>
  </div>
</header>

<style>
  /* Still-water masthead: a hairline base rule, dim chrome, no glow. The grid
     is intentionally asymmetric -- brand anchors left, the ambient pulse + theme
     sit right, the scope + cwd flow in the elastic middle. */
  .hb {
    display: grid;
    grid-template-columns: auto auto 1fr auto auto;
    align-items: center;
    gap: var(--space-5, 14px);
    padding: var(--space-3, 6px) var(--space-6, 22px);
    background: var(--calm-surface, var(--bg, #080a0c));
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    min-height: 3rem;
  }

  /* WORDMARK -- bespoke, two-weight split (Stream | Manager) for a non-template
     silhouette. The square mark glyph is the only accent ink in the resting
     header, kept small so it whispers. */
  .hb__brand {
    display: inline-flex;
    align-items: center;
    gap: var(--space-3, 6px);
    text-decoration: none;
    min-width: 0;
  }
  .hb__mark {
    width: var(--logo-size, 18px);
    height: var(--logo-size, 18px);
    flex: 0 0 auto;
    /* a hollow square with an accent corner -- a small bespoke monitor glyph */
    border: 2px solid var(--calm-accent, var(--accent, #f59e0b));
    border-radius: var(--radius-sharp, 2px);
    position: relative;
    opacity: 0.92;
  }
  .hb__mark::after {
    content: '';
    position: absolute;
    right: -2px;
    bottom: -2px;
    width: 40%;
    height: 40%;
    background: var(--calm-accent, var(--accent, #f59e0b));
    border-radius: 1px;
  }
  .hb__word {
    font-family: var(--font-h, var(--ff-system));
    font-size: var(--logo-size, 17px);
    line-height: 1;
    letter-spacing: var(--logo-ls, 0.06em);
    white-space: nowrap;
  }
  .hb__word-strong {
    font-weight: 680;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
  }
  .hb__word-soft {
    font-weight: 320;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }

  .hb__scope { grid-column: 2; min-width: 0; display: flex; align-items: center; }

  /* CWD readout: occupies the elastic middle, truncates gracefully. */
  .hb__cwd {
    grid-column: 3;
    min-width: 0;
    display: inline-flex;
    align-items: baseline;
    gap: var(--space-3, 6px);
    overflow: hidden;
  }
  .hb__cwd-tag {
    flex: 0 0 auto;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .hb__cwd-path {
    min-width: 0;
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-meta, 13px);
    color: var(--calm-ink, var(--text, #b8b098));
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    direction: rtl;        /* keep the tail (the actual dir) visible when clipped */
    text-align: left;
  }
  .hb__cwd-none {
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-meta, 13px);
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    font-style: italic;
    white-space: nowrap;
  }

  .hb__pulse {
    grid-column: 4;
    width: 132px;
    height: 22px;
    flex: 0 0 auto;
    align-self: center;
  }

  /* THEME SWITCH: paired label + native select, still-water chrome. */
  .hb__theme {
    grid-column: 5;
    display: inline-flex;
    align-items: center;
    gap: var(--space-3, 6px);
  }
  .hb__theme-label {
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    white-space: nowrap;
  }
  .hb__theme-field { position: relative; display: inline-flex; align-items: center; }
  .hb__theme-select {
    appearance: none;
    -webkit-appearance: none;
    -moz-appearance: none;
    background: var(--calm-surface-raised, var(--bg-card, #0c1118));
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-soft, 4px);
    font-family: var(--font-h, var(--ff-system));
    font-size: var(--fs-meta, 13px);
    padding: 4px 1.5rem 4px 8px;
    cursor: pointer;
    transition: border-color var(--t-calm, 180ms ease);
  }
  .hb__theme-select:hover {
    border-color: var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25)));
  }
  .hb__theme-select option {
    background: var(--calm-surface-raised, var(--bg-card, #0c1118));
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
  }
  .hb__theme-chev {
    position: absolute;
    right: 7px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 0.65rem;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    pointer-events: none;
  }

  /* M17: 2px solid amber focus ring + 2px offset on every interactive element. */
  .hb__brand:focus-visible,
  .hb__theme-select:focus-visible {
    outline: 2px solid var(--badge-ar-border, #d97706);
    outline-offset: 2px;
    border-radius: var(--radius-soft, 4px);
  }

  /* Narrow viewports: the cwd readout is the first thing to yield (it is a
     convenience, not a contract surface), then the ambient pulse. The brand,
     scope picker, and theme switch always survive. */
  @media (max-width: 860px) {
    .hb { grid-template-columns: auto 1fr auto auto; gap: var(--space-4, 10px); }
    .hb__cwd { display: none; }
    .hb__scope { grid-column: 2; }
    .hb__pulse { grid-column: 3; }
    .hb__theme { grid-column: 4; }
  }
  @media (max-width: 560px) {
    .hb { grid-template-columns: auto 1fr auto; }
    .hb__pulse { display: none; }
    .hb__scope { grid-column: 2; }
    .hb__theme { grid-column: 3; }
  }

  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .hb__theme-select { transition: none; }
  }
</style>
