// RegretMiningOverrideLoop-api.js -- the single network seam for the BETA
// feature "regret-mining-override-loop" (#24). ONE read-only GET over the
// additive /api/governance/regret endpoint (a join of the EXISTING
// hitl_overrides + decisions + messages + sessions tables). It performs NO
// mutation: the "Draft as proposal" affordance composes markdown CLIENT-SIDE
// and writes nothing server-side.
//
// This wrapper lives under the component's own prefixed file (collision-free)
// so the component is self-contained even before the canonical api.js helper
// lands; the build also RETURNS the identical helper as `apiHelpers` data for
// the main thread to fold into lib/api.js. Either path yields the same shape.
//
// POLARITY (G2): the server endpoint EXCLUDES SM-self at the SQL WHERE
// (project_slug NOT IN the SM slug set AND session_id != SM_OWN_SESSION_ID) and
// surfaces the dropped tally as excluded_self. This wrapper degrades to a SAFE
// empty shape (mock:false, zero clusters) on ANY error / fresh DB so the
// component falls back to deterministic mock rather than reading as live when
// the server is down. Read-only, post-hoc (M18) -- never on the verdict hot
// path, never a bus write.
//
// ASCII-only (cp1252-safe): dash is "--".

/**
 * GET /api/governance/regret?window_days&limit -- the regret ledger. Returns
 * the ranked divergence clusters (per matched_hash / routing layer) computed
 * from the operator's own overrides, hottest-first, plus the polarity tallies.
 * Shape:
 *   { generated_at, window_days, excluded_self, own_session_id, total_overrides,
 *     mock:boolean, clusters: Array<{ cluster_key, label_dim, identity, layer,
 *       n_decisions, n_overridden, override_rate, dominant_direction,
 *       direction_label, from_action, to_action, sample_content, project_slug,
 *       overrides: Array<{ decision_id, timestamp, original_action,
 *         override_action, note, session_id, project_slug, content }> }> }
 * Degrades to an empty (zero-cluster) shape on any error.
 * @param {{ window_days?:number, limit?:number }} [opts]
 * @returns {Promise<Record<string, any>>}
 */
export async function getRegret(opts = {}) {
  const empty = {
    generated_at: '',
    window_days: Number(opts.window_days) || 30,
    excluded_self: 0,
    own_session_id: null,
    total_overrides: 0,
    mock: false,
    clusters: [],
  };
  const usp = new URLSearchParams();
  if (opts.window_days) usp.set('window_days', String(opts.window_days));
  if (opts.limit) usp.set('limit', String(opts.limit));
  const q = usp.toString();
  try {
    const res = await fetch(`/api/governance/regret${q ? `?${q}` : ''}`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    });
    if (!res.ok) return empty;
    const data = await res.json();
    return data && typeof data === 'object' && Array.isArray(data.clusters) ? data : empty;
  } catch {
    return empty;
  }
}
