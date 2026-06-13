// RecordedSessionReplayForensics.data.js -- pure data + delta math for the BETA
// feature "recorded-session-replay-forensics" (#23). NO Svelte, NO DOM, NO
// network. The component imports the mock fallbacks + the per-frame delta /
// severity derivation from here so the math is unit-inspectable and the .svelte
// file stays presentation-only.
//
// WHAT THIS FEATURE IS (v1 scope -- CONSTRAINED ADDITIVE)
//   A side-by-side decision-delta replay forensics view over EXISTING RECORDED
//   decisions. v1 DIFFS STORED DECISIONS: the "original" column is the decision
//   as captured at record time; the "replayed" column is the current engine's
//   verdict for the same frame. The live re-stream engine (re-evaluating each
//   recorded envelope through a fresh in-process governance engine) is DEFERRED
//   to a documented out-of-process "from CLI" affordance -- it is NOT built in
//   process (no spawn / cron / subprocess / engine re-eval here). When the
//   server has no stored replay rows the component falls back to the realistic
//   mock below so the drawer is always inspectable.
//
// M16 (domain-agnostic): every label here is generic governance taxonomy --
// frame kind (routine / l2_l3 / l4), governance action (ALLOW / SUGGEST /
// GUIDE / INTERVENE / BLOCK), routing layer (L0..L4), matched pattern hash.
// NO monitored-project vocabulary / JOB-IDs / role names. A real session's
// project identity arrives ONLY from server data, never hard-coded here.
//
// G2 (polarity): the mock + the live shape both carry excluded_self_rows so the
// SM-self exclusion is rendered as a VISIBLE feature; recorded sessions are
// NON-SM by construction (the server read excludes SM-self at the SQL WHERE).
//
// ASCII-only (cp1252-safe): dash rendered as "--". No smart quotes / em-dash.

/**
 * Action strictness ordering. A REPLAYED action strictly stricter than the
 * ORIGINAL (e.g. ALLOW -> GUIDE) is an ESCALATION; a same-strength change is a
 * MOVE. Mirrors the governance verdict ladder.
 * @type {Record<string, number>}
 */
export const STRICTNESS = Object.freeze({
  ALLOW: 0,
  SUGGEST: 1,
  GUIDE: 2,
  INTERVENE: 3,
  BLOCK: 4,
});

/** @param {number|string|null|undefined} n @returns {string} an "L<n>" layer label. */
export function layerStr(n) {
  return 'L' + (Number(n) || 0);
}

/** @param {string|null|undefined} h @returns {string} the hash, or the literal "(none)". */
export function hashStr(h) {
  return h ? String(h) : '(none)';
}

/** @param {number|string|null|undefined} c @returns {string} a 2-decimal confidence string. */
export function confStr(c) {
  const v = Number(c);
  return Number.isFinite(v) ? v.toFixed(2) : '--';
}

/** @param {number} n @returns {string} a signed 2-decimal magnitude string. */
export function signed(n) {
  const v = Number(n) || 0;
  return (v > 0 ? '+' : '') + v.toFixed(2);
}

/**
 * Per-frame severity (paired with a LITERAL text label by the component -- M4,
 * color is never the sole signal):
 *   - delta.changed === false                       -> 'match'      (MATCH)
 *   - action got stricter OR routing layer rose     -> 'escalated'  (ESCALATED)
 *   - any other field moved                         -> 'moved'      (VERDICT MOVED)
 * @param {{original:Record<string,any>, replayed:Record<string,any>, delta:Record<string,any>}} f
 * @returns {'match'|'moved'|'escalated'}
 */
export function frameSeverity(f) {
  const d = (f && f.delta) || {};
  if (!d.changed) return 'match';
  const rose = (Number(d.layer_delta) || 0) > 0;
  const stricter =
    (STRICTNESS[(f.replayed && f.replayed.action) || ''] || 0) >
    (STRICTNESS[(f.original && f.original.action) || ''] || 0);
  return rose || stricter ? 'escalated' : 'moved';
}

/** @param {'match'|'moved'|'escalated'} sev @returns {string} the literal badge text (M4). */
export function sevLabel(sev) {
  if (sev === 'match') return 'MATCH';
  if (sev === 'moved') return 'VERDICT MOVED';
  return 'ESCALATED';
}

/**
 * Derive a frame's delta block from its two decision sides. Pure: given the
 * same original/replayed it always yields the same delta (the load-bearing
 * "deterministic forensics" property the operator relies on). Used to fill in /
 * recompute the delta for any frame the server returns without one, and by the
 * mock builder.
 * @param {Record<string,any>} original
 * @param {Record<string,any>} replayed
 * @returns {{changed:boolean, action_changed:boolean, confidence_delta:number, layer_delta:number, matched_hash_changed:boolean, reasoning_changed:boolean, summary?:string}}
 */
export function computeDelta(original, replayed) {
  const o = original || {};
  const r = replayed || {};
  const action_changed = String(o.action || '') !== String(r.action || '');
  const oConf = Number(o.confidence);
  const rConf = Number(r.confidence);
  const confidence_delta =
    Number.isFinite(oConf) && Number.isFinite(rConf)
      ? Math.round((rConf - oConf) * 100) / 100
      : 0;
  const layer_delta = (Number(r.layer) || 0) - (Number(o.layer) || 0);
  const matched_hash_changed = String(o.matched_hash || '') !== String(r.matched_hash || '');
  const reasoning_changed = String(o.reasoning || '') !== String(r.reasoning || '');
  const changed =
    action_changed ||
    Math.abs(confidence_delta) > 0 ||
    layer_delta !== 0 ||
    matched_hash_changed ||
    reasoning_changed;
  /** @type {Record<string,any>} */
  const delta = {
    changed,
    action_changed,
    confidence_delta,
    layer_delta,
    matched_hash_changed,
    reasoning_changed,
  };
  if (changed) {
    const parts = [];
    if (action_changed) parts.push(`action ${o.action}->${r.action}`);
    if (layer_delta !== 0) parts.push(`layer ${layerStr(o.layer)}->${layerStr(r.layer)}`);
    if (matched_hash_changed) parts.push(`pattern ${hashStr(o.matched_hash)}->${hashStr(r.matched_hash)}`);
    if (!parts.length && Math.abs(confidence_delta) > 0)
      parts.push(`confidence ${signed(confidence_delta)}`);
    delta.summary = parts.join('; ');
  }
  return /** @type {any} */ (delta);
}

/**
 * Normalize one raw server frame into the canonical {idx, kind,
 * content_fingerprint, original, replayed, delta} shape, recomputing the delta
 * from the two sides so the diff is consistent even if the server omitted it.
 * @param {Record<string,any>} raw
 * @param {number} fallbackIdx
 * @returns {{idx:number, kind:string, content_fingerprint:string, original:Record<string,any>, replayed:Record<string,any>, delta:Record<string,any>}}
 */
export function normalizeFrame(raw, fallbackIdx) {
  const f = raw && typeof raw === 'object' ? raw : {};
  const o = (f.original && typeof f.original === 'object') ? f.original : {};
  const r = (f.replayed && typeof f.replayed === 'object') ? f.replayed : {};
  const original = {
    action: String(o.action || 'ALLOW'),
    confidence: Number.isFinite(Number(o.confidence)) ? Number(o.confidence) : 0,
    layer: Number(o.layer) || 0,
    matched_hash: o.matched_hash ? String(o.matched_hash) : '',
    reasoning: o.reasoning != null ? String(o.reasoning) : '',
  };
  const replayed = {
    action: String(r.action || original.action),
    confidence: Number.isFinite(Number(r.confidence)) ? Number(r.confidence) : original.confidence,
    layer: Number.isFinite(Number(r.layer)) ? Number(r.layer) : original.layer,
    matched_hash: r.matched_hash ? String(r.matched_hash) : original.matched_hash,
    reasoning: r.reasoning != null ? String(r.reasoning) : original.reasoning,
  };
  return {
    idx: Number.isFinite(Number(f.idx)) ? Number(f.idx) : Number(fallbackIdx) || 0,
    kind: String(f.kind || 'routine'),
    content_fingerprint: String(f.content_fingerprint || ''),
    original,
    replayed,
    // Always recompute the delta from the two sides (deterministic, never trust
    // a stale server-supplied delta block).
    delta: computeDelta(original, replayed),
  };
}

/**
 * Normalize a raw server payload into the canonical replay shape. A
 * null/garbage payload, or one with zero frames, yields null so the caller can
 * treat it as "no data" and swap for the mock.
 * @param {any} raw
 * @returns {{recorded_session_uuid:string, engine_version:string, recorded_at:string, frame_count:number, delta_count:number, polarity_filtered:boolean, excluded_self_rows:number, mock:boolean, frames:Array<Record<string,any>>}|null}
 */
export function normalizeReplay(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const inFrames = Array.isArray(raw.frames) ? raw.frames : [];
  if (inFrames.length === 0) return null;
  const frames = inFrames.map((f, i) => normalizeFrame(f, i));
  const delta_count = frames.filter((f) => f.delta && f.delta.changed).length;
  return {
    recorded_session_uuid: String(raw.recorded_session_uuid || raw.session_id || ''),
    engine_version: String(raw.engine_version || ''),
    recorded_at: String(raw.recorded_at || ''),
    frame_count: frames.length,
    delta_count,
    polarity_filtered: raw.polarity_filtered !== false,
    excluded_self_rows: Number(raw.excluded_self_rows) || 0,
    mock: false,
    frames,
  };
}

/**
 * Normalize the server session-list shape into the picker rows. Each row:
 * {recorded_session_uuid, frame_count, label, project_slug}. Empty array for a
 * null / empty payload (the caller then uses the mock picker rows).
 * @param {any} raw
 * @returns {Array<{recorded_session_uuid:string, frame_count:number, project_slug:string, label:string}>}
 */
export function normalizeSessions(raw) {
  const list =
    raw && typeof raw === 'object' && Array.isArray(raw.sessions) ? raw.sessions : [];
  return list
    .map((s) => {
      const uuid = String((s && (s.recorded_session_uuid || s.session_id)) || '').trim();
      if (!uuid) return null;
      const fc = Number(s.frame_count) || 0;
      const slug = String((s && s.project_slug) || '').trim();
      return {
        recorded_session_uuid: uuid,
        frame_count: fc,
        project_slug: slug,
        label: `${uuid} (${fc} frame${fc === 1 ? '' : 's'})`,
      };
    })
    .filter(Boolean);
}

/**
 * Realistic mock replay payload -- the deterministic fallback when the server
 * returns nothing usable. Two of six frames diverge (one ESCALATED move, one
 * stricter-action escalation) so the drawer exercises every severity path
 * end-to-end without a live gov.db. Frame kinds + actions are generic
 * governance taxonomy (M16); the recorded_session_uuid is a synthetic non-SM
 * key (rs-*), never a monitored-project id.
 * @param {string} [uuid] override the session key (the picker re-renders the
 *   header so the operator sees the picker is live; the triple set is shared).
 * @returns {{recorded_session_uuid:string, engine_version:string, recorded_at:string, frame_count:number, delta_count:number, polarity_filtered:boolean, excluded_self_rows:number, mock:boolean, frames:Array<Record<string,any>>}}
 */
export function mockReplay(uuid) {
  const rawFrames = [
    {
      idx: 0,
      kind: 'routine',
      content_fingerprint: 'pytest tests/test_hitl.py -q',
      original: { action: 'ALLOW', confidence: 0.95, layer: 0, matched_hash: '', reasoning: 'observed: pytest listed routine; no destructive ops.' },
      replayed: { action: 'ALLOW', confidence: 0.95, layer: 0, matched_hash: '', reasoning: 'observed: pytest listed routine; no destructive ops.' },
    },
    {
      idx: 1,
      kind: 'routine',
      content_fingerprint: 'ls -la build/',
      original: { action: 'ALLOW', confidence: 0.98, layer: 0, matched_hash: '', reasoning: 'read-only listing; no side effects.' },
      replayed: { action: 'ALLOW', confidence: 0.98, layer: 0, matched_hash: '', reasoning: 'read-only listing; no side effects.' },
    },
    {
      idx: 2,
      kind: 'l2_l3',
      content_fingerprint: 'rm -rf node_modules/',
      original: { action: 'SUGGEST', confidence: 0.71, layer: 0, matched_hash: '', reasoning: 'scoped recursive delete inside project tree; advisory.' },
      replayed: { action: 'SUGGEST', confidence: 0.71, layer: 0, matched_hash: '', reasoning: 'scoped recursive delete inside project tree; advisory.' },
    },
    {
      idx: 3,
      kind: 'l2_l3',
      content_fingerprint: 'git push origin feature/x',
      original: { action: 'ALLOW', confidence: 0.82, layer: 0, matched_hash: '', reasoning: 'non-protected branch push; advisory only.' },
      replayed: { action: 'GUIDE', confidence: 0.61, layer: 2, matched_hash: 'h-2f9c', reasoning: 'Learn-Mode bias raised branch-push scrutiny; escalated to L2 GUIDE.' },
    },
    {
      idx: 4,
      kind: 'routine',
      content_fingerprint: 'npm run build',
      original: { action: 'ALLOW', confidence: 0.9, layer: 0, matched_hash: '', reasoning: 'standard build invocation; no destructive ops.' },
      replayed: { action: 'ALLOW', confidence: 0.9, layer: 0, matched_hash: '', reasoning: 'standard build invocation; no destructive ops.' },
    },
    {
      idx: 5,
      kind: 'l4',
      content_fingerprint: 'curl -X POST https://api.internal/deploy',
      original: { action: 'INTERVENE', confidence: 0.66, layer: 4, matched_hash: 'h-91ab', reasoning: 'external POST to a deploy endpoint; L4 alignment review.' },
      replayed: { action: 'BLOCK', confidence: 0.88, layer: 4, matched_hash: 'h-91ab', reasoning: 'code iteration hardened deploy-endpoint policy; ALLOW->BLOCK on external deploy POST.' },
    },
  ];
  const frames = rawFrames.map((f, i) => normalizeFrame(f, i));
  return {
    recorded_session_uuid: uuid || 'rs-2026-06-09-sample',
    engine_version: 'current',
    recorded_at: '2026-06-09T14:22:10Z',
    frame_count: frames.length,
    delta_count: frames.filter((f) => f.delta && f.delta.changed).length,
    polarity_filtered: true,
    excluded_self_rows: 0,
    mock: true,
    frames,
  };
}

/**
 * Realistic mock picker rows -- the fallback session list when the server
 * returns no recorded sessions. Synthetic non-SM keys only.
 * @returns {Array<{recorded_session_uuid:string, frame_count:number, project_slug:string, label:string}>}
 */
export function mockSessions() {
  return [
    { recorded_session_uuid: 'rs-2026-06-09-sample', frame_count: 6, project_slug: '', label: 'rs-2026-06-09-sample (6 frames)' },
    { recorded_session_uuid: 'rs-2026-06-08-nightly', frame_count: 6, project_slug: '', label: 'rs-2026-06-08-nightly (6 frames)' },
    { recorded_session_uuid: 'rs-2026-06-07-adhoc', frame_count: 6, project_slug: '', label: 'rs-2026-06-07-adhoc (6 frames)' },
  ];
}

/** @param {Array<Record<string,any>>} frames @returns {number[]} idxs of changed frames, ascending. */
export function deltaIndices(frames) {
  if (!Array.isArray(frames)) return [];
  return frames.filter((f) => f && f.delta && f.delta.changed).map((f) => f.idx);
}
