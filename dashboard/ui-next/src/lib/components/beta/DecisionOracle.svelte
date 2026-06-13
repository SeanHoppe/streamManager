<!--
  DecisionOracle.svelte -- BETA feature #12 "decision-oracle": inline pattern
  pedigree + ancestral replay. A READ-ONLY, non-modal "whisper pane" that turns
  an opaque decision row into a one-click, no-SQL pattern-pedigree card.

  GATING (load-bearing): the whole component is wrapped in
  {#if $betaFlags['decision-oracle']}. When the flag is OFF (the default) it
  renders NOTHING and registers NO listeners / pollers / SSE / timers -- the
  {#if} short-circuits the markup AND the onMount window-listener wiring, so
  there is zero runtime cost. Flip it ON in Settings > BETA features.

  WHAT IT MOUNTS (self-contained, App-root sibling -- it edits no shared file):
    1. A thin, fixed "pedigree launcher" rail listing the most recent
       oracle-ELIGIBLE decisions (each carrying the star glyph from the mockup).
       Eligibility = the decision's session is a GOVERNED, non-SM session (G2):
       its session_id must appear in the self-excluded `sessions` store. SM-self
       rows (project_slug == streamManager, or the self session id) never get a
       glyph -- exactly the mockup's polarity illustration.
    2. The whisper pane (Layer 1 promotion ladder + stat strip + overfit chip;
       Layer 2 collapsible ancestral replay with a read-only scrubber). Opening
       it fetches GET /api/patterns/{hash}/pedigree; on 404 / empty / error it
       falls back to a realistic MOCK payload so the pane is always testable.
    3. It ALSO listens for a `decision-oracle:open` window CustomEvent so a
       future one-line wire on the real DecisionRow glyph can drive the same pane
       (see the build's wireInstruction). Until then the launcher rail is the
       affordance.

  ADR-18 MUST floor honoured:
    - M4 paired label+color: every state renders literal TEXT (CURRENT, OVERFIT?,
      Copied, ON/OFF, "observation N of M"); color is only ever a second channel.
    - M8: the overfit hint is a dashed advisory chip with the word "OVERFIT?" --
      never tint alone, never a verdict, never a button that acts.
    - M16 domain-agnostic: identity is rendered FROM DATA (server) or generic
      mock phrasing; no monitored-project vocabulary.
    - M17 a11y: real <button>s (Tab/Enter/Space), 2px amber focus ring, Escape +
      scrim-click close with focus restored to the originating glyph, a live
      region for copy/scrub announcements, reduced-motion aware.
    - M18: pure post-hoc read. ONE GET per open. Never on the verdict hot path,
      never dispatches back to governance, never opens /api/commands/stream.

  ASCII-only (cp1252-safe): dash is "--"; no smart quotes / em-dashes / box chars.
-->
<script>
  import { onMount, tick } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { decisionsStore } from '../../sse.js';
  import { sessions, getOwnSessionId } from '../../stores/session.js';
  import {
    fetchPedigree,
    normalisePedigree,
    mockPedigree,
  } from './DecisionOracle-data.js';

  const FLAG_KEY = 'decision-oracle';
  const LAUNCHER_LIMIT = 8; // most-recent eligible decisions surfaced in the rail

  // -- G2 self-exclude: the set of GOVERNED (non-SM) session ids. The `sessions`
  // store is already self-excluded by id AND project_slug (see stores/session.js)
  // so a decision whose session is NOT in this set is SM-self / unknown and gets
  // NO oracle glyph. This is the client-side polarity floor; the server also 404s
  // an SM-self pattern hash as the durable gate.
  $: governedIds = new Set(($sessions || []).map((s) => s && s.id).filter(Boolean));
  $: ownId = getOwnSessionId();

  // Oracle-eligible launcher rows: a decision needs a matched_hash (no pedigree
  // without a pattern) AND a governed, non-SM session. Newest-first, capped.
  $: launcherRows = ($betaFlags && $betaFlags[FLAG_KEY])
    ? ($decisionsStore || [])
        .filter((r) => r && r.matched_hash && String(r.matched_hash).trim() !== '')
        .filter((r) => {
          const sid = r.session_id;
          if (!sid) return false;
          if (ownId && sid === ownId) return false; // self session id (G2)
          return governedIds.has(sid); // governed, non-SM (slug-excluded upstream)
        })
        .slice(0, LAUNCHER_LIMIT)
    : [];

  // -- whisper pane state ----------------------------------------------------
  let open = false;
  let loading = false;
  /** @type {ReturnType<typeof normalisePedigree>} */
  let pedigree = null;
  let usedMock = false;
  let loadError = false;
  /** the glyph element to restore focus to on close (M17) */
  let lastTrigger = null;

  let copied = false;
  let replayOpen = false;
  let scrubIndex = 1; // 1-based observation index for the read-only scrubber
  let liveMsg = ''; // aria-live announcements (copy / scrub)

  let closeBtn; // first focusable in the pane (focus target on open)
  let copyTimer = null;

  $: ladderRungs = pedigree ? [0, 1, 2, 3, 4].map((l) => ({
    level: l,
    label: `L${l}`,
    done: l <= pedigree.level,
    current: l === pedigree.level,
    future: l > pedigree.level,
  })) : [];

  $: successPct = pedigree ? Math.round(pedigree.success_rate * 100) : 0;
  $: obsCount = pedigree ? pedigree.observations.length : 0;
  $: activeObs = pedigree && obsCount
    ? pedigree.observations[Math.min(Math.max(scrubIndex, 1), obsCount) - 1]
    : null;

  /**
   * Open the whisper pane for a decision's matched_hash. Fetches the pedigree
   * (read-only GET); on any non-2xx (incl. the G2 404) / empty / error it falls
   * back to realistic mock data so the pane is always populated + testable.
   * @param {string} hash    decision.matched_hash (pattern hash)
   * @param {EventTarget|null} trigger element to restore focus to on close
   */
  async function openFor(hash, trigger) {
    lastTrigger = trigger || null;
    open = true;
    loading = true;
    loadError = false;
    usedMock = false;
    pedigree = null;
    replayOpen = false;
    scrubIndex = 1;
    copied = false;

    await tick();
    if (closeBtn && typeof closeBtn.focus === 'function') closeBtn.focus();

    let payload = null;
    try {
      const raw = await fetchPedigree(hash);
      payload = normalisePedigree(raw);
    } catch {
      payload = null; // 404 (G2 self / no pattern) or transport error -> mock
    }

    if (!payload) {
      payload = mockPedigree(hash);
      usedMock = true;
    }
    pedigree = payload;
    loading = false;
  }

  function closePane() {
    if (!open) return;
    open = false;
    loading = false;
    const t = lastTrigger;
    lastTrigger = null;
    if (t && typeof t.focus === 'function') t.focus();
  }

  /** @param {MouseEvent} e */
  function onLauncherClick(e) {
    const btn = e.currentTarget;
    const hash = btn && btn.getAttribute('data-hash');
    if (hash) openFor(hash, btn);
  }

  /** Window CustomEvent bridge: detail = { hash, decisionId? }. Optional wire. */
  function onExternalOpen(e) {
    const hash = e && e.detail && e.detail.hash;
    if (hash) openFor(String(hash), (e.detail && e.detail.trigger) || null);
  }

  /** @param {KeyboardEvent} e */
  function onKeydown(e) {
    if (e.key === 'Escape' && open) {
      e.preventDefault();
      closePane();
    }
  }

  function copyHash() {
    if (!pedigree) return;
    const full = pedigree.pattern_hash;
    const done = () => {
      copied = true;
      liveMsg = 'Pattern hash copied to clipboard.';
      if (copyTimer) clearTimeout(copyTimer);
      copyTimer = setTimeout(() => { copied = false; }, 1600);
    };
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(full).then(done, done);
      } else {
        done();
      }
    } catch {
      done();
    }
  }

  function toggleReplay() {
    replayOpen = !replayOpen;
  }

  /** @param {Event} e */
  function onScrub(e) {
    const v = Number(/** @type {HTMLInputElement} */ (e.currentTarget).value);
    scrubIndex = Number.isFinite(v) ? v : 1;
    liveMsg = `observation ${scrubIndex} of ${obsCount}`;
  }

  // -- lifecycle: ONLY wires the optional external-open bridge, and ONLY when
  // the flag is ON. With the flag OFF the whole component is {#if}-gated out, so
  // onMount never runs and no listener is ever registered (zero runtime cost).
  onMount(() => {
    if (typeof window === 'undefined') return;
    window.addEventListener('decision-oracle:open', onExternalOpen);
    window.addEventListener('keydown', onKeydown);
    return () => {
      window.removeEventListener('decision-oracle:open', onExternalOpen);
      window.removeEventListener('keydown', onKeydown);
      if (copyTimer) clearTimeout(copyTimer);
    };
  });
</script>

{#if $betaFlags && $betaFlags[FLAG_KEY]}
  <!-- ============ PEDIGREE LAUNCHER RAIL (fixed, bottom-left, calm) ============
       Each eligible decision carries the star glyph from the mockup. Empty when
       no governed decision with a pattern hash is in scope yet (calm, not an
       error). This is the self-contained affordance; the real-row glyph wire is
       an optional one-liner (see wireInstruction). -->
  <aside class="do-launcher" aria-label="Decision Oracle -- pattern pedigree launcher">
    <div class="do-launcher__cap">
      <span class="do-launcher__eyebrow">Decision Oracle</span>
      <span class="do-launcher__hint">
        {launcherRows.length} pedigree{launcherRows.length === 1 ? '' : 's'} in scope
      </span>
    </div>
    {#if launcherRows.length === 0}
      <p class="do-launcher__empty" role="status">
        No governed decision with a matched pattern in scope yet. Glyphs appear as
        non-SM patterns land.
      </p>
    {:else}
      <ul class="do-launcher__list">
        {#each launcherRows as row (row.id ?? row.rid ?? row.matched_hash)}
          {@const action = String(row.action || '?').toUpperCase()}
          {@const hashShort = String(row.matched_hash).slice(0, 8)}
          <li class="do-launcher__item">
            <button
              type="button"
              class="oracle-glyph"
              data-hash={row.matched_hash}
              data-decision={row.id ?? ''}
              on:click={onLauncherClick}
              title={`Show pattern pedigree for this ${action} decision (pattern ${hashShort})`}
              aria-label={`Show pattern pedigree for ${action} decision, pattern ${hashShort}`}
            >
              <span class="oracle-glyph__star" aria-hidden="true">&#9733;</span>
            </button>
            <span class="do-launcher__action do-launcher__action--{action}">{action}</span>
            <span class="do-launcher__hash" title={row.matched_hash}>{hashShort}</span>
          </li>
        {/each}
      </ul>
    {/if}
  </aside>

  <!-- ============ THIN SCRIM (no dim -- the feed stays visible, calm-ambient M1) -->
  {#if open}
    <!-- The scrim is a dismiss target only; the close button + Escape are the
         primary affordances. It carries no role so AT does not announce it. -->
    <div class="wp-scrim" on:click={closePane} aria-hidden="true"></div>
  {/if}

  <!-- ============ WHISPER PANE (non-modal right-edge side-sheet) ============ -->
  <aside
    class="whisper"
    class:is-open={open}
    role="dialog"
    aria-modal="false"
    aria-labelledby="do-wp-eyebrow"
    aria-hidden={open ? 'false' : 'true'}
  >
    <header class="wp-head">
      <div class="wp-head__id">
        <p class="wp-eyebrow" id="do-wp-eyebrow">Pattern pedigree</p>
        <div class="wp-hash-row">
          <span class="wp-hash" title={pedigree ? pedigree.pattern_hash : ''}>
            {pedigree ? pedigree.hash_short : '--------'}
          </span>
          <button
            type="button"
            class="wp-copy"
            data-copied={copied}
            on:click={copyHash}
            disabled={!pedigree}
            aria-label="Copy full pattern hash to clipboard"
          >{copied ? 'Copied' : 'Copy hash'}</button>
        </div>
      </div>
      <button
        type="button"
        class="wp-close"
        bind:this={closeBtn}
        on:click={closePane}
        aria-label="Close pattern pedigree"
      >&times;</button>
    </header>

    <div class="wp-body">
      {#if loading}
        <p class="wp-loading" role="status">Loading pedigree...</p>
      {:else if !pedigree}
        <div class="wp-empty" role="status">
          <p class="wp-empty__glyph" aria-hidden="true">&#9733;</p>
          <p class="wp-empty__txt">No pedigree to show. Pick a decision glyph to inspect its pattern.</p>
        </div>
      {:else}
        {#if usedMock}
          <p class="wp-mock" role="note">
            Sample pedigree -- no live graph_patterns row for this hash yet.
          </p>
        {/if}

        <!-- ===== LAYER 1: PROMOTION LADDER ===== -->
        <section class="wp-section">
          <h3 class="wp-section__title">Layer 1 -- promotion ladder</h3>

          <div
            class="ladder"
            role="list"
            aria-label={`Pattern promotion rungs L0 to L4, current rung L${pedigree.level}`}
          >
            {#each ladderRungs as rung (rung.level)}
              <div
                class="rung"
                class:rung--done={rung.done}
                class:rung--future={rung.future}
                class:rung--current={rung.current}
                role="listitem"
                aria-current={rung.current ? 'step' : undefined}
              >
                {#if !rung.future}<span class="rung__fill" aria-hidden="true"></span>{/if}
                <span class="rung__lbl">{rung.label}</span>
                {#if rung.current}
                  <span class="rung__badge">
                    <span class="dot" aria-hidden="true"></span>{rung.label} -- CURRENT
                  </span>
                {/if}
              </div>
            {/each}
          </div>

          <!-- rung meter: paired TEXT (never a bare bar) -->
          <div class="rung-meter">
            <div class="rung-meter__row">
              <span class="rung-meter__lbl">
                {pedigree.meter.atMax ? 'Top rung' : `Toward L${pedigree.meter.nextLevel} promotion`}
              </span>
              <span class="rung-meter__num">{pedigree.meter.text}</span>
            </div>
            <div
              class="rung-meter__bar"
              role="progressbar"
              aria-valuemin="0"
              aria-valuemax={pedigree.meter.need}
              aria-valuenow={pedigree.meter.have}
              aria-valuetext={pedigree.meter.text}
            >
              <span class="rung-meter__fill" style={`width:${pedigree.meter.pct}%`}></span>
            </div>
          </div>

          <!-- 3-up mono stat strip -->
          <div class="stat-strip">
            <div class="stat">
              <span class="stat__k">Success rate</span>
              <span class="stat__v">{successPct}%</span>
              <span class="stat__sub">{pedigree.successes} / {pedigree.occurrences} hits</span>
            </div>
            <div class="stat">
              <span class="stat__k">Age</span>
              <span class="stat__v">{pedigree.age_days == null ? '--' : `${pedigree.age_days}d`}</span>
              <span class="stat__sub">{pedigree.first_seen_label}</span>
            </div>
            <div class="stat">
              <span class="stat__k">Last reinforced</span>
              <span class="stat__v">{pedigree.last_reinforced_label.split(',')[0] || '--'}</span>
              <span class="stat__sub">{pedigree.last_reinforced_label}</span>
            </div>
          </div>

          <!-- OVERFIT flag: dashed amber chip, ALWAYS paired with the word (M8). -->
          {#if pedigree.overfit.flagged}
            <div
              class="overfit"
              role="note"
              aria-label={`Overfit hint: ${pedigree.overfit.pct} percent of hits on one agent profile${pedigree.overfit.profile ? `, ${pedigree.overfit.profile}` : ''}`}
            >
              <span class="overfit__tag">OVERFIT?</span>
              <span class="overfit__txt">
                {pedigree.overfit.pct}% of hits on one agent profile{pedigree.overfit.profile ? ` (${pedigree.overfit.profile})` : ''}
              </span>
            </div>
          {/if}
        </section>

        <!-- ===== LAYER 2: ANCESTRAL REPLAY (collapsed by default) ===== -->
        {#if obsCount > 0}
          <section class="wp-section">
            <button
              type="button"
              class="replay-toggle"
              aria-expanded={replayOpen}
              aria-controls="do-replay"
              on:click={toggleReplay}
            >
              <span class="replay-toggle__caret" class:is-open={replayOpen} aria-hidden="true">&#9656;</span>
              <span class="wp-section__title wp-section__title--inline">Layer 2 -- ancestral replay</span>
              <span class="replay-toggle__hint">
                {obsCount} observation{obsCount === 1 ? '' : 's'} -- {replayOpen ? 'expanded' : 'collapsed'}
              </span>
            </button>

            {#if replayOpen}
              <div class="replay" id="do-replay">
                <!-- read-only scrubber: visual stepping only, drives NOTHING server-side -->
                <div class="scrubber-wrap">
                  <div class="scrubber-wrap__lbl">
                    <span>Step through observations</span>
                    <span>observation {Math.min(Math.max(scrubIndex, 1), obsCount)} of {obsCount}</span>
                  </div>
                  <input
                    class="scrubber"
                    type="range"
                    min="1"
                    max={obsCount}
                    step="1"
                    value={scrubIndex}
                    on:input={onScrub}
                    aria-label="Step through pattern observations"
                    aria-valuetext={`observation ${Math.min(Math.max(scrubIndex, 1), obsCount)} of ${obsCount}`}
                  />
                </div>

                <div class="timeline">
                  {#each pedigree.observations as obs (obs.seq)}
                    <div
                      class="tnode"
                      class:is-active={activeObs && obs.seq === activeObs.seq}
                    >
                      <div class="tnode__head">
                        <span class="tnode__seq">#{obs.seq}</span>
                        <span class="tnode__ts">{obs.ts_label}</span>
                        <span class="tnode__intent">{obs.intent}</span>
                      </div>
                      <p class="tnode__fp" title={obs.fingerprint}>{obs.fingerprint}</p>
                      {#if obs.match_pct != null}
                        <span class="tnode__conf">match {obs.match_pct}%</span>
                      {/if}
                    </div>
                  {/each}
                </div>
              </div>
            {/if}
          </section>
        {/if}
      {/if}
    </div>

    <!-- BETA annotation footer (required) -->
    <footer class="wp-foot">
      <span class="wp-foot__dot" aria-hidden="true"></span>
      BETA -- default OFF, toggled in Settings &gt; BETA features
    </footer>
  </aside>

  <!-- live region for copy / scrubber announcements -->
  <div class="sr-only" role="status" aria-live="polite">{liveMsg}</div>
{/if}

<style>
  /* ===================================================================
     All color comes from theme.css tokens (--accent / --text* / --border /
     --bg-* / the M4 fixed --badge-* tokens) so the 3 themes retint with no
     class churn. ASCII-only comments.
     =================================================================== */

  /* --- pedigree launcher rail: fixed, bottom-left, deliberately quiet --- */
  .do-launcher {
    position: fixed;
    left: 0.9rem;
    bottom: 0.9rem;
    z-index: 35;
    width: min(15rem, 42vw);
    max-height: 40vh;
    overflow-y: auto;
    padding: 0.5rem 0.6rem;
    background: var(--bg-card, #0c1118);
    border: 1px solid var(--border, #192030);
    border-radius: 8px;
    box-shadow: 0 8px 26px rgba(0, 0, 0, 0.4);
  }
  .do-launcher__cap {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.5rem;
    margin-bottom: 0.4rem;
  }
  .do-launcher__eyebrow {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.6rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--accent, #f59e0b);
  }
  .do-launcher__hint {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.58rem;
    color: var(--text-dim, #948870);
  }
  .do-launcher__empty {
    margin: 0;
    font-size: 0.68rem;
    line-height: 1.4;
    color: var(--text-dim, #948870);
  }
  .do-launcher__list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.28rem; }
  .do-launcher__item {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    min-width: 0;
  }
  .do-launcher__action {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.62rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-dim, #948870);
  }
  .do-launcher__action--ALLOW     { color: var(--c-allow, #22c55e); }
  .do-launcher__action--SUGGEST   { color: var(--c-suggest, #84cc16); }
  .do-launcher__action--GUIDE     { color: var(--c-guide, #eab308); }
  .do-launcher__action--INTERVENE { color: var(--c-intervene, #f97316); font-weight: 600; }
  .do-launcher__action--BLOCK     { color: var(--c-block, #ef4444); font-weight: 700; }
  .do-launcher__hash {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.62rem;
    color: var(--text-ui, #8a8068);
    margin-left: auto;
  }

  /* --- the oracle glyph: a single hairline chip, real <button> --- */
  .oracle-glyph {
    appearance: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.25rem;
    height: 1.25rem;
    padding: 0;
    border: 1px solid var(--border-hi, rgba(245, 158, 11, 0.25));
    border-radius: 4px;
    background: transparent;
    color: var(--accent, #f59e0b);
    font-size: 0.78rem;
    line-height: 1;
    cursor: pointer;
    flex: 0 0 auto;
    transition: border-color 0.16s ease, background 0.16s ease;
  }
  .oracle-glyph:hover {
    border-color: var(--accent, #f59e0b);
    background: var(--accent-dim, rgba(245, 158, 11, 0.09));
  }
  .oracle-glyph:focus-visible {
    outline: 2px solid #d97706;
    outline-offset: 2px;
  }
  .oracle-glyph__star { display: block; }

  /* --- thin scrim: NO dim (feed stays visible, calm-ambient M1) --- */
  .wp-scrim {
    position: fixed;
    inset: 0;
    background: transparent;
    z-index: 40;
  }

  /* --- whisper pane: non-modal right-edge side-sheet --- */
  .whisper {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: min(360px, 90vw);
    z-index: 50;
    background: var(--bg-card, #0c1118);
    border-left: 1px solid var(--border-hi, rgba(245, 158, 11, 0.25));
    box-shadow: -18px 0 48px rgba(0, 0, 0, 0.45);
    transform: translateX(100%);
    transition: transform 0.22s ease;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    /* hidden offscreen state is not interactive */
    visibility: hidden;
  }
  .whisper.is-open {
    transform: translateX(0);
    visibility: visible;
  }

  .wp-head {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    padding: 1rem 1.1rem 0.85rem;
    border-bottom: 1px solid var(--border, #192030);
  }
  .wp-head__id { min-width: 0; }
  .wp-eyebrow {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.6rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--text-ui, #8a8068);
    margin: 0 0 0.3rem;
  }
  .wp-hash-row { display: flex; align-items: center; gap: 0.5rem; }
  .wp-hash {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.92rem;
    font-weight: 700;
    color: var(--text-bright, #e8e0cc);
    letter-spacing: 0.02em;
  }
  .wp-copy {
    appearance: none;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.58rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-dim, #948870);
    background: transparent;
    border: 1px solid var(--border, #192030);
    border-radius: 3px;
    padding: 0.12rem 0.4rem;
    cursor: pointer;
  }
  .wp-copy:hover:not(:disabled) { color: var(--accent, #f59e0b); border-color: var(--accent, #f59e0b); }
  .wp-copy:disabled { opacity: 0.5; cursor: default; }
  .wp-copy[data-copied='true'] { color: var(--badge-decided-fg, #16a34a); border-color: var(--badge-decided-border, #86efac); }
  .wp-copy:focus-visible, .wp-close:focus-visible { outline: 2px solid #d97706; outline-offset: 2px; }
  .wp-close {
    appearance: none;
    margin-left: auto;
    width: 1.8rem;
    height: 1.8rem;
    border: 1px solid var(--border, #192030);
    border-radius: 5px;
    background: transparent;
    color: var(--text-dim, #948870);
    font-size: 1rem;
    line-height: 1;
    cursor: pointer;
    flex: 0 0 auto;
  }
  .wp-close:hover { color: var(--accent, #f59e0b); border-color: var(--accent, #f59e0b); }

  .wp-body { padding: 1rem 1.1rem 1.2rem; overflow-y: auto; flex: 1 1 auto; }

  .wp-loading { margin: 0; font-size: 0.78rem; color: var(--text-dim, #948870); }
  .wp-mock {
    margin: 0 0 0.9rem;
    font-size: 0.66rem;
    line-height: 1.4;
    color: var(--text-dim, #948870);
    border: 1px dashed var(--border-hi, rgba(245, 158, 11, 0.25));
    border-radius: 4px;
    padding: 0.35rem 0.5rem;
  }

  .wp-section + .wp-section { margin-top: 1.3rem; }
  .wp-section__title {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.62rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--accent, #f59e0b);
    margin: 0 0 0.7rem;
  }
  .wp-section__title--inline { margin: 0; }

  /* --- Layer 1 rung ladder (the bespoke signature element) --- */
  .ladder { display: flex; flex-direction: column-reverse; gap: 4px; }
  .rung {
    position: relative;
    display: flex;
    align-items: center;
    gap: 0.55rem;
    height: 1.55rem;
    padding: 0 0.55rem;
    border: 1px solid var(--border, #192030);
    border-radius: 4px;
    background: var(--bg-row-alt, #0b1018);
  }
  .rung__lbl {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.66rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: var(--text-dim, #948870);
    min-width: 1.8ch;
    z-index: 2;
  }
  .rung__fill {
    position: absolute;
    inset: 0;
    border-radius: 3px;
    background: var(--accent-dim, rgba(245, 158, 11, 0.09));
    z-index: 0;
  }
  .rung--done { border-color: var(--border-hi, rgba(245, 158, 11, 0.25)); }
  .rung--done .rung__lbl { color: var(--text-bright, #e8e0cc); }
  .rung--future { opacity: 0.5; }
  .rung--current { border-color: var(--accent, #f59e0b); }
  .rung__badge {
    margin-left: auto;
    z-index: 2;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.56rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--badge-ar-fg, #d97706);
    background: var(--badge-ar-bg, #fef3c7);
    border: 1px solid var(--badge-ar-border, #d97706);
    border-radius: 2px;
    padding: 0.1rem 0.34rem;
  }
  .rung__badge .dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }

  /* rung meter */
  .rung-meter { margin-top: 0.7rem; }
  .rung-meter__row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 0.3rem;
  }
  .rung-meter__lbl { font-size: 0.7rem; color: var(--text-dim, #948870); }
  .rung-meter__num {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.72rem;
    font-weight: 700;
    color: var(--text-bright, #e8e0cc);
    font-variant-numeric: tabular-nums;
  }
  .rung-meter__bar {
    height: 0.42rem;
    border-radius: 999px;
    background: var(--border, #192030);
    overflow: hidden;
  }
  .rung-meter__fill { height: 100%; background: var(--accent, #f59e0b); border-radius: 999px; }

  /* 3-up stat strip */
  .stat-strip { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5rem; margin-top: 0.9rem; }
  .stat {
    border: 1px solid var(--border, #192030);
    border-radius: 5px;
    padding: 0.5rem 0.55rem;
    background: var(--bg-row-alt, #0b1018);
    min-width: 0;
  }
  .stat__k {
    display: block;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.54rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-ui, #8a8068);
    margin-bottom: 0.25rem;
  }
  .stat__v {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.92rem;
    font-weight: 700;
    color: var(--text-bright, #e8e0cc);
    font-variant-numeric: tabular-nums;
  }
  .stat__sub {
    display: block;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.56rem;
    color: var(--text-dim, #948870);
    margin-top: 0.15rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* OVERFIT chip (M8 dashed advisory) */
  .overfit {
    display: inline-flex;
    align-items: baseline;
    gap: 0.5rem;
    margin-top: 0.9rem;
    padding: 0.3rem 0.55rem;
    border: 1px dashed var(--badge-warn-border, #ea580c);
    border-radius: 4px;
    background: rgba(234, 88, 12, 0.06);
  }
  .overfit__tag {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.58rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--badge-warn-fg, #ea580c);
  }
  .overfit__txt { font-size: 0.72rem; color: var(--text-dim, #948870); }

  /* --- Layer 2 ancestral replay --- */
  .replay-toggle {
    appearance: none;
    width: 100%;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: transparent;
    border: none;
    padding: 0;
    cursor: pointer;
    text-align: left;
  }
  .replay-toggle:focus-visible { outline: 2px solid #d97706; outline-offset: 2px; }
  .replay-toggle__caret {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.7rem;
    color: var(--text-ui, #8a8068);
    transition: transform 0.16s ease;
    width: 1ch;
  }
  .replay-toggle__caret.is-open { transform: rotate(90deg); }
  .replay-toggle__hint { margin-left: auto; font-size: 0.64rem; color: var(--text-ui, #8a8068); }

  .replay { margin-top: 0.85rem; }
  .scrubber-wrap { margin-bottom: 0.9rem; }
  .scrubber-wrap__lbl {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    font-size: 0.64rem;
    color: var(--text-dim, #948870);
    margin-bottom: 0.3rem;
  }
  .scrubber { width: 100%; accent-color: var(--accent, #f59e0b); }
  .scrubber:focus-visible { outline: 2px solid #d97706; outline-offset: 2px; }

  .timeline { position: relative; padding-left: 1.1rem; }
  .timeline::before {
    content: "";
    position: absolute;
    left: 0.32rem;
    top: 0.2rem;
    bottom: 0.2rem;
    width: 1px;
    background: var(--border, #192030);
  }
  .tnode { position: relative; padding: 0.45rem 0 0.45rem 0.4rem; }
  .tnode::before {
    content: "";
    position: absolute;
    left: -0.85rem;
    top: 0.7rem;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--bg-card, #0c1118);
    border: 1px solid var(--border-hi, rgba(245, 158, 11, 0.25));
  }
  .tnode.is-active::before { background: var(--accent, #f59e0b); border-color: var(--accent, #f59e0b); }
  .tnode.is-active { background: var(--accent-dim, rgba(245, 158, 11, 0.09)); border-radius: 5px; }
  .tnode__head { display: flex; align-items: baseline; gap: 0.5rem; }
  .tnode__seq {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.62rem;
    font-weight: 700;
    color: var(--accent, #f59e0b);
  }
  .tnode__ts { font-family: var(--ff-mono, ui-monospace, monospace); font-size: 0.6rem; color: var(--text-dim, #948870); }
  .tnode__intent {
    margin-left: auto;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.56rem;
    letter-spacing: 0.06em;
    color: var(--text-ui, #8a8068);
    border: 1px solid var(--border, #192030);
    border-radius: 3px;
    padding: 0.05rem 0.3rem;
  }
  .tnode__fp { margin: 0.3rem 0 0; font-size: 0.72rem; line-height: 1.35; color: var(--text, #b8b098); }
  .tnode__conf { font-family: var(--ff-mono, ui-monospace, monospace); font-size: 0.58rem; color: var(--text-dim, #948870); margin-top: 0.15rem; display: block; }

  /* empty / footer */
  .wp-empty { text-align: center; padding: 2.4rem 1rem; color: var(--text-dim, #948870); }
  .wp-empty__glyph { font-size: 1.4rem; color: var(--text-ui, #8a8068); margin: 0 0 0.6rem; }
  .wp-empty__txt { font-size: 0.78rem; line-height: 1.4; margin: 0; }

  .wp-foot {
    padding: 0.7rem 1.1rem;
    border-top: 1px solid var(--border, #192030);
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.6rem;
    letter-spacing: 0.04em;
    color: var(--text-ui, #8a8068);
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }
  .wp-foot__dot { width: 5px; height: 5px; border-radius: 50%; background: var(--badge-ar-fg, #d97706); }

  .sr-only {
    position: absolute; width: 1px; height: 1px; padding: 0;
    margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); border: 0;
  }

  /* reduced motion: kill the slide + caret rotation transitions */
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .whisper,
    :global(html:not([data-motion='allow'])) .replay-toggle__caret,
    :global(html:not([data-motion='allow'])) .oracle-glyph { transition: none; }
  }
  :global(html[data-motion='reduce']) .whisper,
  :global(html[data-motion='reduce']) .replay-toggle__caret { transition: none !important; }

  /* PAPER (light) theme color-contrast (WCAG AA): the action-color tokens
     (--c-*) are AA on the dark obsidian/phosphor surfaces but sub-AA on the
     paper --bg-card (#f8f4ee) cream surface this launcher row sits on. Darken
     the action ink for the paper theme ONLY -- dark themes stay untouched.
     Covers every --do-launcher__action color variant, not only the ones a
     given mock data set happens to render. (color/foreground only.) */
  :global([data-theme='paper']) .do-launcher__action--ALLOW     { color: #15803d; }
  :global([data-theme='paper']) .do-launcher__action--SUGGEST   { color: #4d7c0f; }
  :global([data-theme='paper']) .do-launcher__action--GUIDE     { color: #946700; }
  :global([data-theme='paper']) .do-launcher__action--INTERVENE { color: #9a3412; }
  :global([data-theme='paper']) .do-launcher__action--BLOCK     { color: #b91c1c; }
</style>
