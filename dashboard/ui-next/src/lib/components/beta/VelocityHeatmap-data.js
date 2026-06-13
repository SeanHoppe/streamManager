// VelocityHeatmap-data.js -- pure bucket-aggregation + state-derivation +
// mock-fixture helpers for the BETA feature "velocity-heatmap" (#19). No DOM,
// no Svelte, no network: a deterministic leaf module so the heatmap math is
// unit-testable in isolation and the component stays lean.
//
// CONTRACT (matches reports/proposals/mockups/velocity-heatmap.html):
//   - The plot is a 5 (governance LEVEL L0..L4) x 30 (one-minute time bucket)
//     grid. A cell (level, minute) carries the COUNT of decisions whose layer
//     == level that landed in that one-minute bucket, plus the matched-pattern
//     hashes + verbatim texts FROM DATA. minute_bucket 0 == "now", 29 == 29
//     minutes ago (the component renders oldest-left, now-right).
//   - The Y axis is governance LEVEL (the decision `layer` 0..4); decisions with
//     a layer outside 0..4 are ignored (defensive -- the engine only emits 0..4).
//   - A derived STATE BADGE (LEARNING / STALLED / RESETTING / CALM) is computed
//     from the dominant-level mass so the read survives with all hue removed
//     (M4 paired label+color: the badge text, the gutter level labels, and the
//     in-cell count digits are each a sufficient monochrome signal).
//
// POLARITY (G2 / M15): this module never reads the SM-own session. The caller
//   passes already-self-excluded rows (decisionsStore is self-excluded in
//   sse.js); bucketize() ALSO drops any row whose session_id matches a supplied
//   ownSessionId as a cheap backstop, so a leak upstream still cannot paint a
//   self cell.
//
// DOMAIN-AGNOSTIC (M16): nothing here hard-codes monitored-project vocabulary.
//   Levels are the canonical governance L0..L4; hashes + texts are rendered
//   verbatim from data.
//
// ASCII-only (cp1252-safe): dash is "--".

/** Governance levels, ceiling-first (render order: L4 top .. L0 floor). */
export const LEVELS_TOP_DOWN = Object.freeze([4, 3, 2, 1, 0]);

/** Number of one-minute buckets on the X axis (rolling 30-minute window). */
export const MINUTES = 30;

/** Default bucket width: 60 seconds, expressed in milliseconds. */
export const BUCKET_MS = 60000;

/**
 * Short word annotation per level for the gutter (paired with the L# label).
 * Domain-agnostic governance taxonomy -- no monitored-project vocabulary.
 * @type {Readonly<Record<number, string>>}
 */
export const LEVEL_WORD = Object.freeze({
  4: 'precedent',
  3: 'high-conf',
  2: 'mid',
  1: 'forming',
  0: 'reset',
});

/**
 * Normalise a decision row's timestamp into epoch MILLISECONDS.
 *
 * The WAL `decisions`/`messages` tables store `timestamp` as epoch SECONDS
 * (float). A value that already looks like ms (>= 1e12) is passed through, so
 * the helper is robust whether the caller hands it raw DB seconds or a
 * Date.now() style value. Returns null for anything non-finite.
 * @param {*} ts
 * @returns {number|null}
 */
export function toEpochMs(ts) {
  const n = Number(ts);
  if (!Number.isFinite(n)) return null;
  return n < 1e12 ? n * 1000 : n;
}

/**
 * Extract the integer governance LEVEL (0..4) from a heterogeneous row. Reads
 * `layer` defensively; returns null when it is not an integer in 0..4 (so a
 * malformed/absent layer is simply ignored rather than mis-bucketed).
 * @param {*} row
 * @returns {number|null}
 */
export function rowLevel(row) {
  if (!row || typeof row !== 'object') return null;
  const n = Number(row.layer);
  if (!Number.isFinite(n)) return null;
  const lvl = Math.trunc(n);
  return lvl >= 0 && lvl <= 4 ? lvl : null;
}

/**
 * Short stable pattern hash for a row. Prefers `matched_hash`; falls back to a
 * truncated `id`/`rid` so a row without a matched pattern is still addressable.
 * Always a short opaque token (M16: never project vocabulary).
 * @param {*} row
 * @returns {string}
 */
export function rowHash(row) {
  if (!row || typeof row !== 'object') return '------';
  const h = (row.matched_hash == null ? '' : String(row.matched_hash)).trim();
  if (h) return h.length > 8 ? h.slice(0, 8) : h;
  const id = row.id != null ? row.id : row.rid;
  const s = id == null ? '' : String(id);
  return s ? `d${s.slice(-5)}` : '------';
}

/**
 * Short verbatim text for a row (the in-popover caption). Prefers a trimmed
 * `content`, then `reasoning`; falls back to a level-only sentence. Rendered
 * FROM DATA (M16) and truncated so the popover never blows out.
 * @param {*} row
 * @returns {string}
 */
export function rowText(row) {
  if (!row || typeof row !== 'object') return 'decision';
  const raw = (row.content == null ? '' : String(row.content)).trim()
    || (row.reasoning == null ? '' : String(row.reasoning)).trim();
  if (!raw) {
    const a = (row.action == null ? '' : String(row.action)).trim();
    return a ? `${a.toLowerCase()} decision` : 'decision';
  }
  const oneLine = raw.replace(/\s+/g, ' ');
  return oneLine.length > 80 ? `${oneLine.slice(0, 77)}...` : oneLine;
}

/**
 * Aggregate decision rows into the sparse {level, minute_bucket, count, hashes,
 * texts} bucket list the heatmap renders (exactly the mockup's BUCKETS shape).
 *
 * @param {Array<Record<string, any>>} rows  decision rows (any order). Each
 *   carries at least { layer, timestamp, matched_hash?, content?, session_id? }.
 * @param {{ bucketMs?:number, minutes?:number, ownSessionId?:string|null,
 *           now?:number }} [opts]
 *   - bucketMs: window width (default BUCKET_MS = 60s).
 *   - minutes: number of buckets on the X axis (default MINUTES = 30).
 *   - ownSessionId: G2 backstop -- drop rows for this session before bucketing.
 *   - now: epoch ms "right edge" of the axis (default Date.now()).
 * @returns {{
 *   buckets: Array<{level:number, minute_bucket:number, count:number,
 *                   hashes:string[], texts:string[]}>,
 *   byKey: Record<string, {level:number, minute_bucket:number, count:number,
 *                          hashes:string[], texts:string[]}>,
 *   max:number, total:number
 * }}
 *   `byKey` is indexed by "level:minute_bucket" for O(1) cell lookup. `max` is
 *   the densest cell's count (>=1 so alpha math never divides by zero).
 */
export function bucketize(rows, opts = {}) {
  const bucketMs = Number(opts.bucketMs) > 0 ? Number(opts.bucketMs) : BUCKET_MS;
  const minutes = Number(opts.minutes) > 0 ? Math.trunc(Number(opts.minutes)) : MINUTES;
  const own = (opts.ownSessionId || '').toString().trim();
  const nowMs = Number.isFinite(opts.now) ? Number(opts.now) : Date.now();
  const list = Array.isArray(rows) ? rows : [];

  // nowBucketStart anchors minute_bucket 0 (the bucket containing `now`).
  const nowStart = Math.floor(nowMs / bucketMs) * bucketMs;

  /** @type {Record<string, {level:number, minute_bucket:number, count:number, hashes:string[], texts:string[]}>} */
  const byKey = {};
  let max = 1;
  let total = 0;

  for (const r of list) {
    // G2 backstop: never bucket an SM-own row even if one slipped through.
    if (own && r && String(r.session_id || '').trim() === own) continue;
    const level = rowLevel(r);
    if (level == null) continue;
    const ms = toEpochMs(r.timestamp);
    if (ms == null) continue;
    const start = Math.floor(ms / bucketMs) * bucketMs;
    // minute_bucket = how many whole buckets ago (0 == now). Drop anything
    // outside the rolling window or in the future.
    const minute = Math.round((nowStart - start) / bucketMs);
    if (minute < 0 || minute > minutes - 1) continue;

    const key = `${level}:${minute}`;
    let cell = byKey[key];
    if (!cell) {
      cell = { level, minute_bucket: minute, count: 0, hashes: [], texts: [] };
      byKey[key] = cell;
    }
    cell.count += 1;
    cell.hashes.push(rowHash(r));
    cell.texts.push(rowText(r));
    if (cell.count > max) max = cell.count;
    total += 1;
  }

  const buckets = Object.keys(byKey).map((k) => byKey[k]);
  return { buckets, byKey, max, total };
}

/**
 * The derived STATE machine -- the load-bearing M4 read that survives with all
 * hue removed. Computed from the dominant-level mass:
 *   LEARNING  (decided)   : top rows (L3/L4) carry the most decisions.
 *   STALLED   (warn)      : mid band (L1/L2) dominates -- oscillating, not maturing.
 *   RESETTING (blocked)   : L0 dominates -- patterns resetting / auto-demoting.
 *   CALM      (observing) : negligible mass -- the monitor is at rest.
 * Every entry carries a Badge.svelte variant key + the literal label word + a
 * plain-language `help` + a one-line `reason` (-> title/aria).
 * @param {{ buckets:Array<{level:number, count:number}>, total?:number }} agg
 * @returns {{key:string, variant:'observing'|'decided'|'warn'|'blocked',
 *            label:string, help:string, reason:string}}
 */
export function deriveState(agg) {
  const buckets = (agg && Array.isArray(agg.buckets)) ? agg.buckets : [];
  let hi = 0;
  let mid = 0;
  let low = 0;
  let total = 0;
  for (const b of buckets) {
    const c = Number(b.count) || 0;
    total += c;
    if (b.level >= 3) hi += c;
    else if (b.level >= 1) mid += c;
    else low += c;
  }
  if (total < 3) {
    return {
      key: 'calm', variant: 'observing', label: 'CALM',
      help: 'Little learning activity -- the monitor is at rest.',
      reason: 'At rest -- negligible pattern movement.',
    };
  }
  if (low >= mid && low >= hi) {
    return {
      key: 'resetting', variant: 'blocked', label: 'RESETTING',
      help: 'Patterns are resetting to L0 / auto-demoting -- possible negative loop. Watch closely.',
      reason: 'L0 reset mass dominates -- patterns demoting, possible negative loop.',
    };
  }
  if (mid >= hi) {
    return {
      key: 'stalled', variant: 'warn', label: 'STALLED',
      help: 'Patterns are parked on the L1/L2 mid-band -- oscillating, not maturing. Watch, do not act.',
      reason: 'Mid-level dwell dominates -- patterns oscillating L1 and L2, not maturing.',
    };
  }
  return {
    key: 'learning', variant: 'decided', label: 'LEARNING',
    help: 'Patterns are climbing toward L3/L4 -- precedent deepening. Learning; leave it.',
    reason: 'Top-level mass dominates -- precedent deepening, governance maturing.',
  };
}

/**
 * Per-level semantic hue family (reinforcement only -- never the sole signal):
 *   L3/L4 -> allow (maturing) ; L1/L2 -> guide (mid dwell) ; L0 -> block (reset).
 * Returns the CSS custom-property NAME so the component reads the live theme
 * value (the obsidian/phosphor/paper retint applies for free).
 * @param {number} level
 * @returns {'--c-allow'|'--c-guide'|'--c-block'}
 */
export function levelHueVar(level) {
  if (level >= 3) return '--c-allow';
  if (level >= 1) return '--c-guide';
  return '--c-block';
}

/**
 * Map a cell count (1..N) to a fill alpha so denser buckets read heavier even
 * in a single hue. Clamped to [0.32, 0.95].
 * @param {number} count
 * @param {number} [max]  the densest cell count (for relative scaling)
 * @returns {number}
 */
export function alphaFor(count, max) {
  const m = Number(max) > 0 ? Number(max) : 6;
  const frac = Math.min(1, (Number(count) || 0) / m);
  return Math.min(0.95, 0.32 + frac * 0.6);
}

/**
 * Build the per-cell PAIRED text (M4) FROM DATA -- a plain-words sentence that
 * accompanies the colored cell everywhere (title / aria-label / popover header).
 * Always names the literal level + count in words; color is never the sole
 * signal.
 * @param {{level:number, minute_bucket:number, count:number}} cell
 * @returns {string}
 */
export function cellLabel(cell) {
  const minAgo = cell.minute_bucket === 0 ? 'now' : `${cell.minute_bucket} min ago`;
  return `Level ${cell.level}, ${minAgo}: ${cell.count} decision${cell.count === 1 ? '' : 's'}`;
}

/**
 * Realistic MOCK bucket fixture for when live gov.db data carries no layered
 * decisions in the window (the live DB is frequently ALLOW-only / sparse, so the
 * heatmap would otherwise be blank in test). Mirrors the approved mockup's
 * BUCKETS: an L1/L2 mid-band dwell with a small L0 reset clump -- which derives a
 * STALLED state. Returned as the SAME {buckets, byKey, max, total} shape
 * bucketize() emits, so the component path is uniform.
 *
 * The mock carries opaque hashes + generic governance texts (M16) and is NOT
 * tied to any session, so self-exclude is a no-op on it.
 * @returns {ReturnType<typeof bucketize>}
 */
export function mockHeatmap() {
  /** @type {Array<{level:number, minute_bucket:number, count:number, hashes:string[], texts:string[]}>} */
  const raw = [
    { level: 4, minute_bucket: 27, count: 3, hashes: ['a1b2c3', 'd4e5f6', '071829'],
      texts: ['pattern matured to precedent', 'approved repeat action', 'auto-allow on known-safe'] },
    { level: 4, minute_bucket: 25, count: 2, hashes: ['a1b2c3', '9f0e1d'],
      texts: ['pattern matured to precedent', 'stable precedent reuse'] },
    { level: 3, minute_bucket: 26, count: 4, hashes: ['a1b2c3', 'd4e5f6', 'cc1100', 'ab98ff'],
      texts: ['promoted L2 to L3', 'promoted L2 to L3', 'new high-confidence row', 'promoted L2 to L3'] },
    { level: 3, minute_bucket: 23, count: 2, hashes: ['a1b2c3', 'cc1100'],
      texts: ['promoted L2 to L3', 'new high-confidence row'] },
    { level: 2, minute_bucket: 21, count: 6, hashes: ['7e7e7e', '7e7e7e', '8d8d8d', '8d8d8d', '7e7e7e', '8d8d8d'],
      texts: ['mid-level dwell', 'mid-level dwell', 'oscillating L1 and L2', 'oscillating L1 and L2', 'mid-level dwell', 'oscillating L1 and L2'] },
    { level: 2, minute_bucket: 20, count: 5, hashes: ['7e7e7e', '8d8d8d', '7e7e7e', '8d8d8d', '7e7e7e'],
      texts: ['mid-level dwell', 'oscillating L1 and L2', 'mid-level dwell', 'oscillating L1 and L2', 'mid-level dwell'] },
    { level: 1, minute_bucket: 21, count: 4, hashes: ['7e7e7e', '8d8d8d', '7e7e7e', '8d8d8d'],
      texts: ['demoted L2 to L1', 'demoted L2 to L1', 're-promote attempt', 're-promote attempt'] },
    { level: 1, minute_bucket: 20, count: 3, hashes: ['7e7e7e', '8d8d8d', '7e7e7e'],
      texts: ['demoted L2 to L1', 'demoted L2 to L1', 're-promote attempt'] },
    { level: 0, minute_bucket: 17, count: 5, hashes: ['ff0000', 'ff0000', 'aa00aa', 'aa00aa', 'ff0000'],
      texts: ['pattern reset to L0', 'auto-demotion (OBSERVE mode)', 'pattern reset to L0', 'auto-demotion (OBSERVE mode)', 'pattern reset to L0'] },
    { level: 0, minute_bucket: 16, count: 3, hashes: ['ff0000', 'aa00aa', 'ff0000'],
      texts: ['pattern reset to L0', 'auto-demotion (OBSERVE mode)', 'pattern reset to L0'] },
  ];
  /** @type {Record<string, any>} */
  const byKey = {};
  let max = 1;
  let total = 0;
  for (const c of raw) {
    byKey[`${c.level}:${c.minute_bucket}`] = c;
    if (c.count > max) max = c.count;
    total += c.count;
  }
  return { buckets: raw, byKey, max, total };
}
