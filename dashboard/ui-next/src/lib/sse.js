// sse.js -- the /events EventSource transport. ONE connection, 3s FIXED
// reconnect (matching the live dashboard contract). It demultiplexes the
// stream into Svelte stores that every pane subscribes to:
//
//   decisionsStore   -- the verdict feed (the default `message` SSE channel,
//                        payloads WITHOUT an `event_type`). Self-excluded
//                        (M15) as defense-in-depth; capped at MAX_ROWS=300.
//   eventsStore      -- bus/message rows (default channel payloads WITH an
//                        `event_type`) -- the Events panel source.
//   busEvents        -- a fan-out emitter for the NAMED SSE events
//                        (audit.*, governance_*, hitl_*, nfr_*) bound via
//                        addEventListener. u-audit / u-hitl-core / u-events
//                        subscribe by name.
//   connectionState  -- 'connecting' | 'open' | 'reconnecting' for the
//                        header live-dot.
//
// M2 (escalation-only foreground) is encoded HERE as a single data-driven
// ranked allow-list (`ESCALATION_ALLOWLIST`) rather than scattered
// conditionals, so the S2 render-validator can assert it against one table.
// Only the three allow-listed triggers are foreground-eligible; everything
// else (new_pattern / low_confidence / governance_variance_alert) is
// badge-in-place only.
//
// M18: this transport is post-hoc. It NEVER opens /api/commands/stream (that
// is the consumer-only command transport, explicitly excluded from any
// dashboard unit) and never sits on the verdict hot path.

import { writable, get } from 'svelte/store';
import { getOwnSessionId } from './stores/session.js';
// Repair (u-selfexclude M2 BLOCKER -- single source of truth): escalation.js is
// the CANONICAL M2 allow-list (the S2 validator asserts it). sse.js keeps only
// a presentation overlay (rank/label/kind) keyed to it; the assertion below
// fails loudly if the two foreground sets ever drift, so M2 can never be
// silently defined in two places.
import { FOREGROUND_ELIGIBLE, BADGE_IN_PLACE_TYPES } from './escalation.js';

export const MAX_ROWS = 300;
const RECONNECT_MS = 3000; // FIXED per contract -- no backoff.
const EVENTS_MAX = 500; // Events panel ring buffer (mirrors live evlog MAX).

// ---------------------------------------------------------------------------
// M2 escalation allow-list -- the ranked, data-driven foreground-eligibility
// table. This is the single source of truth for "what may auto-foreground a
// frame". Three eligible triggers (INTENT.md / REQUIREMENTS.md):
//
//   desktop_pause                   -- named bus event
//   governance_negative_regression  -- named bus event
//   static-rule                     -- a static-rule BLOCK decision (carried
//                                      as a decision row, NOT a named event;
//                                      detected via classifyDecision()).
//
// Everything NOT in this set flags IN PLACE via badges only (M2). `rank`
// orders competing escalations for the escalation store consumers (lower ==
// higher severity). Keep this table the ONLY place foreground eligibility is
// decided so M2 stays auditable (S2).
// ---------------------------------------------------------------------------

/** @typedef {{ trigger:string, kind:'bus'|'decision', rank:number, label:string }} EscalationRule */

/** @type {Readonly<Record<string, EscalationRule>>} */
export const ESCALATION_ALLOWLIST = Object.freeze({
  desktop_pause: { trigger: 'desktop_pause', kind: 'bus', rank: 0, label: 'PAUSE' },
  governance_negative_regression: {
    trigger: 'governance_negative_regression',
    kind: 'bus',
    rank: 0,
    label: 'NEG REGRESSION',
  },
  'static-rule': { trigger: 'static-rule', kind: 'decision', rank: 1, label: 'STATIC RULE' },
});

// Triggers that are explicitly NOT foreground-eligible (badge-in-place only).
// Listed for documentation + so the validator can assert the negative case.
export const BADGE_IN_PLACE_TRIGGERS = Object.freeze([
  'new_pattern',
  'low_confidence',
  'governance_variance_alert',
]);

// M2 single-source-of-truth binding: assert this transport's foreground +
// badge-in-place key sets match the canonical escalation.js table EXACTLY.
// Any drift (a trigger added/removed in one place but not the other) throws at
// module load, so the two tables can never silently diverge on M2.
{
  const here = new Set(Object.keys(ESCALATION_ALLOWLIST));
  const canon = FOREGROUND_ELIGIBLE; // Set<string> from escalation.js
  const mismatch =
    here.size !== canon.size ||
    [...here].some((k) => !canon.has(k)) ||
    [...canon].some((k) => !here.has(k));
  const badgeMismatch =
    BADGE_IN_PLACE_TRIGGERS.length !== BADGE_IN_PLACE_TYPES.size ||
    BADGE_IN_PLACE_TRIGGERS.some((k) => !BADGE_IN_PLACE_TYPES.has(k));
  if (mismatch || badgeMismatch) {
    throw new Error(
      '[ui-next] M2 escalation table drift: sse.js ESCALATION_ALLOWLIST / '
      + 'BADGE_IN_PLACE_TRIGGERS disagree with the canonical lib/escalation.js. '
      + 'Edit escalation.js (the single source of truth) and mirror keys here.',
    );
  }
}

/**
 * Is this named bus event foreground-eligible (M2)? Returns the matching rule
 * or null. Pure lookup against the allow-list -- no side effects.
 * @param {string} eventType
 * @returns {EscalationRule|null}
 */
export function escalationForBusEvent(eventType) {
  const rule = ESCALATION_ALLOWLIST[eventType];
  return rule && rule.kind === 'bus' ? rule : null;
}

/**
 * Classify a decision row for escalation eligibility (M2). A static-rule BLOCK
 * is foreground-eligible; all other decisions are not. We detect static-rule
 * via a deterministic, low-layer (L0) BLOCK with no model_used -- i.e. the
 * verdict came from a static rule, not an LLM tier. This keeps "static-rule"
 * data-driven (M16: no governed-target vocabulary) instead of string-matching
 * reasoning text.
 * @param {Record<string, any>} row
 * @returns {EscalationRule|null}
 */
export function escalationForDecision(row) {
  if (!row || row.action !== 'BLOCK') return null;
  const layer = Number(row.layer) || 0;
  const model = (row.model_used || '').toString().trim();
  // L0 + no model => static-rule verdict (no LLM tier participated).
  if (layer === 0 && model === '') return ESCALATION_ALLOWLIST['static-rule'];
  return null;
}

// ---------------------------------------------------------------------------
// The named bus events this transport binds. Dispatching ALL of them is part
// of the contract -- u-audit / u-events / u-hitl-core listen by name. Keep
// this list complete (spec SS4 "Named SSE events").
// ---------------------------------------------------------------------------

export const NAMED_BUS_EVENTS = Object.freeze([
  'hitl_sync_queued',
  'hitl_timeout',
  'audit.probe',
  'audit.probe_ack',
  'audit.canary_emit',
  'audit.canary_observed',
  'audit.probe_failure',
  'audit.hallucination_detected',
  'governance_negative_regression',
  'governance_variance_alert',
  'nfr_model_routing_alert',
]);

// ---------------------------------------------------------------------------
// Stores.
// ---------------------------------------------------------------------------

/** @type {import('svelte/store').Writable<Array<Record<string, any>>>} */
export const decisionsStore = writable([]);

/** @type {import('svelte/store').Writable<Array<Record<string, any>>>} */
export const eventsStore = writable([]);

/** @type {import('svelte/store').Writable<'connecting'|'open'|'reconnecting'>} */
export const connectionState = writable('connecting');

/**
 * The escalation store: the rolling list of foreground-eligible escalations
 * the shell consumes to bump frame ACTION-REQUIRED counts + auto-foreground
 * (M2/M3). Each entry is { rule, sessionId, ts }. u-shell / u-escalation drain
 * and act on these; this module only PRODUCES them from the allow-list, so the
 * decision of "what escalates" lives in exactly one data-driven place.
 * @type {import('svelte/store').Writable<Array<{ rule:EscalationRule, sessionId:string|null, ts:number }>>}
 */
export const escalationStore = writable([]);

// ---------------------------------------------------------------------------
// Named-bus-event fan-out. Lightweight pub/sub so multiple units can listen to
// the same named event without each opening its own EventSource.
// ---------------------------------------------------------------------------

/** @type {Map<string, Set<(payload:any)=>void>>} */
const _busSubs = new Map();

/**
 * Subscribe to a named bus event (e.g. 'audit.probe'). Returns an unsubscribe
 * fn. Unknown names are allowed (no-op until such an event ever fires).
 * @param {string} eventType
 * @param {(payload:any)=>void} handler
 * @returns {()=>void}
 */
export function onBusEvent(eventType, handler) {
  let set = _busSubs.get(eventType);
  if (!set) {
    set = new Set();
    _busSubs.set(eventType, set);
  }
  set.add(handler);
  return () => set.delete(handler);
}

/** @param {string} eventType @param {any} payload */
function emitBusEvent(eventType, payload) {
  const set = _busSubs.get(eventType);
  if (!set) return;
  for (const h of set) {
    try {
      h(payload);
    } catch {
      /* one bad listener must not break the stream */
    }
  }
}

// ---------------------------------------------------------------------------
// Decision / event ingestion helpers.
// ---------------------------------------------------------------------------

/**
 * Push a decision row onto the feed, newest-first, capped at MAX_ROWS (300).
 * Self-excluded (M15): rows whose session_id matches the SM's own session id
 * are dropped (defense-in-depth; server already strips them). Missing/empty
 * own id => no filtering.
 * @param {Record<string, any>} row
 */
function pushDecision(row) {
  const own = getOwnSessionId();
  if (own && row && row.session_id === own) return; // M15
  decisionsStore.update((rows) => {
    // De-dupe by stable id: the SSE stream can re-deliver a decision that is
    // already in the seeded snapshot (or already streamed). Without this, the
    // feed holds two rows with the same id, and ReplStream's keyed {#each}
    // throws "duplicate keys in a keyed each" -- a thrown render error that
    // aborts the whole Svelte flush (every other pane's reactive update in that
    // flush is dropped). Drop any prior copy first so the freshest row wins and
    // moves to the top; keys stay unique. Mirrors HitlDock.onSyncQueued.
    const key = row && (row.id ?? row.rid);
    const base = key == null ? rows : rows.filter((r) => (r && (r.id ?? r.rid)) !== key);
    const next = [row, ...base];
    if (next.length > MAX_ROWS) next.length = MAX_ROWS;
    return next;
  });

  // M2: a static-rule BLOCK is foreground-eligible -- enqueue an escalation.
  const esc = escalationForDecision(row);
  if (esc) enqueueEscalation(esc, row.session_id || null);
}

/**
 * Push a bus/message row (default channel payload carrying `event_type`) onto
 * the Events ring buffer. Self-excluded on session_id as defense-in-depth.
 * @param {Record<string, any>} row
 */
function pushEvent(row) {
  const own = getOwnSessionId();
  if (own && row && row.session_id === own) return;
  eventsStore.update((rows) => {
    const next = [row, ...rows];
    if (next.length > EVENTS_MAX) next.length = EVENTS_MAX;
    return next;
  });
}

/** @param {EscalationRule} rule @param {string|null} sessionId */
function enqueueEscalation(rule, sessionId) {
  escalationStore.update((list) => {
    const next = [...list, { rule, sessionId, ts: Date.now() }];
    // Keep the escalation log bounded; the shell drains it, but cap anyway.
    if (next.length > 200) next.shift();
    return next;
  });
}

/**
 * Seed the decisions feed from a snapshot (the /api/decisions seed) BEFORE the
 * stream connects. Applies the same self-exclude + cap. Newest-first input is
 * assumed (the server returns DESC); we trust order and just cap.
 * @param {Array<Record<string, any>>} rows
 */
export function seedDecisions(rows) {
  const own = getOwnSessionId();
  const seen = new Set();
  const cleaned = (Array.isArray(rows) ? rows : []).filter((r) => {
    if (own && r && r.session_id === own) return false; // M15 self-exclude
    // Drop duplicate-id snapshot rows so the keyed {#each} stays unique even if
    // the source ever returns the same decision twice (keyed-each safety).
    const key = r && (r.id ?? r.rid);
    if (key != null) {
      if (seen.has(key)) return false;
      seen.add(key);
    }
    return true;
  });
  decisionsStore.set(cleaned.slice(0, MAX_ROWS));
}

// ---------------------------------------------------------------------------
// EventSource lifecycle. Single connection; 3s FIXED reconnect.
// ---------------------------------------------------------------------------

/** @type {EventSource|null} */
let _es = null;
/** @type {ReturnType<typeof setTimeout>|null} */
let _reconnectTimer = null;
let _closedByUser = false;

/** Bind the named-event listeners onto an EventSource instance. */
function bindNamedEvents(es) {
  for (const name of NAMED_BUS_EVENTS) {
    es.addEventListener(name, (/** @type {MessageEvent} */ ev) => {
      let payload;
      try {
        payload = JSON.parse(ev.data);
      } catch {
        return;
      }
      // M2: only allow-listed bus events are foreground-eligible. The fan-out
      // delivers EVERY named event to its subscribers; foreground eligibility
      // is decided solely by the allow-list (everything else is badge-only).
      const esc = escalationForBusEvent(name);
      if (esc) {
        const sid = (payload && (payload.session_id || payload.sessionId)) || null;
        enqueueEscalation(esc, sid);
      }
      emitBusEvent(name, payload);
    });
  }
}

/**
 * Open (or re-open) the /events stream. Idempotent: a second call while open is
 * a no-op. Uses a FIXED 3s reconnect on error -- never /api/commands/stream.
 */
export function connect() {
  if (typeof EventSource === 'undefined') return; // SSR / test guard
  if (_es) return;
  _closedByUser = false;
  connectionState.set(get(connectionState) === 'connecting' ? 'connecting' : 'reconnecting');

  const es = new EventSource('/events');
  _es = es;

  es.onopen = () => {
    connectionState.set('open');
  };

  // Default channel: decision rows (no event_type) vs bus/message rows
  // (event_type set). The server multiplexes both onto `message`.
  es.onmessage = (/** @type {MessageEvent} */ ev) => {
    let d;
    try {
      d = JSON.parse(ev.data);
    } catch {
      return;
    }
    if (!d || d.error) return;
    if (d.event_type) {
      pushEvent(d);
    } else {
      pushDecision(d);
    }
  };

  bindNamedEvents(es);

  es.onerror = () => {
    // FIXED 3s reconnect. Close the dead handle and schedule a fresh connect.
    try {
      es.close();
    } catch {
      /* already closed */
    }
    if (_es === es) _es = null;
    if (_closedByUser) return;
    connectionState.set('reconnecting');
    if (_reconnectTimer) clearTimeout(_reconnectTimer);
    _reconnectTimer = setTimeout(() => {
      _reconnectTimer = null;
      connect();
    }, RECONNECT_MS);
  };
}

/** Close the stream and cancel any pending reconnect (e.g. on teardown). */
export function disconnect() {
  _closedByUser = true;
  if (_reconnectTimer) {
    clearTimeout(_reconnectTimer);
    _reconnectTimer = null;
  }
  if (_es) {
    try {
      _es.close();
    } catch {
      /* noop */
    }
    _es = null;
  }
}
