<script>
  // ThemeToggle.svelte -- the LIVE dark/light + theme control for the masthead.
  //
  // The theme switch logic used to live in the unmounted HeaderBar; it is now
  // owned by stores/theme.js (which applies <html data-theme> at module load and
  // resolves persisted -> OS prefers-color-scheme -> obsidian). This component is
  // the small, always-present chrome control that lets the operator switch:
  //   - a quick dark/light toggle (obsidian <-> paper), and
  //   - the full theme menu (Obsidian / Phosphor / Paper).
  //
  // M4 discipline: the control is text-labelled (paired label + control), color is
  // never the sole signal. M17: 2px amber focus ring on every interactive element.
  // M16: domain-agnostic chrome -- names a theme, never a governed target.
  import { theme, THEMES, setTheme, toggleDarkLight } from '../stores/theme.js';

  $: current = $theme;
  $: isLight = current === 'paper';

  function onSelect(e) {
    setTheme(e.currentTarget.value);
  }
</script>

<div class="tt" role="group" aria-label="Color theme">
  <!-- Quick dark/light toggle: the primary affordance the operator asked for. -->
  <button
    type="button"
    class="tt__toggle"
    on:click={toggleDarkLight}
    aria-pressed={isLight}
    title={isLight ? 'Switch to dark theme' : 'Switch to light theme'}
    aria-label={isLight ? 'Switch to dark theme' : 'Switch to light theme'}
  >
    <span class="tt__toggle-ico" aria-hidden="true">{isLight ? 'L' : 'D'}</span>
    <span class="tt__toggle-text">{isLight ? 'Light' : 'Dark'}</span>
  </button>

  <!-- Full theme menu: exposes all three (Obsidian dark / Phosphor dark / Paper light). -->
  <label class="tt__label" for="sm-theme-select">Theme</label>
  <div class="tt__field">
    <select
      id="sm-theme-select"
      class="tt__select"
      value={current}
      on:change={onSelect}
      aria-label="Color theme"
    >
      {#each THEMES as t (t.id)}
        <option value={t.id}>{t.label}</option>
      {/each}
    </select>
    <span class="tt__chev" aria-hidden="true">&#9662;</span>
  </div>
</div>

<style>
  .tt {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    flex: 0 0 auto;
  }

  .tt__toggle {
    appearance: none;
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    border: 1px solid var(--sm-border, rgba(148, 163, 184, 0.25));
    background: transparent;
    color: var(--sm-text-dim, #94a3b8);
    font-size: 0.72rem;
    letter-spacing: 0.03em;
    padding: 0.32rem 0.6rem;
    border-radius: 6px;
    cursor: pointer;
    transition: color 0.18s ease, border-color 0.18s ease;
  }
  .tt__toggle:hover {
    color: var(--sm-text, #e2e8f0);
    border-color: var(--sm-text-dim, #94a3b8);
  }
  .tt__toggle-ico {
    font-family: var(--sm-font-mono, ui-monospace, monospace);
    font-weight: 700;
    font-size: 0.7rem;
    width: 0.9rem;
    text-align: center;
    color: var(--sm-accent, #38bdf8);
  }

  .tt__label {
    font-family: var(--sm-font-mono, ui-monospace, monospace);
    font-size: 0.62rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--sm-text-dim, #94a3b8);
    white-space: nowrap;
  }

  .tt__field { position: relative; display: inline-flex; align-items: center; }
  .tt__select {
    appearance: none;
    -webkit-appearance: none;
    -moz-appearance: none;
    background: var(--sm-bg-card, #0c1118);
    color: var(--sm-text, #e2e8f0);
    border: 1px solid var(--sm-border, rgba(148, 163, 184, 0.25));
    border-radius: 6px;
    font-size: 0.74rem;
    padding: 0.3rem 1.4rem 0.3rem 0.5rem;
    cursor: pointer;
    transition: border-color 0.18s ease;
  }
  .tt__select:hover { border-color: var(--sm-text-dim, #94a3b8); }
  .tt__chev {
    position: absolute;
    right: 0.45rem;
    top: 50%;
    transform: translateY(-50%);
    font-size: 0.6rem;
    color: var(--sm-text-dim, #94a3b8);
    pointer-events: none;
  }

  /* M17: amber 2px focus ring + 2px offset on every interactive element. */
  .tt__toggle:focus-visible,
  .tt__select:focus-visible {
    outline: 2px solid var(--sm-focus, #d97706);
    outline-offset: 2px;
    border-radius: 6px;
  }

  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .tt__toggle,
    :global(html:not([data-motion='allow'])) .tt__select { transition: none; }
  }

  /* Narrow viewports: keep the quick dark/light toggle, drop the verbose menu
     label to save space (the select itself still carries an aria-label). */
  @media (max-width: 55rem) {
    .tt__label { display: none; }
  }
</style>
