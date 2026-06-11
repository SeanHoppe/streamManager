<!--
  CrossSessionPatterns.svelte -- the cross-session pattern panel (unit
  u-settings-patterns).

  WHAT IT OWNS
    Renders GET /api/patterns/cross_session -- every behavioural pattern the
    governance bus has flagged as recurring across more than one governed
    session -- and exposes a per-pattern DEMOTE action
    (POST /api/patterns/{hash}/demote) that clears the cross_session flag.

    Server row shape (dashboard/server.py api_patterns_cross_session):
      { hash, level, occurrences, success_rate, last_seen, payload }
    Every field is rendered FROM DATA (M16). `payload` is the pattern's own
    opaque description string -- surfaced verbatim, never mapped to a domain
    vocabulary.

  WHY THIS IS NOT AN ESCALATION (M2)
    new_pattern / cross-session flags are BADGE-IN-PLACE only -- they never
    auto-foreground a frame and never steal focus. This panel is therefore a
    calm, still-water list: a recurring pattern is worth a glance, not an alarm.
    It carries a WARN-toned paired badge (label + color, M4) to mark that the
    pattern is flagged, but nothing here pulses or rearranges layout.

  DEMOTE SEMANTICS (optimistic, M10-style)
    Clicking Demote removes the row from the list IMMEDIATELY, then POSTs the
    demote. On error the row is restored in place (silent restore) so the
    operator's view never lies about server state. A 404 (pattern already gone)
    is treated as success -- the desired end-state (not cross-session) holds.

  A11Y (M17)
    The list is a <ul role="list">; each demote control is a real <button> with
    an explicit aria-label naming the pattern, so the global 2px #d97706 focus
    ring (focus.css) applies and the action is reachable by keyboard. An in-flight
    demote disables its button and announces via aria-busy. Empty / error /
    loading states are announced via an aria-live region.

  M16 (domain-agnostic): no monitored-project vocabulary. `hash`, `level`,
  `payload` are the server's own taxonomy, rendered verbatim.

  M18 (latency): post-hoc observability only. The only network calls are the
  initial seed GET and the operator-initiated demote POST -- never on the verdict
  hot path. Refresh is operator-driven (a Refresh button) + an optional poll;
  no live per-decision dependency.

  ASCII-only (cp1252-safe): dash rendered as "--".
-->
<script>
  import { onMount } from 'svelte';
  import Badge from './Badge.svelte';
  import { getCrossSessionPatterns, postPatternDemote } from '../api.js';

  /**
   * patterns: OPTIONAL explicit override of the row set (tests / isolation).
   * When null (the wired path) this component seeds from the endpoint on mount
   * and on operator Refresh.
   * @type {Array<Record<string, any>>|null}
   */
  export let patterns = null;

  /**
   * loadPatterns / demotePattern: injectable transport hooks. Default to the
   * api.js wrappers (the real endpoints). Injectable so the panel is unit-
   * testable without a live server.
   */
  export let loadPatterns = getCrossSessionPatterns;
  export let demotePattern = postPatternDemote;

  /** @type {Array<Record<string, any>>} the live row set */
  let rows = Array.isArray(patterns) ? patterns.slice() : [];
  let loading = false;
  /** @type {string|null} a transport-level error message for the live region */
  let loadError = null;
  /** @type {Set<string>} hashes with an in-flight demote (button disabled) */
  let busy = new Set();

  // When a `patterns` prop is supplied, it is authoritative; the component does
  // not fetch. Otherwise it seeds on mount.
  $: usingProp = Array.isArray(patterns);
  $: if (usingProp) rows = patterns.slice();

  onMount(() => {
    if (!usingProp) refresh();
  });

  /** Seed (or re-seed) the list from the endpoint. Operator-driven; not hot. */
  async function refresh() {
    if (usingProp) return;
    loading = true;
    loadError = null;
    try {
      const data = await loadPatterns();
      rows = Array.isArray(data) ? data : [];
    } catch (err) {
      loadError = 'Could not load cross-session patterns.';
      // keep the prior rows visible rather than blanking the panel on a blip
    } finally {
      loading = false;
    }
  }

  /**
   * Demote a pattern (clear its cross_session flag). Optimistic: drop the row
   * immediately, POST, and restore on error. A 404 == already-gone == success.
   * @param {Record<string, any>} row
   */
  async function demote(row) {
    const hash = row && row.hash != null ? String(row.hash) : '';
    if (!hash || busy.has(hash)) return;

    // optimistic removal -- snapshot for restore-on-error
    const prevRows = rows;
    const idx = rows.findIndex((r) => String(r.hash) === hash);
    rows = rows.filter((r) => String(r.hash) !== hash);
    busy = new Set(busy).add(hash);

    try {
      await demotePattern(hash);
      // success -- the row stays removed
    } catch (err) {
      // 404 means the pattern was already demoted/removed: desired end-state
      // already holds, so treat it as success (do NOT restore).
      const msg = err && err.message ? String(err.message) : '';
      const gone = /(^|\D)404(\D|$)/.test(msg);
      if (!gone) {
        // silent restore at the original position
        rows = restoreAt(prevRows, row, idx);
      }
    } finally {
      const next = new Set(busy);
      next.delete(hash);
      busy = next;
    }
  }

  /**
   * Restore a removed row near its original index (best-effort; the list may
   * have changed underneath). Used only on the error rollback path.
   * @param {Array<Record<string, any>>} prev the pre-removal snapshot
   * @param {Record<string, any>} row
   * @param {number} idx
   */
  function restoreAt(prev, row, idx) {
    // Prefer the clean pre-removal snapshot when the list is otherwise unchanged.
    if (!rows.some((r) => String(r.hash) === String(row.hash))) {
      const copy = rows.slice();
      const insertAt = Math.min(Math.max(idx, 0), copy.length);
      copy.splice(insertAt, 0, row);
      return copy;
    }
    return prev;
  }

  // --- formatting helpers (presentation only; all values come from data) -----

  /** @param {Record<string, any>} row */
  function successText(row) {
    const v = Number(row.success_rate);
    if (!Number.isFinite(v)) return '--';
    // success_rate may arrive as a 0..1 fraction or a 0..100 percent; normalize.
    const pct = v <= 1 ? v * 100 : v;
    return `${Math.round(pct)}%`;
  }

  /** @param {Record<string, any>} row */
  function occurrencesText(row) {
    const n = Number(row.occurrences);
    return Number.isFinite(n) ? String(n) : '--';
  }

  /** @param {Record<string, any>} row */
  function lastSeenText(row) {
    const ts = row.last_seen;
    if (ts == null || ts === '') return '--';
    // last_seen may be an epoch (s or ms) or an ISO string. Render compactly,
    // tolerant of either; fall back to the raw value verbatim (M16).
    const n = Number(ts);
    let d = null;
    if (Number.isFinite(n)) {
      d = new Date(n < 1e12 ? n * 1000 : n);
    } else {
      const parsed = Date.parse(String(ts));
      if (!Number.isNaN(parsed)) d = new Date(parsed);
    }
    if (!d || Number.isNaN(d.getTime())) return String(ts);
    return d.toLocaleString(undefined, {
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  /** Short, stable display of the opaque hash (full value in title/aria). */
  function shortHash(hash) {
    const h = String(hash || '');
    return h.length > 12 ? `${h.slice(0, 8)}...${h.slice(-4)}` : h;
  }

  /** @param {Record<string, any>} row */
  function patternDescription(row) {
    // payload is the pattern's own opaque self-description -- surfaced verbatim.
    const p = row.payload;
    if (p == null) return '';
    if (typeof p === 'string') return p;
    try {
      return JSON.stringify(p);
    } catch {
      return String(p);
    }
  }

  $: isEmpty = !loading && rows.length === 0;
</script>

<section class="csp" aria-labelledby="csp-title">
  <header class="csp__head">
    <div class="csp__head-l">
      <h2 id="csp-title" class="csp__title sev-notice">Cross-session patterns</h2>
      <span class="csp__count sev-quiet" aria-live="polite">
        {rows.length}
        {rows.length === 1 ? 'pattern' : 'patterns'}
      </span>
    </div>
    {#if !usingProp}
      <button
        type="button"
        class="csp__refresh"
        on:click={refresh}
        disabled={loading}
        aria-busy={loading}
        aria-label="Refresh cross-session patterns"
      >
        {loading ? 'Loading...' : 'Refresh'}
      </button>
    {/if}
  </header>

  <!-- a11y live region for load state -->
  <p class="csp__status sev-quiet" role="status" aria-live="polite">
    {#if loadError}{loadError}{/if}
  </p>

  {#if isEmpty}
    <p class="csp__empty sev-quiet">
      No patterns are flagged across sessions. The monitor is calm.
    </p>
  {:else}
    <ul class="csp__list" role="list">
      {#each rows as row (row.hash)}
        <li class="csp__row" class:is-busy={busy.has(String(row.hash))}>
          <div class="csp__row-main">
            <div class="csp__row-top">
              <!-- M4 paired badge: cross-session flag is WARN-toned (in-place,
                   never an escalation), label + color, never color alone. -->
              <Badge
                variant="warn"
                label="CROSS-SESSION"
                reason="Behavioural pattern recurring across more than one governed session -- flagged in place"
              />
              {#if row.level != null && row.level !== ''}
                <span class="csp__level sev-base" title="Pattern level">{row.level}</span>
              {/if}
              <code
                class="csp__hash"
                title={String(row.hash)}
                aria-label={`Pattern hash ${row.hash}`}>{shortHash(row.hash)}</code
              >
            </div>

            {#if patternDescription(row)}
              <p class="csp__desc sev-base">{patternDescription(row)}</p>
            {/if}

            <dl class="csp__meta sev-quiet">
              <div class="csp__meta-cell">
                <dt>Occurrences</dt>
                <dd>{occurrencesText(row)}</dd>
              </div>
              <div class="csp__meta-cell">
                <dt>Success</dt>
                <dd>{successText(row)}</dd>
              </div>
              <div class="csp__meta-cell">
                <dt>Last seen</dt>
                <dd>{lastSeenText(row)}</dd>
              </div>
            </dl>
          </div>

          <div class="csp__row-action">
            <button
              type="button"
              class="csp__demote"
              on:click={() => demote(row)}
              disabled={busy.has(String(row.hash))}
              aria-busy={busy.has(String(row.hash))}
              aria-label={`Demote pattern ${shortHash(row.hash)} -- clear its cross-session flag`}
            >
              {busy.has(String(row.hash)) ? 'Demoting...' : 'Demote'}
            </button>
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .csp {
    display: flex;
    flex-direction: column;
    gap: var(--space-4, 10px);
    font-family: var(--ff-system);
    color: var(--calm-ink, var(--text));
    /* independent scroll discipline: this panel scrolls within its frame */
    min-height: 0;
  }

  .csp__head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-4, 10px);
    padding-bottom: var(--space-3, 6px);
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
  }
  .csp__head-l {
    display: flex;
    align-items: baseline;
    gap: var(--space-4, 10px);
    min-width: 0;
  }
  .csp__title {
    margin: 0;
    font-family: var(--font-h, var(--ff-system));
    font-size: 15px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--calm-ink-loud, var(--text-bright));
  }
  .csp__count {
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .csp__refresh {
    appearance: none;
    background: transparent;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: var(--radius-sharp, 2px);
    color: var(--calm-ink-chrome, var(--text-ui));
    font-family: var(--ff-system);
    font-size: var(--fs-chrome, 11px);
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: var(--space-2, 4px) var(--space-4, 10px);
    cursor: pointer;
    white-space: nowrap;
    transition: color var(--t-calm), border-color var(--t-calm);
  }
  .csp__refresh:hover:not(:disabled) {
    color: var(--calm-accent, var(--accent));
    border-color: var(--calm-hairline-hi, var(--border-hi));
  }
  .csp__refresh:disabled {
    opacity: 0.55;
    cursor: default;
  }

  /* status / empty live regions stay quiet -- they never grab attention */
  .csp__status {
    margin: 0;
    min-height: 0;
    font-size: var(--fs-chrome, 11px);
  }
  .csp__status:empty {
    display: none;
  }
  .csp__empty {
    margin: var(--space-5, 14px) 0;
    font-size: var(--fs-meta, 13px);
    line-height: var(--lh-body, 1.5);
  }

  .csp__list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 6px);
    overflow-y: auto;
    min-height: 0;
  }

  /* Each pattern row: a still hairline card. No motion, no pulse -- a cross-
     session flag is a glance-worthy notice, not an escalation (M2). */
  .csp__row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-5, 14px);
    padding: var(--space-4, 10px) var(--space-4, 10px);
    background: var(--calm-surface-row, var(--bg-row));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-left: 2px solid var(--badge-warn-border, #ea580c);
    border-radius: var(--radius-sharp, 2px);
    transition: background var(--t-calm);
  }
  .csp__row:hover {
    background: var(--calm-surface-hover, var(--bg-row-hover));
  }
  .csp__row.is-busy {
    opacity: 0.7;
  }

  .csp__row-main {
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 6px);
    min-width: 0;
    flex: 1 1 auto;
  }

  .csp__row-top {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-3, 6px);
  }
  .csp__level {
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--calm-ink-chrome, var(--text-ui));
  }
  .csp__hash {
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-chrome, 11px);
    color: var(--calm-ink-quiet, var(--text-dim));
    background: var(--calm-surface-alt, var(--bg-row-alt));
    padding: 1px 5px;
    border-radius: var(--radius-sharp, 2px);
  }

  .csp__desc {
    margin: 0;
    font-size: var(--fs-meta, 13px);
    line-height: var(--lh-body, 1.5);
    color: var(--calm-ink, var(--text));
    /* keep long opaque payloads from blowing out the panel width */
    overflow-wrap: anywhere;
  }

  .csp__meta {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-5, 14px);
    margin: 0;
  }
  .csp__meta-cell {
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .csp__meta dt {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--calm-ink-chrome, var(--text-ui));
  }
  .csp__meta dd {
    margin: 0;
    font-family: var(--font-d, var(--ff-mono));
    font-size: var(--fs-meta, 13px);
    font-variant-numeric: tabular-nums;
    color: var(--calm-ink, var(--text));
  }

  .csp__row-action {
    flex: 0 0 auto;
  }
  .csp__demote {
    appearance: none;
    background: transparent;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: var(--radius-sharp, 2px);
    color: var(--calm-ink-chrome, var(--text-ui));
    font-family: var(--ff-system);
    font-size: var(--fs-chrome, 11px);
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: var(--space-2, 4px) var(--space-4, 10px);
    cursor: pointer;
    white-space: nowrap;
    transition: color var(--t-calm), border-color var(--t-calm), background var(--t-calm);
  }
  .csp__demote:hover:not(:disabled) {
    color: var(--badge-warn-fg, #ea580c);
    border-color: var(--badge-warn-border, #ea580c);
    background: var(--calm-accent-wash, var(--accent-dim));
  }
  .csp__demote:disabled {
    opacity: 0.55;
    cursor: default;
  }
</style>
