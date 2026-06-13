<!--
  WhatChanged.svelte -- BETA feature #49: What Changed Digest (page-focus
  synthesis overlay).

  WHAT IT DOES
    The operator tabs away from the SM window for a few minutes. The live stores
    keep flowing (decisions stream in, agents poll, escalations enqueue). When the
    operator tabs BACK, instead of hand-scrolling a 300-row firehose to work out
    what moved, ONE collapsible banner at the top of Frame B reads them the story
    in 3 seconds: six paired label+color count-badges --
      (a) new agents  (b) scope changes  (c) confidence delta
      (d) patterns applied  (e) HITL overrides  (f) escalations
    -- each expandable inline for detail. Dismissing writes a localStorage
    watermark so the NEXT return diffs from the dismissal point, not the original
    background point.

  CLIENT-SIDE ONLY. No backend, no new endpoint, no new bus envelope, no new
  table. It reads ONLY the shared, already-self-excluded client stores
  (decisionsStore / escalationStore from sse.js, agentsStore from pollers.js) plus
  localStorage timestamps and the Page Visibility API. It never POSTs, never opens
  /api/commands/stream, never sits on the verdict hot path (M18).

  BETA GATING (default OFF). The component subscribes to NOTHING and registers NO
  Page Visibility listener / window bridge / store reads until
  $betaFlags["what-changed"] is true. The entire body is wrapped in {#if enabled};
  the listeners are added/removed reactively as the flag flips. Flipping OFF tears
  every listener down and clears the banner -- a true no-op when OFF.

  ADR-18 floor honoured:
    - M1 3-frame presence: this is a collapsible banner pinned at the TOP of
      Frame B's existing body. It NEVER adds a 4th frame and never removes one.
    - M2 escalation-only foreground: showing the digest is a DATA signal (the page
      became visible), NOT an escalation -- it enqueues nothing and foregrounds no
      frame. The escalations SECTION merely tallies the shared escalationStore
      (which IS the canonical M2 allow-list); the digest re-decides nothing.
    - M4 paired label+color: every section renders its literal TEXT label + TEXT
      count; the tone dot only reinforces. The confidence trend is carried by a
      "v"/"^" glyph + a signed number, never hue. A zero-count section dims to a
      literal "0", never an empty colored box.
    - M15/G2 polarity: every store it reads is SM-self excluded upstream
      (project_slug NOT IN {streamManager} AND session_id != self). This feature
      adds no query of its own and so cannot surface an SM-self row.
    - M16 domain-agnostic: governed identity (sessionId / projectSlug /
      profile_slug / matched_hash / action band) renders FROM DATA. The action
      bands (ALLOW..BLOCK) are the generic verdict schema, never a hardcoded
      envelope kind / JOB id / role name.
    - M17 a11y AAA: real <button>s in tab order; aria-expanded on each section;
      Escape dismisses; focus moves to the Frame B title on dismiss; an aria-live
      polite region announces the digest on show.

  When the live buffers are empty (headless / fresh load) it falls back to a
  realistic, domain-agnostic MOCK digest (usedMockData) so the feature is testable.

  TESTABILITY: when ON, the component also listens for a documented window bridge
  `what-changed:open` (CustomEvent, detail.mock to force the mock path) so a
  headless test can trigger the digest deterministically without racing the real
  Page Visibility timing. The bridge is a no-op when the flag is OFF (no listener).

  ASCII-only (cp1252-safe): dash is "--". No smart quotes, no em-dashes.
-->
<script>
  import { onDestroy, tick } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { decisionsStore, escalationStore } from '../../sse.js';
  import { agentsStore } from '../../pollers.js';
  import { selectedSession, selectedSessionId } from '../../stores/session.js';
  import { buildDigest, mockDigest } from './WhatChanged-data.js';

  const FLAG_KEY = 'what-changed';
  const WATERMARK_KEY = 'dashboard_last_digest_shown';

  // -- gate: TRUE only while the operator has the BETA flag ON. Everything below
  // (listeners, the banner, the diff) is conditioned on this. -----------------
  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // -- banner state -----------------------------------------------------------
  let visible = false;            // is the banner currently shown?
  let digest = null;              // the built digest (or null)
  let usedMock = false;           // surfaced for tests/telemetry
  let openSection = '';           // the one expanded section key (accordion), or ''
  let liveMsg = '';               // aria-live polite announcement

  // -- background bookkeeping (captured on visibility -> hidden) ---------------
  let hiddenAtMs = null;          // when the tab went hidden (or the watermark)
  let decisionsAtHide = [];       // decision-feed snapshot when the tab hid
  let agentsAtHide = [];          // agent-roster snapshot when the tab hid
  let escLenAtHide = 0;           // escalationStore length when the tab hid

  /** @type {HTMLElement|null} */
  let bannerEl = null;

  // The six sections, in mockup order. label/count derive from the built digest;
  // `tone` is a secondary color cue only (the text label+count are the signal).
  const SECTIONS = [
    { key: 'newAgents', label: 'New agents' },
    { key: 'scope', label: 'Scope changes' },
    { key: 'conf', label: 'Confidence' },
    { key: 'learn', label: 'Patterns applied' },
    { key: 'hitl', label: 'HITL overrides' },
    { key: 'esc', label: 'Escalations' },
  ];

  // ---------------------------------------------------------------------------
  // Snapshot on hide / diff on show.
  // ---------------------------------------------------------------------------

  function snapshotNow() {
    hiddenAtMs = readWatermark() ?? Date.now();
    decisionsAtHide = ($decisionsStore || []).slice();
    agentsAtHide = ($agentsStore || []).slice();
    escLenAtHide = ($escalationStore || []).length;
  }

  function readWatermark() {
    if (typeof localStorage === 'undefined') return null;
    try {
      const raw = localStorage.getItem(WATERMARK_KEY);
      if (!raw) return null;
      const n = Date.parse(raw);
      return Number.isFinite(n) ? n : null;
    } catch { return null; }
  }

  function writeWatermark() {
    if (typeof localStorage === 'undefined') return;
    try { localStorage.setItem(WATERMARK_KEY, new Date().toISOString()); } catch { /* noop */ }
  }

  /**
   * Build + show the digest from the buffered material captured at hide-time vs
   * the live stores now. forceMock=true (or empty live buffers) falls back to the
   * realistic mock so the banner is demonstrable/testable headless.
   * @param {boolean} [forceMock]
   */
  async function showDigest(forceMock) {
    const now = Date.now();
    const sinceMs = hiddenAtMs || now - 6 * 60000;

    // Decisions that arrived since the tab hid: rows present now whose id is not
    // in the at-hide snapshot. The feed is capped/self-excluded upstream.
    const hideIds = new Set(
      decisionsAtHide.map((r) => r && (r.id ?? r.rid)).filter((x) => x != null),
    );
    const decisionsSince = ($decisionsStore || []).filter(
      (r) => r && !hideIds.has(r.id ?? r.rid),
    );
    // New escalations captured since hide (the store only grows; slice the tail).
    const escalationsSince = ($escalationStore || []).slice(escLenAtHide);

    const sess = $selectedSession;
    const live = buildDigest({
      sinceMs,
      untilMs: now,
      decisionsSince,
      decisionsBaseline: decisionsAtHide,
      agentsBefore: agentsAtHide,
      agentsAfter: ($agentsStore || []).slice(),
      escalationsSince,
      sessionId: (sess && sess.id) || $selectedSessionId || null,
      projectSlug: (sess && sess.project_slug) || null,
    });

    // Fall back to the mock ONLY when forced OR when the live stores were empty
    // (so there was nothing real to diff). With real data we ALWAYS show real.
    const storesEmpty = ($decisionsStore || []).length === 0
      && ($agentsStore || []).length === 0;
    if (forceMock || (storesEmpty && decisionsSince.length === 0)) {
      digest = mockDigest(now);
      usedMock = true;
    } else {
      digest = live;
      usedMock = false;
    }

    openSection = '';
    visible = true;
    liveMsg = digest.calm
      ? 'No changes while you were away.'
      : `What changed: ${digest.counts.newAgents} new agents, `
        + `${digest.counts.scope} scope changes, ${digest.counts.patterns} patterns, `
        + `${digest.counts.hitl} HITL overrides, ${digest.counts.escalations} escalations.`;
    await tick();
  }

  // ---------------------------------------------------------------------------
  // Page Visibility wiring -- only attached while `enabled`.
  // ---------------------------------------------------------------------------

  function onVisibilityChange() {
    if (!enabled || typeof document === 'undefined') return;
    if (document.hidden) {
      snapshotNow();
    } else {
      // Returned to the tab: synthesize the digest. If we never captured a hide
      // (e.g. flag flipped ON while already visible), use the watermark/default.
      if (hiddenAtMs == null) snapshotNow();
      showDigest(false);
    }
  }

  // Documented test bridge: trigger the digest deterministically (detail.mock to
  // force the mock data path). No-op when the flag is OFF (no listener attached).
  function onBridge(e) {
    if (!enabled) return;
    const forceMock = !!(e && e.detail && e.detail.mock);
    if (hiddenAtMs == null) snapshotNow();
    showDigest(forceMock);
  }

  function onKeydown(e) {
    if (!visible) return;
    if (e.key === 'Escape') { e.preventDefault(); dismiss(); }
  }

  let _listening = false;
  function attach() {
    if (_listening || typeof document === 'undefined') return;
    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('what-changed:open', onBridge);
    document.addEventListener('keydown', onKeydown);
    _listening = true;
    // If the tab is already hidden when the operator enables the feature, capture
    // a baseline now so the next return has something to diff against.
    if (document.hidden) snapshotNow();
  }
  function detach() {
    if (!_listening || typeof document === 'undefined') return;
    document.removeEventListener('visibilitychange', onVisibilityChange);
    window.removeEventListener('what-changed:open', onBridge);
    document.removeEventListener('keydown', onKeydown);
    _listening = false;
  }

  // Reactively attach/detach as the flag flips. OFF => full teardown + clear.
  $: if (enabled) attach(); else teardown();

  function teardown() {
    detach();
    visible = false;
    digest = null;
    usedMock = false;
    openSection = '';
    hiddenAtMs = null;
    decisionsAtHide = [];
    agentsAtHide = [];
    escLenAtHide = 0;
    liveMsg = '';
  }

  onDestroy(() => { teardown(); });

  // ---------------------------------------------------------------------------
  // Section interaction.
  // ---------------------------------------------------------------------------

  /** @param {string} key @returns {{count:number|string, tone:string, zero:boolean}} */
  function sectionMeta(key) {
    if (!digest) return { count: 0, tone: 'calm', zero: true };
    const c = digest.counts;
    switch (key) {
      case 'newAgents': return { count: c.newAgents, tone: 'calm', zero: c.newAgents === 0 };
      case 'scope': return { count: c.scope, tone: c.scope ? 'intervene' : 'calm', zero: c.scope === 0 };
      case 'conf': {
        const t = digest.confidence.trend;
        const tone = t === 'down' ? 'guide' : t === 'up' ? 'allow' : 'calm';
        return { count: signed(digest.confidence.delta), tone, zero: t === 'flat' && digest.confidence.n === 0 };
      }
      case 'learn': return { count: c.patterns, tone: c.patterns ? 'suggest' : 'calm', zero: c.patterns === 0 };
      case 'hitl': return { count: c.hitl, tone: c.hitl ? 'accent' : 'calm', zero: c.hitl === 0 };
      case 'esc': return { count: c.escalations, tone: c.escalations ? 'block' : 'calm', zero: c.escalations === 0 };
      default: return { count: 0, tone: 'calm', zero: true };
    }
  }

  function toggleSection(key) {
    const meta = sectionMeta(key);
    if (meta.zero) return; // a zero-count section is non-interactive (calm)
    openSection = openSection === key ? '' : key;
  }

  function dismiss() {
    visible = false;
    openSection = '';
    writeWatermark();
    // Move focus to the Frame B title so the operator keeps an anchored position.
    if (typeof document !== 'undefined') {
      const title = document.querySelector('#frameB .fh__title, #frameB h2');
      if (title && typeof title.focus === 'function') {
        title.setAttribute('tabindex', '-1');
        title.focus();
      }
    }
    liveMsg = 'Digest dismissed.';
  }

  // -- small display helpers --------------------------------------------------
  function signed(n) {
    const v = Number(n) || 0;
    const s = v > 0 ? '+' : '';
    return `${s}${v.toFixed(2)}`;
  }
  function confArrow(trend) { return trend === 'down' ? 'v' : trend === 'up' ? '^' : '-'; }
  function bandClass(b) { return `wc-tag wc-tag--${String(b || '').toLowerCase()}`; }
</script>

{#if enabled && visible && digest}
  <section
    class="wc-digest"
    class:wc-digest--calm={digest.calm}
    aria-label="What changed while you were away"
    bind:this={bannerEl}
    data-testid="what-changed-digest"
    data-mock={usedMock ? 'true' : 'false'}
  >
    <p class="wc-sr-only" aria-live="polite" data-testid="what-changed-live">{liveMsg}</p>

    {#if digest.calm}
      <!-- CALM null-state: a single OK one-liner, no count badges. -->
      <div class="wc-calm">
        <span class="wc-ok-dot" aria-hidden="true"></span>
        <span class="wc-calm__text">
          No changes while you were away -- roster, confidence, patterns,
          overrides, and escalations all steady.
        </span>
        <span class="wc-beta">BETA -- default OFF, toggled in Settings</span>
        <button
          type="button"
          class="wc-dismiss"
          aria-label="Dismiss digest (Esc)"
          on:click={dismiss}
        >&times;</button>
      </div>
    {:else}
      <!-- CHANGED case: the six-badge manifest line. -->
      <div class="wc-bar">
        <span class="wc-eyebrow">
          <span class="wc-pulse" aria-hidden="true"></span>
          SINCE YOU LEFT -- {digest.awayLabel}
        </span>

        <div class="wc-badges" role="group" aria-label="Six change sections; expand any for detail">
          {#each SECTIONS as s, i (s.key)}
            {@const m = sectionMeta(s.key)}
            <button
              type="button"
              class="wc-badge wc-badge--{m.tone}"
              class:wc-badge--zero={m.zero}
              aria-expanded={openSection === s.key}
              aria-controls={`wc-panel-${s.key}`}
              aria-disabled={m.zero}
              data-section={s.key}
              on:click={() => toggleSection(s.key)}
            >
              <span class="wc-badge__dot" aria-hidden="true"></span>
              <span class="wc-badge__label">{s.label}</span>
              {#if s.key === 'conf'}
                <span class="wc-conf-arrow" aria-hidden="true">{confArrow(digest.confidence.trend)}</span>
              {/if}
              <span class="wc-badge__count">{m.count}</span>
              {#if s.key === 'conf' && digest.confidence.spark}
                <svg class="wc-spark" width="44" height="16" viewBox="0 0 44 16" aria-hidden="true">
                  <polyline points={digest.confidence.spark} fill="none"
                    stroke="currentColor" stroke-width="1.5"
                    stroke-linecap="round" stroke-linejoin="round" />
                </svg>
              {/if}
              {#if !m.zero}<span class="wc-badge__chev" aria-hidden="true">&gt;</span>{/if}
            </button>
            {#if i < SECTIONS.length - 1}<span class="wc-sep" aria-hidden="true">&middot;</span>{/if}
          {/each}
        </div>

        <div class="wc-right">
          <span class="wc-beta" title="Default OFF; enabled in Settings > BETA features">
            BETA -- default OFF, toggled in Settings{#if usedMock} &middot; sample data{/if}
          </span>
          <button
            type="button"
            class="wc-dismiss"
            aria-label="Dismiss digest (Esc) -- writes the dismissal watermark"
            on:click={dismiss}
          >&times;</button>
        </div>
      </div>

      <!-- expandable detail panels (inline accordion) -->
      {#if openSection}
        <div class="wc-details">
          {#if openSection === 'newAgents'}
            <div class="wc-panel" id="wc-panel-newAgents">
              <h4>New agents -- first seen while away</h4>
              {#if digest.newAgents.length}
                <div class="wc-rows">
                  {#each digest.newAgents as a (a.profile_slug)}
                    <div class="wc-row">
                      <span class="wc-chip"><span class="wc-chip__dot" aria-hidden="true"></span>{a.profile_slug}</span>
                      {#if a.session_id}<span>session {a.session_id}</span>{/if}
                      <span class="wc-ts">first seen {a.first_seen_label}</span>
                    </div>
                  {/each}
                </div>
              {:else}<p class="wc-empty">No new agents.</p>{/if}
            </div>
          {:else if openSection === 'scope'}
            <div class="wc-panel" id="wc-panel-scope">
              <h4>Agent scope changes</h4>
              <div class="wc-rows">
                {#each digest.scopeChanges as c (c.profile_slug + c.ts_label)}
                  <div class="wc-row">
                    <span class="wc-chip"><span class="wc-chip__dot" aria-hidden="true"></span>{c.profile_slug}</span>
                    <span class={bandClass(c.from)}>{c.from}</span>
                    <span class="wc-arrow" aria-hidden="true">--&gt;</span>
                    <span class={bandClass(c.to)}>{c.to}</span>
                    <span class="wc-ts">at {c.ts_label}</span>
                  </div>
                {/each}
              </div>
            </div>
          {:else if openSection === 'conf'}
            <div class="wc-panel" id="wc-panel-conf">
              <h4>Rolling-mean confidence -- {digest.confidence.before.toFixed(2)} to {digest.confidence.after.toFixed(2)} (delta {signed(digest.confidence.delta)}, n={digest.confidence.n})</h4>
              <div class="wc-rows">
                <div class="wc-row">
                  <svg class="wc-spark" width="120" height="34" viewBox="0 0 44 16" aria-hidden="true">
                    <polyline points={digest.confidence.spark} fill="none"
                      stroke="currentColor" stroke-width="1.2"
                      stroke-linecap="round" stroke-linejoin="round" />
                  </svg>
                  <span>before <b>{digest.confidence.before.toFixed(2)}</b>
                    <span class="wc-arrow" aria-hidden="true">--&gt;</span>
                    after <b>{digest.confidence.after.toFixed(2)}</b></span>
                  <span class="wc-ts">{digest.confidence.trend} trend ({confArrow(digest.confidence.trend)})</span>
                </div>
              </div>
            </div>
          {:else if openSection === 'learn'}
            <div class="wc-panel" id="wc-panel-learn">
              <h4>Learn-Mode patterns applied (advisory only -- never overrides safety)</h4>
              <div class="wc-rows">
                {#each digest.patterns as p (p.hash)}
                  <div class="wc-row">
                    <span class="wc-chip wc-chip--hash"><span class="wc-chip__dot" aria-hidden="true"></span>{p.hash}</span>
                    <span>applied {p.count}x -- pre-fill bias (advisory only)</span>
                  </div>
                {/each}
              </div>
            </div>
          {:else if openSection === 'hitl'}
            <div class="wc-panel" id="wc-panel-hitl">
              <h4>HITL override tally -- {digest.hitl.total} total</h4>
              <div class="wc-tally">
                {#each ['ALLOW', 'SUGGEST', 'GUIDE', 'INTERVENE', 'BLOCK'] as b (b)}
                  {@const n = digest.hitl.byAction[b] || 0}
                  <span class="wc-tally__item" class:is-zero={n === 0}><b>{n}</b> {b}</span>
                {/each}
              </div>
              <p class="wc-note">Each override is remembered for the next matching pattern -- the HITL gate stays absolute.</p>
            </div>
          {:else if openSection === 'esc'}
            <div class="wc-panel" id="wc-panel-esc">
              <h4>Escalation summary -- {digest.escalations.total} total</h4>
              <div class="wc-tally">
                {#each Object.entries(digest.escalations.byType) as [t, n] (t)}
                  <span class="wc-tally__item" class:is-zero={n === 0}><b>{n}</b> {t}</span>
                {:else}
                  <span class="wc-tally__item is-zero"><b>0</b> none</span>
                {/each}
              </div>
            </div>
          {/if}
        </div>
      {/if}
    {/if}
  </section>
{/if}

<style>
  /* All selectors are .wc-* scoped so this feature pollutes no shared class.
     Tokens come from theme.css with documented fallbacks. The role-calm slate
     mirrors the RoleBadge idiom; the five action colors are the verdict schema. */

  .wc-digest {
    position: relative;
    border-bottom: 1px solid var(--border, #192030);
    background:
      linear-gradient(90deg, var(--accent-dim, rgba(245,158,11,0.09)), transparent 38%),
      var(--bg-row-alt, #0b1018);
  }
  .wc-digest::before {
    content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
    background: var(--accent, #f59e0b); opacity: 0.8;
  }

  .wc-sr-only {
    position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
    overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
  }

  .wc-bar {
    display: flex; align-items: center; flex-wrap: wrap;
    gap: 10px 16px; padding: 13px 16px 13px 19px;
  }

  .wc-eyebrow {
    display: inline-flex; align-items: center; gap: 8px;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 10px; letter-spacing: 0.16em; text-transform: uppercase;
    color: var(--text-dim, #948870); white-space: nowrap;
  }
  .wc-pulse {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--accent, #f59e0b);
    box-shadow: 0 0 6px var(--accent-glow, rgba(245,158,11,0.35));
  }

  .wc-badges { display: flex; align-items: stretch; flex-wrap: wrap; gap: 4px 2px; margin-left: 4px; }
  .wc-sep {
    align-self: center; color: var(--text-dim, #948870); opacity: 0.5;
    font-family: var(--font-d, var(--ff-mono)); padding: 0 6px; user-select: none;
  }

  /* one section badge = real <button>, tone dot (aria-hidden) + TEXT label +
     TEXT count. Color only reinforces; label+count are load-bearing (M4). */
  .wc-badge {
    display: inline-flex; align-items: center; gap: 8px;
    font-family: var(--font-d, var(--ff-mono)); font-size: 12px;
    color: var(--text-bright, #e8e0cc);
    background: var(--role-calm-bg, rgba(148,163,184,0.07));
    border: 1px solid var(--role-calm-bd, rgba(148,163,184,0.26));
    border-radius: 3px; padding: 5px 10px; cursor: pointer;
    transition: background 120ms ease, border-color 120ms ease;
  }
  .wc-badge:hover { background: var(--bg-row-hover, #131c2a); }
  .wc-badge[aria-expanded='true'] {
    border-color: var(--border-hi, rgba(245,158,11,0.25));
    background: var(--accent-dim, rgba(245,158,11,0.09));
  }
  .wc-badge__dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; flex: 0 0 auto; opacity: 0.9; }
  .wc-badge__label {
    color: var(--text-dim, #948870); letter-spacing: 0.04em;
    text-transform: uppercase; font-size: 10px;
  }
  .wc-badge__count { font-weight: 700; font-size: 13px; letter-spacing: 0.01em; }
  .wc-badge__chev { color: var(--text-dim, #948870); font-size: 9px; margin-left: 1px; }

  /* per-section tone tints (the DOT carries hue; the count text + label are the
     real signal). A zero-count section dims to a literal dash, never an empty box. */
  .wc-badge--calm .wc-badge__dot { color: var(--role-calm-fg, #93a4bd); }
  .wc-badge--intervene .wc-badge__dot { color: var(--c-intervene, #f97316); }
  .wc-badge--guide .wc-badge__dot { color: var(--c-guide, #eab308); }
  .wc-badge--allow .wc-badge__dot { color: var(--c-allow, #22c55e); }
  .wc-badge--suggest .wc-badge__dot { color: var(--c-suggest, #84cc16); }
  .wc-badge--accent .wc-badge__dot { color: var(--accent, #f59e0b); }
  .wc-badge--block .wc-badge__dot { color: var(--c-block, #ef4444); }

  .wc-badge--zero {
    color: var(--text-dim, #948870); cursor: default;
    background: transparent; border-color: transparent;
  }
  .wc-badge--zero:hover { background: transparent; }
  .wc-badge--zero .wc-badge__count { font-weight: 600; color: var(--text-dim, #948870); }

  .wc-conf-arrow { font-weight: 800; font-size: 13px; line-height: 1; color: currentColor; }
  .wc-badge--guide .wc-conf-arrow { color: var(--c-guide, #eab308); }
  .wc-badge--allow .wc-conf-arrow { color: var(--c-allow, #22c55e); }
  .wc-spark { display: inline-block; vertical-align: middle; margin-left: 2px; }
  .wc-badge--guide .wc-spark { color: var(--c-guide, #eab308); }
  .wc-badge--allow .wc-spark { color: var(--c-allow, #22c55e); }
  .wc-badge--calm .wc-spark { color: var(--role-calm-fg, #93a4bd); }

  .wc-right { margin-left: auto; display: inline-flex; align-items: center; gap: 12px; }
  .wc-beta {
    font-family: var(--font-d, var(--ff-mono)); font-size: 9.5px; letter-spacing: 0.05em;
    color: var(--text-dim, #948870);
    border: 1px dashed var(--border, #192030); border-radius: 999px;
    padding: 3px 9px; white-space: nowrap;
  }
  .wc-dismiss {
    display: inline-flex; align-items: center; justify-content: center;
    width: 26px; height: 26px;
    font-family: var(--font-d, var(--ff-mono)); font-size: 14px; line-height: 1;
    color: var(--text-dim, #948870);
    background: none; border: 1px solid var(--border, #192030); border-radius: 4px;
    cursor: pointer; flex: 0 0 auto;
  }
  .wc-dismiss:hover { color: var(--text-bright, #e8e0cc); border-color: var(--border-hi, rgba(245,158,11,0.25)); }

  /* inline detail panels */
  .wc-details { border-top: 1px dashed var(--border, #192030); }
  .wc-panel { padding: 14px 16px 16px 19px; }
  .wc-panel h4 {
    margin: 0 0 10px; font-family: var(--font-d, var(--ff-mono)); font-size: 10px;
    letter-spacing: 0.12em; text-transform: uppercase;
    color: var(--text-dim, #948870); font-weight: 700;
  }
  .wc-rows { display: flex; flex-direction: column; gap: 7px; }
  .wc-row {
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
    font-family: var(--font-d, var(--ff-mono)); font-size: 12px; color: var(--text, #b8b098);
    background: var(--bg-row, #0e141e); border: 1px solid var(--border, #192030);
    border-radius: 4px; padding: 7px 11px;
  }
  .wc-row b { color: var(--text-bright, #e8e0cc); }
  .wc-ts { color: var(--text-dim, #948870); font-size: 11px; margin-left: auto; }
  .wc-arrow { color: var(--c-intervene, #f97316); font-weight: 800; padding: 0 4px; }

  .wc-chip {
    display: inline-flex; align-items: center; gap: 6px;
    font-family: var(--font-d, var(--ff-mono)); font-size: 11px; font-weight: 600;
    color: var(--role-calm-fg, #93a4bd);
    background: var(--role-calm-bg, rgba(148,163,184,0.07));
    border: 1px solid var(--role-calm-bd, rgba(148,163,184,0.26));
    border-radius: 2px; padding: 3px 8px; letter-spacing: 0.02em;
  }
  .wc-chip__dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; opacity: 0.85; }
  .wc-chip--hash {
    color: var(--c-suggest, #84cc16);
    border-color: rgba(132,204,22,0.3); background: rgba(132,204,22,0.08);
  }

  /* verdict-band tags (paired text + color) */
  .wc-tag {
    font-family: var(--font-d, var(--ff-mono)); font-size: 11px; font-weight: 700;
    letter-spacing: 0.05em; padding: 2px 8px; border-radius: 2px;
    border: 1px solid var(--border, #192030); color: var(--text-bright, #e8e0cc);
  }
  .wc-tag--allow { color: var(--c-allow, #22c55e); border-color: rgba(34,197,94,0.4); background: rgba(34,197,94,0.08); }
  .wc-tag--suggest { color: var(--c-suggest, #84cc16); border-color: rgba(132,204,22,0.4); background: rgba(132,204,22,0.08); }
  .wc-tag--guide { color: var(--c-guide, #eab308); border-color: rgba(234,179,8,0.4); background: rgba(234,179,8,0.08); }
  .wc-tag--intervene { color: var(--c-intervene, #f97316); border-color: rgba(249,115,22,0.45); background: rgba(249,115,22,0.1); }
  .wc-tag--block { color: var(--c-block, #ef4444); border-color: rgba(239,68,68,0.45); background: rgba(239,68,68,0.1); }

  .wc-tally { display: flex; flex-wrap: wrap; gap: 8px; }
  .wc-tally__item {
    font-family: var(--font-d, var(--ff-mono)); font-size: 11.5px; color: var(--text, #b8b098);
    background: var(--bg-row, #0e141e); border: 1px solid var(--border, #192030);
    border-radius: 3px; padding: 5px 10px;
  }
  .wc-tally__item b { color: var(--text-bright, #e8e0cc); }
  .wc-tally__item.is-zero, .wc-tally__item.is-zero b { color: var(--text-dim, #948870); }
  .wc-note { margin: 10px 0 0; font-size: 11px; color: var(--text-dim, #948870); }
  .wc-empty { color: var(--text-dim, #948870); font-size: 12px; font-style: italic; }

  /* CALM null-state */
  .wc-calm {
    display: flex; align-items: center; gap: 10px;
    padding: 12px 16px 12px 19px;
    font-family: var(--font-d, var(--ff-mono)); font-size: 12px;
    color: var(--text-dim, #948870); letter-spacing: 0.03em;
  }
  .wc-ok-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--c-allow, #22c55e); opacity: 0.85; flex: 0 0 auto; }
  .wc-calm__text { min-width: 0; }
  .wc-calm .wc-beta { margin-left: auto; }

  /* AAA focus ring -- mirrors the global 2px amber ring. */
  .wc-badge:focus-visible,
  .wc-dismiss:focus-visible {
    outline: 2px solid var(--accent, #f59e0b);
    outline-offset: 2px; border-radius: 4px;
  }

  /* Reduced motion: nothing animates beyond the cheap hover transitions; drop
     them when the operator has not force-allowed motion. */
  :global(html[data-motion='reduce']) .wc-badge,
  :global(html[data-motion='reduce']) .wc-dismiss { transition: none; }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .wc-badge,
    :global(html:not([data-motion='allow'])) .wc-dismiss { transition: none; }
  }
</style>
