// BreachCartographyConstrained-data.js -- pure data helpers + mock fixture for
// the BETA feature "breach-cartography-constrained" (#5). No DOM, no Svelte, no
// network: a deterministic leaf module so the swimlane geometry + revert-rank
// math are unit-testable in isolation and the component stays lean.
//
// CONTRACT (matches reports/proposals/mockups/breach-cartography-constrained.html):
//   - A "lane" is one decision in the regression run-up. The X axis is time
//     (older left), the Y axis is one decision per lane. Each lane carries a
//     PAIRED text verdict + confidence ("BLOCK conf=1.00") AND a shape glyph so
//     hue is never the only signal (ADR-18 M5 -- color alone is never a state).
//   - The pattern shelf resolves each lane's matched_hash to its pattern node.
//   - The revert ranking is the v1 HEURISTIC: rank-score = w_conf * confidence +
//     w_freq * (1 - frequency_norm). Highest-confidence verdict on the LOWEST
//     frequency (most immature) pattern ranks first. NO counterfactual replay
//     (deferred to a future ADR-18 amendment, per the constrained-v1 proposal).
//
// POLARITY (G2 / M15): this module never assumes a session is governed. The
// caller passes the server payload (already self-excluded server-side) and an
// `excludedSelf` flag; the component disables the revert accept when the
// escalated session is the SM-self session. This module only formats data.
//
// ASCII-only (cp1252-safe): dash is "--"; no smart quotes; no em-dashes.

/** The four action verdicts, ascending severity. Index === severity rank-1. */
export const ACTION_ORDER = Object.freeze(['ALLOW', 'GUIDE', 'INTERVENE', 'BLOCK']);

/** @type {Readonly<Record<string, number>>} severity rank (1..5). */
export const ACTION_RANK = Object.freeze({
  ALLOW: 1, SUGGEST: 2, GUIDE: 3, INTERVENE: 4, BLOCK: 5,
});

/** Shape glyph class per action -- the color-blind read path (M5). */
export const ACTION_GLYPH = Object.freeze({
  ALLOW: 'glyph-allow', SUGGEST: 'glyph-allow', GUIDE: 'glyph-guide',
  INTERVENE: 'glyph-intervene', BLOCK: 'glyph-block',
});

/** Default look-back window before the alert: 10 minutes (600000 ms). */
export const WINDOW_MS = 600000;

/** Heuristic revert-rank weights (v1: confidence + pattern immaturity). */
const W_CONF = 0.6;
const W_FREQ = 0.4;

/**
 * Normalise a verdict action string to one of the known actions (uppercased).
 * Returns 'ALLOW' for anything unrecognised so a lane always paints SOMETHING
 * with a literal text label (never a bare/blank node).
 * @param {*} a
 * @returns {string}
 */
export function normAction(a) {
  const s = (a == null ? '' : String(a)).trim().toUpperCase();
  return ACTION_RANK[s] ? s : 'ALLOW';
}

/**
 * The paired verdict label for a lane: "BLOCK conf=1.00". ALWAYS text, so color
 * is never the sole signal (ADR-18 M5).
 * @param {string} action @param {number} confidence
 * @returns {string}
 */
export function verdictLabel(action, confidence) {
  const c = Number.isFinite(Number(confidence)) ? Number(confidence) : 0;
  return `${normAction(action)} conf=${c.toFixed(2)}`;
}

/** The shape-glyph class for an action (M5 redundant-with-color channel). */
export function glyphClass(action) {
  return ACTION_GLYPH[normAction(action)] || 'glyph-allow';
}

/**
 * Convert a raw timestamp to epoch MILLISECONDS. The WAL decisions/messages
 * tables store epoch SECONDS (float); a value already >= 1e12 is treated as ms.
 * @param {*} ts @returns {number|null}
 */
export function toEpochMs(ts) {
  const n = Number(ts);
  if (!Number.isFinite(n)) return null;
  return n < 1e12 ? n * 1000 : n;
}

/** m:ss formatter for the scrubber + axis (input is ms relative to t0). */
export function fmtClock(ms) {
  const s = Math.max(0, Math.round(Number(ms) / 1000));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r < 10 ? '0' : ''}${r}`;
}

/**
 * Truncate a decision message to N chars for the lane tile / tooltip. Appends
 * " ..." when truncated. Defensive against null/non-string.
 * @param {*} msg @param {number} [n]
 * @returns {string}
 */
export function clampMsg(msg, n = 100) {
  const s = (msg == null ? '' : String(msg)).replace(/\s+/g, ' ').trim();
  if (!s) return '(no message)';
  return s.length > n ? `${s.slice(0, n)} ...` : s;
}

/**
 * Build the swimlane view-model from a server (or mock) cartography payload.
 *
 * Input payload shape (server `/api/breach/cartography` OR the mock below):
 *   { alert_ts, window_ms, session_id, project_slug, excluded_self,
 *     regressed_cells:[{id,label}], maturity_delta:{cells, note},
 *     decisions:[{decision_id, action, confidence, message, matched_hash,
 *                 timestamp, hitl_note}],
 *     patterns:[{hash, level, occurrences, mature, label}] }
 *
 * Returns a render-ready model with each lane positioned in [0..1] on X (time)
 * and Y (lane order), the pattern shelf, and the heuristic-ranked revert list.
 * Pure + deterministic. Never throws on a malformed payload (degrades to empty).
 *
 * @param {Record<string, any>|null} payload
 * @returns {{
 *   alertTs:number, windowMs:number, t0:number, t1:number,
 *   sessionId:string, projectSlug:string, excludedSelf:boolean,
 *   regressedCells:Array<{id:string,label:string}>,
 *   maturityDelta:{cells:number, note:string},
 *   lanes:Array<Object>, patterns:Array<Object>,
 *   reverts:Array<Object>, empty:boolean }}
 */
export function buildModel(payload) {
  const p = payload && typeof payload === 'object' ? payload : {};
  const decisionsRaw = Array.isArray(p.decisions) ? p.decisions : [];
  const patternsRaw = Array.isArray(p.patterns) ? p.patterns : [];

  const alertTs = toEpochMs(p.alert_ts) || (decisionsRaw.length
    ? Math.max(...decisionsRaw.map((d) => toEpochMs(d && d.timestamp) || 0))
    : Date.now());
  const windowMs = Number(p.window_ms) > 0 ? Number(p.window_ms) : WINDOW_MS;
  const t1 = alertTs;
  const t0 = alertTs - windowMs;
  const span = Math.max(1, t1 - t0);

  // -- pattern shelf (occurrence drives the immaturity flag) --
  const patterns = patternsRaw
    .map((pat) => {
      if (!pat || typeof pat !== 'object') return null;
      const occ = Math.max(0, Number(pat.occurrences) || 0);
      const level = Math.max(0, Math.min(4, Number(pat.level) || 0));
      const mature = pat.mature != null ? !!pat.mature : occ >= 20;
      return {
        hash: String(pat.hash || ''),
        level,
        occurrences: occ,
        mature,
        label: clampMsg(pat.label || '', 48),
      };
    })
    .filter((x) => x && x.hash);
  const patByHash = new Map(patterns.map((pat) => [pat.hash, pat]));
  // max occurrence across the shelf -> normalise frequency for the heuristic.
  const maxOcc = patterns.reduce((mx, pat) => Math.max(mx, pat.occurrences), 1);

  // -- lanes (one decision per lane, ordered oldest-first by timestamp) --
  const sorted = decisionsRaw
    .filter((d) => d && typeof d === 'object')
    .map((d, i) => ({ d, i, ts: toEpochMs(d.timestamp) }))
    .sort((a, b) => {
      const ta = a.ts == null ? a.i : a.ts;
      const tb = b.ts == null ? b.i : b.ts;
      return ta - tb;
    });

  const laneCount = sorted.length;
  const lanes = sorted.map((entry, lane) => {
    const d = entry.d;
    const action = normAction(d.action);
    const confidence = Number.isFinite(Number(d.confidence)) ? Number(d.confidence) : 0;
    const ts = entry.ts == null ? t1 : entry.ts;
    // X in [0..1] across the window; clamp so out-of-window rows still paint.
    const xFrac = Math.max(0, Math.min(1, (ts - t0) / span));
    // Y in [0..1]; evenly spaced lanes top->bottom (older verdicts higher).
    const yFrac = laneCount > 1 ? lane / (laneCount - 1) : 0.5;
    const hash = String(d.matched_hash || '');
    return {
      decisionId: String(d.decision_id != null ? d.decision_id : `d-${lane}`),
      action,
      confidence,
      verdict: verdictLabel(action, confidence),
      glyph: glyphClass(action),
      message: clampMsg(d.message, 100),
      hash,
      hitlNote: (d.hitl_note == null ? '' : String(d.hitl_note)).trim(),
      tMs: ts,
      tRel: Math.max(0, ts - t0),
      xFrac,
      yFrac,
      rank: ACTION_RANK[action] || 1,
    };
  });

  // -- heuristic revert ranking (v1: confidence + pattern immaturity) --
  // score = W_CONF*conf + W_FREQ*(1 - occ/maxOcc). Highest-confidence verdict on
  // the lowest-frequency (most immature) pattern ranks first. Escalation verdicts
  // (GUIDE/INTERVENE/BLOCK) are the only revert candidates -- an ALLOW did not
  // cause a regression boundary. NO counterfactual replay in v1.
  const reverts = lanes
    .filter((l) => l.rank >= 3) // GUIDE/INTERVENE/BLOCK only
    .map((l) => {
      const pat = patByHash.get(l.hash);
      const occ = pat ? pat.occurrences : maxOcc;
      const freqNorm = maxOcc > 0 ? occ / maxOcc : 1;
      const score = W_CONF * l.confidence + W_FREQ * (1 - freqNorm);
      const immature = pat ? !pat.mature : false;
      const why = immature
        ? `${l.action} verdict on the ${pat ? `low-frequency (immature L${pat.level}, occ ${pat.occurrences})` : 'unmatched'} pattern ${l.hash || '(none)'}.`
        : `${l.action} verdict on the ${pat ? `mature L${pat.level} (occ ${pat.occurrences})` : 'unmatched'} pattern ${l.hash || '(none)'}.`;
      return {
        decisionId: l.decisionId,
        action: l.action,
        verdict: l.verdict,
        glyph: l.glyph,
        confidence: l.confidence,
        score: Math.round(score * 100) / 100,
        immature,
        why,
      };
    })
    .sort((a, b) => b.score - a.score)
    .map((r, i) => ({ ...r, rankNum: i + 1 }));

  const regressedCells = (Array.isArray(p.regressed_cells) ? p.regressed_cells : [])
    .map((c) => (c && typeof c === 'object'
      ? { id: String(c.id || ''), label: String(c.label || c.id || '') }
      : { id: String(c), label: String(c) }))
    .filter((c) => c.id || c.label);

  const md = p.maturity_delta && typeof p.maturity_delta === 'object' ? p.maturity_delta : {};

  return {
    alertTs: t1,
    windowMs,
    t0,
    t1,
    sessionId: String(p.session_id || ''),
    projectSlug: String(p.project_slug || ''),
    excludedSelf: !!p.excluded_self,
    regressedCells,
    maturityDelta: {
      cells: Number.isFinite(Number(md.cells)) ? Number(md.cells) : -regressedCells.length,
      note: String(md.note || ''),
    },
    lanes,
    patterns,
    reverts,
    empty: lanes.length === 0,
  };
}

/**
 * Deterministic mock cartography payload (no Date.now drift unless `now` given).
 * Mirrors the vetted mockDataSpec in the approved mockup: a NON-SM target
 * (project_slug=demo-target, excluded_self=true) so the revert accept is ENABLED
 * in the default view, with a 4-decision run-up converging on an immature-pattern
 * BLOCK at the regression boundary. Used when the live gov.db returns no rows.
 *
 * @param {{ now?:number, selfLocked?:boolean }} [opts]
 * @returns {Record<string, any>}
 */
export function mockCartographyPayload(opts = {}) {
  const now = Number.isFinite(Number(opts.now)) ? Number(opts.now) : 1718150400000;
  const selfLocked = !!opts.selfLocked;
  const alertTs = now;
  const t0 = alertTs - WINDOW_MS;
  return {
    alert_ts: alertTs / 1000, // server emits epoch SECONDS
    window_ms: WINDOW_MS,
    session_id: selfLocked ? 'sm-self-session' : 'sess-mock-7',
    project_slug: selfLocked ? 'streamManager' : 'demo-target',
    excluded_self: !selfLocked,
    mock: true,
    regressed_cells: [
      { id: 'cell-a', label: 'auth-rotation' },
      { id: 'cell-b', label: 'scope-narrowing' },
    ],
    maturity_delta: {
      cells: -2,
      note: 'v1 CONSTRAINED: coarse delta from the alert RingDelta only. Per-decision maturity is not live (FROZEN schema) -- deferred to an ADR-18 amendment.',
    },
    decisions: [
      {
        decision_id: 'd-101', action: 'ALLOW', confidence: 0.94,
        message: 'approved file-read in scope',
        matched_hash: '9f1c2a', timestamp: (t0 + 0) / 1000, hitl_note: '',
      },
      {
        decision_id: 'd-118', action: 'GUIDE', confidence: 0.92,
        message: 'guided a scope-narrowing edit',
        matched_hash: '9f1c2a', timestamp: (t0 + 142000) / 1000, hitl_note: 'operator nudged',
      },
      {
        decision_id: 'd-130', action: 'INTERVENE', confidence: 0.61,
        message: 'intervened on a rotation skip',
        matched_hash: 'b733de', timestamp: (t0 + 405000) / 1000, hitl_note: '',
      },
      {
        decision_id: 'd-141', action: 'BLOCK', confidence: 1.0,
        message: 'static-rule BLOCK at regression boundary',
        matched_hash: 'b733de', timestamp: (t0 + 588000) / 1000, hitl_note: '',
      },
    ],
    patterns: [
      { hash: '9f1c2a', level: 3, occurrences: 41, mature: true, label: 'scope-narrowing edit' },
      { hash: 'b733de', level: 1, occurrences: 6, mature: false, label: 'rotation skip' },
    ],
  };
}
