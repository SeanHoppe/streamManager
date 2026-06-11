<script context="module">
  // SessionMirror.svelte -- the collapsible terminal-style tool-activity stream
  // scoped to the operator's selected session, self-excluded (M15).
  //
  // BEHAVIOURAL CONTRACT (preserved from the live Session Mirror, Task C):
  //  - Terminal-style rows: `[hh:mm:ss.mmm] $ <kind>: <args>`. `kind` is
  //    derived (tool_result / tool_use_result -> tool_result; else the
  //    metadata tool_name|role; else tool_call), and tool_result rows tint
  //    differently. The kind string is ALWAYS rendered as TEXT (M4 spirit).
  //  - 200-entry cap, PAUSE (freeze ingestion) + CLEAR controls, default
  //    COLLAPSED (SHOW/HIDE).
  //  - Scoped to the SELECTED session only: when no session is selected the
  //    mirror shows a quiet "select a session" prompt (the live mirror only
  //    streams when a session is chosen).
  //  - M15 hard self-exclude: rows whose session_id is the SM's own session id
  //    are dropped (defense-in-depth; the server already strips them).
  //    Empty/missing own-id => skip filtering (loud-fail-safe).
  //
  // M16 (domain-agnostic): kind + args + session render from DATA; no
  // monitored-project vocabulary is hard-coded. M18: post-hoc; consumes the
  // shared eventsStore (and an optional injected rows prop), no own transport.
  //
  // CRAFT (calm-ambient): a quiet monospace terminal lane, paused-tag, and a
  // gentle prompt glyph -- still water until tool activity flows.

  const MIRROR_MAX = 200;

  /** Tool-activity event types this mirror surfaces (frozen contract). */
  export const MIRROR_EVENT_TYPES = Object.freeze(
    new Set(['tool_call', 'tool_result', 'tool_use', 'tool_use_result']),
  );

  /**
   * Derive the terminal "kind" token for a tool-activity event. Mirrors the
   * live deriveKind() exactly. Domain-agnostic: reads metadata tool_name/role
   * from DATA, never a hard-coded governed-target name.
   * @param {Record<string, any>} ev
   * @returns {string}
   */
  export function deriveKind(ev) {
    const t = ev && (ev.event_type || ev.type);
    if (t === 'tool_result' || t === 'tool_use_result') return 'tool_result';
    try {
      const meta =
        typeof ev.metadata === 'string' ? JSON.parse(ev.metadata) : ev.metadata || {};
      const tn = String(meta.tool_name || meta.role || '').toLowerCase();
      if (tn) return tn;
    } catch (_e) {
      /* malformed metadata -- fall through to the default kind */
    }
    return 'tool_call';
  }

  /** Is this event tool-activity the mirror should surface? */
  export function isMirrorEvent(ev) {
    if (!ev || typeof ev !== 'object') return false;
    const t = ev.event_type || ev.type;
    return MIRROR_EVENT_TYPES.has(t);
  }
</script>

<script>
  import { eventsStore } from '../sse.js';
  import { selectedSessionId, selectedSession, getOwnSessionId } from '../stores/session.js';
  import { makeSelfExcludeFilter } from '../selfExclude.js';

  /** Default-collapsed (matches the live mirror default). */
  export let open = false;

  /**
   * rows: an OPTIONAL injected mirror feed. When the composing App wires a
   * dedicated tool-activity store it can pass it here; otherwise the mirror
   * derives tool activity from the shared eventsStore. Either way the same
   * self-exclude + session-scope + cap rules apply.
   * @type {Array<Record<string, any>>|null}
   */
  export let rows = null;

  let paused = false;
  let frozen = null;
  /** Per-panel clear cutoff (view-only; does not mutate the shared store). */
  let cleared = new Set();

  // M15 hard self-exclude predicate.
  $: selfFilter = makeSelfExcludeFilter(getOwnSessionId() || '');
  $: scopeId = $selectedSessionId;
  $: sess = $selectedSession;
  $: sessLabel = sess
    ? sess.project_slug || (sess.id ? String(sess.id).slice(0, 8) : 'session')
    : '';

  // Source rows: the injected feed if provided, else the tool-activity subset
  // of the shared eventsStore.
  $: sourceRows = Array.isArray(rows)
    ? rows
    : $eventsStore.filter(isMirrorEvent);

  // The live, contract-filtered mirror rows: tool-activity, self-excluded,
  // scoped to the SELECTED session ONLY (the mirror does not run unscoped),
  // cleared-aware, capped, oldest-first (terminal append order).
  $: liveRows =
    scopeId == null
      ? []
      : sourceRows
          .filter(selfFilter)
          .filter((r) => r.session_id === scopeId)
          .filter((r) => !cleared.has(rowKey(r)))
          .slice(0, MIRROR_MAX)
          .slice()
          .reverse();

  $: shown = paused && frozen ? frozen : liveRows;

  function rowKey(r) {
    return `${r.event_type || r.type || ''}:${r.timestamp ?? ''}:${(r.content || '').slice(0, 24)}`;
  }

  function togglePanel() { open = !open; }
  function togglePause() {
    paused = !paused;
    frozen = paused ? liveRows.slice() : null;
  }
  function clearAll() {
    const next = new Set(cleared);
    for (const r of sourceRows) next.add(rowKey(r));
    cleared = next;
    if (paused) frozen = [];
  }

  function fmtTs(t) {
    const d = typeof t === 'number' ? new Date(t * 1000) : new Date(t);
    if (Number.isNaN(d.getTime())) return '--:--:--.---';
    const pad = (n, w = 2) => String(n).padStart(w, '0');
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`;
  }
  function clipArgs(s, n = 80) {
    return String(s || '').slice(0, n);
  }
</script>

<section class="mir" class:mir--open={open} class:mir--paused={paused} aria-label="Session mirror">
  <header class="mir__head">
    <span class="mir__title">Session mirror</span>
    <span class="mir__sess" title={sess ? sess.id : 'no session selected'}>
      {sessLabel || '-'}
    </span>
    {#if paused}<span class="mir__paused-tag" aria-hidden="true">PAUSED</span>{/if}

    <div class="mir__controls" role="group" aria-label="Mirror controls">
      <button
        type="button"
        class="mir__btn"
        class:mir__btn--on={paused}
        aria-pressed={paused}
        on:click={togglePause}
        title={paused ? 'Resume tool-activity ingestion' : 'Pause tool-activity ingestion'}
      >{paused ? 'Paused' : 'Pause'}</button>
      <button
        type="button"
        class="mir__btn"
        on:click={clearAll}
        title="Clear all mirror entries"
      >Clear</button>
      <button
        type="button"
        class="mir__btn mir__btn--toggle"
        aria-expanded={open}
        on:click={togglePanel}
        title={open ? 'Hide the mirror' : 'Show the mirror'}
      >{open ? 'Hide' : 'Show'}</button>
    </div>
  </header>

  {#if open}
    <div class="mir__body" tabindex="0" role="log" aria-live="polite" aria-label="Tool activity, newest last">
      {#if scopeId == null}
        <p class="mir__empty" role="status">Select a session to mirror its tool activity.</p>
      {:else if shown.length === 0}
        <p class="mir__empty" role="status">No tool activity yet.</p>
      {:else}
        {#each shown as ev (rowKey(ev))}
          {@const kind = deriveKind(ev)}
          <div class="mir__row" data-kind={kind}>
            <span class="mir__ts">[{fmtTs(ev.timestamp)}]</span>
            <span class="mir__prompt" aria-hidden="true">$</span>
            <span class="mir__kind">{kind}</span><span class="mir__sep" aria-hidden="true">:</span>
            <span class="mir__args">{clipArgs(ev.content)}</span>
          </div>
        {/each}
      {/if}
    </div>
  {/if}
</section>

<style>
  .mir {
    border: 1px solid var(--border, rgba(148, 163, 184, 0.18));
    border-radius: 8px;
    background: var(--bg-card, rgba(8, 10, 12, 0.6));
    overflow: hidden;
  }

  .mir__head {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.35rem 0.5rem;
  }
  .mir__title {
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.66rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-ui, #8a8068);
  }
  .mir__sess {
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.64rem;
    color: var(--text-dim, #94a3b8);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 16ch;
  }
  .mir__paused-tag {
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.58rem;
    letter-spacing: 0.1em;
    color: var(--c-guide, #eab308);
    border: 1px solid var(--c-guide, #eab308);
    border-radius: 3px;
    padding: 0.02rem 0.3rem;
  }

  .mir__controls { display: inline-flex; gap: 0.3rem; margin-left: auto; }
  .mir__btn {
    appearance: none;
    border: 1px solid var(--border, rgba(148, 163, 184, 0.3));
    background: transparent;
    color: var(--text-dim, #94a3b8);
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.62rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    padding: 0.18rem 0.5rem;
    border-radius: 4px;
    cursor: pointer;
    transition: color 0.16s ease, border-color 0.16s ease;
  }
  .mir__btn:hover { color: var(--text, #e2e8f0); border-color: var(--text-dim, #94a3b8); }
  .mir__btn--on { color: var(--c-guide, #eab308); border-color: var(--c-guide, #eab308); }

  /* M17 amber focus ring on every interactive element. */
  .mir__btn:focus-visible { outline: 2px solid #d97706; outline-offset: 2px; }

  .mir__body {
    max-height: 16rem;
    overflow-y: auto;
    overscroll-behavior: contain;
    border-top: 1px solid var(--border, rgba(148, 163, 184, 0.15));
    padding: 0.35rem 0.6rem 0.5rem;
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.7rem;
    line-height: 1.5;
  }
  .mir__body:focus-visible { outline: 2px solid #d97706; outline-offset: -2px; }

  .mir__row {
    color: var(--text, #e2e8f0);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .mir__ts { color: var(--text-dim, #94a3b8); }
  .mir__prompt { color: var(--accent, #38bdf8); margin: 0 0.25rem; }
  .mir__kind { color: var(--text-bright, #e8e0cc); font-weight: 600; }
  /* tool_result rows tint their kind differently (mirrors the live rule). */
  .mir__row[data-kind='tool_result'] .mir__kind { color: var(--c-allow, #22c55e); }
  .mir__sep { color: var(--text-dim, #94a3b8); margin-right: 0.35rem; }
  .mir__args { color: var(--text-dim, #94a3b8); }

  .mir__empty {
    margin: 0.4rem 0;
    color: var(--text-dim, #94a3b8);
    font-size: 0.72rem;
    font-style: italic;
    text-align: center;
    opacity: 0.85;
  }

  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .mir__btn { transition: none; }
  }
</style>
