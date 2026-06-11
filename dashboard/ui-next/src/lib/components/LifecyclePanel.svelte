<!--
  LifecyclePanel.svelte -- Frame C background-jobs lifecycle (MUST M14).

  Renders the open BG jobs + spawned sub-agents lifecycle list. The frozen
  behavioural contract (Task C / v1.2 lifecycle bridge, live dashboard
  #lifecycleList) is PRESERVED while the FORM is re-architected into the
  still-water calm-ambient idiom:

    M14  Each row renders job/agent NAME, id/PID, STATUS (running/exited),
         ELAPSED, EXIT CODE. The source is GET /api/lifecycle/jobs?session_id,
         polled every 2s by the u-stores poller (lifecycleJobsStore), filtered
         by the selected session. This component is presentation-only -- it
         reads the store, it never fetches (the 2s cadence + session scope are
         owned by pollers.js). When rendered outside the wired app it accepts a
         `jobs` prop override so it is correct standalone.

    M4   Status is a PAIRED label+color badge (RUNNING / EXITED) -- color is
         never the sole signal. A non-zero exit code additionally surfaces as a
         BLOCKED-toned paired badge so a failed job is never color-only.

    M16  Domain-agnostic: every governed identifier (name, session_id, job_id,
         pid, kind) is rendered FROM DATA. No monitored-project vocabulary is
         hard-coded; `kind` is the server's own taxonomy string, surfaced
         verbatim, never mapped to a domain label.

    M15/G2  Self-exclude is enforced upstream (the poller scopes to the selected
         non-self session; the session store can never resolve to SM self). As
         defense-in-depth this panel also drops any row whose session_id equals
         the SM own-session id when that id is known.

    M18  Post-hoc observability only. The only timer here is a calm 1s elapsed
         re-clock for the live readout; it touches no verdict and is off the hot
         path. M19: no terminal/IDE surface -- just an observation list.

  CALM-AMBIENT (winning spine): the list is still water at rest -- a hairline
  per row, dim chrome, tabular telemetry columns. A RUNNING job breathes only
  via the shared calm live-dot; saturation/motion are reserved for true M2
  escalations elsewhere (this panel never escalates). Severity is carried by the
  variable-weight type scale (.sev-*), reinforced by -- never replaced by --
  the status badge text.

  File-disjoint: depends only on theme/calm tokens, Badge.svelte (shared M4
  primitive), the u-stores lifecycleJobsStore, and the session self-exclude id.
-->
<script>
  import { onDestroy } from 'svelte';
  import Badge from './Badge.svelte';
  import { lifecycleJobsStore } from '../pollers.js';
  import { ownSessionId } from '../stores/session.js';

  /**
   * jobs: OPTIONAL explicit override of the lifecycle rows. When omitted (the
   * wired path) we read the u-stores lifecycleJobsStore, which is fed by the 2s
   * session-scoped poller. The override exists so the panel renders correctly in
   * isolation (tests / Storybook) without the poller registry running.
   * @type {Array<Record<string, any>>|null}
   */
  export let jobs = null;

  // Resolve the live row set: explicit prop wins, else the store.
  $: rows = Array.isArray(jobs) ? jobs : $lifecycleJobsStore;

  // M15 defense-in-depth: drop any row that somehow carries the SM own session
  // id. Empty/missing own id => skip filtering (documented contract). The
  // poller already scopes server-side; this is the belt-and-braces mirror.
  $: own = $ownSessionId;
  $: visibleRows = (Array.isArray(rows) ? rows : []).filter(
    (r) => r && (!own || String(r.session_id) !== String(own)),
  );

  $: count = visibleRows.length;

  // ---- calm 1s elapsed re-clock (M14 elapsed is LIVE) ----------------------
  // A single shared "now" ticks once a second so every running row's elapsed
  // readout advances without per-row timers. Off the verdict hot path (M18).
  let nowSec = Date.now() / 1000;
  const _clock = setInterval(() => {
    nowSec = Date.now() / 1000;
  }, 1000);
  onDestroy(() => clearInterval(_clock));

  // ---- per-row derivations, all FROM DATA (M16) ----------------------------

  /** Stable id/PID: prefer an explicit pid (meta), else the job_id. */
  function idLabel(j) {
    if (j && j.pid !== null && j.pid !== undefined && String(j.pid).trim() !== '') {
      return `pid ${String(j.pid).trim()}`;
    }
    const jid = j && j.job_id != null ? String(j.job_id) : '';
    return jid ? shortId(jid) : '--';
  }

  /** Short, stable id fragment for the telemetry column. */
  function shortId(id) {
    if (id.length <= 16) return id;
    return `${id.slice(0, 8)}...${id.slice(-4)}`;
  }

  /** Human display name, FROM DATA (M16): name, else job_id, never invented. */
  function nameOf(j) {
    const n = j && typeof j.name === 'string' ? j.name.trim() : '';
    if (n) return n;
    const jid = j && j.job_id != null ? String(j.job_id) : '';
    return jid || 'unnamed job';
  }

  /**
   * Status, FROM DATA. The server returns open jobs as status:"running",
   * ended_at:null. A row that later carries ended_at (or status "exited") is
   * rendered as EXITED so the M14 lifecycle (running -> exited) is complete.
   * @returns {'running'|'exited'}
   */
  function statusOf(j) {
    const s = j && typeof j.status === 'string' ? j.status.toLowerCase() : '';
    if (s === 'exited' || s === 'done' || s === 'completed' || s === 'ended') return 'exited';
    if (j && j.ended_at !== null && j.ended_at !== undefined) return 'exited';
    return 'running';
  }

  /** Elapsed seconds, LIVE for running rows, frozen at ended_at for exited. */
  function elapsedOf(j) {
    const start = j && j.started_at != null ? Number(j.started_at) : NaN;
    if (!Number.isFinite(start)) return null;
    const end =
      j && j.ended_at !== null && j.ended_at !== undefined ? Number(j.ended_at) : nowSec;
    return Math.max(0, Math.round(end - start));
  }

  /** Human elapsed (Ns / Nm Ns / Nh Nm), tabular + compact. */
  function elapsedLabel(secs) {
    if (secs == null) return '--';
    if (secs < 60) return `${secs}s`;
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    if (m < 60) return `${m}m ${s}s`;
    const h = Math.floor(m / 60);
    return `${h}h ${m % 60}m`;
  }

  /** Exit code: present only when the server attached one (exited rows). */
  function exitCodeOf(j) {
    const c = j ? j.exit_code : undefined;
    return c === null || c === undefined ? null : Number(c);
  }
</script>

<section class="lc" aria-label="Background jobs lifecycle">
  <header class="lc__head">
    <h3 class="lc__title sev-base">Background jobs</h3>
    <!-- M4-spirit paired count: literal label + tabular number, never color
         alone. data-count lets the S2 render-validator assert the tally. -->
    <span class="lc__count" data-count={count} title={`${count} open job${count === 1 ? '' : 's'} or agent${count === 1 ? '' : 's'}`}>
      <span class="lc__count-tag">OPEN</span>
      <span class="lc__count-num">{count}</span>
    </span>
  </header>

  {#if count === 0}
    <p class="lc__empty">Still water. No active jobs or agents in scope.</p>
  {:else}
    <!-- A telemetry table read by columns. role=table keeps the column meaning
         reachable to assistive tech without a heavy data-grid widget (M17). -->
    <div class="lc__list" role="table" aria-label="Active jobs and agents">
      <div class="lc__row lc__row--head" role="row" aria-hidden="true">
        <span class="lc__col lc__col--kind" role="columnheader">kind</span>
        <span class="lc__col lc__col--name" role="columnheader">name</span>
        <span class="lc__col lc__col--id" role="columnheader">id / pid</span>
        <span class="lc__col lc__col--status" role="columnheader">status</span>
        <span class="lc__col lc__col--elapsed" role="columnheader">elapsed</span>
        <span class="lc__col lc__col--exit" role="columnheader">exit</span>
      </div>

      {#each visibleRows as j (j.job_id || nameOf(j))}
        {@const status = statusOf(j)}
        {@const running = status === 'running'}
        {@const elapsed = elapsedOf(j)}
        {@const exitCode = exitCodeOf(j)}
        {@const failed = exitCode !== null && exitCode !== 0}
        <div
          class="lc__row"
          class:lc__row--exited={!running}
          class:lc__row--failed={failed}
          role="row"
          data-job-id={j.job_id || ''}
          data-kind={j.kind || ''}
          data-status={status}
        >
          <!-- kind: the server's own taxonomy ("agent" | "bg_job"), verbatim.
               M16: a governance-grain label, not a monitored-project term. -->
          <span class="lc__col lc__col--kind" role="cell">
            <span class="lc__kind">{j.kind || 'job'}</span>
          </span>

          <!-- name: FROM DATA (M16). The load-bearing identity column. -->
          <span class="lc__col lc__col--name" role="cell">
            <span class="lc__name sev-base" title={nameOf(j)}>{nameOf(j)}</span>
            {#if j.session_id}
              <span class="lc__session sev-quiet" title={`session ${j.session_id}`}>
                {shortId(String(j.session_id))}
              </span>
            {/if}
          </span>

          <!-- id / pid: monospace tabular telemetry. -->
          <span class="lc__col lc__col--id sev-quiet" role="cell">{idLabel(j)}</span>

          <!-- status: PAIRED label+color (M4). RUNNING breathes via the shared
               calm live-dot only; EXITED is calm slate. Never color-alone. -->
          <span class="lc__col lc__col--status" role="cell">
            {#if running}
              <span class="lc__status lc__status--running" title={`${nameOf(j)} is running`}>
                <span class="lc__pip calm-live-dot" aria-hidden="true"></span>
                <span class="lc__status-text">RUNNING</span>
              </span>
            {:else}
              <span class="lc__status lc__status--exited" title={`${nameOf(j)} has exited`}>
                <span class="lc__pip" aria-hidden="true"></span>
                <span class="lc__status-text">EXITED</span>
              </span>
            {/if}
          </span>

          <!-- elapsed: LIVE for running rows (1s re-clock), tabular. -->
          <span
            class="lc__col lc__col--elapsed sev-quiet"
            role="cell"
            aria-label={elapsed == null ? 'elapsed unknown' : `${elapsedLabel(elapsed)} elapsed`}
          >{elapsedLabel(elapsed)}</span>

          <!-- exit code: present only for exited rows. A non-zero code is a
               failure -- surfaced as a paired BLOCKED-toned badge so it is
               never color-only (M4). Running rows show a quiet em dash. -->
          <span class="lc__col lc__col--exit" role="cell">
            {#if exitCode === null}
              <span class="lc__exit-none sev-quiet" aria-label="no exit code yet">&mdash;</span>
            {:else if failed}
              <Badge
                variant="blocked"
                label={`EXIT ${exitCode}`}
                reason={`${nameOf(j)} exited with code ${exitCode}`}
              />
            {:else}
              <Badge
                variant="decided"
                label="EXIT 0"
                reason={`${nameOf(j)} exited cleanly (code 0)`}
              />
            {/if}
          </span>
        </div>
      {/each}
    </div>
  {/if}
</section>

<style>
  .lc {
    display: flex;
    flex-direction: column;
    gap: var(--space-4, 10px);
  }

  .lc__head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-4, 10px);
  }

  .lc__title {
    margin: 0;
    font-family: var(--font-h, var(--ff-system));
    font-size: var(--fs-body, 14px);
    letter-spacing: 0.02em;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
  }

  /* Paired count pill -- label + tabular number, the M4 discipline at panel
     grain (color is never the sole signal). Calm slate at rest. */
  .lc__count {
    display: inline-flex;
    align-items: baseline;
    gap: var(--space-3, 6px);
    padding: var(--space-1, 2px) var(--space-4, 10px);
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: 999px;
    background: var(--calm-surface-raised, var(--bg-card, #0c1118));
  }
  .lc__count-tag {
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    letter-spacing: 0.13em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .lc__count-num {
    font-family: var(--font-d, var(--ff-mono));
    font-variant-numeric: tabular-nums;
    font-size: var(--fs-meta, 13px);
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
  }

  .lc__empty {
    margin: 0;
    padding: var(--space-5, 14px) var(--space-4, 10px);
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
    font-size: var(--fs-meta, 13px);
    font-style: italic;
  }

  /* Telemetry table. Square corners, hairline separators, tabular columns. */
  .lc__list {
    display: flex;
    flex-direction: column;
  }

  .lc__row {
    display: grid;
    grid-template-columns:
      4.5rem            /* kind */
      minmax(0, 1.4fr)  /* name */
      minmax(0, 0.9fr)  /* id/pid */
      6.5rem            /* status */
      5rem              /* elapsed */
      auto;             /* exit */
    align-items: center;
    gap: var(--space-4, 10px);
    padding: var(--space-3, 6px) var(--space-2, 4px);
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
  }
  .lc__row:last-child { border-bottom: none; }

  .lc__row--head {
    padding-bottom: var(--space-2, 4px);
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi, rgba(245,158,11,0.25)));
  }
  .lc__row--head .lc__col {
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }

  /* Exited rows recede -- history, not live. (M9-style calm fade, but driven
     by lifecycle status, not a HITL countdown.) */
  .lc__row--exited { opacity: 0.72; }
  /* A failed job keeps full ink so the failure is never dimmed away. */
  .lc__row--failed { opacity: 1; }

  .lc__col {
    min-width: 0;
    font-size: var(--fs-meta, 13px);
    color: var(--calm-ink, var(--text, #b8b098));
  }

  .lc__kind {
    display: inline-block;
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    letter-spacing: 0.04em;
    text-transform: lowercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    padding: var(--space-1, 2px) var(--space-3, 6px);
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    border-radius: var(--radius-sharp, 2px);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
  }

  .lc__col--name {
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .lc__name {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
  }
  .lc__session {
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .lc__col--id {
    font-family: var(--font-d, var(--ff-mono));
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* Status: paired pip + literal text. The pip is decorative; the text is the
     signal (M4). RUNNING breathes via .calm-live-dot; EXITED is static slate. */
  .lc__status {
    display: inline-flex;
    align-items: center;
    gap: var(--space-3, 6px);
  }
  .lc__pip {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex: 0 0 auto;
    background: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .lc__status--running .lc__pip { background: var(--calm-accent, var(--accent, #f59e0b)); }
  .lc__status-text {
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    font-weight: 600;
    letter-spacing: 0.08em;
  }
  .lc__status--running .lc__status-text { color: var(--calm-ink-loud, var(--text-bright, #e8e0cc)); }
  .lc__status--exited .lc__status-text { color: var(--calm-ink-quiet, var(--text-dim, #948870)); }

  .lc__col--elapsed {
    font-family: var(--font-d, var(--ff-mono));
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .lc__col--exit {
    display: flex;
    justify-content: flex-start;
  }
  .lc__exit-none { color: var(--calm-ink-quiet, var(--text-dim, #948870)); }

  /* Reduced motion: the only motion here is the inherited .calm-live-dot pulse,
     already gated by calm.css. Nothing extra to suppress -- but guard the row
     fade transition defensively in case a theme adds one. */
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .lc__row { transition: none; }
  }
</style>
