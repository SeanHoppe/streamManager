/**
 * selfExclude.js -- governance-integrity primitive (MUST M15, POLARITY G2).
 *
 * StreamManager monitors NON-SM sessions and MUST NEVER present its own
 * session as a governed target (default-exclude self). The server injects
 * the SM's own session id into the document head as:
 *
 *     <meta name="sm-own-session-id" content="<session_id>">
 *
 * (see dashboard/server.py root() -- only injected when the SM_OWN_SESSION_ID
 * env var is set). This module reads that meta at DOM-ready and exports the
 * own-session-id plus a filter predicate that drops that session_id from
 * every decision row AND the mirror (defense-in-depth: the SSE handler also
 * strips these rows server-side; this is the redundant client-side layer).
 *
 * Loud-fail-safe contract: an empty / missing meta means SKIP filtering.
 * We never invent or guess a self id. If the server did not inject one,
 * the safest observable behaviour is to show everything (zero rows from a
 * silent over-filter would be an invisible failure; showing rows is loud
 * and operator-correctable). M15 mandates this exact polarity.
 *
 * Pure logic only: no DOM mutation, no component deps, no framework import.
 * The single environmental read (document head meta) is isolated behind
 * readOwnSessionId() and is overridable for tests via an explicit argument,
 * so the module stays a deterministic, side-effect-free leaf.
 *
 * @module lib/selfExclude
 */

const META_NAME = 'sm-own-session-id';

/**
 * Normalize a raw session-id candidate to the canonical form used for
 * comparison. Returns '' for any non-string, null, undefined, or
 * whitespace-only value -- which the rest of the module treats as
 * "no self id, skip filtering".
 *
 * @param {*} raw
 * @returns {string} trimmed id, or '' when absent/invalid
 */
function normalizeId(raw) {
  if (typeof raw !== 'string') return '';
  const trimmed = raw.trim();
  return trimmed;
}

/**
 * Read the SM's own session id from the document head meta tag.
 *
 * Resolution order:
 *   1. an explicit `doc` argument (injected for tests / SSR-free envs);
 *   2. the ambient `document` global when present (browser at DOM-ready).
 * If neither is available (e.g. a non-DOM unit-test context with no doc
 * passed), returns '' -- skip filtering, loud-fail-safe.
 *
 * Per the server contract the meta is ONLY present when SM_OWN_SESSION_ID
 * is set, so a missing tag is a legitimate "no self to exclude" state and
 * MUST NOT throw.
 *
 * @param {Document} [doc] optional document override (defaults to the
 *   ambient global when running in a browser).
 * @returns {string} the own session id, or '' when missing/empty.
 */
export function readOwnSessionId(doc) {
  const d =
    doc !== undefined
      ? doc
      : typeof document !== 'undefined'
        ? document
        : null;
  if (!d || typeof d.querySelector !== 'function') return '';
  let el = null;
  try {
    el = d.querySelector(`meta[name="${META_NAME}"]`);
  } catch (_e) {
    return '';
  }
  if (!el || typeof el.getAttribute !== 'function') return '';
  return normalizeId(el.getAttribute('content'));
}

/**
 * Extract the session id from a heterogeneous row/event/mirror object.
 *
 * Decision rows, SSE bus events, and mirror tool-call events all carry the
 * session under `session_id`. We read defensively so a malformed row never
 * throws inside a hot render loop.
 *
 * @param {*} row
 * @returns {string} the row's session id, or '' when absent.
 */
function rowSessionId(row) {
  if (!row || typeof row !== 'object') return '';
  return normalizeId(row.session_id);
}

/**
 * Build a stable self-exclude predicate bound to a single own-session-id.
 *
 * The returned predicate answers "should this row be KEPT?" -- true means
 * render it, false means drop it (it belongs to the SM's own session).
 *
 * Loud-fail-safe: when `ownId` is empty (missing/blank meta) the predicate
 * keeps EVERYTHING -- it never silently swallows rows. This is the M15
 * mandated polarity: absence of a self id disables filtering rather than
 * filtering everything out.
 *
 * Reference matches against EITHER the canonical own id OR a row whose id is
 * empty are KEPT -- self-exclusion only ever drops an exact, non-empty match,
 * so an unattributed row is never mistaken for self.
 *
 * @param {string} ownId the normalized own session id (from readOwnSessionId).
 * @returns {(row: *) => boolean} predicate: true to keep, false to drop.
 */
export function makeSelfExcludeFilter(ownId) {
  const own = normalizeId(ownId);
  if (!own) {
    // No self id -> skip filtering entirely (loud-fail-safe). Identity keep.
    return function keepAll() {
      return true;
    };
  }
  return function keepIfNotSelf(row) {
    const sid = rowSessionId(row);
    if (!sid) return true; // unattributed rows are never assumed to be self
    return sid !== own;
  };
}

/**
 * Direct boolean test: is this row the SM's own session (and thus to be
 * excluded)? The inverse of the keep-predicate's drop case. Convenience for
 * call sites that branch on exclusion rather than filtering an array.
 *
 * Returns false when `ownId` is empty (nothing is "self" -> exclude nothing)
 * or when the row carries no session id (never assume self).
 *
 * @param {*} row
 * @param {string} ownId normalized own session id.
 * @returns {boolean} true iff the row belongs to the SM's own session.
 */
export function isOwnSession(row, ownId) {
  const own = normalizeId(ownId);
  if (!own) return false;
  const sid = rowSessionId(row);
  if (!sid) return false;
  return sid === own;
}

/**
 * Filter an array of rows, dropping any that belong to the SM's own session.
 * Pure: returns a new array, never mutates the input. Non-array input yields
 * an empty array (defensive; a render loop must never throw here).
 *
 * Loud-fail-safe: with an empty `ownId` this returns a shallow copy of the
 * input unchanged (no rows dropped).
 *
 * @template T
 * @param {T[]} rows
 * @param {string} ownId normalized own session id.
 * @returns {T[]} new array with self-session rows removed.
 */
export function excludeSelfRows(rows, ownId) {
  if (!Array.isArray(rows)) return [];
  const keep = makeSelfExcludeFilter(ownId);
  return rows.filter(keep);
}

/**
 * Resolve the own-session-id once and return a small bound API. Call this
 * at DOM-ready (or pass an explicit `doc` in tests) and reuse the returned
 * object so the meta is read exactly once.
 *
 * @param {Document} [doc] optional document override.
 * @returns {{
 *   ownSessionId: string,
 *   active: boolean,
 *   filter: (row: *) => boolean,
 *   isSelf: (row: *) => boolean,
 *   exclude: <T>(rows: T[]) => T[],
 * }}
 *   - ownSessionId: the resolved id ('' when absent).
 *   - active: true iff filtering is engaged (a non-empty id was found).
 *   - filter: keep-predicate (true to keep a row).
 *   - isSelf: drop-test (true iff a row is the SM's own session).
 *   - exclude: array filter dropping self rows.
 */
export function createSelfExcluder(doc) {
  const ownSessionId = readOwnSessionId(doc);
  const filter = makeSelfExcludeFilter(ownSessionId);
  return {
    ownSessionId,
    active: ownSessionId !== '',
    filter,
    isSelf: (row) => isOwnSession(row, ownSessionId),
    exclude: (rows) => excludeSelfRows(rows, ownSessionId),
  };
}

export { META_NAME as SELF_META_NAME };
