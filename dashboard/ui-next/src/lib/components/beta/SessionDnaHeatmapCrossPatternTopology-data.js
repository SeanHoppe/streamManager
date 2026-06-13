// SessionDnaHeatmapCrossPatternTopology-data.js -- pure graph-to-grid helpers +
// the deterministic mock fixture for the BETA feature
// "session-dna-heatmap-cross-pattern-topology" (#30). No DOM, no Svelte, no
// network: a leaf module so the topology math is unit-testable in isolation and
// the component stays lean.
//
// CONTRACT (matches reports/proposals/mockups/
//   session-dna-heatmap-cross-pattern-topology.html):
//   The endpoint GET /api/patterns/cross-session-topology returns a graph shape
//   { used_mock, excluded_self, nodes, patterns, edges, isolated }:
//     nodes:    [{ id, slug, project_slug, agent_slugs:[] }]            sessions
//     patterns: { hash: { level, payload } }                           pattern meta
//     edges:    [{ hash, session_a, conf_a, session_b, conf_b }]       SHARED (>=2)
//     isolated: [{ hash, session_id, confidence }]                     1-session only
//   This module turns that graph into a DENSE (session x pattern) cell grid so
//   the matrix renders: reading DOWN a column = is a pattern SPREADING; reading
//   ACROSS a row = a session's pattern signature ("DNA").
//
// POLARITY (G2 / M15): this module never reads the SM-own session. The endpoint
//   self-excludes at the SQL WHERE (project_slug NOT IN the SM slug set AND
//   session_id != SM_OWN_SESSION_ID) and surfaces `excluded_self`; this module
//   only renders the non-SM nodes it is handed. No self node is ever derivable.
//
// ASCII-only (cp1252-safe): dash is "--".

/** Band thresholds (paired numeric + WORD; color is reinforcement, M4). */
export const BAND_HIGH = 0.7;
export const BAND_MEDIUM = 0.4;

/**
 * Classify a confidence value into a paired band WORD. EMPTY when absent so the
 * caller can render a hairline ghost cell (no ink) rather than a fake 0.00.
 * @param {number|null|undefined} c
 * @returns {'HIGH'|'MEDIUM'|'LEARNING'|'EMPTY'}
 */
export function bandOf(c) {
  if (c === undefined || c === null || !Number.isFinite(Number(c))) return 'EMPTY';
  const v = Number(c);
  if (v >= BAND_HIGH) return 'HIGH';
  if (v >= BAND_MEDIUM) return 'MEDIUM';
  return 'LEARNING';
}

/** The human band WORD for a cell (M4 paired label). @param {string} b */
export function bandWord(b) {
  return b === 'EMPTY' ? 'absent' : b;
}

/**
 * Format a confidence value as a fixed 2-dp string, or '--' when absent. The
 * LITERAL value is the load-bearing signal (never color alone).
 * @param {number|null|undefined} c
 * @returns {string}
 */
export function fmtConf(c) {
  if (c === undefined || c === null || !Number.isFinite(Number(c))) return '--';
  return Number(c).toFixed(2);
}

/**
 * A short, domain-agnostic label for a pattern hash. Hex-looking hashes are
 * truncated to 8 chars + an ellipsis; mock "h_*" hashes render with a leading
 * '#'. Rendered FROM DATA (M16) -- no monitored-project vocabulary baked in.
 * @param {string} h
 * @returns {string}
 */
export function shortHash(h) {
  const s = String(h || '');
  if (!s) return '(none)';
  if (s.startsWith('h_')) return '#' + s.slice(2);
  return s.length > 8 ? s.slice(0, 8) + '...' : s;
}

/**
 * Turn the endpoint graph shape into a dense (session x pattern) grid.
 *
 * @param {{
 *   nodes?: Array<{id:string, slug?:string, project_slug?:string, agent_slugs?:string[]}>,
 *   patterns?: Record<string, {level?:string|number, payload?:string}>,
 *   edges?: Array<{hash:string, session_a:string, conf_a:number, session_b:string, conf_b:number}>,
 *   isolated?: Array<{hash:string, session_id:string, confidence:number}>,
 * }} topo
 * @returns {{
 *   patternOrder: string[],
 *   cellConf: Record<string, Record<string, number>>,
 *   sharedHashes: Record<string, true>,
 *   nodes: Array<Record<string, any>>,
 *   patterns: Record<string, any>
 * }}
 *   `cellConf[hash][session_id] = confidence` (absent => no entry).
 *   `sharedHashes[hash] = true` iff the pattern appears in >= 2 sessions.
 *   Column order: edge (shared) patterns first by first appearance, then
 *   isolated-only patterns -- so the spreading columns lead the eye.
 */
export function buildGrid(topo) {
  const t = topo && typeof topo === 'object' ? topo : {};
  const edges = Array.isArray(t.edges) ? t.edges : [];
  const isolated = Array.isArray(t.isolated) ? t.isolated : [];
  const nodes = Array.isArray(t.nodes) ? t.nodes : [];
  const patterns = t.patterns && typeof t.patterns === 'object' ? t.patterns : {};

  /** @type {string[]} */
  const patternOrder = [];
  /** @type {Record<string, true>} */
  const seen = {};
  const remember = (h) => {
    if (h && !seen[h]) {
      seen[h] = true;
      patternOrder.push(h);
    }
  };
  edges.forEach((e) => remember(e && e.hash));
  isolated.forEach((iso) => remember(iso && iso.hash));

  /** @type {Record<string, Record<string, number>>} */
  const cellConf = {};
  patternOrder.forEach((h) => {
    cellConf[h] = {};
  });
  edges.forEach((e) => {
    if (!e || !cellConf[e.hash]) return;
    if (e.session_a != null && Number.isFinite(Number(e.conf_a))) {
      cellConf[e.hash][e.session_a] = Number(e.conf_a);
    }
    if (e.session_b != null && Number.isFinite(Number(e.conf_b))) {
      cellConf[e.hash][e.session_b] = Number(e.conf_b);
    }
  });
  isolated.forEach((iso) => {
    if (!iso || !cellConf[iso.hash]) return;
    if (iso.session_id != null && Number.isFinite(Number(iso.confidence))) {
      cellConf[iso.hash][iso.session_id] = Number(iso.confidence);
    }
  });

  /** @type {Record<string, true>} */
  const sharedHashes = {};
  patternOrder.forEach((h) => {
    if (Object.keys(cellConf[h]).length >= 2) sharedHashes[h] = true;
  });

  return { patternOrder, cellConf, sharedHashes, nodes, patterns };
}

/**
 * The per-pattern participation for ONE session, used by the drill-down card.
 * Returns [{hash, conf, shared, spread:[{node, conf}]}] for every pattern this
 * node participates in, where `spread` is the full per-session confidence list.
 * @param {ReturnType<typeof buildGrid>} grid
 * @param {string} nodeId
 * @returns {Array<{hash:string, conf:number, shared:boolean, spread:Array<{node:any, conf:number}>}>}
 */
export function patternsForNode(grid, nodeId) {
  const out = [];
  const nodeById = (id) => grid.nodes.find((n) => n && n.id === id) || { id, slug: id };
  grid.patternOrder.forEach((h) => {
    const conf = grid.cellConf[h][nodeId];
    if (conf === undefined || conf === null) return;
    const shared = !!grid.sharedHashes[h];
    const spread = Object.keys(grid.cellConf[h]).map((sid) => ({
      node: nodeById(sid),
      conf: grid.cellConf[h][sid],
    }));
    out.push({ hash: h, conf, shared, spread });
  });
  return out;
}

/**
 * The topology VERDICT for a shared pattern's spread (M4 text, never color
 * alone): "asymmetric -- Npp gap" when the max-min confidence gap is wide,
 * else "spreading". The gap (in percentage points) is the headline signal.
 * @param {Array<{conf:number}>} spread
 * @returns {{verdict:'asymmetric'|'spreading', gapPp:number, text:string}}
 */
export function spreadVerdict(spread) {
  const vals = (Array.isArray(spread) ? spread : [])
    .map((s) => Number(s.conf))
    .filter((n) => Number.isFinite(n));
  if (vals.length < 2) {
    return { verdict: 'spreading', gapPp: 0, text: 'spreading' };
  }
  const gap = Math.max(...vals) - Math.min(...vals);
  const gapPp = Math.round(gap * 100);
  if (gap >= 0.2) {
    return { verdict: 'asymmetric', gapPp, text: `asymmetric -- ${gapPp}pp gap` };
  }
  return { verdict: 'spreading', gapPp, text: 'spreading -- tighten now' };
}

/**
 * The deterministic MOCK fixture, returned by the component when the live
 * endpoint degrades to empty (a fresh / ALLOW-only gov.db carries no
 * cross-session patterns, so the matrix would otherwise be blank in test).
 * Mirrors the approved mockup's TOPO object EXACTLY. The component sets
 * usedMockData=true whenever it falls back to this fixture.
 *
 * The fixture deliberately encodes all three readings the feature surfaces:
 *   * h_force_push  -- SPREADING / ASYMMETRIC: 0.78 vs 0.52 (a 26pp gap).
 *   * h_secret_echo -- a second cross-session edge: 0.81 vs 0.44.
 *   * h_wide_rm     -- ISOLATED: present in one session only (0.66).
 *   * excluded_self = 1 -- the SM-own session was dropped at the SQL WHERE.
 * @returns {Object}
 */
export function mockTopology() {
  return {
    used_mock: true,
    excluded_self: 1,
    nodes: [
      { id: 'a1b2c3d4-mock', slug: 'a1b2c3d4', project_slug: 'alpha-svc', agent_slugs: ['build', 'review'] },
      { id: 'e5f6a7b8-mock', slug: 'e5f6a7b8', project_slug: 'alpha-svc', agent_slugs: ['plan'] },
      { id: 'c9d0e1f2-mock', slug: 'c9d0e1f2', project_slug: 'beta-lib', agent_slugs: ['build'] },
    ],
    patterns: {
      h_force_push: { level: 'L3', payload: 'force-push to protected ref' },
      h_secret_echo: { level: 'L2', payload: 'echo of credential-shaped token' },
      h_wide_rm: { level: 'L3', payload: 'recursive delete outside workspace' },
    },
    edges: [
      { hash: 'h_force_push', session_a: 'a1b2c3d4-mock', conf_a: 0.78, session_b: 'e5f6a7b8-mock', conf_b: 0.52 },
      { hash: 'h_secret_echo', session_a: 'a1b2c3d4-mock', conf_a: 0.81, session_b: 'c9d0e1f2-mock', conf_b: 0.44 },
    ],
    isolated: [{ hash: 'h_wide_rm', session_id: 'e5f6a7b8-mock', confidence: 0.66 }],
  };
}

/**
 * True when a topology graph carries at least one renderable (node + pattern)
 * pair. A degraded/empty endpoint shape returns false so the component can fall
 * back to the mock fixture rather than render a blank matrix.
 * @param {Object} topo
 * @returns {boolean}
 */
export function hasTopology(topo) {
  if (!topo || typeof topo !== 'object') return false;
  const nodes = Array.isArray(topo.nodes) ? topo.nodes : [];
  const edges = Array.isArray(topo.edges) ? topo.edges : [];
  const isolated = Array.isArray(topo.isolated) ? topo.isolated : [];
  return nodes.length > 0 && (edges.length > 0 || isolated.length > 0);
}

/** The level WORD for a pattern (M4 paired label). @param {*} level */
export function levelWord(level) {
  if (level === undefined || level === null || level === '') return '';
  const s = String(level).trim().toUpperCase();
  // numeric levels (0..4) render as "L<n>"; already-prefixed pass through.
  if (/^\d+$/.test(s)) return 'L' + s;
  return s;
}
