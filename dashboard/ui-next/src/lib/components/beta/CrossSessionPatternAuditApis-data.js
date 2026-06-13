// CrossSessionPatternAuditApis-data.js -- pure (no-DOM, no-fetch) helpers + mock
// fixtures for the BETA feature "cross-session-pattern-audit-apis" (#11). Kept
// separate from the .svelte component so the scope / probe / format math is
// unit-testable in isolation and the Svelte file stays presentation-focused.
//
// WHAT THE FEATURE READS (the two additive endpoints this feeds):
//   GET /api/patterns/cross-session/{session_id}/hydrated -> the hydrated-rule
//       rows scoping the AUDIT rail to ONE governed (non-SM) session.
//   GET /api/patterns/{hash}/would-apply?message_content=... -> the read-only
//       "would this fire?" applicability probe (post-hoc; emits NO verdict).
//
// DOMAIN-AGNOSTIC (M16): every identifier in the mock fixtures is a generic,
// invented governance slug -- NO monitored-project vocabulary, NO JOB-IDs, NO
// role names. Identity is data; the only literals here are the UI's own copy.
//
// POLARITY (G2/M15): the SM-self scope is NEVER a populated scope -- the mock
// scope list carries one DISABLED self entry so the picker exercises the
// suppression even on the mock path, mirroring the server-side 404-on-self.
//
// ASCII-only (cp1252-safe): dash is "--". No smart quotes, no em-dashes.

/** The SM-own project slug set echoed client-side (mirrors the server exclude). */
export const SELF_SLUGS = new Set(['streammanager']);

/** Below this cosine the rule "would not fire" (mirrors server SIMILARITY_THRESHOLD). */
export const SIMILARITY_THRESHOLD = 0.72;

/** decay_status -> the LITERAL paired text label (M4: color is never the sole signal). */
export const DECAY_WORD = { stable: 'STABLE', decaying: 'DECAYING', unknown: 'UNKNOWN' };

/**
 * Is this session row SM-self (by project_slug or by matching the injected own
 * session id)? A self scope is NEVER selectable / NEVER audited (G2/M15).
 * @param {Record<string, any>} s
 * @param {string|null} ownSessionId
 * @returns {boolean}
 */
export function isSelfScope(s, ownSessionId) {
  if (!s) return false;
  const slug = String(s.project_slug || '').trim().toLowerCase();
  if (slug && SELF_SLUGS.has(slug)) return true;
  if (ownSessionId && s.id && String(s.id) === String(ownSessionId)) return true;
  return false;
}

/**
 * The mock scope list -- two governed (non-SM) sessions plus one DISABLED
 * SM-self entry so the polarity suppression is visible on the mock path.
 * Each governed entry carries its hydrated-rule count for the chip tally.
 * @returns {Array<{id:string, project_slug:string, hydrated_count:number, self:boolean}>}
 */
export function mockScopes() {
  return [
    { id: 'sess-fresh-now-07', project_slug: 'governed-alpha', hydrated_count: 4, self: false },
    { id: 'sess-fresh-now-12', project_slug: 'governed-beta', hydrated_count: 2, self: false },
    // SM-self: present but DISABLED -- audit suppressed (G2). Never populated.
    { id: 'sess-self-sm', project_slug: 'streamManager', hydrated_count: 0, self: true },
  ];
}

/**
 * Mock hydrated-rule rows for a scoped session id. Mirrors the server shape of
 * GET /api/patterns/cross-session/{session_id}/hydrated:
 *   { pattern_hash, level, last_seen_session_id, last_seen_ts, occurrence_count,
 *     success_rate, matched_decision_count_this_session, sourced_from, decay_status }
 * An SM-self / unknown scope yields [] (the audit is suppressed for self).
 * @param {string} sessionId
 * @returns {Array<Record<string, any>>}
 */
export function mockHydrated(sessionId) {
  /** @type {Record<string, Array<Record<string, any>>>} */
  const byScope = {
    'sess-fresh-now-07': [
      { pattern_hash: 'a1b2c3d4e5f60718', level: 2, last_seen_session_id: 'sess-prior-soak-01', last_seen_ts: 1749600000, occurrence_count: 17, success_rate: 0.88, matched_decision_count_this_session: 4, sourced_from: 'cross_session_hydrator', decay_status: 'stable' },
      { pattern_hash: '9f8e7d6c5b4a3021', level: 1, last_seen_session_id: 'sess-prior-soak-01', last_seen_ts: 1749590000, occurrence_count: 6, success_rate: 0.5, matched_decision_count_this_session: 0, sourced_from: 'cross_session_hydrator', decay_status: 'decaying' },
      { pattern_hash: '1122334455667788', level: 3, last_seen_session_id: 'sess-prior-soak-02', last_seen_ts: 1749610000, occurrence_count: 31, success_rate: 0.97, matched_decision_count_this_session: 9, sourced_from: 'cross_session_hydrator', decay_status: 'stable' },
      { pattern_hash: 'aabbccddeeff0011', level: 1, last_seen_session_id: null, last_seen_ts: 1749580000, occurrence_count: 3, success_rate: 0.33, matched_decision_count_this_session: 1, sourced_from: 'unknown', decay_status: 'unknown' },
    ],
    'sess-fresh-now-12': [
      { pattern_hash: '1122334455667788', level: 3, last_seen_session_id: 'sess-prior-soak-02', last_seen_ts: 1749610000, occurrence_count: 31, success_rate: 0.97, matched_decision_count_this_session: 2, sourced_from: 'cross_session_hydrator', decay_status: 'stable' },
      { pattern_hash: '77665544332211ff', level: 2, last_seen_session_id: 'sess-prior-soak-03', last_seen_ts: 1749605000, occurrence_count: 12, success_rate: 0.75, matched_decision_count_this_session: 0, sourced_from: 'cross_session_hydrator', decay_status: 'decaying' },
    ],
  };
  return byScope[sessionId] ? byScope[sessionId].slice() : [];
}

/**
 * Deterministic mock of GET /api/patterns/{hash}/would-apply. Mirrors the server
 * post-hoc contract: longer text clears SIMILARITY_THRESHOLD, short text does
 * not. NEVER a verdict -- only an applicability score + rationale.
 * @param {string} text   the candidate message content
 * @returns {{applies:boolean, match_confidence:number, sourced_from:string[], rationale:string}}
 */
export function mockWouldApply(text) {
  const longish = String(text || '').trim().length > 20;
  const conf = longish ? 0.81 : 0.41;
  return {
    applies: longish,
    match_confidence: conf,
    sourced_from: ['graph_match'],
    rationale: longish
      ? 'cosine 0.81 >= threshold 0.72'
      : 'cosine 0.41 below threshold 0.72',
  };
}

/**
 * The degraded shape returned on a 500ms timeout / engine error. The probe NEVER
 * throws to the operator -- it returns this safe, explicit "unavailable" shape.
 * @returns {{applies:boolean, match_confidence:number, sourced_from:string[], rationale:string}}
 */
export function unavailableShape() {
  return {
    applies: false,
    match_confidence: 0.0,
    sourced_from: [],
    rationale: 'matching engine unavailable',
  };
}

/**
 * Classify a would-apply result into one of three PAIRED (text + color) verdict
 * kinds. The literal text label is load-bearing (M4) -- color is never alone.
 * @param {{applies:boolean, match_confidence:number, rationale:string}} res
 * @returns {{kind:'fire'|'nofire'|'degraded', label:string}}
 */
export function classifyProbe(res) {
  const r = res || {};
  if (r.rationale === 'matching engine unavailable') {
    return { kind: 'degraded', label: 'ENGINE UNAVAILABLE' };
  }
  const conf = Number(r.match_confidence) || 0;
  const fire = !!r.applies && conf >= SIMILARITY_THRESHOLD;
  return fire
    ? { kind: 'fire', label: 'WOULD FIRE -- conf ' + conf.toFixed(2) }
    : { kind: 'nofire', label: 'WOULD NOT FIRE -- conf ' + conf.toFixed(2) };
}

// ---------------------------------------------------------------------------
// Resilient transport wrappers. Self-contained so the component works BEFORE
// the canonical api.js helpers (returned as build DATA) are wired in, and
// degrades to {} / [] on ANY error so the component falls back to mock (never
// reads as live when the endpoint is absent / the server is down). Mirrors the
// other beta features' defensive read idiom (getCoverageBands / getStaleSessions).
// ---------------------------------------------------------------------------

/**
 * GET /api/patterns/cross-session/{session_id}/hydrated -- hydrated-rule rows
 * scoping the AUDIT rail to one governed (non-SM) session. Returns
 * { session_id, count, mock, rows } or a safe empty shape on any error / 404.
 * @param {string} sessionId
 * @returns {Promise<{session_id:string, count:number, mock:boolean, rows:Array<Record<string, any>>}>}
 */
export async function fetchHydrated(sessionId) {
  const empty = { session_id: String(sessionId || ''), count: 0, mock: false, rows: [] };
  if (!sessionId) return empty;
  try {
    const res = await fetch(
      `/api/patterns/cross-session/${encodeURIComponent(String(sessionId))}/hydrated`,
      { headers: { Accept: 'application/json' }, cache: 'no-store' },
    );
    if (!res.ok) return empty;
    const data = await res.json();
    return data && typeof data === 'object' && Array.isArray(data.rows) ? data : empty;
  } catch {
    return empty;
  }
}

/**
 * GET /api/patterns/{hash}/would-apply?message_content=... -- the read-only
 * applicability probe. Returns the {applies, match_confidence, sourced_from,
 * rationale} shape; degrades to unavailableShape() on any error / non-2xx so the
 * probe NEVER throws to the operator. A client AbortController caps it at 500ms.
 * @param {string} hash
 * @param {string} text
 * @returns {Promise<{applies:boolean, match_confidence:number, sourced_from:string[], rationale:string}>}
 */
export async function fetchWouldApply(hash, text) {
  if (!hash) return unavailableShape();
  let timer = null;
  const ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
  try {
    if (ctrl) timer = setTimeout(() => ctrl.abort(), 500);
    const url = `/api/patterns/${encodeURIComponent(String(hash))}/would-apply` +
      `?message_content=${encodeURIComponent(String(text || ''))}`;
    const res = await fetch(url, {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      signal: ctrl ? ctrl.signal : undefined,
    });
    if (!res.ok) return unavailableShape();
    const data = await res.json();
    if (!data || typeof data !== 'object' || typeof data.applies !== 'boolean') {
      return unavailableShape();
    }
    return data;
  } catch {
    return unavailableShape();
  } finally {
    if (timer) clearTimeout(timer);
  }
}

/** Short, stable 8-char display of an opaque hash (full value goes in title/aria). */
export function shortHash(hash) {
  return String(hash || '').slice(0, 8) || '--------';
}

/**
 * Deterministic UTC timestamp label (ASCII-only). Tolerant of epoch seconds /
 * ms / ISO strings; falls back to "--" rather than throwing.
 * @param {number|string|null} ts
 * @returns {string}
 */
export function tsLabel(ts) {
  if (ts == null || ts === '') return '--';
  const n = Number(ts);
  let d = null;
  if (Number.isFinite(n)) {
    d = new Date(n < 1e12 ? n * 1000 : n);
  } else {
    const parsed = Date.parse(String(ts));
    if (!Number.isNaN(parsed)) d = new Date(parsed);
  }
  if (!d || Number.isNaN(d.getTime())) return String(ts);
  const mo = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getUTCMonth()];
  const p = (x) => (x < 10 ? '0' : '') + x;
  return mo + ' ' + d.getUTCDate() + ', ' + d.getUTCFullYear() +
    ' -- ' + p(d.getUTCHours()) + ':' + p(d.getUTCMinutes()) + ' UTC';
}
