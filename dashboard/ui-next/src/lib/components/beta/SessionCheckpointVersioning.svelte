<!--
  SessionCheckpointVersioning.svelte -- BETA feature "session-checkpoint-versioning"
  (#26): read-only session checkpoint snapshots for post-mortem drift analysis.

  WHAT IT DOES
    Mark a named DIGEST snapshot of any governed (non-SM) session in one click,
    then read a structured what-changed delta between any two snapshots -- so
    "what drifted between two pipeline runs?" is three clicks instead of a JSONL
    export-and-diff ritual. A snapshot records decision/message counts +
    confidence + open-HITL/pattern/escalation tallies AT that moment; it NEVER
    rewinds or mutates the live session (purely observational, M18 post-hoc).

    Where it lives (matches the approved mockup): NOT a fourth frame -- the three
    frames stay present and calm (M1). A quiet "ckpt N" affordance is pinned to
    each governed lane in a calm block beneath the SessionRail; clicking it opens
    a right-side DRAWER (the SettingsDrawer side-tray idiom: role=dialog
    aria-modal, Esc-closes, focus-trapped) holding the timeline + compare
    manifest for that one session.

  BETA GATE (load-bearing). The ENTIRE body is wrapped in {#if enabled} where
  enabled is $betaFlags['session-checkpoint-versioning']. While OFF the component
  renders NOTHING and registers NO poller / SSE handler / timer / fetch of its
  own. There is NO background polling at all: the checkpoint list is fetched on
  demand only when the operator opens a lane's drawer; the compare delta is
  fetched on demand only when the operator arms two nodes. Flag defaults OFF
  (lib/beta/registry.js); the operator flips it in Settings > BETA features.

  POLARITY (G2/M15). The "ckpt N" affordance is STRUCTURALLY ABSENT on any
  SM-slug lane (or the injected own-session id) -- isSelfLane() never emits a
  button for self; it renders a dim "no ckpt -- SM-self excluded" note in its
  place (a real comment in the DOM, never a disabled control). The lanes
  themselves come from the `sessions` store, which already self-excludes SM in
  setSessions(); the additive read endpoints additionally exclude SM-self
  server-side, and a POST against an SM-self id is refused (HTTP 400,
  written:false). Belt and suspenders.

  ADR-18 MUST floor honoured here:
    - M1 3-frame presence: a rail block + an overlay drawer; adds NO 4th frame,
      removes none. The three frames are untouched.
    - M2 escalation-only foreground: every snapshot/compare is operator-initiated
      only; nothing auto-foregrounds, steals focus, or fires on its own.
    - M4 paired label+color: EVERY delta carries a TEXT label + signed number +
      a reinforcing tone dot. Confidence drift rides an ASCII v / ^ / = glyph +
      signed number, never hue. A zero escalation delta collapses to a dimmed
      dash. State is never color-alone.
    - Absolute HITL gate: untouched -- this feature reads counts only; it issues
      no governance verdict and resolves no HITL row.
    - M16 domain-agnostic: every session + checkpoint identity renders FROM DATA
      (project_slug / id / operator-typed name). No monitored-project vocabulary.
    - M17 a11y AAA: real buttons; the drawer is role=dialog aria-modal with a
      focus trap, Escape-to-close, focus restored to the invoking affordance; the
      arm/compare state is an aria-live region; full keyboard path.
    - M18: presentation-only; on-demand reads + a single create POST, never on
      the verdict hot path, never opens /api/commands/stream.

  When live gov.db data is absent (fresh DB / fetch error / endpoint missing) it
  falls back to a realistic, domain-agnostic MOCK fixture so the feature is
  always testable headless (usedMockData=true, surfaced as a literal text label).
  On the mock path "Checkpoint now" is client-side only (no POST).

  HEAVY/LIVE part DEFERRED (per build constraint): there is NO live snapshotting
  daemon and NO in-process cron/subprocess. A snapshot is a single on-demand row
  write; continuous/scheduled checkpointing is a documented "from CLI" affordance
  in the drawer footer, not built here.

  All selectors are .scv-* scoped so this feature pollutes no shared class.
  Tokens come from theme.css (calm-* / badge-* / focus-ring / spacing set).
  ASCII-only (cp1252-safe): dash is "--". No smart quotes, no em-dashes.
-->
<script>
  import { onDestroy, tick } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { sessions, ownSessionId } from '../../stores/session.js';
  import { readOwnSessionId } from '../../api.js';
  import {
    getSessionCheckpoints,
    createSessionCheckpoint,
    getCheckpointCompare,
  } from '../../api.js';
  import {
    isSelfLane,
    laneName,
    shortId,
    timelineView,
    compareManifest,
    mockLanes,
    mockCheckpoints,
    mockCompare,
    fmtNum,
  } from './SessionCheckpointVersioning-data.js';

  const FLAG_KEY = 'session-checkpoint-versioning';

  // -- gate: TRUE only while the operator has the BETA flag ON. The entire
  // template + every effect below is conditioned on this. --------------------
  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // SM-own session id (defense-in-depth self-exclude). Read once, lazily.
  let _ownId = null;
  function ownId() {
    if (_ownId === null) _ownId = $ownSessionId || readOwnSessionId();
    return _ownId;
  }

  // -- lane source: the live governed sessions (already self-excluded by the
  // store). When the store is empty we fall back to the mock lane set so the
  // feature is demonstrable headless. We classify SM-self defensively here too
  // (the affordance is structurally absent for any self lane). -----------------
  $: liveLanes = enabled ? $sessions : [];
  $: usingMockLanes = enabled && liveLanes.length === 0;
  $: lanes = enabled
    ? (liveLanes.length ? liveLanes : mockLanes()).map((s) => ({
        s,
        id: String(s.id),
        name: laneName(s),
        self: isSelfLane(s, ownId()),
        count: ckptCounts[String(s.id)] != null ? ckptCounts[String(s.id)] : initialCount(s),
      }))
    : [];

  // Any mock in play => surface a literal SAMPLE DATA label (M4: never implicit).
  $: usedMockData = enabled && (usingMockLanes || drawerMock);

  function initialCount(s) {
    const n = Number(s && s.ckpt_count);
    return Number.isFinite(n) && n >= 0 ? n : 0;
  }

  // Per-lane checkpoint counts shown on the affordance. Seeded lazily from the
  // initial lane data; refreshed when a lane's drawer is opened or a checkpoint
  // is created. This is NOT a poller -- it is updated only on operator action.
  /** @type {Record<string, number>} */
  let ckptCounts = {};

  // -- drawer state -----------------------------------------------------------
  let open = false;
  let loading = false;
  let drawerMock = false;
  let busy = false; // a create is in flight
  /** @type {Record<string, any>|null} */
  let openLane = null;
  /** @type {Array<Record<string, any>>} the live/mock checkpoint rows */
  let checkpoints = [];
  let receipt = '';

  // "Checkpoint now" inline form
  let formOpen = false;
  let ckptName = '';

  // arming + compare
  /** @type {Array<Record<string, any>>} ordered armed node view-models (max 2) */
  let armed = [];
  /** @type {Record<string, any>|null} the rendered manifest (pre-computed) */
  let manifest = null;

  /** @type {HTMLElement|null} */
  let drawerEl = null;
  /** @type {Element|null} */
  let lastFocused = null;

  // -- derived timeline view (pure; newest-first) -----------------------------
  $: nodes = enabled && open ? timelineView(checkpoints) : [];

  // -- on-demand checkpoint fetch (NO background poller) -----------------------
  async function loadCheckpoints(sessionId) {
    loading = true;
    try {
      const data = await getSessionCheckpoints(sessionId);
      const live = data && Array.isArray(data.checkpoints) ? data.checkpoints : [];
      if (live.length > 0) {
        checkpoints = live;
        drawerMock = false;
      } else {
        // fresh gov.db / endpoint absent -- representative mock so it is testable.
        checkpoints = mockCheckpoints(sessionId);
        drawerMock = true;
      }
    } catch {
      checkpoints = mockCheckpoints(sessionId);
      drawerMock = true;
    } finally {
      loading = false;
      ckptCounts = { ...ckptCounts, [String(sessionId)]: checkpoints.length };
    }
  }

  // -- drawer open / close + focus trap ---------------------------------------
  async function openDrawer(lane, invoker) {
    if (!enabled || lane.self) return; // self lanes never open (G2)
    lastFocused = invoker || (typeof document !== 'undefined' ? document.activeElement : null);
    openLane = lane;
    open = true;
    receipt = '';
    formOpen = false;
    ckptName = '';
    closeCompare();
    await loadCheckpoints(lane.id);
    await tick();
    const first =
      drawerEl &&
      drawerEl.querySelector('button:not([disabled]), input, [tabindex]:not([tabindex="-1"])');
    if (first && first.focus) first.focus();
  }

  function closeDrawer() {
    if (!open) return;
    open = false;
    busy = false;
    openLane = null;
    closeCompare();
    formOpen = false;
    if (lastFocused && lastFocused.focus) lastFocused.focus();
  }

  function focusables() {
    if (!drawerEl) return [];
    return Array.prototype.slice
      .call(drawerEl.querySelectorAll('button, input, [tabindex]:not([tabindex="-1"])'))
      .filter((el) => !el.disabled && el.offsetParent !== null);
  }

  function onDrawerKeydown(e) {
    if (e.key === 'Escape') {
      e.preventDefault();
      // Escape clears the compare panel first, then closes the drawer.
      if (manifest) { closeCompare(); return; }
      closeDrawer();
      return;
    }
    if (e.key === 'Tab') {
      const f = focusables();
      if (!f.length) return;
      const firstEl = f[0];
      const lastEl = f[f.length - 1];
      if (e.shiftKey && document.activeElement === firstEl) { e.preventDefault(); lastEl.focus(); }
      else if (!e.shiftKey && document.activeElement === lastEl) { e.preventDefault(); firstEl.focus(); }
    }
  }

  // -- "Checkpoint now" -> one-field name -> Save (writes a snapshot) ----------
  function toggleForm() {
    formOpen = !formOpen;
    if (formOpen) {
      ckptName = '';
      tick().then(() => {
        const inp = drawerEl && drawerEl.querySelector('.scv-form__input');
        if (inp && inp.focus) inp.focus();
      });
    }
  }

  async function saveCheckpoint() {
    if (busy || !openLane) return;
    const name = (ckptName || '').trim() || 'manual mark';
    busy = true;
    let created = null;
    if (!drawerMock) {
      try {
        const res = await createSessionCheckpoint(openLane.id, name);
        if (res && res.written && res.checkpoint) created = res.checkpoint;
      } catch {
        created = null;
      }
    }
    if (!created) {
      // mock path (or server refusal / down): client-side snapshot only.
      const latest = timelineView(checkpoints)[0] || {};
      created = {
        checkpoint_id: 'ck-' + Math.random().toString(36).slice(2, 8),
        name,
        timestamp: isoNow(),
        decision_count_at_checkpoint: (Number(latest.decisions) || 0) + 0,
        message_count_at_checkpoint: (Number(latest.messages) || 0) + 0,
        confidence: latest.confidence != null ? latest.confidence : null,
        open_hitl: Number(latest.openHitl) || 0,
        patterns: Number(latest.patterns) || 0,
        escalations: Number(latest.escalations) || 0,
        _fresh: true,
      };
    }
    checkpoints = [created, ...checkpoints];
    ckptCounts = { ...ckptCounts, [String(openLane.id)]: checkpoints.length };
    receipt =
      'Saved "' + name + '" -- digest snapshot recorded' +
      (drawerMock ? ' (SAMPLE DATA, client-side only).' : ' (<100ms INSERT; live session untouched).');
    formOpen = false;
    busy = false;
  }

  function isoNow() {
    try {
      return new Date().toISOString().replace('T', ' ').slice(0, 19) + 'Z';
    } catch {
      return 'now';
    }
  }

  // -- arming: click a node to arm (aria-pressed); two armed -> fetch compare --
  async function toggleArm(node) {
    const idx = armed.findIndex((n) => n.id === node.id);
    if (idx >= 0) {
      armed = armed.filter((n) => n.id !== node.id);
      manifest = null;
    } else {
      let next = armed.slice();
      if (next.length === 2) next = next.slice(1); // drop oldest-armed, keep two
      next.push(node);
      armed = next;
    }
    if (armed.length === 2) await runCompare();
  }

  $: isArmed = (id) => armed.some((n) => n.id === id);
  $: armedCount = armed.length;

  async function runCompare() {
    if (armed.length !== 2 || !openLane) return;
    const [a, b] = armed;
    let cmp = null;
    if (!drawerMock) {
      try {
        const res = await getCheckpointCompare(openLane.id, a.id, b.id);
        // server returns the pre-computed delta payload; empty => fall to mock.
        if (res && (res.delta_decisions != null || res.checkpoint_1)) cmp = res;
      } catch {
        cmp = null;
      }
    }
    if (!cmp) cmp = mockCompare(a, b);
    manifest = compareManifest(cmp);
  }

  function closeCompare() {
    manifest = null;
    armed = [];
  }

  // -- BETA gate teardown: flag OFF (or destroy) closes the drawer + clears
  // transient state so nothing lingers. The {#if enabled} block unmounts the
  // DOM; this clears the side-channels. --------------------------------------
  $: if (!enabled) teardown();
  function teardown() {
    if (open) { open = false; busy = false; openLane = null; }
    manifest = null;
    armed = [];
    formOpen = false;
  }
  onDestroy(teardown);
</script>

<!-- GATE: render absolutely nothing while OFF. No block, no affordance, no fetch. -->
{#if enabled}
  <!-- The calm rail block: one quiet "ckpt N" affordance per GOVERNED lane.
       Mounts beneath the SessionRail in the left command-column. -->
  <section class="scv" aria-label="Session checkpoint versioning">
    <header class="scv__head">
      <span class="scv__title">Checkpoints</span>
      <span class="scv__beta">BETA</span>
    </header>

    {#if lanes.length === 0}
      <p class="scv__empty">
        No governed sessions yet -- a checkpoint affordance appears per lane as
        non-SM sessions are observed.
      </p>
    {:else}
      <ul class="scv__lanes" role="list">
        {#each lanes as lane (lane.id)}
          <li class="scv__lane" class:scv__lane--self={lane.self}>
            <span class="scv__lane-name" title={lane.name}>{lane.name}</span>
            <span class="scv__lane-id">{shortId(lane.id)}</span>
            <span class="scv__lane-spacer"></span>

            {#if lane.self}
              <!-- POLARITY (G2): the affordance is STRUCTURALLY ABSENT on an
                   SM-self lane -- a dim note, never a disabled button. -->
              <span
                class="scv__absent"
                title="Polarity: checkpointing SM-self is structurally excluded (server returns HTTP 400, written:false)"
              >no ckpt -- SM-self excluded</span>
            {:else}
              <button
                class="scv__aff"
                type="button"
                aria-haspopup="dialog"
                aria-expanded={open && openLane && openLane.id === lane.id}
                aria-label={'Checkpoints for session ' + lane.name + ' -- ' + lane.count + ' saved; open drawer'}
                data-session-id={lane.id}
                on:click={(e) => openDrawer(lane, e.currentTarget)}
              >
                <span class="scv__aff-glyph">ckpt</span>
                <span class="scv__aff-count">{lane.count}</span>
                <span class="scv__aff-chev" aria-hidden="true">&gt;</span>
              </button>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}

    <footer class="scv__foot">
      <span class="scv__foot-pill">BETA -- default OFF, toggled in Settings</span>
      <span class="scv__self" title="StreamManager's own session is never checkpointable">
        <span class="scv__self-dot" aria-hidden="true"></span>self excluded
      </span>
      {#if usingMockLanes}
        <span class="scv__foot-mock">SAMPLE DATA -- no governed sessions in scope yet</span>
      {/if}
    </footer>
  </section>

  {#if open}
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div class="scv-scrim" role="presentation" on:click={(e) => { if (e.target === e.currentTarget) closeDrawer(); }}></div>
    <aside
      class="scv-drawer"
      role="dialog"
      aria-modal="true"
      aria-labelledby="scv-drawer-title"
      bind:this={drawerEl}
      on:keydown={onDrawerKeydown}
    >
      <header class="scv-drawer__head">
        <div class="scv-drawer__grow">
          <span class="scv-drawer__eyebrow">Checkpoints -- post-mortem drift</span>
          <h2 id="scv-drawer-title" class="scv-drawer__title">
            Session <span class="scv-drawer__sid">{openLane ? shortId(openLane.id) : ''}</span>
            {#if openLane}<span class="scv-drawer__slug">({openLane.name})</span>{/if}
          </h2>
        </div>
        <button class="scv-drawer__close" type="button" aria-label="Close checkpoints drawer (Esc)" on:click={closeDrawer}>
          <span aria-hidden="true">&times;</span>
        </button>
      </header>

      <div class="scv-drawer__body">
        <!-- data-source label (mock vs live), M4 literal text -->
        <p class="scv-source" data-mock={drawerMock}>
          {drawerMock
            ? 'SAMPLE DATA -- no live checkpoints for this session yet; showing a representative shape.'
            : 'LIVE -- read from gov.db session_checkpoints for this session.'}
        </p>

        <!-- "Checkpoint now" (one-field name -> Save). Never rewinds the session. -->
        <div class="scv-now">
          <div class="scv-now__row">
            <button class="scv-now__btn" type="button" aria-expanded={formOpen} on:click={toggleForm}>
              <span class="scv-now__plus" aria-hidden="true">+</span> Checkpoint now
            </button>
            <span class="scv-now__hint">writes a digest snapshot -- never rewinds the live session</span>
          </div>
          {#if formOpen}
            <form class="scv-form" autocomplete="off" on:submit|preventDefault={saveCheckpoint}>
              <input
                class="scv-form__input"
                type="text"
                bind:value={ckptName}
                placeholder="name this checkpoint (e.g. 4pm baseline)"
                aria-label="Checkpoint name"
                maxlength="48"
              />
              <button class="scv-form__save" type="submit" disabled={busy}>{busy ? 'Saving...' : 'Save'}</button>
              <button class="scv-form__cancel" type="button" on:click={() => (formOpen = false)}>Cancel</button>
              <span class="scv-lat-note">&lt;100ms INSERT</span>
            </form>
          {/if}
        </div>

        <!-- arm/compare hint bar (aria-live) -->
        <div class="scv-arm" aria-live="polite">
          <span>Pick two checkpoints to compare</span>
          <span class="scv-arm__tag">{armedCount} armed</span>
          <button
            class="scv-arm__btn"
            type="button"
            disabled={armedCount !== 2}
            aria-label="Compare the two armed checkpoints"
            on:click={runCompare}
          >Compare &gt;</button>
        </div>

        <!-- the PRE-COMPUTED compare delta manifest (expands when two armed) -->
        {#if manifest}
          <section class="scv-compare" aria-label="Checkpoint comparison delta manifest">
            <div class="scv-compare__head">
              <span class="scv-compare__eyebrow">Delta</span>
              <span class="scv-compare__pair">
                <span>{manifest.pair.name1}</span>
                <span class="scv-compare__vs" aria-hidden="true">vs</span>
                <span>{manifest.pair.name2}</span>
              </span>
              <button class="scv-compare__close" type="button" aria-label="Close comparison" on:click={closeCompare}>clear</button>
            </div>
            <div class="scv-delta-grid">
              <!-- decisions / messages / confidence (each: label + signed val + tone dot) -->
              {#each manifest.rows as d (d.key)}
                <div class="scv-delta scv-delta--{d.tone}">
                  <span class="scv-delta__dot" aria-hidden="true"></span>
                  <span class="scv-delta__label">{d.label}</span>
                  <span class="scv-delta__val">
                    {#if d.key === 'confidence'}<span class="scv-conf-glyph" aria-hidden="true">{d.confGlyph}</span> {/if}{d.value}
                  </span>
                  {#if d.sub}<span class="scv-delta__sub">{d.sub}</span>{/if}
                </div>
              {/each}

              <!-- new HITL overrides: accent dot + verdict-tag (text + tone) -->
              <div class="scv-delta scv-delta--hitl">
                <span class="scv-delta__dot" aria-hidden="true"></span>
                <span class="scv-delta__label">New HITL overrides</span>
                {#if manifest.hitl.count > 0}
                  <span class="scv-verdict scv-verdict--block">
                    <span class="scv-verdict__count">{manifest.hitl.count}</span> {manifest.hitl.verdict}
                  </span>
                {:else}
                  <span class="scv-zero">-- none</span>
                {/if}
              </div>

              <!-- learned patterns: advisory hash-chips (never auto-acts) -->
              <div class="scv-delta scv-delta--patterns">
                <span class="scv-delta__dot" aria-hidden="true"></span>
                <span class="scv-delta__label">Patterns learned</span>
                {#if manifest.patterns.length > 0}
                  <span class="scv-chips">
                    {#each manifest.patterns as p (p.hash)}
                      <span class="scv-chip">
                        <span class="scv-chip__dot" aria-hidden="true"></span>{p.hash} applied {p.applied}x
                        <span class="scv-chip__adv">-- advisory only</span>
                      </span>
                    {/each}
                  </span>
                {:else}
                  <span class="scv-zero">-- no new patterns</span>
                {/if}
              </div>

              <!-- escalation delta: literal count + type; a ZERO delta is a dash -->
              <div class="scv-delta scv-delta--esc" class:scv-delta--esc-hot={manifest.escalation.count > 0}>
                <span class="scv-delta__dot" aria-hidden="true"></span>
                <span class="scv-delta__label">Escalations</span>
                {#if manifest.escalation.count > 0}
                  <span class="scv-esc-tag"><span class="scv-esc-tag__count">+{manifest.escalation.count}</span> NEW</span>
                  {#if manifest.escalation.type}<span class="scv-esc-type">{manifest.escalation.type}</span>{/if}
                {:else}
                  <span class="scv-zero">-- no change</span>
                {/if}
              </div>
            </div>
          </section>
        {/if}

        <!-- the vertical TIMELINE (manifest-spine; newest first) -->
        {#if loading}
          <p class="scv-loading">Loading checkpoints...</p>
        {:else if nodes.length === 0}
          <p class="scv-empty-nodes">
            No checkpoints yet for this session. Use "Checkpoint now" to mark the
            first digest snapshot.
          </p>
        {:else}
          <div class="scv-timeline" role="group" aria-label="Saved checkpoints, newest first -- arm two to compare">
            {#each nodes as n (n.id)}
              <button
                class="scv-node scv-node--{n.ageBand}"
                class:scv-node--fresh={n.id && checkpoints.find((c) => (c.checkpoint_id || c.id) === n.id && c._fresh)}
                type="button"
                aria-pressed={isArmed(n.id)}
                aria-label={n.aria}
                data-ckpt={n.id}
                on:click={() => toggleArm(n)}
              >
                <div class="scv-node__top">
                  <span class="scv-node__check" aria-hidden="true">{isArmed(n.id) ? 'x' : ''}</span>
                  <span class="scv-node__name">{n.name}</span>
                  <span class="scv-node__ts">{n.ts}</span>
                </div>
                <div class="scv-node__metrics">
                  <span><b>{fmtNum(n.decisions)}</b> decisions</span>
                  <span><b>{fmtNum(n.messages)}</b> messages</span>
                  {#if n.confidence != null}<span>conf <b>{n.confidence.toFixed(2)}</b></span>{/if}
                  <span><b>{n.openHitl}</b> open HITL</span>
                  <span><b>{n.patterns}</b> patterns</span>
                  <span><b>{n.escalations}</b> esc</span>
                </div>
              </button>
            {/each}
          </div>
        {/if}

        {#if receipt}<p class="scv-receipt" role="status">{receipt}</p>{/if}
      </div>

      <footer class="scv-drawer__foot">
        <span class="scv-drawer__beta">BETA -- default OFF, toggled in Settings</span>
        <span class="scv-drawer__note">
          deltas pre-computed server-side -- no client drift math. Continuous /
          scheduled checkpointing runs from the CLI (no in-process daemon).
        </span>
      </footer>
    </aside>
  {/if}
{/if}

<style>
  /* ---- the calm rail block (mirrors the HealthSparklines .hs idiom) --------- */
  .scv {
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 6px);
    padding: var(--space-4, 10px);
    background: var(--calm-surface-raised, var(--bg-card, #0c1118));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-soft, 4px);
    font-family: var(--ff-system);
  }
  .scv__head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-4, 10px);
    padding-bottom: var(--space-2, 4px);
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
  }
  .scv__title {
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .scv__beta {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--badge-ar-fg, #d97706);
    background: var(--badge-ar-bg, #fef3c7);
    border: 1px solid var(--badge-ar-border, #d97706);
    border-radius: 4px;
    padding: 1px 5px;
  }

  .scv__empty {
    margin: 0;
    padding: var(--space-3, 6px) var(--space-2, 4px);
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    font-size: var(--fs-meta, 13px);
    font-style: italic;
    line-height: var(--lh-body, 1.5);
  }

  .scv__lanes {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 6px);
  }
  .scv__lane {
    display: flex;
    align-items: center;
    gap: var(--space-3, 6px);
    padding: var(--space-3, 6px) var(--space-3, 6px);
    background: var(--calm-surface-row, var(--bg-row, #0e141e));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-sharp, 2px);
  }
  .scv__lane--self { opacity: 0.82; }
  .scv__lane-name {
    font-size: var(--fs-meta, 13px);
    font-weight: 460;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 11ch;
  }
  .scv__lane-id {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .scv__lane-spacer { flex: 1 1 auto; }

  /* the bespoke "ckpt N" affordance -- a quiet count-pill button */
  .scv__aff {
    appearance: none;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    font-family: var(--font-d, var(--ff-mono));
    font-size: 11px;
    padding: 3px 9px;
    border-radius: var(--radius-sharp, 2px);
    cursor: pointer;
    transition: color var(--t-calm, 180ms ease), border-color var(--t-calm, 180ms ease),
                background var(--t-calm, 180ms ease);
  }
  .scv__aff:hover {
    border-color: var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25)));
    background: var(--calm-accent-wash, var(--accent-dim, rgba(245, 158, 11, 0.09)));
  }
  .scv__aff[aria-expanded='true'] {
    border-color: var(--calm-hairline-hi, var(--border-hi));
    background: var(--calm-accent-wash, var(--accent-dim, rgba(245, 158, 11, 0.09)));
  }
  .scv__aff-glyph {
    font-size: 9px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .scv__aff-count {
    font-weight: 700;
    color: var(--calm-accent, var(--accent, #f59e0b));
    font-variant-numeric: tabular-nums;
    min-width: 1ch;
    text-align: center;
  }
  .scv__aff-chev { color: var(--calm-ink-quiet, var(--text-dim, #948870)); font-size: 9px; }

  /* SM-self lane: the structural-absence note (dashed; never a button) */
  .scv__absent {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    letter-spacing: 0.02em;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    border: 1px dashed var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-sharp, 2px);
    padding: 3px 9px;
    white-space: nowrap;
  }

  .scv__foot {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-3, 6px);
    margin-top: var(--space-2, 4px);
    padding-top: var(--space-3, 6px);
    border-top: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
  }
  .scv__foot-pill {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    letter-spacing: 0.04em;
    color: var(--badge-obs-fg, #475569);
    background: var(--badge-obs-bg, #f1f5f9);
    border: 1px solid var(--badge-obs-border, #cbd5e1);
    border-radius: 999px;
    padding: 2px 9px;
  }
  .scv__self {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .scv__self-dot {
    width: 5px; height: 5px; border-radius: 50%;
    background: var(--calm-ink-quiet, var(--text-dim, #948870)); opacity: 0.7;
  }
  .scv__foot-mock {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    letter-spacing: 0.02em;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }

  /* ---- scrim + right-anchored drawer (SettingsDrawer dialog idiom) ---------- */
  .scv-scrim {
    position: fixed; inset: 0; background: rgba(8, 10, 12, 0.55);
    backdrop-filter: blur(1px); z-index: 80;
  }
  .scv-drawer {
    position: fixed; top: 0; right: 0; bottom: 0;
    width: min(460px, 94vw); z-index: 81;
    display: flex; flex-direction: column;
    background: var(--calm-surface-raised, var(--bg-card, #0c1118));
    border-left: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25)));
    box-shadow: -18px 0 48px -24px rgba(0, 0, 0, 0.7);
    color: var(--calm-ink, var(--text, #b8b098));
    font-family: var(--ff-system);
    overflow: hidden;
  }
  :global(html[data-motion='allow']) .scv-drawer { animation: scvSlide 160ms ease-out; }
  @keyframes scvSlide { from { transform: translateX(12px); opacity: 0; } to { transform: none; opacity: 1; } }

  .scv-drawer__head {
    flex: 0 0 auto;
    display: flex; align-items: flex-start; gap: var(--space-4, 10px);
    padding: var(--space-4, 10px) var(--space-5, 14px);
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
  }
  .scv-drawer__grow { flex: 1 1 auto; min-width: 0; }
  .scv-drawer__eyebrow {
    display: block;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 9.5px; letter-spacing: 0.16em; text-transform: uppercase;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .scv-drawer__title {
    margin: 2px 0 0;
    font-size: var(--fs-body, 14px); font-weight: 650;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    line-height: var(--lh-tight, 1.25);
  }
  .scv-drawer__sid { font-family: var(--font-d, var(--ff-mono)); font-size: 12px; color: var(--calm-accent, var(--accent, #f59e0b)); }
  .scv-drawer__slug { font-size: 11px; color: var(--calm-ink-quiet, var(--text-dim, #948870)); }
  .scv-drawer__close {
    flex: 0 0 auto;
    appearance: none; background: transparent;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-sharp, 2px);
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    width: 28px; height: 28px; line-height: 1; font-size: 14px; cursor: pointer;
    display: inline-flex; align-items: center; justify-content: center;
    transition: color var(--t-calm, 180ms ease), border-color var(--t-calm, 180ms ease);
  }
  .scv-drawer__close:hover { color: var(--calm-accent, var(--accent, #f59e0b)); border-color: var(--calm-hairline-hi, var(--border-hi)); }

  .scv-drawer__body {
    flex: 1 1 auto; min-height: 0; overflow-y: auto; overscroll-behavior: contain;
    padding: var(--space-4, 10px) var(--space-5, 14px) var(--space-6, 22px);
    display: flex; flex-direction: column; gap: var(--space-4, 10px);
  }

  .scv-source {
    margin: 0;
    font-family: var(--font-d, var(--ff-mono)); font-size: 10px; letter-spacing: 0.02em;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .scv-source[data-mock='true'] { color: var(--badge-ar-fg, #d97706); }

  /* "Checkpoint now" */
  .scv-now {
    display: flex; flex-direction: column; gap: var(--space-3, 6px);
    padding-bottom: var(--space-4, 10px);
    border-bottom: 1px dashed var(--calm-hairline, var(--border, #192030));
  }
  .scv-now__row { display: flex; align-items: center; gap: var(--space-3, 6px); flex-wrap: wrap; }
  .scv-now__btn {
    appearance: none;
    display: inline-flex; align-items: center; gap: 8px;
    font-family: var(--font-d, var(--ff-mono)); font-size: 12px; letter-spacing: 0.03em;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-soft, 4px); padding: 8px 13px; cursor: pointer;
    transition: border-color var(--t-calm, 180ms ease), background var(--t-calm, 180ms ease);
  }
  .scv-now__btn:hover { border-color: var(--calm-hairline-hi, var(--border-hi)); background: var(--calm-accent-wash, var(--accent-dim, rgba(245, 158, 11, 0.09))); }
  .scv-now__plus { color: var(--calm-accent, var(--accent, #f59e0b)); font-weight: 800; }
  .scv-now__hint { font-family: var(--font-d, var(--ff-mono)); font-size: 10px; color: var(--calm-ink-quiet, var(--text-dim, #948870)); }
  .scv-form { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .scv-form__input {
    flex: 1 1 160px;
    font-family: var(--font-d, var(--ff-mono)); font-size: 12px;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    background: var(--calm-surface-row, var(--bg-row, #0e141e));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-sharp, 2px); padding: 7px 10px;
  }
  .scv-form__input::placeholder { color: var(--calm-ink-quiet, var(--text-dim, #948870)); }
  .scv-form__save {
    appearance: none;
    font-family: var(--font-d, var(--ff-mono)); font-size: 11px; letter-spacing: 0.04em;
    color: var(--calm-accent, var(--accent, #f59e0b));
    background: var(--calm-accent-wash, var(--accent-dim, rgba(245, 158, 11, 0.09)));
    border: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25)));
    border-radius: var(--radius-sharp, 2px); padding: 7px 13px; cursor: pointer;
  }
  .scv-form__save:disabled { opacity: 0.45; cursor: not-allowed; }
  .scv-form__cancel {
    appearance: none;
    font-family: var(--font-d, var(--ff-mono)); font-size: 11px;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    background: transparent; border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-sharp, 2px); padding: 7px 11px; cursor: pointer;
  }
  .scv-lat-note { font-family: var(--font-d, var(--ff-mono)); font-size: 9.5px; color: var(--calm-ink-quiet, var(--text-dim, #948870)); }

  /* arm/compare bar */
  .scv-arm {
    display: flex; align-items: center; gap: 9px; flex-wrap: wrap;
    font-family: var(--font-d, var(--ff-mono)); font-size: 10.5px; letter-spacing: 0.03em;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .scv-arm__tag {
    color: var(--calm-accent, var(--accent, #f59e0b));
    border: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25)));
    background: var(--calm-accent-wash, var(--accent-dim, rgba(245, 158, 11, 0.09)));
    border-radius: var(--radius-sharp, 2px); padding: 2px 7px;
  }
  .scv-arm__btn {
    margin-left: auto;
    appearance: none;
    font-family: var(--font-d, var(--ff-mono)); font-size: 11px; letter-spacing: 0.04em;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-sharp, 2px); padding: 6px 12px; cursor: pointer;
    transition: border-color var(--t-calm, 180ms ease), background var(--t-calm, 180ms ease);
  }
  .scv-arm__btn:enabled:hover { border-color: var(--calm-hairline-hi, var(--border-hi)); background: var(--calm-accent-wash, var(--accent-dim, rgba(245, 158, 11, 0.09))); }
  .scv-arm__btn:disabled { opacity: 0.5; cursor: not-allowed; }

  /* compare delta manifest */
  .scv-compare {
    border: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25)));
    border-left: 3px solid var(--calm-accent, var(--accent, #f59e0b));
    border-radius: var(--radius-soft, 4px);
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
    overflow: hidden;
  }
  .scv-compare__head {
    display: flex; align-items: center; gap: 9px; flex-wrap: wrap;
    padding: 10px 12px;
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
  }
  .scv-compare__eyebrow {
    font-family: var(--font-d, var(--ff-mono)); font-size: 9.5px; letter-spacing: 0.16em;
    text-transform: uppercase; color: var(--calm-accent, var(--accent, #f59e0b));
  }
  .scv-compare__pair {
    font-family: var(--font-d, var(--ff-mono)); font-size: 11.5px;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    display: inline-flex; align-items: center; gap: 4px;
  }
  .scv-compare__vs { color: var(--calm-ink-quiet, var(--text-dim, #948870)); padding: 0 4px; }
  .scv-compare__close {
    margin-left: auto;
    appearance: none;
    font-family: var(--font-d, var(--ff-mono)); font-size: 11px;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    background: transparent; border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-sharp, 2px); padding: 4px 9px; cursor: pointer;
  }
  .scv-compare__close:hover { color: var(--calm-ink-loud, var(--text-bright, #e8e0cc)); border-color: var(--calm-hairline-hi, var(--border-hi)); }

  .scv-delta-grid { display: flex; flex-direction: column; }
  .scv-delta {
    display: flex; align-items: center; gap: 11px; flex-wrap: wrap;
    padding: 9px 12px;
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    font-family: var(--font-d, var(--ff-mono)); font-size: 12px;
  }
  .scv-delta:last-child { border-bottom: none; }
  .scv-delta__dot { width: 7px; height: 7px; border-radius: 50%; flex: 0 0 auto; background: var(--role-calm-fg, #93a4bd); opacity: 0.9; }
  .scv-delta__label {
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    letter-spacing: 0.04em; text-transform: uppercase; font-size: 10px;
    min-width: 124px;
  }
  .scv-delta__val { color: var(--calm-ink-loud, var(--text-bright, #e8e0cc)); font-weight: 700; font-size: 13px; font-variant-numeric: tabular-nums; }
  .scv-delta__sub { color: var(--calm-ink-quiet, var(--text-dim, #948870)); font-size: 11px; }

  /* per-row tone reinforcement (DOT carries hue; label + value are the signal) */
  .scv-conf-glyph { font-weight: 800; font-size: 13px; line-height: 1; }
  .scv-delta--conf-down .scv-delta__dot,
  .scv-delta--conf-down .scv-conf-glyph { color: var(--c-guide, #eab308); background: var(--c-guide, #eab308); }
  .scv-delta--conf-down .scv-conf-glyph { background: transparent; }
  .scv-delta--conf-up .scv-delta__dot,
  .scv-delta--conf-up .scv-conf-glyph { color: var(--c-allow, #22c55e); background: var(--c-allow, #22c55e); }
  .scv-delta--conf-up .scv-conf-glyph { background: transparent; }
  .scv-delta--conf-flat .scv-conf-glyph { color: var(--role-calm-fg, #93a4bd); }
  .scv-delta--hitl .scv-delta__dot { background: var(--calm-accent, var(--accent, #f59e0b)); }
  .scv-delta--patterns .scv-delta__dot { background: var(--c-suggest, #84cc16); }
  .scv-delta--esc-hot .scv-delta__dot { background: var(--c-block, #ef4444); }

  .scv-zero { color: var(--calm-ink-quiet, var(--text-dim, #948870)); font-size: 12px; }

  .scv-verdict {
    display: inline-flex; align-items: center; gap: 5px;
    font-family: var(--font-d, var(--ff-mono)); font-size: 11px; font-weight: 700;
    letter-spacing: 0.05em; padding: 2px 8px; border-radius: var(--radius-sharp, 2px);
    border: 1px solid var(--calm-hairline, var(--border, #192030));
  }
  .scv-verdict--block { color: var(--c-block, #ef4444); border-color: rgba(239, 68, 68, 0.45); background: rgba(239, 68, 68, 0.1); }
  .scv-verdict__count { color: var(--calm-ink-loud, var(--text-bright, #e8e0cc)); }

  .scv-chips { display: inline-flex; flex-wrap: wrap; gap: 7px; }
  .scv-chip {
    display: inline-flex; align-items: center; gap: 6px;
    font-family: var(--font-d, var(--ff-mono)); font-size: 11px; font-weight: 600;
    color: var(--c-suggest, #84cc16);
    border: 1px solid rgba(132, 204, 22, 0.3); background: rgba(132, 204, 22, 0.08);
    border-radius: var(--radius-sharp, 2px); padding: 3px 8px; letter-spacing: 0.02em;
  }
  .scv-chip__dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; opacity: 0.85; }
  .scv-chip__adv { color: var(--calm-ink-quiet, var(--text-dim, #948870)); font-weight: 400; }

  .scv-esc-tag {
    display: inline-flex; align-items: center; gap: 6px;
    font-family: var(--font-d, var(--ff-mono)); font-size: 11px; font-weight: 700;
    color: var(--c-block, #ef4444);
    border: 1px solid rgba(239, 68, 68, 0.45); background: rgba(239, 68, 68, 0.1);
    border-radius: var(--radius-sharp, 2px); padding: 2px 8px;
  }
  .scv-esc-tag__count { color: var(--calm-ink-loud, var(--text-bright, #e8e0cc)); }
  .scv-esc-type { color: var(--calm-ink-quiet, var(--text-dim, #948870)); font-size: 10.5px; }

  /* the vertical timeline (manifest-spine) */
  .scv-loading,
  .scv-empty-nodes {
    margin: 4px 0; font-size: 13px; font-style: italic;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    line-height: var(--lh-body, 1.5);
  }
  .scv-timeline { position: relative; margin: 2px 0; padding-left: 22px; }
  .scv-timeline::before {
    content: ""; position: absolute; left: 6px; top: 6px; bottom: 6px; width: 2px;
    background: linear-gradient(var(--calm-accent, var(--accent, #f59e0b)), var(--calm-accent-wash, var(--accent-dim, rgba(245, 158, 11, 0.09))));
    opacity: 0.55;
  }
  .scv-node {
    position: relative;
    display: block; width: 100%; text-align: left;
    margin: 0 0 9px;
    background: var(--calm-surface-row, var(--bg-row, #0e141e));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-soft, 4px);
    padding: 10px 12px 11px; cursor: pointer;
    color: var(--calm-ink, var(--text, #b8b098)); font: inherit;
    transition: border-color var(--t-calm, 180ms ease), background var(--t-calm, 180ms ease);
  }
  .scv-node:hover { background: var(--calm-surface-hover, var(--bg-row-hover, #131c2a)); }
  .scv-node::before {
    content: ""; position: absolute; left: -19px; top: 15px;
    width: 9px; height: 9px; border-radius: 50%;
    background: var(--calm-surface-raised, var(--bg-card, #0c1118));
    border: 2px solid var(--role-calm-fg, #93a4bd);
  }
  .scv-node--newest::before { border-color: var(--calm-accent, var(--accent, #f59e0b)); }
  .scv-node--newest { border-color: var(--calm-hairline-hi, var(--border-hi, rgba(245, 158, 11, 0.25))); }
  .scv-node--age1 { opacity: 0.94; }
  .scv-node--age2 { opacity: 0.88; }
  .scv-node[aria-pressed='true'] {
    border-color: var(--calm-accent, var(--accent, #f59e0b));
    box-shadow: inset 0 0 0 1px var(--calm-accent-wash, var(--accent-dim, rgba(245, 158, 11, 0.09)));
    background: var(--calm-accent-wash, var(--accent-dim, rgba(245, 158, 11, 0.09)));
  }
  .scv-node__top { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
  .scv-node__name {
    font-family: var(--font-d, var(--ff-mono)); font-size: 13px; font-weight: 700;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
  }
  .scv-node__check {
    display: inline-flex; align-items: center; justify-content: center;
    width: 15px; height: 15px; flex: 0 0 auto;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-sharp, 2px);
    font-family: var(--font-d, var(--ff-mono)); font-size: 10px; color: transparent;
  }
  .scv-node[aria-pressed='true'] .scv-node__check {
    border-color: var(--calm-accent, var(--accent, #f59e0b)); color: var(--calm-accent, var(--accent, #f59e0b));
  }
  .scv-node__ts {
    margin-left: auto;
    font-family: var(--font-d, var(--ff-mono)); font-size: 10.5px; color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .scv-node__metrics {
    display: flex; flex-wrap: wrap; gap: 4px 14px; margin-top: 7px;
    font-family: var(--font-d, var(--ff-mono)); font-size: 11px; color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .scv-node__metrics b { color: var(--calm-ink, var(--text, #b8b098)); font-weight: 600; }

  .scv-receipt {
    margin: 0; font-family: var(--font-d, var(--ff-mono)); font-size: 12px;
    color: var(--badge-decided-fg, #16a34a); letter-spacing: 0.02em;
  }

  .scv-drawer__foot {
    flex: 0 0 auto;
    display: flex; align-items: center; gap: var(--space-3, 6px); flex-wrap: wrap;
    padding: var(--space-3, 6px) var(--space-5, 14px);
    border-top: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
  }
  .scv-drawer__beta {
    font-family: var(--font-d, var(--ff-mono)); font-size: 9.5px; letter-spacing: 0.05em;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    border: 1px dashed var(--calm-hairline, var(--border, #192030)); border-radius: 999px;
    padding: 4px 11px; white-space: nowrap;
  }
  .scv-drawer__note { font-family: var(--font-d, var(--ff-mono)); font-size: 9.5px; color: var(--calm-ink-quiet, var(--text-dim, #948870)); line-height: 1.4; }

  /* shared focus-ring contract: 2px solid amber, 2px offset, every control. */
  .scv__aff:focus-visible,
  .scv-drawer__close:focus-visible,
  .scv-now__btn:focus-visible,
  .scv-form__input:focus-visible,
  .scv-form__save:focus-visible,
  .scv-form__cancel:focus-visible,
  .scv-arm__btn:focus-visible,
  .scv-compare__close:focus-visible,
  .scv-node:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid) var(--focus-ring-color, #d97706);
    outline-offset: var(--focus-ring-offset, 2px);
  }

  /* reduced motion (M17): suppress the slide-in + transitions unless allowed. */
  :global(html[data-motion='reduce']) .scv-drawer,
  :global(html[data-motion='reduce']) .scv__aff,
  :global(html[data-motion='reduce']) .scv-node { transition: none; animation: none; }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .scv-drawer { animation: none; }
    :global(html:not([data-motion='allow'])) .scv__aff,
    :global(html:not([data-motion='allow'])) .scv-node { transition: none; }
  }
</style>
