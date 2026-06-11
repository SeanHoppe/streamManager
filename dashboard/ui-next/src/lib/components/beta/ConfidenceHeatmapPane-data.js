// ConfidenceHeatmapPane-data.js -- pure grid-aggregation + mock-fixture helpers
// for the BETA feature "confidence-heatmap-pane" (#9). No DOM, no Svelte, no
// network: a deterministic leaf module so the band/grid math is unit-testable
// in isolation and the component stays lean.
//
// CONTRACT (matches reports/proposals/mockups/confidence-heatmap-pane.html):
//   - A "bucket" is a contiguous 5-min wall-clock window. The X axis is 12
//     contiguous buckets (rolling 60 min), oldest-left newest-right; the
//     rightmost ("now") bucket holds the current 5-min window.
//   - A "cell" is one role x bucket pair with >=1 decision; it carries
//     {count, mean_confidence (count-weighted), band, action_breakdown}.
//   - band derives from mean_confidence ONLY:
//        HIGH  >= 0.75 | OK 0.60-0.75 | WATCH 0.45-0.60 | LOW < 0.45
//   - An EMPTY (role,bucket) pair (no decisions) has NO cell -- the component
//     renders an uncolored hairline gap (absence reads as quiet, M4).
//   - roles are sorted by current count-weighted mean confidence DESC.
//
// M4 (paired label+color, never color alone): every cell carries THREE
//   simultaneous encodings -- (1) band fill color, (2) the literal mean % text,
//   (3) a one-letter band glyph (H/O/W/L). The helpers here expose all three as
//   DATA (band, mean_confidence -> %, BAND_GLYPH) so the component never relies
//   on color alone.
//
// POLARITY (G2 / M15): this module never reads the SM-own session. The caller
//   passes already-self-excluded decision rows; aggregateGrid() additionally
//   drops any row whose session_id matches a supplied ownSessionId as a cheap
//   backstop, so a leak upstream still cannot paint a self cell. A self-scoped
//   render yields an empty grid (roles:[], cells:[]) -- never a wall of cells.
//
// M16 (domain-agnostic): roles come from the live decision rows' role field
//   (agent_profile_slug / profile_slug), rendered FROM DATA -- no monitored-
//   project vocabulary is baked in.
//
// ASCII-only (cp1252-safe): dash is "--".

/** The four confidence bands, in DESC severity-of-confidence order. */
export const BANDS = Object.freeze(['HIGH', 'OK', 'WATCH', 'LOW']);

/** One-letter glyph per band (the 3rd, color-independent encoding -- M4). */
export const BAND_GLYPH = Object.freeze({ HIGH: 'H', OK: 'O', WATCH: 'W', LOW: 'L' });

/** Human band label (kept identical to the key; explicit for the aria text). */
export const BAND_NAME = Object.freeze({ HIGH: 'HIGH', OK: 'OK', WATCH: 'WATCH', LOW: 'LOW' });

/** The five governance actions tallied per cell (action_breakdown keys). */
export const ACTIONS = Object.freeze(['ALLOW', 'SUGGEST', 'GUIDE', 'INTERVENE', 'BLOCK']);

/** Default bucket width: 5 minutes, in milliseconds. */
export const BUCKET_MS = 5 * 60 * 1000;

/** Number of contiguous buckets on the X axis (rolling 60 min / 5-min). */
export const NCOLS = 12;

/**
 * Band for a mean confidence in [0,1]. Color is DERIVED from this; the literal
 * % + glyph travel with it so color is never the sole signal (M4).
 * @param {number} conf
 * @returns {'HIGH'|'OK'|'WATCH'|'LOW'}
 */
export function bandOf(conf) {
  const c = Number(conf);
  if (c >= 0.75) return 'HIGH';
  if (c >= 0.6) return 'OK';
  if (c >= 0.45) return 'WATCH';
  return 'LOW';
}

/**
 * Normalise a decision row's timestamp into epoch MILLISECONDS. The WAL
 * decisions/messages tables store timestamp as epoch SECONDS (float); a value
 * already in ms (>= 1e12) passes through. Returns null for non-finite input.
 * @param {*} ts
 * @returns {number|null}
 */
export function toEpochMs(ts) {
  const n = Number(ts);
  if (!Number.isFinite(n)) return null;
  return n < 1e12 ? n * 1000 : n;
}

/**
 * Read a decision row's role FROM DATA. Mirrors the server alias chain
 * (agent_profile_slug -> profile_slug) and degrades to 'unknown' so a row with
 * no attributed agent still lands somewhere domain-agnostically (M16).
 * @param {*} row
 * @returns {string}
 */
export function roleOf(row) {
  if (!row || typeof row !== 'object') return 'unknown';
  const r =
    row.agent_profile_slug != null && String(row.agent_profile_slug).trim() !== ''
      ? row.agent_profile_slug
      : row.profile_slug;
  const s = (r == null ? '' : String(r)).trim();
  return s === '' ? 'unknown' : s;
}

/**
 * Read a decision row's action, upper-cased, restricted to the five known
 * actions; anything else maps to 'ALLOW' so the breakdown always sums to count.
 * @param {*} row
 * @returns {'ALLOW'|'SUGGEST'|'GUIDE'|'INTERVENE'|'BLOCK'}
 */
export function actionOf(row) {
  const a = (row && row.action != null ? String(row.action) : '').trim().toUpperCase();
  return ACTIONS.includes(a) ? /** @type {any} */ (a) : 'ALLOW';
}

/** Read a confidence in [0,1] defensively; out-of-range / NaN -> 0. */
function confOf(row) {
  const c = Number(row && row.confidence);
  if (!Number.isFinite(c)) return 0;
  return c < 0 ? 0 : c > 1 ? 1 : c;
}

/** A fresh zeroed action_breakdown. */
function emptyMix() {
  return { ALLOW: 0, SUGGEST: 0, GUIDE: 0, INTERVENE: 0, BLOCK: 0 };
}

/**
 * Build the 12 contiguous bucket descriptors ending at the bucket containing
 * `nowMs`. idx 0 == oldest (left), idx NCOLS-1 == "now" (right).
 * @param {number} nowMs @param {number} bucketMs
 * @returns {Array<{ idx:number, t_ms:number, label:string }>}
 */
export function buildBuckets(nowMs, bucketMs = BUCKET_MS) {
  const bw = Number(bucketMs) > 0 ? Number(bucketMs) : BUCKET_MS;
  const nowStart = Math.floor(Number(nowMs) / bw) * bw;
  const t0 = nowStart - (NCOLS - 1) * bw;
  const out = [];
  for (let i = 0; i < NCOLS; i++) {
    const t = t0 + i * bw;
    out.push({ idx: i, t_ms: t, label: hhmm(t) });
  }
  return out;
}

/**
 * Aggregate decision rows into a role x 5-min-bucket grid payload that mirrors
 * the /api/heatmap server shape EXACTLY (so live + mock are interchangeable).
 *
 * @param {Array<Record<string, any>>} rows decision rows (any order). Each
 *   carries at least { action, confidence, timestamp, session_id?, role fields }.
 * @param {{ bucketMs?:number, ownSessionId?:string|null, now?:number }} [opts]
 * @returns {{
 *   now_ms:number, bucket_min:number, minutes:number, excluded_self:number,
 *   roles:string[],
 *   buckets:Array<{idx:number,t_ms:number,label:string}>,
 *   cells:Array<{role:string,bucket_idx:number,count:number,
 *     mean_confidence:number,band:string,action_breakdown:Record<string,number>}>
 * }}
 */
export function aggregateGrid(rows, opts = {}) {
  const bucketMs = Number(opts.bucketMs) > 0 ? Number(opts.bucketMs) : BUCKET_MS;
  const own = (opts.ownSessionId || '').toString().trim();
  const nowMs = Number.isFinite(opts.now) ? Number(opts.now) : Date.now();
  const buckets = buildBuckets(nowMs, bucketMs);
  const oldestStart = buckets[0].t_ms;
  const newestStart = buckets[NCOLS - 1].t_ms;
  const list = Array.isArray(rows) ? rows : [];

  // accumulator keyed "role|idx": running sum of confidence + count + mix.
  /** @type {Map<string, {role:string, idx:number, n:number, sum:number, mix:Record<string,number>}>} */
  const acc = new Map();

  for (const r of list) {
    // G2 backstop: never bucket an SM-own row even if one slipped through.
    if (own && r && String(r.session_id || '').trim() === own) continue;
    const ms = toEpochMs(r && r.timestamp);
    if (ms == null) continue;
    const start = Math.floor(ms / bucketMs) * bucketMs;
    // only the rolling 60-min window (the 12 visible buckets) counts.
    if (start < oldestStart || start > newestStart) continue;
    const idx = Math.round((start - oldestStart) / bucketMs);
    if (idx < 0 || idx >= NCOLS) continue;
    const role = roleOf(r);
    const key = role + '|' + idx;
    let a = acc.get(key);
    if (!a) {
      a = { role, idx, n: 0, sum: 0, mix: emptyMix() };
      acc.set(key, a);
    }
    a.n += 1;
    a.sum += confOf(r);
    a.mix[actionOf(r)] += 1;
  }

  /** @type {Array<{role:string,bucket_idx:number,count:number,mean_confidence:number,band:string,action_breakdown:Record<string,number>}>} */
  const cells = [];
  for (const a of acc.values()) {
    const mean = a.n ? a.sum / a.n : 0;
    cells.push({
      role: a.role,
      bucket_idx: a.idx,
      count: a.n,
      mean_confidence: mean,
      band: bandOf(mean),
      action_breakdown: a.mix,
    });
  }

  const roles = rolesByMeanDesc(cells);
  return {
    now_ms: nowMs,
    bucket_min: Math.round(bucketMs / 60000),
    minutes: Math.round((NCOLS * bucketMs) / 60000),
    excluded_self: 0,
    roles,
    buckets,
    cells,
  };
}

/**
 * Count-weighted current mean confidence for a role over its cells.
 * @param {Array<{role:string,count:number,mean_confidence:number}>} cells
 * @param {string} role
 * @returns {number}
 */
export function meanForRole(cells, role) {
  let wSum = 0;
  let n = 0;
  for (const c of cells) {
    if (c.role !== role) continue;
    wSum += Number(c.mean_confidence) * Number(c.count);
    n += Number(c.count);
  }
  return n ? wSum / n : 0;
}

/**
 * The distinct roles present in `cells`, sorted by count-weighted mean
 * confidence DESC (heaviest/most-confident at top), ties broken by name for a
 * stable order.
 * @param {Array<{role:string,count:number,mean_confidence:number}>} cells
 * @returns {string[]}
 */
export function rolesByMeanDesc(cells) {
  const set = new Set();
  for (const c of cells) set.add(c.role);
  const roles = [...set];
  roles.sort((a, b) => {
    const d = meanForRole(cells, b) - meanForRole(cells, a);
    if (Math.abs(d) > 1e-9) return d;
    return a < b ? -1 : a > b ? 1 : 0;
  });
  return roles;
}

/**
 * Index a grid payload's cells into grid[r][c] = cell|null for O(1) cell lookup
 * by row (role) + column (bucket idx). Returns { roles, grid }.
 * @param {{roles:string[], cells:Array<{role:string,bucket_idx:number}>}} payload
 * @returns {{ roles:string[], grid:Array<Array<any>> }}
 */
export function indexGrid(payload) {
  const roles = Array.isArray(payload && payload.roles) ? payload.roles : [];
  const cells = Array.isArray(payload && payload.cells) ? payload.cells : [];
  const byKey = new Map();
  for (const c of cells) byKey.set(c.role + '|' + c.bucket_idx, c);
  const grid = roles.map((role) => {
    const row = new Array(NCOLS).fill(null);
    for (let c = 0; c < NCOLS; c++) row[c] = byKey.get(role + '|' + c) || null;
    return row;
  });
  return { roles, grid };
}

/**
 * Build the cell's PAIRED aria text (M4) FROM DATA -- the SAME signal in WORDS,
 * naming the role, window, count, mean %, and literal band name. Color-free.
 * @param {string} role @param {{label:string}} bucket
 * @param {{count:number,mean_confidence:number,band:string}} cell @param {boolean} isNow
 * @returns {string}
 */
export function cellAria(role, bucket, cell, isNow) {
  const pct = Math.round(Number(cell.mean_confidence) * 100);
  const plural = cell.count === 1 ? '' : 's';
  return (
    role +
    ', ' +
    bucket.label +
    ' window' +
    (isNow ? ' (now)' : '') +
    ', ' +
    cell.count +
    ' decision' +
    plural +
    ', mean ' +
    pct +
    '%, band ' +
    (BAND_NAME[cell.band] || cell.band)
  );
}

/**
 * Build the hover/focus tooltip lines (M4 paired -- the same signal in words +
 * the action mix). Returns { line1, line2 } as plain strings.
 * @param {string} role @param {{label:string}} bucket
 * @param {{count:number,mean_confidence:number,band:string,action_breakdown:Record<string,number>}} cell
 * @returns {{ line1:string, line2:string }}
 */
export function cellTooltip(role, bucket, cell) {
  const pct = Math.round(Number(cell.mean_confidence) * 100);
  const bd = cell.action_breakdown || {};
  const parts = [];
  for (const a of ACTIONS) if (bd[a]) parts.push(bd[a] + ' ' + a);
  return {
    line1: role + ': ' + cell.count + ' decisions in ' + bucket.label + ', mean ' + pct + '%',
    line2: (parts.length ? parts.join('  ') : 'no action breakdown') + '  -- band ' + (BAND_NAME[cell.band] || cell.band),
  };
}

/** Zero-pad to 2 digits. @param {number} n @returns {string} */
function pad2(n) {
  return n < 10 ? '0' + n : String(n);
}

/** Local HH:MM from epoch ms. @param {number} ms @returns {string} */
export function hhmm(ms) {
  const d = new Date(ms);
  return pad2(d.getHours()) + ':' + pad2(d.getMinutes());
}

/** Local HH:MM:SS from epoch ms. @param {number} ms @returns {string} */
export function hhmmss(ms) {
  const d = new Date(ms);
  return pad2(d.getHours()) + ':' + pad2(d.getMinutes()) + ':' + pad2(d.getSeconds());
}

/**
 * Realistic MOCK decision rows for when live gov.db data is absent/sparse (the
 * live DB is frequently ALLOW-only or empty, so the grid would otherwise be
 * blank in test). Mirrors the approved mockup fixture: a code_reviewer DRIFT row
 * (HIGH -> OK -> WATCH -> LOW left-to-right), a fully-HIGH frontend_architect
 * row, a steady developer row, a mostly-OK tester row, and a SPARSE researcher
 * row (gaps -> empty hairline cells), laid out on the 12-bucket (60-min) span
 * ending at `now`.
 *
 * Rows carry a non-SM session_id so they survive self-exclude. The caller sets
 * usedMockData=true whenever it falls back to this fixture. Domain-agnostic:
 * the roles are the FIXED generic RoleBadge schema, not monitored-project names.
 * @param {{ now?:number, bucketMs?:number, sessionId?:string }} [opts]
 * @returns {Array<{ action:string, confidence:number, timestamp:number,
 *   session_id:string, agent_profile_slug:string, reasoning:string }>}
 */
export function mockHeatmapRows(opts = {}) {
  const bucketMs = Number(opts.bucketMs) > 0 ? Number(opts.bucketMs) : BUCKET_MS;
  const now = Number.isFinite(opts.now) ? Number(opts.now) : Date.now();
  const sid = opts.sessionId || 'mock-governed-session';
  const nowStart = Math.floor(now / bucketMs) * bucketMs;
  const t0 = nowStart - (NCOLS - 1) * bucketMs;
  /** @type {Array<{action:string,confidence:number,timestamp:number,session_id:string,agent_profile_slug:string,reasoning:string}>} */
  const out = [];
  let seq = 0;

  // Emit `count` rows for (role, bucketIdx) with a target mean confidence + an
  // action mix; per-row confidence jitters tightly around the mean so the
  // count-weighted aggregate lands on the band the fixture intends.
  function emit(role, bucketIdx, mean, mix, reasons) {
    const order = ['BLOCK', 'INTERVENE', 'GUIDE', 'SUGGEST', 'ALLOW'];
    const base = t0 + bucketIdx * bucketMs;
    const total = ACTIONS.reduce((s, a) => s + (mix[a] || 0), 0) || 1;
    let k = 0;
    for (const act of order) {
      const n = mix[act] || 0;
      for (let j = 0; j < n; j++) {
        // spread timestamps inside the 5-min window; ts stored as epoch SECONDS.
        const tMs = base + Math.floor(((k + 1) / (total + 1)) * bucketMs);
        const jitter =
          act === 'BLOCK' ? -0.1 : act === 'INTERVENE' ? -0.05 : act === 'GUIDE' ? -0.01 : 0.02;
        let conf = mean + jitter;
        conf = conf < 0.05 ? 0.05 : conf > 0.98 ? 0.98 : conf;
        out.push({
          action: act,
          confidence: conf,
          timestamp: tMs / 1000,
          session_id: sid,
          agent_profile_slug: role,
          reasoning: reasons[(seq + k) % reasons.length],
        });
        k++;
        seq++;
      }
    }
  }

  const R = {
    fa: [
      'approved a token-only style change within scope',
      'suggested reusing an existing component over a new one',
      'guided toward an accessible focus-ring pattern',
    ],
    dev: [
      'approved a scoped edit to a single module',
      'suggested a smaller diff for the same outcome',
      'guided toward an idempotent migration step',
    ],
    rev: [
      'flagged an unverified claim in the review summary',
      'lowered confidence: could not reproduce the cited test',
      'guided toward re-running the failing case before approving',
      'intervened: review approved a change with no test coverage',
      'blocked: sign-off on an unscoped destructive edit',
    ],
    test: [
      'approved a read-only status assertion',
      'guided toward a deterministic fixture',
      'intervened on a flaky timing-dependent assertion',
    ],
    res: ['approved a read-only context gather', 'suggested narrowing the search scope'],
  };

  // -- frontend_architect: a fully-HIGH row (confident throughout) --
  emit('frontend_architect', 4, 0.79, { ALLOW: 5, SUGGEST: 1 }, R.fa);
  emit('frontend_architect', 5, 0.82, { ALLOW: 4, SUGGEST: 1 }, R.fa);
  emit('frontend_architect', 6, 0.8, { ALLOW: 6, GUIDE: 1 }, R.fa);
  emit('frontend_architect', 7, 0.84, { ALLOW: 4 }, R.fa);
  emit('frontend_architect', 8, 0.78, { ALLOW: 5, SUGGEST: 1 }, R.fa);
  emit('frontend_architect', 9, 0.81, { ALLOW: 4, SUGGEST: 1 }, R.fa);
  emit('frontend_architect', 10, 0.83, { ALLOW: 5, SUGGEST: 1 }, R.fa);
  emit('frontend_architect', 11, 0.81, { ALLOW: 5, SUGGEST: 1, GUIDE: 1 }, R.fa);
  // -- developer: steady OK/HIGH, mild dip mid-window then recovers --
  emit('developer', 3, 0.77, { ALLOW: 3, SUGGEST: 1 }, R.dev);
  emit('developer', 4, 0.72, { ALLOW: 3, SUGGEST: 1, GUIDE: 1 }, R.dev);
  emit('developer', 5, 0.68, { ALLOW: 3, SUGGEST: 2, GUIDE: 1 }, R.dev);
  emit('developer', 6, 0.71, { ALLOW: 3, SUGGEST: 1, GUIDE: 1 }, R.dev);
  emit('developer', 7, 0.74, { ALLOW: 4, SUGGEST: 1, GUIDE: 1 }, R.dev);
  emit('developer', 8, 0.76, { ALLOW: 5, SUGGEST: 1, GUIDE: 1 }, R.dev);
  emit('developer', 9, 0.73, { ALLOW: 3, SUGGEST: 1, GUIDE: 1 }, R.dev);
  emit('developer', 10, 0.75, { ALLOW: 4, SUGGEST: 1, GUIDE: 1 }, R.dev);
  emit('developer', 11, 0.74, { ALLOW: 3, SUGGEST: 1, GUIDE: 1 }, R.dev);
  // -- code_reviewer: THE DRIFT row -- HIGH -> OK -> WATCH -> LOW left-to-right --
  emit('code_reviewer', 4, 0.8, { ALLOW: 4, SUGGEST: 1 }, R.rev); // HIGH
  emit('code_reviewer', 5, 0.76, { ALLOW: 4, SUGGEST: 1, GUIDE: 1 }, R.rev); // HIGH
  emit('code_reviewer', 6, 0.71, { ALLOW: 3, SUGGEST: 1, GUIDE: 1 }, R.rev); // OK
  emit('code_reviewer', 7, 0.66, { ALLOW: 3, SUGGEST: 1, GUIDE: 2 }, R.rev); // OK
  emit('code_reviewer', 8, 0.62, { ALLOW: 2, SUGGEST: 1, GUIDE: 1 }, R.rev); // OK
  emit('code_reviewer', 9, 0.58, { ALLOW: 1, GUIDE: 2, INTERVENE: 1 }, R.rev); // WATCH
  emit('code_reviewer', 10, 0.51, { ALLOW: 1, GUIDE: 2, INTERVENE: 2 }, R.rev); // WATCH
  emit('code_reviewer', 11, 0.41, { GUIDE: 1, INTERVENE: 1, BLOCK: 1 }, R.rev); // LOW (now)
  // -- tester: mostly OK with one WATCH cell --
  emit('tester', 5, 0.7, { ALLOW: 2, SUGGEST: 1 }, R.test);
  emit('tester', 6, 0.67, { ALLOW: 2, SUGGEST: 1, GUIDE: 1 }, R.test);
  emit('tester', 7, 0.63, { ALLOW: 2, GUIDE: 1 }, R.test);
  emit('tester', 9, 0.55, { ALLOW: 1, GUIDE: 1, INTERVENE: 1 }, R.test); // WATCH
  emit('tester', 10, 0.64, { ALLOW: 2, SUGGEST: 1, GUIDE: 1 }, R.test);
  emit('tester', 11, 0.66, { ALLOW: 2, SUGGEST: 1, GUIDE: 1 }, R.test);
  // -- researcher: a SPARSE row (big gaps -> empty hairline cells) --
  emit('researcher', 2, 0.73, { ALLOW: 1, SUGGEST: 1 }, R.res);
  emit('researcher', 6, 0.69, { ALLOW: 2, GUIDE: 1 }, R.res);
  emit('researcher', 11, 0.72, { ALLOW: 1, SUGGEST: 1 }, R.res);

  return out;
}
