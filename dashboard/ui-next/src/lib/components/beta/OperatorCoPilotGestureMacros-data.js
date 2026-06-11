// OperatorCoPilotGestureMacros-data.js -- pure data helpers for the BETA
// "operator-co-pilot-gesture-macros" feature (#17 Operator Co-Pilot: one-tap
// ranked next-action macro palette). NO Svelte, NO network, NO side effects:
// this module only derives a ranked-actions view-model from data the palette
// already has (the pending envelope) or from the existing
// /api/decisions/{id}/suggestions response (consumed by the host via the api.js
// getDecisionSuggestions helper -- NO new endpoint). The palette is the
// multi-action superset of the #18 ConfidenceChip and reuses its data plumbing.
//
// MACRO SEMANTICS (mockup-locked): exactly ONE macro is binding (APPROVE --
// routes the host's existing commit('approve', ...) path, the same surface the
// row's Approve button calls). TUNE / ESCALATE / SNOOZE are ADVISORY: they
// pre-stage existing client affordances (the OVERRIDE picker / the override
// control focus / a client-side localStorage snooze) and mutate NOTHING
// server-side. No new bus envelope, no new disposition string.
//
// M16 (domain-agnostic): every governed identifier (action verb, precedent
// count, confidence) is carried through verbatim from data. The macro KEYS
// (APPROVE / TUNE / ESCALATE / SNOOZE) are generic operator-intent taxonomy,
// never monitored-project vocabulary.
//
// ASCII-only (cp1252-safe): dash rendered as "--", no smart quotes, no
// em-dashes, no box-drawing.

/**
 * Clamp a numeric confidence into a whole-percent 0..100, or null when the
 * input is not a finite number. Tolerates either a 0..1 float (the
 * GovDecision.confidence convention) or an already-scaled 0..100 value.
 * @param {unknown} raw
 * @returns {number|null}
 */
export function toPct(raw) {
  const n = Number(raw);
  if (!Number.isFinite(n)) return null;
  const scaled = n > 0 && n <= 1 ? n * 100 : n;
  return Math.min(100, Math.max(0, Math.round(scaled)));
}

/**
 * Confidence -> literal WORD (the same number rendered as a word so the signal
 * survives with color stripped -- M4/M5 paired label). >=75 high, >=60
 * moderate, else low. Mirrors the approved mockup confWord().
 * @param {number|null} pct
 * @returns {'high'|'moderate'|'low'|'unknown'}
 */
export function confWord(pct) {
  if (pct == null || !Number.isFinite(Number(pct))) return 'unknown';
  if (pct >= 75) return 'high';
  if (pct >= 60) return 'moderate';
  return 'low';
}

/**
 * Resolve the top recommended action verb from the pending envelope, tolerant
 * of field names (M16 -- rendered FROM DATA, never invented). Returns a short
 * verb string, or '' when nothing usable is present.
 * @param {Record<string, any>} pending
 * @returns {string}
 */
export function topActionVerb(pending) {
  return (
    pending?.action ??
    pending?.recommended_action ??
    pending?.suggested_action ??
    ''
  )
    .toString()
    .trim();
}

/**
 * Resolve the headline confidence from the pending envelope. Prefers an explicit
 * confidence field; falls back to a nested bias-hint confidence; else null.
 * @param {Record<string, any>} pending
 * @returns {number|null}
 */
export function envelopeConfidence(pending) {
  return toPct(
    pending?.confidence ??
      pending?.advisory_confidence ??
      pending?.bias_hint?.confidence ??
      null,
  );
}

/**
 * The decision id to query /api/decisions/{id}/suggestions for, tolerant of
 * field names. Returns null when no id is resolvable (then the palette uses
 * mock / a deterministic fallback ranking).
 * @param {Record<string, any>} pending
 * @returns {string|null}
 */
export function decisionIdOf(pending) {
  const id = pending?.decision_id ?? pending?.id ?? pending?.pending_id ?? null;
  return id == null ? null : String(id);
}

// The fixed macro catalogue (operator-intent taxonomy, domain-agnostic). Each
// macro carries:
//   key       -- stable id (used for keying + the host routing switch)
//   label     -- operator-facing verb (rendered FROM this constant, generic)
//   binding   -- true ONLY for APPROVE (routes the host commit). All others are
//                advisory (pre-stage existing affordances; no server write).
//   route     -- the host-side routing token the component switches on.
// The ORDER here is the deterministic-fallback rank order (high-confidence +
// high-frequency = APPROVE; medium boundary = TUNE; novel = ESCALATE; low SNR =
// SNOOZE) -- the same hardcoded operator-intent model the proposal specifies.
export const MACRO_CATALOGUE = [
  { key: 'APPROVE',  label: 'Approve',             binding: true,  route: 'commit-approve' },
  { key: 'TUNE',     label: 'Tune threshold',      binding: false, route: 'prestage-override' },
  { key: 'ESCALATE', label: 'Escalate / hand off', binding: false, route: 'focus-escalate' },
  { key: 'SNOOZE',   label: 'Snooze 5m',           binding: false, route: 'client-snooze' },
];

/**
 * Build the ranked next-action view-model from the existing suggestions response
 * (an array of Candidate.to_json() shapes). The top candidate's blended
 * confidence anchors APPROVE; the lower macros derive deterministically-decayed
 * confidences off the same number so the ranking is always honest about being a
 * derived heuristic (state tag = "LIVE"). This is presentation-only: it
 * re-displays values the engine already computed and NEVER re-derives or
 * overrides a verdict.
 *
 * @param {Array<Record<string, any>>} suggestions
 * @param {Record<string, any>} [pending]
 * @returns {{
 *   pending_id:(string|number|null),
 *   source:'live', ranker:'deterministic-fallback',
 *   actions:Array<{key:string,label:string,confidence:number,binding:boolean,route:string,rationale:string,precedent:(number|null)}>
 * } | null}  null when the suggestions array yields no usable top candidate.
 */
export function rankedFromSuggestions(suggestions, pending = {}) {
  if (!Array.isArray(suggestions) || suggestions.length === 0) return null;
  const top = suggestions.reduce((best, c) => {
    if (!best) return c;
    const bs = Number(best.score ?? best.confidence ?? 0);
    const cs = Number(c?.score ?? c?.confidence ?? 0);
    return cs > bs ? c : best;
  }, null);
  if (!top) return null;

  const topPct = toPct(top.confidence);
  if (topPct == null) return null;

  const precedent = Number.isFinite(Number(top.historical_precedent_count))
    ? Number(top.historical_precedent_count)
    : null;
  const verb = (top.action ?? topActionVerb(pending) ?? 'approve').toString().trim() || 'approve';
  const rationale = (top.rationale ?? '').toString().trim();

  // Deterministic decay for the lower-ranked advisory macros. These are derived
  // heuristic confidences (not separate engine verdicts) -- the state tag stays
  // honest by labelling the ranker "deterministic-fallback".
  const decay = [0, 14, 27, 34]; // pct points subtracted by rank
  const actions = MACRO_CATALOGUE.map((m, i) => {
    const c = Math.max(0, Math.min(100, topPct - decay[i]));
    return {
      key: m.key,
      label: m.label,
      confidence: c / 100,
      binding: m.binding,
      route: m.route,
      rationale:
        m.key === 'APPROVE'
          ? (rationale || (precedent != null ? `matches ${precedent} prior approvals on this pattern` : 'matches the recommended verdict'))
          : RATIONALE_BY_KEY[m.key],
      precedent: m.key === 'APPROVE' ? precedent : PRECEDENT_BY_KEY[m.key],
    };
  });

  return {
    pending_id: decisionIdOf(pending),
    source: 'live',
    ranker: 'deterministic-fallback',
    actions,
  };
}

// Per-macro advisory rationale (generic governance taxonomy, domain-agnostic).
const RATIONALE_BY_KEY = {
  TUNE: 'boundary case -- pre-fills the OVERRIDE picker (you confirm)',
  ESCALATE: 'novel pattern, not seen before this session',
  SNOOZE: 'low signal-to-noise -- defer without resolving',
};
// Indicative precedent counts for the advisory macros (mock parity).
const PRECEDENT_BY_KEY = { TUNE: 31, ESCALATE: 0, SNOOZE: 7 };

/**
 * Realistic mock ranking used ONLY when live suggestions are absent (no decision
 * id, server unavailable, or empty array) so the palette is testable offline.
 * The caller sets usedMockData=true and surfaces the SAMPLE DATA state tag.
 * Values mirror the approved mockup (92 / 78 / 65 / 58, APPROVE binding) and
 * stay domain-agnostic.
 * @param {Record<string, any>} [pending]
 * @returns {{
 *   pending_id:(string|number|null),
 *   source:'mock', ranker:'deterministic-fallback',
 *   actions:Array<{key:string,label:string,confidence:number,binding:boolean,route:string,rationale:string,precedent:(number|null)}>
 * }}
 */
export function mockRanked(pending = {}) {
  return {
    pending_id: decisionIdOf(pending),
    source: 'mock',
    ranker: 'deterministic-fallback',
    actions: [
      { key: 'APPROVE',  label: 'Approve',             confidence: 0.92, binding: true,  route: 'commit-approve',   rationale: 'matches 214 prior approvals on this pattern', precedent: 214 },
      { key: 'TUNE',     label: 'Tune threshold',      confidence: 0.78, binding: false, route: 'prestage-override', rationale: RATIONALE_BY_KEY.TUNE,     precedent: 31 },
      { key: 'ESCALATE', label: 'Escalate / hand off', confidence: 0.65, binding: false, route: 'focus-escalate',    rationale: RATIONALE_BY_KEY.ESCALATE, precedent: 0 },
      { key: 'SNOOZE',   label: 'Snooze 5m',           confidence: 0.58, binding: false, route: 'client-snooze',     rationale: RATIONALE_BY_KEY.SNOOZE,   precedent: 7 },
    ],
  };
}

// localStorage key prefix for the client-side SNOOZE (advisory; mutates nothing
// server-side -- it just dims the row locally for a window).
export const SNOOZE_LS_PREFIX = 'sm.next.coPilotSnooze.';

/**
 * Persist a client-side snooze marker for a row id (advisory -- no server
 * write). Best-effort; private-mode safe.
 * @param {string|number|null} rowId
 * @param {number} [minutes]
 */
export function persistSnooze(rowId, minutes = 5) {
  if (rowId == null || typeof localStorage === 'undefined') return;
  try {
    const until = Date.now() + Math.max(1, minutes) * 60000;
    localStorage.setItem(SNOOZE_LS_PREFIX + String(rowId), JSON.stringify({ until }));
  } catch {
    /* private-mode / quota -- non-fatal; the snooze just won't persist */
  }
}
