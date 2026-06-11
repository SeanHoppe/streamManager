<!--
  CanaryEchoRow.svelte -- FR-PPP Layer-2 canary echo surface (M12).

  WHAT THIS IS
    A canary echo proves the governance<->session binding BOTH ways. The bridge
    emits a one-time nonce; the operator types that nonce into their active
    Claude CLI session; if the parser observes the nonce coming back through the
    JSONL stream it claims to be reading, the binding is proven. This leaf
    renders one canary: the nonce, the prompt-to-type, and a countdown -- then
    flips state from the live SSE stream.

  CONTRACT (inviolable MUST M12):
    - Render the nonce + the prompt-to-type with a COUNTDOWN (reuses the M9
      CountdownBar primitive from u-badge so the countdown contract is shared,
      not re-implemented).
    - State machine driven by the audit.* SSE events:
        pending  -> observed : binding proven; AUTO-CLEAR after 1.5s (a brief
                               confirmation flash, then the row dispatches
                               `clear` so the list drops it).
        pending  -> failed   : binding suspect; render the failure REASON.
      (The emit / observed / failure events are delivered by the sse.js named-
      bus fan-out; the parent passes the resulting state in via `canary`, OR
      this leaf can subscribe itself when handed a probeId -- see below.)
    - May TRIGGER a canary via POST /api/sm-canary/emit and register a decoy via
      POST /api/sm-decoy/register (negative-control). Both are operator-
      initiated; neither sits on the verdict path (M18).

  CRAFT (calm-ambient spine, KingMode):
    The canary is a quiet proof-of-life, not an alarm -- it lives in the calm
    register. The nonce is the hero of the row: rendered LARGE and monospaced
    with generous tracking so it is trivially copy-typed, framed by a quiet
    accent-wash chip. The countdown is the shared still-water bar (no hue
    alarm as time runs out). On `observed` the row settles to a calm DECIDED
    green confirmation for its 1.5s flash; on `failed` it shifts to the WARN
    register with the reason as real prose. Severity is type weight, never
    saturation spikes.

  M4 (paired label+color): every state is named in WORDS -- "CANARY ECHO",
    "confirmed", "FAILED" -- color is always the second channel. The confirmed
    state pairs the DECIDED badge label with green; failed pairs WARN with the
    reason text. No state is signalled by color alone.

  M16 (domain-agnostic): the nonce, jsonl_path, reason, session id, decoy path
    -- all DATA from the envelope / props. No monitored-project vocabulary. The
    prompt-to-type copy is generic ("your active Claude CLI session").

  M17 (a11y): the nonce is selectable text in a labelled region; state changes
    are announced via aria-live; the trigger / decoy / dismiss controls are real
    <button>s with non-empty accessible names + the focus.css amber ring.

  M18 (post-hoc): the only network is the operator-initiated emit / decoy POSTs.
    No polling, nothing on the verdict hot path. State arrives over the existing
    /events SSE transport (never /api/commands/stream).

  FILE-DISJOINT: owns only itself. Consumes api.js (emit/decoy) + sse.js
  (onBusEvent, optional self-subscription) + the CountdownBar primitive. Emits
  `clear` so the parent list drops the row; performs no list mutation itself.
-->
<script>
  import { createEventDispatcher, onDestroy } from 'svelte';
  import CountdownBar from './CountdownBar.svelte';
  import { onBusEvent } from '../sse.js';
  import { postCanaryEmit, postDecoyRegister } from '../api.js';

  /**
   * canary: the current canary state for ONE probe, as assembled by the audit
   * store from the audit.canary_emit / canary_observed / probe_failure events:
   *   { probe_id, nonce, jsonl_path?, issued_at?, timeout_s?, status, failure_reason? }
   * status is 'pending' | 'observed' | 'failed'. When the parent already owns
   * the state machine it passes the whole object and re-renders on change; this
   * leaf then just reflects it. REQUIRED when not self-subscribing.
   * @type {{ probe_id?:string, nonce?:string, jsonl_path?:string,
   *          issued_at?:number, timeout_s?:number,
   *          status?:'pending'|'observed'|'failed', failure_reason?:string }
   *        | null}
   */
  export let canary = null;

  /**
   * subscribe: when true, this leaf binds its OWN named-bus listeners for the
   * probe_id and runs the state machine internally (useful when rendered
   * standalone). When false (default) the parent owns state and passes `canary`.
   * Both paths honor the identical M12 transitions.
   */
  export let subscribe = false;

  const dispatch = createEventDispatcher();

  // ---- Internal state machine (only used when subscribe=true). --------------
  // We keep a local mirror so the standalone path is correct; when the parent
  // drives state, `canary` flows straight through.
  let local = null;
  $: model = subscribe ? local : canary;

  $: probeId = (model && model.probe_id) || '';
  $: nonce = (model && model.nonce) || '';
  $: status = (model && model.status) || 'pending';
  $: timeoutS = Math.max(1, Number(model && model.timeout_s) || 10);
  $: issuedAtMs = model && model.issued_at ? Number(model.issued_at) * 1000 : undefined;
  $: failureReason = (model && model.failure_reason) || '';
  $: jsonlPath = (model && model.jsonl_path) || '';

  // ---- Self-subscription (subscribe=true). Mirrors the live dashboard's SSE
  //      handlers exactly: emit sets pending; observed -> auto-clear 1.5s;
  //      probe_failure -> failed + reason. ---------------------------------
  let _unsubs = [];
  let _clearTimer = null;

  function bindSelf(pid) {
    teardownSelf();
    if (!pid) return;

    _unsubs.push(
      onBusEvent('audit.canary_emit', (env) => {
        if (!env || env.probe_id !== pid) return;
        local = {
          probe_id: pid,
          nonce: env.nonce,
          jsonl_path: env.jsonl_path,
          issued_at: env.issued_at,
          timeout_s: env.timeout_s,
          status: 'pending',
        };
      }),
    );

    _unsubs.push(
      onBusEvent('audit.canary_observed', (env) => {
        if (!env || env.probe_id !== pid || !local) return;
        local = { ...local, status: 'observed' };
        // M12: pending -> observed auto-clears after a 1.5s confirmation flash.
        scheduleAutoClear();
      }),
    );

    _unsubs.push(
      onBusEvent('audit.probe_failure', (env) => {
        if (!env || env.probe_id !== pid) return;
        local = { ...(local || { probe_id: pid }), status: 'failed', failure_reason: env.reason || 'unknown' };
      }),
    );
  }

  function teardownSelf() {
    for (const u of _unsubs) {
      try {
        u();
      } catch {
        /* noop */
      }
    }
    _unsubs = [];
  }

  // When subscribing, (re)bind whenever the target probe_id changes. The
  // initial pending state can also be seeded by the parent via `canary`.
  $: if (subscribe) {
    const pid = (canary && canary.probe_id) || '';
    if (canary && !local) local = { ...canary };
    bindSelf(pid);
  }

  // ---- Auto-clear (M12: observed -> clear after 1.5s). ----------------------
  // Works for BOTH the self-subscribed and parent-driven paths: whenever we
  // observe a transition into 'observed', schedule the 1.5s clear dispatch.
  let _observedHandled = false;
  $: if (status === 'observed' && !_observedHandled) {
    _observedHandled = true;
    scheduleAutoClear();
  }
  $: if (status !== 'observed') {
    _observedHandled = false;
  }

  function scheduleAutoClear() {
    if (_clearTimer) clearTimeout(_clearTimer);
    _clearTimer = setTimeout(() => {
      _clearTimer = null;
      dispatch('clear', { probeId });
    }, 1500);
  }

  onDestroy(() => {
    teardownSelf();
    if (_clearTimer) clearTimeout(_clearTimer);
  });

  // ---- Operator-initiated triggers (M12). -----------------------------------
  let busy = false;
  let actionError = '';

  /**
   * Emit a fresh canary echo for this probe / session. The server answers on
   * the bus (audit.canary_emit) which the state machine above consumes.
   */
  async function emitCanary() {
    actionError = '';
    busy = true;
    try {
      await postCanaryEmit({ probe_id: probeId, jsonl_path: jsonlPath });
      // The pending state will arrive over SSE; do not fabricate it locally.
      dispatch('emitted', { probeId });
    } catch (e) {
      actionError = `Canary emit failed: ${e && e.message ? e.message : 'unknown error'}`;
    } finally {
      busy = false;
    }
  }

  /**
   * Register a decoy stream (negative control): a stream the parser must NEVER
   * report activity on. If it does, Layer-3 fires audit.hallucination_detected.
   */
  async function registerDecoy() {
    actionError = '';
    busy = true;
    try {
      await postDecoyRegister({ probe_id: probeId });
      dispatch('decoy-registered', { probeId });
    } catch (e) {
      actionError = `Decoy register failed: ${e && e.message ? e.message : 'unknown error'}`;
    } finally {
      busy = false;
    }
  }

  function dismiss() {
    dispatch('clear', { probeId });
  }

  // Accessible live-region sentence per state (M17), data-derived (M16).
  $: liveSentence =
    status === 'observed'
      ? 'Canary echo confirmed -- session binding proven both ways.'
      : status === 'failed'
        ? `Canary echo failed -- ${failureReason}.`
        : nonce
          ? 'Canary echo pending -- type the nonce into your active session.'
          : 'Canary echo armed.';
</script>

<article
  class="canary"
  class:is-observed={status === 'observed'}
  class:is-failed={status === 'failed'}
  data-probe-id={probeId}
  data-status={status}
  aria-label="Canary echo"
>
  <span class="canary__rail" aria-hidden="true"></span>

  <div class="canary__body">
    <!-- aria-live region: announces each state transition without stealing
         focus (calm tech). polite, not assertive -- this is not an alarm. -->
    <p class="canary__live" aria-live="polite">{liveSentence}</p>

    <header class="canary__head">
      {#if status === 'pending'}
        <!-- Paired label: text first, the dot/hue are reinforcement (M4). -->
        <span class="canary__kind sev-notice">
          <span class="canary__dot" aria-hidden="true"></span>
          CANARY ECHO
        </span>
        <span class="canary__sub">proof-of-binding</span>
      {:else if status === 'observed'}
        <span class="canary__kind canary__kind--ok sev-base">
          <span class="canary__dot" aria-hidden="true"></span>
          CANARY ECHO &middot; CONFIRMED
        </span>
        <span class="canary__sub">binding proven both ways</span>
      {:else}
        <span class="canary__kind canary__kind--bad sev-notice">
          <span class="canary__dot" aria-hidden="true"></span>
          CANARY ECHO &middot; FAILED
        </span>
        <span class="canary__sub">binding suspect</span>
      {/if}
    </header>

    {#if status === 'pending'}
      <p class="canary__prompt">
        Type this string into your active Claude CLI session within {timeoutS}s:
      </p>

      <!-- The nonce is the hero: large, monospaced, selectable, generously
           tracked for trivial copy-typing. Region-labelled for a11y. -->
      <div
        class="canary__nonce-wrap"
        role="group"
        aria-label="Canary nonce to type"
      >
        <code class="canary__nonce">{nonce || '--'}</code>
      </div>

      <!-- M12 countdown via the shared M9 primitive. startedAt resumes the
           clock across re-renders (mirrors HITL.startedAt). -->
      <CountdownBar
        seconds={timeoutS}
        startedAt={issuedAtMs}
        showReadout={true}
        dim={false}
        label="Canary echo countdown"
      />
    {:else if status === 'observed'}
      <p class="canary__prompt">Binding proven both ways. Clearing...</p>
      {#if nonce}
        <div class="canary__nonce-wrap canary__nonce-wrap--ok">
          <code class="canary__nonce">{nonce}</code>
        </div>
      {/if}
    {:else}
      <!-- Failure: the REASON as real prose (M12). WARN register, paired text. -->
      <p class="canary__prompt">
        Binding suspect ({failureReason || 'unknown'}). Re-pick your stream when re-prompted.
      </p>
    {/if}

    {#if actionError}
      <p class="canary__error" role="alert">{actionError}</p>
    {/if}

    <div class="canary__actions">
      <button
        type="button"
        class="canary__btn"
        on:click={emitCanary}
        disabled={busy || !probeId}
        aria-label="Emit a fresh canary echo for this session"
      >
        {status === 'failed' ? 'Re-emit canary' : 'Emit canary'}
      </button>

      <button
        type="button"
        class="canary__btn canary__btn--ghost"
        on:click={registerDecoy}
        disabled={busy || !probeId}
        aria-label="Register a decoy stream (negative control)"
      >
        Register decoy
      </button>

      <button
        type="button"
        class="canary__btn canary__btn--ghost"
        on:click={dismiss}
        aria-label="Dismiss this canary echo from the panel"
      >
        Dismiss
      </button>
    </div>
  </div>
</article>

<style>
  .canary {
    position: relative;
    display: flex;
    align-items: stretch;
    gap: 0;
    background: var(--calm-surface-raised, #0c1118);
    border: var(--hairline, 1px) solid var(--calm-hairline, #192030);
    border-radius: var(--radius-soft, 4px);
    overflow: hidden;
    transition: border-color var(--t-calm, 180ms ease), background var(--t-flash, 300ms ease);
  }

  .canary__rail {
    flex: 0 0 3px;
    background: var(--calm-accent-wash, rgba(245, 158, 11, 0.09));
    align-self: stretch;
  }

  /* observed -> calm DECIDED green confirmation flash (the 1.5s window). */
  .canary.is-observed {
    border-color: var(--badge-decided-border, #86efac);
    background: color-mix(in srgb, var(--badge-decided-bg, #dcfce7) 14%, var(--calm-surface-raised, #0c1118));
  }
  .canary.is-observed .canary__rail {
    background: var(--badge-decided-fg, #16a34a);
  }

  /* failed -> WARN register. Reason carried as prose (M4 paired). */
  .canary.is-failed {
    border-color: var(--badge-warn-border, #ea580c);
  }
  .canary.is-failed .canary__rail {
    background: var(--badge-warn-fg, #ea580c);
  }

  .canary__body {
    flex: 1 1 auto;
    min-width: 0;
    padding: var(--space-4, 10px) var(--space-5, 14px);
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 6px);
  }

  /* aria-live sentence -- visually hidden but reachable by assistive tech, so
     the announcement does not add chrome to the calm surface (M17). */
  .canary__live {
    position: absolute;
    width: 1px;
    height: 1px;
    margin: -1px;
    padding: 0;
    overflow: hidden;
    clip: rect(0 0 0 0);
    clip-path: inset(50%);
    white-space: nowrap;
    border: 0;
  }

  .canary__head {
    display: flex;
    align-items: baseline;
    gap: var(--space-3, 6px);
    flex-wrap: wrap;
  }

  .canary__kind {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: var(--ff-system);
    font-size: var(--fs-chrome, 11px);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--calm-ink-loud, #e8e0cc);
  }
  .canary__kind--ok {
    color: var(--badge-decided-fg, #16a34a);
  }
  .canary__kind--bad {
    color: var(--badge-warn-fg, #ea580c);
  }

  .canary__dot {
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    flex: 0 0 auto;
  }

  .canary__sub {
    font-family: var(--ff-system);
    font-size: var(--fs-chrome, 11px);
    letter-spacing: 0.04em;
    color: var(--calm-ink-quiet, #948870);
  }

  .canary__prompt {
    margin: 0;
    font-family: var(--ff-system);
    font-size: var(--fs-meta, 13px);
    line-height: var(--lh-body, 1.5);
    color: var(--calm-ink, #b8b098);
  }

  /* The nonce -- the hero of the row. Large monospaced, tracked, selectable,
     framed by a quiet accent-wash chip so it reads as "type this exact text". */
  .canary__nonce-wrap {
    display: inline-flex;
    align-self: flex-start;
    max-width: 100%;
    padding: var(--space-3, 6px) var(--space-5, 14px);
    background: var(--calm-accent-wash, rgba(245, 158, 11, 0.09));
    border: 1px dashed var(--calm-accent, #f59e0b);
    border-radius: var(--radius-sharp, 2px);
  }
  .canary__nonce-wrap--ok {
    background: var(--badge-decided-bg, #dcfce7);
    border-style: solid;
    border-color: var(--badge-decided-border, #86efac);
  }

  .canary__nonce {
    font-family: var(--ff-mono);
    font-size: 18px;
    font-weight: 600;
    letter-spacing: 0.16em;
    color: var(--calm-ink-loud, #e8e0cc);
    user-select: all; /* one click selects the whole nonce for copy-typing */
    overflow-wrap: anywhere;
    word-break: break-all;
  }
  .canary__nonce-wrap--ok .canary__nonce {
    color: var(--badge-decided-fg, #16a34a);
  }

  .canary__error {
    margin: 0;
    padding: var(--space-2, 4px) var(--space-3, 6px);
    font-family: var(--ff-system);
    font-size: var(--fs-meta, 13px);
    font-weight: 600;
    color: var(--badge-warn-fg, #ea580c);
    background: var(--badge-warn-bg, #ffedd5);
    border-left: 2px solid var(--badge-warn-border, #ea580c);
    border-radius: var(--radius-sharp, 2px);
  }

  .canary__actions {
    display: flex;
    gap: var(--space-3, 6px);
    margin-top: var(--space-2, 4px);
    flex-wrap: wrap;
  }

  .canary__btn {
    appearance: none;
    font-family: var(--ff-system);
    font-size: var(--fs-meta, 13px);
    font-weight: 600;
    line-height: 1;
    padding: 6px 12px;
    border-radius: var(--radius-sharp, 2px);
    cursor: pointer;
    color: var(--calm-accent, #f59e0b);
    background: var(--calm-accent-wash, rgba(245, 158, 11, 0.09));
    border: 1px solid var(--calm-accent, #f59e0b);
    transition: background var(--t-calm, 180ms ease), color var(--t-calm, 180ms ease),
      border-color var(--t-calm, 180ms ease);
  }
  .canary__btn:hover:not(:disabled) {
    background: var(--calm-accent, #f59e0b);
    color: var(--calm-surface, #080a0c);
  }
  .canary__btn--ghost {
    color: var(--calm-ink-chrome, #8a8068);
    background: transparent;
    border-color: var(--calm-hairline-hi, rgba(245, 158, 11, 0.25));
  }
  .canary__btn--ghost:hover:not(:disabled) {
    color: var(--calm-ink-loud, #e8e0cc);
    border-color: var(--calm-accent, #f59e0b);
    background: transparent;
  }
  .canary__btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  /* M17: restate the focus ring locally (focus.css also enforces globally). */
  .canary__btn:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid)
      var(--focus-ring-color, #d97706);
    outline-offset: var(--focus-ring-offset, 2px);
  }
</style>
