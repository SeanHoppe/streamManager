<!--
  SessionStoryPanelNarrativeArc.svelte -- BETA feature
  "session-story-panel-narrative-arc" (#37).

  WHAT IT IS
    A frame-sized SESSION STORY card docked ABOVE the still-water decision
    stream inside Frame A. It turns one session's raw decision feed into a calm,
    glance-readable NARRATIVE ARC -- a few short paragraphs whose key phrases are
    real <button>s that scroll-highlight the matching decision rows (the
    bi-directional feed link: click a phrase -> the evidence rows pulse + focus
    moves to the first; hover/focus a row -> the referencing sentence
    reverse-underlines). A paired label+color TONE badge (CLEAN / LEARNING /
    TURBULENT / BLOCKED) is the at-a-glance hero (M4: the literal WORD is always
    rendered; color is never the only channel).

    An empty session offers a single calm "Compose Story" affordance. The rich
    (Sonnet) narrative is DEFERRED to a non-functional "from CLI" affordance per
    the constrained-additive brief (NO in-process spawn / subprocess / worker
    queue here); the always-available CLIENT-SIDE arc (deriveStory) is the floor
    so the panel renders with no backend and no new bus envelope.

  BETA GATE (load-bearing)
    The ENTIRE component is wrapped in {#if enabled} where enabled is
    $betaFlags['session-story-panel-narrative-arc']. When the flag is OFF it
    renders NOTHING and registers NO store subscriptions beyond the cheap flag
    read, NO poller, NO SSE handler, NO timer. The flag defaults OFF
    (lib/beta/registry.js); the operator flips it in Settings > BETA features.

  DATA (M18 post-hoc -- no new transport, no new envelope, no FROZEN edit)
    The arc is derived 100% CLIENT-SIDE from the ALREADY-OPEN decision feed
    (decisionsStore from lib/sse.js) scoped to the selected session -- there is
    NO new poller and NO new SSE channel. When the live feed has no rows for the
    scope (fresh gov.db) the component falls back to a realistic deterministic
    MOCK arc + mock evidence rows so it is always inspectable
    (usedMockData=true, labelled in the UI). The optional persisted server
    narrative (GET /api/sessions/{id}/story) is read once on demand and prepended
    when present; its absence is the normal path and degrades silently to the
    derived arc.

  POLARITY (G2 / M15)
    The feed is the decisionsStore (already self-excluded in sse.js) + a cheap
    ownSessionId backstop on the scope; the selected session can never resolve to
    SM-self (session.js). There is no code path that narrates SM-self. When the
    scope is somehow the SM-own session the card renders an explicit
    "self -- excluded (G2)" note, never an arc.

  DOMAIN-AGNOSTIC (M16 / zero-contamination): the session identity + every
    rendered string come FROM DATA. The mock slug ("node-worker-04") mirrors the
    approved mockup and is a generic placeholder, never monitored-project vocab.

  ASCII-only (cp1252-safe): dash is "--". No smart quotes / em-dash.
-->
<script>
  import { onDestroy, onMount, tick } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { decisionsStore } from '../../sse.js';
  import { selectedSessionId, selectedSession, getOwnSessionId } from '../../stores/session.js';
  import Badge from '../Badge.svelte';
  import {
    deriveStory,
    mockStory,
    mockRows,
    toneLabel,
    TONE_MAP,
    actionOf,
    weightForAction,
    badgeForAction,
    confPct,
    shortId,
    fmtComposed,
  } from './SessionStoryPanelNarrativeArc-data.js';

  /** The stable BETA flag key this component gates on. */
  const FLAG_KEY = 'session-story-panel-narrative-arc';

  /**
   * allowMock: when the live feed has no rows in scope, fall back to a realistic
   * deterministic mock arc so the card is visible/testable. Default true (tests
   * rely on it). Set false to force a true live-only render.
   * @type {boolean}
   */
  export let allowMock = true;

  // -- gate (single source of truth: the betaFlags store) --------------------
  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // -- self-exclude (G2 / M15) -----------------------------------------------
  // Resolved once on mount; used as a cheap backstop when the scope is somehow
  // the SM-own session (selectedSessionId can never resolve to it per
  // session.js, but guard anyway so the card shows the calm self note).
  let ownSessionId = '';
  $: scopedSessionId = $selectedSessionId || null;
  $: isSelfScope = !!(ownSessionId && scopedSessionId && scopedSessionId === ownSessionId);

  // -- the live feed, scoped + self-excluded ---------------------------------
  // decisionsStore is fed by the SINGLE shared SSE (sse.js); we open no stream.
  // Only read it while ENABLED -- when OFF the {#if enabled} block is unmounted
  // so this reactive read does no work (the gate is load-bearing).
  $: feedRows = enabled ? $decisionsStore || [] : [];
  $: scopedRows = scopedSessionId
    ? feedRows.filter((r) => r && r.session_id === scopedSessionId)
    : feedRows;

  // -- the session label (identity FROM DATA, M16) ---------------------------
  $: scopeName = (() => {
    const s = $selectedSession;
    if (s && typeof s.project_slug === 'string' && s.project_slug.trim()) return s.project_slug.trim();
    if (scopedSessionId) return shortId(scopedSessionId);
    return 'all governed sessions';
  })();

  // ---- the arc: derive live, or fall back to the deterministic mock ---------
  // A purely reactive RE-DERIVE (no timer): the feed/flag/scope drive it.
  let usedMockData = false;
  /** @type {ReturnType<typeof deriveStory>} */
  let story = emptyStory();
  /** @type {Array<Record<string, any>>} */
  let evidenceRows = [];

  function emptyStory() {
    return {
      session_id: '',
      tone: 'clean',
      decision_count: 0,
      narrative_composed_at: null,
      narrative_model: null,
      paragraphs: [],
      mock: false,
      source: 'derived',
    };
  }

  // The composed/empty UI mode: when there is a story (live-derived OR a
  // server/mock one already loaded) we render the arc; otherwise the empty
  // "Compose Story" affordance.
  let composed = false;
  // The mock arc is only painted after an explicit Compose (so the empty state
  // is reachable in tests); live-derived arcs paint immediately.
  let mockComposed = false;
  // Compose job status walks pending -> running -> complete (client-side mock of
  // the async poll; no in-process spawn -- the heavy path is the CLI deferral).
  /** @type {''|'pending'|'running'|'complete'} */
  let composeStatus = '';
  /** @type {ReturnType<typeof setTimeout>[]} */
  let composeTimers = [];

  function recompute() {
    if (!enabled || isSelfScope) {
      story = emptyStory();
      evidenceRows = [];
      usedMockData = false;
      composed = false;
      return;
    }
    if (scopedRows.length > 0) {
      // Live-derived arc -- always available, painted immediately.
      story = deriveStory(scopedRows, { sessionId: scopedSessionId || '' });
      evidenceRows = scopedRows;
      usedMockData = false;
      composed = true;
      return;
    }
    // No live rows in scope. Show the empty "Compose" affordance UNTIL the
    // operator composes; then paint the deterministic mock arc (so the
    // bi-directional jump + tone are demonstrable with an empty gov.db).
    usedMockData = true;
    if (allowMock && mockComposed) {
      story = mockStory(scopedSessionId || '');
      evidenceRows = mockRows(scopedSessionId || '');
      composed = true;
    } else {
      story = emptyStory();
      evidenceRows = allowMock ? mockRows(scopedSessionId || '') : [];
      composed = false;
    }
  }

  $: enabled, isSelfScope, scopedRows, allowMock, mockComposed, recompute();

  // The paired tone read (M4): the literal label + the one-line reason.
  $: toneMeta = TONE_MAP[story.tone] || TONE_MAP.clean;

  // The meta line (composed-at / model / count) -- only when a server/mock
  // narrative carries those; a purely derived live arc shows the count only.
  $: hasComposedMeta = !!(story.narrative_composed_at || story.narrative_model);

  // ---- bi-directional link state -------------------------------------------
  // activeIds: the decision_ids the operator last jumped to (rows stay
  // "linked" until another phrase is activated or Escape clears). reverseId: the
  // row currently hovered/focused (its referencing sentences reverse-underline).
  /** @type {number[]} */
  let activeIds = [];
  /** @type {number|null} */
  let reverseRowId = null;
  let statusMsg = '';

  /** @type {HTMLElement|null} */
  let rootEl = null;

  function isReduced() {
    if (typeof document === 'undefined') return false;
    const m = document.documentElement.getAttribute('data-motion');
    if (m === 'reduce') return true;
    if (m === 'allow') return false;
    return (
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    );
  }

  /**
   * Activate a linked phrase: highlight the matching evidence rows, scroll the
   * first into view, and move focus to it (focus follows the jump -- a keyboard
   * operator lands ON the evidence). Pure observability (M18).
   * @param {number[]} ids
   */
  async function activatePhrase(ids) {
    const valid = (Array.isArray(ids) ? ids : []).map(Number).filter((n) => Number.isFinite(n));
    activeIds = valid;
    if (valid.length === 0) {
      statusMsg = 'No decision evidence is linked to that phrase.';
      return;
    }
    await tick();
    const first = rootEl && rootEl.querySelector(`#ssp-row-${valid[0]}`);
    if (first && typeof first.scrollIntoView === 'function') {
      first.scrollIntoView({ behavior: isReduced() ? 'auto' : 'smooth', block: 'center' });
    }
    if (first && typeof first.focus === 'function') first.focus({ preventScroll: true });
    statusMsg = `Jumped to ${valid.length} linked decision row${valid.length === 1 ? '' : 's'}.`;
  }

  /** Is a decision row in the active (jumped-to) set? */
  function isLinked(id) {
    return activeIds.includes(Number(id));
  }

  /** Does a phrase's id-set include the currently reverse-highlighted row? */
  function isReversePhrase(ids) {
    if (reverseRowId == null) return false;
    return (Array.isArray(ids) ? ids : []).map(Number).includes(Number(reverseRowId));
  }

  function clearLinks() {
    activeIds = [];
    statusMsg = '';
  }

  // If the flag flips OFF (or scope changes) while links are active, clear them.
  $: if (!enabled || isSelfScope) {
    activeIds = [];
    reverseRowId = null;
  }

  // ---- compose flow (mock async; heavy path DEFERRED to CLI) ---------------
  function clearComposeTimers() {
    for (const t of composeTimers) clearTimeout(t);
    composeTimers = [];
  }

  /**
   * The "Compose Story" affordance. This DOES NOT spawn a subprocess / worker /
   * cron in-process (constrained-additive brief): it mocks the async pending ->
   * running -> complete poll client-side and then paints the deterministic mock
   * arc. The RICH (Sonnet) narrative is the documented "from CLI" deferral shown
   * beside this button -- never built in-process here.
   */
  function startCompose() {
    if (composeStatus === 'pending' || composeStatus === 'running') return;
    clearComposeTimers();
    composeStatus = 'pending';
    statusMsg = 'Compose job queued (status: pending). Polling story-result...';
    composeTimers.push(
      setTimeout(() => {
        composeStatus = 'running';
        statusMsg = 'Composing (status: running)...';
      }, 700),
    );
    composeTimers.push(
      setTimeout(() => {
        composeStatus = 'complete';
        mockComposed = true; // triggers recompute() -> paints the mock arc
        statusMsg = `Session story composed -- tone: ${toneLabel(mockStory(scopedSessionId || '').tone).toLowerCase()}.`;
      }, 1800),
    );
  }

  onDestroy(() => {
    clearComposeTimers();
  });

  // Resolve the self-exclude identity once at DOM-ready (meta is server-injected).
  onMount(() => {
    ownSessionId = getOwnSessionId() || '';
    recompute();
  });
</script>

{#if enabled}
  <section
    class="ssp"
    aria-label="Session story (BETA) -- narrative arc with bi-directional feed linking"
    bind:this={rootEl}
  >
    {#if isSelfScope}
      <!-- G2 / M15: SM never narrates its own session. No arc. -->
      <p class="ssp__self" role="note">self -- excluded (G2): the SM own session is never narrated.</p>
    {:else}
      <!-- ===== STORY CARD ===== -->
      <div class="ssp__card">
        <div class="ssp__top">
          <div class="ssp__label-wrap">
            <span class="ssp__eyebrow">Session story</span>
            <h2 class="ssp__title">{scopeName}</h2>
            <span
              class="ssp__tide"
              class:ssp__tide--composing={composeStatus === 'pending' || composeStatus === 'running'}
              aria-hidden="true"
            ></span>
          </div>
          {#if composed}
            <div class="ssp__tone">
              <Badge variant={toneMeta.variant} label={toneMeta.label} reason={toneMeta.reason} />
            </div>
          {/if}
        </div>

        <p class="ssp__beta-caption">BETA -- default OFF, toggled in Settings &gt; BETA features</p>

        {#if composed}
          <!-- ===== rendered arc: paragraphs with linked phrases ===== -->
          <div class="ssp__body">
            {#each story.paragraphs as para, pi}
              <p class="ssp__para">
                {#each para as seg, si}
                  {#if seg.t !== undefined}{seg.t}{:else if seg.noevidence}<span
                      class="ssp__nlink ssp__nlink--noevidence"
                      title="no decision evidence -- nothing to jump to"
                      >{seg.phrase}</span
                    >{:else}<button
                      type="button"
                      class="ssp__nlink"
                      class:ssp__nlink--reverse={isReversePhrase(seg.ids)}
                      data-ids={(seg.ids || []).join(',')}
                      aria-label={`${seg.phrase} -- jump to the ${(seg.ids || []).length} matching decision row${(seg.ids || []).length === 1 ? '' : 's'}`}
                      on:click={() => activatePhrase(seg.ids)}
                      >{seg.phrase}</button
                    >{/if}
                {/each}
              </p>
            {/each}
          </div>

          <div class="ssp__meta">
            {#if hasComposedMeta}
              {#if story.narrative_composed_at}
                <span>composed <b>{fmtComposed(story.narrative_composed_at)}</b></span>
              {/if}
              {#if story.narrative_model}
                <span>model <b>{story.narrative_model}</b></span>
              {/if}
            {/if}
            <span><b>{story.decision_count}</b> decision{story.decision_count === 1 ? '' : 's'}</span>
            {#if activeIds.length}
              <button type="button" class="ssp__clear" on:click={clearLinks}>Clear link</button>
            {/if}
          </div>
        {:else}
          <!-- ===== EMPTY state ("still unwritten") + Compose affordance ===== -->
          {#if composeStatus === 'pending' || composeStatus === 'running'}
            <button type="button" class="ssp__compose" disabled aria-busy="true">Composing...</button>
            <p class="ssp__composing-note">
              Composing this session's arc client-side. The richer Sonnet narrative is composed
              off the verdict hot path -- see the CLI affordance below.
            </p>
          {:else}
            <p class="ssp__empty">
              Still unwritten. Compose this session's story to turn its decision rows into a
              one-glance, evidence-linked arc.
            </p>
            <button
              type="button"
              class="ssp__compose"
              on:click={startCompose}
              aria-label="Compose this session's story"
            >
              <span aria-hidden="true">+</span> Compose Story
            </button>
          {/if}

          <!-- DEFERRED heavy path (constrained-additive): NOT built in-process. -->
          <p class="ssp__cli-note">
            Rich narrative (Sonnet) is composed OUT of process. Run it from the CLI:
            <code>python -m stream_manager.tools.compose_story --session &lt;id&gt;</code>
            -- this panel reads the persisted result when present and otherwise shows the
            always-available client-side arc above.
          </p>
        {/if}

        {#if usedMockData}
          <p class="ssp__mock" title="No live decisions in scope yet -- showing a representative arc so the panel is inspectable.">
            SAMPLE DATA -- no live decisions in scope yet
          </p>
        {/if}

        <!-- aria-live: announces the tone / the jump the moment it happens -->
        <p class="ssp__status" aria-live="polite">{statusMsg}</p>
      </div>

      <!-- ===== EVIDENCE: the decision rows the arc links into ===== -->
      {#if composed && evidenceRows.length}
        <div class="ssp__evidence">
          <div class="ssp__evidence-head">
            <h3 class="ssp__evidence-title">Linked decisions</h3>
            <span class="ssp__evidence-tide" aria-hidden="true"></span>
          </div>
          <ol class="ssp__rows" aria-label={`Decisions in ${scopeName}, newest first`}>
            {#each evidenceRows as r (r.id ?? r.rid)}
              {@const act = actionOf(r)}
              {@const rid = Number(r.id ?? r.rid)}
              {@const rb = badgeForAction(act)}
              {@const pct = confPct(r.confidence)}
              <li class="ssp__row-item">
                <article
                  id={`ssp-row-${rid}`}
                  class="ssp__row"
                  class:ssp__row--linked={isLinked(rid)}
                  class:ssp__row--escalation={act === 'BLOCK'}
                  data-id={rid}
                  tabindex="-1"
                  aria-label={`${act} decision, ${pct}% confidence${isLinked(rid) ? ' -- linked from the story above' : ''}`}
                  on:mouseenter={() => (reverseRowId = rid)}
                  on:mouseleave={() => (reverseRowId = null)}
                  on:focus={() => (reverseRowId = rid)}
                  on:blur={() => (reverseRowId = null)}
                >
                  <div class="ssp__row-head">
                    <span class="ssp__row-ts">{r.timestamp ?? ''}</span>
                    <span
                      class="ssp__row-action ssp__row-action--{act}"
                      data-weight={weightForAction(act)}
                      title={`Action: ${act}`}>{act}</span
                    >
                    <span class="ssp__row-badge">
                      <Badge
                        variant={rb.variant}
                        label={rb.label}
                        reason={`Observing -- ${act} decision recorded (${pct}% confidence)`}
                      />
                    </span>
                    {#if r.layer !== undefined && r.layer !== null}
                      <span class="ssp__row-layer">L{r.layer}</span>
                    {/if}
                    <span class="ssp__row-conf">
                      <span class="ssp__row-conf-bar" aria-hidden="true">
                        <span class="ssp__row-conf-fill" style={`width:${pct}%`}></span>
                      </span>
                      <span class="ssp__row-conf-num">{pct}%</span>
                    </span>
                  </div>
                  <div class="ssp__row-body">
                    <p class="ssp__row-content">{r.content ?? ''}</p>
                    {#if r.reasoning}
                      <p class="ssp__row-reason">{r.reasoning}</p>
                    {/if}
                  </div>
                </article>
              </li>
            {/each}
          </ol>
        </div>
      {/if}
    {/if}
  </section>
{/if}

<style>
  /* ==========================================================================
     SESSION STORY CARD -- anti-generic: a left ACCENT SPINE is the only chrome;
     the rest is type + whitespace. Mirrors the approved mockup verbatim, on
     theme.css tokens (with calm-* / --accent / --text* fallbacks).
     ========================================================================== */
  .ssp {
    display: block;
    font-family: var(--ff-system);
    margin-bottom: var(--space-4, 10px);
  }

  .ssp__card {
    position: relative;
    padding: var(--space-5, 14px) var(--space-5, 14px) var(--space-4, 10px) var(--space-6, 22px);
    background: transparent;
  }
  /* left accent spine -- the only chrome (2px, near-full height) */
  .ssp__card::before {
    content: '';
    position: absolute;
    left: 0;
    top: 4px;
    bottom: 4px;
    width: 2px;
    background: var(--calm-accent, var(--accent, #f59e0b));
    opacity: 0.85;
    border-radius: 2px;
  }

  .ssp__top {
    display: flex;
    align-items: flex-start;
    gap: var(--space-5, 14px);
  }
  .ssp__label-wrap {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
  }
  .ssp__eyebrow {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .ssp__title {
    margin: 0;
    font-family: var(--font-h, var(--ff-system));
    font-size: 1.5rem;
    font-weight: 600;
    line-height: 1.05;
    letter-spacing: 0.005em;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  /* bespoke tide-line under the title (mirrors ReplStream .repl__tide) */
  .ssp__tide {
    height: 2px;
    width: 2.5rem;
    background: var(--calm-accent, var(--accent, #f59e0b));
    opacity: 0.55;
    border-radius: 2px;
    margin-top: 2px;
  }
  .ssp__tone {
    margin-left: auto;
    flex: 0 0 auto;
  }
  /* the TONE badge is the at-a-glance hero -- bump it a hair. */
  .ssp__tone :global(.ar-badge) {
    font-size: 12.5px;
    padding: 5px 11px;
  }

  .ssp__beta-caption {
    margin: 9px 0 0;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }

  /* the rendered narrative -- comfortable measure, calm resting weight */
  .ssp__body {
    max-width: 62ch;
    margin: 14px 0 0;
  }
  .ssp__para {
    margin: 0 0 11px;
    font-size: 0.92rem;
    line-height: 1.6;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
  }
  .ssp__para:last-child {
    margin-bottom: 0;
  }

  /* a linked phrase: a real <button>, dotted underline (non-color affordance) */
  .ssp__nlink {
    appearance: none;
    background: transparent;
    border: 0;
    padding: 0 0.05em;
    margin: 0;
    font: inherit;
    color: inherit;
    cursor: pointer;
    text-decoration: underline;
    text-decoration-style: dotted;
    text-decoration-thickness: 1.5px;
    text-underline-offset: 3px;
    text-decoration-color: var(--calm-accent, var(--accent, #f59e0b));
    border-radius: 2px;
  }
  .ssp__nlink:hover {
    color: var(--calm-accent, var(--accent, #f59e0b));
  }
  .ssp__nlink:focus-visible {
    outline: 2px solid var(--calm-accent, var(--accent, #f59e0b));
    outline-offset: 2px;
  }
  /* reverse-highlight: a row hover/focus underlines the referencing sentence */
  .ssp__nlink--reverse {
    background: var(--accent-dim, rgba(245, 158, 11, 0.09));
    color: var(--calm-accent, var(--accent, #f59e0b));
    text-decoration-style: solid;
  }
  /* the "no evidence" phrase (ids: []) reads as plain, not a link */
  .ssp__nlink--noevidence {
    cursor: default;
    text-decoration-style: dashed;
    text-decoration-color: var(--calm-ink-quiet, var(--text-dim, #948870));
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .ssp__nlink--noevidence:hover {
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }

  /* whisper-quiet meta line at the bottom (composed-at / model / count) */
  .ssp__meta {
    margin-top: 15px;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px 18px;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    letter-spacing: 0.04em;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .ssp__meta b {
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    font-weight: 600;
  }
  .ssp__clear {
    appearance: none;
    background: transparent;
    border: 1px solid var(--calm-hairline, var(--border, #192030));
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    border-radius: 3px;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    letter-spacing: 0.04em;
    padding: 1px 7px;
    cursor: pointer;
  }
  .ssp__clear:focus-visible {
    outline: 2px solid var(--calm-accent, var(--accent, #f59e0b));
    outline-offset: 2px;
  }

  /* -- EMPTY state + Compose affordance + CLI deferral note ----------------- */
  .ssp__empty {
    margin: 11px 0 0;
    font-size: 0.92rem;
    font-style: italic;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    max-width: 60ch;
  }
  .ssp__compose {
    appearance: none;
    margin-top: 14px;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: transparent;
    border: 1px solid var(--calm-hairline, var(--border, #192030));
    color: var(--calm-ink, var(--text, #b8b098));
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.72rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 8px 15px;
    border-radius: 6px;
    cursor: pointer;
    transition: color 0.18s ease, border-color 0.18s ease;
  }
  .ssp__compose:hover:not([disabled]) {
    color: var(--calm-accent, var(--accent, #f59e0b));
    border-color: var(--calm-accent, var(--accent, #f59e0b));
  }
  .ssp__compose:focus-visible {
    outline: 2px solid var(--calm-accent, var(--accent, #f59e0b));
    outline-offset: 2px;
  }
  .ssp__compose[disabled] {
    cursor: progress;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .ssp__composing-note {
    margin: 12px 0 0;
    font-size: 0.86rem;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    font-style: italic;
  }
  .ssp__cli-note {
    margin: 14px 0 0;
    font-size: 0.78rem;
    line-height: 1.5;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    max-width: 62ch;
  }
  .ssp__cli-note code {
    font-family: var(--font-d, var(--ff-mono));
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    font-size: 0.74rem;
    word-break: break-all;
  }

  /* composing tide-line shimmer (reduced-motion: static accent bar). */
  .ssp__tide--composing {
    width: 100%;
    max-width: 18rem;
    background: linear-gradient(
      90deg,
      transparent 0%,
      var(--calm-accent, var(--accent, #f59e0b)) 50%,
      transparent 100%
    );
    background-size: 200% 100%;
    opacity: 0.7;
    animation: sspTide 1.8s linear infinite;
  }
  @keyframes sspTide {
    from {
      background-position: 200% 0;
    }
    to {
      background-position: -200% 0;
    }
  }
  :global(html[data-motion='reduce']) .ssp__tide--composing {
    animation: none;
    background: var(--calm-accent, var(--accent, #f59e0b));
  }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .ssp__tide--composing {
      animation: none;
      background: var(--calm-accent, var(--accent, #f59e0b));
    }
  }

  .ssp__mock {
    margin: 13px 0 0;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    letter-spacing: 0.04em;
    color: var(--badge-ar-fg, #d97706);
    text-transform: uppercase;
  }

  .ssp__self {
    margin: 0;
    padding: var(--space-4, 10px) var(--space-5, 14px);
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-meta, 13px);
    font-style: italic;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }

  /* aria-live status -- visually present but quiet. */
  .ssp__status {
    margin: 10px 0 0;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px;
    letter-spacing: 0.04em;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    min-height: 1em;
  }

  /* ==========================================================================
     EVIDENCE -- the decision rows the arc links into (DecisionRow-like).
     ========================================================================== */
  .ssp__evidence {
    margin-top: var(--space-4, 10px);
    padding-top: var(--space-4, 10px);
    border-top: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
  }
  .ssp__evidence-head {
    display: flex;
    align-items: baseline;
    gap: 14px;
    margin-bottom: var(--space-3, 6px);
  }
  .ssp__evidence-title {
    margin: 0;
    font-family: var(--font-h, var(--ff-system));
    font-weight: 460;
    font-size: 0.9rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--calm-ink, var(--text, #b8b098));
  }
  .ssp__evidence-tide {
    height: 1px;
    width: 2.5rem;
    background: var(--calm-accent, var(--accent, #f59e0b));
    opacity: 0.5;
  }

  .ssp__rows {
    list-style: none;
    margin: var(--space-3, 6px) 0 0;
    padding: 0;
  }
  .ssp__row-item + .ssp__row-item {
    margin-top: var(--space-2, 4px);
  }

  .ssp__row {
    display: grid;
    grid-template-columns: 1fr;
    gap: 5px;
    padding: 9px 11px 8px;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-left-width: 2px;
    border-left-color: transparent;
    border-radius: 7px;
    background: var(--calm-surface-row, var(--bg-row, #0e141e));
    transition: border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
    scroll-margin: 90px;
  }
  .ssp__row:hover {
    background: var(--bg-row-hover, #131c2a);
  }
  .ssp__row--escalation {
    border-left-color: #d97706;
    background: var(--bg-row-flash, rgba(245, 158, 11, 0.09));
  }
  /* the bi-directional jump target: a persistent accent ring + spine while
     linked, plus a 1.2s flash pulse on activation (reduced-motion: static). */
  .ssp__row--linked {
    border-left-color: var(--calm-accent, var(--accent, #f59e0b));
    background: var(--bg-row-flash, rgba(245, 158, 11, 0.09));
    box-shadow: 0 0 0 1px var(--calm-accent, var(--accent, #f59e0b)) inset;
    animation: sspRowFlash 1.2s ease-out 1;
  }
  @keyframes sspRowFlash {
    0% {
      box-shadow: 0 0 0 2px var(--calm-accent, var(--accent, #f59e0b)) inset;
    }
    100% {
      box-shadow: 0 0 0 1px var(--calm-accent, var(--accent, #f59e0b)) inset;
    }
  }
  :global(html[data-motion='reduce']) .ssp__row--linked {
    animation: none;
    box-shadow: 0 0 0 1px var(--calm-accent, var(--accent, #f59e0b)) inset;
  }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .ssp__row--linked {
      animation: none;
      box-shadow: 0 0 0 1px var(--calm-accent, var(--accent, #f59e0b)) inset;
    }
  }
  .ssp__row:focus-visible {
    outline: 2px solid var(--calm-accent, var(--accent, #f59e0b));
    outline-offset: 2px;
  }

  .ssp__row-head {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 5px 10px;
  }
  .ssp__row-ts {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.7rem;
    font-variant-numeric: tabular-nums;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    flex: 0 0 auto;
  }
  .ssp__row-action {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.72rem;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    flex: 0 0 auto;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .ssp__row-action[data-weight='calm'] {
    font-weight: 400;
  }
  .ssp__row-action[data-weight='notice'] {
    font-weight: 500;
  }
  .ssp__row-action[data-weight='signal'] {
    font-weight: 600;
  }
  .ssp__row-action[data-weight='urgent'] {
    font-weight: 700;
  }
  .ssp__row-action--ALLOW {
    color: var(--c-allow, #22c55e);
  }
  .ssp__row-action--SUGGEST {
    color: var(--c-suggest, #84cc16);
  }
  .ssp__row-action--GUIDE {
    color: var(--c-guide, #eab308);
  }
  .ssp__row-action--INTERVENE {
    color: var(--c-intervene, #f97316);
  }
  .ssp__row-action--BLOCK {
    color: var(--c-block, #ef4444);
  }
  .ssp__row-layer {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.66rem;
    letter-spacing: 0.04em;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    border: 1px solid var(--calm-hairline, var(--border, #192030));
    border-radius: 3px;
    padding: 1px 5px;
    flex: 0 0 auto;
  }
  .ssp__row-conf {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin-left: auto;
    flex: 0 0 auto;
  }
  .ssp__row-conf-bar {
    width: 3.5rem;
    height: 5px;
    border-radius: 999px;
    background: var(--calm-hairline, var(--border, #192030));
    overflow: hidden;
  }
  .ssp__row-conf-fill {
    display: block;
    height: 100%;
    background: var(--calm-accent, var(--accent, #f59e0b));
    border-radius: 999px;
  }
  .ssp__row-conf-num {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.68rem;
    font-variant-numeric: tabular-nums;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    min-width: 2.6ch;
    text-align: right;
  }
  .ssp__row-body {
    min-width: 0;
  }
  .ssp__row-content {
    margin: 0;
    font-size: 0.82rem;
    line-height: 1.35;
    color: var(--calm-ink, var(--text, #b8b098));
  }
  .ssp__row-reason {
    margin: 2px 0 0;
    font-size: 0.72rem;
    line-height: 1.3;
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }

  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .ssp__row {
      transition: none;
    }
  }
  :global(html[data-motion='reduce']) .ssp__row {
    transition: none;
  }
</style>
