<!--
  RecordedSessionReplayForensics.svelte -- BETA feature
  "recorded-session-replay-forensics" (#23).

  WHAT IT IS
    A read-only right-side DRAWER that replays a recorded NON-SM session's
    decisions frame-by-frame, side by side: ORIGINAL (record-time verdict) |
    REPLAYED (current engine) | DELTA (field-level diff). A film-strip rail lets
    the operator scrub frames; n/p jump between divergent frames. The whole point
    is the delta_count headline: "X of N frames diverge from the current engine"
    -- root-cause analysis without parsing logs or re-running a soak.

  v1 SCOPE (CONSTRAINED ADDITIVE)
    v1 DIFFS STORED DECISIONS. The "original" + "replayed" columns are read from
    the additive /api/soak/replay endpoint over EXISTING recorded gov.db
    decisions (polarity-filtered, SM-self excluded server-side). The LIVE
    re-stream engine -- re-evaluating each recorded envelope through a fresh
    in-process governance engine -- is DEFERRED to a documented out-of-process
    "from CLI" affordance (the amber Build-gated footnote in the drawer). This
    component spawns NOTHING, re-evaluates NOTHING, mints NO bus envelope, and
    touches NO FROZEN surface.

  BETA GATE (load-bearing)
    The ENTIRE component is wrapped in
    {#if $betaFlags['recorded-session-replay-forensics']}. When the flag is OFF
    it renders NOTHING and registers NO fetch / poller / SSE / timer -- zero
    runtime cost. The flag defaults OFF (lib/beta/registry.js); the operator
    flips it in Settings > BETA features. There is no SSE here at all: the replay
    is read once per drawer-open (and once per picker change) via a single
    post-hoc GET (M18). It is a DRAWER, never a fourth frame, and NEVER
    auto-foregrounds (ADR-18 MUST).

  DATA
    Reads GET /api/soak/replay/sessions (the picker list) + GET
    /api/soak/replay/{recorded_session_uuid} (the triple set). Both polarity-
    filter (project_slug NOT IN {streamManager} AND session_id != self) server-
    side. When the endpoints are absent or return an empty set (fresh DB, no
    recorded decisions) the drawer falls back to realistic mock data
    (RecordedSessionReplayForensics.data.js) so it is always inspectable; the
    mock state is labelled in the source line (never silent).

  ADR-18 MUST floor honoured here:
    - M2/M3: never auto-foregrounds; the chip + drawer are operator-invoked only;
      a right-side drawer, never a fourth frame.
    - M4 (paired label+color): every frame severity renders its LITERAL text
      (MATCH / VERDICT MOVED / ESCALATED) beside any color; each diff cell writes
      the literal old->new text; color is never the sole signal.
    - M16 (domain-agnostic): no monitored-project vocabulary; frame kind +
      governance action + routing layer are governance taxonomy; project identity
      is rendered from server data.
    - M17 (a11y): chip is a real <button> with aria-haspopup; the drawer is
      role=dialog aria-modal with a labelled heading, Escape-to-close, focus
      moved in on open + restored on close, a focus trap, an aria-live scrubber
      announcer, and the 2px amber focus ring. Reduced motion honoured.
    - M18: pure post-hoc GET; never on the verdict hot path.

  ASCII-only (cp1252-safe): dash rendered as "--". No smart quotes / em-dash.
-->
<script>
  import { tick } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { getReplayForensics, getReplaySessions } from '../../api.js';
  import {
    frameSeverity,
    sevLabel,
    layerStr,
    hashStr,
    confStr,
    signed,
    deltaIndices,
    normalizeReplay,
    normalizeSessions,
    mockReplay,
    mockSessions,
  } from './RecordedSessionReplayForensics.data.js';

  const FLAG_KEY = 'recorded-session-replay-forensics';
  $: enabled = !!($betaFlags && $betaFlags[FLAG_KEY]);

  // ---- drawer open/close + focus contract (mirrors CoverageAnalyzer) --------
  let open = false;
  /** @type {HTMLDivElement|null} */
  let panelEl = null;
  /** @type {HTMLButtonElement|null} */
  let chipEl = null;
  /** @type {Element|null} */
  let prevFocus = null;

  // ---- data state -----------------------------------------------------------
  let loading = false;
  let usedMockData = false;
  /** @type {ReturnType<typeof mockReplay>|null} */
  let data = null;
  /** @type {ReturnType<typeof mockSessions>} */
  let sessions = [];
  /** the currently selected recorded-session key (drives the picker + fetch). */
  let selectedUuid = '';

  // ---- scrubber state -------------------------------------------------------
  let current = 0;
  let deltasOnly = false;

  /**
   * Load the picker list once (called on first drawer-open only -- no poller).
   * Best-effort: any failure / empty result degrades to the mock picker rows.
   */
  async function loadSessions() {
    let raw = null;
    try {
      raw = await getReplaySessions();
    } catch {
      raw = null;
    }
    const norm = normalizeSessions(raw);
    sessions = norm.length ? norm : mockSessions();
    if (!selectedUuid && sessions.length) selectedUuid = sessions[0].recorded_session_uuid;
  }

  /**
   * Load one recorded session's replay triple set. Best-effort: any failure /
   * empty result degrades to the realistic mock so the drawer is always
   * inspectable. Never throws to the render path. Resets the scrubber to frame 0.
   * @param {string} uuid
   */
  async function loadReplay(uuid) {
    loading = true;
    let raw = null;
    try {
      raw = await getReplayForensics(uuid);
    } catch {
      raw = null;
    }
    const norm = normalizeReplay(raw);
    if (norm) {
      data = norm;
      usedMockData = false;
    } else {
      data = mockReplay(uuid);
      usedMockData = true;
    }
    current = 0;
    loading = false;
  }

  // ---- derived view ---------------------------------------------------------
  $: frames = (data && Array.isArray(data.frames)) ? data.frames : [];
  $: frameCount = frames.length;
  $: deltaIdxs = deltaIndices(frames);
  $: visibleFrames = deltasOnly ? frames.filter((f) => f.delta && f.delta.changed) : frames;
  $: cur = frames[current] || null;
  $: curSev = cur ? frameSeverity(cur) : 'match';
  $: announceText = (() => {
    if (!cur) return '';
    let msg = `frame ${cur.idx + 1} of ${frameCount}, ${sevLabel(curSev)}`;
    if (cur.delta && cur.delta.changed && cur.delta.action_changed) {
      msg += ` -- action ${cur.original.action} to ${cur.replayed.action}`;
    } else if (!cur.delta || !cur.delta.changed) {
      msg += ' -- no field changed.';
    } else {
      msg += ' -- fields changed.';
    }
    return msg;
  })();

  // ---- interactions ---------------------------------------------------------
  function goTo(idx) {
    if (!frameCount) return;
    let n = Number(idx) || 0;
    if (n < 0) n = 0;
    if (n > frameCount - 1) n = frameCount - 1;
    current = n;
  }
  function nextDelta() {
    if (!deltaIdxs.length) return;
    for (const i of deltaIdxs) if (i > current) return goTo(i);
    goTo(deltaIdxs[0]); // wrap
  }
  function prevDelta() {
    if (!deltaIdxs.length) return;
    for (let k = deltaIdxs.length - 1; k >= 0; k--) {
      if (deltaIdxs[k] < current) return goTo(deltaIdxs[k]);
    }
    goTo(deltaIdxs[deltaIdxs.length - 1]); // wrap
  }
  function toggleDeltasOnly() {
    deltasOnly = !deltasOnly;
    if (deltasOnly && cur && (!cur.delta || !cur.delta.changed) && deltaIdxs.length) {
      goTo(deltaIdxs[0]);
    }
  }
  async function onPick(e) {
    const uuid = e && e.target ? e.target.value : selectedUuid;
    selectedUuid = uuid;
    deltasOnly = false;
    await loadReplay(uuid);
  }

  // ---- drawer lifecycle -----------------------------------------------------
  async function openDrawer() {
    if (!enabled) return;
    prevFocus = typeof document !== 'undefined' ? document.activeElement : null;
    open = true;
    if (sessions.length === 0) await loadSessions();
    if (data === null) await loadReplay(selectedUuid);
    await tick();
    panelEl?.focus();
  }
  function closeDrawer() {
    open = false;
    const target = prevFocus && /** @type {any} */ (prevFocus).focus ? prevFocus : chipEl;
    /** @type {HTMLElement|null} */ (target)?.focus?.();
    prevFocus = null;
  }

  function onKeydown(e) {
    if (!open) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      closeDrawer();
      return;
    }
    if (e.key === 'n') {
      e.preventDefault();
      nextDelta();
      return;
    }
    if (e.key === 'p') {
      e.preventDefault();
      prevDelta();
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      goTo(current + 1);
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      goTo(current - 1);
      return;
    }
    if (e.key === 'Tab' && panelEl) {
      const f = Array.from(
        panelEl.querySelectorAll(
          'button:not([disabled]), select:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((n) => /** @type {HTMLElement} */ (n).offsetParent !== null);
      if (!f.length) return;
      const first = /** @type {HTMLElement} */ (f[0]);
      const last = /** @type {HTMLElement} */ (f[f.length - 1]);
      const active = document.activeElement;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  // When the flag flips OFF while the drawer is open, close it so nothing
  // lingers (defense-in-depth -- the {#if} below already unmounts everything).
  $: if (!enabled && open) open = false;
</script>

<svelte:window on:keydown={onKeydown} />

{#if enabled}
  <!-- HEADER CHIP: the only resting affordance. A real button; opens the
       drawer. Present only while the flag is ON (the {#if enabled} guard). -->
  <button
    bind:this={chipEl}
    class="rf-chip"
    type="button"
    aria-haspopup="dialog"
    aria-expanded={open}
    aria-controls="rf-panel"
    on:click={openDrawer}
  >
    <span class="rf-chip__dot" aria-hidden="true"></span>
    Replay Forensics
    <span class="rf-chip__beta">BETA</span>
  </button>

  {#if open}
    <!-- SCRIM: click-out closes. Not a focus target. -->
    <div class="rf-scrim" on:click={closeDrawer} aria-hidden="true"></div>

    <!-- DRAWER: role=dialog aria-modal; labelled heading; Escape + focus trap. -->
    <div
      id="rf-panel"
      class="rf-panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="rf-title"
      tabindex="-1"
      bind:this={panelEl}
    >
      <header class="rf-head">
        <div class="rf-head__grow">
          <h2 id="rf-title" class="rf-title">Replay Forensics</h2>
          <p class="rf-sub">recorded session -- side-by-side decision deltas</p>
        </div>
        <button
          class="rf-close"
          type="button"
          aria-label="Close replay forensics"
          on:click={closeDrawer}
        >
          <span aria-hidden="true">x</span>
        </button>
      </header>

      <div class="rf-body">
        <!-- BETA strip -->
        <div class="rf-betastrip">
          <span class="rf-pill">BETA</span>
          <span class="rf-pill__note">
            default OFF -- toggled in Settings &gt; BETA features. Reads are a
            single post-hoc GET on open; no poller, no SSE, zero model quota.
          </span>
        </div>

        <!-- GATED-BUILD amber footnote: the LIVE re-stream engine is DEFERRED -->
        <div class="rf-gatenote">
          <span class="rf-gatenote__badge">Live replay deferred</span>
          <span>
            v1 <strong>diffs stored decisions</strong> read-only. The live
            re-stream engine -- re-evaluating each recorded envelope through a
            fresh in-process governance engine -- runs <strong>from the CLI</strong>
            (<code class="rf-code">soak_driver --replay</code>), not in this
            dashboard. No spawn, no model quota, no FROZEN-surface touch here.
          </span>
        </div>

        {#if loading && data === null}
          <p class="rf-loading">Loading replay...</p>
        {:else if data && cur}
          <!-- TOP STRIP: session metadata (tabular mono) -->
          <dl class="rf-meta">
            <dt>session</dt>
            <dd>{data.recorded_session_uuid}</dd>
            <dt>engine</dt>
            <dd>{data.engine_version || 'current'} (current at replay)</dd>
            <dt>recorded</dt>
            <dd>{data.recorded_at || '--'}</dd>
          </dl>

          <!-- data-source label: ALWAYS a literal text label (mock vs live) -->
          <p class="rf-source" data-mock={usedMockData}>
            {usedMockData
              ? 'SAMPLE DATA -- no recorded decisions in gov.db yet; rendering a deterministic representative triple set.'
              : 'LIVE -- diffed from recorded gov.db decisions (polarity-filtered).'}
          </p>

          <!-- HEADLINE: delta_count is THE point (paired text, never a bare num) -->
          <div class="rf-headline" data-has-delta={data.delta_count > 0}>
            <span class="rf-headline__dot" aria-hidden="true"></span>
            <span class="rf-headline__text">
              <span class="rf-headline__num">{data.delta_count}</span> of
              <span class="rf-headline__num">{data.frame_count}</span>
              frame{data.frame_count === 1 ? '' : 's'} diverge from the current engine
            </span>
          </div>

          <!-- SESSION PICKER -->
          <div class="rf-pickerrow">
            <label for="rf-select">Recorded session</label>
            <select
              id="rf-select"
              class="rf-select"
              bind:value={selectedUuid}
              on:change={onPick}
            >
              {#each sessions as s (s.recorded_session_uuid)}
                <option value={s.recorded_session_uuid}>{s.label}</option>
              {/each}
            </select>
            <span class="rf-picker__note">
              {data.excluded_self_rows} SM-self row{data.excluded_self_rows === 1 ? '' : 's'}
              excluded (polarity filter, G2)
            </span>
          </div>

          <!-- THE SPLIT: left film-strip rail + right triple grid -->
          <div class="rf-split">
            <!-- FRAME RAIL: one tick per frame; delta frames = filled notch -->
            <nav class="rf-rail" aria-label={`Frame scrubber, ${frameCount} frames`}>
              <span class="rf-rail__cap">frame</span>
              {#each visibleFrames as f (f.idx)}
                <button
                  class="rf-tick"
                  class:is-current={f.idx === current}
                  type="button"
                  data-sev={frameSeverity(f)}
                  aria-current={f.idx === current ? 'true' : 'false'}
                  aria-label={`Frame ${f.idx}, ${sevLabel(frameSeverity(f)).toLowerCase()}. Activate to inspect.`}
                  on:click={() => goTo(f.idx)}
                >
                  <span class="rf-tick__notch" aria-hidden="true"></span>
                  <span class="rf-tick__idx">{f.idx}</span>
                </button>
              {/each}
            </nav>

            <!-- RIGHT COLUMN -->
            <div class="rf-rightcol">
              <!-- scrubber controls -->
              <div class="rf-scrubctl">
                <button class="rf-btn" type="button" on:click={prevDelta}>
                  prev delta <span class="rf-btn__kbd">p</span>
                </button>
                <button class="rf-btn" type="button" on:click={nextDelta}>
                  next delta <span class="rf-btn__kbd">n</span>
                </button>
                <button
                  class="rf-btn"
                  class:is-active={deltasOnly}
                  type="button"
                  aria-pressed={deltasOnly}
                  on:click={toggleDeltasOnly}
                >
                  deltas only
                </button>
                <span class="rf-scrubctl__pos tabular">
                  frame {current + 1} of {frameCount}
                </span>
              </div>

              <!-- selected frame head -->
              <div class="rf-framehead">
                <span class="rf-kindtag">{cur.kind}</span>
                <span class="rf-fingerprint">{cur.content_fingerprint || '(no fingerprint)'}</span>
                <span class="rf-statusbadge" data-sev={curSev}>
                  <span class="rf-statusbadge__dot" aria-hidden="true"></span>
                  <span>{sevLabel(curSev)}</span>
                </span>
              </div>

              <!-- THE TRIPLE GRID -->
              <div class="rf-grid">
                <!-- ORIGINAL -->
                <section class="rf-col" aria-label="Original decision, captured at record time">
                  <div class="rf-col__head">
                    <h3 class="rf-col__title">Original</h3>
                    <span class="rf-col__cap">record-time</span>
                  </div>
                  <div class="rf-field">
                    <div class="rf-field__k">action</div>
                    <div class="rf-field__v mono">{cur.original.action}</div>
                  </div>
                  <div class="rf-field">
                    <div class="rf-field__k">confidence</div>
                    <div class="rf-field__v mono">{confStr(cur.original.confidence)}</div>
                  </div>
                  <div class="rf-field">
                    <div class="rf-field__k">layer</div>
                    <div class="rf-field__v mono">{layerStr(cur.original.layer)}</div>
                  </div>
                  <div class="rf-field">
                    <div class="rf-field__k">matched_hash</div>
                    <div class="rf-field__v mono">{hashStr(cur.original.matched_hash)}</div>
                  </div>
                  <div class="rf-field">
                    <div class="rf-field__k">reasoning</div>
                    <div class="rf-field__v">{cur.original.reasoning || '--'}</div>
                  </div>
                </section>

                <!-- REPLAYED -->
                <section class="rf-col" aria-label="Replayed decision, current engine">
                  <div class="rf-col__head">
                    <h3 class="rf-col__title">Replayed</h3>
                    <span class="rf-col__cap">current engine</span>
                  </div>
                  <div class="rf-field">
                    <div class="rf-field__k">action</div>
                    <div class="rf-field__v mono">{cur.replayed.action}</div>
                  </div>
                  <div class="rf-field">
                    <div class="rf-field__k">confidence</div>
                    <div class="rf-field__v mono">{confStr(cur.replayed.confidence)}</div>
                  </div>
                  <div class="rf-field">
                    <div class="rf-field__k">layer</div>
                    <div class="rf-field__v mono">{layerStr(cur.replayed.layer)}</div>
                  </div>
                  <div class="rf-field">
                    <div class="rf-field__k">matched_hash</div>
                    <div class="rf-field__v mono">{hashStr(cur.replayed.matched_hash)}</div>
                  </div>
                  <div class="rf-field">
                    <div class="rf-field__k">reasoning</div>
                    <div class="rf-field__v">{cur.replayed.reasoning || '--'}</div>
                  </div>
                </section>

                <!-- DELTA -- literal old->new text, never color alone (M4) -->
                <section class="rf-col rf-col--delta" aria-label="Field-level delta, original versus replayed">
                  <div class="rf-col__head">
                    <h3 class="rf-col__title">Delta</h3>
                    <span class="rf-col__cap">field-level diff</span>
                  </div>

                  <!-- action -->
                  <div
                    class="rf-field"
                    class:is-same={!cur.delta.action_changed}
                    class:is-changed={cur.delta.action_changed && curSev === 'moved'}
                    class:is-escalated={cur.delta.action_changed && curSev === 'escalated'}
                  >
                    <div class="rf-field__k">action</div>
                    <div class="rf-field__v">
                      {#if cur.delta.action_changed}
                        <span class="rf-from">{cur.original.action}</span>
                        <span class="rf-arrow"> -&gt; </span>
                        <span class={curSev === 'escalated' ? 'rf-to-escalated' : 'rf-to-moved'}
                          >{cur.replayed.action}</span
                        >
                      {:else}
                        <span class="rf-same">(same)</span>
                      {/if}
                    </div>
                  </div>

                  <!-- confidence -->
                  <div
                    class="rf-field"
                    class:is-same={!(Math.abs(cur.delta.confidence_delta) > 0)}
                    class:is-changed={Math.abs(cur.delta.confidence_delta) > 0 && curSev === 'moved'}
                    class:is-escalated={Math.abs(cur.delta.confidence_delta) > 0 && curSev === 'escalated'}
                  >
                    <div class="rf-field__k">confidence</div>
                    <div class="rf-field__v">
                      {#if Math.abs(cur.delta.confidence_delta) > 0}
                        <span class="rf-from">{confStr(cur.original.confidence)}</span>
                        <span class="rf-arrow"> -&gt; </span>
                        <span class={curSev === 'escalated' ? 'rf-to-escalated' : 'rf-to-moved'}
                          >{confStr(cur.replayed.confidence)}</span
                        >
                        <span class="rf-mag" class:neg={cur.delta.confidence_delta < 0}>
                          ({signed(cur.delta.confidence_delta)})
                        </span>
                      {:else}
                        <span class="rf-same">(same)</span>
                      {/if}
                    </div>
                  </div>

                  <!-- layer -->
                  <div
                    class="rf-field"
                    class:is-same={cur.delta.layer_delta === 0}
                    class:is-changed={cur.delta.layer_delta !== 0 && curSev === 'moved'}
                    class:is-escalated={cur.delta.layer_delta !== 0 && curSev === 'escalated'}
                  >
                    <div class="rf-field__k">layer</div>
                    <div class="rf-field__v">
                      {#if cur.delta.layer_delta !== 0}
                        <span class="rf-from">{layerStr(cur.original.layer)}</span>
                        <span class="rf-arrow"> -&gt; </span>
                        <span class={curSev === 'escalated' ? 'rf-to-escalated' : 'rf-to-moved'}
                          >{layerStr(cur.replayed.layer)}</span
                        >
                        <span class="rf-mag">({cur.delta.layer_delta > 0 ? '+' : ''}{cur.delta.layer_delta})</span>
                      {:else}
                        <span class="rf-same">(same)</span>
                      {/if}
                    </div>
                  </div>

                  <!-- matched_hash -->
                  <div
                    class="rf-field"
                    class:is-same={!cur.delta.matched_hash_changed}
                    class:is-changed={cur.delta.matched_hash_changed && curSev === 'moved'}
                    class:is-escalated={cur.delta.matched_hash_changed && curSev === 'escalated'}
                  >
                    <div class="rf-field__k">matched_hash</div>
                    <div class="rf-field__v">
                      {#if cur.delta.matched_hash_changed}
                        <span class="rf-from">{hashStr(cur.original.matched_hash)}</span>
                        <span class="rf-arrow"> -&gt; </span>
                        <span class={curSev === 'escalated' ? 'rf-to-escalated' : 'rf-to-moved'}
                          >{hashStr(cur.replayed.matched_hash)}</span
                        >
                      {:else}
                        <span class="rf-same">(same)</span>
                      {/if}
                    </div>
                  </div>

                  <!-- summary -->
                  <div class="rf-field">
                    <div class="rf-field__k">summary</div>
                    <div class="rf-field__v">
                      {#if cur.delta.changed && cur.delta.summary}
                        <code class="rf-deltasummary">{cur.delta.summary}</code>
                      {:else}
                        <span class="rf-deltamatch">No field moved -- replay reproduces the record-time verdict.</span>
                      {/if}
                    </div>
                  </div>
                </section>
              </div>

              <!-- the polite aria-live announcer -->
              <div class="rf-announce" role="status" aria-live="polite">
                {announceText}
              </div>
            </div>
          </div>
        {:else}
          <p class="rf-loading">No replay data available.</p>
        {/if}
      </div>

      <footer class="rf-foot">
        <span class="rf-pill rf-pill--sm">BETA</span>
        <span>
          Read-only, offline, zero model quota. Default OFF, toggled in Settings
          &gt; BETA features. Never auto-foregrounds; never a fourth frame.
        </span>
      </footer>
    </div>
  {/if}
{/if}

<style>
  /* ---- header chip --------------------------------------------------------- */
  .rf-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    font: inherit;
    font-size: 0.72rem;
    letter-spacing: 0.03em;
    padding: 0.3rem 0.65rem;
    background: var(--calm-accent-wash, var(--accent-dim));
    color: var(--calm-ink-loud, var(--text-bright));
    border: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi));
    border-radius: 999px;
    cursor: pointer;
  }
  .rf-chip:hover {
    border-color: var(--calm-accent, var(--accent));
  }
  .rf-chip__dot {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 50%;
    background: var(--calm-accent, var(--accent));
    flex: 0 0 auto;
  }
  .rf-chip__beta {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.56rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: #92400e;
    background: var(--badge-ar-bg);
    border: 1px solid var(--badge-ar-border);
    border-radius: 4px;
    padding: 0 0.3rem;
  }

  /* ---- scrim + drawer ------------------------------------------------------ */
  .rf-scrim {
    position: fixed;
    inset: 0;
    z-index: 80;
    background: rgba(8, 10, 12, 0.55);
    backdrop-filter: blur(1px);
  }
  .rf-panel {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    z-index: 81;
    width: min(640px, 96vw);
    display: flex;
    flex-direction: column;
    background: var(--calm-surface-raised, var(--bg-card));
    border-left: var(--hairline, 1px) solid var(--calm-hairline-hi, var(--border-hi));
    box-shadow: -18px 0 48px -24px rgba(0, 0, 0, 0.7);
    color: var(--calm-ink, var(--text));
    font-family: var(--ff-system);
    overflow: hidden;
  }

  .rf-head {
    flex: 0 0 auto;
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    padding: 1rem 1.15rem 0.85rem;
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
  }
  .rf-head__grow {
    flex: 1 1 auto;
    min-width: 0;
  }
  .rf-title {
    margin: 0;
    font-size: 1.02rem;
    letter-spacing: 0.01em;
    color: var(--calm-ink-loud, var(--text-bright));
    font-weight: 700;
    line-height: 1.25;
  }
  .rf-sub {
    margin: 0.2rem 0 0;
    font-size: 0.76rem;
    color: var(--calm-ink-quiet, var(--text-dim));
    font-family: var(--font-d, var(--ff-mono));
  }
  .rf-close {
    flex: 0 0 auto;
    font: inherit;
    line-height: 1;
    font-size: 1rem;
    background: transparent;
    color: var(--calm-ink-quiet, var(--text-dim));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: 8px;
    width: 2rem;
    height: 2rem;
    cursor: pointer;
  }
  .rf-close:hover {
    color: var(--calm-ink-loud, var(--text-bright));
  }

  .rf-body {
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
    padding: 1rem 1.15rem 1.4rem;
    overscroll-behavior: contain;
  }

  /* ---- BETA strip ---------------------------------------------------------- */
  .rf-betastrip {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    flex-wrap: wrap;
    padding: 0.55rem 0.7rem;
    margin-bottom: 1rem;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: 8px;
    background: var(--bg-row-alt);
  }
  .rf-pill {
    display: inline-flex;
    align-items: center;
    font-size: 0.66rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    font-weight: 700;
    padding: 0.22rem 0.55rem;
    border-radius: 6px;
    color: var(--badge-ar-fg);
    background: var(--badge-ar-bg);
    border: 2px solid var(--badge-ar-border);
  }
  .rf-pill--sm {
    font-size: 0.6rem;
    padding: 0.16rem 0.45rem;
    border-width: 1px;
  }
  .rf-pill__note {
    flex: 1 1 auto;
    font-size: 0.72rem;
    color: var(--calm-ink-quiet, var(--text-dim));
  }

  /* ---- live-replay-deferred amber footnote --------------------------------- */
  .rf-gatenote {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
    padding: 0.55rem 0.7rem;
    margin-bottom: 1rem;
    border: var(--hairline, 1px) solid var(--sm-warn-border, var(--badge-warn-border));
    border-left-width: 3px;
    border-radius: 8px;
    background: rgba(234, 88, 12, 0.08);
    font-size: 0.74rem;
    line-height: 1.45;
    color: var(--calm-ink, var(--text));
  }
  .rf-gatenote__badge {
    flex: 0 0 auto;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    padding: 0.16rem 0.45rem;
    border-radius: 5px;
    color: var(--sm-warn-fg, var(--badge-warn-fg));
    background: var(--badge-warn-bg);
    border: 1px solid var(--sm-warn-border, var(--badge-warn-border));
    margin-top: 0.05rem;
  }
  .rf-gatenote strong {
    color: var(--calm-ink-loud, var(--text-bright));
  }
  .rf-code {
    font-family: var(--font-d, var(--ff-mono));
    color: var(--calm-ink-loud, var(--text-bright));
  }

  /* ---- meta + source ------------------------------------------------------- */
  .rf-meta {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 0.3rem 0.9rem;
    margin-bottom: 0.7rem;
    font-size: 0.74rem;
  }
  .rf-meta dt {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.62rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui));
    align-self: center;
  }
  .rf-meta dd {
    margin: 0;
    font-family: var(--font-d, var(--ff-mono));
    font-variant-numeric: tabular-nums;
    color: var(--calm-ink, var(--text));
    overflow-wrap: anywhere;
  }

  .rf-source {
    margin: 0 0 0.7rem;
    font-size: 0.7rem;
    font-family: var(--font-d, var(--ff-mono));
    letter-spacing: 0.02em;
    color: var(--calm-ink-quiet, var(--text-dim));
  }
  .rf-source[data-mock='true'] {
    color: var(--sm-warn-fg, var(--badge-warn-fg));
  }

  .rf-loading {
    padding: 1.2rem 0.4rem;
    text-align: center;
    color: var(--calm-ink-quiet, var(--text-dim));
    font-size: 0.82rem;
    font-style: italic;
  }

  /* ---- headline ------------------------------------------------------------ */
  .rf-headline {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    flex-wrap: wrap;
    padding: 0.7rem 0.8rem;
    margin-bottom: 1rem;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: 8px;
    background: var(--bg-card);
  }
  .rf-headline[data-has-delta='true'] {
    border-color: var(--sm-warn-fg, var(--badge-warn-fg));
  }
  .rf-headline__dot {
    width: 0.65rem;
    height: 0.65rem;
    border-radius: 50%;
    flex: 0 0 auto;
    background: var(--calm-ink-quiet, var(--text-dim));
  }
  .rf-headline[data-has-delta='true'] .rf-headline__dot {
    background: var(--sm-warn-fg, var(--badge-warn-fg));
  }
  .rf-headline__text {
    font-size: 0.92rem;
    font-weight: 700;
    color: var(--calm-ink-loud, var(--text-bright));
    letter-spacing: 0.01em;
  }
  .rf-headline__num {
    font-family: var(--font-d, var(--ff-mono));
    color: var(--calm-ink-quiet, var(--text-dim));
  }
  .rf-headline[data-has-delta='true'] .rf-headline__num {
    color: var(--sm-warn-fg, var(--badge-warn-fg));
  }

  /* ---- session picker ------------------------------------------------------ */
  .rf-pickerrow {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    flex-wrap: wrap;
    margin-bottom: 1rem;
  }
  .rf-pickerrow label {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.62rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui));
  }
  .rf-select {
    font: inherit;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.74rem;
    padding: 0.32rem 0.5rem;
    background: var(--bg-row);
    color: var(--calm-ink-loud, var(--text-bright));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: 7px;
    cursor: pointer;
  }
  .rf-select:hover {
    border-color: var(--calm-hairline-hi, var(--border-hi));
  }
  .rf-picker__note {
    margin-left: auto;
    font-size: 0.68rem;
    color: var(--calm-ink-quiet, var(--text-dim));
  }

  /* ---- the split: rail + right column -------------------------------------- */
  .rf-split {
    display: grid;
    grid-template-columns: 3.1rem 1fr;
    gap: 0.9rem;
    align-items: start;
  }

  .rf-rail {
    position: relative;
    border-left: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    padding: 0.1rem 0 0.1rem 0.55rem;
    display: flex;
    flex-direction: column;
    gap: 0.32rem;
  }
  .rf-rail__cap {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.54rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui));
    margin-bottom: 0.15rem;
  }
  .rf-tick {
    position: relative;
    display: flex;
    align-items: center;
    gap: 0.35rem;
    width: 100%;
    font: inherit;
    text-align: left;
    background: transparent;
    border: var(--hairline, 1px) solid transparent;
    border-radius: 6px;
    padding: 0.2rem 0.25rem;
    cursor: pointer;
    color: var(--calm-ink-quiet, var(--text-dim));
  }
  .rf-tick:hover {
    background: var(--bg-row-hover);
  }
  .rf-tick.is-current {
    background: var(--bg-row-hover);
    border-color: var(--calm-hairline-hi, var(--border-hi));
  }
  .rf-tick__notch {
    width: 0.55rem;
    height: 0.55rem;
    border-radius: 2px;
    flex: 0 0 auto;
    background: transparent;
    border: 1px solid var(--calm-ink-chrome, var(--text-ui)); /* hairline = MATCH */
  }
  .rf-tick[data-sev='moved'] .rf-tick__notch {
    background: var(--sm-warn-fg, var(--badge-warn-fg));
    border-color: var(--sm-warn-fg, var(--badge-warn-fg));
  }
  .rf-tick[data-sev='escalated'] .rf-tick__notch {
    background: var(--badge-blocked-fg);
    border-color: var(--badge-blocked-fg);
  }
  .rf-tick__idx {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.64rem;
    font-variant-numeric: tabular-nums;
  }
  .rf-tick.is-current .rf-tick__idx {
    color: var(--calm-ink-loud, var(--text-bright));
  }

  /* ---- right column -------------------------------------------------------- */
  .rf-rightcol {
    min-width: 0;
  }
  .rf-scrubctl {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
    margin-bottom: 0.7rem;
  }
  .rf-btn {
    font: inherit;
    font-size: 0.72rem;
    padding: 0.34rem 0.6rem;
    background: var(--bg-row-alt);
    color: var(--calm-ink-loud, var(--text-bright));
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: 7px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
  }
  .rf-btn:hover {
    border-color: var(--calm-hairline-hi, var(--border-hi));
  }
  .rf-btn.is-active {
    color: var(--calm-accent, var(--accent));
    border-color: var(--calm-hairline-hi, var(--border-hi));
    background: var(--calm-accent-wash, var(--accent-dim));
  }
  .rf-btn__kbd {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.6rem;
    color: var(--calm-ink-quiet, var(--text-dim));
    border: 1px solid var(--calm-hairline, var(--border));
    border-radius: 3px;
    padding: 0 0.22rem;
  }
  .rf-scrubctl__pos {
    margin-left: auto;
    font-size: 0.68rem;
    color: var(--calm-ink-quiet, var(--text-dim));
  }
  .tabular {
    font-variant-numeric: tabular-nums;
    font-family: var(--font-d, var(--ff-mono));
  }

  /* ---- frame head ---------------------------------------------------------- */
  .rf-framehead {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    flex-wrap: wrap;
    padding: 0.5rem 0.6rem;
    margin-bottom: 0.7rem;
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: 7px;
    background: var(--bg-row-alt);
  }
  .rf-kindtag {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.6rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    font-weight: 700;
    color: var(--calm-ink-chrome, var(--text-ui));
    border: 1px solid var(--calm-hairline, var(--border));
    border-radius: 4px;
    padding: 0.06rem 0.34rem;
  }
  .rf-fingerprint {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.74rem;
    color: var(--calm-ink, var(--text));
    overflow-wrap: anywhere;
    min-width: 0;
  }
  .rf-statusbadge {
    margin-left: auto;
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    padding: 0.12rem 0.45rem;
    border-radius: 5px;
  }
  .rf-statusbadge__dot {
    width: 0.42rem;
    height: 0.42rem;
    border-radius: 50%;
    background: currentColor;
    flex: 0 0 auto;
  }
  .rf-statusbadge[data-sev='match'] {
    color: var(--calm-ink-quiet, var(--text-dim));
    background: var(--bg-row-alt);
    border: 1px solid var(--calm-hairline, var(--border));
  }
  .rf-statusbadge[data-sev='moved'] {
    color: var(--sm-warn-fg, var(--badge-warn-fg));
    background: rgba(234, 88, 12, 0.1);
    border: 1px solid var(--sm-warn-border, var(--badge-warn-border));
  }
  .rf-statusbadge[data-sev='escalated'] {
    color: var(--badge-blocked-fg);
    background: rgba(220, 38, 38, 0.1);
    border: 1px solid var(--badge-blocked-border);
  }

  /* ---- the triple grid ----------------------------------------------------- */
  .rf-grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 0.6rem;
  }
  .rf-col {
    border: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    border-radius: 8px;
    background: var(--bg-card);
    overflow: hidden;
  }
  .rf-col__head {
    padding: 0.4rem 0.55rem;
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    background: var(--bg-row-alt);
  }
  .rf-col__title {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--calm-ink-loud, var(--text-bright));
    margin: 0;
  }
  .rf-col__cap {
    display: block;
    font-size: 0.62rem;
    color: var(--calm-ink-quiet, var(--text-dim));
    font-family: var(--font-d, var(--ff-mono));
    margin-top: 0.12rem;
  }
  .rf-col--delta .rf-col__title {
    color: var(--calm-accent, var(--accent));
  }

  .rf-field {
    padding: 0.42rem 0.55rem;
    border-bottom: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
  }
  .rf-field:last-child {
    border-bottom: none;
  }
  .rf-field__k {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.56rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--calm-ink-chrome, var(--text-ui));
    margin-bottom: 0.18rem;
  }
  .rf-field__v {
    font-size: 0.76rem;
    color: var(--calm-ink, var(--text));
    font-variant-numeric: tabular-nums;
    overflow-wrap: anywhere;
    line-height: 1.35;
  }
  .rf-field__v.mono {
    font-family: var(--font-d, var(--ff-mono));
  }

  .rf-field.is-changed {
    border-left: 2px solid var(--sm-warn-fg, var(--badge-warn-fg));
    background: rgba(234, 88, 12, 0.05);
  }
  .rf-field.is-escalated {
    border-left: 2px solid var(--badge-blocked-fg);
    background: rgba(220, 38, 38, 0.05);
  }
  .rf-field.is-same .rf-field__v {
    color: var(--calm-ink-quiet, var(--text-dim));
  }
  .rf-same {
    font-style: italic;
    color: var(--calm-ink-quiet, var(--text-dim));
    font-size: 0.7rem;
  }
  .rf-arrow {
    color: var(--calm-ink-loud, var(--text-bright));
    font-weight: 700;
    font-family: var(--font-d, var(--ff-mono));
    padding: 0 0.15rem;
  }
  .rf-from {
    color: var(--calm-ink-quiet, var(--text-dim));
  }
  .rf-to-moved {
    color: var(--sm-warn-fg, var(--badge-warn-fg));
    font-weight: 700;
  }
  .rf-to-escalated {
    color: var(--badge-blocked-fg);
    font-weight: 700;
  }
  .rf-mag {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.68rem;
    color: var(--calm-ink-quiet, var(--text-dim));
  }
  .rf-mag.neg {
    color: var(--sm-warn-fg, var(--badge-warn-fg));
  }
  .rf-deltasummary {
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.72rem;
    color: var(--calm-ink-loud, var(--text-bright));
    line-height: 1.4;
    overflow-wrap: anywhere;
  }
  .rf-deltamatch {
    font-size: 0.74rem;
    color: var(--calm-ink-quiet, var(--text-dim));
    font-style: italic;
  }

  /* ---- announcer ----------------------------------------------------------- */
  .rf-announce {
    margin-top: 0.85rem;
    padding: 0.45rem 0.6rem;
    border: var(--hairline, 1px) dashed var(--calm-hairline, var(--border));
    border-radius: 7px;
    background: var(--bg-row-alt);
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.68rem;
    color: var(--calm-ink-quiet, var(--text-dim));
  }

  /* ---- footer -------------------------------------------------------------- */
  .rf-foot {
    flex: 0 0 auto;
    padding: 0.55rem 1.15rem;
    border-top: var(--hairline, 1px) solid var(--calm-hairline, var(--border));
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
    font-size: 0.68rem;
    color: var(--calm-ink-quiet, var(--text-dim));
    background: var(--bg-row-alt);
  }

  /* ---- focus ring (M17): the global 2px amber ring on every interactive el -- */
  .rf-chip:focus-visible,
  .rf-close:focus-visible,
  .rf-tick:focus-visible,
  .rf-btn:focus-visible,
  .rf-select:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid)
      var(--focus-ring-color, var(--sm-focus, #d97706));
    outline-offset: 2px;
  }

  /* ---- reduced motion (M17) ------------------------------------------------ */
  :global(html[data-motion='reduce']) .rf-tick {
    transition: none;
  }

  /* ---- narrow viewport: the triple grid stacks ----------------------------- */
  @media (max-width: 560px) {
    .rf-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
