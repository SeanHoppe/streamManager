// EscalationTimelineCausalForensics-data.js -- pure, DOM-free, network-free leaf
// helpers + mock fixtures for the BETA feature
// "escalation-timeline-causal-forensics" (#13: Escalation Timeline -- forensic
// causal-chain visibility). No Svelte, no fetch: a deterministic module so the
// derivation math is unit-testable in isolation and the component stays lean.
//
// CONSTRAINED-ADDITIVE BUILD NOTE (vs the original proposal/mockup):
//   The approved mockup imagined two NEW tables on the FROZEN message_bus.py
//   schema (escalations + a persisted agent_id / event_type column) gated on an
//   ADR-18 amendment. This build is CONSTRAINED ADDITIVE -- NO message_bus.py
//   edit, NO ADR-18 amendment, NO new bus envelope. So the escalation cards and
//   the causal context are DERIVED at READ TIME from the EXISTING decision rows
//   (action IN {GUIDE, INTERVENE, BLOCK}); event_type is classified from the
//   decision's own action + matched_hash (no new column); agent attribution is
//   read from the EXISTING agents table / decision row attribution. The ONLY
//   persisted state is the operator's dismiss ack, which lives in an additive
//   dashboard-side `escalation_dismissals` table (CREATE TABLE IF NOT EXISTS) --
//   off the verdict hot path (M18), never a decisions/messages row write.
//
// POLARITY (G2 / M15): this module never fabricates an SM-own row. The caller
// passes already-self-excluded rows; deriveEscalations() additionally drops any
// row whose session_id matches a supplied ownSessionId as a cheap backstop, so a
// leak upstream still cannot paint a self node.
//
// M4 (paired label + color): event_type ALWAYS resolves to a literal WORD label
// here; the component pairs that word with a color swatch. Color is never the
// sole channel -- the word travels in the title / aria-label everywhere.
//
// ASCII-only (cp1252-safe): dash is "--". No smart quotes, no em-dashes.

/** The escalation actions, ascending severity. Index === severity rank-1. */
export const SEVERITY_ORDER = Object.freeze(['GUIDE', 'INTERVENE', 'BLOCK']);

/** @type {Readonly<Record<string, number>>} action severity rank lookup (1..3). */
export const ACTION_RANK = Object.freeze({ GUIDE: 1, INTERVENE: 2, BLOCK: 3 });

/** Default forensic context window: +/- 10 seconds, in milliseconds. */
export const WINDOW_MS = 10000;

/** The operator-pannable window choices (ms). Matches the approved mockup. */
export const WINDOW_CHOICES = Object.freeze([5000, 10000, 20000]);

/**
 * Event-type metadata, keyed by the DERIVED event_type. Domain-agnostic: the
 * label is a generic governance taxonomy WORD, never monitored-project vocab.
 * sev (1..3) drives the TYPOGRAPHIC weight (severity is type emphasis, not
 * chrome). `action` ties the node's color swatch to the existing --c-* token.
 * @type {Readonly<Record<string, Readonly<{ sev:number, label:string, reason:string, action:string }>>>}
 */
export const EVT_META = Object.freeze({
  'static-rule': Object.freeze({
    sev: 3, label: 'STATIC-RULE', action: 'BLOCK',
    reason: 'Static rule fired -- hard governance trigger',
  }),
  governance_negative_regression: Object.freeze({
    sev: 3, label: 'NEG-REGRESSION', action: 'INTERVENE',
    reason: 'Governance negative regression detected',
  }),
  desktop_pause: Object.freeze({
    sev: 3, label: 'DESKTOP-PAUSE', action: 'INTERVENE',
    reason: 'Desktop orchestration paused',
  }),
  governance_variance_alert: Object.freeze({
    sev: 2, label: 'VARIANCE-ALERT', action: 'GUIDE',
    reason: 'Governance variance alert',
  }),
  hitl_timeout: Object.freeze({
    sev: 2, label: 'HITL-TIMEOUT', action: 'GUIDE',
    reason: 'Async HITL row timed out',
  }),
});

/**
 * Resolve the EVT_META row for an event_type, with a safe domain-agnostic
 * fallback so an unknown type still renders a complete paired label.
 * @param {string} eventType
 * @returns {{ sev:number, label:string, reason:string, action:string }}
 */
export function evtMeta(eventType) {
  const key = typeof eventType === 'string' ? eventType.trim() : '';
  if (key && Object.prototype.hasOwnProperty.call(EVT_META, key)) {
    return EVT_META[key];
  }
  const upper = key ? key.toUpperCase() : 'ESCALATION';
  return { sev: 1, label: upper, action: 'GUIDE', reason: key || 'Escalation event' };
}

/**
 * Normalise a decision row's timestamp into epoch SECONDS (the DB stores epoch
 * seconds; a value already >= 1e12 is treated as ms and scaled down). Returns
 * null for anything non-finite.
 * @param {*} ts
 * @returns {number|null}
 */
export function toEpochSec(ts) {
  const n = Number(ts);
  if (!Number.isFinite(n)) return null;
  return n >= 1e12 ? n / 1000 : n;
}

/**
 * Extract the escalation action from a heterogeneous decision row; '' when it is
 * not one of the three escalation actions (ALLOW / SUGGEST / unknown ignored).
 * @param {*} row
 * @returns {''|'GUIDE'|'INTERVENE'|'BLOCK'}
 */
export function escalationAction(row) {
  if (!row || typeof row !== 'object') return '';
  const a = (row.action == null ? '' : String(row.action)).trim().toUpperCase();
  return ACTION_RANK[a] ? /** @type {any} */ (a) : '';
}

/**
 * DERIVE an event_type from an EXISTING decision row WITHOUT any new column.
 * The classification is a transparent read-time heuristic over fields the row
 * already carries:
 *   - BLOCK with a matched_hash  -> 'static-rule'      (a hard deny-rule fire)
 *   - BLOCK without matched_hash -> 'governance_negative_regression'
 *   - INTERVENE                  -> 'governance_negative_regression'
 *   - GUIDE                      -> 'governance_variance_alert'
 * If the row already carries an explicit event_type (e.g. a future server that
 * supplies one), that is honoured verbatim.
 * @param {Record<string, any>} row
 * @returns {string}
 */
export function deriveEventType(row) {
  if (row && typeof row.event_type === 'string' && row.event_type.trim()) {
    return row.event_type.trim();
  }
  const act = escalationAction(row);
  const hash = row && row.matched_hash != null ? String(row.matched_hash).trim() : '';
  if (act === 'BLOCK') return hash ? 'static-rule' : 'governance_negative_regression';
  if (act === 'INTERVENE') return 'governance_negative_regression';
  if (act === 'GUIDE') return 'governance_variance_alert';
  return 'governance_variance_alert';
}

/**
 * Resolve a domain-agnostic agent label FROM DATA. Preference order:
 * agent_id -> agent_profile_slug -> profile_slug -> 'agent'. Never a literal
 * monitored-project role name (M16).
 * @param {Record<string, any>} row
 * @returns {string}
 */
export function agentLabel(row) {
  if (!row || typeof row !== 'object') return 'agent';
  const cand = [row.agent_id, row.agent_profile_slug, row.profile_slug];
  for (const c of cand) {
    if (typeof c === 'string' && c.trim()) return c.trim();
  }
  return 'agent';
}

/**
 * A stable decision id for a row: id -> rid -> message_id -> '' . Used as the
 * node key + the dismiss key (the dismissals table keys on this).
 * @param {Record<string, any>} row
 * @returns {string}
 */
export function decisionIdOf(row) {
  if (!row || typeof row !== 'object') return '';
  const cand = [row.id, row.rid, row.message_id];
  for (const c of cand) {
    if (c != null && String(c).trim()) return String(c).trim();
  }
  return '';
}

/**
 * DERIVE the newest-first escalation card list from a flat decision feed.
 *
 * @param {Array<Record<string, any>>} rows decision rows (any order). Each
 *   carries at least { action, timestamp, session_id?, id?/rid?/message_id? }.
 * @param {{ ownSessionId?:string|null, dismissed?:Set<string>|Record<string,any>, limit?:number }} [opts]
 *   - ownSessionId: G2 backstop -- drop rows for this session before deriving.
 *   - dismissed: a Set (or map) of decision_ids the operator has acked; matched
 *     nodes are tagged dismissed_at (self-prune to a struck hairline).
 *   - limit: cap on cards (default 100).
 * @returns {Array<{ escalation_id:string, decision_id:string, event_type:string,
 *   triggered_at:number, proposed_action:string, confidence:number,
 *   agent_id:string, session_id:string, project_slug:string,
 *   reasoning:string, content:string, direction:string, dismissed_at:number|null }>}
 */
export function deriveEscalations(rows, opts = {}) {
  const own = (opts.ownSessionId || '').toString().trim();
  const limit = Number(opts.limit) > 0 ? Number(opts.limit) : 100;
  const dismissed = opts.dismissed instanceof Set
    ? opts.dismissed
    : new Set(
        opts.dismissed && typeof opts.dismissed === 'object'
          ? Object.keys(opts.dismissed)
          : [],
      );
  const list = Array.isArray(rows) ? rows : [];
  const out = [];
  for (const r of list) {
    if (own && r && String(r.session_id || '').trim() === own) continue;
    const act = escalationAction(r);
    if (!act) continue;
    const ts = toEpochSec(r.timestamp);
    if (ts == null) continue;
    const did = decisionIdOf(r);
    const conf = Number(r.confidence);
    out.push({
      escalation_id: did ? `esc-${did}` : `esc-${ts}`,
      decision_id: did,
      event_type: deriveEventType(r),
      triggered_at: ts,
      proposed_action: act,
      confidence: Number.isFinite(conf) ? conf : 0,
      agent_id: agentLabel(r),
      session_id: typeof r.session_id === 'string' ? r.session_id : '',
      project_slug: typeof r.project_slug === 'string' ? r.project_slug : '',
      reasoning: typeof r.reasoning === 'string' ? r.reasoning : '',
      content: typeof r.content === 'string' ? r.content : '',
      direction: typeof r.direction === 'string' ? r.direction : '',
      dismissed_at: did && dismissed.has(did) ? 'dismissed' : null,
    });
  }
  // newest-first
  out.sort((a, b) => b.triggered_at - a.triggered_at);
  return out.slice(0, limit);
}

/**
 * DERIVE the split-view causal context for one focus decision from the SAME flat
 * feed (no extra fetch needed when the feed is already loaded). Returns the 5
 * prior + 3 next decisions (by wall-clock, same session) and the distinct agents
 * active within +/- window around the focus.
 *
 * @param {Array<Record<string, any>>} rows the decision feed (any order).
 * @param {string} decisionId the focus decision_id.
 * @param {{ windowMs?:number, ownSessionId?:string|null }} [opts]
 * @returns {null | { decision_id:string, event_type:string, window_ms:number,
 *   focus:Record<string, any>, prior:Array<Record<string, any>>,
 *   next:Array<Record<string, any>>, agents_in_window:Array<Record<string, any>> }}
 */
export function deriveContext(rows, decisionId, opts = {}) {
  const own = (opts.ownSessionId || '').toString().trim();
  const windowMs = WINDOW_CHOICES.includes(Number(opts.windowMs))
    ? Number(opts.windowMs)
    : WINDOW_MS;
  const list = Array.isArray(rows) ? rows : [];
  const did = String(decisionId || '').trim();
  if (!did) return null;
  // find the focus row
  let focusRow = null;
  for (const r of list) {
    if (own && String(r.session_id || '').trim() === own) continue;
    if (decisionIdOf(r) === did) { focusRow = r; break; }
  }
  if (!focusRow) return null;
  const focusTs = toEpochSec(focusRow.timestamp);
  if (focusTs == null) return null;
  const sid = String(focusRow.session_id || '').trim();

  // same-session decisions, ascending by time
  const same = list
    .filter((r) => {
      if (own && String(r.session_id || '').trim() === own) return false;
      return String(r.session_id || '').trim() === sid && toEpochSec(r.timestamp) != null;
    })
    .sort((a, b) => toEpochSec(a.timestamp) - toEpochSec(b.timestamp));
  const focusIdx = same.findIndex((r) => decisionIdOf(r) === did);

  const compress = (r) => ({
    action: (String(r.action || '').trim().toUpperCase()) || 'ALLOW',
    confidence: Number.isFinite(Number(r.confidence)) ? Number(r.confidence) : 0,
    agent_id: agentLabel(r),
    reason: typeof r.reasoning === 'string' && r.reasoning.trim()
      ? r.reasoning.trim()
      : (typeof r.content === 'string' ? r.content.trim() : ''),
    timestamp: toEpochSec(r.timestamp),
  });

  const prior = focusIdx > 0 ? same.slice(Math.max(0, focusIdx - 5), focusIdx).map(compress) : [];
  const next = focusIdx >= 0 ? same.slice(focusIdx + 1, focusIdx + 4).map(compress) : [];

  // agents active within +/- window (distinct), FROM DATA
  const winSec = windowMs / 1000;
  const lo = focusTs - winSec;
  const hi = focusTs + winSec;
  const seen = new Map();
  for (const r of same) {
    const ts = toEpochSec(r.timestamp);
    if (ts == null || ts < lo || ts > hi) continue;
    const ag = agentLabel(r);
    const prev = seen.get(ag) || { agent_id: ag, active_from: ts, active_to: ts };
    prev.active_from = Math.min(prev.active_from, ts);
    prev.active_to = Math.max(prev.active_to, ts);
    seen.set(ag, prev);
  }

  return {
    decision_id: did,
    event_type: deriveEventType(focusRow),
    window_ms: windowMs,
    focus: {
      action: (String(focusRow.action || '').trim().toUpperCase()) || 'BLOCK',
      confidence: Number.isFinite(Number(focusRow.confidence)) ? Number(focusRow.confidence) : 0,
      reasoning: typeof focusRow.reasoning === 'string' ? focusRow.reasoning : '',
      content: typeof focusRow.content === 'string' ? focusRow.content : '',
      direction: typeof focusRow.direction === 'string' ? focusRow.direction : '',
      agent_id: agentLabel(focusRow),
      timestamp: focusTs,
    },
    prior,
    next,
    agents_in_window: Array.from(seen.values()),
  };
}

/** Zero-pad to 2 digits. @param {number} n @returns {string} */
function pad2(n) {
  return n < 10 ? `0${n}` : String(n);
}

/** Local HH:MM:SS from epoch SECONDS. @param {number} sec @returns {string} */
export function hhmmss(sec) {
  const d = new Date(Number(sec) * 1000);
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
}

/** Whole-number percent from a 0..1 fraction. @param {number} x @returns {string} */
export function pct(x) {
  const n = Number(x);
  return `${Math.round((Number.isFinite(n) ? n : 0) * 100)}%`;
}

/** Map an action to its existing --c-* token (var() string). @param {string} act */
export function actionColorVar(act) {
  const a = String(act || '').trim().toUpperCase();
  if (a === 'ALLOW') return 'var(--c-allow, #22c55e)';
  if (a === 'GUIDE') return 'var(--c-guide, #eab308)';
  if (a === 'INTERVENE') return 'var(--c-intervene, #f97316)';
  if (a === 'BLOCK') return 'var(--c-block, #ef4444)';
  return 'var(--c-intervene, #f97316)';
}

/**
 * Realistic MOCK escalation feed for when live gov.db carries no escalation rows
 * (the live DB is frequently ALLOW-only). Mirrors the approved mockup fixture: a
 * static-rule BLOCK, a negative-regression INTERVENE, and a variance-alert GUIDE
 * (the last already dismissed), each surrounded by a representative lead-up +
 * aftermath so every node opens to a real forensic transcript.
 *
 * Rows carry a non-SM session_id + project_slug so they survive self-exclude.
 * The caller sets usedMockData=true whenever it falls back to this fixture.
 * @param {{ now?:number }} [opts]
 * @returns {{ rows:Array<Record<string, any>>, focusIds:string[], dismissedIds:string[] }}
 */
export function mockFeed(opts = {}) {
  const now = Number.isFinite(opts.now) ? Number(opts.now) : Date.now();
  // epoch SECONDS, anchored so the newest escalation is ~2 min before now.
  const base = Math.floor(now / 1000) - 120;
  const sid = 'mock-governed-session';
  const slug = 'web-checkout';
  /** @type {Array<Record<string, any>>} */
  const rows = [];
  const mk = (id, off, action, agent, reasoning, content, matched) =>
    rows.push({
      id,
      message_id: `m-${id}`,
      action,
      confidence: action === 'BLOCK' ? 0.97 : action === 'INTERVENE' ? 0.71 : action === 'GUIDE' ? 0.64 : 0.9,
      reasoning,
      content,
      matched_hash: matched || '',
      timestamp: base + off,
      session_id: sid,
      project_slug: slug,
      direction: 'agent_to_user',
      agent_id: agent,
      profile_slug: agent,
    });

  // --- focus C: variance-alert GUIDE (oldest, already dismissed) ---
  mk('d-8694', -580, 'ALLOW', 'executor', 'fetch attempt 1 ok', 'fetch https://api/x', '');
  mk('d-8696', -578, 'ALLOW', 'executor', 'fetch attempt 3 retry', 'fetch https://api/x', '');
  mk('d-8698', -576, 'GUIDE', 'executor', 'noisy retry loop noted', 'retry network fetch (attempt 5)', '');
  mk('d-8700', -574, 'GUIDE', 'executor', 'variance rising', 'retry network fetch (attempt 6)', '');
  mk('d-8702', -572, 'GUIDE', 'executor', 'Decision variance exceeded the rolling band for this agent profile', 'retry network fetch (attempt 7)', '');
  mk('d-8704', -570, 'ALLOW', 'executor', 'added a backoff delay', 'sleep 2', '');
  mk('d-8706', -567, 'ALLOW', 'executor', 'fetch succeeded, loop exited', 'fetch https://api/x', '');
  mk('d-8708', -564, 'ALLOW', 'planner', 'recorded the recovery', 'note: recovered', '');

  // --- focus B: negative-regression INTERVENE ---
  mk('d-8782', -310, 'ALLOW', 'planner', 'drafted migration plan', 'plan: migration', '');
  mk('d-8784', -308, 'GUIDE', 'planner', 'flagged unscoped index drop', 'review: drop_legacy_index', '');
  mk('d-8786', -306, 'GUIDE', 'executor', 'requested a dry-run first', 'dry-run migration', '');
  mk('d-8788', -304, 'GUIDE', 'planner', 'confidence trending down', 'reconsider migration', '');
  mk('d-8790', -300, 'INTERVENE', 'planner', 'Confidence regressed below band floor across 3 consecutive decisions', 'apply migration drop_legacy_index on primary', '');
  mk('d-8792', -296, 'ALLOW', 'planner', 'added a reversible guard clause', 'wrap migration in transaction', '');
  mk('d-8794', -293, 'ALLOW', 'executor', 'ran the dry-run, no rows affected', 'dry-run ok', '');
  mk('d-8796', -290, 'GUIDE', 'planner', 'recommended a backup snapshot', 'snapshot before migrate', '');

  // --- focus A: static-rule BLOCK (newest, undismissed) ---
  mk('d-8833', -68, 'ALLOW', 'executor', 'read-only ls', 'ls ./build', '');
  mk('d-8835', -66, 'GUIDE', 'executor', 'ambiguous path arg', 'cd ./build', '');
  mk('d-8837', -64, 'ALLOW', 'planner', 'plan step recorded', 'plan: clean build dir', '');
  mk('d-8839', -62, 'INTERVENE', 'executor', 'escalating privilege', 'sudo rm tmpfile', '');
  mk('d-8840', -61, 'ALLOW', 'executor', 'cd build', 'cd build', '');
  mk('d-8841', -60, 'BLOCK', 'executor', 'Destructive shell command matched static deny rule', 'rm -rf ./build --no-preserve-root', 'deny:rm-rf-root');
  mk('d-8843', -56, 'ALLOW', 'executor', 'agent reverted to safe rm of single file', 'rm ./build/stale.o', '');
  mk('d-8845', -53, 'ALLOW', 'planner', 'replanned cleanup step', 'plan: targeted cleanup', '');
  mk('d-8847', -50, 'ALLOW', 'executor', 'git status', 'git status', '');

  return {
    rows,
    focusIds: ['d-8841', 'd-8790', 'd-8702'],
    dismissedIds: ['d-8702'],
  };
}
