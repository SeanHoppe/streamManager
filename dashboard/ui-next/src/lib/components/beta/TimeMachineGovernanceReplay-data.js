// TimeMachineGovernanceReplay-data.js -- pure helpers for the BETA feature
// "time-machine-governance-replay" (#48).
//
// This module is the deterministic CORE of the Time Machine panel: the
// read-only RE-DERIVATION of the post-engine confidence-floor overlay over
// already-stored decisions, the diff/tally math, the realistic MOCK fixture
// (used when gov.db is empty so the panel is always testable), and the
// client-side markdown export builder. It owns NO Svelte / DOM state and makes
// NO network call -- the component injects the live POST result (or this mock)
// and asks this module to shape it.
//
// WHY RE-DERIVE, NOT RE-CALL THE MODEL
//   The live governance.evaluate() applies a deterministic post-engine overlay:
//   if a decision's confidence < the operator's confidence_floor, the action is
//   capped UP to at least GUIDE (governance.py _cap_action + the confidence_floor
//   block). That overlay is a pure function of (action, confidence, floor) -- no
//   LLM call. v1 of Time Machine replays exactly THAT overlay under a trial
//   floor, so the diff is faithful WITHOUT re-running the model, WITHOUT a new
//   bus envelope, and WITHOUT any FROZEN-surface edit. The "live counterfactual
//   engine" (re-running the full pipeline) is the DEFERRED part, surfaced as a
//   read-only "from CLI" affordance in the panel -- never built in-process.
//
// ASCII-only (cp1252-safe): dash is "--". No smart quotes / em-dash.

// Action restrictiveness ranking -- mirrors governance.py _ACTION_RANK exactly
// so the client re-derivation matches the server overlay byte-for-byte.
export const ACTION_RANK = Object.freeze({
  ALLOW: 0,
  OBSERVE: 0,
  SUGGEST: 1,
  GUIDE: 2,
  INTERVENE: 3,
  BLOCK: 4,
});

/**
 * Cap an action UP to a ceiling -- returns whichever of (current, ceiling) is
 * strictly more restrictive. Mirrors governance.py _cap_action.
 * @param {string} current
 * @param {string} ceiling
 * @returns {string}
 */
export function capAction(current, ceiling) {
  const cur = ACTION_RANK[current] ?? 0;
  const ceil = ACTION_RANK[ceiling] ?? 0;
  return ceil > cur ? ceiling : current;
}

/**
 * The deterministic floor overlay for ONE decision under a trial floor. This is
 * the exact re-derivation the server performs; the client mirrors it so a mock
 * (or a server row that already carries replay_action) renders identically.
 *
 * A decision is N/A (the floor knob does not apply) when its ORIGINAL action is
 * already at or above GUIDE for a reason other than the floor (a hard
 * blocked-op / restricted-op match): lowering or raising the floor cannot change
 * a hard BLOCK. We approximate that with: if the original action rank is already
 * >= GUIDE AND the original confidence is at/above the floor, the floor did not
 * drive it -- treat as N/A. Otherwise the floor is the live lever.
 * @param {{ original_action:string, confidence:number }} row
 * @param {number} trialFloor
 * @returns {{ replay_action:string, applies:boolean }}
 */
export function deriveReplay(row, trialFloor) {
  const orig = String(row.original_action || 'ALLOW').toUpperCase();
  const conf = Number(row.confidence);
  const floor = Number(trialFloor);
  // A hard escalation (>= GUIDE) that the confidence floor did NOT cause: the
  // floor knob is irrelevant to it. We detect "floor did not cause it" as the
  // confidence being at/above the trial floor while the action is still raised.
  const origRank = ACTION_RANK[orig] ?? 0;
  if (!Number.isFinite(conf) || !Number.isFinite(floor)) {
    return { replay_action: orig, applies: false };
  }
  if (conf >= floor && origRank >= ACTION_RANK.GUIDE) {
    // already escalated for a non-floor reason; floor change cannot move it
    return { replay_action: orig, applies: false };
  }
  // The trial floor IS the lever: cap up to GUIDE when below the floor, else
  // the decision rides at its un-floored action (ALLOW family) -- we model the
  // un-floored baseline as ALLOW for rows the original floor escalated, which
  // the server provides verbatim; on the client we conservatively keep orig as
  // the base when we cannot know the un-floored action.
  const base = origRank >= ACTION_RANK.GUIDE && conf < floor ? 'ALLOW' : orig;
  const replay = conf < floor ? capAction(base, 'GUIDE') : base;
  return { replay_action: replay, applies: true };
}

/**
 * Classify a row into the paired label+color state (M4). Returns the literal
 * TEXT token (CHANGED / SAME / N/A) plus a class hint and a polarity word.
 * @param {{ original_action:string, replay_action:string, affected?:boolean, applies?:boolean }} row
 * @returns {{ state:'changed'|'same'|'na', label:string, polarity:null|{cls:'escalated'|'released', text:string} }}
 */
export function classifyRow(row) {
  const orig = String(row.original_action || '').toUpperCase();
  const rep = String(row.replay_action || '').toUpperCase();
  const applies = row.applies !== undefined ? !!row.applies : true;
  if (!applies) {
    return { state: 'na', label: 'N/A', polarity: null };
  }
  if (orig === rep) {
    return { state: 'same', label: 'SAME', polarity: null };
  }
  const more = (ACTION_RANK[rep] ?? 0) > (ACTION_RANK[orig] ?? 0);
  return {
    state: 'changed',
    label: 'CHANGED',
    polarity: more
      ? { cls: 'escalated', text: 'now escalates' }
      : { cls: 'released', text: 'now releases' },
  };
}

/**
 * Compute the load-bearing tally over a row set under a trial floor. Returns the
 * summary the aria-live region announces. Pure -- no side effects.
 * @param {Array<Record<string, any>>} rows
 * @param {number} trialFloor
 * @returns {{ checked:number, changed:number, escalated:number, released:number, na:number }}
 */
export function summarize(rows, trialFloor) {
  let changed = 0;
  let escalated = 0;
  let released = 0;
  let na = 0;
  for (const r of rows || []) {
    const c = classifyRow(r);
    if (c.state === 'na') {
      na += 1;
      continue;
    }
    if (c.state === 'changed') {
      changed += 1;
      if (c.polarity && c.polarity.cls === 'escalated') escalated += 1;
      else if (c.polarity && c.polarity.cls === 'released') released += 1;
    }
  }
  return { checked: (rows || []).length, changed, escalated, released, na };
}

/**
 * Re-derive an entire row set under a NEW trial floor on the client. Used when
 * the operator nudges the floor before re-POSTing (so the matrix updates with
 * the same deterministic overlay the server would apply). Each row keeps its
 * original_action/confidence/reason and gets a fresh replay_action + applies +
 * replay_reason. Domain-agnostic: ids/timestamps/slugs carried verbatim.
 * @param {Array<Record<string, any>>} rows
 * @param {number} trialFloor
 * @param {number} origFloor
 * @returns {Array<Record<string, any>>}
 */
export function rederive(rows, trialFloor, origFloor) {
  const f = Number(trialFloor);
  const of = Number(origFloor);
  return (rows || []).map((r) => {
    const d = deriveReplay(r, f);
    const conf = Number(r.confidence);
    const replayReason = !d.applies
      ? String(r.original_reason || 'floor does not apply to this decision')
      : conf < f
        ? `confidence_floor ${fmtFloor(f)} (got ${fmtConf(conf)}) -> escalated to GUIDE`
        : `confidence_floor ${fmtFloor(f)} (got ${fmtConf(conf)}) -> floor not tripped; ${d.replay_action}`;
    const origReason = String(
      r.original_reason ||
        (Number.isFinite(of)
          ? `confidence_floor ${fmtFloor(of)} (got ${fmtConf(conf)}) applied at live time`
          : 'original decision'),
    );
    return {
      ...r,
      replay_action: d.replay_action,
      applies: d.applies,
      affected: d.applies && String(r.original_action || '').toUpperCase() !== d.replay_action,
      original_reason: origReason,
      replay_reason: replayReason,
    };
  });
}

// -- formatting helpers (tabular, deterministic) ----------------------------

/** @param {number} n @returns {string} */
export function fmtFloor(n) {
  const v = Number(n);
  return Number.isFinite(v) ? v.toFixed(2) : '--';
}
/** @param {number} n @returns {string} */
export function fmtConf(n) {
  const v = Number(n);
  return Number.isFinite(v) ? v.toFixed(2) : '--';
}
/** @param {number} ms @returns {string} HH:MM:SS UTC */
export function fmtTime(ms) {
  const d = new Date(Number(ms) || 0);
  const p = (x) => (x < 10 ? '0' : '') + x;
  return p(d.getUTCHours()) + ':' + p(d.getUTCMinutes()) + ':' + p(d.getUTCSeconds());
}

// -- the realistic MOCK fixture ---------------------------------------------
// Matches the POST /api/time-machine/replay shape exactly so the component
// renders identically whether the data is live or mock. Used when gov.db has no
// governed (non-SM) decisions in the window. usedMockData=true is surfaced.

/**
 * Build the deterministic mock replay payload anchored at `now`. The trial floor
 * defaults to 0.50 (from a 0.60 live floor) -- the proposal's worked example.
 * @param {{ now?:number, origFloor?:number, trialFloor?:number }} [opts]
 * @returns {{ window:Record<string,any>, config_delta:Record<string,any>,
 *   summary:Record<string,any>, excluded_self:number, mock:boolean,
 *   rows:Array<Record<string,any>> }}
 */
export function mockReplay(opts = {}) {
  const now = Number(opts.now) || Date.UTC(2026, 5, 11, 6, 0, 0);
  const origFloor = Number.isFinite(opts.origFloor) ? Number(opts.origFloor) : 0.6;
  const trialFloor = Number.isFinite(opts.trialFloor) ? Number(opts.trialFloor) : 0.5;
  const start = now - 60 * 60 * 1000;
  const baseRows = [
    {
      decision_id: 'd-1041', message_id: 'm-1041', timestamp_ms: start + 20 * 60 * 1000,
      confidence: 0.54, original_action: 'GUIDE',
      original_reason: `confidence_floor ${fmtFloor(origFloor)} (got 0.54) -> escalated to GUIDE`,
      project_slug: 'demo-project-a', session_id: 'sess-A',
    },
    {
      decision_id: 'd-1042', message_id: 'm-1042', timestamp_ms: start + 21 * 60 * 1000,
      confidence: 0.92, original_action: 'ALLOW',
      original_reason: 'above floor; ALLOW',
      project_slug: 'demo-project-a', session_id: 'sess-A',
    },
    {
      decision_id: 'd-1050', message_id: 'm-1050', timestamp_ms: start + 31 * 60 * 1000,
      confidence: 0.48, original_action: 'ALLOW',
      original_reason: `floor ${fmtFloor(origFloor)} not tripped at live time -> ALLOW`,
      project_slug: 'demo-project-b', session_id: 'sess-B',
    },
    {
      decision_id: 'd-1061', message_id: 'm-1061', timestamp_ms: start + 40 * 60 * 1000,
      confidence: 0.71, original_action: 'BLOCK',
      original_reason: 'blocked_op match -- floor does not apply',
      project_slug: 'demo-project-b', session_id: 'sess-B',
    },
  ];
  const rows = rederive(baseRows, trialFloor, origFloor);
  const summary = { ...summarize(rows, trialFloor), mock: true };
  return {
    window: { start_ms: start, end_ms: now, label: 'last 1h' },
    config_delta: { confidence_floor: { from: origFloor, to: trialFloor }, hitl_mode: null },
    summary,
    excluded_self: 4,
    mock: true,
    rows,
  };
}

/**
 * Normalise a server (or mock) payload into the component's render contract.
 * Defensive: tolerates a degraded/empty server shape and falls back to mock.
 * @param {Record<string, any>|null|undefined} payload
 * @param {{ now?:number, origFloor?:number, trialFloor?:number }} [mockOpts]
 * @returns {{ data:Record<string,any>, usedMock:boolean }}
 */
export function normalizeReplay(payload, mockOpts = {}) {
  const ok =
    payload &&
    typeof payload === 'object' &&
    Array.isArray(payload.rows) &&
    payload.rows.length > 0 &&
    !payload.mock;
  if (!ok) {
    return { data: mockReplay(mockOpts), usedMock: true };
  }
  const summary =
    payload.summary && typeof payload.summary === 'object'
      ? payload.summary
      : summarize(payload.rows, (payload.config_delta?.confidence_floor?.to) ?? 0.5);
  return {
    data: {
      window: payload.window || {},
      config_delta: payload.config_delta || {},
      summary: { ...summary, mock: false },
      excluded_self: Number(payload.excluded_self) || 0,
      mock: false,
      rows: payload.rows,
    },
    usedMock: false,
  };
}

/**
 * Build the client-side markdown export (a Blob is created by the component).
 * No server write -- a team-review note an operator downloads locally.
 * @param {Record<string, any>} data the normalized replay payload
 * @returns {string} markdown text (ASCII-only)
 */
export function buildExportMarkdown(data) {
  const s = data.summary || {};
  const cd = data.config_delta || {};
  const floor = cd.confidence_floor || {};
  const win = data.window || {};
  const lines = [];
  lines.push('# Time Machine -- counterfactual governance replay');
  lines.push('');
  const startIso = win.start_ms ? new Date(win.start_ms).toISOString() : '--';
  const endIso = win.end_ms ? new Date(win.end_ms).toISOString() : '--';
  lines.push(`Window: ${win.label || 'window'} (${startIso} .. ${endIso})`);
  lines.push(
    `Config delta: confidence_floor ${fmtFloor(floor.from)} -> ${fmtFloor(floor.to)}` +
      (cd.hitl_mode ? `; hitl_mode ${cd.hitl_mode}` : ''),
  );
  lines.push(
    `Summary: ${s.changed || 0} of ${s.checked || 0} change -- +${s.escalated || 0} escalate, ` +
      `-${s.released || 0} release (${s.na || 0} N/A)`,
  );
  lines.push(`Self-excluded (polarity): ${Number(data.excluded_self) || 0} rows`);
  lines.push(s.mock ? 'Source: SAMPLE DATA (summary.mock = true)' : 'Source: LIVE gov.db');
  lines.push('');
  lines.push('| time | decision_id | conf | original | replay | state |');
  lines.push('| --- | --- | --- | --- | --- | --- |');
  for (const r of data.rows || []) {
    const c = classifyRow(r);
    lines.push(
      `| ${fmtTime(r.timestamp_ms)} | ${r.decision_id} | ${fmtConf(r.confidence)} | ` +
        `${r.original_action} | ${r.replay_action} | ${c.label} |`,
    );
  }
  lines.push('');
  lines.push(
    '_Read-only re-derivation of the deterministic confidence-floor overlay. ' +
      'No model re-call, no bus publish, nothing persisted._',
  );
  return lines.join('\n');
}
