<!--
  SonificationEscalationLayer.svelte -- BETA feature #44 "sonification-escalation
  -layer": a DERIVED audio confirmation layer on a real escalation. Web Audio,
  default-OFF, client-side only. Sound is CONFIRMATION, never SIGNAL (ADR-18 M5):
  it is always paired with the existing VISUAL escalation badge and never a lone
  channel -- a deaf or muted operator loses nothing.

  GATING (load-bearing): the entire component is wrapped in
  {#if $betaFlags['sonification-escalation-layer']}. When the flag is OFF (the
  default) it renders NOTHING and registers NO subscriber / listener / timer /
  AudioContext -- the {#if} short-circuits the markup AND the onMount wiring, so
  there is ZERO runtime cost (the controller never touches AudioContext). Flip it
  ON in Settings > BETA features (group "Monitor & glance-readability").

  HOW SOUND STAYS DERIVED-OF-A-BADGE (M5, structural):
    - It subscribes to the EXISTING escalationStore (sse.js), which is produced
      SOLELY from the FROZEN lib/escalation.js allow-list. It classifies NOTHING
      -- single source of truth preserved (M2). It only looks a tone up by the
      type the store already decided.
    - A tone loops ONLY while the paired escalation is inside the SAME 20s
      ESC_WINDOW_MS that the Frame-A foreground already uses. The instant the
      window drains (the badge clears) the loop stops -- silence == handled.
    - The existing FR-UI-9 "Audible cue" setting ($settings.audibleCue, dormant
      until now) is the MASTER gate: OFF => no tone, ever. Per-type enable +
      volume + a one-keystroke "Master mute" hush layer on top (client-side only).

  WHAT IT MOUNTS (self-contained, App-root sibling -- edits no shared file):
    1. The INVISIBLE controller: the escalationStore subscriber + the Web Audio
       renderer. Renders no governance DOM.
    2. A quiet launcher button (bottom-left) that opens the settings sub-panel
       (the only visible surface, mirroring the approved mockup): a master ON/OFF
       + hush row, FOREGROUND (3) + BADGE-IN-PLACE (3) per-type rows with a
       Preview / Enable / Volume control each, and a small live strip proving the
       sound is coupled to badge visibility (a "Simulate burst" of MOCK data so
       the panel is always testable -- usedMockData=true).

  ADR-18 MUST floor honoured:
    - M2: defers to lib/escalation.js; invents no escalation; never foregrounds.
    - M4 paired label+color: every state renders literal TEXT first (ON/OFF,
      MUTED, AUDIBLE, the type label); the painted dot/chip only REINFORCES it.
    - Absolute HITL gate: sound is advisory-of-a-badge; it auto-resolves nothing.
    - M16 domain-agnostic: identity is rendered FROM DATA / generic mock ids.
    - M17 a11y AAA: real <button>/<input>; 2px amber focus ring; Escape closes
      the panel with focus restored; aria-labels everywhere; reduced-motion aware;
      a polite live region; sound is a SUPPLEMENT, the badge is sufficient.
    - M18: pure presentation. No GET/POST, no bus, no verdict hot path.

  ASCII-only (cp1252-safe): dash is "--"; no smart quotes / em-dashes / box chars.
-->
<script>
  import { onMount, onDestroy, tick } from 'svelte';
  import { betaFlags } from '../../stores/beta.js';
  import { settings } from '../../stores/settings.js';
  import { escalationStore } from '../../sse.js';
  import {
    GRAMMAR,
    TYPES,
    MOCK_FEED,
    metaForType,
    typeOfEscalation,
    loadPrefs,
    persistPrefs,
    pct,
  } from './SonificationEscalationLayer-grammar.js';

  const FLAG_KEY = 'sonification-escalation-layer';

  // The SAME bounded window the Frame-A foreground uses (App.svelte ESC_WINDOW_MS
  // = 20000). Sound is coupled to it: a tone loops only while the escalation is
  // still inside the window; on expiry the badge clears AND the tone stops.
  const ESC_WINDOW_MS = 20000;

  // -- per-type prefs (client-side only; localStorage mirror, never the bus) ---
  let prefs = loadPrefs(); // { master_muted, types: { [type]: {enabled, volume} } }

  // group the rows by tier for the settings sub-panel (the escalation.js M2
  // partition: 3 foreground, 3 badge-in-place).
  const foregroundTypes = TYPES.filter((t) => t.tier === 'foreground');
  const badgeTypes = TYPES.filter((t) => t.tier === 'badge');

  // -- master gate: the existing FR-UI-9 "Audible cue" setting is the master ON.
  // Feature flag -> audibleCue -> master_muted -> per-type enabled is the gate
  // order; ALL must pass for a tone to play.
  $: audibleOn = !!$settings.audibleCue;
  $: featureOn = !!($betaFlags && $betaFlags[FLAG_KEY]);
  $: masterActive = featureOn && audibleOn && !prefs.master_muted;

  // -- Web Audio (lazily created on first user gesture; browser autoplay policy)
  /** @type {AudioContext|null} */
  let actx = null;
  function audioCtx() {
    if (typeof window === 'undefined') return null;
    if (!actx) {
      const Ctor = window.AudioContext || /** @type {any} */ (window).webkitAudioContext;
      if (!Ctor) return null;
      try { actx = new Ctor(); } catch { actx = null; }
    }
    if (actx && actx.state === 'suspended') { try { actx.resume(); } catch { /* noop */ } }
    return actx;
  }

  /**
   * Render ONE pass of a type's grammar (a short sequence of oscillator notes).
   * Gate order mirrors masterActive + per-type enable. Returns true iff a tone
   * was actually emitted (false when suppressed -- never throws).
   * @param {string} type
   * @returns {boolean}
   */
  function play(type) {
    if (!masterActive) return false;
    const pref = prefs.types[type];
    if (!pref || !pref.enabled) return false;
    const g = GRAMMAR[type];
    if (!g) return false;
    const ctx = audioCtx();
    if (!ctx) return false;

    const t0 = ctx.currentTime;
    const step = g.durationMs / 1000;
    const vol = Math.max(0, Math.min(1, pref.volume)) * 0.18; // headroom-limited
    for (let i = 0; i < g.freqs.length; i += 1) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = g.waveform;
      osc.frequency.value = g.freqs[i];
      const start = t0 + i * step;
      const end = start + step;
      // tiny attack/release so square/sawtooth don't click.
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(Math.max(0.0002, vol), start + Math.min(0.02, step * 0.3));
      gain.gain.exponentialRampToValueAtTime(0.0001, end);
      osc.connect(gain).connect(ctx.destination);
      osc.start(start);
      osc.stop(end + 0.02);
    }
    return true;
  }

  // ==========================================================================
  // THE INVISIBLE CONTROLLER: subscribe to the live escalationStore. For each
  // NEW escalation entry inside the window, start a loop at the grammar interval;
  // stop the loop the instant the window drains (badge cleared). This is the
  // real, live behaviour -- the demo strip below is a visible stand-in for it.
  // ==========================================================================

  /** @type {Map<string, { stop:()=>void }>} active live loops, keyed per escalation. */
  const liveLoops = new Map();
  let lastSeenIndex = 0; // high-water mark into the append-only escalationStore
  let liveCount = 0; // how many live tones are currently looping (for the panel readout)
  /** @type {(()=>void)|null} */
  let unsubEsc = null;

  function escKey(entry, idx) {
    const sid = entry && entry.sessionId != null ? entry.sessionId : 'na';
    return `${idx}:${sid}:${entry && entry.ts}`;
  }

  function startLiveLoop(type, key, ts) {
    const g = GRAMMAR[type];
    if (!g) return;
    // play immediately, then loop at the grammar interval until the window drains.
    play(type);
    liveCount += 1;
    const repeat = setInterval(() => {
      // window expiry => clear: silence == handled (M5 coupling).
      if (Date.now() - ts >= ESC_WINDOW_MS) { stop(); return; }
      play(type); // play() itself re-checks masterActive + per-type enable
    }, Math.max(1000, g.repeatMs));
    function stop() {
      clearInterval(repeat);
      if (liveLoops.has(key)) { liveLoops.delete(key); liveCount = Math.max(0, liveCount - 1); }
    }
    // a hard stop after the window even if intervals are throttled (bg tab).
    const guard = setTimeout(stop, ESC_WINDOW_MS + 200);
    liveLoops.set(key, { stop: () => { clearTimeout(guard); stop(); } });
  }

  function ingestEscalations(list) {
    if (!Array.isArray(list)) return;
    // process only entries appended since we last looked (append-only store).
    for (let i = lastSeenIndex; i < list.length; i += 1) {
      const entry = list[i];
      const ts = entry && typeof entry.ts === 'number' ? entry.ts : Date.now();
      if (Date.now() - ts >= ESC_WINDOW_MS) continue; // already-stale on first paint
      const type = typeOfEscalation(entry);
      if (!type || !GRAMMAR[type]) continue;
      startLiveLoop(type, escKey(entry, i), ts);
    }
    lastSeenIndex = list.length;
  }

  function stopAllLive() {
    for (const loop of liveLoops.values()) { try { loop.stop(); } catch { /* noop */ } }
    liveLoops.clear();
    liveCount = 0;
  }

  // ==========================================================================
  // SETTINGS SUB-PANEL (the only visible surface) + the MOCK live strip.
  // ==========================================================================
  let panelOpen = false;
  let liveMsg = ''; // aria-live announcements (preview / hush / burst)
  /** @type {HTMLElement|null} */ let launcherBtn = null;
  /** @type {HTMLElement|null} */ let firstPanelFocus = null;

  // the visible mock strip (a stand-in for Frame A's badge + the window). MOCK
  // data so the panel is always demonstrable when no live escalation is in scope.
  /** @type {Array<{ id:string, type:string, sessionId:string, audible:boolean, fillPct:number }>} */
  let demoRows = [];
  let demoHint = 'idle';
  /** @type {ReturnType<typeof setInterval>|null} */ let burstTimer = null;
  /** @type {Map<string, { stop:()=>void }>} */
  const demoLoops = new Map();
  const DEMO_WINDOW_MS = 6000; // compressed from 20s so a burst is watchable

  function setPref(type, patch) {
    prefs = {
      ...prefs,
      types: { ...prefs.types, [type]: { ...prefs.types[type], ...patch } },
    };
    persistPrefs(prefs);
  }

  function toggleEnabled(type, e) {
    const checked = /** @type {HTMLInputElement} */ (e.currentTarget).checked;
    setPref(type, { enabled: checked });
    liveMsg = `${(metaForType(type) || {}).label || type} tone ${checked ? 'enabled' : 'disabled'}.`;
  }

  function setVolume(type, e) {
    const v = Number(/** @type {HTMLInputElement} */ (e.currentTarget).value) / 100;
    setPref(type, { volume: Number.isFinite(v) ? v : 0 });
  }

  function toggleMasterMute(e) {
    const muted = /** @type {HTMLInputElement} */ (e.currentTarget).checked;
    prefs = { ...prefs, master_muted: muted };
    persistPrefs(prefs);
    if (muted) {
      // hush stops every looping tone immediately (live + demo); badges remain.
      stopAllLive();
      stopDemo();
      liveMsg = 'Master mute on -- all escalation tones hushed (badges remain).';
    } else {
      liveMsg = 'Master mute off -- tones re-armed.';
    }
  }

  function preview(type, e) {
    const ok = play(type);
    const label = (metaForType(type) || {}).label || type;
    liveMsg = ok
      ? `Played ${label} preview tone.`
      : `${label} preview suppressed (feature/audible/mute off or disabled).`;
  }

  // -- MOCK burst: enqueue the mock feed, each row loops a tone while its window
  // bar drains, then clears (badge gone, tone stopped). Proves the M5 coupling.
  function enqueueDemo(entry) {
    const t = metaForType(entry.type);
    if (!t) return;
    const id = `${entry.sessionId}:${entry.type}:${Date.now()}:${Math.random().toString(36).slice(2, 6)}`;
    const didPlay = play(entry.type);
    demoRows = [...demoRows, { id, type: entry.type, sessionId: entry.sessionId, audible: didPlay, fillPct: 100 }];
    liveMsg = (didPlay ? 'Sounding: ' : 'Badge up (silent): ') + t.label;

    const g = GRAMMAR[entry.type];
    const started = Date.now();
    const repeat = setInterval(() => {
      if (!masterActive) return; // hush keeps the badge, drops sound
      const ok = play(entry.type);
      if (ok) markDemo(id, { audible: true });
    }, Math.max(1200, Math.min(g.repeatMs, 2200)));
    const drain = setInterval(() => {
      const left = Math.max(0, DEMO_WINDOW_MS - (Date.now() - started));
      markDemo(id, { fillPct: (left / DEMO_WINDOW_MS) * 100 });
      if (left <= 0) stop();
    }, 80);
    function stop() {
      clearInterval(repeat);
      clearInterval(drain);
      demoLoops.delete(id);
      demoRows = demoRows.filter((r) => r.id !== id);
    }
    demoLoops.set(id, { stop });
  }

  function markDemo(id, patch) {
    demoRows = demoRows.map((r) => (r.id === id ? { ...r, ...patch } : r));
  }

  function simulateBurst() {
    audioCtx(); // unlock on the user gesture
    if (burstTimer) { clearInterval(burstTimer); burstTimer = null; }
    let i = 0;
    demoHint = 'bursting -- 5 escalations';
    enqueueDemo(MOCK_FEED[i]); i += 1;
    burstTimer = setInterval(() => {
      if (i >= MOCK_FEED.length) {
        clearInterval(burstTimer); burstTimer = null;
        demoHint = 'burst done -- windows draining';
        return;
      }
      enqueueDemo(MOCK_FEED[i]); i += 1;
    }, 1400);
  }

  function stopDemo() {
    if (burstTimer) { clearInterval(burstTimer); burstTimer = null; }
    for (const loop of demoLoops.values()) { try { loop.stop(); } catch { /* noop */ } }
    demoLoops.clear();
    demoRows = [];
    demoHint = 'cleared';
  }

  async function openPanel() {
    panelOpen = true;
    await tick();
    if (firstPanelFocus && typeof firstPanelFocus.focus === 'function') firstPanelFocus.focus();
  }

  function closePanel() {
    if (!panelOpen) return;
    panelOpen = false;
    stopDemo();
    if (launcherBtn && typeof launcherBtn.focus === 'function') launcherBtn.focus();
  }

  function onKeydown(e) {
    if (e.key === 'Escape' && panelOpen) { e.preventDefault(); closePanel(); }
  }

  // ==========================================================================
  // LIFECYCLE: wire the live escalationStore subscriber ONLY while mounted (the
  // {#if} gate means onMount only runs when the flag is ON). When the feature is
  // toggled OFF the component unmounts, onDestroy tears everything down, and the
  // AudioContext is closed -- zero residual runtime cost.
  // ==========================================================================
  onMount(() => {
    if (typeof window !== 'undefined') window.addEventListener('keydown', onKeydown);
    // seed the high-water mark so we don't re-sound a backlog already past its
    // window on first paint; then subscribe for new escalations.
    const initial = escalationStore;
    unsubEsc = escalationStore.subscribe((list) => { ingestEscalations(list); });
    void initial;
    return () => {};
  });

  onDestroy(() => {
    if (typeof window !== 'undefined') window.removeEventListener('keydown', onKeydown);
    if (unsubEsc) { unsubEsc(); unsubEsc = null; }
    stopAllLive();
    stopDemo();
    if (actx) { try { actx.close(); } catch { /* noop */ } actx = null; }
  });
</script>

{#if featureOn}
  <!-- INVISIBLE CONTROLLER: no governance DOM. The only rendered surface is the
       quiet launcher + the on-demand settings sub-panel below. -->
  <button
    bind:this={launcherBtn}
    type="button"
    class="son-launcher"
    aria-haspopup="dialog"
    aria-expanded={panelOpen}
    aria-label={`Escalation sonification settings -- ${audibleOn && !prefs.master_muted ? 'audible' : 'silent'}, ${liveCount} tone${liveCount === 1 ? '' : 's'} sounding`}
    on:click={openPanel}
  >
    <span class="son-launcher__glyph" aria-hidden="true">&#9834;</span>
    <span class="son-launcher__txt">Sonification</span>
    <span class="son-launcher__state" data-on={masterActive}>
      {!audibleOn ? 'AUDIBLE OFF' : prefs.master_muted ? 'HUSHED' : liveCount ? `${liveCount} SOUNDING` : 'ARMED'}
    </span>
  </button>

  {#if panelOpen}
    <!-- backdrop: click-away closes (focus returns to the launcher). -->
    <div class="son-scrim" on:click={closePanel} aria-hidden="true"></div>

    <section
      class="son-panel"
      role="dialog"
      aria-modal="false"
      aria-label="Escalation sonification settings (BETA)"
    >
      <header class="son-panel__head">
        <span class="son-panel__title">Settings &gt; BETA &gt; Escalation sonification</span>
        <button
          bind:this={firstPanelFocus}
          type="button"
          class="son-x"
          aria-label="Close sonification settings"
          on:click={closePanel}
        >Close</button>
      </header>

      <p class="son-lede">
        Sound is the <b>summons</b>; the badge is the <b>signal</b>. A tone loops
        only while its escalation badge is up, then stops -- <b>silence == handled</b>.
        The visible badge stays fully sufficient; sound only adds a channel for
        the looking-away case.
      </p>

      <!-- MASTER ROW: the existing "Audible cue" gate + a one-keystroke hush. -->
      <div class="son-master">
        <span class="son-master__label">Sonification</span>
        <span class="son-statechip" data-on={masterActive}>
          <span class="son-statechip__dot" aria-hidden="true"></span>
          <span>{!audibleOn ? 'AUDIBLE CUE OFF' : prefs.master_muted ? 'HUSHED' : 'ON'}</span>
        </span>
        <span class="son-master__spacer"></span>
        {#if !audibleOn}
          <span class="son-master__note">
            Master "Audible cue" is OFF in Settings -- turn it on to hear any tone.
          </span>
        {/if}
        <label class="son-hush" title="Hush all tones without changing per-type prefs">
          <input
            type="checkbox"
            checked={prefs.master_muted}
            aria-label={`Master mute -- hush all escalation tones, currently ${prefs.master_muted ? 'on' : 'off'}`}
            on:change={toggleMasterMute}
          />
          <span class="son-hush__txt" data-muted={prefs.master_muted}>
            {prefs.master_muted ? 'Muted' : 'Master mute'}
          </span>
        </label>
      </div>

      <!-- GROUP: FOREGROUND (3) -- hard triggers, typographically louder. -->
      <div class="son-grp">
        <span class="son-grp__name">Foreground triggers</span>
        <span class="son-grp__hint">-- auto-foreground + ACTION REQUIRED badge</span>
      </div>
      <div class="son-rows">
        {#each foregroundTypes as t (t.type)}
          {@const pref = prefs.types[t.type]}
          <div class="son-row" data-tier="foreground" data-sev={t.sev}>
            <span class="son-row__id">
              <span class="son-sev-dot" aria-hidden="true"></span>
              <span class="son-row__names">
                <span class="son-row__name">{t.label}</span>
                <span class="son-row__type">{t.type}</span>
              </span>
            </span>
            <button
              type="button"
              class="son-preview"
              aria-label={`${t.label} escalation sound, preview tone`}
              on:click={(e) => preview(t.type, e)}
            >
              <span class="son-preview__glyph" aria-hidden="true">&#9658;</span>Preview
            </button>
            <label class="son-en" title={`Enable the ${t.label} tone`}>
              <input
                type="checkbox"
                checked={pref.enabled}
                aria-label={`${t.label} escalation sound, currently ${pref.enabled ? 'ON' : 'OFF'}`}
                on:change={(e) => toggleEnabled(t.type, e)}
              />
              <span class="son-en__txt" data-on={pref.enabled}>{pref.enabled ? 'ON' : 'OFF'}</span>
            </label>
            <span class="son-vol">
              <input
                type="range" min="0" max="100" step="5"
                value={pct(pref.volume)}
                aria-label={`${t.label} escalation sound volume, ${pct(pref.volume)} percent`}
                on:input={(e) => setVolume(t.type, e)}
              />
              <span class="son-vol__num">{pct(pref.volume)}%</span>
            </span>
          </div>
        {/each}
      </div>

      <!-- GROUP: BADGE-IN-PLACE (3) -- advisories, quiet-and-distinct. -->
      <div class="son-grp son-grp--badge">
        <span class="son-grp__name">Badge-in-place advisories</span>
        <span class="son-grp__hint">-- flag in place, never steal focus</span>
      </div>
      <div class="son-rows">
        {#each badgeTypes as t (t.type)}
          {@const pref = prefs.types[t.type]}
          <div class="son-row" data-tier="badge" data-sev={t.sev}>
            <span class="son-row__id">
              <span class="son-sev-dot" aria-hidden="true"></span>
              <span class="son-row__names">
                <span class="son-row__name">{t.label}</span>
                <span class="son-row__type">{t.type}</span>
              </span>
            </span>
            <button
              type="button"
              class="son-preview"
              aria-label={`${t.label} escalation sound, preview tone`}
              on:click={(e) => preview(t.type, e)}
            >
              <span class="son-preview__glyph" aria-hidden="true">&#9658;</span>Preview
            </button>
            <label class="son-en" title={`Enable the ${t.label} tone`}>
              <input
                type="checkbox"
                checked={pref.enabled}
                aria-label={`${t.label} escalation sound, currently ${pref.enabled ? 'ON' : 'OFF'}`}
                on:change={(e) => toggleEnabled(t.type, e)}
              />
              <span class="son-en__txt" data-on={pref.enabled}>{pref.enabled ? 'ON' : 'OFF'}</span>
            </label>
            <span class="son-vol">
              <input
                type="range" min="0" max="100" step="5"
                value={pct(pref.volume)}
                aria-label={`${t.label} escalation sound volume, ${pct(pref.volume)} percent`}
                on:input={(e) => setVolume(t.type, e)}
              />
              <span class="son-vol__num">{pct(pref.volume)}%</span>
            </span>
          </div>
        {/each}
      </div>

      <!-- LIVE STRIP (MOCK demo) -- sound coupled to badge visibility. -->
      <div class="son-demo">
        <div class="son-demo__head">
          <span class="son-demo__title">Live -- sound coupled to badge</span>
          <span class="son-badge son-badge--observing">DEMO</span>
        </div>
        <div class="son-demo__ctl">
          <button type="button" class="son-btn son-btn--primary" on:click={simulateBurst}>Simulate burst</button>
          <button type="button" class="son-btn" on:click={stopDemo}>Clear</button>
          <span class="son-demo__hint">{demoHint}</span>
        </div>
        <div class="son-live" aria-live="polite">
          {#if demoRows.length === 0}
            <p class="son-live__empty">No active escalation -- silence == nothing needs you.</p>
          {:else}
            {#each demoRows as r (r.id)}
              {@const t = metaForType(r.type)}
              <div class="son-live__row" data-tier={t ? t.tier : 'badge'}>
                <span class="son-badge son-badge--{t ? t.badge : 'observing'}">{t ? t.label : r.type}</span>
                <span class="son-live__meta">{r.sessionId} &middot; {r.type}</span>
                <span class="son-live__spacer"></span>
                {#if r.audible}
                  <span class="son-audible">
                    <span class="son-audible__spk" aria-hidden="true">&#9834;</span>AUDIBLE
                  </span>
                {:else}
                  <span class="son-audible son-audible--silent">SILENT</span>
                {/if}
                <span class="son-winbar"><span class="son-winbar__fill" style={`width:${r.fillPct}%`}></span></span>
              </div>
            {/each}
          {/if}
        </div>
      </div>

      <p class="son-foot">
        BETA -- ui-only, additive. No new bus envelope, no new table, no server
        data. Per-type prefs are client-side only. With the flag OFF the
        controller registers no subscriber and never touches AudioContext.
        Heavy parts (custom sound packs, recorded sonification timelines) are
        deferred to a from-CLI affordance, not built in-process.
      </p>
    </section>
  {/if}

  <!-- polite live region for screen-reader announcements (sound is supplemental). -->
  <p class="son-sr" aria-live="polite">{liveMsg}</p>
{/if}

<style>
  /* QUIET LAUNCHER -- fixed bottom-left, calm; paired glyph + literal text +
     paired state chip (M4). Does not compete with the monitor it serves. */
  .son-launcher {
    position: fixed;
    left: 0.75rem;
    bottom: 0.75rem;
    z-index: 40;
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    appearance: none;
    cursor: pointer;
    font-family: var(--font-d, var(--ff-mono));
    font-size: 0.66rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 0.3rem 0.6rem;
    border-radius: 999px;
    background: var(--bg-card, #0c1118);
    border: 1px solid var(--border, #192030);
    color: var(--text-ui, #8a8068);
    transition: border-color 0.18s, color 0.18s;
  }
  .son-launcher:hover { border-color: var(--border-hi, rgba(245, 158, 11, 0.25)); color: var(--text-bright, #e8e0cc); }
  .son-launcher__glyph { font-size: 0.8rem; line-height: 1; }
  .son-launcher__state {
    font-weight: 700;
    color: var(--text-dim, #948870);
    border-left: 1px solid var(--border, #192030);
    padding-left: 0.45rem;
  }
  .son-launcher__state[data-on='true'] { color: var(--accent, #f59e0b); }

  /* SCRIM + PANEL -- a bottom-left non-modal sub-panel mirroring the mockup. */
  .son-scrim {
    position: fixed; inset: 0; z-index: 41;
    background: rgba(0, 0, 0, 0.35);
  }
  .son-panel {
    position: fixed;
    left: 0.75rem;
    bottom: 3rem;
    z-index: 42;
    width: min(34rem, calc(100vw - 1.5rem));
    max-height: min(80vh, 44rem);
    overflow-y: auto;
    background: var(--bg-card, #0c1118);
    border: 1px solid var(--border, #192030);
    border-radius: 10px;
    box-shadow: 0 18px 48px rgba(0, 0, 0, 0.5);
    color: var(--text, #b8b098);
    font-family: var(--font-h, var(--ff-system));
    font-size: 0.82rem;
  }

  .son-panel__head {
    display: flex; align-items: center; justify-content: space-between; gap: 0.75rem;
    padding: 0.75rem 0.9rem;
    border-bottom: 1px solid var(--border, #192030);
    position: sticky; top: 0; background: var(--bg-card, #0c1118); z-index: 1;
  }
  .son-panel__title {
    font-family: var(--font-d, var(--ff-mono)); font-size: 0.66rem; font-weight: 700;
    letter-spacing: 0.1em; text-transform: uppercase; color: var(--text-ui, #8a8068);
  }
  .son-x {
    appearance: none; cursor: pointer;
    font-family: var(--font-d, var(--ff-mono)); font-size: 0.62rem; font-weight: 700;
    letter-spacing: 0.08em; text-transform: uppercase;
    padding: 0.25rem 0.6rem; border-radius: 5px;
    background: transparent; border: 1px solid var(--border, #192030); color: var(--text-bright, #e8e0cc);
    transition: border-color 0.16s;
  }
  .son-x:hover { border-color: var(--border-hi, rgba(245, 158, 11, 0.25)); }

  .son-lede {
    margin: 0; padding: 0.65rem 0.9rem;
    font-size: 0.74rem; line-height: 1.55; color: var(--text-dim, #948870);
    border-bottom: 1px solid var(--border, #192030);
  }
  .son-lede b { color: var(--text, #b8b098); font-weight: 700; }

  /* MASTER ROW */
  .son-master {
    display: flex; align-items: center; gap: 0.65rem; flex-wrap: wrap;
    padding: 0.65rem 0.9rem;
    border-bottom: 1px solid var(--border, #192030);
    background: var(--bg-row-alt, #0b1018);
  }
  .son-master__label {
    font-family: var(--font-d, var(--ff-mono)); font-size: 0.72rem; font-weight: 700;
    letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-bright, #e8e0cc);
  }
  .son-master__spacer { flex: 1 1 auto; }
  .son-master__note {
    font-family: var(--font-d, var(--ff-mono)); font-size: 0.6rem;
    color: var(--badge-warn-fg, #ea580c); letter-spacing: 0.02em; max-width: 22ch;
  }
  .son-statechip {
    display: inline-flex; align-items: center; gap: 0.4rem;
    font-family: var(--font-d, var(--ff-mono)); font-size: 0.62rem; font-weight: 700;
    letter-spacing: 0.06em; text-transform: uppercase;
    padding: 0.2rem 0.55rem; border-radius: 999px;
    background: var(--bg-row, #0e141e); border: 1px solid var(--border, #192030); color: var(--text-ui, #8a8068);
  }
  .son-statechip[data-on='true'] {
    background: var(--accent-dim, rgba(245, 158, 11, 0.09));
    border-color: var(--border-hi, rgba(245, 158, 11, 0.25));
    color: var(--accent, #f59e0b);
  }
  .son-statechip__dot { width: 0.4rem; height: 0.4rem; border-radius: 50%; background: currentColor; }

  .son-hush { display: inline-flex; align-items: center; gap: 0.4rem; cursor: pointer; }
  .son-hush input { width: 1rem; height: 1rem; accent-color: var(--accent, #f59e0b); cursor: pointer; }
  .son-hush__txt {
    font-family: var(--font-d, var(--ff-mono)); font-size: 0.62rem; font-weight: 600;
    letter-spacing: 0.05em; text-transform: uppercase; color: var(--text-ui, #8a8068);
  }
  .son-hush__txt[data-muted='true'] { color: var(--badge-blocked-fg, #dc2626); }

  /* GROUP HEADERS */
  .son-grp {
    display: flex; align-items: baseline; gap: 0.5rem;
    padding: 0.65rem 0.9rem 0.3rem;
  }
  .son-grp--badge { border-top: 1px solid var(--border, #192030); margin-top: 0.3rem; }
  .son-grp__name {
    font-family: var(--font-d, var(--ff-mono)); font-size: 0.6rem; font-weight: 700;
    letter-spacing: 0.14em; text-transform: uppercase; color: var(--text-ui, #8a8068);
  }
  .son-grp__hint {
    font-family: var(--font-d, var(--ff-mono)); font-size: 0.58rem; color: var(--text-dim, #948870);
  }

  /* PER-TYPE ROWS */
  .son-rows { padding: 0 0 0.25rem; }
  .son-row {
    display: grid; align-items: center; gap: 0.6rem;
    grid-template-columns: minmax(0, 1fr) auto auto 6.5rem;
    padding: 0.5rem 0.9rem;
    border-bottom: 1px solid var(--border, #192030);
  }
  .son-row:last-child { border-bottom: 0; }
  @media (max-width: 32rem) {
    .son-row { grid-template-columns: 1fr auto; row-gap: 0.45rem; }
    .son-vol { grid-column: 1 / -1; }
  }

  .son-row__id { display: inline-flex; align-items: center; gap: 0.5rem; min-width: 0; }
  .son-sev-dot { width: 0.55rem; height: 0.55rem; border-radius: 50%; flex: 0 0 auto; background: currentColor; }
  .son-row__names { min-width: 0; display: inline-flex; align-items: baseline; gap: 0.4rem; }
  .son-row__name {
    font-family: var(--font-d, var(--ff-mono)); font-weight: 700;
    letter-spacing: 0.03em; text-transform: uppercase;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .son-row__type {
    font-family: var(--font-d, var(--ff-mono)); font-size: 0.58rem;
    color: var(--text-dim, #948870);
  }
  /* FOREGROUND tier: heavier weight + red severity dot (the loud triggers). */
  .son-row[data-tier='foreground'] .son-row__name { font-size: 0.84rem; font-weight: 800; color: var(--text-bright, #e8e0cc); }
  .son-row[data-tier='foreground'] .son-sev-dot { color: var(--c-block, #ef4444); }
  /* BADGE-IN-PLACE tier: lighter; variance = guide-yellow, advisories = slate. */
  .son-row[data-tier='badge'] .son-row__name { font-size: 0.74rem; font-weight: 600; color: var(--text, #b8b098); }
  .son-row[data-tier='badge'][data-sev='warn'] .son-sev-dot { color: var(--c-guide, #eab308); }
  .son-row[data-tier='badge'][data-sev='notice'] .son-sev-dot { color: var(--badge-obs-fg, #475569); }

  .son-preview {
    appearance: none; cursor: pointer;
    display: inline-flex; align-items: center; gap: 0.35rem;
    font-family: var(--font-d, var(--ff-mono)); font-size: 0.6rem; font-weight: 700;
    letter-spacing: 0.05em; text-transform: uppercase;
    padding: 0.3rem 0.55rem; border-radius: 6px;
    background: transparent; border: 1px solid var(--border, #192030); color: var(--text-bright, #e8e0cc);
    transition: border-color 0.16s, color 0.16s;
  }
  .son-preview:hover { border-color: var(--border-hi, rgba(245, 158, 11, 0.25)); }
  .son-preview__glyph { font-size: 0.62rem; line-height: 1; }

  .son-en { display: inline-flex; align-items: center; gap: 0.4rem; cursor: pointer; }
  .son-en input { width: 1rem; height: 1rem; accent-color: var(--accent, #f59e0b); cursor: pointer; }
  .son-en__txt {
    font-family: var(--font-d, var(--ff-mono)); font-size: 0.58rem; font-weight: 700;
    letter-spacing: 0.05em; min-width: 2.2ch; color: var(--text-dim, #948870);
  }
  .son-en__txt[data-on='true'] { color: var(--accent, #f59e0b); }

  .son-vol { display: inline-flex; align-items: center; gap: 0.45rem; }
  .son-vol input[type='range'] { width: 4.4rem; accent-color: var(--accent, #f59e0b); cursor: pointer; }
  .son-vol__num {
    font-family: var(--font-d, var(--ff-mono)); font-size: 0.58rem; color: var(--text-dim, #948870);
    min-width: 2.6ch; text-align: right;
  }

  /* LIVE DEMO STRIP */
  .son-demo { border-top: 1px solid var(--border, #192030); }
  .son-demo__head {
    display: flex; align-items: center; justify-content: space-between; gap: 0.6rem;
    padding: 0.6rem 0.9rem; border-bottom: 1px solid var(--border, #192030);
  }
  .son-demo__title {
    font-family: var(--font-d, var(--ff-mono)); font-size: 0.62rem; font-weight: 700;
    letter-spacing: 0.1em; text-transform: uppercase; color: var(--text-ui, #8a8068);
  }
  .son-demo__ctl {
    display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center;
    padding: 0.6rem 0.9rem; border-bottom: 1px solid var(--border, #192030);
  }
  .son-btn {
    appearance: none; cursor: pointer;
    font-family: var(--font-h, var(--ff-system)); font-size: 0.7rem; font-weight: 600;
    padding: 0.35rem 0.7rem; border-radius: 6px;
    border: 1px solid var(--border, #192030); background: transparent; color: var(--text-bright, #e8e0cc);
    transition: border-color 0.16s, filter 0.16s;
  }
  .son-btn:hover { border-color: var(--border-hi, rgba(245, 158, 11, 0.25)); }
  .son-btn--primary { background: var(--accent, #f59e0b); color: #1a1206; border-color: var(--accent, #f59e0b); }
  .son-btn--primary:hover { filter: brightness(1.06); }
  .son-demo__hint {
    font-family: var(--font-d, var(--ff-mono)); font-size: 0.58rem; color: var(--text-ui, #8a8068);
  }

  .son-live { min-height: 4rem; padding: 0.75rem 0.9rem; display: flex; flex-direction: column; gap: 0.5rem; }
  .son-live__empty {
    margin: 0; color: var(--text-dim, #948870); font-style: italic; font-size: 0.74rem; text-align: center;
  }
  .son-live__row {
    display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;
    padding: 0.5rem 0.6rem; border: 1px solid var(--border, #192030); border-radius: 8px;
    background: var(--bg-row, #0e141e);
  }
  .son-live__row[data-tier='foreground'] { border-color: var(--badge-ar-border, #d97706); }
  .son-live__meta { font-family: var(--font-d, var(--ff-mono)); font-size: 0.6rem; color: var(--text-dim, #948870); }
  .son-live__spacer { flex: 1 1 auto; }
  .son-audible {
    display: inline-flex; align-items: center; gap: 0.35rem;
    font-family: var(--font-d, var(--ff-mono)); font-size: 0.58rem; font-weight: 700;
    letter-spacing: 0.05em; text-transform: uppercase;
    padding: 0.15rem 0.45rem; border-radius: 999px;
    background: var(--accent-dim, rgba(245, 158, 11, 0.09));
    border: 1px solid var(--border-hi, rgba(245, 158, 11, 0.25)); color: var(--accent, #f59e0b);
  }
  .son-audible--silent {
    background: var(--bg-row-alt, #0b1018);
    border-color: var(--border, #192030); color: var(--text-dim, #948870);
  }
  .son-audible__spk { animation: son-ring 1s ease-in-out infinite; }
  @keyframes son-ring { 0%, 100% { opacity: 0.45; } 50% { opacity: 1; } }

  .son-winbar {
    width: 100%; height: 0.25rem; border-radius: 999px; overflow: hidden;
    background: var(--bg-row-alt, #0b1018); border: 1px solid var(--border, #192030);
  }
  .son-winbar__fill { display: block; height: 100%; background: var(--accent, #f59e0b); }
  .son-live__row[data-tier='foreground'] .son-winbar__fill { background: var(--badge-ar-fg, #d97706); }

  /* PAIRED LABEL+COLOR BADGES (M4) -- leading swatch + literal text. */
  .son-badge {
    display: inline-flex; align-items: center; gap: 0.35rem;
    font-family: var(--font-d, var(--ff-mono)); font-size: 0.58rem; font-weight: 700;
    letter-spacing: 0.06em; text-transform: uppercase;
    padding: 0.15rem 0.45rem; border-radius: 4px; white-space: nowrap;
  }
  .son-badge::before { content: ''; width: 0.45rem; height: 0.45rem; border-radius: 2px; background: currentColor; opacity: 0.9; }
  .son-badge--ar { color: var(--badge-ar-fg, #d97706); background: var(--badge-ar-bg, #fef3c7); border: 2px solid var(--badge-ar-border, #d97706); }
  .son-badge--blocked { color: var(--badge-blocked-fg, #dc2626); background: var(--badge-blocked-bg, #fee2e2); border: 2px solid var(--badge-blocked-border, #dc2626); }
  .son-badge--warn { color: var(--badge-warn-fg, #ea580c); background: var(--badge-warn-bg, #ffedd5); border: 1px dashed var(--badge-warn-border, #ea580c); }
  .son-badge--observing { color: var(--badge-obs-fg, #475569); background: var(--badge-obs-bg, #f1f5f9); border: 1px solid var(--badge-obs-border, #cbd5e1); }

  .son-foot {
    margin: 0; padding: 0.65rem 0.9rem;
    font-size: 0.64rem; line-height: 1.5; color: var(--text-dim, #948870);
    border-top: 1px solid var(--border, #192030);
  }

  /* A11Y: 2px amber focus ring + 2px offset on every interactive element. */
  .son-launcher:focus-visible,
  .son-x:focus-visible,
  .son-preview:focus-visible,
  .son-btn:focus-visible,
  .son-hush input:focus-visible,
  .son-en input:focus-visible,
  .son-vol input:focus-visible {
    outline: 2px solid var(--badge-ar-border, #d97706);
    outline-offset: 2px;
    border-radius: 6px;
  }

  .son-sr {
    position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
    overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
  }

  /* Reduced motion: drop the ring pulse + transitions. */
  :global(html[data-motion='reduce']) .son-audible__spk { animation: none; }
  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .son-audible__spk { animation: none; }
    :global(html:not([data-motion='allow'])) .son-launcher,
    :global(html:not([data-motion='allow'])) .son-preview,
    :global(html:not([data-motion='allow'])) .son-btn { transition: none; }
  }
</style>
