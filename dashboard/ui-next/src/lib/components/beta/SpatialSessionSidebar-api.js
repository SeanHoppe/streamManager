// SpatialSessionSidebar-api.js -- read-only transport for the BETA
// "spatial-session-sidebar" feature (#45). Two additive GETs over the existing
// gov.db, both polarity-filtered server-side (project_slug NOT IN the SM slug set
// AND session_id != SM_OWN_SESSION_ID). Mirrors the lib/api.js getJSON contract
// (Accept JSON, no-store, degrade-not-throw) so the component never reads as
// "live" when the server is down -- it falls back to the deterministic mock.
//
// These two wrappers are ALSO returned to the main thread as the canonical
// lib/api.js helpers (apiHelpers) so the shipped transport layer owns them; this
// local module keeps the build agent's component self-contained without editing
// the shared lib/api.js. The function bodies are identical to the returned ones.
//
// M18: pure post-hoc GET; never on the verdict hot path. M16: hard-codes NO
// governed-target vocabulary -- every identifier is carried verbatim from data.
//
// ASCII-only (cp1252-safe): dash rendered as "--".

/**
 * @param {Record<string, string|number|boolean|null|undefined>} [params]
 * @returns {string}
 */
function qs(params) {
  if (!params) return '';
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === '') continue;
    usp.set(k, String(v));
  }
  const s = usp.toString();
  return s ? `?${s}` : '';
}

/**
 * GET /api/sessions/spatial-overview?limit -- BETA spatial-session-sidebar (#45).
 * One aggregated read of every governed NON-SM session as a spatial node:
 *   { session_id, project_slug, governance_mode, last_activity_ts, open_hitl,
 *     agent_slug, latency_sparkline:number[<=10], alert:string|null }
 * plus the shared-pattern edges between them:
 *   { edges:[{from_session_id, to_session_id, pattern_count, pattern_hashes}] }
 * Polarity-filtered server-side; excluded_self surfaces the dropped self rows.
 * Read-only, post-hoc (M18). Degrades to an empty-shape object on any error /
 * fresh DB so the caller falls back to mock (never reads as live when down).
 * @param {{ limit?:number }} [opts]
 * @returns {Promise<{ now:number, excluded_self:number, nodes:Array<Record<string,any>>, edges:Array<Record<string,any>> }>}
 */
export async function getSpatialOverview(opts = {}) {
  const empty = { now: Math.floor(Date.now() / 1000), excluded_self: 0, nodes: [], edges: [] };
  try {
    const res = await fetch(`/api/sessions/spatial-overview${qs({ limit: opts.limit })}`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    });
    if (!res.ok) return empty;
    const data = await res.json();
    return data && typeof data === 'object' && Array.isArray(data.nodes) ? data : empty;
  } catch {
    return empty;
  }
}

/**
 * GET /api/sessions/pattern-edges?min_pattern_count -- BETA spatial-session-
 * sidebar (#45) standalone edge read (used when the overview is already cached
 * and only the cross-session pattern flows need refreshing). Same edge shape as
 * the overview's `edges`. Polarity-filtered server-side. Degrades to {edges:[]}.
 * @param {{ min_pattern_count?:number }} [opts]
 * @returns {Promise<{ edges:Array<Record<string,any>>, excluded_self:number }>}
 */
export async function getPatternEdges(opts = {}) {
  const empty = { edges: [], excluded_self: 0 };
  try {
    const res = await fetch(
      `/api/sessions/pattern-edges${qs({ min_pattern_count: opts.min_pattern_count })}`,
      { method: 'GET', headers: { Accept: 'application/json' }, cache: 'no-store' },
    );
    if (!res.ok) return empty;
    const data = await res.json();
    return data && typeof data === 'object' && Array.isArray(data.edges) ? data : empty;
  } catch {
    return empty;
  }
}
