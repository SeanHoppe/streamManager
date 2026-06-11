// session.js -- the single source of truth that scopes every pane by
// session_id. Three stores:
//
//   ownSessionId      -- the SM's own session id (M15 self-exclude source),
//                        read once from <meta name="sm-own-session-id">. Null
//                        when the meta is absent/empty (=> no self-filtering;
//                        defense-in-depth, the server already strips self).
//   sessions          -- the governed-session list (M16: identities come from
//                        /api/sessions data, NEVER hard-coded), self-excluded,
//                        newest-active first. The SessionRail + header picker
//                        render from this.
//   selectedSessionId -- the operator's active filter. localStorage-persisted;
//                        defaults to the most-recently-active non-self session.
//                        null == ALL governed sessions (no scope filter).
//
// POLARITY (M15/G2): the SM's own session is NEVER presented as a governed
// target. setSessions() filters ownSessionId out structurally, and
// selectedSessionId can never resolve to ownSessionId.

import { writable, derived, get } from 'svelte/store';
import { readOwnSessionId, readOwnProjectSlugs } from '../api.js';

const LS_SELECTED = 'sm.next.selectedSessionId';

// The SM's own project slug(s) -- read once at module load. The polarity rule
// (CLAUDE.md) excludes a governed-target lane by EITHER the self session id OR a
// project_slug in this set, so the SM never presents its own sessions (incl.
// other SM windows/worktrees) as targets. Empty set => no slug-based filtering.
/** @type {Set<string>} */
const OWN_PROJECT_SLUGS = readOwnProjectSlugs();

// ---------------------------------------------------------------------------
// ownSessionId -- read once at module load. Static for the page lifetime
// (the meta is injected server-side by `GET /`). null => skip self-filtering.
// ---------------------------------------------------------------------------

/** @type {import('svelte/store').Readable<string|null>} */
export const ownSessionId = writable(readOwnSessionId());

/**
 * Convenience non-reactive read of the own session id (for the decisions store
 * filter in pollers/sse, where a $-subscription would be heavyweight).
 * @returns {string|null}
 */
export function getOwnSessionId() {
  return get(ownSessionId);
}

// ---------------------------------------------------------------------------
// sessions -- the governed-session list. Self-excluded. Newest-active first.
// ---------------------------------------------------------------------------

/** @typedef {{ id:string, project_slug?:string|null, pid?:number|null,
 *   started_at?:number|null, ended_at?:number|null,
 *   hitl_mode?:string|null, hitl_floor?:number|null }} SessionRow */

/** @type {import('svelte/store').Writable<SessionRow[]>} */
export const sessions = writable([]);

/**
 * Sort key for "most-recently-active". Active sessions (ended_at == null) sort
 * ahead of ended ones; within each group, larger started_at is newer. The
 * server already returns started_at DESC, but we re-sort defensively so the
 * "default most-recent" rule (and the rail order) is stable regardless of
 * source order.
 * @param {SessionRow} a
 * @param {SessionRow} b
 */
function byRecency(a, b) {
  const aActive = a.ended_at === null || a.ended_at === undefined;
  const bActive = b.ended_at === null || b.ended_at === undefined;
  if (aActive !== bActive) return aActive ? -1 : 1;
  return (Number(b.started_at) || 0) - (Number(a.started_at) || 0);
}

/**
 * Replace the session list from /api/sessions data. Filters out the SM's own
 * session (M15) and any row without a usable id (M16: id is the governed
 * identity -- a row with no id cannot be a governed target). Re-anchors the
 * selection if the previously selected session has disappeared.
 * @param {SessionRow[]} rows
 */
export function setSessions(rows) {
  const own = get(ownSessionId);
  const cleaned = (Array.isArray(rows) ? rows : [])
    .filter((r) => {
      if (!r || !r.id || r.id === own) return false; // M15: drop self session id
      // Polarity (CLAUDE.md): drop ANY session on the SM's own project slug --
      // SM must never present its own sessions as governed targets, not just the
      // one self session_id. Slug compared lowercased; empty set => no-op.
      if (OWN_PROJECT_SLUGS.size > 0) {
        const slug = (r.project_slug || '').toString().trim().toLowerCase();
        if (slug && OWN_PROJECT_SLUGS.has(slug)) return false;
      }
      return true;
    })
    .slice()
    .sort(byRecency);
  // Dedup by id: /api/sessions can return the same session_id more than once
  // across its scan window. The recency sort runs FIRST, so keeping the first
  // occurrence keeps the most-recent instance per id; this guarantees a keyed
  // {#each} over the list (the SessionRail lanes / picker) never sees a
  // duplicate key (Svelte throws "duplicate keys in a keyed each" otherwise).
  const seen = new Set();
  const deduped = cleaned.filter((r) => {
    if (seen.has(r.id)) return false;
    seen.add(r.id);
    return true;
  });
  sessions.set(deduped);
  reconcileSelection(deduped);
}

// ---------------------------------------------------------------------------
// selectedSessionId -- the active scope filter. localStorage-persisted.
// null == ALL governed sessions.
// ---------------------------------------------------------------------------

/** @returns {string|null} */
function readPersistedSelection() {
  if (typeof localStorage === 'undefined') return null;
  try {
    const v = localStorage.getItem(LS_SELECTED);
    return v === null || v === '' ? null : v;
  } catch {
    return null;
  }
}

/** @param {string|null} id */
function persistSelection(id) {
  if (typeof localStorage === 'undefined') return;
  try {
    if (id === null) localStorage.removeItem(LS_SELECTED);
    else localStorage.setItem(LS_SELECTED, id);
  } catch {
    /* private mode / quota -- non-fatal, scope just won't persist */
  }
}

/** @type {import('svelte/store').Writable<string|null>} */
const _selected = writable(readPersistedSelection());

/**
 * Public selectedSessionId store. Writes persist to localStorage and refuse to
 * ever resolve to the SM's own session (M15/G2 polarity floor).
 * @type {import('svelte/store').Writable<string|null>}
 */
export const selectedSessionId = {
  subscribe: _selected.subscribe,
  /** @param {string|null} id */
  set(id) {
    const own = get(ownSessionId);
    const safe = id === own ? null : id;
    persistSelection(safe);
    _selected.set(safe);
  },
  /** @param {(v:string|null)=>string|null} fn */
  update(fn) {
    this.set(fn(get(_selected)));
  },
};

/**
 * Select a session by id, or null for ALL. Thin alias used by the header
 * picker / SessionRail click handlers.
 * @param {string|null} id
 */
export function selectSession(id) {
  selectedSessionId.set(id);
}

/**
 * After a session-list refresh, keep the selection valid:
 *  - if a persisted selection still exists in the list, keep it;
 *  - else if there was a selection that vanished, fall back to ALL (null) so
 *    the operator is never stuck filtered to a dead session;
 *  - if no selection was ever made (first load) AND a default is desired, the
 *    caller may opt into most-recent via `defaultToMostRecent()`. We do NOT
 *    auto-pick here so "ALL" stays a deliberate, reachable state.
 * @param {SessionRow[]} list
 */
function reconcileSelection(list) {
  const cur = get(_selected);
  if (cur === null) return; // ALL -- nothing to reconcile
  const stillPresent = list.some((s) => s.id === cur);
  if (!stillPresent) {
    persistSelection(null);
    _selected.set(null);
  }
}

/**
 * Default the selection to the most-recently-active governed session, but ONLY
 * when the operator has no persisted choice yet (first-ever load). Honors the
 * spec "default most-recent" without clobbering a returning operator's pick.
 * Call after the first setSessions().
 */
export function defaultToMostRecent() {
  if (readPersistedSelection() !== null) return; // operator already chose
  if (get(_selected) !== null) return;
  const list = get(sessions);
  if (list.length === 0) return;
  // list is already recency-sorted by setSessions(); [0] is most-recent-active.
  _selected.set(list[0].id);
  persistSelection(list[0].id);
}

// ---------------------------------------------------------------------------
// Derived convenience: the currently selected SessionRow (or null for ALL /
// not-found). Lets panes render the selected session's project_slug / pid /
// hitl_mode without re-querying.
// ---------------------------------------------------------------------------

/** @type {import('svelte/store').Readable<SessionRow|null>} */
export const selectedSession = derived(
  [sessions, _selected],
  ([$sessions, $sel]) => {
    if ($sel === null) return null;
    return $sessions.find((s) => s.id === $sel) || null;
  },
);

/**
 * The session_id query param to pass to scoped endpoints. Returns undefined for
 * the ALL state so api wrappers omit the param entirely (qs() drops undefined).
 * @returns {string|undefined}
 */
export function scopeParam() {
  const sel = get(_selected);
  return sel === null ? undefined : sel;
}
