// CoverageAnalyzer.data.js -- pure data + drift math for the coverage-analyzer
// BETA feature (#10). NO Svelte, NO DOM, NO network. The component imports the
// mock fallbacks + the band-drift derivation from here so the math is unit-
// inspectable and the .svelte file stays presentation-only.
//
// CONTRACT
//   - mockCassette() / mockLive() / mockFixture() return the realistic fallback
//     distributions the component renders when the live /api/coverage/bands
//     endpoint is absent or empty (usedMockData=true). The cassette numbers
//     mirror tests/fixtures/soak_cassette_latest.jsonl verbatim: 50 routine
//     (ALLOW), 5 l2_l3, 5 l4, 10 learn_dialogue (LEARN) -- 70 envelopes.
//   - buildDrift(cassette, reference) derives the per-band signed delta
//     (cassette pct - reference pct) + a paired severity (notice/warn/alert).
//     Severity is ALWAYS surfaced WITH a literal text label by the component
//     (M4: color is never the sole signal); this module supplies both.
//
// M16 (domain-agnostic): the four bands are governance routing layers
// (ALLOW / L2-L3 / L4 / LEARN), NOT monitored-project vocabulary. No JOB-IDs,
// role names, or project slugs appear here -- a project's identity is rendered
// from server data by the live endpoint, never hard-coded.
//
// ASCII-only (cp1252-safe): dash rendered as "--". No smart quotes / em-dash.

/** Drift threshold (percent) above which a band is flagged WATCH. */
export const THRESHOLD = 10.0;

/** Magnitude (percent) above which a band escalates from WATCH to DRIFT. */
export const ALERT_THRESHOLD = 22.0;

/**
 * The canonical four-band order + display labels. Layer bins mirror
 * tools/cassette_record.py:_KIND_TO_LAYER (routine/learn -> 0, l2_l3 -> 2,
 * l4 -> 4). Kept as one frozen table so the chart, the warnings, and the
 * server histogram agree on order + naming.
 * @type {ReadonlyArray<{key:string,label:string,layer:number}>}
 */
export const BANDS = Object.freeze([
  { key: 'allow', label: 'ALLOW', layer: 0 },
  { key: 'l2_l3', label: 'L2/L3', layer: 2 },
  { key: 'l4', label: 'L4', layer: 4 },
  { key: 'learn', label: 'LEARN', layer: 0 },
]);

/**
 * Realistic mock cassette composition -- the fallback when the server returns
 * nothing. Mirrors soak_cassette_latest.jsonl (50/5/5/10 of 70).
 * @returns {{source:string,fixture:string,total:number,bands:Array<{key:string,label:string,layer:number,count:number,pct:number}>}}
 */
export function mockCassette() {
  return {
    source: 'cassette',
    fixture: 'soak_cassette_latest.jsonl',
    total: 70,
    bands: [
      { key: 'allow', label: 'ALLOW', layer: 0, count: 50, pct: 71.4 },
      { key: 'l2_l3', label: 'L2/L3', layer: 2, count: 5, pct: 7.1 },
      { key: 'l4', label: 'L4', layer: 4, count: 5, pct: 7.1 },
      { key: 'learn', label: 'LEARN', layer: 0, count: 10, pct: 14.3 },
    ],
  };
}

/**
 * Realistic mock LIVE composition -- a rolling 1000-decision window over
 * non-SM sessions, polarity-filtered (SM-self excluded). The deltas vs the
 * mock cassette deliberately trip the L2/L3 WATCH band so the drawer is
 * testable end-to-end without a live gov.db.
 * @returns {{source:string,window:number,total:number,polarity_filtered:boolean,excluded_self_rows:number,bands:Array<{key:string,label:string,layer:number,count:number,pct:number}>}}
 */
export function mockLive() {
  return {
    source: 'live',
    window: 1000,
    total: 842,
    polarity_filtered: true,
    excluded_self_rows: 17,
    bands: [
      { key: 'allow', label: 'ALLOW', layer: 0, count: 505, pct: 60.0 },
      { key: 'l2_l3', label: 'L2/L3', layer: 2, count: 177, pct: 21.0 },
      { key: 'l4', label: 'L4', layer: 4, count: 118, pct: 14.0 },
      { key: 'learn', label: 'LEARN', layer: 0, count: 42, pct: 5.0 },
    ],
  };
}

/**
 * Realistic mock FIXTURE composition -- a hand-supplied live fixture to A/B
 * against the cassette (the "Compare fixture" mode).
 * @returns {{source:string,fixture_id:string,total:number,polarity_filtered:boolean,excluded_self_rows:number,bands:Array<{key:string,label:string,layer:number,count:number,pct:number}>}}
 */
export function mockFixture() {
  return {
    source: 'fixture',
    fixture_id: 'fx-2026-06-09-rollup',
    total: 410,
    polarity_filtered: true,
    excluded_self_rows: 4,
    bands: [
      { key: 'allow', label: 'ALLOW', layer: 0, count: 246, pct: 60.0 },
      { key: 'l2_l3', label: 'L2/L3', layer: 2, count: 90, pct: 22.0 },
      { key: 'l4', label: 'L4', layer: 4, count: 57, pct: 13.9 },
      { key: 'learn', label: 'LEARN', layer: 0, count: 17, pct: 4.1 },
    ],
  };
}

/**
 * Coerce a raw server payload into the canonical band shape, filling any band
 * the server omitted with a zero row so the chart always renders all four. A
 * null/garbage payload yields an empty (total 0) set the caller can treat as
 * "no data" and swap for a mock.
 * @param {any} raw
 * @param {string} fallbackSource
 * @returns {{source:string,total:number,bands:Array<Record<string,any>>,[k:string]:any}|null}
 */
export function normalizeSet(raw, fallbackSource) {
  if (!raw || typeof raw !== 'object') return null;
  const inBands = Array.isArray(raw.bands) ? raw.bands : [];
  const byKey = new Map(inBands.map((b) => [b && b.key, b]));
  const bands = BANDS.map((def) => {
    const b = byKey.get(def.key) || {};
    const count = Number(b.count) || 0;
    const pct = Number.isFinite(Number(b.pct)) ? Number(b.pct) : 0;
    return { key: def.key, label: def.label, layer: def.layer, count, pct };
  });
  return {
    ...raw,
    source: raw.source || fallbackSource,
    total: Number(raw.total) || 0,
    bands,
  };
}

/** @param {{bands:Array<{key:string}>}} set @param {string} key */
export function bandByKey(set, key) {
  if (!set || !Array.isArray(set.bands)) return null;
  return set.bands.find((b) => b.key === key) || null;
}

/**
 * Severity for a signed delta (paired with a text label by the component).
 *   notice -> "OK", warn -> "WATCH", alert -> "DRIFT".
 * @param {number} deltaPct
 * @returns {'notice'|'warn'|'alert'}
 */
export function severityFor(deltaPct) {
  const mag = Math.abs(Number(deltaPct) || 0);
  if (mag >= ALERT_THRESHOLD) return 'alert';
  if (mag >= THRESHOLD) return 'warn';
  return 'notice';
}

/** @param {'notice'|'warn'|'alert'} sev @returns {string} the literal badge text (M4). */
export function sevLabel(sev) {
  return sev === 'alert' ? 'DRIFT' : sev === 'warn' ? 'WATCH' : 'OK';
}

/** @param {number} n @returns {string} a signed, 1-decimal percent string. */
export function signedPct(n) {
  const v = Number(n) || 0;
  return `${v > 0 ? '+' : ''}${v.toFixed(1)}%`;
}

/**
 * Derive the per-band drift rows: cassette vs the active reference (live OR
 * fixture). delta = cassette pct - reference pct; severity is paired with a
 * text label by the caller.
 * @param {{bands:Array<Record<string,any>>}} cassette
 * @param {{bands:Array<Record<string,any>>}} reference
 * @returns {Array<{key:string,label:string,layer:number,cassettePct:number,cassetteCount:number,refPct:number,refCount:number,delta_pct:number,severity:'notice'|'warn'|'alert'}>}
 */
export function buildDrift(cassette, reference) {
  const cas = cassette && Array.isArray(cassette.bands) ? cassette.bands : [];
  return cas.map((cb) => {
    const rb = bandByKey(reference, cb.key) || { pct: 0, count: 0 };
    const delta = Math.round((Number(cb.pct) - Number(rb.pct)) * 10) / 10;
    return {
      key: cb.key,
      label: cb.label,
      layer: cb.layer,
      cassettePct: Number(cb.pct) || 0,
      cassetteCount: Number(cb.count) || 0,
      refPct: Number(rb.pct) || 0,
      refCount: Number(rb.count) || 0,
      delta_pct: delta,
      severity: severityFor(delta),
    };
  });
}

/**
 * The worst (largest-magnitude) drift row -- drives the top one-line verdict.
 * @param {Array<{delta_pct:number}>} drift
 * @returns {any|null}
 */
export function worstDrift(drift) {
  if (!Array.isArray(drift) || drift.length === 0) return null;
  return drift
    .slice()
    .sort((a, b) => Math.abs(b.delta_pct) - Math.abs(a.delta_pct))[0];
}

/**
 * Human remediation note for a band (re-record / compare-fixture hint).
 * @param {{label:string,severity:string,delta_pct:number}} row
 * @param {string} refLabel
 * @returns {string}
 */
export function remediationFor(row, refLabel) {
  if (row.severity === 'notice') {
    return `Within +/-${THRESHOLD}%. ${row.label} is representative against ${refLabel}.`;
  }
  const dir = row.delta_pct < 0 ? 'under-represents' : 'over-represents';
  const verb = row.delta_pct < 0 ? 'miss' : 'over-weight';
  return (
    `Cassette ${dir} ${row.label} by ~${Math.abs(row.delta_pct).toFixed(0)}%. ` +
    `Tier-1 replay may ${verb} this path. Re-record via cassette_record.py, ` +
    `or compare a live fixture.`
  );
}
