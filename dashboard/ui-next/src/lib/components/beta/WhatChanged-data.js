// WhatChanged-data.js -- pure, framework-free data helpers for the what-changed
// BETA feature (#49: What Changed Digest -- page-focus synthesis overlay). Leaf
// module: it imports NOTHING from the app graph, so the synthesis logic is unit-
// testable in isolation and can never reach a governed-target query path.
//
// WHAT IT DOES
//   Given the two client-side buffers the digest already holds (the decision
//   feed rows seen since the operator backgrounded the tab, and the agent roster
//   before/after that window), plus a couple of counts, it diffs them into the
//   six-section "what moved while you were away" manifest the banner renders:
//     (a) new agents      -- profile_slugs present after, absent before
//     (b) scope changes   -- an agent whose verdict band moved (e.g. GUIDE -> INTERVENE)
//     (c) confidence delta -- rolling-mean confidence before vs after (signed)
//     (d) patterns applied -- Learn-Mode pre-fill bias activations (matched_hash tally)
//     (e) hitl overrides   -- operator overrides since the watermark, tallied by action
//     (f) escalations      -- foreground-eligible escalations since the watermark, by type
//
// DOMAIN-AGNOSTIC (M16): this module hard-codes NO monitored-project vocabulary.
// Every governed identity (session_id / project_slug / profile_slug / matched_hash
// / action band) is carried through verbatim from the live rows. The five action
// bands (ALLOW / SUGGEST / GUIDE / INTERVENE / BLOCK) are the generic governance
// verdict schema -- never an envelope kind, JOB id, or role name.
//
// POLARITY (G2): this module does NO querying. It only shapes rows the component
// already received from the shared stores (decisionsStore / escalationStore /
// agentsStore), each of which is self-excluded upstream (project_slug NOT IN
// {streamManager} AND session_id != self) before it ever reaches here. There is
// no path in this file that could surface an SM-self row.
//
// ASCII-only (cp1252-safe): dash is "--". No smart quotes, no em-dashes.

// The five generic governance action bands, ordered from softest to hardest, so
// a "scope change" can be detected as a move along this axis without any
// monitored-project vocabulary. Carried verbatim from the row `action` field.
export const ACTION_BANDS = Object.freeze([
  'ALLOW',
  'SUGGEST',
  'GUIDE',
  'INTERVENE',
  'BLOCK',
]);

const _BAND_INDEX = (() => {
  /** @type {Record<string, number>} */
  const m = {};
  ACTION_BANDS.forEach((b, i) => { m[b] = i; });
  return m;
})();

/** @param {*} a @returns {string} normalized upper-case action band, or '' */
function band(a) {
  const v = (a == null ? '' : String(a)).trim().toUpperCase();
  return v in _BAND_INDEX ? v : '';
}

/** @param {Record<string, any>} a @returns {string} an agent/decision profile slug */
function slugOf(a) {
  if (!a || typeof a !== 'object') return '';
  return (a.profile_slug || a.agent_profile_slug || a.slug || '').toString().trim();
}

/**
 * Coerce a timestamp (epoch seconds OR ms OR ISO string) to ms. Returns 0 when
 * unparseable. Dashboard rows carry epoch seconds; the escalationStore carries
 * Date.now() ms; ISO strings appear in mock data -- handle all three.
 * @param {*} t @returns {number}
 */
export function toMs(t) {
  if (t == null) return 0;
  if (typeof t === 'number' && Number.isFinite(t)) {
    return t < 1e12 ? Math.round(t * 1000) : Math.round(t);
  }
  const n = Date.parse(String(t));
  return Number.isFinite(n) ? n : 0;
}

/** @param {number} ms @returns {string} stable HH:MM:SS clock label (ASCII). */
export function fmtClock(ms) {
  const d = new Date(Number(ms) || Date.now());
  const p = (n) => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

/** @param {number} ms @returns {string} human "Nm Ns" away-window label (ASCII). */
export function fmtAway(ms) {
  const total = Math.max(0, Math.round(Number(ms) / 1000) || 0);
  const m = Math.floor(total / 60);
  const s = total % 60;
  if (m <= 0) return `${s}s`;
  return `${m}m ${String(s).padStart(2, '0')}s`;
}

/** @param {number} ms @returns {number} epoch seconds (for mock row timestamps). */
function msToSec(ms) { return Math.round(ms / 1000); }

/**
 * Rolling-mean confidence of a set of decision rows (0..1). Ignores rows with no
 * numeric confidence. Returns { mean, n }.
 * @param {Array<Record<string, any>>} rows
 * @returns {{ mean:number, n:number }}
 */
export function meanConfidence(rows) {
  let sum = 0;
  let n = 0;
  for (const r of Array.isArray(rows) ? rows : []) {
    const c = Number(r && r.confidence);
    if (Number.isFinite(c)) { sum += c; n += 1; }
  }
  return { mean: n ? sum / n : 0, n };
}

/**
 * Build the full "What Changed" digest from the buffered material the component
 * collected since the operator backgrounded the tab (or since the dismissal
 * watermark). Pure shaping -- no side effects, no I/O.
 *
 * @param {{
 *   sinceMs?: number|null,
 *   untilMs?: number|null,
 *   decisionsSince?: Array<Record<string, any>>,
 *   decisionsBaseline?: Array<Record<string, any>>,
 *   agentsBefore?: Array<Record<string, any>>,
 *   agentsAfter?: Array<Record<string, any>>,
 *   escalationsSince?: Array<{ rule?:any, sessionId?:string|null, ts?:number }>,
 *   sessionId?: string|null,
 *   projectSlug?: string|null,
 * }} input
 */
export function buildDigest(input) {
  const inp = input || {};
  const sinceMs = Number(inp.sinceMs) || null;
  const untilMs = Number(inp.untilMs) || Date.now();
  const since = Array.isArray(inp.decisionsSince) ? inp.decisionsSince : [];
  const baseline = Array.isArray(inp.decisionsBaseline) ? inp.decisionsBaseline : [];

  // ---- (a) new agents: slugs present after, absent before --------------------
  const beforeSlugs = new Set(
    (Array.isArray(inp.agentsBefore) ? inp.agentsBefore : [])
      .map(slugOf).filter(Boolean),
  );
  /** @type {Array<{ profile_slug:string, session_id:string|null, first_seen_label:string }>} */
  const newAgents = [];
  const seenNew = new Set();
  for (const a of (Array.isArray(inp.agentsAfter) ? inp.agentsAfter : [])) {
    const slug = slugOf(a);
    if (!slug || beforeSlugs.has(slug) || seenNew.has(slug)) continue;
    seenNew.add(slug);
    const fs = toMs(a.first_seen) || toMs(a.last_seen) || untilMs;
    newAgents.push({
      profile_slug: slug,
      session_id: (a.session_id || a.sessionId || null),
      first_seen_label: fmtClock(fs),
    });
  }

  // ---- (b) scope changes: an agent whose verdict band moved within the window.
  // Detected generically: group the since-window decision rows by profile_slug,
  // and report any slug whose FIRST band differs from its LAST band along the
  // ALLOW..BLOCK axis. No monitored-project vocabulary -- only the generic bands.
  /** @type {Map<string, { first:string, last:string, ts:number }>} */
  const bySlug = new Map();
  // since is newest-first (the feed order); iterate oldest-first for first/last.
  for (let i = since.length - 1; i >= 0; i -= 1) {
    const r = since[i];
    const slug = slugOf(r);
    const b = band(r && r.action);
    if (!slug || !b) continue;
    const cur = bySlug.get(slug);
    if (!cur) bySlug.set(slug, { first: b, last: b, ts: toMs(r.timestamp) || untilMs });
    else { cur.last = b; cur.ts = toMs(r.timestamp) || cur.ts; }
  }
  /** @type {Array<{ profile_slug:string, from:string, to:string, ts_label:string, hardened:boolean }>} */
  const scopeChanges = [];
  for (const [slug, v] of bySlug) {
    if (v.first === v.last) continue;
    scopeChanges.push({
      profile_slug: slug,
      from: v.first,
      to: v.last,
      ts_label: fmtClock(v.ts),
      hardened: (_BAND_INDEX[v.last] ?? 0) > (_BAND_INDEX[v.first] ?? 0),
    });
  }

  // ---- (c) confidence delta: rolling mean before (baseline) vs after (since +
  // baseline as the live "now" window). Sign + magnitude carry meaning (M4 -- the
  // hue only reinforces an arrow glyph). --------------------------------------
  const before = meanConfidence(baseline);
  // the "now" mean is over the freshest window: prefer the since-window when it
  // has rows, else fall back to the baseline so the delta is 0 (flat) not NaN.
  const afterRows = since.length ? since : baseline;
  const after = meanConfidence(afterRows);
  const delta = round2((after.mean || 0) - (before.mean || 0));
  /** @type {'up'|'down'|'flat'} */
  const trend = delta > 0.0049 ? 'up' : delta < -0.0049 ? 'down' : 'flat';
  const confidence = {
    before: round2(before.mean),
    after: round2(after.mean),
    delta,
    trend,
    n: after.n,
    spark: sparkPoints(afterRows),
  };

  // ---- (d) Learn-Mode patterns applied: tally rows carrying a matched_hash that
  // arrived in the window. Advisory pre-fill bias -- never a safety override. ---
  /** @type {Map<string, number>} */
  const hashCounts = new Map();
  for (const r of since) {
    const h = (r && (r.matched_hash || r.matching_hash)) ? String(r.matched_hash || r.matching_hash).trim() : '';
    if (!h) continue;
    hashCounts.set(h, (hashCounts.get(h) || 0) + 1);
  }
  const patterns = [...hashCounts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([hash, count]) => ({ hash: shortHash(hash), count }));

  // ---- (e) HITL overrides: rows in the window flagged as an operator override.
  // Generic detection: the row carries an explicit override marker
  // (hitl_override / operator_override / overridden truthy) -- NOT a band guess,
  // so a normal verdict is never miscounted as an override. Tallied by action. --
  /** @type {Record<string, number>} */
  const hitlByAction = {};
  let hitlTotal = 0;
  for (const r of since) {
    if (!isHitlOverride(r)) continue;
    const b = band(r.action) || 'ALLOW';
    hitlByAction[b] = (hitlByAction[b] || 0) + 1;
    hitlTotal += 1;
  }

  // ---- (f) escalations: the foreground-eligible escalations the shared
  // escalationStore captured in the window, tallied by trigger/type. The store
  // is BY CONSTRUCTION the M2 allow-list, so the digest re-decides nothing. -----
  /** @type {Record<string, number>} */
  const escByType = {};
  let escTotal = 0;
  for (const e of (Array.isArray(inp.escalationsSince) ? inp.escalationsSince : [])) {
    const trig = (e && e.rule && (e.rule.trigger || e.rule.label)) ? String(e.rule.trigger || e.rule.label) : 'escalation';
    escByType[trig] = (escByType[trig] || 0) + 1;
    escTotal += 1;
  }

  const counts = {
    newAgents: newAgents.length,
    scope: scopeChanges.length,
    confidence: delta,
    patterns: patterns.reduce((n, p) => n + p.count, 0),
    hitl: hitlTotal,
    escalations: escTotal,
  };
  // The digest is "calm" (a single OK one-liner) iff nothing material moved.
  const calm = counts.newAgents === 0 && counts.scope === 0 && trend === 'flat'
    && counts.patterns === 0 && counts.hitl === 0 && counts.escalations === 0;

  return {
    sinceLabel: sinceMs ? fmtClock(sinceMs) : '--:--:--',
    untilLabel: fmtClock(untilMs),
    awayLabel: sinceMs ? fmtAway(untilMs - sinceMs) : '--',
    sessionId: inp.sessionId || null,
    projectSlug: inp.projectSlug || null,
    counts,
    calm,
    newAgents,
    scopeChanges,
    confidence,
    patterns,
    hitl: { total: hitlTotal, byAction: hitlByAction },
    escalations: { total: escTotal, byType: escByType },
  };
}

/**
 * Realistic, domain-agnostic MOCK digest for when the live buffers are empty (set
 * usedMockData=true at the call site). Mirrors the approved mockup's six-section
 * shape so the feature is testable headless. ASCII-only, generic vocabulary only.
 * @param {number} [nowMs]
 */
export function mockDigest(nowMs) {
  const end = Number(nowMs) || Date.now();
  const start = end - (6 * 60000 + 12000); // a 6m 12s away window
  const sid = 'sess-7af3';
  const sec = (offMs) => msToSec(start + offMs);
  return buildDigest({
    sinceMs: start,
    untilMs: end,
    sessionId: sid,
    projectSlug: 'alpha-proj',
    agentsBefore: [
      { profile_slug: 'planner', first_seen: sec(-3 * 3600000), session_id: sid },
    ],
    agentsAfter: [
      { profile_slug: 'planner', first_seen: sec(-3 * 3600000), session_id: sid },
      { profile_slug: 'researcher', first_seen: sec(70000), session_id: sid },
      { profile_slug: 'tester', first_seen: sec(231000), session_id: sid },
    ],
    // since-window decisions: a developer that moved GUIDE -> INTERVENE, two
    // pattern-biased rows + one more, plus one operator override (ALLOW), with a
    // gentle confidence dip across the window.
    decisionsSince: [
      { action: 'INTERVENE', confidence: 0.74, profile_slug: 'developer',
        timestamp: sec(188000), session_id: sid },
      { action: 'GUIDE', confidence: 0.77, profile_slug: 'reviewer',
        matched_hash: 'a1c93e0099', timestamp: sec(150000), session_id: sid },
      { action: 'ALLOW', confidence: 0.79, profile_slug: 'reviewer',
        matched_hash: 'a1c93e0099', hitl_override: true, timestamp: sec(120000), session_id: sid },
      { action: 'SUGGEST', confidence: 0.80, profile_slug: 'builder',
        matched_hash: '7fd2041abc', timestamp: sec(60000), session_id: sid },
      { action: 'GUIDE', confidence: 0.81, profile_slug: 'developer',
        timestamp: sec(8000), session_id: sid },
    ],
    decisionsBaseline: [
      { action: 'ALLOW', confidence: 0.82, profile_slug: 'planner', timestamp: sec(-60000), session_id: sid },
      { action: 'ALLOW', confidence: 0.80, profile_slug: 'planner', timestamp: sec(-120000), session_id: sid },
    ],
    escalationsSince: [],
  });
}

// ---------------------------------------------------------------------------
// Small pure utilities.
// ---------------------------------------------------------------------------

/**
 * Generic HITL-override detector. True iff the row carries an explicit operator-
 * override marker. Domain-agnostic: it checks generic flags, never a band guess
 * or a monitored-project field, so a routine verdict is never miscounted.
 * @param {Record<string, any>} r
 * @returns {boolean}
 */
export function isHitlOverride(r) {
  if (!r || typeof r !== 'object') return false;
  return !!(r.hitl_override || r.operator_override || r.overridden
    || r.is_override || (r.source && String(r.source).toLowerCase() === 'operator'));
}

/** @param {string} h @returns {string} a short (6-char) pattern-hash label. */
export function shortHash(h) {
  const s = (h == null ? '' : String(h)).trim();
  return s.length > 6 ? s.slice(0, 6) : s;
}

/** @param {number} n @returns {number} rounded to 2dp (no float noise). */
function round2(n) {
  const v = Number(n);
  return Number.isFinite(v) ? Math.round(v * 100) / 100 : 0;
}

/**
 * Tiny 6-point sparkline polyline (viewBox 0..44 x 0..16) over a confidence
 * series, newest-first input rendered left-to-right oldest-first. Higher
 * confidence => lower y (top). Domain-free, no library.
 * @param {Array<Record<string, any>>} rows
 * @returns {string} a `points="..."` value for an SVG polyline
 */
export function sparkPoints(rows) {
  const series = (Array.isArray(rows) ? rows : [])
    .map((r) => Number(r && r.confidence))
    .filter((c) => Number.isFinite(c))
    .slice(0, 6)
    .reverse();
  if (series.length === 0) return '2,8 42,8';
  const W = 44; const H = 16; const PAD = 2;
  const n = series.length;
  const lo = Math.min(...series);
  const hi = Math.max(...series);
  const span = hi - lo || 1;
  const pts = series.map((c, i) => {
    const x = n === 1 ? W / 2 : PAD + (i * (W - 2 * PAD)) / (n - 1);
    const y = PAD + (1 - (c - lo) / span) * (H - 2 * PAD);
    return `${round2(x)},${round2(y)}`;
  });
  return pts.join(' ');
}
