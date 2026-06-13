<!--
  QuickFilters.svelte -- BETA feature #22 "quick-filters" (FR-UI-9 quick-filter
  presets). The Svelte form of the operator-APPROVED KingMode mockup
  (reports/proposals/mockups/quick-filters.html): a hairline rail of monospace
  mode-cards (PARANOID / STANDARD / TRUST / AUDIT + operator custom presets)
  rendered ABOVE the four FR-UI-9 knobs in the Settings drawer. One named click
  -- or a hotkey (Alt+1..4) -- patches all four settings at once; hand-tuning any
  knob flips the active mode to "custom".

  WHAT IT DRIVES (cause sits above effect)
    Clicking a card cascades DOWN into the SHARED settings store via patch()
    (lib/stores/settings.js). patch() coerces + persists localStorage + emits the
    FR-UI-9 `dashboard_settings_changed` event, so the existing four
    SettingsDrawer knobs re-render and the existing best-effort POST
    /api/hitl/settings fires -- EXACTLY as if the operator had moved each slider
    by hand. This component owns NO settings state of its own; it reads + patches
    the one shared store. The four preset fields are the four SmSettings keys
    settings.js owns (confidenceFloor / hitlMode / syncTimeoutSec / pauseDetection).

  NO NEW gov.db TABLE / NO ADR-18 AMENDMENT / CLIENT-SIDE ONLY
    Built-in presets are constants. Custom presets persist CLIENT-SIDE ONLY in
    localStorage (key sm.next.presets), mirroring the settings/beta store idiom.
    No backend endpoint, no new column, no new bus envelope, no FROZEN edit.

  GATING (BETA, default OFF). The component renders NOTHING and registers NO
  pollers / SSE handlers / timers / hotkey listeners unless
  $betaFlags["quick-filters"] is true. Flipping the flag OFF closes the modal and
  detaches the global Alt+digit listener -- zero runtime cost while OFF.

  ADR-18 MUST floor honoured:
    - M1 3-frame presence: this adds a section INSIDE the Settings drawer (Frame
      B chrome) + an optional ambient masthead pill. It NEVER adds/removes a frame.
    - M2 escalation-only foreground: presets are ambient settings chrome. The
      header pill is calm (never amber/urgent); it surfaces the active mode NAME,
      not an escalation.
    - M4 paired label+color, never color alone: every card renders its NAME and
      the literal micro-spec ("95% . SYNC . 120s . pause ON") as TEXT; the accent
      fill is a SECOND channel on the active card only. The pill renders
      "MODE: PARANOID" (label + value text). The active state reads with all
      color stripped.
    - M5 HITL gate: presets only SET the SYNC/ASYNC value (never a third state,
      coerced); they do not bypass the HITL gate. patch() routes mode through the
      same store path the HitlModeToggle uses.
    - M15/G2 polarity: this feature issues NO session query of its own; it never
      surfaces or sweeps any session, SM-self or otherwise. The server sync that
      patch() triggers (POST /api/hitl/settings) is scoped to the operator-
      selected NON-SELF session by the SettingsDrawer / settings store, unchanged.
    - M16 domain-agnostic: the four-tuple is generic operator-settings taxonomy;
      preset_name is operator-supplied free text. No monitored-project vocabulary.
    - M17 a11y AAA: radiogroup cards (Arrow + Space/Enter), real <button>s so the
      global 2px amber focus ring applies, a polite live region for apply/save/
      delete, a focus-trapped role=dialog save modal with Escape + focus restore,
      and AAA-contrast theme tokens. ASCII-only (cp1252-safe): dash is "--".

  When localStorage holds no custom presets the rail seeds ONE realistic mock
  custom preset (usedMockData) so the divider + the "x" delete affordance are
  always testable.
-->
<script>
  import { onMount, onDestroy, tick } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { settings, patch as patchSettings } from '../../stores/settings.js';
  import {
    BUILTINS,
    loadCustom,
    saveCustom,
    mockCustom,
    coerceConfig,
    eqConfig,
    activePresetName,
    specLine,
    configFromSettings,
  } from './QuickFilters-presets.js';

  const FLAG_KEY = 'quick-filters';

  /**
   * showPill: render the optional ambient masthead pill ("MODE: <name>"). The
   * Settings drawer mounts this WITHOUT the pill (carousel only); a host that
   * wants the glance pill can pass showPill. Default false so the drawer mount is
   * carousel-only and adds no chrome elsewhere.
   */
  export let showPill = false;

  /** usedMockData: surfaced for the test harness (true when the seed fired). */
  export let usedMockData = false;

  // -- gate (default OFF) -----------------------------------------------------
  // Reactive flag read. Everything below is a no-op while OFF: nothing renders,
  // the Alt+digit listener is detached, the modal is closed.
  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // -- custom presets (client-side localStorage; loaded on mount) -------------
  /** @type {import('./QuickFilters-presets.js').Preset[]} */
  let customPresets = [];

  // -- the active four-tuple, read live from the SHARED settings store --------
  /** @type {import('./QuickFilters-presets.js').PresetConfig} */
  let current = configFromSettings($settings);
  $: current = configFromSettings($settings);

  // -- derived: which preset (if any) the live config equals ------------------
  $: activeName = activePresetName(current, customPresets);

  // -- live region + helpers --------------------------------------------------
  let liveMsg = '';
  function announce(msg) {
    // clear then set so repeated identical messages still announce.
    liveMsg = '';
    setTimeout(() => { liveMsg = msg; }, 30);
  }

  // -- apply a preset by name: the KEY INTERACTION ----------------------------
  // One atomic patch() on the SHARED store -> coerces + persists + emits
  // dashboard_settings_changed; the existing four knobs re-render and the
  // existing server sync fires. We own no copy of the settings.
  /** @param {string} name */
  function applyPreset(name) {
    const all = BUILTINS.concat(customPresets);
    const p = all.find((x) => x.name === name);
    if (!p) return;
    const cfg = coerceConfig(p.config);
    patchSettings({
      confidenceFloor: cfg.confidenceFloor,
      hitlMode: cfg.hitlMode,
      syncTimeoutSec: cfg.syncTimeoutSec,
      pauseDetection: cfg.pauseDetection,
    });
    announce(
      'Preset ' + name + ' applied -- floor ' + Math.round(cfg.confidenceFloor * 100) +
      ' percent, ' + cfg.hitlMode.toUpperCase() + ', ' + cfg.syncTimeoutSec +
      ' second timeout, pause ' + (cfg.pauseDetection ? 'on' : 'off'),
    );
  }

  // -- carousel keyboard (radiogroup): Arrow roves, Space/Enter applies --------
  /** @type {HTMLElement|null} */
  let carouselEl = null;
  function onCarouselKeydown(e) {
    const card = e.target instanceof Element ? e.target.closest('.qf-card') : null;
    if (!card || !carouselEl) return;
    const cards = Array.prototype.slice.call(carouselEl.querySelectorAll('.qf-card'));
    const idx = cards.indexOf(card);
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      cards[(idx + 1) % cards.length].focus();
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      cards[(idx - 1 + cards.length) % cards.length].focus();
    } else if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      applyPreset(card.getAttribute('data-preset'));
    }
  }

  // -- delete a custom preset -------------------------------------------------
  /** @param {string} name */
  function deleteCustom(name) {
    customPresets = customPresets.filter((p) => p.name !== name);
    saveCustom(customPresets);
    usedMockData = false; // a deliberate edit supersedes the seed
    announce('Deleted preset ' + name);
  }

  // -- save-as-preset modal (focus-trapped dialog) ----------------------------
  let modalOpen = false;
  let modalName = '';
  /** @type {HTMLElement|null} */
  let modalEl = null;
  /** @type {HTMLInputElement|null} */
  let modalInputEl = null;
  /** @type {Element|null} */
  let lastFocused = null;

  async function openModal() {
    if (!enabled) return;
    lastFocused = typeof document !== 'undefined' ? document.activeElement : null;
    modalName = '';
    modalOpen = true;
    await tick();
    if (modalInputEl) modalInputEl.focus();
  }
  function closeModal() {
    if (!modalOpen) return;
    modalOpen = false;
    if (lastFocused && typeof (/** @type {any} */ (lastFocused).focus) === 'function') {
      /** @type {HTMLElement} */ (lastFocused).focus();
    }
  }
  function commitSave() {
    const name = (modalName || '').trim();
    if (!name) { if (modalInputEl) modalInputEl.focus(); return; }
    // de-dup: a same-named custom preset is replaced (built-ins are immutable;
    // a name colliding a built-in still saves as a custom override under the
    // same label, kept after the divider).
    const next = customPresets.filter((p) => p.name !== name);
    next.push({ name, config: { ...current }, createdAt: new Date().toISOString() });
    customPresets = next;
    saveCustom(customPresets);
    usedMockData = false;
    closeModal();
    announce('Saved preset ' + name + ' -- it now lives in the rail and is the active mode');
  }
  function onModalKeydown(e) {
    if (e.key === 'Escape') { e.preventDefault(); closeModal(); return; }
    if (e.key === 'Enter') { e.preventDefault(); commitSave(); return; }
    if (e.key === 'Tab' && modalEl) {
      const f = Array.prototype.slice
        .call(modalEl.querySelectorAll('button, input, [tabindex]:not([tabindex="-1"])'))
        .filter((el) => !el.disabled && el.offsetParent !== null);
      if (!f.length) return;
      const first = f[0];
      const last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  }

  // -- global hotkeys: Alt+1..4 apply the four built-ins (only while ON) -------
  function onGlobalKeydown(e) {
    if (!enabled) return;
    if (modalOpen) return; // the modal owns the keyboard while open
    if (!e.altKey || e.ctrlKey || e.metaKey) return;
    const map = { '1': 0, '2': 1, '3': 2, '4': 3 };
    const i = map[e.key];
    if (i === undefined) return;
    const p = BUILTINS[i];
    if (!p) return;
    e.preventDefault();
    applyPreset(p.name);
  }

  let _keyBound = false;
  function bindKey() {
    if (_keyBound || typeof window === 'undefined') return;
    window.addEventListener('keydown', onGlobalKeydown);
    _keyBound = true;
  }
  function unbindKey() {
    if (!_keyBound || typeof window === 'undefined') return;
    window.removeEventListener('keydown', onGlobalKeydown);
    _keyBound = false;
  }
  // Bind/unbind purely on the gate so an OFF flag leaves zero listeners.
  $: if (enabled) bindKey(); else { unbindKey(); if (modalOpen) closeModal(); }

  onMount(() => {
    const loaded = loadCustom();
    if (loaded.length) {
      customPresets = loaded;
      usedMockData = false;
    } else {
      customPresets = mockCustom();
      usedMockData = true;
    }
    if (enabled) bindKey();
  });
  onDestroy(() => unbindKey());

  // Stable tabindex: the active card (or the first card) is the single roving
  // tab stop so the radiogroup is keyboard-reachable.
  $: firstStopName = activeName || (BUILTINS[0] && BUILTINS[0].name);
</script>

<!-- GATE: render absolutely nothing while OFF. No section, no pill, no listener. -->
{#if enabled}
  <!-- optional ambient masthead pill (host opt-in). Calm chrome, never amber. -->
  {#if showPill}
    <span
      class="qf-pill"
      data-custom={activeName ? 'false' : 'true'}
      title="Active posture preset -- one glance tells you which mode is live"
    >
      <span class="qf-pill__dot" aria-hidden="true"></span>
      <span class="qf-pill__tag">MODE:</span>
      <span class="qf-pill__val">{activeName || 'custom'}</span>
    </span>
  {/if}

  <section class="qf" aria-labelledby="qf-label">
    <div class="qf__head">
      <span class="qf__label" id="qf-label">Quick-filter presets</span>
      <span class="qf__chip">BETA -- default OFF, toggled in Settings</span>
    </div>
    <p class="qf__desc">
      One named click -- or a hotkey (Alt+1..4) -- sets all four knobs below.
      Cause sits above effect: a preset cascades DOWN into confidence / HITL mode
      / timeout / pause. Every knob stays fully mutable; a preset is a shortcut,
      never a constraint. Hand-tune any knob and the active mode flips to "custom".
      {#if usedMockData}<span class="qf__mock"> -- DEMO custom preset</span>{/if}
    </p>

    <div
      class="qf-carousel"
      role="radiogroup"
      aria-label="Posture presets"
      bind:this={carouselEl}
      on:keydown={onCarouselKeydown}
    >
      {#each BUILTINS as p, i (p.name)}
        {@const active = eqConfig(p.config, current)}
        <button
          type="button"
          class="qf-card"
          class:is-active={active}
          role="radio"
          aria-checked={active}
          tabindex={p.name === firstStopName ? 0 : -1}
          data-preset={p.name}
          title={p.hint || (p.name + ' preset')}
          aria-label={p.name + ' preset (Alt+' + (i + 1) + ') -- ' + specLine(p.config)}
          on:click={() => applyPreset(p.name)}
        >
          <span class="qf-card__name">{p.name}</span>
          <span class="qf-card__spec">{specLine(p.config)}</span>
          <span class="qf-card__kbd" aria-hidden="true">Alt+{i + 1}</span>
        </button>
      {/each}

      {#if customPresets.length}
        <span class="qf-carousel__divider" aria-hidden="true"></span>
        <span class="qf-carousel__custom-label">Your presets</span>
        {#each customPresets as p (p.name)}
          {@const active = eqConfig(p.config, current)}
          <button
            type="button"
            class="qf-card qf-card--custom"
            class:is-active={active}
            role="radio"
            aria-checked={active}
            tabindex={p.name === firstStopName ? 0 : -1}
            data-preset={p.name}
            title={p.name + ' preset'}
            aria-label={'Custom preset ' + p.name + ' -- ' + specLine(p.config)}
            on:click={() => applyPreset(p.name)}
          >
            <span
              class="qf-del"
              role="button"
              tabindex="0"
              aria-label={'Delete preset ' + p.name}
              title="Delete preset"
              on:click|stopPropagation={() => deleteCustom(p.name)}
              on:keydown|stopPropagation={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); deleteCustom(p.name); } }}
            >x</span>
            <span class="qf-card__name">{p.name}</span>
            <span class="qf-card__spec">{specLine(p.config)}</span>
          </button>
        {/each}
      {/if}

      <button
        type="button"
        class="qf-save"
        aria-label="Save the current posture as a named preset"
        on:click={openModal}
      >
        <span class="qf-save__plus" aria-hidden="true">+</span> Save as preset
      </button>
    </div>
  </section>

  <!-- polite live region: apply / save / delete announcements (M17). -->
  <p class="qf-sr-only" role="status" aria-live="polite">{liveMsg}</p>

  {#if modalOpen}
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div class="qf-scrim" role="presentation" on:click={(e) => { if (e.target === e.currentTarget) closeModal(); }}>
      <div
        class="qf-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="qf-modal-title"
        bind:this={modalEl}
        on:keydown={onModalKeydown}
      >
        <h3 id="qf-modal-title" class="qf-modal__title">Save current posture as a preset</h3>
        <p class="qf-modal__lede">
          Names the four current knob values ({specLine(current)}) so you can
          recall this posture in one click.
        </p>
        <input
          class="qf-modal__input"
          type="text"
          maxlength="40"
          placeholder="e.g. my-strict-review"
          aria-label="Preset name"
          bind:value={modalName}
          bind:this={modalInputEl}
        />
        <div class="qf-modal__actions">
          <button type="button" class="qf-modal__btn qf-modal__btn--ghost" on:click={closeModal}>Cancel</button>
          <button type="button" class="qf-modal__btn qf-modal__btn--primary" on:click={commitSave}>Save preset</button>
        </div>
      </div>
    </div>
  {/if}
{/if}

<style>
  /* === ambient masthead pill (host opt-in) -- "MODE: PARANOID". Calm chrome,
     never amber (M2). Active = accent ink; "custom" = muted slate (OBSERVING). */
  .qf-pill {
    display: inline-flex; align-items: center; gap: 0.4rem;
    font-family: var(--font-d, var(--ff-mono)); font-size: 0.72rem; font-weight: 700;
    letter-spacing: 0.06em; text-transform: uppercase;
    padding: 0.22rem 0.5rem; border-radius: var(--radius-soft, 6px);
    background: var(--calm-surface-card, var(--bg-card));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    color: var(--calm-ink-chrome, var(--text-ui)); white-space: nowrap;
  }
  .qf-pill__tag { color: var(--calm-ink-chrome, var(--text-ui)); font-weight: 600; }
  .qf-pill__val { color: var(--calm-accent, var(--accent)); }
  .qf-pill__dot {
    width: 0.42rem; height: 0.42rem; border-radius: 50%;
    background: var(--calm-accent, var(--accent)); flex: 0 0 auto; opacity: 0.9;
  }
  .qf-pill[data-custom='true'] { border-color: var(--badge-obs-border, #cbd5e1); }
  .qf-pill[data-custom='true'] .qf-pill__val { color: var(--calm-ink-quiet, var(--text-dim)); }
  .qf-pill[data-custom='true'] .qf-pill__dot { background: var(--calm-ink-quiet, var(--text-dim)); opacity: 0.7; }

  /* === the preset section ============================================== */
  .qf { display: flex; flex-direction: column; gap: var(--space-3, 6px); }
  .qf__head {
    display: flex; align-items: baseline; gap: var(--space-4, 10px); flex-wrap: wrap;
  }
  .qf__label {
    font-size: var(--fs-meta, 13px); font-weight: 600; letter-spacing: 0.02em;
    color: var(--calm-ink-loud, var(--text-bright));
  }
  .qf__chip {
    font-size: 10px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase;
    color: var(--badge-ar-fg, #d97706); background: var(--badge-ar-bg, #fef3c7);
    border: var(--hairline, 1px) solid var(--badge-ar-border, #d97706);
    border-radius: 3px; padding: 1px 6px;
  }
  .qf__desc {
    margin: 0; font-size: var(--fs-chrome, 11px); line-height: var(--lh-body, 1.5);
    color: var(--calm-ink-quiet, var(--text-dim)); max-width: 62ch;
  }
  .qf__mock { font-family: var(--font-d, var(--ff-mono)); color: var(--badge-warn-fg, #ea580c); }

  /* the carousel: a hairline rail of monospace mode-cards, sized to content. */
  .qf-carousel {
    display: flex; align-items: stretch; flex-wrap: wrap;
    gap: var(--space-3, 6px); margin-top: var(--space-2, 4px);
  }

  .qf-card {
    appearance: none; text-align: left; cursor: pointer; position: relative;
    display: flex; flex-direction: column; gap: 0.2rem;
    min-width: 9.5rem; padding: var(--space-3, 6px) var(--space-4, 10px);
    background: var(--calm-surface-row, var(--bg-row));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: var(--radius-soft, 6px); color: var(--calm-ink, var(--text));
    transition: background var(--t-calm, 0.18s), border-color var(--t-calm, 0.18s), color var(--t-calm, 0.18s);
  }
  .qf-card:hover {
    background: var(--calm-surface-hover, var(--bg-row-hover));
    border-color: var(--calm-hairline-hi, var(--border-hi));
  }
  .qf-card__name {
    font-family: var(--font-d, var(--ff-mono)); font-size: var(--fs-meta, 13px);
    font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
    color: var(--calm-ink-loud, var(--text-bright)); font-variant-numeric: tabular-nums;
  }
  /* the literal micro-spec -- load-bearing TEXT (M4 second channel), not decoration. */
  .qf-card__spec {
    font-family: var(--font-d, var(--ff-mono)); font-size: 10.5px; line-height: 1.35;
    color: var(--calm-ink-quiet, var(--text-dim)); font-variant-numeric: tabular-nums;
  }
  .qf-card__kbd {
    position: absolute; top: var(--space-2, 4px); right: var(--space-3, 6px);
    font-family: var(--font-d, var(--ff-mono)); font-size: 9.5px;
    color: var(--calm-ink-chrome, var(--text-ui)); letter-spacing: 0.04em;
  }
  /* ACTIVE card: accent fill + heavier weight + the proven on-accent ink (the
     #1a1206-on-amber pairing from HitlModeToggle.svelte, axe-clean AA-documented). */
  .qf-card.is-active {
    background: var(--calm-accent, var(--accent));
    border-color: var(--calm-accent, var(--accent));
  }
  .qf-card.is-active .qf-card__name { color: #1a1206; font-weight: 800; }
  .qf-card.is-active .qf-card__spec { color: #1a1206; opacity: 0.9; }
  .qf-card.is-active .qf-card__kbd { color: #1a1206; opacity: 0.75; }
  :global([data-theme='paper']) .qf-card.is-active .qf-card__name,
  :global([data-theme='paper']) .qf-card.is-active .qf-card__spec,
  :global([data-theme='paper']) .qf-card.is-active .qf-card__kbd { color: #fffefb; }

  /* vertical hairline + the custom-group label */
  .qf-carousel__divider {
    width: 1px; align-self: stretch; flex: 0 0 auto; margin: 0 0.1rem;
    background: var(--calm-hairline, var(--border));
  }
  .qf-carousel__custom-label {
    flex-basis: 100%; font-size: 10px; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--calm-ink-quiet, var(--text-dim));
    margin-top: 0.2rem;
  }

  /* custom card: room for the "x" delete affordance */
  .qf-card--custom { padding-right: 1.5rem; }
  .qf-del {
    position: absolute; top: 0.3rem; right: 0.3rem;
    width: 16px; height: 16px; line-height: 1; padding: 0;
    display: inline-flex; align-items: center; justify-content: center;
    background: transparent; border: var(--hairline, 1px) solid transparent;
    border-radius: 3px; color: var(--calm-ink-chrome, var(--text-ui));
    cursor: pointer; font-size: 11px; font-family: var(--font-d, var(--ff-mono));
  }
  .qf-del:hover {
    color: var(--badge-blocked-fg, #dc2626);
    border-color: var(--calm-hairline, var(--border));
  }
  .qf-card--custom.is-active .qf-del { color: #1a1206; }
  :global([data-theme='paper']) .qf-card--custom.is-active .qf-del { color: #fffefb; }

  /* "Save as preset" -- a quiet dashed ghost button at the rail tail. */
  .qf-save {
    appearance: none; align-self: stretch;
    display: inline-flex; align-items: center; justify-content: center; gap: 0.35rem;
    min-width: 9.5rem;
    background: transparent;
    border: var(--hairline, 1px) dashed var(--calm-hairline-hi, var(--border-hi));
    border-radius: var(--radius-soft, 6px); color: var(--calm-ink-loud, var(--text-bright));
    font-family: var(--ff-system); font-size: 12px; font-weight: 600;
    letter-spacing: 0.02em; padding: var(--space-3, 6px) var(--space-4, 10px); cursor: pointer;
    transition: background var(--t-calm, 0.18s), color var(--t-calm, 0.18s), border-color var(--t-calm, 0.18s);
  }
  .qf-save:hover {
    background: var(--calm-accent-wash, var(--accent-dim));
    border-color: var(--calm-accent, var(--accent)); color: var(--calm-accent, var(--accent));
  }
  .qf-save__plus { font-family: var(--font-d, var(--ff-mono)); font-weight: 800; }

  /* shared focus ring: 2px solid amber, 2px offset (focus.css contract). */
  .qf-card:focus-visible,
  .qf-del:focus-visible,
  .qf-save:focus-visible,
  .qf-modal__input:focus-visible,
  .qf-modal__btn:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid) var(--focus-ring-color, #d97706);
    outline-offset: var(--focus-ring-offset, 2px);
  }

  /* === save-as-preset modal (focus-trapped dialog) ==================== */
  .qf-scrim {
    position: fixed; inset: 0; background: rgba(8, 10, 12, 0.55);
    backdrop-filter: blur(1px); z-index: 90;
    display: flex; align-items: center; justify-content: center; padding: 24px;
  }
  .qf-modal {
    width: min(360px, 92vw);
    background: var(--calm-surface-card, var(--bg-card));
    border: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi));
    border-radius: 10px; padding: 1.1rem;
    box-shadow: 0 18px 48px -24px rgba(0, 0, 0, 0.7);
  }
  .qf-modal__title {
    margin: 0 0 0.3rem; font-size: 0.9rem; font-weight: 700; letter-spacing: 0.02em;
    color: var(--calm-ink-loud, var(--text-bright));
  }
  .qf-modal__lede {
    margin: 0 0 0.7rem; font-size: 11px; line-height: var(--lh-body, 1.5);
    color: var(--calm-ink-quiet, var(--text-dim));
  }
  .qf-modal__input {
    width: 100%; box-sizing: border-box;
    font-family: var(--font-d, var(--ff-mono)); font-size: 13px;
    color: var(--calm-ink-loud, var(--text-bright));
    background: var(--calm-surface-row, var(--bg-row));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: 4px; padding: 0.45rem 0.55rem; margin-bottom: 0.8rem;
  }
  .qf-modal__actions { display: flex; justify-content: flex-end; gap: 0.5rem; }
  .qf-modal__btn {
    appearance: none; font-family: var(--ff-system); font-size: 12px; font-weight: 600;
    letter-spacing: 0.02em; padding: 0.4rem 0.8rem; border-radius: 4px; cursor: pointer;
  }
  .qf-modal__btn--ghost {
    background: transparent; border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    color: var(--calm-ink, var(--text));
  }
  .qf-modal__btn--ghost:hover {
    color: var(--calm-ink-loud, var(--text-bright));
    border-color: var(--calm-hairline-hi, var(--border-hi));
  }
  .qf-modal__btn--primary {
    background: var(--calm-accent, var(--accent));
    border: var(--hairline, 1px) solid var(--badge-ar-border, #d97706);
    color: #1a1206; font-weight: 700;
  }
  :global([data-theme='paper']) .qf-modal__btn--primary { color: #fffefb; }

  .qf-sr-only {
    position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
    overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
  }

  /* reduced motion: suppress the card/save transitions. */
  :global(html[data-motion='reduce']) .qf-card,
  :global(html[data-motion='reduce']) .qf-save { transition: none; }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .qf-card,
    :global(html:not([data-motion='allow'])) .qf-save { transition: none; }
  }
</style>
