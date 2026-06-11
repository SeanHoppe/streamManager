// QuickFilters-presets.js -- the data layer for BETA feature "quick-filters"
// (#22, FR-UI-9 quick-filter presets). Pure, side-effect-light helpers shared by
// QuickFilters.svelte: the four built-in posture presets, the localStorage
// custom-preset store, config equality + the active-name resolver, and the
// literal micro-spec line. No DOM, no Svelte, no fetch.
//
// DOMAIN-AGNOSTIC (M16): the four-tuple is pure operator-settings taxonomy
// (confidence floor / HITL mode / sync timeout / pause detection). ZERO
// monitored-project vocabulary; preset_name is operator-supplied free text.
//
// NO NEW gov.db TABLE / NO AMENDMENT: custom presets persist CLIENT-SIDE ONLY in
// localStorage (key sm.next.presets), mirroring the lib/stores/settings.js +
// lib/stores/beta.js localStorage idiom. The four config keys are EXACTLY the
// SmSettings keys settings.js coerce() owns, so applying a preset is just
// patch(config) on the shared settings store.
//
// ASCII-only (cp1252-safe): dash is "--". No smart quotes, no em-dashes.

/**
 * @typedef {Object} PresetConfig
 * @property {number} confidenceFloor   0..1 advisory floor
 * @property {'sync'|'async'} hitlMode  M5: two states only, never off
 * @property {number} syncTimeoutSec    1..3600 HITL SYNC hold timeout
 * @property {boolean} pauseDetection   desktop-pause auto-foreground source
 */

/**
 * @typedef {Object} Preset
 * @property {string} name
 * @property {PresetConfig} config
 * @property {string} [hint]
 * @property {string} [createdAt]
 * @property {boolean} [builtin]
 */

/** localStorage key for operator custom presets (client-side only). */
export const LS_PRESETS = 'sm.next.presets';

/**
 * The four built-in posture presets (frozen). Values match the operator-approved
 * KingMode mockup (reports/proposals/mockups/quick-filters.html) field-for-field.
 * @type {ReadonlyArray<Preset>}
 */
export const BUILTINS = Object.freeze([
  {
    name: 'PARANOID',
    builtin: true,
    config: { confidenceFloor: 0.95, hitlMode: 'sync', syncTimeoutSec: 120, pauseDetection: true },
    hint: 'Clamp down: high floor, every decision held SYNC, long read window.',
  },
  {
    name: 'STANDARD',
    builtin: true,
    config: { confidenceFloor: 0.6, hitlMode: 'sync', syncTimeoutSec: 60, pauseDetection: true },
    hint: 'Day-to-day triage posture.',
  },
  {
    name: 'TRUST',
    builtin: true,
    config: { confidenceFloor: 0.35, hitlMode: 'async', syncTimeoutSec: 30, pauseDetection: false },
    hint: 'Fast prototyping: low floor, async, no holds.',
  },
  {
    name: 'AUDIT',
    builtin: true,
    config: { confidenceFloor: 0.99, hitlMode: 'sync', syncTimeoutSec: 300, pauseDetection: true },
    hint: 'Pre-ship: maximal floor, very long hold.',
  },
]);

/**
 * Coerce one raw config to the four legal fields, clamped to the same ranges
 * settings.js coerce() enforces (so a corrupt localStorage entry can never push
 * an out-of-contract value -- e.g. hitlMode 'off', forbidden by M5).
 * @param {unknown} raw
 * @returns {PresetConfig}
 */
export function coerceConfig(raw) {
  const r = raw && typeof raw === 'object' ? /** @type {Record<string, any>} */ (raw) : {};
  const clamp = (v, lo, hi, dflt) => {
    const n = Number(v);
    if (!Number.isFinite(n)) return dflt;
    return Math.min(hi, Math.max(lo, n));
  };
  return {
    confidenceFloor: Math.round(clamp(r.confidenceFloor, 0, 1, 0.5) * 100) / 100,
    // M5: anything that is not exactly 'sync' falls back to 'async'.
    hitlMode: r.hitlMode === 'sync' ? 'sync' : 'async',
    syncTimeoutSec: Math.round(clamp(r.syncTimeoutSec, 1, 3600, 60)),
    pauseDetection: typeof r.pauseDetection === 'boolean' ? r.pauseDetection : true,
  };
}

/**
 * True when two configs are equal across the four FR-UI-9 fields.
 * @param {PresetConfig} a
 * @param {PresetConfig} b
 */
export function eqConfig(a, b) {
  if (!a || !b) return false;
  return (
    a.confidenceFloor === b.confidenceFloor &&
    a.hitlMode === b.hitlMode &&
    a.syncTimeoutSec === b.syncTimeoutSec &&
    a.pauseDetection === b.pauseDetection
  );
}

/**
 * Load operator custom presets from localStorage. Always returns an array;
 * coerces each entry and drops malformed ones. Never throws (private mode /
 * quota / corrupt blob -> empty list).
 * @returns {Preset[]}
 */
export function loadCustom() {
  if (typeof localStorage === 'undefined') return [];
  try {
    const raw = localStorage.getItem(LS_PRESETS);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    /** @type {Preset[]} */
    const out = [];
    for (const p of parsed) {
      const name = p && typeof p.name === 'string' ? p.name.trim() : '';
      if (!name) continue;
      out.push({
        name,
        config: coerceConfig(p.config),
        createdAt: typeof p.createdAt === 'string' ? p.createdAt : undefined,
      });
    }
    return out;
  } catch {
    return [];
  }
}

/**
 * Persist operator custom presets to localStorage. Best-effort; non-fatal.
 * @param {Preset[]} list
 */
export function saveCustom(list) {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(LS_PRESETS, JSON.stringify(Array.isArray(list) ? list : []));
  } catch {
    /* private mode / quota -- non-fatal; the rail just won't persist this run */
  }
}

/**
 * A realistic mock custom preset, used ONLY when localStorage is empty so the
 * feature is testable headless (usedMockData). Domain-agnostic, ASCII-only.
 * @returns {Preset[]}
 */
export function mockCustom() {
  return [
    {
      name: 'my-strict-review',
      config: { confidenceFloor: 0.9, hitlMode: 'sync', syncTimeoutSec: 90, pauseDetection: true },
      createdAt: '2026-06-11T05:40:00Z',
    },
  ];
}

/**
 * The matching preset NAME for a config, searching built-ins THEN custom, or
 * null when the config matches none (= "custom" hand-tuned posture).
 * @param {PresetConfig} cfg
 * @param {Preset[]} custom
 * @returns {string|null}
 */
export function activePresetName(cfg, custom) {
  for (const p of BUILTINS) if (eqConfig(p.config, cfg)) return p.name;
  for (const p of custom || []) if (eqConfig(p.config, cfg)) return p.name;
  return null;
}

/**
 * The literal micro-spec line ("95% . SYNC . 120s . pause ON"). Load-bearing
 * TEXT (M4 second channel): the posture is readable in words with all color
 * stripped.
 * @param {PresetConfig} cfg
 * @returns {string}
 */
export function specLine(cfg) {
  const c = coerceConfig(cfg);
  const floor = Math.round(c.confidenceFloor * 100) + '%';
  const mode = c.hitlMode === 'sync' ? 'SYNC' : 'ASYNC';
  const to = c.syncTimeoutSec + 's';
  const pause = c.pauseDetection ? 'pause ON' : 'pause OFF';
  return floor + ' . ' + mode + ' . ' + to + ' . ' + pause;
}

/**
 * Extract just the four preset fields from a fuller SmSettings snapshot.
 * @param {Record<string, any>} s
 * @returns {PresetConfig}
 */
export function configFromSettings(s) {
  return coerceConfig({
    confidenceFloor: s && s.confidenceFloor,
    hitlMode: s && s.hitlMode,
    syncTimeoutSec: s && s.syncTimeoutSec,
    pauseDetection: s && s.pauseDetection,
  });
}
