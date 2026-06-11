// SonificationEscalationLayer-grammar.js -- the data-only leaf for BETA feature
// "sonification-escalation-layer" (#44: Escalation Sonification as a DERIVED
// confirmation layer). Pure data + pure helpers: NO DOM, NO Svelte import, NO
// AudioContext here. The component owns the Web Audio rendering; this module
// owns the frozen synthesis grammar, the per-type metadata mirror, the mock
// escalation feed, and the per-type preference defaults + (de)serialization.
//
// SOUND IS CONFIRMATION, NEVER SIGNAL (ADR-18 M5, structural): every key in the
// GRAMMAR / TYPES tables is 1:1 with a trigger in the FROZEN lib/escalation.js
// ESCALATION_TABLE. This module classifies NOTHING -- the component subscribes
// to the existing escalationStore (produced solely from the escalation.js
// allow-list) and looks a tone up by the type the store already decided. Adding
// a type here that is NOT in escalation.js does nothing (the store never emits
// it); removing one only silences that already-visible badge's tone.
//
// M16 (domain-agnostic): the only identifiers are generic escalation TYPE keys
// (already public in escalation.js) + placeholder mock session ids
// (sess-mock-1..3). No monitored-project vocabulary, no JOB ids, no role names.
//
// G2 (polarity): this is a presentation overlay over the escalationStore, which
// is already SM-self excluded upstream (sse.js drops own-session rows). This
// module reads NO database, opens NO socket; there is nothing here to poison.
//
// ASCII-only (cp1252-safe): dash is "--"; no smart quotes / em-dashes / box chars.

/**
 * @typedef {Object} GrammarTone
 * @property {'sine'|'triangle'|'square'|'sawtooth'} waveform oscillator type
 * @property {number[]} freqs          sequence of frequencies (Hz), played in order
 * @property {number} durationMs       per-note duration (ms)
 * @property {number} repeatMs         loop interval while the badge is up (ms)
 */

/**
 * THE SOUND GRAMMAR. One frozen row per recognized escalation type. Keyed 1:1 to
 * lib/escalation.js ESCALATION_TABLE. Pure synthesis params -- no audio assets
 * are shipped; the controller renders these as AudioContext oscillators so the
 * feature adds zero static files. Foreground triggers get heavier, more
 * arresting timbres (sawtooth + sub-bass); badge-in-place advisories get quiet,
 * distinct two-notes so the operator LEARNS not to break focus for them.
 *
 * @type {Readonly<Record<string, Readonly<GrammarTone>>>}
 */
export const GRAMMAR = Object.freeze({
  // ---- foreground-eligible (the only three that may steal focus) ----
  desktop_pause: Object.freeze({
    waveform: 'square', freqs: [880, 880], durationMs: 100, repeatMs: 3000,
  }),
  governance_negative_regression: Object.freeze({
    waveform: 'sawtooth', freqs: [80, 440], durationMs: 1000, repeatMs: 3000,
  }),
  'static-rule': Object.freeze({
    waveform: 'sawtooth', freqs: [80, 440], durationMs: 1000, repeatMs: 3000,
  }),
  // ---- badge-in-place only (never foreground) ----
  governance_variance_alert: Object.freeze({
    waveform: 'triangle', freqs: [659.25, 587.33, 523.25], durationMs: 300, repeatMs: 4000,
  }),
  new_pattern: Object.freeze({
    waveform: 'sine', freqs: [523.25, 659.25], durationMs: 200, repeatMs: 8000,
  }),
  low_confidence: Object.freeze({
    waveform: 'sine', freqs: [523.25, 659.25], durationMs: 200, repeatMs: 8000,
  }),
});

/**
 * @typedef {Object} SonType
 * @property {string} type     canonical escalation.js key (the GRAMMAR key)
 * @property {string} label    paired UPPERCASE text label (M4 -- text-first)
 * @property {'foreground'|'badge'} tier  the M2 partition (defers to escalation.js)
 * @property {'critical'|'warn'|'notice'} sev  presentation severity (weight only)
 * @property {'ar'|'blocked'|'warn'|'observing'} badge  paired badge style
 * @property {string} desc     human reason (badge title / aria text)
 * @property {number} volume   default per-type volume 0..1
 */

/**
 * Per-type metadata, MIRRORING lib/escalation.js (disposition + severity) plus
 * the canonical badge style + a sensible default volume. The controller DEFERS
 * to escalation.js for what escalates; this table only drives presentation of
 * the settings rows + the mock live strip. Foreground tier is louder by default.
 *
 * @type {ReadonlyArray<Readonly<SonType>>}
 */
export const TYPES = Object.freeze([
  // FOREGROUND tier ---------------------------------------------------------
  Object.freeze({
    type: 'desktop_pause', label: 'PAUSE', tier: 'foreground', sev: 'critical',
    badge: 'ar', volume: 0.7,
    desc: 'Desktop orchestration paused -- operator attention required',
  }),
  Object.freeze({
    type: 'governance_negative_regression', label: 'NEG REGRESSION',
    tier: 'foreground', sev: 'critical', badge: 'ar', volume: 0.8,
    desc: 'Governance negative regression detected',
  }),
  Object.freeze({
    type: 'static-rule', label: 'STATIC RULE', tier: 'foreground', sev: 'critical',
    badge: 'blocked', volume: 0.8,
    desc: 'Static rule fired -- hard governance trigger',
  }),
  // BADGE-IN-PLACE tier -----------------------------------------------------
  Object.freeze({
    type: 'governance_variance_alert', label: 'VARIANCE', tier: 'badge', sev: 'warn',
    badge: 'warn', volume: 0.55,
    desc: 'Governance variance alert -- flagged in place',
  }),
  Object.freeze({
    type: 'new_pattern', label: 'NEW PATTERN', tier: 'badge', sev: 'notice',
    badge: 'observing', volume: 0.4,
    desc: 'New behavioural pattern observed -- flagged in place',
  }),
  Object.freeze({
    type: 'low_confidence', label: 'LOW CONFIDENCE', tier: 'badge', sev: 'notice',
    badge: 'observing', volume: 0.4,
    desc: 'Low-confidence decision -- flagged in place',
  }),
]);

/** O(1) lookup of a type's metadata by its canonical key. */
const _BY_TYPE = Object.freeze(
  TYPES.reduce((m, t) => { m[t.type] = t; return m; }, /** @type {Record<string, SonType>} */ ({})),
);

/**
 * Resolve the presentation metadata for an escalation type. Returns null for an
 * unknown / non-string type so the caller can no-op (closed-world: a type with
 * no grammar simply has no tone -- the badge is still fully sufficient, M5).
 * @param {*} type
 * @returns {Readonly<SonType>|null}
 */
export function metaForType(type) {
  if (typeof type !== 'string') return null;
  return _BY_TYPE[type] || null;
}

/**
 * Pull a canonical escalation type off a heterogeneous escalationStore entry.
 * sse.js entries are `{ rule:{ trigger }, sessionId, ts }`; we read defensively
 * so a malformed entry never throws in the subscriber. Falls back to a bare
 * `type` field for forward-compat / the mock feed.
 * @param {*} entry
 * @returns {string} canonical type or '' when absent.
 */
export function typeOfEscalation(entry) {
  if (!entry || typeof entry !== 'object') return '';
  const rule = entry.rule;
  if (rule && typeof rule.trigger === 'string' && rule.trigger) return rule.trigger;
  if (typeof entry.type === 'string') return entry.type;
  return '';
}

/**
 * MOCK escalation feed used when no live escalation is in scope (so the live
 * strip + the burst demo are always testable, usedMockData=true). Placeholder
 * session ids only (M16). Ordered foreground-then-advisory so the operator hears
 * the grammar discriminate hard triggers from quiet advisories.
 * @type {ReadonlyArray<Readonly<{type:string, sessionId:string}>>}
 */
export const MOCK_FEED = Object.freeze([
  Object.freeze({ type: 'new_pattern', sessionId: 'sess-mock-1' }),
  Object.freeze({ type: 'governance_variance_alert', sessionId: 'sess-mock-1' }),
  Object.freeze({ type: 'desktop_pause', sessionId: 'sess-mock-2' }),
  Object.freeze({ type: 'static-rule', sessionId: 'sess-mock-2' }),
  Object.freeze({ type: 'governance_negative_regression', sessionId: 'sess-mock-3' }),
]);

/** localStorage key for the per-type prefs mirror (client-side only; never the bus). */
export const LS_SONIFICATION = 'sm.next.sonification';

/**
 * Build the default per-type preference map (every recognized type enabled, at
 * its tier-appropriate default volume). This is the OFF-by-tone-but-feature-ON
 * baseline; the feature flag still gates the whole controller above this.
 * @returns {Record<string, {enabled:boolean, volume:number}>}
 */
export function defaultPrefs() {
  /** @type {Record<string, {enabled:boolean, volume:number}>} */
  const out = {};
  for (const t of TYPES) out[t.type] = { enabled: true, volume: t.volume };
  return out;
}

/**
 * Coerce a raw (operator-mutable localStorage) prefs blob back into range over
 * the known type set, so a corrupt mirror can never push an out-of-contract
 * value downstream. Unknown keys are dropped; missing keys take their default.
 * @param {unknown} raw
 * @returns {{ master_muted:boolean, types:Record<string, {enabled:boolean, volume:number}> }}
 */
export function coercePrefs(raw) {
  const base = defaultPrefs();
  const r = raw && typeof raw === 'object' ? /** @type {Record<string, any>} */ (raw) : {};
  const rt = r.types && typeof r.types === 'object' ? r.types : {};
  /** @type {Record<string, {enabled:boolean, volume:number}>} */
  const types = {};
  for (const key of Object.keys(base)) {
    const got = rt[key] && typeof rt[key] === 'object' ? rt[key] : {};
    const v = Number(got.volume);
    types[key] = {
      enabled: typeof got.enabled === 'boolean' ? got.enabled : base[key].enabled,
      volume: Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : base[key].volume,
    };
  }
  return {
    master_muted: typeof r.master_muted === 'boolean' ? r.master_muted : false,
    types,
  };
}

/**
 * Load the per-type prefs from localStorage, coerced. Falls back to defaults on
 * any error / SSR (no localStorage). Client-side only -- never a server read.
 * @returns {{ master_muted:boolean, types:Record<string, {enabled:boolean, volume:number}> }}
 */
export function loadPrefs() {
  if (typeof localStorage === 'undefined') return coercePrefs(null);
  try {
    const raw = localStorage.getItem(LS_SONIFICATION);
    return coercePrefs(raw ? JSON.parse(raw) : null);
  } catch {
    return coercePrefs(null);
  }
}

/**
 * Persist the per-type prefs to localStorage (best-effort; private-mode / quota
 * failures are non-fatal -- the feature simply does not remember across reloads).
 * @param {{ master_muted:boolean, types:Record<string, {enabled:boolean, volume:number}> }} prefs
 */
export function persistPrefs(prefs) {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(LS_SONIFICATION, JSON.stringify(prefs));
  } catch {
    /* private mode / quota -- non-fatal */
  }
}

/** Round a 0..1 volume to an integer percent for the paired text readout. */
export function pct(v) {
  return Math.round(Math.min(1, Math.max(0, Number(v) || 0)) * 100);
}
