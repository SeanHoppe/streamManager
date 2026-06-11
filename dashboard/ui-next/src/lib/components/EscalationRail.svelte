<!--
  EscalationRail.svelte -- the lone source of motion + saturated color, and the
  structural home of M2 escalation discipline in the running UI.

  THESIS (calm-ambient spine): the monitor is still water. At rest this rail is
  a single hairline at the top of the shell -- no motion, no saturation, no
  layout it can steal. It expands into the amber AmberActionCard hero ONLY when
  a live signal is foreground-eligible per the escalation.js M2 allow-list. That
  is the whole point: awe is rationed to the one signal that earned it.

  MUSTs this component owns / enforces:

    M2  Escalation-only foreground. The rail foregrounds (expands + animates)
        ONLY for the three foreground-eligible triggers --
            desktop_pause / governance_negative_regression / static-rule
        -- read from the SINGLE auditable escalation.js allow-list table via
        isForegroundEligible(). Every other signal (new_pattern /
        low_confidence / governance_variance_alert / unknown) is dropped here
        and flagged-in-place by OTHER frames' badges; it NEVER expands this rail
        and NEVER moves the layout. M2 is therefore one table + one function
        call, not scattered conditionals -- trivially S2-auditable.

    M3  This component is the SSE-driven source of the live open-ACTION-REQUIRED
        counts. It maintains a per-frame count store and a derived total, both
        exported from <script context="module"> so the co-owned TabTitle.svelte
        (M3 browser-tab half) consumes the SAME source of truth. Frame headers
        (u-shell) read the same per-frame store.

    M4  The expanded hero is rendered by AmberActionCard with the paired
        label+color ACTION REQUIRED treatment (amber #d97706 on #fef3c7, pulsing
        border, aria-label = trigger reason). Color is never the sole signal.

    M15 Self-exclude (POLARITY G2). Every inbound SSE event is run through the
        selfExclude predicate before it can escalate or bump a count, so the
        SM's own session can NEVER appear as a governed escalation. Loud-fail-
        safe: an empty/missing meta disables filtering (never silently hides).

    M16 Domain-agnostic. No monitored-project vocabulary. The governed-target
        identity shown in the hero is rendered FROM the event's session data,
        never from a literal here.

    M18 Post-hoc observability. The rail consumes the /events SSE stream that
        already exists; it performs NO verdict-path work and adds nothing to the
        hot path. SSE is a 3s fixed-reconnect read transport.

  SSE CONTRACT (preserved from dashboard/static/index.html):
    /events is a default-message EventSource. Each `message` carries a JSON
    payload; `event_type` present => a named bus event, absent => a decision
    row. Foreground-eligible bus events raise the ACTION REQUIRED count + the
    hero. The named SSE events (audit.*, hitl_*, governance_*) are consumed by
    OTHER units; this rail only reacts to the escalation allow-list, so it
    listens to the default `message` channel + the named events whose type is
    foreground-eligible. Reconnect is a fixed 3s (matches the live contract).

  FILE-DISJOINT: this component owns the EventSource. No other unit opens
  /events for escalation; the module-context stores below are the single shared
  surface, imported (not duplicated) by TabTitle.svelte.
-->
<script context="module">
  import { writable, derived } from 'svelte/store';
  import { FRAME_KEYS } from '../stores/layout.js';

  /**
   * Per-frame live open-ACTION-REQUIRED counts (M3). Frame A carries the
   * escalation-driven actions (Interactive Sessions is the foreground target
   * in the live contract); B/C are exported at zero here and are bumped by
   * their own units when those frames raise actions. Keeping the full {A,B,C}
   * shape means the derived total below already sums every frame, so TabTitle
   * and frame headers read ONE source of truth.
   *
   * @type {import('svelte/store').Writable<{A:number,B:number,C:number}>}
   */
  export const frameActionCounts = writable({ A: 0, B: 0, C: 0 });

  /**
   * The total open ACTION REQUIRED across all frames (M3). TabTitle.svelte
   * subscribes to THIS so the tab title and the frame headers can never drift.
   * @type {import('svelte/store').Readable<number>}
   */
  export const tabActionTotal = derived(frameActionCounts, ($c) =>
    FRAME_KEYS.reduce((sum, k) => sum + (Number($c[k]) || 0), 0),
  );

  /**
   * The single foreground escalation descriptor currently promoted to the hero,
   * or null when the monitor is at rest (still water). At most ONE hero is shown
   * -- the highest-severity live escalation -- so the lone amber surface truly
   * stands alone (M2/M4).
   * @type {import('svelte/store').Writable<null | {
   *   type:string, reason:string, severity:number, foreground:boolean,
   *   sessionId:string, sessionLabel:string, at:number
   * }>}
   */
  export const foregroundEscalation = writable(null);

  /**
   * Test/validator seam: set the per-frame counts directly (the S2 render-
   * validator and unit tests drive the M3 path without a live SSE). Clamps to
   * >= 0 so a count can never go negative.
   * @param {'A'|'B'|'C'} frameKey
   * @param {number} n
   */
  export function setFrameActionCount(frameKey, n) {
    if (!FRAME_KEYS.includes(frameKey)) return;
    const v = Math.max(0, Math.floor(Number(n) || 0));
    frameActionCounts.update((c) => (c[frameKey] === v ? c : { ...c, [frameKey]: v }));
  }

  /** Reset all escalation state (used on teardown / tests). */
  export function resetEscalationState() {
    frameActionCounts.set({ A: 0, B: 0, C: 0 });
    foregroundEscalation.set(null);
  }
</script>

<script>
  import { onMount, onDestroy } from 'svelte';
  import { describe, isForegroundEligible } from '../escalation.js';
  import { createSelfExcluder } from '../selfExclude.js';
  import AmberActionCard from './AmberActionCard.svelte';

  /**
   * eventsUrl: the SSE endpoint. Defaults to the preserved /events transport.
   * Overridable for tests / a non-default mount; never points at
   * /api/commands/stream (the consumer-only transport -- see M18).
   */
  export let eventsUrl = '/events';

  /**
   * autoConnect: open the EventSource on mount. Tests mount with false and
   * drive ingest() directly so no live socket is required.
   */
  export let autoConnect = true;

  /**
   * reconnectMs: fixed reconnect delay. Matches the live dashboard's 3s fixed
   * reconnect contract. The browser's own EventSource reconnect is the primary
   * path; this guards the explicit-error / closed case.
   */
  export let reconnectMs = 3000;

  // M15 self-exclude predicate, resolved once at mount from the injected meta.
  // Empty/missing meta => keepAll (loud-fail-safe). Defense-in-depth: the
  // server already strips self rows; this is the redundant client layer.
  let selfExcluder = createSelfExcluder();

  /** @type {EventSource | null} */
  let es = null;
  /** @type {ReturnType<typeof setTimeout> | null} */
  let reconnectTimer = null;
  let destroyed = false;

  // The named SSE bus events whose type can be foreground-eligible. We listen on
  // BOTH the default `message` channel (decision rows + generic bus events) and
  // these named channels so a foreground trigger emitted as a named event is
  // never missed. Membership here does NOT grant foreground -- escalation.js
  // does; this is only the set of channels we bother to subscribe to.
  const NAMED_ESCALATION_CHANNELS = [
    'governance_negative_regression',
    'desktop_pause',
    'static-rule',
    'static_rule',
  ];

  /**
   * Resolve a human session label from event data WITHOUT hard-coding any
   * monitored-project vocabulary (M16). Preference order is data-driven:
   * project_slug (operator-meaningful) -> a short session_id tail -> ''.
   * @param {Record<string, any>} d
   * @returns {string}
   */
  function sessionLabelFrom(d) {
    if (!d || typeof d !== 'object') return '';
    if (typeof d.project_slug === 'string' && d.project_slug.trim()) {
      return d.project_slug.trim();
    }
    const sid = typeof d.session_id === 'string' ? d.session_id.trim() : '';
    if (!sid) return '';
    // Short, stable tail so concurrent sessions stay glance-distinguishable
    // without leaking a full opaque id into the calm surface.
    return sid.length > 8 ? `...${sid.slice(-8)}` : sid;
  }

  /**
   * Ingest one parsed SSE payload. THE M2 gate lives here, expressed as the
   * single escalation.js call. Exported-by-binding for tests via the module
   * seam is not needed -- tests can mount with autoConnect=false and call this
   * through a bound ref; for the S2 validator the module-context stores above
   * are the assertion surface.
   *
   * @param {Record<string, any>} d a parsed /events payload (decision or bus).
   */
  function ingest(d) {
    if (!d || typeof d !== 'object') return;
    if (d.error) return;

    // M15: drop the SM's own session before it can escalate or bump a count.
    // Unattributed rows (no session_id) are KEPT by the predicate -- they are
    // never assumed to be self -- so a malformed event still escalates safely.
    if (!selfExcluder.filter(d)) return;

    // M2: the ONLY foreground decision. Reads the single escalation.js allow-
    // list table. Non-foreground signals (new_pattern / low_confidence /
    // governance_variance_alert / unknown / decision rows) are dropped HERE --
    // they flag-in-place via other frames' badges and never touch this rail.
    if (!isForegroundEligible(d)) return;

    const desc = describe(d);
    if (!desc || !desc.foreground) return; // belt-and-suspenders on M2

    const sessionId = typeof d.session_id === 'string' ? d.session_id : '';
    const next = {
      type: desc.type,
      reason: desc.reason,
      severity: desc.severity,
      foreground: true,
      sessionId,
      sessionLabel: sessionLabelFrom(d),
      at: Date.now(),
    };

    // Promote to the hero: keep the most-severe live escalation; ties go to the
    // newest (most recent operator-relevant). At most ONE hero at a time so the
    // lone amber surface stands alone (M2/M4).
    foregroundEscalation.update((cur) => {
      if (cur && cur.severity > next.severity) return cur;
      return next;
    });

    // M3: raise the open ACTION REQUIRED count on Frame A (the live contract's
    // foreground target). The count is the SSE-driven source TabTitle sums.
    frameActionCounts.update((c) => ({ ...c, A: c.A + 1 }));
  }

  // Expose ingest on the instance for the S2 validator / unit tests that mount
  // with autoConnect=false and feed synthetic events. (Bind via `bind:this`.)
  export function __ingestForTest(d) {
    ingest(d);
  }

  function handleRaw(eventData) {
    let d;
    try {
      d = JSON.parse(eventData);
    } catch (_e) {
      return; // malformed frame -- never throw in the hot SSE handler
    }
    ingest(d);
  }

  function connect() {
    if (destroyed || typeof EventSource === 'undefined') return;
    teardownSocket();
    try {
      es = new EventSource(eventsUrl);
    } catch (_e) {
      scheduleReconnect();
      return;
    }
    // Default channel: decision rows + generic bus events (incl. some
    // foreground triggers emitted without a named event).
    es.onmessage = (e) => handleRaw(e.data);
    // Named channels that may carry a foreground trigger.
    for (const ch of NAMED_ESCALATION_CHANNELS) {
      es.addEventListener(ch, (e) => handleRaw(e.data));
    }
    es.onerror = () => {
      // EventSource auto-reconnects, but if the socket is CLOSED we re-open on
      // the fixed 3s cadence to match the live contract.
      if (es && es.readyState === EventSource.CLOSED) {
        scheduleReconnect();
      }
    };
  }

  function scheduleReconnect() {
    teardownSocket();
    if (destroyed || reconnectTimer != null) return;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, reconnectMs);
  }

  function teardownSocket() {
    if (es) {
      try {
        es.close();
      } catch (_e) {
        /* already closed */
      }
      es = null;
    }
  }

  // --- hero subscription (the only reactive read this component renders) ---
  let hero = null;
  const unsub = foregroundEscalation.subscribe((v) => {
    hero = v;
  });

  function onHeroDismiss() {
    // Acknowledge + clear the hero, and release its Frame A action count so the
    // tab title / header settle back to still water. Underlying governance
    // state is untouched (observability only, M18).
    foregroundEscalation.set(null);
    frameActionCounts.update((c) => ({ ...c, A: Math.max(0, c.A - 1) }));
  }

  function onHeroFocus(e) {
    // Re-emit as a DOM CustomEvent so the shell (u-shell) can scope panes to the
    // escalation's session without this leaf importing the session store
    // (file-disjoint). Carries session_id only -- domain-agnostic (M16).
    if (typeof window !== 'undefined' && typeof CustomEvent !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('sm:focus-session', { detail: { sessionId: e.detail.sessionId } }),
      );
    }
  }

  onMount(() => {
    // Re-resolve the self-excluder at DOM-ready: the meta is injected by the
    // server into <head>, guaranteed present by the time the component mounts.
    selfExcluder = createSelfExcluder();
    if (autoConnect) connect();
  });

  onDestroy(() => {
    destroyed = true;
    if (reconnectTimer != null) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    teardownSocket();
    unsub();
  });
</script>

<!--
  RESTING STATE = a single hairline lane. No motion, no saturation, no layout it
  can steal (still water). data-foreground reflects the M2 state for the S2
  validator: "false" at rest, "true" only when a foreground-eligible escalation
  is live. aria-live=polite so the calm transition into the hero is announced
  without interrupting the operator mid-task; the hero itself (role=alert) is
  assertive.
-->
<section
  class="erail"
  class:erail--active={hero !== null}
  data-foreground={hero !== null ? 'true' : 'false'}
  data-escalation-type={hero ? hero.type : ''}
  aria-live="polite"
  aria-label="Escalation rail"
>
  {#if hero}
    <AmberActionCard
      descriptor={{ type: hero.type, reason: hero.reason, severity: hero.severity, foreground: true }}
      sessionId={hero.sessionId}
      sessionLabel={hero.sessionLabel}
      on:dismiss={onHeroDismiss}
      on:focus={onHeroFocus}
    />
  {:else}
    <!-- The hairline: a 1px calm tide line. Purely decorative at rest; it holds
         the rail's place in the shell so promotion does not shift the layout. -->
    <span class="erail__hairline" aria-hidden="true"></span>
  {/if}
</section>

<style>
  .erail {
    /* The rail reserves a stable slot so expansion never reflows siblings
       below it abruptly (M18: cheap, no layout thrash). At rest it collapses to
       a hairline's height; active it grows to fit the hero. */
    display: block;
    width: 100%;
    /* calm transition on the container box only -- color/size easing, never an
       attention-grabbing keyframe. The keyframe pulse lives on the hero. */
    transition: padding var(--t-calm, 180ms ease);
    padding: 0;
  }

  .erail--active {
    padding: var(--space-3, 6px) 0;
  }

  /* RESTING hairline: whisper-quiet, slate-calm. No accent, no motion. The lone
     saturated element only ever appears when the hero is live. */
  .erail__hairline {
    display: block;
    width: 100%;
    height: 1px;
    background: var(--calm-hairline, var(--border, rgba(148, 163, 184, 0.18)));
  }

  /* Honor the OS reduced-motion preference for the container easing unless the
     operator force-allows. (The hero's pulse handles its own reduced-motion.) */
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .erail {
      transition: none;
    }
  }
  :global(html[data-motion='reduce']) .erail {
    transition: none !important;
  }
</style>
