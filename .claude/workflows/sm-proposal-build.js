// sm-proposal-build -- approved-proposal -> BETA feature build + adversarial review + test-spec workflow.
// Rosetta-Stone adaptation of Claude-ResearchFixWorkflow.md /report-fixes (Split -> Fix&refute -> Verify&ship),
// recast for the BETA-proposals initiative. Runs AFTER the sm-proposal-research mockup gate on the operator-
// APPROVED set.
//
// BUILD MODEL (operator choice 2026-06-11: "build in working tree", NO worktrees):
//   Each build agent runs in the SHARED working tree (so it sees the uncommitted BETA-flag foundation) and
//   creates ONLY its own NEW isolated production files (the Svelte component + any new mock-data module) at a
//   UNIQUE per-key path. It does NOT edit shared files (server.py, registry.js, App.svelte, SettingsDrawer) --
//   those edits are RETURNED AS DATA so the MAIN THREAD applies them serially. Because every feature writes
//   only its own uniquely-named files, parallel builds in one tree never collide. The refuters then READ those
//   new files directly from the tree (no worktree => no blindness) and review the returned shared-edit data.
//
// Memory rules embedded: (1) build stages use agentType general-purpose; (2) refuters review the ACTUAL written
// files + returned edit data (the worktree-blindness rule is moot without worktrees, but refuters still review
// the artifact, never trust a self-report); (3) main thread re-runs every gate before any PR; (4) workaround
// reuse audited across partitions; (5) "deferred to follow-up" is a BLOCK signal; (6) live soak needs a
// confirmed non-SM session. Long (>5min) test runs are MAIN-THREAD owned -- build agents NEVER run npm build /
// servers / live --headed (that is the main-thread gate); they only write source + return test SPECS.
//
// ASCII-only (cp1252-safe). ARGS-DRIVEN; defaults to the 13 buildable batch-1 features.
//   args: { approved: [{key,num,file,mockupPath,group,buildNote}], target, mockDir }
export const meta = {
  name: 'sm-proposal-build',
  description: 'Approved BETA proposal -> feature build (in the shared working tree, NO worktree) + adversarial review + test specs. Each build agent writes ONLY its own uniquely-named new Svelte component gated on the beta flag, and RETURNS shared-file edits as DATA (registry entry, additive backend endpoint, wire instruction) + a Playwright --headed spec + targeted pytest. 2 refuters READ the written files + review the edit data (FROZEN/polarity/contamination/betaGated/a11y). Returns everything for the MAIN-THREAD gate re-check + PR. Never runs npm build / servers / live --headed itself. Args-driven; defaults to the 13 buildable features.',
  phases: [{ title: 'Build' }, { title: 'Refute' }, { title: 'Assemble' }],
};

const KINGMODE = [
  'PERSONA: Senior Frontend Architect & Avant-Garde UI Designer (docs/KingModePrompt.txt).',
  'INTENTIONAL MINIMALISM: anti-generic, bespoke, every element earns its place. Reuse the ui-next Svelte stack',
  '  + styles/theme.css CSS-variable tokens (the calm-* / --sm-* / --text* / --accent / badge tokens). The built',
  '  component MUST match its approved .html mockup. Micro-interactions, perfect spacing, WCAG AAA. No CSS pollution.',
].join('\n');

const SAFETY = [
  'FIREWALL (G1): never read/glob/grep **/certPortal/**. Add NO new certPortal/monitored-project coupling.',
  'ZERO-CONTAMINATION: stay DOMAIN-AGNOSTIC. No monitored-project vocab / JOB-IDs / role names. Identity is',
  '  configuration rendered FROM DATA. ASCII-only output (cp1252): no smart quotes, no em-dashes (use --), no',
  '  box-drawing chars (use - or =), no section sign (write "section").',
  'POLARITY (G2): no feature monitors/governs/sweeps SM-self. project_slug NOT IN {streamManager} AND',
  '  session_id != self. Any session query/sweep/soft-delete EXCLUDES SM-self. A live soak needs a CONFIRMED',
  '  live non-SM session (#r1) -- which is a MAIN-THREAD step, never done here.',
  'ADR-18 MUST FLOOR (inviolable): 3-frame presence; escalation-only foreground; paired label+color badges',
  '  (color alone never a signal -- always render the literal text state); absolute HITL gate; domain-agnostic;',
  '  a11y axe (0 serious); latency budget (post-hoc only, never the verdict hot path); non-goals.',
  'FROZEN (DO NOT MODIFY): governance.py decision flow, message_bus envelope schemas, cli_pool, model_router,',
  '  LifecycleBridge, wirecli. If building correctly would REQUIRE editing one of these OR minting a new bus',
  '  envelope, STOP and return blocked=true with blockedReason -- do NOT work around it. dashboard/server.py +',
  '  dashboard/ui-next/ are EVOLVING: additive NEW read endpoints, additive NEW columns (CREATE-IF-NOT-EXISTS /',
  '  ALTER-ADD guarded), and NEW panes are allowed.',
  'NO ESCAPE HATCHES: never return "deferred to a follow-up" / "TODO later" for in-scope work. Land it or return',
  '  blocked=true with a concrete reason.',
  'BETA GATING: the component renders nothing (registers NO pollers/SSE handlers/timers) unless',
  '  $betaFlags["<key>"] is true. Default OFF. Read the flag from the betaFlags store (lib/stores/beta.js).',
  'BUILD-AGENT DISCIPLINE: you may Read/Glob/Grep freely and WRITE ONLY your own new uniquely-named files. Do',
  '  NOT edit shared files (dashboard/server.py, lib/beta/registry.js, App.svelte, SettingsDrawer.svelte,',
  '  lib/api.js, lib/sse.js) -- return those edits as DATA. Do NOT run `npm run build`, start servers, or run',
  '  live --headed tests (those are the MAIN-THREAD gate). A short `npx svelte-check`-free read is fine; no',
  '  long-running commands.',
].join('\n');

// ---- the 13 buildable batch-1 features (soak-panel + event-cursor held for the ADR-18 amendment) ----
// buildNote carries the adjudicator constraints + my triage so the agent builds the compliant shape.
const APPROVED_13 = [
  { key: 'away-mode', num: 4, group: 'monitor',
    file: 'reports/proposals/2026-06-11-away-mode-activity-summary.proposal.md',
    buildNote: 'CLIENT-SIDE ONLY. No backend. Buffer SSE events client-side while Away; on return show an Activity Summary modal (escalation timeline from action IN [BLOCK,INTERVENE] or escalation_type -- generic, never hardcoded envelope kinds; new-agent roster; queued-HITL count; away window). Real escalations break through. Gate on $betaFlags["away-mode"].' },
  { key: 'coverage-analyzer', num: 10, group: 'monitor',
    file: 'reports/proposals/2026-06-11-coverage-analyzer-dashboard.proposal.md',
    buildNote: 'Read-only drawer comparing cassette-vs-live band distribution (ALLOW/L2-L3/L4/LEARN). Prefer a NEW additive read endpoint /api/coverage/bands (aggregate over gov.db decisions by layer); fall back to mockDataSpec data when empty. Never auto-foreground (drawer, not a 4th frame).' },
  { key: 'decision-oracle', num: 12, group: 'hitl',
    file: 'reports/proposals/2026-06-11-decision-oracle-pattern-provenance.proposal.md',
    buildNote: 'READ-ONLY pattern pedigree whisper-pane on a decision row. Additive read endpoint /api/patterns/{hash}/pedigree (or reuse existing pattern reads) -- NO governance.py edit, NO new envelope. MUST suppress the glyph + return nothing for SM-self rows (project_slug=streamManager) per G2. (Soft-amendment was a doc addendum only; build read-only and additive.)' },
  { key: 'escalation-heatmap', num: 14, group: 'monitor',
    file: 'reports/proposals/2026-06-11-escalation-timeline-heatmap.proposal.md',
    buildNote: 'CLIENT-SIDE heatmap gutter beside the decision stream, density by 30s bucket, color=peak severity with a PAIRED legend + per-bucket text. Click/keyboard scopes a time window via a CustomEvent (dim out-of-window rows, never hide). SM-self gutter empty (G2). No backend needed.' },
  { key: 'hitl-bulk-dismiss', num: 15, group: 'hitl',
    file: 'reports/proposals/2026-06-11-hitl-bulk-dismiss-triage.proposal.md',
    buildNote: 'A focus-trapped triage modal that batch-resolves pending HITL rows via the EXISTING POST /api/hitl/resolve (loop existing endpoint -- no new endpoint, no FROZEN touch). Keyboard presets + confidence/older-than filters; destructive-confirm; optimistic dock cull. CONSTRAIN: only the operator-selected rows, never an implicit select-all without a visible checked state.' },
  { key: 'confidence-chip', num: 18, group: 'hitl',
    file: 'reports/proposals/2026-06-11-operator-confidence-chip.proposal.md',
    buildNote: 'ADVISORY chip on a HITL pending row proposing the next action with a confidence (from existing decision_suggestions / confidence fields -- reuse getDecisionSuggestions). One-tap accept routes through the EXISTING commit path; NEVER auto-acts. Ctrl+Enter = accept, Esc = collapse to OVERRIDE. Client-side; no new endpoint.' },
  { key: 'velocity-heatmap', num: 19, group: 'monitor',
    file: 'reports/proposals/2026-06-11-pattern-velocity-heatmap.proposal.md',
    buildNote: 'Ambient L0--L4 x time heatmap strip inside Frame A with a PAIRED state badge (LEARNING/STALLED/RESETTING/CALM) -- in-cell count digits carry the signal even with color removed. Prefer client-side over existing pattern/decision data; a NEW additive read endpoint is OK if needed. CONSTRAIN: never auto-foreground; ambient only.' },
  { key: 'quick-filters', num: 22, group: 'session',
    file: 'reports/proposals/2026-06-11-quick-filter-presets-fr-ui-9.proposal.md',
    buildNote: 'Named monitor-config PRESETS persisted in localStorage (NO new gov.db table -> NO amendment), mirroring the settings store idiom (lib/stores/settings.js). One-click apply + hotkeys. Client-side only.' },
  { key: 'session-pinning', num: 25, group: 'session',
    file: 'reports/proposals/2026-06-11-session-agent-pinning-swim-lane.proposal.md',
    buildNote: 'Pin a session/agent to a Frame B swim-lane; pin state persists in localStorage. Visual pin affordance + paired text. Client-side only; reorders the existing roster, adds no backend.' },
  { key: 'health-digest', num: 32, group: 'soak',
    file: 'reports/proposals/2026-06-11-session-health-digest-api-flywheel.proposal.md',
    buildNote: 'A NEW additive read endpoint /api/sessions/health-digest aggregating per-session confidence/throughput/escalation counts over gov.db (read-only, _open() pattern, EXCLUDE SM-self project_slug per G2, degrade to empty). A small glance widget consumes it. No FROZEN touch, no new envelope.' },
  { key: 'health-sparklines', num: 34, group: 'soak',
    file: 'reports/proposals/2026-06-11-session-health-sparklines-confidence-throughput.proposal.md',
    buildNote: 'Confidence + throughput sparklines in each session lane header, sourced from the health-digest endpoint (or existing per-session decision data) with a PAIRED text delta. Client-side render; reuse health-digest read if present, else mock.' },
  { key: 'stale-cleanup', num: 46, group: 'session',
    file: 'reports/proposals/2026-06-11-stale-session-cleanup.proposal.md',
    buildNote: 'Operator soft-delete + restore of stale sessions. Additive ONLY: a guarded sessions.deleted_at column (ALTER ADD if missing) + additive endpoints POST /api/sessions/{id}/archive and /restore. MUST refuse SM-self (project_slug=streamManager) AND firewalled cwd. No FROZEN envelope, no governance.py touch. Soft-delete only (reversible) -- never a hard DELETE.' },
  { key: 'what-changed', num: 49, group: 'monitor',
    file: 'reports/proposals/2026-06-11-what-changed-digest-page-focus.proposal.md',
    buildNote: 'On page visibility/focus regain, a synthesis overlay of what moved since last focus (decisions delta, new sessions, escalations) from the client-side buffered stream. No backend. Gate on $betaFlags["what-changed"].' },
];

// The held-2 (event-cursor + soak-panel), built CONSTRAINED-ADDITIVE so neither
// needs a FROZEN message_bus edit / ADR-18 amendment (see initiative doc 6b).
const HELD_2 = [
  { key: 'event-cursor', num: 31, group: 'session', file: 'reports/proposals/2026-06-11-session-event-append-stream.proposal.md',
    buildNote: 'ADDITIVE ONLY (the vetted footprint is frozenTouch:false). Build a new additive read endpoint GET /api/sessions/{session_id}/events?since=<cursor>&full=0|1 reading existing messages+decisions newer than the cursor (cursor = max decisions.rowid the client has seen; EXCLUDE SM-self via project_slug NOT IN the SM slug set). A ResumeBadge.svelte persists the last-seen cursor in localStorage per session and resumes the decision feed from it on reload (small "resumed N events" badge). NO message_bus.py edit, NO new bus envelope, NO new table. Mount ResumeBadge in App.svelte near the footer connection readout, gated on $betaFlags["event-cursor"].' },
  { key: 'soak-panel', num: 16, group: 'soak', file: 'reports/proposals/2026-06-11-live-session-soak-with-polarity-audit.proposal.md',
    buildNote: 'CONSTRAINED ADDITIVE v1 -- NO new bus envelope, NO message_bus.py edit, NO ADR-18 amendment, NO in-process soak spawn. Build ONLY additive surfaces: (1) an additive soak_runs table in gov.db (soak_id TEXT PK, session_id, project_slug, started_at REAL, status TEXT, polarity_pass INTEGER, rejection_count INTEGER, report_md TEXT) created lazily; (2) GET /api/soak/sessions -- ranked NON-SM candidate sessions (project_slug NOT IN sm slugs AND session_id != self; reject firewalled cwd paths containing certPortal); (3) GET /api/soak/status -- read soak_runs rows; (4) GET /api/soak/polarity-audit -- a READ computation over gov.db proving zero SM-self leakage (PASS/FAIL). A SoakControlPanel.svelte (Frame-D-style right drawer summoned from a footer SOAK affordance) shows a single loud paired label+color POLARITY PASS/FAIL verdict header + the ranked self-excluded session selector with an "excluded: N self / M firewalled" footer + a soak status/report readout (per-band p50/p95 from soak_runs.report_md or mock), default-OFF gated on $betaFlags["soak-panel"]. The live soak LAUNCH (spawn Tier-4 subprocess) is DEFERRED -- render a clearly-labelled NON-functional "Launch from CLI (soak_driver --live-session)" affordance, NOT an in-process spawn (long-running soak is main-thread/r1-owned per feedback_subagent_long_task_abandonment). usedMockData=true so it renders mock when gov.db is empty. NO FROZEN touch -- if you cannot avoid one, set blocked=true.' },
];

// Batch-2 NEW (14): the genuinely-new CONSTRAIN proposals (the ~13 overlaps are
// covered by batch-1 -- see BETA-DEFERRAL-LEDGER.md). All CONSTRAINED-ADDITIVE.
const _BN = 'CONSTRAINED ADDITIVE -- NO message_bus.py edit, NO new bus envelope, NO ADR-18 amendment, NO in-process spawn/cron/subprocess. Component default-OFF gated on $betaFlags["<key>"]; renders nothing + registers no pollers/SSE/timers when OFF. Add additive READ endpoint(s) over existing gov.db (EXCLUDE SM-self project_slug NOT IN sm slugs) and/or an additive table (CREATE TABLE IF NOT EXISTS) only if persistence is needed. Any heavy/live/spawn part (cron, subprocess, live replay engine, audio) is DEFERRED to a documented non-functional "from CLI" affordance, NOT built in-process. usedMockData=true so it renders with mock when gov.db is empty. Match the approved mockup. NO FROZEN touch -- if unavoidable, set blocked=true. ';
const BATCH2_NEW = [
  { key: 'ambient-soak-task', num: 2, group: 'soak', file: 'reports/proposals/2026-06-11-ambient-soak-task.proposal.md', buildNote: _BN + 'A calm read-only AMBIENT OK/WARN polarity badge + drawer with a cadence strip + a ledger of recent ambient runs (additive ambient_runs table or mock). The Cron scheduler itself is deferred.' },
  { key: 'breach-cartography-constrained', num: 5, group: 'monitor', file: 'reports/proposals/2026-06-11-breach-cartography-constrained.proposal.md', buildNote: _BN + 'A transient modal mapping a regression run-up (causal swimlane + temporal scrubber + ranked revert panel; revert is HITL-gated + disabled for SM-self), reading existing decisions.' },
  { key: 'confidence-heatmap-pane', num: 9, group: 'monitor', file: 'reports/proposals/2026-06-11-confidence-heatmap-pane.proposal.md', buildNote: _BN + 'A role x 5-min-bucket confidence heatmap grid in Frame B above the roster; 3 paired encodings per cell (band fill + literal % + glyph); SM-self scope returns empty.' },
  { key: 'cross-session-pattern-audit-apis', num: 11, group: 'hitl', file: 'reports/proposals/2026-06-11-cross-session-pattern-audit-apis.proposal.md', buildNote: _BN + 'A right-edge audit rail of hydrated-rule chips + a focus-trapped drawer with a "would this fire?" read-only probe; reuses existing pattern reads + the existing demote action; SM-self disabled.' },
  { key: 'escalation-timeline-causal-forensics', num: 13, group: 'monitor', file: 'reports/proposals/2026-06-11-escalation-timeline-causal-forensics.proposal.md', buildNote: _BN + 'A Frame-C-gutter escalation count badge that opens a vertical causal timeline spine + a Frame-C-scoped split DecisionDiff/causal overlay; reads existing decisions; never auto-foregrounds.' },
  { key: 'operator-co-pilot-gesture-macros', num: 17, group: 'hitl', file: 'reports/proposals/2026-06-11-operator-co-pilot-gesture-macros.proposal.md', buildNote: _BN + 'One-tap ranked next-action affordances on a HITL row (advisory; route through the EXISTING commit/override path; NEVER auto-act). Client-side over existing suggestion data.' },
  { key: 'recorded-session-replay-forensics', num: 23, group: 'soak', file: 'reports/proposals/2026-06-11-recorded-session-replay-forensics.proposal.md', buildNote: _BN + 'A side-by-side decision-delta replay forensics view over existing recorded decisions (additive read endpoint, EXCLUDE SM-self); the live replay engine is deferred -- v1 diffs stored decisions.' },
  { key: 'session-checkpoint-versioning', num: 26, group: 'session', file: 'reports/proposals/2026-06-11-session-checkpoint-versioning.proposal.md', buildNote: _BN + 'Read-only session checkpoint snapshots for post-mortem drift (additive session_checkpoints table + read endpoint, or mock); no live snapshotting daemon (deferred).' },
  { key: 'session-dna-heatmap-cross-pattern-topology', num: 30, group: 'monitor', file: 'reports/proposals/2026-06-11-session-dna-heatmap-cross-pattern-topology.proposal.md', buildNote: _BN + 'A cross-session pattern-topology heatmap (sessions x patterns, confidence per cell) read from existing patterns/decisions; SM-self excluded; paired in-cell encodings.' },
  { key: 'session-story-panel-narrative-arc', num: 37, group: 'session', file: 'reports/proposals/2026-06-11-session-story-panel-narrative-arc.proposal.md', buildNote: _BN + 'A read-only narrative-arc panel for one session (bi-directional feed linking) computed client-side from the existing decision feed; no new envelope.' },
  { key: 'sonification-escalation-layer', num: 44, group: 'monitor', file: 'reports/proposals/2026-06-11-sonification-escalation-layer.proposal.md', buildNote: _BN + 'A DERIVED audio-cue layer on a real escalation (Web Audio, default-OFF, respects the audible-cue setting); never the primary/only signal (paired with the existing visual escalation). Client-side only.' },
  { key: 'spatial-session-sidebar', num: 45, group: 'session', file: 'reports/proposals/2026-06-11-spatial-session-sidebar.proposal.md', buildNote: _BN + 'A right-rail spatial session overview that COEXISTS with the 3-frame layout (never displaces it); reads the existing session store; client-side.' },
  { key: 'temporal-scrubber-governance-audit', num: 47, group: 'session', file: 'reports/proposals/2026-06-11-temporal-scrubber-governance-audit.proposal.md', buildNote: _BN + 'A Settings-drawer temporal scrubber showing a policy-archaeology replay DIFF between two points over existing decisions (read-only); the live policy-version store is deferred -- v1 diffs the stored decision stream.' },
  { key: 'time-machine-governance-replay', num: 48, group: 'session', file: 'reports/proposals/2026-06-11-time-machine-governance-replay.proposal.md', buildNote: _BN + 'A Settings-drawer counterfactual replay viewer over stored decisions (read-only "what would governance have done" framed from the corpus); the live counterfactual engine is deferred -- v1 replays stored decisions read-only.' },
];

// Batch-3 (4 gap-fill): governance-semantics features. All READ-ONLY/ADVISORY +
// CONSTRAINED-ADDITIVE -- they surface/preview from existing data, NEVER edit the
// rule store / governance.py / call governance.evaluate.
const BATCH3_NEW = [
  { key: 'allow-pattern-auto-graduation', num: 1, group: 'hitl', file: 'reports/proposals/2026-06-11-allow-pattern-auto-graduation.proposal.md', buildNote: _BN + 'READ-ONLY + operator-confirmed. Surface learn-mode patterns eligible to graduate to a static ALLOW rule; a "graduate" affordance is ADVISORY -- it does NOT auto-edit the rule store or governance.py. v1 writes the operator confirmation to an additive proposals/graduations table (or a documented disabled "apply from CLI" affordance), reading candidates from existing patterns. EXCLUDE SM-self.' },
  { key: 'confidence-calibration-loop', num: 8, group: 'monitor', file: 'reports/proposals/2026-06-11-confidence-calibration-loop.proposal.md', buildNote: _BN + 'READ-ONLY calibration view: bucket existing decisions by predicted confidence vs observed outcome (decisions + hitl_overrides), render a calibration curve + reliability readout. Additive read endpoint. NO change to the engine confidence semantics. EXCLUDE SM-self.' },
  { key: 'policy-preview-chip', num: 21, group: 'hitl', file: 'reports/proposals/2026-06-11-policy-preview-chip.proposal.md', buildNote: _BN + 'READ-ONLY "what would governance do" preview from the CORPUS only: for a draft/selected message, show the likely verdict via a corpus pattern lookup over existing decisions/patterns -- NEVER call governance.evaluate / the live engine. Additive read endpoint. MUST exclude SM-self (polarity: never preview against SM-self corpus).' },
  { key: 'regret-mining-override-loop', num: 24, group: 'hitl', file: 'reports/proposals/2026-06-11-regret-mining-override-loop.proposal.md', buildNote: _BN + 'READ-ONLY regret view: surface operator overrides where the override diverged from the engine verdict (read hitl_overrides + decisions), to close the feedback loop ADVISORY-only. Additive read endpoint over hitl_overrides, EXCLUDE SM-self. NO writeback to governance / no rule edit.' },
];

const IN = (args && typeof args === 'object') ? args : {};
// NOTE: Workflow `args` does NOT thread to the script via scriptPath (verified
// 2026-06-11). Set ACTIVE_APPROVED here per run (APPROVED_13 | HELD_2 | BATCH2_NEW | BATCH3_NEW).
// Batch-3 gate (2026-06-13): 3 PASS build now; allow-pattern-auto-graduation is
// HELD (NEEDS-AMENDMENT -- genuinely needs an ADR-18 FROZEN amendment: a new
// `pattern_graduated` envelope + verdict short-circuit; NOT constrained-additive).
const BATCH3_PASS = BATCH3_NEW.filter((x) => x.key !== 'allow-pattern-auto-graduation');
const ACTIVE_APPROVED = BATCH3_PASS;
const APPROVED = (Array.isArray(IN.approved) && IN.approved.length ? IN.approved : ACTIVE_APPROVED).slice(0, 24);
const TARGET = IN.target || 'dashboard/ui-next/';
const MOCK_DIR = IN.mockDir || 'reports/proposals/mockups/';

// ---- schemas ----
const BUILD_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['key', 'blocked', 'newFiles', 'registryEntry'],
  properties: {
    key: { type: 'string' },
    blocked: { type: 'boolean' },
    blockedReason: { type: 'string' },
    newFiles: { type: 'array', items: { type: 'string' } }, // uniquely-named files this build WROTE into the tree
    componentPath: { type: 'string' }, // the main Svelte component path (import target)
    registryEntry: { // appended to lib/beta/registry.js by the MAIN THREAD (already seeded there; confirm match)
      type: 'object', additionalProperties: false,
      required: ['key', 'label', 'description', 'group', 'component', 'defaultEnabled'],
      properties: {
        key: { type: 'string' }, label: { type: 'string' }, description: { type: 'string' },
        group: { type: 'string' }, component: { type: 'string' }, defaultEnabled: { type: 'boolean' },
      },
    },
    backendEndpoints: { type: 'array', items: { // MAIN THREAD appends to server.py serially
      type: 'object', additionalProperties: false,
      required: ['method', 'path', 'code'],
      properties: { method: { type: 'string' }, path: { type: 'string' }, code: { type: 'string' } },
    } },
    apiHelpers: { type: 'array', items: { type: 'string' } }, // lib/api.js helper fns to add (as source)
    newColumnDDL: { type: 'string' }, // additive ALTER/CREATE guarded SQL the main thread applies (if any)
    wireInstruction: { type: 'string' }, // EXACTLY where the component mounts (which Frame/drawer/row + gate)
    playwrightSpec: { type: 'string' }, // a standalone --headed Playwright test (main thread writes+runs it)
    pytestSpec: { type: 'string' }, // targeted backend pytest source (if backend), else ""
    usedMockData: { type: 'boolean' }, // true if the component falls back to mock data when live data absent
    notes: { type: 'string' },
  },
};

const REVIEW_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['key', 'sound', 'checks', 'reasoning'],
  properties: {
    key: { type: 'string' },
    sound: { type: 'boolean' },
    checks: {
      type: 'object', additionalProperties: false,
      required: ['frozen', 'polarity', 'contamination', 'betaGated', 'escapeHatch', 'a11y', 'matchesMockup'],
      properties: {
        frozen: { type: 'string', enum: ['CLEAN', 'TOUCHES-FROZEN'] },
        polarity: { type: 'string', enum: ['CLEAN', 'SM-SELF-LEAK'] },
        contamination: { type: 'string', enum: ['CLEAN', 'MONITORED-VOCAB'] },
        betaGated: { type: 'string', enum: ['GATED-OFF-DEFAULT', 'NOT-GATED'] },
        escapeHatch: { type: 'string', enum: ['NONE', 'DEFERRED-WORK'] },
        a11y: { type: 'string', enum: ['PAIRED-BADGES', 'COLOR-ONLY-SIGNAL'] },
        matchesMockup: { type: 'string', enum: ['MATCHES', 'DIVERGES'] },
      },
    },
    requiredFixes: { type: 'array', items: { type: 'string' } },
    reasoning: { type: 'string' },
  },
};

function buildPrompt(item) {
  const pascal = item.key.split('-').map((p) => p.charAt(0).toUpperCase() + p.slice(1)).join('');
  return `${KINGMODE}

${SAFETY}

BUILD the BETA feature "${item.key}" (#${item.num}). You are in the SHARED working tree (the BETA-flag foundation
-- lib/beta/registry.js, lib/stores/beta.js, lib/components/BetaToggles.svelte, server.py /api/beta/flags -- is
already present, uncommitted). Read these to ground the build:
  - the proposal: ${item.file}
  - the operator-APPROVED mockup (the built UI MUST match it): ${MOCK_DIR}${item.key}.html
  - ${TARGET}src/lib/beta/registry.js + ${TARGET}src/lib/stores/beta.js (the gate idiom: $betaFlags["${item.key}"])
  - ${TARGET}src/styles/theme.css (tokens), ${TARGET}src/lib/api.js, ${TARGET}src/lib/sse.js,
    ${TARGET}src/lib/stores/settings.js, and the relevant Frame/row component you will mount into.

BUILD CONSTRAINTS for this feature: ${item.buildNote}

BUILD RULES (working-tree, collision-free):
- WRITE ONLY your own uniquely-named NEW files. The main component MUST be:
    ${TARGET}src/lib/components/beta/${pascal}.svelte
  Any helper/mock module you add must also live under ${TARGET}src/lib/components/beta/ with a ${pascal}- prefix.
  Do NOT create or edit any other shared file. componentPath = that path. newFiles = every file you wrote.
- The component gates on $betaFlags["${item.key}"]: it renders nothing and registers NO pollers/SSE/timers when
  OFF. It matches the approved mockup, uses theme.css tokens, pairs every state with a TEXT label (never color
  alone), is keyboard-operable, WCAG AAA. When live gov.db data is absent it falls back to realistic mock data
  (set usedMockData=true) so it is testable.
- RETURN (do NOT write) the shared-file edits as DATA:
    registryEntry = {key:"${item.key}", label, description, group:"${item.group}", component:"./components/beta/${pascal}.svelte" (relative to src/lib), defaultEnabled:false}
    backendEndpoints = additive read/POST handlers for dashboard/server.py (full FastAPI fns, read via _open()/
      _open_rw(), defensive, EXCLUDE SM-self project_slug where it queries sessions, no FROZEN touch). [] if none.
    apiHelpers = lib/api.js helper fn source strings the component needs. [] if none.
    newColumnDDL = a guarded additive ALTER/CREATE (e.g. add sessions.deleted_at if missing) if the feature needs
      a new column; else "".
    wireInstruction = EXACTLY where the component mounts in App.svelte / a Frame / a row, wrapped in
      {#if $betaFlags["${item.key}"]}...{/if}.
- RETURN test specs as STRINGS (the MAIN THREAD writes + runs them; do NOT run them yourself):
    playwrightSpec = a standalone Playwright --headed test (CommonJS, like the foundation test) that toggles the
      flag ON (Settings > BETA), asserts the feature renders with (mock) data + the key interaction works, and
      asserts it renders nothing when OFF.
    pytestSpec = a targeted pytest for any backendEndpoints (assert shape + empty-DB degrade + SM-self excluded),
      else "".
- If building correctly REQUIRES a FROZEN edit or a new bus envelope, set blocked=true + blockedReason and STOP.
- Do NOT run npm build / servers / live tests. Do NOT edit shared files. Return the full BUILD object.`;
}

// ===== Stage 1 BUILD -> Stage 2 REFUTE (pipeline; per-feature, shared tree, no worktree) =====
phase('Build');
log(`BUILD (working tree, NO worktree): ${APPROVED.length} approved BETA features -> write own component -> `
  + `2-refuter file review. Foundation already present (uncommitted). Shared-file edits returned as DATA.`);

const processed = await pipeline(
  APPROVED,
  // Stage 1: build (general-purpose; writes its own new files into the shared tree).
  (item) => agent(buildPrompt(item), { label: `build:${item.key}`, phase: 'Build', agentType: 'general-purpose', schema: BUILD_SCHEMA }),

  // Stage 2: 2 refuters READ the written files from the tree + review the returned shared-edit data.
  (build, item) => {
    if (!build) return Promise.resolve(null);
    if (build.blocked) return Promise.resolve({ build, item, votes: [], blocked: true });
    const editData = JSON.stringify({
      key: build.key, componentPath: build.componentPath, newFiles: build.newFiles,
      registryEntry: build.registryEntry, backendEndpoints: build.backendEndpoints || [],
      apiHelpers: build.apiHelpers || [], newColumnDDL: build.newColumnDDL || '',
      wireInstruction: build.wireInstruction || '', usedMockData: build.usedMockData,
    });
    return parallel([0, 1].map((n) => () =>
      agent(`${SAFETY}

Adversarially REVIEW the build of BETA feature "${build.key}" (reviewer ${n}). READ the actual written files from
the working tree (listed in newFiles), and the approved mockup ${MOCK_DIR}${build.key}.html. Returned edit data:
${editData}
Open and read EACH file in newFiles. Check honestly:
- frozen: do the written files OR any returned endpoint/DDL/apiHelper MODIFY or require a FROZEN surface
  (governance.py decision flow, message_bus envelope schema, cli_pool, model_router, LifecycleBridge, wirecli)
  or mint a new bus envelope? CLEAN | TOUCHES-FROZEN.
- polarity: any session query/sweep/soft-delete path missing the SM-self exclusion (project_slug NOT IN
  {streamManager})? CLEAN | SM-SELF-LEAK.
- contamination: any monitored-project vocabulary / JOB-IDs / role names hard-coded (not data-rendered)?
  CLEAN | MONITORED-VOCAB.
- betaGated: is the component gated on $betaFlags["${build.key}"] and inert (no pollers/SSE/timers) when OFF,
  defaultEnabled:false? GATED-OFF-DEFAULT | NOT-GATED.
- escapeHatch: any "deferred to follow-up" / TODO-later for in-scope work in the files? NONE | DEFERRED-WORK.
- a11y: state signals paired label+color (never color alone), keyboard-operable, real native controls?
  PAIRED-BADGES | COLOR-ONLY-SIGNAL.
- matchesMockup: does the built component match the approved mockup's layout + interaction? MATCHES | DIVERGES.
sound=true ONLY if frozen=CLEAN, polarity=CLEAN, contamination=CLEAN, betaGated=GATED-OFF-DEFAULT,
escapeHatch=NONE, a11y=PAIRED-BADGES, matchesMockup=MATCHES. Else list requiredFixes. Give reasoning.`,
        { label: `refute:${item.key}:${n}`, phase: 'Refute', agentType: 'Explore', schema: REVIEW_SCHEMA })
    )).then((votes) => ({ build, item, votes: votes.filter(Boolean), blocked: false }));
  },
);

// ===== Aggregate =====
phase('Assemble');
const rows = processed.filter(Boolean);
const blocked = rows.filter((r) => r.blocked || (r.build && r.build.blocked))
  .map((r) => ({ key: r.build.key, reason: r.build.blockedReason || 'build returned blocked' }));
const reviewed = rows.filter((r) => !r.blocked && r.build && !r.build.blocked);
const shippable = reviewed.filter((r) => r.votes.length === 2 && r.votes.every((v) => v && v.sound));
const needsRepair = reviewed.filter((r) => !(r.votes.length === 2 && r.votes.every((v) => v && v.sound)))
  .map((r) => ({ key: r.build.key, fixes: r.votes.flatMap((v) => (v && v.requiredFixes) || []), reasoning: r.votes.map((v) => v && v.reasoning) }));
const workaroundFlags = reviewed
  .filter((r) => r.build.notes && /workaround|hack|bypass|skip|stub|temporar/i.test(r.build.notes))
  .map((r) => ({ key: r.build.key, note: r.build.notes }));

log(`ASSEMBLE: ${shippable.length}/${APPROVED.length} unanimously-sound; ${needsRepair.length} need repair; ${blocked.length} blocked.`);
if (workaroundFlags.length) log(`WORKAROUND AUDIT: ${workaroundFlags.length} build(s) flagged a workaround -- audit reuse across ALL features before PR.`);

return {
  scope: 'beta-proposals-build (working-tree; foundation uncommitted)',
  counts: { approved: APPROVED.length, shippable: shippable.length, needsRepair: needsRepair.length, blocked: blocked.length },
  // Files are ALREADY written in the tree. Each shippable feature carries the shared-file edits the MAIN THREAD
  // applies SERIALLY (registry entry confirm, backend endpoints, api helpers, DDL, wire instruction) + test specs.
  shippable: shippable.map((r) => ({
    key: r.build.key,
    newFiles: r.build.newFiles,
    componentPath: r.build.componentPath,
    registryEntry: r.build.registryEntry,
    backendEndpoints: r.build.backendEndpoints || [],
    apiHelpers: r.build.apiHelpers || [],
    newColumnDDL: r.build.newColumnDDL || '',
    wireInstruction: r.build.wireInstruction || '',
    playwrightSpec: r.build.playwrightSpec || '',
    pytestSpec: r.build.pytestSpec || '',
    usedMockData: !!r.build.usedMockData,
  })),
  needsRepair,
  blocked,
  workaroundFlags,
  mainThreadGate: {
    note: 'MAIN-THREAD GATE (the main thread IS the gate -- no CI). For the shippable set, SERIALLY: (1) confirm/'
      + 'append each registryEntry in lib/beta/registry.js; (2) append backendEndpoints to server.py + apiHelpers '
      + 'to lib/api.js; (3) apply newColumnDDL; (4) wire each component per wireInstruction (gated on its flag); '
      + '(5) cp1252 scan on ADDED lines; (6) ruff on changed .py; (7) targeted pytest (pytestSpec); (8) npm run '
      + 'build exit 0 + axe 0 serious (scope the BETA panes); (9) Playwright --headed run of each playwrightSpec '
      + 'against a live dashboard (run_in_background if >5min). A feature goes live ONLY with backend + --headed '
      + 'BOTH green. (10) live-session features soak against a CONFIRMED non-SM session (#r1) -- N/A for this 13.',
    perFeaturePR: 'open a PR per file-disjoint cluster citing the proposal #; never commit to main directly.',
  },
};
