// registry.js -- BETA feature registry (2026-06-11 BETA proposals initiative).
//
// Single source of truth for the optional, default-OFF BETA features the
// operator can toggle "at the UI level" (Settings > BETA features). DATA ONLY:
// label / description / group / number. It deliberately imports NO feature
// component, so the registry (and the BetaToggles panel that reads it) never
// breaks the build when a feature component has not landed yet -- each feature
// build adds its own gated mount point at its own site in the composition.
//
// Promotion path: a feature that earns its place is later flipped to
// defaultEnabled:true, then has its flag + gate removed entirely (always-on) in
// a separate cycle. Until then every entry stays opt-in and reversible.
//
// M16 (domain-agnostic): labels/descriptions are generic governance/UI taxonomy
// -- no monitored-project vocabulary. ASCII-only (cp1252-safe): dash is "--".

/**
 * @typedef {Object} BetaFeature
 * @property {string} key          stable flag key (kebab; matches beta_flags.key + the gate test)
 * @property {number} num          source proposal number in PROPOSALS-INDEX.md
 * @property {string} label        operator-facing name
 * @property {string} description  one line: what turning it ON does
 * @property {'monitor'|'hitl'|'soak'|'session'} group
 * @property {boolean} defaultEnabled  ALWAYS false at introduction (default OFF)
 * @property {boolean} [needsAmendment]  build gated on a pending ADR-18 amendment
 */

/** @type {BetaFeature[]} */
export const BETA_REGISTRY = [
  // -- Monitor & glance-readability --
  { key: 'away-mode', num: 4, group: 'monitor', defaultEnabled: false,
    label: 'Away / Calm Mode + Activity Summary',
    description: 'Step away; events buffer quietly and HITL rows demote to OBSERVING. On return, a one-glance summary of escalations, new agents, and queued HITL. Real alarms still break through.' },
  { key: 'escalation-heatmap', num: 14, group: 'monitor', defaultEnabled: false,
    label: 'Escalation Timeline heatmap',
    description: 'A glance-readable density heatmap of governance escalations over time -- spot the hot windows without scrolling the log.' },
  { key: 'velocity-heatmap', num: 19, group: 'monitor', defaultEnabled: false,
    label: 'Pattern Velocity heatmap',
    description: 'Ambient session-health signal from L0--L4 learning dynamics: is governance maturing or thrashing?' },
  { key: 'what-changed', num: 49, group: 'monitor', defaultEnabled: false,
    label: 'What Changed digest',
    description: 'On page-focus, a synthesis overlay of everything that moved since you last looked.' },
  { key: 'coverage-analyzer', num: 10, group: 'monitor', defaultEnabled: false,
    label: 'Coverage Analyzer widget',
    description: 'A drawer comparing cassette-vs-live band distribution to surface where soak coverage drifts from production.' },

  // -- HITL & operator co-pilot --
  { key: 'hitl-bulk-dismiss', num: 15, group: 'hitl', defaultEnabled: false,
    label: 'HITL bulk-dismiss triage',
    description: 'A keyboard-preset triage modal to clear a backed-up async HITL queue in seconds instead of row-by-row.' },
  { key: 'confidence-chip', num: 18, group: 'hitl', defaultEnabled: false,
    label: 'Operator Co-Pilot confidence chip',
    description: 'An advisory chip proposing the next HITL action with a confidence you can one-tap accept. Never auto-acts.' },
  { key: 'decision-oracle', num: 12, group: 'hitl', defaultEnabled: false, needsAmendment: true,
    label: 'Decision Oracle pedigree',
    description: 'Inline pattern pedigree + ancestral replay on any decision -- where did this verdict come from?' },

  // -- Soak & non-SM session validation --
  { key: 'soak-panel', num: 16, group: 'soak', defaultEnabled: false, needsAmendment: true,
    label: 'Live Session Soak control panel',
    description: 'Pick a live NON-SM Claude session as a soak target (SM-self + firewalled cwd refused) and watch progress + a polarity audit live.' },
  { key: 'health-digest', num: 32, group: 'soak', defaultEnabled: false,
    label: 'Session health digest',
    description: 'A server-side glance digest per session (confidence, throughput, escalations) for fast multi-session triage.' },
  { key: 'health-sparklines', num: 34, group: 'soak', defaultEnabled: false,
    label: 'Session health sparklines',
    description: 'Confidence + throughput sparklines in each session lane header -- trend at a glance, paired with a text delta.' },

  // -- Session management --
  { key: 'session-pinning', num: 25, group: 'session', defaultEnabled: false,
    label: 'Session-per-agent pinning',
    description: 'Pin a session/agent to a Frame B swim-lane so it stays put while others churn.' },
  { key: 'quick-filters', num: 22, group: 'session', defaultEnabled: false,
    label: 'Quick-Filter presets',
    description: 'Named one-click monitor configurations (FR-UI-9) with hotkeys.' },
  { key: 'event-cursor', num: 31, group: 'session', defaultEnabled: false, needsAmendment: true,
    label: 'Durable session event cursor',
    description: 'The browser resumes the event stream where it left off across refreshes -- no lost context on reload.' },
  { key: 'stale-cleanup', num: 46, group: 'session', defaultEnabled: false, needsAmendment: true,
    label: 'Stale session cleanup',
    description: 'Operator-driven soft-delete + restore of sessions gone quiet (process exited / cwd vanished). SM-self always excluded.' },

  // -- batch-2 (new functionality, constrained-additive) --
  { key: 'breach-cartography-constrained', num: 5, group: 'monitor', defaultEnabled: false,
    label: 'Breach Cartography',
    description: 'Map a regression run-up: a causal swimlane + temporal scrubber + ranked surgical-revert (HITL-gated).' },
  { key: 'confidence-heatmap-pane', num: 9, group: 'monitor', defaultEnabled: false,
    label: 'Confidence Heat Map',
    description: 'A role x time-bucket confidence grid in Frame B -- spot confidence drift at a glance.' },
  { key: 'escalation-timeline-causal-forensics', num: 13, group: 'monitor', defaultEnabled: false,
    label: 'Escalation Causal Forensics',
    description: 'A causal-chain timeline + side-by-side decision diff for an escalation.' },
  { key: 'session-dna-heatmap-cross-pattern-topology', num: 30, group: 'monitor', defaultEnabled: false,
    label: 'Session DNA Heatmap',
    description: 'Cross-session pattern topology with confidence per session.' },
  { key: 'sonification-escalation-layer', num: 44, group: 'monitor', defaultEnabled: false,
    label: 'Escalation Sonification',
    description: 'A derived audio cue on a real escalation (default OFF; paired with the visual signal, never the only signal).' },
  { key: 'cross-session-pattern-audit-apis', num: 11, group: 'hitl', defaultEnabled: false,
    label: 'Cross-session Pattern Audit',
    description: 'Inspect hydrated rules across sessions + a read-only "would this fire?" probe.' },
  { key: 'operator-co-pilot-gesture-macros', num: 17, group: 'hitl', defaultEnabled: false,
    label: 'Co-Pilot Gesture Macros',
    description: 'One-tap ranked next-action affordances on a HITL row (advisory; never auto-acts).' },
  { key: 'ambient-soak-task', num: 2, group: 'soak', defaultEnabled: false,
    label: 'Ambient Soak Task',
    description: 'Continuous polarity validation in the background: a calm AMBIENT OK/WARN badge + a ledger of recent checks.' },
  { key: 'recorded-session-replay-forensics', num: 23, group: 'soak', defaultEnabled: false,
    label: 'Replay Forensics',
    description: 'Side-by-side decision-delta replay for operator root-cause.' },
  { key: 'session-checkpoint-versioning', num: 26, group: 'session', defaultEnabled: false,
    label: 'Session Checkpoint Versioning',
    description: 'Read-only session checkpoint snapshots for post-mortem drift analysis.' },
  { key: 'session-story-panel-narrative-arc', num: 37, group: 'session', defaultEnabled: false,
    label: 'Session Story',
    description: 'A narrative-arc panel for one session with bi-directional feed linking.' },
  { key: 'spatial-session-sidebar', num: 45, group: 'session', defaultEnabled: false,
    label: 'Spatial Session Sidebar',
    description: 'A right-rail spatial session overview that coexists with the 3-frame layout.' },
  { key: 'temporal-scrubber-governance-audit', num: 47, group: 'session', defaultEnabled: false,
    label: 'Temporal Scrubber',
    description: 'Policy archaeology: replay a diff between two points in the decision stream.' },
  { key: 'time-machine-governance-replay', num: 48, group: 'session', defaultEnabled: false,
    label: 'Time Machine',
    description: 'Counterfactual governance replay over stored decisions in the Settings drawer.' },
];

/** Group display order + labels for the BetaToggles panel. */
export const BETA_GROUPS = [
  { id: 'monitor', label: 'Monitor & glance-readability' },
  { id: 'hitl', label: 'HITL & operator co-pilot' },
  { id: 'soak', label: 'Soak & non-SM session validation' },
  { id: 'session', label: 'Session management' },
];

/** @returns {Record<string, boolean>} the default-OFF map for every known key. */
export function betaDefaults() {
  /** @type {Record<string, boolean>} */
  const out = {};
  for (const f of BETA_REGISTRY) out[f.key] = !!f.defaultEnabled;
  return out;
}
