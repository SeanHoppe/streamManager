// ConfidenceChip-data.js -- pure data helpers for the BETA "confidence-chip"
// feature (#18 Operator Co-Pilot Confidence Chip). NO Svelte, NO network, NO
// side effects: this module only derives view-model shapes from data the chip
// already has (the pending envelope) or from the existing
// /api/decisions/{id}/suggestions response (consumed via the api.js
// getDecisionSuggestions helper -- NO new endpoint).
//
// M16 (domain-agnostic): every governed identifier (action verb, source key) is
// carried through verbatim from data. The only literal vocabulary here is the
// FROZEN SuggestionWeights source-enum keys
// (graph_pattern / hitl_override / static_rule / project_context) which are
// generic governance taxonomy, never monitored-project vocabulary.
//
// ASCII-only (cp1252-safe): dash rendered as "--", no smart quotes, no
// em-dashes, no box-drawing.

// The four FROZEN source keys (decision_suggestions.SuggestionWeights), in the
// canonical display order. Rendered with a literal label beside every bar so the
// breakdown is never carried by color alone (M4).
export const SOURCE_KEYS = [
  'graph_pattern',
  'hitl_override',
  'static_rule',
  'project_context',
];

/**
 * Clamp a numeric confidence into a whole-percent 0..100, or null when the
 * input is not a finite number. Tolerates either a 0..1 float (the
 * GovDecision.confidence / Candidate.confidence convention) or an already-
 * scaled 0..100 value (defensive -- some envelopes pre-scale).
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
 * Resolve the top recommended action verb from the pending envelope, tolerant
 * of field names (M16 -- rendered FROM DATA, never invented). Returns a short
 * upper-cased verb string, or '' when nothing usable is present.
 * @param {Record<string, any>} pending
 * @returns {string}
 */
export function topActionVerb(pending) {
  const raw = (
    pending?.action ??
    pending?.recommended_action ??
    pending?.suggested_action ??
    ''
  )
    .toString()
    .trim();
  return raw;
}

/**
 * Resolve the chip's headline confidence from the pending envelope. Prefers an
 * explicit confidence field; falls back to a nested bias-hint confidence; else
 * null (the caller then uses suggestions or mock).
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
 * field names. Returns null when no id is resolvable (then the chip uses mock).
 * @param {Record<string, any>} pending
 * @returns {string|null}
 */
export function decisionIdOf(pending) {
  const id =
    pending?.decision_id ??
    pending?.id ??
    pending?.pending_id ??
    null;
  return id == null ? null : String(id);
}

/**
 * Build the breakdown view-model from the existing suggestions response (an
 * array of Candidate.to_json() shapes). The top candidate's `sourced_from` list
 * is mapped to weighted bars; weights come from the FROZEN default
 * SuggestionWeights blend (graph_pattern .40 / hitl_override .35 /
 * static_rule .15 / project_context .10) intersected with the sources the
 * winning candidate actually drew on, then renormalised so the visible bars sum
 * to 100. This is presentation-only: it re-displays values the engine already
 * computed and NEVER re-derives or overrides a verdict.
 *
 * @param {Array<Record<string, any>>} suggestions
 * @returns {{
 *   verb:string,
 *   confidencePct:number|null,
 *   precedent:number|null,
 *   rationale:string,
 *   bars:Array<{key:string,pct:number}>,
 *   live:boolean
 * } | null}  null when the suggestions array yields no usable top candidate.
 */
export function breakdownFromSuggestions(suggestions) {
  if (!Array.isArray(suggestions) || suggestions.length === 0) return null;
  // The server returns the array sorted by descending blended score; the top is
  // index 0. Be defensive in case it is unsorted.
  const top = suggestions.reduce((best, c) => {
    if (!best) return c;
    const bs = Number(best.score ?? best.confidence ?? 0);
    const cs = Number(c?.score ?? c?.confidence ?? 0);
    return cs > bs ? c : best;
  }, null);
  if (!top) return null;

  const verb = (top.action ?? '').toString().trim();
  const sources = Array.isArray(top.sourced_from) ? top.sourced_from : [];
  const bars = barsForSources(sources);

  return {
    verb,
    confidencePct: toPct(top.confidence),
    precedent:
      Number.isFinite(Number(top.historical_precedent_count))
        ? Number(top.historical_precedent_count)
        : null,
    rationale: (top.rationale ?? '').toString().trim(),
    bars,
    live: true,
  };
}

// FROZEN default SuggestionWeights blend (decision_suggestions._DEFAULT_WEIGHTS)
// -- the static presentation weights for the breakdown bars. Display-only.
const DEFAULT_BLEND = {
  graph_pattern: 0.4,
  hitl_override: 0.35,
  static_rule: 0.15,
  project_context: 0.1,
};

/**
 * Map a candidate's `sourced_from` list to renormalised percentage bars in the
 * canonical SOURCE_KEYS order. Only the sources the candidate actually used are
 * shown; their default-blend weights are renormalised to sum to 100 so the
 * visible bars are honest. When `sourced_from` is empty we fall back to the full
 * default blend (so the operator still sees the standard weighting).
 * @param {string[]} sources
 * @returns {Array<{key:string,pct:number}>}
 */
export function barsForSources(sources) {
  const used = Array.isArray(sources) && sources.length
    ? SOURCE_KEYS.filter((k) => sources.includes(k))
    : SOURCE_KEYS.slice();
  const present = used.length ? used : SOURCE_KEYS.slice();
  const total = present.reduce((s, k) => s + (DEFAULT_BLEND[k] ?? 0), 0) || 1;
  return present.map((k) => ({
    key: k,
    pct: Math.round(((DEFAULT_BLEND[k] ?? 0) / total) * 100),
  }));
}

/**
 * Realistic mock breakdown used ONLY when live suggestions are absent (no
 * decision id, server unavailable, or empty array) so the chip is testable
 * offline. The caller sets usedMockData=true and surfaces the mock-state label.
 * Values mirror the approved mockup (78% / recommend APPROVE / the default
 * blend) and stay domain-agnostic.
 * @returns {{
 *   verb:string, confidencePct:number, precedent:number, rationale:string,
 *   bars:Array<{key:string,pct:number}>, live:boolean
 * }}
 */
export function mockBreakdown() {
  return {
    verb: 'approve',
    confidencePct: 78,
    precedent: 12,
    rationale: 'matches prior approvals on a recency-decayed pattern',
    bars: SOURCE_KEYS.map((k) => ({
      key: k,
      pct: Math.round((DEFAULT_BLEND[k] ?? 0) * 100),
    })),
    live: false,
  };
}
