// HealthDigest.data.js -- pure data + verdict math for the health-digest BETA
// feature (#32). NO Svelte, NO DOM, NO network. The component imports the mock
// fallbacks + the per-session health classification from here so the math is
// unit-inspectable and the .svelte file stays presentation-only.
//
// CONTRACT
//   - mockDigests() returns the realistic fallback the widget renders when the
//     live GET /api/sessions/health-digest endpoint is absent or returns an
//     empty set (fresh DB, no governed sessions). usedMockData=true then.
//   - verdict(d) classifies one digest into a PAIRED state {state, word, aria}:
//       RED   ACTION N  -- hitl_pending_count > 0
//       AMBER VARIANCE  -- latest_escalation.type === 'governance_variance_alert'
//       GREEN QUIET     -- otherwise
//     The WORD is the load-bearing channel (M4: color is never the sole signal);
//     this module supplies the literal text + the screen-reader phrasing.
//
// G2 (polarity): NO SM-own session_id appears in the mock fixture. The live
//   endpoint excludes SM-self by project_slug server-side; this module never
//   re-introduces a self row. The footer readout states the self-exclude.
// M16 (domain-agnostic): every identity is a generic placeholder rendered from
//   the digest's project_slug. NO monitored-project vocabulary / JOB-IDs / role
//   names. A real project's identity arrives from server data, never hard-coded.
//
// ASCII-only (cp1252-safe): dash rendered as "--". No smart quotes / em-dash.

/**
 * @typedef {Object} Digest
 * @property {string} session_id
 * @property {string} project_slug
 * @property {number|null} started_at
 * @property {number|null} ended_at
 * @property {number} uptime_seconds
 * @property {number} decision_count
 * @property {{action:string,confidence:number,agent_id:string,timestamp:number}|null} latest_decision
 * @property {number} active_agent_count
 * @property {number} active_job_count
 * @property {number} hitl_pending_count
 * @property {string} hitl_mode
 * @property {{type:string,severity:string,timestamp:number}|null} latest_escalation
 */

/**
 * A fixed reference "now" (epoch seconds) so the mock uptimes / ages render
 * deterministically in tests. Mirrors the approved mockup's NOW.
 */
export const MOCK_NOW = 1749635802; // 2026-06-11T09:16:42Z

/**
 * Realistic mock digest set -- the fallback when the server returns nothing.
 * 9 lanes: 1 RED (ACTION 2) + 1 AMBER (VARIANCE) + 7 GREEN (QUIET), matching
 * the operator-approved mockup. All identities are generic placeholders; NO
 * SM-own id (G2); NO monitored-project vocabulary (M16).
 * @returns {{now:number, sessions:Digest[], excluded_self:number, source:string}}
 */
export function mockDigests() {
  const N = MOCK_NOW;
  /** @type {Digest[]} */
  const sessions = [
    {
      session_id: 'sess-alpha', project_slug: 'session-alpha',
      started_at: N - 8120, ended_at: null, uptime_seconds: 8120,
      decision_count: 263,
      latest_decision: { action: 'BLOCK', confidence: 0.34, agent_id: 'agent-04', timestamp: N - 41 },
      active_agent_count: 3, active_job_count: 2,
      hitl_pending_count: 2, hitl_mode: 'SYNC',
      latest_escalation: { type: 'governance_negative_regression', severity: 'CRITICAL', timestamp: N - 38 },
    },
    {
      session_id: 'sess-bravo', project_slug: 'session-bravo',
      started_at: N - 3960, ended_at: null, uptime_seconds: 3960,
      decision_count: 141,
      latest_decision: { action: 'L3', confidence: 0.71, agent_id: 'agent-12', timestamp: N - 12 },
      active_agent_count: 2, active_job_count: 1,
      hitl_pending_count: 0, hitl_mode: 'ASYNC',
      latest_escalation: { type: 'governance_variance_alert', severity: 'WARN', timestamp: N - 58 },
    },
    {
      session_id: 'sess-charlie', project_slug: 'session-charlie',
      started_at: N - 5340, ended_at: null, uptime_seconds: 5340,
      decision_count: 418,
      latest_decision: { action: 'ALLOW', confidence: 0.94, agent_id: 'agent-21', timestamp: N - 8 },
      active_agent_count: 2, active_job_count: 1,
      hitl_pending_count: 0, hitl_mode: 'ASYNC', latest_escalation: null,
    },
    {
      session_id: 'sess-delta', project_slug: 'session-delta',
      started_at: N - 1180, ended_at: null, uptime_seconds: 1180,
      decision_count: 54,
      latest_decision: { action: 'ALLOW', confidence: 0.88, agent_id: 'agent-30', timestamp: N - 24 },
      active_agent_count: 1, active_job_count: 0,
      hitl_pending_count: 0, hitl_mode: 'ASYNC', latest_escalation: null,
    },
    {
      session_id: 'sess-echo', project_slug: 'session-echo',
      started_at: N - 7720, ended_at: null, uptime_seconds: 7720,
      decision_count: 502,
      latest_decision: { action: 'L2', confidence: 0.62, agent_id: 'agent-33', timestamp: N - 51 },
      active_agent_count: 2, active_job_count: 1,
      hitl_pending_count: 0, hitl_mode: 'ASYNC', latest_escalation: null,
    },
    {
      session_id: 'sess-foxtrot', project_slug: 'session-foxtrot',
      started_at: N - 640, ended_at: null, uptime_seconds: 640,
      decision_count: 19,
      latest_decision: { action: 'ALLOW', confidence: 0.91, agent_id: 'agent-41', timestamp: N - 3 },
      active_agent_count: 1, active_job_count: 1,
      hitl_pending_count: 0, hitl_mode: 'ASYNC', latest_escalation: null,
    },
    {
      session_id: 'sess-golf', project_slug: 'session-golf',
      started_at: N - 9990, ended_at: null, uptime_seconds: 9990,
      decision_count: 631,
      latest_decision: { action: 'ALLOW', confidence: 0.96, agent_id: 'agent-50', timestamp: N - 110 },
      active_agent_count: 2, active_job_count: 0,
      hitl_pending_count: 0, hitl_mode: 'ASYNC', latest_escalation: null,
    },
    {
      session_id: 'sess-hotel', project_slug: 'session-hotel',
      started_at: N - 2210, ended_at: null, uptime_seconds: 2210,
      decision_count: 88,
      latest_decision: { action: 'ALLOW', confidence: 0.85, agent_id: 'agent-60', timestamp: N - 17 },
      active_agent_count: 1, active_job_count: 1,
      hitl_pending_count: 0, hitl_mode: 'ASYNC', latest_escalation: null,
    },
    {
      session_id: 'sess-india', project_slug: 'session-india',
      started_at: N - 4500, ended_at: null, uptime_seconds: 4500,
      decision_count: 207,
      latest_decision: { action: 'ALLOW', confidence: 0.90, agent_id: 'agent-70', timestamp: N - 64 },
      active_agent_count: 2, active_job_count: 0,
      hitl_pending_count: 0, hitl_mode: 'ASYNC', latest_escalation: null,
    },
  ];
  return { now: N, sessions, excluded_self: 1, source: 'mock' };
}

/**
 * Coerce one raw server digest row into the canonical shape, defaulting every
 * field so the widget never reads undefined. Returns null for a non-object.
 * @param {any} raw
 * @returns {Digest|null}
 */
export function normalizeDigest(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const ld = raw.latest_decision;
  const esc = raw.latest_escalation;
  return {
    session_id: String(raw.session_id || ''),
    project_slug:
      typeof raw.project_slug === 'string' && raw.project_slug.trim()
        ? raw.project_slug.trim()
        : String(raw.session_id || ''),
    started_at: numOrNull(raw.started_at),
    ended_at: numOrNull(raw.ended_at),
    uptime_seconds: num(raw.uptime_seconds),
    decision_count: num(raw.decision_count),
    latest_decision:
      ld && typeof ld === 'object'
        ? {
            action: String(ld.action || '').toUpperCase(),
            confidence: num(ld.confidence),
            agent_id: String(ld.agent_id || ''),
            timestamp: num(ld.timestamp),
          }
        : null,
    active_agent_count: num(raw.active_agent_count),
    active_job_count: num(raw.active_job_count),
    hitl_pending_count: num(raw.hitl_pending_count),
    hitl_mode:
      typeof raw.hitl_mode === 'string' && raw.hitl_mode.trim()
        ? raw.hitl_mode.trim().toUpperCase()
        : 'ASYNC',
    latest_escalation:
      esc && typeof esc === 'object' && esc.type
        ? {
            type: String(esc.type),
            severity: String(esc.severity || ''),
            timestamp: num(esc.timestamp),
          }
        : null,
  };
}

/**
 * Normalize the whole server payload into {now, sessions, excluded_self}.
 * Returns null when there is no usable session list (caller swaps for mock).
 * @param {any} payload
 * @returns {{now:number, sessions:Digest[], excluded_self:number, source:string}|null}
 */
export function normalizePayload(payload) {
  if (!payload || typeof payload !== 'object') return null;
  const rawSessions = Array.isArray(payload.sessions) ? payload.sessions : [];
  const sessions = rawSessions
    .map(normalizeDigest)
    .filter((d) => d && d.session_id);
  if (sessions.length === 0) return null;
  return {
    now: num(payload.now) || Math.floor(Date.now() / 1000),
    sessions: /** @type {Digest[]} */ (sessions),
    excluded_self: num(payload.excluded_self),
    source: 'live',
  };
}

/** @param {any} v */ function num(v) { const n = Number(v); return Number.isFinite(n) ? n : 0; }
/** @param {any} v */ function numOrNull(v) { const n = Number(v); return Number.isFinite(n) ? n : null; }

/**
 * The PAIRED health verdict for one digest. The WORD is always present; color
 * is strictly the second channel (M4). aria carries the same verdict so a
 * screen-reader user gets the identical read.
 * @param {Digest} d
 * @returns {{state:'action'|'variance'|'quiet', word:string, aria:string}}
 */
export function verdict(d) {
  const pending = num(d && d.hitl_pending_count);
  if (pending > 0) {
    return {
      state: 'action',
      word: `ACTION ${pending}`,
      aria: `${pending} action${pending === 1 ? '' : 's'} required -- HITL pending`,
    };
  }
  if (
    d &&
    d.latest_escalation &&
    d.latest_escalation.type === 'governance_variance_alert'
  ) {
    return {
      state: 'variance',
      word: 'VARIANCE',
      aria: 'variance alert -- flagged in place, no action required yet',
    };
  }
  return { state: 'quiet', word: 'QUIET', aria: 'quiet -- no action required' };
}

/**
 * The sum of open actions across every digest -- drives the rail-header ACTIVE
 * tally (paired with the literal "ACTIVE" label by the widget; never alone).
 * @param {Digest[]} sessions
 * @returns {number}
 */
export function totalOpenActions(sessions) {
  if (!Array.isArray(sessions)) return 0;
  return sessions.reduce((acc, d) => acc + num(d && d.hitl_pending_count), 0);
}

/** @param {number} s @returns {string} a compact "Hh Mm" / "Mm" uptime. */
export function fmtUptime(s) {
  const sec = Math.max(0, num(s));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

/** @param {number} ts @param {number} now @returns {string} a human "Ns ago". */
export function ago(ts, now) {
  const s = Math.max(0, num(now) - num(ts));
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.floor(m / 60)}h ago`;
}

/**
 * The paired action-chip class for a latest-decision action (text + color).
 * @param {string} action
 * @returns {'allow'|'block'|'l4'|'l3'|'l2'}
 */
export function actionClass(action) {
  const a = String(action || '').toUpperCase();
  if (a === 'ALLOW') return 'allow';
  if (a === 'BLOCK') return 'block';
  if (a === 'L4') return 'l4';
  if (a === 'L3') return 'l3';
  return 'l2';
}
