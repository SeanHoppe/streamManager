/**
 * contract-fixtures.js -- synthetic envelopes for the S2 render-validator.
 *
 * These are the canonical, DOMAIN-AGNOSTIC test inputs the render-validator
 * (render-validator.test.js) feeds to the contract oracles. They model the
 * shapes the live server emits on /events, /api/hitl/pending, and the named
 * bus channels -- WITHOUT importing any production module, so the fixtures are
 * an independent statement of "what the wire looks like" that the validator
 * checks the implementation against.
 *
 * ZERO-CONTAMINATION (MUST M16): every identifier here is a generic placeholder.
 * There is NO monitored-project vocabulary -- no certPortal, no JOB-IDs, no
 * concrete agent-role names beyond the FROZEN domain-agnostic governance role
 * taxonomy (prompt_constructor / developer / ... / unknown), which is an
 * SM-internal vocabulary, not a monitored-project one. Session ids are opaque
 * "sess-*" tokens; project slugs are generic "alpha"/"beta"/"gamma"; option /
 * suggestion text is abstract ("Option ...", "Alternative ..."). A reviewer
 * grepping these fixtures for a governed-project term must find nothing.
 *
 * POLARITY (MUST M15 / G2): SELF_SESSION_ID models the SM's OWN session id (the
 * value the server would inject into <meta name="sm-own-session-id">). The
 * validator asserts that the self-exclude predicate drops rows carrying it.
 *
 * Pure data only: no logic, no DOM, no framework import. ESM named exports so
 * the validator can `import { ... } from './contract-fixtures.js'`.
 *
 * @module test/contract-fixtures
 */

// ---------------------------------------------------------------------------
// Session identity fixtures (domain-agnostic, opaque)
// ---------------------------------------------------------------------------

/**
 * The SM's OWN session id. Models the value the server injects into
 * <meta name="sm-own-session-id">. M15: rows carrying THIS id must be excluded
 * from every governed pane. It is never a governed target.
 */
export const SELF_SESSION_ID = 'sess-self-0000';

/** Three distinct NON-self governed session ids (opaque, domain-agnostic). */
export const SESSION_ALPHA = 'sess-alpha-1111';
export const SESSION_BETA = 'sess-beta-2222';
export const SESSION_GAMMA = 'sess-gamma-3333';

/**
 * Generic, operator-meaningful project slugs rendered as the governed-target
 * label (M16: identity FROM DATA). Deliberately abstract -- never a real
 * monitored-project name.
 */
export const SLUG_ALPHA = 'project-alpha';
export const SLUG_BETA = 'project-beta';
export const SLUG_GAMMA = 'project-gamma';

// ---------------------------------------------------------------------------
// M2 ESCALATION FIXTURES -- the foreground allow-list oracle
// ---------------------------------------------------------------------------

/**
 * The THREE -- and only three -- signal types the M2 contract permits to
 * auto-foreground a frame. The validator asserts the implementation's
 * foreground-eligible set equals EXACTLY this set (no more, no fewer). Mirrors
 * INTENT.md/REQUIREMENTS.md and the data-driven escalation.js allow-list.
 */
export const FOREGROUND_ELIGIBLE_TYPES = Object.freeze([
  'desktop_pause',
  'governance_negative_regression',
  'static-rule',
]);

/**
 * The signal types that MUST flag IN PLACE (badge + count only) and MUST NEVER
 * foreground. The validator asserts none of these is foreground-eligible.
 */
export const BADGE_IN_PLACE_TYPES = Object.freeze([
  'new_pattern',
  'low_confidence',
  'governance_variance_alert',
]);

/**
 * Synthetic SSE bus events for each foreground-eligible trigger. Each carries a
 * NON-self session so it is a legitimate governed escalation. `event_type` is
 * the channel the live bus uses; `session_id` + `project_slug` drive M16
 * data-rendered identity.
 */
export const FOREGROUND_EVENTS = Object.freeze([
  Object.freeze({
    event_type: 'desktop_pause',
    session_id: SESSION_ALPHA,
    project_slug: SLUG_ALPHA,
    reason: 'Desktop orchestration paused',
  }),
  Object.freeze({
    event_type: 'governance_negative_regression',
    session_id: SESSION_BETA,
    project_slug: SLUG_BETA,
    reason: 'Negative regression in governance alignment',
  }),
  Object.freeze({
    event_type: 'static-rule',
    session_id: SESSION_GAMMA,
    project_slug: SLUG_GAMMA,
    reason: 'Hard static rule fired',
  }),
]);

/**
 * The hyphen/underscore spelling drift of the static-rule trigger. The contract
 * normalizes this to 'static-rule' so a single spelling cannot silently demote
 * a hard trigger to badge-in-place. The validator asserts both spellings
 * foreground.
 */
export const STATIC_RULE_ALIAS_EVENT = Object.freeze({
  event_type: 'static_rule',
  session_id: SESSION_ALPHA,
  project_slug: SLUG_ALPHA,
  reason: 'Hard static rule fired (underscore spelling)',
});

/**
 * Synthetic bus events for each badge-in-place-only signal. The validator
 * asserts NONE of these foregrounds the rail -- they raise an in-place badge
 * via other frames, never steal focus.
 */
export const BADGE_IN_PLACE_EVENTS = Object.freeze([
  Object.freeze({
    event_type: 'new_pattern',
    session_id: SESSION_ALPHA,
    project_slug: SLUG_ALPHA,
    reason: 'New behavioural pattern observed',
  }),
  Object.freeze({
    event_type: 'low_confidence',
    session_id: SESSION_BETA,
    project_slug: SLUG_BETA,
    reason: 'Low-confidence decision',
  }),
  Object.freeze({
    event_type: 'governance_variance_alert',
    session_id: SESSION_GAMMA,
    project_slug: SLUG_GAMMA,
    reason: 'Governance variance alert',
  }),
]);

/**
 * Signals that must NEVER foreground: an unknown/unrecognized type (closed-world
 * safe default -> badge-in-place) and a plain decision row (no event_type at
 * all). The validator asserts both classify as badge-in-place.
 */
export const NON_FOREGROUND_OTHER = Object.freeze([
  Object.freeze({
    event_type: 'totally_unknown_signal',
    session_id: SESSION_ALPHA,
    reason: 'Unrecognized signal -- must default to badge-in-place',
  }),
  // A bare decision row -- no event_type. Decision rows never foreground.
  Object.freeze({
    session_id: SESSION_BETA,
    action: 'allow',
    layer: 'L2',
    confidence: 0.82,
    content: 'a governed message',
  }),
]);

/**
 * A foreground-eligible trigger that belongs to the SM's OWN session. M15 +
 * M2 together: this must be dropped by self-exclude BEFORE M2 can ever
 * foreground it. The validator asserts the self-filter drops it.
 */
export const SELF_FOREGROUND_EVENT = Object.freeze({
  event_type: 'desktop_pause',
  session_id: SELF_SESSION_ID,
  reason: 'Desktop pause on the SM own session -- must be excluded',
});

// ---------------------------------------------------------------------------
// M4 BADGE FIXTURES -- paired label+color, never color-without-text
// ---------------------------------------------------------------------------

/**
 * The SIX canonical M4 badge labels. Every badge the UI renders must carry one
 * of these as visible TEXT (color is only ever the second channel). The
 * validator asserts the Badge variant table exposes exactly these labels.
 */
export const CANONICAL_BADGE_LABELS = Object.freeze([
  'ACTION REQUIRED',
  'OBSERVING',
  'DECIDED',
  'BLOCKED',
  'WARN',
  'TIMEOUT',
]);

/**
 * The ACTION REQUIRED palette contract (the one true escalation surface):
 * amber #d97706 on #fef3c7 with a 2px solid amber pulsing border. The validator
 * asserts these literals are present in the badge/hero source so color can
 * never drift away from the frozen contract.
 */
export const ACTION_REQUIRED_PALETTE = Object.freeze({
  fg: '#d97706',
  bg: '#fef3c7',
  border: '2px solid #d97706',
});

/**
 * Color tokens that MUST NEVER appear as a badge's SOLE signal. Each is paired
 * here with the text label that must accompany it. The validator uses this to
 * assert the structural rule "every color has text beside it".
 */
export const COLOR_PAIRED_WITH_TEXT = Object.freeze([
  { variant: 'action-required', label: 'ACTION REQUIRED', color: '#d97706' },
  { variant: 'observing', label: 'OBSERVING', color: '#475569' },
  { variant: 'decided', label: 'DECIDED', color: '#16a34a' },
  { variant: 'blocked', label: 'BLOCKED', color: '#dc2626' },
  { variant: 'warn', label: 'WARN', color: '#ea580c' },
  { variant: 'timeout', label: 'TIMEOUT', color: '#7c3aed' },
]);

// ---------------------------------------------------------------------------
// M6 HITL FIXTURES -- HITL ON ranked APPROVE / OVERRIDE / DISMISS
// ---------------------------------------------------------------------------

/**
 * The three operator affordances a HITL-ON pending row MUST render. The
 * validator asserts all three are present in the pending-row source.
 */
export const HITL_AFFORDANCES = Object.freeze(['Approve', 'Override', 'Dismiss']);

/**
 * A HITL-ON pending envelope with a RANKED options list (string form) +
 * advisory bias + a message hash (the reinforcement key, M6). The validator
 * feeds `options` through the ranked-list normalizer and asserts highest-rank-
 * first ordering. Option text is abstract -- no monitored-project vocabulary.
 */
export const HITL_PENDING_RANKED = Object.freeze({
  pending_id: 'pend-0001',
  message_hash: 'hash-abc123',
  session_id: SESSION_ALPHA,
  project_slug: SLUG_ALPHA,
  reason: 'Message awaits operator decision before it reaches the executor',
  // Ranked alternatives, highest priority FIRST (M6 ranked list). Abstract.
  options: Object.freeze([
    'Alternative one -- the top-ranked suggested override',
    'Alternative two -- the second-ranked override',
    'Alternative three -- the third-ranked override',
  ]),
  advisory: 'advisory only -- operator decision still required',
  advisory_confidence: 0.71,
  seconds: 60,
});

/**
 * The SAME contract with EXPLICIT object-form ranks given OUT of array order,
 * to prove the normalizer honours `rank` (lower rank number == higher
 * priority) and is not merely echoing array order. The validator asserts the
 * normalized order is rank-2, rank-5, rank-9 by VALUE.
 */
export const HITL_PENDING_RANKED_EXPLICIT = Object.freeze({
  pending_id: 'pend-0002',
  message_hash: 'hash-def456',
  session_id: SESSION_BETA,
  reason: 'Decision pending; explicit ranks supplied out of order',
  options: Object.freeze([
    Object.freeze({ value: 'opt-mid', label: 'middle by rank', rank: 5 }),
    Object.freeze({ value: 'opt-top', label: 'top by rank', rank: 2 }),
    Object.freeze({ value: 'opt-low', label: 'lowest by rank', rank: 9 }),
  ]),
  seconds: 45,
});

/** Expected normalized order (by value) for HITL_PENDING_RANKED_EXPLICIT. */
export const HITL_RANKED_EXPLICIT_EXPECTED_ORDER = Object.freeze([
  'opt-top', // rank 2
  'opt-mid', // rank 5
  'opt-low', // rank 9
]);

/**
 * A pending envelope on the SM's OWN session. Upstream (M15) it must be filtered
 * before a row is ever constructed. Present so the validator can assert the
 * self-exclude predicate drops it.
 */
export const HITL_PENDING_SELF = Object.freeze({
  pending_id: 'pend-self-0009',
  message_hash: 'hash-self-000',
  session_id: SELF_SESSION_ID,
  reason: 'Pending on the SM own session -- must be excluded (M15)',
  options: Object.freeze(['should never render']),
  seconds: 60,
});

// ---------------------------------------------------------------------------
// M1 FRAME FIXTURES -- the three guaranteed frames
// ---------------------------------------------------------------------------

/**
 * The THREE frame keys that MUST be present at page load (M1). Arrangement is
 * free; presence is not. The validator asserts the layout taxonomy materializes
 * exactly these, and that a corrupt persisted order is HEALED back to all three.
 */
export const REQUIRED_FRAME_KEYS = Object.freeze(['A', 'B', 'C']);

/**
 * Corrupt / partial persisted layout blobs. M1 requires the store to HEAL each
 * of these back to the full {A,B,C} set (presence guarantee). The validator
 * feeds these to the layout sanitiser and asserts all three survive.
 */
export const CORRUPT_LAYOUTS = Object.freeze([
  null, // no persisted blob at all
  Object.freeze({}), // empty object
  Object.freeze({ order: ['A'] }), // missing B and C
  Object.freeze({ order: ['B', 'B', 'B'] }), // dupes, missing A and C
  Object.freeze({ order: ['Z', 'Q', 'A'] }), // unknown keys + one real
  Object.freeze({ order: 'not-an-array' }), // wrong type
]);

// ---------------------------------------------------------------------------
// M13 ROLE TAXONOMY (domain-agnostic governance roles, FROZEN)
// ---------------------------------------------------------------------------

/**
 * The frozen, DOMAIN-AGNOSTIC role taxonomy Frame B renders (M13). These are
 * SM-internal governance role names -- NOT monitored-project agent-role names
 * (M16). Included so the validator can assert the role-badge set never leaks a
 * concrete governed-project role.
 */
export const ROLE_TAXONOMY = Object.freeze([
  'prompt_constructor',
  'developer',
  'code_reviewer',
  'tester',
  'frontend_architect',
  'researcher',
  'strategic_advisor',
  'health_monitor',
  'sub_agent',
  'unknown',
]);

// ---------------------------------------------------------------------------
// M16 CONTAMINATION SENTINELS
// ---------------------------------------------------------------------------

/**
 * Substrings that MUST NEVER appear in any ui-next source/test file (M16 zero-
 * contamination). The validator greps the spike source tree for these. They are
 * generic monitored-project shapes, not a leak themselves: they are the things
 * a leak would look like. Kept lowercase for case-insensitive matching.
 *
 * NOTE: this list is intentionally CONSERVATIVE -- it names structural shapes
 * (the firewalled sibling-repo token) rather than trying to enumerate a
 * governed project's whole vocabulary, which the UI cannot know. The
 * monitored-project JOB-id token is matched by JOB_ID_PATTERN below, NOT as a
 * substring here: a substring like "job-id" would false-positive on the
 * generic, domain-agnostic lifecycle field `job_id` / `data-job-id` (M14
 * renders a job's id FROM DATA -- that is correct, not contamination).
 */
export const CONTAMINATION_SENTINELS = Object.freeze([
  'certportal',
  'cert-portal',
]);

/**
 * A JOB-id regular-expression shape (e.g. "JOB-1234") that a monitored-project
 * leak would match. The validator asserts no ui-next source line matches it.
 * Domain-agnostic governance code renders ids FROM DATA, never as a literal.
 */
export const JOB_ID_PATTERN = /\bJOB-\d{3,}\b/;
