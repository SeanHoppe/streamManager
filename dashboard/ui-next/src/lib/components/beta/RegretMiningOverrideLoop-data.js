// RegretMiningOverrideLoop-data.js -- pure, DOM-free, network-free leaf helpers
// + mock fixtures for the BETA feature "regret-mining-override-loop" (#24:
// Regret Mining -- close the operator-override feedback loop). No Svelte, no
// fetch: a deterministic module so the ranking / draft-composition math is
// unit-testable in isolation and the component stays lean.
//
// WHAT THE FEATURE IS (the operator-APPROVED mockup, realised):
//   A READ-ONLY regret ledger. Every operator OVERRIDE (HITL APPROVE-over-a-
//   SUGGEST, DISMISS-of-an-INTERVENE, a free-text annotate) is the single
//   richest learning signal the system produces -- the human said "you were
//   wrong here". This pane mines the AGGREGATE of those overrides from the
//   EXISTING hitl_overrides + decisions tables and ranks the divergence
//   clusters (per matched_hash / routing layer) so the operator can fix the
//   worst recurring wrong verdict ONCE -- as an advisory-bias proposal stub
//   they copy/download -- instead of re-correcting it by hand forever.
//
// CONSTRAINED-ADDITIVE BUILD NOTE (vs the original proposal/mockup):
//   The proposal imagined a "Draft as proposal" that staged an advisory-bias
//   write through the Learn-Mode channel. This build is CONSTRAINED ADDITIVE --
//   the draft is composed CLIENT-SIDE as operator-facing markdown the operator
//   copies or downloads. It WRITES NOTHING server-side, never mutates a
//   decisions row, never edits a rule, and never bypasses the absolute HITL
//   gate. The actual bias write-back is DEFERRED to a documented operator-facing
//   "from CLI" affordance (the operator reviews + applies the drafted stub by
//   hand). NO message_bus.py edit, NO new bus envelope, NO ADR-18 amendment, NO
//   in-process spawn/cron/subprocess.
//
// POLARITY (G2 / M15): this module never fabricates an SM-own row. The server
//   endpoint excludes SM-self at the SQL WHERE (project_slug NOT IN the SM slug
//   set AND session_id != SM_OWN_SESSION_ID); deriveClusters() additionally
//   drops any override whose session_id matches a supplied ownSessionId as a
//   cheap backstop, so a leak upstream still cannot paint a self cluster.
//
// M4 / M5 (paired label + color): the override DIRECTION always resolves to a
//   literal WORD label here (ESCALATED / DE-ESCALATED); the component pairs that
//   word with a color swatch. Color is never the sole channel -- the word
//   travels in the title / aria-label and the literal "n/N" fraction is always
//   rendered next to the bar.
//
// M16 (domain-agnostic): cluster identity (matched_hash / routing layer), the
//   governed-target slug, the from/to actions, and the override directions all
//   render FROM DATA. No monitored-project vocabulary is baked in.
//
// ASCII-only (cp1252-safe): dash is "--". No smart quotes, no em-dashes.

/**
 * Action severity rank (ascending). Used to classify an override's DIRECTION:
 * a higher override_action rank than the original => operator ESCALATED (made
 * it stricter); a lower rank => DE-ESCALATED (relaxed it).
 * @type {Readonly<Record<string, number>>}
 */
export const ACTION_RANK = Object.freeze({
  APPROVE: 0,
  ALLOW: 0,
  DISMISS: 1,
  SUGGEST: 2,
  GUIDE: 3,
  INTERVENE: 4,
  BLOCK: 5,
});

/** Default look-back window for the ledger, in days. */
export const WINDOW_DAYS = 30;

/**
 * Normalise an action token to an uppercase string ('' when absent).
 * @param {*} a
 * @returns {string}
 */
export function normAction(a) {
  return (a == null ? '' : String(a)).trim().toUpperCase();
}

/**
 * Classify the dominant override DIRECTION for an (original -> override) pair.
 * Domain-agnostic: returns the literal WORD label the component pairs with a
 * color. Unknown actions fall back to ESCALATED only when the override clearly
 * outranks; otherwise DE-ESCALATED. Never throws.
 * @param {string} original  the engine's proposed action
 * @param {string} override  the operator's chosen action
 * @returns {'ESCALATED'|'DE-ESCALATED'}
 */
export function overrideDirection(original, override) {
  const o = ACTION_RANK[normAction(original)];
  const v = ACTION_RANK[normAction(override)];
  if (Number.isFinite(o) && Number.isFinite(v)) {
    return v > o ? 'ESCALATED' : 'DE-ESCALATED';
  }
  // Unknown vocabulary: treat a non-empty override that differs as a relax.
  return 'DE-ESCALATED';
}

/** Human label for a direction (paired-label primitive). @param {string} d */
export function directionLabel(d) {
  return d === 'ESCALATED' ? 'ESCALATED' : 'DE-ESCALATED';
}

/**
 * A whole-number percent string from a 0..1 fraction. @param {number} x
 * @returns {string}
 */
export function pct(x) {
  const n = Number(x);
  return `${Math.round((Number.isFinite(n) ? n : 0) * 100)}%`;
}

/**
 * The hotness rank score for a cluster: override_rate x volume. The top cluster
 * is the one the operator should fix first.
 * @param {{ override_rate:number, n_decisions:number }} c
 * @returns {number}
 */
export function rankScore(c) {
  if (!c) return 0;
  const r = Number(c.override_rate);
  const n = Number(c.n_decisions);
  return (Number.isFinite(r) ? r : 0) * (Number.isFinite(n) ? n : 0);
}

/**
 * Compose the operator-facing advisory-bias proposal STUB for a cluster as
 * markdown. READ-ONLY: this is a string the operator copies/downloads -- it is
 * never written server-side, never applied, never bypasses the HITL gate.
 * ASCII-only.
 * @param {Record<string, any>} cluster
 * @returns {string}
 */
export function composeDraftMarkdown(cluster) {
  const c = cluster || {};
  const n = Number(c.n_overridden) || 0;
  const total = Number(c.n_decisions) || 0;
  const rate = pct(c.override_rate);
  const dim = c.label_dim || 'cluster';
  const ident = c.identity || c.cluster_key || '(unknown)';
  const from = normAction(c.from_action) || '(verdict)';
  const to = normAction(c.to_action) || '(operator)';
  return (
    `## Advisory-bias candidate -- ${dim} ${ident}\n` +
    `- governance: ${from} | operator: ${to} | ${n}/${total} (${rate})\n` +
    `- proposed: raise advisory bias toward ${to} for this shape (HITL gate unchanged)\n` +
    `- NEVER auto-applies; operator review required.\n` +
    `- READ-ONLY stub composed in the dashboard; nothing was written server-side.\n`
  );
}

/**
 * DERIVE the ranked divergence-cluster ledger from a flat list of override join
 * rows. Each row is an operator override joined to its decision + session:
 *   { decision_id, session_id, project_slug, original_action, override_action,
 *     note, timestamp, matched_hash, layer, content }
 * plus the cluster needs the per-cluster DENOMINATOR (how many governed
 * decisions of that shape exist), supplied as `decisionCounts` keyed by the same
 * cluster_key. When the denominator is unknown the override count is used (so
 * override_rate <= 1 always holds and the cluster is still rankable).
 *
 * Clustering: prefer matched_hash (a concrete rule/pattern shape); fall back to
 * the routing layer when no hash is present. Domain-agnostic throughout.
 *
 * @param {Array<Record<string, any>>} rows override+decision join rows.
 * @param {{ ownSessionId?:string|null, decisionCounts?:Record<string, number>, limit?:number }} [opts]
 * @returns {Array<Record<string, any>>} clusters, hottest-first.
 */
export function deriveClusters(rows, opts = {}) {
  const own = (opts.ownSessionId || '').toString().trim();
  const counts = opts.decisionCounts && typeof opts.decisionCounts === 'object'
    ? opts.decisionCounts : {};
  const limit = Number(opts.limit) > 0 ? Number(opts.limit) : 50;
  const list = Array.isArray(rows) ? rows : [];

  /** @type {Map<string, Record<string, any>>} */
  const byKey = new Map();

  for (const r of list) {
    if (!r || typeof r !== 'object') continue;
    // G2 backstop: never let an SM-own override paint a cluster.
    if (own && String(r.session_id || '').trim() === own) continue;

    const hash = r.matched_hash != null ? String(r.matched_hash).trim() : '';
    const layer = Number.isFinite(Number(r.layer)) ? Number(r.layer) : 0;
    const labelDim = hash ? 'matched_hash' : 'layer';
    const identity = hash ? hash.slice(0, 6) : `L${layer}`;
    const clusterKey = hash ? `h:${identity}` : `layer:${layer}`;

    const from = normAction(r.original_action);
    const to = normAction(r.override_action);
    const dir = overrideDirection(from, to);

    let acc = byKey.get(clusterKey);
    if (!acc) {
      acc = {
        cluster_key: clusterKey,
        label_dim: labelDim,
        identity,
        layer,
        n_overridden: 0,
        n_decisions: 0,
        override_rate: 0,
        dominant_direction: dir,
        direction_label: '',
        from_action: from,
        to_action: to,
        sample_content: typeof r.content === 'string' ? r.content.slice(0, 80) : '',
        project_slug: typeof r.project_slug === 'string' ? r.project_slug : '',
        _dirs: { ESCALATED: 0, 'DE-ESCALATED': 0 },
        _overrides: [],
      };
      byKey.set(clusterKey, acc);
    }
    acc.n_overridden += 1;
    acc._dirs[dir] += 1;
    if (!acc.sample_content && typeof r.content === 'string') {
      acc.sample_content = r.content.slice(0, 80);
    }
    if (!acc.project_slug && typeof r.project_slug === 'string') {
      acc.project_slug = r.project_slug;
    }
    acc._overrides.push({
      decision_id: r.decision_id != null ? String(r.decision_id) : '',
      timestamp: r.timestamp != null ? String(r.timestamp) : '',
      original_action: from,
      override_action: to,
      note: typeof r.note === 'string' && r.note.trim() ? r.note : null,
      session_id: typeof r.session_id === 'string' ? r.session_id : '',
      project_slug: typeof r.project_slug === 'string' ? r.project_slug : '',
      content: typeof r.content === 'string' ? r.content : '',
    });
  }

  const out = [];
  for (const acc of byKey.values()) {
    const denom = Number(counts[acc.cluster_key]);
    acc.n_decisions = Number.isFinite(denom) && denom >= acc.n_overridden
      ? denom : acc.n_overridden;
    acc.override_rate = acc.n_decisions > 0 ? acc.n_overridden / acc.n_decisions : 0;
    // dominant direction = the more frequent of the two; tie -> ESCALATED.
    const esc = acc._dirs.ESCALATED;
    const de = acc._dirs['DE-ESCALATED'];
    acc.dominant_direction = esc >= de ? 'ESCALATED' : 'DE-ESCALATED';
    acc.direction_label = acc.dominant_direction === 'ESCALATED'
      ? `you ESCALATED ${acc.n_overridden}/${acc.n_decisions}`
      : `you DE-ESCALATED ${acc.n_overridden}/${acc.n_decisions}`;
    // from/to default to the dominant-direction representative pair.
    out.push(acc);
  }

  out.sort((a, b) => rankScore(b) - rankScore(a));
  return out.slice(0, limit);
}

/**
 * Build the per-cluster evidence payload (the expand drawer body) from the
 * already-derived cluster's accumulated overrides. Synthesises a draft stub.
 * @param {Record<string, any>} cluster
 * @param {{ limit?:number }} [opts]
 * @returns {{ cluster_key:string, mock:boolean, overrides:Array<Record<string, any>>, draft_markdown:string }}
 */
export function evidenceFor(cluster, opts = {}) {
  const c = cluster || {};
  const limit = Number(opts.limit) > 0 ? Number(opts.limit) : 8;
  const overrides = Array.isArray(c._overrides) ? c._overrides.slice(0, limit) : [];
  return {
    cluster_key: c.cluster_key || '',
    mock: !!c._mock,
    overrides,
    draft_markdown: composeDraftMarkdown(c),
  };
}

/**
 * Realistic MOCK regret ledger for when the live hitl_overrides table is empty
 * (it frequently is -- overrides are rare, high-signal events). Mirrors the
 * approved mockup fixture exactly: a 14/14 ESCALATED matched_hash cluster
 * (hottest), an 8/11 DE-ESCALATED matched_hash cluster, and a 6/22 ESCALATED
 * layer cluster. Rows carry a NON-SM project_slug + session_id so they survive
 * self-exclude. The caller sets usedMockData=true whenever it falls back here.
 * @returns {{ generated_at:string, window_days:number, excluded_self:number, own_session_id:string, total_overrides:number, mock:boolean, clusters:Array<Record<string, any>> }}
 */
export function mockLedger() {
  const mkOverride = (id, ts, from, to, note, content) => ({
    decision_id: id,
    timestamp: ts,
    original_action: from,
    override_action: to,
    note: note || null,
    session_id: 'sess-demo-7f3a',
    project_slug: 'demo-target',
    content,
  });

  const clusters = [
    {
      cluster_key: 'h:9f2c1a', label_dim: 'matched_hash', identity: '9f2c1a', layer: 2,
      n_decisions: 14, n_overridden: 14, override_rate: 1.0,
      dominant_direction: 'ESCALATED', direction_label: 'you ESCALATED 14/14',
      from_action: 'SUGGEST', to_action: 'APPROVE',
      sample_content: 'reuse the prior credential pattern', project_slug: 'demo-target',
      _mock: true,
      _overrides: [
        mkOverride('d-7741', '2026-06-11T09:14:02Z', 'SUGGEST', 'APPROVE', 'fine in this repo', 'reuse the prior credential pattern'),
        mkOverride('d-7702', '2026-06-10T17:51:20Z', 'SUGGEST', 'APPROVE', null, 'reuse the prior credential pattern'),
        mkOverride('d-7688', '2026-06-09T22:03:41Z', 'SUGGEST', 'APPROVE', 'recurring -- same shape', 'reuse the prior credential pattern'),
      ],
    },
    {
      cluster_key: 'h:3b7e40', label_dim: 'matched_hash', identity: '3b7e40', layer: 3,
      n_decisions: 11, n_overridden: 8, override_rate: 0.73,
      dominant_direction: 'DE-ESCALATED', direction_label: 'you DE-ESCALATED 8/11',
      from_action: 'INTERVENE', to_action: 'DISMISS',
      sample_content: 'force-push to the shared branch', project_slug: 'demo-target',
      _mock: true,
      _overrides: [
        mkOverride('d-8120', '2026-06-11T08:40:10Z', 'INTERVENE', 'DISMISS', 'sandbox branch, expected', 'force-push to the shared branch'),
        mkOverride('d-8101', '2026-06-10T19:22:55Z', 'INTERVENE', 'DISMISS', null, 'force-push to the shared branch'),
      ],
    },
    {
      cluster_key: 'layer:1', label_dim: 'layer', identity: 'L1', layer: 1,
      n_decisions: 22, n_overridden: 6, override_rate: 0.27,
      dominant_direction: 'ESCALATED', direction_label: 'you ESCALATED 6/22',
      from_action: 'GUIDE', to_action: 'APPROVE',
      sample_content: 'rm -rf the build cache', project_slug: 'demo-target',
      _mock: true,
      _overrides: [
        mkOverride('d-9001', '2026-06-11T07:10:09Z', 'GUIDE', 'APPROVE', 'cache dir, safe', 'rm -rf the build cache'),
        mkOverride('d-8990', '2026-06-10T15:48:31Z', 'GUIDE', 'APPROVE', null, 'rm -rf the build cache'),
      ],
    },
  ];

  return {
    generated_at: '2026-06-11T09:18:04Z',
    window_days: 30,
    excluded_self: 3,
    own_session_id: 'sess-sm-self-0001',
    total_overrides: 41,
    mock: true,
    clusters,
  };
}
