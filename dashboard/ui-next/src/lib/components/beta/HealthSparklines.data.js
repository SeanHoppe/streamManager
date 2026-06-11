// HealthSparklines.data.js -- pure data helpers for the BETA feature
// "health-sparklines" (#34). NO Svelte, NO DOM, NO fetch -- just the math that
// turns a decision stream (or a /sparkline-data row set) into the per-session
// rolling buffers + tri-state read the sparkline strip renders.
//
// Split out from HealthSparklines.svelte so the geometry / state logic is unit-
// testable in isolation and the component stays presentation-only.
//
// DOMAIN-AGNOSTIC (M16): nothing here knows a governed-target name. The only
// identity it touches is an opaque session_id string carried through verbatim.
// No monitored-project vocabulary, no JOB ids, no role names.
//
// M4 (paired label+color): every state this module computes is returned with a
// LITERAL text label (`stateLabel`) + a one-line text read. The color class is
// the SECOND channel only; the component never renders color without the word.
//
// ASCII-only (cp1252-safe): dash is "--". No smart quotes / em-dash.

// ---------------------------------------------------------------------------
// Tri-state thresholds. Keyed to the SAME semantics the lane badge carries:
//   healthy  -- rolling-mean confidence at/above the drift line (OBSERVING).
//   drifting -- confidence sagging toward the floor but not yet breached.
//   breach   -- rolling-mean confidence below the confidence floor.
// The floor mirrors the operator confidenceFloor default (settings.js = 0.5)
// but the feature reads its own conservative band so it is glance-meaningful
// even before the operator tunes the floor.
// ---------------------------------------------------------------------------

/** The confidence-floor breach line (rolling mean below this => breach). */
export const FLOOR = 0.6;
/** The drift line (rolling mean below this but >= FLOOR => drifting). */
export const DRIFT = 0.72;
/** How many of the most-recent decisions feed the rolling-mean confidence. */
export const WINDOW = 10;
/** How many sample points the strip retains (its width in samples). */
export const POINTS = 10;

/**
 * Classify a rolling-mean confidence into the tri-state. Pure.
 * @param {number} meanConf 0..1
 * @returns {'healthy'|'drift'|'breach'}
 */
export function classify(meanConf) {
  const c = Number(meanConf);
  if (!Number.isFinite(c)) return 'healthy';
  if (c < FLOOR) return 'breach';
  if (c < DRIFT) return 'drift';
  return 'healthy';
}

/**
 * The literal text label for a state (M4 -- the always-present word channel).
 * @param {'healthy'|'drift'|'breach'} state
 * @returns {string}
 */
export function stateLabel(state) {
  if (state === 'breach') return 'breach';
  if (state === 'drift') return 'drifting';
  return 'healthy';
}

/**
 * A short trend word from the slope of the confidence series (oldest->newest).
 * Used in the paired text read so the operator gets direction, not just level.
 * @param {number[]} series confidence samples, oldest first
 * @returns {'rising'|'falling'|'steady'}
 */
export function trendWord(series) {
  if (!Array.isArray(series) || series.length < 2) return 'steady';
  const first = Number(series[0]);
  const last = Number(series[series.length - 1]);
  if (!Number.isFinite(first) || !Number.isFinite(last)) return 'steady';
  const d = last - first;
  if (d <= -0.04) return 'falling';
  if (d >= 0.04) return 'rising';
  return 'steady';
}

/**
 * The end-state read line for the breach case suffix (so the strip text mirrors
 * the mockup: "conf 0.52 -- below floor", "conf 0.68 -- falling", etc).
 * @param {'healthy'|'drift'|'breach'} state
 * @param {string} trend
 * @returns {string}
 */
export function readSuffix(state, trend) {
  if (state === 'breach') return 'below floor';
  if (state === 'drift') return trend === 'falling' ? 'falling' : 'drifting';
  return trend === 'falling' ? 'easing' : 'steady';
}

/**
 * Reduce a session's recent decision rows into a sparkline view-model. Pure --
 * the component feeds it the rows it already has (from the live decisionsStore
 * scoped to the session, or the /sparkline-data fetch).
 *
 * Each row is shaped { confidence:number, timestamp?:number } and ordered
 * NEWEST-FIRST (the decisionsStore + /api/decisions contract). We reverse to
 * oldest-first for the trace, take the last POINTS, and derive a WINDOW-mean.
 *
 * @param {Array<{confidence?:number, timestamp?:number}>} rows newest-first
 * @returns {{
 *   conf:number[], thru:number[], meanConf:number, state:'healthy'|'drift'|'breach',
 *   label:string, trend:string, suffix:string, n:number
 * }}
 */
export function buildView(rows) {
  const list = Array.isArray(rows) ? rows : [];
  // oldest-first for the trace direction
  const ordered = list.slice().reverse();
  const conf = ordered
    .map((r) => clamp01(Number(r && r.confidence)))
    .slice(-POINTS);

  // throughput proxy: decisions-per-equal-interval is not directly on a row,
  // so we derive a coarse activity sample from inter-arrival gaps when
  // timestamps exist, else a flat steady baseline. It is the SECONDARY trace
  // (the dotted floor wash) -- shape-only, never a severity signal.
  const thru = throughputSamples(ordered).slice(-POINTS);

  const windowConf = conf.slice(-WINDOW);
  const meanConf = windowConf.length
    ? windowConf.reduce((a, b) => a + b, 0) / windowConf.length
    : 0;
  const state = conf.length ? classify(meanConf) : 'healthy';
  const trend = trendWord(conf);
  return {
    conf,
    thru,
    meanConf,
    state,
    label: stateLabel(state),
    trend,
    suffix: readSuffix(state, trend),
    n: conf.length,
  };
}

/** Clamp a value into [0,1]; non-finite => 0. */
export function clamp01(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

/**
 * Derive a normalized 0..1 throughput sample per point from inter-arrival
 * timestamps (closer arrivals => higher throughput). When timestamps are
 * missing/equal it returns a gentle steady baseline so the floor wash always
 * draws. Pure; oldest-first input.
 * @param {Array<{timestamp?:number}>} ordered oldest-first
 * @returns {number[]}
 */
export function throughputSamples(ordered) {
  const n = ordered.length;
  if (n === 0) return [];
  const ts = ordered.map((r) => Number(r && r.timestamp)).filter(Number.isFinite);
  if (ts.length < 2) return ordered.map(() => 0.4);
  const gaps = [];
  for (let i = 1; i < ordered.length; i++) {
    const a = Number(ordered[i - 1] && ordered[i - 1].timestamp);
    const b = Number(ordered[i] && ordered[i].timestamp);
    const g = Number.isFinite(a) && Number.isFinite(b) ? Math.max(0, b - a) : NaN;
    gaps.push(g);
  }
  const valid = gaps.filter(Number.isFinite);
  const maxGap = valid.length ? Math.max(1, ...valid) : 1;
  // first point has no predecessor: seed it with the first real sample.
  const out = gaps.map((g) => {
    if (!Number.isFinite(g)) return 0.4;
    // smaller gap => higher throughput; normalize + invert.
    return clamp01(1 - g / maxGap) * 0.85 + 0.1;
  });
  return [out.length ? out[0] : 0.4, ...out];
}

/**
 * Map a confidence series (oldest-first, 0..1) to an SVG path string in a
 * viewBox of width W x height H. Confidence rides the TOP 70% of the band so it
 * is the load-bearing trace; 1.0 sits near the top, FLOOR sits ~70% down.
 * @param {number[]} conf
 * @param {number} W
 * @param {number} H
 * @returns {string}
 */
export function confPath(conf, W = 132, H = 18) {
  const n = conf.length;
  if (n === 0) return '';
  const innerW = W - 2;
  const top = 2;
  const usable = H * 0.7 - top; // confidence lives in the top 70%
  const stepX = n > 1 ? innerW / (n - 1) : 0;
  const pts = conf.map((c, i) => {
    const x = 1 + i * stepX;
    const y = top + usable * (1 - clamp01(c));
    return `${x.toFixed(1)} ${y.toFixed(1)}`;
  });
  return 'M ' + pts.join(' L ');
}

/**
 * Map a throughput series (oldest-first, 0..1) to a baseline-anchored area
 * path (the faint floor wash beneath the confidence trace). Returns { line,
 * area } path strings.
 * @param {number[]} thru
 * @param {number} W
 * @param {number} H
 * @returns {{line:string, area:string}}
 */
export function thruPaths(thru, W = 132, H = 18) {
  const n = thru.length;
  if (n === 0) return { line: '', area: '' };
  const innerW = W - 2;
  const base = H - 1;
  const band = H * 0.4; // throughput wash occupies the bottom 40%
  const stepX = n > 1 ? innerW / (n - 1) : 0;
  const pts = thru.map((t, i) => {
    const x = 1 + i * stepX;
    const y = base - band * clamp01(t);
    return [x, y];
  });
  const line = 'M ' + pts.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join(' L ');
  const first = pts[0][0].toFixed(1);
  const last = pts[pts.length - 1][0].toFixed(1);
  const area = `${line} L ${last} ${base} L ${first} ${base} Z`;
  return { line, area };
}

// ---------------------------------------------------------------------------
// MOCK fallback. When the live decisionsStore has no rows for a session AND the
// /sparkline-data endpoint is absent/empty (fresh gov.db, no governed decisions
// yet), the component renders this representative shape so the feature is always
// inspectable. Deterministic (seeded by the session id) so it is stable across
// reloads -- mirrors the approved mockup's SEEDS.
// ---------------------------------------------------------------------------

/** domain-agnostic enum ONLY -- never a project / JOB / role string. */
export const REASON_LABELS = Object.freeze({
  null: 'none (clean ALLOW)',
  new_pattern: 'new_pattern',
  low_confidence: 'low_confidence',
  governance_variance_alert: 'governance_variance_alert',
});

/** Representative seed shapes (level + slope) keyed to the tri-state band. */
const MOCK_SEEDS = Object.freeze({
  healthy: { base: 0.91, slope: 0.0, noise: 0.02 },
  drift: { base: 0.70, slope: -0.004, noise: 0.02 },
  breach: { base: 0.68, slope: -0.022, noise: 0.03 },
});

/** A tiny deterministic PRNG so the mock is stable across reloads. */
function rng(seed) {
  let s = (Math.abs(Math.floor(seed)) % 2147483646) + 1;
  return function next() {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

/** Hash a session id string into a stable integer seed. */
function seedFor(sessionId) {
  const str = String(sessionId || 'mock');
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) | 0;
  return h;
}

/**
 * Build a deterministic mock decision-row set (NEWEST-FIRST, matching the live
 * contract) for a session, in one of the three representative bands. Used both
 * for the strip fallback and to populate the drawer's "last 100" detail.
 * @param {string} sessionId
 * @param {'healthy'|'drift'|'breach'} band
 * @param {number} [count]
 * @returns {Array<{confidence:number, timestamp:number, action:string, trigger_reason:string|null, throughput:number}>}
 */
export function mockRows(sessionId, band = 'healthy', count = 100) {
  const sp = MOCK_SEEDS[band] || MOCK_SEEDS.healthy;
  const rand = rng(seedFor(sessionId));
  const t0 = 1749600000.0;
  const rows = [];
  for (let i = 0; i < count; i++) {
    let conf = sp.base + sp.slope * i + (rand() - 0.5) * sp.noise * 2;
    conf = Math.max(0.3, Math.min(0.99, conf));
    let reason = null;
    let action = 'ALLOW';
    if (conf < FLOOR) {
      reason = 'governance_variance_alert';
      action = 'ESCALATE';
    } else if (conf < DRIFT) {
      reason = 'low_confidence';
      action = 'INTERVENE';
    } else if (rand() < 0.06) {
      reason = 'new_pattern';
      action = 'GUIDE';
    } else {
      action = rand() < 0.2 ? 'SUGGEST' : 'ALLOW';
    }
    const throughput = 2 + Math.floor(rand() * 3);
    rows.push({
      confidence: +conf.toFixed(2),
      timestamp: +(t0 + i * 2.4).toFixed(1),
      action,
      trigger_reason: reason,
      throughput,
    });
  }
  // newest-first to match the live decisionsStore / /api/decisions contract
  return rows.reverse();
}

/**
 * Assign a representative mock band to a session deterministically so a rail of
 * mock lanes shows variety (one healthy, one drifting, one breach) without any
 * domain knowledge -- purely a hash of the id.
 * @param {string} sessionId
 * @returns {'healthy'|'drift'|'breach'}
 */
export function mockBandFor(sessionId) {
  const bands = ['healthy', 'drift', 'breach', 'healthy'];
  return bands[Math.abs(seedFor(sessionId)) % bands.length];
}

/**
 * Tally the trigger_reason enum across a row set for the drawer breakdown.
 * Returns an ordered array of { key, label, count } -- paired text + count
 * (M4: never a color-only stacked bar).
 * @param {Array<{trigger_reason?:string|null}>} rows
 * @returns {Array<{key:string, label:string, count:number}>}
 */
export function reasonBreakdown(rows) {
  const counts = { null: 0, new_pattern: 0, low_confidence: 0, governance_variance_alert: 0 };
  for (const r of Array.isArray(rows) ? rows : []) {
    const k = r && r.trigger_reason ? String(r.trigger_reason) : 'null';
    if (k in counts) counts[k] += 1;
    else counts.null += 1;
  }
  return Object.keys(counts).map((k) => ({
    key: k,
    label: REASON_LABELS[k] || k,
    count: counts[k],
  }));
}
