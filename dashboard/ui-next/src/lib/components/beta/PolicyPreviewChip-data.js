// PolicyPreviewChip-data.js -- pure data helpers for the BETA
// "policy-preview-chip" feature (#21 -- "what governance will do, read from the
// corpus"). NO Svelte, NO network, NO side effects: this module only normalizes
// the GET /api/governance/predict response into a stable view-model and supplies
// realistic offline fixtures so the chip is always paintable.
//
// READ-ONLY PREVIEW (the absolute HITL gate + M18 are intact): the prediction is
// a post-hoc retrieval over the historical decision corpus. It NEVER calls
// governance.evaluate / the live engine, NEVER pre-selects a HITL mode, and
// emits no selection event. The corpus is polarity-filtered SERVER-SIDE
// (project_slug NOT IN the SM slug set AND session_id != SM-self); this module
// only renders the dropped-self tally the server returns (excluded_self).
//
// M4 (paired label+color, never color alone): the dominant action VERB word +
// the share fraction (14/15) + n carry ALL meaning. The band only drives a
// decorative left-edge tint that REINFORCES the literal text -- strip the tint
// and the signal survives.
//
// M16 (domain-agnostic): every governed identifier (action verb, shape hash,
// layer label, session id) is carried through verbatim FROM DATA. NO
// monitored-project vocabulary is baked in.
//
// ASCII-only (cp1252-safe): dash rendered as "--", no smart quotes, no
// em-dashes, no box-drawing.

// Canonical action display order. The five governance bands, generic taxonomy
// (never monitored-project vocabulary). Rendered with a literal label beside
// every histogram bar so the breakdown is never carried by color alone (M4).
export const ACTION_ORDER = ['ALLOW', 'SUGGEST', 'GUIDE', 'INTERVENE', 'BLOCK'];

/**
 * Coerce an arbitrary action_hist object into a complete, non-negative integer
 * histogram keyed by the canonical ACTION_ORDER (missing keys -> 0). Tolerant of
 * a server that omits zero-count buckets.
 * @param {Record<string, any>|null|undefined} raw
 * @returns {Record<string, number>}
 */
export function normalizeHist(raw) {
  /** @type {Record<string, number>} */
  const out = {};
  const src = raw && typeof raw === 'object' ? raw : {};
  for (const k of ACTION_ORDER) {
    const n = Number(src[k]);
    out[k] = Number.isFinite(n) && n > 0 ? Math.round(n) : 0;
  }
  return out;
}

/**
 * Resolve the dominant (modal) action + its count from a histogram, breaking
 * ties by the canonical ACTION_ORDER (the calmer action wins a tie, which is the
 * conservative read -- never inflate a BLOCK on a tie). Returns null when the
 * histogram is empty.
 * @param {Record<string, number>} hist
 * @returns {{ action:string, count:number }|null}
 */
export function dominantOf(hist) {
  let best = null;
  for (const a of ACTION_ORDER) {
    const c = Number(hist[a]) || 0;
    if (c <= 0) continue;
    if (best === null || c > best.count) best = { action: a, count: c };
  }
  return best;
}

/**
 * The decorative band (left-edge tint reinforcement only -- M4). The literal
 * text always carries meaning; the band never stands alone.
 *   cold  = no history (n === 0)            -> neutral hairline, "no tint claim"
 *   calm  = ALLOW-dominant, >=2/3 share     -> routine, safe to leave ASYNC
 *   block = BLOCK/INTERVENE dominant         -> governance has pushed back; look
 *   mixed = anything else (no clear winner)  -> not clearly routine
 * @param {{ n:number, dominant_action:string|null, dominant_share:number }} p
 * @returns {'cold'|'calm'|'block'|'mixed'}
 */
export function bandFor(p) {
  if (!p || Number(p.n) === 0) return 'cold';
  const share = Number(p.dominant_share) || 0;
  if (p.dominant_action === 'ALLOW' && share >= 0.66) return 'calm';
  if (p.dominant_action === 'BLOCK' || p.dominant_action === 'INTERVENE') return 'block';
  return 'mixed';
}

/**
 * A short plain-English read so the headline tells the operator what to do. The
 * read pairs the band so a colorblind operator gets the same guidance in words.
 * @param {'cold'|'calm'|'block'|'mixed'} band
 * @returns {string}
 */
export function readFor(band) {
  if (band === 'calm') return 'looks routine -- safe to leave ASYNC';
  if (band === 'block') return 'governance has pushed back here -- worth a second look';
  if (band === 'mixed') return 'mixed precedent -- not clearly routine';
  return 'novel shape, earns attention';
}

/**
 * Human label for the match_kind the server reports.
 * @param {string} kind
 * @returns {string}
 */
export function matchLabel(kind) {
  if (kind === 'exact') return 'exact shape match';
  if (kind === 'knn') return 'nearest k-NN (no exact match)';
  return 'no match';
}

/**
 * Normalize the raw GET /api/governance/predict response (or a fixture) into the
 * stable view-model the chip renders. Defensive against partial/garbage shapes:
 * an unusable payload degrades to the cold ("no history") view-model rather than
 * throwing. The `mock` flag is preserved so the chip can paint the SAMPLE DATA
 * tag (never letting sample data read as live).
 * @param {Record<string, any>|null|undefined} raw
 * @returns {{
 *   shape:string, session_id:string, n:number, match_kind:string,
 *   action_hist:Record<string, number>, dominant_action:string|null,
 *   dominant_count:number, dominant_share:number, mean_conf:number|null,
 *   dominant_layer:string|null, excluded_self:number, mock:boolean,
 *   band:'cold'|'calm'|'block'|'mixed'
 * }}
 */
export function normalizePrediction(raw) {
  const src = raw && typeof raw === 'object' ? raw : {};
  const hist = normalizeHist(src.action_hist);
  const n = ACTION_ORDER.reduce((s, a) => s + (hist[a] || 0), 0);
  const dom = dominantOf(hist);
  const dominant_action = dom ? dom.action : null;
  const dominant_count = dom ? dom.count : 0;
  const dominant_share = n > 0 && dom ? dom.count / n : 0;

  let mean_conf = null;
  const mc = Number(src.mean_conf);
  if (Number.isFinite(mc)) mean_conf = Math.min(1, Math.max(0, mc));

  const layerRaw = src.dominant_layer;
  const dominant_layer =
    layerRaw === null || layerRaw === undefined || layerRaw === ''
      ? null
      : String(layerRaw);

  const match_kind = ['exact', 'knn', 'none'].includes(src.match_kind)
    ? src.match_kind
    : n > 0
      ? 'exact'
      : 'none';

  const excluded_self = Number.isFinite(Number(src.excluded_self))
    ? Math.max(0, Math.round(Number(src.excluded_self)))
    : 0;

  const vm = {
    shape: src.shape == null ? '' : String(src.shape),
    session_id: src.session_id == null ? '' : String(src.session_id),
    n,
    match_kind,
    action_hist: hist,
    dominant_action,
    dominant_count,
    dominant_share,
    mean_conf,
    dominant_layer,
    excluded_self,
    mock: !!src.mock,
  };
  return { ...vm, band: bandFor(vm) };
}

/**
 * The full aria-label sentence (carries the meaning to assistive tech). Mirrors
 * the headline so a screen-reader user gets the same advisory read.
 * @param {ReturnType<typeof normalizePrediction>} p
 * @returns {string}
 */
export function ariaFor(p) {
  if (!p || p.n === 0) {
    return 'Corpus prediction: no history for this shape; novel shape, earns attention. Advisory only, your decision stands.';
  }
  const layer = p.dominant_layer ? p.dominant_layer.replace(/^L/, '') : 'unknown';
  const mean = p.mean_conf == null ? 'unknown' : p.mean_conf.toFixed(2);
  return (
    `Corpus prediction: ${p.dominant_count} of ${p.n} ${p.dominant_action}, ` +
    `mean confidence ${mean}, layer ${layer}; advisory only, your decision stands.`
  );
}

// ---------------------------------------------------------------------------
// Offline fixtures. Used ONLY when the server is unavailable / returns garbage,
// so the chip is always testable (the caller sets usedMockData=true + paints the
// SAMPLE DATA tag). The shapes mirror GET /api/governance/predict exactly and the
// values mirror the approved mockup (routine 14/15 ALLOW at 0.97 on L1) so the
// preview look is identical. Domain-agnostic: ids/shapes/actions are data.
// ---------------------------------------------------------------------------

/**
 * Routine fixture: 14/15 ALLOW at 0.97 mean on L1 -- the calm "look away" state.
 * @param {string} [sessionId]
 * @returns {Record<string, any>}
 */
export function mockPrediction(sessionId) {
  return {
    shape: 'a1b9c4e2',
    session_id: sessionId || 'sess-sample',
    n: 15,
    match_kind: 'exact',
    action_hist: { ALLOW: 14, SUGGEST: 1, GUIDE: 0, INTERVENE: 0, BLOCK: 0 },
    mean_conf: 0.97,
    dominant_layer: 'L1',
    excluded_self: 0,
    mock: true,
  };
}

/**
 * Cold fixture: no exact + no near neighbor -> degrade honestly to "no history".
 * The inverse signal is what makes the calm signal trustworthy.
 * @param {string} [sessionId]
 * @returns {Record<string, any>}
 */
export function mockColdPrediction(sessionId) {
  return {
    shape: '',
    session_id: sessionId || 'sess-sample',
    n: 0,
    match_kind: 'none',
    action_hist: {},
    mean_conf: null,
    dominant_layer: null,
    excluded_self: 0,
    mock: true,
  };
}
