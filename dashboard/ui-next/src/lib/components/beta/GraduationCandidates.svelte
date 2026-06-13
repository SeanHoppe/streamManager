<!--
  GraduationCandidates.svelte -- BETA feature "graduation-candidates" (#1).

  WHAT IT IS
    ADR-18 Amendment F surface. A glance panel that proposes proven-routine
    command shapes for operator-confirmed graduation to a static ALLOW, and
    lists already-graduated rules with a one-tap reverse (demote).
      - CANDIDATES: shapes the corpus shows ALLOWed >=30x at >=0.95 mean
        confidence, with zero operator override, zero BLOCK ever, and never
        matching a safety-floor regex (the server enforces all of this;
        GET /api/graduation/candidates). Each row has a "Graduate" button.
      - GRADUATED: active rules (GET /api/graduation/active). Each row has a
        "Demote" button that reuses POST /api/patterns/{hash}/demote.

  M8 (never auto): graduation happens ONLY when the operator clicks Graduate.
    The scan PROPOSES; it never writes. The server re-verifies eligibility
    on confirm (defense-in-depth) and refuses safety-floor / SM-self shapes.

  BETA GATE (load-bearing): the ENTIRE component is wrapped in
    {#if $betaFlags['graduation-candidates']}. OFF => no DOM, no fetch, no
    poller, no timer. The verdict short-circuit in the engine is SEPARATELY
    gated by the BRIDGE_GRADUATED_RULES env flag, so a confirmed rule does
    not fire until the operator also enables the engine path.

  ADR-18 MUST floor honoured:
    - M2: never pulses / auto-foregrounds; a candidate is badge-in-place only.
    - M4 (paired label+color): every badge renders its LITERAL WORD (ROUTINE /
      GRADUATED) beside any color; color is never the sole signal.
    - M15 / G2 (polarity): the server excludes SM-self before aggregation; the
      footer surfaces the excluded_self tally.
    - M16 (domain-agnostic): shape text is rendered FROM DATA; no monitored-
      project vocabulary in this source.
    - M17 (a11y): real <button>s with aria-labels + the 2px amber focus ring.
    - M18: pure post-hoc GETs on a calm cadence; never on the verdict hot path.

  ASCII-only (cp1252-safe): dash rendered as "--". No smart quotes / em-dash.
-->
<script>
  import { onDestroy } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import {
    getGraduationCandidates,
    getGraduationActive,
    postGraduationConfirm,
    postPatternDemote,
  } from '../../api.js';

  const FLAG_KEY = 'graduation-candidates';
  /** Calm glance cadence; this is post-hoc data, not a hot-path signal. */
  const REFRESH_MS = 8000;

  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  let loaded = false;
  let usedMockData = false;
  /** @type {Array<Record<string, any>>} */
  let candidates = [];
  /** @type {Array<Record<string, any>>} */
  let active = [];
  let excludedSelf = 0;
  let busyHash = '';

  function mock() {
    return {
      candidates: [
        { shape_hash: 'a1b2c3d4', canonical_text: 'git status', n_allow: 64,
          mean_confidence: 0.98, n_override: 0, n_block_ever: 0 },
        { shape_hash: 'e5f6a7b8', canonical_text: 'ruff check .', n_allow: 41,
          mean_confidence: 0.96, n_override: 0, n_block_ever: 0 },
      ],
      active: [
        { shape_hash: 'c9d0e1f2', canonical_text: 'pytest -q',
          n_allow_at_grad: 52, confirmed_ts: 0, active: 1 },
      ],
      excluded_self: 0,
    };
  }

  async function load() {
    let cands = null;
    let acts = null;
    try {
      cands = await getGraduationCandidates(50);
    } catch {
      cands = null;
    }
    try {
      acts = await getGraduationActive();
    } catch {
      acts = null;
    }
    const haveLive =
      (cands && Array.isArray(cands.candidates) && cands.candidates.length) ||
      (acts && Array.isArray(acts.rules) && acts.rules.length);
    if (haveLive) {
      candidates = (cands && cands.candidates) || [];
      active = (acts && acts.rules) || [];
      excludedSelf = (cands && cands.excluded_self) || 0;
      usedMockData = false;
    } else {
      const m = mock();
      candidates = m.candidates;
      active = m.active;
      excludedSelf = m.excluded_self;
      usedMockData = true;
    }
    loaded = true;
  }

  /** @type {ReturnType<typeof setInterval>|null} */
  let _timer = null;
  function startPolling() {
    if (_timer || typeof setInterval === 'undefined') return;
    load();
    _timer = setInterval(load, REFRESH_MS);
  }
  function stopPolling() {
    if (_timer) {
      clearInterval(_timer);
      _timer = null;
    }
  }
  $: if (enabled) startPolling();
  else {
    stopPolling();
    loaded = false;
    candidates = [];
    active = [];
    busyHash = '';
  }
  onDestroy(stopPolling);

  // ---- operator actions (M8: explicit click only) ---------------------------
  async function graduate(row) {
    if (usedMockData || busyHash) return;
    busyHash = row.shape_hash;
    // optimistic: move from candidates -> active
    candidates = candidates.filter((c) => c.shape_hash !== row.shape_hash);
    active = [
      { shape_hash: row.shape_hash, canonical_text: row.canonical_text,
        n_allow_at_grad: row.n_allow, confirmed_ts: 0, active: 1 },
      ...active,
    ];
    try {
      await postGraduationConfirm(row.shape_hash);
    } catch {
      await load(); // rollback to server truth on failure
    } finally {
      busyHash = '';
    }
  }

  async function demote(row) {
    if (usedMockData || busyHash) return;
    busyHash = row.shape_hash;
    active = active.filter((a) => a.shape_hash !== row.shape_hash);
    try {
      await postPatternDemote(row.shape_hash);
    } catch {
      await load();
    } finally {
      busyHash = '';
    }
  }

  function shortHash(h) {
    return String(h || '').slice(0, 8);
  }
</script>

{#if enabled}
  <section class="gc" aria-label="Allow-pattern graduation candidates">
    <div class="gc__head">
      <span class="gc__tag" title="Operator-confirmed graduated ALLOW rules (ADR-18 Amendment F)">
        <span class="gc__tag-dot" aria-hidden="true"></span>GRADUATION
      </span>
      <span class="gc__beta">BETA</span>
      <span class="gc__tally" aria-label={`${candidates.length} candidate${candidates.length === 1 ? '' : 's'} proposed`}>
        <span class="gc__tally-tag">CANDIDATES</span>
        <span class="gc__tally-num tabular">{candidates.length}</span>
      </span>
    </div>

    <p class="gc__source" data-mock={usedMockData}>
      {usedMockData
        ? 'SAMPLE DATA -- no eligible shapes in gov.db yet; showing a representative shape.'
        : 'LIVE -- proven-routine shapes from gov.db (polarity-filtered, safety-floor excluded).'}
    </p>

    {#if !loaded}
      <p class="gc__loading">Loading candidates...</p>
    {:else}
      <!-- CANDIDATES: proposed for graduation (M8: confirm is explicit) -->
      <h3 class="gc__sub">Proposed</h3>
      {#if candidates.length === 0}
        <p class="gc__empty">No eligible candidates. Shapes graduate as routine, override-free history accrues.</p>
      {:else}
        <div class="gc__list" role="list">
          {#each candidates as c (c.shape_hash)}
            <div class="gc-row" role="listitem" data-shape-hash={c.shape_hash}>
              <span class="gc-row__id">
                <span class="gc-row__text" title={c.canonical_text}>{c.canonical_text}</span>
                <span class="gc-row__meta tabular">
                  {c.n_allow} allow <span class="gc-sep" aria-hidden="true">&middot;</span>
                  conf {Number(c.mean_confidence).toFixed(2)} <span class="gc-sep" aria-hidden="true">&middot;</span>
                  #{shortHash(c.shape_hash)}
                </span>
              </span>
              <span class="gc-badge gc-badge--routine" aria-hidden="true">
                <span class="gc-badge__dot" aria-hidden="true"></span>ROUTINE
              </span>
              <button
                type="button"
                class="gc-act gc-act--go"
                disabled={usedMockData || !!busyHash}
                aria-label={`Graduate shape ${c.canonical_text} to a static ALLOW`}
                on:click={() => graduate(c)}
              >Graduate</button>
            </div>
          {/each}
        </div>
      {/if}

      <!-- GRADUATED: active rules, reverse via the existing demote affordance -->
      <h3 class="gc__sub">Graduated</h3>
      {#if active.length === 0}
        <p class="gc__empty">No active graduated rules.</p>
      {:else}
        <div class="gc__list" role="list">
          {#each active as a (a.shape_hash)}
            <div class="gc-row gc-row--active" role="listitem" data-shape-hash={a.shape_hash}>
              <span class="gc-row__id">
                <span class="gc-row__text" title={a.canonical_text}>{a.canonical_text}</span>
                <span class="gc-row__meta tabular">
                  graduated at {a.n_allow_at_grad} allow <span class="gc-sep" aria-hidden="true">&middot;</span>
                  #{shortHash(a.shape_hash)}
                </span>
              </span>
              <span class="gc-badge gc-badge--graduated" aria-hidden="true">
                <span class="gc-badge__dot" aria-hidden="true"></span>GRADUATED
              </span>
              <button
                type="button"
                class="gc-act gc-act--undo"
                disabled={usedMockData || !!busyHash}
                aria-label={`Demote graduated rule ${a.canonical_text} (stops the static ALLOW)`}
                on:click={() => demote(a)}
              >Demote</button>
            </div>
          {/each}
        </div>
      {/if}

      <footer class="gc__foot">
        <span class="gc__self-dot" aria-hidden="true"></span>
        {excludedSelf} self row{excludedSelf === 1 ? '' : 's'} excluded (polarity filter)
      </footer>
    {/if}
  </section>
{/if}

<style>
  .gc {
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 6px);
    width: 100%;
    min-width: 0;
    padding: var(--space-3, 6px) 0 0;
    font-family: var(--ff-system);
  }
  .gc__head { display: flex; align-items: center; gap: var(--space-3, 6px); flex-wrap: wrap; }
  .gc__tag {
    display: inline-flex; align-items: center; gap: 5px;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 9px; font-weight: 600; letter-spacing: 0.13em; text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
    padding: 2px 7px; border-radius: 999px;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border, #192030));
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
  }
  .gc__tag-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--badge-decided-fg, #16a34a); opacity: 0.85; }
  .gc__beta {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 9px; font-weight: 700; letter-spacing: 0.08em;
    color: #92400e; background: var(--badge-ar-bg, #fef3c7);
    border: 1px solid var(--badge-ar-border, #d97706); border-radius: 4px; padding: 0 5px;
  }
  .gc__tally {
    margin-left: auto; display: inline-flex; align-items: baseline; gap: 5px;
    padding: 2px 7px; border-radius: 999px;
    border: var(--hairline, 1px) solid transparent;
    background: var(--calm-accent-wash, rgba(245, 158, 11, 0.09));
  }
  .gc__tally-tag {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 9px; font-weight: 600; letter-spacing: 0.13em; text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .gc__tally-num { font-size: 13px; font-weight: 560; line-height: 1; color: var(--calm-ink-quiet, var(--text-dim, #948870)); }

  .gc__source {
    margin: 0; font-size: var(--fs-chrome, 11px); font-family: var(--font-d, var(--ff-mono));
    letter-spacing: 0.02em; line-height: var(--lh-body, 1.5);
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .gc__source[data-mock='true'] { color: var(--badge-warn-fg, #ea580c); }
  :global([data-theme='paper']) .gc__source[data-mock='true'] { color: #9a3412; }

  .gc__loading, .gc__empty {
    margin: 0; padding: var(--space-3, 6px) 0; font-size: var(--fs-chrome, 11px);
    font-style: italic; line-height: var(--lh-body, 1.5);
    color: var(--calm-ink-quiet, var(--text-dim, #948870));
  }
  .gc__sub {
    margin: var(--space-3, 6px) 0 0;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }

  .gc__list { display: flex; flex-direction: column; gap: var(--space-3, 6px); }
  .gc-row {
    display: grid;
    grid-template-columns: 1fr auto auto;
    align-items: center;
    gap: var(--space-3, 8px);
    padding: 7px var(--space-4, 10px);
    background: var(--calm-lane-bg, var(--bg-card, #0c1118));
    border: var(--hairline, 1px) solid var(--calm-lane-edge, var(--border, #192030));
    border-left-width: 2px;
    border-left-color: var(--badge-decided-border, #86efac);
    border-radius: var(--radius-soft, 4px);
  }
  .gc-row--active { border-left-color: var(--calm-accent, var(--accent, #f59e0b)); }
  .gc-row__id { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
  .gc-row__text {
    font-size: var(--fs-meta, 13px); font-weight: 460; letter-spacing: 0.01em;
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    line-height: var(--lh-tight, 1.25);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    font-family: var(--font-d, var(--ff-mono));
  }
  .gc-row__meta {
    display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    font-size: var(--fs-chrome, 11px); color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .gc-sep { opacity: 0.5; }

  .gc-badge {
    flex: 0 0 auto; align-self: center;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px; font-weight: 700; letter-spacing: 0.04em; line-height: 1.4;
    padding: 1px 8px; border-radius: 999px; white-space: nowrap;
    display: inline-flex; align-items: center; gap: 5px;
  }
  .gc-badge__dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex: 0 0 auto; }
  .gc-badge--routine {
    color: #15803d; background: var(--badge-decided-bg, #dcfce7);
    border: 1px solid var(--badge-decided-border, #86efac);
  }
  .gc-badge--graduated {
    color: #92400e; background: var(--badge-ar-bg, #fef3c7);
    border: 1px solid var(--badge-ar-border, #d97706);
  }

  .gc-act {
    flex: 0 0 auto;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 11px; font-weight: 600; letter-spacing: 0.02em;
    padding: 3px 10px; border-radius: var(--radius-soft, 4px);
    cursor: pointer;
    background: var(--calm-surface-alt, var(--bg-row-alt, #0b1018));
    color: var(--calm-ink-loud, var(--text-bright, #e8e0cc));
    border: var(--hairline, 1px) solid var(--calm-lane-edge, var(--border, #192030));
    transition: background var(--t-calm, 180ms ease), border-color var(--t-calm, 180ms ease);
  }
  .gc-act--go { border-color: var(--badge-decided-border, #86efac); }
  .gc-act--undo { border-color: var(--badge-ar-border, #d97706); }
  .gc-act:hover:not(:disabled) { background: var(--calm-surface-hover, var(--bg-row-hover, #131c2a)); }
  .gc-act:disabled { opacity: 0.5; cursor: default; }
  .gc-act:focus-visible {
    outline: 2px solid var(--badge-ar-border, #d97706);
    outline-offset: 2px;
    border-radius: var(--radius-soft, 4px);
  }

  .gc__foot {
    display: flex; align-items: center; gap: 6px; padding: var(--space-2, 4px) 0 0;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px; letter-spacing: 0.06em; text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui, #8a8068));
  }
  .gc__self-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--calm-ink-quiet, var(--text-dim, #948870)); opacity: 0.7; }

  .tabular { font-variant-numeric: tabular-nums; font-family: var(--font-d, var(--ff-mono)); }

  :global(html[data-motion='reduce']) .gc-act { transition: none; }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .gc-act { transition: none; }
  }
</style>
