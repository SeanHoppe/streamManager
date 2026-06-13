// StaleCleanup-data.js -- pure (no-DOM, no-fetch) helpers + mock fixture for the
// BETA feature "stale-cleanup" (#46). Kept separate from the .svelte component so
// the classification + tally math is unit-testable in isolation and the Svelte
// file stays presentation-focused.
//
// DOMAIN-AGNOSTIC (M16): every identifier in the mock fixture is a generic,
// invented governance slug -- NO monitored-project vocabulary, NO JOB-IDs, NO
// role names. Identity is data; the only literals here are the UI's own copy.
//
// POLARITY (G2/M15): the mock fixture includes one SM-self row (project_slug
// "streamManager") so the classifier's self-exclusion is exercised even on the
// mock path. A self row is NEVER eligible + NEVER counted -- it is rendered as a
// dim "Self -- never governed" badge, mirroring the server-side exclude.
//
// ASCII-only (cp1252-safe): dash is "--". No smart quotes, no em-dashes.

/** The SM-own project slug set echoed client-side (mirrors the server exclude). */
export const SELF_SLUGS = new Set(['streammanager']);

/**
 * Is this row SM-self (by project_slug or by matching the injected own
 * session id)? Self rows are structurally excluded from any archive (G2/M15).
 * @param {Record<string, any>} s
 * @param {string|null} ownSessionId
 * @returns {boolean}
 */
export function isSelfRow(s, ownSessionId) {
  if (!s) return false;
  const slug = String(s.project_slug || '').trim().toLowerCase();
  if (slug && SELF_SLUGS.has(slug)) return true;
  if (ownSessionId && s.id && String(s.id) === String(ownSessionId)) return true;
  return false;
}

/**
 * Classify one session row against the operator's "older than" window.
 *
 * States (each renders a PAIRED text+color badge -- color is never the sole
 * signal, M4/ADR-18):
 *   self      -- SM's own session; never governed, never eligible.
 *   protected -- has >=1 open HITL row; the absolute HITL gate forbids archiving.
 *   archived  -- already soft-deleted this pass (carries a RESTORE affordance).
 *   toonew    -- ended inside the window (or still live); not yet stale -- hidden.
 *   stale     -- ended past the window with no open HITL; the only archivable
 *                state. `eligible` is true ONLY here.
 *
 * @param {Record<string, any>} s          a session row (live or mock shape)
 * @param {number} windowHours             the operator-chosen "older than" window
 * @param {string|null} ownSessionId       SM-own session id (defense-in-depth)
 * @param {boolean} [archived]             true once soft-deleted this pass
 * @returns {{ state:string, eligible:boolean, reason:string }}
 */
export function classify(s, windowHours, ownSessionId, archived) {
  if (isSelfRow(s, ownSessionId)) {
    return { state: 'self', eligible: false, reason: 'SM own session -- never governed' };
  }
  if (archived) {
    return { state: 'archived', eligible: false, reason: '' };
  }
  const openHitl = Number(s && s.open_hitl) || 0;
  if (openHitl > 0) {
    return {
      state: 'protected',
      eligible: false,
      reason: 'has ' + openHitl + ' open HITL row' + (openHitl === 1 ? '' : 's') + ' -- protected',
    };
  }
  const endedHoursAgo = Number(s && s.ended_hours_ago);
  // A live session (no ended_at) reports a non-finite ended_hours_ago -> never
  // stale (a running session is never archivable).
  if (!Number.isFinite(endedHoursAgo)) {
    return { state: 'toonew', eligible: false, reason: 'still live -- not ended' };
  }
  if (endedHoursAgo < windowHours) {
    return { state: 'toonew', eligible: false, reason: 'within the window -- not yet stale' };
  }
  return { state: 'stale', eligible: true, reason: '' };
}

/**
 * The paired badge variant + literal label for a state. The label is the
 * load-bearing signal (text), the variant only the second (color) channel.
 * @param {string} state
 * @returns {{ variant:string, label:string }}
 */
export function badgeFor(state) {
  switch (state) {
    case 'stale': return { variant: 'stale', label: 'Stale' };
    case 'protected': return { variant: 'protected', label: 'Protected -- open HITL' };
    case 'archived': return { variant: 'archived', label: 'Archived' };
    case 'self': return { variant: 'self', label: 'Self -- never governed' };
    default: return { variant: 'stale', label: 'Stale' };
  }
}

/**
 * Compute the preview tally + the visible row list for a given window.
 * Rows in the `toonew` state are dropped from the visible list (mirrors the
 * server filter). Eligible rows accumulate the archive counts.
 * @param {Array<Record<string, any>>} sessions
 * @param {number} windowHours
 * @param {string|null} ownSessionId
 * @param {Record<string, boolean>} archivedMap  id -> true once soft-deleted
 * @returns {{
 *   rows: Array<{ s:Record<string, any>, state:string, eligible:boolean,
 *                 reason:string, archived:boolean }>,
 *   sessionCount:number, messageCount:number, decisionCount:number,
 *   protectedCount:number, shownCount:number }}
 */
export function preview(sessions, windowHours, ownSessionId, archivedMap) {
  const list = Array.isArray(sessions) ? sessions : [];
  const archived = archivedMap || {};
  const rows = [];
  let sessionCount = 0;
  let messageCount = 0;
  let decisionCount = 0;
  let protectedCount = 0;

  for (const s of list) {
    const isArchived = !!archived[s && s.id];
    const c = classify(s, windowHours, ownSessionId, isArchived);
    // A within-window (toonew) row is simply not shown unless already archived.
    if (c.state === 'toonew' && !isArchived) continue;
    rows.push({ s, state: c.state, eligible: c.eligible, reason: c.reason, archived: isArchived });
    if (c.eligible) {
      sessionCount += 1;
      messageCount += Number(s.message_count) || 0;
      decisionCount += Number(s.decision_count) || 0;
    }
    if (c.state === 'protected') protectedCount += 1;
  }
  return {
    rows,
    sessionCount,
    messageCount,
    decisionCount,
    protectedCount,
    shownCount: rows.length,
  };
}

/** Format an integer with thousands separators (locale-stable en-US). */
export function fmtNum(n) {
  const v = Number(n);
  return Number.isFinite(v) ? v.toLocaleString('en-US') : '0';
}

/** "ended 1d 4h ago" / "ended 6h ago" from an hours-ago offset. */
export function relWhen(hoursAgo) {
  const h = Number(hoursAgo);
  if (!Number.isFinite(h)) return 'still live';
  if (h < 1) return 'ended just now';
  if (h < 24) return 'ended ' + Math.floor(h) + 'h ago';
  const d = Math.floor(h / 24);
  const r = Math.floor(h % 24);
  return 'ended ' + d + 'd' + (r ? ' ' + r + 'h' : '') + ' ago';
}

/**
 * The realistic mock fixture served when live gov.db data is absent (fresh DB /
 * fetch error). Domain-agnostic invented slugs; includes one SM-self row (G2)
 * and one protected (open-HITL) row so every badge state is demonstrable.
 * @returns {Array<Record<string, any>>}
 */
export function mockSessions() {
  return [
    { id: 'sess-a91f', project_slug: 'alpha-svc', pid: 48213, ended_hours_ago: 28, message_count: 210, decision_count: 71, open_hitl: 0 },
    { id: 'sess-7c20', project_slug: 'beta-pipe', pid: 48990, ended_hours_ago: 33, message_count: 150, decision_count: 52, open_hitl: 0 },
    { id: 'sess-de03', project_slug: 'gamma-batch', pid: null, ended_hours_ago: 36, message_count: 52, decision_count: 15, open_hitl: 2 },
    { id: 'sess-11bd', project_slug: 'delta-stream', pid: 49120, ended_hours_ago: null, message_count: 88, decision_count: 30, open_hitl: 0 },
    { id: 'sess-self0', project_slug: 'streamManager', pid: 40001, ended_hours_ago: 50, message_count: 999, decision_count: 999, open_hitl: 0 },
  ];
}
