/**
 * escalation.js -- the M2 escalation allow-list, encoded as ONE auditable
 * data-driven table (grafted from signal-hero-asymmetric).
 *
 * MUST M2 (escalation-only foreground): ONLY three triggers may auto-bring a
 * frame to the foreground --
 *
 *     desktop_pause
 *     governance_negative_regression
 *     static-rule
 *
 * Every other flag -- new_pattern, low_confidence, governance_variance_alert --
 * is BADGE-IN-PLACE ONLY: it raises an in-frame badge / count but MUST NOT
 * steal focus or rearrange the layout.
 *
 * The whole point of this module is that M2 lives in a single table here,
 * not scattered across event-handler conditionals. The render layer
 * (u-escalation) and the S2 render-validator both read THIS table, so the
 * contract is structural and trivially auditable: to verify M2 you read one
 * frozen object, not the diff of every SSE callback.
 *
 * Pure logic only: no DOM, no component deps, no framework import. This is a
 * leaf module -- imported by others, importing none.
 *
 * Source-of-contract cross-refs:
 *   - dashboard/static/index.html EVENT_FOREGROUND_TYPES (live foreground set)
 *   - dashboard/static/index.html FR-UI-3 severity-graded auto-foreground note
 *   - src/stream_manager/governance.py (emits governance_negative_regression)
 *
 * Note vs the live dashboard: the live EVENT_FOREGROUND_TYPES currently lists
 * {governance_negative_regression, desktop_pause}. The KingMode spec promotes
 * `static-rule` to the foreground-eligible set as the third hard trigger; it
 * is added here as a first-class allow-list entry, NOT a scattered special
 * case, so the contract stays one table.
 *
 * @module lib/escalation
 */

/**
 * Disposition a signal can receive. Exactly two outcomes -- there is no
 * "off" and no third escalation behaviour. This binary is the M2 floor.
 * @readonly
 * @enum {string}
 */
export const ESCALATION_DISPOSITION = Object.freeze({
  /** Allowed to auto-foreground a frame (steal focus / rearrange). */
  FOREGROUND: 'foreground',
  /** Flag in place via badge + count only; never moves the layout. */
  BADGE_IN_PLACE: 'badge_in_place',
});

/**
 * Severity rank, ascending. Used by the variable-weight typographic severity
 * scale (grafted from monitor-first-elevated): severity is expressed as TYPE
 * EMPHASIS, not chrome. Higher number = heavier emphasis. These ranks are
 * presentation weights only -- they do NOT change the foreground decision,
 * which is governed solely by the allow-list membership below.
 * @readonly
 * @enum {number}
 */
export const SEVERITY = Object.freeze({
  INFO: 0, // ambient, lowest emphasis
  NOTICE: 1, // a badge worth a glance
  WARN: 2, // elevated badge
  CRITICAL: 3, // the foreground-eligible tier
});

/**
 * THE M2 allow-list table. One frozen row per recognized signal type.
 *
 * `foreground: true`  -> ESCALATION_DISPOSITION.FOREGROUND  (the ONLY 3)
 * `foreground: false` -> ESCALATION_DISPOSITION.BADGE_IN_PLACE
 *
 * `severity` drives the typographic weight only. `reason` is a stable
 * human string surfaced in the badge title / aria-label (paired with M4).
 *
 * To change M2 you edit THIS object and nothing else. The S2 validator
 * asserts the foreground partition against it.
 *
 * @type {Readonly<Record<string, Readonly<{
 *   foreground: boolean,
 *   severity: number,
 *   reason: string,
 * }>>>}
 */
export const ESCALATION_TABLE = Object.freeze({
  // ---- foreground-eligible: the ONLY three that may steal focus ----
  desktop_pause: Object.freeze({
    foreground: true,
    severity: SEVERITY.CRITICAL,
    reason: 'Desktop orchestration paused -- operator attention required',
  }),
  governance_negative_regression: Object.freeze({
    foreground: true,
    severity: SEVERITY.CRITICAL,
    reason: 'Governance negative regression detected',
  }),
  'static-rule': Object.freeze({
    foreground: true,
    severity: SEVERITY.CRITICAL,
    reason: 'Static rule fired -- hard governance trigger',
  }),

  // ---- badge-in-place only: never foreground ----
  new_pattern: Object.freeze({
    foreground: false,
    severity: SEVERITY.NOTICE,
    reason: 'New behavioural pattern observed -- flagged in place',
  }),
  low_confidence: Object.freeze({
    foreground: false,
    severity: SEVERITY.NOTICE,
    reason: 'Low-confidence decision -- flagged in place',
  }),
  governance_variance_alert: Object.freeze({
    foreground: false,
    severity: SEVERITY.WARN,
    reason: 'Governance variance alert -- flagged in place',
  }),
});

/**
 * Canonical alias map: some emitters / specs spell the static-rule trigger
 * with an underscore. Normalize to the hyphenated allow-list key so a single
 * spelling drift cannot silently demote a hard trigger to badge-in-place.
 * @type {Readonly<Record<string, string>>}
 */
const TYPE_ALIASES = Object.freeze({
  static_rule: 'static-rule',
  staticrule: 'static-rule',
});

/**
 * The foreground-eligible set, derived ONCE from the table (not a second
 * hand-maintained list -- single source of truth). Frozen.
 * @type {ReadonlySet<string>}
 */
export const FOREGROUND_ELIGIBLE = Object.freeze(
  new Set(
    Object.keys(ESCALATION_TABLE).filter(
      (k) => ESCALATION_TABLE[k].foreground === true,
    ),
  ),
);

/**
 * The badge-in-place set, derived from the table. Frozen.
 * @type {ReadonlySet<string>}
 */
export const BADGE_IN_PLACE_TYPES = Object.freeze(
  new Set(
    Object.keys(ESCALATION_TABLE).filter(
      (k) => ESCALATION_TABLE[k].foreground === false,
    ),
  ),
);

/**
 * Normalize a raw signal type into its canonical allow-list key.
 * Trims, lower-cases nothing (keys are case-sensitive by contract) but
 * resolves known aliases. Returns '' for non-string / blank input.
 *
 * @param {*} type
 * @returns {string} canonical key, or '' when unrecognizable as a string.
 */
export function canonicalType(type) {
  if (typeof type !== 'string') return '';
  const t = type.trim();
  if (!t) return '';
  return Object.prototype.hasOwnProperty.call(TYPE_ALIASES, t)
    ? TYPE_ALIASES[t]
    : t;
}

/**
 * Extract the signal type from a heterogeneous event/row object. SSE bus
 * events use `event_type`; some payloads carry `type`. Read defensively so a
 * malformed event never throws in a hot handler.
 *
 * @param {*} ev
 * @returns {string} canonical type, or '' when absent.
 */
export function eventType(ev) {
  if (typeof ev === 'string') return canonicalType(ev);
  if (!ev || typeof ev !== 'object') return '';
  const raw =
    typeof ev.event_type === 'string'
      ? ev.event_type
      : typeof ev.type === 'string'
        ? ev.type
        : '';
  return canonicalType(raw);
}

/**
 * Is this signal type allowed to auto-foreground a frame?
 *
 * This is THE M2 gate. The entire foreground decision in the app routes
 * through this one function reading the one table. A type not present in the
 * table is, by construction, NOT foreground-eligible (closed-world: unknown
 * signals never steal focus -- the safe default for calm-tech monitor-first).
 *
 * @param {*} typeOrEvent a signal type string OR an event/row object.
 * @returns {boolean} true iff the signal may auto-foreground.
 */
export function isForegroundEligible(typeOrEvent) {
  const key =
    typeof typeOrEvent === 'string'
      ? canonicalType(typeOrEvent)
      : eventType(typeOrEvent);
  if (!key) return false;
  return FOREGROUND_ELIGIBLE.has(key);
}

/**
 * Classify a signal into its M2 disposition. Unknown / unrecognized types
 * default to BADGE_IN_PLACE (never foreground) -- closed-world safe default.
 *
 * @param {*} typeOrEvent a signal type string OR an event/row object.
 * @returns {string} an ESCALATION_DISPOSITION value.
 */
export function classify(typeOrEvent) {
  return isForegroundEligible(typeOrEvent)
    ? ESCALATION_DISPOSITION.FOREGROUND
    : ESCALATION_DISPOSITION.BADGE_IN_PLACE;
}

/**
 * Resolve the full escalation descriptor for a signal: its canonical type,
 * disposition, severity weight, foreground flag, and human reason string
 * (for the M4 paired badge title / aria-label).
 *
 * Known types resolve from the table. Unknown-but-stringy types resolve to a
 * safe badge-in-place descriptor at INFO severity with a generic reason, so
 * the render layer always has a complete, non-throwing descriptor. Returns
 * null only when no type can be extracted at all.
 *
 * @param {*} typeOrEvent a signal type string OR an event/row object.
 * @returns {null | Readonly<{
 *   type: string,
 *   disposition: string,
 *   foreground: boolean,
 *   severity: number,
 *   reason: string,
 *   known: boolean,
 * }>}
 */
export function describe(typeOrEvent) {
  const type =
    typeof typeOrEvent === 'string'
      ? canonicalType(typeOrEvent)
      : eventType(typeOrEvent);
  if (!type) return null;
  const entry = ESCALATION_TABLE[type];
  if (entry) {
    return Object.freeze({
      type,
      disposition: entry.foreground
        ? ESCALATION_DISPOSITION.FOREGROUND
        : ESCALATION_DISPOSITION.BADGE_IN_PLACE,
      foreground: entry.foreground,
      severity: entry.severity,
      reason: entry.reason,
      known: true,
    });
  }
  // Unknown signal: safe badge-in-place default, lowest emphasis.
  return Object.freeze({
    type,
    disposition: ESCALATION_DISPOSITION.BADGE_IN_PLACE,
    foreground: false,
    severity: SEVERITY.INFO,
    reason: `Unrecognized signal "${type}" -- flagged in place (not foreground-eligible)`,
    known: false,
  });
}

/**
 * Severity ranker: numeric weight for a signal, for the variable-weight
 * typographic emphasis scale. Unknown types -> SEVERITY.INFO (lowest).
 * Presentation-only; does NOT affect the foreground gate.
 *
 * @param {*} typeOrEvent a signal type string OR an event/row object.
 * @returns {number} a SEVERITY value.
 */
export function severityOf(typeOrEvent) {
  const d = describe(typeOrEvent);
  return d ? d.severity : SEVERITY.INFO;
}

/**
 * Rank a list of signals by severity, descending (most severe first), as a
 * stable sort (preserves input order for equal severity). Returns a NEW
 * array of descriptors; never mutates the input. Items that yield no type
 * are dropped. This is the ranked escalation store the S2 validator and the
 * render layer consume.
 *
 * @param {Array<*>} signals event/row objects or type strings.
 * @returns {Array<ReturnType<typeof describe>>} descriptors, most-severe-first.
 */
export function rankBySeverity(signals) {
  if (!Array.isArray(signals)) return [];
  const decorated = [];
  for (let i = 0; i < signals.length; i += 1) {
    const d = describe(signals[i]);
    if (d) decorated.push({ d, i });
  }
  decorated.sort((a, b) => {
    if (b.d.severity !== a.d.severity) return b.d.severity - a.d.severity;
    return a.i - b.i; // stable for equal severity
  });
  return decorated.map((x) => x.d);
}

/**
 * Snapshot of the M2 contract as a plain auditable object. The S2 render-
 * validator asserts against this -- it is the canonical, frozen statement of
 * "which signals may foreground". Returns fresh arrays (sorted) each call so
 * a caller cannot mutate the frozen sets.
 *
 * @returns {{
 *   foregroundEligible: string[],
 *   badgeInPlace: string[],
 *   table: typeof ESCALATION_TABLE,
 * }}
 */
export function escalationContract() {
  return {
    foregroundEligible: Array.from(FOREGROUND_ELIGIBLE).sort(),
    badgeInPlace: Array.from(BADGE_IN_PLACE_TYPES).sort(),
    table: ESCALATION_TABLE,
  };
}
