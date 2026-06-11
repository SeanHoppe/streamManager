// SessionPinning-data.js -- pure, framework-free data helpers for the
// "session-pinning" BETA feature (#25: Session-per-Agent Pinning swim-lane,
// Frame B). Leaf module: imports NOTHING. All identity is carried through
// verbatim from the /api/agents rows the component already received.
//
// WHAT THIS FEATURE DOES (client-side only -- no backend, no new bus envelope,
// no new table): it lets the operator nail one or more observed sub-agents to a
// PINNED group at the top of the Frame B swim-lane so churn in the "active in
// window" ordering can never bury a watched agent below the fold. Pin state is
// a per-session Set persisted in localStorage. The roster is REORDERED only; no
// agent is hidden, no count is fabricated, no server call is made.
//
// DOMAIN-AGNOSTIC (M16): this module hard-codes NO governed-target vocabulary.
// The pin key is derived from the agent's own attribution (profile_slug, else
// attribution_plugin) -- never a hardcoded monitored-project name / JOB id /
// role name. The fixed mock roster below uses GENERIC role slugs only.
//
// POLARITY (G2): this module does no querying. It only shapes rows the
// component already received from the shared agentsStore, which is self-excluded
// (project_slug NOT IN {streamManager} AND session_id != self) upstream BEFORE
// it ever reaches here. There is no path in this file that surfaces an SM-self
// row, and the localStorage pin key is scoped per (non-self) session_id.
//
// ASCII-only (cp1252-safe): dash is "--". No smart quotes, no em-dashes.

/**
 * localStorage key for a session's pin set. Mirrors the session-store idiom
 * (sm.next.<thing>.<sessionId>). When the selected scope is ALL (null), the
 * pins live under a stable "__all" bucket so a global view still persists.
 * @param {string|null|undefined} sessionId
 * @returns {string}
 */
export function pinStorageKey(sessionId) {
  const scope = sessionId == null || sessionId === '' ? '__all' : String(sessionId);
  return `sm.next.pinnedAgents.${scope}`;
}

/**
 * The stable pin SUFFIX for an agent row -- the durable identity a pin is keyed
 * on. Prefer the role/skill attribution; fall back to attribution_plugin, then
 * agent_id. Domain-agnostic (M16): always FROM DATA, never a hardcoded name.
 * @param {Record<string, any>} a
 * @returns {string}
 */
export function pinSuffix(a) {
  if (!a || typeof a !== 'object') return '';
  return (a.profile_slug || a.attribution_plugin || a.agent_id || '').toString().trim();
}

/**
 * Per-row display identity shown next to the role badge (M16: from data only).
 * @param {Record<string, any>} a
 * @returns {string}
 */
export function displayName(a) {
  if (!a || typeof a !== 'object') return 'unknown';
  return String(a.profile_slug || a.attribution_plugin || a.agent_id || 'unknown');
}

/**
 * Load a session's persisted pin set. Returns BOTH the Set (membership) and the
 * ordered list (earliest-pinned first -- the within-PINNED-group sort order).
 * Tolerates a missing/corrupt/private-mode store by returning an empty set.
 * @param {Storage|null|undefined} storage  localStorage (or a test double)
 * @param {string} key
 * @returns {{ set:Set<string>, order:string[] }}
 */
export function loadPins(storage, key) {
  try {
    if (!storage) return { set: new Set(), order: [] };
    const raw = storage.getItem(key);
    if (!raw) return { set: new Set(), order: [] };
    const arr = JSON.parse(raw);
    if (!Array.isArray(arr)) return { set: new Set(), order: [] };
    const order = arr.map((s) => String(s)).filter(Boolean);
    return { set: new Set(order), order };
  } catch {
    return { set: new Set(), order: [] };
  }
}

/**
 * Persist a pin order list (the Set membership is derivable from it). Best-
 * effort -- private mode / quota failures are swallowed (non-fatal; the in-
 * memory state remains authoritative for the page lifetime).
 * @param {Storage|null|undefined} storage
 * @param {string} key
 * @param {string[]} order
 */
export function savePins(storage, key, order) {
  try {
    if (!storage) return;
    storage.setItem(key, JSON.stringify(Array.from(order)));
  } catch {
    /* private mode / quota -- non-fatal */
  }
}

/**
 * Coerce a server timestamp (epoch seconds OR ms OR ISO string) to epoch-ms.
 * Returns -Infinity when unparseable so such a row sorts as "never seen" (idle)
 * and never crashes the comparator.
 * @param {*} ts
 * @returns {number}
 */
export function toMs(ts) {
  if (ts == null || ts === '') return -Infinity;
  if (typeof ts === 'number' && Number.isFinite(ts)) return ts < 1e12 ? ts * 1000 : ts;
  const n = Number(ts);
  if (Number.isFinite(n)) return n < 1e12 ? n * 1000 : n;
  const p = Date.parse(String(ts));
  return Number.isFinite(p) ? p : -Infinity;
}

/**
 * Project + 3-tier sort the roster: PINNED first (earliest-pinned first), then
 * ACTIVE-in-window (newest-seen first), then IDLE (newest-seen first). A row
 * that is BOTH active and pinned belongs to the PINNED tier only (it must not
 * recede when its activity lapses -- that is the whole point of the pin).
 *
 * Pure projection -- never mutates the input rows. Mirrors the live
 * AgentRoster.svelte active/idle partition so the pinned variant is a strict
 * superset of the existing FR-UI-1 ordering.
 *
 * @param {Array<Record<string, any>>} agents   the session-scoped /api/agents rows
 * @param {Set<string>} pinnedSet                pin membership (by suffix)
 * @param {string[]} pinOrder                    earliest-pinned-first suffixes
 * @param {number} nowMs                         injected clock
 * @param {number} activityWindowSec             FR-UI-9 window (clamped 1..600)
 * @returns {Array<{
 *   key:string, suffix:string, name:string, role:string|null,
 *   sidechain:boolean, skill:string|null, modeOverride:string|null,
 *   firstMs:number, lastMs:number, pinned:boolean, isActive:boolean,
 *   pinRank:number
 * }>}
 */
export function projectRoster(agents, pinnedSet, pinOrder, nowMs, activityWindowSec) {
  const winMs = Math.max(1, Math.min(600, Number(activityWindowSec) || 10)) * 1000;
  const set = pinnedSet instanceof Set ? pinnedSet : new Set();
  const order = Array.isArray(pinOrder) ? pinOrder : [];
  const now = Number.isFinite(Number(nowMs)) ? Number(nowMs) : Date.now();

  const rows = (Array.isArray(agents) ? agents : []).map((a, i) => {
    const last = toMs(a && a.last_seen);
    const first = toMs(a && a.first_seen);
    const suffix = pinSuffix(a);
    const pinned = !!suffix && set.has(suffix);
    const activeRaw = Number.isFinite(last) && now - last < winMs;
    return {
      key: rowKey(a, i),
      suffix,
      name: displayName(a),
      role: (a && a.profile_slug) ?? null,
      sidechain: !!(a && a.is_sidechain),
      skill: (a && a.attribution_skill) || null,
      modeOverride: (a && a.mode_override) || null,
      firstMs: first,
      lastMs: Number.isFinite(last) ? last : -Infinity,
      pinned,
      // a pinned row is removed from the ACTIVE tier so it lives in PINNED only
      isActive: activeRaw && !pinned,
      pinRank: pinned ? indexOrInf(order, suffix) : Infinity,
    };
  });

  rows.sort((x, y) => {
    if (x.pinned !== y.pinned) return x.pinned ? -1 : 1; // tier 1: pinned first
    if (x.pinned && y.pinned) return x.pinRank - y.pinRank; // earliest-pinned first
    if (x.isActive !== y.isActive) return x.isActive ? -1 : 1; // tier 2: active first
    return y.lastMs - x.lastMs; // within tier: newest-seen first
  });
  return rows;
}

/** @param {string[]} order @param {string} suffix @returns {number} */
function indexOrInf(order, suffix) {
  const i = order.indexOf(suffix);
  return i === -1 ? Infinity : i;
}

/**
 * Stable row key (M16): a session-scoped synthetic key so two unattributed
 * agents in different sessions never collapse into one keyed {#each} row.
 * @param {Record<string, any>} a
 * @param {number} i
 * @returns {string}
 */
function rowKey(a, i) {
  const slug = pinSuffix(a);
  const sess = (a && a.session_id) || 'sess';
  return slug ? `${sess}::${slug}` : `${sess}::idx${i}`;
}

/**
 * Realistic, domain-agnostic mock roster for when live gov.db data is absent
 * (set usedMockData=true at the call site). Mirrors the approved mockup: the
 * "developer" row has the OLDEST last_seen and would normally sink off the
 * bottom of a 13-inch viewport -- so the demo pre-pins it to prove it stays at
 * row 1. Generic role slugs only; ASCII-only; epoch SECONDS (matches the live
 * /api/agents shape). nowMs anchors the relative window so the mock is stable.
 *
 * @param {number} [nowMs]
 * @returns {{ agents:Array<Record<string, any>>, sessionId:string,
 *             nowMs:number, activityWindowSec:number, defaultPins:string[] }}
 */
export function mockRoster(nowMs) {
  const now = Number(nowMs) || Date.now();
  const s = (deltaSec) => Math.round((now - deltaSec * 1000) / 1000); // epoch SECONDS
  const sessionId = 'sess-mock-001';
  return {
    sessionId,
    nowMs: now,
    activityWindowSec: 10,
    // developer is deliberately the OLDEST last_seen (486s) -- pinned by default.
    defaultPins: ['developer'],
    agents: [
      { session_id: sessionId, profile_slug: 'developer', attribution_plugin: 'code',
        attribution_skill: 'edit-file', is_sidechain: false,
        first_seen: s(900), last_seen: s(486), mode_override: null },
      { session_id: sessionId, profile_slug: 'code_reviewer', attribution_plugin: 'review',
        attribution_skill: 'diff-review', is_sidechain: false,
        first_seen: s(840), last_seen: s(6), mode_override: null },
      { session_id: sessionId, profile_slug: 'tester', attribution_plugin: 'test',
        attribution_skill: 'run-suite', is_sidechain: false,
        first_seen: s(780), last_seen: s(1), mode_override: null },
      { session_id: sessionId, profile_slug: 'researcher', attribution_plugin: 'search',
        attribution_skill: 'grep', is_sidechain: true,
        first_seen: s(700), last_seen: s(3), mode_override: null },
      { session_id: sessionId, profile_slug: 'health_monitor', attribution_plugin: 'watch',
        attribution_skill: '', is_sidechain: false,
        first_seen: s(890), last_seen: s(600), mode_override: null },
    ],
  };
}

/**
 * Compact relative-time label vs the injected clock (e.g. "now", "3s", "2m").
 * @param {number} ms epoch-ms
 * @param {number} nowMs epoch-ms
 * @returns {string}
 */
export function relTime(ms, nowMs) {
  if (!Number.isFinite(ms)) return '';
  const d = Math.max(0, (Number(nowMs) || Date.now()) - ms);
  if (d < 1000) return 'now';
  const sec = Math.floor(d / 1000);
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}
