<!--
  HitlModeToggle.svelte -- the M5 runtime HITL-mode switch.

  CONTRACT (inviolable MUST M5):
    - EXACTLY two modes are ever exposed: SYNC (hold) and ASYNC (decide +
      annotate). There is NO "off" position. The control is a two-state segmented
      switch; a third state is structurally impossible (the value is coerced to
      one of the two literals before render, mirroring settings.js coerce()).
    - Switching at runtime POSTs /api/hitl/mode {session_id, mode}; the SERVER
      emits `hitl_mode_promoted` on the bus (the UI does not fabricate that
      event -- it requests the switch and lets the server promote). On a
      successful switch this leaf emits a local `promoted` event so the parent
      (HitlDock) can reflect the new mode immediately + the settings store can
      mirror it. On failure it rolls the visual state back (optimistic-but-safe).
    - Self-exclude (M15) is upstream: the parent never renders a toggle bound to
      the SM's own session. This leaf just refuses to POST when handed a blank
      session_id, so it can never promote a mode against "no session".

  ACCESSIBILITY (M17):
    - role="radiogroup" with two role="radio" buttons (SYNC / ASYNC). Arrow keys
      + Space/Enter select; aria-checked tracks the active mode. Each option is a
      real <button> so the global 2px #d97706 focus ring (focus.css) applies. The
      group has an aria-label; neither option's accessible name is ever empty.
    - The active mode is conveyed by aria-checked + a text label + a paired fill,
      never by color alone (M4 discipline, even though this is not an M4 badge).

  CRAFT (calm-ambient spine, KingMode): a quiet segmented control. The active
  segment carries the accent fill + heavier type weight; the inactive segment is
  still slate. No motion -- mode is a deliberate operator act, not telemetry, so
  it does not animate. Density tight; both labels clear the NFR-UI-2 floor.

  M16: domain-agnostic -- the only literals are the two governance mode names
  SYNC / ASYNC (UI taxonomy, not monitored-project vocabulary). M18: the only
  network call is the operator-initiated mode POST -- never on the verdict hot
  path.
-->
<script context="module">
  // The two -- and only two -- HITL modes (M5). Frozen so the S2 render-validator
  // can assert the control never surfaces a third option. Values match the
  // settings.js / server contract ('sync' | 'async').
  export const HITL_MODES = Object.freeze([
    { value: 'sync', label: 'SYNC', hint: 'Hold the message until the operator decides' },
    { value: 'async', label: 'ASYNC', hint: 'Decide and annotate without holding the message' },
  ]);

  /**
   * Coerce any incoming value to one of the two legal modes. Anything that is
   * not exactly 'sync' falls back to 'async' -- there is no third state (M5),
   * mirroring settings.js coerce().
   * @param {unknown} v
   * @returns {'sync'|'async'}
   */
  export function coerceMode(v) {
    return v === 'sync' ? 'sync' : 'async';
  }
</script>

<script>
  import { createEventDispatcher } from 'svelte';
  import { postHitlMode } from '../api.js';

  /**
   * mode: the active HITL mode (two-way bindable). Coerced to 'sync'|'async'
   * before every render so a corrupt value can never paint a third state (M5).
   * @type {'sync'|'async'}
   */
  export let mode = 'async';

  /**
   * sessionId: the session the mode applies to. When blank/null the toggle is
   * inert (it refuses to POST a mode against "no session"). Self-exclude (M15)
   * is enforced upstream -- this is never bound to the SM's own session.
   * @type {string|null}
   */
  export let sessionId = null;

  /** disabled: external lock (e.g. while a parent action is mid-flight). */
  export let disabled = false;

  const dispatch = createEventDispatcher();

  // In-flight guard so a double-click can't fire two competing mode POSTs.
  let switching = false;

  $: active = coerceMode(mode);
  $: hasSession = typeof sessionId === 'string' && sessionId.trim() !== '';
  $: inert = disabled || switching || !hasSession;

  /**
   * Request a mode switch (M5). Optimistic: flip the visual state immediately,
   * POST /api/hitl/mode, and roll back on error. The SERVER emits
   * hitl_mode_promoted on success; we emit a local `promoted` event so the
   * parent can mirror the new mode without waiting for the SSE round-trip.
   * @param {'sync'|'async'} next
   */
  async function switchTo(next) {
    const target = coerceMode(next);
    if (inert || target === active) return;

    const prev = active;
    mode = target; // optimistic flip (M5 -- two states only)
    switching = true;
    try {
      await postHitlMode({ session_id: sessionId, mode: target });
      // Success: the server has (or will) emit hitl_mode_promoted on the bus.
      dispatch('promoted', { sessionId, mode: target, previousMode: prev });
    } catch (err) {
      // Roll back the visual state; the gate is unchanged on failure.
      mode = prev;
      dispatch('error', { sessionId, attemptedMode: target, error: err });
    } finally {
      switching = false;
    }
  }

  // Keyboard: arrow keys move between the two radios within the group.
  function onKeydown(e) {
    if (inert) return;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      switchTo(active === 'sync' ? 'async' : 'sync');
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      switchTo(active === 'async' ? 'sync' : 'async');
    }
  }
</script>

<div
  class="hmt"
  class:hmt--inert={inert}
  role="radiogroup"
  aria-label="HITL mode"
  on:keydown={onKeydown}
>
  {#each HITL_MODES as m (m.value)}
    <button
      type="button"
      class="hmt__seg"
      class:is-active={active === m.value}
      role="radio"
      aria-checked={active === m.value}
      aria-label={`HITL ${m.label} -- ${m.hint}`}
      title={m.hint}
      tabindex={active === m.value ? 0 : -1}
      disabled={inert}
      on:click={() => switchTo(m.value)}
    >
      <span class="hmt__dot" aria-hidden="true"></span>
      <span class="hmt__label">{m.label}</span>
    </button>
  {/each}
</div>

<style>
  /* A quiet segmented control. The active segment carries the accent fill +
     heavier type; the inactive segment stays still slate. No motion -- a mode
     switch is a deliberate act, not telemetry. */
  .hmt {
    display: inline-flex;
    align-items: stretch;
    gap: 0;
    border: 1px solid var(--calm-hairline, #cbd5e1);
    border-radius: var(--radius-soft, 4px);
    overflow: hidden;
    background: var(--calm-surface-raised, #0c1118);
  }
  .hmt--inert {
    opacity: 0.55;
  }

  .hmt__seg {
    appearance: none;
    display: inline-flex;
    align-items: center;
    gap: var(--space-2, 4px);
    border: none;
    background: transparent;
    color: var(--calm-ink-chrome, #8a8068);
    font-family: var(--ff-system, system-ui, sans-serif);
    font-size: var(--fs-badge, 12px);
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: var(--space-2, 4px) var(--space-4, 10px);
    cursor: pointer;
    line-height: 1;
    transition: background var(--t-calm, 180ms ease), color var(--t-calm, 180ms ease);
  }
  .hmt__seg + .hmt__seg {
    border-left: 1px solid var(--calm-hairline, #cbd5e1);
  }
  .hmt__seg:hover:not(:disabled) {
    background: var(--calm-surface-hover, #131c2a);
  }
  .hmt__seg:disabled {
    cursor: default;
  }

  /* Active segment: accent fill + heavier weight + loud ink. The text label is
     ALWAYS present, so the active state is never conveyed by fill alone (M4). */
  .hmt__seg.is-active {
    background: var(--calm-accent, #d97706);
    /* Dark ink on the saturated amber fill (the M4 ACTION-REQUIRED idiom). The
       near-white #fffbeb on obsidian's amber (--calm-accent #f59e0b) was 2.07 --
       a serious WCAG AA fail. This warm near-black is 8.6:1 on #f59e0b and 5.8:1
       on the #d97706 fallback. The paper theme keeps its own light ink (its fill
       is the dark editorial red, overridden below). axe color-contrast. */
    color: #1a1206;
    font-weight: 750;
  }

  /* Paired dot glyph -- decorative; filled on the active segment. */
  .hmt__dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    opacity: 0.55;
    flex: 0 0 auto;
  }
  .hmt__seg.is-active .hmt__dot {
    opacity: 1;
  }

  .hmt__label {
    display: inline;
  }

  /* Paper theme: the active fill uses the editorial-red accent on the warm
     ground; the label stays high-contrast cream. */
  :global([data-theme='paper']) .hmt__seg.is-active {
    background: var(--calm-accent, #c0392b);
    color: #fffefb;
  }
</style>
