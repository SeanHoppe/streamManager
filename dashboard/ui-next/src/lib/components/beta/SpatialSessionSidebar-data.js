// SpatialSessionSidebar-data.js -- pure data + projection math for the BETA
// "spatial-session-sidebar" feature (#45). NO Svelte, NO DOM, NO network. The
// component imports the mock fallback, the normalizers, and the geometry helpers
// from here so the math is unit-inspectable and the .svelte file stays
// presentation-only.
//
// CONTRACT
//   - mockOverview() returns the realistic fallback the sidebar renders when the
//     live GET /api/sessions/spatial-overview endpoint is absent or returns an
//     empty set (fresh DB, no governed sessions). usedMockData=true then. It is
//     the SAME deterministic fixture shape the operator-approved mockup uses
//     (reports/proposals/mockups/spatial-session-sidebar.html).
//   - normalizeOverview(payload) coerces the server shape into the canonical one;
//     returns null when there is no usable node list (caller swaps for mock).
//   - modeLabel / modeClass / bandColorVar / escLabel are the PAIRED-label helpers
//     (M4: the literal mode WORD / alert WORD is the load-bearing channel; color
//     is strictly the second channel). They never invent a word; an unknown mode
//     falls back to OBSERVE so a row is never color-only.
//   - sparklinePath / nodeCenter / ago are deterministic geometry/format helpers.
//
// G2 (polarity): NO SM-own session_id appears in the mock fixture. The live
//   endpoints exclude SM-self by project_slug server-side; this module never
//   re-introduces a self row. The footer readout states excluded_self (>=1 mock).
// M16 (domain-agnostic): every identity is a generic placeholder rendered FROM
//   the node's project_slug. NO monitored-project vocabulary / JOB-IDs / role
//   names. A real project's identity arrives from server data, never hard-coded.
//
// ASCII-only (cp1252-safe): dash rendered as "--". No smart quotes / em-dash.

/**
 * @typedef {Object} SpatialNode
 * @property {string} session_id
 * @property {string} project_slug
 * @property {string} governance_mode   OBSERVE|SUGGEST|GUIDE|INTERVENE|BLOCK
 * @property {number} last_activity_ts   epoch seconds
 * @property {number} open_hitl
 * @property {string} agent_slug         '' when no active agent
 * @property {number[]} latency_sparkline up to 10 points (ms), oldest-first
 * @property {string|null} alert         M2 escalation key, or null
 */

/**
 * @typedef {Object} SpatialEdge
 * @property {string} from_session_id
 * @property {string} to_session_id
 * @property {number} pattern_count
 * @property {string[]} pattern_hashes
 */

/**
 * A fixed reference "now" (epoch seconds) so the mock recency / ages render
 * deterministically in tests. Mirrors the approved mockup's NOW.
 */
export const MOCK_NOW = 1749600000;

/** The five governance-mode -> CSS color-token names (theme.css :root). */
const BAND_VAR = {
  OBSERVE: '--c-allow',
  SUGGEST: '--c-suggest',
  GUIDE: '--c-guide',
  INTERVENE: '--c-intervene',
  BLOCK: '--c-block',
};

/**
 * The literal alert WORD for each M2 escalation key (reuse, never redefine). The
 * WORD is the load-bearing channel; the pulsing outline is the second channel.
 */
const ESC_LABEL = {
  'static-rule': 'STATIC RULE',
  static_rule: 'STATIC RULE',
  governance_negative_regression: 'NEG REGRESSION',
  desktop_pause: 'PAUSE',
};

/** @param {any} v */ function num(v) { const n = Number(v); return Number.isFinite(n) ? n : 0; }

/**
 * Canonical UPPERCASE mode word; unknown / missing falls back to OBSERVE so a
 * node is never rendered color-only (M4).
 * @param {any} m
 * @returns {string}
 */
export function modeLabel(m) {
  const u = String(m || '').toUpperCase();
  return u in BAND_VAR ? u : 'OBSERVE';
}

/** @param {any} m @returns {string} the node--<mode> presentation class. */
export function modeClass(m) {
  return `node--${modeLabel(m).toLowerCase()}`;
}

/** @param {any} m @returns {string} the CSS color-token name for the mode ring. */
export function bandColorVar(m) {
  return BAND_VAR[modeLabel(m)] || '--c-allow';
}

/**
 * The literal alert WORD for an escalation key, or '' when the key is unknown /
 * absent. Never returns a color -- the WORD is the signal.
 * @param {any} key
 * @returns {string}
 */
export function escLabel(key) {
  if (!key) return '';
  return ESC_LABEL[String(key)] || String(key).toUpperCase().replace(/[_-]+/g, ' ');
}

/**
 * Realistic mock overview -- the fallback when the server returns nothing. 4
 * non-SM nodes (1 BLOCK on fire + static-rule alert, 1 INTERVENE, 1 OBSERVE, 1
 * SUGGEST) and 2 shared-pattern edges, matching the operator-approved mockup. All
 * identities are generic placeholders; NO SM-own id (G2); NO monitored-project
 * vocabulary (M16). excluded_self is >=1 so the polarity readout is always shown.
 * @returns {{now:number, excluded_self:number, mock:boolean, nodes:SpatialNode[], edges:SpatialEdge[]}}
 */
export function mockOverview() {
  const N = MOCK_NOW;
  /** @type {SpatialNode[]} */
  const nodes = [
    {
      session_id: 'sess-c40e', project_slug: 'gamma-lib', governance_mode: 'BLOCK',
      last_activity_ts: N - 1, open_hitl: 1, agent_slug: 'planner',
      latency_sparkline: [700, 720, 690, 710, 705, 2200, 2600, 3100, 5200, 6100],
      alert: 'static-rule',
    },
    {
      session_id: 'sess-2b91', project_slug: 'beta-app', governance_mode: 'INTERVENE',
      last_activity_ts: N - 5, open_hitl: 2, agent_slug: 'builder',
      latency_sparkline: [610, 680, 940, 1320, 1880, 2410, 3050, 3600, 4100, 4720],
      alert: null,
    },
    {
      session_id: 'sess-7f3a', project_slug: 'alpha-svc', governance_mode: 'OBSERVE',
      last_activity_ts: N - 20, open_hitl: 0, agent_slug: 'reviewer',
      latency_sparkline: [820, 910, 760, 805, 790, 840, 815, 800, 795, 810],
      alert: null,
    },
    {
      session_id: 'sess-9d12', project_slug: 'delta-cli', governance_mode: 'SUGGEST',
      last_activity_ts: N - 100, open_hitl: 0, agent_slug: '',
      latency_sparkline: [540, 560, 520, 530, 545, 538, 550, 525, 535, 542],
      alert: null,
    },
  ];
  /** @type {SpatialEdge[]} */
  const edges = [
    { from_session_id: 'sess-7f3a', to_session_id: 'sess-2b91', pattern_count: 4, pattern_hashes: ['h31a', 'h44c', 'h58e', 'h6b2'] },
    { from_session_id: 'sess-2b91', to_session_id: 'sess-c40e', pattern_count: 1, pattern_hashes: ['h6b2'] },
  ];
  return { now: N, excluded_self: 1, mock: true, nodes, edges };
}

/**
 * Coerce one raw server node into the canonical shape, defaulting every field so
 * the sidebar never reads undefined. Returns null for a non-object / id-less row.
 * @param {any} raw
 * @returns {SpatialNode|null}
 */
export function normalizeNode(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const sid = String(raw.session_id || '');
  if (!sid) return null;
  const spark = Array.isArray(raw.latency_sparkline)
    ? raw.latency_sparkline.map(num).slice(-10)
    : [];
  return {
    session_id: sid,
    project_slug:
      typeof raw.project_slug === 'string' && raw.project_slug.trim()
        ? raw.project_slug.trim()
        : sid,
    governance_mode: modeLabel(raw.governance_mode),
    last_activity_ts: num(raw.last_activity_ts),
    open_hitl: Math.max(0, num(raw.open_hitl)),
    agent_slug: typeof raw.agent_slug === 'string' ? raw.agent_slug : '',
    latency_sparkline: spark,
    alert: raw.alert ? String(raw.alert) : null,
  };
}

/**
 * Coerce one raw server edge. Both endpoints must be present and distinct (a
 * self-loop is not a cross-session flow). Returns null otherwise.
 * @param {any} raw
 * @returns {SpatialEdge|null}
 */
export function normalizeEdge(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const from = String(raw.from_session_id || '');
  const to = String(raw.to_session_id || '');
  if (!from || !to || from === to) return null;
  const hashes = Array.isArray(raw.pattern_hashes)
    ? raw.pattern_hashes.map((h) => String(h)).filter(Boolean)
    : [];
  const count = Math.max(1, num(raw.pattern_count) || hashes.length || 1);
  return { from_session_id: from, to_session_id: to, pattern_count: count, pattern_hashes: hashes };
}

/**
 * Normalize the whole server payload into {now, excluded_self, mock, nodes,
 * edges}. Returns null when there is no usable node list (caller swaps for mock).
 * Edges that reference a missing node are dropped (so the field never draws a
 * dangling line).
 * @param {any} payload
 * @returns {{now:number, excluded_self:number, mock:boolean, nodes:SpatialNode[], edges:SpatialEdge[]}|null}
 */
export function normalizeOverview(payload) {
  if (!payload || typeof payload !== 'object') return null;
  const rawNodes = Array.isArray(payload.nodes) ? payload.nodes : [];
  const nodes = rawNodes.map(normalizeNode).filter((n) => n && n.session_id);
  if (nodes.length === 0) return null;
  const ids = new Set(nodes.map((n) => n.session_id));
  const rawEdges = Array.isArray(payload.edges) ? payload.edges : [];
  const edges = rawEdges
    .map(normalizeEdge)
    .filter((e) => e && ids.has(e.from_session_id) && ids.has(e.to_session_id));
  return {
    now: num(payload.now) || Math.floor(Date.now() / 1000),
    excluded_self: num(payload.excluded_self),
    mock: false,
    nodes: /** @type {SpatialNode[]} */ (nodes),
    edges: /** @type {SpatialEdge[]} */ (edges),
  };
}

/**
 * Build an SVG path d-string for a min-max-normalised latency polyline. Returns
 * '' for an empty series. Shape-only (M18): never a severity signal.
 * @param {number[]} arr
 * @param {number} w
 * @param {number} h
 * @returns {string}
 */
export function sparklinePath(arr, w, h) {
  if (!arr || !arr.length) return '';
  if (arr.length === 1) return `M0,${(h - 1).toFixed(1)} L${w.toFixed(1)},${(h - 1).toFixed(1)}`;
  const lo = Math.min.apply(null, arr);
  const hi = Math.max.apply(null, arr);
  const span = hi - lo || 1;
  const step = w / (arr.length - 1);
  const pts = arr.map((v, i) => {
    const x = i * step;
    const y = h - ((v - lo) / span) * (h - 2) - 1; // 1px pad top/bottom
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return `M${pts.join(' L')}`;
}

/**
 * Deterministic 2D placement for a node, by recency rank. Newest sits upper-right
 * and older drift down-left along a calm arc -- stable, no physics, no RNG (so the
 * field reads the same every paint and in tests). rank 0 = most recent.
 * @param {number} rank
 * @param {number} total
 * @param {number} w
 * @param {number} h
 * @returns {{x:number, y:number}}
 */
export function nodeCenter(rank, total, w, h) {
  const n = Math.max(1, total);
  if (n === 1) return { x: w * 0.5, y: h * 0.4 };
  // Spread ranks along a gentle diagonal arc from upper-right to lower-left.
  const t = rank / (n - 1); // 0 (newest) .. 1 (oldest)
  const x = (0.72 - 0.48 * t) * w;
  const arc = Math.sin(t * Math.PI) * 0.12; // bow the line so nodes do not stack
  const y = (0.22 + 0.56 * t + arc) * h;
  return { x, y };
}

/** @param {number} ts @param {number} now @returns {string} a human "Ns ago". */
export function ago(ts, now) {
  const s = Math.max(0, num(now) - num(ts));
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.floor(m / 60)}h ago`;
}

/**
 * Recency-ordered copy of the node list (newest last_activity first) so DOM order
 * == Tab order. Stable: equal timestamps keep input order.
 * @param {SpatialNode[]} nodes
 * @returns {SpatialNode[]}
 */
export function byRecency(nodes) {
  return (Array.isArray(nodes) ? nodes.slice() : []).sort(
    (a, b) => num(b.last_activity_ts) - num(a.last_activity_ts),
  );
}

/**
 * The aria-label for one node -- the full PAIRED verdict (project, mode word,
 * recency, open-action count, alert word) so a screen-reader user gets the
 * identical read the visual chip carries.
 * @param {SpatialNode} n
 * @param {number} now
 * @returns {string}
 */
export function nodeAria(n, now) {
  const parts = [`Session ${n.project_slug}`, `mode ${modeLabel(n.governance_mode)}`, ago(n.last_activity_ts, now)];
  if (n.open_hitl > 0) parts.push(`${n.open_hitl} action${n.open_hitl === 1 ? '' : 's'} required`);
  if (n.alert) parts.push(`${escLabel(n.alert)} escalation`);
  return parts.join(', ');
}
