// AwayMode-data.js -- pure, framework-free data helpers for the away-mode BETA
// feature (#4: Away / Calm Mode + Activity Summary Replay). Leaf module: imports
// the canonical M2 escalation table (lib/escalation.js) and nothing else, so the
// foreground/escalation classification lives in exactly ONE place (never a second
// hand-maintained allow-list here).
//
// DOMAIN-AGNOSTIC (M16): this module hard-codes NO governed-target vocabulary. It
// classifies an escalation generically -- by a row's `action` being a hard verdict
// (BLOCK / INTERVENE) OR by an `escalation_type` / `event_type` that the canonical
// allow-list marks foreground-eligible. It NEVER string-matches a monitored-project
// envelope kind, JOB id, or role name. Identity (session_id / project_slug /
// profile_slug) is carried through verbatim from the live data.
//
// POLARITY (G2): this module does no querying. It only shapes rows the component
// already received from the shared stores (decisionsStore / escalationStore /
// agentsStore), every one of which is self-excluded (project_slug NOT IN
// {streamManager} AND session_id != self) BEFORE it ever reaches here. There is no
// path in this file that could surface an SM-self row.
//
// ASCII-only (cp1252-safe): dash is "--". No smart quotes, no em-dashes.

import { describe } from '../../escalation.js';

// Hard-verdict actions that are ALWAYS escalation-worthy in the Activity Summary,
// independent of any named-event allow-list. These are generic governance verdicts,
// not envelope kinds -- BLOCK and INTERVENE are the two actions that demand operator
// attention. Kept here as a tiny frozen set so the classifier reads as a table.
export const HARD_VERDICT_ACTIONS = Object.freeze(new Set(['BLOCK', 'INTERVENE']));

/**
 * Is this decision row an escalation worth surfacing on return?
 * Generic + domain-agnostic: true iff the row's action is a hard verdict
 * (BLOCK / INTERVENE) OR the canonical M2 table marks its trigger
 * foreground-eligible (desktop_pause / governance_negative_regression /
 * static-rule). NEVER matches a hardcoded envelope kind name.
 * @param {Record<string, any>} row
 * @returns {boolean}
 */
export function isEscalationRow(row) {
  if (!row || typeof row !== 'object') return false;
  const action = (row.action || '').toString().trim().toUpperCase();
  if (HARD_VERDICT_ACTIONS.has(action)) return true;
  // A row may carry an explicit escalation_type / event_type; defer the
  // foreground decision to the ONE canonical table (lib/escalation.js).
  const trigger = row.escalation_type || row.event_type || row.trigger || '';
  if (!trigger) return false;
  const d = describe(trigger);
  return !!(d && d.foreground);
}

/**
 * Normalize a heterogeneous buffered entry (a decision row OR an escalationStore
 * entry {rule, sessionId, ts}) into the timeline shape the overlay renders:
 *   { ts:number, tsLabel:string, label:string, reason:string, kind:'amber'|'slate' }
 * `label` is the literal paired text state (M4); `kind` is a secondary colour cue
 * only. Returns null for anything that is not an escalation.
 * @param {Record<string, any>} entry
 * @returns {null | { ts:number, tsLabel:string, label:string, reason:string, kind:'amber'|'slate' }}
 */
export function toTimelineItem(entry) {
  if (!entry || typeof entry !== 'object') return null;

  // Shape A: an escalationStore entry already classified by sse.js (the canonical
  // path) -- { rule:{label,reason?}, sessionId, ts }.
  if (entry.rule && typeof entry.rule === 'object') {
    const ts = Number(entry.ts) || Date.now();
    const label = (entry.rule.label || 'ESCALATION').toString();
    return {
      ts,
      tsLabel: fmtClock(ts),
      label,
      reason: entry.rule.reason || `${label} -- foreground escalation`,
      // desktop_pause / neg-regression read amber (PAUSE/NOTICE); a static-rule
      // BLOCK reads slate-red. Rank 1 in the allow-list => the harder BLOCK band.
      kind: entry.rule.rank === 1 ? 'slate' : 'amber',
    };
  }

  // Shape B: a raw decision row buffered from the feed. Only hard verdicts /
  // allow-listed triggers become timeline items.
  if (!isEscalationRow(entry)) return null;
  const ts = toMs(entry.timestamp) || Date.now();
  const action = (entry.action || '').toString().trim().toUpperCase();
  const trig = entry.escalation_type || entry.event_type || entry.trigger || '';
  let label = action || 'ESCALATION';
  let reason = '';
  if (trig) {
    const d = describe(trig);
    if (d) {
      label = (trig.toString().replace(/_/g, ' ')).toUpperCase();
      reason = d.reason;
    }
  }
  if (action === 'BLOCK') reason = reason || 'Hard BLOCK verdict during away window';
  else if (action === 'INTERVENE') reason = reason || 'INTERVENE verdict during away window';
  return {
    ts,
    tsLabel: fmtClock(ts),
    label,
    reason: reason || `${label} during away window`,
    kind: action === 'BLOCK' ? 'slate' : 'amber',
  };
}

/**
 * Build the full Activity Summary from the buffered material the component
 * collected while AWAY. Pure shaping -- no side effects, no I/O.
 *
 * @param {{
 *   bufferedDecisions?: Array<Record<string, any>>,
 *   bufferedEscalations?: Array<Record<string, any>>,
 *   agentsBefore?: Array<Record<string, any>>,
 *   agentsAfter?: Array<Record<string, any>>,
 *   hitlQueuedCount?: number,
 *   awayStart?: number|null,
 *   awayEnd?: number|null,
 *   sessionId?: string|null,
 *   projectSlug?: string|null,
 * }} input
 * @returns {{
 *   timeline: Array<{ts:number,tsLabel:string,label:string,reason:string,kind:string}>,
 *   newAgents: Array<{ profile_slug:string, first_seen_label:string }>,
 *   hitlQueuedCount: number,
 *   bufferedEventCount: number,
 *   awayStartLabel: string,
 *   awayEndLabel: string,
 *   awayMinutes: number,
 *   sessionId: string|null,
 *   projectSlug: string|null,
 *   hasEscalation: boolean,
 * }}
 */
export function buildSummary(input) {
  const inp = input || {};
  const decisions = Array.isArray(inp.bufferedDecisions) ? inp.bufferedDecisions : [];
  const escEntries = Array.isArray(inp.bufferedEscalations) ? inp.bufferedEscalations : [];

  // Timeline: the canonical escalationStore entries PLUS any hard-verdict decision
  // rows the feed buffered, de-duped by (ts,label), most-recent first.
  const items = [];
  for (const e of escEntries) {
    const it = toTimelineItem(e);
    if (it) items.push(it);
  }
  for (const d of decisions) {
    const it = toTimelineItem(d);
    if (it) items.push(it);
  }
  const seen = new Set();
  const timeline = [];
  for (const it of items) {
    const key = `${it.ts}|${it.label}`;
    if (seen.has(key)) continue;
    seen.add(key);
    timeline.push(it);
  }
  timeline.sort((a, b) => b.ts - a.ts);

  // New agents: profile_slugs present in agentsAfter that were absent in
  // agentsBefore (the roster the operator last saw before going AWAY). Generic
  // identity from data (M16) -- profile_slug verbatim, never a hardcoded role.
  const beforeSlugs = new Set(
    (Array.isArray(inp.agentsBefore) ? inp.agentsBefore : [])
      .map((a) => agentSlug(a))
      .filter(Boolean),
  );
  const newAgents = [];
  const seenSlug = new Set();
  for (const a of (Array.isArray(inp.agentsAfter) ? inp.agentsAfter : [])) {
    const slug = agentSlug(a);
    if (!slug || beforeSlugs.has(slug) || seenSlug.has(slug)) continue;
    seenSlug.add(slug);
    const firstSeen = toMs(a.first_seen) || toMs(a.last_seen);
    newAgents.push({
      profile_slug: slug,
      first_seen_label: firstSeen ? fmtClock(firstSeen) : 'new',
    });
  }

  const awayStart = Number(inp.awayStart) || null;
  const awayEnd = Number(inp.awayEnd) || Date.now();
  const awayMinutes = awayStart ? Math.max(0, Math.round((awayEnd - awayStart) / 60000)) : 0;

  return {
    timeline,
    newAgents,
    hitlQueuedCount: Math.max(0, Number(inp.hitlQueuedCount) || 0),
    bufferedEventCount: decisions.length,
    awayStartLabel: awayStart ? fmtClock(awayStart) : '--:--',
    awayEndLabel: fmtClock(awayEnd),
    awayMinutes,
    sessionId: inp.sessionId || null,
    projectSlug: inp.projectSlug || null,
    hasEscalation: timeline.length > 0,
  };
}

/**
 * Realistic, domain-agnostic mock summary for when live gov.db data is absent
 * (set usedMockData=true at the call site). Mirrors the approved mockup's shape
 * so the feature is testable headless. ASCII-only, generic vocabulary only.
 * @param {number} [nowMs]
 * @returns {ReturnType<typeof buildSummary>}
 */
export function mockSummary(nowMs) {
  const end = Number(nowMs) || Date.now();
  const start = end - 42 * 60000; // a 42-minute away window
  return buildSummary({
    awayStart: start,
    awayEnd: end,
    sessionId: 'sess-7c2f',
    projectSlug: 'alpha-proj',
    hitlQueuedCount: 4,
    bufferedDecisions: [
      { action: 'BLOCK', timestamp: msToSec(start + 29 * 60000), session_id: 'sess-7c2f',
        escalation_type: 'static-rule' },
    ],
    bufferedEscalations: [
      { rule: { label: 'PAUSE', reason: 'Desktop orchestration paused -- operator attention required', rank: 0 },
        sessionId: 'sess-7c2f', ts: start + 6 * 60000 },
    ],
    agentsBefore: [
      { profile_slug: 'planner', first_seen: msToSec(start - 3 * 3600000) },
    ],
    agentsAfter: [
      { profile_slug: 'planner', first_seen: msToSec(start - 3 * 3600000) },
      { profile_slug: 'reviewer', first_seen: msToSec(start + 13 * 60000) },
      { profile_slug: 'builder', first_seen: msToSec(start + 21 * 60000) },
    ],
  });
}

// ---------------------------------------------------------------------------
// Small pure utilities.
// ---------------------------------------------------------------------------

/** @param {Record<string, any>} a @returns {string} */
function agentSlug(a) {
  if (!a || typeof a !== 'object') return '';
  return (a.profile_slug || a.agent_profile_slug || a.slug || '').toString().trim();
}

/**
 * Coerce a timestamp (epoch seconds OR ms OR ISO string) to ms. Returns 0 when
 * unparseable. The dashboard rows carry epoch seconds; the escalationStore
 * carries Date.now() ms; ISO strings appear in mock data -- handle all three.
 * @param {*} t
 * @returns {number}
 */
function toMs(t) {
  if (t == null) return 0;
  if (typeof t === 'number' && Number.isFinite(t)) {
    // < 1e12 => almost certainly epoch SECONDS, not ms.
    return t < 1e12 ? Math.round(t * 1000) : Math.round(t);
  }
  const n = Date.parse(String(t));
  return Number.isFinite(n) ? n : 0;
}

/** @param {number} ms @returns {number} epoch seconds (for mock row timestamps). */
function msToSec(ms) { return Math.round(ms / 1000); }

/**
 * Format an epoch-ms instant as a stable HH:MM:SS clock label. ASCII-only.
 * @param {number} ms
 * @returns {string}
 */
export function fmtClock(ms) {
  const d = new Date(Number(ms) || Date.now());
  const p = (n) => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
