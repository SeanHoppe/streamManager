// pollers.js -- the interval registry for the post-hoc REST pollers. Three
// pollers, all OFF the verdict hot path (M18):
//
//   stats          /api/stats             every  5s   (global)
//   agents         /api/agents            every  8s   (session-scoped)
//   lifecycleJobs  /api/lifecycle/jobs    every  2s   (session-scoped, M14)
//
// Each poller writes to a Svelte store the panes subscribe to. Session-scoped
// pollers re-fire immediately when selectedSessionId changes so the panes
// re-scope without waiting a full interval. Errors are swallowed to keep the
// timers alive (the server already degrades to empty/zero shapes; a transient
// transport failure must not kill the poll loop). M18: nothing here is a hard
// dependency of any verdict -- it is observability only.

import { writable, get } from 'svelte/store';
import { getStats, getAgents, getLifecycleJobs } from './api.js';
import { selectedSessionId, scopeParam } from './stores/session.js';

// ---------------------------------------------------------------------------
// Output stores.
// ---------------------------------------------------------------------------

/** @type {import('svelte/store').Writable<Record<string, any>>} */
export const statsStore = writable({
  total_decisions: 0,
  sessions: 0,
  active_sessions: 0,
  graph_pct: 0,
  avg_confidence: 0,
  actions: {},
});

/** @type {import('svelte/store').Writable<Array<Record<string, any>>>} */
export const agentsStore = writable([]);

/** @type {import('svelte/store').Writable<Array<Record<string, any>>>} */
export const lifecycleJobsStore = writable([]);

// ---------------------------------------------------------------------------
// Poller definitions. `scoped` pollers read scopeParam() at fire time so they
// always use the current selection (no stale closure over session_id).
// ---------------------------------------------------------------------------

/**
 * @typedef {Object} PollerDef
 * @property {string} name
 * @property {number} intervalMs
 * @property {boolean} scoped     -- true => re-fires on session change
 * @property {() => Promise<void>} tick
 */

/** @type {PollerDef[]} */
const POLLERS = [
  {
    name: 'stats',
    intervalMs: 5000,
    scoped: false,
    async tick() {
      try {
        const data = await getStats();
        if (data && !data.error) statsStore.set(data);
      } catch {
        /* keep the loop alive */
      }
    },
  },
  {
    name: 'agents',
    intervalMs: 8000,
    scoped: true,
    async tick() {
      try {
        const rows = await getAgents({ session_id: scopeParam() });
        agentsStore.set(Array.isArray(rows) ? rows : []);
      } catch {
        /* keep the loop alive */
      }
    },
  },
  {
    name: 'lifecycleJobs',
    intervalMs: 2000,
    scoped: true,
    async tick() {
      try {
        const res = await getLifecycleJobs({ session_id: scopeParam() });
        lifecycleJobsStore.set(res && Array.isArray(res.jobs) ? res.jobs : []);
      } catch {
        /* keep the loop alive */
      }
    },
  },
];

// ---------------------------------------------------------------------------
// Registry lifecycle.
// ---------------------------------------------------------------------------

/** @type {Map<string, ReturnType<typeof setInterval>>} */
const _timers = new Map();
/** @type {(() => void)|null} */
let _unsubSession = null;
let _running = false;

/**
 * Start all pollers. Each fires once immediately (so panes populate without
 * waiting a full interval), then on its interval. Subscribes to
 * selectedSessionId so the scoped pollers re-fire on selection change.
 * Idempotent: a second call while running is a no-op.
 */
export function startPollers() {
  if (_running) return;
  _running = true;

  for (const p of POLLERS) {
    // Immediate first fire.
    void p.tick();
    _timers.set(
      p.name,
      setInterval(() => void p.tick(), p.intervalMs),
    );
  }

  // Re-scope on selection change. svelte's `subscribe` fires immediately with
  // the current value; skip that first synchronous call so we don't double-
  // fire the immediate ticks above.
  let primed = false;
  _unsubSession = selectedSessionId.subscribe(() => {
    if (!primed) {
      primed = true;
      return;
    }
    for (const p of POLLERS) {
      if (p.scoped) void p.tick();
    }
  });
}

/** Stop all pollers + drop the session subscription. */
export function stopPollers() {
  _running = false;
  for (const t of _timers.values()) clearInterval(t);
  _timers.clear();
  if (_unsubSession) {
    _unsubSession();
    _unsubSession = null;
  }
}

/**
 * Force an immediate re-fire of every scoped poller (e.g. after an operator
 * action that should refresh agents/jobs without waiting). Safe to call even
 * when stopped (it just ticks once).
 */
export function refreshScoped() {
  for (const p of POLLERS) {
    if (p.scoped) void p.tick();
  }
}

/** @returns {boolean} whether the registry is currently running */
export function isRunning() {
  return _running;
}

// Re-export so consumers needing the current scope (e.g. a manual export) can
// read it from one place without importing session.js directly.
export { scopeParam };
