// layout.js -- per-session frame arrangement + scroll state (MUST M1).
//
// Owns the still-water shell's persisted layout: which order the three
// guaranteed frames (A Interactive Sessions / B Sub-Agents / C Background
// Jobs) are stacked in, and each frame's last scroll offset, keyed per
// session_id in localStorage. Ships a Reset control contract.
//
// Contract notes for reviewers:
//  - M1: arrangement is free, PRESENCE is not. This store NEVER removes a
//    frame from the order; reset/sanitise always re-materialises the full
//    canonical {A,B,C} set. A corrupt or partial persisted order is healed,
//    not honoured, so a frame can never vanish from a bad localStorage blob.
//  - M16 (domain-agnostic): zero monitored-project vocabulary here. Frame
//    identity is the fixed UI taxonomy A/B/C, not a governed-target name.
//  - M18 (latency budget): this is pure client-side view state. It performs
//    no network I/O and is never on any verdict hot path.
//
// The store is framework-light on purpose: a hand-rolled Svelte store
// contract ({subscribe, ...methods}) so it has a single owner and no hidden
// coupling to sibling units.

import { writable } from 'svelte/store';

// The three frames are a FROZEN presence guarantee. Order may permute; the
// SET may not shrink. Anything reading this must treat it as exhaustive.
export const FRAME_KEYS = Object.freeze(['A', 'B', 'C']);

// Human-facing, domain-AGNOSTIC frame identity. These are UI taxonomy
// labels (the operator's three observation lanes), never governed-target
// vocabulary -- M16. A governed session's name is rendered from /api/sessions
// data by child units, never hard-coded here.
export const FRAME_META = Object.freeze({
  A: Object.freeze({ key: 'A', title: 'Interactive Sessions', hint: 'REPL + session activity' }),
  B: Object.freeze({ key: 'B', title: 'Sub-Agents', hint: 'role-tagged agent timeline' }),
  C: Object.freeze({ key: 'C', title: 'Background Jobs', hint: 'lifecycle: jobs + spawned agents' }),
});

const STORAGE_PREFIX = 'sm.ui-next.layout.';
const NO_SESSION = '__no_session__';

function storageKey(sessionId) {
  const s = sessionId == null || sessionId === '' ? NO_SESSION : String(sessionId);
  return STORAGE_PREFIX + s;
}

// A localStorage shim that degrades to an in-memory map. Private-mode
// browsers / SSR / a hostile storage quota must never break frame presence,
// so persistence failure is non-fatal: the layout still renders, just
// session-volatile.
const memFallback = new Map();
function safeStorage() {
  try {
    if (typeof localStorage !== 'undefined') {
      const probe = '__sm_probe__';
      localStorage.setItem(probe, '1');
      localStorage.removeItem(probe);
      return localStorage;
    }
  } catch (_e) {
    // fall through to memory
  }
  return {
    getItem: (k) => (memFallback.has(k) ? memFallback.get(k) : null),
    setItem: (k, v) => { memFallback.set(k, v); },
    removeItem: (k) => { memFallback.delete(k); },
  };
}

// Canonical default layout: frames in declared order, no remembered scroll.
function defaultLayout() {
  return {
    order: [...FRAME_KEYS],
    scroll: { A: 0, B: 0, C: 0 },
  };
}

// Heal an arbitrary persisted blob back to a valid layout. The healing rule
// is the load-bearing M1 guard: every canonical frame key is guaranteed
// present exactly once, in a stable, de-duplicated order. Unknown keys are
// dropped; missing keys are appended in canonical order.
function sanitise(raw) {
  const base = defaultLayout();
  if (!raw || typeof raw !== 'object') return base;

  const seen = new Set();
  const order = [];
  if (Array.isArray(raw.order)) {
    for (const k of raw.order) {
      if (FRAME_KEYS.includes(k) && !seen.has(k)) {
        seen.add(k);
        order.push(k);
      }
    }
  }
  // Guarantee presence: append any canonical frame the persisted order missed.
  for (const k of FRAME_KEYS) {
    if (!seen.has(k)) order.push(k);
  }

  const scroll = { A: 0, B: 0, C: 0 };
  if (raw.scroll && typeof raw.scroll === 'object') {
    for (const k of FRAME_KEYS) {
      const v = Number(raw.scroll[k]);
      scroll[k] = Number.isFinite(v) && v >= 0 ? v : 0;
    }
  }

  return { order, scroll };
}

function load(sessionId) {
  try {
    const rawStr = safeStorage().getItem(storageKey(sessionId));
    if (!rawStr) return defaultLayout();
    return sanitise(JSON.parse(rawStr));
  } catch (_e) {
    return defaultLayout();
  }
}

function persist(sessionId, layout) {
  try {
    safeStorage().setItem(storageKey(sessionId), JSON.stringify(layout));
  } catch (_e) {
    // Persistence is best-effort; presence is guaranteed regardless. Swallow.
  }
}

function createLayoutStore() {
  // Internal shape: { sessionId, layout: {order, scroll} }.
  const initialSession = null;
  const inner = writable({ sessionId: initialSession, layout: load(initialSession) });
  const { subscribe, update, set } = inner;

  // Point the store at a session. Loads that session's persisted arrangement
  // (or the canonical default), so switching the header session picker
  // re-materialises the right per-session layout. PRESENCE is preserved
  // across the switch because load() routes through sanitise().
  function useSession(sessionId) {
    set({ sessionId, layout: load(sessionId) });
  }

  // Re-order the frames. The new order is sanitised before persist so a
  // malformed argument can never drop a frame -- M1.
  function setOrder(nextOrder) {
    update((s) => {
      const layout = sanitise({ order: nextOrder, scroll: s.layout.scroll });
      persist(s.sessionId, layout);
      return { ...s, layout };
    });
  }

  // Move a single frame up/down within the stack (keyboard-reorder friendly).
  function move(frameKey, delta) {
    update((s) => {
      const order = [...s.layout.order];
      const idx = order.indexOf(frameKey);
      if (idx === -1) return s;
      const target = idx + delta;
      if (target < 0 || target >= order.length) return s;
      [order[idx], order[target]] = [order[target], order[idx]];
      const layout = sanitise({ order, scroll: s.layout.scroll });
      persist(s.sessionId, layout);
      return { ...s, layout };
    });
  }

  // Remember a frame's scroll offset (called from Frame.svelte on scroll,
  // debounced by the caller). Cheap client-only write -- M18.
  function setScroll(frameKey, top) {
    if (!FRAME_KEYS.includes(frameKey)) return;
    update((s) => {
      const v = Number.isFinite(top) && top >= 0 ? top : 0;
      if (s.layout.scroll[frameKey] === v) return s;
      const layout = { ...s.layout, scroll: { ...s.layout.scroll, [frameKey]: v } };
      persist(s.sessionId, layout);
      return { ...s, layout };
    });
  }

  // The M1 Reset control: restore canonical order + zero scroll for the
  // active session, persist it, and return the fresh layout so the caller
  // can imperatively reset scrollTop on the DOM nodes.
  function reset() {
    let fresh = defaultLayout();
    update((s) => {
      fresh = defaultLayout();
      persist(s.sessionId, fresh);
      return { ...s, layout: fresh };
    });
    return fresh;
  }

  return { subscribe, useSession, setOrder, move, setScroll, reset };
}

export const layoutStore = createLayoutStore();

// Test-facing pure helpers (the render-validator / S2 contract can import
// these without a DOM). Exposed so the M1 presence-heal is unit-testable.
export const __layoutInternals = { defaultLayout, sanitise, FRAME_KEYS };
