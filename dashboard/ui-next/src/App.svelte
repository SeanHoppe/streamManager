<script>
  // App.svelte -- the composition root for the still-water shell (u-compose).
  //
  // App wires the scaffold (AppShell + Frames) to the real feature panes and
  // boots the read-only data transports. It owns the composition seam and the
  // app-lifetime bootstrap; every pane below is file-disjoint and self-wires to
  // the shared stores, so App only has to (a) mount the right component in each
  // AppShell named slot and (b) start the transports that feed those stores.
  //
  //   Frame A  -> FrameA_Sessions (live decision stream) + HitlDock in its
  //               `pending` slot (live /api/hitl/pending + bus).
  //   Frame B  -> AgentRoster bound to the 8s /api/agents poller store.
  //   Frame C  -> FrameC_Jobs (live 2s /api/lifecycle/jobs via LifecyclePanel).
  //   header   -> SessionPicker (writes selectedSessionId -> scopes every pane).
  //   footer   -> live connection dot + decision tally.
  //
  // Governance invariants App preserves at the seam:
  //   - M1: all three frames render (AppShell guarantees presence regardless of
  //     store state -- an empty store yields a calm "still water" frame, never a
  //     missing one).
  //   - M2: App invents NO escalation policy. The only foreground it drives is
  //     Frame A `escalated`, fed STRICTLY from sse.js's escalationStore, which is
  //     produced solely from the lib/escalation.js allow-list. App reads that
  //     stream; it never classifies a trigger itself.
  //   - M3: App threads each frame's live open-ACTION-REQUIRED count (Frame A
  //     from HitlDock, Frame C from FrameC_Jobs) into AppShell, which owns the
  //     header pills + debounced browser-tab total.
  //   - M15: it reads <meta name="sm-own-session-id"> at DOM-ready; the stores
  //     default-exclude SM self. Empty/missing meta => no filtering.
  //   - M16: no monitored-project vocabulary; governed-target identity is
  //     data-rendered by children, never hard-coded here.
  //   - M18: the transports App starts are post-hoc observability only (SSE feed
  //     + REST pollers). App never opens /api/commands/stream and never sits on
  //     the verdict hot path.

  import { onMount, onDestroy } from 'svelte';

  import AppShell from './lib/components/AppShell.svelte';
  import SessionPicker from './lib/components/SessionPicker.svelte';
  import SessionRail from './lib/components/SessionRail.svelte';
  import FrameA_Sessions from './lib/components/FrameA_Sessions.svelte';
  import AgentRoster from './lib/components/AgentRoster.svelte';
  import FrameC_Jobs from './lib/components/FrameC_Jobs.svelte';
  import HitlDock from './lib/components/HitlDock.svelte';

  import { connect, disconnect, seedDecisions, connectionState, escalationStore } from './lib/sse.js';
  import { startPollers, stopPollers, agentsStore, statsStore } from './lib/pollers.js';
  import { getSessions, getDecisions, getHitlPending } from './lib/api.js';
  import {
    setSessions,
    defaultToMostRecent,
    selectedSessionId,
  } from './lib/stores/session.js';
  import { settings, patch as patchSettings } from './lib/stores/settings.js';

  // -- M15 self-exclude (defense-in-depth) -----------------------------------
  // Read the SM-own session id once at DOM-ready. The stores already filter SM
  // self structurally; this is the redundant client layer. Empty/missing meta
  // => skip filtering (documented contract). The polarity rule (CLAUDE.md): SM
  // monitors NON-SM sessions, never itself.
  let ownSessionId = '';
  function readOwnSession() {
    if (typeof document === 'undefined') return '';
    const meta = document.querySelector('meta[name="sm-own-session-id"]');
    const v = meta && meta.getAttribute('content');
    return v ? v.trim() : '';
  }

  // -- FR-UI-9 reduced-motion override ---------------------------------------
  // The settings unit owns the real toggle (writes <html data-motion>); App
  // reflects the resolved value so AppShell can gate its ambient motion. We
  // honour reduced-motion UNLESS the operator force-allows it.
  let reducedMotionOverride = false;
  function syncReducedMotion() {
    if (typeof document === 'undefined') return;
    const forceAllow = document.documentElement.getAttribute('data-motion') === 'allow';
    const osReduce = typeof matchMedia === 'function'
      && matchMedia('(prefers-reduced-motion: reduce)').matches;
    reducedMotionOverride = osReduce && !forceAllow;
  }

  // -- HITL mode -> Frame A read-only vs editable (M5/M7) --------------------
  // 'sync' == HITL ON (editable holding gate); 'async' == read-only + opt-in.
  $: hitlOn = $settings.hitlMode === 'sync';

  // -- live clock (1s) for Frame B active-in-window re-partition (M13) -------
  let nowMs = Date.now();

  // -- per-frame M3 counts (threaded into AppShell) --------------------------
  // Frame A count = HitlDock's open-ACTION-REQUIRED tally (editable/promoted
  // rows). Frame C count = FrameC_Jobs's undecided async-HITL tally. Frame B is
  // observational (agents are not actioned in this surface) -> always 0.
  let frameACount = 0;
  let frameCCount = 0;
  function onFrameActionCount(e) {
    const d = e.detail || {};
    if (d.frame === 'A') frameACount = Number(d.count) || 0;
    else if (d.frame === 'C') frameCCount = Number(d.count) || 0;
  }

  // -- M2 foreground (Frame A escalation), fed ONLY by the escalation stream --
  // sse.js produces escalationStore strictly from the lib/escalation.js
  // allow-list (desktop_pause / governance_negative_regression / static-rule).
  // App reads the most recent escalation and foregrounds Frame A for a bounded
  // window; it classifies NOTHING itself (M2 single source of truth). The
  // window auto-clears so a one-shot escalation does not pin the frame forever.
  const ESC_WINDOW_MS = 20000;
  $: latestEsc = $escalationStore.length ? $escalationStore[$escalationStore.length - 1] : null;
  $: aEscalated = !!(latestEsc && nowMs - latestEsc.ts < ESC_WINDOW_MS);
  $: aFlagLabel = aEscalated ? (latestEsc.rule?.label || 'ESCALATION') : '';

  // The per-frame view-state AppShell consumes. Presence-preserving defaults
  // (every key present, calm) keep the shell contract-correct even before any
  // store populates -- M1.
  $: frames = {
    A: { count: frameACount, flagged: false, flagLabel: aFlagLabel, escalated: aEscalated },
    B: { count: 0, flagged: false, flagLabel: '', escalated: false },
    C: { count: frameCCount, flagged: false, flagLabel: '', escalated: false },
  };

  // -- SessionRail feed (left command-column) --------------------------------
  // The rail self-wires its session lanes + selection from the session store;
  // App supplies only the two per-session SIGNAL maps it derives from the same
  // read-only transports the frames use. Both are keyed by session_id.
  //
  //   escalations  -- the lone M2 foreground per lane, derived STRICTLY from the
  //                   sse.js escalationStore (the lib/escalation.js allow-list).
  //                   App classifies nothing; it only re-keys the open
  //                   escalations by session within the same 20s window the
  //                   Frame A foreground uses. Most-recent rule per session wins.
  //   actionCounts -- per-session open HITL tally, from an UNSCOPED /api/hitl/
  //                   pending poll grouped by session_id (M18 post-hoc GET). The
  //                   scoped dock in Frame A is the actionable surface; this is
  //                   the glance count across ALL lanes.
  $: escBySession = (() => {
    const map = {};
    for (const e of $escalationStore) {
      if (!e || e.sessionId == null) continue;
      if (nowMs - e.ts >= ESC_WINDOW_MS) continue; // only still-open escalations
      // append order => later entries overwrite => most-recent rule per session.
      map[e.sessionId] = { reason: (e.rule && e.rule.label) || 'Escalation' };
    }
    return map;
  })();

  let actionCountsBySession = {};
  const PENDING_REFRESH_MS = 4000;
  async function refreshPendingCounts() {
    try {
      const rows = await getHitlPending({}); // UNSCOPED: counts across all lanes
      const counts = {};
      for (const r of Array.isArray(rows) ? rows : []) {
        const sid = r && r.session_id;
        if (sid == null) continue;
        if (ownSessionId && sid === ownSessionId) continue; // M15 defense-in-depth
        counts[sid] = (counts[sid] || 0) + 1;
      }
      actionCountsBySession = counts;
    } catch {
      // Calm degrade: the rail keeps its prior tallies; monitoring continues.
    }
  }

  // -- footer connection readout (from the shared SSE connection state) -------
  $: connLabel =
    $connectionState === 'open'
      ? 'live'
      : $connectionState === 'reconnecting'
        ? 'reconnecting'
        : 'connecting';
  $: totalDecisions = Number($statsStore?.total_decisions) || 0;
  $: activeSessions = Number($statsStore?.active_sessions) || 0;

  // -- M7: a Take-action opt-in from a read-only decision row promotes the
  // session to HITL ON SYNC. App flips the shared settings mode; the dock reacts
  // (its rows re-render editable). App holds no HITL state of its own.
  function onTakeAction() {
    if ($settings.hitlMode !== 'sync') patchSettings({ hitlMode: 'sync' });
  }

  // -- /api/sessions refresh loop (the SessionPicker / scope source) ----------
  // pollers.js owns stats/agents/lifecycle; sessions are seeded here and kept
  // fresh on a calm 5s cadence so the picker reflects new governed sessions.
  // Read-only, post-hoc (M18).
  const SESSIONS_REFRESH_MS = 5000;
  let _firstSessionsLoad = true;
  async function refreshSessions() {
    try {
      const rows = await getSessions({ limit: 20 });
      setSessions(rows);
      if (_firstSessionsLoad) {
        _firstSessionsLoad = false;
        // Honour the "default most-recent" rule once, without clobbering a
        // returning operator's persisted pick.
        defaultToMostRecent();
      }
    } catch {
      // The picker degrades to whatever it has; monitoring continues.
    }
  }

  // -- seed the decision feed before SSE warms (M18: one GET) ----------------
  async function seedDecisionFeed() {
    try {
      const rows = await getDecisions({ limit: 200 });
      seedDecisions(rows);
    } catch {
      // Live rows still arrive over the stream; the seed is best-effort.
    }
  }

  /** @type {ReturnType<typeof setInterval>|null} */
  let _clockTimer = null;
  /** @type {ReturnType<typeof setInterval>|null} */
  let _sessionsTimer = null;
  /** @type {ReturnType<typeof setInterval>|null} */
  let _pendingTimer = null;

  onMount(() => {
    ownSessionId = readOwnSession();
    syncReducedMotion();

    // Boot the read-only transports (M18 post-hoc): one SSE connection + the
    // REST poller registry. Both write the shared stores the panes subscribe to.
    seedDecisionFeed();
    connect();
    startPollers();

    // Seed + refresh the governed-session list (picker scope source).
    refreshSessions();
    _sessionsTimer = setInterval(refreshSessions, SESSIONS_REFRESH_MS);

    // Seed + refresh the per-session HITL-pending tallies that warm the rail
    // lanes (unscoped GET; post-hoc M18). Calm cadence -- glance data, not a
    // hot-path signal.
    refreshPendingCounts();
    _pendingTimer = setInterval(refreshPendingCounts, PENDING_REFRESH_MS);

    // One shared 1s clock for the Frame B active/idle re-partition + the M2
    // escalation-window expiry. Single timer -> no per-row clocks.
    _clockTimer = setInterval(() => { nowMs = Date.now(); }, 1000);

    // React to OS preference + the settings-unit data-motion attribute.
    let mq;
    if (typeof matchMedia === 'function') {
      mq = matchMedia('(prefers-reduced-motion: reduce)');
      mq.addEventListener?.('change', syncReducedMotion);
    }
    let obs;
    if (typeof MutationObserver !== 'undefined') {
      obs = new MutationObserver(syncReducedMotion);
      obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-motion'] });
    }

    return () => {
      mq?.removeEventListener?.('change', syncReducedMotion);
      obs?.disconnect();
    };
  });

  onDestroy(() => {
    if (_clockTimer) clearInterval(_clockTimer);
    if (_sessionsTimer) clearInterval(_sessionsTimer);
    if (_pendingTimer) clearInterval(_pendingTimer);
    stopPollers();
    disconnect();
  });
</script>

<AppShell
  frames={frames}
  sessionId={$selectedSessionId}
  reducedMotionOverride={reducedMotionOverride}
  productName="StreamManager"
>
  <!-- RAIL: the left command-column. The multi-session glance deck (graft:
       ops-command-deck). It self-wires its lanes + selection from the session
       store; App feeds only the two per-session SIGNAL maps (escalations from
       the M2 allow-list stream, actionCounts from the unscoped HITL-pending
       poll). On narrow viewports AppShell collapses this column and the header
       picker below takes over scope. -->
  <SessionRail
    slot="rail"
    actionCounts={actionCountsBySession}
    escalations={escBySession}
  />

  <!-- HEADER: compact session scope picker. On WIDE viewports the rail is the
       scope control and this is hidden (see .seam--header media query); on
       NARROW viewports the rail collapses and this picker takes over. It is
       always in the DOM so data-own-session keeps carrying M15's self-exclude
       id to non-Svelte consumers / the render-validator regardless of width. -->
  <div slot="header" class="seam seam--header" data-own-session={ownSessionId}>
    <SessionPicker />
  </div>

  <!-- FRAME A: Interactive Sessions / REPL decision stream, with the live HITL
       dock mounted in its `pending` seam (reachable above the ambient stream).
       HitlDock emits its open-action tally up for M3. -->
  <svelte:fragment slot="frameA">
    <FrameA_Sessions {hitlOn} on:takeaction={onTakeAction}>
      <HitlDock slot="pending" on:actioncount={onFrameActionCount} />
    </FrameA_Sessions>
  </svelte:fragment>

  <!-- FRAME B: Sub-Agents roster, bound to the 8s /api/agents poller store +
       the operator activity window. The shared 1s clock drives the active/idle
       re-pin. (AppShell already provides Frame B's shelf -- we mount the body
       only, never a nested Frame.) -->
  <svelte:fragment slot="frameB">
    <AgentRoster
      agents={$agentsStore}
      activityWindowSec={$settings.activityWindowSec}
      {nowMs}
    />
  </svelte:fragment>

  <!-- FRAME C: Background Jobs lifecycle (live 2s poller via LifecyclePanel) +
       the ASYNC HITL host. Emits its undecided async tally up for M3. -->
  <svelte:fragment slot="frameC">
    <FrameC_Jobs on:actioncount={onFrameActionCount} />
  </svelte:fragment>

  <!-- FOOTER: live connection dot + a calm decision/session tally. -->
  <div slot="footer" class="seam seam--footer">
    <span class="conn conn--{$connectionState}" title={`Stream ${connLabel}`}>
      <span class="conn__dot" aria-hidden="true"></span>
      <span class="conn__text">{connLabel}</span>
    </span>
    <span class="foot__stats" aria-label="governance totals">
      {totalDecisions} decisions &middot; {activeSessions} active session{activeSessions === 1 ? '' : 's'}
    </span>
  </div>
</AppShell>

<style>
  /* The composition seam wrappers are quiet -- they only position the slotted
     panes; the panes carry their own still-water chrome. */
  .seam { display: flex; align-items: center; gap: 0.5rem; min-width: 0; }
  .seam--header { width: 100%; }
  .seam--footer { justify-content: flex-start; gap: 0.85rem; }

  /* On WIDE viewports the left rail (AppShell, shown >55rem) is the scope
     control, so the redundant header picker is hidden -- exactly one scope
     control is visible at any width. The wrapper stays in the DOM (display:none
     still queryable) so the data-own-session M15 hook is always present. The
     boundary is 1px above the rail's 55rem collapse so the two never overlap. */
  @media (min-width: 55.0625rem) {
    .seam--header { display: none; }
  }

  /* Footer connection readout: paired dot + literal text (M4 spirit -- color is
     never the sole signal). Calm at rest; green when live, amber reconnecting. */
  .conn {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.68rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--sm-text-dim, #94a3b8);
  }
  .conn__dot {
    width: 0.45rem; height: 0.45rem; border-radius: 50%;
    background: var(--sm-text-dim, #94a3b8);
    flex: 0 0 auto;
  }
  .conn--open .conn__dot { background: var(--c-allow, #22c55e); }
  .conn--reconnecting .conn__dot { background: var(--c-guide, #eab308); }
  .conn--connecting .conn__dot { background: var(--c-guide, #eab308); }

  .foot__stats {
    font-size: 0.68rem;
    color: var(--sm-text-dim, #94a3b8);
    letter-spacing: 0.02em;
  }
</style>
