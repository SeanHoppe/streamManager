// EventCursor-data.js -- pure (no-DOM, no-fetch) helpers + mock fixture for the
// BETA feature "event-cursor" (#31): the durable session event cursor that
// resumes the decision feed across a browser refresh.
//
// Kept separate from the .svelte component so the cursor parse/encode + the
// localStorage persistence math + the resume-state classification are
// unit-testable in isolation and the Svelte file stays presentation-focused.
//
// DOMAIN-AGNOSTIC (M16): every identifier in the mock fixture is a generic,
// invented governance slug -- NO monitored-project vocabulary, NO JOB-IDs, NO
// role names. Identity (session_id / cursor) is data; the only literals here are
// the UI's own copy + the compound-cursor format.
//
// POLARITY (G2/M15): this module persists + parses a tab-scoped cursor only. It
// performs NO read of the SM-self session; the server endpoint (and the live
// decision feed it resumes) already exclude SM-self by project_slug + session
// id. The mock fixture is generic and never SM-self.
//
// ASCII-only (cp1252-safe): dash is "--". No smart quotes, no em-dashes.

// The compound watermark format -- d{decisions.rowid}:m{messages.rowid}. This
// mirrors the existing /events SSE `id:` / Last-Event-ID contract (the decision
// rows the feed delivers carry `rid` (decisions.rowid) + `message_id`). The
// cursor's load-bearing term is the decision rowid: the resume endpoint asks for
// every decision newer than it.
const CURSOR_RE = /^d(\d+):m(\d+)$/;

/** localStorage key prefix; one entry per (session_id). Tab/origin scoping is
 * inherent to localStorage (same-origin) -- we key the session within it so a
 * multi-session operator resumes each lane independently. */
export const LS_PREFIX = 'sm.next.event-cursor.';

/** The "all governed sessions" pseudo-id used when no single session is scoped
 * (selectedSessionId === null). Kept distinct from any real session id. */
export const ALL_SCOPE_KEY = '__all__';

/**
 * Build the localStorage key for a session scope. A null/empty scope (the "ALL
 * governed sessions" view) maps to a stable sentinel so the ALL view also
 * resumes. Never collides with a real session id (sentinel is bracketed).
 * @param {string|null|undefined} sessionId
 * @returns {string}
 */
export function lsKey(sessionId) {
  const scope = sessionId == null || sessionId === '' ? ALL_SCOPE_KEY : String(sessionId);
  return LS_PREFIX + scope;
}

/**
 * Encode a compound cursor from the two rowids. Either may be null/0 (a row that
 * exists only in one table -- e.g. a HITL-queued message with no decision yet).
 * Always returns the canonical `d{n}:m{n}` string.
 * @param {number|string|null|undefined} decisionRowId
 * @param {number|string|null|undefined} messageRowId
 * @returns {string}
 */
export function encodeCursor(decisionRowId, messageRowId) {
  const d = Math.max(0, Math.floor(Number(decisionRowId) || 0));
  const m = Math.max(0, Math.floor(Number(messageRowId) || 0));
  return 'd' + d + ':m' + m;
}

/**
 * Parse a compound cursor string into its two rowids. Returns null on any
 * malformed input (so a corrupt localStorage entry degrades to "no cursor" =
 * cold seed, never a thrown render).
 * @param {string|null|undefined} cursor
 * @returns {{ d:number, m:number }|null}
 */
export function parseCursor(cursor) {
  if (typeof cursor !== 'string') return null;
  const mm = CURSOR_RE.exec(cursor.trim());
  if (!mm) return null;
  return { d: Number(mm[1]), m: Number(mm[2]) };
}

/**
 * Derive the live watermark cursor from the current decision feed rows. The
 * feed is newest-first (decisionsStore contract). The max decision rowid is the
 * cursor's load-bearing term; we pair it with the max message rowid present so
 * the popover can show a faithful compound watermark. Returns null for an empty
 * feed (nothing to checkpoint yet).
 * @param {Array<Record<string, any>>} rows  newest-first decision rows
 * @returns {string|null}
 */
export function cursorFromFeed(rows) {
  const list = Array.isArray(rows) ? rows : [];
  if (list.length === 0) return null;
  let maxD = 0;
  let maxM = 0;
  for (const r of list) {
    if (!r) continue;
    const d = Number(r.rid);
    if (Number.isFinite(d) && d > maxD) maxD = d;
    // message rowid is not carried as a number on the row; message_id is the
    // string PK. The decision rowid is the durable cursor term, so when no
    // numeric message rowid is present we leave maxM at 0 (still a valid
    // compound cursor -- the server pages on the decision rowid).
    const m = Number(r.message_rid);
    if (Number.isFinite(m) && m > maxM) maxM = m;
  }
  if (maxD === 0 && maxM === 0) return null;
  return encodeCursor(maxD, maxM);
}

/**
 * Read the persisted cursor for a session scope from localStorage. Returns null
 * when absent / unavailable / corrupt (=> cold seed). Never throws.
 * @param {string|null} sessionId
 * @returns {string|null}
 */
export function readCursor(sessionId) {
  if (typeof localStorage === 'undefined') return null;
  try {
    const raw = localStorage.getItem(lsKey(sessionId));
    if (!raw) return null;
    // Validate before returning so a corrupt entry can never poison the resume.
    return parseCursor(raw) ? raw : null;
  } catch {
    return null;
  }
}

/**
 * Persist the cursor for a session scope. A null/empty cursor REMOVES the entry
 * (so a cleared feed does not leave a stale watermark). Non-fatal on quota /
 * private-mode failure -- the in-memory feed still works, resume just won't
 * survive the next refresh.
 * @param {string|null} sessionId
 * @param {string|null} cursor
 */
export function writeCursor(sessionId, cursor) {
  if (typeof localStorage === 'undefined') return;
  try {
    if (!cursor || !parseCursor(cursor)) {
      localStorage.removeItem(lsKey(sessionId));
    } else {
      localStorage.setItem(lsKey(sessionId), cursor);
    }
  } catch {
    /* private mode / quota -- non-fatal; resume just won't persist */
  }
}

/**
 * The resume STATE machine. Three paired label+color states (M4: the WORD is
 * the load-bearing signal, color is the second channel -- never alone):
 *
 *   live      -- no saved cursor for this scope (a cold fresh seed). Filled
 *                accent dot. aria: "Live stream, fresh seed".
 *   resumed   -- a saved cursor was found AND the server returned the gap rows
 *                from it (continuity held). Hollow slate dot (calm/non-alarm).
 *   reseeded  -- a saved cursor was found but it was too old / the server
 *                returned a truncation marker (the gap exceeded the page) so the
 *                client reseeded from latest. WARN amber dot -- surfaced, never
 *                hidden. aria: "Saved position too old; reseeded from latest".
 *
 * @param {{ hadCursor:boolean, resumedCount:number, truncated:boolean }} input
 * @returns {{ state:'live'|'resumed'|'reseeded', label:string, aria:string }}
 */
export function resumeState(input) {
  const hadCursor = !!(input && input.hadCursor);
  const truncated = !!(input && input.truncated);
  if (!hadCursor) {
    return { state: 'live', label: 'LIVE', aria: 'Live stream, fresh seed' };
  }
  if (truncated) {
    return {
      state: 'reseeded',
      label: 'RESEEDED',
      aria: 'Saved position too old; reseeded from latest',
    };
  }
  const n = Math.max(0, Number(input && input.resumedCount) || 0);
  return {
    state: 'resumed',
    label: 'RESUMED',
    aria:
      'Monitoring resumed from saved cursor -- ' +
      n +
      ' event' +
      (n === 1 ? '' : 's') +
      ' restored. Activate to resume from an earlier checkpoint.',
  };
}

/** Format an integer with thousands separators (locale-stable en-US). */
export function fmtNum(n) {
  const v = Number(n);
  return Number.isFinite(v) ? v.toLocaleString('en-US') : '0';
}

/**
 * Short HH:MM:SS clock from a unix-seconds (or ms) timestamp, for the row time
 * column. Tolerates a missing/0 timestamp (-> '--:--:--').
 * @param {number|string|null|undefined} ts
 * @returns {string}
 */
export function clockTime(ts) {
  const n = Number(ts);
  if (!Number.isFinite(n) || n <= 0) return '--:--:--';
  // gov.db timestamps are unix seconds; tolerate ms by a magnitude check.
  const ms = n > 1e12 ? n : n * 1000;
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return '--:--:--';
  const p = (x) => String(x).padStart(2, '0');
  return p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
}

/**
 * Short HH:MM clock for the badge time chip.
 * @param {number|string|null|undefined} ts
 * @returns {string}
 */
export function shortTime(ts) {
  const full = clockTime(ts);
  return full === '--:--:--' ? '--:--' : full.slice(0, 5);
}

/**
 * Normalise one server event row (from GET .../events) into the shape the feed
 * mounts: {action, cursor, conf, time, kind}. Tolerates partial rows. The
 * `kind` drives the badge variant (allow/block/queued/observing).
 * @param {Record<string, any>} ev
 * @returns {{ action:string, cursor:string, detail:string, time:string, variant:string }}
 */
export function normalizeEvent(ev) {
  const e = ev || {};
  const action = String(e.action || e.type || 'OBSERVING').toUpperCase();
  const cursor = encodeCursor(e.rid || e.decision_rowid, e.message_rid || e.message_rowid);
  let variant = 'observing';
  let detail = '';
  if (action === 'ALLOW') {
    variant = 'allow';
    detail = confDetail(e);
  } else if (action === 'BLOCK') {
    variant = 'block';
    detail = confDetail(e);
  } else if (action === 'HITL' || action === 'HITL QUEUED' || action === 'QUEUED') {
    variant = 'queued';
    detail = 'pending review';
  } else {
    variant = 'observing';
    detail = String(e.kind || e.msg_type || 'tool_call');
  }
  return {
    action: variant === 'queued' ? 'HITL QUEUED' : action,
    cursor,
    detail,
    time: clockTime(e.timestamp),
    variant,
  };
}

/** Render the "conf 0.94 / L2" detail string for a decision row. */
function confDetail(e) {
  const c = Number(e.confidence);
  const conf = Number.isFinite(c) ? 'conf ' + c.toFixed(2) : 'conf --';
  const layer = e.layer === undefined || e.layer === null ? '' : ' / L' + Number(e.layer);
  return conf + layer;
}

/**
 * The realistic mock fixture served when live gov.db data is absent (fresh DB /
 * fetch error). Domain-agnostic invented values; mirrors the four event shapes
 * the mockup previews (ALLOW / BLOCK / HITL QUEUED / OBSERVING) so every badge
 * state is demonstrable headless. The cursor watermark + checkpoints below let
 * the popover render fully on the mock path. usedMockData=true is surfaced as a
 * literal text label by the component.
 * @returns {{ cursor:string, resumedCount:number, events:Array<Record<string,any>>,
 *   checkpoints:Array<{ when:string, cursor:string }> }}
 */
export function mockResume() {
  const base = Math.floor(Date.now() / 1000) - 90;
  return {
    cursor: 'd21129:m48817',
    resumedCount: 4,
    events: [
      { rid: 21130, message_rid: 0, action: 'ALLOW', confidence: 0.94, layer: 2, timestamp: base + 0 },
      { rid: 21131, message_rid: 0, action: 'BLOCK', confidence: 0.99, layer: 0, timestamp: base + 19 },
      { rid: 0, message_rid: 48819, action: 'HITL', kind: 'tool_call', timestamp: base + 28 },
      { rid: 0, message_rid: 48820, action: 'OBSERVING', kind: 'tool_call', timestamp: base + 29 },
    ],
    checkpoints: [
      { when: 'Now (last seen)', cursor: 'd21129:m48817' },
      { when: '5 min ago', cursor: 'd21088:m48740' },
      { when: '30 min ago', cursor: 'd20950:m48402' },
      { when: 'Session start', cursor: 'd18004:m41100' },
    ],
  };
}
