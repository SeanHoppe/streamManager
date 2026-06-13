// theme.js -- the SINGLE live owner of the active color theme (<html data-theme>).
//
// Why this exists: the original theme switch + prefers-color-scheme logic lived
// inside HeaderBar.svelte, which the composition root (App.svelte) does NOT mount
// (App injects SessionPicker into the header slot directly; the SessionRail owns
// scope). So in the live tree NOTHING ever set data-theme -- the three themes in
// theme.css never activated and the UI rendered off the component-layer dark
// fallbacks only, with no dark/light control. Lifting the logic to a store that
// applies at module load (and is driven by a mounted ThemeToggle) makes dark +
// light actually work in the running app.
//
// Resolution order at boot: persisted operator pick -> OS prefers-color-scheme
// (light -> paper, otherwise obsidian) -> obsidian default. A persisted pick
// always wins so an explicit choice is never overridden by a later OS change.
//
// theme.css carries the AA-documented token VALUES (FROZEN contract); this store
// only flips the attribute + persists. ASCII-only (cp1252).
import { writable, get } from 'svelte/store';

export const THEMES = Object.freeze([
  { id: 'obsidian', label: 'Obsidian', scheme: 'dark' },
  { id: 'phosphor', label: 'Phosphor', scheme: 'dark' },
  { id: 'paper', label: 'Paper', scheme: 'light' },
]);

const VALID = new Set(THEMES.map((t) => t.id));
const LS_THEME = 'sm.next.theme';
const DEFAULT = 'obsidian';

function systemTheme() {
  try {
    if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
      if (window.matchMedia('(prefers-color-scheme: light)').matches) return 'paper';
    }
  } catch (_e) {
    /* matchMedia unavailable -- fall through to the dark default */
  }
  return DEFAULT;
}

function persisted() {
  try {
    const s = typeof localStorage !== 'undefined' ? localStorage.getItem(LS_THEME) : null;
    return s && VALID.has(s) ? s : null;
  } catch (_e) {
    return null;
  }
}

function resolveInitial() {
  // persisted pick wins; else the OS dark/light preference; else the dark default.
  return persisted() || systemTheme();
}

function applyAttr(t) {
  const v = VALID.has(t) ? t : DEFAULT;
  if (typeof document !== 'undefined' && document.documentElement) {
    document.documentElement.setAttribute('data-theme', v);
  }
  try {
    if (typeof localStorage !== 'undefined') localStorage.setItem(LS_THEME, v);
  } catch (_e) {
    /* private mode / quota -- theme just will not persist, non-fatal */
  }
}

const _theme = writable(resolveInitial());

/**
 * Public theme store. `set` validates, applies <html data-theme>, and persists.
 * @type {{ subscribe: import('svelte/store').Readable<string>['subscribe'], set:(t:string)=>void }}
 */
export const theme = {
  subscribe: _theme.subscribe,
  set(t) {
    const v = VALID.has(t) ? t : DEFAULT;
    applyAttr(v);
    _theme.set(v);
  },
};

export function setTheme(t) {
  theme.set(t);
}

/** Toggle the dark/light axis: paper (light) <-> obsidian (dark). phosphor counts as dark. */
export function toggleDarkLight() {
  theme.set(get(_theme) === 'paper' ? 'obsidian' : 'paper');
}

// Apply the resolved theme at module load so data-theme is live before any
// control mounts (the import graph reaches here via App -> ThemeToggle). Idempotent.
applyAttr(resolveInitial());
