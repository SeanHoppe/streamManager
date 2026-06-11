// beta.js -- BETA feature-flag store (2026-06-11 BETA proposals initiative).
//
// Holds the operator's on/off choice for each optional BETA feature. The store
// is the single client-side owner of flag state; every feature component gates
// itself on it (renders nothing -- registers no pollers/SSE handlers -- when its
// key is OFF). Persistence is server-side (beta_flags table via /api/beta/flags)
// with a localStorage mirror so a returning operator's choices apply instantly
// on first paint before the server hydrate lands.
//
// Default OFF is load-bearing: an unknown/unset key reads false. A server read
// error NEVER flips a flag on -- it degrades to the persisted mirror, then to
// the registry defaults (all OFF).
//
// ASCII-only (cp1252-safe): dash is "--".

import { writable, get, derived } from 'svelte/store';
import { betaDefaults } from '../beta/registry.js';
import { getBetaFlags, postBetaFlag } from '../api.js';

const LS_BETA = 'sm.next.beta-flags';

/** @returns {Record<string, boolean>} defaults merged over any localStorage mirror. */
function load() {
  const base = betaDefaults();
  if (typeof localStorage === 'undefined') return base;
  try {
    const raw = localStorage.getItem(LS_BETA);
    if (!raw) return base;
    const stored = JSON.parse(raw);
    if (stored && typeof stored === 'object') {
      for (const k of Object.keys(stored)) {
        if (k in base) base[k] = !!stored[k];
      }
    }
  } catch {
    /* corrupt mirror -- fall back to defaults (all OFF) */
  }
  return base;
}

/** @param {Record<string, boolean>} flags */
function persist(flags) {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(LS_BETA, JSON.stringify(flags));
  } catch {
    /* private mode / quota -- non-fatal; server remains the source of truth */
  }
}

const _flags = writable(load());

/**
 * Public read-only view of the flag map. Components subscribe with
 * `$betaFlags['<key>']` -- truthy means the feature is ON.
 * @type {import('svelte/store').Readable<Record<string, boolean>>}
 */
export const betaFlags = { subscribe: _flags.subscribe };

/**
 * One-feature derived gate. `derived(isBetaOn('away-mode'), ...)` style usage:
 * returns a store that is true iff the named feature is ON.
 * @param {string} key
 */
export function betaGate(key) {
  return derived(_flags, ($f) => !!$f[key]);
}

/**
 * Synchronous gate read (for non-reactive call sites).
 * @param {string} key
 * @returns {boolean}
 */
export function isBetaEnabled(key) {
  return !!get(_flags)[key];
}

/**
 * Hydrate from the server (GET /api/beta/flags). Merges stored overrides over
 * the current map; unknown keys are ignored. Best-effort: a failed/empty fetch
 * leaves the persisted/default map untouched (never flips anything on). Call
 * once at app boot.
 */
export async function hydrateBetaFlags() {
  try {
    const { flags } = await getBetaFlags();
    if (!flags || typeof flags !== 'object') return;
    _flags.update((cur) => {
      const next = { ...cur };
      for (const k of Object.keys(next)) {
        if (k in flags) next[k] = !!flags[k];
      }
      persist(next);
      return next;
    });
  } catch {
    /* offline / server down -- keep the persisted mirror; monitoring continues */
  }
}

/**
 * Toggle one feature. Optimistically updates + persists the mirror, POSTs the
 * new state, and rolls back the single key on a write failure (so a server-down
 * condition can never leave the UI claiming ON while the backend is OFF).
 * @param {string} key
 * @param {boolean} enabled
 */
export async function setBetaFlag(key, enabled) {
  const prev = get(_flags)[key];
  _flags.update((cur) => { const n = { ...cur, [key]: !!enabled }; persist(n); return n; });
  try {
    await postBetaFlag(key, !!enabled);
  } catch {
    // rollback just this key
    _flags.update((cur) => { const n = { ...cur, [key]: !!prev }; persist(n); return n; });
  }
}
