// DecisionOracle-data.js -- helper module for the BETA feature "decision-oracle"
// (#12: inline pattern pedigree + ancestral replay). Self-contained, lives under
// lib/components/beta/ with the DecisionOracle- prefix so it never collides with
// a shared file. NO shared-file imports beyond the read-only api transport.
//
// CONTRACT
//   - Pure data: a fetch wrapper for the additive read endpoint
//     GET /api/patterns/{hash}/pedigree, plus a realistic MOCK payload the
//     component falls back to when live gov.db pedigree is absent (so the pane
//     is always testable). NO pollers, NO timers, NO SSE. The component owns all
//     lifecycle; this module is stateless helpers.
//   - G2 polarity: this module never decides self-exclusion -- the SERVER 404s
//     SM-self pattern hashes, and the component suppresses the glyph for SM-self
//     rows by project_slug/session before it ever calls fetchPedigree(). This
//     helper only shapes/normalises whatever the (already-self-excluded) server
//     returns.
//   - M16 domain-agnostic: no monitored-project vocabulary. The mock content is
//     generic governance/tooling phrasing; every governed identifier the real
//     path renders comes from server DATA.
//   - ASCII-only (cp1252-safe): dash is "--"; no smart quotes / box-drawing.

// Promotion ladder (mirrors src/stream_manager/decision_graph.py
// PROMOTION_THRESHOLDS): occurrences needed to climb OFF a given level. L4 is
// terminal. Kept here as a read-only copy so the meter ("X / N toward L<next>")
// renders without a server round-trip; the server returns the authoritative
// level/occurrences and we only derive the toward-next text from them.
export const PROMOTION_THRESHOLDS = Object.freeze({ 0: 3, 1: 5, 2: 10, 3: 20 });

export const MAX_LEVEL = 4;

/**
 * Derive the "toward next promotion" meter from the authoritative level +
 * occurrences the server returns. Returns a stable, never-empty descriptor so
 * the pane always has paired TEXT (never a bare bar). At L4 the pattern is
 * terminal -- we say so in words rather than render a misleading 100%.
 * @param {number} level       current rung 0..4
 * @param {number} occurrences total observations on this pattern
 * @returns {{ atMax:boolean, nextLevel:number|null, have:number, need:number,
 *   pct:number, text:string }}
 */
export function towardNext(level, occurrences) {
  const lvl = clampLevel(level);
  const occ = Number.isFinite(Number(occurrences)) ? Math.max(0, Math.floor(Number(occurrences))) : 0;
  if (lvl >= MAX_LEVEL) {
    return { atMax: true, nextLevel: null, have: occ, need: occ, pct: 100, text: 'L4 -- top rung reached' };
  }
  const need = PROMOTION_THRESHOLDS[lvl] || 0;
  const have = Math.min(occ, need);
  const pct = need > 0 ? Math.round((have / need) * 100) : 0;
  return {
    atMax: false,
    nextLevel: lvl + 1,
    have,
    need,
    pct,
    text: `${have} / ${need} toward L${lvl + 1}`,
  };
}

/** @param {unknown} v @returns {number} a level coerced into 0..4 */
export function clampLevel(v) {
  const n = Math.floor(Number(v));
  if (!Number.isFinite(n)) return 0;
  return Math.min(MAX_LEVEL, Math.max(0, n));
}

/**
 * Normalise a raw server pedigree payload (or a mock) into the exact shape the
 * component renders. Defensive: any missing field degrades to a calm default so
 * a partial server row never throws in the template. Returns null only for a
 * genuinely empty/absent payload (the component then shows its empty state).
 * @param {any} raw
 * @returns {null | {
 *   pattern_hash:string, hash_short:string, level:number, success_rate:number,
 *   successes:number, occurrences:number, age_days:number|null,
 *   first_seen_label:string, last_reinforced_label:string,
 *   overfit:{ flagged:boolean, pct:number, profile:string|null },
 *   meter:ReturnType<typeof towardNext>,
 *   observations:Array<{ seq:number, ts_label:string, intent:string,
 *     fingerprint:string, match_pct:number|null }> }}
 */
export function normalisePedigree(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const hash = String(raw.pattern_hash || raw.hash || '').trim();
  if (!hash) return null;

  const level = clampLevel(raw.level);
  const occurrences = intOr(raw.occurrences, 0);
  const successes = intOr(raw.successes, 0);
  const success_rate =
    raw.success_rate != null
      ? clamp01(Number(raw.success_rate))
      : occurrences > 0
        ? clamp01(successes / occurrences)
        : 0;

  const overfitRaw = raw.overfit && typeof raw.overfit === 'object' ? raw.overfit : {};
  const overfit = {
    flagged: !!overfitRaw.flagged,
    pct: intOr(overfitRaw.pct, 0),
    profile: overfitRaw.profile ? String(overfitRaw.profile) : null,
  };

  const observations = Array.isArray(raw.observations)
    ? raw.observations.map((o, i) => ({
        seq: intOr(o && o.seq, i + 1),
        ts_label: String((o && o.ts_label) || '--'),
        intent: String((o && o.intent) || 'unlabelled'),
        fingerprint: String((o && o.fingerprint) || ''),
        match_pct:
          o && o.match_pct != null && Number.isFinite(Number(o.match_pct))
            ? Math.round(Number(o.match_pct))
            : null,
      }))
    : [];

  return {
    pattern_hash: hash,
    hash_short: hash.slice(0, 8),
    level,
    success_rate,
    successes,
    occurrences,
    age_days: raw.age_days != null && Number.isFinite(Number(raw.age_days)) ? Math.floor(Number(raw.age_days)) : null,
    first_seen_label: String(raw.first_seen_label || '--'),
    last_reinforced_label: String(raw.last_reinforced_label || '--'),
    overfit,
    meter: towardNext(level, occurrences),
    observations,
  };
}

/** @param {unknown} v @param {number} d @returns {number} */
function intOr(v, d) {
  const n = Math.floor(Number(v));
  return Number.isFinite(n) ? n : d;
}
/** @param {number} v @returns {number} clamped to 0..1 */
function clamp01(v) {
  if (!Number.isFinite(v)) return 0;
  return Math.min(1, Math.max(0, v));
}

/**
 * Fetch the pattern pedigree for a matched_hash from the additive read endpoint
 * GET /api/patterns/{hash}/pedigree. Read-only. Throws on non-2xx (incl. the
 * G2 404 for an SM-self pattern) so the caller can fall back to mock data and/or
 * show the calm empty state -- it NEVER reads an error as a populated pedigree.
 * @param {string} hash a decision.matched_hash (pattern hash)
 * @returns {Promise<any>} the raw server JSON (caller normalises)
 */
export async function fetchPedigree(hash) {
  const h = encodeURIComponent(String(hash || '').trim());
  const res = await fetch(`/api/patterns/${h}/pedigree`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`GET /api/patterns/${h}/pedigree -> ${res.status} ${res.statusText}`);
  }
  return res.json();
}

/**
 * A realistic MOCK pedigree (the vetted mockDataSpec from the approved mockup,
 * decision dec_8a31 / pattern 9f2c1a77...). Used when live gov.db has no
 * pedigree for the hash (fresh clone, pre-soak, or the endpoint 404s a non-SM
 * hash that simply has no graph_patterns row yet). Domain-agnostic phrasing.
 * @param {string} [hash] optional real hash to surface instead of the sample
 * @returns {ReturnType<typeof normalisePedigree>}
 */
export function mockPedigree(hash) {
  const h = (hash && String(hash).trim()) || '9f2c1a77b4e03d56';
  return normalisePedigree({
    pattern_hash: h,
    level: 2,
    occurrences: 47,
    successes: 39,
    success_rate: 39 / 47,
    age_days: 6,
    first_seen_label: 'first seen Jun 5',
    last_reinforced_label: 'today, <1m ago',
    overfit: { flagged: true, pct: 91, profile: 'doc-writer' },
    observations: [
      {
        seq: 1,
        ts_label: 'Jun 5, 09:02',
        intent: 'test-gate',
        fingerprint: 'run the full integration suite before tagging the rel...',
        match_pct: 55,
      },
      {
        seq: 2,
        ts_label: 'Jun 7, 14:20',
        intent: 'test-gate',
        fingerprint: 'kick off the integration tests, do not skip the slow o...',
        match_pct: 71,
      },
      {
        seq: 3,
        ts_label: 'Jun 9, 11:48',
        intent: 'test-gate',
        fingerprint: 'running integration before the version bump as usual',
        match_pct: 83,
      },
    ],
  });
}
