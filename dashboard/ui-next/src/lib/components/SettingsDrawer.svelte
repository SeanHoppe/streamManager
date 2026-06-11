<!--
  SettingsDrawer.svelte -- the FR-UI-9 operator settings surface (unit
  u-settings-patterns).

  WHAT IT OWNS
    The full FR-UI-9 settings panel, restructured into the still-water calm-
    ambient idiom but PRESERVING the live dashboard behavioural contract field-
    for-field:

      1. HITL mode .............. SYNC | ASYNC  (M5: two states only, never off)
      2. Confidence floor ....... 0.00 .. 1.00 slider (advisory floor)
      3. Sync timeout (s) ....... 1 .. 3600 (HITL SYNC hold; M9 countdown source)
      4. Pause detection ........ on/off (desktop_pause auto-foreground source)
      5. Audible cue ............ on/off (audible escalation cue; default OFF)
      6. Sub-agents activity window (s) .. 1 .. 600 (Frame B active-in-window pin)
      7. Reduced motion ......... system | on (reduce) | off (allow)  (M17)
      8. Layout reset ........... operator action -> clears per-session layout

  PERSISTENCE CONTRACT (NO RELOAD)
    Every mutation flows through the u-stores `settings` store (patch / set /
    resetLayout). That store is the single owner of localStorage persistence
    AND of the `dashboard_settings_changed` CustomEvent (FR-UI-9). This drawer
    NEVER reloads the page and NEVER writes localStorage directly -- it calls
    the store, the store persists + emits, and every other pane reacts live.

    The two server-scoped fields (HITL mode + sync timeout + pause detection)
    are ALSO synced to the runtime via POST /api/hitl/settings so the live
    governance engine honors the operator's choice. That POST is the only
    network mutation this drawer performs; it is fire-and-forget and OFF the
    verdict hot path (M18). The client store is the source of truth for the UI;
    the server sync is best-effort and never blocks the UI update or reload.

  REDUCED MOTION (M17 / NFR-UI-7)
    The reduced-motion control writes html[data-motion="reduce"|"allow"] (or
    removes it for 'system'), which is exactly the attribute calm.css / focus.css
    / Badge.svelte read to gate every animation. 'system' defers to the OS
    prefers-reduced-motion; 'on' forces reduce; 'off' force-allows motion.

  M4 (paired label+color, never color alone): every toggle here renders a TEXT
  state ('ON'/'OFF', 'SYNC'/'ASYNC', etc.) beside any color -- a control's state
  is never conveyed by color alone. The HITL-mode control delegates to the
  shared HitlModeToggle (radiogroup, two states), reinforcing M5 structurally.

  M15/G2 (self-exclude polarity): the server HITL fields are scoped to the
  operator-selected NON-SELF session (selectedSessionId, which can never resolve
  to the SM own session). When no session is selected the server lets the
  field apply to the latest active governed session; we never bind settings to
  the SM own session.

  M16 (domain-agnostic): no monitored-project vocabulary anywhere. Every label
  is generic governance/UI taxonomy.

  M17 (a11y): drawer is role="dialog" aria-modal with a labelled heading, an
  Escape-to-close handler, focus moved to the panel on open and restored to the
  invoking element on close, and a focus trap. Every control is a real native
  input/button so the global 2px #d97706 focus ring (focus.css) applies; each
  carries an explicit <label>/aria-label. Sliders announce value via
  aria-valuetext.

  M18 (latency): pure post-hoc presentation + one best-effort settings POST.
  Nothing here sits on the verdict hot path.

  ASCII-only (cp1252-safe): dash rendered as "--".
-->
<script context="module">
  /**
   * Reduced-motion option table (M17). The `attr` is the html[data-motion]
   * value calm.css/focus.css/Badge.svelte read; 'system' clears the attribute
   * so the OS preference governs. Frozen so the contract is one auditable table.
   */
  export const MOTION_OPTIONS = Object.freeze([
    { value: 'system', label: 'SYSTEM', attr: null, hint: 'Follow the operating system reduced-motion preference' },
    { value: 'on',      label: 'REDUCE', attr: 'reduce', hint: 'Force reduced motion -- suppress all non-essential animation' },
    { value: 'off',     label: 'ALLOW',  attr: 'allow', hint: 'Force-allow motion even if the OS requests reduced motion' },
  ]);

  /**
   * Apply the reduced-motion preference to the document root. This is the ONE
   * place the data-motion attribute is written; calm.css / focus.css / Badge
   * read it to gate every animation in the product. 'system' removes the
   * attribute so prefers-reduced-motion governs.
   * @param {'system'|'on'|'off'} value
   */
  export function applyMotionPreference(value) {
    if (typeof document === 'undefined') return;
    const opt = MOTION_OPTIONS.find((o) => o.value === value) || MOTION_OPTIONS[0];
    const root = document.documentElement;
    if (opt.attr === null) root.removeAttribute('data-motion');
    else root.setAttribute('data-motion', opt.attr);
  }
</script>

<script>
  import { createEventDispatcher, onMount, onDestroy, tick } from 'svelte';
  import { settings, patch, resetLayout, DEFAULT_SETTINGS } from '../stores/settings.js';
  import { selectedSessionId } from '../stores/session.js';
  import HitlModeToggle from './HitlModeToggle.svelte';

  /** open: whether the drawer is shown. Two-way bindable from the parent. */
  export let open = false;

  /**
   * postSettings: injectable server-sync hook (OPTIONAL). Defaults to a best-
   * effort POST /api/hitl/settings so the running governance engine honors the
   * operator's HITL mode / timeout / pause-detection choice. Injectable so the
   * drawer is testable in isolation without a live server, and so api.js (owned
   * by u-stores) need not be edited to add a wrapper this unit alone consumes.
   * Fire-and-forget, OFF the verdict hot path (M18).
   * @type {(body: Record<string, any>) => Promise<any>}
   */
  export let postSettings = defaultPostSettings;

  const dispatch = createEventDispatcher();
  const FLOOR_ID = 'sm-set-floor';
  const TIMEOUT_ID = 'sm-set-timeout';
  const WINDOW_ID = 'sm-set-window';

  /** @type {HTMLDivElement|null} */
  let panelEl = null;
  /** @type {Element|null} the element focused before the drawer opened */
  let prevFocus = null;

  // Local mirror of the store so inputs bind two-way without writing back on
  // every keystroke before coercion. We subscribe and copy; every commit goes
  // back through patch() (which coerces + persists + emits).
  let s = { ...DEFAULT_SETTINGS };
  const unsub = settings.subscribe((v) => {
    s = { ...v };
    // Keep the document motion attribute in lock-step with the persisted value,
    // including on first hydrate (so a returning operator's choice is applied).
    applyMotionPreference(s.reducedMotion);
  });

  // The server-scoped HITL session (M15: never the SM own session). null => the
  // server applies the change to the latest active governed session.
  $: serverSessionId = $selectedSessionId;

  /**
   * Default server sync: POST /api/hitl/settings. Best-effort. Swallows errors
   * (the client store already persisted; a server-down condition must not block
   * the operator's UI). NOT on the verdict hot path (M18).
   * @param {Record<string, any>} body
   */
  async function defaultPostSettings(body) {
    if (typeof fetch === 'undefined') return;
    try {
      await fetch('/api/hitl/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        cache: 'no-store',
        body: JSON.stringify(body),
      });
    } catch {
      /* best-effort runtime sync; client store remains the UI source of truth */
    }
  }

  /**
   * Sync the server-scoped HITL fields to the runtime. Only the subset the
   * server owns (mode/floor/timeout/pause) is sent. session_id is the operator-
   * selected non-self session (M15) or omitted so the server picks the latest
   * active governed session.
   * @param {Partial<{hitl_mode:string, hitl_floor:number, timeout_seconds:number, pause_detection_enabled:boolean}>} fields
   */
  function syncServer(fields) {
    /** @type {Record<string, any>} */
    const body = { ...fields };
    if (serverSessionId) body.session_id = serverSessionId;
    // fire-and-forget; never awaited on a UI-blocking path
    void postSettings(body);
  }

  // --- field commits: each goes through patch() (coerce + persist + emit) -----

  /** @param {'sync'|'async'} mode */
  function onHitlModePromoted(mode) {
    if (mode !== 'sync' && mode !== 'async') return;
    patch({ hitlMode: mode });
    syncServer({ hitl_mode: mode });
  }

  function onFloorInput(e) {
    const v = Number(/** @type {HTMLInputElement} */ (e.currentTarget).value);
    patch({ confidenceFloor: v });
    syncServer({ hitl_floor: v });
  }

  function onTimeoutInput(e) {
    const v = Math.round(Number(/** @type {HTMLInputElement} */ (e.currentTarget).value));
    patch({ syncTimeoutSec: v });
    syncServer({ timeout_seconds: v });
  }

  function onWindowInput(e) {
    const v = Math.round(Number(/** @type {HTMLInputElement} */ (e.currentTarget).value));
    patch({ activityWindowSec: v });
  }

  function onPauseToggle(e) {
    const v = /** @type {HTMLInputElement} */ (e.currentTarget).checked;
    patch({ pauseDetection: v });
    syncServer({ pause_detection_enabled: v });
  }

  function onAudibleToggle(e) {
    const v = /** @type {HTMLInputElement} */ (e.currentTarget).checked;
    patch({ audibleCue: v });
  }

  /** @param {'system'|'on'|'off'} value */
  function onMotionSelect(value) {
    patch({ reducedMotion: value });
    applyMotionPreference(value);
  }

  /**
   * Layout reset (FR-UI-9 row 8). Delegates to the store, which re-broadcasts
   * dashboard_settings_changed with {layoutReset:true}; u-shell clears its per-
   * session layout localStorage in response. No reload (M1 Reset contract).
   */
  function onResetLayout() {
    resetLayout();
    dispatch('layoutReset');
  }

  function close() {
    open = false;
    dispatch('close');
  }

  // --- a11y: open/close lifecycle, focus management, Escape, focus trap -------

  $: if (open) onOpen();

  async function onOpen() {
    if (typeof document !== 'undefined') prevFocus = document.activeElement;
    await tick();
    if (panelEl) {
      const first = panelEl.querySelector(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      /** @type {HTMLElement|null} */ (first || panelEl).focus?.();
    }
  }

  function restoreFocus() {
    if (prevFocus && typeof (/** @type {any} */ (prevFocus).focus) === 'function') {
      /** @type {HTMLElement} */ (prevFocus).focus();
    }
    prevFocus = null;
  }

  function onKeydown(e) {
    if (!open) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      restoreFocus();
      close();
      return;
    }
    if (e.key === 'Tab' && panelEl) {
      // simple focus trap within the panel
      const focusables = /** @type {HTMLElement[]} */ (
        Array.from(
          panelEl.querySelectorAll(
            'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
          ),
        )
      ).filter((el) => el.offsetParent !== null || el === document.activeElement);
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  onMount(() => {
    if (typeof window !== 'undefined') window.addEventListener('keydown', onKeydown);
    // Apply persisted motion preference on mount (covers SSR/first-paint).
    applyMotionPreference(s.reducedMotion);
  });
  onDestroy(() => {
    unsub();
    if (typeof window !== 'undefined') window.removeEventListener('keydown', onKeydown);
  });

  // Derived display strings (M4: state is always text, never color alone).
  $: floorPct = Math.round((Number(s.confidenceFloor) || 0) * 100);
  $: pauseText = s.pauseDetection ? 'ON' : 'OFF';
  $: audibleText = s.audibleCue ? 'ON' : 'OFF';
</script>

{#if open}
  <!-- scrim: click-out closes; not a focus target -->
  <div
    class="sd-scrim"
    on:click={() => {
      restoreFocus();
      close();
    }}
    aria-hidden="true"
  ></div>

  <div
    class="sd-panel"
    role="dialog"
    aria-modal="true"
    aria-labelledby="sd-title"
    bind:this={panelEl}
    tabindex="-1"
  >
    <header class="sd-head">
      <h2 id="sd-title" class="sd-title sev-notice">Operator settings</h2>
      <button
        type="button"
        class="sd-close"
        aria-label="Close settings"
        on:click={() => {
          restoreFocus();
          close();
        }}
      >
        <span aria-hidden="true">x</span>
      </button>
    </header>

    <div class="sd-body">
      <!-- 1. HITL MODE (M5: SYNC | ASYNC only) ------------------------------ -->
      <section class="sd-field" aria-labelledby="sd-hitl-lbl">
        <div class="sd-field__head">
          <span id="sd-hitl-lbl" class="sd-label">HITL mode</span>
          <span class="sd-value sev-base">{s.hitlMode === 'sync' ? 'SYNC' : 'ASYNC'}</span>
        </div>
        <p class="sd-desc sev-quiet">
          SYNC holds the message until you decide; ASYNC lets you decide and
          annotate without holding. There is no off state.
        </p>
        <HitlModeToggle
          mode={s.hitlMode}
          sessionId={serverSessionId}
          on:promoted={(e) => onHitlModePromoted(e.detail.mode)}
        />
      </section>

      <!-- 2. CONFIDENCE FLOOR ---------------------------------------------- -->
      <section class="sd-field">
        <div class="sd-field__head">
          <label class="sd-label" for={FLOOR_ID}>Confidence floor</label>
          <span class="sd-value sev-base">{floorPct}%</span>
        </div>
        <p class="sd-desc sev-quiet">
          Advisory threshold below which a decision is flagged low-confidence
          in place (badge only -- never auto-foreground).
        </p>
        <input
          id={FLOOR_ID}
          class="sd-range"
          type="range"
          min="0"
          max="1"
          step="0.01"
          value={s.confidenceFloor}
          aria-valuetext={`${floorPct} percent`}
          on:input={onFloorInput}
        />
      </section>

      <!-- 3. SYNC TIMEOUT --------------------------------------------------- -->
      <section class="sd-field">
        <div class="sd-field__head">
          <label class="sd-label" for={TIMEOUT_ID}>Sync timeout</label>
          <span class="sd-value sev-base">{s.syncTimeoutSec}s</span>
        </div>
        <p class="sd-desc sev-quiet">
          How long a SYNC HITL hold waits for an operator decision before it
          times out. Drives the pending-row countdown.
        </p>
        <input
          id={TIMEOUT_ID}
          class="sd-range"
          type="range"
          min="1"
          max="300"
          step="1"
          value={s.syncTimeoutSec}
          aria-valuetext={`${s.syncTimeoutSec} seconds`}
          on:input={onTimeoutInput}
        />
      </section>

      <!-- 4. PAUSE DETECTION (toggle) -------------------------------------- -->
      <section class="sd-field sd-field--inline">
        <div class="sd-toggle-row">
          <span class="sd-label">Pause detection</span>
          <label class="sd-switch">
            <input
              type="checkbox"
              checked={s.pauseDetection}
              aria-label={`Desktop pause detection (currently ${pauseText})`}
              on:change={onPauseToggle}
            />
            <span class="sd-switch__track" aria-hidden="true">
              <span class="sd-switch__knob"></span>
            </span>
            <span class="sd-switch__text sev-base" data-on={s.pauseDetection}>{pauseText}</span>
          </label>
        </div>
        <p class="sd-desc sev-quiet">
          When on, a detected desktop-orchestration pause auto-foregrounds a
          frame (one of the three true escalation triggers).
        </p>
      </section>

      <!-- 5. AUDIBLE CUE (toggle) ------------------------------------------ -->
      <section class="sd-field sd-field--inline">
        <div class="sd-toggle-row">
          <span class="sd-label">Audible cue</span>
          <label class="sd-switch">
            <input
              type="checkbox"
              checked={s.audibleCue}
              aria-label={`Audible escalation cue (currently ${audibleText})`}
              on:change={onAudibleToggle}
            />
            <span class="sd-switch__track" aria-hidden="true">
              <span class="sd-switch__knob"></span>
            </span>
            <span class="sd-switch__text sev-base" data-on={s.audibleCue}>{audibleText}</span>
          </label>
        </div>
        <p class="sd-desc sev-quiet">
          Play a short sound on a true escalation. Off by default to keep the
          monitor calm.
        </p>
      </section>

      <!-- 6. SUB-AGENTS ACTIVITY WINDOW ------------------------------------ -->
      <section class="sd-field">
        <div class="sd-field__head">
          <label class="sd-label" for={WINDOW_ID}>Sub-agents activity window</label>
          <span class="sd-value sev-base">{s.activityWindowSec}s</span>
        </div>
        <p class="sd-desc sev-quiet">
          A sub-agent counts as "active in window" -- and pins to the top of
          Frame B -- if it has an event within this span.
        </p>
        <input
          id={WINDOW_ID}
          class="sd-range"
          type="range"
          min="1"
          max="120"
          step="1"
          value={s.activityWindowSec}
          aria-valuetext={`${s.activityWindowSec} seconds`}
          on:input={onWindowInput}
        />
      </section>

      <!-- 7. REDUCED MOTION (M17) ------------------------------------------ -->
      <section class="sd-field" aria-labelledby="sd-motion-lbl">
        <div class="sd-field__head">
          <span id="sd-motion-lbl" class="sd-label">Reduced motion</span>
        </div>
        <p class="sd-desc sev-quiet">
          Override the animation budget. SYSTEM follows your OS setting; REDUCE
          forces motion off; ALLOW force-enables it.
        </p>
        <div class="sd-seg" role="radiogroup" aria-label="Reduced motion preference">
          {#each MOTION_OPTIONS as opt (opt.value)}
            <button
              type="button"
              class="sd-seg__btn"
              class:is-active={s.reducedMotion === opt.value}
              role="radio"
              aria-checked={s.reducedMotion === opt.value}
              aria-label={`Reduced motion: ${opt.label} -- ${opt.hint}`}
              title={opt.hint}
              tabindex={s.reducedMotion === opt.value ? 0 : -1}
              on:click={() => onMotionSelect(opt.value)}
            >
              {opt.label}
            </button>
          {/each}
        </div>
      </section>

      <!-- 8. LAYOUT RESET (operator action) -------------------------------- -->
      <section class="sd-field sd-field--action">
        <div class="sd-field__head">
          <span class="sd-label">Frame layout</span>
        </div>
        <p class="sd-desc sev-quiet">
          Restore the three frames (Sessions / Sub-Agents / Background Jobs) to
          their default arrangement and scroll positions for this session.
        </p>
        <button type="button" class="sd-reset" on:click={onResetLayout}>
          Reset layout
        </button>
      </section>
    </div>
  </div>
{/if}

<style>
  /* The drawer slides in from the right as a calm panel; the scrim dims the
     monitor without obscuring it. Motion is a single short opacity/transform
     transition (calm budget) and is suppressed under reduced-motion. */
  .sd-scrim {
    position: fixed;
    inset: 0;
    background: rgba(8, 10, 12, 0.55);
    backdrop-filter: blur(1px);
    z-index: 80;
  }

  .sd-panel {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: min(420px, 92vw);
    z-index: 81;
    display: flex;
    flex-direction: column;
    background: var(--calm-surface-raised, #0c1118);
    border-left: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi));
    box-shadow: -18px 0 48px -24px rgba(0, 0, 0, 0.7);
    color: var(--calm-ink, var(--text));
    font-family: var(--ff-system);
    /* independent scroll discipline -- the panel body scrolls, the head pins */
    overflow: hidden;
  }

  .sd-head {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: var(--space-5, 14px) var(--space-6, 22px);
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
  }
  .sd-title {
    margin: 0;
    font-family: var(--font-h, var(--ff-system));
    font-size: 18px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--calm-ink-loud, var(--text-bright));
  }

  .sd-close {
    appearance: none;
    background: transparent;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: var(--radius-sharp, 2px);
    color: var(--calm-ink-chrome, var(--text-ui));
    width: 28px;
    height: 28px;
    line-height: 1;
    font-size: 14px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: color var(--t-calm), border-color var(--t-calm);
  }
  .sd-close:hover {
    color: var(--calm-accent, var(--accent));
    border-color: var(--calm-hairline-hi, var(--border-hi));
  }

  .sd-body {
    flex: 1 1 auto;
    overflow-y: auto;
    padding: var(--space-5, 14px) var(--space-6, 22px) var(--space-7, 36px);
    /* asymmetric vertical rhythm between fields */
    display: flex;
    flex-direction: column;
    gap: var(--space-6, 22px);
  }

  .sd-field {
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 6px);
  }
  .sd-field--action {
    border-top: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    padding-top: var(--space-5, 14px);
  }

  .sd-field__head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-4, 10px);
  }

  .sd-label {
    font-size: var(--fs-meta, 13px);
    font-weight: 600;
    letter-spacing: 0.02em;
    color: var(--calm-ink-loud, var(--text-bright));
  }

  .sd-value {
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-meta, 13px);
    font-variant-numeric: tabular-nums;
    color: var(--calm-accent, var(--accent));
  }

  .sd-desc {
    margin: 0;
    font-size: var(--fs-chrome, 11px);
    line-height: var(--lh-body, 1.5);
    color: var(--calm-ink-quiet, var(--text-dim));
    max-width: 46ch;
  }

  /* Range inputs: a calm hairline track with an accent thumb. The native
     control is kept (real input[type=range]) so the focus.css ring + keyboard
     behaviour apply for free (M17). */
  .sd-range {
    width: 100%;
    margin: var(--space-2, 4px) 0 0;
    accent-color: var(--calm-accent, var(--accent));
    cursor: pointer;
  }

  /* Toggle switch -- a real checkbox (visually styled), so it is keyboard- and
     screen-reader-native; the paired TEXT (ON/OFF) is the actual signal (M4). */
  .sd-toggle-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4, 10px);
  }
  .sd-switch {
    display: inline-flex;
    align-items: center;
    gap: var(--space-3, 6px);
    cursor: pointer;
  }
  .sd-switch input {
    /* keep the native input in the layout (so :focus-visible ring lands on it)
       but visually collapse it -- the track below is the painted affordance */
    position: absolute;
    width: 1px;
    height: 1px;
    margin: -1px;
    padding: 0;
    border: 0;
    clip: rect(0 0 0 0);
    overflow: hidden;
  }
  .sd-switch__track {
    position: relative;
    width: 38px;
    height: 20px;
    border-radius: 999px;
    background: var(--calm-surface-row, var(--bg-row));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    transition: background var(--t-calm), border-color var(--t-calm);
    flex: 0 0 auto;
  }
  .sd-switch__knob {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: var(--calm-ink-chrome, var(--text-ui));
    transition: transform var(--t-calm), background var(--t-calm);
  }
  .sd-switch input:checked + .sd-switch__track {
    background: var(--calm-accent-wash, var(--accent-dim));
    border-color: var(--calm-hairline-hi, var(--border-hi));
  }
  .sd-switch input:checked + .sd-switch__track .sd-switch__knob {
    transform: translateX(18px);
    background: var(--calm-accent, var(--accent));
  }
  /* The :focus-visible ring lands on the visually-hidden input; mirror it onto
     the painted track so keyboard focus is visible (M17). */
  .sd-switch input:focus-visible + .sd-switch__track {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid)
      var(--focus-ring-color, #d97706);
    outline-offset: var(--focus-ring-offset, 2px);
  }
  .sd-switch__text {
    min-width: 3ch;
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-meta, 13px);
    letter-spacing: 0.06em;
    color: var(--calm-ink-quiet, var(--text-dim));
  }
  .sd-switch__text[data-on='true'] {
    color: var(--calm-accent, var(--accent));
  }

  /* Segmented radiogroup (reduced motion) -- mirrors the HitlModeToggle idiom:
     active segment carries the accent fill + heavier weight + the text label. */
  .sd-seg {
    display: inline-flex;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: var(--radius-soft, 4px);
    overflow: hidden;
    align-self: flex-start;
  }
  .sd-seg__btn {
    appearance: none;
    background: transparent;
    border: none;
    color: var(--calm-ink-chrome, var(--text-ui));
    font-family: var(--ff-system);
    font-size: var(--fs-badge, 12px);
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: var(--space-2, 4px) var(--space-4, 10px);
    cursor: pointer;
    line-height: 1;
    transition: background var(--t-calm), color var(--t-calm);
  }
  .sd-seg__btn + .sd-seg__btn {
    border-left: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
  }
  .sd-seg__btn:hover {
    background: var(--calm-surface-hover, var(--bg-row-hover));
  }
  .sd-seg__btn.is-active {
    background: var(--calm-accent, var(--accent));
    color: #fffbeb;
    font-weight: 750;
  }
  :global([data-theme='paper']) .sd-seg__btn.is-active {
    color: #fffefb;
  }

  /* Reset action button -- deliberate, quiet, bordered (not a destructive red:
     it is a non-data operator preference). */
  .sd-reset {
    appearance: none;
    align-self: flex-start;
    background: transparent;
    border: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi));
    border-radius: var(--radius-sharp, 2px);
    color: var(--calm-ink-loud, var(--text-bright));
    font-family: var(--ff-system);
    font-size: var(--fs-meta, 13px);
    font-weight: 600;
    letter-spacing: 0.04em;
    padding: var(--space-3, 6px) var(--space-5, 14px);
    cursor: pointer;
    transition: background var(--t-calm), color var(--t-calm), border-color var(--t-calm);
  }
  .sd-reset:hover {
    background: var(--calm-accent-wash, var(--accent-dim));
    border-color: var(--calm-accent, var(--accent));
    color: var(--calm-accent, var(--accent));
  }

  /* The drawer's own slide-in is a calm transition; suppress under reduced
     motion (the data-motion attribute the drawer itself writes). */
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .sd-switch__knob {
      transition: none;
    }
  }
  :global(html[data-motion='reduce']) .sd-switch__knob {
    transition: none;
  }
</style>
