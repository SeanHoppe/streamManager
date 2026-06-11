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

/**
 * GET /api/beta/flags -- the operator's stored BETA feature on/off overrides.
 * Returns { flags: { key: bool } }; missing keys are OFF (the registry merges
 * defaults). Degrades to an empty map on any error (never reads as "on").
 * @returns {Promise<{flags: Record<string, boolean>}>}
 */
export async function getBetaFlags() {
  try {
    const res = await fetch('/api/beta/flags', {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    });
    if (!res.ok) return { flags: {} };
    const data = await res.json();
    return data && typeof data === 'object' && data.flags ? data : { flags: {} };
  } catch {
    return { flags: {} };
  }
}

/**
 * POST /api/beta/flags/{key} -- set one BETA flag. Body {enabled:bool}.
 * @param {string} key
 * @param {boolean} enabled
 * @returns {Promise<{key:string, enabled:boolean}>}
 */
export function postBetaFlag(key, enabled) {
  return postJSON(`/api/beta/flags/${encodeURIComponent(String(key))}`, { enabled: !!enabled });
}

// --- coverage-analyzer helper 1 ---
/**
 * GET /api/coverage/bands?window=&fixture_id= -- BETA coverage-analyzer (#10).
 * Aggregate band distribution (ALLOW/L2-L3/L4/LEARN by routing layer) for the
 * soak cassette vs the live non-SM session window (polarity-filtered), plus an
 * optional uploaded fixture. Read-only post-hoc aggregate (M18). Degrades to an
 * empty-shape object on any error so the caller can fall back to mock data
 * (never reads as live when the server is down).
 * @param {{ window?:number, fixture_id?:string|null }} [opts]
 * @returns {Promise<{cassette?:Record<string,any>, live?:Record<string,any>, fixture?:Record<string,any>, error?:string}>}
 */
export async function getCoverageBands(opts = {}) {
  try {
    const res = await fetch(
      `/api/coverage/bands${qs({ window: opts.window, fixture_id: opts.fixture_id })}`,
      { method: 'GET', headers: { Accept: 'application/json' }, cache: 'no-store' },
    );
    if (!res.ok) return {};
    const data = await res.json();
    return data && typeof data === 'object' ? data : {};
  } catch {
    return {};
  }
}

// --- escalation-heatmap helper 1 ---
/**
 * GET /api/escalation-timeline?session_id&bucket_ms -- server pre-aggregated
 * escalation density buckets for the BETA escalation-heatmap gutter (#14).
 * Read-only, post-hoc (M18). SM-self is excluded server-side at the SQL WHERE.
 * Degrades to an empty buckets list on any error (never throws to the gutter).
 * @param {{ session_id?:string|null, bucket_ms?:number }} [opts]
 * @returns {Promise<{ bucket_ms:number, buckets:Array<{t_ms:number, counts:{GUIDE:number,INTERVENE:number,BLOCK:number}, total:number, peak:string}>, max:number, escalation_count:number }>}
 */
export async function getEscalationTimeline(opts = {}) {
  try {
    return await getJSON(`/api/escalation-timeline${qs({ session_id: opts.session_id, bucket_ms: opts.bucket_ms })}`);
  } catch {
    return { bucket_ms: opts.bucket_ms || 30000, buckets: [], max: 1, escalation_count: 0 };
  }
}

// --- hitl-bulk-dismiss helper 1 ---
/**
 * GET /api/hitl/pending/triage?session_id -- polarity-safe pending seed for the
 * BETA hitl-bulk-dismiss triage modal (#15). Same row shape as getHitlPending
 * but SM-self is excluded server-side (project_slug NOT IN the SM slug set AND
 * session_id != SM_OWN_SESSION_ID). session_id scopes to one session; omitted =>
 * across all governed (non-SM) sessions. The modal then loops the existing
 * postHitlResolve over the operator-checked rows -- this read mutates nothing.
 * @param {{ session_id?:string|null }} [opts]
 * @returns {Promise<Array<Record<string, any>>>}
 */
export function getHitlTriagePending(opts = {}) {
  return getJSON(`/api/hitl/pending/triage${qs({ session_id: opts.session_id })}`);
}

// --- health-digest helper 1 ---
/**
 * GET /api/sessions/health-digest -- the BETA health-digest source (#32).
 * Returns a single aggregated object per governed NON-SM session so the
 * SessionRail can render a pre-computed health verdict per lane WITHOUT the
 * prior 4 per-session roundtrips. Shape:
 *   { now:number, excluded_self:number, sessions: Array<{
 *       session_id, project_slug, started_at, ended_at, uptime_seconds,
 *       decision_count, latest_decision:{action,confidence,agent_id,timestamp}|null,
 *       active_agent_count, active_job_count, hitl_pending_count, hitl_mode,
 *       latest_escalation:{type,severity,timestamp}|null }> }
 * Polarity-filtered server-side (project_slug NOT IN {streamManager} AND
 * session_id != self). Degrades to an empty set on any error / fresh DB.
 * @param {{ limit?:number }} [opts]
 * @returns {Promise<{ now:number, excluded_self:number, sessions:Array<Record<string, any>> }>}
 */
export async function getSessionsHealthDigest(opts = {}) {
  return getJSON(`/api/sessions/health-digest${qs({ limit: opts.limit })}`);
}

// --- health-sparklines helper 1 ---
/**
 * GET /api/sessions/{session_id}/sparkline-data -- the health-sparklines (#34)
 * drawer detail: the last N decisions for ONE session as
 * {timestamp, confidence, action, trigger_reason, throughput}[] (newest-first).
 * Read-only, post-hoc (M18). The endpoint POLARITY-excludes SM-self (returns an
 * empty row set for an SM project_slug session or the SM own-session id), so the
 * caller never receives SM-self detail. Degrades to {rows:[], count:0, mock:false}
 * on any error -- the component then falls back to deterministic mock data.
 * @param {string} sessionId
 * @param {{ limit?:number }} [opts]
 * @returns {Promise<{ session_id:string, count:number, mock:boolean, rows:Array<Record<string, any>> }>}
 */
export async function getSparklineData(sessionId, opts = {}) {
  try {
    const url = `/api/sessions/${encodeURIComponent(String(sessionId))}/sparkline-data${qs({ limit: opts.limit })}`;
    const res = await fetch(url, { headers: { Accept: 'application/json' }, cache: 'no-store' });
    if (!res.ok) return { session_id: String(sessionId), count: 0, mock: false, rows: [] };
    const data = await res.json();
    return data && typeof data === 'object' && Array.isArray(data.rows)
      ? data
      : { session_id: String(sessionId), count: 0, mock: false, rows: [] };
  } catch {
    return { session_id: String(sessionId), count: 0, mock: false, rows: [] };
  }
}

// --- stale-cleanup helper 1 ---
/**
 * GET /api/sessions/stale?older_than_hours -- preview of stale (ended past the
 * window, not yet archived) NON-SM sessions eligible for soft-delete (BETA #46).
 * Read-only. Returns { sessions:[{id, project_slug, pid, ended_hours_ago,
 * message_count, decision_count, open_hitl}], older_than_hours, own_session_id }.
 * SM-self is excluded server-side. Degrades to {sessions:[]} on any error.
 * @param {{ older_than_hours?:number }} [opts]
 * @returns {Promise<{sessions:Array<Record<string,any>>, older_than_hours:number, own_session_id:string|null}>}
 */
export async function getStaleSessions(opts = {}) {
  try {
    return await getJSON(`/api/sessions/stale${qs({ older_than_hours: opts.older_than_hours })}`);
  } catch {
    return { sessions: [], older_than_hours: Number(opts.older_than_hours) || 24, own_session_id: null };
  }
}

// --- stale-cleanup helper 2 ---
/**
 * POST /api/sessions/{id}/archive -- soft-delete (archive) one stale session.
 * Reversible (sets deleted_at; never a hard DELETE). Refuses SM-self (HTTP 400).
 * @param {string} sessionId
 * @returns {Promise<{id:string, archived:boolean}>}
 */
export function archiveSession(sessionId) {
  return postJSON(`/api/sessions/${encodeURIComponent(String(sessionId))}/archive`);
}

// --- stale-cleanup helper 3 ---
/**
 * POST /api/sessions/{id}/restore -- un-archive one soft-deleted session
 * (clears deleted_at; the lane returns to the rail). Refuses SM-self (HTTP 400).
 * @param {string} sessionId
 * @returns {Promise<{id:string, archived:boolean}>}
 */
export function restoreSession(sessionId) {
  return postJSON(`/api/sessions/${encodeURIComponent(String(sessionId))}/restore`);
}

// --- event-cursor helper 1 ---
// --- event-cursor helper 1 ---
/**
 * GET /api/sessions/{session_id}/events?since=<cursor>&full=0|1 -- the BETA
 * event-cursor (#31) resume read. Returns the events (decision rows joined to
 * their message) strictly NEWER than the client's last-seen compound cursor
 * (d{decisions.rowid}:m{messages.rowid}), oldest-first, capped at 100. full=1
 * additionally returns the accumulated digest AT the cursor (decision_count /
 * block_count / pending_hitl_count / latest_action) for a cold-start /
 * checkpoint load. Read-only, post-hoc (M18). The endpoint POLARITY-excludes
 * SM-self (project_slug NOT IN the SM slug set AND session_id != SM_OWN_SESSION
 * _ID), so an SM-self scope yields ZERO events. Degrades to an empty event list
 * on any error -- the component then falls back to deterministic mock data
 * (never reads as live when the server is down).
 * @param {string|null} sessionId  the scope (null => ALL governed sessions path is
 *   a no-op shape; callers pass a concrete non-SM session id)
 * @param {{ since?:string, full?:0|1|boolean }} [opts]
 * @returns {Promise<{ session_id:string, since:string, cursor:string, count:number,
 *   truncated:boolean, events:Array<Record<string, any>>, digest:Record<string, any>|null }>}
 */
export async function getSessionEvents(sessionId, opts = {}) {
  const empty = {
    session_id: String(sessionId || ''),
    since: opts.since || '',
    cursor: opts.since || '',
    count: 0,
    truncated: false,
    events: [],
    digest: null,
  };
  // No concrete session scope -> nothing to resume server-side; the component
  // falls back to its mock fixture. Avoid a malformed /api/sessions//events URL.
  if (sessionId == null || sessionId === '') return empty;
  try {
    const url = `/api/sessions/${encodeURIComponent(String(sessionId))}/events${qs({ since: opts.since, full: opts.full ? 1 : 0 })}`;
    const res = await fetch(url, { method: 'GET', headers: { Accept: 'application/json' }, cache: 'no-store' });
    if (!res.ok) return empty;
    const data = await res.json();
    return data && typeof data === 'object' && Array.isArray(data.events) ? data : empty;
  } catch {
    return empty;
  }
}

// --- soak-panel helper 1 ---
// --- soak-panel helper 1 ---
/**
 * GET /api/soak/sessions -- BETA soak-panel (#16) ranked, SELF-EXCLUDED,
 * firewall-filtered NON-SM candidate sessions for the live-soak selector.
 * Each row: { session_id, project_slug, cwd, busy, last_seen_secs_ago }. The
 * server excludes SM-self (project_slug NOT IN the SM slug set AND session_id !=
 * SM_OWN_SESSION_ID) and rejects firewalled (certPortal-cwd) candidates; the
 * dropped tallies surface as { excluded_self, excluded_firewalled } so the UI
 * can render self-exclusion as a visible feature. Degrades to an empty shape on
 * any error / fresh DB (the component then falls back to deterministic mock).
 * @returns {Promise<{ sessions:Array<Record<string, any>>, excluded_self:number, excluded_firewalled:number, own_session_id:string|null }>}
 */
export async function getSoakSessions() {
  try {
    return await getJSON('/api/soak/sessions');
  } catch {
    return { sessions: [], excluded_self: 0, excluded_firewalled: 0, own_session_id: null };
  }
}

// --- soak-panel helper 2 ---
// --- soak-panel helper 2 ---
/**
 * GET /api/soak/status?limit -- BETA soak-panel (#16) read of the additive
 * soak_runs table (newest-first). Each row: { soak_id, session_id, project_slug,
 * started_at, status, polarity_pass, rejection_count, report_md }. Read-only,
 * post-hoc (M18); the row writer is the out-of-process soak_driver, never this
 * UI. Degrades to { runs:[] } on any error / empty table (component mocks).
 * @param {{ limit?:number }} [opts]
 * @returns {Promise<{ runs:Array<Record<string, any>> }>}
 */
export async function getSoakStatus(opts = {}) {
  try {
    return await getJSON(`/api/soak/status${qs({ limit: opts.limit })}`);
  } catch {
    return { runs: [] };
  }
}

// --- soak-panel helper 3 ---
// --- soak-panel helper 3 ---
/**
 * GET /api/soak/polarity-audit -- BETA soak-panel (#16) READ computation over
 * gov.db proving zero SM-self leakage: counts decision rows whose joined
 * session project_slug IS IN the SM exclusion set OR whose session_id ==
 * SM_OWN_SESSION_ID (a leak past the self-exclude WHERE-clause). Returns
 * { pass:boolean, leak_count:number, checked:number }; pass === (leak_count
 * === 0). Read-only, post-hoc (M18). Degrades to a SAFE-but-explicit default on
 * error so the component falls back to mock rather than reading as live.
 * @returns {Promise<{ pass:boolean, leak_count:number, checked:number }>}
 */
export async function getSoakPolarityAudit() {
  try {
    const data = await getJSON('/api/soak/polarity-audit');
    return data && typeof data.pass === 'boolean'
      ? data
      : { pass: false, leak_count: 0, checked: 0 };
  } catch {
    return { pass: false, leak_count: 0, checked: 0 };
  }
}

// --- ambient-soak-task helper 1 ---
// --- ambient-soak-task helper 1 ---
/**
 * GET /api/ambient/soak-status -- BETA ambient-soak-task (#2) latest-verdict +
 * cadence read for the footer chip. Returns { enabled, last_run_at,
 * last_run_ago_s, interval_minutes, verdict ("OK"|"WARN"|"NONE"), history_count,
 * excluded_self, own_session_id, mock }. The verdict is a READ attribute of the
 * freshest NON-SM ambient_runs row (polarity_violation OR a coverage_gap =>
 * WARN). Polarity-filtered server-side (project_slug NOT IN {streamManager} AND
 * session_id != self). Degrades to a SAFE empty/NONE shape on any error / fresh
 * DB so the component falls back to deterministic mock (never reads as live when
 * the server is down). Read-only, post-hoc (M18).
 * @returns {Promise<{ enabled:boolean, last_run_at:number|null, last_run_ago_s:number|null, interval_minutes:number, verdict:string, history_count:number, excluded_self:number, own_session_id:string|null, mock:boolean }>}
 */
export async function getAmbientSoakStatus() {
  try {
    const res = await fetch('/api/ambient/soak-status', {
      method: 'GET', headers: { Accept: 'application/json' }, cache: 'no-store',
    });
    if (!res.ok) return { verdict: 'NONE', history_count: 0, excluded_self: 0, interval_minutes: 30, last_run_ago_s: null, own_session_id: null };
    const data = await res.json();
    return data && typeof data === 'object' ? data : { verdict: 'NONE', history_count: 0, excluded_self: 0, interval_minutes: 30, last_run_ago_s: null, own_session_id: null };
  } catch {
    return { verdict: 'NONE', history_count: 0, excluded_self: 0, interval_minutes: 30, last_run_ago_s: null, own_session_id: null };
  }
}

// --- ambient-soak-task helper 2 ---
// --- ambient-soak-task helper 2 ---
/**
 * GET /api/ambient/soak-history?limit -- BETA ambient-soak-task (#2) newest-first
 * ledger read over the additive ambient_runs table. Returns { runs:[{ id, ts,
 * session_id, project_slug, polarity_pass, polarity_violation, coverage_gaps:[],
 * duration_s, messages_seen }], excluded_self, own_session_id }. Read-only,
 * post-hoc (M18); the row writer is the out-of-process soak_driver --mode
 * ambient, never this UI. Polarity-excludes SM-self server-side (project_slug
 * NOT IN {streamManager} AND session_id != self), with excluded_self surfaced.
 * Degrades to { runs: [] } on any error / empty table (the component then falls
 * back to deterministic mock).
 * @param {{ limit?:number }} [opts]
 * @returns {Promise<{ runs:Array<Record<string, any>>, excluded_self:number, own_session_id:string|null }>}
 */
export async function getAmbientSoakHistory(opts = {}) {
  try {
    return await getJSON(`/api/ambient/soak-history${qs({ limit: opts.limit })}`);
  } catch {
    return { runs: [], excluded_self: 0, own_session_id: null };
  }
}

// --- breach-cartography-constrained helper 1 ---
// --- breach-cartography-constrained helper 1 ---
/**
 * GET /api/breach/cartography?session_id&window_ms&limit -- BETA breach-
 * cartography-constrained (#5). Traces the decision causation chain for one
 * governed session's regression run-up (decisions -> messages -> patterns) so
 * the transient Breach Cartography modal can render the causal swimlane +
 * heuristic-ranked surgical-revert list. Read-only, post-hoc (M18). The endpoint
 * POLARITY-excludes SM-self server-side (project_slug NOT IN the SM slug set AND
 * session_id != SM_OWN_SESSION_ID), so an SM-self scope yields ZERO decisions ->
 * the component renders the polarity lockout. Degrades to an empty-shape payload
 * on any error / fresh DB so the component falls back to deterministic mock data
 * (never reads as live when the server is down).
 * @param {{ session_id?:string|null, window_ms?:number, limit?:number }} [opts]
 * @returns {Promise<{ alert_ts:number|null, window_ms:number, session_id:string,
 *   project_slug:string, excluded_self:boolean, regressed_cells:Array<Object>,
 *   maturity_delta:{cells:number, note:string},
 *   decisions:Array<Record<string, any>>, patterns:Array<Record<string, any>>,
 *   mock:boolean }>}
 */
export async function getBreachCartography(opts = {}) {
  const empty = {
    alert_ts: null,
    window_ms: Number(opts.window_ms) || 600000,
    session_id: String(opts.session_id || ''),
    project_slug: '',
    excluded_self: true,
    regressed_cells: [],
    maturity_delta: { cells: 0, note: '' },
    decisions: [],
    patterns: [],
    mock: false,
  };
  try {
    const url = `/api/breach/cartography${qs({ session_id: opts.session_id, window_ms: opts.window_ms, limit: opts.limit })}`;
    const res = await fetch(url, { method: 'GET', headers: { Accept: 'application/json' }, cache: 'no-store' });
    if (!res.ok) return empty;
    const data = await res.json();
    return data && typeof data === 'object' && Array.isArray(data.decisions) ? data : empty;
  } catch {
    return empty;
  }
}

// --- confidence-heatmap-pane helper 1 ---
// --- confidence-heatmap-pane helper 1 ---
/**
 * GET /api/heatmap?session_id&minutes&bucket_min -- server pre-aggregated
 * role x 5-min-bucket confidence grid for the BETA confidence-heatmap-pane (#9).
 * Read-only, post-hoc (M18). SM-self is excluded server-side at the SQL WHERE
 * (project_slug NOT IN the SM slug set AND session_id != SM_OWN_SESSION_ID), so
 * an SM-self scope yields roles:[], cells:[]. Each cell carries
 * {role, bucket_idx, count, mean_confidence, band, action_breakdown:
 * {ALLOW,SUGGEST,GUIDE,INTERVENE,BLOCK}}. Degrades to an empty grid shape on
 * any error -- the component then falls back to deterministic mock data (never
 * reads as live when the server is down).
 * @param {{ session_id?:string|null, minutes?:number, bucket_min?:number }} [opts]
 * @returns {Promise<{ now_ms:number, bucket_min:number, minutes:number, excluded_self:number, roles:string[], buckets:Array<{idx:number,t_ms:number,label:string}>, cells:Array<Record<string, any>> }>}
 */
export async function getHeatmap(opts = {}) {
  const empty = {
    now_ms: Date.now(),
    bucket_min: Number(opts.bucket_min) || 5,
    minutes: Number(opts.minutes) || 60,
    excluded_self: 0,
    roles: [],
    buckets: [],
    cells: [],
  };
  try {
    const data = await getJSON(
      `/api/heatmap${qs({ session_id: opts.session_id, minutes: opts.minutes, bucket_min: opts.bucket_min })}`,
    );
    return data && typeof data === 'object' && Array.isArray(data.cells) ? data : empty;
  } catch {
    return empty;
  }
}

// --- cross-session-pattern-audit-apis helper 1 ---
// --- cross-session-pattern-audit-apis helper 1 ---
/**
 * GET /api/patterns/cross-session/{session_id}/hydrated -- BETA #11 cross-session
 * pattern audit. The hydrated cross-session rules injected into ONE governed
 * (non-SM) session at engine-init, each with its reach INTO this session. Row:
 * { pattern_hash, level, last_seen_session_id, last_seen_ts, occurrence_count,
 *   success_rate, matched_decision_count_this_session, sourced_from, decay_status }.
 * POLARITY (G2): an SM-self scope (project_slug IN the SM slug set OR id == SM_OWN
 * _SESSION_ID) 404s -- the audit never exposes SM-self hydration. Read-only,
 * post-hoc (M18). Degrades to {session_id, count:0, mock:false, rows:[]} on any
 * error / 404 so the component falls back to deterministic mock data.
 * @param {string} sessionId
 * @returns {Promise<{session_id:string, count:number, mock:boolean, rows:Array<Record<string, any>>}>}
 */
export async function getHydratedPatterns(sessionId) {
  const empty = { session_id: String(sessionId || ''), count: 0, mock: false, rows: [] };
  if (!sessionId) return empty;
  try {
    const url = `/api/patterns/cross-session/${encodeURIComponent(String(sessionId))}/hydrated`;
    const res = await fetch(url, { headers: { Accept: 'application/json' }, cache: 'no-store' });
    if (!res.ok) return empty;
    const data = await res.json();
    return data && typeof data === 'object' && Array.isArray(data.rows) ? data : empty;
  } catch {
    return empty;
  }
}

// --- cross-session-pattern-audit-apis helper 2 ---
// --- cross-session-pattern-audit-apis helper 2 ---
/**
 * GET /api/patterns/{hash}/would-apply?message_content=... -- BETA #11 read-only
 * applicability probe. Runs the pattern matcher post-hoc against the rule's
 * vector and returns {applies, match_confidence, sourced_from, rationale} WITHOUT
 * emitting a verdict or touching the governance path (M18). A 500ms client guard
 * mirrors the server cap; on timeout / non-2xx / error it degrades to the
 * documented unavailable shape so the probe NEVER throws to the operator.
 * @param {string} hash
 * @param {string} text   the candidate message content
 * @returns {Promise<{applies:boolean, match_confidence:number, sourced_from:string[], rationale:string}>}
 */
export async function getPatternWouldApply(hash, text) {
  const unavailable = { applies: false, match_confidence: 0.0, sourced_from: [], rationale: 'matching engine unavailable' };
  if (!hash) return unavailable;
  let timer = null;
  const ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
  try {
    if (ctrl) timer = setTimeout(() => ctrl.abort(), 500);
    const url = `/api/patterns/${encodeURIComponent(String(hash))}/would-apply?message_content=${encodeURIComponent(String(text || ''))}`;
    const res = await fetch(url, { headers: { Accept: 'application/json' }, cache: 'no-store', signal: ctrl ? ctrl.signal : undefined });
    if (!res.ok) return unavailable;
    const data = await res.json();
    return data && typeof data === 'object' && typeof data.applies === 'boolean' ? data : unavailable;
  } catch {
    return unavailable;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

// --- escalation-timeline-causal-forensics helper 1 ---
// --- escalation-timeline-causal-forensics helper 1 ---
/**
 * GET /api/escalations?session_id&limit -- the BETA Escalation Timeline causal-
 * forensics card list (#13). DERIVED at read time from the EXISTING decision
 * rows (action IN GUIDE/INTERVENE/BLOCK); event_type is classified server-side
 * (no new column). SM-self is excluded server-side (project_slug NOT IN the SM
 * slug set AND session_id != SM_OWN_SESSION_ID). Read-only, post-hoc (M18).
 * Degrades to [] on any error / empty DB so the component falls back to mock.
 * @param {{ session_id?:string|null, limit?:number }} [opts]
 * @returns {Promise<Array<Record<string, any>>>}
 */
export async function getEscalations(opts = {}) {
  try {
    return await getJSON(`/api/escalations${qs({ session_id: opts.session_id, limit: opts.limit })}`);
  } catch {
    return [];
  }
}

// --- escalation-timeline-causal-forensics helper 2 ---
// --- escalation-timeline-causal-forensics helper 2 ---
/**
 * GET /api/escalations/{decision_id}/context?window_ms -- the split-view causal
 * context (#13): the 5 prior + 3 next same-session decisions + the agents active
 * within +/- window, all DERIVED from existing rows. SM-self context is
 * suppressed server-side (focus:null). Read-only, post-hoc (M18). Degrades to an
 * empty-but-valid shape on any error.
 * @param {string} decisionId
 * @param {{ window_ms?:number }} [opts]
 * @returns {Promise<{ decision_id:string, event_type:string, window_ms:number, focus:Record<string,any>|null, prior:Array<Record<string,any>>, next:Array<Record<string,any>>, agents_in_window:Array<Record<string,any>> }>}
 */
export async function getEscalationContext(decisionId, opts = {}) {
  const empty = { decision_id: String(decisionId || ''), event_type: '', window_ms: Number(opts.window_ms) || 10000, focus: null, prior: [], next: [], agents_in_window: [] };
  if (decisionId == null || decisionId === '') return empty;
  try {
    const url = `/api/escalations/${encodeURIComponent(String(decisionId))}/context${qs({ window_ms: opts.window_ms })}`;
    const res = await fetch(url, { method: 'GET', headers: { Accept: 'application/json' }, cache: 'no-store' });
    if (!res.ok) return empty;
    const data = await res.json();
    return data && typeof data === 'object' ? data : empty;
  } catch {
    return empty;
  }
}

// --- escalation-timeline-causal-forensics helper 3 ---
// --- escalation-timeline-causal-forensics helper 3 ---
/**
 * POST /api/escalations/{decision_id}/dismiss -- operator ack of one escalation
 * (#13). Writes ONLY the additive escalation_dismissals table; never a decisions
 * row, never a verdict (M18). Refuses SM-self (HTTP 400). Best-effort: callers
 * ack optimistically and tolerate a throw (the local ack stands for the session).
 * @param {string} decisionId
 * @returns {Promise<{decision_id:string, dismissed:boolean}>}
 */
export function dismissEscalation(decisionId) {
  return postJSON(`/api/escalations/${encodeURIComponent(String(decisionId))}/dismiss`, { decision_id: String(decisionId) });
}

// --- recorded-session-replay-forensics helper 1 ---
// --- recorded-session-replay-forensics helper 1 ---
/**
 * GET /api/soak/replay/sessions -- the BETA recorded-session-replay-forensics
 * (#23) picker source: NON-SM recorded sessions (those with >=1 decision),
 * polarity-filtered server-side (project_slug NOT IN the SM slug set AND
 * session_id != SM_OWN_SESSION_ID). Read-only, post-hoc (M18). Returns
 * { sessions:[{recorded_session_uuid, project_slug, frame_count}], excluded_self,
 * own_session_id }. Degrades to an empty shape on any error / fresh DB so the
 * component falls back to deterministic mock (never reads as live when down).
 * @param {{ limit?:number }} [opts]
 * @returns {Promise<{ sessions:Array<Record<string,any>>, excluded_self:number, own_session_id:string|null }>}
 */
export async function getReplaySessions(opts = {}) {
  try {
    return await getJSON(`/api/soak/replay/sessions${qs({ limit: opts.limit })}`);
  } catch {
    return { sessions: [], excluded_self: 0, own_session_id: null };
  }
}

// --- recorded-session-replay-forensics helper 2 ---
// --- recorded-session-replay-forensics helper 2 ---
/**
 * GET /api/soak/replay/{recorded_session_uuid} -- the BETA recorded-session-
 * replay-forensics (#23) triple set for ONE recorded NON-SM session: per frame
 * { idx, kind, content_fingerprint, original, replayed, delta }. v1 DIFFS
 * STORED DECISIONS read-only (the live re-stream engine is deferred to the
 * soak_driver --replay CLI). The endpoint POLARITY-REFUSES an SM-self target
 * (project_slug NOT IN the SM slug set AND session_id != SM_OWN_SESSION_ID),
 * returning a zero-frame shape with excluded_self_rows=1 rather than a verdict.
 * Read-only, post-hoc (M18). Degrades to an empty shape on any error / unknown
 * session so the component falls back to deterministic mock.
 * @param {string} uuid the recorded_session_uuid (a NON-SM session id)
 * @param {{ start_idx?:number, end_idx?:number }} [opts]
 * @returns {Promise<{ recorded_session_uuid:string, engine_version:string, recorded_at:string, frame_count:number, delta_count:number, polarity_filtered:boolean, excluded_self_rows:number, frames:Array<Record<string,any>> }>}
 */
export async function getReplayForensics(uuid, opts = {}) {
  const empty = {
    recorded_session_uuid: String(uuid || ''),
    engine_version: 'current',
    recorded_at: '',
    frame_count: 0,
    delta_count: 0,
    polarity_filtered: true,
    excluded_self_rows: 0,
    frames: [],
  };
  if (uuid == null || uuid === '') return empty;
  try {
    const url = `/api/soak/replay/${encodeURIComponent(String(uuid))}${qs({ start_idx: opts.start_idx, end_idx: opts.end_idx })}`;
    const res = await fetch(url, { method: 'GET', headers: { Accept: 'application/json' }, cache: 'no-store' });
    if (!res.ok) return empty;
    const data = await res.json();
    return data && typeof data === 'object' && Array.isArray(data.frames) ? data : empty;
  } catch {
    return empty;
  }
}

// --- session-checkpoint-versioning helper 1 ---
// --- session-checkpoint-versioning helper 1 ---
/**
 * GET /api/sessions/{session_id}/checkpoints -- BETA session-checkpoint-versioning
 * (#26). Lists the named digest snapshots for ONE governed session, newest-first.
 * Read-only, post-hoc (M18). The endpoint POLARITY-excludes SM-self (returns an
 * empty list for an SM project_slug session or the SM own-session id), so the
 * caller never receives SM-self checkpoints. Each row: { checkpoint_id, name,
 * timestamp, decision_count_at_checkpoint, message_count_at_checkpoint,
 * confidence, open_hitl, patterns, escalations }. Degrades to {checkpoints:[]}
 * on any error -- the component then falls back to deterministic mock data
 * (never reads as live when the server is down).
 * @param {string} sessionId
 * @returns {Promise<{ session_id:string, checkpoints:Array<Record<string, any>>, own_session_id:string|null }>}
 */
export async function getSessionCheckpoints(sessionId) {
  const empty = { session_id: String(sessionId || ''), checkpoints: [], own_session_id: null };
  if (sessionId == null || sessionId === '') return empty;
  try {
    const url = `/api/sessions/${encodeURIComponent(String(sessionId))}/checkpoints`;
    const res = await fetch(url, { headers: { Accept: 'application/json' }, cache: 'no-store' });
    if (!res.ok) return empty;
    const data = await res.json();
    return data && typeof data === 'object' && Array.isArray(data.checkpoints) ? data : empty;
  } catch {
    return empty;
  }
}

// --- session-checkpoint-versioning helper 2 ---
// --- session-checkpoint-versioning helper 2 ---
/**
 * POST /api/sessions/{session_id}/checkpoint -- BETA session-checkpoint-versioning
 * (#26). Records a named digest snapshot of one governed session's CURRENT
 * state (INSERT one row; <100ms latency budget). NEVER rewinds/mutates the live
 * session -- purely observational. Body { name }. Refuses SM-self (HTTP 400,
 * {written:false}) by SM_OWN_SESSION_ID + project_slug (polarity G2). Returns
 * { written:true, checkpoint:{...} } on success; the component appends the
 * returned checkpoint to its timeline. Throws on non-2xx (the component then
 * falls back to a client-side mock snapshot).
 * @param {string} sessionId
 * @param {string} name
 * @returns {Promise<{ written:boolean, checkpoint?:Record<string, any>, detail?:string }>}
 */
export function createSessionCheckpoint(sessionId, name) {
  return postJSON(`/api/sessions/${encodeURIComponent(String(sessionId))}/checkpoint`, { name: String(name || '') });
}

// --- session-checkpoint-versioning helper 3 ---
// --- session-checkpoint-versioning helper 3 ---
/**
 * GET /api/sessions/{session_id}/compare?checkpoint_1=&checkpoint_2= -- BETA
 * session-checkpoint-versioning (#26). Returns the PRE-COMPUTED what-changed
 * delta manifest between two checkpoints of ONE governed session (SQLite diff on
 * two stored rows; <500ms budget). All drift numbers are computed server-side --
 * the component renders them verbatim, never computing a delta client-side.
 * Shape: { checkpoint_1, checkpoint_2, name_1, name_2, decisions_1, decisions_2,
 * delta_decisions, messages_1, messages_2, delta_messages, confidence_1,
 * confidence_2, new_hitl_overrides:{count,verdict}, policy_changes_learned:
 * [{hash,applied}], escalation_delta:{count,type} }. POLARITY-excludes SM-self
 * (empty/refused for an SM session). Read-only, post-hoc (M18). Degrades to an
 * empty object on any error -- the component then falls back to a mock compare.
 * @param {string} sessionId
 * @param {string} checkpoint1
 * @param {string} checkpoint2
 * @returns {Promise<Record<string, any>>}
 */
export async function getCheckpointCompare(sessionId, checkpoint1, checkpoint2) {
  if (sessionId == null || sessionId === '') return {};
  try {
    const url = `/api/sessions/${encodeURIComponent(String(sessionId))}/compare${qs({ checkpoint_1: checkpoint1, checkpoint_2: checkpoint2 })}`;
    const res = await fetch(url, { headers: { Accept: 'application/json' }, cache: 'no-store' });
    if (!res.ok) return {};
    const data = await res.json();
    return data && typeof data === 'object' ? data : {};
  } catch {
    return {};
  }
}

// --- session-dna-heatmap-cross-pattern-topology helper 1 ---
// --- session-dna-heatmap helper 1 ---
/**
 * GET /api/patterns/cross-session-topology?session_id&limit -- the BETA
 * session-dna-heatmap (#30) source. Aggregates mean confidence per
 * (matched_hash, session_id) over the existing decisions+messages+sessions rows
 * and returns a graph shape {used_mock, excluded_self, nodes, patterns, edges,
 * isolated}: a pattern in >= 2 governed sessions yields an edge (SHARED /
 * spreading); in exactly 1 yields an isolated node tag. Read-only, post-hoc
 * (M18). SM-self is EXCLUDED server-side (project_slug NOT IN the SM slug set
 * AND session_id != SM_OWN_SESSION_ID) and the dropped count surfaces as
 * excluded_self. Degrades to an EMPTY graph on any error / fresh DB so the
 * component falls back to its deterministic mock fixture (never reads as live
 * when the server is down).
 * @param {{ session_id?:string|null, limit?:number }} [opts]
 * @returns {Promise<{ used_mock:boolean, excluded_self:number, nodes:Array<Record<string,any>>, patterns:Record<string,{level:any,payload:string}>, edges:Array<Record<string,any>>, isolated:Array<Record<string,any>> }>}
 */
export async function getCrossSessionTopology(opts = {}) {
  const empty = { used_mock: false, excluded_self: 0, nodes: [], patterns: {}, edges: [], isolated: [] };
  try {
    const data = await getJSON(`/api/patterns/cross-session-topology${qs({ session_id: opts.session_id, limit: opts.limit })}`);
    if (!data || typeof data !== 'object' || !Array.isArray(data.nodes)) return empty;
    return {
      used_mock: !!data.used_mock,
      excluded_self: Number(data.excluded_self) || 0,
      nodes: Array.isArray(data.nodes) ? data.nodes : [],
      patterns: data.patterns && typeof data.patterns === 'object' ? data.patterns : {},
      edges: Array.isArray(data.edges) ? data.edges : [],
      isolated: Array.isArray(data.isolated) ? data.isolated : [],
    };
  } catch {
    return empty;
  }
}

// --- session-story-panel-narrative-arc helper 1 ---
// --- session-story-panel-narrative-arc helper 1 ---
/**
 * GET /api/sessions/{session_id}/story -- BETA session-story (#37) read of the
 * PERSISTED narrative metadata for ONE session (written out-of-process by the
 * deferred compose_story CLI; the live arc is derived client-side regardless).
 * Read-only, post-hoc (M18). The endpoint POLARITY-excludes SM-self (project_
 * slug NOT IN the SM slug set AND session_id != SM_OWN_SESSION_ID), returning
 * {composed:false} for an SM-self scope. Degrades to a SAFE not-composed shape
 * on any error so the component falls back to its client-side arc / mock data
 * (never reads as a live composed story when the server is down).
 * @param {string} sessionId
 * @returns {Promise<{ session_id:string, composed:boolean, narrative_markdown:string|null, narrative_composed_at:number|null, narrative_model:string|null, decision_count:number }>}
 */
export async function getSessionStory(sessionId) {
  const empty = {
    session_id: String(sessionId || ''),
    composed: false,
    narrative_markdown: null,
    narrative_composed_at: null,
    narrative_model: null,
    decision_count: 0,
  };
  if (sessionId == null || sessionId === '') return empty;
  try {
    const url = `/api/sessions/${encodeURIComponent(String(sessionId))}/story`;
    const res = await fetch(url, { headers: { Accept: 'application/json' }, cache: 'no-store' });
    if (!res.ok) return empty;
    const data = await res.json();
    return data && typeof data === 'object' && typeof data.composed === 'boolean' ? data : empty;
  } catch {
    return empty;
  }
}

// --- spatial-session-sidebar helper 1 ---
// --- spatial-session-sidebar helper 1 ---
/**
 * GET /api/sessions/spatial-overview?limit -- BETA spatial-session-sidebar (#45).
 * One aggregated read of every governed NON-SM session as a spatial node
 * { session_id, project_slug, governance_mode, last_activity_ts, open_hitl,
 *   agent_slug, latency_sparkline:number[<=10], alert:string|null } plus the
 * shared-pattern edges between them { edges:[{from_session_id, to_session_id,
 * pattern_count, pattern_hashes}] }. Polarity-filtered server-side (project_slug
 * NOT IN the SM slug set AND session_id != SM_OWN_SESSION_ID); excluded_self
 * surfaces the dropped self rows. Read-only, post-hoc (M18). Degrades to an
 * empty-shape object on any error / fresh DB so the caller falls back to mock.
 * @param {{ limit?:number }} [opts]
 * @returns {Promise<{ now:number, excluded_self:number, nodes:Array<Record<string,any>>, edges:Array<Record<string,any>> }>}
 */
export async function getSpatialOverview(opts = {}) {
  const empty = { now: Math.floor(Date.now() / 1000), excluded_self: 0, nodes: [], edges: [] };
  try {
    const res = await fetch(`/api/sessions/spatial-overview${qs({ limit: opts.limit })}`, {
      method: 'GET', headers: { Accept: 'application/json' }, cache: 'no-store',
    });
    if (!res.ok) return empty;
    const data = await res.json();
    return data && typeof data === 'object' && Array.isArray(data.nodes) ? data : empty;
  } catch {
    return empty;
  }
}

// --- spatial-session-sidebar helper 2 ---
// --- spatial-session-sidebar helper 2 ---
/**
 * GET /api/sessions/pattern-edges?min_pattern_count -- BETA spatial-session-
 * sidebar (#45) standalone edge read. Same edge shape as the overview's `edges`:
 * {from_session_id, to_session_id, pattern_count, pattern_hashes}. Polarity-
 * filtered server-side. Read-only, post-hoc (M18). Degrades to {edges:[]}.
 * @param {{ min_pattern_count?:number }} [opts]
 * @returns {Promise<{ edges:Array<Record<string,any>>, excluded_self:number }>}
 */
export async function getPatternEdges(opts = {}) {
  const empty = { edges: [], excluded_self: 0 };
  try {
    const res = await fetch(`/api/sessions/pattern-edges${qs({ min_pattern_count: opts.min_pattern_count })}`, {
      method: 'GET', headers: { Accept: 'application/json' }, cache: 'no-store',
    });
    if (!res.ok) return empty;
    const data = await res.json();
    return data && typeof data === 'object' && Array.isArray(data.edges) ? data : empty;
  } catch {
    return empty;
  }
}

// --- temporal-scrubber-governance-audit helper 1 ---
// --- temporal-scrubber-governance-audit helper 1 ---
/**
 * GET /api/decisions/replay-diff/sessions -- BETA temporal-scrubber (#47) picker
 * source: governed NON-SM sessions that carry stored decisions, newest-active
 * first, each {session_id, project_slug, decision_count}. SM-self is EXCLUDED
 * server-side (project_slug NOT IN the SM slug set AND session_id !=
 * SM_OWN_SESSION_ID); the dropped self tally surfaces as {excluded_self} so the
 * picker can render self-exclusion as a VISIBLE feature (G2). Read-only,
 * post-hoc (M18). Degrades to an empty shape on any error / fresh DB (the
 * component then falls back to deterministic mock).
 * @returns {Promise<{sessions:Array<Record<string, any>>, excluded_self:number, own_session_id:string|null}>}
 */
export async function getReplayDiffSessions() {
  try {
    return await getJSON('/api/decisions/replay-diff/sessions');
  } catch {
    return { sessions: [], excluded_self: 0, own_session_id: null };
  }
}

// --- temporal-scrubber-governance-audit helper 2 ---
// --- temporal-scrubber-governance-audit helper 2 ---
/**
 * GET /api/decisions/replay-diff?session_id&a&b -- BETA temporal-scrubber (#47)
 * READ-ONLY replay-diff over the stored decision stream for one governed
 * session. `a` and `b` are 0..100 scrubber-handle positions across the
 * session's decision-time span; the server slices a window around each, keys
 * comparable decisions by a content fingerprint, and returns the newest
 * decision per fingerprint in each window paired into diff rows
 * {key, content, window_a:{action,confidence,layer,model_used,matched_hash,content,timestamp}, window_b:{...}}.
 * SM-self is EXCLUDED server-side (project_slug NOT IN the SM slug set AND
 * session_id != SM_OWN_SESSION_ID); {excluded_self} surfaces the dropped tally.
 * One post-hoc GET (M18) -- never on the verdict hot path, never a bus write.
 * Degrades to an empty shape on any error / empty window (the component then
 * falls back to deterministic mock so the corridor is always paintable).
 * @param {{ session_id:string, a?:number, b?:number }} opts
 * @returns {Promise<{session_id:string, project_slug:string, window_a_label:string, window_b_label:string, rows:Array<Record<string, any>>, excluded_self:number, polarity_filtered:boolean}>}
 */
export async function getReplayDiff(opts = {}) {
  const empty = {
    session_id: String(opts.session_id || ''),
    project_slug: '',
    window_a_label: 'window A',
    window_b_label: 'window B',
    rows: [],
    excluded_self: 0,
    polarity_filtered: true,
  };
  if (!opts.session_id) return empty;
  try {
    const data = await getJSON(
      `/api/decisions/replay-diff${qs({ session_id: opts.session_id, a: opts.a, b: opts.b })}`,
    );
    return data && typeof data === 'object' && Array.isArray(data.rows) ? data : empty;
  } catch {
    return empty;
  }
}

// --- time-machine-governance-replay helper 1 ---
// --- time-machine-governance-replay helper 1 ---
/**
 * POST /api/time-machine/replay -- BETA time-machine-governance-replay (#48).
 * Counterfactual REPLAY of the deterministic post-engine confidence-floor
 * overlay over already-stored governed (non-SM) decisions in a window. The
 * server RE-DERIVES (it does NOT re-call the model, publish a bus envelope, or
 * persist anything) and POLARITY-excludes SM-self (project_slug NOT IN the SM
 * slug set AND session_id != SM_OWN_SESSION_ID), surfacing the dropped count as
 * `excluded_self`. Read-only, post-hoc (M18). Body:
 *   { time_range_start:number(ms), time_range_end:number(ms),
 *     confidence_floor:number(0..1), hitl_mode?:'sync'|'async' }
 * Returns { window, config_delta, summary:{checked,changed,escalated,released,
 * na,mock}, excluded_self, mock, rows:[{decision_id, message_id, timestamp_ms,
 * confidence, original_action, replay_action, applies, affected, original_reason,
 * replay_reason, project_slug, session_id}] }. Degrades to { ..., mock:true,
 * rows:[] } on any error / empty window so the component falls back to its own
 * deterministic mock (never reads as live when the server is down).
 * @param {{ time_range_start:number, time_range_end:number, confidence_floor:number, hitl_mode?:string }} body
 * @returns {Promise<Record<string, any>>}
 */
export async function getTimeMachineReplay(body) {
  const empty = { window: {}, config_delta: {}, summary: { checked: 0, changed: 0, escalated: 0, released: 0, na: 0, mock: true }, excluded_self: 0, mock: true, rows: [] };
  try {
    const res = await fetch('/api/time-machine/replay', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      cache: 'no-store',
      body: JSON.stringify(body || {}),
    });
    if (!res.ok) return empty;
    const data = await res.json();
    return data && typeof data === 'object' && Array.isArray(data.rows) ? data : empty;
  } catch {
    return empty;
  }
}
