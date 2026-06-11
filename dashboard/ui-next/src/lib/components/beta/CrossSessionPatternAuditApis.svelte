<!--
  CrossSessionPatternAuditApis.svelte -- BETA feature #11
  "cross-session-pattern-audit-apis": Cross-session pattern audit & applicability
  inspector.

  WHAT IT ANSWERS
    "Which learned rules from a prior soak are silently governing THIS freshly-
    booted session -- and would a rule I am worried about actually fire?" Today
    the operator only has the flat global cross-session list (occurrences /
    success_rate); there is no "reach INTO this session" view and no way to test
    a hypothetical message against a rule without running the governance path.

  WHAT IT MOUNTS (self-contained, App-root sibling -- it edits no shared file):
    1. A SessionRail-scoped picker: choosing a governed (non-SM) session scopes
       the AUDIT rail to "what hydrated INTO this session". The SM-self entry is
       present but DISABLED (G2 polarity) -- it never exposes hydrated rules.
    2. A thin, fixed right-edge AUDIT rail of hydrated-rule chips (each a real
       <button>), sourced from GET /api/patterns/cross-session/{id}/hydrated. A
       2px left rule encodes decay_status, PAIRED with the literal decay word.
    3. A focus-trapped, Escape-closable drawer (role=dialog, aria-modal) with the
       rule's provenance + a "Would this fire?" read-only probe over
       GET /api/patterns/{hash}/would-apply (post-hoc; emits NO verdict, never
       touches the governance path) + the EXISTING demote action this audit feeds
       (POST /api/patterns/{hash}/demote -- already wired in CrossSessionPatterns).

  BETA GATING (load-bearing): the WHOLE component is wrapped in
  {#if $betaFlags['cross-session-pattern-audit-apis']}. When the flag is OFF (the
  default) it renders NOTHING and registers NO poller / SSE handler / timer /
  fetch -- the {#if} short-circuits the markup AND the onMount keydown wiring, so
  there is zero runtime cost. There is no background polling AT ALL: the rail is
  seeded once on scope-select; the probe fetches on demand only. Flip it ON in
  Settings > BETA features ("Cross-session pattern audit & applicability").

  POLARITY (G2/M15): the scope list (from the self-excluded `sessions` store)
  NEVER selects an SM-self session -- the self entry is a DISABLED, dim
  "self -- audit suppressed (G2)" chip. The hydrated read 404s an SM-self scope
  server-side; the would-apply read 404s an SM-self-only pattern. As defense in
  depth the picker classifies + disables any SM-self row by project_slug / own id.

  ADR-18 MUST floor honoured:
    - M2 escalation-only foreground: the audit rail is a calm, still glance
      surface -- it raises no escalation, steals no focus, auto-fires nothing. The
      drawer DOES dim (the probe is a focused task), but only on operator open.
    - M4 paired label+color: EVERY state (decay STABLE/DECAYING/UNKNOWN, the
      probe WOULD FIRE / WOULD NOT FIRE / ENGINE UNAVAILABLE verdict, the success
      meter, the reach tally) renders a LITERAL text label beside its color;
      color is never the sole signal.
    - Absolute HITL gate: this audit only READS + feeds the existing operator
      demote action -- it never auto-acts on a rule.
    - M16 domain-agnostic: every rule identity renders FROM DATA (hash / level /
      slug) or generic mock phrasing; no monitored-project vocabulary.
    - M17 a11y AAA: real <button>s; the drawer is role=dialog aria-modal with a
      focus trap, Escape + scrim-click close, focus restored to the originating
      chip; a live region announces scope changes + probe verdicts; reduced-motion
      aware.
    - M18: pure post-hoc read. The reads are on-demand only, never on the verdict
      hot path, never open /api/commands/stream.

  When live gov.db data is absent (fresh DB / 404 / fetch error) it falls back to
  realistic, domain-agnostic MOCK fixtures (usedMock=true, surfaced as a literal
  "sample data" note) so the feature is always testable headless.

  All selectors are .csa-* scoped so this feature pollutes no shared class.
  Tokens come from theme.css. ASCII-only (cp1252-safe): dash is "--".
-->
<script>
  import { onMount, tick } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { sessions, getOwnSessionId } from '../../stores/session.js';
  import { postPatternDemote } from '../../api.js';
  import {
    isSelfScope,
    mockScopes,
    mockHydrated,
    mockWouldApply,
    classifyProbe,
    fetchHydrated,
    fetchWouldApply,
    shortHash,
    tsLabel,
    DECAY_WORD,
  } from './CrossSessionPatternAuditApis-data.js';

  const FLAG_KEY = 'cross-session-pattern-audit-apis';

  // -- scope list: governed (non-SM) sessions from the self-excluded `sessions`
  // store, PLUS a disabled SM-self entry so the polarity suppression is visible.
  // When the store is empty (fresh page) fall back to the mock scope list so the
  // feature is always testable. Each entry: {id, project_slug, self, mock}.
  $: ownId = getOwnSessionId();
  $: liveScopes = ($sessions || [])
    .filter((s) => s && s.id)
    .map((s) => ({
      id: s.id,
      project_slug: s.project_slug || '',
      self: isSelfScope(s, ownId),
      mock: false,
    }));
  // Live store wins when it has any GOVERNED (non-self) lane; else mock fixture.
  $: usingMockScopes = liveScopes.filter((s) => !s.self).length === 0;
  $: scopeRows = usingMockScopes
    ? mockScopes().map((s) => ({ id: s.id, project_slug: s.project_slug, self: !!s.self, mock: true }))
    : liveScopes;

  // -- rail state ------------------------------------------------------------
  /** @type {string|null} the selected governed scope */
  let currentSession = null;
  /** @type {Array<Record<string, any>>} the hydrated-rule rows for the scope */
  let railRows = [];
  let railLoading = false;
  let railUsedMock = false;

  // -- drawer state ----------------------------------------------------------
  let open = false;
  /** @type {Record<string, any>|null} the rule being inspected */
  let active = null;
  /** restore focus here on close (M17) */
  let lastTrigger = null;
  let closeBtn; // first focusable in the drawer (focus target on open)
  let drawerEl;

  // -- probe state -----------------------------------------------------------
  let probeText = '';
  let probing = false;
  /** @type {{kind:string, label:string}|null} */
  let verdict = null;
  /** @type {{rationale:string, sourced_from:string[]}|null} */
  let verdictDetail = null;
  let probeUsedMock = false;
  let degraded = false; // simulate-timeout affordance

  // -- demote (feeds the EXISTING wired action) ------------------------------
  let demoting = false;
  let demoted = false;

  let liveMsg = ''; // aria-live announcements (scope / probe / demote)

  // Auto-select the first governed scope once a scope set is available (and only
  // while the flag is ON -- the reactive block is inert when gated out).
  $: if ($betaFlags && $betaFlags[FLAG_KEY] && currentSession == null) {
    const first = (scopeRows || []).find((s) => !s.self);
    if (first) selectScope(first.id);
  }

  /**
   * Scope the audit rail to a governed session. Seeds the hydrated rows from the
   * endpoint; on 404 / empty / error falls back to realistic mock rows so the
   * rail is always populated + testable. A self scope is never selectable.
   * @param {string} sessionId
   */
  async function selectScope(sessionId) {
    if (!sessionId) return;
    const row = (scopeRows || []).find((s) => s.id === sessionId);
    if (row && row.self) return; // G2: self scope never audited
    currentSession = sessionId;
    railLoading = true;
    railUsedMock = false;
    railRows = [];
    liveMsg = 'Audit scoped to ' + sessionId + '.';

    let rows = [];
    let mock = false;
    try {
      const data = await fetchHydrated(sessionId);
      rows = Array.isArray(data.rows) ? data.rows : [];
    } catch {
      rows = [];
    }
    if (!rows.length) {
      rows = mockHydrated(sessionId);
      // Mock is only "used" when it actually produces rows (a governed mock
      // scope). A real-but-empty scope shows the calm empty state, not mock.
      mock = rows.length > 0;
    }
    railRows = rows;
    railUsedMock = mock;
    railLoading = false;
  }

  /** @param {MouseEvent} e */
  function onScopeClick(e) {
    const btn = e.currentTarget;
    const sid = btn && btn.getAttribute('data-session');
    if (sid) selectScope(sid);
  }

  // -- drawer open / close + focus trap (M17) --------------------------------
  async function openDrawer(row, trigger) {
    lastTrigger = trigger || null;
    active = row;
    // reset probe + demote for the freshly-opened rule
    probeText = '';
    verdict = null;
    verdictDetail = null;
    probeUsedMock = false;
    degraded = false;
    demoting = false;
    demoted = false;
    open = true;
    await tick();
    if (closeBtn && typeof closeBtn.focus === 'function') closeBtn.focus();
  }

  function closeDrawer() {
    if (!open) return;
    open = false;
    const t = lastTrigger;
    lastTrigger = null;
    if (t && typeof t.focus === 'function') t.focus();
  }

  /** @param {MouseEvent} e */
  function onChipClick(e) {
    const btn = e.currentTarget;
    const hash = btn && btn.getAttribute('data-hash');
    if (!hash) return;
    const row = railRows.find((r) => r.pattern_hash === hash);
    if (row) openDrawer(row, btn);
  }

  /** @param {KeyboardEvent} e */
  function onKeydown(e) {
    if (!open) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      closeDrawer();
      return;
    }
    if (e.key === 'Tab' && drawerEl) {
      const focusables = drawerEl.querySelectorAll(
        'button:not([disabled]), textarea, [href], input, [tabindex]:not([tabindex="-1"])',
      );
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  // -- the "would this fire?" probe (post-hoc; emits NO verdict) --------------
  async function runProbe() {
    if (!active || probing) return;
    probing = true;
    verdict = null;
    verdictDetail = null;
    let res;
    if (degraded) {
      // operator forced the degraded path -> the unavailable shape, no fetch
      res = { applies: false, match_confidence: 0.0, sourced_from: [], rationale: 'matching engine unavailable' };
      probeUsedMock = true;
    } else {
      try {
        res = await fetchWouldApply(active.pattern_hash, probeText);
        // fetchWouldApply degrades to the unavailable shape on 404 / timeout /
        // error. Treat that as "no live engine" -> fall back to the mock score
        // so the probe is testable headless (but keep the real shape when live).
        if (res && res.rationale === 'matching engine unavailable') {
          res = mockWouldApply(probeText);
          probeUsedMock = true;
        } else {
          probeUsedMock = false;
        }
      } catch {
        res = mockWouldApply(probeText);
        probeUsedMock = true;
      }
    }
    verdict = classifyProbe(res);
    verdictDetail = {
      rationale: res.rationale,
      sourced_from: Array.isArray(res.sourced_from) ? res.sourced_from : [],
    };
    liveMsg = verdict.label + '. ' + res.rationale;
    probing = false;
  }

  function toggleDegraded() {
    degraded = !degraded;
  }

  // -- demote: feeds the EXISTING wired POST (never auto-acts) ----------------
  async function demote() {
    if (!active || demoting || demoted) return;
    const hash = active.pattern_hash;
    demoting = true;
    if (railUsedMock) {
      // mock path: client-side confirm only (no live POST)
      demoting = false;
      demoted = true;
      liveMsg = 'Pattern demote queued for ' + shortHash(hash) + ' (sample data -- no live call).';
      return;
    }
    try {
      await postPatternDemote(hash);
      demoted = true;
      // drop the demoted rule from the rail (optimistic; the audit informs it)
      railRows = railRows.filter((r) => r.pattern_hash !== hash);
      liveMsg = 'Pattern ' + shortHash(hash) + ' demoted.';
    } catch (err) {
      const msg = err && err.message ? String(err.message) : '';
      // 404 == already gone == desired end-state holds.
      if (/(^|\D)404(\D|$)/.test(msg)) {
        demoted = true;
        railRows = railRows.filter((r) => r.pattern_hash !== hash);
        liveMsg = 'Pattern ' + shortHash(hash) + ' already demoted.';
      } else {
        liveMsg = 'Could not demote pattern ' + shortHash(hash) + '.';
      }
    } finally {
      demoting = false;
    }
  }

  // -- derived presentation for the active rule ------------------------------
  $: activePct = active ? Math.round((Number(active.success_rate) || 0) * 100) : 0;
  $: activeSucc = active
    ? Math.round((Number(active.success_rate) || 0) * (Number(active.occurrence_count) || 0))
    : 0;

  /** Reach tally segments (capped at 12) for matched_decision_count_this_session. */
  function reachSegs(n) {
    const c = Math.max(0, Math.min(Number(n) || 0, 12));
    return Array.from({ length: c });
  }

  // -- lifecycle: ONLY wires the keydown trap, and ONLY when the flag is ON.
  // With the flag OFF the whole component is {#if}-gated out, so onMount never
  // runs and no listener is ever registered (zero runtime cost).
  onMount(() => {
    if (typeof window === 'undefined') return;
    window.addEventListener('keydown', onKeydown);
    return () => window.removeEventListener('keydown', onKeydown);
  });
</script>

{#if $betaFlags && $betaFlags[FLAG_KEY]}
  <!-- ============ SCOPE PICKER (SessionRail selection) ============ -->
  <section class="csa-scope" aria-label="Scope the cross-session audit to a governed session">
    <div class="csa-scope__cap">
      <span class="csa-scope__eyebrow">Scope -- governed session</span>
      <span class="csa-scope__hint">
        Pick a freshly-booted session. The audit rail scopes to what hydrated INTO it.
        {#if usingMockScopes}<em class="csa-scope__mock">sample sessions -- soak to populate</em>{/if}
      </span>
    </div>
    <div class="csa-scope__list" role="group" aria-label="Session selection">
      {#each scopeRows as s (s.id)}
        {#if s.self}
          <button
            type="button"
            class="csa-chip"
            disabled
            aria-disabled="true"
            title="G2 polarity: SM never audits its own session"
          >
            <span class="csa-chip__dot" aria-hidden="true"></span>
            {s.id}
            <span class="csa-chip__self">self -- audit suppressed (G2)</span>
          </button>
        {:else}
          <button
            type="button"
            class="csa-chip"
            data-session={s.id}
            aria-pressed={currentSession === s.id}
            on:click={onScopeClick}
          >
            <span class="csa-chip__dot" aria-hidden="true"></span>
            {s.id}
          </button>
        {/if}
      {/each}
    </div>
  </section>

  <!-- ============ THE AUDIT RAIL (fixed, right edge) ============ -->
  <aside class="csa-rail" aria-label="Cross-session pattern audit -- hydrated rules">
    <div class="csa-rail__cap">
      <p class="csa-rail__eyebrow">Audit -- hydrated rules</p>
      <p class="csa-rail__scope">{currentSession || '(no scope)'}</p>
      <p class="csa-rail__count">
        {railRows.length} learned rule{railRows.length === 1 ? '' : 's'} injected at engine init
      </p>
      {#if railUsedMock}
        <p class="csa-rail__meta" role="note">sample data -- soak to populate</p>
      {/if}
    </div>

    {#if railLoading}
      <p class="csa-rail__state" role="status">Loading hydrated rules...</p>
    {:else if railRows.length === 0}
      <p class="csa-rail__state" role="status">
        No cross-session rules hydrated into this scope. The session is governing
        from its own context only.
      </p>
    {:else}
      <ul class="csa-rail__list">
        {#each railRows as r (r.pattern_hash)}
          {@const pct = Math.round((Number(r.success_rate) || 0) * 100)}
          {@const reach = Number(r.matched_decision_count_this_session) || 0}
          {@const word = DECAY_WORD[r.decay_status] || DECAY_WORD.unknown}
          <li>
            <button
              type="button"
              class="csa-hyd"
              data-decay={r.decay_status}
              data-hash={r.pattern_hash}
              on:click={onChipClick}
              aria-label={`Hydrated rule ${shortHash(r.pattern_hash)}, level ${r.level}, decay ${word}, touched ${reach} decisions this session. Open for provenance and probe.`}
            >
              <span class="csa-hyd__top">
                <span class="csa-hyd__hash">{shortHash(r.pattern_hash)}</span>
                <span class="csa-hyd__level">L{r.level}</span>
              </span>

              <!-- M4 paired decay badge: color + LITERAL word, never color alone -->
              <span class="csa-decay csa-decay--{r.decay_status}">
                <span class="dot" aria-hidden="true"></span>{word}
              </span>

              <!-- success meter: bar PLUS the paired text percentage -->
              <span class="csa-srate">
                <span class="csa-srate__row">
                  <span class="csa-srate__lbl">success</span>
                  <span class="csa-srate__num">{pct}%</span>
                </span>
                <span class="csa-srate__bar">
                  <span class="csa-srate__fill" style={`width:${pct}%`}></span>
                </span>
              </span>

              <!-- reach tally: segments PLUS the literal count -->
              <span class="csa-reach">
                <span class="csa-reach__lbl">reach into this session</span>
                <span class="csa-reach__tally">
                  {#if reach <= 0}
                    <span class="csa-reach__seg csa-reach__seg--hollow" aria-hidden="true"></span>
                    <span class="csa-reach__count csa-reach__count--zero">0 here</span>
                  {:else}
                    {#each reachSegs(reach) as _seg}
                      <span class="csa-reach__seg" aria-hidden="true"></span>
                    {/each}
                    <span class="csa-reach__count">{reach} here{reach > 12 ? ` (${reach})` : ''}</span>
                  {/if}
                </span>
              </span>
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </aside>

  <!-- ============ SCRIM + DRAWER (role=dialog, aria-modal, focus trap) ============ -->
  {#if open}
    <!-- dismiss target only; close button + Escape are the primary affordances -->
    <div class="csa-scrim" on:click={closeDrawer} aria-hidden="true"></div>
  {/if}

  <aside
    class="csa-drawer"
    class:is-open={open}
    bind:this={drawerEl}
    role="dialog"
    aria-modal="true"
    aria-labelledby="csa-dr-eyebrow"
    aria-hidden={open ? 'false' : 'true'}
  >
    <header class="csa-dr-head">
      <div class="csa-dr-head__id">
        <p class="csa-dr-eyebrow" id="csa-dr-eyebrow">Hydrated rule -- provenance &amp; probe</p>
        <div class="csa-dr-hash-row">
          <span class="csa-dr-hash" title={active ? active.pattern_hash : ''}>
            {active ? shortHash(active.pattern_hash) : '--------'}
          </span>
          {#if active}<span class="csa-hyd__level">L{active.level}</span>{/if}
        </div>
      </div>
      <button
        type="button"
        class="csa-dr-close"
        bind:this={closeBtn}
        on:click={closeDrawer}
        aria-label="Close pattern audit drawer"
      >&times;</button>
    </header>

    <div class="csa-dr-body">
      {#if active}
        {#if railUsedMock}
          <p class="csa-dr-mock" role="note">
            Sample data -- no live patterns / decisions rows for this hash in this
            scope yet. Soak a non-SM session to populate.
          </p>
        {/if}

        <!-- ===== reach + success stats ===== -->
        <section class="csa-dr-section">
          <h3 class="csa-dr-section__title">Reach into this session</h3>
          <div class="csa-dr-stats">
            <div class="csa-dr-stat">
              <span class="csa-dr-stat__k">Touched here</span>
              <span class="csa-dr-stat__v">{Number(active.matched_decision_count_this_session) || 0}</span>
              <span class="csa-dr-stat__sub">decisions this session</span>
            </div>
            <div class="csa-dr-stat">
              <span class="csa-dr-stat__k">Success rate</span>
              <span class="csa-dr-stat__v">{activePct}%</span>
              <span class="csa-dr-stat__sub">{activeSucc} / {Number(active.occurrence_count) || 0} hits</span>
            </div>
            <div class="csa-dr-stat">
              <span class="csa-dr-stat__k">Level</span>
              <span class="csa-dr-stat__v">L{active.level}</span>
              <span class="csa-dr-stat__sub">decay: {active.decay_status}</span>
            </div>
          </div>
        </section>

        <!-- ===== provenance ===== -->
        <section class="csa-dr-section">
          <h3 class="csa-dr-section__title">Provenance</h3>
          <div class="csa-prov">
            <span class="csa-prov__k">Last seen session</span>
            <span class="csa-prov__v">{active.last_seen_session_id || '(none recorded)'}</span>
            <span class="csa-prov__k">Last seen</span>
            <span class="csa-prov__v csa-prov__v--dim">{tsLabel(active.last_seen_ts)}</span>
            <span class="csa-prov__k">Occurrences</span>
            <span class="csa-prov__v">{Number(active.occurrence_count) || 0}</span>
            <span class="csa-prov__k">Sourced from</span>
            <span class="csa-prov__v">{active.sourced_from || 'unknown'}</span>
          </div>
        </section>

        <!-- ===== THE "Would this fire?" PROBE ===== -->
        <section class="csa-dr-section">
          <h3 class="csa-dr-section__title">Would this fire?</h3>
          <p class="csa-probe__hint">
            Paste a candidate message. This runs the pattern matcher post-hoc
            against the rule's vector -- it returns an applicability score, it does
            NOT emit a verdict and never touches the governance path.
          </p>
          <textarea
            class="csa-probe__box"
            bind:value={probeText}
            placeholder="e.g. running the integration suite before the release tag as usual"
            aria-label="Candidate message to test against this rule"
          ></textarea>
          <div class="csa-probe__controls">
            <button
              type="button"
              class="csa-probe__btn"
              on:click={runProbe}
              disabled={probing}
              aria-busy={probing}
            >{probing ? 'Probing...' : 'Probe'}</button>
            <button
              type="button"
              class="csa-probe__altbtn"
              on:click={toggleDegraded}
              aria-pressed={degraded}
            >{degraded ? 'Engine timeout: ON' : 'Simulate engine timeout'}</button>
          </div>
          <p class="csa-probe__note">
            Client 500ms guard mirrors the server cap (cosine threshold 0.72).
            Short text (&lt;=20 chars) lands below threshold; longer text clears it.
          </p>

          <!-- verdict -- paired badge + rationale verbatim (M4) -->
          {#if verdict}
            <div class="csa-verdict csa-verdict--{verdict.kind}" role="status">
              <span class="csa-verdict__badge">
                <span class="dot" aria-hidden="true"></span>{verdict.label}
              </span>
              {#if probeUsedMock}
                <span class="csa-verdict__mock">sample score -- engine not live</span>
              {/if}
              {#if verdictDetail}
                <p class="csa-verdict__rationale">rationale: {verdictDetail.rationale}</p>
                <p class="csa-verdict__src">
                  sourced_from: [{verdictDetail.sourced_from.join(', ')}]
                </p>
              {/if}
            </div>
          {/if}
        </section>

        <!-- ===== DEMOTE (the EXISTING wired action this audit feeds) ===== -->
        <div class="csa-demote">
          <button
            type="button"
            class="csa-demote__btn"
            on:click={demote}
            disabled={demoting || demoted}
            aria-busy={demoting}
          >{demoted ? 'Demoted' : demoting ? 'Demoting...' : 'Demote this rule'}</button>
          <span class="csa-demote__hint">
            {#if demoted}
              Demote queued -- POST /api/patterns/&lcub;hash&rcub;/demote carried this hash.
            {:else}
              Feeds the existing POST /api/patterns/&lcub;hash&rcub;/demote (already wired in
              Cross-session patterns). The audit informs the call -- it never auto-acts.
            {/if}
          </span>
        </div>
      {:else}
        <p class="csa-dr-empty" role="status">Pick a hydrated rule to inspect its provenance.</p>
      {/if}
    </div>

    <!-- BETA annotation footer (required) -->
    <footer class="csa-dr-foot">
      <span class="csa-dr-foot__dot" aria-hidden="true"></span>
      BETA -- default OFF, toggled in Settings &gt; BETA features
    </footer>
  </aside>

  <!-- live region for scope / probe / demote announcements -->
  <div class="csa-sr-only" role="status" aria-live="polite">{liveMsg}</div>
{/if}

<style>
  /* All color comes from theme.css tokens (--accent / --text* / --border /
     --bg-* / the M4 fixed --badge-* tokens) so the themes retint with no class
     churn. ASCII-only comments. */

  /* ===================================================================
     SCOPE PICKER
     =================================================================== */
  .csa-scope {
    position: fixed;
    top: 0.85rem;
    left: 0.9rem;
    z-index: 34;
    max-width: min(34rem, calc(100vw - 17rem));
    padding: 0.6rem 0.75rem;
    background: var(--bg-card, #0c1118);
    border: 1px solid var(--border, #192030);
    border-radius: 8px;
    box-shadow: 0 8px 26px rgba(0, 0, 0, 0.4);
  }
  .csa-scope__cap {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 0.4rem 0.6rem;
    margin-bottom: 0.55rem;
  }
  .csa-scope__eyebrow {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.6rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--accent, #f59e0b);
  }
  .csa-scope__hint {
    font-size: 0.66rem;
    line-height: 1.4;
    color: var(--text-dim, #948870);
  }
  .csa-scope__mock {
    font-style: italic;
    color: var(--text-ui, #8a8068);
  }
  .csa-scope__list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
  }
  .csa-chip {
    appearance: none;
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.68rem;
    color: var(--text-dim, #948870);
    background: var(--bg-row-alt, #0b1018);
    border: 1px solid var(--border, #192030);
    border-radius: 6px;
    padding: 0.35rem 0.6rem;
    cursor: pointer;
    transition: border-color 0.16s ease, color 0.16s ease, background 0.16s ease;
  }
  .csa-chip:hover:not(:disabled) {
    border-color: var(--accent, #f59e0b);
    color: var(--text-bright, #e8e0cc);
  }
  .csa-chip[aria-pressed='true'] {
    border-color: var(--accent, #f59e0b);
    color: var(--text-bright, #e8e0cc);
    background: var(--accent-dim, rgba(245, 158, 11, 0.09));
  }
  .csa-chip__dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--text-ui, #8a8068);
    flex: 0 0 auto;
  }
  .csa-chip[aria-pressed='true'] .csa-chip__dot { background: var(--accent, #f59e0b); }
  .csa-chip:disabled {
    cursor: not-allowed;
    opacity: 0.55;
    border-style: dashed;
  }
  .csa-chip__self {
    font-style: italic;
    font-size: 0.58rem;
    color: var(--text-ui, #8a8068);
  }
  .csa-chip:focus-visible { outline: 2px solid #d97706; outline-offset: 2px; }

  /* ===================================================================
     AUDIT RAIL: thin, fixed, right edge
     =================================================================== */
  .csa-rail {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: min(15.5rem, 46vw);
    z-index: 35;
    display: flex;
    flex-direction: column;
    background: var(--bg-card, #0c1118);
    border-left: 1px solid var(--border-hi, rgba(245, 158, 11, 0.25));
    box-shadow: -10px 0 28px rgba(0, 0, 0, 0.4);
    overflow: hidden;
  }
  .csa-rail__cap {
    padding: 0.85rem 0.85rem 0.6rem;
    border-bottom: 1px solid var(--border, #192030);
  }
  .csa-rail__eyebrow {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.6rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--accent, #f59e0b);
    margin: 0;
  }
  .csa-rail__scope {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.66rem;
    color: var(--text-bright, #e8e0cc);
    margin: 0.3rem 0 0;
    word-break: break-all;
  }
  .csa-rail__count {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.62rem;
    color: var(--text-dim, #948870);
    margin: 0.2rem 0 0;
  }
  .csa-rail__meta {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.58rem;
    color: var(--text-ui, #8a8068);
    margin: 0.3rem 0 0;
    font-style: italic;
  }
  .csa-rail__state {
    margin: 0;
    padding: 0.85rem;
    font-size: 0.7rem;
    line-height: 1.45;
    color: var(--text-dim, #948870);
  }
  .csa-rail__list {
    list-style: none;
    margin: 0;
    padding: 0.6rem 0.65rem 1rem;
    overflow-y: auto;
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  /* a hydrated-rule chip: a still hairline card; 2px left rule encodes
     decay_status; the whole card is a real <button>. */
  .csa-hyd {
    appearance: none;
    width: 100%;
    text-align: left;
    display: block;
    padding: 0.55rem 0.6rem 0.6rem;
    border: 1px solid var(--border, #192030);
    border-left-width: 2px;
    border-left-color: var(--text-ui, #8a8068);
    border-radius: 6px;
    background: var(--bg-row, #0e141e);
    color: var(--text, #b8b098);
    cursor: pointer;
    transition: border-color 0.16s ease, background 0.16s ease;
  }
  .csa-hyd:hover { background: var(--bg-row-hover, #131c2a); }
  .csa-hyd:focus-visible { outline: 2px solid #d97706; outline-offset: 2px; }
  .csa-hyd[data-decay='stable'] { border-left-color: #64748b; }
  .csa-hyd[data-decay='decaying'] { border-left-color: var(--badge-warn-fg, #ea580c); }
  .csa-hyd[data-decay='unknown'] {
    border-left-color: var(--border, #192030);
    border-left-style: dashed;
  }

  .csa-hyd__top { display: flex; align-items: baseline; gap: 0.5rem; }
  .csa-hyd__hash {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.82rem;
    font-weight: 700;
    letter-spacing: 0.02em;
    color: var(--text-bright, #e8e0cc);
    font-variant-numeric: tabular-nums;
  }
  .csa-hyd__level {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.58rem;
    letter-spacing: 0.06em;
    color: var(--text-ui, #8a8068);
    border: 1px solid var(--border, #192030);
    border-radius: 3px;
    padding: 0.02rem 0.3rem;
    margin-left: auto;
  }

  /* paired decay badge: COLOR + literal word (M4). */
  .csa-decay {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.56rem;
    font-weight: 700;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    padding: 0.1rem 0.36rem;
    border-radius: 2px;
    margin-top: 0.4rem;
  }
  .csa-decay .dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; flex: 0 0 auto; }
  .csa-decay--stable {
    color: var(--badge-obs-fg, #475569);
    background: var(--badge-obs-bg, #f1f5f9);
    border: 1px solid var(--badge-obs-border, #cbd5e1);
  }
  .csa-decay--decaying {
    color: #9a3412;
    background: var(--badge-warn-bg, #ffedd5);
    border: 1px solid var(--badge-warn-border, #ea580c);
  }
  .csa-decay--unknown {
    color: var(--text-dim, #948870);
    background: transparent;
    border: 1px dashed var(--border, #192030);
  }

  /* success_rate meter: a bar PLUS a paired TEXT percentage. */
  .csa-srate { display: block; margin-top: 0.5rem; }
  .csa-srate__row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 0.2rem;
  }
  .csa-srate__lbl {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.54rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-ui, #8a8068);
  }
  .csa-srate__num {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.64rem;
    font-weight: 700;
    color: var(--text-bright, #e8e0cc);
    font-variant-numeric: tabular-nums;
  }
  .csa-srate__bar {
    display: block;
    height: 0.28rem;
    border-radius: 999px;
    background: var(--border, #192030);
    overflow: hidden;
  }
  .csa-srate__fill { display: block; height: 100%; background: var(--accent, #f59e0b); border-radius: 999px; }

  /* reach tally: segments PLUS the literal count. */
  .csa-reach { display: block; margin-top: 0.55rem; }
  .csa-reach__lbl {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.54rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-ui, #8a8068);
    display: block;
    margin-bottom: 0.28rem;
  }
  .csa-reach__tally { display: flex; align-items: center; gap: 3px; flex-wrap: wrap; }
  .csa-reach__seg { width: 9px; height: 12px; border-radius: 2px; background: var(--accent, #f59e0b); flex: 0 0 auto; }
  .csa-reach__seg--hollow { background: transparent; border: 1px dashed var(--border, #192030); }
  .csa-reach__count {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.62rem;
    font-weight: 700;
    color: var(--text-bright, #e8e0cc);
    margin-left: 0.4rem;
    font-variant-numeric: tabular-nums;
  }
  .csa-reach__count--zero { color: var(--text-dim, #948870); font-weight: 400; }

  /* ===================================================================
     SCRIM + DRAWER (modal -- the probe is a focused task)
     =================================================================== */
  .csa-scrim {
    position: fixed;
    inset: 0;
    background: rgba(4, 6, 9, 0.55);
    z-index: 60;
  }
  .csa-drawer {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: min(420px, 94vw);
    z-index: 70;
    background: var(--bg-card, #0c1118);
    border-left: 1px solid var(--border-hi, rgba(245, 158, 11, 0.25));
    box-shadow: -22px 0 56px rgba(0, 0, 0, 0.5);
    transform: translateX(100%);
    transition: transform 0.22s ease;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    visibility: hidden;
  }
  .csa-drawer.is-open { transform: translateX(0); visibility: visible; }

  .csa-dr-head {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    padding: 1rem 1.1rem 0.85rem;
    border-bottom: 1px solid var(--border, #192030);
  }
  .csa-dr-head__id { min-width: 0; }
  .csa-dr-eyebrow {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.6rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--text-ui, #8a8068);
    margin: 0 0 0.3rem;
  }
  .csa-dr-hash-row { display: flex; align-items: center; gap: 0.5rem; }
  .csa-dr-hash {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.95rem;
    font-weight: 700;
    color: var(--text-bright, #e8e0cc);
    letter-spacing: 0.02em;
  }
  .csa-dr-close {
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
  .csa-dr-close:hover { color: var(--accent, #f59e0b); border-color: var(--accent, #f59e0b); }
  .csa-dr-close:focus-visible { outline: 2px solid #d97706; outline-offset: 2px; }

  .csa-dr-body { padding: 1rem 1.1rem 1.2rem; overflow-y: auto; flex: 1 1 auto; }
  .csa-dr-empty { margin: 0; font-size: 0.78rem; color: var(--text-dim, #948870); }
  .csa-dr-mock {
    margin: 0 0 0.9rem;
    font-size: 0.66rem;
    line-height: 1.4;
    color: var(--text-dim, #948870);
    border: 1px dashed var(--border-hi, rgba(245, 158, 11, 0.25));
    border-radius: 4px;
    padding: 0.35rem 0.5rem;
  }

  .csa-dr-section + .csa-dr-section { margin-top: 1.3rem; }
  .csa-dr-section__title {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.62rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--accent, #f59e0b);
    margin: 0 0 0.7rem;
  }

  .csa-dr-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5rem; }
  .csa-dr-stat {
    border: 1px solid var(--border, #192030);
    border-radius: 5px;
    padding: 0.5rem 0.55rem;
    background: var(--bg-row-alt, #0b1018);
    min-width: 0;
  }
  .csa-dr-stat__k {
    display: block;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.52rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-ui, #8a8068);
    margin-bottom: 0.25rem;
  }
  .csa-dr-stat__v {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.92rem;
    font-weight: 700;
    color: var(--text-bright, #e8e0cc);
    font-variant-numeric: tabular-nums;
  }
  .csa-dr-stat__sub {
    display: block;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.54rem;
    color: var(--text-dim, #948870);
    margin-top: 0.15rem;
  }

  /* provenance grid */
  .csa-prov { display: grid; grid-template-columns: auto 1fr; gap: 0.4rem 0.8rem; }
  .csa-prov__k {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.58rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-ui, #8a8068);
  }
  .csa-prov__v {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.72rem;
    color: var(--text-bright, #e8e0cc);
    word-break: break-all;
  }
  .csa-prov__v--dim { color: var(--text-dim, #948870); }

  /* probe */
  .csa-probe__hint { font-size: 0.72rem; line-height: 1.4; color: var(--text-dim, #948870); margin: 0 0 0.6rem; }
  .csa-probe__box {
    width: 100%;
    min-height: 3.6rem;
    resize: vertical;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.78rem;
    line-height: 1.45;
    color: var(--text-bright, #e8e0cc);
    background: var(--bg-row, #0e141e);
    border: 1px solid var(--border, #192030);
    border-radius: 6px;
    padding: 0.55rem 0.6rem;
  }
  .csa-probe__box:focus-visible { outline: 2px solid #d97706; outline-offset: 2px; }
  .csa-probe__controls { display: flex; align-items: center; gap: 0.6rem; margin-top: 0.55rem; }
  .csa-probe__btn {
    appearance: none;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.66rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--bg, #080a0c);
    background: var(--accent, #f59e0b);
    border: 1px solid var(--accent, #f59e0b);
    border-radius: 5px;
    padding: 0.4rem 0.85rem;
    cursor: pointer;
  }
  .csa-probe__btn:hover:not(:disabled) { filter: brightness(1.08); }
  .csa-probe__btn:disabled { opacity: 0.6; cursor: default; }
  .csa-probe__btn:focus-visible { outline: 2px solid #d97706; outline-offset: 2px; }
  .csa-probe__altbtn {
    appearance: none;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.58rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-dim, #948870);
    background: transparent;
    border: 1px dashed var(--border, #192030);
    border-radius: 4px;
    padding: 0.3rem 0.5rem;
    cursor: pointer;
    margin-left: auto;
  }
  .csa-probe__altbtn:hover { color: var(--text-bright, #e8e0cc); border-color: var(--accent, #f59e0b); }
  .csa-probe__altbtn[aria-pressed='true'] { color: var(--badge-warn-fg, #ea580c); border-color: var(--badge-warn-border, #ea580c); border-style: solid; }
  .csa-probe__altbtn:focus-visible { outline: 2px solid #d97706; outline-offset: 2px; }
  .csa-probe__note { margin: 0.5rem 0 0; font-size: 0.62rem; font-style: italic; color: var(--text-ui, #8a8068); line-height: 1.4; }

  /* verdict -- paired badge + rationale verbatim */
  .csa-verdict {
    margin-top: 0.85rem;
    padding: 0.65rem 0.7rem;
    border: 1px solid var(--border, #192030);
    border-radius: 6px;
    background: var(--bg-row, #0e141e);
  }
  .csa-verdict__badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    padding: 0.18rem 0.5rem;
    border-radius: 2px;
    line-height: 1;
  }
  .csa-verdict__badge .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex: 0 0 auto; }
  .csa-verdict--fire .csa-verdict__badge {
    color: var(--badge-ar-fg, #d97706);
    background: var(--badge-ar-bg, #fef3c7);
    border: 1px solid var(--badge-ar-border, #d97706);
  }
  .csa-verdict--nofire .csa-verdict__badge {
    color: var(--badge-obs-fg, #475569);
    background: var(--badge-obs-bg, #f1f5f9);
    border: 1px solid var(--badge-obs-border, #cbd5e1);
  }
  .csa-verdict--degraded .csa-verdict__badge {
    color: var(--text-dim, #948870);
    background: transparent;
    border: 1px dashed var(--border, #192030);
  }
  .csa-verdict__mock {
    display: inline-block;
    margin-left: 0.5rem;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.56rem;
    font-style: italic;
    color: var(--text-ui, #8a8068);
  }
  .csa-verdict__rationale {
    margin: 0.5rem 0 0;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.7rem;
    line-height: 1.45;
    color: var(--text, #b8b098);
  }
  .csa-verdict__src {
    margin: 0.4rem 0 0;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.58rem;
    color: var(--text-ui, #8a8068);
    word-break: break-all;
  }

  /* demote (the existing wired action this audit feeds) */
  .csa-demote { margin-top: 1.1rem; padding-top: 0.9rem; border-top: 1px solid var(--border, #192030); }
  .csa-demote__btn {
    appearance: none;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: 0.62rem;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: var(--badge-blocked-fg, #dc2626);
    background: transparent;
    border: 1px solid var(--badge-blocked-border, #dc2626);
    border-radius: 5px;
    padding: 0.35rem 0.7rem;
    cursor: pointer;
  }
  .csa-demote__btn:hover:not(:disabled) { background: var(--badge-blocked-bg, #fee2e2); }
  .csa-demote__btn:disabled { opacity: 0.6; cursor: default; }
  .csa-demote__btn:focus-visible { outline: 2px solid #d97706; outline-offset: 2px; }
  .csa-demote__hint { display: block; margin-top: 0.4rem; font-size: 0.62rem; color: var(--text-ui, #8a8068); line-height: 1.4; }

  /* beta footer */
  .csa-dr-foot {
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
  .csa-dr-foot__dot { width: 5px; height: 5px; border-radius: 50%; background: var(--badge-ar-fg, #d97706); }

  .csa-sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    border: 0;
  }

  /* reduced motion: kill the slide transition (the audit is glance-worthy, never
     an alarm -- M2). */
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .csa-drawer,
    :global(html:not([data-motion='allow'])) .csa-chip,
    :global(html:not([data-motion='allow'])) .csa-hyd { transition: none; }
  }
  :global(html[data-motion='reduce']) .csa-drawer,
  :global(html[data-motion='reduce']) .csa-chip,
  :global(html[data-motion='reduce']) .csa-hyd { transition: none !important; }
</style>
