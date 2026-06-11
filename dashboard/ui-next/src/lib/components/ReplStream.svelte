<script>
  // ReplStream.svelte -- Frame A's calm decision/REPL stream.
  //
  // The "still water" verdict stream: it SEEDS from GET /api/decisions, then
  // subscribes to the live decisionsStore (fed by the single /events SSE
  // connection in u-stores). It renders newest-first DecisionRow atoms, scoped
  // to the operator's selected session.
  //
  // CONTRACT:
  //  - M15 (self-exclude): the seed AND the live store are both filtered to
  //    drop the SM's own session_id (defense-in-depth: u-stores already strips
  //    self in seedDecisions/pushDecision; this is the redundant client layer).
  //    Empty/missing own-id => skip filtering (loud-fail-safe).
  //  - M16 (domain-agnostic): scoping is by session_id from data; no governed-
  //    target vocabulary is hard-coded. The "ALL sessions" affordance and the
  //    selected-session scope both come from the session store.
  //  - M18 (latency budget): this is post-hoc observability. The ONLY network
  //    call is the seed GET (and an optional manual re-seed); the live feed
  //    arrives via the shared SSE store. Nothing here sits on the verdict hot
  //    path or opens /api/commands/stream.
  //  - M7 hook: each row's Take-action intent bubbles up via `takeaction` so
  //    u-hitl-core can promote the session to HITL ON SYNC. ReplStream never
  //    flips HITL state itself.
  //
  // CRAFT (calm-ambient): an asymmetric "tide line" header, whisper-quiet
  // metadata, and a still-water empty state. Severity is carried by the rows'
  // type-weight, not by stream chrome.

  import { onMount, onDestroy, createEventDispatcher } from 'svelte';
  import { get } from 'svelte/store';
  import DecisionRow from './DecisionRow.svelte';
  import { decisionsStore, connectionState } from '../sse.js';
  import { getDecisions } from '../api.js';
  import { selectedSessionId, selectedSession, getOwnSessionId } from '../stores/session.js';
  import { makeSelfExcludeFilter } from '../selfExclude.js';

  const dispatch = createEventDispatcher();

  /**
   * hitlOn: whether the currently selected session is in HITL ON (threaded
   * from the composing App / u-hitl-core). Controls each row's read-only vs
   * Take-action affordance (M7). Default OFF => rows render the opt-in.
   */
  export let hitlOn = false;

  /**
   * advisoryByDecisionId: optional map of decisionId -> Learn-Mode advisory
   * bias (M8). Threaded from u-hitl-core when a bias pre-fill exists for a
   * row. Empty by default. The chip is informational only, never a verdict.
   * @type {Record<string|number, any>}
   */
  export let advisoryByDecisionId = {};

  /** Max rows rendered (mirrors the store cap; defensive second clamp). */
  const RENDER_CAP = 300;

  let seedError = '';
  let seeding = true;

  // -- Self-exclude predicate (M15), bound once to the resolved own id -------
  $: selfFilter = makeSelfExcludeFilter(getOwnSessionId() || '');

  // -- Session scope (M16): when a session is selected, show only its rows; --
  //    null selection == ALL governed sessions.
  $: scopeId = $selectedSessionId;

  // The visible rows: self-excluded, scoped to the selection, newest-first,
  // capped. Derived purely from the store -- no mutation.
  $: visibleRows = $decisionsStore
    .filter(selfFilter)
    .filter((r) => scopeId == null || r.session_id === scopeId)
    .slice(0, RENDER_CAP);

  $: connLabel =
    $connectionState === 'open'
      ? 'live'
      : $connectionState === 'reconnecting'
        ? 'reconnecting'
        : 'connecting';

  // Domain-agnostic scope label (M16): rendered from data, never hard-coded.
  $: scopeLabel = scopeId == null
    ? 'all governed sessions'
    : `session ${String(scopeId).slice(0, 8)}`;

  // -- Seed from /api/decisions ----------------------------------------------
  // Re-seed when the selected session changes so the stream re-scopes promptly
  // (the live SSE store is global; we just refresh the seed snapshot for the
  // scope so the operator isn't waiting on the next event for that session).
  let _lastSeedScope = Symbol('init');
  $: maybeSeed(scopeId);

  async function maybeSeed(scope) {
    if (scope === _lastSeedScope) return;
    _lastSeedScope = scope;
    await seed(scope);
  }

  async function seed(scope) {
    seeding = true;
    seedError = '';
    try {
      const rows = await getDecisions({ limit: RENDER_CAP, session_id: scope ?? undefined });
      // Merge the seed into the store ONLY when the live store is still empty
      // for this scope; otherwise the SSE store is authoritative and we leave
      // it alone (avoid clobbering newer live rows with an older snapshot).
      const cur = get(decisionsStore);
      if (!Array.isArray(cur) || cur.length === 0) {
        const own = getOwnSessionId() || '';
        const keep = makeSelfExcludeFilter(own);
        decisionsStore.set((Array.isArray(rows) ? rows : []).filter(keep).slice(0, RENDER_CAP));
      }
    } catch (e) {
      seedError = 'Could not load the decision history. Live updates still arrive over the stream.';
    } finally {
      seeding = false;
    }
  }

  function onTakeAction(e) {
    // M7: forward the opt-in intent up to u-hitl-core unchanged.
    dispatch('takeaction', e.detail);
  }

  onMount(() => { void maybeSeed(scopeId); });
  onDestroy(() => { /* the shared SSE store outlives this component */ });
</script>

<section class="repl" aria-label="Interactive decision stream">
  <header class="repl__head">
    <div class="repl__title-wrap">
      <h3 class="repl__title">Decision stream</h3>
      <span class="repl__tide" aria-hidden="true"></span>
    </div>
    <p class="repl__scope" aria-live="polite">
      observing <span class="repl__scope-em">{scopeLabel}</span>
    </p>
    <span
      class="repl__conn repl__conn--{$connectionState}"
      title={`Stream ${connLabel}`}
      aria-label={`Stream ${connLabel}`}
    >
      <span class="repl__conn-dot" aria-hidden="true"></span>
      <span class="repl__conn-text">{connLabel}</span>
    </span>
  </header>

  {#if seedError}
    <p class="repl__note repl__note--err" role="status">{seedError}</p>
  {/if}

  {#if visibleRows.length === 0}
    {#if seeding}
      <p class="repl__empty" role="status">Reading the decision history<span class="repl__dots" aria-hidden="true">...</span></p>
    {:else}
      <p class="repl__empty" role="status">Still water. No decisions in {scopeLabel} yet.</p>
    {/if}
  {:else}
    <ol class="repl__list" aria-label={`Decisions in ${scopeLabel}, newest first`}>
      {#each visibleRows as row (row.id ?? row.rid ?? `${row.message_id ?? ''}:${row.timestamp ?? ''}`)}
        <li class="repl__item">
          <DecisionRow
            {row}
            {hitlOn}
            advisoryBias={row.id != null ? (advisoryByDecisionId[row.id] || null) : null}
            on:takeaction={onTakeAction}
          />
        </li>
      {/each}
    </ol>
  {/if}
</section>

<style>
  .repl {
    display: flex;
    flex-direction: column;
    min-height: 0;
    gap: 0.5rem;
  }

  .repl__head {
    display: flex;
    align-items: baseline;
    gap: 0.85rem;
    flex-wrap: wrap;
    padding-bottom: 0.2rem;
  }

  .repl__title-wrap { display: inline-flex; flex-direction: column; gap: 0.2rem; }

  .repl__title {
    margin: 0;
    font-family: var(--font-h, var(--ff-system, system-ui, sans-serif));
    /* calm-ambient resting voice: low weight, wide tracking */
    font-weight: 460;
    font-size: 0.9rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text, #e2e8f0);
  }

  /* asymmetric tide line under the title -- bespoke, intentionally short */
  .repl__tide {
    height: 1px;
    width: 2.5rem;
    background: var(--accent, #38bdf8);
    opacity: 0.5;
  }

  .repl__scope {
    margin: 0;
    font-size: 0.72rem;
    color: var(--text-dim, #94a3b8);
    letter-spacing: 0.02em;
  }
  .repl__scope-em { color: var(--text-ui, #8a8068); font-weight: 600; }

  .repl__conn {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    margin-left: auto;
    font-size: 0.66rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-dim, #94a3b8);
  }
  .repl__conn-dot {
    width: 0.45rem; height: 0.45rem; border-radius: 50%;
    background: var(--text-dim, #94a3b8);
    flex: 0 0 auto;
  }
  .repl__conn--open .repl__conn-dot { background: var(--c-allow, #22c55e); }
  .repl__conn--reconnecting .repl__conn-dot { background: var(--c-guide, #eab308); }

  .repl__note {
    margin: 0;
    font-size: 0.72rem;
    padding: 0.3rem 0.5rem;
    border-radius: 5px;
  }
  .repl__note--err {
    color: var(--c-intervene, #f97316);
    border: 1px dashed var(--c-intervene, #f97316);
    background: transparent;
  }

  .repl__list {
    list-style: none;
    margin: 0;
    padding: 0;
    min-width: 0;
  }
  .repl__item { min-width: 0; }

  .repl__empty {
    margin: 0.5rem 0;
    color: var(--text-dim, #94a3b8);
    font-size: 0.82rem;
    font-style: italic;
    /* No opacity drag: --text-dim is the AA-documented dim token; compositing
       opacity on top pushes it under WCAG AA (axe color-contrast FAIL). */
  }
  .repl__dots { letter-spacing: 0.15em; }
</style>
