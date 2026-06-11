// SessionCheckpointVersioning-data.js -- pure (no-DOM, no-fetch) helpers + mock
// fixtures for the BETA feature "session-checkpoint-versioning" (#26). Kept
// separate from the .svelte component so the lane-eligibility, self-exclude,
// ordering, and delta-classification math is unit-testable in isolation and the
// Svelte file stays presentation-focused.
//
// WHAT IT SUPPORTS
//   A right-side DRAWER opened from a quiet "ckpt N" affordance pinned to each
//   GOVERNED (non-SM) session lane. Inside: a vertical TIMELINE of named digest
//   snapshots (newest first) + a pre-computed COMPARE delta manifest between any
//   two. Every numeric delta is computed SERVER-SIDE (or in the mock here); the
//   component NEVER computes drift client-side -- it only renders the manifest.
//
// POLARITY (G2/M15): the lane affordance is STRUCTURALLY ABSENT on any SM-slug
// lane (or the injected own-session id) -- not a disabled control. isSelfLane()
// is the single classifier; the mock session set includes one SM-self row so
// the structural-absence path is exercised even on the mock path. A checkpoint
// POST against an SM-self id is refused server-side (HTTP 400, written:false).
//
// DOMAIN-AGNOSTIC (M16): every identifier in the mock fixtures is a generic,
// invented governance slug -- NO monitored-project vocabulary, NO JOB-IDs, NO
// role names. Identity is data; the only literals here are the UI's own copy.
//
// ASCII-only (cp1252-safe): dash is "--". No smart quotes, no em-dashes.

/** The SM-own project slug set echoed client-side (mirrors the server exclude). */
export const SELF_SLUGS = new Set(['streammanager']);

/**
 * Is this session lane SM-self (by project_slug or by the injected own session
 * id)? Self lanes NEVER mount the checkpoint affordance (G2/M15). This is the
 * single structural gate -- there is no "disabled" affordance for self.
 * @param {Record<string, any>} s
 * @param {string|null} ownSessionId
 * @returns {boolean}
 */
export function isSelfLane(s, ownSessionId) {
  if (!s) return false;
  const slug = String(s.project_slug || '').trim().toLowerCase();
  if (slug && SELF_SLUGS.has(slug)) return true;
  if (ownSessionId && s.id && String(s.id) === String(ownSessionId)) return true;
  return false;
}

/**
 * Short, glance-readable session identity from data (M16): prefer the
 * project_slug, fall back to a truncated id. Never invents a target name.
 * @param {Record<string, any>} s
 * @returns {string}
 */
export function laneName(s) {
  if (!s) return '';
  const slug = typeof s.project_slug === 'string' && s.project_slug.trim() ? s.project_slug.trim() : '';
  if (slug) return slug;
  return shortId(s.id);
}

/** Truncate a long session id to a glance token (keeps head + tail). */
export function shortId(id) {
  const s = String(id == null ? '' : id);
  return s.length <= 12 ? s : `${s.slice(0, 7)}..${s.slice(-3)}`;
}

/**
 * Order a checkpoint list NEWEST FIRST by timestamp (ts is an ISO-ish string or
 * epoch ms; both compare lexicographically-safe after Number coercion when
 * numeric). Pure -- returns a new array, never mutates input.
 * @param {Array<Record<string, any>>} checkpoints
 * @returns {Array<Record<string, any>>}
 */
export function newestFirst(checkpoints) {
  const list = Array.isArray(checkpoints) ? checkpoints.slice() : [];
  return list.sort((a, b) => tsKey(b) - tsKey(a));
}

/** Sortable numeric key for a checkpoint timestamp. */
function tsKey(c) {
  const t = c && (c.timestamp != null ? c.timestamp : c.ts);
  if (typeof t === 'number' && Number.isFinite(t)) return t;
  const parsed = Date.parse(String(t || ''));
  return Number.isFinite(parsed) ? parsed : 0;
}

/**
 * Build the per-node view model for the timeline (newest-first). Each node
 * carries an accessible label string + an "age band" used purely for the
 * recede-in-opacity asymmetry in the mockup (newest = node--newest).
 * @param {Array<Record<string, any>>} checkpoints
 * @returns {Array<Record<string, any>>}
 */
export function timelineView(checkpoints) {
  const ordered = newestFirst(checkpoints);
  return ordered.map((c, i) => ({
    id: String(c.checkpoint_id || c.id || `ck-${i}`),
    name: String(c.name || 'manual mark'),
    ts: String(c.timestamp || c.ts || ''),
    decisions: numOr(c.decision_count_at_checkpoint != null ? c.decision_count_at_checkpoint : c.decisions, 0),
    messages: numOr(c.message_count_at_checkpoint != null ? c.message_count_at_checkpoint : c.messages, 0),
    confidence: confOr(c.confidence),
    openHitl: numOr(c.open_hitl, 0),
    patterns: numOr(c.patterns, 0),
    escalations: numOr(c.escalations, 0),
    ageBand: i === 0 ? 'newest' : i === 1 ? 'age1' : 'age2',
    aria: nodeAria(c, i === 0),
  }));
}

function nodeAria(c, newest) {
  const name = String(c.name || 'manual mark');
  const ts = String(c.timestamp || c.ts || '');
  const dec = numOr(c.decision_count_at_checkpoint != null ? c.decision_count_at_checkpoint : c.decisions, 0);
  const msg = numOr(c.message_count_at_checkpoint != null ? c.message_count_at_checkpoint : c.messages, 0);
  const conf = confOr(c.confidence);
  const confTxt = conf == null ? '' : `, confidence ${conf.toFixed(2)}`;
  const tail = newest ? ' Newest.' : '';
  return `Checkpoint ${name}, ${ts}, ${dec} decisions, ${msg} messages${confTxt}.${tail} Arm for compare.`;
}

function numOr(v, dflt) {
  const n = Number(v);
  return Number.isFinite(n) ? n : dflt;
}
function confOr(v) {
  const n = Number(v);
  return Number.isFinite(n) ? Math.max(0, Math.min(1, n)) : null;
}

/**
 * Order two armed checkpoint nodes so the OLDER is checkpoint_1 (the baseline)
 * and the NEWER is checkpoint_2. Returns {first, second} node view-models.
 * @param {Record<string, any>} a
 * @param {Record<string, any>} b
 */
export function orderPair(a, b) {
  const ka = Date.parse(a && a.ts) || 0;
  const kb = Date.parse(b && b.ts) || 0;
  return ka <= kb ? { first: a, second: b } : { first: b, second: a };
}

/**
 * Build the PRE-COMPUTED delta manifest rows from a server compare payload (or
 * the mock). The component renders these verbatim -- it does NOT compute any
 * delta itself. Each row pairs a TEXT label + a signed value + a tone variant
 * (M4: color is only the second channel; the label + number are load-bearing).
 *
 * The confidence row carries an ASCII glyph (v down / ^ up / = flat) so the
 * direction is never hue-only. A zero escalation delta collapses to a dash.
 *
 * @param {Record<string, any>} cmp  the compare payload
 * @returns {{
 *   pair:{name1:string, name2:string},
 *   rows:Array<Record<string, any>>,
 *   hitl:{count:number, verdict:string},
 *   patterns:Array<{hash:string, applied:number}>,
 *   escalation:{count:number, type:string}
 * }}
 */
export function compareManifest(cmp) {
  const c = cmp && typeof cmp === 'object' ? cmp : {};
  const dDec = numOr(c.delta_decisions, 0);
  const dMsg = numOr(c.delta_messages, 0);
  const conf1 = confOr(c.confidence_1);
  const conf2 = confOr(c.confidence_2);
  const dConf = conf1 != null && conf2 != null ? conf2 - conf1 : 0;
  const confDir = dConf < -0.001 ? 'down' : dConf > 0.001 ? 'up' : 'flat';
  const confGlyph = confDir === 'down' ? 'v' : confDir === 'up' ? '^' : '=';

  const hitl = c.new_hitl_overrides && typeof c.new_hitl_overrides === 'object'
    ? { count: numOr(c.new_hitl_overrides.count, 0), verdict: String(c.new_hitl_overrides.verdict || 'BLOCK') }
    : { count: 0, verdict: 'BLOCK' };

  const patterns = Array.isArray(c.policy_changes_learned)
    ? c.policy_changes_learned.map((p) => ({
        hash: String(p && p.hash ? p.hash : p),
        applied: numOr(p && p.applied, 1),
      }))
    : [];

  const escSrc = c.escalation_delta && typeof c.escalation_delta === 'object' ? c.escalation_delta : {};
  const escalation = { count: numOr(escSrc.count, 0), type: String(escSrc.type || '') };

  return {
    pair: { name1: String(c.name_1 || c.checkpoint_1 || 'baseline'), name2: String(c.name_2 || c.checkpoint_2 || 'latest') },
    rows: [
      {
        key: 'decisions',
        label: 'Decisions',
        value: signed(dDec),
        sub: spanSub(c.decisions_1, c.decisions_2),
        tone: 'neutral',
      },
      {
        key: 'messages',
        label: 'Messages',
        value: signed(dMsg),
        sub: spanSub(c.messages_1, c.messages_2),
        tone: 'neutral',
      },
      {
        key: 'confidence',
        confGlyph,
        confDir,
        label: 'Confidence',
        value: signedFloat(dConf),
        sub:
          conf1 != null && conf2 != null
            ? `${conf1.toFixed(2)} -> ${conf2.toFixed(2)} (${confDir === 'down' ? 'down' : confDir === 'up' ? 'up' : 'flat'}, n=${numOr(c.delta_decisions, 0)})`
            : 'no confidence sample',
        tone: confDir === 'down' ? 'conf-down' : confDir === 'up' ? 'conf-up' : 'conf-flat',
      },
    ],
    hitl,
    patterns,
    escalation,
  };
}

/** "+312" / "-5" / "0" (always signed except zero). */
export function signed(n) {
  const v = numOr(n, 0);
  if (v === 0) return '0';
  return (v > 0 ? '+' : '') + v.toLocaleString('en-US');
}
/** "-0.05" / "+0.03" / "0.00" for a confidence delta. */
export function signedFloat(n) {
  const v = numOr(n, 0);
  if (Math.abs(v) < 0.001) return '0.00';
  return (v > 0 ? '+' : '') + v.toFixed(2);
}
function spanSub(a, b) {
  const x = a == null ? null : numOr(a, null);
  const y = b == null ? null : numOr(b, null);
  if (x == null || y == null) return '';
  return `${x.toLocaleString('en-US')} -> ${y.toLocaleString('en-US')}`;
}

/** Format an integer with thousands separators (locale-stable en-US). */
export function fmtNum(n) {
  const v = Number(n);
  return Number.isFinite(v) ? v.toLocaleString('en-US') : '0';
}

// ---------------------------------------------------------------------------
// MOCK fixtures (served when live gov.db data is absent: fresh DB / fetch error
// / endpoint missing). Domain-agnostic invented slugs. Includes ONE SM-self
// lane (G2) so the structural-absence of its affordance is demonstrable.
// ---------------------------------------------------------------------------

/**
 * Mock governed lanes for the Frame-A rail mock when /api/sessions is empty.
 * One SM-self row is included so the affordance-absence path is exercised.
 * @returns {Array<Record<string, any>>}
 */
export function mockLanes() {
  return [
    { id: 's-mock-7af3', project_slug: 'demo-target', pid: 41822, started_at: 1749648000, ckpt_count: 3 },
    { id: 's-mock-3b10', project_slug: 'batch-runner', pid: 39517, started_at: 1749632520, ckpt_count: 1 },
    { id: 's-self-0000', project_slug: 'streamManager', pid: 40001, started_at: 1749648000, ckpt_count: 0 },
  ];
}

/**
 * Mock checkpoint list for a given governed session id. Returns the 3-node
 * demo set for the primary mock lane; a single node for the secondary; empty
 * for anything else (so an unseeded lane shows the "no checkpoints yet" state).
 * @param {string} sessionId
 * @returns {Array<Record<string, any>>}
 */
export function mockCheckpoints(sessionId) {
  const sid = String(sessionId || '');
  if (sid === 's-mock-3b10') {
    return [
      { checkpoint_id: 'ck-b1', name: 'run start', timestamp: '2026-06-11 09:02:10Z', decision_count_at_checkpoint: 40, message_count_at_checkpoint: 96, confidence: 0.88, open_hitl: 0, patterns: 4, escalations: 0 },
    ];
  }
  // primary mock lane (default) -- the 3-node 2pm/pre-refactor/4pm set.
  return [
    { checkpoint_id: 'ck-0003', name: '4pm baseline', timestamp: '2026-06-11 16:00:11Z', decision_count_at_checkpoint: 500, message_count_at_checkpoint: 1102, confidence: 0.79, open_hitl: 1, patterns: 13, escalations: 1 },
    { checkpoint_id: 'ck-0002', name: 'pre-refactor', timestamp: '2026-06-11 15:31:40Z', decision_count_at_checkpoint: 352, message_count_at_checkpoint: 771, confidence: 0.81, open_hitl: 1, patterns: 12, escalations: 0 },
    { checkpoint_id: 'ck-0001', name: '2pm baseline', timestamp: '2026-06-11 14:00:05Z', decision_count_at_checkpoint: 188, message_count_at_checkpoint: 404, confidence: 0.84, open_hitl: 0, patterns: 11, escalations: 0 },
  ];
}

/**
 * Mock pre-computed compare payload between two checkpoint ids. Keyed to the
 * 2pm-vs-4pm demo pair; for any other pair it derives a generic delta from the
 * two nodes' own metrics so the manifest still renders (a real build fetches the
 * server-cached delta). All numbers are pre-computed here -- the component never
 * does drift math.
 * @param {Record<string, any>} nodeA  older node view-model (or its checkpoint)
 * @param {Record<string, any>} nodeB  newer node view-model (or its checkpoint)
 * @returns {Record<string, any>}
 */
export function mockCompare(nodeA, nodeB) {
  const { first, second } = orderPair(nodeA, nodeB);
  const f = first || {};
  const s = second || {};
  // The canonical demo story (2pm -> 4pm): a confidence dip + 1 new BLOCK HITL.
  const is2to4 =
    (f.name === '2pm baseline' && s.name === '4pm baseline') ||
    (f.id === 'ck-0001' && s.id === 'ck-0003');
  if (is2to4) {
    return {
      checkpoint_1: 'ck-0001',
      checkpoint_2: 'ck-0003',
      name_1: '2pm baseline',
      name_2: '4pm baseline',
      decisions_1: 188,
      decisions_2: 500,
      delta_decisions: 312,
      messages_1: 404,
      messages_2: 1102,
      delta_messages: 698,
      confidence_1: 0.84,
      confidence_2: 0.79,
      new_hitl_overrides: { count: 1, verdict: 'BLOCK' },
      policy_changes_learned: [
        { hash: 'a1c93e', applied: 2 },
        { hash: '7fd204', applied: 1 },
      ],
      escalation_delta: { count: 1, type: 'governance_negative_regression' },
    };
  }
  // generic derived delta between any two nodes (still pre-computed, not live).
  const d1 = numOr(f.decisions, 0);
  const d2 = numOr(s.decisions, 0);
  const m1 = numOr(f.messages, 0);
  const m2 = numOr(s.messages, 0);
  return {
    checkpoint_1: f.id || 'baseline',
    checkpoint_2: s.id || 'latest',
    name_1: f.name || 'baseline',
    name_2: s.name || 'latest',
    decisions_1: d1,
    decisions_2: d2,
    delta_decisions: d2 - d1,
    messages_1: m1,
    messages_2: m2,
    delta_messages: m2 - m1,
    confidence_1: f.confidence != null ? f.confidence : null,
    confidence_2: s.confidence != null ? s.confidence : null,
    new_hitl_overrides: { count: Math.max(0, numOr(s.openHitl, 0) - numOr(f.openHitl, 0)), verdict: 'BLOCK' },
    policy_changes_learned: [],
    escalation_delta: { count: Math.max(0, numOr(s.escalations, 0) - numOr(f.escalations, 0)), type: numOr(s.escalations, 0) > numOr(f.escalations, 0) ? 'governance_negative_regression' : '' },
  };
}
