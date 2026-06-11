<!--
  BetaToggles.svelte -- the "BETA features" section of the operator Settings
  drawer (2026-06-11 BETA proposals initiative). This is the surface where the
  operator turns optional features ON/OFF "at the UI level".

  CONTRACT
    - Reads the data-only registry (lib/beta/registry.js) + the betaFlags store
      (lib/stores/beta.js). Imports NO feature component, so it renders before
      any feature lands and never breaks the build.
    - Every feature is DEFAULT OFF. Toggling writes through the store
      (optimistic + POST /api/beta/flags/{key}, rollback on failure).
    - Hydrates the server overrides once on mount.

  M4 (paired label+color, never color alone): each toggle renders the literal
  ON/OFF text beside the painted track; color only reinforces the text.
  M16 (domain-agnostic): every label is generic governance/UI taxonomy.
  M17 (a11y): real native <input type=checkbox> so the global focus ring +
  keyboard behaviour apply; each carries an explicit aria-label; the group is a
  labelled region. Reduced motion honoured via the same data-motion attribute.
  ASCII-only (cp1252-safe): dash rendered as "--".
-->
<script>
  import { onMount } from 'svelte';
  import { BETA_REGISTRY, BETA_GROUPS } from '../beta/registry.js';
  import { betaFlags, setBetaFlag, hydrateBetaFlags } from '../stores/beta.js';

  // group key -> features, preserving registry order within each group.
  const byGroup = BETA_GROUPS.map((g) => ({
    ...g,
    features: BETA_REGISTRY.filter((f) => f.group === g.id),
  }));

  onMount(() => {
    // Best-effort server hydrate; failure leaves the persisted/default map.
    hydrateBetaFlags();
  });

  $: onCount = BETA_REGISTRY.reduce((n, f) => n + (($betaFlags && $betaFlags[f.key]) ? 1 : 0), 0);

  /** @param {string} key @param {Event} e */
  function onToggle(key, e) {
    const checked = /** @type {HTMLInputElement} */ (e.currentTarget).checked;
    setBetaFlag(key, checked);
  }
</script>

<section class="bt" aria-labelledby="bt-title">
  <div class="bt__head">
    <span id="bt-title" class="bt__title">BETA features</span>
    <span class="bt__count" aria-label={`${onCount} of ${BETA_REGISTRY.length} BETA features on`}>
      {onCount} of {BETA_REGISTRY.length} ON
    </span>
  </div>
  <p class="bt__lede">
    Optional. Off by default. Toggling one ON mounts its pane live; OFF removes
    it with no runtime cost. Safety governance is never affected by a BETA flag.
  </p>

  {#each byGroup as g (g.id)}
    {#if g.features.length}
      <div class="bt__group">
        <p class="bt__group-label">{g.label}</p>
        {#each g.features as f (f.key)}
          {@const on = !!($betaFlags && $betaFlags[f.key])}
          <div class="bt__feat">
            <div class="bt__feat-main">
              <div class="bt__feat-name">
                {f.label}<span class="bt__num">#{f.num}</span>
              </div>
              <p class="bt__feat-desc">{f.description}</p>
              {#if f.needsAmendment}
                <span class="bt__gate">build gated on ADR-18 amendment</span>
              {/if}
            </div>
            <label class="bt__switch">
              <input
                type="checkbox"
                checked={on}
                aria-label={`${f.label} (currently ${on ? 'ON' : 'OFF'})`}
                on:change={(e) => onToggle(f.key, e)}
              />
              <span class="bt__track" aria-hidden="true"><span class="bt__knob"></span></span>
              <span class="bt__state" data-on={on}>{on ? 'ON' : 'OFF'}</span>
            </label>
          </div>
        {/each}
      </div>
    {/if}
  {/each}
</section>

<style>
  .bt { display: flex; flex-direction: column; gap: var(--space-3, 6px); }
  .bt__head {
    display: flex; align-items: baseline; justify-content: space-between; gap: var(--space-4, 10px);
  }
  .bt__title {
    font-size: var(--fs-meta, 13px); font-weight: 600; letter-spacing: 0.02em;
    color: var(--calm-ink-loud, var(--text-bright));
  }
  .bt__count {
    font-family: var(--font-d, var(--ff-mono)); font-size: var(--fs-meta, 13px);
    font-variant-numeric: tabular-nums; color: var(--calm-accent, var(--accent));
  }
  .bt__lede {
    margin: 0; font-size: var(--fs-chrome, 11px); line-height: var(--lh-body, 1.5);
    color: var(--calm-ink-quiet, var(--text-dim)); max-width: 46ch;
  }

  .bt__group { margin-top: var(--space-4, 10px); display: flex; flex-direction: column; }
  .bt__group-label {
    margin: 0 0 var(--space-2, 4px); font-size: var(--fs-chrome, 11px);
    letter-spacing: 0.12em; text-transform: uppercase; font-weight: 700;
    color: var(--calm-ink-chrome, var(--text-ui));
  }

  .bt__feat {
    display: flex; align-items: flex-start; justify-content: space-between;
    gap: var(--space-4, 10px); padding: var(--space-3, 6px) 0;
    border-top: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
  }
  .bt__feat:first-of-type { border-top: none; }
  .bt__feat-main { min-width: 0; }
  .bt__feat-name {
    font-size: var(--fs-meta, 13px); font-weight: 600;
    color: var(--calm-ink-loud, var(--text-bright));
  }
  .bt__num {
    font-family: var(--font-d, var(--ff-mono)); font-size: var(--fs-chrome, 11px);
    color: var(--calm-ink-quiet, var(--text-dim)); margin-left: 7px;
  }
  .bt__feat-desc {
    margin: 2px 0 0; font-size: var(--fs-chrome, 11px); line-height: var(--lh-body, 1.5);
    color: var(--calm-ink-quiet, var(--text-dim)); max-width: 50ch;
  }
  .bt__gate {
    display: inline-block; margin-top: 5px; font-size: 10px; letter-spacing: 0.05em;
    text-transform: uppercase; color: var(--badge-ar-fg); background: var(--badge-ar-bg);
    border: var(--hairline, 1px) solid var(--badge-ar-border); border-radius: 3px;
    padding: 1px 6px;
  }

  /* switch -- the SettingsDrawer .sd-switch idiom: real checkbox, painted track,
     paired ON/OFF text (M4). The text is the signal; color reinforces. */
  .bt__switch {
    display: inline-flex; align-items: center; gap: var(--space-3, 6px);
    cursor: pointer; flex: 0 0 auto;
  }
  .bt__switch input {
    position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; border: 0;
    clip: rect(0 0 0 0); overflow: hidden;
  }
  .bt__track {
    position: relative; width: 38px; height: 20px; border-radius: 999px;
    background: var(--calm-surface-row, var(--bg-row));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    transition: background var(--t-calm, 0.18s), border-color var(--t-calm, 0.18s);
    flex: 0 0 auto;
  }
  .bt__knob {
    position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; border-radius: 50%;
    background: var(--calm-ink-chrome, var(--text-ui));
    transition: transform var(--t-calm, 0.18s), background var(--t-calm, 0.18s);
  }
  .bt__switch input:checked + .bt__track {
    background: var(--calm-accent-wash, var(--accent-dim));
    border-color: var(--calm-hairline-hi, var(--border-hi));
  }
  .bt__switch input:checked + .bt__track .bt__knob {
    transform: translateX(18px); background: var(--calm-accent, var(--accent));
  }
  .bt__switch input:focus-visible + .bt__track {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid)
      var(--focus-ring-color, #d97706);
    outline-offset: var(--focus-ring-offset, 2px);
  }
  .bt__state {
    min-width: 3ch; font-family: var(--font-d, var(--ff-mono)); font-size: var(--fs-meta, 13px);
    letter-spacing: 0.06em; font-weight: 600; color: var(--calm-ink-quiet, var(--text-dim));
  }
  .bt__state[data-on='true'] { color: var(--calm-accent, var(--accent)); }

  :global(html[data-motion='reduce']) .bt__knob { transition: none; }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .bt__knob { transition: none; }
  }
</style>
