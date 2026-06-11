// api.js -- read-only typed wrappers for every preserved StreamManager
// dashboard endpoint (UI-DESIGN-SPEC SS4). This is the transport floor of
// unit u-stores. It performs NO server mutation beyond the operator-action
// POSTs that other units explicitly invoke (hitl resolve/annotate, probe ack,
// canary emit, decoy register, pattern demote, hitl mode). Everything here is
// post-hoc observability -- it never sits on the verdict hot path (M18) and
// never opens /api/commands/stream (that is the consumer-only transport, NOT
// a dashboard transport -- see M18 + spec SS4 note).
//
// Domain-agnostic (M16): this module hard-codes NO governed-target vocabulary.
// Every governed identifier (session_id, project_slug, agent profile slug,
// job/agent name) is carried through verbatim from server data. The only
// literals here are SM's own API route strings.

// ---------------------------------------------------------------------------
// Low-level fetch helpers
// ---------------------------------------------------------------------------

/**
 * Build a query string from a params object, dropping null/undefined/'' values
 * so an omitted session_id never becomes a literal "?session_id=undefined".
 * @param {Record<string, string|number|boolean|null|undefined>} [params]
 * @returns {string} leading '?' included, or '' when no params survive
 */
function qs(params) {
  if (!params) return '';
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === '') continue;
    usp.set(k, String(v));
  }
  const s = usp.toString();
  return s ? `?${s}` : '';
}

/**
 * GET a JSON endpoint. Read-only by contract. Throws on non-2xx so callers
 * (pollers, seeders) can decide whether to swallow -- the server itself
 * already degrades to empty shapes on error, but a transport-level failure
 * (server down, network) must surface to the caller's catch.
 * @template T
 * @param {string} url
 * @param {RequestInit} [init]
 * @returns {Promise<T>}
 */
async function getJSON(url, init) {
  const res = await fetch(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
    cache: 'no-store',
    ...init,
  });
  if (!res.ok) {
    throw new Error(`GET ${url} -> ${res.status} ${res.statusText}`);
  }
  return /** @type {Promise<T>} */ (res.json());
}

/**
 * POST a JSON body and parse a JSON response. Used ONLY by the operator-action
 * wrappers other units invoke (never by the post-hoc pollers). Throws on
 * non-2xx so the optimistic-resolve path (M10) can roll back on error.
 * @template T
 * @param {string} url
 * @param {unknown} [body]
 * @returns {Promise<T>}
 */
async function postJSON(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    cache: 'no-store',
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`POST ${url} -> ${res.status} ${res.statusText}`);
  }
  // Some POST endpoints (annotate) may return an empty body; tolerate it.
  const text = await res.text();
  if (!text) return /** @type {T} */ ({});
  try {
    return /** @type {T} */ (JSON.parse(text));
  } catch {
    return /** @type {T} */ ({});
  }
}

// ---------------------------------------------------------------------------
// Self-exclude (M15): read <meta name="sm-own-session-id"> at module load.
// Empty/missing meta => null => callers SKIP filtering (defense-in-depth only;
// the server already strips self rows on /events). This is exposed so
// session.js (ownSessionId store) and the decisions store can both consume the
// single canonical read.
// ---------------------------------------------------------------------------

/**
 * Read the SM's own session id injected by `GET /` into a meta tag.
 * @returns {string|null} the own session_id, or null when absent/empty
 */
export function readOwnSessionId() {
  if (typeof document === 'undefined') return null;
  const meta = document.querySelector('meta[name="sm-own-session-id"]');
  if (!meta) return null;
  const content = (meta.getAttribute('content') || '').trim();
  return content === '' ? null : content;
}

/**
 * Read the SM's own project slug(s) injected into `<meta name="sm-own-project-
 * slugs">` (the polarity-flip self-exclude by project_slug -- CLAUDE.md: SM must
 * NEVER present its own sessions as governed targets, regardless of session id).
 * Comma-separated; returned as a lowercased Set. Empty/missing => empty set =>
 * callers SKIP slug-based filtering (loud-fail-safe; mirrors readOwnSessionId).
 * @returns {Set<string>}
 */
export function readOwnProjectSlugs() {
  if (typeof document === 'undefined') return new Set();
  const meta = document.querySelector('meta[name="sm-own-project-slugs"]');
  const content = ((meta && meta.getAttribute('content')) || '').trim();
  if (content === '') return new Set();
  return new Set(content.split(',').map((s) => s.trim().toLowerCase()).filter(Boolean));
}

// ---------------------------------------------------------------------------
// Read-only typed wrappers. One function per preserved GET endpoint.
// Each returns the server shape verbatim (documented inline). Query params
// match the server signatures exactly (limit / session_id).
// ---------------------------------------------------------------------------

/**
 * GET /api/stats -- poll target every 5s (M18 post-hoc). Aggregate counters.
 * @returns {Promise<{
 *   total_decisions:number, sessions:number, active_sessions:number,
 *   graph_pct:number, avg_confidence:number,
 *   actions:Record<string, number>, error?:string }>}
 */
export function getStats() {
  return getJSON('/api/stats');
}

/**
 * GET /api/decisions?limit&session_id -- seed the Feed before SSE connects.
 * Newest-first. Server caps limit at 200. session_id scopes to one session.
 * Each row carries: rid,id,message_id,action,confidence,reasoning,
 * matched_hash,timestamp,model_used,layer,content,direction,session_id,
 * profile_slug,agent_profile_slug,attribution_plugin.
 * @param {{ limit?:number, session_id?:string|null }} [opts]
 * @returns {Promise<Array<Record<string, any>>>}
 */
export function getDecisions(opts = {}) {
  return getJSON(`/api/decisions${qs({ limit: opts.limit, session_id: opts.session_id })}`);
}

/**
 * GET /api/decisions/export -- NDJSON (application/x-ndjson) export. Returns
 * the raw text body (one JSON record per line) so u-feed can offer it as a
 * file download without re-serializing.
 * @param {{ session_id?:string|null }} [opts]
 * @returns {Promise<string>}
 */
export async function getDecisionsExport(opts = {}) {
  const res = await fetch(`/api/decisions/export${qs({ session_id: opts.session_id })}`, {
    method: 'GET',
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`GET /api/decisions/export -> ${res.status} ${res.statusText}`);
  }
  return res.text();
}

/**
 * GET /api/decisions/{id}/suggestions -- the suggestion tray for a decision.
 * @param {string|number} decisionId
 * @returns {Promise<Record<string, any>>}
 */
export function getDecisionSuggestions(decisionId) {
  return getJSON(`/api/decisions/${encodeURIComponent(String(decisionId))}/suggestions`);
}

/**
 * GET /api/agents?limit&session_id -- poll target every 8s (M18). Active
 * agents, newest last_seen first. Carries session_id, profile_slug,
 * attribution_plugin/skill, is_sidechain, first_seen/last_seen, mode_override.
 * @param {{ limit?:number, session_id?:string|null }} [opts]
 * @returns {Promise<Array<Record<string, any>>>}
 */
export function getAgents(opts = {}) {
  return getJSON(`/api/agents${qs({ limit: opts.limit, session_id: opts.session_id })}`);
}

/**
 * GET /api/sessions -- the SessionRail / selector source (M16: lanes render
 * from this data; self filtered by meta). Newest started_at first. Each row:
 * id, project_slug, pid, started_at, ended_at, hitl_mode, hitl_floor.
 * @param {{ limit?:number }} [opts]
 * @returns {Promise<Array<Record<string, any>>>}
 */
export function getSessions(opts = {}) {
  return getJSON(`/api/sessions${qs({ limit: opts.limit })}`);
}

/**
 * GET /api/sessions/external -- external claude -p sessions discovered by the
 * watcher. {sessions, count}; empty when the watcher is not running.
 * @returns {Promise<{ sessions:Array<Record<string, any>>, count:number, error?:string }>}
 */
export function getExternalSessions() {
  return getJSON('/api/sessions/external');
}

/**
 * GET /api/sessions/bg-tasks -- pending background-task tokens tracked by the
 * watcher. {tasks, count}; empty when the watcher is not running.
 * @returns {Promise<{ tasks:Array<Record<string, any>>, count:number, error?:string }>}
 */
export function getBgTasks() {
  return getJSON('/api/sessions/bg-tasks');
}

/**
 * GET /api/lifecycle/jobs?session_id -- poll target every 2s (M14/M18).
 * Open BG jobs + spawned subagents. {jobs, count}. session_id scopes to the
 * selected session (M14: filter by selected session).
 * @param {{ session_id?:string|null, limit?:number }} [opts]
 * @returns {Promise<{ jobs:Array<Record<string, any>>, count:number, error?:string }>}
 */
export function getLifecycleJobs(opts = {}) {
  return getJSON(`/api/lifecycle/jobs${qs({ session_id: opts.session_id, limit: opts.limit })}`);
}

/**
 * GET /api/registry/active -- session_ids with a hot in-process engine.
 * {active_session_ids, count, refresh_active, last_refresh_ts}.
 * @returns {Promise<{ active_session_ids:string[], count:number,
 *   refresh_active:boolean, last_refresh_ts:number|null }>}
 */
export function getRegistryActive() {
  return getJSON('/api/registry/active');
}

/**
 * GET /api/hitl/pending?session_id -- unresolved HITL rows (u-hitl-core seed).
 * session_id scopes to one session; omitted => across all sessions.
 * @param {{ session_id?:string|null }} [opts]
 * @returns {Promise<Array<Record<string, any>>>}
 */
export function getHitlPending(opts = {}) {
  return getJSON(`/api/hitl/pending${qs({ session_id: opts.session_id })}`);
}

/**
 * GET /api/patterns/cross_session -- cross-session pattern list (u-feed/u-events).
 * @returns {Promise<Array<Record<string, any>>>}
 */
export function getCrossSessionPatterns() {
  return getJSON('/api/patterns/cross_session');
}

/**
 * GET|POST /api/sm-probe?session_id&force=1 -- fetch (or force) the current
 * audit probe envelope for a session (u-audit). force=1 issues a new probe.
 * @param {{ session_id?:string|null, force?:boolean, post?:boolean }} [opts]
 * @returns {Promise<Record<string, any>>}
 */
export function getProbe(opts = {}) {
  const url = `/api/sm-probe${qs({ session_id: opts.session_id, force: opts.force ? 1 : undefined })}`;
  return opts.post ? postJSON(url) : getJSON(url);
}

// ---------------------------------------------------------------------------
// Operator-action POST wrappers. These mutate server state and are invoked by
// other units (u-hitl-core, u-audit, u-feed/events) -- NOT by the post-hoc
// pollers in this unit. They are the ONLY mutations this transport layer
// performs (M18: nothing here touches the verdict hot path).
// ---------------------------------------------------------------------------

/**
 * POST /api/hitl/resolve -- optimistic resolve (M10). Body: {pending_id, resolution}.
 * Caller filters the row immediately and restores prior state on throw.
 * @param {{ pending_id:string|number, resolution:string, [k:string]:any }} body
 * @returns {Promise<Record<string, any>>}
 */
export function postHitlResolve(body) {
  return postJSON('/api/hitl/resolve', body);
}

/**
 * POST /api/hitl/annotate -- attach an operator annotation to a pending row.
 * @param {Record<string, any>} body
 * @returns {Promise<Record<string, any>>}
 */
export function postHitlAnnotate(body) {
  return postJSON('/api/hitl/annotate', body);
}

/**
 * POST /api/sm-probe/ack -- acknowledge an audit probe (M11). Body must carry
 * brain_id + prompt_hash from the envelope and a validated session_id set.
 * @param {Record<string, any>} body
 * @returns {Promise<Record<string, any>>}
 */
export function postProbeAck(body) {
  return postJSON('/api/sm-probe/ack', body);
}

/**
 * POST /api/sm-canary/emit -- emit a Layer-2 canary echo (M12).
 * @param {Record<string, any>} body
 * @returns {Promise<Record<string, any>>}
 */
export function postCanaryEmit(body) {
  return postJSON('/api/sm-canary/emit', body);
}

/**
 * POST /api/sm-decoy/register -- register a decoy for negative-control audit.
 * @param {Record<string, any>} body
 * @returns {Promise<Record<string, any>>}
 */
export function postDecoyRegister(body) {
  return postJSON('/api/sm-decoy/register', body);
}

/**
 * POST /api/patterns/{hash}/demote -- demote a cross-session pattern.
 * @param {string} hash
 * @param {Record<string, any>} [body]
 * @returns {Promise<Record<string, any>>}
 */
export function postPatternDemote(hash, body) {
  return postJSON(`/api/patterns/${encodeURIComponent(String(hash))}/demote`, body);
}

/**
 * POST /api/hitl/mode -- switch HITL mode at runtime (M5). The server emits
 * hitl_mode_promoted on the bus; the UI exposes SYNC/ASYNC only (no off).
 * @param {Record<string, any>} body
 * @returns {Promise<Record<string, any>>}
 */
export function postHitlMode(body) {
  return postJSON('/api/hitl/mode', body);
}
