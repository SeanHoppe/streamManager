// EscalationHeatmap-data.js -- pure bucket-aggregation + mock-fixture helpers
// for the BETA feature "escalation-heatmap" (#14). No DOM, no Svelte, no
// network: a deterministic leaf module so the density math is unit-testable in
// isolation and the component stays lean.
//
// CONTRACT (matches reports/proposals/mockups/escalation-heatmap.html):
//   - A "bucket" is a contiguous wall-clock window of BUCKET_MS. The Y axis is
//     TRUE wall-clock, so quiet buckets (total 0) are PRESENT in the array, not
//     compacted -- "steady vs bursty" is only legible if gaps keep their place.
//   - peak = the highest-severity escalation present in the bucket
//     (BLOCK > INTERVENE > GUIDE), or null when the bucket has no escalations.
//   - Only the three escalation actions count toward density. ALLOW / SUGGEST
//     (and anything unrecognised) are NOT escalations and are ignored here.
//
// POLARITY (G2 / M15): this module never reads the SM-own session. The caller
// passes already-self-excluded rows; bucketize() additionally drops any row
// whose session_id matches a supplied ownSessionId as a cheap backstop, so a
// leak upstream still cannot paint a self dot.
//
// ASCII-only (cp1252-safe): dash is "--".

/** The escalation actions, in ascending severity. Index === severity rank. */
export const SEVERITY_ORDER = Object.freeze(['GUIDE', 'INTERVENE', 'BLOCK']);

/** @type {Readonly<Record<string, number>>} severity rank lookup (1..3). */
export const SEVERITY_RANK = Object.freeze({ GUIDE: 1, INTERVENE: 2, BLOCK: 3 });

/** Default bucket width: 30 seconds, expressed in milliseconds. */
export const BUCKET_MS = 30000;

/**
 * Normalise a decision row's timestamp into epoch MILLISECONDS.
 *
 * The WAL `decisions`/`messages` tables store `timestamp` as epoch SECONDS
 * (float). A row that already looks like ms (>= 1e12) is passed through, so the
 * helper is robust whether the caller hands it raw DB seconds or a Date.now()
 * style value. Returns null for anything non-finite.
 * @param {*} ts
 * @returns {number|null}
 */
export function toEpochMs(ts) {
  const n = Number(ts);
  if (!Number.isFinite(n)) return null;
  // < 1e12 => seconds (anything after ~2001 in ms is > 1e12); scale up.
  return n < 1e12 ? n * 1000 : n;
}

/**
 * Extract the escalation action from a heterogeneous row. Reads `action`
 * defensively and upper-cases it; returns '' when it is not one of the three
 * escalation actions (so ALLOW/SUGGEST/unknown are ignored).
 * @param {*} row
 * @returns {''|'GUIDE'|'INTERVENE'|'BLOCK'}
 */
export function escalationAction(row) {
  if (!row || typeof row !== 'object') return '';
  const a = (row.action == null ? '' : String(row.action)).trim().toUpperCase();
  return SEVERITY_RANK[a] ? /** @type {any} */ (a) : '';
}

/**
 * Aggregate decision rows into a CONTIGUOUS array of wall-clock buckets.
 *
 * @param {Array<Record<string, any>>} rows  decision rows (any order). Each
 *   carries at least { action, timestamp, session_id? }.
 * @param {{ bucketMs?:number, ownSessionId?:string|null, now?:number }} [opts]
 *   - bucketMs: window width (default BUCKET_MS).
 *   - ownSessionId: G2 backstop -- drop rows for this session before bucketing.
 *   - now: epoch ms "end of axis" (default Date.now()); the axis spans from the
 *          oldest escalation's bucket through the bucket containing `now`.
 * @returns {{
 *   buckets: Array<{ t:number, counts:{GUIDE:number,INTERVENE:number,BLOCK:number},
 *                    total:number, peak:(''|'GUIDE'|'INTERVENE'|'BLOCK') }>,
 *   max:number, bucketMs:number, escalationCount:number
 * }}
 *   `buckets` is newest-LAST (ascending t); the component renders it reversed so
 *   newest sits at the TOP (matching the feed). `max` is the densest bucket's
 *   total (>=1 even when empty, so opacity math never divides by zero).
 */
export function bucketize(rows, opts = {}) {
  const bucketMs = Number(opts.bucketMs) > 0 ? Number(opts.bucketMs) : BUCKET_MS;
  const own = (opts.ownSessionId || '').toString().trim();
  const list = Array.isArray(rows) ? rows : [];

  // 1) collect (bucketStart -> counts) only for escalation rows.
  /** @type {Map<number, {GUIDE:number,INTERVENE:number,BLOCK:number}>} */
  const byBucket = new Map();
  let minStart = Infinity;
  let maxStart = -Infinity;
  let escalationCount = 0;

  for (const r of list) {
    // G2 backstop: never bucket an SM-own row even if one slipped through.
    if (own && r && String(r.session_id || '').trim() === own) continue;
    const act = escalationAction(r);
    if (!act) continue;
    const ms = toEpochMs(r.timestamp);
    if (ms == null) continue;
    const start = Math.floor(ms / bucketMs) * bucketMs;
    let c = byBucket.get(start);
    if (!c) {
      c = { GUIDE: 0, INTERVENE: 0, BLOCK: 0 };
      byBucket.set(start, c);
    }
    c[act] += 1;
    escalationCount += 1;
    if (start < minStart) minStart = start;
    if (start > maxStart) maxStart = start;
  }

  // No escalations at all -> empty axis (the caller renders the calm/empty state).
  if (escalationCount === 0) {
    return { buckets: [], max: 1, bucketMs, escalationCount: 0 };
  }

  // 2) extend the axis up to "now" so the freshest empty buckets still show the
  // recent-quiet at the top (true wall-clock, not a compacted list).
  const nowMs = Number.isFinite(opts.now) ? Number(opts.now) : Date.now();
  const nowStart = Math.floor(nowMs / bucketMs) * bucketMs;
  const lastStart = Math.max(maxStart, nowStart);

  // 3) materialise every contiguous bucket from minStart..lastStart inclusive.
  /** @type {Array<{t:number,counts:any,total:number,peak:any}>} */
  const buckets = [];
  let max = 1;
  for (let start = minStart; start <= lastStart; start += bucketMs) {
    const c = byBucket.get(start) || { GUIDE: 0, INTERVENE: 0, BLOCK: 0 };
    const total = c.GUIDE + c.INTERVENE + c.BLOCK;
    let peak = '';
    if (c.BLOCK > 0) peak = 'BLOCK';
    else if (c.INTERVENE > 0) peak = 'INTERVENE';
    else if (c.GUIDE > 0) peak = 'GUIDE';
    if (total > max) max = total;
    buckets.push({ t: start, counts: c, total, peak });
  }

  return { buckets, max, bucketMs, escalationCount };
}

/**
 * Build the per-bucket PAIRED text (M4) FROM DATA -- a plain words sentence that
 * accompanies the colored dot everywhere (title / aria-label / flyout). Always
 * names the literal severity state in words; color is never the sole signal.
 * @param {{ t:number, counts:{GUIDE:number,INTERVENE:number,BLOCK:number}, total:number }} b
 * @returns {string}
 */
export function bucketText(b) {
  const when = hhmm(b.t);
  if (!b || b.total === 0) return `${when} -- quiet (no escalations)`;
  const parts = [];
  if (b.counts.BLOCK) parts.push(`${b.counts.BLOCK} BLOCK`);
  if (b.counts.INTERVENE) parts.push(`${b.counts.INTERVENE} INTERVENE`);
  if (b.counts.GUIDE) parts.push(`${b.counts.GUIDE} GUIDE`);
  return `${when} -- ${parts.join(', ')} escalation${b.total === 1 ? '' : 's'}`;
}

/** Zero-pad to 2 digits. @param {number} n @returns {string} */
function pad2(n) {
  return n < 10 ? `0${n}` : String(n);
}

/** Local HH:MM from epoch ms. @param {number} ms @returns {string} */
export function hhmm(ms) {
  const d = new Date(ms);
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

/** Local HH:MM:SS from epoch ms. @param {number} ms @returns {string} */
export function hhmmss(ms) {
  const d = new Date(ms);
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
}

/**
 * Realistic MOCK decision rows for when live gov.db data carries no escalations
 * (the live DB is frequently ALLOW-only, so the heatmap would otherwise be
 * blank in test). Mirrors the approved mockup fixture: scattered steady GUIDE
 * dots, a couple of INTERVENE blips, and ONE contiguous BLOCK burst, laid out on
 * a 30-minute (60-bucket) wall-clock span ending at `now`.
 *
 * These rows carry a non-SM `session_id` so they survive self-exclude. The
 * caller sets usedMockData=true whenever it falls back to this fixture.
 * @param {{ now?:number, bucketMs?:number, sessionId?:string }} [opts]
 * @returns {Array<{ action:string, timestamp:number, session_id:string, content:string }>}
 */
export function mockEscalationRows(opts = {}) {
  const bucketMs = Number(opts.bucketMs) > 0 ? Number(opts.bucketMs) : BUCKET_MS;
  const now = Number.isFinite(opts.now) ? Number(opts.now) : Date.now();
  const sid = opts.sessionId || 'mock-governed-session';
  // bucket 0 is the OLDEST; place the 60-bucket span so it ends near `now`.
  const t0 = Math.floor(now / bucketMs) * bucketMs - 59 * bucketMs;
  /** @type {Array<{action:string,timestamp:number,session_id:string,content:string}>} */
  const out = [];
  // timestamp is stored as epoch SECONDS in the DB; emit seconds so the same
  // toEpochMs() path the live rows take applies uniformly.
  const tsAt = (bucketIdx) => (t0 + bucketIdx * bucketMs + 7000) / 1000;
  const push = (bucketIdx, action, content) =>
    out.push({ action, timestamp: tsAt(bucketIdx), session_id: sid, content });

  // scattered steady GUIDE dots (early calm)
  [3, 7, 11, 24, 29, 41, 52, 57].forEach((i) =>
    push(i, 'GUIDE', 'tightened a shell glob to a narrower path'));
  // a couple of INTERVENE blips
  push(9, 'INTERVENE', 'paused on an ambiguous overwrite');
  push(9, 'GUIDE', 'recommended a backup first');
  push(34, 'INTERVENE', 'blocked an unscoped recursive delete proposal');
  push(47, 'INTERVENE', 'rewrote a destructive flag to a dry-run');
  push(47, 'GUIDE', 'suggested a safer equivalent command');
  // THE BLOCK BURST -- contiguous buckets 16, 17, 18 (a red clump)
  push(16, 'BLOCK', 'denied a sandbox-escape path');
  push(16, 'BLOCK', 'denied an unbounded network fetch');
  push(16, 'INTERVENE', 're-scoped a wildcard to an explicit list');
  push(16, 'GUIDE', 'flagged a noisy retry loop');
  push(17, 'BLOCK', 'denied an out-of-scope credential read');
  push(17, 'BLOCK', 'denied a second protected-ref overwrite');
  push(17, 'BLOCK', 'denied a force-push to a protected ref');
  push(17, 'INTERVENE', 'downgraded a bulk operation to single-target');
  push(17, 'INTERVENE', 'required confirmation on a mass rename');
  push(18, 'BLOCK', 'denied a force-push to a protected ref');
  push(18, 'BLOCK', 'denied a wipe of a protected path');
  push(18, 'INTERVENE', 'converted a wipe to a soft archive');
  return out;
}
