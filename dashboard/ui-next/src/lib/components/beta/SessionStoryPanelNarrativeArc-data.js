// SessionStoryPanelNarrativeArc-data.js -- pure data helpers for the BETA
// feature "session-story-panel-narrative-arc" (#37). NO Svelte, NO DOM, NO
// fetch -- just the logic that turns a session's decision feed into a calm,
// evidence-linked narrative arc (the segmented paragraphs + a paired
// label+color TONE) plus the deterministic mock fixture used when the live
// feed is empty.
//
// Split out from SessionStoryPanelNarrativeArc.svelte so the arc-derivation /
// tone-classification is unit-testable in isolation and the component stays
// presentation-only.
//
// DOMAIN-AGNOSTIC (M16 / zero-contamination): nothing here knows a governed-
// target name. The only identity it touches is an opaque session_id / a
// project_slug string carried through verbatim. No monitored-project
// vocabulary, no JOB ids, no role names. The mock slug "node-worker-04"
// mirrors the approved mockup and is a generic placeholder, never real vocab.
//
// M4 (paired label+color): every TONE this module computes is returned WITH a
// LITERAL text label (`TONE_MAP[tone].label`) + a one-line text reason. The
// color/badge variant is the SECOND channel only; the component never renders
// a tone without the word.
//
// POLARITY (G2 / M15): this module computes purely client-side over rows the
// component already holds (decisionsStore, already self-excluded in sse.js).
// It introduces no session query of its own.
//
// ASCII-only (cp1252-safe): dash is "--". No smart quotes / em-dash.

// ---------------------------------------------------------------------------
// TONE: the at-a-glance hero of the card. Four calm states, each paired to a
// frozen Badge variant + a LITERAL label + a one-line reason (M4). Derived from
// the session's decisions: a BLOCK -> blocked; sustained INTERVENE/GUIDE churn
// -> turbulent; pattern reinforcement without blocks -> learning; else clean.
// ---------------------------------------------------------------------------

/** @typedef {'clean'|'learning'|'turbulent'|'blocked'} Tone */

/** Tone -> { variant (Badge), label (literal text), reason (one line) }. */
export const TONE_MAP = Object.freeze({
  clean: {
    variant: 'decided',
    label: 'CLEAN',
    reason: 'clean -- no blocks, no interventions',
  },
  learning: {
    variant: 'observing',
    label: 'LEARNING',
    reason: 'learning -- patterns reinforced, no blocks',
  },
  turbulent: {
    variant: 'warn',
    label: 'TURBULENT',
    reason: 'turbulent -- repeated interventions / nudges',
  },
  blocked: {
    variant: 'blocked',
    label: 'BLOCKED',
    reason: 'blocked -- one or more governance blocks fired',
  },
});

/** The canonical tone order (calmest -> most severe) for any UI legend. */
export const TONE_ORDER = Object.freeze(['clean', 'learning', 'turbulent', 'blocked']);

/**
 * The literal text label for a tone (M4 -- the always-present word channel).
 * @param {string} tone
 * @returns {string}
 */
export function toneLabel(tone) {
  const m = TONE_MAP[tone] || TONE_MAP.clean;
  return m.label;
}

/**
 * The one-line text reason for a tone (badge title + aria-label source).
 * @param {string} tone
 * @returns {string}
 */
export function toneReason(tone) {
  const m = TONE_MAP[tone] || TONE_MAP.clean;
  return m.reason;
}

// ---------------------------------------------------------------------------
// Action classification. Domain-agnostic: a generic governance action enum
// only (ALLOW / SUGGEST / GUIDE / INTERVENE / BLOCK). No vocabulary.
// ---------------------------------------------------------------------------

/**
 * Normalize a decision row's action to the uppercase enum, defaulting to ALLOW.
 * @param {Record<string, any>} row
 * @returns {string}
 */
export function actionOf(row) {
  const a = row && row.action ? String(row.action).trim().toUpperCase() : 'ALLOW';
  return a || 'ALLOW';
}

/** @param {string} action @returns {boolean} is this action an escalation? */
export function isEscalation(action) {
  return action === 'GUIDE' || action === 'INTERVENE' || action === 'BLOCK';
}

/**
 * Classify the overall TONE of a session from its decision rows (any order).
 * Pure. The thresholds are deliberately calm: a single BLOCK dominates;
 * sustained intervention churn reads turbulent; otherwise reinforcement reads
 * learning; a quiet run reads clean.
 * @param {Array<Record<string, any>>} rows
 * @returns {Tone}
 */
export function classifyTone(rows) {
  const list = Array.isArray(rows) ? rows : [];
  if (list.length === 0) return 'clean';
  let blocks = 0;
  let intervenes = 0;
  let guides = 0;
  for (const r of list) {
    const a = actionOf(r);
    if (a === 'BLOCK') blocks += 1;
    else if (a === 'INTERVENE') intervenes += 1;
    else if (a === 'GUIDE') guides += 1;
  }
  if (blocks > 0) return 'blocked';
  // Turbulent when interventions are a meaningful fraction of the run.
  if (intervenes >= 3 || intervenes / list.length >= 0.2) return 'turbulent';
  // Learning when governance nudged/reinforced (GUIDE) without blocking.
  if (guides > 0) return 'learning';
  return 'clean';
}

// ---------------------------------------------------------------------------
// Narrative arc derivation. The arc is a small ordered list of paragraphs;
// each paragraph is a list of SEGMENTS. A plain segment is { t: "text" }; a
// LINKED segment is { anchor, phrase, ids:[decision_id...] } -- the component
// renders it as a real <button> that scroll-highlights the matching rows. A
// segment with { noevidence:true } renders as plain text (dashed, not a link)
// because there is nothing to jump to.
//
// We derive a calm, factual arc from the rows -- NEVER an LLM call here. Any
// richer (Sonnet) narrative is a DEFERRED "from CLI" affordance (see the
// component + the proposal); this client-side arc is the always-available
// floor so the panel renders with no backend and no new envelope.
// ---------------------------------------------------------------------------

/**
 * @typedef {{ t:string }} PlainSeg
 * @typedef {{ anchor:string, phrase:string, ids:number[], noevidence?:boolean }} LinkSeg
 * @typedef {Array<PlainSeg|LinkSeg>} Para
 * @typedef {{
 *   session_id:string, tone:Tone, decision_count:number,
 *   narrative_composed_at:number|null, narrative_model:string|null,
 *   paragraphs:Para[], mock:boolean, source:'derived'|'mock'|'server'
 * }} Story
 */

/** Collect the decision ids whose action matches a predicate. Newest-first in. */
function idsWhere(rows, pred) {
  /** @type {number[]} */
  const out = [];
  for (const r of Array.isArray(rows) ? rows : []) {
    const id = r && (r.id ?? r.rid);
    if (id == null) continue;
    if (pred(r)) out.push(Number(id));
  }
  return out;
}

/** Plural-safe "N thing(s)". */
function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many || `${one}s`}`;
}

/**
 * Derive a client-side narrative arc from a session's decision rows. Pure --
 * the component feeds the rows it already holds (decisionsStore scoped to the
 * session). Newest-first input is assumed (the live contract); the arc text is
 * a calm factual summary, not generated prose. Returns a Story.
 *
 * @param {Array<Record<string, any>>} rows newest-first
 * @param {{ sessionId?:string, now?:number }} [opts]
 * @returns {Story}
 */
export function deriveStory(rows, opts = {}) {
  const list = Array.isArray(rows) ? rows.filter(Boolean) : [];
  const sessionId = String(opts.sessionId || (list[0] && list[0].session_id) || '');
  const tone = classifyTone(list);
  const total = list.length;

  const editIds = idsWhere(list, (r) => {
    const a = actionOf(r);
    return a === 'ALLOW' || a === 'SUGGEST' || a === 'GUIDE' || a === 'INTERVENE';
  });
  const guideIds = idsWhere(list, (r) => actionOf(r) === 'GUIDE');
  const blockIds = idsWhere(list, (r) => actionOf(r) === 'BLOCK');
  const interveneIds = idsWhere(list, (r) => actionOf(r) === 'INTERVENE');

  /** @type {Para[]} */
  const paragraphs = [];

  // Paragraph 1 -- the opening: how many governed actions, and the resting tone.
  if (total === 0) {
    paragraphs.push([{ t: 'No decisions are in scope for this session yet.' }]);
  } else {
    /** @type {Para} */
    const p1 = [{ t: 'This session carried ' }];
    p1.push({ anchor: 'arc-actions', phrase: plural(editIds.length, 'governed action'), ids: editIds });
    if (blockIds.length === 0) {
      p1.push({ t: ', all observed without a governance block.' });
    } else {
      p1.push({ t: ', and governance stepped in (see below).' });
    }
    paragraphs.push(p1);
  }

  // Paragraph 2 -- the governance posture: nudges / interventions / blocks.
  if (blockIds.length > 0) {
    paragraphs.push([
      { t: 'Governance recorded ' },
      { anchor: 'arc-blocks', phrase: plural(blockIds.length, 'block'), ids: blockIds },
      { t: ' -- the heaviest signal in the run; review those rows first.' },
    ]);
  } else if (interveneIds.length > 0) {
    paragraphs.push([
      { t: 'Governance issued ' },
      { anchor: 'arc-intervene', phrase: plural(interveneIds.length, 'intervention'), ids: interveneIds },
      { t: ' and reinforced its nudges without escalating to a block.' },
    ]);
  } else if (guideIds.length > 0) {
    paragraphs.push([
      { t: 'Governance reinforced patterns through ' },
      { anchor: 'arc-guides', phrase: plural(guideIds.length, 'guided edit'), ids: guideIds },
      { t: ', learning as the session progressed -- no blocks.' },
    ]);
  } else if (total > 0) {
    paragraphs.push([
      { t: 'Every action cleared under static allow -- a calm, low-friction run.' },
    ]);
  }

  // Paragraph 3 -- the close: a regression-signal phrase. When there is no
  // negative-regression evidence the phrase reads PLAIN (dashed, not a link).
  if (total > 0) {
    paragraphs.push([
      { t: 'The session closed with ' },
      blockIds.length === 0
        ? { anchor: 'arc-regress', phrase: 'no negative regression signal', ids: [], noevidence: true }
        : { anchor: 'arc-regress', phrase: 'governance blocks on record', ids: blockIds },
      { t: '.' },
    ]);
  }

  return {
    session_id: sessionId,
    tone,
    decision_count: total,
    narrative_composed_at: null,
    narrative_model: null,
    paragraphs,
    mock: false,
    source: 'derived',
  };
}

// ---------------------------------------------------------------------------
// MOCK fixture. When the live decisionsStore has NO rows for the scoped session
// (fresh gov.db, no governed decisions yet) the component renders this
// representative arc so the feature is always inspectable. Deterministic +
// domain-agnostic: the slug "node-worker-04" mirrors the approved mockup and is
// a generic placeholder, never monitored-project vocabulary.
// ---------------------------------------------------------------------------

/** A representative, evidence-linked mock arc (matches the approved mockup). */
export function mockStory(sessionId) {
  const sid = String(sessionId || 'sess-mock-0001');
  return /** @type {Story} */ ({
    session_id: sid,
    tone: 'clean',
    decision_count: 80,
    narrative_composed_at: 1749700000.0,
    narrative_model: 'claude-sonnet-4-5',
    mock: true,
    source: 'mock',
    paragraphs: [
      [
        { t: 'Session opened 2:43pm; apparent goal: refactor an auth module. The agent issued ' },
        { anchor: 'n1', phrase: '7 file edits', ids: [101, 102, 103, 104, 105, 106, 107] },
        { t: ', all governed under GUIDE -- no blocks, no interventions.' },
      ],
      [
        { t: 'Governance learned ' },
        { anchor: 'n2', phrase: 'two patterns', ids: [104, 106] },
        { t: ' during the run: a conditional-import check (+3 confidence) and an async-function-safety check (+2 confidence).' },
      ],
      [
        { t: 'The session closed cleanly with ' },
        { anchor: 'n3', phrase: 'no negative regression signal', ids: [], noevidence: true },
        { t: '.' },
      ],
    ],
  });
}

/**
 * The mock decision rows the mock arc links into (newest-first, matching the
 * live contract). ids match the link ids above. Used when the live feed is
 * empty so the bi-directional jump is demonstrable. Domain-agnostic slug.
 * @param {string} [sessionId]
 * @returns {Array<Record<string, any>>}
 */
export function mockRows(sessionId) {
  const slug = 'node-worker-04';
  const sess = 'node-wor';
  const base = [
    { id: 107, timestamp: '16:08:55.114', action: 'GUIDE', layer: 3, confidence: 91,
      content: 'Edit src/auth/session.py -- tighten token TTL',
      reasoning: 'conditional-import check satisfied; proceeding under GUIDE' },
    { id: 106, timestamp: '16:07:31.880', action: 'GUIDE', layer: 3, confidence: 88,
      content: 'Edit src/auth/refresh.py -- add async-safety guard',
      reasoning: 'async-function-safety pattern reinforced (+2)' },
    { id: 105, timestamp: '16:05:12.402', action: 'ALLOW', layer: 1, confidence: 97,
      content: 'Edit tests/test_auth.py -- cover refresh path',
      reasoning: 'static allow -- test-only file edit' },
    { id: 104, timestamp: '16:03:48.991', action: 'GUIDE', layer: 3, confidence: 84,
      content: 'Edit src/auth/__init__.py -- reorder imports',
      reasoning: 'conditional-import pattern reinforced (+3)' },
    { id: 103, timestamp: '16:01:20.557', action: 'ALLOW', layer: 1, confidence: 95,
      content: 'Edit src/auth/errors.py -- new exception type',
      reasoning: 'static allow -- additive change' },
    { id: 102, timestamp: '15:58:04.310', action: 'GUIDE', layer: 2, confidence: 86,
      content: 'Edit src/auth/middleware.py -- wrap handler',
      reasoning: 'guide nudge -- confirm error propagation' },
    { id: 101, timestamp: '15:55:41.002', action: 'ALLOW', layer: 1, confidence: 98,
      content: 'Edit src/auth/config.py -- read TTL from env',
      reasoning: 'static allow -- config read' },
  ];
  return base.map((r) => ({
    ...r,
    session_id: String(sessionId || 'sess-mock-0001'),
    agent_id: slug,
    agent_profile_slug: slug,
    sess,
  }));
}

// ---------------------------------------------------------------------------
// Row presentation helpers (mirror DecisionRow.svelte semantics, domain-
// agnostic). Used to render the evidence rows the arc links into.
// ---------------------------------------------------------------------------

/** action -> type-weight class (heavier action == heavier ink, M4 second chan). */
export function weightForAction(a) {
  if (a === 'BLOCK') return 'urgent';
  if (a === 'INTERVENE') return 'signal';
  if (a === 'GUIDE') return 'notice';
  return 'calm';
}

/**
 * action -> paired { variant, label } for the per-row OBSERVING/DECIDED/BLOCKED
 * badge (the row's at-a-glance literal state; never color alone).
 * @param {string} a
 * @returns {{ variant:string, label:string }}
 */
export function badgeForAction(a) {
  if (a === 'BLOCK') return { variant: 'blocked', label: 'BLOCKED' };
  if (a === 'INTERVENE') return { variant: 'decided', label: 'DECIDED' };
  return { variant: 'observing', label: 'OBSERVING' };
}

/**
 * Normalize a confidence value to a 0..100 integer for the row meter. The live
 * feed carries confidence as 0..1; the mock rows carry it as 0..100 already.
 * @param {number} conf
 * @returns {number}
 */
export function confPct(conf) {
  const n = Number(conf);
  if (!Number.isFinite(n)) return 0;
  const pct = n <= 1 ? n * 100 : n;
  return Math.max(0, Math.min(100, Math.round(pct)));
}

/**
 * Short display id for an opaque session id (M16: identity from data). Mirrors
 * the SessionRail short-id convention.
 * @param {string} id
 * @returns {string}
 */
export function shortId(id) {
  const s = String(id || '');
  return s.length <= 10 ? s : `${s.slice(0, 6)}..${s.slice(-3)}`;
}

/**
 * Format an epoch (seconds) as "YYYY-MM-DD HH:MM". Mirrors the mockup's
 * fmtComposed. Non-finite => empty string.
 * @param {number|null} epoch
 * @returns {string}
 */
export function fmtComposed(epoch) {
  const n = Number(epoch);
  if (!Number.isFinite(n) || n <= 0) return '';
  const d = new Date(n * 1000);
  const pad = (x) => String(x).padStart(2, '0');
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}
