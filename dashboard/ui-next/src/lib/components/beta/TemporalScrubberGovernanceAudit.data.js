// TemporalScrubberGovernanceAudit.data.js -- pure data + diff math for the BETA
// feature "temporal-scrubber-governance-audit" (#47). NO Svelte, NO DOM, NO
// network. The component imports the mock fallbacks + the confidence-delta /
// heat-band / verdict-change derivation from here so the math is
// unit-inspectable and the .svelte file stays presentation-only.
//
// WHAT THIS FEATURE IS (v1 scope -- CONSTRAINED ADDITIVE)
//   A Settings-reachable temporal-scrubber modal that does POLICY ARCHAEOLOGY by
//   REPLAY DIFF: the operator picks one governed (NON-SM) session, brackets two
//   points on its decision timeline (window A "then" vs window B "now"), and the
//   modal renders a side-by-side diff of how the engine VERDICTED comparable
//   messages in each window -- verdict, routing layer, confidence -- with the
//   confidence movement pre-computed into a center heat-spine.
//
//   v1 DIFFS THE STORED DECISION STREAM. The "window A" + "window B" columns are
//   read from the additive GET /api/decisions/replay-diff endpoint over EXISTING
//   recorded gov.db decisions+messages (polarity-filtered, SM-self excluded
//   server-side). The LIVE policy-version store (a policy_snapshots table + a
//   governance.py config-mutation hook) is DEFERRED to a documented "from CLI"
//   affordance (the amber Build-gated footnote in the modal). This module +
//   component spawn NOTHING, re-evaluate NOTHING, mint NO bus envelope, and touch
//   NO FROZEN surface.
//
// M16 (domain-agnostic): every label here is generic governance taxonomy --
// governance action (ALLOW / SUGGEST / GUIDE / INTERVENE / BLOCK), routing layer
// (L0..L4), model band, matched pattern hash, static-rule flag. NO
// monitored-project vocabulary / JOB-IDs / role names. A real session's project
// identity arrives ONLY from server data, never hard-coded here.
//
// G2 (polarity): the mock + the live shape both carry excluded_self so the
// SM-self exclusion is rendered as a VISIBLE feature; the picked session is
// NON-SM by construction (the server read excludes SM-self at the SQL WHERE).
//
// ASCII-only (cp1252-safe): dash rendered as "--". No smart quotes / em-dash.

/**
 * Verdict strictness ordering. A window-B action strictly stricter than the
 * window-A action (e.g. GUIDE -> BLOCK) is the load-bearing "policy hardened"
 * signal; a same-strength change is still a VERDICT CHANGED but not a hardening.
 * Mirrors the governance verdict ladder.
 * @type {Record<string, number>}
 */
export const STRICTNESS = Object.freeze({
  ALLOW: 0,
  SUGGEST: 1,
  GUIDE: 2,
  INTERVENE: 3,
  BLOCK: 4,
});

/** Verdict -> paired badge variant (the literal text is ALWAYS rendered too -- M4). */
export function verdictBadge(action) {
  const a = String(action || '').toUpperCase();
  if (a === 'BLOCK') return { variant: 'blocked', label: 'BLOCK' };
  if (a === 'INTERVENE') return { variant: 'warn', label: 'INTERVENE' };
  if (a === 'GUIDE') return { variant: 'observing', label: 'GUIDE' };
  if (a === 'SUGGEST') return { variant: 'observing', label: 'SUGGEST' };
  if (a === 'ALLOW') return { variant: 'observing', label: 'ALLOW' };
  return { variant: 'observing', label: a || 'OBSERVE' };
}

/** @param {number|string|null|undefined} n @returns {string} an "L<n>" layer label. */
export function layerStr(n) {
  return 'L' + (Number(n) || 0);
}

/** @param {number|string|null|undefined} c @returns {string} a 2-decimal confidence string. */
export function confStr(c) {
  const v = Number(c);
  return Number.isFinite(v) ? v.toFixed(2) : '--';
}

/** @param {number} n @returns {string} a signed 2-decimal magnitude string. */
export function signedConf(n) {
  const v = Number(n) || 0;
  // -0.00 reads oddly; normalise a sub-epsilon magnitude to a plain 0.00.
  if (Math.abs(v) < 0.005) return '0.00';
  return (v > 0 ? '+' : '-') + Math.abs(v).toFixed(2);
}

/**
 * Map a |confidence delta| to a heat band id (d0..d4). The component tints the
 * center spine by this band AND always renders the literal signed numeral, so
 * the signal survives total color loss / low vision / reduced motion (M4).
 *   d0  ~0.00   d1 <=0.05   d2 <=0.15   d3 <=0.30   d4 > 0.30
 * @param {number} delta signed confidence delta (B minus A)
 * @returns {'d0'|'d1'|'d2'|'d3'|'d4'}
 */
export function heatBand(delta) {
  const m = Math.abs(Number(delta) || 0);
  if (m < 0.005) return 'd0';
  if (m <= 0.05) return 'd1';
  if (m <= 0.15) return 'd2';
  if (m <= 0.3) return 'd3';
  return 'd4';
}

/**
 * Derive one diff row's delta block from its two window sides. Pure: given the
 * same A/B it always yields the same delta (the load-bearing "deterministic
 * archaeology" property the operator relies on).
 * @param {Record<string,any>} a window-A (then) side
 * @param {Record<string,any>} b window-B (now) side
 * @returns {{verdict_changed:boolean, hardened:boolean, confidence_delta:number, band:string, layer_delta:number}}
 */
export function computeDelta(a, b) {
  const aa = a || {};
  const bb = b || {};
  const verdict_changed = String(aa.action || '') !== String(bb.action || '');
  const aConf = Number(aa.confidence);
  const bConf = Number(bb.confidence);
  const confidence_delta =
    Number.isFinite(aConf) && Number.isFinite(bConf)
      ? Math.round((bConf - aConf) * 100) / 100
      : 0;
  const hardened =
    (STRICTNESS[String(bb.action || '').toUpperCase()] || 0) >
    (STRICTNESS[String(aa.action || '').toUpperCase()] || 0);
  const layer_delta = (Number(bb.layer) || 0) - (Number(aa.layer) || 0);
  return {
    verdict_changed,
    hardened,
    confidence_delta,
    band: heatBand(confidence_delta),
    layer_delta,
  };
}

/**
 * Normalize one raw server side ({action, confidence, layer, model_used,
 * matched_hash, content, timestamp}) into a defensive canonical side.
 * @param {Record<string,any>} raw
 * @returns {{action:string, confidence:number, layer:number, model:string, matched_hash:string, content:string, ts:string}}
 */
export function normalizeSide(raw) {
  const r = raw && typeof raw === 'object' ? raw : {};
  return {
    action: String(r.action || 'ALLOW').toUpperCase(),
    confidence: Number.isFinite(Number(r.confidence)) ? Number(r.confidence) : 0,
    layer: Number(r.layer) || 0,
    model: String(r.model_used || r.model || '').trim(),
    matched_hash: r.matched_hash ? String(r.matched_hash) : '',
    content: String(r.content != null ? r.content : ''),
    ts: String(r.timestamp != null ? r.timestamp : r.ts != null ? r.ts : ''),
  };
}

/**
 * Normalize one raw server diff row into the canonical
 * {key, window_a, window_b, delta} shape, recomputing the delta from the two
 * sides so the diff is consistent even if the server omitted it.
 * @param {Record<string,any>} raw
 * @param {number} idx
 * @returns {{key:string, window_a:Record<string,any>, window_b:Record<string,any>, delta:Record<string,any>}}
 */
export function normalizeRow(raw, idx) {
  const r = raw && typeof raw === 'object' ? raw : {};
  const window_a = normalizeSide(r.window_a || r.a || {});
  const window_b = normalizeSide(r.window_b || r.b || {});
  return {
    key: String(r.key || r.content_fingerprint || window_b.content || window_a.content || `row-${idx}`),
    // The operator-facing content prefers the (later) window-B text but both
    // sides keep their own captured content for the side columns.
    content: String(r.content || window_b.content || window_a.content || ''),
    window_a,
    window_b,
    delta: computeDelta(window_a, window_b),
  };
}

/**
 * Normalize a raw server replay-diff payload into the canonical shape. A
 * null/garbage payload, or one with zero rows, yields null so the caller can
 * treat it as "no data" and swap for the mock.
 * @param {any} raw
 * @returns {{session_id:string, project_slug:string, window_a_label:string, window_b_label:string, row_count:number, changed_count:number, excluded_self:number, polarity_filtered:boolean, mock:boolean, rows:Array<Record<string,any>>}|null}
 */
export function normalizeReplayDiff(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const inRows = Array.isArray(raw.rows) ? raw.rows : [];
  if (inRows.length === 0) return null;
  const rows = inRows.map((r, i) => normalizeRow(r, i));
  const changed_count = rows.filter((r) => r.delta && r.delta.verdict_changed).length;
  return {
    session_id: String(raw.session_id || ''),
    project_slug: String(raw.project_slug || ''),
    window_a_label: String(raw.window_a_label || 'window A'),
    window_b_label: String(raw.window_b_label || 'window B'),
    row_count: rows.length,
    changed_count,
    excluded_self: Number(raw.excluded_self) || 0,
    polarity_filtered: raw.polarity_filtered !== false,
    mock: false,
    rows,
  };
}

/**
 * Normalize the server session-list shape into the picker rows. Each row:
 * {session_id, project_slug, decision_count, label}. Empty array for a null /
 * empty payload (the caller then uses the mock picker rows). The server already
 * excludes SM-self; this is a presentation normalize only.
 * @param {any} raw
 * @returns {Array<{session_id:string, project_slug:string, decision_count:number, label:string}>}
 */
export function normalizeSessions(raw) {
  const list =
    raw && typeof raw === 'object' && Array.isArray(raw.sessions)
      ? raw.sessions
      : Array.isArray(raw)
        ? raw
        : [];
  return list
    .map((s) => {
      const sid = String((s && (s.session_id || s.id)) || '').trim();
      if (!sid) return null;
      const slug = String((s && s.project_slug) || '').trim();
      const dc = Number(s && s.decision_count) || 0;
      const shown = slug !== '' ? slug : sid;
      return {
        session_id: sid,
        project_slug: slug,
        decision_count: dc,
        label: dc > 0 ? `${shown} / ${sid} (${dc})` : `${shown} / ${sid}`,
      };
    })
    .filter(Boolean);
}

/**
 * Realistic mock picker rows -- the fallback session list when the server
 * returns no governed sessions. Synthetic NON-SM keys + domain-agnostic slugs
 * (demo-target / other-target), never a monitored-project id. The "excluded N
 * self" tally is surfaced separately by the component so the polarity backstop
 * is a VISIBLE feature even on mock data.
 * @returns {{sessions:Array<{session_id:string, project_slug:string, decision_count:number, label:string}>, excluded_self:number}}
 */
export function mockSessions() {
  return {
    sessions: [
      { session_id: 'sess-demo-7f3a', project_slug: 'demo-target', decision_count: 184, label: 'demo-target / sess-demo-7f3a (184)' },
      { session_id: 'sess-demo-2b91', project_slug: 'demo-target', decision_count: 92, label: 'demo-target / sess-demo-2b91 (92)' },
      { session_id: 'sess-other-c4d0', project_slug: 'other-target', decision_count: 57, label: 'other-target / sess-other-c4d0 (57)' },
    ],
    excluded_self: 1,
  };
}

/**
 * Realistic mock replay-diff payload -- the deterministic fallback when the
 * server returns nothing usable. Three rows: one same-verdict confidence dip
 * (static rule), one VERDICT CHANGED + hardened (INTERVENE -> BLOCK, large +
 * delta), one calm same-verdict near-zero move. Exercises every heat band + the
 * verdict-change path end to end without a live gov.db. Mirrors the mockup's
 * vetted 3-row corridor (sess-demo-7f3a, windows A/B).
 * @param {string} [sessionId] override the session key (the picker re-renders so
 *   the operator sees the picker is live; the row set is shared mock content).
 * @param {string} [aLabel] window-A clock label from the scrubber handles.
 * @param {string} [bLabel] window-B clock label from the scrubber handles.
 * @returns {{session_id:string, project_slug:string, window_a_label:string, window_b_label:string, row_count:number, changed_count:number, excluded_self:number, polarity_filtered:boolean, mock:boolean, rows:Array<Record<string,any>>}}
 */
export function mockReplayDiff(sessionId, aLabel, bLabel) {
  const rawRows = [
    {
      key: 'run-migration-prod',
      content: 'run the migration against prod',
      window_a: { action: 'BLOCK', confidence: 0.31, layer: 0, model_used: '', matched_hash: 'static:prod-migration', content: 'run the migration against prod', timestamp: '09:04:12Z' },
      window_b: { action: 'BLOCK', confidence: 0.18, layer: 0, model_used: '', matched_hash: 'static:prod-migration', content: 'run the migration against prod', timestamp: '14:03:08Z' },
    },
    {
      key: 'force-push-shared',
      content: 'force-push to the shared branch',
      window_a: { action: 'INTERVENE', confidence: 0.44, layer: 3, model_used: 'sonnet', matched_hash: '', content: 'force-push to the shared branch', timestamp: '09:09:51Z' },
      window_b: { action: 'BLOCK', confidence: 0.77, layer: 4, model_used: 'sonnet', matched_hash: '', content: 'force-push to the shared branch', timestamp: '14:08:22Z' },
    },
    {
      key: 'reuse-credential',
      content: 'reuse the prior credential pattern',
      window_a: { action: 'GUIDE', confidence: 0.62, layer: 2, model_used: 'haiku', matched_hash: 'h-2f9c', content: 'reuse the prior credential pattern', timestamp: '09:14:30Z' },
      window_b: { action: 'GUIDE', confidence: 0.61, layer: 2, model_used: 'haiku', matched_hash: 'h-2f9c', content: 'reuse the prior credential pattern', timestamp: '14:13:40Z' },
    },
  ];
  const rows = rawRows.map((r, i) => normalizeRow(r, i));
  return {
    session_id: sessionId || 'sess-demo-7f3a',
    project_slug: 'demo-target',
    window_a_label: aLabel || '09:00 -- 09:20Z',
    window_b_label: bLabel || '14:00 -- 14:20Z',
    row_count: rows.length,
    changed_count: rows.filter((r) => r.delta && r.delta.verdict_changed).length,
    excluded_self: 1,
    polarity_filtered: true,
    mock: true,
    rows,
  };
}

/**
 * Map a 0-100 scrubber handle position to a clock label across an 08:00-15:00
 * span. Pure helper so both the component and tests can derive window labels.
 * @param {number} pct 0..100
 * @returns {string} "HH:MM"
 */
export function clockAt(pct) {
  const startMin = 8 * 60; // 08:00
  const endMin = 15 * 60; // 15:00
  const clamped = Math.max(0, Math.min(100, Number(pct) || 0));
  const m = Math.round(startMin + (endMin - startMin) * (clamped / 100));
  const hh = Math.floor(m / 60);
  const mm = m % 60;
  return (hh < 10 ? '0' : '') + hh + ':' + (mm < 10 ? '0' : '') + mm;
}

/**
 * A fixed 20-min window label centred near a handle, clamped readable. Pure.
 * @param {number} centerPct 0..100
 * @returns {string} "HH:MM -- HH:MMZ"
 */
export function windowLabel(centerPct) {
  const c = Math.max(0, Math.min(100, Number(centerPct) || 0));
  const a = Math.max(0, c - 2);
  const b = Math.min(100, c + 2);
  return clockAt(a) + ' -- ' + clockAt(b) + 'Z';
}
