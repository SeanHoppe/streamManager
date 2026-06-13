// sm-proposal-research -- proposal -> design-brief + KingMode .html mockup workflow.
// Rosetta-Stone adaptation of Claude-ResearchFixWorkflow.md /report-research (Catalog -> Find -> Verify ->
// Report), recast for the BETA-proposals initiative (docs/2026-06-11-beta-proposals-initiative.md):
//   per proposal -> RESEARCH end-user usage + persona-walk + surface/FROZEN/envelope footprint + mock-data
//   spec + KingMode design direction -> adversarial 2-refuter VERIFY (firewall/polarity/ADR-18-FROZEN/
//   feasibility) + adjudicate -> WRITE a self-contained KingMode .html MOCKUP for operator confirmation.
//
// This is the FIRST half of the pipeline. It STOPS at the mockup gate (directive #2: operator confirms UI
// approach before any code is written). sm-proposal-build.js is the second half (runs only on APPROVED).
//
// Directive coverage: #1a (end-user usage), #1b (persona-walk / end-user's shoes), #1c + #r2 (KingMode design),
// #2 (.html mockups), #test mock-data spec authored here. ASCII-only (cp1252-safe). ARGS-DRIVEN.
//   args: { proposals: [{key, num, file, title}], outDir, target }
//     proposals = batch list; defaults to batch-1 (15 SHIP-PROPOSAL) when omitted.
//     outDir    = mockup output dir (default reports/proposals/mockups/).
//     target    = frontend root (default dashboard/ui-next/).
export const meta = {
  name: 'sm-proposal-research',
  description: 'Proposal -> design-brief + KingMode .html mockup. Per proposal: research end-user usage (#1a) + persona-walk (#1b) + surface/FROZEN/envelope footprint + mock-data spec + KingMode design (#1c/#r2) -> adversarial 2-refuter verify (firewall/polarity/ADR-18/feasibility) + adjudicate -> WRITE a self-contained KingMode .html mockup (#2). STOPS at the mockup gate. Args-driven; defaults to batch-1.',
  phases: [{ title: 'Research' }, { title: 'Verify' }, { title: 'Mockup' }],
};

const KINGMODE = [
  'PERSONA: Senior Frontend Architect & Avant-Garde UI Designer (docs/KingModePrompt.txt). 15+ yrs.',
  'INTENTIONAL MINIMALISM: anti-generic, bespoke, asymmetric, distinctive typography. If it looks like a',
  '  template it is WRONG. Every element earns its place ("why factor") or is deleted. Reduction = sophistication.',
  'MULTI-DIMENSIONAL: reason through psychological (cognitive load), technical (repaint/reflow/state),',
  '  accessibility (WCAG AAA), scalability (modularity). NEVER surface-level logic -- dig until irrefutable.',
  'LIBRARY DISCIPLINE: the active stack is Svelte + custom CSS tokens in dashboard/ui-next/ (styles/theme.css).',
  '  Reuse existing components/tokens; wrap/style to achieve the avant-garde look, never re-pollute CSS.',
].join('\n');

const SAFETY = [
  'FIREWALL (G1): never read/glob/grep **/certPortal/** or C:/Users/SeanHoppe/VS/certPortal/**. A feature MUST',
  '  NOT add new certPortal/monitored-project coupling. Surface SM-internal refs only.',
  'ZERO-CONTAMINATION: stay DOMAIN-AGNOSTIC. No monitored-project vocab / JOB-IDs / agent-role names baked in.',
  '  Governed-target identity is configuration rendered FROM DATA, never hard-coded vocabulary.',
  'POLARITY (G2): no feature may make SM monitor/govern its own session. SM monitors NON-SM sessions only',
  '  (project_slug NOT IN {streamManager} AND session_id != self). Any session sweep EXCLUDES SM-self.',
  'ADR-18 MUST FLOOR (inviolable): 3-frame presence; escalation-only foreground; paired label+color badges',
  '  (color ALONE is never a signal); absolute HITL gate; domain-agnostic; a11y axe gate (0 serious); latency',
  '  budget; non-goals (no IDE / multiplexer / multi-tenant).',
  'FROZEN surfaces (additive-only; a feature that needs to MODIFY one is BLOCKED until an ADR-18 amendment',
  '  lands): governance.py decision flow, message_bus envelope schemas, cli_pool, model_router, LifecycleBridge,',
  '  wirecli. dashboard/server.py + dashboard/ui-next/ are EVOLVING -- new read endpoints + new panes + the',
  '  beta_flags table are additive and allowed.',
  'NEW BUS ENVELOPE RULE: a new envelope kind requires same-PR cassette_record.py + soak_driver.py coverage',
  '  (feedback_cassette_must_cover_new_envelopes) -- flag it in footprint.newEnvelope.',
  'BETA GATING: every feature is default-OFF and gated by the beta-flag registry (lib/beta/registry.js +',
  '  betaFlags store + BetaToggles panel). The mockup must show the feature ON with realistic data PLUS a small',
  '  "BETA -- default OFF, toggled in Settings" annotation so the operator sees the gated nature.',
  'ASCII-ONLY output everywhere incl. the .html mockup: no smart quotes, no em-dashes (write --), no box-drawing.',
].join('\n');

// ---- batch-1 default (15 SHIP-PROPOSAL); overridable via args.proposals ----
const BATCH_1 = [
  { key: 'away-mode', num: 4, file: 'reports/proposals/2026-06-11-away-mode-activity-summary.proposal.md', title: 'Away/Calm Mode + Activity Summary Replay' },
  { key: 'coverage-analyzer', num: 10, file: 'reports/proposals/2026-06-11-coverage-analyzer-dashboard.proposal.md', title: 'Coverage Analyzer dashboard widget' },
  { key: 'decision-oracle', num: 12, file: 'reports/proposals/2026-06-11-decision-oracle-pattern-provenance.proposal.md', title: 'Decision Oracle: inline pattern pedigree' },
  { key: 'escalation-heatmap', num: 14, file: 'reports/proposals/2026-06-11-escalation-timeline-heatmap.proposal.md', title: 'Escalation Timeline heatmap' },
  { key: 'hitl-bulk-dismiss', num: 15, file: 'reports/proposals/2026-06-11-hitl-bulk-dismiss-triage.proposal.md', title: 'HITL bulk-dismiss triage modal' },
  { key: 'soak-panel', num: 16, file: 'reports/proposals/2026-06-11-live-session-soak-with-polarity-audit.proposal.md', title: 'Live Session Soak Control Panel w/ Polarity Audit' },
  { key: 'confidence-chip', num: 18, file: 'reports/proposals/2026-06-11-operator-confidence-chip.proposal.md', title: 'Operator Co-Pilot Confidence Chip' },
  { key: 'velocity-heatmap', num: 19, file: 'reports/proposals/2026-06-11-pattern-velocity-heatmap.proposal.md', title: 'Pattern Velocity Heatmap' },
  { key: 'quick-filters', num: 22, file: 'reports/proposals/2026-06-11-quick-filter-presets-fr-ui-9.proposal.md', title: 'Quick-Filter Presets (FR-UI-9)' },
  { key: 'session-pinning', num: 25, file: 'reports/proposals/2026-06-11-session-agent-pinning-swim-lane.proposal.md', title: 'Session-per-Agent Pinning swim-lane' },
  { key: 'event-cursor', num: 31, file: 'reports/proposals/2026-06-11-session-event-append-stream.proposal.md', title: 'Durable session event cursor' },
  { key: 'health-digest', num: 32, file: 'reports/proposals/2026-06-11-session-health-digest-api-flywheel.proposal.md', title: 'Session health digest endpoint' },
  { key: 'health-sparklines', num: 34, file: 'reports/proposals/2026-06-11-session-health-sparklines-confidence-throughput.proposal.md', title: 'Per-session health sparklines' },
  { key: 'stale-cleanup', num: 46, file: 'reports/proposals/2026-06-11-stale-session-cleanup.proposal.md', title: 'Operator-driven stale session cleanup (soft-delete + restore)' },
  { key: 'what-changed', num: 49, file: 'reports/proposals/2026-06-11-what-changed-digest-page-focus.proposal.md', title: 'What Changed Digest (page-focus synthesis)' },
];

// batch-2 = the 27 CONSTRAIN proposals (bold-but-constrained); batch-3 = the 4
// no-verdict gap-fill FEATURE proposals (#6/#20/#39 are process-only, excluded).
const BATCH_2 = [
  { key: "ambient-soak-task", num: 2, file: "reports/proposals/2026-06-11-ambient-soak-task.proposal.md", title: "Ambient Soak Task -- continuous polarity validation via background Cron" },
  { key: "async-hitl-bulk-dismiss", num: 3, file: "reports/proposals/2026-06-11-async-hitl-bulk-dismiss.proposal.md", title: "Bulk-dismiss toolbar for async HITL queue cleanup" },
  { key: "breach-cartography-constrained", num: 5, file: "reports/proposals/2026-06-11-breach-cartography-constrained.proposal.md", title: "Breach Cartography: temporal decision causation UI (constrained v1)" },
  { key: "cleanup-stale-sessions", num: 7, file: "reports/proposals/2026-06-11-cleanup-stale-sessions.proposal.md", title: "Dashboard stale session cleanup (auto + manual)" },
  { key: "confidence-heatmap-pane", num: 9, file: "reports/proposals/2026-06-11-confidence-heatmap-pane.proposal.md", title: "Confidence heat map grid pane (Frame B role x time-bucket)" },
  { key: "cross-session-pattern-audit-apis", num: 11, file: "reports/proposals/2026-06-11-cross-session-pattern-audit-apis.proposal.md", title: "Cross-session pattern audit & applicability APIs" },
  { key: "escalation-timeline-causal-forensics", num: 13, file: "reports/proposals/2026-06-11-escalation-timeline-causal-forensics.proposal.md", title: "Escalation timeline: forensic causal-chain visibility" },
  { key: "operator-co-pilot-gesture-macros", num: 17, file: "reports/proposals/2026-06-11-operator-co-pilot-gesture-macros.proposal.md", title: "Operator Co-Pilot: one-tap ranked affordances for HITL next-actions" },
  { key: "recorded-session-replay-forensics", num: 23, file: "reports/proposals/2026-06-11-recorded-session-replay-forensics.proposal.md", title: "Recorded session replay forensics: side-by-side decision deltas" },
  { key: "session-checkpoint-versioning", num: 26, file: "reports/proposals/2026-06-11-session-checkpoint-versioning.proposal.md", title: "Session checkpoint versioning for post-mortem drift analysis" },
  { key: "session-cleanup-dual-key-polarity", num: 27, file: "reports/proposals/2026-06-11-session-cleanup-dual-key-polarity.proposal.md", title: "Stale session cleanup (dual-key polarity fix)" },
  { key: "session-confidence-sparkline", num: 28, file: "reports/proposals/2026-06-11-session-confidence-sparkline.proposal.md", title: "Per-session confidence trend sparklines in SessionPicker" },
  { key: "session-delta-digest-monitor-frame", num: 29, file: "reports/proposals/2026-06-11-session-delta-digest-monitor-frame.proposal.md", title: "Session Delta Digest: multi-session activity snapshot" },
  { key: "session-dna-heatmap-cross-pattern-topology", num: 30, file: "reports/proposals/2026-06-11-session-dna-heatmap-cross-pattern-topology.proposal.md", title: "Session DNA Heatmap: cross-session pattern topology" },
  { key: "session-health-digest-api", num: 33, file: "reports/proposals/2026-06-11-session-health-digest-api.proposal.md", title: "Session health digest endpoints for multi-session triage" },
  { key: "session-housekeeping-api", num: 35, file: "reports/proposals/2026-06-11-session-housekeeping-api.proposal.md", title: "Session housekeeping API: stale discovery + bulk-purge" },
  { key: "session-quick-filter-presets", num: 36, file: "reports/proposals/2026-06-11-session-quick-filter-presets.proposal.md", title: "Session Picker: favorites + filters + hotkey" },
  { key: "session-story-panel-narrative-arc", num: 37, file: "reports/proposals/2026-06-11-session-story-panel-narrative-arc.proposal.md", title: "Session Story: narrative arc panel w/ bi-directional feed linking" },
  { key: "shadow-soak-lane-audit-refactored", num: 38, file: "reports/proposals/2026-06-11-shadow-soak-lane-audit-refactored.proposal.md", title: "Shadow Soak Audit Lane with polarity-safe filtering" },
  { key: "soak-1-live-session-shadow-harness", num: 40, file: "reports/proposals/2026-06-11-soak-1-live-session-shadow-harness.proposal.md", title: "Live non-SM session soak dashboard harness" },
  { key: "soak-2a-replay-forensics-mvp", num: 41, file: "reports/proposals/2026-06-11-soak-2a-replay-forensics-mvp.proposal.md", title: "Live-soak replay forensics (MVP tier)" },
  { key: "soak-coverage-matrix-excluded-sm", num: 42, file: "reports/proposals/2026-06-11-soak-coverage-matrix-excluded-sm.proposal.md", title: "Soak Coverage Matrix (governed sessions only)" },
  { key: "soak-session-metadata-tagging", num: 43, file: "reports/proposals/2026-06-11-soak-session-metadata-tagging.proposal.md", title: "Session soak_id + soak_metadata tagging for audit hygiene" },
  { key: "sonification-escalation-layer", num: 44, file: "reports/proposals/2026-06-11-sonification-escalation-layer.proposal.md", title: "Sonification as derived escalation confirmation layer" },
  { key: "spatial-session-sidebar", num: 45, file: "reports/proposals/2026-06-11-spatial-session-sidebar.proposal.md", title: "Spatial Session Overview sidebar (right-rail coexist mode)" },
  { key: "temporal-scrubber-governance-audit", num: 47, file: "reports/proposals/2026-06-11-temporal-scrubber-governance-audit.proposal.md", title: "Temporal Scrubber: governance policy archaeology via replay diff" },
  { key: "time-machine-governance-replay", num: 48, file: "reports/proposals/2026-06-11-time-machine-governance-replay.proposal.md", title: "Time Machine: counterfactual governance replay in Settings drawer" },
];

const BATCH_3 = [
  { key: "allow-pattern-auto-graduation", num: 1, file: "reports/proposals/2026-06-11-allow-pattern-auto-graduation.proposal.md", title: "ALLOW-pattern auto-graduation (learn-mode -> static rule, operator-confirmed)" },
  { key: "confidence-calibration-loop", num: 8, file: "reports/proposals/2026-06-11-confidence-calibration-loop.proposal.md", title: "Confidence-calibration loop: make confidence mean something" },
  { key: "policy-preview-chip", num: 21, file: "reports/proposals/2026-06-11-policy-preview-chip.proposal.md", title: "Policy-preview chip: what will governance do, from the corpus" },
  { key: "regret-mining-override-loop", num: 24, file: "reports/proposals/2026-06-11-regret-mining-override-loop.proposal.md", title: "Regret-mining: close the operator-override feedback loop" },
];

const IN = (args && typeof args === 'object') ? args : {};
const BATCHES = { batch1: BATCH_1, batch2: BATCH_2, batch3: BATCH_3, all23: BATCH_2.concat(BATCH_3) };
// NOTE: the Workflow `args` input does NOT thread to the script `args` global
// when invoked via scriptPath (verified 2026-06-11 -- two runs ignored args).
// Set ACTIVE_BATCH here per run ('batch1' | 'batch2' | 'batch3' | 'all23').
const ACTIVE_BATCH = 'batch3';
const _selected = (Array.isArray(IN.proposals) && IN.proposals.length)
  ? IN.proposals
  : (IN.batch && BATCHES[IN.batch]) ? BATCHES[IN.batch]
  : (BATCHES[ACTIVE_BATCH] || BATCH_1);
const PROPOSALS = _selected.slice(0, 32);
const OUT_DIR = IN.outDir || 'reports/proposals/mockups/';
const TARGET = IN.target || 'dashboard/ui-next/';

// ---- schemas ----
const BRIEF_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['key', 'title', 'endUserUsage', 'personaWalk', 'operatorValue', 'footprint', 'mockDataSpec', 'kingmodeDesign'],
  properties: {
    key: { type: 'string' },
    title: { type: 'string' },
    endUserUsage: { type: 'string' }, // #1a: who toggles it ON, what task it serves, glance/click path
    personaWalk: { type: 'string' }, // #1b: operator's shoes -- when/why used, what it replaces, failure feel
    operatorValue: { type: 'string' },
    footprint: {
      type: 'object', additionalProperties: false,
      required: ['kind', 'frozenTouch', 'newEnvelope', 'newTable', 'newEndpoints', 'filesUiNext', 'filesBackend'],
      properties: {
        kind: { type: 'string', enum: ['ui-only', 'new-read-api', 'new-table', 'new-envelope', 'frozen-touch'] },
        frozenTouch: { type: 'boolean' },
        newEnvelope: { type: 'boolean' },
        newTable: { type: 'boolean' },
        newEndpoints: { type: 'array', items: { type: 'string' } },
        filesUiNext: { type: 'array', items: { type: 'string' } }, // svelte components to add/edit
        filesBackend: { type: 'array', items: { type: 'string' } }, // server.py / src additions
      },
    },
    mockDataSpec: { type: 'string' }, // #test: shape of mock data when live data unavailable
    kingmodeDesign: { type: 'string' }, // #1c/#r2: layout, hierarchy, badges, interaction, a11y
    dataNeeds: { type: 'array', items: { type: 'string' } },
    grounding: { type: 'array', items: { type: 'string' } },
  },
};

const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['key', 'verdict', 'checks', 'needsAmendment', 'reasoning'],
  properties: {
    key: { type: 'string' },
    verdict: { type: 'string', enum: ['PASS', 'CONSTRAIN', 'NEEDS-AMENDMENT', 'BLOCK'] },
    checks: {
      type: 'object', additionalProperties: false,
      required: ['firewall', 'polarity', 'frozenAccurate', 'feasibility', 'mustFloor'],
      properties: {
        firewall: { type: 'string', enum: ['PASS', 'FAIL'] },
        polarity: { type: 'string', enum: ['PASS', 'FAIL'] },
        frozenAccurate: { type: 'string', enum: ['ACCURATE', 'UNDERSTATED', 'OVERSTATED'] },
        feasibility: { type: 'string', enum: ['FEASIBLE', 'HARD', 'INFEASIBLE'] },
        mustFloor: { type: 'string', enum: ['PASS', 'BENDS-SHOULD', 'VIOLATES-MUST'] },
      },
    },
    needsAmendment: { type: 'boolean' }, // true if it touches a FROZEN surface / new envelope
    constraint: { type: 'string' }, // if CONSTRAIN/NEEDS-AMENDMENT: exact reshape / amendment required
    reasoning: { type: 'string' },
  },
};

const ADJ_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['key', 'verdict', 'needsAmendment', 'vettedBrief', 'reasoning'],
  properties: {
    key: { type: 'string' },
    verdict: { type: 'string', enum: ['PASS', 'CONSTRAIN', 'NEEDS-AMENDMENT', 'BLOCK'] },
    needsAmendment: { type: 'boolean' },
    amendmentNote: { type: 'string' },
    vettedBrief: BRIEF_SCHEMA, // the brief reconciled with the refute constraints
    reasoning: { type: 'string' },
  },
};

const MOCKUP_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['key', 'mockupPath', 'title', 'summary', 'wrote'],
  properties: {
    key: { type: 'string' },
    mockupPath: { type: 'string' },
    title: { type: 'string' },
    summary: { type: 'string' }, // 1-2 sentences: what the operator will see in the mockup
    wrote: { type: 'boolean' },
  },
};

function briefPrompt(p) {
  return `${KINGMODE}

${SAFETY}

RESEARCH the proposal for BETA feature "${p.key}" (#${p.num}: ${p.title}).
Read the proposal file: ${p.file}
Read whatever you need under ${TARGET} (components, stores, lib/api.js, lib/sse.js) and dashboard/server.py to
ground the footprint. Read docs/2026-06-11-beta-proposals-initiative.md for the BETA-flag architecture.

Produce a DESIGN BRIEF:
- endUserUsage (#1a): WHO turns this BETA on, the exact operator task it serves, and the glance-or-click path
  to value. Be concrete about the monitor-first laptop operator.
- personaWalk (#1b): from the operator's shoes -- the moment they reach for it, what it replaces (scrolling /
  reconstructing / guessing), and how a failure-to-have-it currently feels.
- operatorValue: the one-line why.
- footprint: kind (ui-only | new-read-api | new-table | new-envelope | frozen-touch); frozenTouch bool;
  newEnvelope bool; newTable bool; newEndpoints (additive GET/POST paths on dashboard/server.py); filesUiNext
  (svelte components to add under ${TARGET}); filesBackend (server.py / src additions). Be HONEST: if the real
  build must touch a FROZEN surface, say frozenTouch=true (the build is then amendment-gated).
- mockDataSpec (#test): the JSON shape of MOCK data to render when live gov.db data is unavailable at test time.
- kingmodeDesign (#1c/#r2): the bespoke layout -- visual hierarchy, where it lives (which Frame / drawer /
  header), paired label+color badge scheme, key interaction, keyboard path, WCAG AAA contrast intent. Anti-generic.
- dataNeeds + grounding (file:line).`;
}

// ===== Stage 1: RESEARCH -> Stage 2: VERIFY -> Stage 3: MOCKUP (pipeline; per-proposal, no barrier) =====
phase('Research');
log(`RESEARCH: ${PROPOSALS.length} proposals -> brief -> 2-refuter verify -> KingMode .html mockup. Mockup gate at end.`);

const processed = await pipeline(
  PROPOSALS,
  // Stage 1: research the brief (general-purpose -- reads proposal + codebase).
  (p) => agent(briefPrompt(p), { label: `research:${p.key}`, phase: 'Research', agentType: 'general-purpose', schema: BRIEF_SCHEMA }),

  // Stage 2: adversarial 2-refuter verify + adjudicate (read-only). Refuters review the BRIEF (returned text),
  // re-open cited files to confirm. Memory rule: refuters review returned artifact, not a shared mutable tree.
  (brief, p) => {
    if (!brief) return Promise.resolve(null);
    const briefJson = JSON.stringify(brief);
    return parallel([0, 1].map((n) => () =>
      agent(`${SAFETY}

Adversarially VERIFY the design brief for BETA feature "${p.key}" (refuter ${n}). Be SKEPTICAL, re-open cited
files. Proposal source: ${p.file}. Brief under review:
${briefJson}
Run each check honestly:
- firewall: does the brief add NEW certPortal/monitored coupling or vocab? PASS/FAIL.
- polarity: could it monitor/govern SM-self or sweep SM-self? PASS/FAIL.
- frozenAccurate: is footprint.frozenTouch / newEnvelope HONEST vs the real surfaces? If the brief claims
  "no FROZEN" but the real build must touch governance.py / message_bus envelopes / cli_pool / model_router /
  LifecycleBridge / wirecli, mark UNDERSTATED. If it over-claims FROZEN where an additive read-API suffices,
  mark OVERSTATED. Else ACCURATE.
- feasibility: buildable on the existing /api + SSE contract + ui-next Svelte stack? FEASIBLE | HARD | INFEASIBLE.
- mustFloor: crosses an ADR-18 UI MUST? PASS | BENDS-SHOULD | VIOLATES-MUST.
VERDICT: PASS (clean, additive, ship to mockup) | CONSTRAIN (reshape -- give the exact constraint) |
NEEDS-AMENDMENT (touches a FROZEN surface / adds a new envelope -- name the ADR-18 amendment required;
mockup still proceeds, build is amendment-gated) | BLOCK (firewall FAIL / VIOLATES-MUST / INFEASIBLE).
Set needsAmendment=true iff frozenTouch or newEnvelope is real. Give reasoning.`,
        { label: `verify:${p.key}:${n}`, phase: 'Verify', agentType: 'Explore', schema: VERDICT_SCHEMA })
    )).then((votes) => ({ brief, p, votes: votes.filter(Boolean) }));
  },

  // Stage 2b: adjudicate the 2 votes into a vetted brief (read-only).
  (vr, p) => {
    if (!vr || !vr.brief) return Promise.resolve(null);
    return agent(`${SAFETY}

ADJUDICATE the verification of BETA feature "${p.key}". Two refuters returned:
${JSON.stringify(vr.votes)}
Original brief:
${JSON.stringify(vr.brief)}
Emit the final verdict + a VETTED brief (the original brief reconciled with any CONSTRAIN / NEEDS-AMENDMENT
constraint folded in -- never silently drop a fixable feature). Rules:
- BLOCK only on a decisive firewall FAIL or VIOLATES-MUST or INFEASIBLE from either refuter.
- NEEDS-AMENDMENT if either refuter found a real FROZEN-surface touch / new envelope (set needsAmendment=true,
  amendmentNote = the exact ADR-18 amendment the build needs). The mockup STILL proceeds (operator sees the UI).
- CONSTRAIN if a refuter required a reshape; fold it into vettedBrief.
- else PASS.
vettedBrief MUST be a complete brief object (same shape as the input brief).`,
      { label: `adjudicate:${p.key}`, phase: 'Verify', agentType: 'Explore', schema: ADJ_SCHEMA })
      .then((adj) => ({ adj, p }));
  },

  // Stage 3: WRITE the KingMode .html mockup (general-purpose -- writes the file). Skipped on BLOCK.
  (ar, p) => {
    if (!ar || !ar.adj) return Promise.resolve(null);
    const adj = ar.adj;
    if (adj.verdict === 'BLOCK') return Promise.resolve({ key: p.key, blocked: true, adj });
    const path = `${OUT_DIR}${p.key}.html`;
    return agent(`${KINGMODE}

${SAFETY}

WRITE a self-contained KingMode .html MOCKUP for BETA feature "${p.key}" (#${p.num}: ${p.title}) so the operator
can confirm the UI approach BEFORE any code is written (directive #2). Vetted brief:
${JSON.stringify(adj.vettedBrief)}
${adj.needsAmendment ? `NOTE: this feature is NEEDS-AMENDMENT (${adj.amendmentNote}). Render a small amber "build gated on ADR-18 amendment" footnote in the mockup so the operator knows the UI is approvable but the build is gated.` : ''}

MOCKUP REQUIREMENTS:
- Write to EXACTLY this path with the Write tool: ${path}
- ONE self-contained .html file: inline <style> + inline <script>, NO external assets/CDNs/fonts. System font stack.
- Visual language = dashboard/ui-next/ KingMode: dark surface, restrained accent, generous whitespace, bespoke
  (not a bootstrap template). Read dashboard/ui-next/src/styles/theme.css first and reuse its CSS-variable names
  / palette so the mockup previews the REAL tokens. WCAG AAA contrast.
- Show the feature ON with REALISTIC mock data drawn from mockDataSpec (governance decisions, sessions,
  confidence, escalations -- domain-agnostic, NO certPortal/monitored-project vocabulary).
- Paired label+COLOR badges everywhere a state is shown (text label always present; color alone is never the
  only signal -- ADR-18 MUST).
- Include a compact header strip: feature title + a "BETA -- default OFF, toggled in Settings > BETA features"
  pill, plus an inline on/off toggle wired (client-side only) so the operator can SEE the gated on/off behavior.
- Make the key interaction work client-side (the toggle, any modal/expand/keyboard path) so the operator can
  click through it in a browser.
- ASCII-only. No smart quotes, no em-dashes (use --), no box-drawing chars.
Return mockupPath=${path}, a 1-2 sentence summary of what the operator will see, wrote=true on success.`,
      { label: `mockup:${p.key}`, phase: 'Mockup', agentType: 'general-purpose', schema: MOCKUP_SCHEMA })
      .then((m) => ({ key: p.key, blocked: false, adj, mockup: m }));
  },
);

// ===== Aggregate =====
phase('Mockup');
const rows = processed.filter(Boolean);
const blocked = rows.filter((r) => r.blocked).map((r) => ({ key: r.key, reason: r.adj ? r.adj.reasoning : 'blocked' }));
const built = rows.filter((r) => !r.blocked);
const needsAmend = built.filter((r) => r.adj && r.adj.needsAmendment)
  .map((r) => ({ key: r.key, amendment: r.adj.amendmentNote || '' }));
const mockups = built.filter((r) => r.mockup && r.mockup.wrote)
  .map((r) => ({ key: r.key, path: r.mockup.mockupPath, title: r.mockup.title, summary: r.mockup.summary,
                 verdict: r.adj.verdict, needsAmendment: !!r.adj.needsAmendment }));

log(`MOCKUP GATE: ${mockups.length}/${PROPOSALS.length} mockups written; ${needsAmend.length} NEEDS-AMENDMENT; ${blocked.length} BLOCKED.`);

return {
  scope: 'beta-proposals-research (mockup gate -- STOP for operator approval before sm-proposal-build)',
  counts: { proposals: PROPOSALS.length, mockups: mockups.length, needsAmendment: needsAmend.length, blocked: blocked.length },
  mockups, // operator reviews these .html files, then approves keys for sm-proposal-build
  needsAmendment: needsAmend, // build-gated until the named ADR-18 amendment lands
  blocked, // never silently dropped
  vettedBriefs: built.map((r) => ({ key: r.key, verdict: r.adj.verdict, brief: r.adj.vettedBrief })),
  gate: {
    note: 'MOCKUP GATE. Main thread: present the .html mockups to the operator. Build NOTHING until the operator '
      + 'approves a key set. Pass approved keys + vettedBriefs to sm-proposal-build.js. NEEDS-AMENDMENT keys also '
      + 'require their ADR-18 amendment to land before their build partition runs.',
    outDir: OUT_DIR,
  },
};
