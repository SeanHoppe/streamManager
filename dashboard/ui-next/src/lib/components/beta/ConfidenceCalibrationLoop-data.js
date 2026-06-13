// ConfidenceCalibrationLoop-data.js -- deterministic mock fixture + pure
// helpers for the BETA feature "confidence-calibration-loop" (#8).
//
// The mock fixture mirrors GET /api/governance/calibration VERBATIM (the
// mockDataSpec in the approved mockup). It is the SAMPLE-DATA fallback shown
// when the live endpoint is empty/unavailable (fresh DB, server down) so the
// calibration view is always inspectable + testable. usedMockData=true is set
// by the component whenever this fixture is used.
//
// CALIBRATION SEMANTICS (read-only measurement -- never touches the verdict):
//   predicted = the decile midpoint of decisions.confidence.
//   realized  = realized operator-agreement = 1 - override_rate, where
//               override_rate = overrides / n for the decisions in that decile.
//   gap       = realized - predicted (positive => UNDER-confident: the operator
//               agrees MORE than the number claims; negative => OVER-confident).
//   sign      = OVER / UNDER / CALIBRATED, with a +/-2.5 point tolerance band.
//   band      = the action-ramp tint bucket reused from the heat-map pane.
//
// POLARITY (G2): SM-self is excluded server-side; excluded_self is surfaced.
// The mock carries a non-zero excluded_self so the self-exclusion is visible
// even in the sample state.
//
// ASCII-only (cp1252-safe): dash is "--". No smart quotes / em-dash.

/** Low-sample floor: a decile with fewer than this many decisions is drawn
 * dashed and its gap reading is flagged as not-yet-reliable (M4 paired). */
export const MIN_N = 30;

/** Calibration tolerance: |gap| <= this (in fraction, 0.025 = 2.5 points) reads
 * as CALIBRATED rather than OVER/UNDER. Mirrors the mockup's +/-2.5 pt band. */
export const CAL_TOLERANCE = 0.025;

/**
 * The deterministic sample payload -- the exact shape of
 * GET /api/governance/calibration. Sparse-but-representative decile set
 * (idx 0,4,5,6,8,9) exactly as the approved mockup lists.
 * @returns {Record<string, any>}
 */
export function mockCalibration() {
  return {
    now_ms: 1749600000000,
    bucket_count: 10,
    days: 30,
    excluded_self: 3,
    total_decisions: 1840,
    total_overrides: 268,
    overall_agreement: 0.854,
    brier: 0.118,
    scope: 'all governed sessions',
    buckets: [
      { idx: 0, lo: 0.0, hi: 0.1, mid: 0.05, n: 12, overrides: 9, predicted: 0.05, realized: 0.25, gap: 0.2, sign: 'UNDER', band: 'LOW' },
      { idx: 4, lo: 0.4, hi: 0.5, mid: 0.45, n: 120, overrides: 54, predicted: 0.45, realized: 0.55, gap: 0.1, sign: 'UNDER', band: 'WATCH' },
      { idx: 5, lo: 0.5, hi: 0.6, mid: 0.55, n: 160, overrides: 70, predicted: 0.55, realized: 0.563, gap: 0.013, sign: 'CALIBRATED', band: 'WATCH' },
      { idx: 6, lo: 0.6, hi: 0.7, mid: 0.65, n: 243, overrides: 86, predicted: 0.65, realized: 0.646, gap: -0.004, sign: 'CALIBRATED', band: 'OK' },
      { idx: 8, lo: 0.8, hi: 0.9, mid: 0.85, n: 520, overrides: 104, predicted: 0.85, realized: 0.8, gap: -0.05, sign: 'OVER', band: 'HIGH' },
      { idx: 9, lo: 0.9, hi: 1.0, mid: 0.95, n: 1204, overrides: 217, predicted: 0.95, realized: 0.82, gap: -0.13, sign: 'OVER', band: 'HIGH' },
    ],
    transform: [
      { from: 0.95, to: 0.82 },
      { from: 0.85, to: 0.8 },
      { from: 0.55, to: 0.56 },
    ],
    mock: true,
  };
}

/** @param {number} x @returns {string} percentage label, e.g. "85%" */
export function pct(x) {
  return Math.round((Number(x) || 0) * 100) + '%';
}

/** @param {number} n @returns {string} grouped integer, e.g. "1,840" */
export function fmtN(n) {
  return (Number(n) || 0).toLocaleString('en-US');
}

/** @param {number} gap @returns {number} absolute gap in points (0..100) */
export function gapPoints(gap) {
  return Math.round(Math.abs(Number(gap) || 0) * 100);
}

/**
 * The node/glyph SHAPE for a decile (M4 -- shape carries the sign, not color
 * alone): "low" (n below floor), "over" (filled square), "under" (hollow
 * square), "cal" (dot).
 * @param {Record<string, any>} b
 * @returns {'low'|'over'|'under'|'cal'}
 */
export function shapeFor(b) {
  if (!b || (Number(b.n) || 0) < MIN_N) return 'low';
  if (b.sign === 'OVER') return 'over';
  if (b.sign === 'UNDER') return 'under';
  return 'cal';
}

/**
 * Nearest fitted advisory transform anchor for a predicted value (advisory-only
 * map -- NEVER applied to the verdict or decisions.confidence). Returns null
 * when the payload carries no transform.
 * @param {Array<{from:number,to:number}>} transform
 * @param {number} predicted
 * @returns {{from:number,to:number}|null}
 */
export function transformFor(transform, predicted) {
  if (!Array.isArray(transform) || transform.length === 0) return null;
  let best = null;
  let bestd = Infinity;
  for (const t of transform) {
    const d = Math.abs((Number(t.from) || 0) - (Number(predicted) || 0));
    if (d < bestd) {
      bestd = d;
      best = t;
    }
  }
  return best;
}

/**
 * The worst (largest |gap|) non-low-sample decile. Drives the headline "worst
 * gap" stat. Returns null when every decile is below the floor.
 * @param {Array<Record<string, any>>} buckets
 * @returns {Record<string, any>|null}
 */
export function worstGap(buckets) {
  let worst = null;
  for (const b of Array.isArray(buckets) ? buckets : []) {
    if ((Number(b.n) || 0) < MIN_N) continue;
    if (!worst || Math.abs(Number(b.gap) || 0) > Math.abs(Number(worst.gap) || 0)) worst = b;
  }
  return worst;
}

/**
 * Plain-language reading of a decile (the tray narrative). Pure -- given a
 * bucket it returns the operator-facing sentence (ASCII-only).
 * @param {Record<string, any>} b
 * @returns {string}
 */
export function signWords(b) {
  const g = gapPoints(b.gap);
  if ((Number(b.n) || 0) < MIN_N) {
    return 'n=' + b.n + ' is below the ' + MIN_N + '-decision floor, so this point is drawn dashed -- the gap reading is not yet reliable.';
  }
  if (b.sign === 'OVER') {
    return 'The model is ' + g + ' points OVER-confident here: it predicts ' + pct(b.predicted) + ' but you actually agree only ' + pct(b.realized) + ' of the time. Mentally DISCOUNT a ' + Number(b.lo).toFixed(1) + '-' + Number(b.hi).toFixed(1) + ' confidence in this band.';
  }
  if (b.sign === 'UNDER') {
    return 'The model is ' + g + ' points UNDER-confident here: it predicts ' + pct(b.predicted) + ' but you agree ' + pct(b.realized) + ' of the time -- it is more trustworthy in this band than the number suggests.';
  }
  return 'CALIBRATED: predicted ' + pct(b.predicted) + ' matches your realized agreement ' + pct(b.realized) + ' (gap ' + g + ' points, within the +/-2.5 point tolerance). Trust the number at face value here.';
}

/**
 * The compact gap text for a rail row's sign badge.
 * @param {Record<string, any>} b
 * @returns {string}
 */
export function railGapText(b) {
  const low = (Number(b.n) || 0) < MIN_N;
  if (low) return 'n=' + b.n;
  const gp = gapPoints(b.gap);
  if (b.sign === 'CALIBRATED') return '+/-' + gp + ' ok';
  if (b.sign === 'OVER') return '+' + gp + ' over';
  return '+' + gp + ' under';
}

/**
 * Is the payload a usable LIVE calibration result, or should the component fall
 * back to the deterministic mock? Empty when there are no buckets / zero
 * decisions (fresh DB) or the server flagged it mock.
 * @param {Record<string, any>|null|undefined} p
 * @returns {boolean}
 */
export function isUsableLive(p) {
  return !!(
    p &&
    typeof p === 'object' &&
    Array.isArray(p.buckets) &&
    p.buckets.length > 0 &&
    (Number(p.total_decisions) || 0) > 0 &&
    p.mock !== true
  );
}
