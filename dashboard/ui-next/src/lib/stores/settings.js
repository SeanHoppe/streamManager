// settings.js -- FR-UI-9 operator settings state for u-settings. A single
// persisted store holds every Settings-panel field; any mutation persists to
// localStorage AND emits a `dashboard_settings_changed` CustomEvent on
// `window` so u-settings (and any other interested pane) can react without
// importing this module's internals.
//
// FR-UI-9 fields preserved from the live dashboard contract:
//   hitlMode          -- 'sync' | 'async' (M5: SYNC/ASYNC only, never off)
//   confidenceFloor   -- 0..1 advisory floor
//   syncTimeoutSec    -- HITL SYNC hold timeout (M9 countdown default 60)
//   pauseDetection    -- desktop-pause detection on/off
//   audibleCue        -- audible escalation cue (default OFF)
//   activityWindowSec -- "active in window" span (Frame B pinning, 1..600)
//   reducedMotion     -- 'system' | 'on' | 'off' (M17 reduced-motion)
//
// Layout reset (FR-UI-9 row 8) is a separate operator action that lives with
// the per-session layout keys (owned by u-shell); resetLayout() here just
// fires the same change event with a {layoutReset:true} marker so listeners
// can clear their localStorage layout and re-emit. This module owns NO layout
// geometry -- only the settings payload.

import { writable, get } from 'svelte/store';

const LS_SETTINGS = 'sm.next.settings';
export const SETTINGS_CHANGED_EVENT = 'dashboard_settings_changed';

/**
 * @typedef {Object} SmSettings
 * @property {'sync'|'async'} hitlMode
 * @property {number} confidenceFloor
 * @property {number} syncTimeoutSec
 * @property {boolean} pauseDetection
 * @property {boolean} audibleCue
 * @property {number} activityWindowSec
 * @property {'system'|'on'|'off'} reducedMotion
 */

/** @type {SmSettings} */
export const DEFAULT_SETTINGS = Object.freeze({
  hitlMode: 'async',
  confidenceFloor: 0.5,
  syncTimeoutSec: 60,
  pauseDetection: true,
  audibleCue: false,
  activityWindowSec: 10,
  reducedMotion: 'system',
});

// ---------------------------------------------------------------------------
// Validation / coercion. The persisted blob is operator-mutable localStorage;
// coerce every field back into range so a corrupt entry can never push an
// out-of-contract value (e.g. hitlMode 'off' -- forbidden by M5) downstream.
// ---------------------------------------------------------------------------

/** @param {unknown} raw @returns {SmSettings} */
function coerce(raw) {
  const r = raw && typeof raw === 'object' ? /** @type {Record<string, any>} */ (raw) : {};
  const clamp = (v, lo, hi, dflt) => {
    const n = Number(v);
    if (!Number.isFinite(n)) return dflt;
    return Math.min(hi, Math.max(lo, n));
  };
  return {
    // M5: SYNC/ASYNC only. Any other value (including 'off') falls back to
    // the default async -- the UI must never surface a third HITL state.
    hitlMode: r.hitlMode === 'sync' ? 'sync' : 'async',
    confidenceFloor: clamp(r.confidenceFloor, 0, 1, DEFAULT_SETTINGS.confidenceFloor),
    syncTimeoutSec: Math.round(clamp(r.syncTimeoutSec, 1, 3600, DEFAULT_SETTINGS.syncTimeoutSec)),
    pauseDetection: typeof r.pauseDetection === 'boolean' ? r.pauseDetection : DEFAULT_SETTINGS.pauseDetection,
    audibleCue: typeof r.audibleCue === 'boolean' ? r.audibleCue : DEFAULT_SETTINGS.audibleCue,
    activityWindowSec: Math.round(clamp(r.activityWindowSec, 1, 600, DEFAULT_SETTINGS.activityWindowSec)),
    reducedMotion:
      r.reducedMotion === 'on' || r.reducedMotion === 'off' ? r.reducedMotion : 'system',
  };
}

/** @returns {SmSettings} */
function load() {
  if (typeof localStorage === 'undefined') return { ...DEFAULT_SETTINGS };
  try {
    const raw = localStorage.getItem(LS_SETTINGS);
    if (!raw) return { ...DEFAULT_SETTINGS };
    return coerce(JSON.parse(raw));
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

/** @param {SmSettings} s */
function persist(s) {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(LS_SETTINGS, JSON.stringify(s));
  } catch {
    /* private mode / quota -- non-fatal */
  }
}

/**
 * Emit the FR-UI-9 `dashboard_settings_changed` event. detail carries the full
 * coerced settings snapshot plus the changed key set so listeners can do a
 * cheap diff. layoutReset is surfaced as an extra marker for the layout-reset
 * affordance (the only "setting" this module does not itself store).
 * @param {SmSettings} settings
 * @param {string[]} changedKeys
 * @param {{ layoutReset?:boolean }} [extra]
 */
function emitChanged(settings, changedKeys, extra) {
  if (typeof window === 'undefined' || typeof CustomEvent === 'undefined') return;
  window.dispatchEvent(
    new CustomEvent(SETTINGS_CHANGED_EVENT, {
      detail: { settings: { ...settings }, changedKeys, ...(extra || {}) },
    }),
  );
}

// ---------------------------------------------------------------------------
// The store.
// ---------------------------------------------------------------------------

const _settings = writable(load());

/**
 * Public settings store. `set`/`update` persist and emit the FR-UI-9 change
 * event. Prefer `patch()` for single-field edits from the Settings panel.
 * @type {import('svelte/store').Writable<SmSettings>}
 */
export const settings = {
  subscribe: _settings.subscribe,
  /** @param {SmSettings} value */
  set(value) {
    const next = coerce(value);
    const prev = get(_settings);
    const changedKeys = diffKeys(prev, next);
    persist(next);
    _settings.set(next);
    if (changedKeys.length) emitChanged(next, changedKeys);
  },
  /** @param {(v:SmSettings)=>SmSettings} fn */
  update(fn) {
    this.set(fn(get(_settings)));
  },
};

/**
 * Patch one or more fields. Coerces, persists, and emits with the precise
 * changed-key list. No-ops (and emits nothing) when nothing actually changes.
 * @param {Partial<SmSettings>} partial
 */
export function patch(partial) {
  const prev = get(_settings);
  const next = coerce({ ...prev, ...partial });
  const changedKeys = diffKeys(prev, next);
  if (changedKeys.length === 0) return;
  persist(next);
  _settings.set(next);
  emitChanged(next, changedKeys);
}

/**
 * Layout reset affordance (FR-UI-9 row 8). This module owns no geometry, so it
 * simply re-broadcasts the change event with a layoutReset marker; u-shell
 * clears its per-session layout localStorage in response. Settings values are
 * left untouched.
 */
export function resetLayout() {
  emitChanged(get(_settings), [], { layoutReset: true });
}

/**
 * Reset all settings to defaults (persists + emits). Distinct from
 * resetLayout(); used by a "restore defaults" control if u-settings adds one.
 */
export function resetSettings() {
  const prev = get(_settings);
  const next = { ...DEFAULT_SETTINGS };
  const changedKeys = diffKeys(prev, next);
  persist(next);
  _settings.set(next);
  if (changedKeys.length) emitChanged(next, changedKeys);
}

/**
 * @param {SmSettings} a
 * @param {SmSettings} b
 * @returns {string[]} keys whose value differs between a and b
 */
function diffKeys(a, b) {
  /** @type {string[]} */
  const out = [];
  for (const k of Object.keys(b)) {
    if (a[/** @type {keyof SmSettings} */ (k)] !== b[/** @type {keyof SmSettings} */ (k)]) out.push(k);
  }
  return out;
}
