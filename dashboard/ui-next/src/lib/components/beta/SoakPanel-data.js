// SoakPanel-data.js -- pure (no-DOM, no-fetch) helpers + mock fixtures for the
// BETA feature "soak-panel" (#16: Frame D -- Live Session Soak + Polarity
// Audit). Kept separate from the .svelte component so the ranking / self-exclude
// / verdict / report-parse math is unit-testable in isolation and the Svelte
// file stays presentation-focused.
//
// DOMAIN-AGNOSTIC (M16): every identifier in the mock fixtures is a generic,
// invented governance slug -- NO monitored-project vocabulary, NO JOB-IDs, NO
// role names. Identity is data; the only literals here are the UI's own copy and
// SM's OWN self-exclude markers (which are configuration, not target vocabulary).
//
// POLARITY (G2/M15): the candidate fixture INCLUDES one SM-self row (project_slug
// "streamManager"), one SM own-session-id row, and one firewalled-cwd row so the
// self-exclusion + firewall gate is exercised even on the mock path. The ranked
// selector NEVER surfaces an excluded row; the excluded counts are rendered in a
// VISIBLE footer so self-exclusion is a feature, not a silent filter.
//
// FIREWALL (G1): a candidate cwd containing a firewalled monitored-project path
// fragment is REJECTED (never selectable). The fragment list is configuration
// (FIREWALL_CWD_FRAGMENTS), not hard-coded vocabulary in the UI taxonomy.
//
// ASCII-only (cp1252-safe): dash is "--". No smart quotes, no em-dashes.

/** SM-own project slug set echoed client-side (mirrors the server exclude). */
export const SELF_SLUGS = new Set(['streammanager']);

/**
 * cwd path fragments that mark a FIREWALLED (off-limits) monitored-project
 * working directory. A candidate whose cwd contains any of these (case-
 * insensitive) is rejected from the selector. This is the client-side
 * defense-in-depth mirror of the server reject; the server is the durable gate.
 *
 * M16 (domain-agnostic): this is a GENERIC PLACEHOLDER fragment, never a real
 * monitored-project name. The real firewall list is operator/server
 * configuration (the server reject + BRIDGE_* env at promotion), injected as
 * data -- the UI taxonomy hard-codes no governed-target vocabulary.
 * @type {string[]}
 */
export const FIREWALL_CWD_FRAGMENTS = ['walled-repo'];

/**
 * Is this candidate SM-self (by project_slug or by matching the injected own
 * session id)? Self rows are structurally excluded from the selector (G2/M15).
 * @param {Record<string, any>} c
 * @param {string|null} ownSessionId
 * @returns {boolean}
 */
export function isSelfCandidate(c, ownSessionId) {
  if (!c) return false;
  const slug = String(c.project_slug || '').trim().toLowerCase();
  if (slug && SELF_SLUGS.has(slug)) return true;
  const sid = c.session_id != null ? c.session_id : c.id;
  if (ownSessionId && sid != null && String(sid) === String(ownSessionId)) return true;
  return false;
}

/**
 * Is this candidate's cwd firewalled (an off-limits monitored-project path)?
 * Case-insensitive substring match against FIREWALL_CWD_FRAGMENTS.
 * @param {Record<string, any>} c
 * @returns {boolean}
 */
export function isFirewalledCandidate(c) {
  if (!c) return false;
  const cwd = String(c.cwd || '').trim().toLowerCase();
  if (!cwd) return false;
  return FIREWALL_CWD_FRAGMENTS.some((frag) => frag && cwd.includes(frag));
}

/**
 * Classify a candidate session for the selector.
 *
 * States (each renders a PAIRED text+color signal -- color is never the sole
 * channel, M4/ADR-18):
 *   self       -- SM's own session (by slug or id); never selectable.
 *   firewalled -- cwd is an off-limits monitored-project path (G1); never
 *                 selectable.
 *   eligible   -- a governed NON-SM session with a clean cwd; the only
 *                 selectable state.
 *
 * @param {Record<string, any>} c        a candidate row (live or mock shape)
 * @param {string|null} ownSessionId      SM-own session id (defense-in-depth)
 * @returns {{ state:'self'|'firewalled'|'eligible', selectable:boolean, reason:string }}
 */
export function classifyCandidate(c, ownSessionId) {
  if (isSelfCandidate(c, ownSessionId)) {
    return { state: 'self', selectable: false, reason: 'SM own session -- never governed' };
  }
  if (isFirewalledCandidate(c)) {
    return { state: 'firewalled', selectable: false, reason: 'firewalled cwd -- off limits' };
  }
  return { state: 'eligible', selectable: true, reason: '' };
}

/**
 * The busy-score for ranking. Higher = busier. Defensive coercion: a missing
 * busy field falls back to 0. Used as the primary rank key.
 * @param {Record<string, any>} c
 * @returns {number}
 */
export function busyScore(c) {
  const b = Number(c && (c.busy != null ? c.busy : c.busy_score));
  return Number.isFinite(b) ? b : 0;
}

/**
 * Seconds since this candidate's last activity (recency). Lower = more recent.
 * Accepts either a precomputed `last_seen_secs_ago` or a `last_seen` epoch (s).
 * Missing => +Infinity (ranked last). `nowSec` lets callers pin the clock.
 * @param {Record<string, any>} c
 * @param {number} [nowSec]
 * @returns {number}
 */
export function recencySecs(c, nowSec) {
  if (!c) return Infinity;
  if (c.last_seen_secs_ago != null) {
    const v = Number(c.last_seen_secs_ago);
    return Number.isFinite(v) ? Math.max(0, v) : Infinity;
  }
  if (c.last_seen != null) {
    const t = Number(c.last_seen);
    if (Number.isFinite(t)) {
      const now = Number.isFinite(nowSec) ? nowSec : Date.now() / 1000;
      return Math.max(0, now - t);
    }
  }
  return Infinity;
}

/**
 * Rank + partition candidates. Returns the SELECTABLE (non-self, non-firewalled)
 * candidates ranked by (busy_score DESC, recency ASC) plus the VISIBLE excluded
 * counts (self / firewalled) so the footer can render self-exclusion as a feature.
 *
 * The returned `sessions` carry a derived `recencySecs` + `top` flag (first row).
 * @param {Array<Record<string, any>>} candidates
 * @param {string|null} ownSessionId
 * @param {number} [nowSec]
 * @returns {{
 *   sessions: Array<Record<string, any> & { recencySecs:number, top:boolean }>,
 *   excludedSelf:number, excludedFirewalled:number, totalSeen:number }}
 */
export function rankCandidates(candidates, ownSessionId, nowSec) {
  const list = Array.isArray(candidates) ? candidates : [];
  const eligible = [];
  let excludedSelf = 0;
  let excludedFirewalled = 0;

  for (const c of list) {
    const cls = classifyCandidate(c, ownSessionId);
    if (cls.state === 'self') { excludedSelf += 1; continue; }
    if (cls.state === 'firewalled') { excludedFirewalled += 1; continue; }
    eligible.push({ ...c, recencySecs: recencySecs(c, nowSec) });
  }

  eligible.sort((a, b) => {
    const db = busyScore(b) - busyScore(a); // busy DESC
    if (db !== 0) return db;
    return a.recencySecs - b.recencySecs; // recency ASC (more recent first)
  });

  const sessions = eligible.map((c, i) => ({ ...c, top: i === 0 }));
  return {
    sessions,
    excludedSelf,
    excludedFirewalled,
    totalSeen: list.length,
  };
}

/** Format an integer with thousands separators (locale-stable en-US). */
export function fmtNum(n) {
  const v = Number(n);
  return Number.isFinite(v) ? v.toLocaleString('en-US') : '0';
}

/** "18s ago" / "2m 40s ago" / "19m ago" from a seconds-ago offset. */
export function relRecency(secsAgo) {
  const s = Number(secsAgo);
  if (!Number.isFinite(s)) return 'unknown';
  if (s < 60) return Math.round(s) + 's ago';
  const m = Math.floor(s / 60);
  const r = Math.round(s % 60);
  if (m < 60) return r ? m + 'm ' + r + 's ago' : m + 'm ago';
  const h = Math.floor(m / 60);
  return h + 'h ' + (m % 60) + 'm ago';
}

// ---------------------------------------------------------------------------
// Soak status / verdict helpers (read over the additive soak_runs table). The
// component renders a single LOUD paired label+color POLARITY verdict header
// from the most recent soak run (or a mock when gov.db has no runs).
// ---------------------------------------------------------------------------

/**
 * Derive the paired verdict badge {variant, label} for a soak run. The label is
 * the load-bearing signal (TEXT); the variant only the second (color) channel
 * (M4 -- color is NEVER the only signal). A null/absent run yields the NONE
 * resting state.
 * @param {Record<string, any>|null} run
 * @returns {{ variant:'pass'|'fail'|'none', label:string }}
 */
export function verdictFor(run) {
  if (!run) return { variant: 'none', label: 'NO SOAK YET -- run one below' };
  const status = String(run.status || '').toLowerCase();
  if (status === 'running' || status === 'in_progress') {
    return { variant: 'none', label: 'SOAK RUNNING -- awaiting verdict' };
  }
  // polarity_pass is the authoritative gate (1 = PASS, 0 = FAIL).
  const pass = Number(run.polarity_pass) === 1;
  if (pass) return { variant: 'pass', label: 'POLARITY PASS -- 0 self-leaks' };
  const leaks = Number(run.rejection_count);
  const leakTxt = Number.isFinite(leaks) && leaks > 0 ? ' -- ' + leaks + ' self-leaks' : '';
  return { variant: 'fail', label: 'POLARITY FAIL' + leakTxt };
}

/**
 * The state badge {variant, label} for a run's lifecycle status. Paired text +
 * color (M4). Statuses: running / complete / failed (anything else => complete).
 * @param {Record<string, any>|null} run
 * @returns {{ variant:'inprogress'|'complete'|'failed', label:string }}
 */
export function stateFor(run) {
  if (!run) return { variant: 'inprogress', label: 'IDLE' };
  const status = String(run.status || '').toLowerCase();
  if (status === 'running' || status === 'in_progress') {
    return { variant: 'inprogress', label: 'IN PROGRESS' };
  }
  if (Number(run.polarity_pass) === 1) {
    return { variant: 'complete', label: 'COMPLETE -- PASS' };
  }
  return { variant: 'failed', label: 'COMPLETE -- FAIL' };
}

/**
 * Parse the per-band latency table out of a soak report_md blob. The soak
 * report (mirrors tools/soak_driver._render_per_band) is free-form markdown; we
 * defensively look for "ALLOW", "L2"/"L3", "L4" lines carrying p50/p95 numbers.
 * Returns [] when nothing parses (the caller falls back to a mock band table).
 *
 * Format tolerated (whitespace-separated, p50 then p95, optional n):
 *   "ALLOW (routine)   50   5.9   9.9"
 *   "L2/L3 escalation   4   7.2  12.4"
 *   "L4 alignment       2  13.1  18.6"
 * @param {string} reportMd
 * @returns {Array<{ path:string, n:number, p50:number, p95:number }>}
 */
export function parseBands(reportMd) {
  if (!reportMd || typeof reportMd !== 'string') return [];
  const out = [];
  const lines = reportMd.split(/\r?\n/);
  // path label -> matcher fragments (case-insensitive).
  const matchers = [
    { path: 'ALLOW (routine)', re: /allow/i },
    { path: 'L2/L3 escalation', re: /\bl2\b|\bl3\b|l2\/l3/i },
    { path: 'L4 alignment', re: /\bl4\b/i },
  ];
  for (const line of lines) {
    for (const m of matchers) {
      if (!m.re.test(line)) continue;
      // pull the trailing numeric run: n p50 p95 (the LAST three numbers).
      const nums = (line.match(/-?\d+(?:\.\d+)?/g) || []).map(Number);
      if (nums.length >= 3) {
        const [n, p50, p95] = nums.slice(-3);
        out.push({ path: m.path, n, p50, p95 });
      }
      break;
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Mock fixtures (served when live gov.db data is absent: fresh DB / fetch
// error). usedMockData=true is surfaced as a literal text label so the operator
// always knows whether the panel shows SAMPLE or LIVE data.
// ---------------------------------------------------------------------------

/**
 * Mock ranked candidate set: three selectable governed NON-SM sessions plus the
 * three EXCLUDED rows (one SM-self-by-slug, one SM-self-by-id, one firewalled
 * cwd) so the selector ranking AND the self-exclude/firewall footer are both
 * demonstrable. Domain-agnostic invented slugs.
 * @returns {Array<Record<string, any>>}
 */
export function mockCandidates() {
  return [
    { session_id: 'a1b2c3d4-0001', project_slug: 'webapp-frontend', cwd: '/home/op/vs/webapp', busy: 42, last_seen_secs_ago: 18 },
    { session_id: 'a1b2c3d4-0002', project_slug: 'infra-pipeline', cwd: '/home/op/vs/infra', busy: 17, last_seen_secs_ago: 160 },
    { session_id: 'a1b2c3d4-0003', project_slug: 'docs-site', cwd: '/home/op/vs/docs', busy: 3, last_seen_secs_ago: 1140 },
    // EXCLUDED -- SM-self by project_slug (G2):
    { session_id: 'a1b2c3d4-self', project_slug: 'streamManager', cwd: '/home/op/vs/streamManager', busy: 99, last_seen_secs_ago: 4 },
    // EXCLUDED -- SM-self by own-session-id (G2; slug is non-SM):
    { session_id: 'sm-own-0000-bridge', project_slug: 'bridge-host', cwd: '/home/op/vs/bridge', busy: 8, last_seen_secs_ago: 30 },
    // EXCLUDED -- firewalled cwd (G1):
    { session_id: 'a1b2c3d4-fw01', project_slug: 'walled-target', cwd: '/home/op/vs/walled-repo', busy: 25, last_seen_secs_ago: 12 },
  ];
}

/** The own-session-id the mock fixture self-excludes by id (mirrors the meta). */
export const MOCK_OWN_SESSION_ID = 'sm-own-0000-bridge';

/**
 * A realistic mock completed soak run (PASS) used when soak_runs is empty so the
 * verdict header + per-band report are always populated for a headless walk.
 * @returns {Record<string, any>}
 */
export function mockSoakRun() {
  return {
    soak_id: 'soak-20260611T0915',
    session_id: 'a1b2c3d4-0001',
    project_slug: 'webapp-frontend',
    started_at: 1749636900,
    status: 'complete',
    polarity_pass: 1,
    rejection_count: 2,
    report_md:
      '### Tier-4 live soak -- soak-20260611T0915\n'
      + 'session   : a1b2c3d4-0001 (webapp-frontend)\n'
      + 'duration  : 300s   messages: 58   decisions: 56\n'
      + 'polarity  : PASS    rejections: 2    self-leaks: 0\n'
      + 'recorded_latency_ms: 9912.0  (overall p95 band)\n'
      + '\n'
      + 'Path                n     p50     p95\n'
      + 'ALLOW (routine)     50    5.9     9.9\n'
      + 'L2/L3 escalation    4     7.2     12.4\n'
      + 'L4 alignment        2     13.1    18.6\n',
  };
}

/**
 * The deterministic mock per-band table (used when a run's report_md does not
 * parse into bands). Mirrors the mockup's table.
 * @returns {Array<{ path:string, n:number, p50:number, p95:number }>}
 */
export function mockBands() {
  return [
    { path: 'ALLOW (routine)', n: 50, p50: 5.9, p95: 9.9 },
    { path: 'L2/L3 escalation', n: 4, p50: 7.2, p95: 12.4 },
    { path: 'L4 alignment', n: 2, p50: 13.1, p95: 18.6 },
  ];
}
