// AmbientSoakTask-data.js -- pure (no-DOM, no-fetch) helpers + mock fixtures for
// the BETA feature "ambient-soak-task" (#2: a calm AMBIENT OK/WARN polarity
// badge in the AppShell footer + a read-only history drawer with a cadence strip
// and a newest-first ledger of recent ambient soak runs).
//
// Kept separate from the .svelte component so the verdict / flagged / cadence /
// format math is unit-testable in isolation and the Svelte file stays
// presentation-focused (mirrors SoakPanel-data.js / CoverageAnalyzer.data.js).
//
// CONSTRAINED ADDITIVE: this module reads NOTHING and spawns NOTHING. The actual
// ambient soak runs are launched by an out-of-process operator/main-thread Cron
// job (the long-task rule); the dashboard only READS the additive ambient_runs
// table via two additive GET endpoints. The Cron scheduler itself is DEFERRED to
// a clearly-labelled non-functional "from CLI" affordance in the component.
//
// DOMAIN-AGNOSTIC (M16): every identifier in the mock fixtures is a generic,
// invented governance slug -- NO monitored-project vocabulary, NO JOB-IDs, NO
// role names. Identity is data; the only literals here are the UI's own copy and
// SM's OWN self-exclude markers (configuration, not target vocabulary).
//
// POLARITY (G2/M15): the server endpoints filter SM-self (project_slug NOT IN
// the SM slug set AND session_id != SM_OWN_SESSION_ID) and surface the dropped
// tally as excluded_self so self-exclusion is a VISIBLE feature, not a silent
// filter. The mock status carries a non-zero excluded_self so the visible
// readout is demonstrable headless.
//
// ADR-18 M4 (paired label+color): every verdict here returns a LITERAL text WORD
// (AMBIENT OK / POLARITY CHECK / PASS / FAIL) -- color is NEVER the only signal.
//
// ASCII-only (cp1252-safe): dash is "--". No smart quotes, no em-dashes.

/** SM-own project slug set echoed client-side (mirrors the server exclude). */
export const SELF_SLUGS = new Set(['streammanager']);

/**
 * Is this ambient-run row SM-self (by project_slug or by matching the injected
 * own session id)? Self rows are defense-in-depth filtered from the ledger even
 * on the mock path (the server is the durable gate; this is the client mirror).
 * @param {Record<string, any>} r
 * @param {string|null} ownSessionId
 * @returns {boolean}
 */
export function isSelfRun(r, ownSessionId) {
  if (!r) return false;
  const slug = String(r.project_slug || '').trim().toLowerCase();
  if (slug && SELF_SLUGS.has(slug)) return true;
  const sid = r.session_id != null ? r.session_id : r.id;
  if (ownSessionId && sid != null && String(sid) === String(ownSessionId)) return true;
  return false;
}

/**
 * A run is "flagged" if its polarity check failed OR it surfaced any coverage
 * gap. This is the M4 driver for the amber severity tick beside the PASS/FAIL
 * WORD (never color alone).
 * @param {Record<string, any>} r
 * @returns {boolean}
 */
export function isFlagged(r) {
  if (!r) return false;
  const violated = r.polarity_violation === true || r.polarity_violation === 1
    || Number(r.polarity_pass) === 0;
  const gaps = Array.isArray(r.coverage_gaps) ? r.coverage_gaps : [];
  return violated || gaps.length > 0;
}

/**
 * Did this run's polarity check PASS? polarity_pass is the authoritative gate
 * (true / 1 = PASS). A null/absent run is treated as not-pass (resting NONE).
 * @param {Record<string, any>} r
 * @returns {boolean}
 */
export function isPass(r) {
  if (!r) return false;
  if (r.polarity_pass != null) return Number(r.polarity_pass) === 1 || r.polarity_pass === true;
  // Fall back to the violation flag if polarity_pass is absent.
  return !(r.polarity_violation === true || r.polarity_violation === 1);
}

/** Normalize a coverage_gaps field to a string[] (tolerates JSON-string rows). */
export function coverageGaps(r) {
  if (!r) return [];
  const g = r.coverage_gaps;
  if (Array.isArray(g)) return g.map((x) => String(x));
  if (typeof g === 'string' && g.trim()) {
    try {
      const parsed = JSON.parse(g);
      if (Array.isArray(parsed)) return parsed.map((x) => String(x));
    } catch {
      // a bare comma-joined string -- split defensively.
      return g.split(',').map((s) => s.trim()).filter(Boolean);
    }
  }
  return [];
}

/**
 * Derive the latest-verdict paired badge {variant, word, count} for the footer
 * chip + the in-drawer verdict strip. The WORD is the load-bearing signal (M4);
 * the variant is only the second (color) channel. A null/absent latest run
 * yields the resting NONE state.
 *
 *   ok    -- the latest run passed with no coverage gaps -> "AMBIENT OK"
 *   warn  -- the latest run is flagged (polarity violation OR a coverage gap)
 *            -> "POLARITY CHECK" + the flagged count. WARN never foregrounds.
 *   none  -- no ambient run on record yet -> "NO RUNS YET"
 *
 * @param {Record<string, any>|null} latest
 * @returns {{ variant:'ok'|'warn'|'none', word:string, count:number }}
 */
export function latestVerdict(latest) {
  if (!latest) return { variant: 'none', word: 'NO RUNS YET', count: 0 };
  if (isFlagged(latest)) {
    const gaps = coverageGaps(latest).length;
    const violated = latest.polarity_violation === true || latest.polarity_violation === 1
      || Number(latest.polarity_pass) === 0;
    // flagged count = 1 polarity violation (binary) + the gap count.
    const count = (violated ? 1 : 0) + gaps;
    return { variant: 'warn', word: 'POLARITY CHECK', count: Math.max(1, count) };
  }
  return { variant: 'ok', word: 'AMBIENT OK', count: 0 };
}

/** Format an integer with thousands separators (locale-stable en-US). */
export function fmtNum(n) {
  const v = Number(n);
  return Number.isFinite(v) ? v.toLocaleString('en-US') : '0';
}

/** "HH:MM" clock from an epoch-seconds timestamp (local). */
export function fmtClock(tsSec) {
  const t = Number(tsSec);
  if (!Number.isFinite(t)) return '--:--';
  const d = new Date(t * 1000);
  const p = (x) => (x < 10 ? '0' + x : String(x));
  return p(d.getHours()) + ':' + p(d.getMinutes());
}

/** "14m" / "2h 5m" / "8s" from a seconds-ago offset. */
export function ago(secsAgo) {
  const s = Number(secsAgo);
  if (!Number.isFinite(s) || s < 0) return 'unknown';
  if (s < 60) return Math.round(s) + 's';
  const m = Math.round(s / 60);
  if (m < 60) return m + 'm';
  const h = Math.floor(m / 60);
  return h + 'h ' + (m % 60) + 'm';
}

/**
 * Build the live cadence sentence (the muted top strip). When the latest run is
 * flagged the sentence leads with the flag; otherwise it states the cadence.
 * @param {{ variant:string, count:number }} verdict
 * @param {number} intervalMinutes
 * @param {number} lastRunAgoSec
 * @returns {string}
 */
export function cadenceSentence(verdict, intervalMinutes, lastRunAgoSec) {
  const every = '~' + (Number(intervalMinutes) || 30) + 'm';
  const last = ago(lastRunAgoSec);
  if (verdict && verdict.variant === 'warn') {
    return 'latest run flagged ' + verdict.count + ' -- covered every ' + every
      + ', last check ' + last + ' ago';
  }
  if (verdict && verdict.variant === 'none') {
    return 'no ambient runs yet -- cadence target every ' + every;
  }
  return 'covered every ' + every + ' -- last check ' + last + ' ago';
}

// ---------------------------------------------------------------------------
// Mock fixtures (served when the live ambient_runs table is absent / empty:
// fresh DB / fetch error). usedMockData=true is surfaced as a literal text label
// so the operator always knows whether the drawer shows SAMPLE or LIVE data.
//
// Verbatim from the approved mockup's mockDataSpec. The set includes one row
// with polarity_violation:true and two with coverage_gaps so BOTH the OK and the
// flagged ledger states are inspectable headless. status.excluded_self is
// non-zero so the VISIBLE self-exclude readout is demonstrable (G2).
// ---------------------------------------------------------------------------

/** The own-session-id the mock fixture self-excludes by id (mirrors the meta). */
export const MOCK_OWN_SESSION_ID = 'sm-self-0000-bridge';

/**
 * Mock ambient status -- the latest-run summary + cadence meta.
 * @returns {{ enabled:boolean, last_run_at:number, last_run_ago_s:number,
 *   interval_minutes:number, verdict:string, history_count:number,
 *   excluded_self:number, mock:boolean }}
 */
export function mockStatus() {
  return {
    enabled: true,
    last_run_at: 1749600000,
    last_run_ago_s: 840,
    interval_minutes: 30,
    verdict: 'OK',
    history_count: 4,
    excluded_self: 1,
    mock: true,
  };
}

/**
 * Mock ambient history -- four runs, newest-first (matches the mockup). Three
 * cover the PASS / coverage-gap states; one row carries polarity_violation:true
 * so the FAIL ledger word + the WARN footer chip are both demonstrable.
 * @returns {Array<Record<string, any>>}
 */
export function mockHistory() {
  return [
    { id: 'amb-7f3a-1749600000', ts: 1749600000, session_id: 'sess-7f3a2c', project_slug: 'demo-target',
      polarity_pass: 1, polarity_violation: false, coverage_gaps: [], duration_s: 60, messages_seen: 7, mock: true },
    { id: 'amb-7f3a-1749598200', ts: 1749598200, session_id: 'sess-7f3a2c', project_slug: 'demo-target',
      polarity_pass: 1, polarity_violation: false, coverage_gaps: ['learn-mode'], duration_s: 60, messages_seen: 5, mock: true },
    { id: 'amb-91bd-1749596400', ts: 1749596400, session_id: 'sess-91bd4e', project_slug: 'other-target',
      polarity_pass: 0, polarity_violation: true, coverage_gaps: [], duration_s: 60, messages_seen: 12, mock: true },
    { id: 'amb-91bd-1749594600', ts: 1749594600, session_id: 'sess-91bd4e', project_slug: 'other-target',
      polarity_pass: 1, polarity_violation: false, coverage_gaps: ['L4-alignment'], duration_s: 60, messages_seen: 9, mock: true },
  ];
}
